import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.db.session import create_db_engine, create_session_factory
from app.core.config import get_settings
from app.models.job import BackgroundJob
from app.models.project import Project
from sqlalchemy import select, func

settings = get_settings()
engine = create_db_engine(settings)
session_factory = create_session_factory(engine)

with session_factory() as session:
    print("=================================================================")
    print("BACKGROUND JOBS AUDIT ACROSS ALL PROJECTS")
    print("=================================================================")
    
    rows = session.execute(
        select(
            BackgroundJob.project_id,
            BackgroundJob.job_type,
            BackgroundJob.status,
            func.count(BackgroundJob.id),
        ).group_by(
            BackgroundJob.project_id,
            BackgroundJob.job_type,
            BackgroundJob.status,
        )
    ).all()
    
    print("\nSummary by Project, Job Type, and Status:")
    for proj_id, j_type, status, cnt in rows:
        proj = session.get(Project, proj_id) if proj_id else None
        p_name = proj.name if proj else "GLOBAL/NONE"
        print(f"  Project: {p_name} ({proj_id}) | Type: {j_type} | Status: {status} | Count: {cnt}")
        
    running_jobs = session.execute(
        select(BackgroundJob).where(BackgroundJob.status.in_(["running", "queued"]))
    ).scalars().all()
    print(f"\nCurrently Active (Running / Queued) Jobs ({len(running_jobs)}):")
    for rj in running_jobs:
        proj = session.get(Project, rj.project_id) if rj.project_id else None
        p_name = proj.name if proj else "GLOBAL"
        print(f"  Job {rj.id} | Project: {p_name} | Type: {rj.job_type} | Status: {rj.status} | Attempts: {rj.attempt_count}/{rj.max_attempts} | LockedBy: {rj.locked_by}")
        print(f"    Payload: {rj.payload_json}")
        
    failed_jobs = session.execute(
        select(BackgroundJob).where(BackgroundJob.status == "failed")
    ).scalars().all()
    print(f"\nFailed Jobs Summary ({len(failed_jobs)}):")
    failure_reasons = {}
    for fj in failed_jobs:
        err = f"[{fj.error_code}] {fj.error_message}"
        failure_reasons[err] = failure_reasons.get(err, 0) + 1
    for reason, cnt in failure_reasons.items():
        print(f"  Count {cnt}: {reason}")
