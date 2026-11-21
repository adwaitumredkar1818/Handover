import sys
import os
import uuid
import json
import httpx
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import hashlib
from datetime import timedelta
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
    token, _ = create_access_token(
        user_id=user.id,
        session_family_id=token_family_id,
        settings=settings,
        now=now,
    )

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json",
}

client = httpx.Client(base_url="http://127.0.0.1:8000", headers=headers, timeout=30.0)

# 1. Processing status
res = client.get(f"/api/v1/projects/{target_project_id}/processing-status")
print(f"GET /processing-status: {res.status_code}")
data = res.json()
print("  State:", data.get("state"), "| Label:", data.get("state_label"))
print("  Is Processing:", data.get("is_processing"))
print("  Stage:", data.get("stage"))
print("  Has existing graphs:", data.get("has_existing_graphs"))
print("  Entities:", data.get("entity_count"), "| Relationships:", data.get("relationship_count"))
print("  Knowledge items:", data.get("knowledge_item_count"))

# 2. Technology Stack graph
res_tech = client.get(f"/api/v1/projects/{target_project_id}/knowledge-intelligence/graphs/technology-stack")
print(f"\nGET /graphs/technology-stack: {res_tech.status_code}")
tech_data = res_tech.json()
print(f"  Nodes: {len(tech_data.get('nodes', []))}")
print(f"  Edges: {len(tech_data.get('edges', []))}")
for node in tech_data.get("nodes", [])[:5]:
    print(f"    - [{node.get('node_type')}] {node.get('label')}")

# 3. System Architecture graph
res_arch = client.get(f"/api/v1/projects/{target_project_id}/knowledge-intelligence/graphs/system-architecture")
print(f"\nGET /graphs/system-architecture: {res_arch.status_code}")
arch_data = res_arch.json()
print(f"  Nodes: {len(arch_data.get('nodes', []))}")
print(f"  Edges: {len(arch_data.get('edges', []))}")

# 4. Features & Workflows graph
res_feat = client.get(f"/api/v1/projects/{target_project_id}/knowledge-intelligence/graphs/features-workflows")
print(f"\nGET /graphs/features-workflows: {res_feat.status_code}")
feat_data = res_feat.json()
print(f"  Nodes: {len(feat_data.get('nodes', []))}")
print(f"  Edges: {len(feat_data.get('edges', []))}")
