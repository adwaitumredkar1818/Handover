import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.db.session import create_db_engine, create_session_factory
from app.core.config import get_settings
from app.models.job import BackgroundJob
from sqlalchemy import select
import uuid

settings = get_settings()
engine = create_db_engine(settings)
session_factory = create_session_factory(engine)

website_id = uuid.UUID("5446b943-e4a8-4881-b3ae-31ba4a06b10a")

with session_factory() as session:
    jobs = session.execute(
        select(BackgroundJob)
        .where(BackgroundJob.project_id == website_id)
        .order_by(BackgroundJob.created_at.desc())
    ).scalars().all()
    
    print(f"Total jobs for Website: {len(jobs)}")
    for j in jobs:
        print(f"ID: {j.id}, Type: {j.job_type}, Status: {j.status}, Attempts: {j.attempt_count}, Err: {j.error_code} - {j.error_message}")
