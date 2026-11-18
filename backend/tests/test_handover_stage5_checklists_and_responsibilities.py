"""Stage 5 Tests: Transition Checklists, Responsibility Transfer & Ownership Management.

Platform: The Handover
Module: Handover Workspace (Module 4 / Knowledge Transfer Area)

Covers all Stage 5 backend verification criteria:
1.  Checklist retrieval, persistence, idempotent generation & custom item creation
2.  Mandatory vs optional, blocked, and overdue checklist item metrics
3.  Valid and invalid checklist completion, assignee eligibility & optimistic concurrency
4.  Checklist reopening with mandatory rationale & audit events + independent reviewer separation of duties
5.  Responsibility retrieval, creation, discovered candidate surfacing (without auto-promotion)
6.  Successor eligibility validation (active member, inactive member rejected, self-transfer rejected, conflicting ownership detected)
7.  Outgoing-owner confirmation, successor clarification request/response & successor acknowledgement (strict separation of duties)
8.  Responsibility reopening & audit trail
9.  Fail-closed evidence ACL redaction in both checklists & responsibility workspaces
10. Readiness Intelligence integration (unassigned critical, blocked, reopened, acknowledged) & reassessment idempotency
11. HTTP API RBAC, permission-denied cases & cross-project/cross-case isolation
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_principal, get_db_session
from app.core.exceptions import BadRequestError, ConflictError, ForbiddenError
from app.core.rbac_catalog import deterministic_rbac_id
from app.main import app
from app.models import Base
from app.models.enums import (
    ChecklistItemStatus,
    EpistemicStatus,
    EvidenceProcessingStatus,
    EvidenceSourceType,
    HandoverCaseStatus,
    HandoverReadinessCategory,
    KnowledgeCategory,
    KnowledgeReviewStatus,
    OrganisationStatus,
    ProjectStatus,
    ProjectVisibility,
    RoleName,
    SourcePermissionVerificationStatus,
    TransferStatus,
    UserStatus,
)
from app.models.evidence import EvidenceItem
from app.models.integration import SourceAccessPolicy, SourceConnection
from app.models.knowledge import KnowledgeEvidenceLink, KnowledgeItem
from app.models.organisation import Organisation, OrganisationMembership
from app.models.project import Project, ProjectMembership
from app.models.user import User
from app.repositories.rbac import RbacRepository
from app.repositories.user import UserRepository
from app.schemas.handover import (
    ChecklistItemCreateRequest,
    ChecklistItemReviewRequest,
    ChecklistItemUpdateRequest,
    HandoverCaseCreateRequest,
    PackageAssemblyRequest,
    ResponsibilityClarificationRequest,
    ResponsibilityOutgoingConfirmRequest,
    ResponsibilityReopenRequest,
    ResponsibilitySuccessorAckRequest,
    ResponsibilityTransferBulkRequest,
    ResponsibilityTransferRequest,
    ResponsibilityTransferUpdateRequest,
)
from app.services.handover_assembly import PackageAssemblyService
from app.services.handover_case import HandoverCaseService
from app.services.handover_checklist import ChecklistService
from app.services.handover_ownership import OwnershipTransferService
from app.services.handover_readiness import HandoverReadinessEngine
from app.services.rbac import RbacService


@pytest.fixture
def db_session() -> Any:
    """Create an isolated in-memory SQLite database with seeded RBAC catalog."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _enable_sqlite_fks(dbapi_conn: Any, _: Any) -> None:
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    session_factory = sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
        class_=Session,
    )
    with session_factory() as session:
        RbacRepository(session).ensure_catalog_seeded()
        session.commit()
        yield session
        session.rollback()


def _create_user(
    session: Session,
    email: str,
    full_name: str,
    *,
    status: str = UserStatus.ACTIVE.value,
) -> User:
    u = User(
        id=uuid.uuid4(),
        email=email,
        full_name=full_name,
        password_hash="argon2id$synthetic-test-hash",
        status=status,
        is_email_verified=True,
        email_verified_at=datetime.now(UTC),
    )
    session.add(u)
    session.flush()
    return u


