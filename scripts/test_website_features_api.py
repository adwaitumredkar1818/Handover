import sys
import os
import urllib.request
import json
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from app.db.session import create_db_engine, create_session_factory
from app.core.config import get_settings
from app.models.user import User
from app.repositories.auth import RefreshSessionRepository
from app.core.security import create_access_token, utc_now, generate_refresh_token, hash_refresh_token
from datetime import timedelta
from sqlalchemy import select

settings = get_settings()
engine = create_db_engine(settings)
Session = create_session_factory(engine)
with Session() as s:
    u = s.execute(select(User).where(User.email == "vernitg185@gmail.com")).scalar_one()
    now = utc_now()
    token_family_id = uuid.uuid4()
    raw_refresh = generate_refresh_token()
    token_hash = hash_refresh_token(raw_refresh)
    expires_at = now + timedelta(days=settings.security.jwt_refresh_token_expire_days)
    RefreshSessionRepository(s).create(
        user_id=u.id,
        token_family_id=token_family_id,
        token_hash=token_hash,
        expires_at=expires_at,
        session_metadata={"user_agent": "test-script", "ip": "127.0.0.1"},
    )
    token, _ = create_access_token(user_id=u.id, session_family_id=token_family_id, settings=settings, now=now)
    s.commit()

base = "http://127.0.0.1:8000/api/v1/projects/5446b943-e4a8-4881-b3ae-31ba4a06b10a/knowledge-intelligence/graphs"
for g_type in ["technology-stack", "system-architecture", "features-workflows"]:
    req = urllib.request.Request(f"{base}/{g_type}", headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode())
        nodes = data.get("nodes", [])
        edges = data.get("edges", [])
        print(f"\n=== WEBSITE {g_type.upper()} ===")
        print(f"Nodes: {len(nodes)}, Edges: {len(edges)}")
        for n in nodes[:8]:
            print(f"  - [{n.get('entity_type')}] {n.get('label')}")
