import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from app.core.config import get_settings
from app.db.session import create_db_engine, create_session_factory
from app.models.project import Project, ProjectMembership
from app.models.team_roster import ContributionAttribution
from app.models.evidence import EvidenceItem
from app.services.contribution_attribution import ContributionAttributionService
import uuid

s = get_settings()
engine = create_db_engine(s)
sf = create_session_factory(engine)
db = sf()

for pid_str, pname in [('d92555ab-e8ad-4ab5-96a7-3c228c98fe1a', 'Travello AI'), ('d5a9f550-7f05-4f10-be34-a271f7f4bafe', 'Conark'), ('4c8cedca-66fd-47b5-937e-93d4da866722', 'CTF')]:
    pid = uuid.UUID(pid_str)
    evs = db.query(EvidenceItem).filter_by(project_id=pid).all()
    ev_ids = {e.id for e in evs}
    cas = ContributionAttributionService(db)
    contribs = cas.list_contributor_identities(project_id=pid, accessible_evidence_ids=ev_ids, has_project_manage=True)
    print(f"=== {pname} Contributor Identities count: {len(contribs)} ===")
    for c in contribs:
        print(f"  key: {c['contributor_key']} | display: {c['display_name']} | type: {c['contributor_type']} | count: {c['contribution_count']} | match_pm: {c['matched_project_membership_id']} | gh: {c['github_login']}")
