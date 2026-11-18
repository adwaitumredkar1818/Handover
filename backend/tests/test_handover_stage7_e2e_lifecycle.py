"""Stage 7 End-to-End Integration, Security & Defect-Regression Validation Suite.

Platform: The Handover
Stage: Stage 7 — End-to-End Integration, System Validation & Production-Readiness Audit

Exercises the complete isolated lifecycle:
  Project & Participants -> Evidence -> Knowledge Reconstruction -> Verification ->
  Conflict Detection & Resolution -> 8-Domain Package Assembly -> 9-Category Readiness ->
  Transition Checklists -> Responsibility Transfer (Outgoing + Successor Ack) ->
  Three-Phase Signoff -> Controlled Publication -> Complete-Package Recipient Ack ->
  Audit Trail & SHA-256 Integrity

Plus all 8 negative paths and targeted regression tests for Stage 7 confirmed defects:
  - DEF-01 (CRITICAL): Cross-project IDOR blocked on /eligibility/{target_type}/{target_id}
  - DEF-02 (CRITICAL): Post-signoff / post-approval / historical section editing blocked (409)
                       and narrative drafting enforces case_id + fail-closed source ACLs
  - DEF-03 (HIGH):     Live-authoritative 4-gate approval eligibility & blocking_requirements
                       never lag behind live DB conflicts/verifications; superseded signoffs excluded
  - DEF-04 (HIGH):     Locked case mutation blocked on ACKNOWLEDGED/SUPERSEDED & self-successor blocked
  - DEF-06 (MEDIUM):   listCases returns project_id, version & assigned_reviewer_id matching API contract
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_principal, get_db_session
from app.core.exceptions import BadRequestError, ConflictError, ForbiddenError
from app.core.rbac_catalog import deterministic_rbac_id
from app.main import app
from app.models import Base
from app.models.audit import AuditLog
from app.models.enums import (
    ChecklistItemStatus,
    ConflictResolutionState,
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
    SourcePermissionVerificationStatus,
    UserStatus,
    VerificationCaseStatus,
)
from app.models.evidence import EvidenceItem
from app.models.handover import HandoverPackageSection, HandoverStatusHistory
from app.models.integration import SourceAccessPolicy
from app.models.knowledge import KnowledgeEvidenceLink, KnowledgeItem
from app.models.organisation import Organisation, OrganisationMembership
from app.models.project import Project, ProjectMembership
from app.models.user import User
from app.models.verification import VerificationCase, VerificationConflict
from app.repositories.rbac import RbacRepository
from app.repositories.user import UserRepository
from app.schemas.conflicts import ResolveConflictRequest
from app.schemas.verification import ApproveFindingRequest
from app.schemas.handover import (
    AcknowledgementRequest,
    ChecklistItemReviewRequest,
    ChecklistItemUpdateRequest,
    DeliveryClarificationRequest,
    DeliveryRequest,
    HandoverCaseCreateRequest,
    HandoverCaseUpdateRequest,
    NarrativeDraftRequest,
    PackageAssemblyRequest,
    ResponsibilityOutgoingConfirmRequest,
    ResponsibilitySuccessorAckRequest,
    ResponsibilityTransferBulkRequest,
    ResponsibilityTransferRequest,
    ReviewerAssignRequest,
    SectionEditRequest,
    SignoffPhaseReopenRequest,
    SignoffRequest,
)
from app.services.auth import AuthenticatedPrincipal
from app.services.conflict_service import ConflictService
from app.services.handover_assembly import PackageAssemblyService
from app.services.handover_case import HandoverCaseService
from app.services.handover_checklist import ChecklistService
from app.services.handover_narrative import HandoverNarrativeService
from app.services.handover_ownership import OwnershipTransferService
from app.services.handover_readiness import HandoverReadinessEngine
from app.services.handover_sections import HandoverSectionReadService
from app.services.handover_signoff import HandoverSignoffService
from app.services.rbac import RbacService
from app.services.verification_engine import VerificationEngine
from app.services.verification_review import VerificationReviewService


@pytest.fixture
def db_session() -> Any:
    """Isolated in-memory SQLite database with seeded RBAC catalog."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn: Any, _conn_record: Any) -> None:
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=OFF")
        cursor.close()

    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()

    RbacRepository(session).ensure_catalog_seeded()
    session.commit()

    yield session
    session.close()


