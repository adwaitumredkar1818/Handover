"""Clean polluted deterministic records and reconcile two-stage statuses on Rashkar."""

from __future__ import annotations

import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from sqlalchemy import or_, select
from app.core.config import get_settings
from app.db.session import create_db_engine, create_session_factory
from app.models.enums import EpistemicStatus, KnowledgeReviewStatus
from app.models.evidence import EvidenceItem
from app.models.knowledge import KnowledgeItem
from app.models.project import Project
from app.models.relationship import KnowledgeEntity, KnowledgeRelationship
from app.services.fast_extractor import is_evidence_semantic_eligible
from app.services.knowledge_graphs import invalidate_knowledge_graph_cache
from app.services.relationship_coordinator import RelationshipCoordinatorService

PID = uuid.UUID("17ca9ab2-bbb8-4e61-9f52-4fbd6a7ce9c8")
ADR_001_ID = uuid.UUID("2498e191-42f9-4d2a-8481-8cfeabe0f8f1")
FALSE_TECH_NAMES = {"redis", "next.js", "tailwind css", "typescript", "cloudflare"}


def main() -> None:
    settings = get_settings()
    engine = create_db_engine(settings)
    sf = create_session_factory(engine)

    with sf() as session:
        proj = session.get(Project, PID)
        assert proj is not None, f"Project {PID} not found"
        org_id = proj.organisation_id

        # 1. Mark leftover ungrounded Section-3A prose-regex Technology items as stale (preserve history)
        k_items = list(
            session.execute(
                select(KnowledgeItem).where(
                    KnowledgeItem.project_id == PID,
                    KnowledgeItem.is_deleted.is_(False),
                )
            )
            .scalars()
            .all()
        )
        stale_k_count = 0
        tagged_outline_count = 0
        for ki in k_items:
            payload = dict(ki.structured_payload or {})
            if (
                ki.extraction_model == "fast_deterministic_parser_v1"
                and ki.title.startswith("Technology:")
                and "manifest_file" not in payload
                and not ki.is_stale
            ):
                ki.is_stale = True
                ki.stale_reason = "Superseded: ungrounded prose technology match replaced by manifest-grounded extraction"
                stale_k_count += 1
            elif (
                ki.extraction_model == "fast_deterministic_parser_v1"
                and (ki.title.startswith("Document Section:") or "section_title" in payload)
                and not payload.get("is_document_outline")
            ):
                payload["is_document_outline"] = True
                ki.structured_payload = payload
                tagged_outline_count += 1

        print(f"Marked {stale_k_count} leftover prose Technology KnowledgeItems stale; tagged {tagged_outline_count} document outlines.")

        # 2. Mark polluted KnowledgeEntities and their attached KnowledgeRelationships as stale
        entities = list(
            session.execute(
                select(KnowledgeEntity).where(
                    KnowledgeEntity.project_id == PID,
                    KnowledgeEntity.is_deleted.is_(False),
                )
            )
            .scalars()
            .all()
        )
        ki_by_id = {ki.id: ki for ki in k_items}
        staled_entity_ids: set[uuid.UUID] = set()

        for ent in entities:
            norm = (ent.canonical_name or "").strip().lower()
            meta = dict(ent.metadata_json or {})
            should_stale = False

            if ent.entity_type == "operational_procedure" and (
                norm.startswith(("document section", "section:", "outline:"))
                or "section_title" in meta
                or meta.get("is_document_outline")
            ):
                should_stale = True
            elif ent.entity_type == "feature" and norm in {"commit", "document section"}:
                should_stale = True
            elif ent.entity_type == "work_item" and norm.startswith(("commit:", "pull request:")):
                should_stale = True
            elif ent.entity_type == "technology" and norm in FALSE_TECH_NAMES and not meta.get("manifest_path"):
                should_stale = True

            if should_stale and not ent.is_stale:
                ent.is_stale = True
                staled_entity_ids.add(ent.id)
            elif ent.is_stale:
                staled_entity_ids.add(ent.id)

            # Reset any hardcoded unverified "approved" status unless backed by a genuinely human-verified KnowledgeItem
            linked_ki = ki_by_id.get(ent.primary_knowledge_item_id) if ent.primary_knowledge_item_id else None
            is_actually_human_verified = (
                linked_ki is not None
                and (
                    linked_ki.epistemic_status == EpistemicStatus.HUMAN_VERIFIED.value
                    or linked_ki.review_status == KnowledgeReviewStatus.APPROVED.value
                )
            )
            if meta.get("verification_status") == "approved" and not is_actually_human_verified:
                meta["verification_status"] = linked_ki.review_status if linked_ki else "pending_review"
                ent.metadata_json = meta

        stale_rel_count = 0
        if staled_entity_ids:
            rels = list(
                session.execute(
                    select(KnowledgeRelationship).where(
                        KnowledgeRelationship.project_id == PID,
                        KnowledgeRelationship.is_stale.is_(False),
                        or_(
                            KnowledgeRelationship.source_entity_id.in_(staled_entity_ids),
                            KnowledgeRelationship.target_entity_id.in_(staled_entity_ids),
                        ),
                    )
                )
                .scalars()
                .all()
            )
            for rel in rels:
                rel.is_stale = True
                rel.stale_reason = "Attached entity excluded as document outline/commit metadata noise"
                stale_rel_count += 1

        print(f"Marked {len(staled_entity_ids)} polluted KnowledgeEntities stale and {stale_rel_count} attached relationships stale.")

        # 3. Reconcile EvidenceItem.metadata_json lifecycle_stage & semantic_status across all 141 items
        ev_items = list(
            session.execute(
                select(EvidenceItem).where(
                    EvidenceItem.project_id == PID,
                    EvidenceItem.deleted_at.is_(None),
                )
            )
            .scalars()
            .all()
        )
        ev_counts_summary: dict[tuple[str, str], int] = {}
        for ev in ev_items:
            m = dict(ev.metadata_json or {})
            text_len = len(ev.content.extracted_text.strip()) if getattr(ev, "content", None) and ev.content.extracted_text else (ev.file_size_bytes or 0)
            if ev.id == ADR_001_ID:
                m["lifecycle_stage"] = "graph_updated"
                m["semantic_status"] = "completed"
            else:
                eligible = is_evidence_semantic_eligible(
                    category=ev.category,
                    title=ev.title,
                    mime_type=ev.mime_type,
                    text_len=text_len,
                    metadata_json=m,
                )
                m["lifecycle_stage"] = "deterministic_ready"
                m["semantic_status"] = "queued" if eligible else "not_applicable"
            ev.metadata_json = m
            key = (m["lifecycle_stage"], m["semantic_status"])
            ev_counts_summary[key] = ev_counts_summary.get(key, 0) + 1

        print(f"Reconciled {len(ev_items)} EvidenceItems: {ev_counts_summary}")
        session.flush()

        # 4. Re-run RelationshipCoordinatorService (deterministic) to update implementation_basis & graph consistency
        run = RelationshipCoordinatorService(session).run_reconstruction(
            organisation_id=org_id,
            project_id=PID,
            include_llm_suggestions=False,
        )
        session.commit()
        invalidate_knowledge_graph_cache(PID)
        print(f"Reconciliation run completed: id={run.id}, status={run.status}")


if __name__ == "__main__":
    main()