def _create_project_env(session: Session) -> dict[str, Any]:
    """Create isolated Org + Project A + Project B + Users with varied roles/statuses."""
    manager = _create_user(session, "manager@stage5-test.local", "Alex Manager")
    departing = _create_user(session, "departing@stage5-test.local", "Sam Departing")
    successor = _create_user(session, "successor@stage5-test.local", "Taylor Successor")
    peer_reviewer = _create_user(session, "reviewer@stage5-test.local", "Jordan Reviewer")
    inactive_user = _create_user(session, "inactive@stage5-test.local", "Morgan Inactive")
    outsider = _create_user(session, "outsider@stage5-test.local", "Pat Outsider")

    org = Organisation(
        id=uuid.uuid4(),
        name="Stage 5 Test Org",
        slug=f"stage5-org-{uuid.uuid4().hex[:8]}",
        status=OrganisationStatus.ACTIVE.value,
        created_by_id=manager.id,
    )
    session.add(org)
    session.flush()

    for usr, role_name in (
        (manager, RoleName.ORG_ADMIN.value),
        (departing, RoleName.ORG_MEMBER.value),
        (successor, RoleName.ORG_MEMBER.value),
        (peer_reviewer, RoleName.ORG_MEMBER.value),
        (inactive_user, RoleName.ORG_MEMBER.value),
    ):
        session.add(
            OrganisationMembership(
                id=uuid.uuid4(),
                organisation_id=org.id,
                user_id=usr.id,
                role_id=deterministic_rbac_id("role", role_name),
                status="active",
            )
        )
    session.flush()

    proj_a = Project(
        id=uuid.uuid4(),
        organisation_id=org.id,
        name="Omega Ledger Platform",
        slug=f"omega-{uuid.uuid4().hex[:6]}",
        description="Core ledger platform for Stage 5 checklist and responsibility testing.",
        status=ProjectStatus.ACTIVE.value,
        visibility=ProjectVisibility.PRIVATE.value,
        created_by_id=manager.id,
        owner_id=manager.id,
    )
    proj_b = Project(
        id=uuid.uuid4(),
        organisation_id=org.id,
        name="Sigma Separate Project",
        slug=f"sigma-{uuid.uuid4().hex[:6]}",
        description="Second isolated project for cross-project tests.",
        status=ProjectStatus.ACTIVE.value,
        visibility=ProjectVisibility.PRIVATE.value,
        created_by_id=manager.id,
        owner_id=manager.id,
    )
    session.add_all([proj_a, proj_b])
    session.flush()

    session.add_all([
        ProjectMembership(
            id=uuid.uuid4(),
            project_id=proj_a.id,
            user_id=manager.id,
            role_id=deterministic_rbac_id("role", RoleName.PROJECT_MANAGER.value),
            status="active",
        ),
        ProjectMembership(
            id=uuid.uuid4(),
            project_id=proj_a.id,
            user_id=departing.id,
            role_id=deterministic_rbac_id("role", RoleName.PROJECT_MEMBER.value),
            status="active",
        ),
        ProjectMembership(
            id=uuid.uuid4(),
            project_id=proj_a.id,
            user_id=successor.id,
            role_id=deterministic_rbac_id("role", RoleName.PROJECT_MEMBER.value),
            status="active",
        ),
        ProjectMembership(
            id=uuid.uuid4(),
            project_id=proj_a.id,
            user_id=peer_reviewer.id,
            role_id=deterministic_rbac_id("role", RoleName.REVIEWER.value),
            status="active",
        ),
        ProjectMembership(
            id=uuid.uuid4(),
            project_id=proj_a.id,
            user_id=inactive_user.id,
            role_id=deterministic_rbac_id("role", RoleName.PROJECT_MEMBER.value),
            status="removed",
        ),
        ProjectMembership(
            id=uuid.uuid4(),
            project_id=proj_b.id,
            user_id=manager.id,
            role_id=deterministic_rbac_id("role", RoleName.PROJECT_MANAGER.value),
            status="active",
        ),
    ])
    session.flush()

    return {
        "org": org,
        "proj_a": proj_a,
        "proj_b": proj_b,
        "manager": manager,
        "departing": departing,
        "successor": successor,
        "reviewer": peer_reviewer,
        "inactive": inactive_user,
        "outsider": outsider,
    }


def _create_evidence(
    session: Session,
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    title: str,
    *,
    source_type: str = EvidenceSourceType.DOCUMENT_UPLOAD.value,
    acl_scope: str = "project_members",
    policy_id: uuid.UUID | None = None,
) -> EvidenceItem:
    raw_hash = hashlib.sha256(f"{title}-{uuid.uuid4()}".encode("utf-8")).hexdigest()
    ev = EvidenceItem(
        id=uuid.uuid4(),
        organisation_id=org_id,
        project_id=project_id,
        source_type=source_type,
        source_provider="github" if source_type == EvidenceSourceType.GITHUB.value else "local_upload",
        category="design_document",
        source_external_id=f"ref-{uuid.uuid4().hex[:8]}",
        source_url="https://github.com/org/omega/pull/99" if source_type == EvidenceSourceType.GITHUB.value else None,
        source_author_identity="Sam Departing",
        title=title,
        content_hash=raw_hash,
        processing_status=EvidenceProcessingStatus.EXTRACTED.value,
        acl_scope=acl_scope,
        source_access_policy_id=policy_id,
        source_created_at=datetime.now(UTC),
        extracted_at=datetime.now(UTC),
    )
    session.add(ev)
    session.flush()
    return ev


