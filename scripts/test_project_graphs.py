import sys
import os
import uuid
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.db.session import create_db_engine, create_session_factory
from app.core.config import get_settings
from app.services.knowledge_graphs import KnowledgeGraphProjectionService
from app.services.rbac import RbacService
from app.repositories.rbac import RbacRepository
from app.repositories.user import UserRepository
from app.models.user import User
from sqlalchemy import select

settings = get_settings()
engine = create_db_engine(settings)
session_factory = create_session_factory(engine)

target_id = uuid.UUID("a79345eb-0464-4c8a-bb40-bbce15e9a206")

with session_factory() as session:
    user = session.execute(select(User).where(User.id == uuid.UUID("4c2c7aff-6049-40e0-b359-678bdb2590bf"))).scalar_one()
    rbac = RbacService(
        db_session=session,
        rbac_repository=RbacRepository(session),
        user_repository=UserRepository(session),
    )
    principal = rbac.resolve_principal(user=user, session_family_id=uuid.uuid4())
    ctx = rbac.resolve_project_context(principal=principal, project_id=target_id)
    
    service = KnowledgeGraphProjectionService(session)
    for gtype in ["technology-stack", "system-architecture", "features-workflows"]:
        g = service.get_graph(
            project_ctx=ctx,
            graph_type=gtype,
            include_suggested=True,
        )
        print(f"Graph '{gtype}': {len(g.nodes)} nodes, {len(g.edges)} edges")
        for node in g.nodes[:10]:
            print(f"   Node: [{getattr(node, 'category', getattr(node, 'type', ''))}] {getattr(node, 'label', getattr(node, 'name', node.id))}")
