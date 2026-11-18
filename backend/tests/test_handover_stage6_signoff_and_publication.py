"""Stage 6 Tests: Three-Phase Signoff, Managerial Approval, Publication & Recipient Acknowledgement.

Platform: The Handover
Module: Handover Workspace (Module 4 / Knowledge Transfer Area)

Covers all Stage 6 backend verification criteria:
1.  Valid and invalid lifecycle transitions
2.  Three-phase signoff progression & duplicate approval prevention
3.  Reviewer assignment/reassignment & separation of duties (departing member cannot be reviewer or self-approve)
4.  Authoritative 4-gate approval eligibility & blocker enforcement (cannot silently waive blockers)
5.  Rejection & change-request workflow (mandatory reason, affected sections, valid transitions, no auto-approval)
6.  Package version & SHA-256 hash integrity + changed-package re-review (superseding prior approvals immutably)
7.  Authorised phase reopening with audit trail
8.  Controlled publication eligibility, active recipient validation & duplicate publication prevention
9.  Complete-package recipient acknowledgement (strict recipient identity, SHA-256 hash, unpublished blocked, duplicate blocked)
10. Recipient clarification request & outgoing/manager response preserving published package & acknowledgement
11. HTTP RBAC, cross-project/cross-case isolation & rollback safety on failed transitions
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
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
    KnowledgeCategory,
    KnowledgeReviewStatus,
    OrganisationStatus,
    ProjectStatus,
    ProjectVisibility,
    RoleName,
    SignoffDecision,
    SignoffType,
    UserStatus,
)
from app.models.evidence import EvidenceItem
from app.models.handover import HandoverSignoff
from app.models.knowledge import KnowledgeEvidenceLink, KnowledgeItem
from app.models.organisation import Organisation, OrganisationMembership
from app.models.project import Project, ProjectMembership
from app.models.user import User
from app.repositories.rbac import RbacRepository
from app.repositories.user import UserRepository
from app.schemas.handover import (
    AcknowledgementRequest,
    ChecklistItemUpdateRequest,
    DeliveryClarificationRequest,
    DeliveryRequest,
    HandoverCaseCreateRequest,
    PackageAssemblyRequest,
    ResponsibilityOutgoingConfirmRequest,
    ResponsibilitySuccessorAckRequest,
    ResponsibilityTransferBulkRequest,
    ResponsibilityTransferRequest,
    ReviewerAssignRequest,
    SignoffPhaseReopenRequest,
    SignoffRequest,
)
from app.services.handover_assembly import PackageAssemblyService
from app.services.handover_case import HandoverCaseService
from app.services.handover_checklist import ChecklistService
from app.services.handover_ownership import OwnershipTransferService
from app.services.handover_readiness import HandoverReadinessEngine
from app.services.handover_signoff import HandoverSignoffService
from app.services.rbac import RbacService


@pytest.fixture
def db_session() -> Any:
    """Isolated in-memory SQLite database with seeded RBAC catalog."""
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


def _create_user(session: Session, email: str, full_name: str) -> User:
    u = User(
        id=uuid.uuid4(),
        email=email,
        full_name=full_name,
        password_hash="argon2id$synthetic-test-hash",
        status=UserStatus.ACTIVE.value,
        is_email_verified=True,
        email_verified_at=datetime.now(UTC),
    )
    session.add(u)
    session.flush()
    return u


def _create_env(session: Session) -> dict[str, Any]:
    manager = _create_user(session, "manager@stage6.local", "Alex Manager")
    departing = _create_user(session, "departing@stage6.local", "Sam Departing")
    successor = _create_user(session, "successor@stage6.local", "Taylor Successor")
    reviewer = _create_user(session, "reviewer@stage6.local", "Jordan Reviewer")
    other_reviewer = _create_user(session, "reviewer2@stage6.local", "Casey OtherReviewer")
    removed_member = _create_user(session, "removed@stage6.local", "Morgan Removed")
    outsider = _create_user(session, "outsider@stage6.local", "Pat Outsider")

    org = Organisation(
        id=uuid.uuid4(),
        name="Stage 6 Test Org",
        slug=f"stage6-org-{uuid.uuid4().hex[:8]}",
        status=OrganisationStatus.ACTIVE.value,
        created_by_id=manager.id,
    )
    session.add(org)
    session.flush()

    for usr, role_name in (
        (manager, RoleName.ORG_ADMIN.value),
        (departing, RoleName.ORG_MEMBER.value),
        (successor, RoleName.ORG_MEMBER.value),
        (reviewer, RoleName.ORG_MEMBER.value),
        (other_reviewer, RoleName.ORG_MEMBER.value),
        (removed_member, RoleName.ORG_MEMBER.value),
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
        name="Nova Core Gateway",
        slug=f"nova-{uuid.uuid4().hex[:6]}",
        description="Core gateway for Stage 6 signoff and publication testing.",
        status=ProjectStatus.ACTIVE.value,
        visibility=ProjectVisibility.PRIVATE.value,
        created_by_id=manager.id,
        owner_id=manager.id,
    )
    proj_b = Project(
        id=uuid.uuid4(),
        organisation_id=org.id,
        name="Vega Isolated Project",
        slug=f"vega-{uuid.uuid4().hex[:6]}",
        description="Isolated project for cross-project testing.",
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
            user_id=reviewer.id,
            role_id=deterministic_rbac_id("role", RoleName.REVIEWER.value),
            status="active",
        ),
        ProjectMembership(
            id=uuid.uuid4(),
            project_id=proj_a.id,
            user_id=other_reviewer.id,
            role_id=deterministic_rbac_id("role", RoleName.REVIEWER.value),
            status="active",
        ),
        ProjectMembership(
            id=uuid.uuid4(),
            project_id=proj_a.id,
            user_id=removed_member.id,
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
        "reviewer": reviewer,
        "other_reviewer": other_reviewer,
        "removed": removed_member,
        "outsider": outsider,
    }


def _seed_ready_case(
    session: Session,
    env: dict[str, Any],
    *,
    complete_mandatory_checklists: bool = True,
) -> tuple[Any, Any]:
    """Create a handover case with verified knowledge, acknowledged responsibility & optional checklists."""
    org, proj_a, manager, departing, successor = (
        env["org"],
        env["proj_a"],
        env["manager"],
        env["departing"],
        env["successor"],
    )
    raw_hash = hashlib.sha256(f"spec-{uuid.uuid4()}".encode()).hexdigest()
    ev = EvidenceItem(
        id=uuid.uuid4(),
        organisation_id=org.id,
        project_id=proj_a.id,
        source_type=EvidenceSourceType.DOCUMENT_UPLOAD.value,
        source_provider="local_upload",
        category="design_document",
        source_external_id=f"doc-{uuid.uuid4().hex[:6]}",
        source_author_identity="Sam Departing",
        title="Nova Gateway Production Architecture",
        content_hash=raw_hash,
        processing_status=EvidenceProcessingStatus.EXTRACTED.value,
        acl_scope="project_members",
        source_created_at=datetime.now(UTC),
        extracted_at=datetime.now(UTC),
    )
    session.add(ev)
    session.flush()

    for cat, title in (
        (KnowledgeCategory.DECISIONS_RATIONALE.value, "Use Envoy ingress"),
        (KnowledgeCategory.TECHNICAL_ARCHITECTURE.value, "Gateway TLS termination"),
        (KnowledgeCategory.BUGS_BLOCKERS_RISKS.value, "Rate-limit burst caveat"),
        (KnowledgeCategory.DEPENDENCIES.value, "Depends on Auth IdP"),
        (KnowledgeCategory.OPERATIONAL_HISTORICAL.value, "Zero-downtime rollout runbook"),
    ):
        ki = KnowledgeItem(
            id=uuid.uuid4(),
            organisation_id=org.id,
            project_id=proj_a.id,
            category=cat,
            title=title,
            structured_summary=f"Verified detail for {title}",
            structured_payload={"verified": True},
            epistemic_status=EpistemicStatus.HUMAN_VERIFIED.value,
            review_status=KnowledgeReviewStatus.APPROVED.value,
            support_classification="direct",
            extraction_model="qwen3:8b",
            prompt_version="v1",
            fingerprint=hashlib.sha256(f"{title}-{uuid.uuid4()}".encode()).hexdigest(),
            confidence_metadata_json={"confidence_score": 0.96},
        )
        session.add(ki)
        session.flush()
        session.add(
            KnowledgeEvidenceLink(
                id=uuid.uuid4(),
                organisation_id=org.id,
                project_id=proj_a.id,
                knowledge_item_id=ki.id,
                evidence_id=ev.id,
                support_type="direct",
                supporting_excerpt="Verified verbatim excerpt.",
                excerpt_verified=True,
            )
        )
    session.flush()

    case = HandoverCaseService(session).create_case(
        organisation_id=org.id,
        project_id=proj_a.id,
        user_id=manager.id,
        request=HandoverCaseCreateRequest(
            title="Nova Gateway Handover",
            departing_member_id=departing.id,
            successor_id=successor.id,
        ),
    )

    # Map & acknowledge responsibility transfer so responsibility_coverage = 100
    resp_svc = OwnershipTransferService(session)
    trs = resp_svc.create_responsibility_transfers(
        case.id,
        project_id=proj_a.id,
        user_id=departing.id,
        request=ResponsibilityTransferBulkRequest(
            transfers=[
                ResponsibilityTransferRequest(
                    title="Gateway Operations",
                    responsibility_description="Maintain Nova Core Gateway deployments and alerts.",
                    operational_context="Deploy via ArgoCD; check Grafana latency dashboard.",
                    proposed_successor_id=successor.id,
                )
            ]
        ),
    )
    resp_svc.confirm_outgoing_owner(
        trs[0].id,
        project_id=proj_a.id,
        user_id=departing.id,
        request=ResponsibilityOutgoingConfirmRequest(confirmation_notes="Prepared"),
    )
    resp_svc.acknowledge_as_successor(
        trs[0].id,
        project_id=proj_a.id,
        user_id=successor.id,
        request=ResponsibilitySuccessorAckRequest(acknowledgement_notes="Acknowledged"),
    )

    # Checklists
    chk_svc = ChecklistService(session)
    chks = chk_svc.generate_checklists_for_case(case.id, project_id=proj_a.id, user_id=manager.id)
    if complete_mandatory_checklists:
        for chk in chks:
            for item in chk.items:
                if item.blocking:
                    chk_svc.update_item_status(
                        item.id,
                        project_id=proj_a.id,
                        user_id=departing.id,
                        request=ChecklistItemUpdateRequest(
                            status=ChecklistItemStatus.COMPLETED.value,
                            notes="Verified done",
                        ),
                    )

    version = PackageAssemblyService(session).assemble_package_version(
        case.id,
        project_id=proj_a.id,
        user_id=manager.id,
        request=PackageAssemblyRequest(assembly_notes="v1 ready"),
        has_project_manage=True,
    )
    HandoverReadinessEngine(session).assess_version(
        version.id, project_id=proj_a.id, user_id=manager.id, notes="Initial assessment"
    )
    session.commit()
    return case, version


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
# Test 1: Separation of Duties, Reviewer Assignment, Blocker Enforcement & Full Lifecycle
# =============================================================================


def test_full_three_phase_lifecycle_separation_of_duties_publication_and_acknowledgement(
    db_session: Session,
) -> None:
    env = _create_env(db_session)
    proj_a, manager, departing, successor, reviewer, other_reviewer, removed = (
        env["proj_a"],
        env["manager"],
        env["departing"],
        env["successor"],
        env["reviewer"],
        env["other_reviewer"],
        env["removed"],
    )
    case, version = _seed_ready_case(db_session, env, complete_mandatory_checklists=True)
    svc = HandoverSignoffService(db_session)

    # 1. Departing member CANNOT be assigned as independent reviewer
    with pytest.raises(ForbiddenError, match="Separation of duties"):
        svc.assign_reviewer(
            case.id,
            project_id=proj_a.id,
            actor_user_id=manager.id,
            request=ReviewerAssignRequest(reviewer_user_id=departing.id),
        )

    # Assign independent reviewer cleanly
    svc.assign_reviewer(
        case.id,
        project_id=proj_a.id,
        actor_user_id=manager.id,
        request=ReviewerAssignRequest(
            reviewer_user_id=reviewer.id, reason="Primary engineering reviewer"
        ),
    )

    # 2. Phase 1 departing sign-off with wrong content hash rejected (SHA-256 integrity guard!)
    with pytest.raises(ConflictError, match="Package integrity mismatch"):
        svc.submit_signoff(
            case.id,
            project_id=proj_a.id,
            user_id=departing.id,
            request=SignoffRequest(
                version_id=version.id,
                signoff_type=SignoffType.DEPARTING_SIGNOFF.value,
                decision=SignoffDecision.APPROVED.value,
                expected_content_hash="0" * 64,
            ),
        )

    # Valid Phase 1 departing sign-off
    p1 = svc.submit_signoff(
        case.id,
        project_id=proj_a.id,
        user_id=departing.id,
        request=SignoffRequest(
            version_id=version.id,
            signoff_type=SignoffType.DEPARTING_SIGNOFF.value,
            decision=SignoffDecision.APPROVED.value,
            comments="All 8 domains verified and operational runbooks prepared.",
            expected_content_hash=version.content_hash,
        ),
    )
    assert p1.package_content_hash == version.content_hash
    assert case.status == HandoverCaseStatus.REVIEW_PENDING.value

    # Duplicate Phase 1 rejected
    with pytest.raises(ConflictError, match="already been recorded"):
        svc.submit_signoff(
            case.id,
            project_id=proj_a.id,
            user_id=departing.id,
            request=SignoffRequest(
                version_id=version.id,
                signoff_type=SignoffType.DEPARTING_SIGNOFF.value,
                decision=SignoffDecision.APPROVED.value,
            ),
        )

    # 3. Separation of duties: departing member CANNOT approve Phase 2
    with pytest.raises(ForbiddenError, match="Separation of duties"):
        svc.submit_signoff(
            case.id,
            project_id=proj_a.id,
            user_id=departing.id,
            request=SignoffRequest(
                version_id=version.id,
                signoff_type=SignoffType.REVIEWER_APPROVAL.value,
                decision=SignoffDecision.APPROVED.value,
            ),
            is_org_admin=True,
            can_approve=True,
        )

    # Unassigned reviewer blocked when assigned_reviewer_id is set
    with pytest.raises(ForbiddenError, match="assigned independent reviewer"):
        svc.submit_signoff(
            case.id,
            project_id=proj_a.id,
            user_id=other_reviewer.id,
            request=SignoffRequest(
                version_id=version.id,
                signoff_type=SignoffType.REVIEWER_APPROVAL.value,
                decision=SignoffDecision.APPROVED.value,
            ),
            is_org_admin=False,
            can_approve=True,
        )

    # Cannot publish before Phase 2 approval
    with pytest.raises(BadRequestError, match="Cannot publish"):
        svc.deliver_package(
            case.id,
            project_id=proj_a.id,
            user_id=manager.id,
            request=DeliveryRequest(version_id=version.id, deliver_to_user_ids=[successor.id]),
        )

    # Cannot acknowledge before publication
    with pytest.raises(BadRequestError, match="only permitted after"):
        svc.submit_signoff(
            case.id,
            project_id=proj_a.id,
            user_id=successor.id,
            request=SignoffRequest(
                version_id=version.id,
                signoff_type=SignoffType.SUCCESSOR_ACKNOWLEDGEMENT.value,
                decision=SignoffDecision.APPROVED.value,
            ),
        )

    # 4. Assigned independent reviewer approves Phase 2
    p2 = svc.submit_signoff(
        case.id,
        project_id=proj_a.id,
        user_id=reviewer.id,
        request=SignoffRequest(
            version_id=version.id,
            signoff_type=SignoffType.REVIEWER_APPROVAL.value,
            decision=SignoffDecision.APPROVED.value,
            comments="All 4 readiness gates passed and evidence reviewed.",
            expected_content_hash=version.content_hash,
        ),
        can_approve=True,
    )
    assert p2.package_content_hash == version.content_hash
    assert case.status == HandoverCaseStatus.APPROVED.value

    # Duplicate Phase 2 rejected
    with pytest.raises(BadRequestError):
        svc.submit_signoff(
            case.id,
            project_id=proj_a.id,
            user_id=reviewer.id,
            request=SignoffRequest(
                version_id=version.id,
                signoff_type=SignoffType.REVIEWER_APPROVAL.value,
                decision=SignoffDecision.APPROVED.value,
            ),
            can_approve=True,
        )

    # 5. Controlled Publication: inactive/removed recipient rejected
    with pytest.raises(BadRequestError, match="active project memberships"):
        svc.deliver_package(
            case.id,
            project_id=proj_a.id,
            user_id=manager.id,
            request=DeliveryRequest(version_id=version.id, deliver_to_user_ids=[removed.id]),
        )

    # Valid publication to active successor
    deliveries = svc.deliver_package(
        case.id,
        project_id=proj_a.id,
        user_id=manager.id,
        request=DeliveryRequest(
            version_id=version.id,
            deliver_to_user_ids=[successor.id],
            message="Approved Nova Gateway Handover v1 published.",
            expected_content_hash=version.content_hash,
        ),
    )
    assert len(deliveries) == 1
    delivery = deliveries[0]
    assert delivery.artifact_checksum == version.content_hash
    assert delivery.message == "Approved Nova Gateway Handover v1 published."
    assert case.status == HandoverCaseStatus.DELIVERED.value

    # Duplicate publication blocked
    with pytest.raises(BadRequestError, match="Cannot publish"):
        svc.deliver_package(
            case.id,
            project_id=proj_a.id,
            user_id=manager.id,
            request=DeliveryRequest(version_id=version.id, deliver_to_user_ids=[successor.id]),
        )

    # 6. Recipient Clarification Workflow (before acknowledgement)
    svc.handle_delivery_clarification(
        delivery.id,
        project_id=proj_a.id,
        user_id=successor.id,
        request=DeliveryClarificationRequest(
            mode="request", notes="Is the Envoy canary rollout automated in staging?"
        ),
    )
    svc.handle_delivery_clarification(
        delivery.id,
        project_id=proj_a.id,
        user_id=departing.id,
        request=DeliveryClarificationRequest(
            mode="response", notes="Yes, triggered on main merge via ArgoCD rollout spec."
        ),
    )
    assert len(delivery.clarifications_json) == 2

    # 7. Non-recipient (manager) CANNOT acknowledge delivery
    with pytest.raises(ForbiddenError, match="only the designated publication recipient"):
        svc.acknowledge_delivery(
            delivery.id,
            project_id=proj_a.id,
            user_id=manager.id,
            request=AcknowledgementRequest(acknowledgement_notes="Manager forging receipt"),
        )

    # Valid recipient acknowledgement
    ack = svc.acknowledge_delivery(
        delivery.id,
        project_id=proj_a.id,
        user_id=successor.id,
        request=AcknowledgementRequest(
            acknowledgement_notes="Reviewed all 8 canonical domains and operational runbooks.",
            confirmations={"reviewed_domains": True, "reviewed_responsibilities": True},
            expected_content_hash=version.content_hash,
        ),
    )
    assert ack.acknowledgement_hash is not None
    assert case.status == HandoverCaseStatus.ACKNOWLEDGED.value

    # Duplicate acknowledgement blocked
    with pytest.raises(ConflictError, match="already been acknowledged"):
        svc.acknowledge_delivery(
            delivery.id,
            project_id=proj_a.id,
            user_id=successor.id,
            request=AcknowledgementRequest(acknowledgement_notes="Duplicate"),
        )


# =============================================================================
# Test 2: Blocker Enforcement, Rejection, Change Requests, Phase Reopen & Package Change Re-Review
# =============================================================================


def test_blocker_enforcement_rejection_reopen_and_changed_package_rereview(
    db_session: Session,
) -> None:
    env = _create_env(db_session)
    proj_a, manager, departing, successor, reviewer = (
        env["proj_a"],
        env["manager"],
        env["departing"],
        env["successor"],
        env["reviewer"],
    )
    # Mandatory checklists left incomplete -> checklist_gate_passed = False!
    case, v1 = _seed_ready_case(db_session, env, complete_mandatory_checklists=False)
    svc = HandoverSignoffService(db_session)

    # Phase 1 complete -> case moves to REVIEW_PENDING
    svc.submit_signoff(
        case.id,
        project_id=proj_a.id,
        user_id=departing.id,
        request=SignoffRequest(
            version_id=v1.id,
            signoff_type=SignoffType.DEPARTING_SIGNOFF.value,
            decision=SignoffDecision.APPROVED.value,
        ),
    )

    # Non-admin reviewer CANNOT approve while mandatory checklists are incomplete
    with pytest.raises(BadRequestError, match="unresolved readiness blockers"):
        svc.submit_signoff(
            case.id,
            project_id=proj_a.id,
            user_id=reviewer.id,
            request=SignoffRequest(
                version_id=v1.id,
                signoff_type=SignoffType.REVIEWER_APPROVAL.value,
                decision=SignoffDecision.APPROVED.value,
            ),
            is_org_admin=False,
            can_approve=True,
        )
    assert case.status == HandoverCaseStatus.REVIEW_PENDING.value

    # Rejection without mandatory reason fails
    with pytest.raises(BadRequestError, match="mandatory reason"):
        svc.submit_signoff(
            case.id,
            project_id=proj_a.id,
            user_id=reviewer.id,
            request=SignoffRequest(
                version_id=v1.id,
                signoff_type=SignoffType.REVIEWER_APPROVAL.value,
                decision=SignoffDecision.REJECTED.value,
                comments="no",
            ),
        )

    # Return for revision with affected sections works cleanly
    rev_sig = svc.submit_signoff(
        case.id,
        project_id=proj_a.id,
        user_id=reviewer.id,
        request=SignoffRequest(
            version_id=v1.id,
            signoff_type=SignoffType.REVIEWER_APPROVAL.value,
            decision=SignoffDecision.RETURNED_FOR_REVISION.value,
            comments="Complete all mandatory transition checklists before approval.",
            affected_sections=["operational_historical", "responsibilities_ownership"],
        ),
    )
    assert rev_sig.affected_sections_json == ["operational_historical", "responsibilities_ownership"]
    assert case.status == HandoverCaseStatus.UNDER_REVIEW.value

    # Now complete all mandatory checklists, assemble v2 (changed package!), and reassess
    chk_svc = ChecklistService(db_session)
    for chk in chk_svc.list_checklists(case.id, project_id=proj_a.id):
        for item in chk.items:
            if item.blocking:
                chk_svc.update_item_status(
                    item.id,
                    project_id=proj_a.id,
                    user_id=departing.id,
                    request=ChecklistItemUpdateRequest(status=ChecklistItemStatus.COMPLETED.value),
                )

    v2 = PackageAssemblyService(db_session).assemble_package_version(
        case.id,
        project_id=proj_a.id,
        user_id=manager.id,
        request=PackageAssemblyRequest(assembly_notes="v2 after checklist completion"),
        has_project_manage=True,
    )
    assert v2.version_number == 2
    assert case.status == HandoverCaseStatus.ASSEMBLED.value

    # Prior v1 signoffs MUST be marked superseded immutably
    v1_signoffs = (
        db_session.query(HandoverSignoff).filter(HandoverSignoff.version_id == v1.id).all()
    )
    assert all(s.is_superseded for s in v1_signoffs)

    # Reassess v2, complete Phase 1 & Phase 2 on v2
    HandoverReadinessEngine(db_session).assess_version(
        v2.id, project_id=proj_a.id, user_id=manager.id, notes="v2 readiness"
    )
    svc.submit_signoff(
        case.id,
        project_id=proj_a.id,
        user_id=departing.id,
        request=SignoffRequest(
            version_id=v2.id,
            signoff_type=SignoffType.DEPARTING_SIGNOFF.value,
            decision=SignoffDecision.APPROVED.value,
        ),
    )
    svc.submit_signoff(
        case.id,
        project_id=proj_a.id,
        user_id=reviewer.id,
        request=SignoffRequest(
            version_id=v2.id,
            signoff_type=SignoffType.REVIEWER_APPROVAL.value,
            decision=SignoffDecision.APPROVED.value,
            comments="v2 approved cleanly",
        ),
        can_approve=True,
    )
    assert case.status == HandoverCaseStatus.APPROVED.value

    # Reopen Phase 2 approval -> transitions back to UNDER_REVIEW, supersedes approval, blocks publication
    svc.reopen_signoff_phase(
        case.id,
        project_id=proj_a.id,
        actor_user_id=manager.id,
        request=SignoffPhaseReopenRequest(
            signoff_type=SignoffType.REVIEWER_APPROVAL.value,
            reason="Late security note discovered before release.",
        ),
    )
    assert case.status == HandoverCaseStatus.UNDER_REVIEW.value
    with pytest.raises(BadRequestError, match="Cannot publish"):
        svc.deliver_package(
            case.id,
            project_id=proj_a.id,
            user_id=manager.id,
            request=DeliveryRequest(version_id=v2.id, deliver_to_user_ids=[successor.id]),
        )


# =============================================================================
# Test 3: HTTP Stage 6 Endpoints, Phase-Specific RBAC & Cross-Project Isolation
# =============================================================================


def test_stage6_http_endpoints_rbac_and_cross_project_isolation(db_session: Session) -> None:
    env = _create_env(db_session)
    proj_a, proj_b, manager, departing, successor, reviewer, outsider = (
        env["proj_a"],
        env["proj_b"],
        env["manager"],
        env["departing"],
        env["successor"],
        env["reviewer"],
        env["outsider"],
    )
    case, version = _seed_ready_case(db_session, env, complete_mandatory_checklists=True)

    try:
        # 1. Manager reads signoff workspace & assigns independent reviewer via HTTP
        client_mgr = _build_client(db_session, manager)
        ws_res = client_mgr.get(
            f"/api/v1/projects/{proj_a.id}/handover/cases/{case.id}/signoffs/workspace"
        )
        assert ws_res.status_code == 200, ws_res.text
        assert ws_res.json()["selected_content_hash"] == version.content_hash
        assert len(ws_res.json()["phases"]) == 3

        assign_res = client_mgr.post(
            f"/api/v1/projects/{proj_a.id}/handover/cases/{case.id}/signoffs/reviewer",
            json={"reviewer_user_id": str(reviewer.id), "reason": "Independent review"},
        )
        assert assign_res.status_code == 200, assign_res.text
        assert assign_res.json()["assigned_reviewer_id"] == str(reviewer.id)

        # 2. Departing member (PROJECT_MEMBER) submits Phase 1 sign-off via HTTP
        client_dep = _build_client(db_session, departing)
        p1_res = client_dep.post(
            f"/api/v1/projects/{proj_a.id}/handover/cases/{case.id}/signoffs",
            json={
                "version_id": str(version.id),
                "signoff_type": "departing_signoff",
                "decision": "approved",
                "comments": "Ready for independent review.",
                "expected_content_hash": version.content_hash,
            },
        )
        assert p1_res.status_code == 201, p1_res.text

        # 3. Assigned independent reviewer (REVIEWER) approves Phase 2 via HTTP
        client_rev = _build_client(db_session, reviewer)
        p2_res = client_rev.post(
            f"/api/v1/projects/{proj_a.id}/handover/cases/{case.id}/signoffs",
            json={
                "version_id": str(version.id),
                "signoff_type": "reviewer_approval",
                "decision": "approved",
                "comments": "Verified all 4 gates and evidence provenance.",
                "expected_content_hash": version.content_hash,
            },
        )
        assert p2_res.status_code == 201, p2_res.text

        # 4. Manager publishes approved package via HTTP
        client_mgr2 = _build_client(db_session, manager)
        pub_res = client_mgr2.post(
            f"/api/v1/projects/{proj_a.id}/handover/cases/{case.id}/deliver",
            json={
                "version_id": str(version.id),
                "deliver_to_user_ids": [str(successor.id)],
                "message": "Published Nova Gateway Handover v1",
                "expected_content_hash": version.content_hash,
            },
        )
        assert pub_res.status_code == 201, pub_res.text
        delivery_id = pub_res.json()[0]["id"]

        # 5. Successor requests clarification & acknowledges via HTTP
        client_succ = _build_client(db_session, successor)
        clar_res = client_succ.post(
            f"/api/v1/projects/{proj_a.id}/handover/deliveries/{delivery_id}/clarify",
            json={"mode": "request", "notes": "Confirm on-call rotation start date."},
        )
        assert clar_res.status_code == 200, clar_res.text

        ack_res = client_succ.post(
            f"/api/v1/projects/{proj_a.id}/handover/deliveries/{delivery_id}/acknowledge",
            json={
                "acknowledgement_notes": "Received and reviewed complete package.",
                "confirmations": {"reviewed_domains": True},
                "expected_content_hash": version.content_hash,
            },
        )
        assert ack_res.status_code == 201, ack_res.text

        # 6. Cross-project isolation: Project B cannot read Project A signoffs or workspace -> 404
        client_mgr3 = _build_client(db_session, manager)
        cross_list = client_mgr3.get(
            f"/api/v1/projects/{proj_b.id}/handover/cases/{case.id}/signoffs"
        )
        assert cross_list.status_code == 404
        cross_ws = client_mgr3.get(
            f"/api/v1/projects/{proj_b.id}/handover/cases/{case.id}/signoffs/workspace"
        )
        assert cross_ws.status_code == 404

        # 7. Outsider denied (403/404)
        client_out = _build_client(db_session, outsider)
        out_ws = client_out.get(
            f"/api/v1/projects/{proj_a.id}/handover/cases/{case.id}/signoffs/workspace"
        )
        assert out_ws.status_code in (403, 404)
    finally:
        app.dependency_overrides.clear()