def _create_knowledge_item(
    session: Session,
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    title: str,
    *,
    category: str = KnowledgeCategory.RESPONSIBILITIES_OWNERSHIP.value,
    epistemic_status: str = EpistemicStatus.EXTRACTED.value,
    review_status: str = KnowledgeReviewStatus.PENDING_REVIEW.value,
    evidences: list[EvidenceItem] | None = None,
) -> KnowledgeItem:
    ki = KnowledgeItem(
        id=uuid.uuid4(),
        organisation_id=org_id,
        project_id=project_id,
        category=category,
        title=title,
        structured_summary=f"Grounded summary for {title}",
        structured_payload={"owner": "Sam Departing"},
        epistemic_status=epistemic_status,
        review_status=review_status,
        support_classification="direct",
        extraction_model="qwen3:8b",
        prompt_version="v1",
        fingerprint=hashlib.sha256(f"{title}-{uuid.uuid4()}".encode()).hexdigest(),
        confidence_metadata_json={"confidence_score": 0.91},
    )
    session.add(ki)
    session.flush()
    for ev in evidences or []:
        session.add(
            KnowledgeEvidenceLink(
                id=uuid.uuid4(),
                organisation_id=org_id,
                project_id=project_id,
                knowledge_item_id=ki.id,
                evidence_id=ev.id,
                support_type="direct",
                supporting_excerpt="Excerpt verifying component ownership.",
                excerpt_verified=True,
            )
        )
    session.flush()
    return ki


def _build_client(session: Session, user: User) -> TestClient:
    def _override_db() -> Any:
        yield session

    def _override_principal() -> Any:
        rbac_service = RbacService(
            db_session=session,
            rbac_repository=RbacRepository(session),
            user_repository=UserRepository(session),
        )
        return rbac_service.resolve_principal(user=user, session_family_id=uuid.uuid4())

    app.dependency_overrides[get_db_session] = _override_db
    app.dependency_overrides[get_current_principal] = _override_principal
    return TestClient(app)


# =============================================================================
# Test 1: Checklists Lifecycle — Idempotency, Custom Items, Overdue, Reopen & Review
# =============================================================================


def test_checklist_lifecycle_idempotency_overdue_reopen_and_independent_review(
    db_session: Session,
) -> None:
    env = _create_project_env(db_session)
    org, proj_a, manager, departing, successor, reviewer, inactive = (
        env["org"],
        env["proj_a"],
        env["manager"],
        env["departing"],
        env["successor"],
        env["reviewer"],
        env["inactive"],
    )

    ev_runbook = _create_evidence(db_session, org.id, proj_a.id, "Production Runbook v3")
    case = HandoverCaseService(db_session).create_case(
        organisation_id=org.id,
        project_id=proj_a.id,
        user_id=manager.id,
        request=HandoverCaseCreateRequest(
            title="Omega Handover",
            departing_member_id=departing.id,
            successor_id=successor.id,
            reviewer_id=reviewer.id,
        ),
    )
    db_session.flush()

    chk_svc = ChecklistService(db_session)
    first_gen = chk_svc.generate_checklists_for_case(
        case.id, project_id=proj_a.id, user_id=manager.id
    )
    assert len(first_gen) == 3

    # Idempotent generation: second call must NOT duplicate checklists
    second_gen = chk_svc.generate_checklists_for_case(
        case.id, project_id=proj_a.id, user_id=manager.id
    )
    assert len(second_gen) == 3

    # Add a custom mandatory item with an overdue due_date & evidence link
    past_due = datetime.now(UTC) - timedelta(days=2)
    custom = chk_svc.create_item(
        case.id,
        first_gen[0].id,
        project_id=proj_a.id,
        user_id=manager.id,
        request=ChecklistItemCreateRequest(
            item_text="Hand over PagerDuty escalation schedule",
            description="Transfer primary on-call rotation and escalation policy.",
            completion_criteria="Successor added to PagerDuty schedule and test alert received.",
            category="operations",
            blocking=True,
            assigned_to_user_id=departing.id,
            due_date=past_due,
            evidence_item_id=ev_runbook.id,
        ),
    )
    assert custom.version == 1

    # Invalid assignee (inactive project member) rejected
    with pytest.raises(BadRequestError, match="not active"):
        chk_svc.update_item_status(
            custom.id,
            project_id=proj_a.id,
            user_id=manager.id,
            request=ChecklistItemUpdateRequest(assigned_to_user_id=inactive.id),
        )

    # Invalid status rejected
    with pytest.raises(BadRequestError, match="Invalid checklist status"):
        chk_svc.update_item_status(
            custom.id,
            project_id=proj_a.id,
            user_id=departing.id,
            request=ChecklistItemUpdateRequest(status="auto_done"),
        )

    # Workspace reflects overdue & mandatory counts before completion
    ws_before = chk_svc.get_checklist_workspace(
        case.id, project_id=proj_a.id, viewer_user_id=manager.id, has_project_manage=True
    )
    assert ws_before.total_items == 11
    assert ws_before.overdue_items == 1
    assert ws_before.mandatory_total == 8
    assert ws_before.mandatory_outstanding == 8

    # Complete item as departing user
    completed = chk_svc.update_item_status(
        custom.id,
        project_id=proj_a.id,
        user_id=departing.id,
        request=ChecklistItemUpdateRequest(
            status=ChecklistItemStatus.COMPLETED.value,
            notes="PagerDuty schedule updated and verified.",
            expected_version=1,
        ),
    )
    assert completed.status == ChecklistItemStatus.COMPLETED.value
    assert completed.completed_by_user_id == departing.id
    assert completed.reviewed_by_user_id is None  # Completion != Reviewer verification!
    assert completed.version == 2

    # Optimistic concurrency conflict caught
    with pytest.raises(ConflictError):
        chk_svc.update_item_status(
            custom.id,
            project_id=proj_a.id,
            user_id=manager.id,
            request=ChecklistItemUpdateRequest(notes="Stale write", expected_version=1),
        )

    # Separation of duties: departing user who completed cannot self-verify as reviewer
    with pytest.raises(ForbiddenError, match="Separation of duties"):
        chk_svc.review_item(
            custom.id,
            project_id=proj_a.id,
            reviewer_user_id=departing.id,
            request=ChecklistItemReviewRequest(approved=True, review_notes="Self approving"),
            is_org_admin=False,
        )

    # Independent reviewer verifies completed item
    reviewed = chk_svc.review_item(
        custom.id,
        project_id=proj_a.id,
        reviewer_user_id=reviewer.id,
        request=ChecklistItemReviewRequest(
            approved=True, review_notes="Confirmed PagerDuty test alert succeeded."
        ),
    )
    assert reviewed.reviewed_by_user_id == reviewer.id
    assert reviewed.reviewed_at is not None

    # Reopening without reason rejected
    with pytest.raises(BadRequestError, match="documented reason"):
        chk_svc.update_item_status(
            custom.id,
            project_id=proj_a.id,
            user_id=manager.id,
            request=ChecklistItemUpdateRequest(status=ChecklistItemStatus.PENDING.value),
        )

    # Reopening WITH reason clears completion & review, increments reopened_count, writes audit event
    reopened = chk_svc.update_item_status(
        custom.id,
        project_id=proj_a.id,
        user_id=manager.id,
        request=ChecklistItemUpdateRequest(
            status=ChecklistItemStatus.IN_PROGRESS.value,
            reopen_reason="Secondary fallback escalation rule was missing.",
        ),
    )
    assert reopened.status == ChecklistItemStatus.IN_PROGRESS.value
    assert reopened.completed_at is None
    assert reopened.reviewed_at is None
    assert reopened.reopened_count == 1
    assert "fallback escalation" in (reopened.reopened_reason or "")

    ws_after = chk_svc.get_checklist_workspace(
        case.id, project_id=proj_a.id, viewer_user_id=manager.id, has_project_manage=True
    )
    event_types = [a.event_type for a in ws_after.activity_history]
    assert "handover.checklist_item.reopened" in event_types
    assert "handover.checklist_item.reviewed" in event_types
    assert "handover.checklist_item.completed" in event_types


