import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from app.core.config import get_settings
from app.db.session import create_db_engine, create_session_factory
from app.models.user import User
from app.models.auth import RefreshSession
from app.core.security import create_access_token
import uuid, httpx

s = get_settings()
engine = create_db_engine(s)
sf = create_session_factory(engine)
db = sf()
user = db.query(User).filter_by(email='vernit.gerg25@pccoepune.org').first()
sess = db.query(RefreshSession).filter(RefreshSession.user_id == user.id, RefreshSession.revoked_at.is_(None)).first()
family_id = sess.token_family_id if sess else uuid.uuid4()
token, _ = create_access_token(user_id=user.id, session_family_id=family_id, settings=s)
db.close()

headers = {'Authorization': f'Bearer {token}'}
pid = 'd92555ab-e8ad-4ab5-96a7-3c228c98fe1a'

endpoints = [
    ('TAB 1: Contributors Graph', f'/projects/{pid}/relationships/contributors/graph'),
    ('TAB 1: Contributors List', f'/projects/{pid}/relationships/contributors'),
    ('TAB 2: Work Clusters', f'/projects/{pid}/relationships/work-clusters'),
    ('TAB 3: Identity Candidates', f'/projects/{pid}/relationships/identities/candidates'),
    ('TAB 4: Responsibilities (Roster Attributions)', f'/projects/{pid}/roster/attributions'),
    ('TAB 5: Traceability Chains', f'/projects/{pid}/relationships/traceability'),
    ('TAB 6: Dependencies Graph', f'/projects/{pid}/relationships/dependencies'),
    ('TAB 7: Timeline Events', f'/projects/{pid}/relationships/timeline'),
    ('Shared: All Entities Graph', f'/projects/{pid}/relationships/graph'),
]

with httpx.Client(base_url='http://127.0.0.1:8000/api/v1', headers=headers, timeout=15.0) as client:
    for name, path in endpoints:
        r = client.get(path)
        print(f'{name} [{path}]: HTTP {r.status_code}')
        if r.status_code == 200:
            d = r.json()
            if isinstance(d, list):
                print(f'   count: {len(d)}')
            elif isinstance(d, dict) and 'nodes' in d:
                print(f'   nodes: {len(d["nodes"])} | edges: {len(d["edges"])}')
            elif isinstance(d, dict) and 'items' in d:
                print(f'   items: {len(d["items"])}')
            elif isinstance(d, dict) and 'chains' in d:
                print(f'   chains: {len(d["chains"])}')
            else:
                print(f'   keys: {list(d.keys())[:5]}')
        else:
            print(f'   error: {r.text[:150]}')
