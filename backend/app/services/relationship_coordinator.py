"""Full relationship reconstruction coordinator service.

Coordinates the complete cross-source relationship pipeline:
1. Entity seeding from KnowledgeItems and Evidence metadata
2. Exact identifier discovery (Method 1)
3. Structured connector discovery (Method 2)
4. Contextual path discovery (Method 3)
5. Optional Qwen3 8B LLM discovery (Method 5)
6. Identity resolution and deduplication
7. Decision-to-implementation traceability indexing
8. Timeline event generation
9. Reconstruction run progress and telemetry tracking
"""

from __future__ import annotations

import logging
import time
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.enums import (
    EntityType,
    EpistemicStatus,
    EvidenceSourceType,
    KnowledgeCategory,
    KnowledgeReviewStatus,
    RelationshipBasis,
    RelationshipRunStatus,
    RelationshipType,
    TimelineOrigin,
    TimelinePrecision,
)
from app.models.evidence import EvidenceChunk, EvidenceItem
from app.models.knowledge import KnowledgeItem
from app.models.project import Project
from app.models.relationship import KnowledgeEntity, RelationshipReconstructionRun
from app.repositories.relationship import (
    EntityRepository,
    RelationshipRepository,
    RelationshipRunRepository,
    TimelineRepository,
)
from app.services.identity_resolution import IdentityResolutionService
from app.services.llm import StructuredLLMClient
from app.services.relationship_discovery import (
    DiscoveredRelationshipDraft,
    RelationshipDiscoveryEngine,
)
from app.services.technology_manifest_parser import (
    canonicalize_technology_name,
    extract_known_technologies_from_text,
    is_known_technology,
    is_manifest_path,
    parse_manifest_evidence,
)
from app.services.traceability import DecisionTraceabilityService

logger = logging.getLogger("app.services.relationship_coordinator")

# Mapping from KnowledgeCategory to EntityType
_CATEGORY_TO_ENTITY_TYPE: dict[str, str] = {
    KnowledgeCategory.DECISIONS_RATIONALE.value: EntityType.DECISION.value,
    KnowledgeCategory.TECHNICAL_ARCHITECTURE.value: EntityType.TECHNICAL_COMPONENT.value,
    KnowledgeCategory.WORK_ITEMS.value: EntityType.WORK_ITEM.value,
    KnowledgeCategory.BUGS_BLOCKERS_RISKS.value: EntityType.RISK.value,
    KnowledgeCategory.DEPENDENCIES.value: EntityType.DEPENDENCY.value,
    KnowledgeCategory.OPERATIONAL_HISTORICAL.value: EntityType.DOCUMENT.value,
    KnowledgeCategory.RESPONSIBILITIES_OWNERSHIP.value: EntityType.PERSON.value,
    KnowledgeCategory.PROJECT_OVERVIEW_CONTEXT.value: EntityType.DOCUMENT.value,
}

_NON_COMPONENT_CONCEPTUAL_TOKENS = {
    "user personas",
    "workflow design",
    "stakeholder ecosystem",
    "conceptual guidance",
    "personas",
    "design concepts",
    "business rules",
    "user persona",
    "user personas and workflow",
    "personas and workflow",
}