# =============================================================================
# Test 2: Responsibility Transfer Lifecycle, Separation of Duties & Validation
# =============================================================================


def test_responsibility_transfer_validation_lifecycle_and_separation_of_duties(
    db_session: Session,
) -> None:
    env = _create_project_env(db_session)
    org, proj_a, manager, departing, successor, reviewer, inactive = (
        env["org"],
        env["proj_a"],
        env["manager"],
        env["departing"],
        env["successor"],
        env["reviewer"],
        env["inactive"],
    )

    ev_arch = _create_evidence(db_session, org.id, proj_a.id, "Settlement Ownership Doc")
    ki_unverified = _create_knowledge_item(
        db_session,
        org.id,
        proj_a.id,
        "Owns nightly reconciliation batch job",
        category=KnowledgeCategory.RESPONSIBILITIES_OWNERSHIP.value,
        epistemic_status=EpistemicStatus.EXTRACTED.value,
        review_status=KnowledgeReviewStatus.PENDING_REVIEW.value,
        evidences=[ev_arch],
    )
    ki_verified = _create_knowledge_item(
        db_session,
        org.id,
        proj_a.id,
        "Primary maintainer of Ledger Settlement API",
        category=KnowledgeCategory.RESPONSIBILITIES_OWNERSHIP.value,
        epistemic_status=EpistemicStatus.HUMAN_VERIFIED.value,
        review_status=KnowledgeReviewStatus.APPROVED.value,
        evidences=[ev_arch],
    )

    case = HandoverCaseService(db_session).create_case(
        organisation_id=org.id,
        project_id=proj_a.id,
        user_id=manager.id,
        request=HandoverCaseCreateRequest(
            title="Ledger Ownership Handover",
            departing_member_id=departing.id,
            successor_id=successor.id,
            reviewer_id=reviewer.id,
        ),
    )
    db_session.flush()

    resp_svc = OwnershipTransferService(db_session)

    # Inactive participant rejected as successor
    with pytest.raises(BadRequestError, match="not active"):
        resp_svc.create_responsibility_transfers(
            case.id,
            project_id=proj_a.id,
            user_id=departing.id,
            request=ResponsibilityTransferBulkRequest(
                transfers=[
                    ResponsibilityTransferRequest(
                        title="Settlement API",
                        responsibility_description="Maintain settlement endpoints and ledger writes.",
                        proposed_successor_id=inactive.id,
                    )
                ]
            ),
        )

    # Self-assignment rejected
    with pytest.raises(BadRequestError, match="same user"):
        resp_svc.create_responsibility_transfers(
            case.id,
            project_id=proj_a.id,
            user_id=departing.id,
            request=ResponsibilityTransferBulkRequest(
                transfers=[
                    ResponsibilityTransferRequest(
                        title="Settlement API",
                        responsibility_description="Maintain settlement endpoints and ledger writes.",
                        proposed_successor_id=departing.id,
                    )
                ]
            ),
        )

    # Create a grounded transfer linked to verified KI + an unassigned transfer
    created = resp_svc.create_responsibility_transfers(
        case.id,
        project_id=proj_a.id,
        user_id=departing.id,
        request=ResponsibilityTransferBulkRequest(
            transfers=[
                ResponsibilityTransferRequest(
                    title="Ledger Settlement API Ownership",
                    responsibility_description="Primary engineering owner for Ledger Settlement API and reconciliation jobs.",
                    component_name="ledger-settlement-api",
                    priority="critical",
                    ownership_certainty="proposed",
                    operational_context="Deployed via GitHub Actions; monitor p99 latency and dead-letter queue.",
                    required_access="AWS prod-read, GitHub maintainer on omega-ledger",
                    effective_transfer_date=date(2026, 12, 1),
                    proposed_successor_id=successor.id,
                    related_knowledge_item_id=ki_verified.id,
                )
            ]
        ),
    )
    transfer = created[0]
    assert transfer.transfer_status == TransferStatus.PREPARED.value

    # Workspace surfaces unmapped real candidate without promoting it to verified!
    ws = resp_svc.get_responsibility_workspace(
        case.id, project_id=proj_a.id, viewer_user_id=successor.id, has_project_manage=False
    )
    assert ws.total_transfers == 1
    assert len(ws.discovered_candidates) == 1
    cand = ws.discovered_candidates[0]
    assert cand.knowledge_item_id == ki_unverified.id
    assert cand.is_verified is False
    assert cand.ownership_certainty == "uncertain"

    # Successor CANNOT acknowledge before outgoing-owner confirmation!
    with pytest.raises(BadRequestError, match="Outgoing-owner confirmation is required"):
        resp_svc.acknowledge_as_successor(
            transfer.id,
            project_id=proj_a.id,
            user_id=successor.id,
            request=ResponsibilitySuccessorAckRequest(acknowledgement_notes="Early ack attempt"),
        )

    # Non-owner non-manager (successor) CANNOT confirm outgoing!
    with pytest.raises(ForbiddenError, match="Only the outgoing responsibility owner"):
        resp_svc.confirm_outgoing_owner(
            transfer.id,
            project_id=proj_a.id,
            user_id=successor.id,
            request=ResponsibilityOutgoingConfirmRequest(confirmation_notes="Unauthorized"),
            can_manage_project=False,
        )

    # Outgoing owner confirms preparation -> awaiting_successor_acknowledgement
    confirmed = resp_svc.confirm_outgoing_owner(
        transfer.id,
        project_id=proj_a.id,
        user_id=departing.id,
        request=ResponsibilityOutgoingConfirmRequest(
            confirmation_notes="Runbooks and access checklist prepared."
        ),
    )
    assert confirmed.transfer_status == TransferStatus.AWAITING_SUCCESSOR_ACKNOWLEDGEMENT.value
    assert confirmed.outgoing_confirmed_by_user_id == departing.id

    # Successor requests clarification
    clar_req = resp_svc.handle_clarification(
        transfer.id,
        project_id=proj_a.id,
        user_id=successor.id,
        request=ResponsibilityClarificationRequest(
            mode="request", notes="Where is the dead-letter replay script documented?"
        ),
    )
    assert clar_req.transfer_status == TransferStatus.CLARIFICATION_REQUESTED.value

    # Outgoing owner responds to clarification -> back to awaiting_successor_acknowledgement
    clar_resp = resp_svc.handle_clarification(
        transfer.id,
        project_id=proj_a.id,
        user_id=departing.id,
        request=ResponsibilityClarificationRequest(
            mode="response", notes="Located in scripts/replay_dlq.py and ADR-14."
        ),
    )
    assert clar_resp.transfer_status == TransferStatus.AWAITING_SUCCESSOR_ACKNOWLEDGEMENT.value
    assert "replay_dlq.py" in (clar_resp.clarification_response_notes or "")

    # Separation of duties: departing owner / manager CANNOT forge successor acknowledgement!
    with pytest.raises(ForbiddenError, match="only the designated incoming successor"):
        resp_svc.acknowledge_as_successor(
            transfer.id,
            project_id=proj_a.id,
            user_id=manager.id,
            request=ResponsibilitySuccessorAckRequest(acknowledgement_notes="Manager forging ack"),
        )

    # Designated successor acknowledges transfer (case status MUST remain untouched — not Stage 6 approval!)
    case_status_before = case.status
    acked = resp_svc.acknowledge_as_successor(
        transfer.id,
        project_id=proj_a.id,
        user_id=successor.id,
        request=ResponsibilitySuccessorAckRequest(
            acknowledgement_notes="Reviewed API architecture, DLQ replay runbook, and access plan."
        ),
    )
    assert acked.transfer_status == TransferStatus.ACKNOWLEDGED.value
    assert acked.successor_acknowledged_by_user_id == successor.id
    assert case.status == case_status_before  # Stage 5 ack != Stage 6 final approval!

    # Reopen transfer with rationale
    reopened = resp_svc.reopen_transfer(
        transfer.id,
        project_id=proj_a.id,
        user_id=successor.id,
        request=ResponsibilityReopenRequest(reason="Need staging DB credentials handoff verified."),
    )
    assert reopened.transfer_status == TransferStatus.REOPENED.value
    assert reopened.successor_acknowledged_at is None
    assert reopened.reopened_count == 1

    # Conflicting ownership detection: two transfers for same component with different successors
    resp_svc.create_responsibility_transfers(
        case.id,
        project_id=proj_a.id,
        user_id=manager.id,
        request=ResponsibilityTransferBulkRequest(
            transfers=[
                ResponsibilityTransferRequest(
                    title="Conflicting Ledger Owner",
                    responsibility_description="Duplicate component assignment to reviewer.",
                    component_name="ledger-settlement-api",
                    proposed_successor_id=reviewer.id,
                )
            ]
        ),
    )
    ws_final = resp_svc.get_responsibility_workspace(
        case.id, project_id=proj_a.id, viewer_user_id=manager.id, has_project_manage=True
    )
    assert any(i.code == "conflicting_ownership" for i in ws_final.validation_issues)
    audit_events = [a.event_type for a in ws_final.activity_history]
    assert "handover.responsibility.outgoing_confirmed" in audit_events
    assert "handover.responsibility.clarification_requested" in audit_events
    assert "handover.responsibility.clarification_responded" in audit_events
    assert "handover.responsibility.successor_acknowledged" in audit_events
    assert "handover.responsibility.reopened" in audit_events


