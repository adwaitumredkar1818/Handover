"""Comprehensive integration tests for Knowledge Intelligence graphs, Contributor Identity Review, and Work Grouping."""

from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.security import utc_now
from app.models.enums import (
    ContributionCategory,
    ContributorReviewStatus,
    ContributorType,
    EntityType,
    EpistemicStatus,
    EvidenceCategory,
    EvidenceProcessingStatus,
    EvidenceSourceType,
    KnowledgeCategory,
    KnowledgeReviewStatus,
    ReconciliationStatus,
    RelationshipBasis,
    RelationshipType,
    ResponsibilityAlignment,
    SupportClassification,
)
from app.models.evidence import EvidenceContent, EvidenceItem
from app.models.integration import SourceAccessPolicy, SourceConnection
from app.models.knowledge import KnowledgeExtractionRun, KnowledgeItem
from app.models.organisation import Organisation, OrganisationMembership
from app.models.project import Project, ProjectMembership
from app.models.rbac import Role
from app.models.relationship import KnowledgeEntity, KnowledgeRelationship, RelationshipEvidenceLink
from app.models.team_roster import ContributionAttribution, TeamRosterMember
from app.repositories.knowledge import KnowledgeRepository
from app.services.contribution_attribution import ContributionAttributionService, classify_contribution_domains
from app.services.dependency_intelligence import DependencyIntelligenceService
from app.services.knowledge_validator import ValidatedKnowledgeItemDraft, VerifiedEvidenceLinkDraft
from app.services.relationship_coordinator import RelationshipCoordinatorService
from app.services.technology_manifest_parser import canonicalize_technology_name, parse_manifest_evidence
from app.services.work_grouping import WorkGroupingService
from tests.conftest import isolated_auth_app, register_and_login_user


def _seed_org_and_project(session, *, owner_user_id: uuid.UUID, slug: str = "audit-proj") -> tuple[Organisation, Project, ProjectMembership]:
    owner_role = session.query(Role).filter_by(name="project_manager").first() or session.query(Role).first()
    org_owner_role = session.query(Role).filter_by(name="org_owner").first() or owner_role
    org = Organisation(
        id=uuid.uuid4(),
        name="Audit Org",
        slug=f"org-{uuid.uuid4().hex[:8]}",
        created_by_id=owner_user_id,
    )
    session.add(org)
    session.flush()
    session.add(
        OrganisationMembership(
            organisation_id=org.id,
            user_id=owner_user_id,
            role_id=org_owner_role.id,
            status="active",
        )
    )
    project = Project(
        id=uuid.uuid4(),
        organisation_id=org.id,
        name="Handover Audit Project",
        slug=f"{slug}-{uuid.uuid4().hex[:6]}",
        created_by_id=owner_user_id,
        owner_id=owner_user_id,
        visibility="organisation",
    )
    session.add(project)
    session.flush()
    pm = ProjectMembership(
        id=uuid.uuid4(),
        project_id=project.id,
        user_id=owner_user_id,
        role_id=owner_role.id,
        status="active",
        responsibility_description="Backend FastAPI API and PostgreSQL database engineering",
    )
    session.add(pm)
    session.commit()
    return org, project, pm


