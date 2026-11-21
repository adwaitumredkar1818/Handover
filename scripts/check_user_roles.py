import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.db.session import create_db_engine, create_session_factory
from app.core.config import get_settings
from app.models.organisation import Organisation, OrganisationMembership
from app.models.project import Project, ProjectMembership
from app.models.user import User
from app.models.rbac import Role
from sqlalchemy import select

settings = get_settings()
engine = create_db_engine(settings)
session_factory = create_session_factory(engine)

with session_factory() as session:
    users = session.execute(select(User)).scalars().all()
    print("Users:")
    for u in users:
        print(f"  {u.email} (id={u.id}, verified={u.is_email_verified}, status={u.status})")
    
    orgs = session.execute(select(Organisation)).scalars().all()
    print("\nOrganisations:")
    for o in orgs:
        print(f"  {o.name} (id={o.id}, status={o.status})")

    roles = session.execute(select(Role)).scalars().all()
    print("\nRoles:")
    for r in roles:
        print(f"  {r.name} (id={r.id}, scope_type={r.scope_type})")

    org_mems = session.execute(select(OrganisationMembership)).scalars().all()
    print("\nOrg Memberships:")
    for om in org_mems:
        print(f"  User {om.user_id} in Org {om.organisation_id}, Role {om.role_id}, Status {om.status}")
