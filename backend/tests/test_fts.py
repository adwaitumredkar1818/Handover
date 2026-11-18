from app.db.session import create_db_engine, create_session_factory
from app.core.config import get_settings
from app.models.evidence import EvidenceChunk
from sqlalchemy import select, func, text
import uuid

settings = get_settings()
engine = create_db_engine(settings)
sf = create_session_factory(engine)
s = sf()
try:
    p_id = uuid.UUID("5b30f757-4e93-41c1-b0f3-02f5950af30b")
    chunks = s.scalars(select(EvidenceChunk).where(EvidenceChunk.project_id == p_id)).all()
    print("Project 5b30... chunks count:", len(chunks))
    for c in chunks:
        print("  ID:", c.id, "| search_vector:", c.search_vector, "| Text:", c.chunk_text[:80])
    
    # Check null count across entire DB
    null_count = s.execute(text("SELECT count(*) FROM evidence_chunks WHERE search_vector IS NULL")).scalar()
    populated_count = s.execute(text("SELECT count(*) FROM evidence_chunks WHERE search_vector IS NOT NULL")).scalar()
    print(f"Entire DB: search_vector NULL={null_count}, POPULATED={populated_count}")
finally:
    s.close()