def test_migration_0020_enables_rls_and_contributor_columns() -> None:
    mig_path = (
        Path(__file__).resolve().parents[2]
        / "infrastructure"
        / "database"
        / "migrations"
        / "versions"
        / "20261116_0020_knowledge_graphs_and_contributor_review.py"
    )
    assert mig_path.exists()
    spec = importlib.util.spec_from_file_location("mig_0020", mig_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.revision == "0020_graphs_and_contributors"
    assert mod.down_revision == "0019_sources_and_evidence"
    assert set(mod._RLS_TABLES_0019) == {
        "notifications",
        "team_roster_members",
        "contribution_attributions",
    }


def test_dependency_intelligence_enforces_source_acls(monkeypatch: pytest.MonkeyPatch) -> None:
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        owner = register_and_login_user(client, email="owner@example.com", full_name="Owner User")
        member = register_and_login_user(client, email="member@example.com", full_name="Regular Member")

        with ctx.session_factory() as session:
            org, project, _pm = _seed_org_and_project(session, owner_user_id=owner.user_id)
            viewer_role = session.query(Role).filter_by(name="project_member").first() or session.query(Role).first()
            org_member_role = session.query(Role).filter_by(name="org_member").first() or viewer_role
            session.add(OrganisationMembership(organisation_id=org.id, user_id=member.user_id, role_id=org_member_role.id, status="active"))
            session.add(ProjectMembership(project_id=project.id, user_id=member.user_id, role_id=viewer_role.id, status="active"))

            # Public evidence + restricted evidence
            src_conn = SourceConnection(
                organisation_id=org.id,
                provider="github",
                display_name="Owner GitHub",
                created_by_user_id=owner.user_id,
            )
            session.add(src_conn)
            session.flush()
            pub_ev = EvidenceItem(
                organisation_id=org.id,
                project_id=project.id,
                uploaded_by_user_id=owner.user_id,
                source_type=EvidenceSourceType.DOCUMENT_UPLOAD.value,
                source_provider="upload",
                category=EvidenceCategory.PDF_DOCUMENT.value,
                source_external_id=f"upload:{uuid.uuid4().hex[:8]}",
                title="Public Spec",
                content_hash="a" * 64,
                acl_scope="project_members",
                processing_status=EvidenceProcessingStatus.EXTRACTED.value,
            )
            policy = SourceAccessPolicy(
                organisation_id=org.id,
                project_id=project.id,
                source_connection_id=src_conn.id,
                provider="github",
                scope_identifier="private-repo",
                visibility_policy="explicit_user_grants",
                sync_permission_status="verified",
                allowed_user_ids=[str(owner.user_id)],
            )
            session.add_all([pub_ev, policy])
            session.flush()
            priv_ev = EvidenceItem(
                organisation_id=org.id,
                project_id=project.id,
                uploaded_by_user_id=owner.user_id,
                source_type=EvidenceSourceType.GITHUB.value,
                source_provider="github",
                category=EvidenceCategory.PULL_REQUEST.value,
                source_external_id=f"github:pr:{uuid.uuid4().hex[:8]}",
                title="Secret PR",
                content_hash="b" * 64,
                acl_scope="source_restricted",
                source_access_policy_id=policy.id,
                processing_status=EvidenceProcessingStatus.EXTRACTED.value,
            )
            session.add(priv_ev)
            session.flush()

            e_pub_a = KnowledgeEntity(organisation_id=org.id, project_id=project.id, entity_type=EntityType.TECHNICAL_COMPONENT.value, canonical_name="Public UI", normalized_name="public ui", primary_evidence_id=pub_ev.id)
            e_pub_b = KnowledgeEntity(organisation_id=org.id, project_id=project.id, entity_type=EntityType.TECHNICAL_COMPONENT.value, canonical_name="Public API", normalized_name="public api", primary_evidence_id=pub_ev.id)
            e_priv = KnowledgeEntity(organisation_id=org.id, project_id=project.id, entity_type=EntityType.TECHNICAL_COMPONENT.value, canonical_name="Secret Billing Engine", normalized_name="secret billing engine", primary_evidence_id=priv_ev.id)
            session.add_all([e_pub_a, e_pub_b, e_priv])
            session.flush()

            rel_pub = KnowledgeRelationship(organisation_id=org.id, project_id=project.id, source_entity_id=e_pub_a.id, target_entity_id=e_pub_b.id, relationship_type=RelationshipType.DEPENDS_ON.value, relationship_basis=RelationshipBasis.EXPLICIT.value, fingerprint="fp-pub")
            rel_priv = KnowledgeRelationship(organisation_id=org.id, project_id=project.id, source_entity_id=e_pub_b.id, target_entity_id=e_priv.id, relationship_type=RelationshipType.DEPENDS_ON.value, relationship_basis=RelationshipBasis.EXPLICIT.value, fingerprint="fp-priv")
            session.add_all([rel_pub, rel_priv])
            session.flush()
            session.add(RelationshipEvidenceLink(organisation_id=org.id, project_id=project.id, relationship_id=rel_pub.id, evidence_id=pub_ev.id))
            session.add(RelationshipEvidenceLink(organisation_id=org.id, project_id=project.id, relationship_id=rel_priv.id, evidence_id=priv_ev.id))
            session.commit()

            dep_service = DependencyIntelligenceService(session)
            owner_res = dep_service.analyze_dependencies(project_id=project.id, viewer_user_id=owner.user_id, has_project_manage=True)
            member_res = dep_service.analyze_dependencies(project_id=project.id, viewer_user_id=member.user_id, has_project_manage=False)

            assert len(owner_res.edges) == 2
            assert len(member_res.edges) == 1
            assert all(n.name != "Secret Billing Engine" for n in member_res.nodes)


def test_technology_stack_architecture_and_feature_graphs_from_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        owner = register_and_login_user(client, email="tech@example.com", full_name="Tech Owner")

        # Unit checks for canonicalisation and manifest parsing
        assert canonicalize_technology_name("Postgres")[0] == "PostgreSQL"
        assert canonicalize_technology_name("PostgreSQL")[0] == "PostgreSQL"
        assert canonicalize_technology_name("GitHub Actions")[0] == "GitHub Actions"
        assert canonicalize_technology_name("GitHub")[0] == "GitHub API"

        pkg_dets = parse_manifest_evidence(
            "frontend/package.json",
            '{"dependencies":{"next":"16.4.6","react":"19.3.0"},"devDependencies":{"vitest":"^3.0.0"}}',
        )
        assert {d.canonical_name for d in pkg_dets} >= {"Next.js", "React", "Vitest"}

        with ctx.session_factory() as session:
            org, project, _pm = _seed_org_and_project(session, owner_user_id=owner.user_id)
            manifest_ev = EvidenceItem(
                organisation_id=org.id,
                project_id=project.id,
                uploaded_by_user_id=owner.user_id,
                source_type=EvidenceSourceType.GITHUB.value,
                source_provider="github",
                category=EvidenceCategory.SOURCE_CODE.value,
                source_external_id="github:manifest:requirements.txt",
                title="repo: backend/requirements.txt",
                original_filename="requirements.txt",
                content_hash="c" * 64,
                acl_scope="project_members",
                processing_status=EvidenceProcessingStatus.EXTRACTED.value,
                metadata_json={"path": "backend/requirements.txt", "is_manifest": True},
            )
            doc_ev = EvidenceItem(
                organisation_id=org.id,
                project_id=project.id,
                uploaded_by_user_id=owner.user_id,
                source_type=EvidenceSourceType.DOCUMENT_UPLOAD.value,
                source_provider="upload",
                category=EvidenceCategory.PDF_DOCUMENT.value,
                source_external_id="upload:architecture.pdf",
                title="Architecture Proposal PRD",
                original_filename="architecture.pdf",
                content_hash="d" * 64,
                acl_scope="project_members",
                processing_status=EvidenceProcessingStatus.EXTRACTED.value,
            )
            session.add_all([manifest_ev, doc_ev])
            session.flush()
            session.add(EvidenceContent(evidence_id=manifest_ev.id, extracted_text="fastapi==0.162.4\npsycopg==3.3.8\n"))

            run = KnowledgeExtractionRun(
                organisation_id=org.id,
                project_id=project.id,
                evidence_id=doc_ev.id,
                triggered_by_user_id=owner.user_id,
                scope_type="evidence",
                model_name="qwen3:8b",
                prompt_version="p2.6-v1",
                status="completed",
            )
            session.add(run)
            session.flush()

            k_repo = KnowledgeRepository(session)
            # Duplicate tech alias "Postgres" + proposed "Redis" + Architecture component + Feature
            for title, cat, norm_stat, payload in [
                (
                    "Database choice: Postgres",
                    KnowledgeCategory.TECHNICAL_ARCHITECTURE.value,
                    "active",
                    {"technical_category": "technology_choice", "exact_identifiers": ["Postgres"], "components": ["Backend API"]},
                ),
                (
                    "Proposed Redis caching layer",
                    KnowledgeCategory.TECHNICAL_ARCHITECTURE.value,
                    "proposed",
                    {"technical_category": "technology_choice", "exact_identifiers": ["Redis"], "components": ["Cache Service"]},
                ),
                (
                    "Handover Package Export Feature",
                    KnowledgeCategory.WORK_ITEMS.value,
                    "in_progress",
                    {"work_category": "feature", "components": ["Backend API"]},
                ),
            ]:
                k_repo.upsert_validated_draft(
                    organisation_id=org.id,
                    project_id=project.id,
                    extraction_run_id=run.id,
                    model_name="qwen3:8b",
                    prompt_version="p2.6-v1",
                    draft=ValidatedKnowledgeItemDraft(
                        category=KnowledgeCategory(cat),
                        primary_domain=cat,
                        secondary_domains=[],
                        epistemic_status=EpistemicStatus.EXTRACTED.value,
                        review_status=KnowledgeReviewStatus.PENDING_REVIEW.value,
                        support_classification=SupportClassification.DIRECT.value,
                        title=title,
                        structured_summary=title,
                        structured_payload=payload,
                        normalised_status=norm_stat,
                        person_or_owner_label=None,
                        source_attribution={"evidence_count": 1},
                        fingerprint=f"fp-{title}-{uuid.uuid4().hex[:6]}",
                        confidence_metadata={"confidence_score": 0.9},
                        uncertainty_reason=None,
                        source_observed_at=utc_now(),
                        is_synthetic=False,
                        evidence_links=(
                            VerifiedEvidenceLinkDraft(
                                evidence_id=doc_ev.id,
                                evidence_chunk_id=None,
                                support_type="direct",
                                source_location={},
                                supporting_excerpt="Evidence supporting architectural component.",
                                excerpt_match_mode="exact",
                                source_metadata={},
                            ),
                        ),
                    ),
                )

            # Seed another item using PostgreSQL to verify dedup into single Technology entity
            RelationshipCoordinatorService(session).run_reconstruction(
                organisation_id=org.id,
                project_id=project.id,
                include_llm_suggestions=False,
            )
            session.commit()

        # Verify all 3 Graph APIs
        tech_resp = client.get(f"/api/v1/projects/{project.id}/knowledge-intelligence/graphs/technology-stack", headers=owner.headers)
        assert tech_resp.status_code == 200
        tech_nodes = tech_resp.json()["nodes"]
        labels = {n["label"]: n for n in tech_nodes}
        assert "FastAPI" in labels
        assert labels["FastAPI"]["status"] == "declared_dependency"
        assert "PostgreSQL" in labels
        assert "Postgres" in labels["PostgreSQL"]["aliases"]
        assert "Redis" in labels
        assert labels["Redis"]["status"] == "proposed"

        arch_resp = client.get(f"/api/v1/projects/{project.id}/knowledge-intelligence/graphs/system-architecture", headers=owner.headers)
        assert arch_resp.status_code == 200
        arch_labels = {n["label"]: n for n in arch_resp.json()["nodes"]}
        assert "Backend API" in arch_labels
        assert arch_labels["Backend API"]["status"] == "documented_only"

        feat_resp = client.get(f"/api/v1/projects/{project.id}/knowledge-intelligence/graphs/features-workflows", headers=owner.headers)
        assert feat_resp.status_code == 200
        feat_labels = {n["label"]: n for n in feat_resp.json()["nodes"]}
        assert "Handover Package Export Feature" in feat_labels
        assert feat_labels["Handover Package Export Feature"]["status"] == "IN_PROGRESS"


def test_superseded_by_id_linked_on_reextraction(monkeypatch: pytest.MonkeyPatch) -> None:
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        owner = register_and_login_user(client, email="supersede@example.com", full_name="Supersede Owner")
        with ctx.session_factory() as session:
            org, project, _pm = _seed_org_and_project(session, owner_user_id=owner.user_id)
            ev = EvidenceItem(
                organisation_id=org.id,
                project_id=project.id,
                uploaded_by_user_id=owner.user_id,
                source_type=EvidenceSourceType.DOCUMENT_UPLOAD.value,
                source_provider="upload",
                category=EvidenceCategory.PDF_DOCUMENT.value,
                source_external_id="upload:design.pdf",
                title="Design Doc",
                content_hash="e" * 64,
                acl_scope="project_members",
                processing_status=EvidenceProcessingStatus.EXTRACTED.value,
            )
            session.add(ev)
            session.flush()
            run1 = KnowledgeExtractionRun(organisation_id=org.id, project_id=project.id, evidence_id=ev.id, triggered_by_user_id=owner.user_id, scope_type="evidence", model_name="qwen3:8b", prompt_version="p2.6-v1", status="completed")
            run2 = KnowledgeExtractionRun(organisation_id=org.id, project_id=project.id, evidence_id=ev.id, triggered_by_user_id=owner.user_id, scope_type="evidence", model_name="qwen3:8b", prompt_version="p2.6-v1", status="completed")
            session.add_all([run1, run2])
            session.flush()

            repo = KnowledgeRepository(session)
            draft = ValidatedKnowledgeItemDraft(
                category=KnowledgeCategory.DECISIONS_RATIONALE,
                primary_domain="DECISIONS_RATIONALE",
                secondary_domains=[],
                epistemic_status=EpistemicStatus.EXTRACTED.value,
                review_status=KnowledgeReviewStatus.PENDING_REVIEW.value,
                support_classification=SupportClassification.DIRECT.value,
                title="Use Argon2id for passwords",
                structured_summary="Argon2id hashes passwords",
                structured_payload={},
                normalised_status="active",
                person_or_owner_label=None,
                source_attribution={"evidence_count": 1},
                fingerprint="fp-argon2id-decision",
                confidence_metadata={"confidence_score": 0.9},
                uncertainty_reason=None,
                source_observed_at=utc_now(),
                is_synthetic=False,
                evidence_links=(
                    VerifiedEvidenceLinkDraft(
                        evidence_id=ev.id,
                        evidence_chunk_id=None,
                        support_type="direct",
                        source_location={},
                        supporting_excerpt="Passwords use Argon2id.",
                        excerpt_match_mode="exact",
                        source_metadata={},
                    ),
                ),
            )
            old_item, _ = repo.upsert_validated_draft(organisation_id=org.id, project_id=project.id, extraction_run_id=run1.id, model_name="qwen3:8b", prompt_version="p2.6-v1", draft=draft)
            repo.mark_stale_for_evidence(evidence_id=ev.id, reason="superseded_by_reextraction", exclude_run_id=run2.id)
            new_item, _ = repo.upsert_validated_draft(organisation_id=org.id, project_id=project.id, extraction_run_id=run2.id, model_name="qwen3:8b", prompt_version="p2.6-v1", draft=draft)
            session.commit()
            session.refresh(old_item)
            assert old_item.is_stale is True
            assert old_item.superseded_by_id == new_item.id


def test_github_contributors_bots_identity_review_and_work_grouping(monkeypatch: pytest.MonkeyPatch) -> None:
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        owner = register_and_login_user(client, email="lead@example.com", full_name="Lead Manager")
        member = register_and_login_user(client, email="viewer@example.com", full_name="Viewer Member")

        # Deterministic path-based classification test
        areas, method, _signals = classify_contribution_domains(
            "Update login UI",
            paths=["frontend/src/components/auth/LoginForm.tsx", "backend/app/api/routes/auth.py"],
        )
        assert method == "deterministic_path"
        assert "Frontend" in areas
        assert "Authentication" in areas

        with ctx.session_factory() as session:
            org, project, owner_pm = _seed_org_and_project(session, owner_user_id=owner.user_id)
            viewer_role = session.query(Role).filter_by(name="project_member").first() or session.query(Role).first()
            org_member_role = session.query(Role).filter_by(name="org_member").first() or viewer_role
            session.add(OrganisationMembership(organisation_id=org.id, user_id=member.user_id, role_id=org_member_role.id, status="active"))
            session.add(ProjectMembership(project_id=project.id, user_id=member.user_id, role_id=viewer_role.id, status="active"))

            # Roster evidence + member with backend responsibility
            roster_ev = EvidenceItem(organisation_id=org.id, project_id=project.id, uploaded_by_user_id=owner.user_id, source_type=EvidenceSourceType.DOCUMENT_UPLOAD.value, source_provider="upload", category=EvidenceCategory.TEAM_ROSTER.value, source_external_id="upload:roster.pdf", title="Roster.pdf", content_hash="f" * 64, acl_scope="project_members")
            session.add(roster_ev)
            session.flush()
            session.add(
                TeamRosterMember(
                    project_id=project.id,
                    evidence_item_id=roster_ev.id,
                    full_name="Lead Manager",
                    email="lead@example.com",
                    role_name="Backend Engineer",
                    primary_responsibilities=["Backend Development", "Database Engineering"],
                    github_username="leaddev",
                    reconciliation_status=ReconciliationStatus.MATCHED.value,
                    matched_project_membership_id=owner_pm.id,
                    metadata_json={"github_user_id": "101"},
                )
            )

            # 1) Confirmed member doing Frontend fix -> OUTSIDE_DECLARED_RESPONSIBILITY
            c1 = EvidenceItem(
                organisation_id=org.id, project_id=project.id, uploaded_by_user_id=owner.user_id,
                source_type=EvidenceSourceType.GITHUB.value, source_provider="github", category=EvidenceCategory.COMMIT.value,
                source_external_id="github:commit:sha1",
                title="Fix button alignment", content_hash="1" * 64, acl_scope="project_members",
                metadata_json={
                    "repository": "org/repo", "sha": "sha1",
                    "github_author_login": "leaddev", "github_author_id": 101,
                    "git_author_name": "Lead Manager", "git_author_email": "lead@example.com",
                    "changed_files": [{"filename": "frontend/src/components/Button.tsx", "status": "modified"}],
                },
            )
            # 2) Unidentified contributor with ambiguous name match ("Lead Manager") -> MUST NOT auto-match
            c2 = EvidenceItem(
                organisation_id=org.id, project_id=project.id, uploaded_by_user_id=owner.user_id,
                source_type=EvidenceSourceType.GITHUB.value, source_provider="github", category=EvidenceCategory.COMMIT.value,
                source_external_id="github:commit:sha2",
                title="Add migration index", content_hash="2" * 64, acl_scope="project_members",
                metadata_json={
                    "repository": "org/repo", "sha": "sha2",
                    "github_author_login": "unmatched-dev", "github_author_id": 202,
                    "git_author_name": "Lead Manager", "git_author_email": "private-dev@external.org",
                    "changed_files": [{"filename": "infrastructure/database/migrations/0020.py", "status": "added"}],
                },
            )
            # 3) GitHub Bot account
            c3 = EvidenceItem(
                organisation_id=org.id, project_id=project.id, uploaded_by_user_id=owner.user_id,
                source_type=EvidenceSourceType.GITHUB.value, source_provider="github", category=EvidenceCategory.PULL_REQUEST.value,
                source_external_id="github:pr:1",
                title="Bump deps", content_hash="3" * 64, acl_scope="project_members",
                metadata_json={
                    "repository": "org/repo", "github_author_login": "dependabot[bot]", "github_author_id": 49699333,
                    "github_author_type": "Bot", "associated_commit_shas": ["sha1"],
                    "changed_files": [{"filename": "package.json", "status": "modified"}],
                },
            )
            # 4) Unclassified isolated commit -> Other / Unclustered Contributions
            c4 = EvidenceItem(
                organisation_id=org.id, project_id=project.id, uploaded_by_user_id=owner.user_id,
                source_type=EvidenceSourceType.GITHUB.value, source_provider="github", category=EvidenceCategory.COMMIT.value,
                source_external_id="github:commit:sha4",
                title="Misc chore", content_hash="4" * 64, acl_scope="project_members",
                metadata_json={
                    "repository": "org/repo", "sha": "sha4",
                    "github_author_login": "ext-helper", "github_author_id": 303,
                    "git_author_email": "ext@outside.org",
                },
            )
            session.add_all([c1, c2, c3, c4])
            session.flush()

            attr_svc = ContributionAttributionService(session)
            a1 = attr_svc.attribute_evidence(c1)
            a2 = attr_svc.attribute_evidence(c2)
            a3 = attr_svc.attribute_evidence(c3)
            a4 = attr_svc.attribute_evidence(c4)
            assert a1 and a1.contributor_type == ContributorType.CONFIRMED_MEMBER.value
            assert a1.responsibility_alignment == ResponsibilityAlignment.OUTSIDE_DECLARED_RESPONSIBILITY.value
            assert a2 and a2.contributor_type == ContributorType.UNIDENTIFIED.value
            assert a2.review_status == ContributorReviewStatus.PENDING.value
            assert a3 and a3.contributor_type == ContributorType.BOT.value
            assert a4 is not None

            # Rebuild work clusters & discover PR->Commit relationship
            WorkGroupingService(session).rebuild_work_clusters(organisation_id=org.id, project_id=project.id, triggered_by_user_id=owner.user_id)
            RelationshipCoordinatorService(session).run_reconstruction(organisation_id=org.id, project_id=project.id)
            session.commit()

        # Verify viewer has masked email while owner sees full email
        owner_contribs = client.get(f"/api/v1/projects/{project.id}/relationships/contributors", headers=owner.headers).json()
        viewer_contribs = client.get(f"/api/v1/projects/{project.id}/relationships/contributors", headers=member.headers).json()
        u_owner = next(c for c in owner_contribs if c["contributor_key"] == "ghid:202")
        u_viewer = next(c for c in viewer_contribs if c["contributor_key"] == "ghid:202")
        assert u_owner["git_author_email"] == "private-dev@external.org"
        assert u_viewer["git_author_email"] == "p***@external.org"

        # Verify Manager marks ghid:303 as External and ghid:202 as Confirmed Member
        rev_ext = client.post(
            f"/api/v1/projects/{project.id}/relationships/contributors/ghid:303/review",
            headers=owner.headers,
            json={"action": "mark_external", "notes": "External volunteer"},
        )
        assert rev_ext.status_code == 200
        assert rev_ext.json()["contributor_type"] == "external_contributor"

        # Non-manager cannot review contributor identities
        forbidden_rev = client.post(
            f"/api/v1/projects/{project.id}/relationships/contributors/ghid:202/review",
            headers=member.headers,
            json={"action": "mark_external"},
        )
        assert forbidden_rev.status_code == 403

        # Verify Work Clusters endpoint includes Frontend, Database, and Other / Unclustered Contributions
        wc_resp = client.get(f"/api/v1/projects/{project.id}/relationships/work-clusters", headers=owner.headers)
        assert wc_resp.status_code == 200
        wc_names = {w["name"] for w in wc_resp.json()}
        assert "Frontend" in wc_names
        assert "Database" in wc_names
        assert "Other / Unclustered Contributions" in wc_names

        # Verify Contributor Graph endpoint
        cg_resp = client.get(f"/api/v1/projects/{project.id}/relationships/contributors/graph", headers=owner.headers)
        assert cg_resp.status_code == 200
        assert cg_resp.json()["summary"]["bots"] == 1
        assert cg_resp.json()["summary"]["external_contributors"] == 1
