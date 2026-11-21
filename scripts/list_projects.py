import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.db.session import create_db_engine, create_session_factory
from app.core.config import get_settings
from app.models.project import Project
from sqlalchemy import select

settings = get_settings()
engine = create_db_engine(settings)
session_factory = create_session_factory(engine)

with session_factory() as session:
    projects = session.execute(select(Project)).scalars().all()
    for p in projects:
        print(f"ID: {p.id} | Name: '{p.name}' | Slug: '{p.slug}' | Org: {p.organisation_id}")
