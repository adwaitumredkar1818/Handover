import sys
sys.path.insert(0, 'backend')
from app.core.config import get_settings
from app.db.session import create_db_engine, create_session_factory
from sqlalchemy import text

eng = create_db_engine(get_settings())
S = create_session_factory(eng)
with S() as s:
    p = s.execute(text("SELECT id, name, status, created_at FROM projects WHERE id = 'b5c070cb-4919-4296-88b6-442a0644f72a'")).mappings().fetchone()
    print("Project:", dict(p) if p else "NOT FOUND")

    job_types = s.execute(text("SELECT job_type, status, count(id) FROM background_jobs GROUP BY job_type, status ORDER BY count(id) DESC")).fetchall()
    print("\nJOB COUNTS BY TYPE AND STATUS:")
    for jt in job_types:
        print(jt)

    # Breakdown by project of queued jobs
    proj_queued = s.execute(text("SELECT project_id, job_type, count(id) FROM background_jobs WHERE status = 'queued' GROUP BY project_id, job_type ORDER BY count(id) DESC")).fetchall()
    print("\nQUEUED JOBS BY PROJECT:")
    for pq in proj_queued:
        proj_name = s.execute(text(f"SELECT name FROM projects WHERE id = '{pq[0]}'")).scalar()
        print(f"Project '{proj_name}' ({pq[0]}): {pq[2]} queued {pq[1]} jobs")
