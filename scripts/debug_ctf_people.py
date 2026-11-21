import sys
sys.path.insert(0, 'backend')
import uuid
from app.core.config import get_settings
from app.db.session import create_db_engine, create_session_factory
from app.models.project import Project, ProjectMembership
from app.models.team_roster import TeamRosterMember, ContributionAttribution
from app.models.evidence import EvidenceItem
from app.services.contribution_attribution import ContributionAttributionService
from app.services.work_grouping import WorkGroupingService

settings = get_settings()
engine = create_db_engine(settings)
SessionFactory = create_session_factory(engine)
db = SessionFactory()
pid = uuid.UUID('4c8cedca-66fd-47b5-937e-93d4da866722')

p = db.get(Project, pid)
print(f'Project: {p.name} ({p.id})')

members = db.query(ProjectMembership).filter_by(project_id=pid).all()
print('\nMemberships:')
for m in members:
    print(f'  ID: {m.id}, User: {m.user.email}, Full: {m.user.full_name}, Resp: {m.responsibility_description}')

roster = db.query(TeamRosterMember).filter_by(project_id=pid).all()
print('\nTeam Roster Members:')
for r in roster:
    print(f'  ID: {r.id}, Name: {r.full_name}, GH: {r.github_username}, Email: {r.email}, GitEmail: {r.git_commit_email}, MatchedPM: {r.matched_project_membership_id}')

evs = db.query(EvidenceItem).filter_by(project_id=pid).all()
print(f'\nTotal Evidence Items: {len(evs)}')
for e in evs:
    meta = e.metadata_json or {}
    print(f'  [{e.category}] {e.title[:40]} | author: {e.source_author_identity} | meta: login={meta.get("github_author_login")}, name={meta.get("git_author_name")}, email={meta.get("git_author_email")}')

attrs = db.query(ContributionAttribution).filter_by(project_id=pid).all()
print(f'\nContributionAttribution records: {len(attrs)}')
for a in attrs:
    print(f'  Ev: {a.evidence_item_id} | Ident: {a.contributor_identifier} | Type: {a.contributor_type} | Review: {a.review_status} | Method: {a.match_method} | MatchedPM: {a.matched_project_membership_id}')

cas = ContributionAttributionService(db)
contribs = cas.list_contributor_identities(project_id=pid, accessible_evidence_ids={e.id for e in evs}, has_project_manage=True)
print('\nAggregated Contributor Identities:')
for c in contribs:
    print(f'  Key: {c["contributor_key"]} | Display: {c["display_name"]} | Type: {c["contributor_type"]} | Count: {c["contribution_count"]} | Commits: {c.get("commits_count")} | GH: {c.get("github_login")}')

wgs = WorkGroupingService(db)
graph = wgs.get_contributors_graph(project_id=pid, viewer_user_id=members[0].user_id, has_project_manage=True)
print(f'\nPeople Graph Nodes: {len(graph["nodes"])}, Edges: {len(graph["edges"])}')
for n in graph['nodes']:
    print(f'  Node: {n["id"]} | Kind: {n["node_kind"]} | Label: {n["label"]} | Type: {n.get("contributor_type")} | Count: {n.get("contribution_count")}')
for edge in graph['edges']:
    print(f'  Edge: {edge["source"]} -> {edge["target"]} | {edge.get("relationship_type")}')
db.close()
