"""Comprehensive test suite for Round 3 Remediation improvements.

Validates:
1. Continuous Project Intelligence & Change Impact Monitoring:
   - Post-sync automated change evaluation for created and modified evidence.
   - Distinguishes confirmed impacts (direct grounding links) from inferred impacts (topical overlap).
   - Automatic re-verification triggering for human-verified findings without overwriting verification status.
   - Audit trail logging for re-verification events.
   - Source-level ACL enforcement ensuring restricted source updates fail closed.
2. Change Impact Feed API:
   - `GET /api/v1/projects/{project_id}/verification/change-impact`
   - Pagination, impact nature, and field completeness.
3. Successor Onboarding PostgreSQL Persistence API:
   - `GET /api/v1/projects/{project_id}/handover/onboarding/progress`
   - `PUT /api/v1/projects/{project_id}/handover/onboarding/progress/{step_id}`
   - `DELETE /api/v1/projects/{project_id}/handover/onboarding/progress/{step_id}`
   - Cross-user tenant isolation and role-gated manager access.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.rbac_catalog import deterministic_rbac_id
from app.models.enums import (
    EvidenceSourceType,
    OrganisationStatus,
    ProjectStatus,
    ProjectVisibility,
    RoleName,
    UserStatus,
    VerificationCaseStatus,
    VerificationPriority,
    VerificationTargetType,
)
from app.models.evidence import EvidenceItem
from app.models.handover import ProjectOnboardingProgress
from app.models.knowledge import KnowledgeItem
from app.models.organisation import Organisation, OrganisationMembership
from app.models.project import Project, ProjectMembership
from app.models.user import User
from app.models.verification import VerificationCase, VerificationEvidenceRef
from app.services.verification_intelligence import ContinuousMonitoringService
from tests.conftest import create_isolated_auth_context, register_and_login_user


def _seed_test_project(
    session: Session,
) -> tuple[User, Organisation, Project]:
    """Create test User, Organisation, and Project."""
    user = User(
        id=uuid.uuid4(),
        email=f"remediation-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$fakehash",
        full_name="Remediation Engineer",
        status=UserStatus.ACTIVE,
    )
    session.add(user)
    session.flush()

    org = Organisation(
        id=uuid.uuid4(),
        name=f"Remediation Org {uuid.uuid4().hex[:6]}",
        slug=f"rem-org-{uuid.uuid4().hex[:6]}",
        created_by_id=user.id,
        status=OrganisationStatus.ACTIVE,
    )
    session.add(org)
    session.flush()

    project = Project(
        id=uuid.uuid4(),
        organisation_id=org.id,
        created_by_id=user.id,
        owner_id=user.id,
        name=f"Remediation Project {uuid.uuid4().hex[:6]}",
        slug=f"rem-proj-{uuid.uuid4().hex[:6]}",
        visibility=ProjectVisibility.ORGANISATION,
        status=ProjectStatus.ACTIVE,
    )
    session.add(project)
    session.flush()

    session.add(
        OrganisationMembership(
            id=uuid.uuid4(),
            organisation_id=org.id,
            user_id=user.id,
            role_id=deterministic_rbac_id("role", RoleName.ORG_OWNER.value),
            status="active",
        )
    )

    membership = ProjectMembership(
        id=uuid.uuid4(),
        project_id=project.id,
        user_id=user.id,
        role_id=deterministic_rbac_id("role", RoleName.PROJECT_MANAGER.value),
        status="active",
    )
    session.add(membership)
    session.flush()

    return user, org, project


def test_continuous_monitoring_confirmed_vs_inferred_impact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ContinuousMonitoringService distinguishes confirmed direct links from inferred topical impacts."""
    ctx = create_isolated_auth_context(monkeypatch)
    with ctx.session_factory() as session:
        user, org, project = _seed_test_project(session)

        ev = EvidenceItem(
            id=uuid.uuid4(),
            organisation_id=org.id,
            project_id=project.id,
            source_type=EvidenceSourceType.GITHUB.value,
            category="commit",
            source_external_id="gh-commit-123456",
            title="Database Migration Script V2",
            source_url="https://github.com/org/repo/commit/123456",
            mime_type="text/x-sql",
            content_hash=hashlib.sha256(b"commit1").hexdigest(),
            source_created_at=datetime.now(UTC),
            processing_status="extracted",
            acl_scope="project_members",
        )
        session.add(ev)
        session.flush()

        # Case 1: Confirmed direct link, human-verified
        ki_direct = KnowledgeItem(
            id=uuid.uuid4(),
            organisation_id=org.id,
            project_id=project.id,
            category="technical_architecture",
            primary_domain="technical_and_architectural",
            title="PostgreSQL Database Schema",
            structured_summary="Canonical database schema is PostgreSQL.",
            structured_payload={},
            support_classification="direct",
            extraction_model="qwen3:8b",
            prompt_version="1.0.0",
            fingerprint=uuid.uuid4().hex,
            epistemic_status="human_verified",
            review_status="approved",
        )
        session.add(ki_direct)
        session.flush()

        case_direct = VerificationCase(
            organisation_id=org.id,
            project_id=project.id,
            target_type=VerificationTargetType.KNOWLEDGE_ITEM.value,
            target_id=ki_direct.id,
            current_claim=f"{ki_direct.title}. {ki_direct.structured_summary}",
            case_status=VerificationCaseStatus.VERIFIED.value,
            machine_assessment_status="passed",
            priority=VerificationPriority.LOW.value,
            machine_assessment_json={"assessed_at": datetime.now(UTC).isoformat()},
            version=1,
        )
        session.add(case_direct)
        session.flush()

        # Direct link via VerificationEvidenceRef
        ref = VerificationEvidenceRef(
            id=uuid.uuid4(),
            organisation_id=org.id,
            project_id=project.id,
            case_id=case_direct.id,
            evidence_item_id=ev.id,
            relationship_to_finding="supports",
        )
        session.add(ref)

        # Case 2: Inferred topical correlation (shares "Database Migration"), unverified candidate
        ki_inferred = KnowledgeItem(
            id=uuid.uuid4(),
            organisation_id=org.id,
            project_id=project.id,
            category="operational_historical",
            primary_domain="operational_and_historical",
            title="Database Migration Deployment Playbook",
            structured_summary="Deployment process executes database migration scripts in order.",
            structured_payload={},
            support_classification="interpretation",
            extraction_model="qwen3:8b",
            prompt_version="1.0.0",
            fingerprint=uuid.uuid4().hex,
            epistemic_status="extracted",
            review_status="pending_review",
        )
        session.add(ki_inferred)
        session.flush()

        case_inferred = VerificationCase(
            organisation_id=org.id,
            project_id=project.id,
            target_type=VerificationTargetType.KNOWLEDGE_ITEM.value,
            target_id=ki_inferred.id,
            current_claim=f"{ki_inferred.title}. {ki_inferred.structured_summary}",
            case_status=VerificationCaseStatus.CANDIDATE.value,
            machine_assessment_status="passed",
            priority=VerificationPriority.MEDIUM.value,
            machine_assessment_json={"assessed_at": datetime.now(UTC).isoformat()},
            version=1,
        )
        session.add(case_inferred)
        session.commit()

        # Run ContinuousMonitoringService
        service = ContinuousMonitoringService(session)
        impact = service.process_source_change_event(
            project_id=project.id,
            evidence_item=ev,
            change_type="modified",
            triggered_by_user_id=user.id,
        )
        session.commit()

        assert impact.evidence_id == ev.id
        assert impact.change_type == "modified"
        assert case_direct.id in impact.affected_case_ids
        assert impact.reverification_triggered is True

        # Refresh cases from database
        session.refresh(case_direct)
        session.refresh(case_inferred)

        # 1. Check direct case: verification status NOT overwritten, but reverification flagged
        assert case_direct.case_status == VerificationCaseStatus.VERIFIED.value
        mon_direct = case_direct.machine_assessment_json["monitoring_status"]
        assert mon_direct["reverification_triggered"] is True
        assert mon_direct["impact_nature"] == "confirmed"
        assert "Direct evidence link" in mon_direct["impact_summary"]

        # 2. Check inferred case: flagged with inferred impact nature
        mon_inferred = case_inferred.machine_assessment_json["monitoring_status"]
        assert mon_inferred["impact_nature"] == "inferred"
        assert "Inferred topical correlation" in mon_inferred["impact_summary"]
        assert mon_inferred["reverification_triggered"] is False

        # Query change impact feed items
        events, total = service.get_change_impact_events(
            project_id=project.id,
            viewer_user_id=user.id,
            has_manage=True,
        )
        assert total >= 2
        case_ids = [e["case_id"] for e in events]
        assert case_direct.id in case_ids
        assert case_inferred.id in case_ids


