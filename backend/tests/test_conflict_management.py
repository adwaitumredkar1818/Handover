"""Integration tests for Conflict Management Workspace (API, Service, RBAC, ACL, Audit)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

import app.models
from app.models.audit import AuditLog
from app.models.enums import (
    ConflictPriority,
    ConflictResolutionState,
    ConflictResolutionStrategy,
    ConflictType,
    EvidenceSourceType,
    IssueResolutionState,
    SourcePermissionVerificationStatus,
    SourceVisibilityPolicy,
    TemporalComparison,
    VerificationCaseStatus,
    VerificationCategory,
    VerificationIssueType,
)
from app.models.evidence import EvidenceItem
from app.models.integration import SourceAccessPolicy, SourceConnection
from app.models.verification import (
    VerificationCase,
    VerificationConflict,
    VerificationIssue,
)
from tests.conftest import (
    invite_and_accept_member,
    isolated_auth_app,
    register_and_login_user,
)


def _setup_project(client: TestClient, headers: dict[str, str], suffix: str) -> tuple[str, str]:
    org_res = client.post(
        "/api/v1/organisations",
        headers=headers,
        json={"name": f"Conflict Org {suffix}", "slug": f"c-org-{suffix}"},
    )
    assert org_res.status_code == 201, org_res.text
    org_id = org_res.json()["id"]

    proj_res = client.post(
        f"/api/v1/organisations/{org_id}/projects",
        headers=headers,
        json={"name": f"Conflict Proj {suffix}", "slug": f"c-proj-{suffix}"},
    )
    assert proj_res.status_code == 201, proj_res.text
    return org_id, proj_res.json()["id"]


def _seed_project_evidence(
    session: Session,
    *,
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    title: str,
    source_type: str = EvidenceSourceType.GITHUB.value,
) -> EvidenceItem:
    ev = EvidenceItem(
        organisation_id=org_id,
        project_id=project_id,
        source_type=source_type,
        source_provider=source_type,
        source_external_id=f"ext-{uuid.uuid4().hex[:12]}",
        title=title,
        content_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        uploaded_by_user_id=user_id,
        category="project_document",
        acl_scope="project_members",
    )
    session.add(ev)
    session.flush()
    return ev


def test_conflict_dashboard_and_listing(monkeypatch):
    with isolated_auth_app(monkeypatch) as ctx:
        with TestClient(ctx.app) as client:
            session_factory = ctx.session_factory

            user = register_and_login_user(client, email="conflict_mgr@example.com", full_name="Conflict Manager")
            org_id_str, proj_id_str = _setup_project(client, user.headers, "dashboard")
            project_id = uuid.UUID(proj_id_str)
            org_id = uuid.UUID(org_id_str)

            with session_factory() as session:
                ev1_a = _seed_project_evidence(
                    session, org_id=org_id, project_id=project_id, user_id=user.user_id, title="README.md"
                )
                ev1_b = _seed_project_evidence(
                    session, org_id=org_id, project_id=project_id, user_id=user.user_id, title="PR #42 description"
                )
                ev2_a = _seed_project_evidence(
                    session,
                    org_id=org_id,
                    project_id=project_id,
                    user_id=user.user_id,
                    title="Jira Story MISC-101",
                    source_type=EvidenceSourceType.JIRA.value,
                )
                ev2_b = _seed_project_evidence(
                    session,
                    org_id=org_id,
                    project_id=project_id,
                    user_id=user.user_id,
                    title="Slack #dev channel",
                    source_type=EvidenceSourceType.SLACK.value,
                )

                # Create a test case
                case = VerificationCase(
                    organisation_id=org_id,
                    project_id=project_id,
                    target_type="knowledge_item",
                    target_id=uuid.uuid4(),
                    domain="responsibilities_ownership",
                    case_status=VerificationCaseStatus.CONFLICTED.value,
                    title="Ownership of Onboarding Module",
                    current_claim="Shubham is sole lead of onboarding module",
                    priority="high",
                )
                session.add(case)
                session.flush()

                # Add 2 conflicts across different categories backed by real project-accessible evidence
                conf1 = VerificationConflict(
                    organisation_id=org_id,
                    project_id=project_id,
                    case_id=case.id,
                    conflict_type=ConflictType.OWNERSHIP_CONFLICT.value,
                    claim_a_text="Shubham owns onboarding module",
                    claim_a_source_evidence_id=ev1_a.id,
                    claim_b_text="Adwait committed major rewrite and claims onboarding ownership",
                    claim_b_source_evidence_id=ev1_b.id,
                    side_a_source_title="README.md",
                    side_a_provider="github",
                    side_b_source_title="PR #42 description",
                    side_b_provider="github",
                    explanation="Both developers claim sole ownership of onboarding module",
                    priority=ConflictPriority.HIGH.value,
                    temporal_comparison=TemporalComparison.AMBIGUOUS.value,
                    resolution_state=ConflictResolutionState.UNRESOLVED.value,
                )
                conf2 = VerificationConflict(
                    organisation_id=org_id,
                    project_id=project_id,
                    case_id=case.id,
                    conflict_type=ConflictType.STATUS_CONFLICT.value,
                    claim_a_text="Onboarding feature completed and verified",
                    claim_a_source_evidence_id=ev2_a.id,
                    claim_b_text="Onboarding blocked by backend regression",
                    claim_b_source_evidence_id=ev2_b.id,
                    side_a_source_title="Jira Story MISC-101",
                    side_a_provider="jira",
                    side_b_source_title="Slack #dev channel",
                    side_b_provider="slack",
                    explanation="Jira status indicates completed while Slack reports active blocker",
                    priority=ConflictPriority.CRITICAL.value,
                    temporal_comparison=TemporalComparison.B_SUPERSEDES_A.value,
                    resolution_state=ConflictResolutionState.UNDER_INVESTIGATION.value,
                )
                session.add_all([conf1, conf2])
                session.commit()

            # 1. Fetch dashboard metrics
            dash_res = client.get(
                f"/api/v1/projects/{proj_id_str}/conflicts/dashboard",
                headers=user.headers,
            )
            assert dash_res.status_code == 200, dash_res.text
            metrics = dash_res.json()
            assert metrics["total_conflicts"] == 2
            assert metrics["open_conflicts"] == 1
            assert metrics["under_investigation"] == 1
            assert metrics["high_priority"] == 1
            assert metrics["critical_priority"] == 1
            assert metrics["category_counts"]["ownership_conflict"] == 1
            assert metrics["category_counts"]["status_conflict"] == 1

            # 2. List conflicts with filtering
            list_res = client.get(
                f"/api/v1/projects/{proj_id_str}/conflicts?conflict_type=ownership_conflict",
                headers=user.headers,
            )
            assert list_res.status_code == 200
            items = list_res.json()["items"]
            assert len(items) == 1
            assert items[0]["conflict_type"] == "ownership_conflict"
            assert "onboarding module" in items[0]["explanation"]

            # 3. Search query filter
            search_res = client.get(
                f"/api/v1/projects/{proj_id_str}/conflicts?search=regression",
                headers=user.headers,
            )
            assert search_res.status_code == 200
            assert len(search_res.json()["items"]) == 1
            assert search_res.json()["items"][0]["priority"] == "critical"


def test_conflict_investigation_lifecycle_and_actions(monkeypatch):
    with isolated_auth_app(monkeypatch) as ctx:
        with TestClient(ctx.app) as client:
            session_factory = ctx.session_factory

            lead = register_and_login_user(client, email="lead_reviewer@example.com", full_name="Lead Reviewer")
            org_id_str, proj_id_str = _setup_project(client, lead.headers, "lifecycle")
            project_id = uuid.UUID(proj_id_str)
            org_id = uuid.UUID(org_id_str)

            # Invite teammate
            dev = register_and_login_user(client, email="dev_participant@example.com", full_name="Dev Participant")
            invite_and_accept_member(
                client,
                organisation_id=org_id_str,
                inviter_headers=lead.headers,
                invitee=dev,
                role_name="org_member",
            )
            client.post(
                f"/api/v1/projects/{proj_id_str}/members",
                headers=lead.headers,
                json={"user_id": str(dev.user_id), "role_name": "project_member"},
            )

            conf_id = None
            case_id = None
            with session_factory() as session:
                case = VerificationCase(
                    organisation_id=org_id,
                    project_id=project_id,
                    target_type="knowledge_item",
                    target_id=uuid.uuid4(),
                    domain="technical_architecture",
                    case_status=VerificationCaseStatus.CONFLICTED.value,
                    title="Database Architecture",
                    current_claim="PostgreSQL is the primary database",
                    priority="critical",
                )
                session.add(case)
                session.flush()

                issue = VerificationIssue(
                    organisation_id=org_id,
                    project_id=project_id,
                    case_id=case.id,
                    verification_category=VerificationCategory.CONFLICTING_EVIDENCE.value,
                    issue_type=VerificationIssueType.CONFLICTING_SOURCES.value,
                    severity="high",
                    description="Contradiction on primary database",
                    resolution_state=IssueResolutionState.OPEN.value,
                )
                session.add(issue)

                ev_a = _seed_project_evidence(
                    session, org_id=org_id, project_id=project_id, user_id=lead.user_id, title="architecture.md"
                )
                ev_b = _seed_project_evidence(
                    session,
                    org_id=org_id,
                    project_id=project_id,
                    user_id=lead.user_id,
                    title="Sprint Planning Notes",
                    source_type=EvidenceSourceType.DOCUMENT_UPLOAD.value,
                )
                conf = VerificationConflict(
                    organisation_id=org_id,
                    project_id=project_id,
                    case_id=case.id,
                    conflict_type=ConflictType.TECHNICAL_CONFLICT.value,
                    claim_a_text="System uses PostgreSQL with relational schemas",
                    claim_a_source_evidence_id=ev_a.id,
                    claim_b_text="System uses MongoDB document collections",
                    claim_b_source_evidence_id=ev_b.id,
                    side_a_source_title="architecture.md",
                    side_a_provider="github",
                    side_b_source_title="Sprint Planning Notes",
                    side_b_provider="document_upload",
                    explanation="Architectural divergence: Relational PostgreSQL vs Document MongoDB",
                    priority=ConflictPriority.CRITICAL.value,
                    temporal_comparison=TemporalComparison.A_SUPERSEDES_B.value,
                    resolution_state=ConflictResolutionState.UNRESOLVED.value,
                )
                session.add(conf)
                session.commit()
                conf_id = str(conf.id)
                case_id = str(case.id)

            # 1. Assign reviewer
            assign_res = client.post(
                f"/api/v1/projects/{proj_id_str}/conflicts/{conf_id}/assign",
                headers=lead.headers,
                json={"reviewer_id": str(dev.user_id), "notes": "Please verify with dev team"},
            )
            assert assign_res.status_code == 200, assign_res.text
            assert assign_res.json()["assigned_reviewer_id"] == str(dev.user_id)

            # 2. Start investigation
            inv_res = client.post(
                f"/api/v1/projects/{proj_id_str}/conflicts/{conf_id}/investigate",
                headers=lead.headers,
                json={"notes": "Checking git repository commit history"},
            )
            assert inv_res.status_code == 200, inv_res.text
            assert inv_res.json()["resolution_state"] == "under_investigation"
            assert "Checking git" in inv_res.json()["investigation_notes"]

            # 3. Request context
            ctx_res = client.post(
                f"/api/v1/projects/{proj_id_str}/conflicts/{conf_id}/request-context",
                headers=lead.headers,
                json={
                    "context_queries": ["Which database driver is in requirements.txt?", "Is Docker compose running mongo?"],
                    "notes": "Need confirmation before resolving",
                },
            )
            assert ctx_res.status_code == 200, ctx_res.text
            assert ctx_res.json()["resolution_state"] == "awaiting_context"
            assert "Which database driver" in ctx_res.json()["investigation_notes"]

            # 4. Add notes
            note_res = client.post(
                f"/api/v1/projects/{proj_id_str}/conflicts/{conf_id}/notes",
                headers=lead.headers,
                json={"notes": "Verified requirements.txt: psycopg3 and sqlalchemy are present; no pymongo."},
            )
            assert note_res.status_code == 200, note_res.text
            assert "psycopg3" in note_res.json()["investigation_notes"]

            # 5. Formally resolve conflict
            resolve_res = client.post(
                f"/api/v1/projects/{proj_id_str}/conflicts/{conf_id}/resolve",
                headers=lead.headers,
                json={
                    "resolution_strategy": "side_a_authoritative",
                    "resolution_notes": "PostgreSQL confirmed as single canonical datastore. MongoDB reference in sprint notes was an early rejected proposal.",
                    "authoritative_claim_text": "System canonical database is PostgreSQL 16 managed via SQLAlchemy 2.x and Psycopg 3.",
                    "sync_finding": True,
                },
            )
            assert resolve_res.status_code == 200, resolve_res.text
            res_data = resolve_res.json()
            assert res_data["resolution_state"] == "superseded"
            assert res_data["resolution_strategy"] == "side_a_authoritative"
            assert res_data["resolved_by_user_id"] == str(lead.user_id)
            assert res_data["authoritative_claim_text"] == "System canonical database is PostgreSQL 16 managed via SQLAlchemy 2.x and Psycopg 3."

            # Verify that underlying finding & issue were synchronized
            with session_factory() as session:
                updated_case = session.get(VerificationCase, uuid.UUID(case_id))
                assert updated_case.current_claim == "System canonical database is PostgreSQL 16 managed via SQLAlchemy 2.x and Psycopg 3."
                # No more active conflicts -> status returned to pending_review
                assert updated_case.case_status == VerificationCaseStatus.PENDING_REVIEW.value

                updated_issue = session.execute(
                    select(VerificationIssue).where(VerificationIssue.case_id == updated_case.id)
                ).scalars().first()
                assert updated_issue.resolution_state == IssueResolutionState.RESOLVED.value

                # Check AuditLog entries
                audit_events = session.execute(
                    select(AuditLog).where(AuditLog.resource_id == conf_id)
                ).scalars().all()
                event_types = [a.event_type for a in audit_events]
                assert "conflict.assigned" in event_types
                assert "conflict.investigation_started" in event_types
                assert "conflict.context_requested" in event_types
                assert "conflict.note_added" in event_types
                assert "conflict.resolved" in event_types

            # 6. Reopen conflict
            reopen_res = client.post(
                f"/api/v1/projects/{proj_id_str}/conflicts/{conf_id}/reopen",
                headers=lead.headers,
                json={"reason": "New commit introduced Mongo sidecar for analytics"},
            )
            assert reopen_res.status_code == 200, reopen_res.text
            assert reopen_res.json()["resolution_state"] == "reopened"

            with session_factory() as session:
                reopened_case = session.get(VerificationCase, uuid.UUID(case_id))
                assert reopened_case.case_status == VerificationCaseStatus.CONFLICTED.value


def test_conflict_source_acl_enforcement(monkeypatch):
    """Ensure that users without source permissions receive redacted claims."""
    with isolated_auth_app(monkeypatch) as ctx:
        with TestClient(ctx.app) as client:
            session_factory = ctx.session_factory

            owner = register_and_login_user(client, email="project_owner@example.com", full_name="Project Owner")
            org_id_str, proj_id_str = _setup_project(client, owner.headers, "acl")
            project_id = uuid.UUID(proj_id_str)
            org_id = uuid.UUID(org_id_str)

            # Restricted viewer
            viewer = register_and_login_user(client, email="restricted_member@example.com", full_name="Restricted Member")
            invite_and_accept_member(
                client,
                organisation_id=org_id_str,
                inviter_headers=owner.headers,
                invitee=viewer,
                role_name="org_member",
            )
            client.post(
                f"/api/v1/projects/{proj_id_str}/members",
                headers=owner.headers,
                json={"user_id": str(viewer.user_id), "role_name": "project_member"},
            )

            conf_id = None
            with session_factory() as session:
                # Create a private GitHub source connection
                conn = SourceConnection(
                    organisation_id=org_id,
                    provider=EvidenceSourceType.GITHUB.value,
                    display_name="Test GitHub Connection",
                    status="active",
                    created_by_user_id=owner.user_id,
                )
                session.add(conn)
                session.flush()

                # Restrict source policy to owner only
                policy = SourceAccessPolicy(
                    organisation_id=org_id,
                    project_id=project_id,
                    source_connection_id=conn.id,
                    provider=EvidenceSourceType.GITHUB.value,
                    scope_identifier="res-secret",
                    visibility_policy=SourceVisibilityPolicy.VERIFIED_SOURCE_ACL.value,
                    allowed_user_ids=[str(owner.user_id)],
                    sync_permission_status=SourcePermissionVerificationStatus.VERIFIED.value,
                )
                session.add(policy)
                session.flush()

                # Create private evidence
                ev_private = EvidenceItem(
                    organisation_id=org_id,
                    project_id=project_id,
                    source_connection_id=conn.id,
                    source_access_policy_id=policy.id,
                    source_type=EvidenceSourceType.GITHUB.value,
                    source_provider=EvidenceSourceType.GITHUB.value,
                    source_external_id="gh-pr-999",
                    title="Classified Architecture Draft",
                    source_author_identity="ciso@example.com",
                    content_hash="b" * 64,
                    uploaded_by_user_id=owner.user_id,
                    category="project_document",
                    acl_scope="source_restricted",
                )
                session.add(ev_private)
                session.flush()

                case = VerificationCase(
                    organisation_id=org_id,
                    project_id=project_id,
                    target_type="knowledge_item",
                    target_id=uuid.uuid4(),
                    domain="technical_architecture",
                    case_status=VerificationCaseStatus.CONFLICTED.value,
                    title="Secret Encryption Protocol",
                    current_claim="AES-256-GCM is used",
                    priority="critical",
                )
                session.add(case)
                session.flush()

                ev_public = _seed_project_evidence(
                    session, org_id=org_id, project_id=project_id, user_id=owner.user_id, title="Public Repo"
                )
                conf = VerificationConflict(
                    organisation_id=org_id,
                    project_id=project_id,
                    case_id=case.id,
                    conflict_type=ConflictType.TECHNICAL_CONFLICT.value,
                    claim_a_text="Top secret internal encryption keys use Vault",
                    claim_a_source_evidence_id=ev_private.id,
                    claim_b_text="Public config indicates AWS KMS",
                    claim_b_source_evidence_id=ev_public.id,
                    side_a_source_title=ev_private.title,
                    side_a_provider=ev_private.source_type,
                    side_b_source_title=ev_public.title,
                    side_b_provider=ev_public.source_type,
                    explanation="Encryption mechanism discrepancy",
                    priority=ConflictPriority.CRITICAL.value,
                    temporal_comparison=TemporalComparison.AMBIGUOUS.value,
                    resolution_state=ConflictResolutionState.UNRESOLVED.value,
                )
                session.add(conf)
                session.commit()
                conf_id = str(conf.id)

            # 1. Owner accesses conflict details -> sees full claim A and claim B
            owner_detail = client.get(
                f"/api/v1/projects/{proj_id_str}/conflicts/{conf_id}",
                headers=owner.headers,
            )
            assert owner_detail.status_code == 200, owner_detail.text
            assert owner_detail.json()["side_a"]["is_accessible"] is True
            assert "Top secret" in owner_detail.json()["side_a"]["claim_text"]

            # 2. Restricted member accesses conflict details -> side A is fully redacted, side B stays visible
            viewer_detail = client.get(
                f"/api/v1/projects/{proj_id_str}/conflicts/{conf_id}",
                headers=viewer.headers,
            )
            assert viewer_detail.status_code == 200, viewer_detail.text
            payload = viewer_detail.json()
            assert payload["side_a"]["is_accessible"] is False
            assert payload["side_b"]["is_accessible"] is True
            assert "[Content redacted" in payload["side_a"]["claim_text"]
            assert "Classified Architecture Draft" not in payload["side_a"]["title"]
            assert "Access restricted by source ACL" in payload["side_a"]["redaction_reason"]
            assert "AWS KMS" in payload["side_b"]["claim_text"]
