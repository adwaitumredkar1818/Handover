"""Stage 3 Tests: Canonical Eight-Domain Handover Sections, Provenance & Version Integrity.

Platform: The Handover
Module: Handover Workspace (Module 4 / Knowledge Transfer Area)

Covers:
1. Retrieval of all eight canonical sections in strict order (1..8)
2. Correct handover case association (rejects mismatched case_id)
3. Correct package version association & historical version immutability (v1 vs v2)
4. Empty sections with transparent epistemic breakdown (no fabricated content)
5. Missing sections reporting via missing_section_types
6. API NotFound / error handling
7. Evidence provenance hydration (source type, name, ref, excerpt, timestamps)
8. Fail-closed read-time source ACL enforcement on restricted evidence
9. Human verification attribution (VerificationCase + VerificationReviewEvent)
10. Epistemic & conflict separation (unresolved vs resolved conflicts never upgraded)
11. Secret/credential redaction in Domain 8 operational procedures
12. Project-level RBAC access restrictions & cross-project leakage prevention
13. Read-only guarantee (reading sections never mutates package or SHA-256 hash)
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
from app.core.exceptions import NotFoundError
from app.core.rbac_catalog import deterministic_rbac_id
from app.main import app
from app.services.rbac import RbacService
from app.models import Base
from app.models.enums import (
    ConflictPriority,
    ConflictResolutionState,
    ConflictType,
    EpistemicStatus,
    EvidenceProcessingStatus,
    EvidenceSourceType,
    HandoverPackageSectionType,
    KnowledgeCategory,
    KnowledgeReviewStatus,
    OrganisationStatus,
    ProjectStatus,
    ProjectVisibility,
    RelationshipBasis,
    RelationshipVerificationStatus,
    ReviewActionType,
    RoleName,
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
from app.models.relationship import (
    KnowledgeEntity,
    KnowledgeRelationship,
    RelationshipEvidenceLink,
)
from app.models.user import User
from app.models.verification import (
    VerificationCase,
    VerificationConflict,
    VerificationReviewEvent,
)
from app.repositories.rbac import RbacRepository
from app.repositories.user import UserRepository
from app.schemas.handover import HandoverCaseCreateRequest, PackageAssemblyRequest
from app.services.handover_assembly import PackageAssemblyService, SECTION_ORDER
from app.services.handover_case import HandoverCaseService
from app.services.handover_sections import HandoverSectionReadService, redact_secrets


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
    manager = _create_user(session, "manager@stage3-test.local", "Alex Manager")
    member = _create_user(session, "member@stage3-test.local", "Sam Engineer")
    outsider = _create_user(session, "outsider@stage3-test.local", "Pat Outsider")

    org = Organisation(
        id=uuid.uuid4(),
        name="Stage 3 Test Org",
        slug=f"stage3-org-{uuid.uuid4().hex[:8]}",
        status=OrganisationStatus.ACTIVE.value,
        created_by_id=manager.id,
    )
    session.add(org)
    session.flush()

    for usr in (manager, member):
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
        name="Alpha Payments Service",
        slug=f"alpha-{uuid.uuid4().hex[:6]}",
        description="Core payment settlement service and ledger reconciliation pipeline.",
        status=ProjectStatus.ACTIVE.value,
        visibility=ProjectVisibility.PRIVATE.value,
        created_by_id=manager.id,
        owner_id=manager.id,
    )
    proj_b = Project(
        id=uuid.uuid4(),
        organisation_id=org.id,
        name="Beta Analytics Warehouse",
        slug=f"beta-{uuid.uuid4().hex[:6]}",
        description="Isolated project B for cross-project leakage testing.",
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
            responsibility_description="Release management & architecture sign-off",
        ),
        ProjectMembership(
            id=uuid.uuid4(),
            project_id=proj_a.id,
            user_id=member.id,
            role_id=deterministic_rbac_id("role", RoleName.PROJECT_MEMBER.value),
            status="active",
            responsibility_description="Settlement worker maintenance",
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
    author: str = "Alex Manager",
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
        source_url="https://github.com/org/alpha/pull/42" if source_type == EvidenceSourceType.GITHUB.value else None,
        source_author_identity=author,
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


def _create_verified_ki(
    session: Session,
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    reviewer: User,
    category: str,
    title: str,
    summary: str,
    evidence: EvidenceItem | None = None,
    *,
    excerpt: str = "Supporting verbatim excerpt from authorised specification.",
    structured_payload: dict[str, Any] | None = None,
) -> KnowledgeItem:
    ki = KnowledgeItem(
        id=uuid.uuid4(),
        organisation_id=org_id,
        project_id=project_id,
        category=category,
        epistemic_status=EpistemicStatus.HUMAN_VERIFIED.value,
        review_status=KnowledgeReviewStatus.APPROVED.value,
        support_classification="direct",
        title=title,
        structured_summary=summary,
        structured_payload=structured_payload or {"rationale": "Confirmed by engineering review"},
        extraction_model="qwen3:8b",
        prompt_version="v1",
        fingerprint=hashlib.sha256(f"{title}-{uuid.uuid4()}".encode()).hexdigest(),
        confidence_metadata_json={"confidence_score": 0.94},
    )
    session.add(ki)
    session.flush()

    if evidence:
        session.add(
            KnowledgeEvidenceLink(
                id=uuid.uuid4(),
                organisation_id=org_id,
                project_id=project_id,
                knowledge_item_id=ki.id,
                evidence_id=evidence.id,
                support_type="direct",
                supporting_excerpt=excerpt,
                excerpt_verified=True,
            )
        )

    vc = VerificationCase(
        id=uuid.uuid4(),
        organisation_id=org_id,
        project_id=project_id,
        target_type=VerificationTargetType.KNOWLEDGE_ITEM.value,
        target_id=ki.id,
        domain=category,
        title=title,
        original_ai_claim=summary,
        current_claim=summary,
        case_status=VerificationCaseStatus.VERIFIED.value,
        priority=VerificationPriority.MEDIUM.value,
        assigned_reviewer_id=reviewer.id,
        last_reviewed_at=datetime.now(UTC),
    )
    session.add(vc)
    session.flush()

    session.add(
        VerificationReviewEvent(
            id=uuid.uuid4(),
            organisation_id=org_id,
            project_id=project_id,
            case_id=vc.id,
            reviewer_user_id=reviewer.id,
            action=ReviewActionType.APPROVE.value,
            previous_status=VerificationCaseStatus.CANDIDATE.value,
            new_status=VerificationCaseStatus.VERIFIED.value,
            review_notes="Verified against architecture specification.",
            correlation_id=uuid.uuid4().hex,
        )
    )
    session.flush()
    return ki


def test_eight_canonical_sections_ordering_provenance_and_verification(db_session: Session) -> None:
    """Tests 1, 3, 4, 8, 9: All 8 canonical sections returned in order with hydrated provenance & verification."""
    env = _create_project_env(db_session)
    org, proj_a, manager, member = env["org"], env["proj_a"], env["manager"], env["member"]

    ev_spec = _create_evidence(db_session, org.id, proj_a.id, "Alpha Payments Architecture Spec.docx")
    ev_pr = _create_evidence(
        db_session,
        org.id,
        proj_a.id,
        "PR #42: PostgreSQL Idempotency Ledger",
        source_type=EvidenceSourceType.GITHUB.value,
    )

    # Create verified findings across multiple domains + 1 operational procedure containing a secret token to test redaction
    _create_verified_ki(
        db_session, org.id, proj_a.id, manager,
        KnowledgeCategory.DECISIONS_RATIONALE.value,
        "Use PostgreSQL Advisory Locks for Ledger Settlement",
        "Advisory locks prevent concurrent double-settlement without introducing Redis.",
        ev_pr,
        excerpt="ADR-004: Chosen PostgreSQL advisory locks for atomic ledger settlement.",
    )
    _create_verified_ki(
        db_session, org.id, proj_a.id, manager,
        KnowledgeCategory.OPERATIONAL_HISTORICAL.value,
        "Production Settlement Worker Restart Procedure",
        "Run `systemctl restart alpha-worker`. Never commit token ghp_1234567890abcdef1234567890abcdef1234 or password=SuperSecretPassword123.",
        ev_spec,
        excerpt="Restart procedure documented in section 4.2.",
    )
    # Create an unverified pending item (MUST NOT enter confirmed knowledge_items)
    pending_ki = KnowledgeItem(
        id=uuid.uuid4(),
        organisation_id=org.id,
        project_id=proj_a.id,
        category=KnowledgeCategory.WORK_ITEMS.value,
        epistemic_status=EpistemicStatus.EXTRACTED.value,
        review_status=KnowledgeReviewStatus.PENDING_REVIEW.value,
        support_classification="direct",
        title="Unverified Draft Task",
        structured_summary="Must remain pending and excluded from confirmed handover content.",
        structured_payload={},
        extraction_model="qwen3:8b",
        prompt_version="v1",
        fingerprint=hashlib.sha256(b"pending-task").hexdigest(),
    )
    db_session.add(pending_ki)

    # Create verified dependency relationship
    e1 = KnowledgeEntity(
        id=uuid.uuid4(),
        organisation_id=org.id,
        project_id=proj_a.id,
        entity_type="service",
        canonical_name="Settlement Worker",
        normalized_name="settlement worker",
    )
    e2 = KnowledgeEntity(
        id=uuid.uuid4(),
        organisation_id=org.id,
        project_id=proj_a.id,
        entity_type="database",
        canonical_name="PostgreSQL Ledger DB",
        normalized_name="postgresql ledger db",
    )
    db_session.add_all([e1, e2])
    db_session.flush()

    rel = KnowledgeRelationship(
        id=uuid.uuid4(),
        organisation_id=org.id,
        project_id=proj_a.id,
        source_entity_id=e1.id,
        target_entity_id=e2.id,
        relationship_type="depends_on",
        relationship_basis=RelationshipBasis.EXPLICIT.value,
        verification_status=RelationshipVerificationStatus.VERIFIED.value,
        confidence_score=0.95,
        fingerprint=hashlib.sha256(b"rel-1").hexdigest(),
    )
    db_session.add(rel)
    db_session.flush()
    db_session.add(
        RelationshipEvidenceLink(
            id=uuid.uuid4(),
            relationship_id=rel.id,
            organisation_id=org.id,
            project_id=proj_a.id,
            evidence_id=ev_spec.id,
            supporting_excerpt="Settlement Worker writes atomically to PostgreSQL Ledger DB.",
        )
    )
    db_session.add(
        VerificationCase(
            id=uuid.uuid4(),
            organisation_id=org.id,
            project_id=proj_a.id,
            target_type=VerificationTargetType.RELATIONSHIP.value,
            target_id=rel.id,
            domain="dependencies",
            title="Settlement Worker depends_on PostgreSQL Ledger DB",
            case_status=VerificationCaseStatus.VERIFIED.value,
        )
    )
    db_session.flush()

    # Create case & assemble v1
    case = HandoverCaseService(db_session).create_case(
        organisation_id=org.id,
        project_id=proj_a.id,
        user_id=manager.id,
        request=HandoverCaseCreateRequest(
            title="Alpha Payments Handover",
            departing_member_id=manager.id,
            successor_id=member.id,
        ),
    )
    v1 = PackageAssemblyService(db_session).assemble_package_version(
        case.id,
        project_id=proj_a.id,
        user_id=manager.id,
        request=PackageAssemblyRequest(assembly_notes="Initial v1"),
        has_project_manage=True,
    )
    original_hash = v1.content_hash
    db_session.commit()

    # Retrieve canonical sections via HandoverSectionReadService
    read_svc = HandoverSectionReadService(db_session)
    res = read_svc.get_version_sections(
        case_id=case.id,
        version_id=v1.id,
        project_id=proj_a.id,
        viewer_user_id=manager.id,
        has_project_manage=True,
    )

    # 1. All 8 canonical sections present in strict order
    assert len(res.sections) == 8
    assert [s.section_type for s in res.sections] == SECTION_ORDER
    assert [s.section_order for s in res.sections] == [1, 2, 3, 4, 5, 6, 7, 8]
    assert res.missing_section_types == []
    assert res.version.content_hash == original_hash

    # 2. Decision provenance & verification attribution
    dec_sec = next(s for s in res.sections if s.section_type == HandoverPackageSectionType.DECISIONS_RATIONALE.value)
    assert len(dec_sec.knowledge_items) == 1
    dec_item = dec_sec.knowledge_items[0]
    assert dec_item.title == "Use PostgreSQL Advisory Locks for Ledger Settlement"
    assert dec_item.epistemic_status == EpistemicStatus.HUMAN_VERIFIED.value
    assert dec_item.verification.case_status == VerificationCaseStatus.VERIFIED.value
    assert dec_item.verification.reviewer_decision == ReviewActionType.APPROVE.value
    assert dec_item.verification.reviewed_by_name == "Alex Manager"
    assert dec_item.provenance_available is True
    assert dec_item.provenance[0].source_name == "PR #42: PostgreSQL Idempotency Ledger"
    assert "ADR-004" in (dec_item.provenance[0].supporting_excerpt or "")
    assert dec_item.provenance[0].acl_restricted is False

    # 3. Domain 4 (Work Progress) is empty of verified items, transparently showing 1 pending item
    work_sec = next(s for s in res.sections if s.section_type == HandoverPackageSectionType.WORK_PROGRESS.value)
    assert len(work_sec.knowledge_items) == 0
    assert work_sec.epistemic_breakdown.pending_verification == 1

    # 4. Domain 5 (Ownership) includes real project members from PostgreSQL
    own_sec = next(s for s in res.sections if s.section_type == HandoverPackageSectionType.RESPONSIBILITIES_OWNERSHIP.value)
    team = own_sec.domain_context["team_members"]
    assert len(team) == 2
    assert {m["full_name"] for m in team} == {"Alex Manager", "Sam Engineer"}

    # 5. Domain 6 (Dependencies) includes verified relationship with entities & provenance
    dep_sec = next(s for s in res.sections if s.section_type == HandoverPackageSectionType.DEPENDENCIES_RELATIONSHIPS.value)
    assert len(dep_sec.relationships) == 1
    assert dep_sec.relationships[0].source_entity_name == "Settlement Worker"
    assert dep_sec.relationships[0].target_entity_name == "PostgreSQL Ledger DB"
    assert dep_sec.relationships[0].provenance_available is True

    # 6. Domain 8 (Operations) redacts secrets defensively
    ops_sec = next(s for s in res.sections if s.section_type == HandoverPackageSectionType.OPERATIONAL_HISTORICAL.value)
    assert len(ops_sec.knowledge_items) == 1
    ops_text = ops_sec.knowledge_items[0].content
    assert "ghp_1234567890" not in ops_text
    assert "SuperSecretPassword123" not in ops_text
    assert "[REDACTED_GITHUB_TOKEN]" in ops_text
    assert "[REDACTED]" in ops_text

    # 7. Read-only guarantee: reading sections never mutates content_hash
    db_session.refresh(v1)
    assert v1.content_hash == original_hash


def test_conflict_separation_and_missing_sections(db_session: Session) -> None:
    """Tests 5, 6, 10: Unresolved & resolved conflicts separated cleanly; missing sections explicitly reported."""
    env = _create_project_env(db_session)
    org, proj_a, manager = env["org"], env["proj_a"], env["manager"]

    # Create VerificationCase + 1 unresolved conflict + 1 resolved conflict
    vc = VerificationCase(
        id=uuid.uuid4(),
        organisation_id=org.id,
        project_id=proj_a.id,
        target_type=VerificationTargetType.KNOWLEDGE_ITEM.value,
        target_id=uuid.uuid4(),
        domain="bugs_blockers_risks",
        title="Kafka Retention Policy Conflict",
        case_status=VerificationCaseStatus.CONFLICTED.value,
    )
    db_session.add(vc)
    db_session.flush()

    db_session.add_all([
        VerificationConflict(
            id=uuid.uuid4(),
            organisation_id=org.id,
            project_id=proj_a.id,
            case_id=vc.id,
            conflict_type=ConflictType.TECHNICAL_CONFLICT.value,
            claim_a_text="Retention is 7 days in prod",
            claim_b_text="Retention is 30 days in prod",
            explanation="Conflicting Kafka retention settings between Terraform and Wiki.",
            resolution_state=ConflictResolutionState.UNRESOLVED.value,
            priority=ConflictPriority.HIGH.value,
        ),
        VerificationConflict(
            id=uuid.uuid4(),
            organisation_id=org.id,
            project_id=proj_a.id,
            case_id=vc.id,
            conflict_type=ConflictType.TECHNICAL_CONFLICT.value,
            claim_a_text="Node 18",
            claim_b_text="Node 20",
            explanation="Runtime version mismatch resolved to Node 20.",
            resolution_state=ConflictResolutionState.RESOLVED.value,
            authoritative_claim_text="Node 20 LTS is confirmed in Dockerfile.",
            priority=ConflictPriority.LOW.value,
            resolved_at=datetime.now(UTC),
        ),
    ])
    db_session.flush()

    case = HandoverCaseService(db_session).create_case(
        organisation_id=org.id,
        project_id=proj_a.id,
        user_id=manager.id,
        request=HandoverCaseCreateRequest(
            title="Partial Domain Handover",
            departing_member_id=manager.id,
        ),
    )
    # Assemble ONLY 2 domains to verify missing_section_types reporting
    v1 = PackageAssemblyService(db_session).assemble_package_version(
        case.id,
        project_id=proj_a.id,
        user_id=manager.id,
        request=PackageAssemblyRequest(
            include_domains=[
                HandoverPackageSectionType.PROJECT_OVERVIEW_CONTEXT.value,
                HandoverPackageSectionType.BUGS_BLOCKERS_RISKS.value,
            ]
        ),
        has_project_manage=True,
    )
    db_session.commit()

    res = HandoverSectionReadService(db_session).get_version_sections(
        case_id=case.id,
        version_id=v1.id,
        project_id=proj_a.id,
        viewer_user_id=manager.id,
        has_project_manage=True,
    )

    assert len(res.sections) == 2
    assert len(res.missing_section_types) == 6
    assert HandoverPackageSectionType.TECHNICAL_ARCHITECTURE.value in res.missing_section_types

    risks_sec = next(s for s in res.sections if s.section_type == HandoverPackageSectionType.BUGS_BLOCKERS_RISKS.value)
    # Unresolved conflict MUST NOT appear in confirmed knowledge_items
    assert len(risks_sec.knowledge_items) == 0
    assert len(risks_sec.unresolved_conflicts) == 1
    assert len(risks_sec.resolved_conflicts) == 1
    assert risks_sec.unresolved_conflicts[0].resolution_state == ConflictResolutionState.UNRESOLVED.value
    assert risks_sec.resolved_conflicts[0].authoritative_claim_text == "Node 20 LTS is confirmed in Dockerfile."


def test_source_acl_fail_closed_redaction_on_provenance(db_session: Session) -> None:
    """Test 8/11: Restricted source evidence is fail-closed redacted for users without source ACL."""
    env = _create_project_env(db_session)
    org, proj_a, manager, member = env["org"], env["proj_a"], env["manager"], env["member"]

    # SourceConnection + SourceAccessPolicy allowing ONLY manager (not member)
    conn = SourceConnection(
        id=uuid.uuid4(),
        organisation_id=org.id,
        provider="github",
        display_name="Org Private GitHub",
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
        scope_identifier="org/private-repo",
        sync_permission_status=SourcePermissionVerificationStatus.VERIFIED.value,
        allowed_user_ids=[str(manager.id)],
    )
    db_session.add(policy)
    db_session.flush()

    restricted_ev = _create_evidence(
        db_session,
        org.id,
        proj_a.id,
        "Private Security Architecture Doc",
        source_type=EvidenceSourceType.GITHUB.value,
        acl_scope="source_restricted",
        policy_id=policy.id,
    )
    _create_verified_ki(
        db_session, org.id, proj_a.id, manager,
        KnowledgeCategory.TECHNICAL_ARCHITECTURE.value,
        "HSM Key Rotation Architecture",
        "Keys rotate every 90 days via KMS.",
        restricted_ev,
        excerpt="CONFIDENTIAL_EXCERPT_DO_NOT_LEAK",
    )

    case = HandoverCaseService(db_session).create_case(
        organisation_id=org.id,
        project_id=proj_a.id,
        user_id=manager.id,
        request=HandoverCaseCreateRequest(title="ACL Handover", departing_member_id=manager.id),
    )
    v1 = PackageAssemblyService(db_session).assemble_package_version(
        case.id,
        project_id=proj_a.id,
        user_id=manager.id,
        request=PackageAssemblyRequest(),
        has_project_manage=True,
    )
    db_session.commit()

    read_svc = HandoverSectionReadService(db_session)

    # Manager CAN see provenance details
    mgr_res = read_svc.get_version_sections(
        case_id=case.id,
        version_id=v1.id,
        project_id=proj_a.id,
        viewer_user_id=manager.id,
        has_project_manage=True,
    )
    mgr_arch = next(s for s in mgr_res.sections if s.section_type == HandoverPackageSectionType.TECHNICAL_ARCHITECTURE.value)
    assert mgr_arch.knowledge_items[0].provenance[0].acl_restricted is False
    assert mgr_arch.knowledge_items[0].provenance[0].supporting_excerpt == "CONFIDENTIAL_EXCERPT_DO_NOT_LEAK"

    # Member WITHOUT source ACL gets fail-closed redaction
    mem_res = read_svc.get_version_sections(
        case_id=case.id,
        version_id=v1.id,
        project_id=proj_a.id,
        viewer_user_id=member.id,
        has_project_manage=False,
    )
    mem_arch = next(s for s in mem_res.sections if s.section_type == HandoverPackageSectionType.TECHNICAL_ARCHITECTURE.value)
    prov = mem_arch.knowledge_items[0].provenance[0]
    assert prov.acl_restricted is True
    assert prov.supporting_excerpt is None
    assert prov.source_url is None
    assert "CONFIDENTIAL_EXCERPT" not in prov.source_name


def test_historical_version_immutability_and_cross_project_isolation(db_session: Session) -> None:
    """Tests 2, 7, 12, 14: Historical v1 stays intact after v2 assembly; wrong case/project rejected with 404."""
    env = _create_project_env(db_session)
    org, proj_a, proj_b, manager = env["org"], env["proj_a"], env["proj_b"], env["manager"]

    ev_a = _create_evidence(db_session, org.id, proj_a.id, "Alpha Spec v1")
    _create_verified_ki(
        db_session, org.id, proj_a.id, manager,
        KnowledgeCategory.DECISIONS_RATIONALE.value,
        "Decision One (in v1 and v2)",
        "First architectural decision.",
        ev_a,
    )
    # Create a verified item in Project B to ensure zero cross-project leakage
    ev_b = _create_evidence(db_session, org.id, proj_b.id, "Beta Secret Spec")
    _create_verified_ki(
        db_session, org.id, proj_b.id, manager,
        KnowledgeCategory.DECISIONS_RATIONALE.value,
        "Project B Exclusive Decision",
        "Must never appear in Project A.",
        ev_b,
    )

    case_a = HandoverCaseService(db_session).create_case(
        organisation_id=org.id,
        project_id=proj_a.id,
        user_id=manager.id,
        request=HandoverCaseCreateRequest(title="Case A", departing_member_id=manager.id),
    )
    case_other = HandoverCaseService(db_session).create_case(
        organisation_id=org.id,
        project_id=proj_a.id,
        user_id=manager.id,
        request=HandoverCaseCreateRequest(title="Other Case in A", departing_member_id=manager.id),
    )

    asm = PackageAssemblyService(db_session)
    v1 = asm.assemble_package_version(
        case_a.id,
        project_id=proj_a.id,
        user_id=manager.id,
        request=PackageAssemblyRequest(assembly_notes="v1"),
        has_project_manage=True,
    )
    v1_hash = v1.content_hash

    # Add a second verified decision before assembling v2
    _create_verified_ki(
        db_session, org.id, proj_a.id, manager,
        KnowledgeCategory.DECISIONS_RATIONALE.value,
        "Decision Two (only in v2)",
        "Second architectural decision added later.",
        ev_a,
    )
    v2 = asm.assemble_package_version(
        case_a.id,
        project_id=proj_a.id,
        user_id=manager.id,
        request=PackageAssemblyRequest(assembly_notes="v2"),
        has_project_manage=True,
    )
    db_session.commit()

    assert v1.version_number == 1
    assert v2.version_number == 2
    assert v1.content_hash == v1_hash
    assert v2.content_hash != v1_hash

    read_svc = HandoverSectionReadService(db_session)
    res_v1 = read_svc.get_version_sections(
        case_id=case_a.id, version_id=v1.id, project_id=proj_a.id, viewer_user_id=manager.id, has_project_manage=True
    )
    res_v2 = read_svc.get_version_sections(
        case_id=case_a.id, version_id=v2.id, project_id=proj_a.id, viewer_user_id=manager.id, has_project_manage=True
    )

    dec_v1 = next(s for s in res_v1.sections if s.section_type == HandoverPackageSectionType.DECISIONS_RATIONALE.value)
    dec_v2 = next(s for s in res_v2.sections if s.section_type == HandoverPackageSectionType.DECISIONS_RATIONALE.value)

    assert [k.title for k in dec_v1.knowledge_items] == ["Decision One (in v1 and v2)"]
    assert len(dec_v2.knowledge_items) == 2
    assert "Project B Exclusive Decision" not in [k.title for k in dec_v2.knowledge_items]

    # Wrong case_id rejected
    with pytest.raises(NotFoundError):
        read_svc.get_version_sections(
            case_id=case_other.id, version_id=v1.id, project_id=proj_a.id, viewer_user_id=manager.id
        )

    # Wrong project_id (Project B trying to read Project A's version) rejected
    with pytest.raises(NotFoundError):
        read_svc.get_version_sections(
            case_id=case_a.id, version_id=v1.id, project_id=proj_b.id, viewer_user_id=manager.id
        )


def test_http_endpoint_canonical_sections_and_rbac(db_session: Session) -> None:
    """Tests 1, 7, 11: HTTP GET /cases/{case_id}/versions/{version_id}/sections enforces RBAC & returns canonical payload."""
    env = _create_project_env(db_session)
    org, proj_a, manager, outsider = env["org"], env["proj_a"], env["manager"], env["outsider"]

    case = HandoverCaseService(db_session).create_case(
        organisation_id=org.id,
        project_id=proj_a.id,
        user_id=manager.id,
        request=HandoverCaseCreateRequest(title="HTTP Test Handover", departing_member_id=manager.id),
    )
    v1 = PackageAssemblyService(db_session).assemble_package_version(
        case.id,
        project_id=proj_a.id,
        user_id=manager.id,
        request=PackageAssemblyRequest(),
        has_project_manage=True,
    )
    db_session.commit()

    active_user_holder: dict[str, User] = {"user": manager}

    def _override_db() -> Any:
        yield db_session

    def _override_principal() -> Any:
        return RbacService(
            db_session=db_session,
            rbac_repository=RbacRepository(db_session),
            user_repository=UserRepository(db_session),
        ).resolve_principal(
            user=active_user_holder["user"],
            session_family_id=uuid.uuid4(),
        )

    app.dependency_overrides[get_db_session] = _override_db
    app.dependency_overrides[get_current_principal] = _override_principal
    try:
        client = TestClient(app)

        # 1. Authorized manager succeeds
        resp = client.get(
            f"/api/v1/projects/{proj_a.id}/handover/cases/{case.id}/versions/{v1.id}/sections"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["case_id"] == str(case.id)
        assert body["project_id"] == str(proj_a.id)
        assert body["version"]["id"] == str(v1.id)
        assert body["version"]["content_hash"] == v1.content_hash
        assert len(body["sections"]) == 8
        assert [s["section_type"] for s in body["sections"]] == SECTION_ORDER

        # 2. Missing version returns 404
        resp_404 = client.get(
            f"/api/v1/projects/{proj_a.id}/handover/cases/{case.id}/versions/{uuid.uuid4()}/sections"
        )
        assert resp_404.status_code == 404

        # 3. Unauthorized outsider (non-member) denied with 403/404
        active_user_holder["user"] = outsider
        resp_denied = client.get(
            f"/api/v1/projects/{proj_a.id}/handover/cases/{case.id}/versions/{v1.id}/sections"
        )
        assert resp_denied.status_code in (403, 404)
    finally:
        app.dependency_overrides.clear()