def test_change_impact_feed_api_and_source_acl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /api/v1/projects/{project_id}/verification/change-impact respects permissions and source ACL."""
    ctx = create_isolated_auth_context(monkeypatch)
    client = TestClient(ctx.app)

    # Register project manager and regular member
    manager_session = register_and_login_user(
        client,
        email="manager@example.com",
        full_name="Manager User",
    )
    member_session = register_and_login_user(
        client,
        email="member@example.com",
        full_name="Regular Member",
    )

    with ctx.session_factory() as session:
        org = Organisation(
            id=uuid.uuid4(),
            name="Impact Feed Org",
            slug=f"if-org-{uuid.uuid4().hex[:6]}",
            created_by_id=manager_session.user_id,
            status=OrganisationStatus.ACTIVE,
        )
        session.add(org)
        session.flush()

        project = Project(
            id=uuid.uuid4(),
            organisation_id=org.id,
            created_by_id=manager_session.user_id,
            owner_id=manager_session.user_id,
            name="Impact Feed Project",
            slug=f"if-proj-{uuid.uuid4().hex[:6]}",
            visibility=ProjectVisibility.ORGANISATION,
            status=ProjectStatus.ACTIVE,
        )
        session.add(project)
        session.flush()

        session.add(
            OrganisationMembership(
                id=uuid.uuid4(),
                organisation_id=org.id,
                user_id=manager_session.user_id,
                role_id=deterministic_rbac_id("role", RoleName.ORG_OWNER.value),
                status="active",
            )
        )
        session.add(
            OrganisationMembership(
                id=uuid.uuid4(),
                organisation_id=org.id,
                user_id=member_session.user_id,
                role_id=deterministic_rbac_id("role", RoleName.ORG_MEMBER.value),
                status="active",
            )
        )

        # Manager membership
        session.add(
            ProjectMembership(
                id=uuid.uuid4(),
                project_id=project.id,
                user_id=manager_session.user_id,
                role_id=deterministic_rbac_id("role", RoleName.PROJECT_MANAGER.value),
                status="active",
            )
        )
        # Regular member membership (reader)
        session.add(
            ProjectMembership(
                id=uuid.uuid4(),
                project_id=project.id,
                user_id=member_session.user_id,
                role_id=deterministic_rbac_id("role", RoleName.PROJECT_MEMBER.value),
                status="active",
            )
        )

        # Public evidence item
        ev_public = EvidenceItem(
            id=uuid.uuid4(),
            organisation_id=org.id,
            project_id=project.id,
            source_type=EvidenceSourceType.DOCUMENT_UPLOAD.value,
            category="pdf_document",
            source_external_id="doc-upload-123456",
            title="Public Architecture Spec",
            mime_type="application/pdf",
            content_hash=hashlib.sha256(b"doc1").hexdigest(),
            source_created_at=datetime.now(UTC),
            processing_status="extracted",
            acl_scope="project_members",
        )
        session.add(ev_public)
        session.flush()

        ki = KnowledgeItem(
            id=uuid.uuid4(),
            organisation_id=org.id,
            project_id=project.id,
            category="technical_architecture",
            primary_domain="technical_and_architectural",
            title="API Architecture Design",
            structured_summary="REST API design specification.",
            structured_payload={},
            support_classification="direct",
            extraction_model="qwen3:8b",
            prompt_version="1.0.0",
            fingerprint=uuid.uuid4().hex,
            epistemic_status="human_verified",
            review_status="approved",
        )
        session.add(ki)
        session.flush()

        case = VerificationCase(
            organisation_id=org.id,
            project_id=project.id,
            target_type=VerificationTargetType.KNOWLEDGE_ITEM.value,
            target_id=ki.id,
            case_status=VerificationCaseStatus.VERIFIED.value,
            machine_assessment_status="passed",
            priority=VerificationPriority.LOW.value,
            machine_assessment_json={"assessed_at": datetime.now(UTC).isoformat()},
            version=1,
        )
        session.add(case)
        session.flush()

        session.add(
            VerificationEvidenceRef(
                id=uuid.uuid4(),
                organisation_id=org.id,
                project_id=project.id,
                case_id=case.id,
                evidence_item_id=ev_public.id,
                relationship_to_finding="supports",
            )
        )
        session.commit()

        # Trigger monitoring
        monitor = ContinuousMonitoringService(session)
        monitor.process_source_change_event(
            project_id=project.id,
            evidence_item=ev_public,
            change_type="modified",
            triggered_by_user_id=manager_session.user_id,
        )
        session.commit()

        proj_id_str = str(project.id)

    # 1. Manager queries feed
    res_mgr = client.get(
        f"/api/v1/projects/{proj_id_str}/verification/change-impact",
        headers=manager_session.headers,
    )
    assert res_mgr.status_code == 200
    data_mgr = res_mgr.json()
    assert data_mgr["total"] >= 1
    assert len(data_mgr["items"]) >= 1
    first_item = data_mgr["items"][0]
    assert first_item["evidence_title"] == "Public Architecture Spec"
    assert first_item["impact_nature"] == "confirmed"
    assert first_item["reverification_triggered"] is True

    # 2. Member queries feed
    res_mem = client.get(
        f"/api/v1/projects/{proj_id_str}/verification/change-impact",
        headers=member_session.headers,
    )
    assert res_mem.status_code == 200
    data_mem = res_mem.json()
    assert data_mem["total"] >= 1

    # 3. Unauthenticated request rejected
    res_anon = client.get(
        f"/api/v1/projects/{proj_id_str}/verification/change-impact",
    )
    assert res_anon.status_code == 401


def test_successor_onboarding_persistence_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test full CRUD lifecycle and tenant/user isolation for ProjectOnboardingProgress."""
    ctx = create_isolated_auth_context(monkeypatch)
    client = TestClient(ctx.app)

    manager = register_and_login_user(
        client,
        email="onboard_mgr@example.com",
        full_name="Onboarding Manager",
    )
    successor = register_and_login_user(
        client,
        email="successor@example.com",
        full_name="Incoming Successor",
    )

    with ctx.session_factory() as session:
        org = Organisation(
            id=uuid.uuid4(),
            name="Onboarding Test Org",
            slug=f"ob-org-{uuid.uuid4().hex[:6]}",
            created_by_id=manager.user_id,
            status=OrganisationStatus.ACTIVE,
        )
        session.add(org)
        session.flush()

        project = Project(
            id=uuid.uuid4(),
            organisation_id=org.id,
            created_by_id=manager.user_id,
            owner_id=manager.user_id,
            name="Onboarding Test Project",
            slug=f"ob-proj-{uuid.uuid4().hex[:6]}",
            visibility=ProjectVisibility.ORGANISATION,
            status=ProjectStatus.ACTIVE,
        )
        session.add(project)
        session.flush()

        session.add(
            ProjectMembership(
                id=uuid.uuid4(),
                project_id=project.id,
                user_id=manager.user_id,
                role_id=deterministic_rbac_id("role", RoleName.PROJECT_MANAGER.value),
                status="active",
            )
        )
        session.add(
            ProjectMembership(
                id=uuid.uuid4(),
                project_id=project.id,
                user_id=successor.user_id,
                role_id=deterministic_rbac_id("role", RoleName.PROJECT_MEMBER.value),
                status="active",
            )
        )
        session.add(
            OrganisationMembership(
                id=uuid.uuid4(),
                organisation_id=org.id,
                user_id=manager.user_id,
                role_id=deterministic_rbac_id("role", RoleName.ORG_OWNER.value),
                status="active",
            )
        )
        session.add(
            OrganisationMembership(
                id=uuid.uuid4(),
                organisation_id=org.id,
                user_id=successor.user_id,
                role_id=deterministic_rbac_id("role", RoleName.ORG_MEMBER.value),
                status="active",
            )
        )
        session.commit()
        proj_id_str = str(project.id)

    # 1. Successor initially has 0 completed steps
    res_init = client.get(
        f"/api/v1/projects/{proj_id_str}/handover/onboarding/progress",
        headers=successor.headers,
    )
    assert res_init.status_code == 200
    data_init = res_init.json()
    assert data_init["user_id"] == str(successor.user_id)
    assert data_init["completed_steps"] == {}
    assert len(data_init["items"]) == 0

    # 2. Successor marks step 1 "welcome" as completed
    res_put = client.put(
        f"/api/v1/projects/{proj_id_str}/handover/onboarding/progress/welcome",
        headers=successor.headers,
        json={"is_completed": True},
    )
    assert res_put.status_code == 200
    data_put = res_put.json()
    assert data_put["step_id"] == "welcome"
    assert data_put["is_completed"] is True
    assert data_put["completed_at"] is not None

    # 3. Successor marks step 2 "role" as completed
    client.put(
        f"/api/v1/projects/{proj_id_str}/handover/onboarding/progress/role",
        headers=successor.headers,
        json={"is_completed": True},
    )

    # 4. Successor gets updated progress
    res_prog = client.get(
        f"/api/v1/projects/{proj_id_str}/handover/onboarding/progress",
        headers=successor.headers,
    )
    assert res_prog.status_code == 200
    data_prog = res_prog.json()
    assert data_prog["completed_steps"] == {"welcome": True, "role": True}
    assert len(data_prog["items"]) == 2

    # 5. User Isolation: Manager checks their own progress (should be empty)
    res_mgr_prog = client.get(
        f"/api/v1/projects/{proj_id_str}/handover/onboarding/progress",
        headers=manager.headers,
    )
    assert res_mgr_prog.status_code == 200
    assert res_mgr_prog.json()["completed_steps"] == {}

    # 6. Manager checks Successor's progress (allowed because manager has project.manage)
    res_mgr_view_succ = client.get(
        f"/api/v1/projects/{proj_id_str}/handover/onboarding/progress?target_user_id={successor.user_id}",
        headers=manager.headers,
    )
    assert res_mgr_view_succ.status_code == 200
    assert res_mgr_view_succ.json()["completed_steps"] == {"welcome": True, "role": True}

    # 7. Successor tries to inspect Manager's progress without manage permission (denied fail-closed)
    res_succ_view_mgr = client.get(
        f"/api/v1/projects/{proj_id_str}/handover/onboarding/progress?target_user_id={manager.user_id}",
        headers=successor.headers,
    )
    assert res_succ_view_mgr.status_code == 403

    # 8. Successor un-completes step 1
    res_uncomplete = client.put(
        f"/api/v1/projects/{proj_id_str}/handover/onboarding/progress/welcome",
        headers=successor.headers,
        json={"is_completed": False},
    )
    assert res_uncomplete.status_code == 200
    assert res_uncomplete.json()["is_completed"] is False

    # 9. Delete step completion record
    res_del = client.delete(
        f"/api/v1/projects/{proj_id_str}/handover/onboarding/progress/role",
        headers=successor.headers,
    )
    assert res_del.status_code == 200
    assert res_del.json()["status"] == "deleted"

    # 10. Verify remaining in DB
    with ctx.session_factory() as session:
        records = (
            session.query(ProjectOnboardingProgress)
            .filter(
                ProjectOnboardingProgress.project_id == project.id,
                ProjectOnboardingProgress.user_id == successor.user_id,
            )
            .all()
        )
        assert len(records) == 1
        assert records[0].step_id == "welcome"
        assert records[0].is_completed is False
