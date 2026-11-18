"""Targeted Verification Center Phase 1 tests (models, engine, 5 actions, ACLs, audit)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.enums import (
    EpistemicStatus,
    EvidenceSourceType,
    KnowledgeCategory,
    KnowledgeReviewStatus,
    SourcePermissionVerificationStatus,
    SourceVisibilityPolicy,
    VerificationCaseStatus,
    VerificationCategory,
)
from app.models.evidence import EvidenceItem
from app.models.integration import SourceAccessPolicy, SourceConnection
from app.models.knowledge import KnowledgeEvidenceLink, KnowledgeItem
from app.models.relationship import KnowledgeEntity, KnowledgeRelationship
from app.models.verification import (
    VerificationCase,
    VerificationConflict,
    VerificationFindingRevision,
)
from tests.conftest import (
    invite_and_accept_member,
    isolated_auth_app,
    register_and_login_user,
)


def _create_org_and_project(
    client: TestClient, headers: dict[str, str], slug_suffix: str
) -> tuple[str, str]:
    org_resp = client.post(
        "/api/v1/organisations",
        headers=headers,
        json={"name": f"Org {slug_suffix}", "slug": f"org-{slug_suffix}"},
    )
    assert org_resp.status_code == 201, org_resp.text
    org_id = org_resp.json()["id"]

    proj_resp = client.post(
        f"/api/v1/organisations/{org_id}/projects",
        headers=headers,
        json={
            "name": f"Project {slug_suffix}",
            "slug": f"proj-{slug_suffix}",
        },
    )
    assert proj_resp.status_code == 201, proj_resp.text
    return org_id, proj_resp.json()["id"]


def _seed_evidence(
    session: Session,
    *,
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    source_type: str = EvidenceSourceType.GITHUB.value,
    title: str = "PR #42 Password Reset",
    source_timestamp: datetime | None = None,
    acl_scope: str = "project_members",
    allowed_user_ids: list[str] | None = None,
) -> EvidenceItem:
    policy_id = None
    conn_id = None
    if acl_scope == "source_restricted":
        conn = SourceConnection(
            organisation_id=org_id,
            provider=source_type,
            display_name="Test GitHub Connection",
            status="active",
            created_by_user_id=user_id,
        )
        session.add(conn)
        session.flush()
        conn_id = conn.id
        policy = SourceAccessPolicy(
            organisation_id=org_id,
            project_id=project_id,
            source_connection_id=conn.id,
            provider=source_type,
            scope_identifier=f"res-{uuid.uuid4().hex[:8]}",
            visibility_policy=SourceVisibilityPolicy.VERIFIED_SOURCE_ACL.value,
            allowed_user_ids=allowed_user_ids or [],
            sync_permission_status=SourcePermissionVerificationStatus.VERIFIED.value,
        )
        session.add(policy)
        session.flush()
        policy_id = policy.id

    ev = EvidenceItem(
        organisation_id=org_id,
        project_id=project_id,
        source_type=source_type,
        source_provider=source_type,
        category="design_document",
        source_external_id=f"src-{uuid.uuid4().hex[:8]}",
        source_url="https://github.com/org/repo/pull/42",
        source_author_identity="alice@example.com",
        source_created_at=source_timestamp or datetime.now(UTC),
        title=title,
        content_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        acl_scope=acl_scope,
        source_connection_id=conn_id,
        source_access_policy_id=policy_id,
        uploaded_by_user_id=user_id,
    )
    session.add(ev)
    session.flush()
    return ev


def _seed_knowledge_item(
    session: Session,
    *,
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    title: str,
    statement: str,
    category: str = KnowledgeCategory.WORK_ITEMS.value,
    evidence: EvidenceItem | None = None,
    excerpt: str | None = None,
    confidence: float = 0.85,
) -> KnowledgeItem:
    ki = KnowledgeItem(
        organisation_id=org_id,
        project_id=project_id,
        category=category,
        support_classification="direct" if evidence is not None else "uncertain",
        title=title,
        structured_summary=statement,
        structured_payload={"summary": statement},
        extraction_model="qwen3:8b",
        prompt_version="p2.6-v1",
        fingerprint=uuid.uuid4().hex,
        epistemic_status=EpistemicStatus.EXTRACTED.value,
        review_status=KnowledgeReviewStatus.PENDING_REVIEW.value,
        confidence_metadata_json={"confidence": confidence},
    )
    session.add(ki)
    session.flush()
    if evidence is not None:
        session.add(
            KnowledgeEvidenceLink(
                organisation_id=org_id,
                project_id=project_id,
                knowledge_item_id=ki.id,
                evidence_id=evidence.id,
                support_type="direct",
                supporting_excerpt=excerpt or statement,
            )
        )
        session.flush()
    return ki


def test_sync_and_six_verification_categories(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sync KnowledgeItems + Relationships and verify all 6 automated check categories."""
    with isolated_auth_app(monkeypatch) as ctx:
        with TestClient(ctx.app) as client:
            _run_sync_and_six_categories_test(ctx.session_factory, client)


