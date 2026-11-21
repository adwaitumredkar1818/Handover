import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.db.session import create_db_engine, create_session_factory
from app.core.config import get_settings
from app.models.job import BackgroundJob
from sqlalchemy import select, update
import uuid

settings = get_settings()
engine = create_db_engine(settings)
session_factory = create_session_factory(engine)

website_id = uuid.UUID("5446b943-e4a8-4881-b3ae-31ba4a06b10a")

with session_factory() as session:
    # Reset 1 failed indexing job to queued to test with running ChromaDB
    job = session.execute(
        select(BackgroundJob)
        .where(
            BackgroundJob.project_id == website_id,
            BackgroundJob.job_type == "evidence_indexing",
            BackgroundJob.status == "failed",
        )
    ).scalars().first()
    
    if job:
        print(f"Resetting job {job.id} (evidence_id={job.evidence_id}) to queued...")
        job.status = "queued"
        job.attempt_count = 0
        job.error_code = None
        job.error_message = None
        job.locked_by = None
        job.lease_expires_at = None
        session.commit()
        print("Job reset committed.")
    else:
        print("No failed job found.")