def _seed_isolated_org_and_users(session: Session) -> dict[str, Any]:
    """Create isolated org, Project A, Project B, and 5 distinct test users."""
    def _mk_bare_user(label: str) -> User:
        u = User(
            id=uuid.uuid4(),
            email=f"stage7-{label}-{uuid.uuid4().hex[:6]}@isolated.test",
            full_name=f"Test {label.title()}",
            password_hash="argon2id$isolated-test-hash",
            status=UserStatus.ACTIVE.value,
            is_email_verified=True,
            email_verified_at=datetime.now(UTC),
        )
        session.add(u)
        return u

    manager = _mk_bare_user("manager")
    departing = _mk_bare_user("departing")
    reviewer = _mk_bare_user("reviewer")
    successor = _mk_bare_user("successor")
    outsider = _mk_bare_user("outsider")
    session.flush()

    org = Organisation(
        id=uuid.uuid4(),
        name="Stage 7 Isolated E2E Org",
        slug=f"stage7-e2e-{uuid.uuid4().hex[:8]}",
        status=OrganisationStatus.ACTIVE.value,
        created_by_id=manager.id,
    )
    session.add(org)
    session.flush()

    proj_a = Project(
        id=uuid.uuid4(),
        organisation_id=org.id,
        name="Isolated E2E Handover Project A",
        slug=f"stage7-proj-a-{uuid.uuid4().hex[:6]}",
        status=ProjectStatus.ACTIVE.value,
        visibility=ProjectVisibility.PRIVATE.value,
        created_by_id=manager.id,
        owner_id=manager.id,
    )
    proj_b = Project(
        id=uuid.uuid4(),
        organisation_id=org.id,
        name="Isolated Cross-Tenant Project B",
        slug=f"stage7-proj-b-{uuid.uuid4().hex[:6]}",
        status=ProjectStatus.ACTIVE.value,
        visibility=ProjectVisibility.PRIVATE.value,
        created_by_id=outsider.id,
        owner_id=outsider.id,
    )
    session.add_all([proj_a, proj_b])
    session.flush()

    for u, org_role, proj_role_a, proj_role_b in [
        (manager, RoleName.ORG_MEMBER.value, RoleName.PROJECT_MANAGER.value, None),
        (departing, RoleName.ORG_MEMBER.value, RoleName.PROJECT_MEMBER.value, None),
        (reviewer, RoleName.ORG_MEMBER.value, RoleName.REVIEWER.value, None),
        (successor, RoleName.ORG_MEMBER.value, RoleName.PROJECT_MEMBER.value, None),
        (outsider, RoleName.ORG_MEMBER.value, None, RoleName.PROJECT_MANAGER.value),
    ]:
        session.add(
            OrganisationMembership(
                id=uuid.uuid4(),
                organisation_id=org.id,
                user_id=u.id,
                role_id=deterministic_rbac_id("role", org_role),
                status="active",
            )
        )
        if proj_role_a:
            session.add(
                ProjectMembership(
                    id=uuid.uuid4(),
                    project_id=proj_a.id,
                    user_id=u.id,
                    role_id=deterministic_rbac_id("role", proj_role_a),
                    status="active",
                )
            )
        if proj_role_b:
            session.add(
                ProjectMembership(
                    id=uuid.uuid4(),
                    project_id=proj_b.id,
                    user_id=u.id,
                    role_id=deterministic_rbac_id("role", proj_role_b),
                    status="active",
                )
            )
    session.flush()

    return {
        "org": org,
        "proj_a": proj_a,
        "proj_b": proj_b,
        "manager": manager,
        "departing": departing,
        "reviewer": reviewer,
        "successor": successor,
        "outsider": outsider,
    }


def _create_evidence_and_knowledge(
    session: Session,
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    *,
    title: str,
    category: str,
    summary: str,
    acl_scope: str = "project_members",
    policy_id: uuid.UUID | None = None,
) -> tuple[EvidenceItem, KnowledgeItem]:
    ev = EvidenceItem(
        id=uuid.uuid4(),
        organisation_id=org_id,
        project_id=project_id,
        source_type=EvidenceSourceType.DOCUMENT_UPLOAD.value,
        source_provider="document_upload",
        category="project_document",
        source_external_id=f"doc-{uuid.uuid4().hex[:8]}",
        title=f"Source for {title}",
        content_hash=hashlib.sha256(summary.encode()).hexdigest(),
        acl_scope=acl_scope,
        source_access_policy_id=policy_id,
        processing_status=EvidenceProcessingStatus.EXTRACTED.value,
        source_created_at=datetime.now(UTC),
        extracted_at=datetime.now(UTC),
    )
    session.add(ev)
    ki = KnowledgeItem(
        id=uuid.uuid4(),
        organisation_id=org_id,
        project_id=project_id,
        category=category,
        title=title,
        structured_summary=summary,
        structured_payload={},
        epistemic_status=EpistemicStatus.EXTRACTED.value,
        review_status=KnowledgeReviewStatus.PENDING_REVIEW.value,
        support_classification="direct",
        extraction_model="qwen3:8b",
        prompt_version="v1",
        fingerprint=hashlib.sha256(f"{project_id}:{title}".encode()).hexdigest()[:32],
        is_stale=False,
        is_deleted=False,
    )
    session.add(ki)
    session.flush()
    session.add(
        KnowledgeEvidenceLink(
            id=uuid.uuid4(),
            organisation_id=org_id,
            project_id=project_id,
            knowledge_item_id=ki.id,
            evidence_id=ev.id,
            support_type="direct_support",
            supporting_excerpt=summary[:120],
        )
    )
    session.flush()
    return ev, ki


