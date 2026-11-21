"""Verify Stage 1 Live Knowledge Reconstruction Results."""

import os
import sys
import uuid
import requests
import json
from datetime import timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.core.config import get_settings
from app.core.security import create_access_token, generate_refresh_token, hash_refresh_token, utc_now
from app.db.session import create_db_engine, create_session_factory
from app.models.auth import RefreshSession
from app.models.project import Project, ProjectMembership
from app.models.user import User

print("[1] Loading settings and database...")
settings = get_settings()
engine = create_db_engine(settings)
session_factory = create_session_factory(engine)

pid = uuid.UUID("17ca9ab2-bbb8-4e61-9f52-4fbd6a7ce9c8")
base_url = "http://localhost:8000/api/v1"

print("[2] Finding project user and active session...")
with session_factory() as session:
    member = session.query(ProjectMembership).filter_by(project_id=pid).first()
    if member:
        user_id = member.user_id
        print(f"  Found project member user_id: {user_id}")
    else:
        user = session.query(User).first()
        user_id = user.id
        print(f"  Using first user_id: {user_id}")

    active_session = session.query(RefreshSession).filter(
        RefreshSession.user_id == user_id,
        RefreshSession.revoked_at.is_(None),
        RefreshSession.expires_at > utc_now(),
    ).first()

    if not active_session:
        print("  Creating new active RefreshSession...")
        family_id = uuid.uuid4()
        raw_token = generate_refresh_token()
        active_session = RefreshSession(
            user_id=user_id,
            token_family_id=family_id,
            token_hash=hash_refresh_token(raw_token),
            expires_at=utc_now() + timedelta(days=7),
            revoked_at=None,
        )
        session.add(active_session)
        session.commit()
    else:
        family_id = active_session.token_family_id
        print(f"  Using existing session_family_id: {family_id}")

engine.dispose()

print("[3] Creating JWT access token...")
token, _ = create_access_token(
    user_id=user_id,
    session_family_id=family_id,
    settings=settings,
)

headers = {"Authorization": f"Bearer {token}"}
print("  Token created successfully.")

print("\n--- 1. PROCESSING STATUS ---")
try:
    res = requests.get(f"{base_url}/projects/{pid}/processing-status", headers=headers, timeout=10)
    print(f"Status Code: {res.status_code}")
    if res.ok:
        status_data = res.json()
        print("Project State:", status_data.get("state"))
        print("State Label:", status_data.get("state_label"))
        print("Total Evidence:", status_data.get("total_evidence_count"))
        print("Processed Evidence:", status_data.get("processed_evidence_count"))
        print("Total Knowledge Items:", status_data.get("knowledge_item_count"))
        print("Total Entities:", status_data.get("entity_count"))
        print("Total Relationships:", status_data.get("relationship_count"))
        print("Graph Version:", status_data.get("graph_version"))
        print("Stage 1 Deterministic Ready:", status_data.get("deterministic_ready"))
        print("Stage 2 Semantic Ready:", status_data.get("semantic_ready"))
        print("Stage 2 Semantic Queued:", status_data.get("semantic_queued"))
        print("Graph Published:", status_data.get("graph_published"))
    else:
        print("Response:", res.text)
except Exception as exc:
    print("Error calling processing-status:", exc)

print("\n--- 2. TECHNOLOGY STACK GRAPH ---")
try:
    res = requests.get(f"{base_url}/projects/{pid}/knowledge-intelligence/graphs/technology-stack", headers=headers, timeout=10)
    print(f"Status Code: {res.status_code}")
    if res.ok:
        data = res.json()
        nodes = data.get("nodes", [])
        edges = data.get("edges", [])
        print(f"Technology Stack Nodes: {len(nodes)}")
        print(f"Technology Stack Edges: {len(edges)}")
        for n in nodes[:10]:
            print(f"  - [{n.get('entity_type', 'node')}] {n.get('label')} ({n.get('category')})")
    else:
        print("Response:", res.text)
except Exception as exc:
    print("Error calling technology-stack:", exc)

print("\n--- 3. SYSTEM ARCHITECTURE GRAPH ---")
try:
    res = requests.get(f"{base_url}/projects/{pid}/knowledge-intelligence/graphs/system-architecture", headers=headers, timeout=10)
    print(f"Status Code: {res.status_code}")
    if res.ok:
        data = res.json()
        nodes = data.get("nodes", [])
        edges = data.get("edges", [])
        print(f"System Architecture Nodes: {len(nodes)}")
        print(f"System Architecture Edges: {len(edges)}")
        for n in nodes[:10]:
            print(f"  - [{n.get('entity_type', 'node')}] {n.get('label')}")
    else:
        print("Response:", res.text)
except Exception as exc:
    print("Error calling system-architecture:", exc)

print("\n--- 4. FEATURES & WORKFLOWS GRAPH ---")
try:
    res = requests.get(f"{base_url}/projects/{pid}/knowledge-intelligence/graphs/features-workflows", headers=headers, timeout=10)
    print(f"Status Code: {res.status_code}")
    if res.ok:
        data = res.json()
        nodes = data.get("nodes", [])
        edges = data.get("edges", [])
        print(f"Features/Workflows Nodes: {len(nodes)}")
        print(f"Features/Workflows Edges: {len(edges)}")
        for n in nodes[:10]:
            print(f"  - [{n.get('entity_type', 'node')}] {n.get('label')}")
    else:
        print("Response:", res.text)
except Exception as exc:
    print("Error calling features-workflows:", exc)
