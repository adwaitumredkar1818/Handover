import sys
import os
import uuid
import time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.db.session import create_db_engine, create_session_factory
from app.core.config import get_settings
from app.models.job import BackgroundJob
from app.models.enums import BackgroundJobStatus, BackgroundJobType
from app.services.pipeline_coordinator import PipelineCoordinatorService
from sqlalchemy import select

settings = get_settings()
engine = create_db_engine(settings)
session_factory = create_session_factory(engine)

target_project_id = uuid.UUID("a79345eb-0464-4c8a-bb40-bbce15e9a206")

with session_factory() as session:
    coord = PipelineCoordinatorService(session)
    scheduled = coord.trigger_auto_pipeline(target_project_id)
    print(f"Triggered auto pipeline: scheduled {scheduled} jobs.")
    
    # Check top 10 jobs by priority across entire platform
    top_jobs = session.execute(
        select(BackgroundJob)
        .where(BackgroundJob.status.in_([BackgroundJobStatus.QUEUED.value, BackgroundJobStatus.RUNNING.value]))
        .order_by(BackgroundJob.priority.asc(), BackgroundJob.created_at.asc())
        .limit(10)
    ).scalars().all()
    
    print("\nTop 10 Jobs in Queue (Priority Order):")
    for j in top_jobs:
        is_target = " [TARGET PROJECT]" if j.project_id == target_project_id else ""
        print(f"Prio {j.priority:2d} | Status: {j.status:<8} | Type: {j.job_type:<25} | ID: {str(j.id)[:8]}{is_target}")
