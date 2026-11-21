"""Audit Priority 1 and Priority 2 for Rashkar Project."""

import os
import sys
import uuid
from collections import Counter
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.core.config import get_settings
from app.db.session import create_db_engine, create_session_factory
from app.models.evidence import EvidenceItem, EvidenceChunk
from app.models.knowledge import KnowledgeItem, KnowledgeEvidenceLink, KnowledgeExtractionRun
from app.models.relationship import KnowledgeEntity, KnowledgeRelationship, RelationshipEvidenceLink
from sqlalchemy import func

def main():
    settings = get_settings()
    engine = create_db_engine(settings)
    session_factory = create_session_factory(engine)
    pid = uuid.UUID("17ca9ab2-bbb8-4e61-9f52-4fbd6a7ce9c8")

    with session_factory() as session:
        print("=== PRIORITY 2: EVIDENCE DISTRIBUTION AUDIT ===", flush=True)
        evidence_items = session.query(EvidenceItem).filter_by(project_id=pid).all()
        print(f"Total Evidence Items: {len(evidence_items)}", flush=True)
        ev_cat_counts = Counter(e.category for e in evidence_items)
        for cat, cnt in ev_cat_counts.items():
            print(f"  Category '{cat}': {cnt}", flush=True)

        print("\nAll non-commit evidence items:", flush=True)
        for e in evidence_items:
            if e.category != "commit":
                print(f"  ID: {e.id} | Cat: {e.category} | Title: {e.title} | ExtID: {e.source_external_id} | Created: {e.created_at}", flush=True)

        commit_items = [e for e in evidence_items if e.category == "commit"]
        print(f"\nTotal commit items: {len(commit_items)}", flush=True)

        print("\n=== PRIORITY 1: KNOWLEDGE ITEMS & DETERMINISTIC AUDIT ===", flush=True)
        items = session.query(KnowledgeItem).filter_by(project_id=pid).all()
        print(f"Total KnowledgeItems: {len(items)}", flush=True)

        runs = session.query(KnowledgeExtractionRun).filter_by(project_id=pid).all()
        print(f"Total Extraction Runs: {len(runs)}", flush=True)
        for r in runs:
            print(f"  Run: {r.id} | Status: {r.status} | Model: {r.model_name} | Persisted: {r.claims_persisted} | Batches: {r.batches_executed} | Created: {r.created_at}", flush=True)

        item_by_run = Counter(str(i.extraction_run_id) if i.extraction_run_id else "deterministic_or_none" for i in items)
        for r_id, cnt in item_by_run.items():
            print(f"  ExtractionRun {r_id}: {cnt} items", flush=True)

        # Categorize item semantics
        cat_counts = Counter(i.category for i in items)
        print("\nKnowledge Items by Category:", flush=True)
        for c, cnt in cat_counts.most_common():
            print(f"  {c}: {cnt}", flush=True)

        # Inspect title types
        manifest_deps = [i for i in items if i.category == "dependencies" or "manifest" in (i.payload_json or {}) or "package" in i.title.lower()]
        arch_items = [i for i in items if i.category in ("technical_architecture", "architecture_technical")]
        work_items = [i for i in items if i.category in ("work_items", "work_progress")]
        owner_items = [i for i in items if i.category in ("responsibilities_ownership",)]
        overview_items = [i for i in items if i.category in ("project_overview_context",)]
        operational_items = [i for i in items if i.category in ("operational_historical",)]

        print(f"\nSub-breakdown of items:", flush=True)
        print(f"  Dependencies / Manifests: {len(manifest_deps)}", flush=True)
        print(f"  Architecture / Technical: {len(arch_items)}", flush=True)
        print(f"  Work items / Commits: {len(work_items)}", flush=True)
        print(f"  Ownership / Maintainers: {len(owner_items)}", flush=True)
        print(f"  Project Overview / Context: {len(overview_items)}", flush=True)
        print(f"  Operational / Historical / Headings: {len(operational_items)}", flush=True)

        # Heading / outline check
        heading_items = [i for i in items if "heading" in (i.payload_json or {}) or i.title.startswith("Section:") or i.title.startswith("Outline:")]
        commit_meta_items = [i for i in items if "commit_hash" in (i.payload_json or {}) or i.title.startswith("Commit:")]
        print(f"  Document Section / Outline Headings: {len(heading_items)}", flush=True)
        print(f"  Commit Metadata Items: {len(commit_meta_items)}", flush=True)

        # Check Human-Verified vs Generated
        review_counts = Counter(i.review_status for i in items)
        print("\nReview Status of KnowledgeItems:", flush=True)
        for rs, cnt in review_counts.items():
            print(f"  {rs}: {cnt}", flush=True)

        human_verified = [i for i in items if i.review_status in ("verified", "approved") or i.epistemic_status == "human_verified"]
        print(f"  Items incorrectly/correctly marked human_verified: {len(human_verified)}", flush=True)

        # Entities check
        entities = session.query(KnowledgeEntity).filter_by(project_id=pid).all()
        print(f"\nTotal KnowledgeEntities: {len(entities)}", flush=True)
        ent_types = Counter(e.entity_type for e in entities)
        for et, cnt in ent_types.most_common():
            print(f"  Type '{et}': {cnt}", flush=True)

        human_verified_ent = [e for e in entities if e.resolution_status == "verified"]
        print(f"  Entities marked human-verified: {len(human_verified_ent)}", flush=True)

        # Relationships check
        rels = session.query(KnowledgeRelationship).filter_by(project_id=pid).all()
        print(f"\nTotal KnowledgeRelationships: {len(rels)}", flush=True)
        rel_types = Counter(r.relationship_type for r in rels)
        for rt, cnt in rel_types.most_common():
            print(f"  Type '{rt}': {cnt}", flush=True)

        human_verified_rels = [r for r in rels if r.verification_status in ("verified", "human_verified")]
        print(f"  Relationships marked human-verified: {len(human_verified_rels)}", flush=True)

        # Provenance check for relationships
        rel_evidence = session.query(RelationshipEvidenceLink).all()
        rel_ids_with_evidence = set(re.relationship_id for re in rel_evidence)
        print(f"  Relationships with direct RelationshipEvidenceLink: {len(rel_ids_with_evidence)} / {len(rels)}", flush=True)

if __name__ == "__main__":
    main()
