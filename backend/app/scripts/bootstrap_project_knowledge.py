"""Deterministic Fast Knowledge Bootstrap Script for The Handover.

CLI command:
    python -m app.scripts.bootstrap_project_knowledge --project-id <PROJECT_ID>

Executes Stage 1 deterministic parsing on persisted project evidence without invoking Ollama,
persists grounded KnowledgeItems, reconciles graph projections, and advances graph versions.
"""

from __future__ import annotations

import argparse
import logging
import sys
import uuid
from typing import Any

from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.session import create_db_engine, create_session_factory, session_scope
from app.models.evidence import EvidenceItem
from app.models.knowledge import KnowledgeItem
from app.models.project import Project
from app.models.relationship import KnowledgeEntity, KnowledgeRelationship
from app.services.fast_extractor import FastKnowledgeExtractor
from app.services.knowledge_graphs import invalidate_knowledge_graph_cache
from app.services.relationship_coordinator import RelationshipCoordinatorService

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("bootstrap_project_knowledge")


def bootstrap_project_knowledge(
    *,
    project_id: uuid.UUID,
    force: bool = False,
) -> dict[str, Any]:
    """Execute Stage 1 deterministic reconstruction on persisted project evidence without Ollama."""
    settings = get_settings()
    engine = create_db_engine(settings)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        project = session.query(Project).filter_by(id=project_id).first()
        if not project:
            raise ValueError(f"Project with ID '{project_id}' does not exist.")

        logger.info(
            "Starting Stage 1 deterministic bootstrap for project '%s' (%s, org: %s)...",
            project.name,
            project.id,
            project.organisation_id,
        )

        evidence_items = (
            session.query(EvidenceItem)
            .filter(
                EvidenceItem.project_id == project_id,
                EvidenceItem.deleted_at.is_(None),
            )
            .order_by(EvidenceItem.created_at.asc())
            .all()
        )

        total_evidence = len(evidence_items)
        logger.info("Found %d persisted evidence item(s) for project.", total_evidence)

        if total_evidence == 0:
            logger.warning("No evidence items found. Nothing to bootstrap.")
            return {
                "project_id": str(project_id),
                "total_evidence": 0,
                "processed_evidence": 0,
                "knowledge_items_created": 0,
            }

        # Filter items needing deterministic processing
        extractor = FastKnowledgeExtractor(session)
        items_evaluated = 0
        items_processed = 0
        total_k_created = 0
        categories_tally: dict[str, int] = {}

        existing_fps = set(
            session.execute(
                select(KnowledgeItem.fingerprint).where(
                    KnowledgeItem.project_id == project_id,
                    KnowledgeItem.is_deleted.is_(False),
                )
            )
            .scalars()
            .all()
        )

        for idx, ev in enumerate(evidence_items, start=1):
            items_evaluated += 1
            meta = dict(ev.metadata_json or {})
            has_deterministic = "deterministic_fingerprint" in meta

            if has_deterministic and not force:
                continue

            created = extractor.extract_evidence_knowledge(
                evidence=ev,
                force_rerun=force,
                existing_fps=existing_fps,
                auto_commit=False,
            )
            items_processed += 1
            total_k_created += len(created)
            for k in created:
                categories_tally[k.category] = categories_tally.get(k.category, 0) + 1

            if idx % 10 == 0 or idx == total_evidence:
                session.commit()
                logger.info(
                    "Processed %d/%d evidence items (%d new KnowledgeItems created so far)...",
                    idx,
                    total_evidence,
                    total_k_created,
                )

        session.commit()

        # Reconcile graph projections from all supported project evidence
        logger.info("Reconciling graph projections and canonical relationships...")
        rel_coord = RelationshipCoordinatorService(session)
        rel_coord.run_reconstruction(
            organisation_id=project.organisation_id,
            project_id=project.id,
            include_llm_suggestions=False,
        )
        session.commit()
        invalidate_knowledge_graph_cache(project.id)

        # Retrieve resulting graph & knowledge metrics
        total_k = (
            session.query(func.count(KnowledgeItem.id))
            .filter_by(project_id=project.id, is_deleted=False)
            .scalar()
            or 0
        )
        total_e = (
            session.query(func.count(KnowledgeEntity.id)).filter_by(project_id=project.id).scalar()
            or 0
        )
        total_r = (
            session.query(func.count(KnowledgeRelationship.id))
            .filter_by(project_id=project.id)
            .scalar()
            or 0
        )

        graph_version = f"{total_k}:{total_e}:{total_r}"
        logger.info("Stage 1 bootstrap complete.")
        logger.info("  Total Evidence: %d", total_evidence)
        logger.info("  Evidence Processed: %d (Evaluated: %d)", items_processed, items_evaluated)
        logger.info("  New Knowledge Items Created: %d", total_k_created)
        logger.info("  Total Project Knowledge Items: %d", total_k)
        logger.info("  Total Graph Entities: %d", total_e)
        logger.info("  Total Graph Relationships: %d", total_r)
        logger.info("  Active Graph Version: %s", graph_version)
        logger.info("  Categories Breakdown: %s", categories_tally)

        return {
            "project_id": str(project_id),
            "project_name": project.name,
            "total_evidence": total_evidence,
            "items_processed": items_processed,
            "new_knowledge_created": total_k_created,
            "total_knowledge_items": total_k,
            "total_entities": total_e,
            "total_relationships": total_r,
            "graph_version": graph_version,
            "categories_tally": categories_tally,
        }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Deterministic Fast Knowledge Bootstrap Script (Stage 1)"
    )
    parser.add_argument("--project-id", required=True, type=str, help="Target Project UUID")
    parser.add_argument(
        "--force", action="store_true", help="Force re-extraction of already processed evidence"
    )
    args = parser.parse_args()

    try:
        pid = uuid.UUID(args.project_id)
    except ValueError:
        logger.error("Invalid project-id format. Must be a valid UUID string.")
        sys.exit(1)

    result = bootstrap_project_knowledge(project_id=pid, force=args.force)
    print("\n" + "=" * 60)
    print("STAGE 1 DETERMINISTIC KNOWLEDGE RECONSTRUCTION RESULTS")
    print("=" * 60)
    for k, v in result.items():
        print(f"  {k}: {v}")
    print("=" * 60)


if __name__ == "__main__":
    main()
