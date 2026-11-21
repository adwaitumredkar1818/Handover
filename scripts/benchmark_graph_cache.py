import time
import httpx
from datetime import timedelta
import hashlib
import uuid
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.db.session import create_db_engine, create_session_factory
from app.core.config import get_settings
from app.core.security import create_access_token, utc_now
from app.repositories.auth import RefreshSessionRepository
from app.models.user import User
from sqlalchemy import select

settings = get_settings()
engine = create_db_engine(settings)
session_factory = create_session_factory(engine)
target_project_id = uuid.UUID("a79345eb-0464-4c8a-bb40-bbce15e9a206")

with session_factory() as session:
    user = session.execute(select(User).where(User.id == uuid.UUID("4c2c7aff-6049-40e0-b359-678bdb2590bf"))).scalar_one()
    token_family_id = uuid.uuid4()
    now = utc_now()
    repo = RefreshSessionRepository(session)
    repo.create(
        user_id=user.id,
        token_family_id=token_family_id,
        token_hash=hashlib.sha256(token_family_id.bytes).hexdigest(),
        expires_at=now + timedelta(days=7),
    )
    session.commit()
    token, _ = create_access_token(user_id=user.id, session_family_id=token_family_id, settings=settings, now=now)

headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
client = httpx.Client(base_url="http://127.0.0.1:8000", headers=headers, timeout=10.0)

print("--- CACHED GRAPH RETRIEVAL BENCHMARKS ---")
for path in ["technology-stack", "system-architecture", "features-workflows"]:
    t0 = time.perf_counter()
    res = client.get(f"/api/v1/projects/{target_project_id}/knowledge-intelligence/graphs/{path}")
    elapsed_ms = (time.perf_counter() - t0) * 1000
    data = res.json()
    n_count = len(data.get("nodes", []))
    e_count = len(data.get("edges", []))
    print(f"{path}: status {res.status_code} in {elapsed_ms:.1f}ms | Nodes: {n_count} | Edges: {e_count}")
