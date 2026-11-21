import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.db.session import create_db_engine, create_session_factory
from app.core.config import get_settings
from app.models.job import BackgroundJob
from sqlalchemy import select

settings = get_settings()
engine = create_db_engine(settings)
session_factory = create_session_factory(engine)

with session_factory() as session:
    j = session.execute(select(BackgroundJob).where(BackgroundJob.id == "23804132-398e-4369-a7f6-b52787e1a9bd")).scalar_one_or_none()
    if j:
        print(f"Job: {j.id}")
        print(f"Status: {j.status}")
        print(f"Locked by: {j.locked_by}")
        print(f"Locked at: {j.locked_at}")
        print(f"Lease expires: {j.lease_expires_at}")
        print(f"Attempts: {j.retry_count}/{j.max_attempts}")
        print(f"Started at: {j.started_at}")
        print(f"Updated at: {j.updated_at}")
        print(f"Payload: {j.payload_json}")
