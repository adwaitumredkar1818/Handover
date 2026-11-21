import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.db.session import create_db_engine, create_session_factory
from app.core.config import get_settings
from app.models.project import Project, ProjectMembership
from app.models.evidence import EvidenceItem
from app.models.integration import ProjectSourceMapping
from app.models.user import User
from app.models.relationship import KnowledgeEntity, KnowledgeRelationship
from app.models.team_roster import ContributionAttribution
from sqlalchemy import select, func

settings = get_settings()
engine = create_db_engine(settings)
session_factory = create_session_factory(engine)

check_projects = [
    "4c8cedca-66fd-47b5-937e-93d4da866722", # CTF
    "a3ce0b94-5d06-4092-931d-204544896663", # GFG3.0
    "a75d16d8-9a05-448c-a2af-f1672f3c3549", # GFG
    "a79345eb-0464-4c8a-bb40-bbce15e9a206", # intelligent-project-knowledge-handover
    "5446b943-e4a8-4881-b3ae-31ba4a06b10a", # Website
]

with session_factory() as session:
    for pid_str in check_projects:
        import uuid
        pid = uuid.UUID(pid_str)
        proj = session.execute(select(Project).where(Project.id == pid)).scalar_one_or_none()
        if not proj:
            continue
        print("=" * 60)
        print(f"PROJECT: {proj.name} ({proj.slug}) [ID: {proj.id}]")
        
        # Mappings
        mappings = session.execute(select(ProjectSourceMapping).where(ProjectSourceMapping.project_id == pid)).scalars().all()
        for m in mappings:
            print(f"  Mapping: provider={m.provider}, resource_id={m.external_resource_id}, name={m.external_resource_name}, key={m.external_resource_key}")

        # Members
        members = session.execute(select(ProjectMembership, User).join(User, ProjectMembership.user_id == User.id).where(ProjectMembership.project_id == pid)).all()
        print(f"  Members ({len(members)}):")
        for pm, u in members:
            print(f"    - User: {u.full_name} ({u.email}), id: {u.id}")

        # Evidence authors in this project
        ev_authors = session.execute(
            select(EvidenceItem.source_author_identity, func.count(EvidenceItem.id))
            .where(EvidenceItem.project_id == pid)
            .group_by(EvidenceItem.source_author_identity)
        ).all()
        print(f"  Evidence authors:")
        for auth, count in ev_authors:
            print(f"    - {auth}: {count} items")

        # Knowledge Entities (contributor and feature types)
        person_entities = session.execute(
            select(KnowledgeEntity).where(
                KnowledgeEntity.project_id == pid,
                KnowledgeEntity.entity_type.in_(["Person", "Team", "Contributor", "ExternalContributor"])
            )
        ).scalars().all()
        print(f"  Person/Contributor Entities ({len(person_entities)}):")
        for pe in person_entities:
            print(f"    - [{pe.entity_type}] '{pe.name}' (id: {pe.id}, status: {pe.status})")

        feature_entities = session.execute(
            select(KnowledgeEntity).where(
                KnowledgeEntity.project_id == pid,
                KnowledgeEntity.entity_type.in_(["Feature", "Workflow", "UserStory", "Requirement", "Capability"])
            )
        ).scalars().all()
        print(f"  Feature/Workflow Entities ({len(feature_entities)}):")
        for fe in feature_entities[:10]:
            print(f"    - [{fe.entity_type}] '{fe.name}' (id: {fe.id})")
        if len(feature_entities) > 10:
            print(f"    ... and {len(feature_entities) - 10} more")

        # Relationships involving features
        feat_rels = session.execute(
            select(func.count(KnowledgeRelationship.id)).where(
                KnowledgeRelationship.project_id == pid,
                KnowledgeRelationship.relationship_type.in_(["HAS_FEATURE", "HAS_WORKFLOW_STEP", "HAS_REQUIREMENT", "DEPENDS_ON", "IMPLEMENTS"])
            )
        ).scalar_one()
        print(f"  Feature-related relationships: {feat_rels}")
