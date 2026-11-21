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
    failed_jobs = session.execute(
        select(BackgroundJob)
        .where(BackgroundJob.status == "failed")
        .order_by(BackgroundJob.updated_at.desc())
        .limit(20)
    ).scalars().all()
    
    print("=== RECENT FAILED JOBS ===")
    for j in failed_jobs:
        print(f"ID: {j.id}, Type: {j.job_type}, ErrorCode: {j.error_code}, Msg: {j.error_message}")
