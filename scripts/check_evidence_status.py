import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.db.session import create_db_engine, create_session_factory
from app.core.config import get_settings
from app.models.evidence import EvidenceItem
from app.models.project import Project
from app.models.job import BackgroundJob
from sqlalchemy import select, func

settings = get_settings()
engine = create_db_engine(settings)
session_factory = create_session_factory(engine)

with session_factory() as session:
    projects = session.execute(select(Project)).scalars().all()
    print("=== PROJECTS ===")
    for p in projects:
        print(f"Project: {p.name} (id={p.id})")
        ev_items = session.execute(
            select(EvidenceItem.source_type, EvidenceItem.category, EvidenceItem.processing_status, EvidenceItem.indexing_status, func.count())
            .where(EvidenceItem.project_id == p.id, EvidenceItem.deleted_at.is_(None))
            .group_by(EvidenceItem.source_type, EvidenceItem.category, EvidenceItem.processing_status, EvidenceItem.indexing_status)
        ).all()
        for row in ev_items:
            print(f"  Source: {row[0]}, Category: {row[1]}, Proc: {row[2]}, Index: {row[3]} -> Count: {row[4]}")
    
    print("\n=== BACKGROUND JOBS ===")
    jobs = session.execute(
        select(BackgroundJob.job_type, BackgroundJob.status, func.count())
        .group_by(BackgroundJob.job_type, BackgroundJob.status)
    ).all()
    for j in jobs:
        print(f"Job: {j[0]}, Status: {j[1]} -> Count: {j[2]}")