def _run_sync_and_six_categories_test(session_factory, client: TestClient) -> None:
    owner = register_and_login_user(client, email="owner1@example.com", full_name="Owner One")
    org_id_str, proj_id_str = _create_org_and_project(client, owner.headers, "vc-cats")
    org_id, proj_id = uuid.UUID(org_id_str), uuid.UUID(proj_id_str)

    with session_factory() as db:
        now = datetime.now(UTC)
        ev_new = _seed_evidence(
            db,
            org_id=org_id,
            project_id=proj_id,
            user_id=owner.user_id,
            source_type=EvidenceSourceType.JIRA.value,
            title="AUTH-12 Password reset",
            source_timestamp=now,
        )
        ev_old = _seed_evidence(
            db,
            org_id=org_id,
            project_id=proj_id,
            user_id=owner.user_id,
            source_type=EvidenceSourceType.DOCUMENT_UPLOAD.value,
            title="Legacy Architecture Doc",
            source_timestamp=now - timedelta(days=150),
        )
        ev_pr = _seed_evidence(
            db,
            org_id=org_id,
            project_id=proj_id,
            user_id=owner.user_id,
            source_type=EvidenceSourceType.GITHUB.value,
            title="PR #99 Still Open",
            source_timestamp=now,
        )

        # 1. Missing evidence item
        _seed_knowledge_item(
            db,
            org_id=org_id,
            project_id=proj_id,
            title="Missing Evidence Decision",
            statement="We chose Redis for sessions.",
            category=KnowledgeCategory.DECISIONS_RATIONALE.value,
            evidence=None,
        )
        # 2. Outdated item
        _seed_knowledge_item(
            db,
            org_id=org_id,
            project_id=proj_id,
            title="Old Architecture Endpoint",
            statement="Legacy Architecture Doc defines v1 endpoint.",
            category=KnowledgeCategory.TECHNICAL_ARCHITECTURE.value,
            evidence=ev_old,
            excerpt="Legacy Architecture Doc defines v1 endpoint.",
        )
        # 3 & 4. Duplicate findings
        _seed_knowledge_item(
            db,
            org_id=org_id,
            project_id=proj_id,
            title="Auth Token Choice A",
            statement="Authentication uses Argon2id and short lived JWT access tokens.",
            evidence=ev_new,
            excerpt="Authentication uses Argon2id and short lived JWT access tokens.",
        )
        _seed_knowledge_item(
            db,
            org_id=org_id,
            project_id=proj_id,
            title="Auth Token Choice B",
            statement="Authentication uses Argon2id and short lived JWT access tokens!",
            evidence=ev_new,
            excerpt="Authentication uses Argon2id and short lived JWT access tokens.",
        )
        # 5. Conflicting evidence item (2 opposing sources)
        ki_conflict = _seed_knowledge_item(
            db,
            org_id=org_id,
            project_id=proj_id,
            title="Password Reset Status",
            statement="Password reset feature is completed.",
            evidence=ev_new,
            excerpt="Jira ticket AUTH-12 marked Done.",
        )
        db.add(
            KnowledgeEvidenceLink(
                organisation_id=org_id,
                project_id=proj_id,
                knowledge_item_id=ki_conflict.id,
                evidence_id=ev_pr.id,
                support_type="contradiction",
                supporting_excerpt="GitHub PR #99 remains open and wip.",
            )
        )
        # 6. Uncertain relationship
        e1 = KnowledgeEntity(
            organisation_id=org_id,
            project_id=proj_id,
            entity_type="service",
            canonical_name="AuthService",
            normalized_name="authservice",
        )
        e2 = KnowledgeEntity(
            organisation_id=org_id,
            project_id=proj_id,
            entity_type="service",
            canonical_name="BillingService",
            normalized_name="billingservice",
        )
        db.add_all([e1, e2])
        db.flush()
        db.add(
            KnowledgeRelationship(
                organisation_id=org_id,
                project_id=proj_id,
                source_entity_id=e1.id,
                target_entity_id=e2.id,
                relationship_type="depends_on",
                confidence_score=0.45,
                fingerprint=uuid.uuid4().hex,
            )
        )
        db.commit()

    sync_resp = client.post(
        f"/api/v1/projects/{proj_id_str}/verification/sync",
        headers=owner.headers,
    )
    assert sync_resp.status_code == 200, sync_resp.text
    sync_data = sync_resp.json()
    assert sync_data["cases_created"] == 6
    assert sync_data["issues_detected"] >= 5

    queue_resp = client.get(
        f"/api/v1/projects/{proj_id_str}/verification/queue",
        headers=owner.headers,
    )
    assert queue_resp.status_code == 200, queue_resp.text
    items = queue_resp.json()["items"]
    all_categories = {cat for item in items for cat in item["verification_categories"]}
    assert VerificationCategory.MISSING_EVIDENCE.value in all_categories
    assert VerificationCategory.OUTDATED_INFORMATION.value in all_categories
    assert VerificationCategory.DUPLICATE_FINDINGS.value in all_categories
    assert VerificationCategory.CONFLICTING_EVIDENCE.value in all_categories
    assert VerificationCategory.UNCERTAIN_RELATIONSHIPS.value in all_categories

    summary_resp = client.get(
        f"/api/v1/projects/{proj_id_str}/verification/summary",
        headers=owner.headers,
    )
    assert summary_resp.status_code == 200
    summary = summary_resp.json()
    assert summary["conflicted_count"] >= 1
    assert summary["unresolved_count"] >= 1