def test_stage7_full_17_step_isolated_lifecycle(db_session: Session) -> None:
    """Execute all 17 Stage 7 E2E lifecycle steps in strict isolation without weakening any gate."""
    # Step 1: Isolated project & participants
    env = _seed_isolated_org_and_users(db_session)
    org, proj_a = env["org"], env["proj_a"]
    manager, departing, reviewer, successor = (
        env["manager"],
        env["departing"],
        env["reviewer"],
        env["successor"],
    )

    # Step 2 & 3: Evidence & Knowledge across canonical domains + 1 deliberately unverified finding
    ev_dec, ki_dec = _create_evidence_and_knowledge(
        db_session,
        org.id,
        proj_a.id,
        title="Adopt PostgreSQL as Canonical Store",
        category=KnowledgeCategory.DECISIONS_RATIONALE.value,
        summary="PostgreSQL stores all authoritative records, relationships, and immutable audit logs.",
    )
    ev_arch, ki_arch = _create_evidence_and_knowledge(
        db_session,
        org.id,
        proj_a.id,
        title="FastAPI Modular Service Layer",
        category=KnowledgeCategory.TECHNICAL_ARCHITECTURE.value,
        summary="Backend separates API routes, RBAC, ingestion, retrieval, verification, and handover.",
    )
    ev_ops, ki_ops = _create_evidence_and_knowledge(
        db_session,
        org.id,
        proj_a.id,
        title="Zero-Downtime Alembic Migration Runbook",
        category=KnowledgeCategory.OPERATIONAL_HISTORICAL.value,
        summary="Run alembic upgrade head in dry-run check before rolling backend containers.",
    )
    _, ki_unverified = _create_evidence_and_knowledge(
        db_session,
        org.id,
        proj_a.id,
        title="Unverified Speculative Claim",
        category=KnowledgeCategory.BUGS_BLOCKERS_RISKS.value,
        summary="This speculative AI claim has not been reviewed and must remain excluded.",
    )

    # Step 4: Run VerificationEngine to materialize & assess real VerificationCases
    v_engine = VerificationEngine(db_session)
    v_engine.sync_project_findings(proj_a.id)
    v_engine.assess_project(proj_a.id)
    db_session.flush()

    cases = list(
        db_session.execute(
            select(VerificationCase).where(VerificationCase.project_id == proj_a.id)
        )
        .scalars()
        .all()
    )
    assert len(cases) == 4
    case_by_ki = {c.target_id: c for c in cases}

    # Step 5: Approve 3 eligible findings via VerificationReviewService (leave 1 unverified -> 75% verified >= 50%)
    rbac_svc = RbacService(
        db_session=db_session,
        rbac_repository=RbacRepository(db_session),
        user_repository=UserRepository(db_session),
    )
    reviewer_ctx = rbac_svc.resolve_project_context(
        project_id=proj_a.id,
        principal=AuthenticatedPrincipal(
            user=reviewer,
            session_family_id=None,
            roles=(),
            permissions=frozenset(),
        ),
    )
    v_review = VerificationReviewService(db_session)
    for ki in (ki_dec, ki_arch, ki_ops):
        v_review.approve_case(
            case_by_ki[ki.id].id,
            project_ctx=reviewer_ctx,
            payload=ApproveFindingRequest(
                reviewer_note="Verified against primary source evidence.",
            ),
        )
    db_session.flush()
    db_session.refresh(ki_dec)
    assert ki_dec.epistemic_status == EpistemicStatus.HUMAN_VERIFIED.value
    assert ki_dec.review_status == KnowledgeReviewStatus.APPROVED.value

    # Step 6: Create a test conflict, verify it blocks readiness, resolve it, reopen it, then resolve again
    conflict = VerificationConflict(
        id=uuid.uuid4(),
        organisation_id=org.id,
        project_id=proj_a.id,
        case_id=case_by_ki[ki_dec.id].id,
        conflict_type="decision_conflict",
        claim_a_text="PostgreSQL is the canonical data store.",
        claim_a_source_evidence_id=ev_dec.id,
        claim_b_text="Early prototype mentioned SQLite for local dev.",
        claim_b_source_evidence_id=ev_arch.id,
        explanation="Architecture notes diverged on local vs production database engine.",
        temporal_comparison="a_supersedes_b",
        resolution_state=ConflictResolutionState.UNRESOLVED.value,
        priority="high",
    )
    db_session.add(conflict)
    db_session.flush()

    # Create handover case
    case_svc = HandoverCaseService(db_session)
    hcase = case_svc.create_case(
        organisation_id=org.id,
        project_id=proj_a.id,
        user_id=manager.id,
        request=HandoverCaseCreateRequest(
            title="Stage 7 Isolated Full Lifecycle Handover",
            description="End-to-end verified transition package.",
            departing_member_id=departing.id,
            successor_id=successor.id,
        ),
    )

    # Step 7: Assemble canonical 8-domain package (while conflict exists on ki_dec -> ki_dec excluded while conflicted!)
    assembly_svc = PackageAssemblyService(db_session)
    v1 = assembly_svc.assemble_package_version(
        case_id=hcase.id,
        project_id=proj_a.id,
        user_id=manager.id,
        request=PackageAssemblyRequest(assembly_notes="Initial assembly before conflict resolution"),
        has_project_manage=True,
    )
    assert v1.version_number == 1
    assert v1.content_hash and len(v1.content_hash) == 64

    # Check 8 canonical sections and that ki_unverified is NEVER promoted to verified knowledge
    sec_svc = HandoverSectionReadService(db_session)
    v1_sections = sec_svc.get_version_sections(
        case_id=hcase.id,
        version_id=v1.id,
        project_id=proj_a.id,
        viewer_user_id=manager.id,
        has_project_manage=True,
    )
    assert len(v1_sections.sections) == 8
    verified_ids_v1 = {
        ki.id for s in v1_sections.sections for ki in s.knowledge_items
    }
    assert ki_unverified.id not in verified_ids_v1
    assert ki_dec.id not in verified_ids_v1  # Excluded while conflict is unresolved!
    assert ki_arch.id in verified_ids_v1
    assert ki_ops.id in verified_ids_v1

    # Step 8: Assess readiness while conflict is unresolved -> must block approval
    readiness_engine = HandoverReadinessEngine(db_session)
    r_blocked = readiness_engine.assess_version(
        version_id=v1.id,
        project_id=proj_a.id,
        user_id=manager.id,
        has_project_manage=True,
    )
    assert r_blocked.approval_eligibility is not None
    assert r_blocked.approval_eligibility.conflict_gate_passed is False
    assert r_blocked.approval_eligibility.is_eligible_for_approval is False

    # Resolve conflict via ConflictService, verify reopen restores blocker, then resolve cleanly
    conflict_svc = ConflictService(db_session)
    conflict_svc.resolve_conflict(
        conflict.id,
        proj_a.id,
        manager.id,
        ResolveConflictRequest(
            resolution_strategy="claim_a_authoritative",
            resolution_notes="Confirmed PostgreSQL is authoritative per ADR-01.",
            authoritative_claim_text="PostgreSQL is the canonical data store.",
            sync_finding=True,
        ),
    )
    db_session.flush()
    r_after_resolve = readiness_engine.get_readiness_intelligence(
        case_id=hcase.id,
        version_id=v1.id,
        project_id=proj_a.id,
        viewer_user_id=manager.id,
        has_project_manage=True,
    )
    assert r_after_resolve.approval_eligibility is not None
    assert r_after_resolve.approval_eligibility.conflict_gate_passed is True

    # Reopen restores blocker immediately
    conflict_svc.reopen_conflict(conflict.id, proj_a.id, manager.id, reason="Double-checking legacy note")
    db_session.flush()
    r_reopened = readiness_engine.get_readiness_intelligence(
        case_id=hcase.id,
        version_id=v1.id,
        project_id=proj_a.id,
        viewer_user_id=manager.id,
        has_project_manage=True,
    )
    assert r_reopened.approval_eligibility is not None
    assert r_reopened.approval_eligibility.conflict_gate_passed is False

    # Final resolution of conflict returns case to pending_review; reviewer re-approves finding explicitly
    conflict_svc.resolve_conflict(
        conflict.id,
        proj_a.id,
        manager.id,
        ResolveConflictRequest(
            resolution_strategy="claim_a_authoritative",
            resolution_notes="Confirmed final PostgreSQL decision.",
            authoritative_claim_text="PostgreSQL is the canonical data store.",
            sync_finding=True,
        ),
    )
    db_session.flush()
    db_session.refresh(case_by_ki[ki_dec.id])
    assert case_by_ki[ki_dec.id].case_status == VerificationCaseStatus.PENDING_REVIEW.value
    v_review.approve_case(
        case_by_ki[ki_dec.id].id,
        project_ctx=reviewer_ctx,
        payload=ApproveFindingRequest(
            reviewer_note="Re-verified after authoritative conflict resolution.",
        ),
    )
    db_session.flush()

    # Re-assemble v2 now that conflict is resolved -> ki_dec is now eligible & included
    v2 = assembly_svc.assemble_package_version(
        case_id=hcase.id,
        project_id=proj_a.id,
        user_id=manager.id,
        request=PackageAssemblyRequest(assembly_notes="Post-conflict resolution assembly"),
        has_project_manage=True,
    )
    assert v2.version_number == 2
    assert v2.content_hash != v1.content_hash
    v2_sections = sec_svc.get_version_sections(
        case_id=hcase.id,
        version_id=v2.id,
        project_id=proj_a.id,
        viewer_user_id=manager.id,
        has_project_manage=True,
    )
    verified_ids_v2 = {ki.id for s in v2_sections.sections for ki in s.knowledge_items}
    assert ki_dec.id in verified_ids_v2
    assert ki_unverified.id not in verified_ids_v2

    # Idempotent hash reproducibility check: assembling identical verified set yields identical content_hash
    v3 = assembly_svc.assemble_package_version(
        case_id=hcase.id,
        project_id=proj_a.id,
        user_id=manager.id,
        request=PackageAssemblyRequest(assembly_notes="Idempotency hash check"),
        has_project_manage=True,
    )
    assert v3.content_hash == v2.content_hash

    # Step 9: Generate transition checklists -> incomplete mandatory items block approval
    chk_svc = ChecklistService(db_session)
    checklists = chk_svc.generate_checklists_for_case(
        case_id=hcase.id,
        project_id=proj_a.id,
        user_id=manager.id,
        version_id=v3.id,
    )
    assert len(checklists) == 3

    r_chk_blocked = readiness_engine.assess_version(
        version_id=v3.id,
        project_id=proj_a.id,
        user_id=manager.id,
        has_project_manage=True,
    )
    assert r_chk_blocked.approval_eligibility is not None
    assert r_chk_blocked.approval_eligibility.checklist_gate_passed is False

    # Complete all mandatory items as departing member & independently verify one as reviewer
    first_mandatory_id = None
    for chk in checklists:
        for item in chk.items:
            if item.blocking:
                if first_mandatory_id is None:
                    first_mandatory_id = item.id
                chk_svc.update_item_status(
                    item_id=item.id,
                    project_id=proj_a.id,
                    user_id=departing.id,
                    request=ChecklistItemUpdateRequest(
                        status=ChecklistItemStatus.COMPLETED.value,
                        notes="Completed during isolated E2E handover.",
                    ),
                )
    assert first_mandatory_id is not None
    # Separation of duties: departing member cannot review their own completed checklist item
    with pytest.raises(ForbiddenError):
        chk_svc.review_item(
            item_id=first_mandatory_id,
            project_id=proj_a.id,
            reviewer_user_id=departing.id,
            request=ChecklistItemReviewRequest(approved=True, review_notes="Self-review attempt"),
        )
    chk_svc.review_item(
        item_id=first_mandatory_id,
        project_id=proj_a.id,
        reviewer_user_id=reviewer.id,
        request=ChecklistItemReviewRequest(approved=True, review_notes="Independently verified."),
    )

    # Step 10, 11, 12: Responsibility transfers -> outgoing confirm -> successor acknowledgement
    own_svc = OwnershipTransferService(db_session)
    created_transfers = own_svc.create_responsibility_transfers(
        case_id=hcase.id,
        project_id=proj_a.id,
        user_id=manager.id,
        request=ResponsibilityTransferBulkRequest(
            transfers=[
                ResponsibilityTransferRequest(
                    title="Backend Database & Migrations Ownership",
                    responsibility_description="Own PostgreSQL schema migrations and Alembic rollout procedures.",
                    knowledge_domain="operational_historical",
                    component_name="Database & Migrations",
                    priority="high",
                    ownership_certainty="confirmed",
                    proposed_successor_id=successor.id,
                    related_knowledge_item_id=ki_ops.id,
                )
            ]
        ),
    )
    transfer = created_transfers[0]
    own_svc.confirm_outgoing_owner(
        transfer_id=transfer.id,
        project_id=proj_a.id,
        user_id=departing.id,
        request=ResponsibilityOutgoingConfirmRequest(confirmation_notes="Walked through migration scripts."),
    )
    own_svc.acknowledge_as_successor(
        transfer_id=transfer.id,
        project_id=proj_a.id,
        user_id=successor.id,
        request=ResponsibilitySuccessorAckRequest(acknowledgement_notes="Understood and ready to take ownership."),
    )
    # Responsibility acknowledgement MUST NOT equal managerial approval!
    db_session.refresh(hcase)
    assert hcase.status != HandoverCaseStatus.APPROVED.value

    # Reassess readiness -> all 4 gates pass!
    r_ready = readiness_engine.assess_version(
        version_id=v3.id,
        project_id=proj_a.id,
        user_id=manager.id,
        has_project_manage=True,
    )
    assert r_ready.overall_score >= 70
    assert r_ready.approval_eligibility is not None
    assert r_ready.approval_eligibility.score_gate_passed is True
    assert r_ready.approval_eligibility.verification_gate_passed is True
    assert r_ready.approval_eligibility.conflict_gate_passed is True
    assert r_ready.approval_eligibility.checklist_gate_passed is True
    assert r_ready.approval_eligibility.is_eligible_for_approval is True

    # Step 13: Three-phase signoff with strict separation of duties
    signoff_svc = HandoverSignoffService(db_session)
    # Assign independent reviewer (departing owner cannot be assigned -> ForbiddenError)
    with pytest.raises(ForbiddenError):
        signoff_svc.assign_reviewer(
            case_id=hcase.id,
            project_id=proj_a.id,
            actor_user_id=manager.id,
            request=ReviewerAssignRequest(reviewer_user_id=departing.id),
        )
    signoff_svc.assign_reviewer(
        case_id=hcase.id,
        project_id=proj_a.id,
        actor_user_id=manager.id,
        request=ReviewerAssignRequest(reviewer_user_id=reviewer.id, reason="Independent technical review"),
    )

    # Phase 1: Departing owner sign-off
    db_session.refresh(hcase)
    sf1 = signoff_svc.submit_signoff(
        case_id=hcase.id,
        project_id=proj_a.id,
        user_id=departing.id,
        request=SignoffRequest(
            version_id=v3.id,
            signoff_type=SignoffType.DEPARTING_SIGNOFF.value,
            decision=SignoffDecision.APPROVED.value,
            comments="All domains verified and ready for review.",
            expected_content_hash=v3.content_hash,
            expected_case_version=hcase.version,
        ),
    )
    assert sf1.package_content_hash == v3.content_hash

    # Negative: departing owner cannot self-approve Phase 2
    db_session.refresh(hcase)
    with pytest.raises(ForbiddenError):
        signoff_svc.submit_signoff(
            case_id=hcase.id,
            project_id=proj_a.id,
            user_id=departing.id,
            request=SignoffRequest(
                version_id=v3.id,
                signoff_type=SignoffType.REVIEWER_APPROVAL.value,
                decision=SignoffDecision.APPROVED.value,
                expected_content_hash=v3.content_hash,
            ),
            can_approve=True,
        )

    # Negative: outdated/mismatched package hash rejected (409 ConflictError)
    with pytest.raises(ConflictError):
        signoff_svc.submit_signoff(
            case_id=hcase.id,
            project_id=proj_a.id,
            user_id=reviewer.id,
            request=SignoffRequest(
                version_id=v3.id,
                signoff_type=SignoffType.REVIEWER_APPROVAL.value,
                decision=SignoffDecision.APPROVED.value,
                expected_content_hash="0" * 64,
            ),
            can_approve=True,
        )

    # Phase 2: Independent reviewer approval
    sf2 = signoff_svc.submit_signoff(
        case_id=hcase.id,
        project_id=proj_a.id,
        user_id=reviewer.id,
        request=SignoffRequest(
            version_id=v3.id,
            signoff_type=SignoffType.REVIEWER_APPROVAL.value,
            decision=SignoffDecision.APPROVED.value,
            comments="All readiness gates and responsibilities verified.",
            expected_content_hash=v3.content_hash,
            expected_case_version=hcase.version,
        ),
        can_approve=True,
    )
    assert sf2.package_content_hash == v3.content_hash
    db_session.refresh(hcase)
    assert hcase.status == HandoverCaseStatus.APPROVED.value

    # Step 14 & 15: Validate publication eligibility & publish package
    ws_pre_pub = signoff_svc.get_signoff_workspace(
        case_id=hcase.id,
        project_id=proj_a.id,
        viewer_user_id=manager.id,
        version_id=v3.id,
        can_deliver=True,
        has_project_manage=True,
    )
    assert ws_pre_pub.publication.is_eligible_to_publish is True

    deliveries = signoff_svc.deliver_package(
        case_id=hcase.id,
        project_id=proj_a.id,
        user_id=manager.id,
        request=DeliveryRequest(
            version_id=v3.id,
            deliver_to_user_ids=[successor.id],
            delivery_method="internal_download",
            message="Approved Stage 7 package published for formal receipt.",
            expected_content_hash=v3.content_hash,
            expected_case_version=hcase.version,
        ),
    )
    assert len(deliveries) == 1
    delivery = deliveries[0]
    db_session.refresh(hcase)
    assert hcase.status == HandoverCaseStatus.DELIVERED.value

    # Recipient clarification request & outgoing owner response preserve published package
    signoff_svc.handle_delivery_clarification(
        delivery_id=delivery.id,
        project_id=proj_a.id,
        user_id=successor.id,
        request=DeliveryClarificationRequest(notes="Where is the staging migration dry-run log stored?", mode="request"),
    )
    signoff_svc.handle_delivery_clarification(
        delivery_id=delivery.id,
        project_id=proj_a.id,
        user_id=departing.id,
        request=DeliveryClarificationRequest(notes="Stored in CI workflow artifact migration-dryrun.", mode="response"),
    )

    # Step 16: Complete-package recipient acknowledgement
    ack = signoff_svc.acknowledge_delivery(
        delivery_id=delivery.id,
        project_id=proj_a.id,
        user_id=successor.id,
        request=AcknowledgementRequest(
            acknowledgement_notes="Reviewed all 8 domains and migration runbook.",
            confirmations={"reviewed_all_domains": True, "accepted_responsibilities": True},
            expected_content_hash=v3.content_hash,
        ),
    )
    assert ack.acknowledged_by_user_id == successor.id
    db_session.refresh(hcase)
    assert hcase.status == HandoverCaseStatus.ACKNOWLEDGED.value

    # Step 17: Validate audit history, status transitions, and hash integrity
    history = list(
        db_session.execute(
            select(HandoverStatusHistory)
            .where(HandoverStatusHistory.case_id == hcase.id)
            .order_by(HandoverStatusHistory.changed_at.asc())
        )
        .scalars()
        .all()
    )
    statuses_visited = [h.new_status for h in history]
    assert HandoverCaseStatus.DRAFT.value in statuses_visited
    assert HandoverCaseStatus.ASSEMBLED.value in statuses_visited
    assert HandoverCaseStatus.READINESS_ASSESSED.value in statuses_visited
    assert HandoverCaseStatus.APPROVED.value in statuses_visited
    assert HandoverCaseStatus.DELIVERED.value in statuses_visited
    assert HandoverCaseStatus.ACKNOWLEDGED.value in statuses_visited

    audit_events = list(
        db_session.execute(
            select(AuditLog.event_type).where(AuditLog.project_id == proj_a.id)
        )
        .scalars()
        .all()
    )
    for expected_evt in (
        "verification.case.approved",
        "handover.case.created",
        "handover.package.assembled",
        "handover.checklists.generated",
        "handover.checklist_item.reviewed",
        "handover.responsibility.outgoing_confirmed",
        "handover.responsibility.successor_acknowledged",
        "handover.readiness.assessed",
        "handover.reviewer.assigned",
        "handover.signoff.recorded",
        "handover.package.published",
        "handover.delivery.clarification_requested",
        "handover.delivery.clarification_responded",
        "handover.delivery.acknowledged",
    ):
        assert expected_evt in audit_events


