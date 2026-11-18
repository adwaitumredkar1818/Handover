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
    chunks = s.scalars(select(EvidenceChunk).limit(10)).all()
    print(f"Sample evidence chunks in DB: {len(chunks)}")
    for c in chunks:
        print(f"  Chunk {c.id} | Project: {c.project_id} | Type: {c.chunk_type} | Content: {c.chunk_text[:100]}...")
finally:
    s.close()
