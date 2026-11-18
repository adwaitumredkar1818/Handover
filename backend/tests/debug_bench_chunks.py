from app.db.session import create_db_engine, create_session_factory
from app.core.config import get_settings
from app.models.evidence import EvidenceChunk
from sqlalchemy import select, text
import uuid

settings = get_settings()
engine = create_db_engine(settings)
sf = create_session_factory(engine)
s = sf()
try:
    p_id = uuid.UUID("0f73217a-dbbd-4ef6-92a9-16bace7aaba0")
    chunks = s.scalars(select(EvidenceChunk).where(EvidenceChunk.project_id == p_id)).all()
    print("Benchmark Project chunks count:", len(chunks))
    for c in chunks:
        print(f"  Chunk {c.id} | Status: {c.indexing_status} | SearchVector: {bool(c.search_vector)} | Text: {c.chunk_text[:60]}")
        
    # Test raw FTS query
    q = "PostgreSQL"
    raw_hits = s.execute(
        text("""
        SELECT ec.id, ec.chunk_text, ts_rank_cd(ec.search_vector, websearch_to_tsquery('english', :q)) as rnk
        FROM evidence_chunks ec
        WHERE ec.project_id = :p_id AND ec.search_vector @@ websearch_to_tsquery('english', :q)
        """).params(p_id=p_id, q=q)
    ).all()
    print(f"Raw FTS hits for '{q}':", len(raw_hits))
    for h in raw_hits:
        print("  Hit:", h[0], "Rank:", h[2], "Text:", h[1][:60])
finally:
    s.close()
