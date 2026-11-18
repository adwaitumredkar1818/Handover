from app.db.session import create_db_engine, create_session_factory
from app.core.config import get_settings
from app.models.evidence import EvidenceChunk
from sqlalchemy import select
from collections import Counter

settings = get_settings()
engine = create_db_engine(settings)
sf = create_session_factory(engine)
s = sf()
try:
    chunks = s.scalars(select(EvidenceChunk)).all()
    print(f"Total chunks in entire DB: {len(chunks)}")
    by_proj = Counter(str(c.project_id) for c in chunks)
    for p, count in by_proj.most_common(10):
        print(f"  Project {p}: {count} chunks")
finally:
    s.close()
