import sys
sys.stdout.reconfigure(line_buffering=True)
sys.path.insert(0, 'backend')
import uuid
from app.db.session import create_db_engine, create_session_factory
from app.core.config import get_settings
from app.models.project import Project, ProjectMembership
from app.models.evidence import EvidenceItem
from app.services.contribution_attribution import ContributionAttributionService
from app.services.work_grouping import WorkGroupingService
from app.services.relationship_coordinator import RelationshipCoordinatorService
from app.services.knowledge_graphs import KnowledgeGraphProjectionService, invalidate_knowledge_graph_cache
from app.api.deps import get_rbac_service
from app.core.cache.local_cache import local_response_cache

settings = get_settings()
engine = create_db_engine(settings)
SessionFactory = create_session_factory(engine)
db = SessionFactory()

pid = uuid.UUID('4c8cedca-66fd-47b5-937e-93d4da866722')
p = db.get(Project, pid)
assert p is not None, f"Project {pid} not found"
org_id = p.organisation_id

print(f"=== PROJECT: {p.name} ({p.id}) ===")

# Invalidate all caches for this project first
local_response_cache.invalidate_prefix(f"contrib_graph:{pid}:")
local_response_cache.invalidate_prefix(f"ki_graph:{pid}:")
invalidate_knowledge_graph_cache(pid)

# Step 1: Re-attribute all commit / evidence items
print("\n--- STEP 1: Re-attributing Evidence Items ---")
cas = ContributionAttributionService(db)
evs = db.query(EvidenceItem).filter_by(project_id=pid).all()
for e in evs:
    res = cas.attribute_evidence(e, flush=False)
    if res:
        print(f"  [{e.category}] {e.title[:35]} -> Ident: {res.contributor_identifier} | Type: {res.contributor_type} | Review: {res.review_status} | Method: {res.match_method} | HumanDir: {(res.metadata_json or {}).get('human_director')}")
db.commit()

# Step 2: Re-run Relationship and Feature Reconstruction
print("\n--- STEP 2: Running Relationship & Feature Synthesis ---")
rcs = RelationshipCoordinatorService(db)
res = rcs.run_reconstruction(
    organisation_id=org_id,
    project_id=pid,
    include_llm_suggestions=False,
)
db.commit()
print("Reconstruction Result:", res)

# Step 3: Check Contributor Identities
print("\n--- STEP 3: Aggregated Contributor Identities ---")
cas_fresh = ContributionAttributionService(db)
contribs = cas_fresh.list_contributor_identities(
    project_id=pid,
    accessible_evidence_ids={e.id for e in evs},
    has_project_manage=True,
)
for c in contribs:
    print(f"  Key: {c['contributor_key']} | Name: {c['display_name']} | Type: {c['contributor_type']} | Count: {c['contribution_count']} (Assisted: {c.get('assisted_commits_count', 0)}) | GH: {c.get('github_login')} | Note: {c.get('identity_note')}")

# Step 4: Check People-Centric Graph
print("\n--- STEP 4: People-Centric Contributor Graph ---")
members = db.query(ProjectMembership).filter_by(project_id=pid).all()
assert len(members) > 0, "No memberships"
viewer_id = members[0].user_id

wgs = WorkGroupingService(db)
graph = wgs.get_contributors_graph(
    project_id=pid,
    viewer_user_id=viewer_id,
    has_project_manage=True,
)
print(f"People Graph Nodes: {len(graph['nodes'])}, Edges: {len(graph['edges'])}")
print("Nodes:")
for n in graph['nodes']:
    print(f"  [{n['node_kind']}] {n['id']} | Label: {n['label']} | Type: {n.get('contributor_type')} | Contribs: {n.get('contribution_count')}")
print("Edges:")
for edge in graph['edges']:
    print(f"  {edge['source']} -> {edge['target']} | {edge.get('relationship_type')} | {edge.get('label')}")

# Step 5: Check Features & Workflows Graph
print("\n--- STEP 5: Features & Workflows Graph Projection ---")
kg_service = KnowledgeGraphProjectionService(db)
rbac = get_rbac_service(db)
principal = rbac.resolve_principal(user=members[0].user, session_family_id=uuid.uuid4())
project_ctx = rbac.resolve_project_context(project_id=pid, principal=principal)

fw_graph = kg_service.get_graph(
    project_ctx=project_ctx,
    graph_type="features-workflows",
    include_suggested=True,
)
print(f"Features & Workflows Nodes: {len(fw_graph.nodes)}, Edges: {len(fw_graph.edges)}")
for n in fw_graph.nodes[:15]:
    print(f"  [{n.entity_type}] {n.label} (cat: {n.category}, status: {n.status}, evs: {n.evidence_count})")
for e in fw_graph.edges[:15]:
    print(f"  {e.source} -> {e.target} | {e.relationship_type} | {e.label}")

# Step 6: Also verify Technology Stack and System Architecture (Zero Regressions)
ts_graph = kg_service.get_graph(
    project_ctx=project_ctx,
    graph_type="technology-stack",
    include_suggested=True,
)
print(f"\nTech Stack Nodes: {len(ts_graph.nodes)}, Edges: {len(ts_graph.edges)}")

sa_graph = kg_service.get_graph(
    project_ctx=project_ctx,
    graph_type="system-architecture",
    include_suggested=True,
)
print(f"System Architecture Nodes: {len(sa_graph.nodes)}, Edges: {len(sa_graph.edges)}")

db.close()
