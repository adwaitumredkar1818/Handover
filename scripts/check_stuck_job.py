import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.db.session import create_db_engine, create_session_factory
from app.core.config import get_settings
from app.models.job import BackgroundJob
import uuid

settings = get_settings()
engine = create_db_engine(settings)
session_factory = create_session_factory(engine)

with session_factory() as session:
    j = session.get(BackgroundJob, uuid.UUID("23804132-398e-4369-a7f6-b52787e1a9bd"))
    if j:
        print(f"Job 23804132: status={j.status}, created_at={j.created_at}, locked_at={j.locked_at}, lease_expires_at={j.lease_expires_at}, locked_by={j.locked_by}")
    
    j2 = session.get(BackgroundJob, uuid.UUID("3ea7b7f0-1a94-4ef4-b735-8e62206028f7"))
    if j2:
        print(f"Job 3ea7b7f0 (test): status={j2.status}, created_at={j2.created_at}, locked_at={j2.locked_at}, lease_expires_at={j2.lease_expires_at}, locked_by={j2.locked_by}")
