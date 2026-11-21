import sys, os, uuid, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from app.db.session import create_db_engine, create_session_factory
from app.core.config import get_settings
from app.models.evidence import EvidenceItem
from sqlalchemy import select

settings = get_settings()
engine = create_db_engine(settings)
session_factory = create_session_factory(engine)
ctf_pid = uuid.UUID("4c8cedca-66fd-47b5-937e-93d4da866722")

with session_factory() as session:
    items = session.execute(
        select(EvidenceItem).where(
            EvidenceItem.project_id == ctf_pid,
        ).limit(5)
    ).scalars().all()
    for item in items:
        print("=" * 60)
        print(f"Title: {item.title}")
        print(f"Author Identity: {item.source_author_identity}")
        print("metadata_json:", json.dumps(item.metadata_json, indent=2))
