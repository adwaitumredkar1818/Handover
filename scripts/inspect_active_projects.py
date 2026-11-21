import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.db.session import create_db_engine, create_session_factory
from app.core.config import get_settings
from app.models.project import Project, ProjectMembership
from app.models.evidence import EvidenceItem
from app.models.integration import ProjectSourceMapping
from app.models.user import User
from sqlalchemy import select, func

settings = get_settings()
engine = create_db_engine(settings)
session_factory = create_session_factory(engine)

with session_factory() as session:
    projects = session.execute(select(Project).order_by(Project.created_at.desc())).scalars().all()
    print(f"Total projects: {len(projects)}")
    for p in projects:
        ev_count = session.execute(select(func.count(EvidenceItem.id)).where(EvidenceItem.project_id == p.id)).scalar_one()
        mapping_count = session.execute(select(func.count(ProjectSourceMapping.id)).where(ProjectSourceMapping.project_id == p.id)).scalar_one()
        members = session.execute(select(ProjectMembership).where(ProjectMembership.project_id == p.id)).scalars().all()
        print(f"Project ID: {p.id} | Name: '{p.name}' | Slug: '{p.slug}' | Evidence: {ev_count} | Mappings: {mapping_count} | Members: {len(members)}")
