import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from app.core.config import get_settings
from app.db.session import create_db_engine, create_session_factory
from app.models.project import Project, ProjectMembership
from app.models.team_roster import TeamRosterMember, ContributionAttribution
from app.models.evidence import EvidenceItem
from app.services.work_grouping import WorkGroupingService
import uuid

s = get_settings()
engine = create_db_engine(s)
sf = create_session_factory(engine)
db = sf()

for pid_str, pname in [('d92555ab-e8ad-4ab5-96a7-3c228c98fe1a', 'Travello AI'), ('d5a9f550-7f05-4f10-be34-a271f7f4bafe', 'Conark'), ('4c8cedca-66fd-47b5-937e-93d4da866722', 'CTF')]:
    pid = uuid.UUID(pid_str)
    print(f"=== {pname} ({pid_str}) ===")
    mems = db.query(ProjectMembership).filter_by(project_id=pid).all()
    print("Memberships:", [(m.user.full_name, m.user.email) for m in mems])
    roster = db.query(TeamRosterMember).filter_by(project_id=pid).all()
    print("Roster members:", [(r.full_name, r.email, r.github_username) for r in roster])
    attrs = db.query(ContributionAttribution).filter_by(project_id=pid).all()
    print("Attributions count:", len(attrs))
    identities = set(a.contributor_identifier for a in attrs)
    print("Distinct contributor_identifiers in attributions:", len(identities), list(identities)[:5])
    wgs = WorkGroupingService(db)
    uid = mems[0].user_id if mems else uuid.uuid4()
    graph = wgs.get_contributors_graph(project_id=pid, viewer_user_id=uid, has_project_manage=True)
    person_nodes = [n for n in graph.get("nodes", []) if n.get("node_type") == "contributor"]
    print(f"Graph person nodes count: {len(person_nodes)}")
    for p in person_nodes:
        print(f"   Person Node: id={p.get('id')} label={p.get('label')} clusters={p.get('work_clusters')} is_member={p.get('is_member')} role={p.get('project_role')}")