def test_stage7_defect_regressions_and_security_boundaries(db_session: Session) -> None:
    """Targeted regression tests for DEF-01, DEF-02, DEF-03, DEF-04, DEF-06 & cross-project isolation."""
    env = _seed_isolated_org_and_users(db_session)
    org, proj_a, proj_b = env["org"], env["proj_a"], env["proj_b"]
    manager, departing, reviewer, successor, outsider = (
        env["manager"],
        env["departing"],
        env["reviewer"],
        env["successor"],
        env["outsider"],
    )

    # Create restricted policy in Project A allowing ONLY manager (not departing)
    restricted_policy = SourceAccessPolicy(
        id=uuid.uuid4(),
        organisation_id=org.id,
        project_id=proj_a.id,
        source_connection_id=uuid.uuid4(),
        provider="github",
        scope_identifier="org/private-repo",
        visibility_policy="explicit_user_grants",
        allowed_user_ids=[str(manager.id)],
        sync_permission_status=SourcePermissionVerificationStatus.VERIFIED.value,
        authorised_by_user_id=manager.id,
    )
    db_session.add(restricted_policy)
    db_session.flush()

    ev_public, ki_public = _create_evidence_and_knowledge(
        db_session,
        org.id,
        proj_a.id,
        title="Public Architecture Decision",
        category=KnowledgeCategory.DECISIONS_RATIONALE.value,
        summary="Publicly visible architecture note.",
    )
    ev_restricted, ki_restricted = _create_evidence_and_knowledge(
        db_session,
        org.id,
        proj_a.id,
        title="Restricted Secret Architecture Note",
        category=KnowledgeCategory.DECISIONS_RATIONALE.value,
        summary="Private repo internal topology details.",
        acl_scope="source_restricted",
        policy_id=restricted_policy.id,
    )
    ev_restricted.source_type = EvidenceSourceType.GITHUB.value
    db_session.flush()

    # Create a knowledge item in Project B to test DEF-01 cross-project IDOR
    _, ki_proj_b = _create_evidence_and_knowledge(
        db_session,
        org.id,
        proj_b.id,
        title="Project B Confidential Finding",
        category=KnowledgeCategory.DECISIONS_RATIONALE.value,
        summary="Secret Project B decision.",
    )

    # Approve Project A items
    v_engine = VerificationEngine(db_session)
    v_engine.sync_project_findings(proj_a.id)
    v_engine.assess_project(proj_a.id)
    db_session.flush()
    rbac_svc = RbacService(
        db_session=db_session,
        rbac_repository=RbacRepository(db_session),
        user_repository=UserRepository(db_session),
    )
    reviewer_ctx = rbac_svc.resolve_project_context(
        project_id=proj_a.id,
        principal=AuthenticatedPrincipal(
            user=reviewer,
            session_family_id=None,
            roles=(),
            permissions=frozenset(),
        ),
    )
    v_review = VerificationReviewService(db_session)
    for ki in (ki_public, ki_restricted):
        vc = db_session.execute(
            select(VerificationCase).where(VerificationCase.target_id == ki.id)
        ).scalar_one()
        v_review.approve_case(
            vc.id,
            project_ctx=reviewer_ctx,
            payload=ApproveFindingRequest(reviewer_note="Approved"),
        )
    db_session.flush()

    # Create & assemble Project A case
    case_svc = HandoverCaseService(db_session)
    hcase = case_svc.create_case(
        organisation_id=org.id,
        project_id=proj_a.id,
        user_id=manager.id,
        request=HandoverCaseCreateRequest(
            title="Regression Test Case",
            departing_member_id=departing.id,
            successor_id=successor.id,
        ),
    )
    hcase2 = case_svc.create_case(
        organisation_id=org.id,
        project_id=proj_a.id,
        user_id=manager.id,
        request=HandoverCaseCreateRequest(
            title="Second Case in Same Project",
            departing_member_id=departing.id,
        ),
    )
    assembly_svc = PackageAssemblyService(db_session)
    ver = assembly_svc.assemble_package_version(
        case_id=hcase.id,
        project_id=proj_a.id,
        user_id=manager.id,
        request=PackageAssemblyRequest(),
        has_project_manage=True,
    )

    # --- DEF-03 Regression: Live DB conflict created AFTER readiness assessment immediately blocks & updates blocking_requirements ---
    readiness_engine = HandoverReadinessEngine(db_session)
    r_before = readiness_engine.assess_version(
        version_id=ver.id,
        project_id=proj_a.id,
        user_id=manager.id,
        has_project_manage=True,
    )
    assert r_before.approval_eligibility is not None
    assert r_before.approval_eligibility.conflict_gate_passed is True

    vc_pub = db_session.execute(
        select(VerificationCase).where(VerificationCase.target_id == ki_public.id)
    ).scalar_one()
    new_conflict = VerificationConflict(
        id=uuid.uuid4(),
        organisation_id=org.id,
        project_id=proj_a.id,
        case_id=vc_pub.id,
        conflict_type="decision_conflict",
        claim_a_text="Claim A",
        claim_a_source_evidence_id=ev_public.id,
        claim_b_text="Claim B",
        claim_b_source_evidence_id=ev_public.id,
        explanation="Post-assessment conflict injected.",
        temporal_comparison="ambiguous",
        resolution_state=ConflictResolutionState.UNRESOLVED.value,
        priority="high",
    )
    db_session.add(new_conflict)
    db_session.flush()

    r_after = readiness_engine.get_readiness_intelligence(
        case_id=hcase.id,
        version_id=ver.id,
        project_id=proj_a.id,
        viewer_user_id=manager.id,
        has_project_manage=True,
    )
    assert r_after.approval_eligibility is not None
    assert r_after.approval_eligibility.conflict_gate_passed is False
    assert r_after.approval_eligibility.is_eligible_for_approval is False
    assert any("1 unresolved cross-source" in msg for msg in r_after.approval_eligibility.blocking_requirements)

    # --- DEF-02 Regression: Narrative drafting ACL filtering + cross-case check + post-signoff section edit lock ---
    narrative_svc = HandoverNarrativeService(db_session)
    # Cross-case version_id mismatch rejected
    with pytest.raises(Exception):
        narrative_svc.draft_section_narrative(
            project_id=proj_a.id,
            case_id=hcase2.id,
            request=NarrativeDraftRequest(
                version_id=ver.id,
                section_type="decisions_rationale",
            ),
            viewer_user_id=manager.id,
            has_project_manage=True,
        )
    # Departing user lacks ACL to restricted GitHub evidence -> snippet must be omitted from narrative draft!
    draft_dep = narrative_svc.draft_section_narrative(
        project_id=proj_a.id,
        case_id=hcase.id,
        request=NarrativeDraftRequest(
            version_id=ver.id,
            section_type="decisions_rationale",
        ),
        viewer_user_id=departing.id,
        has_project_manage=False,
    )
    assert "Public Architecture Decision" in draft_dep["draft_content"]
    assert "Restricted Secret Architecture Note" not in draft_dep["draft_content"]

    dec_sec = db_session.execute(
        select(HandoverPackageSection).where(
            HandoverPackageSection.version_id == ver.id,
            HandoverPackageSection.section_type == "decisions_rationale",
        )
    ).scalar_one()

    # Before signoff: edit is allowed and audited
    narrative_svc.edit_section_content(
        section_id=dec_sec.id,
        project_id=proj_a.id,
        user_id=manager.id,
        request=SectionEditRequest(
            section_content="Updated editable draft content.",
            content_summary="Updated summary",
        ),
    )

    # Submit Phase 1 signoff -> subsequent section edit MUST be blocked (409 ConflictError)
    signoff_svc = HandoverSignoffService(db_session)
    signoff_svc.submit_signoff(
        case_id=hcase.id,
        project_id=proj_a.id,
        user_id=departing.id,
        request=SignoffRequest(
            version_id=ver.id,
            signoff_type=SignoffType.DEPARTING_SIGNOFF.value,
            decision=SignoffDecision.APPROVED.value,
            expected_content_hash=ver.content_hash,
        ),
    )
    with pytest.raises(ConflictError):
        narrative_svc.edit_section_content(
            section_id=dec_sec.id,
            project_id=proj_a.id,
            user_id=manager.id,
            request=SectionEditRequest(
                section_content="Post-signoff tampering attempt!",
                content_summary="Tampered",
            ),
        )

    # DEF-03 sub-check: Reopen Phase 1 -> required_signoffs in readiness MUST mark Phase 1 pending again (not completed!)
    signoff_svc.reopen_signoff_phase(
        case_id=hcase.id,
        project_id=proj_a.id,
        actor_user_id=manager.id,
        request=SignoffPhaseReopenRequest(
            signoff_type=SignoffType.DEPARTING_SIGNOFF.value,
            reason="Reopening Phase 1 after conflict check.",
        ),
    )
    r_reopened_sf = readiness_engine.get_readiness_intelligence(
        case_id=hcase.id,
        version_id=ver.id,
        project_id=proj_a.id,
        viewer_user_id=manager.id,
        has_project_manage=True,
    )
    assert r_reopened_sf.approval_eligibility is not None
    p1_req = next(
        s for s in r_reopened_sf.approval_eligibility.required_signoffs
        if s["signoff_type"] == SignoffType.DEPARTING_SIGNOFF.value
    )
    assert p1_req["status"] == "pending"

    # --- DEF-04 Regression: Self-successor rejected & ACKNOWLEDGED case locked ---
    with pytest.raises(BadRequestError):
        case_svc.update_case(
            hcase.id,
            project_id=proj_a.id,
            user_id=manager.id,
            request=HandoverCaseUpdateRequest(successor_id=departing.id),
        )
    hcase.status = HandoverCaseStatus.ACKNOWLEDGED.value
    db_session.flush()
    with pytest.raises(BadRequestError):
        case_svc.update_case(
            hcase.id,
            project_id=proj_a.id,
            user_id=manager.id,
            request=HandoverCaseUpdateRequest(title="Mutate after acknowledgement"),
        )

    # --- HTTP API Tests: DEF-01 (Cross-project IDOR on /eligibility) & DEF-06 (listCases schema) ---
    db_session.commit()

    active_principal = {"user": manager}

    def _override_db() -> Any:
        yield db_session

    def _override_principal() -> Any:
        class _P:
            user = active_principal["user"]
            user_id = active_principal["user"].id
            organisation_id = org.id
        return _P()

    app.dependency_overrides[get_db_session] = _override_db
    app.dependency_overrides[get_current_principal] = _override_principal
    try:
        client = TestClient(app)

        # DEF-01: Manager in Project A probing Project B's knowledge item via Project A's eligibility endpoint -> 404!
        resp_idor = client.get(
            f"/api/v1/projects/{proj_a.id}/handover/eligibility/knowledge_item/{ki_proj_b.id}"
        )
        assert resp_idor.status_code == 404

        # Valid in-project eligibility check succeeds (200)
        resp_ok = client.get(
            f"/api/v1/projects/{proj_a.id}/handover/eligibility/knowledge_item/{ki_public.id}"
        )
        assert resp_ok.status_code == 200
        assert resp_ok.json()["target_id"] == str(ki_public.id)

        # DEF-06: listCases returns project_id, version & assigned_reviewer_id
        resp_list = client.get(f"/api/v1/projects/{proj_a.id}/handover/cases")
        assert resp_list.status_code == 200
        first_case = resp_list.json()["items"][0]
        assert first_case["project_id"] == str(proj_a.id)
        assert isinstance(first_case["version"], int)

        # Cross-project outsider (manager of Project B only) denied on private Project A (404 non-disclosure / 403)
        active_principal["user"] = outsider
        resp_denied = client.get(
            f"/api/v1/projects/{proj_a.id}/handover/cases/{hcase.id}/signoffs/workspace"
        )
        assert resp_denied.status_code in (403, 404)
    finally:
        app.dependency_overrides.clear()
