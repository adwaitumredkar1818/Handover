import sys
sys.path.insert(0, 'backend')
import requests
import uuid
from app.db.session import create_db_engine, create_session_factory
from app.core.config import get_settings
from app.models.user import User
from app.models.auth import RefreshSession
from app.core.security import create_access_token

settings = get_settings()
engine = create_db_engine(settings)
SessionFactory = create_session_factory(engine)
db = SessionFactory()

user = db.query(User).filter_by(email="vernitga185@gmail.com").first()
assert user is not None, "User not found"

session = db.query(RefreshSession).filter(
    RefreshSession.user_id == user.id,
    RefreshSession.revoked_at.is_(None)
).order_by(RefreshSession.created_at.desc()).first()

if session:
    family_id = session.token_family_id
else:
    from app.core.security import hash_refresh_token, generate_refresh_token, utc_now
    from datetime import timedelta
    family_id = uuid.uuid4()
    raw_token = generate_refresh_token()
    token_hash = hash_refresh_token(raw_token)
    session = RefreshSession(
        user_id=user.id,
        token_family_id=family_id,
        token_hash=token_hash,
        expires_at=utc_now() + timedelta(days=7),
    )
    db.add(session)
    db.commit()

token, _ = create_access_token(
    user_id=user.id,
    session_family_id=family_id,
    settings=settings,
)
db.close()

headers = {"Authorization": f"Bearer {token}"}
base_url = "http://127.0.0.1:8000/api/v1"
project_id = "4c8cedca-66fd-47b5-937e-93d4da866722"

print("--- Testing Live Features & Workflows Graph API ---")
res_fw = requests.get(f"{base_url}/projects/{project_id}/knowledge-intelligence/graphs/features-workflows", headers=headers)
print(f"Status: {res_fw.status_code}")
if res_fw.status_code == 200:
    data = res_fw.json()
    print(f"Nodes: {len(data.get('nodes', []))}, Edges: {len(data.get('edges', []))}")
    if data.get('nodes'):
        print(f"Sample node: {data['nodes'][0]['label']} (type: {data['nodes'][0].get('entity_type')})")
else:
    print(f"Error: {res_fw.text}")

print("\n--- Testing Live People-Centric Contributor Graph API ---")
res_cg = requests.get(f"{base_url}/projects/{project_id}/relationships/contributors/graph", headers=headers)
print(f"Status: {res_cg.status_code}")
if res_cg.status_code == 200:
    data = res_cg.json()
    print(f"Nodes: {len(data.get('nodes', []))}, Edges: {len(data.get('edges', []))}")
    if data.get('nodes'):
        print(f"Sample node: {data['nodes'][0]['label']} (kind: {data['nodes'][0].get('node_kind')})")
else:
    print(f"Error: {res_cg.text}")

print("\n--- Testing Live Contributor Identities API ---")
res_ci = requests.get(f"{base_url}/projects/{project_id}/relationships/contributors", headers=headers)
print(f"Status: {res_ci.status_code}")
if res_ci.status_code == 200:
    data = res_ci.json()
    print(f"Contributors: {len(data)}")
    for c in data:
        print(f"  {c.get('display_name')} ({c.get('contributor_type')}): {c.get('contribution_count')} contributions | Note: {c.get('identity_note')}")
else:
    print(f"Error: {res_ci.text}")