# =============================================================================
# Test 3: Evidence ACL Fail-Closed Redaction in Checklists & Responsibilities
# =============================================================================


def test_stage5_evidence_acl_fail_closed_redaction(db_session: Session) -> None:
    env = _create_project_env(db_session)
    org, proj_a, manager, departing, successor = (
        env["org"],
        env["proj_a"],
        env["manager"],
        env["departing"],
        env["successor"],
    )

    conn = SourceConnection(
        id=uuid.uuid4(),
        organisation_id=org.id,
        provider="github",
        display_name="Restricted SecOps Repo",
        status="active",
        created_by_user_id=manager.id,
    )
    db_session.add(conn)
    db_session.flush()

    policy = SourceAccessPolicy(
        id=uuid.uuid4(),
        organisation_id=org.id,
        project_id=proj_a.id,
        source_connection_id=conn.id,
        provider="github",
        scope_identifier="org/restricted-secops",
        sync_permission_status=SourcePermissionVerificationStatus.VERIFIED.value,
        allowed_user_ids=[str(manager.id)],
    )
    db_session.add(policy)
    db_session.flush()

    ev_secret = _create_evidence(
        db_session,
        org.id,
        proj_a.id,
        "TOP_SECRET_KMS_ROTATION_DOC",
        source_type=EvidenceSourceType.GITHUB.value,
        acl_scope="source_restricted",
        policy_id=policy.id,
    )
    ki_resp = _create_knowledge_item(
        db_session,
        org.id,
        proj_a.id,
        "KMS Key Rotation Duty",
        category=KnowledgeCategory.RESPONSIBILITIES_OWNERSHIP.value,
        epistemic_status=EpistemicStatus.HUMAN_VERIFIED.value,
        review_status=KnowledgeReviewStatus.APPROVED.value,
        evidences=[ev_secret],
    )

    case = HandoverCaseService(db_session).create_case(
        organisation_id=org.id,
        project_id=proj_a.id,
        user_id=manager.id,
        request=HandoverCaseCreateRequest(
            title="ACL Test Handover",
            departing_member_id=departing.id,
            successor_id=successor.id,
        ),
    )
    chks = ChecklistService(db_session).generate_checklists_for_case(
        case.id, project_id=proj_a.id, user_id=manager.id
    )
    ChecklistService(db_session).update_item_status(
        chks[0].items[0].id,
        project_id=proj_a.id,
        user_id=manager.id,
        request=ChecklistItemUpdateRequest(evidence_item_id=ev_secret.id),
    )
    OwnershipTransferService(db_session).create_responsibility_transfers(
        case.id,
        project_id=proj_a.id,
        user_id=manager.id,
        request=ResponsibilityTransferBulkRequest(
            transfers=[
                ResponsibilityTransferRequest(
                    title="KMS Key Rotation",
                    responsibility_description="Rotate KMS keys quarterly.",
                    proposed_successor_id=successor.id,
                    related_knowledge_item_id=ki_resp.id,
                )
            ]
        ),
    )
    db_session.commit()

    # Successor does NOT have source ACL access -> restricted source MUST be redacted
    chk_ws = ChecklistService(db_session).get_checklist_workspace(
        case.id, project_id=proj_a.id, viewer_user_id=successor.id, has_project_manage=False
    )
    attached_item = chk_ws.checklists[0].items[0]
    assert attached_item.evidence_summary is not None
    assert attached_item.evidence_summary.acl_restricted is True
    assert attached_item.evidence_summary.title == "Restricted Source (ACL Protected)"
    assert attached_item.evidence_summary.source_url is None
    assert "TOP_SECRET_KMS_ROTATION_DOC" not in attached_item.evidence_summary.title

    resp_ws = OwnershipTransferService(db_session).get_responsibility_workspace(
        case.id, project_id=proj_a.id, viewer_user_id=successor.id, has_project_manage=False
    )
    assert len(resp_ws.transfers[0].supporting_evidence) == 1
    ev_ref = resp_ws.transfers[0].supporting_evidence[0]
    assert ev_ref.acl_restricted is True
    assert ev_ref.title == "Restricted Source (ACL Protected)"
    assert ev_ref.excerpt is None
    assert ev_ref.source_url is None