def test_five_reviewer_actions_and_audit_history(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise all 5 reviewer actions end-to-end with persistence and audit logs."""
    with isolated_auth_app(monkeypatch) as ctx:
        with TestClient(ctx.app) as client:
            _run_five_reviewer_actions_test(ctx.session_factory, client)


def _run_five_reviewer_actions_test(session_factory, client: TestClient) -> None:
    reviewer = register_and_login_user(client, email="rev1@example.com", full_name="Reviewer One")
    teammate = register_and_login_user(client, email="dev1@example.com", full_name="Teammate One")
    org_id_str, proj_id_str = _create_org_and_project(client, reviewer.headers, "vc-actions")
    org_id, proj_id = uuid.UUID(org_id_str), uuid.UUID(proj_id_str)

    invite_and_accept_member(
        client,
        organisation_id=org_id_str,
        inviter_headers=reviewer.headers,
        invitee=teammate,
        role_name="org_member",
    )
    add_proj_member = client.post(
        f"/api/v1/projects/{proj_id_str}/members",
        headers=reviewer.headers,
        json={"user_id": str(teammate.user_id), "role_name": "project_member"},
    )
    assert add_proj_member.status_code in (200, 201), add_proj_member.text

    with session_factory() as db:
        ev = _seed_evidence(
            db,
            org_id=org_id,
            project_id=proj_id,
            user_id=reviewer.user_id,
            title="ADR-001 Database Selection",
        )
        ki_approve = _seed_knowledge_item(
            db,
            org_id=org_id,
            project_id=proj_id,
            title="PostgreSQL Canonical Store",
            statement="PostgreSQL is the canonical database for structured records.",
            evidence=ev,
        )
        ki_reject = _seed_knowledge_item(
            db,
            org_id=org_id,
            project_id=proj_id,
            title="Incorrect MongoDB Claim",
            statement="MongoDB is used as the primary database.",
            evidence=ev,
        )
        ki_unresolved = _seed_knowledge_item(
            db,
            org_id=org_id,
            project_id=proj_id,
            title="Unclear Deployment Window",
            statement="Deployment happens on weekends.",
            evidence=ev,
        )
        db.commit()
        ki_approve_id = ki_approve.id
        ki_reject_id = ki_reject.id
        ki_unresolved_id = ki_unresolved.id

    client.post(f"/api/v1/projects/{proj_id_str}/verification/sync", headers=reviewer.headers)
    q = client.get(
        f"/api/v1/projects/{proj_id_str}/verification/queue", headers=reviewer.headers
    ).json()["items"]
    by_target = {item["target_id"]: item["id"] for item in q}

    approve_case_id = by_target[str(ki_approve_id)]
    reject_case_id = by_target[str(ki_reject_id)]
    unresolved_case_id = by_target[str(ki_unresolved_id)]

    # Action 1: Edit Finding (preserves original AI claim, increments version, creates revision)
    edit_resp = client.patch(
        f"/api/v1/projects/{proj_id_str}/verification/cases/{approve_case_id}/finding",
        headers=reviewer.headers,
        json={
            "current_claim": "PostgreSQL 16 is the canonical database for structured records and audit logs.",
            "edit_reason": "Clarified PostgreSQL version and audit scope from ADR-001.",
            "reviewer_note": "Verified against ADR-001.",
        },
    )
    assert edit_resp.status_code == 200, edit_resp.text
    edited = edit_resp.json()
    assert edited["version"] == 2
    assert edited["original_ai_claim"] == "PostgreSQL is the canonical database for structured records."
    assert len(edited["revisions"]) == 2

    # Action 2: Request Additional Context + Respond
    ctx_resp = client.post(
        f"/api/v1/projects/{proj_id_str}/verification/cases/{approve_case_id}/request-context",
        headers=reviewer.headers,
        json={
            "question": "Can you confirm the backup retention window for PostgreSQL?",
            "requested_from_user_id": str(teammate.user_id),
            "requested_information_type": "operational_detail",
        },
    )
    assert ctx_resp.status_code == 200, ctx_resp.text
    req_id = ctx_resp.json()["context_requests"][0]["id"]

    respond_resp = client.post(
        f"/api/v1/projects/{proj_id_str}/verification/context-requests/{req_id}/respond",
        headers=teammate.headers,
        json={"response_text": "Daily snapshots are retained for 30 days."},
    )
    assert respond_resp.status_code == 200, respond_resp.text
    assert respond_resp.json()["status"] == "responded"

    # Action 3: Approve
    app_resp = client.post(
        f"/api/v1/projects/{proj_id_str}/verification/cases/{approve_case_id}/approve",
        headers=reviewer.headers,
        json={"reviewer_note": "All evidence and context confirmed."},
    )
    assert app_resp.status_code == 200, app_resp.text
    app_data = app_resp.json()
    assert app_data["case_status"] == VerificationCaseStatus.VERIFIED.value
    assert app_data["handover_eligible"] is True

    # Action 4: Reject (reason required)
    bad_rej = client.post(
        f"/api/v1/projects/{proj_id_str}/verification/cases/{reject_case_id}/reject",
        headers=reviewer.headers,
        json={"decision_reason": "  "},
    )
    assert bad_rej.status_code == 422

    rej_resp = client.post(
        f"/api/v1/projects/{proj_id_str}/verification/cases/{reject_case_id}/reject",
        headers=reviewer.headers,
        json={"decision_reason": "Contradicts ADR-001; MongoDB was never adopted."},
    )
    assert rej_resp.status_code == 200, rej_resp.text
    assert rej_resp.json()["case_status"] == VerificationCaseStatus.REJECTED.value
    assert rej_resp.json()["handover_eligible"] is False

    # Action 5: Mark Unresolved
    unres_resp = client.post(
        f"/api/v1/projects/{proj_id_str}/verification/cases/{unresolved_case_id}/mark-unresolved",
        headers=reviewer.headers,
        json={"decision_reason": "Deployment calendar is missing from uploaded docs."},
    )
    assert unres_resp.status_code == 200, unres_resp.text
    assert unres_resp.json()["case_status"] == VerificationCaseStatus.UNRESOLVED.value
    assert unres_resp.json()["handover_eligible"] is False

    # Verify AuditLog & KnowledgeItem states in DB
    with session_factory() as db:
        ki_app_db = db.get(KnowledgeItem, ki_approve_id)
        ki_rej_db = db.get(KnowledgeItem, ki_reject_id)
        ki_unr_db = db.get(KnowledgeItem, ki_unresolved_id)
        assert ki_app_db is not None and ki_app_db.review_status == KnowledgeReviewStatus.APPROVED.value
        assert ki_app_db.epistemic_status == EpistemicStatus.HUMAN_VERIFIED.value
        assert ki_rej_db is not None and ki_rej_db.review_status == KnowledgeReviewStatus.REJECTED.value
        assert ki_unr_db is not None and ki_unr_db.review_status == KnowledgeReviewStatus.NEEDS_CLARIFICATION.value

        audits = db.execute(
            select(AuditLog.event_type).where(AuditLog.project_id == proj_id)
        ).scalars().all()
        assert "verification.case.approved" in audits
        assert "verification.case.rejected" in audits
        assert "verification.case.edited" in audits
        assert "verification.case.marked_unresolved" in audits


def test_source_acl_and_rbac_isolation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Enforce Project Membership != Source Access and RBAC review permissions."""
    with isolated_auth_app(monkeypatch) as ctx:
        with TestClient(ctx.app) as client:
            _run_source_acl_test(ctx.session_factory, client)


def _run_source_acl_test(session_factory, client: TestClient) -> None:
    owner = register_and_login_user(client, email="acl_owner@example.com", full_name="ACL Owner")
    member = register_and_login_user(client, email="acl_member@example.com", full_name="ACL Member")
    outsider = register_and_login_user(client, email="outsider@example.com", full_name="Outsider")

    org_id_str, proj_id_str = _create_org_and_project(client, owner.headers, "vc-acl")
    org_id, proj_id = uuid.UUID(org_id_str), uuid.UUID(proj_id_str)

    invite_and_accept_member(
        client,
        organisation_id=org_id_str,
        inviter_headers=owner.headers,
        invitee=member,
        role_name="org_member",
    )
    client.post(
        f"/api/v1/projects/{proj_id_str}/members",
        headers=owner.headers,
        json={"user_id": str(member.user_id), "role_name": "project_member"},
    )

    with session_factory() as db:
        restricted_ev = _seed_evidence(
            db,
            org_id=org_id,
            project_id=proj_id,
            user_id=owner.user_id,
            title="Private Repo Secret Spec",
            acl_scope="source_restricted",
            allowed_user_ids=[str(owner.user_id)],
        )
        ki = _seed_knowledge_item(
            db,
            org_id=org_id,
            project_id=proj_id,
            title="Private Repo Finding",
            statement="Secret rotation runs every 30 days.",
            evidence=restricted_ev,
        )
        db.commit()
        ki_id = ki.id

    client.post(f"/api/v1/projects/{proj_id_str}/verification/sync", headers=owner.headers)
    q = client.get(
        f"/api/v1/projects/{proj_id_str}/verification/queue", headers=owner.headers
    ).json()["items"]
    case_id = next(i["id"] for i in q if i["target_id"] == str(ki_id))

    # Owner sees the restricted evidence
    owner_detail = client.get(
        f"/api/v1/projects/{proj_id_str}/verification/cases/{case_id}",
        headers=owner.headers,
    )
    assert owner_detail.status_code == 200
    assert len(owner_detail.json()["evidence_references"]) == 1
    assert owner_detail.json()["restricted_evidence_count"] == 0

    # Project member WITHOUT source access does NOT see restricted evidence (fail-closed)
    member_detail = client.get(
        f"/api/v1/projects/{proj_id_str}/verification/cases/{case_id}",
        headers=member.headers,
    )
    assert member_detail.status_code == 200
    assert len(member_detail.json()["evidence_references"]) == 0
    assert member_detail.json()["restricted_evidence_count"] == 1

    # Project member without project.knowledge.review cannot approve
    forbid_resp = client.post(
        f"/api/v1/projects/{proj_id_str}/verification/cases/{case_id}/approve",
        headers=member.headers,
        json={"reviewer_note": "Trying to approve"},
    )
    assert forbid_resp.status_code == 403

    # Outsider cannot read project verification queue (tenant isolation returns 404/403)
    outsider_resp = client.get(
        f"/api/v1/projects/{proj_id_str}/verification/queue",
        headers=outsider.headers,
    )
    assert outsider_resp.status_code in (403, 404)


def test_direct_finding_review_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test fast atomic POST /findings/{finding_id}/review endpoint."""
    with isolated_auth_app(monkeypatch) as ctx:
        with TestClient(ctx.app) as client:
            owner = register_and_login_user(client, email="direct_rev@example.com", full_name="Direct Reviewer")
            org_id_str, proj_id_str = _create_org_and_project(client, owner.headers, "vc-direct")
            org_id, proj_id = uuid.UUID(org_id_str), uuid.UUID(proj_id_str)

            with ctx.session_factory() as db:
                ev = _seed_evidence(db, org_id=org_id, project_id=proj_id, user_id=owner.user_id, title="Direct Doc")
                ki = _seed_knowledge_item(
                    db,
                    org_id=org_id,
                    project_id=proj_id,
                    title="Direct Knowledge Finding",
                    statement="Direct test statement.",
                    evidence=ev,
                )
                db.commit()
                ki_id_str = str(ki.id)

            # Direct approve
            res_approve = client.post(
                f"/api/v1/projects/{proj_id_str}/verification/findings/{ki_id_str}/review",
                headers=owner.headers,
                json={"action": "approve", "notes": "Approved via direct review"},
            )
            assert res_approve.status_code == 200
            assert res_approve.json()["case_status"] == "verified"

