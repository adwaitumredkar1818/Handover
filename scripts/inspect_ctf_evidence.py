import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.db.session import create_db_engine, create_session_factory
from app.core.config import get_settings
from app.models.evidence import EvidenceItem
from sqlalchemy import select
import uuid
import json

settings = get_settings()
engine = create_db_engine(settings)
session_factory = create_session_factory(engine)
ctf_pid = uuid.UUID("4c8cedca-66fd-47b5-937e-93d4da866722")

with session_factory() as session:
    items = session.execute(
        select(EvidenceItem).where(EvidenceItem.project_id == ctf_pid).order_by(EvidenceItem.created_at.desc())
    ).scalars().all()
    print(f"Total evidence in CTF: {len(items)}")
    for item in items:
        meta = item.metadata_json or {}
        print("-" * 50)
        print(f"ID: {item.id} | Type: {item.source_type} | Title: {item.title}")
        print(f"  Author Identity: {item.source_author_identity}")
        print(f"  Author Name: {meta.get('author_name')} | Email: {meta.get('author_email')}")
        print(f"  Committer Name: {meta.get('committer_name')} | Email: {meta.get('committer_email')}")
        print(f"  GitHub Author: {meta.get('github_author_login') or meta.get('author_login')} | Committer Login: {meta.get('github_committer_login') or meta.get('committer_login')}")
        print(f"  Ext ID: {item.source_external_id}")
