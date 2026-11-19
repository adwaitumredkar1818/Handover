from app.db.session import create_db_engine, create_session_factory
from app.core.config import get_settings
from app.models.evidence import EvidenceChunk
from sqlalchemy import select
import uuid

settings = get_settings()
engine = create_db_engine(settings)
sf = create_session_factory(engine)
s = sf()
try:
    p_id = uuid.UUID("5b30f757-4e93-41c1-b0f3-02f5950af30b")
    chunks = s.scalars(select(EvidenceChunk).where(EvidenceChunk.project_id == p_id)).all()
    print(f"Chunks in project {p_id}: {len(chunks)}")
    for c in chunks:
        print(f"  ID: {c.id} | EvidenceID: {c.evidence_id} | IndexingStatus: {c.indexing_status} | Text: {c.chunk_text}")
finally:
    s.close()