class RelationshipCoordinatorService:
    """Coordinates full asynchronous or on-demand relationship graph reconstruction."""

    def __init__(
        self,
        session: Session,
        *,
        llm_client: StructuredLLMClient | None = None,
    ) -> None:
        self._session = session
        self._entity_repo = EntityRepository(session)
        self._rel_repo = RelationshipRepository(session)
        self._run_repo = RelationshipRunRepository(session)
        self._timeline_repo = TimelineRepository(session)
        self._discovery_engine = RelationshipDiscoveryEngine(session, llm_client=llm_client)
        self._identity_service = IdentityResolutionService(session)
        self._traceability_service = DecisionTraceabilityService(session)

    def seed_entities_from_project_evidence(
        self,
        *,
        organisation_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> int:
        """Seed canonical KnowledgeEntity and evidence-backed graph records from persisted data."""
        seeded = 0
        seen_people: dict[str, KnowledgeEntity] = {}
        pending_drafts: list[DiscoveredRelationshipDraft] = []

        # 0. Canonical Project root entity
        project_row = self._session.get(Project, project_id)
        project_entity = self._entity_repo.create_or_get_entity(
            organisation_id=organisation_id,
            project_id=project_id,
            entity_type=EntityType.PROJECT.value,
            canonical_name=(project_row.name if project_row else "Project")[:255],
            description=(project_row.description if project_row else None),
            source_provider="platform",
        )
        seeded += 1

        def _ensure_person(raw_name: str, source_provider: str, *, is_synthetic: bool = False, extra_aliases: list[str] | None = None) -> KnowledgeEntity | None:
            cleaned = (raw_name or "").strip()
            if len(cleaned) <= 1:
                return None
            norm_owner = cleaned.lower()
            if norm_owner not in seen_people:
                p_ent = self._entity_repo.create_or_get_entity(
                    organisation_id=organisation_id,
                    project_id=project_id,
                    entity_type=EntityType.PERSON.value,
                    canonical_name=cleaned[:255],
                    source_provider=source_provider,
                    is_synthetic=is_synthetic,
                )
                self._entity_repo.add_alias(
                    entity_id=p_ent.id,
                    organisation_id=organisation_id,
                    project_id=project_id,
                    alias_value=cleaned[:255],
                    source_provider=source_provider,
                    is_synthetic=is_synthetic,
                )
                seen_people[norm_owner] = p_ent
            p_ent = seen_people[norm_owner]
            for al in extra_aliases or []:
                al_c = (al or "").strip()
                if len(al_c) > 1 and al_c.lower() != norm_owner:
                    self._entity_repo.add_alias(
                        entity_id=p_ent.id,
                        organisation_id=organisation_id,
                        project_id=project_id,
                        alias_value=al_c[:255],
                        source_provider=source_provider,
                        is_synthetic=is_synthetic,
                    )
            return p_ent

        def _derive_implementation_basis(k: KnowledgeItem, evidence_items_by_id: dict[uuid.UUID, EvidenceItem]) -> str:
            if k.is_stale:
                return "superseded"
            if k.epistemic_status == EpistemicStatus.HUMAN_VERIFIED.value or k.review_status == KnowledgeReviewStatus.APPROVED.value:
                return "verified_implementation"
            norm_stat = (k.normalised_status or "").lower()
            combined_text = f"{k.title} {k.structured_summary}".lower()
            if norm_stat in {"proposed", "planned", "draft", "candidate"} or any(
                w in combined_text for w in ("future ", "plans to ", "planned", "pursue ", "phase 2", "roadmap")
            ):
                return "proposed"
            # Check supporting evidence types — markdown docs stored in GitHub are NOT implementation evidence
            has_impl_evidence = False
            for lnk in k.evidence_links or []:
                ev = evidence_items_by_id.get(lnk.evidence_id)
                if ev and (
                    ev.category in {"commit", "pull_request", "source_code"}
                    or is_manifest_path(ev.title)
                ):
                    has_impl_evidence = True
                    break
            return "implementation_evidenced" if has_impl_evidence else "documented_only"

        def _extract_short_label(title: str, fallback: str) -> str:
            # Prefer concise identifier before ':' or '-' if title is sentence-like
            t = (title or "").strip()
            if len(t) <= 64:
                return t
            if ":" in t[:64]:
                return t.split(":", 1)[0].strip()[:64]
            return t[:64].rsplit(" ", 1)[0].strip() or fallback

        # Preload active EvidenceItems for provenance checks and manifest parsing
        evidence_items = list(
            self._session.execute(
                select(EvidenceItem)
                .options(selectinload(EvidenceItem.content))
                .where(
                    EvidenceItem.project_id == project_id,
                    EvidenceItem.deleted_at.is_(None),
                )
            )
            .scalars()
            .all()
        )
        ev_by_id: dict[uuid.UUID, EvidenceItem] = {ev.id: ev for ev in evidence_items}

        # 1. Seed from non-stale, non-deleted KnowledgeItems using structured payloads
        k_items = list(
            self._session.execute(
                select(KnowledgeItem)
                .options(selectinload(KnowledgeItem.evidence_links))
                .where(
                    KnowledgeItem.project_id == project_id,
                    KnowledgeItem.is_deleted.is_(False),
                    KnowledgeItem.is_stale.is_(False),
                )
            )
            .scalars()
            .all()
        )

        comp_entities_by_ev: dict[uuid.UUID, list[KnowledgeEntity]] = {}
        feature_proc_candidates: list[
            tuple[KnowledgeEntity, uuid.UUID | None, float, str, str, uuid.UUID]
        ] = []
        seen_project_tech_pairs: set[tuple[uuid.UUID, uuid.UUID]] = set()
        seen_comp_tech_pairs: set[tuple[uuid.UUID, uuid.UUID]] = set()
        seen_repo_pairs: set[tuple[uuid.UUID, uuid.UUID]] = set()
        seen_doc_tech_pairs: set[tuple[uuid.UUID, uuid.UUID]] = set()

        def _record_technology(
            *,
            raw_tech: str,
            canon_name: str,
            stack_cat: str,
            usage_basis: str,
            summary: str,
            k_item: KnowledgeItem,
            ev_id: uuid.UUID | None,
            conf: float,
            rel_basis: str,
            first_excerpt: str,
            comp_entities: list[KnowledgeEntity] | None = None,
            version: str | None = None,
            role_in_project: str | None = None,
            usage_status: str | None = None,
        ) -> KnowledgeEntity | None:
            nonlocal seeded
            if not canon_name:
                return None
            tech_meta: dict[str, Any] = {
                "technology_category": stack_cat,
                "usage_basis": usage_basis,
                "purpose": (role_in_project or summary[:280]) if (role_in_project or summary) else None,
                "verification_status": k_item.review_status,
            }
            resolved_ver = version or (getattr(k_item, "structured_payload", None) or {}).get("version")
            if resolved_ver:
                tech_meta["version"] = resolved_ver
            if role_in_project:
                tech_meta["role_in_project"] = role_in_project
            if usage_status:
                tech_meta["usage_status"] = usage_status
            t_ent = self._entity_repo.create_or_get_entity(
                organisation_id=organisation_id,
                project_id=project_id,
                entity_type=EntityType.TECHNOLOGY.value,
                canonical_name=canon_name[:255],
                description=summary,
                primary_knowledge_item_id=k_item.id,
                primary_evidence_id=ev_id,
                confidence_score=conf,
                metadata_json=tech_meta,
                first_observed_at=k_item.created_at,
                last_observed_at=k_item.updated_at,
                is_synthetic=k_item.is_synthetic,
            )
            if raw_tech.strip() and raw_tech.strip().lower() != canon_name.lower():
                self._entity_repo.add_alias(
                    entity_id=t_ent.id,
                    organisation_id=organisation_id,
                    project_id=project_id,
                    alias_value=raw_tech.strip()[:255],
                    source_provider="knowledge_extraction",
                    is_synthetic=k_item.is_synthetic,
                )
            seeded += 1
            if ev_id is not None:
                if (project_entity.id, t_ent.id) not in seen_project_tech_pairs:
                    seen_project_tech_pairs.add((project_entity.id, t_ent.id))
                    pending_drafts.append(
                        DiscoveredRelationshipDraft(
                            source_entity_id=project_entity.id,
                            target_entity_id=t_ent.id,
                            relationship_type=RelationshipType.USES_TECHNOLOGY.value,
                            relationship_basis=rel_basis,
                            confidence_score=conf,
                            discovery_method="knowledge_payload",
                            evidence_id=ev_id,
                            evidence_chunk_id=None,
                            knowledge_item_id=k_item.id,
                            supporting_excerpt=first_excerpt,
                            source_location_json={"source": "knowledge_item"},
                        )
                    )
                for c_ent in comp_entities or []:
                    if c_ent.id == t_ent.id:
                        continue
                    if c_ent.canonical_name.strip().lower() == t_ent.canonical_name.strip().lower():
                        continue
                    c_canon = c_ent.canonical_name.strip().lower()
                    if c_canon in {"postgresql", "chromadb", "supabase", "ollama", "sqlite"}:
                        continue
                    if (c_ent.id, t_ent.id) not in seen_comp_tech_pairs:
                        seen_comp_tech_pairs.add((c_ent.id, t_ent.id))
                        pending_drafts.append(
                            DiscoveredRelationshipDraft(
                                source_entity_id=c_ent.id,
                                target_entity_id=t_ent.id,
                                relationship_type=RelationshipType.USES_TECHNOLOGY.value,
                                relationship_basis=rel_basis,
                                confidence_score=conf,
                                discovery_method="knowledge_payload",
                                evidence_id=ev_id,
                                evidence_chunk_id=None,
                                knowledge_item_id=k_item.id,
                                supporting_excerpt=first_excerpt,
                                source_location_json={"component": c_ent.canonical_name},
                            )
                        )
            return t_ent

        def _tech_usage_basis(impl_basis: str) -> str:
            if impl_basis == "proposed":
                return "proposed"
            if impl_basis == "verified_implementation":
                return "verified"
            if impl_basis == "implementation_evidenced":
                return "implemented"
            return "documented"

        for k in k_items:
            ev_id = k.evidence_links[0].evidence_id if getattr(k, "evidence_links", None) else None
            first_excerpt = (
                k.evidence_links[0].supporting_excerpt
                if getattr(k, "evidence_links", None)
                else k.structured_summary[:240]
            )
            conf = float((getattr(k, "confidence_metadata_json", None) or {}).get("confidence_score", 0.85))
            meta = dict(getattr(k, "structured_payload", None) or {})
            summary = getattr(k, "structured_summary", "")
            impl_basis = _derive_implementation_basis(k, ev_by_id)
            usage_basis = _tech_usage_basis(impl_basis)
            rel_basis = (
                RelationshipBasis.HUMAN_CONFIRMED.value
                if k.epistemic_status == EpistemicStatus.HUMAN_VERIFIED.value
                else RelationshipBasis.EXPLICIT.value
            )
            graph_classes = set(str(g).upper() for g in (meta.get("graph_classifications") or []))

            # 1.0 Explicit Graph-Structured Details from Qwen3 / Validator
            tech_det = meta.get("technology_details")
            if isinstance(tech_det, dict) and tech_det.get("technology_name"):
                raw_tname = str(tech_det["technology_name"]).strip()
                canon_tname, detected_cat, _etype = canonicalize_technology_name(raw_tname)
                final_tname = canon_tname or raw_tname
                final_cat = str(tech_det.get("technology_category") or detected_cat or "technology").lower()
                raw_ustatus = str(tech_det.get("usage_status") or "UNKNOWN").upper()
                _ustatus_map = {
                    "DECLARED_DEPENDENCY": "declared_dependency",
                    "DIRECTLY_EVIDENCED_USE": "implemented",
                    "DOCUMENTED_PLANNED": "documented_planned",
                    "DEPRECATED_OR_REMOVED": "deprecated",
                    "MENTIONED_ONLY": "mentioned",
                    "UNKNOWN": usage_basis,
                }
                mapped_ubasis = _ustatus_map.get(raw_ustatus, usage_basis)
                assoc_comp_entities: list[KnowledgeEntity] = []
                assoc_comp_name = str(tech_det.get("associated_component") or "").strip()
                if assoc_comp_name and assoc_comp_name.lower() not in _NON_COMPONENT_CONCEPTUAL_TOKENS:
                    ac_ent = self._entity_repo.create_or_get_entity(
                        organisation_id=organisation_id,
                        project_id=project_id,
                        entity_type=EntityType.TECHNICAL_COMPONENT.value,
                        canonical_name=assoc_comp_name[:255],
                        primary_evidence_id=ev_id,
                        is_synthetic=k.is_synthetic,
                    )
                    assoc_comp_entities.append(ac_ent)
                _record_technology(
                    raw_tech=raw_tname,
                    canon_name=final_tname,
                    stack_cat=final_cat,
                    usage_basis=mapped_ubasis,
                    summary=summary,
                    k_item=k,
                    ev_id=ev_id,
                    conf=conf,
                    rel_basis=rel_basis,
                    first_excerpt=first_excerpt,
                    comp_entities=assoc_comp_entities or None,
                    version=(str(tech_det.get("version") or "").strip() or None),
                    role_in_project=(str(tech_det.get("role_in_project") or "").strip() or None),
                    usage_status=raw_ustatus,
                )

            arch_det = meta.get("architecture_details")
            if isinstance(arch_det, dict) and arch_det.get("component_name"):
                acomp_name = str(arch_det["component_name"]).strip()
                if acomp_name.lower() not in _NON_COMPONENT_CONCEPTUAL_TOKENS:
                    ac_ent = self._entity_repo.create_or_get_entity(
                        organisation_id=organisation_id,
                        project_id=project_id,
                        entity_type=EntityType.TECHNICAL_COMPONENT.value,
                        canonical_name=acomp_name[:255],
                        description=str(arch_det.get("component_responsibility") or summary),
                        primary_knowledge_item_id=k.id,
                        primary_evidence_id=ev_id,
                        confidence_score=conf,
                        metadata_json={
                            "component_type": arch_det.get("component_type"),
                            "implementation_status": arch_det.get("implementation_status") or impl_basis,
                            "verification_status": k.review_status,
                        },
                        first_observed_at=k.created_at,
                        last_observed_at=k.updated_at,
                        is_synthetic=k.is_synthetic,
                    )
                    seeded += 1
                    if ev_id is not None:
                        comp_entities_by_ev.setdefault(ev_id, []).append(ac_ent)
                        pending_drafts.append(
                            DiscoveredRelationshipDraft(
                                source_entity_id=project_entity.id,
                                target_entity_id=ac_ent.id,
                                relationship_type=RelationshipType.INTEGRATES_WITH.value,
                                relationship_basis=rel_basis,
                                confidence_score=conf,
                                discovery_method="knowledge_payload",
                                evidence_id=ev_id,
                                evidence_chunk_id=None,
                                knowledge_item_id=k.id,
                                supporting_excerpt=first_excerpt,
                                source_location_json={"component": ac_ent.canonical_name},
                            )
                        )
                        for atech in arch_det.get("associated_technologies") or []:
                            if isinstance(atech, str) and atech.strip():
                                c_tn, s_cat, _et = canonicalize_technology_name(atech.strip())
                                _record_technology(
                                    raw_tech=atech.strip(),
                                    canon_name=c_tn or atech.strip(),
                                    stack_cat=s_cat or "technology",
                                    usage_basis=usage_basis,
                                    summary=summary,
                                    k_item=k,
                                    ev_id=ev_id,
                                    conf=conf,
                                    rel_basis=rel_basis,
                                    first_excerpt=first_excerpt,
                                    comp_entities=[ac_ent],
                                )
                        src_c = str(arch_det.get("source_component") or "").strip()
                        dst_c = str(arch_det.get("target_component") or "").strip()
                        raw_rtype = str(arch_det.get("relationship_type") or "").strip().lower()
                        if src_c and dst_c and src_c.lower() != dst_c.lower():
                            _arch_rel_map = {
                                "calls": RelationshipType.CALLS.value,
                                "reads_from": RelationshipType.READS_FROM.value,
                                "writes_to": RelationshipType.WRITES_TO.value,
                                "depends_on": RelationshipType.DEPENDS_ON.value,
                                "integrates_with": RelationshipType.INTEGRATES_WITH.value,
                                "sends_events_to": RelationshipType.INTEGRATES_WITH.value,
                                "processes": RelationshipType.INTEGRATES_WITH.value,
                                "authenticates_through": RelationshipType.DEPENDS_ON.value,
                                "deploys_to": RelationshipType.INTEGRATES_WITH.value,
                            }
                            mapped_rtype = _arch_rel_map.get(raw_rtype, RelationshipType.INTEGRATES_WITH.value)
                            src_ent_c = self._entity_repo.create_or_get_entity(
                                organisation_id=organisation_id,
                                project_id=project_id,
                                entity_type=EntityType.TECHNICAL_COMPONENT.value,
                                canonical_name=src_c[:255],
                                primary_evidence_id=ev_id,
                                is_synthetic=k.is_synthetic,
                            )
                            dst_ent_c = self._entity_repo.create_or_get_entity(
                                organisation_id=organisation_id,
                                project_id=project_id,
                                entity_type=EntityType.TECHNICAL_COMPONENT.value,
                                canonical_name=dst_c[:255],
                                primary_evidence_id=ev_id,
                                is_synthetic=k.is_synthetic,
                            )
                            pending_drafts.append(
                                DiscoveredRelationshipDraft(
                                    source_entity_id=src_ent_c.id,
                                    target_entity_id=dst_ent_c.id,
                                    relationship_type=mapped_rtype,
                                    relationship_basis=rel_basis,
                                    confidence_score=conf,
                                    discovery_method="knowledge_payload",
                                    evidence_id=ev_id,
                                    evidence_chunk_id=None,
                                    knowledge_item_id=k.id,
                                    supporting_excerpt=first_excerpt,
                                    source_location_json={"architecture_relationship": raw_rtype},
                                )
                            )

            feat_det = meta.get("feature_details")
            if isinstance(feat_det, dict) and feat_det.get("feature_name"):
                fname = str(feat_det["feature_name"]).strip()
                f_ent = self._entity_repo.create_or_get_entity(
                    organisation_id=organisation_id,
                    project_id=project_id,
                    entity_type=EntityType.FEATURE.value,
                    canonical_name=fname[:255],
                    description=str(feat_det.get("user_visible_behavior") or summary),
                    primary_knowledge_item_id=k.id,
                    primary_evidence_id=ev_id,
                    confidence_score=conf,
                    metadata_json={
                        "user_goal": feat_det.get("user_goal"),
                        "user_actor": feat_det.get("user_actor"),
                        "user_visible_behavior": feat_det.get("user_visible_behavior"),
                        "workflow_steps": feat_det.get("workflow_steps") or [],
                        "feature_status": str(feat_det.get("implementation_status") or "PLANNED").upper(),
                        "verification_status": k.review_status,
                    },
                    first_observed_at=k.created_at,
                    last_observed_at=k.updated_at,
                    is_synthetic=k.is_synthetic,
                )
                seeded += 1
                feature_proc_candidates.append(
                    (f_ent, ev_id, conf, rel_basis, first_excerpt, k.id)
                )
                if project_entity is not None and ev_id is not None:
                    pending_drafts.append(
                        DiscoveredRelationshipDraft(
                            source_entity_id=project_entity.id,
                            target_entity_id=f_ent.id,
                            relationship_type=RelationshipType.HAS_FEATURE.value,
                            relationship_basis=rel_basis,
                            confidence_score=conf,
                            discovery_method="knowledge_payload",
                            evidence_id=ev_id,
                            evidence_chunk_id=None,
                            knowledge_item_id=k.id,
                            supporting_excerpt=first_excerpt,
                            source_location_json={"feature": f_ent.canonical_name},
                        )
                    )

            # Skip generic fallback seeding if explicit graph_details already handled the primary graph intent
            if isinstance(tech_det, dict) and graph_classes == {"TECHNOLOGY_STACK"}:
                continue
            if isinstance(feat_det, dict) and graph_classes == {"FEATURES_WORKFLOWS"}:
                continue

            # 1A. Technical & Architecture Knowledge -> unpack technologies & components
            if k.category in {
                KnowledgeCategory.TECHNICAL_ARCHITECTURE.value,
                KnowledgeCategory.ARCHITECTURE_TECHNICAL.value,
            }:
                tech_cat = str(meta.get("technical_category") or "").lower()
                raw_components = [
                    str(c).strip()
                    for c in (meta.get("components") or [])
                    if isinstance(c, str) and len(c.strip()) > 1
                ]
                raw_identifiers = [
                    str(i).strip()
                    for i in (meta.get("exact_identifiers") or [])
                    if isinstance(i, str) and len(i.strip()) > 1
                ]

                comp_entities: list[KnowledgeEntity] = []
                for comp_name in raw_components:
                    if comp_name.strip().lower() in _NON_COMPONENT_CONCEPTUAL_TOKENS:
                        continue
                    c_ent = self._entity_repo.create_or_get_entity(
                        organisation_id=organisation_id,
                        project_id=project_id,
                        entity_type=EntityType.TECHNICAL_COMPONENT.value,
                        canonical_name=comp_name[:255],
                        description=summary,
                        primary_knowledge_item_id=k.id,
                        primary_evidence_id=ev_id,
                        confidence_score=conf,
                        metadata_json={
                            **meta,
                            "implementation_basis": impl_basis,
                            "layer": meta.get("layer") or "core_services",
                            "verification_status": k.review_status,
                        },
                        first_observed_at=k.created_at,
                        last_observed_at=k.updated_at,
                        is_synthetic=k.is_synthetic,
                    )
                    comp_entities.append(c_ent)
                    seeded += 1
                    if ev_id is not None:
                        comp_entities_by_ev.setdefault(ev_id, []).append(c_ent)
                        pending_drafts.append(
                            DiscoveredRelationshipDraft(
                                source_entity_id=project_entity.id,
                                target_entity_id=c_ent.id,
                                relationship_type=RelationshipType.INTEGRATES_WITH.value,
                                relationship_basis=rel_basis,
                                confidence_score=conf,
                                discovery_method="knowledge_payload",
                                evidence_id=ev_id,
                                evidence_chunk_id=None,
                                knowledge_item_id=k.id,
                                supporting_excerpt=first_excerpt,
                                source_location_json={"component": c_ent.canonical_name},
                            )
                        )

                # Seed Technology entities strictly from technology_choice or verified known tech aliases
                tech_entries: list[tuple[str, str, str]] = []
                seen_canon: set[str] = set()
                if tech_cat == "technology_choice":
                    raw_tech_list = raw_identifiers or raw_components or [_extract_short_label(k.title, "Technology")]
                    for raw_tech in raw_tech_list:
                        canon_name, stack_cat, _etype = canonicalize_technology_name(raw_tech)
                        if canon_name and canon_name not in seen_canon:
                            seen_canon.add(canon_name)
                            tech_entries.append((raw_tech, canon_name, stack_cat))
                else:
                    for raw_tech in raw_identifiers:
                        if is_known_technology(raw_tech):
                            canon_name, stack_cat, _etype = canonicalize_technology_name(raw_tech)
                            if canon_name and canon_name not in seen_canon:
                                seen_canon.add(canon_name)
                                tech_entries.append((raw_tech, canon_name, stack_cat))

                for canon_name, stack_cat, _etype in extract_known_technologies_from_text(
                    k.title, summary, first_excerpt
                ):
                    if canon_name not in seen_canon:
                        seen_canon.add(canon_name)
                        tech_entries.append((canon_name, canon_name, stack_cat))

                for raw_tech, canon_name, stack_cat in tech_entries:
                    _record_technology(
                        raw_tech=raw_tech,
                        canon_name=canon_name,
                        stack_cat=stack_cat,
                        usage_basis=usage_basis,
                        summary=summary,
                        k_item=k,
                        ev_id=ev_id,
                        conf=conf,
                        rel_basis=rel_basis,
                        first_excerpt=first_excerpt,
                        comp_entities=comp_entities,
                    )

                # If neither explicit components nor tech choice/tech_det existed, seed concise architecture component
                is_conceptual = any(tok in k.title.lower() for tok in _NON_COMPONENT_CONCEPTUAL_TOKENS)
                is_tech_stack_title = "technology stack" in k.title.lower() or "tech stack" in k.title.lower()
                if (
                    not comp_entities
                    and tech_cat != "technology_choice"
                    and not is_conceptual
                    and not is_tech_stack_title
                    and not isinstance(arch_det, dict)
                    and "TECHNOLOGY_STACK" not in graph_classes
                ):
                    arch_ent = self._entity_repo.create_or_get_entity(
                        organisation_id=organisation_id,
                        project_id=project_id,
                        entity_type=EntityType.ARCHITECTURE_COMPONENT.value,
                        canonical_name=_extract_short_label(k.title, "Architecture Component"),
                        description=summary,
                        primary_knowledge_item_id=k.id,
                        primary_evidence_id=ev_id,
                        confidence_score=conf,
                        metadata_json={
                            **meta,
                            "implementation_basis": impl_basis,
                            "verification_status": k.review_status,
                        },
                        first_observed_at=k.created_at,
                        last_observed_at=k.updated_at,
                        is_synthetic=k.is_synthetic,
                    )
                    seeded += 1
                    if ev_id is not None:
                        comp_entities_by_ev.setdefault(ev_id, []).append(arch_ent)
                        pending_drafts.append(
                            DiscoveredRelationshipDraft(
                                source_entity_id=project_entity.id,
                                target_entity_id=arch_ent.id,
                                relationship_type=RelationshipType.INTEGRATES_WITH.value,
                                relationship_basis=rel_basis,
                                confidence_score=conf,
                                discovery_method="knowledge_payload",
                                evidence_id=ev_id,
                                evidence_chunk_id=None,
                                knowledge_item_id=k.id,
                                supporting_excerpt=first_excerpt,
                                source_location_json={"component": arch_ent.canonical_name},
                            )
                        )

            # 1B. Work Items & Features -> Feature / Requirement / Work Item entities
            elif k.category in {KnowledgeCategory.WORK_ITEMS.value, KnowledgeCategory.WORK_PROGRESS.value}:
                work_cat = str(meta.get("work_category") or "").lower()
                is_commit_or_pr = work_cat in {
                    "commit",
                    "bug_fix",
                    "refactoring",
                    "documentation",
                } or k.title.lower().startswith(("commit:", "pull request:"))

                if not is_commit_or_pr:
                    for canon_name, stack_cat, _etype in extract_known_technologies_from_text(k.title, summary):
                        _record_technology(
                            raw_tech=canon_name,
                            canon_name=canon_name,
                            stack_cat=stack_cat,
                            usage_basis=usage_basis,
                            summary=summary,
                            k_item=k,
                            ev_id=ev_id,
                            conf=conf,
                            rel_basis=rel_basis,
                            first_excerpt=first_excerpt,
                        )

                is_feature_candidate = (not is_commit_or_pr) and (
                    work_cat == "feature"
                    or any(
                        kw in k.title.lower()
                        for kw in ("feature", "application", "portal", "engine", "pipeline", "lifecycle", "roadmap")
                    )
                )
                feature_status = (
                    "HUMAN_VERIFIED"
                    if k.epistemic_status == EpistemicStatus.HUMAN_VERIFIED.value
                    else (
                        "IMPLEMENTATION_EVIDENCED"
                        if impl_basis == "implementation_evidenced"
                        else (
                            "BLOCKED"
                            if (k.normalised_status or "").lower() == "blocked"
                            else (
                                "IN_PROGRESS"
                                if (k.normalised_status or "").lower() in {"in_progress", "active"}
                                else "PLANNED"
                            )
                        )
                    )
                )
                w_ent: KnowledgeEntity | None = None
                if work_cat != "feature" and not is_commit_or_pr:
                    w_ent = self._entity_repo.create_or_get_entity(
                        organisation_id=organisation_id,
                        project_id=project_id,
                        entity_type=EntityType.WORK_ITEM.value,
                        canonical_name=k.title[:255],
                        description=summary,
                        primary_knowledge_item_id=k.id,
                        primary_evidence_id=ev_id,
                        confidence_score=conf,
                        metadata_json=meta,
                        first_observed_at=k.created_at,
                        last_observed_at=k.updated_at,
                        is_synthetic=k.is_synthetic,
                    )
                    seeded += 1

                if is_feature_candidate:
                    f_ent = self._entity_repo.create_or_get_entity(
                        organisation_id=organisation_id,
                        project_id=project_id,
                        entity_type=EntityType.FEATURE.value,
                        canonical_name=_extract_short_label(k.title, "Feature"),
                        description=summary,
                        primary_knowledge_item_id=k.id,
                        primary_evidence_id=ev_id,
                        confidence_score=conf,
                        metadata_json={
                            **meta,
                            "feature_status": feature_status,
                            "verification_status": k.review_status,
                        },
                        first_observed_at=k.created_at,
                        last_observed_at=k.updated_at,
                        is_synthetic=k.is_synthetic,
                    )
                    seeded += 1
                    feature_proc_candidates.append(
                        (f_ent, ev_id, conf, rel_basis, first_excerpt, k.id)
                    )
                    if project_entity is not None and ev_id is not None:
                        pending_drafts.append(
                            DiscoveredRelationshipDraft(
                                source_entity_id=project_entity.id,
                                target_entity_id=f_ent.id,
                                relationship_type=RelationshipType.HAS_FEATURE.value,
                                relationship_basis=rel_basis,
                                confidence_score=conf,
                                discovery_method="knowledge_payload",
                                evidence_id=ev_id,
                                evidence_chunk_id=None,
                                knowledge_item_id=k.id,
                                supporting_excerpt=first_excerpt,
                                source_location_json={"feature": f_ent.canonical_name},
                            )
                        )
                    if w_ent is not None and ev_id is not None:
                        pending_drafts.append(
                            DiscoveredRelationshipDraft(
                                source_entity_id=f_ent.id,
                                target_entity_id=w_ent.id,
                                relationship_type=RelationshipType.TRACKED_BY.value,
                                relationship_basis=rel_basis,
                                confidence_score=conf,
                                discovery_method="knowledge_payload",
                                evidence_id=ev_id,
                                evidence_chunk_id=None,
                                knowledge_item_id=k.id,
                                supporting_excerpt=first_excerpt,
                                source_location_json={"feature": f_ent.canonical_name},
                            )
                        )
                    for comp_name in meta.get("components") or []:
                        if isinstance(comp_name, str) and len(comp_name.strip()) > 1:
                            c_ent = self._entity_repo.create_or_get_entity(
                                organisation_id=organisation_id,
                                project_id=project_id,
                                entity_type=EntityType.TECHNICAL_COMPONENT.value,
                                canonical_name=comp_name.strip()[:255],
                                primary_evidence_id=ev_id,
                                is_synthetic=k.is_synthetic,
                            )
                            if ev_id is not None:
                                pending_drafts.append(
                                    DiscoveredRelationshipDraft(
                                        source_entity_id=f_ent.id,
                                        target_entity_id=c_ent.id,
                                        relationship_type=RelationshipType.USES_COMPONENT.value,
                                        relationship_basis=rel_basis,
                                        confidence_score=conf,
                                        discovery_method="knowledge_payload",
                                        evidence_id=ev_id,
                                        evidence_chunk_id=None,
                                        knowledge_item_id=k.id,
                                        supporting_excerpt=first_excerpt,
                                        source_location_json={"feature": f_ent.canonical_name},
                                    )
                                )

            # 1C. Operational / Historical -> Operational Procedure (excluding raw Markdown headings/outlines)
            elif k.category == KnowledgeCategory.OPERATIONAL_HISTORICAL.value:
                is_doc_outline = (
                    "section_title" in meta
                    or bool(meta.get("is_document_outline"))
                    or k.title.lower().startswith(("document section", "section:", "outline:"))
                )
                is_valid_proc = (
                    not is_doc_outline
                    and (
                        bool(meta.get("procedure_name"))
                        or str(meta.get("knowledge_type") or "").lower()
                        in {"procedure", "runbook", "deployment", "setup", "troubleshooting", "workflow"}
                        or k.extraction_run_id is not None
                    )
                )
                if not is_doc_outline:
                    for canon_name, stack_cat, _etype in extract_known_technologies_from_text(k.title, summary):
                        _record_technology(
                            raw_tech=canon_name,
                            canon_name=canon_name,
                            stack_cat=stack_cat,
                            usage_basis=usage_basis,
                            summary=summary,
                            k_item=k,
                            ev_id=ev_id,
                            conf=conf,
                            rel_basis=rel_basis,
                            first_excerpt=first_excerpt,
                        )
                if is_valid_proc:
                    proc_name = str(meta.get("procedure_name") or "").strip() or _extract_short_label(
                        k.title, "Operational Procedure"
                    )
                    proc_ent = self._entity_repo.create_or_get_entity(
                        organisation_id=organisation_id,
                        project_id=project_id,
                        entity_type=EntityType.OPERATIONAL_PROCEDURE.value,
                        canonical_name=proc_name[:255],
                        description=summary,
                        primary_knowledge_item_id=k.id,
                        primary_evidence_id=ev_id,
                        confidence_score=conf,
                        metadata_json={**meta, "verification_status": k.review_status},
                        first_observed_at=k.created_at,
                        last_observed_at=k.updated_at,
                        is_synthetic=k.is_synthetic,
                    )
                    seeded += 1
                    feature_proc_candidates.append(
                        (proc_ent, ev_id, conf, rel_basis, first_excerpt, k.id)
                    )

            # 1D. Project Overview -> Requirement / Feature candidates
            elif k.category == KnowledgeCategory.PROJECT_OVERVIEW_CONTEXT.value:
                for canon_name, stack_cat, _etype in extract_known_technologies_from_text(k.title, summary):
                    _record_technology(
                        raw_tech=canon_name,
                        canon_name=canon_name,
                        stack_cat=stack_cat,
                        usage_basis=usage_basis,
                        summary=summary,
                        k_item=k,
                        ev_id=ev_id,
                        conf=conf,
                        rel_basis=rel_basis,
                        first_excerpt=first_excerpt,
                    )
                req_ent = self._entity_repo.create_or_get_entity(
                    organisation_id=organisation_id,
                    project_id=project_id,
                    entity_type=EntityType.REQUIREMENT.value,
                    canonical_name=_extract_short_label(k.title, "Project Requirement"),
                    description=summary,
                    primary_knowledge_item_id=k.id,
                    primary_evidence_id=ev_id,
                    confidence_score=conf,
                    metadata_json={**meta, "feature_status": "PLANNED", "verification_status": k.review_status},
                    first_observed_at=k.created_at,
                    last_observed_at=k.updated_at,
                    is_synthetic=k.is_synthetic,
                )
                seeded += 1
                if project_entity is not None and ev_id is not None:
                    pending_drafts.append(
                        DiscoveredRelationshipDraft(
                            source_entity_id=project_entity.id,
                            target_entity_id=req_ent.id,
                            relationship_type=RelationshipType.HAS_REQUIREMENT.value,
                            relationship_basis=rel_basis,
                            confidence_score=conf,
                            discovery_method="knowledge_payload",
                            evidence_id=ev_id,
                            evidence_chunk_id=None,
                            knowledge_item_id=k.id,
                            supporting_excerpt=first_excerpt,
                            source_location_json={"requirement": req_ent.canonical_name},
                        )
                    )

            # 1E. Dependencies -> Component DEPENDS_ON Component + Technology extraction
            elif k.category == KnowledgeCategory.DEPENDENCIES.value:
                src_label = str(meta.get("source_item") or meta.get("source") or "").strip()
                tgt_label = str(meta.get("target_item") or meta.get("target") or "").strip()
                for canon_name, stack_cat, _etype in extract_known_technologies_from_text(
                    k.title, summary, src_label, tgt_label
                ):
                    _record_technology(
                        raw_tech=canon_name,
                        canon_name=canon_name,
                        stack_cat=stack_cat,
                        usage_basis=usage_basis,
                        summary=summary,
                        k_item=k,
                        ev_id=ev_id,
                        conf=conf,
                        rel_basis=rel_basis,
                        first_excerpt=first_excerpt,
                    )
                if src_label and tgt_label and ev_id is not None:
                    src_canon = src_label.strip()
                    tgt_canon_str = tgt_label.strip()
                    is_browser_api_contract = (
                        src_canon.lower() == "browser"
                        and "browser ↔ api" in k.title.lower()
                    )

                    if is_browser_api_contract and not ("route" in tgt_canon_str.lower() or "api" in tgt_canon_str.lower()):
                        # Mark coarse/unsplit item as stale while retaining full audit provenance
                        k.is_stale = True
                        k.stale_reason = "Superseded by component-to-component architectural reconstruction"
                        # The client talks to FastAPI routes, and FastAPI routes interacts with backend resources
                        api_ent = self._entity_repo.create_or_get_entity(
                            organisation_id=organisation_id,
                            project_id=project_id,
                            entity_type=EntityType.TECHNICAL_COMPONENT.value,
                            canonical_name="FastAPI routes",
                            description="Versioned FastAPI routes under /api/v1",
                            primary_knowledge_item_id=k.id,
                            primary_evidence_id=ev_id,
                            confidence_score=conf,
                            metadata_json={"layer": "core_services", "verification_status": k.review_status},
                            is_synthetic=k.is_synthetic,
                        )
                        browser_ent = self._entity_repo.create_or_get_entity(
                            organisation_id=organisation_id,
                            project_id=project_id,
                            entity_type=EntityType.TECHNICAL_COMPONENT.value,
                            canonical_name="Browser",
                            description="Browser web client application",
                            primary_knowledge_item_id=k.id,
                            primary_evidence_id=ev_id,
                            confidence_score=conf,
                            metadata_json={"layer": "core_services", "verification_status": k.review_status},
                            is_synthetic=k.is_synthetic,
                        )
                        pending_drafts.append(
                            DiscoveredRelationshipDraft(
                                source_entity_id=browser_ent.id,
                                target_entity_id=api_ent.id,
                                relationship_type=RelationshipType.CALLS.value,
                                relationship_basis=rel_basis,
                                confidence_score=conf,
                                discovery_method="knowledge_payload",
                                evidence_id=ev_id,
                                evidence_chunk_id=None,
                                knowledge_item_id=k.id,
                                supporting_excerpt=first_excerpt,
                                source_location_json={"contract": "Browser ↔ API"},
                            )
                        )
                        src_ent = api_ent
                    else:
                        src_ent = self._entity_repo.create_or_get_entity(
                            organisation_id=organisation_id,
                            project_id=project_id,
                            entity_type=EntityType.TECHNICAL_COMPONENT.value,
                            canonical_name=src_canon[:255],
                            description=summary,
                            primary_knowledge_item_id=k.id,
                            primary_evidence_id=ev_id,
                            confidence_score=conf,
                            metadata_json={"implementation_basis": impl_basis, "verification_status": k.review_status},
                            is_synthetic=k.is_synthetic,
                        )

                    tgt_ent = self._entity_repo.create_or_get_entity(
                        organisation_id=organisation_id,
                        project_id=project_id,
                        entity_type=EntityType.TECHNICAL_COMPONENT.value,
                        canonical_name=tgt_canon_str[:255],
                        description=summary,
                        primary_knowledge_item_id=k.id,
                        primary_evidence_id=ev_id,
                        confidence_score=conf,
                        metadata_json={"implementation_basis": impl_basis, "verification_status": k.review_status},
                        is_synthetic=k.is_synthetic,
                    )
                    seeded += 2
                    comp_entities_by_ev.setdefault(ev_id, []).extend([src_ent, tgt_ent])
                    if src_ent.id != tgt_ent.id:
                        tgt_canon = tgt_canon_str.lower()
                        if "route" in tgt_canon or "api" in tgt_canon:
                            r_type = RelationshipType.CALLS.value
                        elif "auth" in tgt_canon:
                            r_type = RelationshipType.AUTHENTICATES_WITH.value
                        elif "storage" in tgt_canon:
                            r_type = RelationshipType.STORES_IN.value
                        elif "postgres" in tgt_canon or "database" in tgt_canon:
                            r_type = RelationshipType.READS_FROM.value
                        elif "ollama" in tgt_canon or "model" in tgt_canon:
                            r_type = RelationshipType.USES_MODEL.value
                        elif "chroma" in tgt_canon or "vector" in tgt_canon:
                            r_type = RelationshipType.STORES_IN.value
                        elif "git" in tgt_canon or "jira" in tgt_canon:
                            r_type = RelationshipType.INTEGRATES_WITH.value
                        else:
                            r_type = RelationshipType.DEPENDS_ON.value
                        pending_drafts.append(
                            DiscoveredRelationshipDraft(
                                source_entity_id=src_ent.id,
                                target_entity_id=tgt_ent.id,
                                relationship_type=r_type,
                                relationship_basis=rel_basis,
                                confidence_score=conf,
                                discovery_method="knowledge_payload",
                                evidence_id=ev_id,
                                evidence_chunk_id=None,
                                knowledge_item_id=k.id,
                                supporting_excerpt=first_excerpt,
                                source_location_json={"dependency_title": k.title[:120]},
                            )
                        )
                else:
                    self._entity_repo.create_or_get_entity(
                        organisation_id=organisation_id,
                        project_id=project_id,
                        entity_type=EntityType.DEPENDENCY.value,
                        canonical_name=k.title[:255],
                        description=summary,
                        primary_knowledge_item_id=k.id,
                        primary_evidence_id=ev_id,
                        confidence_score=conf,
                        metadata_json=meta,
                        first_observed_at=k.created_at,
                        last_observed_at=k.updated_at,
                        is_synthetic=k.is_synthetic,
                    )
                    seeded += 1

            # 1F. Decisions & Remaining Knowledge Categories
            else:
                if k.category == KnowledgeCategory.DECISIONS_RATIONALE.value:
                    for canon_name, stack_cat, _etype in extract_known_technologies_from_text(
                        k.title,
                        summary,
                        str(meta.get("decision") or ""),
                        str(meta.get("chosen_approach") or ""),
                    ):
                        _record_technology(
                            raw_tech=canon_name,
                            canon_name=canon_name,
                            stack_cat=stack_cat,
                            usage_basis=usage_basis,
                            summary=summary,
                            k_item=k,
                            ev_id=ev_id,
                            conf=conf,
                            rel_basis=rel_basis,
                            first_excerpt=first_excerpt,
                        )
                e_type = _CATEGORY_TO_ENTITY_TYPE.get(k.category, EntityType.DOCUMENT.value)
                self._entity_repo.create_or_get_entity(
                    organisation_id=organisation_id,
                    project_id=project_id,
                    entity_type=e_type,
                    canonical_name=k.title[:255],
                    description=summary,
                    primary_knowledge_item_id=k.id,
                    primary_evidence_id=ev_id,
                    confidence_score=conf,
                    metadata_json=meta,
                    first_observed_at=k.created_at,
                    last_observed_at=k.updated_at,
                    is_synthetic=k.is_synthetic,
                )
                seeded += 1

            owner_name = getattr(k, "person_or_owner_label", None) or meta.get("owner") or meta.get("author")
            if owner_name and isinstance(owner_name, str):
                _ensure_person(owner_name, "metadata", is_synthetic=k.is_synthetic)

        # Link features and operational procedures to components sharing the same supporting evidence item
        seen_fp_comp: set[tuple[uuid.UUID, uuid.UUID]] = set()
        for fp_ent, fp_ev_id, fp_conf, fp_basis, fp_excerpt, fp_k_id in feature_proc_candidates:
            if fp_ev_id is None:
                continue
            for c_ent in comp_entities_by_ev.get(fp_ev_id, []):
                if c_ent.id == fp_ent.id or (fp_ent.id, c_ent.id) in seen_fp_comp:
                    continue
                seen_fp_comp.add((fp_ent.id, c_ent.id))
                pending_drafts.append(
                    DiscoveredRelationshipDraft(
                        source_entity_id=fp_ent.id,
                        target_entity_id=c_ent.id,
                        relationship_type=RelationshipType.USES_COMPONENT.value,
                        relationship_basis=fp_basis,
                        confidence_score=fp_conf,
                        discovery_method="shared_evidence_component",
                        evidence_id=fp_ev_id,
                        evidence_chunk_id=None,
                        knowledge_item_id=fp_k_id,
                        supporting_excerpt=fp_excerpt,
                        source_location_json={"entity": fp_ent.canonical_name},
                    )
                )

        # 2. Seed from EvidenceItems (GitHub PRs, Commits, Jira Issues, Manifests)
        for ev in evidence_items:
            meta = ev.metadata_json or {}
            source_type = ev.source_type
            ev_cat = (ev.category or "").lower()

            if ev_cat == "pull_request" or "pull_request" in source_type or "pr" in source_type:
                ent_type = EntityType.PULL_REQUEST.value
            elif ev_cat == "commit" or "commit" in source_type:
                ent_type = EntityType.COMMIT.value
            elif "jira" in source_type or ev_cat == "issue":
                ent_type = EntityType.WORK_ITEM.value
            else:
                ent_type = EntityType.DOCUMENT.value

            ev_ent = self._entity_repo.create_or_get_entity(
                organisation_id=organisation_id,
                project_id=project_id,
                entity_type=ent_type,
                canonical_name=ev.title[:255],
                description=getattr(ev, "description", None),
                primary_evidence_id=ev.id,
                external_source_id=ev.source_external_id,
                source_provider=ev.source_type,
                metadata_json=meta,
                first_observed_at=ev.source_created_at or ev.created_at,
                last_observed_at=ev.source_updated_at or ev.created_at,
                is_synthetic=getattr(ev, "is_synthetic", False),
            )
            seeded += 1

            # Seed Repository entity if present
            repo_name = meta.get("repository")
            if isinstance(repo_name, str) and repo_name.strip():
                repo_ent = self._entity_repo.create_or_get_entity(
                    organisation_id=organisation_id,
                    project_id=project_id,
                    entity_type=EntityType.REPOSITORY.value,
                    canonical_name=repo_name.strip()[:255],
                    primary_evidence_id=ev.id,
                    source_provider=ev.source_type,
                    is_synthetic=getattr(ev, "is_synthetic", False),
                )
                if (project_entity.id, repo_ent.id) not in seen_repo_pairs:
                    seen_repo_pairs.add((project_entity.id, repo_ent.id))
                    pending_drafts.append(
                        DiscoveredRelationshipDraft(
                            source_entity_id=project_entity.id,
                            target_entity_id=repo_ent.id,
                            relationship_type=RelationshipType.INTEGRATES_WITH.value,
                            relationship_basis=RelationshipBasis.EXPLICIT.value,
                            confidence_score=0.95,
                            discovery_method="connector_metadata",
                            evidence_id=ev.id,
                            evidence_chunk_id=None,
                            knowledge_item_id=None,
                            supporting_excerpt=f"Connected repository {repo_name.strip()}",
                            source_location_json={"repository": repo_name.strip()},
                        )
                    )

            # Parse technical manifests deterministically into canonical Technology entities
            manifest_path = str(meta.get("path") or ev.original_filename or "")
            if is_manifest_path(manifest_path) and ev.content and ev.content.extracted_text:
                detections = parse_manifest_evidence(manifest_path, ev.content.extracted_text)
                for det in detections:
                    t_ent = self._entity_repo.create_or_get_entity(
                        organisation_id=organisation_id,
                        project_id=project_id,
                        entity_type=EntityType.TECHNOLOGY.value,
                        canonical_name=det.canonical_name[:255],
                        description=det.purpose,
                        primary_evidence_id=ev.id,
                        source_provider=ev.source_type,
                        confidence_score=0.98,
                        metadata_json={
                            "technology_category": det.category,
                            "usage_basis": det.usage_basis,
                            "version": det.version,
                            "purpose": det.purpose,
                            "manifest_path": det.source_path,
                            "manifest_metadata": det.metadata,
                        },
                        is_synthetic=getattr(ev, "is_synthetic", False),
                    )
                    if det.raw_name.strip().lower() != det.canonical_name.lower():
                        self._entity_repo.add_alias(
                            entity_id=t_ent.id,
                            organisation_id=organisation_id,
                            project_id=project_id,
                            alias_value=det.raw_name.strip()[:255],
                            source_provider="manifest_parser",
                            is_synthetic=getattr(ev, "is_synthetic", False),
                        )
                    seeded += 1
                    if (project_entity.id, t_ent.id) not in seen_project_tech_pairs:
                        seen_project_tech_pairs.add((project_entity.id, t_ent.id))
                        pending_drafts.append(
                            DiscoveredRelationshipDraft(
                                source_entity_id=project_entity.id,
                                target_entity_id=t_ent.id,
                                relationship_type=RelationshipType.USES_TECHNOLOGY.value,
                                relationship_basis=RelationshipBasis.EXPLICIT.value,
                                confidence_score=0.98,
                                discovery_method="manifest_parser",
                                evidence_id=ev.id,
                                evidence_chunk_id=None,
                                knowledge_item_id=None,
                                supporting_excerpt=f"{det.canonical_name} ({det.version or 'unpinned'}) declared in {manifest_path}",
                                source_location_json={"manifest_path": manifest_path},
                            )
                        )
                    if (t_ent.id, ev_ent.id) not in seen_doc_tech_pairs:
                        seen_doc_tech_pairs.add((t_ent.id, ev_ent.id))
                        pending_drafts.append(
                            DiscoveredRelationshipDraft(
                                source_entity_id=t_ent.id,
                                target_entity_id=ev_ent.id,
                                relationship_type=RelationshipType.CONFIGURED_IN.value,
                                relationship_basis=RelationshipBasis.EXPLICIT.value,
                                confidence_score=0.98,
                                discovery_method="manifest_parser",
                                evidence_id=ev.id,
                                evidence_chunk_id=None,
                                knowledge_item_id=None,
                                supporting_excerpt=f"Configured in {manifest_path}",
                                source_location_json={"manifest_path": manifest_path},
                            )
                        )
            elif (
                ev.content is not None
                and (ev.content.extracted_text or "").strip()
                and meta.get("github_item_type") != "repository"
                and ev_cat != "commit"
            ):
                ev_text = ev.content.extracted_text[:60000]
                is_impl = ev_cat in {"pull_request", "source_code"} or is_manifest_path(manifest_path)
                text_basis = "implemented" if is_impl else "documented"
                low_text = ev_text.lower()
                for canon_name, stack_cat, _etype in extract_known_technologies_from_text(
                    ev.title, ev_text
                ):
                    if not is_impl or ev_cat in {"pull_request", "source_code"} or canon_name not in {"GitHub API", "Jira API", "Slack API"}:
                        pos = low_text.find(canon_name.lower())
                        if pos >= 0:
                            start = max(0, pos - 60)
                            end = min(len(ev_text), pos + 180)
                            excerpt = " ".join(ev_text[start:end].split())[:240]
                        else:
                            excerpt = f"{canon_name} referenced in {ev.title[:160]}"
                        t_ent = self._entity_repo.create_or_get_entity(
                            organisation_id=organisation_id,
                            project_id=project_id,
                            entity_type=EntityType.TECHNOLOGY.value,
                            canonical_name=canon_name[:255],
                            description=excerpt,
                            primary_evidence_id=ev.id,
                            source_provider=ev.source_type,
                            confidence_score=0.88 if not is_impl else 0.9,
                            metadata_json={
                                "technology_category": stack_cat,
                                "usage_basis": text_basis,
                                "purpose": excerpt,
                            },
                            first_observed_at=ev.source_created_at or ev.created_at,
                            last_observed_at=ev.source_updated_at or ev.created_at,
                            is_synthetic=getattr(ev, "is_synthetic", False),
                        )
                        seeded += 1
                        if (project_entity.id, t_ent.id) not in seen_project_tech_pairs:
                            seen_project_tech_pairs.add((project_entity.id, t_ent.id))
                            pending_drafts.append(
                                DiscoveredRelationshipDraft(
                                    source_entity_id=project_entity.id,
                                    target_entity_id=t_ent.id,
                                    relationship_type=RelationshipType.USES_TECHNOLOGY.value,
                                    relationship_basis=RelationshipBasis.EXPLICIT.value,
                                    confidence_score=0.88,
                                    discovery_method="evidence_text_scanner",
                                    evidence_id=ev.id,
                                    evidence_chunk_id=None,
                                    knowledge_item_id=None,
                                    supporting_excerpt=excerpt,
                                    source_location_json={"evidence_title": ev.title[:120]},
                                )
                            )
                        if (
                            ev_ent.entity_type == EntityType.DOCUMENT.value
                            and (t_ent.id, ev_ent.id) not in seen_doc_tech_pairs
                        ):
                            seen_doc_tech_pairs.add((t_ent.id, ev_ent.id))
                            pending_drafts.append(
                                DiscoveredRelationshipDraft(
                                    source_entity_id=t_ent.id,
                                    target_entity_id=ev_ent.id,
                                    relationship_type=RelationshipType.CONFIGURED_IN.value,
                                    relationship_basis=RelationshipBasis.EXPLICIT.value,
                                    confidence_score=0.86,
                                    discovery_method="evidence_text_scanner",
                                    evidence_id=ev.id,
                                    evidence_chunk_id=None,
                                    knowledge_item_id=None,
                                    supporting_excerpt=excerpt,
                                    source_location_json={"document": ev.title[:120]},
                                )
                            )

            # Seed author / creator identities
            gh_login = meta.get("github_author_login")
            git_email = meta.get("git_author_email")
            git_name = meta.get("git_author_name") or meta.get("author") or meta.get("user") or meta.get("reporter") or ev.source_author_identity
            primary_person = gh_login or git_name or git_email
            if isinstance(primary_person, str) and len(primary_person.strip()) > 1:
                _ensure_person(
                    primary_person,
                    ev.source_type,
                    is_synthetic=getattr(ev, "is_synthetic", False),
                    extra_aliases=[x for x in (gh_login, git_name, git_email) if isinstance(x, str)],
                )

        if pending_drafts:
            self._discovery_engine.persist_discovered_relationships(
                organisation_id=organisation_id,
                project_id=project_id,
                drafts=pending_drafts,
            )

        self._session.flush()
        return seeded

    def synthesize_user_facing_features(
        self,
        *,
        organisation_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> int:
        """Synthesize canonical user-facing product features, workflows, and requirements
        grounded in PRD and SRS evidence documents and existing knowledge items."""
        seeded = 0
        project_row = self._session.get(Project, project_id)
        project_entity = self._entity_repo.create_or_get_entity(
            organisation_id=organisation_id,
            project_id=project_id,
            entity_type=EntityType.PROJECT.value,
            canonical_name=(project_row.name if project_row else "Project")[:255],
            description=(project_row.description if project_row else None),
            source_provider="platform",
        )
        if not project_entity:
            return 0

        # Load document evidence items for this project (PRD, SRS, README, and Markdown Docs)
        doc_evs = list(
            self._session.execute(
                select(EvidenceItem).where(
                    EvidenceItem.project_id == project_id,
                    EvidenceItem.deleted_at.is_(None),
                    (
                        (EvidenceItem.source_type == EvidenceSourceType.DOCUMENT_UPLOAD.value)
                        | (
                            (EvidenceItem.source_type == EvidenceSourceType.GITHUB.value)
                            & (
                                (EvidenceItem.category.in_(["design_document", "documentation", "specification"]))
                                | (EvidenceItem.title.ilike("%.md%"))
                                | (EvidenceItem.title.ilike("%README%"))
                            )
                        )
                    ),
                )
            )
            .scalars()
            .all()
        )

        # Preload chunks for all document evidence items
        doc_ev_ids = [ev.id for ev in doc_evs]
        chunks = list(
            self._session.execute(
                select(EvidenceChunk)
                .where(EvidenceChunk.evidence_id.in_(doc_ev_ids))
                .order_by(EvidenceChunk.chunk_index)
            )
            .scalars()
            .all()
        ) if doc_ev_ids else []

        # 1. Dynamically parse PRD/SRS/Requirements chunks for features & user stories
        import re
        req_pattern = re.compile(
            r"((?:PRD|FR|FEAT|REQ)-[A-Z0-9]{2,8}(?:-[0-9]{1,3})?)\s*[—:-]\s*([^\n\r\.\,]{4,80})",
            re.IGNORECASE,
        )
        story_pattern = re.compile(
            r"\*\*(P\d+(?:\s*(?:and|&|-)\s*P\d+)?)\s*:\*\*\s*(?:As a\s+([^\,]+?),\s+I can\s+)?([^\n\r]{4,100})",
            re.IGNORECASE,
        )
        heading_pattern = re.compile(
            r"###?\s*(?:Feature|Capability|Use Case|User Story|Epic):\s*([^\n\r]{4,80})",
            re.IGNORECASE,
        )
        numbered_feature_pattern = re.compile(
            r"^\s*(?:#+\s*)?(\d+)\.\s+([A-Z0-9\s—:-]{3,60})$",
            re.MULTILINE,
        )
        ignore_numbered_sections = {
            "technical requirements",
            "design direction",
            "development",
            "prerequisites",
            "installation",
            "license",
            "table of contents",
        }

        discovered_from_chunks: list[dict[str, Any]] = []
        seen_disc_names: set[str] = set()

        for c in chunks:
            for match in numbered_feature_pattern.finditer(c.chunk_text):
                num_str = match.group(1).strip()
                raw_name = match.group(2).strip()
                clean_name = raw_name.split("—")[0].split("-")[0].strip().title()
                norm_name = clean_name.lower()
                if norm_name in ignore_numbered_sections or len(clean_name) < 4:
                    continue
                if norm_name not in seen_disc_names:
                    seen_disc_names.add(norm_name)
                    feat_code = f"FEAT-{num_str.zfill(2)}"
                    discovered_from_chunks.append({
                        "code": feat_code,
                        "req_code": f"FR-{num_str.zfill(2)}",
                        "name": clean_name,
                        "role": "User",
                        "goal": f"Deliver {clean_name} functionality as documented in project specifications",
                        "action": f"User navigates to and interacts with {clean_name}",
                        "result": f"Verified interaction with {clean_name}",
                        "workflow_step": f"Access {clean_name}",
                        "step_action": f"Open and operate {clean_name}",
                        "step_result": f"Verified status in {clean_name}",
                        "status": "DOCUMENTED",
                        "evidence_id": c.evidence_id,
                        "chunk_id": c.id,
                        "matched_chunk": c,
                        "excerpt": c.chunk_text[:300],
                    })
            for match in story_pattern.finditer(c.chunk_text):
                code = match.group(1).strip()
                role = (match.group(2) or "User").strip()
                name = match.group(3).strip()
                norm_name = name.lower()
                if norm_name not in seen_disc_names and len(name) >= 4:
                    seen_disc_names.add(norm_name)
                    discovered_from_chunks.append({
                        "code": code,
                        "req_code": f"FR-{code}",
                        "name": f"{code}: {name}" if not name.startswith("P") else name,
                        "role": role,
                        "goal": f"Enable {role} to {name}",
                        "action": f"User executes {name}",
                        "result": f"Verified completion of {name}",
                        "workflow_step": f"Execute {name}",
                        "step_action": f"Trigger user action for {name}",
                        "step_result": f"Verified output for {name}",
                        "status": "DOCUMENTED",
                        "evidence_id": c.evidence_id,
                        "chunk_id": c.id,
                        "matched_chunk": c,
                        "excerpt": c.chunk_text[:300],
                    })

            for match in req_pattern.finditer(c.chunk_text):
                code = match.group(1).upper()
                name = match.group(2).strip()
                norm_name = name.lower()
                if norm_name not in seen_disc_names and len(name) >= 4:
                    seen_disc_names.add(norm_name)
                    discovered_from_chunks.append({
                        "code": code,
                        "req_code": code,
                        "name": name,
                        "role": "User",
                        "goal": f"Deliver {name} capability as specified in requirements",
                        "action": f"Execute user workflow for {name}",
                        "result": f"Verified completion of {name} criteria",
                        "workflow_step": f"Execute {name}",
                        "step_action": f"Trigger user action for {name}",
                        "step_result": f"Verified output for {name}",
                        "status": "DOCUMENTED",
                        "evidence_id": c.evidence_id,
                        "chunk_id": c.id,
                        "matched_chunk": c,
                        "excerpt": c.chunk_text[:300],
                    })

            for match in heading_pattern.finditer(c.chunk_text):
                h_name = match.group(1).strip()
                h_norm = h_name.lower()
                if h_norm not in seen_disc_names and len(h_name) >= 4:
                    h_code = f"FEAT-{len(discovered_from_chunks) + 1:02d}"
                    seen_disc_names.add(h_norm)
                    discovered_from_chunks.append({
                        "code": h_code,
                        "req_code": f"FR-{len(discovered_from_chunks) + 1:02d}",
                        "name": h_name,
                        "role": "User",
                        "goal": f"Enable user to utilize {h_name}",
                        "action": f"Initiate {h_name} in application",
                        "result": f"Completed {h_name} process",
                        "workflow_step": f"Operate {h_name}",
                        "step_action": f"Perform steps for {h_name}",
                        "step_result": f"Verified result for {h_name}",
                        "status": "DOCUMENTED",
                        "evidence_id": c.evidence_id,
                        "chunk_id": c.id,
                        "matched_chunk": c,
                        "excerpt": c.chunk_text[:300],
                    })

        pending_drafts: list[DiscoveredRelationshipDraft] = []
        feature_entities: list[KnowledgeEntity] = []

        # Create entities from dynamically discovered chunks (if any)
        for item in discovered_from_chunks:
            ev_id = item["evidence_id"]
            chunk_id = item["chunk_id"]
            matched_excerpt = item["excerpt"]

            f_ent = self._entity_repo.create_or_get_entity(
                organisation_id=organisation_id,
                project_id=project_id,
                entity_type=EntityType.FEATURE.value,
                canonical_name=item["name"],
                description=f"{item['goal']}. Trigger: {item['action']}. Expected outcome: {item['result']}.",
                primary_evidence_id=ev_id,
                confidence_score=0.98,
                metadata_json={
                    "code": item["code"],
                    "req_code": item["req_code"],
                    "feature_status": item["status"],
                    "user_role": item["role"],
                    "user_goal": item["goal"],
                    "triggering_action": item["action"],
                    "expected_result": item["result"],
                    "work_category": "feature",
                    "verification_status": "pending_review",
                },
            )
            seeded += 1
            feature_entities.append(f_ent)

            # Connect Project -> Feature (HAS_FEATURE)
            pending_drafts.append(
                DiscoveredRelationshipDraft(
                    source_entity_id=project_entity.id,
                    target_entity_id=f_ent.id,
                    relationship_type=RelationshipType.HAS_FEATURE.value,
                    relationship_basis=RelationshipBasis.EXPLICIT.value,
                    confidence_score=0.98,
                    discovery_method="prd_srs_specification",
                    evidence_id=ev_id,
                    evidence_chunk_id=chunk_id,
                    knowledge_item_id=None,
                    supporting_excerpt=matched_excerpt,
                    source_location_json={"feature_code": item["code"]},
                )
            )

            # Create Operational Procedure / Workflow Step
            step_ent = self._entity_repo.create_or_get_entity(
                organisation_id=organisation_id,
                project_id=project_id,
                entity_type=EntityType.OPERATIONAL_PROCEDURE.value,
                canonical_name=item["workflow_step"],
                description=f"Action: {item['step_action']}. Result: {item['step_result']}.",
                primary_evidence_id=ev_id,
                confidence_score=0.95,
                metadata_json={
                    "work_category": "workflow_step",
                    "parent_feature": item["name"],
                    "step_action": item["step_action"],
                    "step_result": item["step_result"],
                    "verification_status": "pending_review",
                },
            )
            seeded += 1

            # Connect Feature -> Workflow Step (HAS_WORKFLOW_STEP)
            pending_drafts.append(
                DiscoveredRelationshipDraft(
                    source_entity_id=f_ent.id,
                    target_entity_id=step_ent.id,
                    relationship_type=RelationshipType.HAS_WORKFLOW_STEP.value,
                    relationship_basis=RelationshipBasis.EXPLICIT.value,
                    confidence_score=0.95,
                    discovery_method="prd_srs_specification",
                    evidence_id=ev_id,
                    evidence_chunk_id=chunk_id,
                    knowledge_item_id=None,
                    supporting_excerpt=matched_excerpt,
                    source_location_json={"feature_code": item["code"]},
                )
            )

            # Create Requirement entity
            req_ent = self._entity_repo.create_or_get_entity(
                organisation_id=organisation_id,
                project_id=project_id,
                entity_type=EntityType.REQUIREMENT.value,
                canonical_name=f"{item['req_code']} — {item['name']}",
                description=f"Requirement specification for {item['name']}: {item['goal']}",
                primary_evidence_id=ev_id,
                confidence_score=0.95,
                metadata_json={
                    "req_code": item["req_code"],
                    "parent_feature": item["name"],
                    "feature_status": "PLANNED",
                    "verification_status": "pending_review",
                },
            )
            seeded += 1

            # Connect Feature -> Requirement (HAS_REQUIREMENT)
            pending_drafts.append(
                DiscoveredRelationshipDraft(
                    source_entity_id=f_ent.id,
                    target_entity_id=req_ent.id,
                    relationship_type=RelationshipType.HAS_REQUIREMENT.value,
                    relationship_basis=RelationshipBasis.EXPLICIT.value,
                    confidence_score=0.95,
                    discovery_method="prd_srs_specification",
                    evidence_id=ev_id,
                    evidence_chunk_id=chunk_id,
                    knowledge_item_id=None,
                    supporting_excerpt=matched_excerpt,
                    source_location_json={"req_code": item["req_code"]},
                )
            )

        # 2. ALSO query existing KnowledgeEntity rows for this project (e.g. seeded from KnowledgeItems)
        existing_features = list(self._session.execute(
            select(KnowledgeEntity).where(
                KnowledgeEntity.project_id == project_id,
                KnowledgeEntity.entity_type == EntityType.FEATURE.value,
                KnowledgeEntity.is_deleted.is_(False),
                KnowledgeEntity.is_stale.is_(False),
            )
        ).scalars().all())

        existing_reqs = list(self._session.execute(
            select(KnowledgeEntity).where(
                KnowledgeEntity.project_id == project_id,
                KnowledgeEntity.entity_type == EntityType.REQUIREMENT.value,
                KnowledgeEntity.is_deleted.is_(False),
                KnowledgeEntity.is_stale.is_(False),
            )
        ).scalars().all())

        existing_procs = list(self._session.execute(
            select(KnowledgeEntity).where(
                KnowledgeEntity.project_id == project_id,
                KnowledgeEntity.entity_type == EntityType.OPERATIONAL_PROCEDURE.value,
                KnowledgeEntity.is_deleted.is_(False),
                KnowledgeEntity.is_stale.is_(False),
            )
        ).scalars().all())

        # Filter conventional commit noise
        _NOISE_TOKENS = {"feat", "fix", "chore", "docs", "refactor", "style", "test", "perf", "ci", "build", "merge"}
        all_clean_features: list[KnowledgeEntity] = []
        for f in existing_features:
            n_low = f.canonical_name.strip().lower()
            if n_low in _NOISE_TOKENS or n_low.startswith("commit ") or "commit:" in n_low or ("@" in n_low and len(n_low.split("@")[-1]) >= 7):
                continue
            all_clean_features.append(f)

        fallback_ev_id = doc_evs[0].id if doc_evs else (project_entity.primary_evidence_id or None)

        # Connect Project -> Feature for all clean features
        for f in all_clean_features:
            ev_id = f.primary_evidence_id or fallback_ev_id
            if ev_id:
                pending_drafts.append(
                    DiscoveredRelationshipDraft(
                        source_entity_id=project_entity.id,
                        target_entity_id=f.id,
                        relationship_type=RelationshipType.HAS_FEATURE.value,
                        relationship_basis=RelationshipBasis.EXPLICIT.value,
                        confidence_score=0.95,
                        discovery_method="project_feature_hierarchy",
                        evidence_id=ev_id,
                        evidence_chunk_id=None,
                        knowledge_item_id=f.primary_knowledge_item_id,
                        supporting_excerpt=f"Project feature: {f.canonical_name}",
                        source_location_json={"feature": f.canonical_name},
                    )
                )

        # Connect Sequential Feature Dependencies (e.g. P01 -> P02 -> P03 ...)
        def _feature_order_key(name: str):
            m = re.search(r"P0?(\d+)", name, re.IGNORECASE)
            if m:
                return (1, int(m.group(1)))
            m = re.search(r"(?:FR|FEAT|REQ)-?0?(\d+)", name, re.IGNORECASE)
            if m:
                return (2, int(m.group(1)))
            return (3, name.lower())

        ordered_features = sorted(all_clean_features, key=lambda f: _feature_order_key(f.canonical_name))
        seq_features = [f for f in ordered_features if _feature_order_key(f.canonical_name)[0] in (1, 2)]
        for i in range(len(seq_features) - 1):
            f_curr = seq_features[i]
            f_next = seq_features[i + 1]
            if f_curr.canonical_name.strip().lower() == f_next.canonical_name.strip().lower():
                continue
            ev_id = f_next.primary_evidence_id or f_curr.primary_evidence_id or fallback_ev_id
            if ev_id:
                pending_drafts.append(
                    DiscoveredRelationshipDraft(
                        source_entity_id=f_curr.id,
                        target_entity_id=f_next.id,
                        relationship_type=RelationshipType.DEPENDS_ON.value,
                        relationship_basis=RelationshipBasis.EXPLICIT.value,
                        confidence_score=0.90,
                        discovery_method="user_journey_sequence",
                        evidence_id=ev_id,
                        evidence_chunk_id=None,
                        knowledge_item_id=f_next.primary_knowledge_item_id,
                        supporting_excerpt=f"Sequential workflow dependency: {f_curr.canonical_name} precedes {f_next.canonical_name}",
                        source_location_json={"sequence": f"{f_curr.canonical_name} -> {f_next.canonical_name}"},
                    )
                )

        # Connect Feature -> Requirement & Project -> Requirement
        for r in existing_reqs:
            ev_id = r.primary_evidence_id or fallback_ev_id
            if not ev_id:
                continue
            linked = False
            r_low = r.canonical_name.lower()
            for f in all_clean_features:
                f_low = f.canonical_name.lower()
                if any(tok in r_low for tok in f_low.split() if len(tok) > 4):
                    pending_drafts.append(
                        DiscoveredRelationshipDraft(
                            source_entity_id=f.id,
                            target_entity_id=r.id,
                            relationship_type=RelationshipType.HAS_REQUIREMENT.value,
                            relationship_basis=RelationshipBasis.EXPLICIT.value,
                            confidence_score=0.92,
                            discovery_method="feature_requirement_link",
                            evidence_id=ev_id,
                            evidence_chunk_id=None,
                            knowledge_item_id=r.primary_knowledge_item_id,
                            supporting_excerpt=f"Requirement for {f.canonical_name}: {r.canonical_name}",
                            source_location_json={"requirement": r.canonical_name},
                        )
                    )
                    linked = True
                    break
            if not linked:
                pending_drafts.append(
                    DiscoveredRelationshipDraft(
                        source_entity_id=project_entity.id,
                        target_entity_id=r.id,
                        relationship_type=RelationshipType.HAS_REQUIREMENT.value,
                        relationship_basis=RelationshipBasis.EXPLICIT.value,
                        confidence_score=0.90,
                        discovery_method="project_requirement_hierarchy",
                        evidence_id=ev_id,
                        evidence_chunk_id=None,
                        knowledge_item_id=r.primary_knowledge_item_id,
                        supporting_excerpt=f"Project requirement: {r.canonical_name}",
                        source_location_json={"requirement": r.canonical_name},
                    )
                )

        # Connect Feature -> Operational Procedure (HAS_WORKFLOW_STEP)
        for p in existing_procs:
            ev_id = p.primary_evidence_id or fallback_ev_id
            if not ev_id:
                continue
            p_low = p.canonical_name.lower()
            for f in all_clean_features:
                f_low = f.canonical_name.lower()
                if f.primary_evidence_id == p.primary_evidence_id or any(tok in p_low for tok in f_low.split() if len(tok) > 4):
                    pending_drafts.append(
                        DiscoveredRelationshipDraft(
                            source_entity_id=f.id,
                            target_entity_id=p.id,
                            relationship_type=RelationshipType.HAS_WORKFLOW_STEP.value,
                            relationship_basis=RelationshipBasis.EXPLICIT.value,
                            confidence_score=0.90,
                            discovery_method="feature_workflow_step",
                            evidence_id=ev_id,
                            evidence_chunk_id=None,
                            knowledge_item_id=p.primary_knowledge_item_id,
                            supporting_excerpt=f"Workflow step for {f.canonical_name}: {p.canonical_name}",
                            source_location_json={"procedure": p.canonical_name},
                        )
                    )
                    break

        if pending_drafts:
            self._discovery_engine.persist_discovered_relationships(
                organisation_id=organisation_id,
                project_id=project_id,
                drafts=pending_drafts,
            )

        return seeded

    def run_reconstruction(
        self,
        *,
        organisation_id: uuid.UUID,
        project_id: uuid.UUID,
        run_id: uuid.UUID | None = None,
        include_llm_suggestions: bool = False,
    ) -> RelationshipReconstructionRun:
        """Execute full relationship discovery and graph reconstruction run."""
        start_time = time.monotonic()

        if run_id is not None:
            run = self._run_repo.get_run(run_id)
            if not run:
                raise ValueError(f"Run {run_id} not found")
        else:
            run = self._run_repo.create_run(organisation_id=organisation_id, project_id=project_id)

        self._run_repo.update_run_progress(run.id, status=RelationshipRunStatus.RUNNING.value)

        try:
            # 1. Seed Entities
            self.seed_entities_from_project_evidence(
                organisation_id=organisation_id,
                project_id=project_id,
            )

            # 2. Synthesize User-Facing Product Features & Workflows
            self.synthesize_user_facing_features(
                organisation_id=organisation_id,
                project_id=project_id,
            )

            # 3. Discover Exact Identifier Links
            exact_drafts = self._discovery_engine.discover_exact_identifier_links(
                project_id=project_id,
                organisation_id=organisation_id,
            )

            # 4. Discover Structured Connector Links
            connector_drafts = self._discovery_engine.discover_structured_connector_links(
                project_id=project_id,
                organisation_id=organisation_id,
            )

            # 5. Discover Contextual File Path Matches
            contextual_drafts = self._discovery_engine.discover_contextual_path_matches(
                project_id=project_id,
            )

            # 6. Discover Grounded Architecture & Component Relationships
            arch_drafts = self._discovery_engine.discover_architecture_relationships(
                project_id=project_id,
                organisation_id=organisation_id,
            )

            # 7. Optional LLM Extraction
            llm_drafts = []
            if include_llm_suggestions:
                llm_drafts = self._discovery_engine.discover_llm_assisted_relationships(
                    project_id=project_id,
                    organisation_id=organisation_id,
                )

            all_drafts = exact_drafts + connector_drafts + contextual_drafts + arch_drafts + llm_drafts

            # Persist Relationships
            created_count, updated_count = self._discovery_engine.persist_discovered_relationships(
                organisation_id=organisation_id,
                project_id=project_id,
                drafts=all_drafts,
            )

            explicit_count = sum(
                1 for d in all_drafts if d.relationship_basis == RelationshipBasis.EXPLICIT.value
            )
            inferred_count = sum(
                1 for d in all_drafts if d.relationship_basis == RelationshipBasis.INFERRED.value
            )

            # 6. Run Identity Resolution across entities of the same type
            all_entities = list(
                self._session.execute(
                    select(KnowledgeEntity)
                    .options(selectinload(KnowledgeEntity.aliases))
                    .where(
                        KnowledgeEntity.project_id == project_id,
                        KnowledgeEntity.is_deleted.is_(False),
                        KnowledgeEntity.is_stale.is_(False),
                    )
                )
                .scalars()
                .all()
            )
            # 6. Run Identity Resolution across person entities for cross-platform profile matching
            person_group = [e for e in all_entities if e.entity_type == EntityType.PERSON.value]
            if len(person_group) > 1:
                for i in range(len(person_group)):
                    for j in range(i + 1, min(i + 10, len(person_group))):
                        self._identity_service.evaluate_and_record_candidate(person_group[i], person_group[j])

            # 7. Index Decision Traceability Chains
            self._traceability_service.index_project_traceability(
                organisation_id=organisation_id,
                project_id=project_id,
            )

            # 8. Index Timeline Events from Evidence Items
            ents_by_ev: dict[uuid.UUID, list[KnowledgeEntity]] = {}
            for e in all_entities:
                if e.primary_evidence_id:
                    ents_by_ev.setdefault(e.primary_evidence_id, []).append(e)

            evidence_items = list(
                self._session.execute(
                    select(EvidenceItem).where(
                        EvidenceItem.project_id == project_id,
                        EvidenceItem.deleted_at.is_(None),
                    )
                )
                .scalars()
                .all()
            )
            for ev in evidence_items:
                matched_ents = ents_by_ev.get(ev.id, [])
                for matched_ent in matched_ents:
                    evt_title = (
                        f"{matched_ent.entity_type.replace('_', ' ').title()}: "
                        f"{matched_ent.canonical_name}"
                    )
                    self._timeline_repo.create_event(
                        organisation_id=organisation_id,
                        project_id=project_id,
                        entity_id=matched_ent.id,
                        evidence_id=ev.id,
                        event_type=matched_ent.entity_type,
                        title=evt_title,
                        summary=matched_ent.description,
                        occurred_at=ev.source_created_at or ev.created_at,
                        timestamp_precision=TimelinePrecision.EXACT_DATETIME.value,
                        timestamp_origin=TimelineOrigin.SOURCE_API.value,
                        is_synthetic=getattr(ev, "is_synthetic", False),
                    )

            duration_ms = int((time.monotonic() - start_time) * 1000)

            run = self._run_repo.update_run_progress(
                run.id,
                status=RelationshipRunStatus.COMPLETED.value,
                entities_count=len(all_entities),
                relationships_count=created_count + updated_count,
                explicit_count=explicit_count,
                inferred_count=inferred_count,
                duration_ms=duration_ms,
            )
            return run

        except Exception as exc:
            logger.exception("Relationship reconstruction run %s failed: %s", run.id, exc)
            self._session.rollback()
            duration_ms = int((time.monotonic() - start_time) * 1000)
            if self._run_repo.get_run(run.id) is not None:
                run = self._run_repo.update_run_progress(
                    run.id,
                    status=RelationshipRunStatus.FAILED.value,
                    duration_ms=duration_ms,
                    error_message=str(exc)[:500],
                )
            raise
