import sys
sys.path.insert(0, 'backend')
from app.core.config import get_settings
from app.db.session import create_db_engine, create_session_factory
from sqlalchemy import text

eng = create_db_engine(get_settings())
S = create_session_factory(eng)
with S() as s:
    jobs = s.execute(text("SELECT id, job_type, status, error_code, error_message, created_at, started_at, completed_at, payload_json FROM background_jobs WHERE created_at >= '2026-11-17 17:00:00+00' ORDER BY created_at DESC")).mappings().fetchall()
    print(f"Jobs since 17:00: {len(jobs)}")
    for j in jobs:
        print(dict(j))

    mapping = s.execute(text("SELECT * FROM project_source_mappings WHERE external_resource_name = 'Rashkar'")).mappings().fetchone()
    print("\nRashkar mapping:")
    if mapping:
        print(dict(mapping))
        proj_id = mapping['project_id']
        proj = s.execute(text(f"SELECT id, name, organisation_id FROM projects WHERE id = '{proj_id}'")).mappings().fetchone()
        print("Project for Rashkar:", dict(proj) if proj else "NOT FOUND")
        
        # Check any background jobs for this project
        proj_jobs = s.execute(text(f"SELECT id, job_type, status, created_at, started_at, completed_at FROM background_jobs WHERE project_id = '{proj_id}' ORDER BY created_at DESC")).mappings().fetchall()
        print(f"\nBackground jobs for project {proj_id}: {len(proj_jobs)}")
        for pj in proj_jobs:
            print(dict(pj))
            
        # Check evidence for this project
        ev_items = s.execute(text(f"SELECT id, title, category, source_type, provider, processing_status, indexing_status, created_at FROM evidence WHERE project_id = '{proj_id}' ORDER BY created_at DESC")).mappings().fetchall()
        print(f"\nEvidence items for project {proj_id}: {len(ev_items)}")
        for ev in ev_items:
            print(dict(ev))
    else:
        print("Rashkar mapping NOT FOUND")
