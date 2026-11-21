import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import httpx
from datetime import timedelta
from app.core.security import utc_now, generate_refresh_token, hash_refresh_token, create_access_token
from app.core.config import get_settings
from app.db.session import create_db_engine, create_session_factory
from app.repositories.auth import RefreshSessionRepository
from app.models.user import User
from sqlalchemy import select
import uuid

settings = get_settings()
engine = create_db_engine(settings)
session_factory = create_session_factory(engine)

website_id = "5446b943-e4a8-4881-b3ae-31ba4a06b10a"
user_id = uuid.UUID("4c2c7aff-6049-40e0-b359-678bdb2590bf")

now = utc_now()
with session_factory() as session:
    user = session.get(User, user_id)
    token_family_id = uuid.uuid4()
    raw_refresh_token = generate_refresh_token()
    token_hash = hash_refresh_token(raw_refresh_token)
    expires_at = now + timedelta(days=settings.security.jwt_refresh_token_expire_days)
    
    RefreshSessionRepository(session).create(
        user_id=user.id,
        token_family_id=token_family_id,
        token_hash=token_hash,
        expires_at=expires_at,
        session_metadata={"user_agent": "status-test", "ip": "127.0.0.1"},
    )
    access_token, _ = create_access_token(
        user_id=user.id,
        session_family_id=token_family_id,
        settings=settings,
        now=now,
    )
    session.commit()

headers = {"Authorization": f"Bearer {access_token}"}
resp = httpx.get(f"http://127.0.0.1:8000/api/v1/projects/{website_id}/processing-status", headers=headers)
print("HTTP STATUS:", resp.status_code)
print("RESPONSE:", resp.json())
