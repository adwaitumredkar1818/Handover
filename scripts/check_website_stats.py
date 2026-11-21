import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.db.session import create_db_engine, create_session_factory
from app.core.config import get_settings
from app.models.evidence import EvidenceItem, EvidenceChunk
from app.models.knowledge import KnowledgeItem, KnowledgeExtractionRun
from app.models.relationship import KnowledgeEntity, KnowledgeRelationship
from sqlalchemy import select, func
import uuid

settings = get_settings()
engine = create_db_engine(settings)
session_factory = create_session_factory(engine)

website_id = uuid.UUID("5446b943-e4a8-4881-b3ae-31ba4a06b10a")

with session_factory() as session:
    ev_count = session.execute(select(func.count(EvidenceItem.id)).where(EvidenceItem.project_id == website_id)).scalar()
    chunk_count = session.execute(select(func.count(EvidenceChunk.id)).where(EvidenceChunk.project_id == website_id)).scalar()
    k_count = session.execute(select(func.count(KnowledgeItem.id)).where(KnowledgeItem.project_id == website_id)).scalar()
    entity_count = session.execute(select(func.count(KnowledgeEntity.id)).where(KnowledgeEntity.project_id == website_id)).scalar()
    rel_count = session.execute(select(func.count(KnowledgeRelationship.id)).where(KnowledgeRelationship.project_id == website_id)).scalar()
    runs = session.execute(select(KnowledgeExtractionRun).where(KnowledgeExtractionRun.project_id == website_id)).scalars().all()
    
    print(f"Website Project Stats:")
    print(f"Evidence items: {ev_count}")
    print(f"Chunks: {chunk_count}")
    print(f"Knowledge items: {k_count}")
    print(f"Entities: {entity_count}")
    print(f"Relationships: {rel_count}")
    print(f"Runs count: {len(runs)}")
    for r in runs:
        print(f"  Run id={r.id}, status={r.status}, model={r.model_name}, claims={r.claims_persisted}")
