"""Read-Only Canonical Handover Section Retrieval & Provenance Hydration Service.

Platform: The Handover
Module: Handover Workspace (Module 4 / Knowledge Transfer Area)

Provides read-only hydration of persisted HandoverPackageSection records and
HandoverContentLink provenance chains for a specific handover case and immutable
package version while enforcing:
1. Strict project & case scoping (prevents cross-project/cross-case leakage)
2. Fail-closed read-time source ACL checks via check_evidence_accessibility()
3. Four-tier epistemic separation (never upgrades unverified or conflicted items)
4. Defensive secret redaction on displayed content (Domain 8 & all domains)
5. Zero mutation of persisted versions, sections, or hashes
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import NotFoundError
from app.models.enums import (
    ConflictResolutionState,
    EpistemicStatus,
    HandoverLinkType,
    HandoverPackageSectionType,
    KnowledgeReviewStatus,
    ProjectMembershipStatus,
    VerificationTargetType,
)
from app.models.evidence import EvidenceItem
from app.models.handover import (
    HandoverCase,
    HandoverContentLink,
    HandoverPackageSection,
    HandoverPackageVersion,
    HandoverResponsibilityTransfer,
)
from app.models.integration import SourceAccessPolicy
from app.models.knowledge import KnowledgeEvidenceLink, KnowledgeItem
from app.models.project import Project, ProjectMembership
from app.models.relationship import (
    KnowledgeEntity,
    KnowledgeRelationship,
    RelationshipEvidenceLink,
)
from app.models.user import User
from app.models.verification import (
    VerificationCase,
    VerificationConflict,
    VerificationReviewEvent,
)
from app.repositories.handover import HandoverPackageVersionRepository
from app.schemas.handover import (
    HandoverContentLinkResponse,
    HandoverDomainEpistemicBreakdown,
    HandoverEvidenceProvenanceResponse,
    HandoverPackageVersionResponse,
    HandoverSectionConflictItemResponse,
    HandoverSectionDetailResponse,
    HandoverSectionKnowledgeItemResponse,
    HandoverSectionRelationshipResponse,
    HandoverVerificationSummaryResponse,
    HandoverVersionSectionsResponse,
)
from app.services.handover_assembly import DOMAIN_CATEGORY_MAP, SECTION_ORDER
from app.services.handover_eligibility import check_evidence_accessibility

_SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"-----BEGIN [A-Z0-9 ]+ PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9 ]+ PRIVATE KEY-----"), "[REDACTED_PRIVATE_KEY]"),
    (re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{20,}\b"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"), "[REDACTED_GITHUB_PAT]"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), "[REDACTED_SLACK_TOKEN]"),
    (re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"), "[REDACTED_API_KEY]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED_AWS_KEY]"),
    (re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9\-._~+/]+=*"), r"\1 [REDACTED_TOKEN]"),
    (
        re.compile(r"(?i)\b(password|passwd|api_key|apikey|secret_key|client_secret|access_token|refresh_token|private_key)\s*[:=]\s*['\"]?[^\s'\",;]{6,}['\"]?"),
        r"\1=[REDACTED]",
    ),
]


def redact_secrets(text: str | None) -> str:
    """Defensively redact credential or token patterns from displayed text."""
    if not text:
        return ""
    cleaned = text
    for pattern, replacement in _SECRET_PATTERNS:
        cleaned = pattern.sub(replacement, cleaned)
    return cleaned


def _redact_payload(value: Any) -> Any:
    """Recursively redact secrets from structured JSON payloads for safe display."""
    if isinstance(value, str):
        return redact_secrets(value)
    if isinstance(value, list):
        return [_redact_payload(v) for v in value]
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for k, v in value.items():
            key_lower = str(k).lower()
            if any(tok in key_lower for tok in ("password", "secret", "token", "api_key", "private_key", "credential")):
                redacted[k] = "[REDACTED]"
            else:
                redacted[k] = _redact_payload(v)
        return redacted
    return value


def _extract_confidence(ki: KnowledgeItem) -> float | None:
    meta = ki.confidence_metadata_json or {}
    for key in ("confidence_score", "confidence", "score"):
        val = meta.get(key)
        if isinstance(val, (int, float)):
            return float(val) if val <= 1.0 else round(float(val) / 100.0, 3)
    return None


def _map_category_to_section(category: str) -> str:
    for sec_type, categories in DOMAIN_CATEGORY_MAP.items():
        if category in categories:
            return sec_type
    return HandoverPackageSectionType.PROJECT_OVERVIEW_CONTEXT.value


class HandoverSectionReadService:
    """Pure read-only service hydrating canonical handover sections with provenance and ACL checks."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.version_repo = HandoverPackageVersionRepository(session)

    def get_version_sections(
        self,
        case_id: uuid.UUID,
        version_id: uuid.UUID,
        *,
        project_id: uuid.UUID,
        viewer_user_id: uuid.UUID,
        has_project_manage: bool = False,
    ) -> HandoverVersionSectionsResponse:
        """Retrieve all persisted canonical sections for a specific case and package version."""
        version = self.version_repo.get_by_id(version_id, load_sections=True)
        if not version or version.project_id != project_id or version.case_id != case_id:
            raise NotFoundError("Handover package version not found for this case and project.")

        sections_sorted = sorted(version.sections, key=lambda s: (s.section_order, s.section_type))
        present_types = {s.section_type for s in sections_sorted}
        missing_types = [sec_t for sec_t in SECTION_ORDER if sec_t not in present_types]

        # Gather all linked IDs across sections
        linked_ki_ids: set[uuid.UUID] = set()
        linked_rel_ids: set[uuid.UUID] = set()
        for sec in sections_sorted:
            for link in sec.content_links:
                if link.link_type == HandoverLinkType.KNOWLEDGE_ITEM.value and link.knowledge_item_id:
                    linked_ki_ids.add(link.knowledge_item_id)
                elif link.link_type == HandoverLinkType.RELATIONSHIP.value and link.relationship_id:
                    linked_rel_ids.add(link.relationship_id)

        # Load linked KnowledgeItems with their evidence links
        ki_map: dict[uuid.UUID, KnowledgeItem] = {}
        if linked_ki_ids:
            ki_stmt = (
                select(KnowledgeItem)
                .where(
                    KnowledgeItem.id.in_(linked_ki_ids),
                    KnowledgeItem.project_id == project_id,
                )
                .options(selectinload(KnowledgeItem.evidence_links))
            )
            for ki in self.session.execute(ki_stmt).scalars().all():
                ki_map[ki.id] = ki

        # Load linked KnowledgeRelationships with entities & evidence links
        rel_map: dict[uuid.UUID, KnowledgeRelationship] = {}
        if linked_rel_ids:
            rel_stmt = (
                select(KnowledgeRelationship)
                .where(
                    KnowledgeRelationship.id.in_(linked_rel_ids),
                    KnowledgeRelationship.project_id == project_id,
                )
                .options(
                    selectinload(KnowledgeRelationship.source_entity),
                    selectinload(KnowledgeRelationship.target_entity),
                    selectinload(KnowledgeRelationship.evidence_links),
                )
            )
            for rel in self.session.execute(rel_stmt).scalars().all():
                rel_map[rel.id] = rel

        # Gather all referenced EvidenceItem IDs for a single batched ACL check + lookup
        all_evidence_ids: set[uuid.UUID] = set()
        for ki in ki_map.values():
            for el in ki.evidence_links:
                all_evidence_ids.add(el.evidence_id)
        for rel in rel_map.values():
            for rel_el in rel.evidence_links:
                all_evidence_ids.add(rel_el.evidence_id)

        cached_policies = list(
            self.session.execute(
                select(SourceAccessPolicy).where(SourceAccessPolicy.project_id == project_id)
            )
            .scalars()
            .all()
        )
        _, inaccessible_evidence_list = check_evidence_accessibility(
            self.session,
            list(all_evidence_ids),
            project_id=project_id,
            viewer_user_id=viewer_user_id,
            has_project_manage=has_project_manage,
            cached_policies=cached_policies,
        )
        inaccessible_evidence_ids = set(inaccessible_evidence_list)

        evidence_map: dict[uuid.UUID, EvidenceItem] = {}
        if all_evidence_ids:
            ev_stmt = select(EvidenceItem).where(
                EvidenceItem.id.in_(all_evidence_ids),
                EvidenceItem.project_id == project_id,
                EvidenceItem.deleted_at.is_(None),
            )
            for ev in self.session.execute(ev_stmt).scalars().all():
                evidence_map[ev.id] = ev

        # Load VerificationCases & latest VerificationReviewEvent for linked KnowledgeItems
        vc_map: dict[uuid.UUID, VerificationCase] = {}
        reviewer_user_ids: set[uuid.UUID] = set()
        if linked_ki_ids:
            vc_stmt = (
                select(VerificationCase)
                .where(
                    VerificationCase.project_id == project_id,
                    VerificationCase.target_type == VerificationTargetType.KNOWLEDGE_ITEM.value,
                    VerificationCase.target_id.in_(linked_ki_ids),
                )
                .options(selectinload(VerificationCase.review_events))
            )
            for vc in self.session.execute(vc_stmt).scalars().all():
                vc_map[vc.target_id] = vc
                if vc.review_events:
                    reviewer_user_ids.add(vc.review_events[0].reviewer_user_id)
                if vc.assigned_reviewer_id:
                    reviewer_user_ids.add(vc.assigned_reviewer_id)

        # Load Users needed for verification attribution & ownership context
        user_map: dict[uuid.UUID, User] = {}
        if reviewer_user_ids:
            u_stmt = select(User).where(User.id.in_(reviewer_user_ids))
            for u in self.session.execute(u_stmt).scalars().all():
                user_map[u.id] = u

        # Load project-wide epistemic counts (read-only transparency, never upgrades unverified items)
        all_project_kis = list(
            self.session.execute(
                select(
                    KnowledgeItem.id,
                    KnowledgeItem.category,
                    KnowledgeItem.epistemic_status,
                    KnowledgeItem.review_status,
                    KnowledgeItem.is_stale,
                    KnowledgeItem.superseded_by_id,
                ).where(
                    KnowledgeItem.project_id == project_id,
                    KnowledgeItem.is_deleted.is_(False),
                )
            ).all()
        )
        domain_epistemic: dict[str, dict[str, int]] = {
            sec_t: {
                "human_verified_included": 0,
                "pending_verification": 0,
                "rejected": 0,
                "unresolved_conflicts": 0,
                "resolved_conflicts": 0,
                "outdated": 0,
            }
            for sec_t in SECTION_ORDER
        }
        for row in all_project_kis:
            sec_t = _map_category_to_section(row.category)
            bucket = domain_epistemic.setdefault(
                sec_t,
                {
                    "human_verified_included": 0,
                    "pending_verification": 0,
                    "rejected": 0,
                    "unresolved_conflicts": 0,
                    "resolved_conflicts": 0,
                    "outdated": 0,
                },
            )
            if row.id in linked_ki_ids:
                bucket["human_verified_included"] += 1
            elif row.is_stale or row.superseded_by_id is not None:
                bucket["outdated"] += 1
            elif row.review_status == KnowledgeReviewStatus.REJECTED.value:
                bucket["rejected"] += 1
            elif (
                row.epistemic_status != EpistemicStatus.HUMAN_VERIFIED.value
                or row.review_status != KnowledgeReviewStatus.APPROVED.value
            ):
                bucket["pending_verification"] += 1

        # Load project VerificationConflicts (separated strictly from verified items)
        conflict_stmt = (
            select(VerificationConflict)
            .where(VerificationConflict.project_id == project_id)
            .order_by(VerificationConflict.updated_at.desc())
        )
        project_conflicts = list(self.session.execute(conflict_stmt).scalars().all())
        unresolved_conflict_items: list[HandoverSectionConflictItemResponse] = []
        resolved_conflict_items: list[HandoverSectionConflictItemResponse] = []
        for cf in project_conflicts:
            res_state = str(cf.resolution_state.value if hasattr(cf.resolution_state, "value") else cf.resolution_state)
            cf_type = str(cf.conflict_type.value if hasattr(cf.conflict_type, "value") else cf.conflict_type)
            item = HandoverSectionConflictItemResponse(
                id=cf.id,
                verification_case_id=cf.case_id,
                conflict_type=cf_type,
                priority=str(cf.priority or "medium"),
                resolution_state=res_state,
                explanation=redact_secrets(cf.explanation),
                claim_a_text=redact_secrets(cf.claim_a_text),
                claim_b_text=redact_secrets(cf.claim_b_text),
                side_a_source_title=cf.side_a_source_title,
                side_b_source_title=cf.side_b_source_title,
                authoritative_claim_text=redact_secrets(cf.authoritative_claim_text) if cf.authoritative_claim_text else None,
                resolution_notes=redact_secrets(cf.resolution_notes) if cf.resolution_notes else None,
                resolved_at=cf.resolved_at,
                updated_at=cf.updated_at,
            )
            if res_state in (
                ConflictResolutionState.RESOLVED.value,
                ConflictResolutionState.DISMISSED.value,
            ):
                resolved_conflict_items.append(item)
            else:
                unresolved_conflict_items.append(item)

        bugs_key = HandoverPackageSectionType.BUGS_BLOCKERS_RISKS.value
        domain_epistemic[bugs_key]["unresolved_conflicts"] = len(unresolved_conflict_items)
        domain_epistemic[bugs_key]["resolved_conflicts"] = len(resolved_conflict_items)

        # Load real Project, HandoverCase, active ProjectMemberships, and ResponsibilityTransfers
        project = self.session.get(Project, project_id)
        case = version.case or self.session.get(HandoverCase, case_id)

        memberships_stmt = (
            select(ProjectMembership)
            .where(
                ProjectMembership.project_id == project_id,
                ProjectMembership.status == ProjectMembershipStatus.ACTIVE.value,
            )
            .options(
                selectinload(ProjectMembership.user),
                selectinload(ProjectMembership.role),
            )
        )
        active_memberships = list(self.session.execute(memberships_stmt).scalars().all())
        team_members_ctx = [
            {
                "user_id": str(m.user_id),
                "full_name": m.user.full_name if m.user else None,
                "email": m.user.email if m.user else None,
                "role_name": m.role.name if m.role else "member",
                "responsibility_description": m.responsibility_description,
                "is_departing_member": bool(case and case.departing_member_id == m.user_id),
                "is_successor": bool(case and case.successor_id == m.user_id),
            }
            for m in active_memberships
        ]

        transfers_stmt = (
            select(HandoverResponsibilityTransfer)
            .where(
                HandoverResponsibilityTransfer.case_id == case_id,
                HandoverResponsibilityTransfer.project_id == project_id,
            )
            .options(
                selectinload(HandoverResponsibilityTransfer.current_owner),
                selectinload(HandoverResponsibilityTransfer.proposed_successor),
            )
            .order_by(HandoverResponsibilityTransfer.created_at.asc())
        )
        resp_transfers = list(self.session.execute(transfers_stmt).scalars().all())
        transfers_ctx = [
            {
                "id": str(t.id),
                "responsibility_description": t.responsibility_description,
                "knowledge_domain": t.knowledge_domain,
                "transfer_status": t.transfer_status,
                "transfer_notes": t.transfer_notes,
                "current_owner_id": str(t.current_owner_id),
                "current_owner_name": t.current_owner.full_name if t.current_owner else None,
                "proposed_successor_id": str(t.proposed_successor_id) if t.proposed_successor_id else None,
                "proposed_successor_name": t.proposed_successor.full_name if t.proposed_successor else None,
            }
            for t in resp_transfers
        ]

        # Build hydrated sections
        hydrated_sections: list[HandoverSectionDetailResponse] = []
        for sec in sections_sorted:
            sec_kis: list[HandoverSectionKnowledgeItemResponse] = []
            sec_rels: list[HandoverSectionRelationshipResponse] = []
            content_links_out = [
                HandoverContentLinkResponse.model_validate(link) for link in sec.content_links
            ]

            for link in sec.content_links:
                if link.link_type == HandoverLinkType.KNOWLEDGE_ITEM.value and link.knowledge_item_id:
                    ki = ki_map.get(link.knowledge_item_id)
                    if not ki:
                        continue
                    provenance_list = self._build_ki_provenance(
                        ki.evidence_links, evidence_map, inaccessible_evidence_ids
                    )
                    vc = vc_map.get(ki.id)
                    verif_summary = self._build_verification_summary(vc, user_map)
                    sec_kis.append(
                        HandoverSectionKnowledgeItemResponse(
                            id=ki.id,
                            content_link_id=link.id,
                            title=redact_secrets(ki.title),
                            content=redact_secrets(ki.structured_summary),
                            category=ki.category,
                            epistemic_status=ki.epistemic_status,
                            review_status=ki.review_status,
                            support_classification=ki.support_classification,
                            normalised_status=ki.normalised_status,
                            owner_label=ki.person_or_owner_label,
                            structured_payload=_redact_payload(ki.structured_payload or {}),
                            confidence_score=_extract_confidence(ki),
                            is_stale=bool(ki.is_stale),
                            created_at=ki.created_at,
                            updated_at=ki.updated_at,
                            source_observed_at=ki.source_observed_at,
                            eligibility=link.eligibility_status_json or {},
                            verification=verif_summary,
                            provenance=provenance_list,
                            provenance_available=len(provenance_list) > 0,
                        )
                    )
                elif link.link_type == HandoverLinkType.RELATIONSHIP.value and link.relationship_id:
                    rel = rel_map.get(link.relationship_id)
                    if not rel:
                        continue
                    rel_prov = self._build_rel_provenance(
                        rel.evidence_links, evidence_map, inaccessible_evidence_ids
                    )
                    sec_rels.append(
                        HandoverSectionRelationshipResponse(
                            id=rel.id,
                            content_link_id=link.id,
                            relationship_type=rel.relationship_type,
                            source_entity_id=rel.source_entity_id,
                            source_entity_name=(
                                rel.source_entity.canonical_name
                                if rel.source_entity
                                else str(rel.source_entity_id)
                            ),
                            source_entity_type=(
                                rel.source_entity.entity_type if rel.source_entity else "entity"
                            ),
                            target_entity_id=rel.target_entity_id,
                            target_entity_name=(
                                rel.target_entity.canonical_name
                                if rel.target_entity
                                else str(rel.target_entity_id)
                            ),
                            target_entity_type=(
                                rel.target_entity.entity_type if rel.target_entity else "entity"
                            ),
                            verification_status=rel.verification_status,
                            confidence_score=float(rel.confidence_score or 1.0),
                            is_stale=bool(rel.is_stale),
                            reviewed_at=rel.reviewed_at,
                            eligibility=link.eligibility_status_json or {},
                            provenance=rel_prov,
                            provenance_available=len(rel_prov) > 0,
                        )
                    )

            domain_context: dict[str, Any] = {}
            if sec.section_type == HandoverPackageSectionType.PROJECT_OVERVIEW_CONTEXT.value:
                domain_context = {
                    "project_name": project.name if project else None,
                    "project_description": project.description if project else None,
                    "project_status": project.status if project else None,
                    "start_date": (
                        project.start_date.isoformat()
                        if project and project.start_date
                        else None
                    ),
                    "target_completion_date": (
                        project.target_completion_date.isoformat()
                        if project and project.target_completion_date
                        else None
                    ),
                    "case_title": case.title if case else None,
                    "case_description": case.description if case else None,
                    "case_status": case.status if case else None,
                    "case_metadata": (case.metadata_json or {}) if case else {},
                }
            elif sec.section_type == HandoverPackageSectionType.RESPONSIBILITIES_OWNERSHIP.value:
                domain_context = {
                    "team_members": team_members_ctx,
                    "responsibility_transfers": transfers_ctx,
                }

            sec_unresolved = (
                unresolved_conflict_items
                if sec.section_type == HandoverPackageSectionType.BUGS_BLOCKERS_RISKS.value
                else []
            )
            sec_resolved = (
                resolved_conflict_items
                if sec.section_type == HandoverPackageSectionType.BUGS_BLOCKERS_RISKS.value
                else []
            )
            ep_counts = domain_epistemic.get(
                sec.section_type,
                {
                    "human_verified_included": len(sec_kis),
                    "pending_verification": 0,
                    "rejected": 0,
                    "unresolved_conflicts": 0,
                    "resolved_conflicts": 0,
                    "outdated": 0,
                },
            )

            hydrated_sections.append(
                HandoverSectionDetailResponse(
                    id=sec.id,
                    version_id=sec.version_id,
                    section_type=sec.section_type,
                    section_title=sec.section_title,
                    section_content=redact_secrets(sec.section_content),
                    content_summary=sec.content_summary,
                    section_order=sec.section_order,
                    knowledge_item_count=sec.knowledge_item_count,
                    relationship_count=sec.relationship_count,
                    metadata_json=sec.metadata_json or {},
                    created_at=sec.created_at,
                    updated_at=sec.created_at,
                    content_links=content_links_out,
                    knowledge_items=sec_kis,
                    relationships=sec_rels,
                    unresolved_conflicts=sec_unresolved,
                    resolved_conflicts=sec_resolved,
                    epistemic_breakdown=HandoverDomainEpistemicBreakdown(**ep_counts),
                    domain_context=domain_context,
                )
            )

        # Aggregate project-level epistemic summary across all 8 domains
        summary = HandoverDomainEpistemicBreakdown(
            human_verified_included=sum(d["human_verified_included"] for d in domain_epistemic.values()),
            pending_verification=sum(d["pending_verification"] for d in domain_epistemic.values()),
            rejected=sum(d["rejected"] for d in domain_epistemic.values()),
            unresolved_conflicts=len(unresolved_conflict_items),
            resolved_conflicts=len(resolved_conflict_items),
            outdated=sum(d["outdated"] for d in domain_epistemic.values()),
        )

        version_res = HandoverPackageVersionResponse(
            id=version.id,
            package_id=version.package_id,
            version_number=version.version_number,
            assembly_status=version.assembly_status,
            assembly_notes=version.notes,
            notes=version.notes,
            content_hash=version.content_hash,
            assembly_snapshot_json=version.assembly_snapshot_json,
            assembled_by_user_id=version.assembled_by_user_id,
            assembled_at=version.assembled_at,
            is_current=version.is_current,
            created_at=version.created_at,
        )

        return HandoverVersionSectionsResponse(
            case_id=case_id,
            project_id=project_id,
            version=version_res,
            sections=hydrated_sections,
            missing_section_types=missing_types,
            epistemic_summary=summary,
        )

    def _build_ki_provenance(
        self,
        links: list[KnowledgeEvidenceLink],
        evidence_map: dict[uuid.UUID, EvidenceItem],
        inaccessible_ids: set[uuid.UUID],
    ) -> list[HandoverEvidenceProvenanceResponse]:
        out: list[HandoverEvidenceProvenanceResponse] = []
        for el in links:
            if el.evidence_id in inaccessible_ids:
                out.append(
                    HandoverEvidenceProvenanceResponse(
                        evidence_id=el.evidence_id,
                        source_type="restricted",
                        source_provider=None,
                        source_name="Restricted Source (Source ACL Protected)",
                        source_reference=None,
                        source_url=None,
                        author=None,
                        source_timestamp=None,
                        extracted_at=None,
                        support_type=el.support_type,
                        supporting_excerpt=None,
                        acl_restricted=True,
                    )
                )
                continue
            ev = evidence_map.get(el.evidence_id)
            if not ev:
                continue
            out.append(
                HandoverEvidenceProvenanceResponse(
                    evidence_id=ev.id,
                    source_type=ev.source_type,
                    source_provider=ev.source_provider,
                    source_name=ev.title or ev.original_filename or ev.source_external_id,
                    source_reference=ev.source_external_id,
                    source_url=ev.source_url,
                    author=ev.source_author_identity,
                    source_timestamp=ev.source_created_at or ev.source_updated_at,
                    extracted_at=ev.extracted_at,
                    support_type=el.support_type,
                    supporting_excerpt=redact_secrets(el.supporting_excerpt),
                    acl_restricted=False,
                )
            )
        return out

    def _build_rel_provenance(
        self,
        links: list[RelationshipEvidenceLink],
        evidence_map: dict[uuid.UUID, EvidenceItem],
        inaccessible_ids: set[uuid.UUID],
    ) -> list[HandoverEvidenceProvenanceResponse]:
        out: list[HandoverEvidenceProvenanceResponse] = []
        for el in links:
            if el.evidence_id in inaccessible_ids:
                out.append(
                    HandoverEvidenceProvenanceResponse(
                        evidence_id=el.evidence_id,
                        source_type="restricted",
                        source_provider=None,
                        source_name="Restricted Source (Source ACL Protected)",
                        source_reference=None,
                        source_url=None,
                        author=None,
                        source_timestamp=None,
                        extracted_at=None,
                        support_type=el.evidence_role,
                        supporting_excerpt=None,
                        acl_restricted=True,
                    )
                )
                continue
            ev = evidence_map.get(el.evidence_id)
            if not ev:
                continue
            out.append(
                HandoverEvidenceProvenanceResponse(
                    evidence_id=ev.id,
                    source_type=ev.source_type,
                    source_provider=ev.source_provider,
                    source_name=ev.title or ev.original_filename or ev.source_external_id,
                    source_reference=ev.source_external_id,
                    source_url=ev.source_url,
                    author=ev.source_author_identity,
                    source_timestamp=ev.source_created_at or ev.source_updated_at,
                    extracted_at=ev.extracted_at,
                    support_type=el.evidence_role,
                    supporting_excerpt=redact_secrets(el.supporting_excerpt) if el.supporting_excerpt else None,
                    acl_restricted=False,
                )
            )
        return out

    def _build_verification_summary(
        self,
        vc: VerificationCase | None,
        user_map: dict[uuid.UUID, User],
    ) -> HandoverVerificationSummaryResponse:
        if not vc:
            return HandoverVerificationSummaryResponse()
        latest_event: VerificationReviewEvent | None = vc.review_events[0] if vc.review_events else None
        reviewer_id = latest_event.reviewer_user_id if latest_event else vc.assigned_reviewer_id
        reviewer = user_map.get(reviewer_id) if reviewer_id else None
        case_status = str(vc.case_status.value if hasattr(vc.case_status, "value") else vc.case_status)
        decision = None
        if latest_event:
            decision = str(
                latest_event.action.value
                if hasattr(latest_event.action, "value")
                else latest_event.action
            )
        return HandoverVerificationSummaryResponse(
            verification_case_id=vc.id,
            case_status=case_status,
            reviewer_decision=decision,
            reviewed_by_user_id=reviewer_id,
            reviewed_by_name=(reviewer.full_name or reviewer.email) if reviewer else None,
            reviewed_at=(latest_event.created_at if latest_event else vc.last_reviewed_at),
            review_notes=(
                redact_secrets(latest_event.review_notes or latest_event.decision_reason)
                if latest_event and (latest_event.review_notes or latest_event.decision_reason)
                else None
            ),
        )
