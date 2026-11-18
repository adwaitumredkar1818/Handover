"""Verification Center & Conflict Management Security, RBAC, ACL, and E2E Integration Test Suite.

Module: Verification Center (Module 3 / Validation Area)
Migrated for Post-0020 Verification Center Rebuild & Conflict Management Architecture (DEF-10).

Coverage:
- Tier 1: Feature Coverage & E2E Lifecycle Testing (Sync/Assess -> Queue -> Detail -> Reviewer Actions -> Handover Eligibility Gate)
- Tier 2: Boundary & Corner Cases (Pagination, approval blockers, malformed UUIDs, unassignment, unauthorized context response, conflict states)
- Tier 3: Version Monotonicity & Audit Revision Diff Integrity (Original AI claim preservation, immutable audit events)
- Tier 4: Security, RBAC & Multi-Tenant Isolation (401 auth bar, suspended JWT, 403 member vs reviewer RBAC, 404/403 tenant isolation, fail-closed ACL masking)

Intentionally Retired Pre-0020 Legacy Tests (Documented per DEF-10):
- `test_tier3_occ_stale_expected_version_rejected_across_all_mutations`
- `test_tier3_occ_race_condition_simulation`
  Reason: Post-0020 Verification Center action schemas (`AssignReviewerRequest`, `EditFindingRequest`,
  `ApproveFindingRequest`, etc.) no longer accept client-supplied `expected_version` tokens.
  Optimistic concurrency control (`expected_version` / `expected_case_version` -> 409 Conflict)
  is actively tested on Handover mutations in `tests/test_handover_stage5_checklists_and_responsibilities.py`
  and `tests/test_handover_stage6_signoff_and_publication.py`.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.rbac_catalog import deterministic_rbac_id
from app.models.audit import AuditLog
from app.models.enums import (
    ConflictResolutionState,
    ConflictType,
    EpistemicStatus,
    EvidenceProcessingStatus,
    EvidenceSourceType,
    IntegrationProvider,
    IssueResolutionState,
    KnowledgeReviewStatus,
    OrganisationMembershipStatus,
    ProjectMembershipStatus,
    RoleName,
    SourcePermissionVerificationStatus,
    SourceVisibilityPolicy,
    TemporalComparison,
    UserStatus,
    VerificationCaseStatus,
    VerificationIssueType,
    VerificationPriority,
    VerificationSeverity,
    VerificationTargetType,
)
from app.models.evidence import EvidenceChunk, EvidenceItem
from app.models.integration import SourceAccessPolicy, SourceConnection
from app.models.knowledge import KnowledgeEvidenceLink, KnowledgeItem
from app.models.organisation import OrganisationMembership
from app.models.project import ProjectMembership
from app.models.relationship import (
    KnowledgeEntity,
    KnowledgeRelationship,
    RelationshipEvidenceLink,
)
from app.models.user import User
from app.models.verification import (
    VerificationCase,
    VerificationConflict,
    VerificationIssue,
)
from tests.conftest import (
    RegisteredUserSession,
    isolated_auth_app,
    register_and_login_user,
)


# ==============================================================================
# Test Fixture Helpers
# ==============================================================================


def _setup_org_and_project(
    client: TestClient,
    owner: RegisteredUserSession,
    *,
    org_name: str | None = None,
    proj_name: str | None = None,
    visibility: str = "private",
) -> tuple[str, str]:
    """Create test Organisation and Project via genuine authenticated API calls."""
    org_slug = uuid.uuid4().hex[:6]
    res_org = client.post(
        "/api/v1/organisations",
        headers=owner.headers,
        json={"name": org_name or f"E2E Org {org_slug}"},
    )
    assert res_org.status_code == 201, f"Failed org creation: {res_org.text}"
    org_id = res_org.json()["id"]

    proj_slug = uuid.uuid4().hex[:6]
    res_proj = client.post(
        f"/api/v1/organisations/{org_id}/projects",
        headers=owner.headers,
        json={"name": proj_name or f"E2E Project {proj_slug}", "visibility": visibility},
    )
    assert res_proj.status_code == 201, f"Failed project creation: {res_proj.text}"
    proj_id = res_proj.json()["id"]
    return org_id, proj_id


def _assign_member_role(
    session: Session,
    org_id: str,
    proj_id: str,
    user: RegisteredUserSession,
    role_name: RoleName = RoleName.PROJECT_MEMBER,
) -> None:
    """Add a user to an organisation and project with a deterministic RBAC role."""
    org_uuid = uuid.UUID(org_id)
    proj_uuid = uuid.UUID(proj_id)

    session.add(
        OrganisationMembership(
            id=uuid.uuid4(),
            organisation_id=org_uuid,
            user_id=user.user_id,
            role_id=deterministic_rbac_id("role", RoleName.ORG_MEMBER.value),
            status=OrganisationMembershipStatus.ACTIVE.value,
        )
    )
    session.add(
        ProjectMembership(
            id=uuid.uuid4(),
            project_id=proj_uuid,
            user_id=user.user_id,
            role_id=deterministic_rbac_id("role", role_name.value),
            status=ProjectMembershipStatus.ACTIVE.value,
        )
    )
    session.commit()


def _create_evidence_and_chunk(
    session: Session,
    org_id: str,
    proj_id: str,
    user_id: uuid.UUID,
    *,
    title: str = "System Architecture Document.pdf",
    chunk_text: str = "PostgreSQL is selected as the primary relational database with Alembic for migrations.",
    source_type: str = EvidenceSourceType.DOCUMENT_UPLOAD.value,
    acl_scope: str = "project_members",
    source_policy_id: uuid.UUID | None = None,
    source_created_at: datetime | None = None,
) -> tuple[EvidenceItem, EvidenceChunk]:
    """Create an EvidenceItem and its indexed EvidenceChunk."""
    org_uuid = uuid.UUID(org_id)
    proj_uuid = uuid.UUID(proj_id)
    content_hash = hashlib.sha256(f"{title}-{uuid.uuid4()}".encode()).hexdigest()

    ev = EvidenceItem(
        id=uuid.uuid4(),
        organisation_id=org_uuid,
        project_id=proj_uuid,
        uploaded_by_user_id=user_id,
        source_type=source_type,
        source_provider="local_upload",
        category="pdf_document",
        source_external_id=uuid.uuid4().hex,
        title=title,
        original_filename=title.lower().replace(" ", "_"),
        content_hash=content_hash,
        file_size_bytes=len(chunk_text.encode()),
        mime_type="application/pdf",
        source_created_at=source_created_at or datetime.now(UTC),
        processing_status=EvidenceProcessingStatus.EXTRACTED.value,
        acl_scope=acl_scope,
        source_access_policy_id=source_policy_id,
    )
    session.add(ev)
    session.flush()

    chunk_hash = hashlib.sha256(chunk_text.encode()).hexdigest()
    chunk = EvidenceChunk(
        id=uuid.uuid4(),
        organisation_id=org_uuid,
        project_id=proj_uuid,
        evidence_id=ev.id,
        chunk_index=0,
        chunk_type="text_segment",
        chunk_text=chunk_text,
        chunk_content_hash=chunk_hash,
        char_start=0,
        char_end=len(chunk_text),
        char_count=len(chunk_text),
        token_estimate=max(1, len(chunk_text) // 4),
        source_type=ev.source_type,
        indexing_status="indexed",
    )
    session.add(chunk)
    session.flush()
    return ev, chunk


def _create_knowledge_item_and_link(
    session: Session,
    org_id: str,
    proj_id: str,
    ev: EvidenceItem,
    chunk: EvidenceChunk,
    *,
    title: str = "Database Engine Selection",
    summary: str = "PostgreSQL is selected as the primary relational persistence store.",
    supporting_excerpt: str = "PostgreSQL is selected as the primary relational database",
    domain: str = "technical_architecture",
    category: str = "technical_architecture",
    epistemic_status: str = EpistemicStatus.EXTRACTED.value,
    review_status: str = KnowledgeReviewStatus.PENDING_REVIEW.value,
) -> tuple[KnowledgeItem, KnowledgeEvidenceLink]:
    """Create a KnowledgeItem grounded by an EvidenceChunk link."""
    org_uuid = uuid.UUID(org_id)
    proj_uuid = uuid.UUID(proj_id)

    item = KnowledgeItem(
        id=uuid.uuid4(),
        organisation_id=org_uuid,
        project_id=proj_uuid,
        category=category,
        primary_domain=domain,
        title=title,
        structured_summary=summary,
        structured_payload={"database": "PostgreSQL", "migrations": "Alembic"},
        support_classification="direct",
        extraction_model="qwen3:8b",
        prompt_version="1.0.0",
        fingerprint=uuid.uuid4().hex,
        epistemic_status=epistemic_status,
        review_status=review_status,
    )
    session.add(item)
    session.flush()

    link = KnowledgeEvidenceLink(
        id=uuid.uuid4(),
        organisation_id=org_uuid,
        project_id=proj_uuid,
        knowledge_item_id=item.id,
        evidence_id=ev.id,
        evidence_chunk_id=chunk.id,
        support_type="direct",
        supporting_excerpt=supporting_excerpt,
        excerpt_verified=True,
    )
    session.add(link)
    session.flush()
    return item, link


def _create_relationship_with_evidence(
    session: Session,
    org_id: str,
    proj_id: str,
    ev: EvidenceItem,
    chunk: EvidenceChunk,
    *,
    source_name: str = "API Gateway",
    target_name: str = "Auth Service",
    rel_type: str = "depends_on",
    supporting_excerpt: str = "API Gateway delegates all token verification to Auth Service.",
) -> tuple[KnowledgeRelationship, RelationshipEvidenceLink]:
    """Create KnowledgeEntities, a KnowledgeRelationship, and a grounding citation."""
    org_uuid = uuid.UUID(org_id)
    proj_uuid = uuid.UUID(proj_id)

    src_entity = KnowledgeEntity(
        id=uuid.uuid4(),
        organisation_id=org_uuid,
        project_id=proj_uuid,
        entity_type="microservice",
        canonical_name=source_name,
        normalized_name=source_name.lower().replace(" ", "_"),
    )
    tgt_entity = KnowledgeEntity(
        id=uuid.uuid4(),
        organisation_id=org_uuid,
        project_id=proj_uuid,
        entity_type="microservice",
        canonical_name=target_name,
        normalized_name=target_name.lower().replace(" ", "_"),
    )
    session.add_all([src_entity, tgt_entity])
    session.flush()

    rel = KnowledgeRelationship(
        id=uuid.uuid4(),
        organisation_id=org_uuid,
        project_id=proj_uuid,
        source_entity_id=src_entity.id,
        target_entity_id=tgt_entity.id,
        relationship_type=rel_type,
        relationship_basis="explicit",
        fingerprint=uuid.uuid4().hex,
        confidence_score=0.98,
    )
    session.add(rel)
    session.flush()

    link = RelationshipEvidenceLink(
        id=uuid.uuid4(),
        organisation_id=org_uuid,
        project_id=proj_uuid,
        relationship_id=rel.id,
        evidence_id=ev.id,
        evidence_chunk_id=chunk.id,
        evidence_role="direct_support",
        supporting_excerpt=supporting_excerpt,
        source_location_json={"section": "architecture_overview"},
    )
    session.add(link)
    session.flush()
    return rel, link


def _sync_and_get_case_id(
    client: TestClient,
    proj_id: str,
    headers: dict[str, str],
    target_id: str,
) -> str:
    """Sync & assess verification cases via current post-0020 API and locate the case for target_id."""
    res_sync = client.post(f"/api/v1/projects/{proj_id}/verification/sync", headers=headers)
    assert res_sync.status_code == 200, res_sync.text
    res_q = client.get(f"/api/v1/projects/{proj_id}/verification/queue?limit=50", headers=headers)
    assert res_q.status_code == 200, res_q.text
    for item in res_q.json()["items"]:
        if item["target_id"] == target_id:
            return str(item["id"])
    raise AssertionError(f"Verification case for target {target_id} not found in queue.")


# ==============================================================================
# TIER 1: Feature Coverage & E2E Lifecycle Testing
# ==============================================================================


def test_tier1_full_verification_lifecycle_e2e(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tier 1: Full post-0020 verification lifecycle from sync to handover eligibility gate."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        owner = register_and_login_user(client, email="tier1-owner@example.com", full_name="Owner User")
        reviewer = register_and_login_user(client, email="tier1-reviewer@example.com", full_name="Lead Reviewer")
        author = register_and_login_user(client, email="tier1-author@example.com", full_name="Departing Author")
        org_id, proj_id = _setup_org_and_project(client, owner)

        with ctx.session_factory() as session:
            _assign_member_role(session, org_id, proj_id, reviewer, RoleName.REVIEWER)
            _assign_member_role(session, org_id, proj_id, author, RoleName.PROJECT_MEMBER)
            ev, chunk = _create_evidence_and_chunk(
                session,
                org_id,
                proj_id,
                owner.user_id,
                title="Service Communication RFC.pdf",
                chunk_text="All microservices communicate via gRPC over HTTP/2 with mutual TLS enabled.",
            )
            item, _ = _create_knowledge_item_and_link(
                session,
                org_id,
                proj_id,
                ev,
                chunk,
                title="Inter-Service Protocol",
                summary="Microservices communicate via gRPC over HTTP/2.",
                supporting_excerpt="All microservices communicate via gRPC over HTTP/2",
            )
            session.commit()
            item_id = str(item.id)

        # Sync & assess -> locate case
        case_id = _sync_and_get_case_id(client, proj_id, reviewer.headers, item_id)

        # Summary & Detail with embedded evidence references
        res_sum = client.get(f"/api/v1/projects/{proj_id}/verification/summary", headers=reviewer.headers)
        assert res_sum.status_code == 200
        assert res_sum.json()["total_cases"] >= 1

        res_detail = client.get(f"/api/v1/projects/{proj_id}/verification/cases/{case_id}", headers=reviewer.headers)
        assert res_detail.status_code == 200
        detail = res_detail.json()
        assert detail["title"] == "Inter-Service Protocol"
        assert detail["handover_eligible"] is False
        assert detail["restricted_evidence_count"] == 0
        assert len(detail["evidence_references"]) >= 1
        assert "gRPC" in (detail["evidence_references"][0]["excerpt"] or "")

        # Handover eligibility gate BEFORE approval -> fails closed
        res_elig_pre = client.get(
            f"/api/v1/projects/{proj_id}/handover/eligibility/knowledge_item/{item_id}",
            headers=reviewer.headers,
        )
        assert res_elig_pre.status_code == 200
        assert res_elig_pre.json()["is_eligible"] is False

        # Assign -> Edit -> Request context -> Author responds -> Unassign -> Mark unresolved -> Approve
        res_assign = client.post(
            f"/api/v1/projects/{proj_id}/verification/cases/{case_id}/assign",
            headers=reviewer.headers,
            json={"assigned_reviewer_id": str(reviewer.user_id)},
        )
        assert res_assign.status_code == 200
        assert res_assign.json()["assigned_reviewer_id"] == str(reviewer.user_id)

        res_edit = client.patch(
            f"/api/v1/projects/{proj_id}/verification/cases/{case_id}/finding",
            headers=reviewer.headers,
            json={
                "current_claim": "Microservices communicate via gRPC over HTTP/2 with mandatory mutual TLS.",
                "edit_reason": "Clarified mutual TLS requirement",
            },
        )
        assert res_edit.status_code == 200
        assert "mandatory mutual TLS" in res_edit.json()["current_claim"]
        assert len(res_edit.json()["revisions"]) >= 1

        res_req = client.post(
            f"/api/v1/projects/{proj_id}/verification/cases/{case_id}/request-context",
            headers=reviewer.headers,
            json={
                "question": "Which certificate authority issues mTLS certs?",
                "requested_from_user_id": str(author.user_id),
            },
        )
        assert res_req.status_code == 200
        req_id = res_req.json()["context_requests"][0]["id"]

        res_resp = client.post(
            f"/api/v1/projects/{proj_id}/verification/context-requests/{req_id}/respond",
            headers=author.headers,
            json={"response_text": "Internal HashiCorp Vault PKI issues short-lived mTLS certs."},
        )
        assert res_resp.status_code == 200
        assert res_resp.json()["status"] == "responded"

        res_unassign = client.post(
            f"/api/v1/projects/{proj_id}/verification/cases/{case_id}/assign",
            headers=reviewer.headers,
            json={"assigned_reviewer_id": None},
        )
        assert res_unassign.status_code == 200
        assert res_unassign.json()["assigned_reviewer_id"] is None

        res_unres = client.post(
            f"/api/v1/projects/{proj_id}/verification/cases/{case_id}/mark-unresolved",
            headers=reviewer.headers,
            json={"decision_reason": "Pending final mTLS verification"},
        )
        assert res_unres.status_code == 200
        assert res_unres.json()["case_status"] == VerificationCaseStatus.UNRESOLVED.value

        res_approve = client.post(
            f"/api/v1/projects/{proj_id}/verification/cases/{case_id}/approve",
            headers=reviewer.headers,
            json={"reviewer_note": "Confirmed against Service Communication RFC."},
        )
        assert res_approve.status_code == 200
        assert res_approve.json()["case_status"] == VerificationCaseStatus.VERIFIED.value
        assert res_approve.json()["handover_eligible"] is True

        # Handover eligibility gate AFTER approval -> passes
        res_elig_post = client.get(
            f"/api/v1/projects/{proj_id}/handover/eligibility/knowledge_item/{item_id}",
            headers=reviewer.headers,
        )
        assert res_elig_post.status_code == 200
        assert res_elig_post.json()["is_eligible"] is True


def test_tier1_rejection_workflow_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tier 1: Reject finding with mandatory reason -> excluded from handover eligibility."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        owner = register_and_login_user(client, email="rej-owner@example.com", full_name="Owner")
        reviewer = register_and_login_user(client, email="rej-rev@example.com", full_name="Reviewer")
        org_id, proj_id = _setup_org_and_project(client, owner)

        with ctx.session_factory() as session:
            _assign_member_role(session, org_id, proj_id, reviewer, RoleName.REVIEWER)
            ev, chunk = _create_evidence_and_chunk(session, org_id, proj_id, owner.user_id)
            item, _ = _create_knowledge_item_and_link(session, org_id, proj_id, ev, chunk)
            session.commit()
            item_id = str(item.id)

        case_id = _sync_and_get_case_id(client, proj_id, reviewer.headers, item_id)

        # Reject without valid reason fails validation (422)
        res_bad = client.post(
            f"/api/v1/projects/{proj_id}/verification/cases/{case_id}/reject",
            headers=reviewer.headers,
            json={"decision_reason": "  "},
        )
        assert res_bad.status_code == 422

        res_rej = client.post(
            f"/api/v1/projects/{proj_id}/verification/cases/{case_id}/reject",
            headers=reviewer.headers,
            json={"decision_reason": "Contradicted by current production deployment."},
        )
        assert res_rej.status_code == 200
        assert res_rej.json()["case_status"] == VerificationCaseStatus.REJECTED.value
        assert res_rej.json()["handover_eligible"] is False

        res_elig = client.get(
            f"/api/v1/projects/{proj_id}/handover/eligibility/knowledge_item/{item_id}",
            headers=reviewer.headers,
        )
        assert res_elig.status_code == 200
        assert res_elig.json()["is_eligible"] is False


def test_tier1_conflict_lifecycle_and_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tier 1: Conflict resolution & reopening via Conflict Management API updates verification case safely."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        owner = register_and_login_user(client, email="conf-owner@example.com", full_name="Owner")
        org_id, proj_id = _setup_org_and_project(client, owner)

        with ctx.session_factory() as session:
            ev_a, chunk_a = _create_evidence_and_chunk(
                session, org_id, proj_id, owner.user_id, title="ADR-1.md", chunk_text="Uses PostgreSQL."
            )
            ev_b, chunk_b = _create_evidence_and_chunk(
                session, org_id, proj_id, owner.user_id, title="Notes.md", chunk_text="Uses MongoDB."
            )
            item, _ = _create_knowledge_item_and_link(session, org_id, proj_id, ev_a, chunk_a)
            session.commit()
            item_id = str(item.id)
            ev_a_id, ev_b_id = ev_a.id, ev_b.id

        case_id = _sync_and_get_case_id(client, proj_id, owner.headers, item_id)

        with ctx.session_factory() as session:
            vc = session.get(VerificationCase, uuid.UUID(case_id))
            assert vc is not None
            vc.case_status = VerificationCaseStatus.CONFLICTED.value
            cf = VerificationConflict(
                id=uuid.uuid4(),
                organisation_id=uuid.UUID(org_id),
                project_id=uuid.UUID(proj_id),
                case_id=vc.id,
                conflict_type=ConflictType.DECISION_CONFLICT.value,
                claim_a_text="Uses PostgreSQL.",
                claim_a_source_evidence_id=ev_a_id,
                claim_b_text="Uses MongoDB.",
                claim_b_source_evidence_id=ev_b_id,
                explanation="Conflicting database specs.",
                temporal_comparison=TemporalComparison.SIMULTANEOUS.value,
                resolution_state=ConflictResolutionState.UNRESOLVED.value,
                priority="high",
            )
            session.add(cf)
            session.commit()
            conflict_id = str(cf.id)

        res_resolve = client.post(
            f"/api/v1/projects/{proj_id}/conflicts/{conflict_id}/resolve",
            headers=owner.headers,
            json={
                "resolution_strategy": "claim_a_authoritative",
                "resolution_notes": "ADR-1 PostgreSQL is authoritative.",
                "authoritative_claim_text": "Uses PostgreSQL.",
                "sync_finding": True,
            },
        )
        assert res_resolve.status_code == 200
        assert res_resolve.json()["resolution_state"] == ConflictResolutionState.RECONCILED.value

        # Case returned to pending_review (never auto-verified!)
        res_case = client.get(f"/api/v1/projects/{proj_id}/verification/cases/{case_id}", headers=owner.headers)
        assert res_case.json()["case_status"] == VerificationCaseStatus.PENDING_REVIEW.value

        # Reopen restores conflicted state
        res_reopen = client.post(
            f"/api/v1/projects/{proj_id}/conflicts/{conflict_id}/reopen",
            headers=owner.headers,
            json={"reason": "New contradictory architecture note found."},
        )
        assert res_reopen.status_code == 200
        assert res_reopen.json()["resolution_state"] == ConflictResolutionState.REOPENED.value


def test_tier1_relationship_target_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tier 1: Relationship target synced, reviewed, approved, and passes handover eligibility."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        owner = register_and_login_user(client, email="rel-owner@example.com", full_name="Owner")
        reviewer = register_and_login_user(client, email="rel-rev@example.com", full_name="Reviewer")
        org_id, proj_id = _setup_org_and_project(client, owner)

        with ctx.session_factory() as session:
            _assign_member_role(session, org_id, proj_id, reviewer, RoleName.REVIEWER)
            ev, chunk = _create_evidence_and_chunk(session, org_id, proj_id, owner.user_id)
            rel, _ = _create_relationship_with_evidence(session, org_id, proj_id, ev, chunk)
            session.commit()
            rel_id = str(rel.id)

        case_id = _sync_and_get_case_id(client, proj_id, reviewer.headers, rel_id)

        res_approve = client.post(
            f"/api/v1/projects/{proj_id}/verification/cases/{case_id}/approve",
            headers=reviewer.headers,
            json={"reviewer_note": "Verified dependency edge."},
        )
        assert res_approve.status_code == 200
        assert res_approve.json()["case_status"] == VerificationCaseStatus.VERIFIED.value

        res_elig = client.get(
            f"/api/v1/projects/{proj_id}/handover/eligibility/relationship/{rel_id}",
            headers=reviewer.headers,
        )
        assert res_elig.status_code == 200
        assert res_elig.json()["is_eligible"] is True


# ==============================================================================
# TIER 2: Boundary & Corner Cases
# ==============================================================================


def test_tier2_approval_blocked_by_open_critical_issue(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tier 2: Open CRITICAL VerificationIssue blocks handover eligibility even on an approved item."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        owner = register_and_login_user(client, email="crit-owner@example.com", full_name="Owner")
        reviewer = register_and_login_user(client, email="crit-rev@example.com", full_name="Reviewer")
        org_id, proj_id = _setup_org_and_project(client, owner)

        with ctx.session_factory() as session:
            _assign_member_role(session, org_id, proj_id, reviewer, RoleName.REVIEWER)
            ev, chunk = _create_evidence_and_chunk(session, org_id, proj_id, owner.user_id)
            item, _ = _create_knowledge_item_and_link(session, org_id, proj_id, ev, chunk)
            session.commit()
            item_id = str(item.id)

        case_id = _sync_and_get_case_id(client, proj_id, reviewer.headers, item_id)
        client.post(
            f"/api/v1/projects/{proj_id}/verification/cases/{case_id}/approve",
            headers=reviewer.headers,
            json={"reviewer_note": "Initial approval"},
        )

        with ctx.session_factory() as session:
            session.add(
                VerificationIssue(
                    id=uuid.uuid4(),
                    organisation_id=uuid.UUID(org_id),
                    project_id=uuid.UUID(proj_id),
                    case_id=uuid.UUID(case_id),
                    issue_type=VerificationIssueType.CONFLICTING_SOURCES.value,
                    severity=VerificationSeverity.CRITICAL.value,
                    description="Critical open integrity issue.",
                    detection_method="deterministic_rule",
                    resolution_state=IssueResolutionState.OPEN.value,
                )
            )
            session.commit()

        res_elig = client.get(
            f"/api/v1/projects/{proj_id}/handover/eligibility/knowledge_item/{item_id}",
            headers=reviewer.headers,
        )
        assert res_elig.status_code == 200
        assert res_elig.json()["is_eligible"] is False
        assert any("blocking issues" in b.lower() for b in res_elig.json()["blockers"])


def test_tier2_approval_blocked_by_open_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tier 2: Approving a conflicted case without rationale fails 422 and open conflict blocks handover eligibility."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        owner = register_and_login_user(client, email="oc-owner@example.com", full_name="Owner")
        reviewer = register_and_login_user(client, email="oc-rev@example.com", full_name="Reviewer")
        org_id, proj_id = _setup_org_and_project(client, owner)

        with ctx.session_factory() as session:
            _assign_member_role(session, org_id, proj_id, reviewer, RoleName.REVIEWER)
            ev, chunk = _create_evidence_and_chunk(session, org_id, proj_id, owner.user_id)
            item, _ = _create_knowledge_item_and_link(session, org_id, proj_id, ev, chunk)
            session.commit()
            item_id = str(item.id)
            ev_id = ev.id

        case_id = _sync_and_get_case_id(client, proj_id, reviewer.headers, item_id)
        with ctx.session_factory() as session:
            vc = session.get(VerificationCase, uuid.UUID(case_id))
            assert vc is not None
            vc.case_status = VerificationCaseStatus.CONFLICTED.value
            session.add(
                VerificationConflict(
                    id=uuid.uuid4(),
                    organisation_id=uuid.UUID(org_id),
                    project_id=uuid.UUID(proj_id),
                    case_id=vc.id,
                    conflict_type=ConflictType.DECISION_CONFLICT.value,
                    claim_a_text="Claim A",
                    claim_a_source_evidence_id=ev_id,
                    claim_b_text="Claim B",
                    claim_b_source_evidence_id=ev_id,
                    explanation="Unresolved contradiction.",
                    temporal_comparison=TemporalComparison.AMBIGUOUS.value,
                    resolution_state=ConflictResolutionState.UNRESOLVED.value,
                )
            )
            session.commit()

        # Approving conflicted finding without mandatory note/reason fails 422
        res_no_note = client.post(
            f"/api/v1/projects/{proj_id}/verification/cases/{case_id}/approve",
            headers=reviewer.headers,
            json={},
        )
        assert res_no_note.status_code == 422

        # Handover eligibility remains blocked while unresolved conflict exists
        res_elig = client.get(
            f"/api/v1/projects/{proj_id}/handover/eligibility/knowledge_item/{item_id}",
            headers=reviewer.headers,
        )
        assert res_elig.status_code == 200
        assert res_elig.json()["is_eligible"] is False


def test_tier2_non_existent_and_malformed_uuids(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tier 2: Missing and malformed UUIDs return 404/422 cleanly."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        owner = register_and_login_user(client, email="uuid-owner@example.com", full_name="Owner")
        _, proj_id = _setup_org_and_project(client, owner)

        res_404 = client.get(
            f"/api/v1/projects/{proj_id}/verification/cases/{uuid.uuid4()}",
            headers=owner.headers,
        )
        assert res_404.status_code == 404

        res_422 = client.get(
            f"/api/v1/projects/{proj_id}/verification/cases/not-a-valid-uuid",
            headers=owner.headers,
        )
        assert res_422.status_code == 422


def test_tier2_pagination_boundary_cases(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tier 2: Queue limit/offset boundaries enforce bounds (422) and empty out-of-range pages."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        owner = register_and_login_user(client, email="pag-owner@example.com", full_name="Owner")
        _, proj_id = _setup_org_and_project(client, owner)

        assert client.get(
            f"/api/v1/projects/{proj_id}/verification/queue?limit=0", headers=owner.headers
        ).status_code == 422
        assert client.get(
            f"/api/v1/projects/{proj_id}/verification/queue?limit=500", headers=owner.headers
        ).status_code == 422
        res_far = client.get(
            f"/api/v1/projects/{proj_id}/verification/queue?limit=10&offset=9999",
            headers=owner.headers,
        )
        assert res_far.status_code == 200
        assert res_far.json()["items"] == []


def test_tier2_reviewer_assignment_and_unassignment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tier 2: Reviewer can be assigned and explicitly unassigned with assigned_reviewer_id: null."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        owner = register_and_login_user(client, email="asgn-owner@example.com", full_name="Owner")
        reviewer = register_and_login_user(client, email="asgn-rev@example.com", full_name="Reviewer")
        org_id, proj_id = _setup_org_and_project(client, owner)

        with ctx.session_factory() as session:
            _assign_member_role(session, org_id, proj_id, reviewer, RoleName.REVIEWER)
            ev, chunk = _create_evidence_and_chunk(session, org_id, proj_id, owner.user_id)
            item, _ = _create_knowledge_item_and_link(session, org_id, proj_id, ev, chunk)
            session.commit()
            item_id = str(item.id)

        case_id = _sync_and_get_case_id(client, proj_id, reviewer.headers, item_id)

        r1 = client.post(
            f"/api/v1/projects/{proj_id}/verification/cases/{case_id}/assign",
            headers=reviewer.headers,
            json={"assigned_reviewer_id": str(reviewer.user_id)},
        )
        assert r1.status_code == 200
        assert r1.json()["assigned_reviewer_id"] == str(reviewer.user_id)

        r2 = client.post(
            f"/api/v1/projects/{proj_id}/verification/cases/{case_id}/assign",
            headers=reviewer.headers,
            json={"assigned_reviewer_id": None},
        )
        assert r2.status_code == 200
        assert r2.json()["assigned_reviewer_id"] is None


def test_tier2_context_response_unauthorized_actor(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tier 2: Third-party member who was NOT asked for context is rejected with 403."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        owner = register_and_login_user(client, email="ctx-owner@example.com", full_name="Owner")
        reviewer = register_and_login_user(client, email="ctx-rev@example.com", full_name="Reviewer")
        target_member = register_and_login_user(client, email="ctx-target@example.com", full_name="Target Member")
        other_member = register_and_login_user(client, email="ctx-other@example.com", full_name="Other Member")
        org_id, proj_id = _setup_org_and_project(client, owner)

        with ctx.session_factory() as session:
            _assign_member_role(session, org_id, proj_id, reviewer, RoleName.REVIEWER)
            _assign_member_role(session, org_id, proj_id, target_member, RoleName.PROJECT_MEMBER)
            _assign_member_role(session, org_id, proj_id, other_member, RoleName.PROJECT_MEMBER)
            ev, chunk = _create_evidence_and_chunk(session, org_id, proj_id, owner.user_id)
            item, _ = _create_knowledge_item_and_link(session, org_id, proj_id, ev, chunk)
            session.commit()
            item_id = str(item.id)

        case_id = _sync_and_get_case_id(client, proj_id, reviewer.headers, item_id)
        res_req = client.post(
            f"/api/v1/projects/{proj_id}/verification/cases/{case_id}/request-context",
            headers=reviewer.headers,
            json={
                "question": "Please confirm deployment port.",
                "requested_from_user_id": str(target_member.user_id),
            },
        )
        assert res_req.status_code == 200
        req_id = res_req.json()["context_requests"][0]["id"]

        res_unauth_resp = client.post(
            f"/api/v1/projects/{proj_id}/verification/context-requests/{req_id}/respond",
            headers=other_member.headers,
            json={"response_text": "Unauthorized answer attempt."},
        )
        assert res_unauth_resp.status_code == 403


def test_tier2_conflict_resolution_invalid_target(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tier 2: Resolving non-existent conflict returns 404; member without project.manage gets 403."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        owner = register_and_login_user(client, email="cfinv-owner@example.com", full_name="Owner")
        member = register_and_login_user(client, email="cfinv-mem@example.com", full_name="Member")
        org_id, proj_id = _setup_org_and_project(client, owner)
        with ctx.session_factory() as session:
            _assign_member_role(session, org_id, proj_id, member, RoleName.PROJECT_MEMBER)

        res_404 = client.post(
            f"/api/v1/projects/{proj_id}/conflicts/{uuid.uuid4()}/resolve",
            headers=owner.headers,
            json={"resolution_strategy": "claim_a_authoritative", "resolution_notes": "Notes"},
        )
        assert res_404.status_code == 404

        res_403 = client.post(
            f"/api/v1/projects/{proj_id}/conflicts/{uuid.uuid4()}/resolve",
            headers=member.headers,
            json={"resolution_strategy": "claim_a_authoritative", "resolution_notes": "Notes"},
        )
        assert res_403.status_code == 403


# ==============================================================================
# TIER 3: Version Monotonicity & Audit Revision Diff Integrity
# ==============================================================================


def test_tier3_audit_diff_snapshot_and_version_monotonicity(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tier 3: Editing a finding increments version, preserves original_ai_claim, records revision diff & immutable audit log."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        owner = register_and_login_user(client, email="aud-owner@example.com", full_name="Owner")
        reviewer = register_and_login_user(client, email="aud-rev@example.com", full_name="Reviewer")
        org_id, proj_id = _setup_org_and_project(client, owner)

        with ctx.session_factory() as session:
            _assign_member_role(session, org_id, proj_id, reviewer, RoleName.REVIEWER)
            ev, chunk = _create_evidence_and_chunk(session, org_id, proj_id, owner.user_id)
            item, _ = _create_knowledge_item_and_link(
                session,
                org_id,
                proj_id,
                ev,
                chunk,
                summary="Original AI statement about PostgreSQL.",
            )
            session.commit()
            item_id = str(item.id)

        case_id = _sync_and_get_case_id(client, proj_id, reviewer.headers, item_id)
        d0 = client.get(f"/api/v1/projects/{proj_id}/verification/cases/{case_id}", headers=reviewer.headers).json()
        v0 = d0["version"]

        res_edit = client.patch(
            f"/api/v1/projects/{proj_id}/verification/cases/{case_id}/finding",
            headers=reviewer.headers,
            json={
                "current_claim": "Human-corrected PostgreSQL 16 canonical architecture statement.",
                "edit_reason": "Specified exact PostgreSQL version",
            },
        )
        assert res_edit.status_code == 200
        d1 = res_edit.json()
        assert d1["version"] > v0
        assert "Original AI statement" in d1["original_ai_claim"]
        assert "Human-corrected PostgreSQL 16" in d1["current_claim"]
        assert len(d1["revisions"]) == 2
        assert any(
            r["is_ai_original"] is True and "Original AI statement" in r["claim_text"]
            for r in d1["revisions"]
        )
        assert any(
            r["is_ai_original"] is False and "Human-corrected PostgreSQL 16" in r["claim_text"]
            for r in d1["revisions"]
        )

        with ctx.session_factory() as session:
            audits = list(
                session.execute(
                    select(AuditLog).where(
                        AuditLog.project_id == uuid.UUID(proj_id),
                        AuditLog.event_type == "verification.case.edited",
                    )
                )
                .scalars()
                .all()
            )
            assert len(audits) == 1


# ==============================================================================
# TIER 4: Security, RBAC & Multi-Tenant Isolation
# ==============================================================================


def test_tier4_unauthenticated_requests_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tier 4: Unauthenticated requests to verification & conflict routes return 401."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        fake_proj = uuid.uuid4()
        fake_case = uuid.uuid4()
        assert client.get(f"/api/v1/projects/{fake_proj}/verification/summary").status_code == 401
        assert client.get(f"/api/v1/projects/{fake_proj}/verification/queue").status_code == 401
        assert client.post(f"/api/v1/projects/{fake_proj}/verification/cases/{fake_case}/approve", json={}).status_code == 401
        assert client.get(f"/api/v1/projects/{fake_proj}/conflicts").status_code == 401


def test_tier4_invalid_or_suspended_jwt_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tier 4: Malformed JWTs and disabled users are blocked (401/403)."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        owner = register_and_login_user(client, email="susp-owner@example.com", full_name="Owner")
        _, proj_id = _setup_org_and_project(client, owner)

        assert client.get(
            f"/api/v1/projects/{proj_id}/verification/summary",
            headers={"Authorization": "Bearer invalid.jwt.token"},
        ).status_code == 401

        with ctx.session_factory() as session:
            u = session.get(User, owner.user_id)
            assert u is not None
            u.status = UserStatus.DISABLED.value
            session.commit()

        assert client.get(
            f"/api/v1/projects/{proj_id}/verification/summary",
            headers=owner.headers,
        ).status_code in (401, 403)


def test_tier4_rbac_member_read_only_and_reviewer_mutations(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tier 4: PROJECT_MEMBER can read verification queue/detail but gets 403 on all reviewer mutations."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        owner = register_and_login_user(client, email="rbac-owner@example.com", full_name="Owner")
        reviewer = register_and_login_user(client, email="rbac-rev@example.com", full_name="Reviewer")
        member = register_and_login_user(client, email="rbac-mem@example.com", full_name="Member")
        org_id, proj_id = _setup_org_and_project(client, owner)

        with ctx.session_factory() as session:
            _assign_member_role(session, org_id, proj_id, reviewer, RoleName.REVIEWER)
            _assign_member_role(session, org_id, proj_id, member, RoleName.PROJECT_MEMBER)
            ev, chunk = _create_evidence_and_chunk(session, org_id, proj_id, owner.user_id)
            item, _ = _create_knowledge_item_and_link(session, org_id, proj_id, ev, chunk)
            session.commit()
            item_id = str(item.id)

        case_id = _sync_and_get_case_id(client, proj_id, reviewer.headers, item_id)

        # Member CAN read
        assert client.get(f"/api/v1/projects/{proj_id}/verification/summary", headers=member.headers).status_code == 200
        assert client.get(f"/api/v1/projects/{proj_id}/verification/queue", headers=member.headers).status_code == 200
        assert client.get(f"/api/v1/projects/{proj_id}/verification/cases/{case_id}", headers=member.headers).status_code == 200

        # Member CANNOT mutate (403 across all review endpoints)
        assert client.post(f"/api/v1/projects/{proj_id}/verification/sync", headers=member.headers).status_code == 403
        assert client.post(f"/api/v1/projects/{proj_id}/verification/assess", headers=member.headers).status_code == 403
        assert client.post(
            f"/api/v1/projects/{proj_id}/verification/cases/{case_id}/approve",
            headers=member.headers,
            json={"reviewer_note": "Unauthorized"},
        ).status_code == 403
        assert client.post(
            f"/api/v1/projects/{proj_id}/verification/cases/{case_id}/reject",
            headers=member.headers,
            json={"decision_reason": "Unauthorized"},
        ).status_code == 403
        assert client.patch(
            f"/api/v1/projects/{proj_id}/verification/cases/{case_id}/finding",
            headers=member.headers,
            json={"current_claim": "Tampered", "edit_reason": "Unauthorized"},
        ).status_code == 403
        assert client.post(
            f"/api/v1/projects/{proj_id}/verification/cases/{case_id}/assign",
            headers=member.headers,
            json={"assigned_reviewer_id": str(member.user_id)},
        ).status_code == 403

        # Reviewer CAN approve
        assert client.post(
            f"/api/v1/projects/{proj_id}/verification/cases/{case_id}/approve",
            headers=reviewer.headers,
            json={"reviewer_note": "Authorized reviewer approval"},
        ).status_code == 200


def test_tier4_cross_project_and_cross_tenant_isolation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tier 4: Users in Org B / Project B cannot access Project A verification cases, conflicts, or eligibility."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        owner_a = register_and_login_user(client, email="iso-a@example.com", full_name="Owner A")
        owner_b = register_and_login_user(client, email="iso-b@example.com", full_name="Owner B")
        org_a, proj_a = _setup_org_and_project(client, owner_a, org_name="Org A", proj_name="Proj A")
        _, proj_b = _setup_org_and_project(client, owner_b, org_name="Org B", proj_name="Proj B")

        with ctx.session_factory() as session:
            ev, chunk = _create_evidence_and_chunk(session, org_a, proj_a, owner_a.user_id)
            item, _ = _create_knowledge_item_and_link(session, org_a, proj_a, ev, chunk)
            session.commit()
            item_a_id = str(item.id)

        case_a_id = _sync_and_get_case_id(client, proj_a, owner_a.headers, item_a_id)

        # Owner B querying Project A directly -> 403/404
        assert client.get(f"/api/v1/projects/{proj_a}/verification/queue", headers=owner_b.headers).status_code in (403, 404)
        assert client.get(f"/api/v1/projects/{proj_a}/verification/cases/{case_a_id}", headers=owner_b.headers).status_code in (403, 404)

        # Owner B probing Case A or Item A through Project B URL -> 404 (no IDOR!)
        assert client.get(f"/api/v1/projects/{proj_b}/verification/cases/{case_a_id}", headers=owner_b.headers).status_code == 404
        assert client.get(
            f"/api/v1/projects/{proj_b}/handover/eligibility/knowledge_item/{item_a_id}",
            headers=owner_b.headers,
        ).status_code == 404


def test_tier4_fail_closed_evidence_acl_masking_and_eligibility(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tier 4: Revoked/restricted SourceAccessPolicy masks evidence excerpts in case detail and fails closed in eligibility."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        owner = register_and_login_user(client, email="acl-owner@example.com", full_name="Owner")
        reviewer = register_and_login_user(client, email="acl-rev@example.com", full_name="Reviewer")
        org_id, proj_id = _setup_org_and_project(client, owner)

        with ctx.session_factory() as session:
            _assign_member_role(session, org_id, proj_id, reviewer, RoleName.REVIEWER)
            conn = SourceConnection(
                id=uuid.uuid4(),
                organisation_id=uuid.UUID(org_id),
                created_by_user_id=owner.user_id,
                provider=IntegrationProvider.GITHUB.value,
                display_name="Revoked GitHub",
                external_workspace_id="gh-revoked-1",
                status="disconnected",
            )
            session.add(conn)
            session.flush()
            revoked_policy = SourceAccessPolicy(
                id=uuid.uuid4(),
                organisation_id=uuid.UUID(org_id),
                project_id=uuid.UUID(proj_id),
                source_connection_id=conn.id,
                provider=IntegrationProvider.GITHUB.value,
                scope_identifier="org/secret-vault-repo",
                visibility_policy=SourceVisibilityPolicy.EXPLICIT_USER_GRANTS.value,
                sync_permission_status=SourcePermissionVerificationStatus.REVOKED.value,
                authorised_by_user_id=owner.user_id,
                allowed_user_ids=[str(owner.user_id)],
            )
            session.add(revoked_policy)
            session.flush()

            ev_revoked, chunk_revoked = _create_evidence_and_chunk(
                session,
                org_id,
                proj_id,
                owner.user_id,
                title="Secret Credentials Policy.pdf",
                chunk_text="Root database password is stored in HashiCorp Vault path secret/db.",
                source_type=EvidenceSourceType.GITHUB.value,
                acl_scope="source_restricted",
                source_policy_id=revoked_policy.id,
            )
            item_revoked, _ = _create_knowledge_item_and_link(
                session,
                org_id,
                proj_id,
                ev_revoked,
                chunk_revoked,
                title="Database Credential Rotation",
                summary="Database credentials managed via Vault.",
                supporting_excerpt="HashiCorp Vault path secret/db",
                epistemic_status=EpistemicStatus.HUMAN_VERIFIED.value,
                review_status=KnowledgeReviewStatus.APPROVED.value,
            )
            session.commit()
            item_id = str(item_revoked.id)

        # Sync verification cases; reviewer without source access MUST NOT see the revoked finding in queue (Stage 8A)
        res_sync = client.post(f"/api/v1/projects/{proj_id}/verification/sync", headers=reviewer.headers)
        assert res_sync.status_code == 200, res_sync.text
        res_q = client.get(f"/api/v1/projects/{proj_id}/verification/queue?limit=50", headers=reviewer.headers)
        assert res_q.status_code == 200, res_q.text
        assert res_q.json()["total"] == 0

        with ctx.session_factory() as session:
            vc = session.execute(
                select(VerificationCase).where(
                    VerificationCase.project_id == uuid.UUID(proj_id),
                    VerificationCase.target_id == uuid.UUID(item_id),
                )
            ).scalar_one()
            case_id = str(vc.id)

        # Direct case detail probe must redact restricted finding & evidence excerpts and increment restricted_evidence_count
        res_detail = client.get(
            f"/api/v1/projects/{proj_id}/verification/cases/{case_id}",
            headers=reviewer.headers,
        )
        assert res_detail.status_code == 200
        detail = res_detail.json()
        assert detail["restricted_evidence_count"] >= 1
        assert len(detail["evidence_references"]) == 0
        assert detail["title"] == "[Restricted finding]"
        assert "secret/db" not in res_detail.text
        assert "Vault" not in res_detail.text

        # Handover eligibility fails closed for restricted/revoked evidence
        res_elig = client.get(
            f"/api/v1/projects/{proj_id}/handover/eligibility/knowledge_item/{item_id}",
            headers=reviewer.headers,
        )
        assert res_elig.status_code == 200
        assert res_elig.json()["is_eligible"] is False