# =============================================================================
# Test 4: Readiness Integration & Reassessment Idempotency
# =============================================================================


def test_stage5_readiness_integration_and_reassessment_idempotency(db_session: Session) -> None:
    env = _create_project_env(db_session)
    org, proj_a, manager, departing, successor = (
        env["org"],
        env["proj_a"],
        env["manager"],
        env["departing"],
        env["successor"],
    )

    ev = _create_evidence(db_session, org.id, proj_a.id, "Verified Design Doc")
    _create_knowledge_item(
        db_session,
        org.id,
        proj_a.id,
        "Core API Architecture",
        category=KnowledgeCategory.TECHNICAL_ARCHITECTURE.value,
        epistemic_status=EpistemicStatus.HUMAN_VERIFIED.value,
        review_status=KnowledgeReviewStatus.APPROVED.value,
        evidences=[ev],
    )

    case = HandoverCaseService(db_session).create_case(
        organisation_id=org.id,
        project_id=proj_a.id,
        user_id=manager.id,
        request=HandoverCaseCreateRequest(
            title="Readiness Integration Handover",
            departing_member_id=departing.id,
            successor_id=None,  # Deliberately unassigned at case level
        ),
    )
    version = PackageAssemblyService(db_session).assemble_package_version(
        case.id,
        project_id=proj_a.id,
        user_id=manager.id,
        request=PackageAssemblyRequest(assembly_notes="v1"),
        has_project_manage=True,
    )

    resp_svc = OwnershipTransferService(db_session)
    created = resp_svc.create_responsibility_transfers(
        case.id,
        project_id=proj_a.id,
        user_id=departing.id,
        request=ResponsibilityTransferBulkRequest(
            transfers=[
                ResponsibilityTransferRequest(
                    title="Payment Gateway Failover",
                    responsibility_description="Manage payment gateway failover and incident runbook.",
                    priority="critical",
                    proposed_successor_id=None,  # Unassigned critical responsibility!
                )
            ]
        ),
    )
    transfer = created[0]
    db_session.commit()

    # 1. Unassigned critical responsibility MUST surface as a readiness blocker (score = 0)
    engine = HandoverReadinessEngine(db_session)
    r1 = engine.assess_version(version.id, project_id=proj_a.id, user_id=manager.id, notes="Unassigned")
    cat1 = {c.category: c for c in r1.categories}[HandoverReadinessCategory.RESPONSIBILITY_COVERAGE.value]
    assert cat1.score == 0
    assert any("critical/high-priority" in b for b in cat1.blockers_json)

    # 2. Assign successor, confirm outgoing, and acknowledge -> score jumps to 100 & blockers clear
    resp_svc.update_responsibility_transfer(
        transfer.id,
        project_id=proj_a.id,
        user_id=manager.id,
        request=ResponsibilityTransferUpdateRequest(
            proposed_successor_id=successor.id,
            operational_context="Failover runbook verified in staging.",
        ),
    )
    resp_svc.confirm_outgoing_owner(
        transfer.id,
        project_id=proj_a.id,
        user_id=departing.id,
        request=ResponsibilityOutgoingConfirmRequest(confirmation_notes="Ready"),
    )
    resp_svc.acknowledge_as_successor(
        transfer.id,
        project_id=proj_a.id,
        user_id=successor.id,
        request=ResponsibilitySuccessorAckRequest(acknowledgement_notes="Acknowledged"),
    )
    db_session.commit()

    r2 = engine.assess_version(version.id, project_id=proj_a.id, user_id=manager.id, notes="Acknowledged")
    cat2 = {c.category: c for c in r2.categories}[HandoverReadinessCategory.RESPONSIBILITY_COVERAGE.value]
    assert cat2.score == 100
    assert cat2.blockers_json == []

    # 3. Reopen transfer -> score drops back to 25 and warning surfaces
    resp_svc.reopen_transfer(
        transfer.id,
        project_id=proj_a.id,
        user_id=successor.id,
        request=ResponsibilityReopenRequest(reason="Need failover alert escalation details."),
    )
    db_session.commit()

    r3 = engine.assess_version(version.id, project_id=proj_a.id, user_id=manager.id, notes="Reopened")
    cat3 = {c.category: c for c in r3.categories}[HandoverReadinessCategory.RESPONSIBILITY_COVERAGE.value]
    assert cat3.score == 25
    assert any("reopened or require clarification" in w for w in cat3.warnings_json)

    # 4. Idempotent reassessment does not duplicate blockers or categories
    r4 = engine.assess_version(version.id, project_id=proj_a.id, user_id=manager.id, notes="Idempotent")
    assert len(r4.categories) == 9
    assert r4.blocker_count == r3.blocker_count
    assert len(r4.assessment_history) == 4


