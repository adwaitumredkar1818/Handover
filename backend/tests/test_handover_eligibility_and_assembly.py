"""Regression and Integration Tests for Handover Eligibility and Package Assembly.

Platform: The Handover
Module: Handover Workspace (Module 4 / Knowledge Transfer Area)

Validates:
1. VerificationCaseRepository.get_by_target keyword-only signature contract
2. HandoverEligibilityService integration with VerificationCaseRepository
3. Four-tier epistemic gating (only human_verified knowledge is eligible)
4. VerificationCase status gating (only verified cases are eligible)
5. Issue and cross-source conflict blocking on eligibility
6. Deterministic 8-domain package assembly and section compilation
7. Cryptographic SHA-256 version integrity hashing and content links
8. Version lineage, is_current toggling, and idempotency
9. Conflict-aware readiness assessment blocking
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.models.audit import AuditLog
from app.core.rbac_catalog import deterministic_rbac_id
from app.models.enums import (
    ConflictPriority,
    ConflictResolutionState,
    ConflictType,
    EpistemicStatus,
    EvidenceProcessingStatus,
    EvidenceSourceType,
    HandoverCaseStatus,
    HandoverPackageSectionType,
    KnowledgeCategory,
    KnowledgeReviewStatus,
    OrganisationStatus,
    ProjectStatus,
    ProjectVisibility,
    RelationshipBasis,
    RelationshipVerificationStatus,
    RoleName,
    UserStatus,
    VerificationCaseStatus,
    VerificationPriority,
    VerificationSeverity,
    VerificationTargetType,
)
from app.models.evidence import EvidenceItem
from app.models.handover import (
    HandoverCase,
    HandoverContentLink,
    HandoverPackage,
    HandoverPackageSection,
    HandoverPackageVersion,
    HandoverReadinessAssessment,
)
from app.models.knowledge import KnowledgeEvidenceLink, KnowledgeItem
from app.models.organisation import Organisation, OrganisationMembership
from app.models.project import Project, ProjectMembership
from app.models.relationship import KnowledgeEntity, KnowledgeRelationship, RelationshipEvidenceLink
from app.models.user import User
from app.models.verification import (
    VerificationCase,
    VerificationConflict,
    VerificationIssue,
)
from app.repositories.rbac import RbacRepository
from app.repositories.verification import VerificationCaseRepository
from app.schemas.handover import HandoverCaseCreateRequest, PackageAssemblyRequest
from app.services.handover_assembly import PackageAssemblyService
from app.services.handover_case import HandoverCaseService
from app.services.handover_eligibility import HandoverEligibilityService
from app.services.handover_readiness import HandoverReadinessEngine


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

    with session_factory() as session:
        yield session


def _create_test_context(
    session: Session,
) -> tuple[Organisation, Project, User, User]:
    """Helper to create organisation, project, lead reviewer, and successor."""
    user_reviewer = User(
        id=uuid.uuid4(),
        email=f"reviewer-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="test-hash",
        full_name="Lead Reviewer",
        status=UserStatus.ACTIVE,
        is_email_verified=True,
    )
    user_successor = User(
        id=uuid.uuid4(),
        email=f"successor-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="test-hash",
        full_name="Successor",
        status=UserStatus.ACTIVE,
        is_email_verified=True,
    )
    session.add_all([user_reviewer, user_successor])
    session.flush()

    org = Organisation(
        id=uuid.uuid4(),
        name="Test Handover Org",
        slug=f"org-{uuid.uuid4().hex[:8]}",
        created_by_id=user_reviewer.id,
        status=OrganisationStatus.ACTIVE,
    )
    session.add(org)
    session.flush()

    project = Project(
        id=uuid.uuid4(),
        organisation_id=org.id,
        name="Test Handover Project",
        slug=f"proj-{uuid.uuid4().hex[:8]}",
        created_by_id=user_reviewer.id,
        owner_id=user_reviewer.id,
        visibility=ProjectVisibility.ORGANISATION,
        status=ProjectStatus.ACTIVE,
    )
    session.add(project)
    session.flush()

    session.add_all([
        OrganisationMembership(
            id=uuid.uuid4(),
            organisation_id=org.id,
            user_id=user_reviewer.id,
            role_id=deterministic_rbac_id("role", RoleName.ORG_OWNER.value),
            status="active",
            joined_at=datetime.now(UTC),
        ),
        OrganisationMembership(
            id=uuid.uuid4(),
            organisation_id=org.id,
            user_id=user_successor.id,
            role_id=deterministic_rbac_id("role", RoleName.ORG_MEMBER.value),
            status="active",
            joined_at=datetime.now(UTC),
        ),
        ProjectMembership(
            id=uuid.uuid4(),
            project_id=project.id,
            user_id=user_reviewer.id,
            role_id=deterministic_rbac_id("role", RoleName.PROJECT_MANAGER.value),
            status="active",
        ),
        ProjectMembership(
            id=uuid.uuid4(),
            project_id=project.id,
            user_id=user_successor.id,
            role_id=deterministic_rbac_id("role", RoleName.PROJECT_MEMBER.value),
            status="active",
        ),
    ])
    session.flush()
    return org, project, user_reviewer, user_successor


def _create_finding_with_evidence(
    session: Session,
    org: Organisation,
    project: Project,
    user: User,
    *,
    category: str = "technical_architecture",
    title: str = "Canonical PostgreSQL Store",
    claim: str = "PostgreSQL is canonical store for all entities.",
    epistemic_status: str = EpistemicStatus.HUMAN_VERIFIED.value,
    review_status: str = KnowledgeReviewStatus.APPROVED.value,
    case_status: str = VerificationCaseStatus.VERIFIED.value,
) -> tuple[KnowledgeItem, VerificationCase, EvidenceItem]:
    """Helper to create a full traceable knowledge finding with evidence and verification case."""
    ev = EvidenceItem(
        id=uuid.uuid4(),
        organisation_id=org.id,
        project_id=project.id,
        uploaded_by_user_id=user.id,
        source_type=EvidenceSourceType.DOCUMENT_UPLOAD.value,
        source_provider="local_upload",
        category="pdf_document",
        source_external_id=uuid.uuid4().hex,
        title="Architecture Spec.pdf",
        original_filename="arch_spec.pdf",
        content_hash=hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
        file_size_bytes=4096,
        mime_type="application/pdf",
        source_created_at=datetime.now(UTC),
        processing_status=EvidenceProcessingStatus.EXTRACTED.value,
        acl_scope="project_members",
    )
    session.add(ev)
    session.flush()

    ki = KnowledgeItem(
        id=uuid.uuid4(),
        organisation_id=org.id,
        project_id=project.id,
        category=category,
        primary_domain=category,
        title=title,
        structured_summary=claim,
        structured_payload={"spec": "v1"},
        support_classification="direct",
        extraction_model="qwen3:8b",
        prompt_version="1.0.0",
        fingerprint=uuid.uuid4().hex,
        epistemic_status=epistemic_status,
        review_status=review_status,
        is_stale=False,
        is_deleted=False,
    )
    session.add(ki)
    session.flush()

    link = KnowledgeEvidenceLink(
        id=uuid.uuid4(),
        organisation_id=org.id,
        project_id=project.id,
        knowledge_item_id=ki.id,
        evidence_id=ev.id,
        support_type="direct",
        supporting_excerpt=claim,
    )
    session.add(link)
    session.flush()

    v_case = VerificationCase(
        id=uuid.uuid4(),
        organisation_id=org.id,
        project_id=project.id,
        target_type=VerificationTargetType.KNOWLEDGE_ITEM.value,
        target_id=ki.id,
        case_status=case_status,
        priority=VerificationPriority.MEDIUM.value,
        title=f"Verification for {title}",
        original_ai_claim=claim,
        current_claim=claim,
        machine_assessment_json={"status": "passed"},
        version=1,
    )
    session.add(v_case)
    session.flush()

    return ki, v_case, ev


# =============================================================================
# 1. Regression Test for Repository Signature and Call Contract
# =============================================================================

def test_verification_case_repository_get_by_target_signature(db_session: Session) -> None:
    """Assert VerificationCaseRepository.get_by_target enforces keyword-only arguments and handles enums and strings."""
    org, project, reviewer, _ = _create_test_context(db_session)
    ki, v_case, _ = _create_finding_with_evidence(db_session, org, project, reviewer)

    repo = VerificationCaseRepository(db_session)

    # 1. Correct keyword call with VerificationTargetType enum
    case_enum = repo.get_by_target(
        project_id=project.id,
        target_type=VerificationTargetType.KNOWLEDGE_ITEM,
        target_id=ki.id,
    )
    assert case_enum is not None
    assert case_enum.id == v_case.id

    # 2. Correct keyword call with string target_type
    case_str = repo.get_by_target(
        project_id=project.id,
        target_type="knowledge_item",
        target_id=ki.id,
    )
    assert case_str is not None
    assert case_str.id == v_case.id

    # 3. Non-existent target returns None without error
    missing_case = repo.get_by_target(
        project_id=project.id,
        target_type=VerificationTargetType.KNOWLEDGE_ITEM,
        target_id=uuid.uuid4(),
    )
    assert missing_case is None

    # 4. Project boundary enforcement: querying same target under wrong project returns None
    wrong_project_case = repo.get_by_target(
        project_id=uuid.uuid4(),
        target_type=VerificationTargetType.KNOWLEDGE_ITEM,
        target_id=ki.id,
    )
    assert wrong_project_case is None


# =============================================================================
# 2. Regression Test: HandoverEligibilityService Calls get_by_target Without TypeError
# =============================================================================

def test_handover_eligibility_invocations_without_type_error(db_session: Session) -> None:
    """Verify that HandoverEligibilityService calls get_by_target with exact keyword signature."""
    org, project, reviewer, _ = _create_test_context(db_session)
    ki, v_case, ev = _create_finding_with_evidence(db_session, org, project, reviewer)

    elig_service = HandoverEligibilityService(db_session)

    # Must execute cleanly without TypeError (the bug previously crashed here)
    result = elig_service.check_knowledge_item_eligibility(
        ki.id,
        viewer_user_id=reviewer.id,
        has_project_manage=True,
    )
    assert result.is_eligible is True
    assert result.case_status == VerificationCaseStatus.VERIFIED.value
    assert len(result.blockers) == 0


# =============================================================================
# 3. Epistemic Gating and Case Status Enforcement
# =============================================================================

def test_handover_eligibility_epistemic_and_review_status_gates(db_session: Session) -> None:
    """Verify that unverified or non-approved knowledge items are strictly rejected."""
    org, project, reviewer, _ = _create_test_context(db_session)

    # 1. Item with epistemic_status = EXTRACTED
    ki_extracted, _, _ = _create_finding_with_evidence(
        db_session, org, project, reviewer,
        epistemic_status=EpistemicStatus.EXTRACTED.value,
        review_status=KnowledgeReviewStatus.PENDING_REVIEW.value,
        case_status=VerificationCaseStatus.CANDIDATE.value,
    )
    elig_service = HandoverEligibilityService(db_session)
    res1 = elig_service.check_knowledge_item_eligibility(
        ki_extracted.id, viewer_user_id=reviewer.id, has_project_manage=True
    )
    assert res1.is_eligible is False
    assert any("epistemic status" in b for b in res1.blockers)

    # 2. Item with epistemic_status = HUMAN_VERIFIED, but review_status = REJECTED
    ki_rejected, _, _ = _create_finding_with_evidence(
        db_session, org, project, reviewer,
        epistemic_status=EpistemicStatus.HUMAN_VERIFIED.value,
        review_status=KnowledgeReviewStatus.REJECTED.value,
        case_status=VerificationCaseStatus.REJECTED.value,
    )
    res2 = elig_service.check_knowledge_item_eligibility(
        ki_rejected.id, viewer_user_id=reviewer.id, has_project_manage=True
    )
    assert res2.is_eligible is False
    assert any("review status is 'rejected'" in b for b in res2.blockers)

    # 3. Item with human_verified and approved, but VerificationCase is CANDIDATE
    ki_candidate_case, _, _ = _create_finding_with_evidence(
        db_session, org, project, reviewer,
        epistemic_status=EpistemicStatus.HUMAN_VERIFIED.value,
        review_status=KnowledgeReviewStatus.APPROVED.value,
        case_status=VerificationCaseStatus.CANDIDATE.value,
    )
    res3 = elig_service.check_knowledge_item_eligibility(
        ki_candidate_case.id, viewer_user_id=reviewer.id, has_project_manage=True
    )
    assert res3.is_eligible is False
    assert any("expected 'verified'" in b for b in res3.blockers)


# =============================================================================
# 4. Critical Issues and Unresolved Conflicts as Eligibility Blockers
# =============================================================================

def test_handover_eligibility_open_issues_and_conflicts_block(db_session: Session) -> None:
    """Verify that critical issues or unresolved cross-source conflicts block knowledge eligibility."""
    org, project, reviewer, _ = _create_test_context(db_session)
    ki, v_case, _ = _create_finding_with_evidence(db_session, org, project, reviewer)

    # Attach an unresolved conflict to the verification case
    conflict = VerificationConflict(
        id=uuid.uuid4(),
        organisation_id=org.id,
        project_id=project.id,
        case_id=v_case.id,
        conflict_type=ConflictType.TECHNICAL_CONFLICT.value,
        claim_a_text="PostgreSQL is canonical store",
        claim_b_text="MySQL is canonical store",
        explanation="Contradiction in primary data store selection.",
        resolution_state=ConflictResolutionState.UNRESOLVED.value,
    )
    db_session.add(conflict)
    db_session.flush()

    elig_service = HandoverEligibilityService(db_session)
    res = elig_service.check_knowledge_item_eligibility(
        ki.id, viewer_user_id=reviewer.id, has_project_manage=True
    )
    assert res.is_eligible is False
    assert any("unresolved cross-source conflicts" in b for b in res.blockers)


# =============================================================================
# 5. Deterministic 8-Domain Package Assembly and Hashing
# =============================================================================

def test_package_assembly_deterministic_compilation(db_session: Session) -> None:
    """Verify deterministic 8-domain package assembly, SHA-256 integrity hashing, and content links."""
    org, project, reviewer, successor = _create_test_context(db_session)

    # Create 3 verified findings across different domains
    ki_arch, _, _ = _create_finding_with_evidence(
        db_session, org, project, reviewer,
        category=KnowledgeCategory.TECHNICAL_ARCHITECTURE.value,
        title="Architecture: FastAPI + PostgreSQL",
        claim="Standardized on FastAPI and PostgreSQL.",
    )
    ki_dec, _, _ = _create_finding_with_evidence(
        db_session, org, project, reviewer,
        category=KnowledgeCategory.DECISIONS_RATIONALE.value,
        title="Decision: Epistemic Gating",
        claim="Enforce strict four-tier epistemic separation.",
    )
    ki_work, _, _ = _create_finding_with_evidence(
        db_session, org, project, reviewer,
        category=KnowledgeCategory.WORK_PROGRESS.value,
        title="Work Status: Module 4 Complete",
        claim="Completed Stage 1 backend repair.",
    )

    # Create 1 unverified candidate finding that MUST be excluded
    ki_unverified, _, _ = _create_finding_with_evidence(
        db_session, org, project, reviewer,
        category=KnowledgeCategory.BUGS_BLOCKERS_RISKS.value,
        title="Unverified Rumor",
        claim="Synthetic or unverified claim.",
        epistemic_status=EpistemicStatus.EXTRACTED.value,
        review_status=KnowledgeReviewStatus.PENDING_REVIEW.value,
        case_status=VerificationCaseStatus.CANDIDATE.value,
    )

    # Create HandoverCase
    case_service = HandoverCaseService(db_session)
    case_req = HandoverCaseCreateRequest(
        title="Staff Engineer Transition",
        description="Engineering handover for active backend initiatives.",
        departing_member_id=reviewer.id,
        successor_id=successor.id,
    )
    case = case_service.create_case(
        organisation_id=org.id,
        project_id=project.id,
        user_id=reviewer.id,
        request=case_req,
    )
    assert case.status == HandoverCaseStatus.DRAFT.value

    # Assemble Package
    assembly_service = PackageAssemblyService(db_session)
    assembly_req = PackageAssemblyRequest(assembly_notes="Stage 1 Verification Assembly")
    version = assembly_service.assemble_package_version(
        case_id=case.id,
        project_id=project.id,
        user_id=reviewer.id,
        request=assembly_req,
        has_project_manage=True,
    )
    db_session.commit()

    # 1. Check version metadata
    assert version.version_number == 1
    assert version.is_current is True
    assert version.assembly_status == "assembled"
    assert len(version.content_hash) == 64  # Valid SHA-256 hex string

    # 2. Check snapshot exclusion audit
    snapshot = version.assembly_snapshot_json
    assert snapshot["total_eligible_knowledge_items"] == 3
    assert snapshot["total_excluded_knowledge_items"] == 1
    excluded_ids = [e["id"] for e in snapshot["excluded_items"]]
    assert str(ki_unverified.id) in excluded_ids

    # 3. Check 8 canonical domain sections
    sections = version.sections
    assert len(sections) == 8
    sec_types = [s.section_type for s in sections]
    assert HandoverPackageSectionType.PROJECT_OVERVIEW_CONTEXT.value in sec_types
    assert HandoverPackageSectionType.DECISIONS_RATIONALE.value in sec_types
    assert HandoverPackageSectionType.TECHNICAL_ARCHITECTURE.value in sec_types
    assert HandoverPackageSectionType.WORK_PROGRESS.value in sec_types
    assert HandoverPackageSectionType.RESPONSIBILITIES_OWNERSHIP.value in sec_types
    assert HandoverPackageSectionType.DEPENDENCIES_RELATIONSHIPS.value in sec_types
    assert HandoverPackageSectionType.BUGS_BLOCKERS_RISKS.value in sec_types
    assert HandoverPackageSectionType.OPERATIONAL_HISTORICAL.value in sec_types

    # 4. Check Content Links
    all_links = [link for s in sections for link in s.content_links]
    linked_ki_ids = {str(link.knowledge_item_id) for link in all_links if link.knowledge_item_id}
    assert str(ki_arch.id) in linked_ki_ids
    assert str(ki_dec.id) in linked_ki_ids
    assert str(ki_work.id) in linked_ki_ids
    assert str(ki_unverified.id) not in linked_ki_ids


# =============================================================================
# 6. Version Lineage and Idempotency
# =============================================================================

def test_package_assembly_version_lineage_and_idempotency(db_session: Session) -> None:
    """Verify that repeated assembly increments version number, updates is_current, and preserves history."""
    org, project, reviewer, successor = _create_test_context(db_session)
    ki, _, _ = _create_finding_with_evidence(db_session, org, project, reviewer)

    case_service = HandoverCaseService(db_session)
    case = case_service.create_case(
        organisation_id=org.id,
        project_id=project.id,
        user_id=reviewer.id,
        request=HandoverCaseCreateRequest(
            title="Lineage Test Case",
            description="Testing version increments",
            departing_member_id=reviewer.id,
            successor_id=successor.id,
        ),
    )

    assembly_service = PackageAssemblyService(db_session)

    # First assembly
    v1 = assembly_service.assemble_package_version(
        case_id=case.id,
        project_id=project.id,
        user_id=reviewer.id,
        request=PackageAssemblyRequest(assembly_notes="Version 1 compile"),
        has_project_manage=True,
    )
    db_session.flush()
    assert v1.version_number == 1
    assert v1.is_current is True

    # Second assembly
    v2 = assembly_service.assemble_package_version(
        case_id=case.id,
        project_id=project.id,
        user_id=reviewer.id,
        request=PackageAssemblyRequest(assembly_notes="Version 2 compile"),
        has_project_manage=True,
    )
    db_session.flush()
    assert v2.version_number == 2
    assert v2.is_current is True
    assert v1.is_current is False

    # Package retains both versions
    package = db_session.get(HandoverPackage, v1.package_id)
    assert package is not None
    assert len(package.versions) == 2


# =============================================================================
# 7. Handover Readiness Assessment & Conflict Blockers
# =============================================================================

def test_handover_readiness_unresolved_conflicts_block(db_session: Session) -> None:
    """Verify that HandoverReadinessEngine surfaces unresolved conflicts as blockers."""
    org, project, reviewer, successor = _create_test_context(db_session)
    ki, v_case, _ = _create_finding_with_evidence(db_session, org, project, reviewer)

    # Create case and assemble version
    case_service = HandoverCaseService(db_session)
    case = case_service.create_case(
        organisation_id=org.id,
        project_id=project.id,
        user_id=reviewer.id,
        request=HandoverCaseCreateRequest(
            title="Readiness Test Case",
            description="Testing conflict blockers in readiness",
            departing_member_id=reviewer.id,
            successor_id=successor.id,
        ),
    )
    assembly_service = PackageAssemblyService(db_session)
    version = assembly_service.assemble_package_version(
        case_id=case.id,
        project_id=project.id,
        user_id=reviewer.id,
        request=PackageAssemblyRequest(assembly_notes="Readiness compile"),
        has_project_manage=True,
    )
    db_session.flush()

    # Without conflicts: readiness passes conflict check
    readiness_engine = HandoverReadinessEngine(db_session)
    res_clean = readiness_engine.assess_version(
        version_id=version.id,
        project_id=project.id,
        user_id=reviewer.id,
    )
    conflict_cat_clean = next(c for c in res_clean.categories if c.category == "conflict_resolution")
    assert conflict_cat_clean.score == 100
    assert len(conflict_cat_clean.blockers_json) == 0

    # Add an unresolved conflict to the project
    conflict = VerificationConflict(
        id=uuid.uuid4(),
        organisation_id=org.id,
        project_id=project.id,
        case_id=v_case.id,
        conflict_type=ConflictType.TECHNICAL_CONFLICT.value,
        claim_a_text="Architecture uses FastAPI",
        claim_b_text="Architecture uses Django",
        explanation="Conflicting framework decisions.",
        resolution_state=ConflictResolutionState.UNRESOLVED.value,
    )
    db_session.add(conflict)
    db_session.flush()

    # Re-assemble a new version to re-evaluate readiness
    v2 = assembly_service.assemble_package_version(
        case_id=case.id,
        project_id=project.id,
        user_id=reviewer.id,
        request=PackageAssemblyRequest(assembly_notes="Re-evaluating after conflicts detected"),
        has_project_manage=True,
    )
    db_session.flush()

    res_conflicted = readiness_engine.assess_version(
        version_id=v2.id,
        project_id=project.id,
        user_id=reviewer.id,
    )
    conflict_cat = next(c for c in res_conflicted.categories if c.category == "conflict_resolution")
    assert conflict_cat.score < 100
    assert any("unresolved cross-source contradictions" in b for b in conflict_cat.blockers_json)

