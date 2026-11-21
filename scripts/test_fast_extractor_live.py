import sys
import time
sys.path.insert(0, 'backend')

from app.db.session import create_db_engine, create_session_factory
from app.core.config import get_settings
from app.models.evidence import EvidenceItem
from app.services.fast_extractor import FastKnowledgeExtractor
from app.services.relationship_coordinator import RelationshipCoordinatorService
from sqlalchemy import select

settings = get_settings()
engine = create_db_engine(settings)
SessionFactory = create_session_factory(engine)

with SessionFactory() as session:
    # Pick one document or manifest evidence item
    ev = session.execute(
        select(EvidenceItem).where(
            EvidenceItem.deleted_at.is_(None)
        ).order_by(EvidenceItem.created_at.desc())
    ).scalars().first()

    if ev:
        print(f"Testing FastKnowledgeExtractor on Evidence: '{ev.title}' (category: {ev.category}, ID: {ev.id})")
        t0 = time.perf_counter()
        extractor = FastKnowledgeExtractor(session)
        items = extractor.extract_evidence_knowledge(evidence=ev, force_rerun=True)
        t1 = time.perf_counter()
        elapsed_ms = (t1 - t0) * 1000
        print(f"Extracted {len(items)} knowledge items in {elapsed_ms:.2f} ms!")
        for item in items[:5]:
            print(f"  - [{item.category}] {item.title}: {item.structured_summary[:80]}...")

        # Test fast relationship reconstruction
        t2 = time.perf_counter()
        rel_service = RelationshipCoordinatorService(session)
        run = rel_service.run_reconstruction(
            organisation_id=ev.organisation_id,
            project_id=ev.project_id,
            include_llm_suggestions=False,
        )
        session.commit()
        t3 = time.perf_counter()
        print(f"Relationship reconstruction completed in {(t3 - t2):.2f} seconds! Run ID: {run.id}")
    else:
        print("No evidence items found to test.")
