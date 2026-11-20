"""Tests for Deterministic Knowledge-to-Handover Composition & Successor Briefing.

Covers:
1. Eliminating manifest dependency dumps (Alembic, HTTPX, python-dotenv, PyJWT, pwdlib) into compact layer overviews.
2. Grouping raw GitHub commits into Completed Workstreams (never misclassifying commits as Pending Work).
3. Consolidating duplicate Commit Author records and distinguishing authorship from formal ownership.
4. Generating the 6-part 'Start Here' executive briefing from grounded project evidence.
5. Preserving strict epistemic boundaries (human-approved vs provisional draft vs locked/approved exclusion).
6. Verifying Developer, Project Manager, and Technical Lead presentations and Markdown/JSON/PDF export parity & ACLs.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

import pymupdf as fitz
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.rbac_catalog import deterministic_rbac_id
from app.models import Base
from app.models.enums import (
    EpistemicStatus,
    EvidenceProcessingStatus,
    EvidenceSourceType,
    HandoverCaseStatus,
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
from app.models.handover import HandoverResponsibilityTransfer
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
from app.models.verification import VerificationCase, VerificationReviewEvent
from app.repositories.rbac import RbacRepository
from app.schemas.handover import HandoverCaseCreateRequest, PackageAssemblyRequest
from app.services.handover_assembly import PackageAssemblyService
from app.services.handover_case import HandoverCaseService
from app.services.handover_export import HandoverExportService
from app.services.handover_sections import HandoverSectionReadService


@pytest.fixture
def db_session() -> Any:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn: Any, _: Any) -> None:
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False, class_=Session)
    with factory() as session:
        RbacRepository(session).ensure_catalog_seeded()
        session.commit()
        yield session
        session.rollback()


def _mk_user(session: Session, email: str, name: str) -> User:
    u = User(
        id=uuid.uuid4(),
        email=email,
        full_name=name,
        password_hash="argon2id$test",
        status=UserStatus.ACTIVE.value,
        is_email_verified=True,
        email_verified_at=datetime.now(UTC),
    )
    session.add(u)
    session.flush()
    return u


def _add_finding(
    session: Session,
    *,
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    reviewer: User,
    ev: EvidenceItem,
    category: str,
    title: str,
    summary: str,
    verified: bool = True,
    normalised_status: str | None = None,
    payload: dict[str, Any] | None = None,
) -> KnowledgeItem:
    ki = KnowledgeItem(
        id=uuid.uuid4(),
        organisation_id=org_id,
        project_id=project_id,
        category=category,
        title=title,
        structured_summary=summary,
        normalised_status=normalised_status,
        structured_payload=payload or {},
        epistemic_status=EpistemicStatus.HUMAN_VERIFIED.value if verified else EpistemicStatus.EXTRACTED.value,
        review_status=KnowledgeReviewStatus.APPROVED.value if verified else KnowledgeReviewStatus.PENDING_REVIEW.value,
        support_classification="direct",
        extraction_model="deterministic_fast_extractor",
        prompt_version="v1",
        fingerprint=hashlib.sha256(f"{title}-{uuid.uuid4()}".encode()).hexdigest()[:32],
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
            support_type="direct",
            supporting_excerpt=summary[:120],
            excerpt_verified=verified,
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
        case_status=VerificationCaseStatus.VERIFIED.value if verified else VerificationCaseStatus.CANDIDATE.value,
        priority=VerificationPriority.MEDIUM.value,
        assigned_reviewer_id=reviewer.id if verified else None,
        last_reviewed_at=datetime.now(UTC) if verified else None,
    )
    session.add(vc)
    session.flush()
    if verified:
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
                review_notes="Human verified for acceptance test",
                correlation_id=uuid.uuid4().hex,
            )
        )
    return ki


def test_composed_successor_briefing_noise_consolidation_exports_and_epistemic_gate(
    db_session: Session,
) -> None:
    """Verify full knowledge-transfer composition, Start Here briefing, PDF parity, and ACL enforcement."""
    manager = _mk_user(db_session, "mgr@compose.local", "Morgan Manager")
    departing = _mk_user(db_session, "out@compose.local", "Dev Departing")
    successor = _mk_user(db_session, "in@compose.local", "Sam Successor")

    org = Organisation(
        id=uuid.uuid4(),
        name="Compose Org",
        slug=f"compose-{uuid.uuid4().hex[:6]}",
        status=OrganisationStatus.ACTIVE.value,
        created_by_id=manager.id,
    )
    db_session.add(org)
    db_session.flush()

    proj = Project(
        id=uuid.uuid4(),
        organisation_id=org.id,
        name="Settlement Gateway Refactor",
        slug=f"settle-{uuid.uuid4().hex[:6]}",
        description="Orchestrates idempotent ledger postings and async webhook reconciliation.",
        status=ProjectStatus.ACTIVE.value,
        visibility=ProjectVisibility.PRIVATE.value,
        created_by_id=manager.id,
        owner_id=manager.id,
    )
    db_session.add(proj)
    db_session.flush()

    for usr, rname, desc in [
        (manager, RoleName.PROJECT_MANAGER.value, "Engineering governance"),
        (departing, RoleName.PROJECT_MEMBER.value, "Settlement API & Worker Lead"),
        (successor, RoleName.PROJECT_MEMBER.value, "Incoming Backend Owner"),
    ]:
        db_session.add(OrganisationMembership(id=uuid.uuid4(), organisation_id=org.id, user_id=usr.id, role_id=deterministic_rbac_id("role", RoleName.ORG_MEMBER.value), status="active"))
        db_session.add(ProjectMembership(id=uuid.uuid4(), project_id=proj.id, user_id=usr.id, role_id=deterministic_rbac_id("role", rname), status="active", responsibility_description=desc))

    src_conn = SourceConnection(
        id=uuid.uuid4(),
        organisation_id=org.id,
        provider="github",
        display_name="Org Private Repo Connection",
        status="active",
        created_by_user_id=manager.id,
    )
    db_session.add(src_conn)
    db_session.flush()

    restricted_policy = SourceAccessPolicy(
        id=uuid.uuid4(),
        organisation_id=org.id,
        project_id=proj.id,
        source_connection_id=src_conn.id,
        provider="github",
        scope_identifier="org/private-infra",
        visibility_policy="explicit_user_grants",
        allowed_user_ids=[str(manager.id)],
        sync_permission_status=SourcePermissionVerificationStatus.VERIFIED.value,
        authorised_by_user_id=manager.id,
    )
    db_session.add(restricted_policy)
    db_session.flush()

    ev_public = EvidenceItem(
        id=uuid.uuid4(),
        organisation_id=org.id,
        project_id=proj.id,
        source_type=EvidenceSourceType.GITHUB.value,
        source_provider="github",
        category="design_document",
        source_external_id="repo:README.md",
        source_url="https://github.com/org/settlement/blob/main/README.md",
        source_author_identity="Dev Departing",
        title="README.md",
        content_hash=hashlib.sha256(b"readme").hexdigest(),
        processing_status=EvidenceProcessingStatus.EXTRACTED.value,
        acl_scope="project_members",
        source_created_at=datetime.now(UTC),
        extracted_at=datetime.now(UTC),
    )
    ev_restricted = EvidenceItem(
        id=uuid.uuid4(),
        organisation_id=org.id,
        project_id=proj.id,
        source_type=EvidenceSourceType.GITHUB.value,
        source_provider="github",
        category="design_document",
        source_external_id="repo:secrets-vault.md",
        title="RESTRICTED_VAULT_RUNBOOK",
        content_hash=hashlib.sha256(b"vault").hexdigest(),
        processing_status=EvidenceProcessingStatus.EXTRACTED.value,
        acl_scope="source_restricted",
        source_access_policy_id=restricted_policy.id,
        source_created_at=datetime.now(UTC),
        extracted_at=datetime.now(UTC),
    )
    db_session.add_all([ev_public, ev_restricted])
    db_session.flush()

    # Add realistic raw manifest dependencies (must consolidate into 1 card, NOT separate cards!)
    for pkg in ("FastAPI", "Alembic", "HTTPX", "python-dotenv", "PyJWT", "pwdlib", "SQLAlchemy"):
        _add_finding(
            db_session,
            org_id=org.id,
            project_id=proj.id,
            reviewer=manager,
            ev=ev_public,
            category=KnowledgeCategory.TECHNICAL_ARCHITECTURE.value,
            title=f"Technology: {pkg}",
            summary=f"Project declares dependency on {pkg} (v>=1.0.0) in manifest 'org/settlement: backend/pyproject.toml'.",
            verified=True,
        )
        _add_finding(
            db_session,
            org_id=org.id,
            project_id=proj.id,
            reviewer=manager,
            ev=ev_public,
            category=KnowledgeCategory.DEPENDENCIES.value,
            title=f"Dependency: {pkg}",
            summary=f"External dependency '{pkg}' (v>=1.0.0) specified in org/settlement: backend/pyproject.toml",
            verified=True,
        )

    # Substantive architecture items
    _add_finding(db_session, org_id=org.id, project_id=proj.id, reviewer=manager, ev=ev_public, category=KnowledgeCategory.TECHNICAL_ARCHITECTURE.value, title="FastAPI Idempotent API Service", summary="FastAPI handles webhook ingestion with PostgreSQL advisory locks.", verified=True)
    _add_finding(db_session, org_id=org.id, project_id=proj.id, reviewer=manager, ev=ev_public, category=KnowledgeCategory.TECHNICAL_ARCHITECTURE.value, title="PostgreSQL Ledger Schema", summary="PostgreSQL 16 stores canonical double-entry ledger transactions.", verified=True)
    _add_finding(db_session, org_id=org.id, project_id=proj.id, reviewer=manager, ev=ev_public, category=KnowledgeCategory.TECHNICAL_ARCHITECTURE.value, title="Classified KMS Key Topology", summary="SECRET_VAULT_NEVER_LEAK hardware HSM root keys.", verified=True)
    # Link classified finding to restricted evidence only
    db_session.flush()
    classified_ki = db_session.query(KnowledgeItem).filter_by(title="Classified KMS Key Topology").one()
    db_session.query(KnowledgeEvidenceLink).filter_by(knowledge_item_id=classified_ki.id).update({"evidence_id": ev_restricted.id})

    # Raw commits across two workstreams (must NOT appear as Pending Work!)
    for i, msg in enumerate([
        "feat(handover): implement idempotent ledger writer",
        "feat(handover): add webhook signature verification",
        "fix(auth): enforce short-lived JWT expiry checks",
        "fix(auth): rotate refresh session tokens",
    ]):
        _add_finding(
            db_session,
            org_id=org.id,
            project_id=proj.id,
            reviewer=manager,
            ev=ev_public,
            category=KnowledgeCategory.WORK_ITEMS.value,
            title=f"Commit: org/settlement@{1000+i:08x}: {msg}",
            summary=f"Git commit by alice: 'org/settlement@{1000+i:08x}: {msg}'",
            verified=True,
        )

    # Actual unfinished pending task + provisional candidate item
    _add_finding(db_session, org_id=org.id, project_id=proj.id, reviewer=manager, ev=ev_public, category=KnowledgeCategory.WORK_ITEMS.value, title="Complete Multi-Currency Settlement Batching", summary="Pending migration of EUR batch window reconciliation before Q1 go-live.", normalised_status="pending", verified=True)
    _add_finding(db_session, org_id=org.id, project_id=proj.id, reviewer=manager, ev=ev_public, category=KnowledgeCategory.BUGS_BLOCKERS_RISKS.value, title="Webhook Retry Backoff Blocker", summary="Partner gateway rate-limits bursts over 50 req/s; exponential jitter backoff not yet deployed.", normalised_status="open", verified=True)
    _add_finding(db_session, org_id=org.id, project_id=proj.id, reviewer=manager, ev=ev_public, category=KnowledgeCategory.DECISIONS_RATIONALE.value, title="PostgreSQL Advisory Locks Over Redis", summary="Chose PostgreSQL advisory locks instead of Redis to avoid distributed broker split-brain.", verified=True, payload={"rationale": "Single transactional failure domain without external broker state."})
    _add_finding(db_session, org_id=org.id, project_id=proj.id, reviewer=manager, ev=ev_public, category=KnowledgeCategory.PROJECT_OVERVIEW_CONTEXT.value, title="Platform Purpose", summary="Prevents critical settlement architecture knowledge loss during team transitions.", verified=True)

    # Duplicate Commit Author rows (must consolidate cleanly)
    for _ in range(4):
        _add_finding(db_session, org_id=org.id, project_id=proj.id, reviewer=manager, ev=ev_public, category=KnowledgeCategory.RESPONSIBILITIES_OWNERSHIP.value, title="Commit Author: alice", summary="alice is recorded as commit author for 'org/settlement'", verified=True)

    # Provisional unreviewed candidate item
    _add_finding(db_session, org_id=org.id, project_id=proj.id, reviewer=manager, ev=ev_public, category=KnowledgeCategory.DECISIONS_RATIONALE.value, title="UNVERIFIED_CANDIDATE_DECISION_MARKER", summary="Provisional unreviewed architecture hypothesis awaiting reviewer sign-off.", verified=False)

    # Relationship
    e_api = KnowledgeEntity(id=uuid.uuid4(), organisation_id=org.id, project_id=proj.id, entity_type="service", canonical_name="Settlement API", normalized_name="settlement api")
    e_pg = KnowledgeEntity(id=uuid.uuid4(), organisation_id=org.id, project_id=proj.id, entity_type="database", canonical_name="PostgreSQL Ledger", normalized_name="postgresql ledger")
    e_wc = KnowledgeEntity(id=uuid.uuid4(), organisation_id=org.id, project_id=proj.id, entity_type="work_cluster", canonical_name="Backend", normalized_name="backend")
    db_session.add_all([e_api, e_pg, e_wc])
    db_session.flush()
    rel_dep = KnowledgeRelationship(id=uuid.uuid4(), organisation_id=org.id, project_id=proj.id, source_entity_id=e_api.id, target_entity_id=e_pg.id, relationship_type="STORES_IN", relationship_basis=RelationshipBasis.EXPLICIT.value, verification_status=RelationshipVerificationStatus.VERIFIED.value, confidence_score=0.95, fingerprint=hashlib.sha256(b"rel-dep").hexdigest())
    rel_noise = KnowledgeRelationship(id=uuid.uuid4(), organisation_id=org.id, project_id=proj.id, source_entity_id=e_api.id, target_entity_id=e_wc.id, relationship_type="BELONGS_TO_WORK_CLUSTER", relationship_basis=RelationshipBasis.EXPLICIT.value, verification_status=RelationshipVerificationStatus.VERIFIED.value, confidence_score=0.95, fingerprint=hashlib.sha256(b"rel-noise").hexdigest())
    db_session.add_all([rel_dep, rel_noise])
    db_session.flush()
    for r in (rel_dep, rel_noise):
        db_session.add(RelationshipEvidenceLink(id=uuid.uuid4(), organisation_id=org.id, project_id=proj.id, relationship_id=r.id, evidence_id=ev_public.id, supporting_excerpt="Settlement API stores in PostgreSQL Ledger."))
        db_session.add(
            VerificationCase(
                id=uuid.uuid4(),
                organisation_id=org.id,
                project_id=proj.id,
                target_type=VerificationTargetType.RELATIONSHIP.value,
                target_id=r.id,
                domain="dependencies",
                title=f"Relationship {r.relationship_type}",
                case_status=VerificationCaseStatus.VERIFIED.value,
            )
        )

    # Formal case & responsibility transfer
    case = HandoverCaseService(db_session).create_case(
        organisation_id=org.id,
        project_id=proj.id,
        user_id=manager.id,
        request=HandoverCaseCreateRequest(
            title="Backend Lead Handover",
            description="Transfer settlement platform ownership",
            departing_member_id=departing.id,
            successor_id=successor.id,
            handover_type="developer",
        ),
    )
    db_session.add(
        HandoverResponsibilityTransfer(
            id=uuid.uuid4(),
            organisation_id=org.id,
            project_id=proj.id,
            case_id=case.id,
            title="Settlement Webhook & Batch Windows",
            responsibility_description="Maintain settlement webhook retry limits and EUR batch cutover.",
            knowledge_domain="technical_architecture",
            current_owner_id=departing.id,
            proposed_successor_id=successor.id,
            transfer_status="awaiting_outgoing_confirmation",
        )
    )
    db_session.commit()

    # 1. Strict official assembly (include_provisional_draft=False): excludes UNVERIFIED_CANDIDATE_DECISION_MARKER
    assembler = PackageAssemblyService(db_session)
    v_official = assembler.assemble_package_version(
        case.id,
        project_id=proj.id,
        user_id=manager.id,
        request=PackageAssemblyRequest(assembly_notes="Official verified snapshot"),
        has_project_manage=True,
    )
    db_session.commit()

    reader = HandoverSectionReadService(db_session)
    sec_official = reader.get_version_sections(
        case_id=case.id,
        version_id=v_official.id,
        project_id=proj.id,
        viewer_user_id=manager.id,
        has_project_manage=True,
        role_override="developer",
    )
    assert "UNVERIFIED_CANDIDATE_DECISION_MARKER" not in str(
        [m.model_dump(mode="json") for m in sec_official.mandatory_sections]
    )
    assert "UNVERIFIED_CANDIDATE_DECISION_MARKER" not in str(
        [s.model_dump(mode="json") for s in sec_official.sections]
    )
    assert sec_official.start_here_briefing is not None
    assert "Settlement Gateway Refactor" in sec_official.start_here_briefing.what_is_this_project

    # Verify manifest dependencies consolidated cleanly (no individual Alembic/HTTPX cards!)
    sec_arch = next(m for m in sec_official.mandatory_sections if m.section_number == 2)
    arch_titles = [k.title for k in sec_arch.knowledge_items]
    assert not any(t in ("Technology: Alembic", "Technology: HTTPX", "Technology: PyJWT", "Technology: pwdlib", "Technology: python-dotenv") for t in arch_titles)
    assert any("Declared Technology Stack Overview" in t for t in arch_titles)

    # Verify commits are grouped in Completed Work (Section 3) and NEVER in Pending Work (Section 4)
    sec_comp = next(m for m in sec_official.mandatory_sections if m.section_number == 3)
    sec_pend = next(m for m in sec_official.mandatory_sections if m.section_number == 4)
    assert any(k.title.startswith("Workstream:") for k in sec_comp.knowledge_items)
    assert not any("Commit:" in k.title for k in sec_pend.knowledge_items)
    assert any("Complete Multi-Currency Settlement Batching" in k.title for k in sec_pend.knowledge_items)

    # Verify Dependencies filter out BELONGS_TO_WORK_CLUSTER noise and keep STORES_IN
    sec_dep = next(m for m in sec_official.mandatory_sections if m.section_number == 6)
    assert [r.relationship_type for r in sec_dep.relationships] == ["STORES_IN"]

    # Verify Responsibilities consolidate 4 Commit Author records into 1 Historical Contributor card
    sec_resp = next(m for m in sec_official.mandatory_sections if m.section_number == 8)
    assert any("Historical Repository Contributors" in k.title for k in sec_resp.knowledge_items)

    # Verify distinct role priorities across Developer, PM, Technical Lead
    dev_prio = {m.section_key for m in sec_official.mandatory_sections if m.is_role_priority}
    pm_secs = reader.get_version_sections(case_id=case.id, version_id=v_official.id, project_id=proj.id, viewer_user_id=manager.id, has_project_manage=True, role_override="project_manager")
    tl_secs = reader.get_version_sections(case_id=case.id, version_id=v_official.id, project_id=proj.id, viewer_user_id=manager.id, has_project_manage=True, role_override="technical_lead")
    assert dev_prio != {m.section_key for m in pm_secs.mandatory_sections if m.is_role_priority}
    assert dev_prio != {m.section_key for m in tl_secs.mandatory_sections if m.is_role_priority}

    # 2. Provisional draft assembly (include_provisional_draft=True): includes candidate labelled provisionally!
    v_draft = assembler.assemble_package_version(
        case.id,
        project_id=proj.id,
        user_id=manager.id,
        request=PackageAssemblyRequest(assembly_notes="Provisional draft", include_provisional_draft=True),
        has_project_manage=True,
    )
    db_session.commit()
    sec_draft = reader.get_version_sections(
        case_id=case.id,
        version_id=v_draft.id,
        project_id=proj.id,
        viewer_user_id=manager.id,
        has_project_manage=True,
    )
    assert sec_draft.start_here_briefing is not None
    assert sec_draft.start_here_briefing.is_provisional_draft is True
    sec_dec_draft = next(m for m in sec_draft.mandatory_sections if m.section_number == 5)
    cand_cards = [k for k in sec_dec_draft.knowledge_items if "UNVERIFIED_CANDIDATE_DECISION_MARKER" in k.title]
    assert len(cand_cards) == 1
    assert cand_cards[0].epistemic_status == EpistemicStatus.EXTRACTED.value
    assert cand_cards[0].review_status == KnowledgeReviewStatus.PENDING_REVIEW.value

    # 3. Export parity & fail-closed ACL checks across Markdown, JSON, and PDF
    exporter = HandoverExportService(db_session)
    md_mgr = exporter.export_markdown(project_id=proj.id, case_id=case.id, user_id=manager.id, version_id=v_official.id, has_project_manage=True)
    assert "Start Here" in md_mgr
    assert "SECRET_VAULT_NEVER_LEAK" in md_mgr  # manager has restricted_policy grant

    json_succ = exporter.export_json(project_id=proj.id, case_id=case.id, user_id=successor.id, version_id=v_official.id, has_project_manage=False, can_review_or_manage=True)
    assert json_succ["viewer_acl_filtered"] is True
    assert "SECRET_VAULT_NEVER_LEAK" not in str(json_succ)

    pdf_succ = exporter.export_pdf(project_id=proj.id, case_id=case.id, user_id=successor.id, version_id=v_official.id, has_project_manage=False, can_review_or_manage=True)
    doc = fitz.open(stream=pdf_succ, filetype="pdf")
    pdf_text = "\n".join(page.get_text("text") for page in doc)
    doc.close()
    assert "Start Here" in pdf_text
    assert "Declared Technology Stack Overview" in pdf_text
    assert "Complete Multi-Currency Settlement Batching" in pdf_text
    assert "SECRET_VAULT_NEVER_LEAK" not in pdf_text
    assert "Technology: Alembic" not in pdf_text

    # 4. Once case moves to APPROVED, provisional items must be stripped automatically even on read
    case.status = HandoverCaseStatus.APPROVED.value
    db_session.commit()
    sec_locked = reader.get_version_sections(
        case_id=case.id,
        version_id=v_draft.id,
        project_id=proj.id,
        viewer_user_id=manager.id,
        has_project_manage=True,
    )
    assert "UNVERIFIED_CANDIDATE_DECISION_MARKER" not in str(
        [m.model_dump(mode="json") for m in sec_locked.mandatory_sections]
    )
    assert "UNVERIFIED_CANDIDATE_DECISION_MARKER" not in str(
        [s.model_dump(mode="json") for s in sec_locked.sections]
    )
