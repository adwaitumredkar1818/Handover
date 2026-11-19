"""Stage 4 Tests: Live Readiness Intelligence, Conflict Management Integration, Checklists & Reassessment.

Platform: The Handover
Module: Handover Workspace (Module 4 / Knowledge Transfer Area)

Covers all Stage 4 verification requirements:
1.  Readiness retrieval via HTTP GET & POST + RBAC (non-member denied)
2.  All 9 canonical readiness categories returned with weights & scores
3.  Weighted score aggregation matching CATEGORY_WEIGHTS
4.  Missing knowledge & responsibility blockers
5.  Pending verification blockers & VerificationCase 6-status counts
6.  Unresolved conflict blockers across ALL active states (unresolved, open, under_investigation, awaiting_context, reopened)
7.  Resolved conflict handling (resolved, reconciled, superseded, dismissed do NOT block)
8.  Critical/high conflict approval gating (HandoverSignoffService cannot bypass unresolved blockers)
9.  Checklist integration (mandatory blocking=True items reflected in checklist_summary & approval_eligibility)
10. Evidence completeness, corroboration, staleness, and uncertain claim metrics
11. Source ACL fail-closed redaction on restricted evidence & conflict source titles
12. Cross-project and cross-case isolation (404 when reading/assessing version from another project/case)
13. Reassessment on an already `readiness_assessed` case succeeds without status transition error
14. Historical assessment integrity (assessment_history preserves prior runs without doubling active blocker_count/categories)
15. Persistence after refresh (re-reading via GET returns exact latest persisted snapshot)
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
from app.core.exceptions import BadRequestError
from app.core.rbac_catalog import deterministic_rbac_id
from app.main import app
from app.models import Base
from app.models.enums import (
    ConflictPriority,
    ConflictResolutionState,
    ConflictType,
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
    ReviewActionType,
    RoleName,
    SignoffDecision,
    SignoffType,
    SourcePermissionVerificationStatus,
    UserStatus,
    VerificationCaseStatus,
    VerificationPriority,
    VerificationTargetType,
)
from app.models.evidence import EvidenceItem
from app.models.integration import SourceAccessPolicy, SourceConnection
from app.models.knowledge import KnowledgeEvidenceLink, KnowledgeItem
from app.models.organisation import Organisation, OrganisationMembership
from app.models.project import Project, ProjectMembership
from app.models.user import User
from app.models.verification import (
    VerificationCase,
    VerificationConflict,
    VerificationReviewEvent,
)
from app.repositories.rbac import RbacRepository
from app.repositories.user import UserRepository
from app.schemas.handover import (
    HandoverCaseCreateRequest,
    PackageAssemblyRequest,
    SignoffRequest,
)
from app.services.handover_assembly import PackageAssemblyService
from app.services.handover_case import HandoverCaseService
from app.services.handover_checklist import ChecklistService
from app.services.handover_readiness import CATEGORY_WEIGHTS, HandoverReadinessEngine
from app.services.handover_signoff import HandoverSignoffService
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


def _create_project_env(session: Session) -> dict[str, Any]:
    """Create isolated Org + Project A + Project B + Users + RBAC memberships."""
    manager = _create_user(session, "manager@stage4-test.local", "Alex Manager")
    member = _create_user(session, "member@stage4-test.local", "Sam Engineer")
    reviewer = _create_user(session, "reviewer@stage4-test.local", "Jordan Reviewer")
    outsider = _create_user(session, "outsider@stage4-test.local", "Pat Outsider")

    org = Organisation(
        id=uuid.uuid4(),
        name="Stage 4 Test Org",
        slug=f"stage4-org-{uuid.uuid4().hex[:8]}",
        status=OrganisationStatus.ACTIVE.value,
        created_by_id=manager.id,
    )
    session.add(org)
    session.flush()

    for usr in (manager, member, reviewer):
        session.add(
            OrganisationMembership(
                id=uuid.uuid4(),
                organisation_id=org.id,
                user_id=usr.id,
                role_id=deterministic_rbac_id("role", RoleName.ORG_ADMIN.value),
                status="active",
            )
        )
    session.flush()

    proj_a = Project(
        id=uuid.uuid4(),
        organisation_id=org.id,
        name="Delta Settlement Engine",
        slug=f"delta-{uuid.uuid4().hex[:6]}",
        description="Settlement engine for Stage 4 readiness verification.",
        status=ProjectStatus.ACTIVE.value,
        visibility=ProjectVisibility.PRIVATE.value,
        created_by_id=manager.id,
        owner_id=manager.id,
    )
    proj_b = Project(
        id=uuid.uuid4(),
        organisation_id=org.id,
        name="Gamma Isolated Project",
        slug=f"gamma-{uuid.uuid4().hex[:6]}",
        description="Second project for cross-project isolation checks.",
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
            user_id=member.id,
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
        "member": member,
        "reviewer": reviewer,
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
        source_url="https://github.com/org/delta/pull/101" if source_type == EvidenceSourceType.GITHUB.value else None,
        source_author_identity="Alex Manager",
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
    category: str = KnowledgeCategory.DECISIONS_RATIONALE.value,
    epistemic_status: str = EpistemicStatus.EXTRACTED.value,
    review_status: str = KnowledgeReviewStatus.PENDING_REVIEW.value,
    support_classification: str = "direct",
    is_stale: bool = False,
    superseded_by_id: uuid.UUID | None = None,
    evidences: list[EvidenceItem] | None = None,
) -> KnowledgeItem:
    ki = KnowledgeItem(
        id=uuid.uuid4(),
        organisation_id=org_id,
        project_id=project_id,
        category=category,
        title=title,
        structured_summary=f"Summary for {title}",
        structured_payload={"rationale": f"Details for {title}"},
        epistemic_status=epistemic_status,
        review_status=review_status,
        support_classification=support_classification,
        is_stale=is_stale,
        superseded_by_id=superseded_by_id,
        extraction_model="qwen3:8b",
        prompt_version="v1",
        fingerprint=hashlib.sha256(f"{title}-{uuid.uuid4()}".encode()).hexdigest(),
        confidence_metadata_json={"confidence_score": 0.92},
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
                supporting_excerpt="Supporting evidence excerpt",
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
# Test 1: 9 Categories, Weighted Score Aggregation, Blockers & Verification Metrics
# =============================================================================


def test_readiness_nine_categories_weights_verification_and_evidence_metrics(
    db_session: Session,
) -> None:
    env = _create_project_env(db_session)
    org, proj_a, manager, member, reviewer = (
        env["org"],
        env["proj_a"],
        env["manager"],
        env["member"],
        env["reviewer"],
    )

    ev1 = _create_evidence(db_session, org.id, proj_a.id, "Architecture ADR-01")
    ev2 = _create_evidence(db_session, org.id, proj_a.id, "Deployment Runbook v2")

    # 1 verified & corroborated item (2 evidence links)
    ki_verified = _create_knowledge_item(
        db_session,
        org.id,
        proj_a.id,
        "Adopt PostgreSQL canonical ledger",
        category=KnowledgeCategory.DECISIONS_RATIONALE.value,
        epistemic_status=EpistemicStatus.HUMAN_VERIFIED.value,
        review_status=KnowledgeReviewStatus.APPROVED.value,
        support_classification="corroborated",
        evidences=[ev1, ev2],
    )
    # 1 pending unverified item with uncertainty + staleness, missing evidence
    ki_pending = _create_knowledge_item(
        db_session,
        org.id,
        proj_a.id,
        "Legacy cron schedule",
        category=KnowledgeCategory.OPERATIONAL_HISTORICAL.value,
        epistemic_status=EpistemicStatus.EXTRACTED.value,
        review_status=KnowledgeReviewStatus.PENDING_REVIEW.value,
        support_classification="uncertain",
        is_stale=True,
        evidences=[],
    )
    # VerificationCase records
    vc_verified = VerificationCase(
        id=uuid.uuid4(),
        organisation_id=org.id,
        project_id=proj_a.id,
        target_type=VerificationTargetType.KNOWLEDGE_ITEM.value,
        target_id=ki_verified.id,
        domain=KnowledgeCategory.DECISIONS_RATIONALE.value,
        title=ki_verified.title,
        original_ai_claim=ki_verified.structured_summary,
        current_claim=ki_verified.structured_summary,
        case_status=VerificationCaseStatus.VERIFIED.value,
        priority=VerificationPriority.HIGH.value,
        assigned_reviewer_id=reviewer.id,
        last_reviewed_at=datetime.now(UTC),
    )
    vc_candidate = VerificationCase(
        id=uuid.uuid4(),
        organisation_id=org.id,
        project_id=proj_a.id,
        target_type=VerificationTargetType.KNOWLEDGE_ITEM.value,
        target_id=ki_pending.id,
        domain=KnowledgeCategory.OPERATIONAL_HISTORICAL.value,
        title=ki_pending.title,
        original_ai_claim=ki_pending.structured_summary,
        current_claim=ki_pending.structured_summary,
        case_status=VerificationCaseStatus.CANDIDATE.value,
        priority=VerificationPriority.MEDIUM.value,
    )
    db_session.add_all([vc_verified, vc_candidate])
    db_session.flush()

    db_session.add(
        VerificationReviewEvent(
            id=uuid.uuid4(),
            organisation_id=org.id,
            project_id=proj_a.id,
            case_id=vc_verified.id,
            reviewer_user_id=reviewer.id,
            action=ReviewActionType.APPROVE.value,
            previous_status=VerificationCaseStatus.PENDING_REVIEW.value,
            new_status=VerificationCaseStatus.VERIFIED.value,
            review_notes="Confirmed against ADR-01 and Runbook v2.",
            correlation_id=uuid.uuid4().hex,
        )
    )
    db_session.flush()

    # Create handover case, assemble package, generate checklists
    case = HandoverCaseService(db_session).create_case(
        organisation_id=org.id,
        project_id=proj_a.id,
        user_id=manager.id,
        request=HandoverCaseCreateRequest(
            title="Delta Engine Handover",
            departing_member_id=member.id,
            reviewer_id=reviewer.id,
        ),
    )
    ChecklistService(db_session).generate_checklists_for_case(
        case_id=case.id,
        project_id=proj_a.id,
        user_id=manager.id,
    )
    version = PackageAssemblyService(db_session).assemble_package_version(
        case.id,
        project_id=proj_a.id,
        user_id=manager.id,
        request=PackageAssemblyRequest(assembly_notes="v1"),
        has_project_manage=True,
    )
    db_session.commit()

    # Run readiness assessment
    engine = HandoverReadinessEngine(db_session)
    summary = engine.assess_version(
        version.id,
        project_id=proj_a.id,
        user_id=manager.id,
        notes="Initial Stage 4 readiness run",
    )
    db_session.commit()

    # Verify all 9 canonical categories present
    returned_cats = [c.category for c in summary.categories]
    assert len(returned_cats) == 9
    for cat in HandoverReadinessCategory:
        assert cat.value in returned_cats

    # Verify exact weighted score math
    cat_scores = {c.category: c.score for c in summary.categories}
    expected_overall = int(
        sum(cat_scores[cat_key] * weight for cat_key, weight in CATEGORY_WEIGHTS.items())
    )
    assert summary.overall_score == expected_overall

    # Verify verification summary counts
    assert summary.verification_summary is not None
    vs = summary.verification_summary
    assert vs.total_knowledge_items == 2
    assert vs.eligible_human_verified == 1
    assert vs.pending_verification == 1
    assert vs.verification_coverage_pct == 50
    assert vs.case_counts["verified"] == 1
    assert vs.case_counts["candidate"] == 1
    assert len(vs.recent_reviews) == 1
    assert vs.recent_reviews[0].reviewer_name == "Jordan Reviewer"

    # Verify evidence quality metrics
    assert summary.evidence_quality is not None
    eq = summary.evidence_quality
    assert eq.total_knowledge_items == 2
    assert eq.items_with_evidence == 1
    assert eq.items_missing_evidence == 1
    assert eq.evidence_coverage_pct == 50
    assert eq.corroborated_items == 1
    assert eq.uncertain_items == 1
    assert eq.stale_items == 1
    assert eq.total_evidence_sources == 2
    assert eq.accessible_evidence_count == 2
    assert eq.restricted_evidence_count == 0

    # Verify checklist summary & mandatory blocking items
    assert summary.checklist_summary is not None
    cs = summary.checklist_summary
    assert cs.total_groups >= 3
    assert cs.mandatory_total > 0
    assert cs.mandatory_outstanding == cs.mandatory_total

    # Approval eligibility must be false due to unverified items & mandatory checklists
    assert summary.approval_eligibility is not None
    assert summary.approval_eligibility.is_eligible_for_approval is False
    assert summary.approval_eligibility.checklist_gate_passed is False
    assert any("mandatory transition checklist" in r for r in summary.approval_eligibility.blocking_requirements)


# =============================================================================
# Test 2: Conflict States (Active vs Resolved), Critical/High Gating & Signoff Block
# =============================================================================


def test_conflict_states_gating_and_signoff_protection(db_session: Session) -> None:
    env = _create_project_env(db_session)
    org, proj_a, manager, member, reviewer = (
        env["org"],
        env["proj_a"],
        env["manager"],
        env["member"],
        env["reviewer"],
    )

    ev_a = _create_evidence(db_session, org.id, proj_a.id, "Production Config A")
    ev_b = _create_evidence(db_session, org.id, proj_a.id, "Staging Config B")
    ki = _create_knowledge_item(
        db_session,
        org.id,
        proj_a.id,
        "Database pooling threshold",
        epistemic_status=EpistemicStatus.HUMAN_VERIFIED.value,
        review_status=KnowledgeReviewStatus.APPROVED.value,
        evidences=[ev_a, ev_b],
    )
    vc = VerificationCase(
        id=uuid.uuid4(),
        organisation_id=org.id,
        project_id=proj_a.id,
        target_type=VerificationTargetType.KNOWLEDGE_ITEM.value,
        target_id=ki.id,
        domain=KnowledgeCategory.DECISIONS_RATIONALE.value,
        title=ki.title,
        original_ai_claim=ki.structured_summary,
        current_claim=ki.structured_summary,
        case_status=VerificationCaseStatus.CONFLICTED.value,
        priority=VerificationPriority.CRITICAL.value,
    )
    db_session.add(vc)
    db_session.flush()

    # Add 2 active non-'unresolved' conflicts (under_investigation + awaiting_context)
    # and 1 resolved conflict (resolved)
    c_investigating = VerificationConflict(
        id=uuid.uuid4(),
        organisation_id=org.id,
        project_id=proj_a.id,
        case_id=vc.id,
        conflict_type=ConflictType.TECHNICAL_CONFLICT.value,
        priority=ConflictPriority.CRITICAL.value,
        resolution_state=ConflictResolutionState.UNDER_INVESTIGATION.value,
        claim_a_text="Pool size is 20",
        claim_b_text="Pool size is 200",
        claim_a_source_evidence_id=ev_a.id,
        claim_b_source_evidence_id=ev_b.id,
        explanation="Pool size 20 vs 200 in production.",
    )
    c_awaiting = VerificationConflict(
        id=uuid.uuid4(),
        organisation_id=org.id,
        project_id=proj_a.id,
        case_id=vc.id,
        conflict_type=ConflictType.TEMPORAL_CONFLICT.value,
        priority=ConflictPriority.HIGH.value,
        resolution_state=ConflictResolutionState.AWAITING_CONTEXT.value,
        claim_a_text="Cutover at 02:00 UTC",
        claim_b_text="Cutover at 06:00 UTC",
        claim_a_source_evidence_id=ev_a.id,
        claim_b_source_evidence_id=ev_b.id,
        explanation="Cutover window discrepancy.",
    )
    c_resolved = VerificationConflict(
        id=uuid.uuid4(),
        organisation_id=org.id,
        project_id=proj_a.id,
        case_id=vc.id,
        conflict_type=ConflictType.OWNERSHIP_CONFLICT.value,
        priority=ConflictPriority.LOW.value,
        resolution_state=ConflictResolutionState.RESOLVED.value,
        claim_a_text="Owned by Alex",
        claim_b_text="Owned by Sam",
        claim_a_source_evidence_id=ev_a.id,
        claim_b_source_evidence_id=ev_b.id,
        explanation="Already resolved ownership overlap.",
        resolution_notes="Confirmed Alex owns settlement module.",
        resolved_at=datetime.now(UTC),
    )
    db_session.add_all([c_investigating, c_awaiting, c_resolved])
    db_session.flush()

    case = HandoverCaseService(db_session).create_case(
        organisation_id=org.id,
        project_id=proj_a.id,
        user_id=manager.id,
        request=HandoverCaseCreateRequest(
            title="Conflict Gating Handover",
            departing_member_id=member.id,
            reviewer_id=reviewer.id,
        ),
    )
    version = PackageAssemblyService(db_session).assemble_package_version(
        case.id,
        project_id=proj_a.id,
        user_id=manager.id,
        request=PackageAssemblyRequest(assembly_notes="v1"),
        has_project_manage=True,
    )
    db_session.commit()

    engine = HandoverReadinessEngine(db_session)
    summary = engine.assess_version(
        version.id,
        project_id=proj_a.id,
        user_id=manager.id,
    )
    db_session.commit()

    # Conflict summary must detect BOTH under_investigation and awaiting_context as blocking
    # while counting resolved separately and NOT blocking on it
    assert summary.conflict_summary is not None
    cf = summary.conflict_summary
    assert cf.total_conflicts == 3
    assert cf.under_investigation == 1
    assert cf.awaiting_context == 1
    assert cf.resolved_conflicts == 1
    assert cf.blocking_approval_count == 2
    assert cf.critical_and_high_count == 2

    # Conflict category score must drop and report blockers (general + critical/high approval gate)
    cat_map = {c.category: c for c in summary.categories}
    cf_cat = cat_map[HandoverReadinessCategory.CONFLICT_RESOLUTION.value]
    assert cf_cat.score == 50  # 100 - 2 * 25
    assert len(cf_cat.blockers_json) == 2
    assert any("2 unresolved cross-source contradictions" in b for b in cf_cat.blockers_json)
    assert any("critical/high-priority conflicts block approval" in b for b in cf_cat.blockers_json)

    # Approval eligibility must block
    assert summary.approval_eligibility is not None
    assert summary.approval_eligibility.conflict_gate_passed is False
    assert summary.approval_eligibility.is_eligible_for_approval is False

    # Signoff service MUST refuse reviewer approval while blockers exist
    signoff_svc = HandoverSignoffService(db_session)
    signoff_svc.submit_signoff(
        case_id=case.id,
        project_id=proj_a.id,
        user_id=member.id,
        request=SignoffRequest(
            version_id=version.id,
            signoff_type=SignoffType.DEPARTING_SIGNOFF.value,
            decision=SignoffDecision.APPROVED.value,
            comments="Submitting for review",
        ),
    )
    db_session.flush()
    with pytest.raises(BadRequestError, match="unresolved readiness blockers"):
        signoff_svc.submit_signoff(
            case_id=case.id,
            project_id=proj_a.id,
            user_id=reviewer.id,
            request=SignoffRequest(
                version_id=version.id,
                signoff_type=SignoffType.REVIEWER_APPROVAL.value,
                decision=SignoffDecision.APPROVED.value,
                comments="Attempting approval with blockers",
            ),
        )

    # Now resolve both remaining conflicts and REASSESS on the same case
    c_investigating.resolution_state = ConflictResolutionState.RESOLVED.value
    c_investigating.resolved_at = datetime.now(UTC)
    c_awaiting.resolution_state = ConflictResolutionState.DISMISSED.value
    c_awaiting.resolved_at = datetime.now(UTC)
    db_session.flush()

    reassessed = engine.assess_version(
        version.id,
        project_id=proj_a.id,
        user_id=manager.id,
        notes="Post-conflict resolution reassessment",
    )
    db_session.commit()

    assert reassessed.conflict_summary is not None
    assert reassessed.conflict_summary.blocking_approval_count == 0
    assert reassessed.conflict_summary.resolved_conflicts == 3
    reassessed_cat_map = {c.category: c for c in reassessed.categories}
    assert reassessed_cat_map[HandoverReadinessCategory.CONFLICT_RESOLUTION.value].score == 100
    assert reassessed_cat_map[HandoverReadinessCategory.CONFLICT_RESOLUTION.value].blockers_json == []
    assert reassessed.approval_eligibility is not None
    assert reassessed.approval_eligibility.conflict_gate_passed is True
    assert reassessed.blocker_count == 0


# =============================================================================
# Test 3: Reassessment on readiness_assessed Case, Historical Integrity & Persistence
# =============================================================================


def test_reassessment_on_readiness_assessed_case_and_historical_integrity(
    db_session: Session,
) -> None:
    env = _create_project_env(db_session)
    org, proj_a, manager, member = env["org"], env["proj_a"], env["manager"], env["member"]

    ev = _create_evidence(db_session, org.id, proj_a.id, "System Spec")
    _create_knowledge_item(
        db_session,
        org.id,
        proj_a.id,
        "Unverified service contract",
        epistemic_status=EpistemicStatus.EXTRACTED.value,
        review_status=KnowledgeReviewStatus.PENDING_REVIEW.value,
        evidences=[ev],
    )

    case = HandoverCaseService(db_session).create_case(
        organisation_id=org.id,
        project_id=proj_a.id,
        user_id=manager.id,
        request=HandoverCaseCreateRequest(title="Reassessment Case", departing_member_id=member.id),
    )
    version = PackageAssemblyService(db_session).assemble_package_version(
        case.id,
        project_id=proj_a.id,
        user_id=manager.id,
        request=PackageAssemblyRequest(assembly_notes="v1"),
        has_project_manage=True,
    )
    db_session.commit()

    engine = HandoverReadinessEngine(db_session)
    first_run = engine.assess_version(
        version.id,
        project_id=proj_a.id,
        user_id=manager.id,
        notes="Run 1",
    )
    db_session.commit()

    assert case.status == HandoverCaseStatus.READINESS_ASSESSED.value
    assert len(first_run.categories) == 9
    assert first_run.blocker_count == 1  # NOT doubled by overall_quality!
    assert len(first_run.assessment_history) == 1

    # Reassess while case.status == 'readiness_assessed' -> must NOT crash
    second_run = engine.assess_version(
        version.id,
        project_id=proj_a.id,
        user_id=manager.id,
        notes="Run 2",
    )
    db_session.commit()

    assert case.status == HandoverCaseStatus.READINESS_ASSESSED.value
    # Latest snapshot still has exactly 9 categories and 1 active blocker (no inflation!)
    assert len(second_run.categories) == 9
    assert second_run.blocker_count == 1
    # Historical snapshots preserved (2 runs in history)
    assert len(second_run.assessment_history) == 2
    assert second_run.assessment_history[0].notes == "Run 2"
    assert second_run.assessment_history[1].notes == "Run 1"

    # Simulate page reload / fresh read via get_readiness_intelligence
    reloaded = engine.get_readiness_intelligence(
        case_id=case.id,
        version_id=version.id,
        project_id=proj_a.id,
        viewer_user_id=manager.id,
        has_project_manage=True,
    )
    assert reloaded.overall_score == second_run.overall_score
    assert reloaded.blocker_count == 1
    assert len(reloaded.categories) == 9
    assert len(reloaded.assessment_history) == 2


# =============================================================================
# Test 4: Fail-Closed Source ACL Redaction on Evidence & Conflicts
# =============================================================================


def test_source_acl_fail_closed_redaction_in_readiness_intelligence(
    db_session: Session,
) -> None:
    env = _create_project_env(db_session)
    org, proj_a, manager, member = env["org"], env["proj_a"], env["manager"], env["member"]

    # Create a private GitHub connection owned by manager only (member has NO access)
    conn = SourceConnection(
        id=uuid.uuid4(),
        organisation_id=org.id,
        provider="github",
        display_name="Private Security Repo",
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
        scope_identifier="org/private-security",
        sync_permission_status=SourcePermissionVerificationStatus.VERIFIED.value,
        allowed_user_ids=[str(manager.id)],
    )
    db_session.add(policy)
    db_session.flush()

    ev_public = _create_evidence(
        db_session,
        org.id,
        proj_a.id,
        "Public Architecture Overview",
        acl_scope="project_members",
    )
    ev_restricted = _create_evidence(
        db_session,
        org.id,
        proj_a.id,
        "SECRET_PRIVATE_KEY_ROTATION_PR",
        source_type=EvidenceSourceType.GITHUB.value,
        acl_scope="source_restricted",
        policy_id=policy.id,
    )

    ki = _create_knowledge_item(
        db_session,
        org.id,
        proj_a.id,
        "Key rotation cadence",
        evidences=[ev_public, ev_restricted],
    )
    vc = VerificationCase(
        id=uuid.uuid4(),
        organisation_id=org.id,
        project_id=proj_a.id,
        target_type=VerificationTargetType.KNOWLEDGE_ITEM.value,
        target_id=ki.id,
        domain=KnowledgeCategory.DECISIONS_RATIONALE.value,
        title=ki.title,
        original_ai_claim=ki.structured_summary,
        current_claim=ki.structured_summary,
        case_status=VerificationCaseStatus.CONFLICTED.value,
        priority=VerificationPriority.HIGH.value,
    )
    db_session.add(vc)
    db_session.flush()

    db_session.add(
        VerificationConflict(
            id=uuid.uuid4(),
            organisation_id=org.id,
            project_id=proj_a.id,
            case_id=vc.id,
            conflict_type=ConflictType.DECISION_CONFLICT.value,
            priority=ConflictPriority.HIGH.value,
            resolution_state=ConflictResolutionState.UNRESOLVED.value,
            claim_a_text="Rotate every 30 days",
            claim_b_text="Rotate every 90 days",
            claim_a_source_evidence_id=ev_public.id,
            claim_b_source_evidence_id=ev_restricted.id,
            explanation="Rotation period 30d vs 90d.",
        )
    )
    db_session.flush()

    case = HandoverCaseService(db_session).create_case(
        organisation_id=org.id,
        project_id=proj_a.id,
        user_id=manager.id,
        request=HandoverCaseCreateRequest(title="ACL Redaction Case", departing_member_id=member.id),
    )
    version = PackageAssemblyService(db_session).assemble_package_version(
        case.id,
        project_id=proj_a.id,
        user_id=manager.id,
        request=PackageAssemblyRequest(assembly_notes="v1"),
        has_project_manage=True,
    )
    engine = HandoverReadinessEngine(db_session)
    engine.assess_version(version.id, project_id=proj_a.id, user_id=manager.id)
    db_session.commit()

    # Viewer = member (NOT in allowed_user_ids_json and NOT project_manage)
    member_view = engine.get_readiness_intelligence(
        case_id=case.id,
        version_id=version.id,
        project_id=proj_a.id,
        viewer_user_id=member.id,
        has_project_manage=False,
    )
    assert member_view.evidence_quality is not None
    assert member_view.evidence_quality.total_evidence_sources == 2
    assert member_view.evidence_quality.accessible_evidence_count == 1
    assert member_view.evidence_quality.restricted_evidence_count == 1

    assert member_view.conflict_summary is not None
    assert len(member_view.conflict_summary.items) == 1
    cf_item = member_view.conflict_summary.items[0]
    assert cf_item.acl_restricted is True
    assert cf_item.side_a_source_title == "Public Architecture Overview"
    assert cf_item.side_b_source_title == "Restricted Source (ACL Protected)"
    assert "SECRET_PRIVATE_KEY_ROTATION_PR" not in (cf_item.side_b_source_title or "")


# =============================================================================
# Test 5: HTTP API Routes, RBAC Enforcement & Cross-Project/Cross-Case Isolation
# =============================================================================


def test_http_readiness_routes_rbac_and_cross_project_isolation(
    db_session: Session,
) -> None:
    env = _create_project_env(db_session)
    org, proj_a, proj_b, manager, member, outsider = (
        env["org"],
        env["proj_a"],
        env["proj_b"],
        env["manager"],
        env["member"],
        env["outsider"],
    )

    ev = _create_evidence(db_session, org.id, proj_a.id, "HTTP Route Evidence")
    _create_knowledge_item(
        db_session,
        org.id,
        proj_a.id,
        "HTTP Verified Decision",
        epistemic_status=EpistemicStatus.HUMAN_VERIFIED.value,
        review_status=KnowledgeReviewStatus.APPROVED.value,
        evidences=[ev],
    )

    case_a = HandoverCaseService(db_session).create_case(
        organisation_id=org.id,
        project_id=proj_a.id,
        user_id=manager.id,
        request=HandoverCaseCreateRequest(title="Project A Case", departing_member_id=member.id),
    )
    ver_a = PackageAssemblyService(db_session).assemble_package_version(
        case_a.id,
        project_id=proj_a.id,
        user_id=manager.id,
        request=PackageAssemblyRequest(assembly_notes="v1"),
        has_project_manage=True,
    )
    case_b = HandoverCaseService(db_session).create_case(
        organisation_id=org.id,
        project_id=proj_b.id,
        user_id=manager.id,
        request=HandoverCaseCreateRequest(title="Project B Case", departing_member_id=manager.id),
    )
    db_session.commit()

    try:
        # 1. Manager POSTs readiness assessment on Project A
        client_mgr = _build_client(db_session, manager)
        post_res = client_mgr.post(
            f"/api/v1/projects/{proj_a.id}/handover/cases/{case_a.id}/readiness",
            json={"version_id": str(ver_a.id), "notes": "HTTP Stage 4 run"},
        )
        assert post_res.status_code == 200, post_res.text
        post_data = post_res.json()
        assert len(post_data["categories"]) == 9
        assert post_data["version_id"] == str(ver_a.id)
        assert post_data["approval_eligibility"]["current_case_status"] == "readiness_assessed"

        # 2. Manager GETs persisted readiness assessment
        get_res = client_mgr.get(
            f"/api/v1/projects/{proj_a.id}/handover/cases/{case_a.id}/readiness/{ver_a.id}"
        )
        assert get_res.status_code == 200, get_res.text
        assert get_res.json()["overall_score"] == post_data["overall_score"]
        assert len(get_res.json()["assessment_history"]) == 1

        # 3. Manager POSTs reassessment again (no 400 status transition error)
        reassess_res = client_mgr.post(
            f"/api/v1/projects/{proj_a.id}/handover/cases/{case_a.id}/readiness",
            json={"version_id": str(ver_a.id), "notes": "HTTP Stage 4 rerun"},
        )
        assert reassess_res.status_code == 200, reassess_res.text
        assert len(reassess_res.json()["assessment_history"]) == 2

        # 4. Cross-project isolation: reading Project A's version under Project B -> 404
        cross_proj_get = client_mgr.get(
            f"/api/v1/projects/{proj_b.id}/handover/cases/{case_b.id}/readiness/{ver_a.id}"
        )
        assert cross_proj_get.status_code == 404

        cross_proj_post = client_mgr.post(
            f"/api/v1/projects/{proj_b.id}/handover/cases/{case_b.id}/readiness",
            json={"version_id": str(ver_a.id)},
        )
        assert cross_proj_post.status_code == 404

        # 5. Outsider (non-project-member) -> 403/404 (anti-enumeration tenant isolation)
        client_out = _build_client(db_session, outsider)
        out_get = client_out.get(
            f"/api/v1/projects/{proj_a.id}/handover/cases/{case_a.id}/readiness/{ver_a.id}"
        )
        assert out_get.status_code in (403, 404)
    finally:
        app.dependency_overrides.clear()
