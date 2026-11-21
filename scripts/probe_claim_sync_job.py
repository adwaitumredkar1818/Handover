import sys
sys.path.insert(0, 'backend')
from app.core.config import get_settings
from app.db.session import create_db_engine, create_session_factory
from app.models.enums import BackgroundJobType
from app.repositories.job import BackgroundJobRepository
from app.core.security import utc_now
from sqlalchemy import text

eng = create_db_engine(get_settings())
S = create_session_factory(eng)
with S() as s:
    j1 = s.execute(text("SELECT id, status, locked_by, lease_expires_at, attempt_count, max_attempts, next_retry_at FROM background_jobs WHERE id = '16352b2d-f411-46df-aa37-84b991513012'")).mappings().fetchone()
    print("Job 16352b2d:", dict(j1) if j1 else "NOT FOUND")

    repo = BackgroundJobRepository(s)
    now = utc_now()
    claimed = repo.claim_next_job(worker_id="test-probe", lease_seconds=60, now=now, job_type=BackgroundJobType.SOURCE_SYNC.value)
    if claimed:
        print("Probe claimed job:", claimed.id, claimed.job_type, claimed.status, claimed.payload_json)
        s.rollback()
    else:
        print("Probe could NOT claim any source_sync job!")