# =============================================================================
# Test 5: HTTP Stage 5 Endpoints, RBAC, Permission-Denied & Cross-Project Isolation
# =============================================================================


def test_stage5_http_endpoints_rbac_and_cross_project_isolation(db_session: Session) -> None:
    env = _create_project_env(db_session)
    org, proj_a, proj_b, manager, departing, successor, outsider = (
        env["org"],
        env["proj_a"],
        env["proj_b"],
        env["manager"],
        env["departing"],
        env["successor"],
        env["outsider"],
    )

    case_a = HandoverCaseService(db_session).create_case(
        organisation_id=org.id,
        project_id=proj_a.id,
        user_id=manager.id,
        request=HandoverCaseCreateRequest(
            title="HTTP Stage 5 Case",
            departing_member_id=departing.id,
            successor_id=successor.id,
        ),
    )
    db_session.commit()

    try:
        # 1. Manager generates checklists and reads checklist workspace
        client_mgr = _build_client(db_session, manager)
        gen = client_mgr.post(f"/api/v1/projects/{proj_a.id}/handover/cases/{case_a.id}/checklists/generate")
        assert gen.status_code == 201, gen.text

        chk_ws = client_mgr.get(f"/api/v1/projects/{proj_a.id}/handover/cases/{case_a.id}/checklists/workspace")
        assert chk_ws.status_code == 200, chk_ws.text
        assert chk_ws.json()["total_checklists"] == 3
        assert chk_ws.json()["mandatory_total"] == 7

        # 2. Create responsibility transfer & confirm outgoing via HTTP
        create_resp = client_mgr.post(
            f"/api/v1/projects/{proj_a.id}/handover/cases/{case_a.id}/responsibilities",
            json={
                "transfers": [
                    {
                        "title": "CI/CD Pipeline Ownership",
                        "responsibility_description": "Maintain GitHub Actions release workflows.",
                        "priority": "high",
                        "proposed_successor_id": str(successor.id),
                    }
                ]
            },
        )
        assert create_resp.status_code == 201, create_resp.text
        transfer_id = create_resp.json()[0]["id"]

        confirm_res = client_mgr.post(
            f"/api/v1/projects/{proj_a.id}/handover/responsibilities/{transfer_id}/confirm-outgoing",
            json={"confirmation_notes": "Pipeline docs ready."},
        )
        assert confirm_res.status_code == 200, confirm_res.text
        assert confirm_res.json()["transfer_status"] == "awaiting_successor_acknowledgement"

        # 3. Manager CANNOT acknowledge on behalf of successor (403 Forbidden)
        forged_ack = client_mgr.post(
            f"/api/v1/projects/{proj_a.id}/handover/responsibilities/{transfer_id}/acknowledge",
            json={"acknowledgement_notes": "Forged by manager"},
        )
        assert forged_ack.status_code == 403

        # 4. Successor CAN acknowledge via HTTP
        client_succ = _build_client(db_session, successor)
        succ_ack = client_succ.post(
            f"/api/v1/projects/{proj_a.id}/handover/responsibilities/{transfer_id}/acknowledge",
            json={"acknowledgement_notes": "Reviewed CI/CD workflows."},
        )
        assert succ_ack.status_code == 200, succ_ack.text
        assert succ_ack.json()["transfer_status"] == "acknowledged"

        # 5. Cross-project isolation: accessing Project A's case/transfer under Project B -> 404
        client_mgr2 = _build_client(db_session, manager)
        cross_chk = client_mgr2.get(
            f"/api/v1/projects/{proj_b.id}/handover/cases/{case_a.id}/checklists/workspace"
        )
        assert cross_chk.status_code == 404
        cross_resp = client_mgr2.post(
            f"/api/v1/projects/{proj_b.id}/handover/responsibilities/{transfer_id}/reopen",
            json={"reason": "Cross project attempt"},
        )
        assert cross_resp.status_code == 404

        # 6. Outsider denied (403/404 tenant isolation)
        client_out = _build_client(db_session, outsider)
        out_res = client_out.get(
            f"/api/v1/projects/{proj_a.id}/handover/cases/{case_a.id}/responsibilities/workspace"
        )
        assert out_res.status_code in (403, 404)
    finally:
        app.dependency_overrides.clear()
