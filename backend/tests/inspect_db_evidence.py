from app.db.session import create_db_engine, create_session_factory
from app.core.config import get_settings
from app.models.project import Project
from app.models.evidence import EvidenceItem, EvidenceChunk
from sqlalchemy import select, func

settings = get_settings()
engine = create_db_engine(settings)
sf = create_session_factory(engine)
s = sf()
try:
    projects = s.scalars(select(Project)).all()
    print(f"Projects count: {len(projects)}")
    for p in projects:
        ev_count = s.scalar(select(func.count(EvidenceItem.id)).where(EvidenceItem.project_id == p.id))
        chunk_count = s.scalar(select(func.count(EvidenceChunk.id)).where(EvidenceChunk.project_id == p.id))
        print(f"  Project {p.id}: '{p.name}' - Evidence items: {ev_count}, Chunks: {chunk_count}")
finally:
    s.close()
