"""Handover Package Assembly Service.

Platform: The Handover
Module: Handover Workspace (Module 4 / Knowledge Transfer Area)

Enforces:
1. Deterministic 8-domain compilation engine
2. Strict downstream eligibility verification via HandoverEligibilityService
3. Immutable version snapshots with cryptographic content hashes
4. Four-tier epistemic separation (only human_verified knowledge is eligible)
5. Zero synthetic or unverified claims in published handover content
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import BadRequestError, NotFoundError
from app.core.security import utc_now
from app.models.audit import AuditLog
from app.models.enums import (
    AuditOutcome,
    ConflictResolutionState,
    EpistemicStatus,
    HandoverCaseStatus,
    HandoverLinkType,
    HandoverPackageSectionType,
    KnowledgeCategory,
    KnowledgeReviewStatus,
    RelationshipVerificationStatus,
    VerificationCaseStatus,
    VerificationSeverity,
    VerificationTargetType,
)
from app.models.handover import (
    HandoverCase,
    HandoverContentLink,
    HandoverPackage,
    HandoverPackageSection,
    HandoverPackageVersion,
)
from app.models.knowledge import KnowledgeEvidenceLink, KnowledgeItem
from app.models.relationship import KnowledgeEntity, KnowledgeRelationship, RelationshipEvidenceLink
from app.models.verification import VerificationCase, VerificationConflict, VerificationIssue
from app.repositories.audit import AuditLogRepository
from app.repositories.handover import (
    HandoverCaseRepository,
    HandoverContentLinkRepository,
    HandoverPackageRepository,
    HandoverPackageVersionRepository,
    HandoverSectionRepository,
)
from app.schemas.handover import PackageAssemblyRequest
from app.services.audit import AuditService
from app.services.handover_case import HandoverCaseService
from app.services.handover_eligibility import (
    HandoverEligibilityService,
    check_evidence_accessibility,
)

# Map Knowledge categories to Section types
DOMAIN_CATEGORY_MAP: dict[str, list[str]] = {
    HandoverPackageSectionType.DECISIONS_RATIONALE.value: [
        KnowledgeCategory.DECISIONS_RATIONALE.value,
    ],
    HandoverPackageSectionType.TECHNICAL_ARCHITECTURE.value: [
        KnowledgeCategory.TECHNICAL_ARCHITECTURE.value,
        KnowledgeCategory.ARCHITECTURE_TECHNICAL.value,
    ],
    HandoverPackageSectionType.WORK_PROGRESS.value: [
        KnowledgeCategory.WORK_ITEMS.value,
        KnowledgeCategory.WORK_PROGRESS.value,
    ],
    HandoverPackageSectionType.RESPONSIBILITIES_OWNERSHIP.value: [
        KnowledgeCategory.RESPONSIBILITIES_OWNERSHIP.value,
    ],
    HandoverPackageSectionType.DEPENDENCIES_RELATIONSHIPS.value: [
        KnowledgeCategory.DEPENDENCIES.value,
        KnowledgeCategory.DEPENDENCIES_RELATIONSHIPS.value,
    ],
    HandoverPackageSectionType.BUGS_BLOCKERS_RISKS.value: [
        KnowledgeCategory.BUGS_BLOCKERS_RISKS.value,
        KnowledgeCategory.RISKS_BLOCKERS_QUESTIONS.value,
    ],
    HandoverPackageSectionType.OPERATIONAL_HISTORICAL.value: [
        KnowledgeCategory.OPERATIONAL_HISTORICAL.value,
    ],
    HandoverPackageSectionType.PROJECT_OVERVIEW_CONTEXT.value: [
        KnowledgeCategory.PROJECT_OVERVIEW_CONTEXT.value,
    ],
}

SECTION_TITLES: dict[str, str] = {
    HandoverPackageSectionType.PROJECT_OVERVIEW_CONTEXT.value: "Project Overview & Strategic Context",
    HandoverPackageSectionType.DECISIONS_RATIONALE.value: "Key Architecture & Technical Decisions",
    HandoverPackageSectionType.TECHNICAL_ARCHITECTURE.value: "System Architecture, Services & Schemas",
    HandoverPackageSectionType.WORK_PROGRESS.value: "Active Work, Backlog & In-Flight Tasks",
    HandoverPackageSectionType.RESPONSIBILITIES_OWNERSHIP.value: "Component Ownership & Team Roles",
    HandoverPackageSectionType.DEPENDENCIES_RELATIONSHIPS.value: "Upstream/Downstream Dependencies",
    HandoverPackageSectionType.BUGS_BLOCKERS_RISKS.value: "Known Issues, Blockers & Open Risks",
    HandoverPackageSectionType.OPERATIONAL_HISTORICAL.value: "Operational Procedures & Runbooks",
}

SECTION_ORDER: list[str] = [
    HandoverPackageSectionType.PROJECT_OVERVIEW_CONTEXT.value,
    HandoverPackageSectionType.DECISIONS_RATIONALE.value,
    HandoverPackageSectionType.TECHNICAL_ARCHITECTURE.value,
    HandoverPackageSectionType.WORK_PROGRESS.value,
    HandoverPackageSectionType.RESPONSIBILITIES_OWNERSHIP.value,
    HandoverPackageSectionType.DEPENDENCIES_RELATIONSHIPS.value,
    HandoverPackageSectionType.BUGS_BLOCKERS_RISKS.value,
    HandoverPackageSectionType.OPERATIONAL_HISTORICAL.value,
]

ROLE_SECTION_ORDER: dict[str, list[str]] = {
    "developer": [
        HandoverPackageSectionType.PROJECT_OVERVIEW_CONTEXT.value,
        HandoverPackageSectionType.TECHNICAL_ARCHITECTURE.value,
        HandoverPackageSectionType.WORK_PROGRESS.value,
        HandoverPackageSectionType.DECISIONS_RATIONALE.value,
        HandoverPackageSectionType.DEPENDENCIES_RELATIONSHIPS.value,
        HandoverPackageSectionType.BUGS_BLOCKERS_RISKS.value,
        HandoverPackageSectionType.RESPONSIBILITIES_OWNERSHIP.value,
        HandoverPackageSectionType.OPERATIONAL_HISTORICAL.value,
    ],
    "project_manager": [
        HandoverPackageSectionType.PROJECT_OVERVIEW_CONTEXT.value,
        HandoverPackageSectionType.WORK_PROGRESS.value,
        HandoverPackageSectionType.RESPONSIBILITIES_OWNERSHIP.value,
        HandoverPackageSectionType.BUGS_BLOCKERS_RISKS.value,
        HandoverPackageSectionType.DEPENDENCIES_RELATIONSHIPS.value,
        HandoverPackageSectionType.DECISIONS_RATIONALE.value,
        HandoverPackageSectionType.TECHNICAL_ARCHITECTURE.value,
        HandoverPackageSectionType.OPERATIONAL_HISTORICAL.value,
    ],
    "technical_lead": [
        HandoverPackageSectionType.PROJECT_OVERVIEW_CONTEXT.value,
        HandoverPackageSectionType.DECISIONS_RATIONALE.value,
        HandoverPackageSectionType.TECHNICAL_ARCHITECTURE.value,
        HandoverPackageSectionType.DEPENDENCIES_RELATIONSHIPS.value,
        HandoverPackageSectionType.BUGS_BLOCKERS_RISKS.value,
        HandoverPackageSectionType.RESPONSIBILITIES_OWNERSHIP.value,
        HandoverPackageSectionType.WORK_PROGRESS.value,
        HandoverPackageSectionType.OPERATIONAL_HISTORICAL.value,
    ],
}


class PackageAssemblyService:
    """Orchestrates deterministic compilation of verified project knowledge into handover packages."""

    def __init__(self, session: Session, *, llm_client: Any = None) -> None:
        self.session = session
        self._unused_llm_client = llm_client
        self.case_repo = HandoverCaseRepository(session)
        self.package_repo = HandoverPackageRepository(session)
        self.version_repo = HandoverPackageVersionRepository(session)
        self.section_repo = HandoverSectionRepository(session)
        self.link_repo = HandoverContentLinkRepository(session)
        self.eligibility_service = HandoverEligibilityService(session)
        self.case_service = HandoverCaseService(session)
        self.audit_service = AuditService(audit_repository=AuditLogRepository(session))

    def assemble_package_version(
        self,
        case_id: uuid.UUID,
        *,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        request: PackageAssemblyRequest,
        has_project_manage: bool = True,
    ) -> HandoverPackageVersion:
        """Assemble an immutable handover package version from eligible project knowledge."""
        case = self.case_service.get_case(case_id, project_id=project_id, load_relationships=False)

        # Transition case to ASSEMBLING
        if case.status in (HandoverCaseStatus.DRAFT.value, HandoverCaseStatus.ASSEMBLED.value):
            self.case_service.transition_status(
                case_id,
                project_id=project_id,
                new_status=HandoverCaseStatus.ASSEMBLING.value,
                user_id=user_id,
                change_reason="Starting package compilation",
            )

        # Ensure container package exists
        package = self.package_repo.get_by_case(case.id)
        if not package:
            package = HandoverPackage(
                organisation_id=case.organisation_id,
                project_id=project_id,
                case_id=case.id,
                title=f"Handover Package: {case.title}",
                summary=case.description,
                created_by_user_id=user_id,
            )
            package = self.package_repo.create(package)

        next_version_num = self.version_repo.get_next_version_number(package.id)

        # Query all active knowledge items for the project
        stmt_ki = select(KnowledgeItem).where(
            KnowledgeItem.project_id == project_id,
            KnowledgeItem.is_deleted.is_(False),
        )
        knowledge_items = list(self.session.execute(stmt_ki).scalars().all())

        # Exclusions filter
        exclude_kis = set(request.exclude_knowledge_item_ids or [])
        exclude_rels = set(request.exclude_relationship_ids or [])
        filtered_kis = [ki for ki in knowledge_items if ki.id not in exclude_kis]

        # Query all active relationships for the project
        stmt_rel = select(KnowledgeRelationship).where(
            KnowledgeRelationship.project_id == project_id
        )
        relationships = list(self.session.execute(stmt_rel).scalars().all())
        filtered_rels = [r for r in relationships if r.id not in exclude_rels]

        allow_provisional_draft = bool(
            request.include_provisional_draft
            and case.status
            in (
                HandoverCaseStatus.DRAFT.value,
                HandoverCaseStatus.ASSEMBLING.value,
                HandoverCaseStatus.ASSEMBLED.value,
                HandoverCaseStatus.UNDER_REVIEW.value,
                HandoverCaseStatus.READINESS_ASSESSED.value,
            )
        )

        # Evaluate eligibility for all items
        eligible_items_by_section: dict[str, list[tuple[KnowledgeItem, Any]]] = {
            sec: [] for sec in SECTION_ORDER
        }

        included_ki_ids: list[str] = []
        provisional_ki_ids: list[str] = []
        excluded_ki_ids: list[dict[str, Any]] = []
        exclusion_breakdown: dict[str, int] = {
            "pending_review": 0,
            "conflicted": 0,
            "rejected": 0,
            "missing_evidence": 0,
            "restricted_acl": 0,
            "other": 0,
        }
        sample_verified_items: list[dict[str, Any]] = []

        # Batch preload maps for all projects so assembly never triggers N+1 eligibility queries
        vc_ki_map: dict[uuid.UUID, VerificationCase] = {}
        vc_rel_map: dict[uuid.UUID, VerificationCase] = {}
        open_conflict_vc_ids: set[uuid.UUID] = set()
        blocking_issue_vc_ids: set[uuid.UUID] = set()
        ki_ev_links_map: dict[uuid.UUID, list[uuid.UUID]] = {}
        rel_ev_links_map: dict[uuid.UUID, list[uuid.UUID]] = {}
        accessible_ev_cache: dict[uuid.UUID, bool] = {}

        if filtered_kis or filtered_rels:
            for vc in self.session.execute(
                select(VerificationCase).where(
                    VerificationCase.project_id == project_id,
                )
            ).scalars().all():
                if vc.target_type == VerificationTargetType.KNOWLEDGE_ITEM.value:
                    vc_ki_map[vc.target_id] = vc
                elif vc.target_type == VerificationTargetType.RELATIONSHIP.value:
                    vc_rel_map[vc.target_id] = vc

            open_conflict_vc_ids = set(
                self.session.execute(
                    select(VerificationConflict.case_id).where(
                        VerificationConflict.project_id == project_id,
                        VerificationConflict.resolution_state == ConflictResolutionState.UNRESOLVED.value,
                    )
                ).scalars().all()
            )
            blocking_issue_vc_ids = set(
                self.session.execute(
                    select(VerificationIssue.case_id).where(
                        VerificationIssue.project_id == project_id,
                        VerificationIssue.resolution_state == "open",
                        VerificationIssue.severity.in_(
                            [VerificationSeverity.CRITICAL.value, VerificationSeverity.HIGH.value]
                        ),
                    )
                ).scalars().all()
            )
            all_ev_ids_set: set[uuid.UUID] = set()
            for row_ki_id, row_ev_id in self.session.execute(
                select(KnowledgeEvidenceLink.knowledge_item_id, KnowledgeEvidenceLink.evidence_id).where(
                    KnowledgeEvidenceLink.project_id == project_id
                )
            ).all():
                ki_ev_links_map.setdefault(row_ki_id, []).append(row_ev_id)
                all_ev_ids_set.add(row_ev_id)
            for row_rel_id, row_ev_id in self.session.execute(
                select(RelationshipEvidenceLink.relationship_id, RelationshipEvidenceLink.evidence_id).where(
                    RelationshipEvidenceLink.project_id == project_id
                )
            ).all():
                rel_ev_links_map.setdefault(row_rel_id, []).append(row_ev_id)
                all_ev_ids_set.add(row_ev_id)

            if all_ev_ids_set:
                cached_policies = self.eligibility_service._get_policies(project_id)
                _, inacc_list = check_evidence_accessibility(
                    self.session,
                    list(all_ev_ids_set),
                    project_id=project_id,
                    viewer_user_id=user_id,
                    has_project_manage=has_project_manage,
                    cached_policies=cached_policies,
                )
                inacc_set = set(inacc_list)
                for ev_id in all_ev_ids_set:
                    accessible_ev_cache[ev_id] = ev_id not in inacc_set

        for ki in filtered_kis:
            if ki.review_status == KnowledgeReviewStatus.REJECTED.value:
                exclusion_breakdown["rejected"] += 1
                excluded_ki_ids.append({
                    "id": str(ki.id),
                    "title": ki.title or str(ki.id),
                    "blockers": ["Knowledge item was rejected during verification review."],
                })
                continue

            if getattr(ki, "is_stale", False):
                exclusion_breakdown["other"] += 1
                excluded_ki_ids.append({
                    "id": str(ki.id),
                    "title": ki.title or str(ki.id),
                    "blockers": ["Knowledge item is marked stale."],
                })
                continue

            is_ki_meta_verified = (
                ki.epistemic_status == EpistemicStatus.HUMAN_VERIFIED.value
                and ki.review_status == KnowledgeReviewStatus.APPROVED.value
            )

            if not is_ki_meta_verified and not allow_provisional_draft:
                exclusion_breakdown["pending_review"] += 1
                excluded_ki_ids.append({
                    "id": str(ki.id),
                    "title": ki.title or str(ki.id),
                    "blockers": ["Knowledge item is not human-verified and approved."],
                })
                continue

            vc = vc_ki_map.get(ki.id)
            vc_status = vc.case_status if vc else "missing_case"
            has_open_conflict = bool(vc and vc.id in open_conflict_vc_ids)
            has_blocking_issue = bool(vc and vc.id in blocking_issue_vc_ids)
            ev_ids = ki_ev_links_map.get(ki.id, [])
            ev_ok = bool(ev_ids) and all(accessible_ev_cache.get(eid, False) for eid in ev_ids)

            if not allow_provisional_draft:
                if vc is None:
                    exclusion_breakdown["pending_review"] += 1
                    excluded_ki_ids.append({
                        "id": str(ki.id),
                        "title": ki.title or str(ki.id),
                        "blockers": ["No active verification case found for this knowledge item."],
                    })
                    continue
                if vc_status != VerificationCaseStatus.VERIFIED.value:
                    exclusion_breakdown["pending_review"] += 1
                    excluded_ki_ids.append({
                        "id": str(ki.id),
                        "title": ki.title or str(ki.id),
                        "blockers": [f"Verification case is in status '{vc_status}', expected 'verified'."],
                    })
                    continue
                if has_blocking_issue:
                    exclusion_breakdown["other"] += 1
                    excluded_ki_ids.append({
                        "id": str(ki.id),
                        "title": ki.title or str(ki.id),
                        "blockers": ["There are unresolved blocking verification issues."],
                    })
                    continue

            if not ev_ids:
                exclusion_breakdown["missing_evidence"] += 1
                excluded_ki_ids.append({
                    "id": str(ki.id),
                    "title": ki.title or str(ki.id),
                    "blockers": ["Knowledge item has no supporting evidence links attached."],
                })
                continue
            if not ev_ok:
                exclusion_breakdown["restricted_acl"] += 1
                excluded_ki_ids.append({
                    "id": str(ki.id),
                    "title": ki.title or str(ki.id),
                    "blockers": ["Viewer lacks access to supporting evidence source(s)."],
                })
                continue
            if has_open_conflict:
                exclusion_breakdown["conflicted"] += 1
                excluded_ki_ids.append({
                    "id": str(ki.id),
                    "title": ki.title or str(ki.id),
                    "blockers": ["Unresolved cross-source conflict."],
                })
                continue

            strict_eligible = (
                is_ki_meta_verified
                and vc_status == VerificationCaseStatus.VERIFIED.value
                and not has_blocking_issue
            )
            matched_section = HandoverPackageSectionType.PROJECT_OVERVIEW_CONTEXT.value
            for sec_type, categories in DOMAIN_CATEGORY_MAP.items():
                if ki.category in categories:
                    matched_section = sec_type
                    break
            link_meta = {
                "is_eligible": strict_eligible,
                "is_provisional_draft": not strict_eligible,
                "case_status": vc_status,
                "epistemic_status": ki.epistemic_status if strict_eligible else EpistemicStatus.EXTRACTED.value,
            }
            eligible_items_by_section[matched_section].append((ki, link_meta))
            if strict_eligible:
                included_ki_ids.append(str(ki.id))
                if len(sample_verified_items) < 5:
                    sample_verified_items.append({
                        "id": str(ki.id),
                        "title": ki.title or "Verified Finding",
                        "category": ki.category,
                        "review_status": ki.review_status,
                        "epistemic_status": ki.epistemic_status,
                    })
            else:
                provisional_ki_ids.append(str(ki.id))
                exclusion_breakdown["pending_review"] += 1

        # Evaluate eligibility for relationships using preloaded maps
        eligible_rels_by_section: dict[str, list[tuple[KnowledgeRelationship, Any]]] = {
            sec: [] for sec in SECTION_ORDER
        }
        for rel in filtered_rels:
            if rel.verification_status in (
                RelationshipVerificationStatus.REJECTED.value,
                "rejected",
            ) or getattr(rel, "is_stale", False):
                continue

            if not allow_provisional_draft:
                if rel.verification_status != RelationshipVerificationStatus.VERIFIED.value:
                    continue
                r_vc = vc_rel_map.get(rel.id)
                if r_vc is None or r_vc.case_status != VerificationCaseStatus.VERIFIED.value:
                    continue

            r_ev_ids = rel_ev_links_map.get(rel.id, [])
            if not r_ev_ids or not all(accessible_ev_cache.get(eid, False) for eid in r_ev_ids):
                continue

            is_rel_verified = rel.verification_status == RelationshipVerificationStatus.VERIFIED.value
            eligible_rels_by_section[
                HandoverPackageSectionType.DEPENDENCIES_RELATIONSHIPS.value
            ].append((
                rel,
                {
                    "is_eligible": is_rel_verified,
                    "is_provisional_draft": not is_rel_verified,
                    "case_status": "verified" if is_rel_verified else "candidate",
                },
            ))

        handover_type = str((case.metadata_json or {}).get("handover_type") or "developer").lower()
        ordered_sections = ROLE_SECTION_ORDER.get(handover_type, SECTION_ORDER)

        # Build snapshot data
        snapshot_data: dict[str, Any] = {
            "version_number": next_version_num,
            "assembled_at": utc_now().isoformat(),
            "assembled_by_user_id": str(user_id),
            "project_id": str(project_id),
            "case_id": str(case_id),
            "handover_type": handover_type,
            "generation_method": "deterministic_knowledge_composition",
            "include_provisional_draft": allow_provisional_draft,
            "is_test_draft": allow_provisional_draft,
            "total_eligible_knowledge_items": len(included_ki_ids),
            "total_provisional_knowledge_items": len(provisional_ki_ids),
            "total_excluded_knowledge_items": len(excluded_ki_ids),
            "exclusion_breakdown": exclusion_breakdown,
            "sample_verified_items": sample_verified_items,
            "excluded_items": excluded_ki_ids[:100],
            "domains_included": request.include_domains or ordered_sections,
        }

        # Create Version record
        version = HandoverPackageVersion(
            organisation_id=case.organisation_id,
            project_id=project_id,
            package_id=package.id,
            case_id=case.id,
            version_number=next_version_num,
            is_current=True,
            assembly_status="assembled",
            assembly_snapshot_json=snapshot_data,
            assembled_by_user_id=user_id,
            assembled_at=utc_now(),
            notes=request.assembly_notes,
        )
        created_version = self.version_repo.create(version)
        self.version_repo.set_current(package.id, created_version.id)

        # Deterministic, composed section compilation (zero Ollama/LLM calls)
        from app.services.handover_composer import classify_finding, _format_item_bullets as _fmt_composed
        from app.schemas.handover import (
            HandoverSectionKnowledgeItemResponse as _SecKIRsp,
            HandoverVerificationSummaryResponse as _VerifRsp,
        )

        entity_name_map: dict[uuid.UUID, str] = {}
        if any(eligible_rels_by_section.values()):
            for eid, cname in self.session.execute(
                select(KnowledgeEntity.id, KnowledgeEntity.canonical_name).where(
                    KnowledgeEntity.project_id == project_id
                )
            ).all():
                entity_name_map[eid] = cname

        def _elig_json(elig_obj: Any, *, default_ep: str) -> dict[str, Any]:
            if isinstance(elig_obj, dict):
                return dict(elig_obj)
            return {
                "is_eligible": getattr(elig_obj, "is_eligible", False),
                "is_provisional_draft": False,
                "case_status": getattr(elig_obj, "case_status", "verified"),
                "epistemic_status": getattr(elig_obj, "epistemic_status", default_ep),
            }

        section_hashes: list[str] = []

        for order, sec_type in enumerate(SECTION_ORDER, start=1):
            if request.include_domains and sec_type not in request.include_domains:
                continue

            sec_items = eligible_items_by_section.get(sec_type, [])
            sec_rels = eligible_rels_by_section.get(sec_type, [])

            verified_cnt = sum(1 for _, el in sec_items if _elig_json(el, default_ep="human_verified").get("is_eligible"))
            prov_cnt = len(sec_items) - verified_cnt

            content_lines: list[str] = [
                f"# {SECTION_TITLES[sec_type]}",
                "",
            ]
            if allow_provisional_draft:
                content_lines.append(
                    f"Composed from {verified_cnt} human-verified and {prov_cnt} provisional finding(s), "
                    f"and {len(sec_rels)} relationship(s)."
                )
            else:
                content_lines.append(
                    f"Compiled {len(sec_items)} human-approved knowledge items and {len(sec_rels)} verified relationships."
                )
            content_lines.append("")

            if not sec_items and not sec_rels:
                content_lines.append("Insufficient approved information for this section.")
                content_lines.append("")
            else:
                # Build lightweight DTOs so persisted Markdown is also grouped cleanly
                manifest_pkgs: list[str] = []
                commit_groups: dict[str, list[str]] = {}
                author_counts: dict[str, int] = {}
                substantive_lines: list[str] = []

                for ki, elig in sec_items:
                    ej = _elig_json(elig, default_ep=ki.epistemic_status)
                    is_ver = bool(ej.get("is_eligible"))
                    dto = _SecKIRsp(
                        id=ki.id,
                        content_link_id=ki.id,
                        title=ki.title or "Finding",
                        content=ki.structured_summary or "",
                        category=ki.category,
                        epistemic_status=ki.epistemic_status if is_ver else "extracted",
                        review_status=ki.review_status if is_ver else "pending_review",
                        support_classification=ki.support_classification,
                        normalised_status=ki.normalised_status,
                        owner_label=ki.person_or_owner_label,
                        structured_payload=ki.structured_payload or {},
                        created_at=ki.created_at,
                        updated_at=ki.updated_at,
                        verification=_VerifRsp(case_status="verified" if is_ver else "candidate"),
                    )
                    meta = classify_finding(dto)
                    kind = meta["kind"]
                    if kind == "manifest_dependency":
                        manifest_pkgs.append(f"{meta['package']} ({meta['version']})" if meta.get("version") else meta["package"])
                    elif kind == "raw_commit":
                        ws = meta.get("workstream") or "Core Changes"
                        sha = meta.get("sha") or ""
                        subj = meta.get("subject") or dto.title
                        commit_groups.setdefault(ws, []).append(f"`@{sha[:8]}` {subj}" if sha else subj)
                    elif kind == "commit_author":
                        auth = meta.get("author") or "Contributor"
                        author_counts[auth] = author_counts.get(auth, 0) + 1
                    else:
                        tag = "" if is_ver else " *(Provisional — Pending Review)*"
                        substantive_lines.append(f"### {dto.title}{tag}")
                        if dto.content:
                            substantive_lines.append(dto.content)
                        substantive_lines.append("")

                content_lines.extend(substantive_lines)
                if commit_groups:
                    content_lines.append("### Grouped Repository Workstreams")
                    for ws, msgs in commit_groups.items():
                        content_lines.append(f"- **{ws}** ({len(msgs)} commit(s)): " + "; ".join(msgs[:5]))
                    content_lines.append("")
                if author_counts:
                    content_lines.append("### Historical Commit Authors (Distinct from Ownership)")
                    for auth, cnt in sorted(author_counts.items(), key=lambda x: -x[1]):
                        content_lines.append(f"- **{auth}**: {cnt} commit(s)")
                    content_lines.append("")
                if manifest_pkgs:
                    uniq_pkgs = sorted(set(manifest_pkgs))
                    content_lines.append(f"### Declared Packages ({len(uniq_pkgs)} unique)")
                    content_lines.append(", ".join(uniq_pkgs[:60]))
                    content_lines.append("")

            structural_rels = [
                (r, e)
                for r, e in sec_rels
                if r.relationship_type not in {"BELONGS_TO_WORK_CLUSTER", "AUTHORED_BY", "CONFIGURED_IN"}
            ]
            for rel, _ in structural_rels[:40]:
                s_name = entity_name_map.get(rel.source_entity_id, str(rel.source_entity_id))
                t_name = entity_name_map.get(rel.target_entity_id, str(rel.target_entity_id))
                content_lines.append(f"- **Relationship**: **{s_name}** `{rel.relationship_type}` **{t_name}**")

            section_text = "\n".join(content_lines)
            sec_hash = hashlib.sha256(section_text.encode("utf-8")).hexdigest()
            section_hashes.append(sec_hash)

            section = HandoverPackageSection(
                organisation_id=case.organisation_id,
                project_id=project_id,
                version_id=created_version.id,
                section_type=sec_type,
                section_title=SECTION_TITLES[sec_type],
                section_content=section_text,
                content_summary=f"{len(sec_items)} findings ({verified_cnt} verified, {prov_cnt} provisional), {len(sec_rels)} relationships.",
                section_order=order,
                knowledge_item_count=len(sec_items),
                relationship_count=len(sec_rels),
                metadata_json={
                    "sha256": sec_hash,
                    "llm_used": False,
                    "handover_type": handover_type,
                    "generation_method": "deterministic_knowledge_composition",
                    "include_provisional_draft": allow_provisional_draft,
                    "is_test_draft": allow_provisional_draft,
                },
            )
            created_section = self.section_repo.create(section)

            # Create Content Links for Knowledge Items
            links_to_create: list[HandoverContentLink] = []
            for ki, elig in sec_items:
                links_to_create.append(
                    HandoverContentLink(
                        organisation_id=case.organisation_id,
                        project_id=project_id,
                        section_id=created_section.id,
                        version_id=created_version.id,
                        link_type=HandoverLinkType.KNOWLEDGE_ITEM.value,
                        knowledge_item_id=ki.id,
                        eligibility_status_json=_elig_json(elig, default_ep=ki.epistemic_status),
                    )
                )

            # Create Content Links for Relationships
            for rel, elig in sec_rels:
                ej_rel = (
                    elig
                    if isinstance(elig, dict)
                    else {
                        "is_eligible": getattr(elig, "is_eligible", False),
                        "case_status": getattr(elig, "case_status", "verified"),
                    }
                )
                links_to_create.append(
                    HandoverContentLink(
                        organisation_id=case.organisation_id,
                        project_id=project_id,
                        section_id=created_section.id,
                        version_id=created_version.id,
                        link_type=HandoverLinkType.RELATIONSHIP.value,
                        relationship_id=rel.id,
                        eligibility_status_json=ej_rel,
                    )
                )

            if links_to_create:
                self.link_repo.create_bulk(links_to_create)

        # Compute version-level content hash
        version_hash = hashlib.sha256("".join(section_hashes).encode("utf-8")).hexdigest()
        created_version.content_hash = version_hash

        # Stage 6 package integrity guard: assembling a new version supersedes any prior
        # approvals on older versions (preserving original signoff rows immutably)
        if next_version_num > 1:
            from app.models.handover import HandoverSignoff

            prior_signoffs = list(
                self.session.execute(
                    select(HandoverSignoff).where(
                        HandoverSignoff.case_id == case.id,
                        HandoverSignoff.version_id != created_version.id,
                        HandoverSignoff.is_superseded.is_(False),
                    )
                )
                .scalars()
                .all()
            )
            if prior_signoffs:
                for sig in prior_signoffs:
                    sig.is_superseded = True
                self.audit_service.record_event(
                    event_type="handover.signoff.superseded_by_new_version",
                    resource_type="handover_case",
                    resource_id=str(case.id),
                    actor_user_id=user_id,
                    organisation_id=case.organisation_id,
                    project_id=project_id,
                    outcome=AuditOutcome.SUCCESS.value,
                    metadata={
                        "case_id": str(case.id),
                        "new_version_id": str(created_version.id),
                        "new_version_number": next_version_num,
                        "superseded_signoff_count": len(prior_signoffs),
                    },
                )

        # Transition Case to ASSEMBLED
        if case.status != HandoverCaseStatus.ASSEMBLED.value:
            self.case_service.transition_status(
                case_id,
                project_id=project_id,
                new_status=HandoverCaseStatus.ASSEMBLED.value,
                user_id=user_id,
                change_reason=f"Assembled package version {created_version.version_number}",
            )

        self.audit_service.record_event(
            event_type="handover.package.assembled",
            resource_type="handover_package_version",
            resource_id=str(created_version.id),
            actor_user_id=user_id,
            organisation_id=case.organisation_id,
            project_id=project_id,
            outcome=AuditOutcome.SUCCESS.value,
            metadata={
                "version_number": next_version_num,
                "content_hash": version_hash,
                "eligible_items_count": len(included_ki_ids),
                "excluded_items_count": len(excluded_ki_ids),
            },
        )

        self.session.flush()
        from app.services.handover_sections import invalidate_handover_sections_cache

        invalidate_handover_sections_cache(project_id)
        return created_version
