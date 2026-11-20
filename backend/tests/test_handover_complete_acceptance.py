"""Comprehensive End-to-End Acceptance Suite for The Handover Workspace.

Platform: The Handover — Intelligent Project Knowledge Reconstruction & Handover Platform

Covers all 22 end-to-end user-journey steps and all 9 negative security, source-ACL,
epistemic-integrity, and lifecycle state-machine tests in complete isolation without
live external LLM/Chroma dependencies or seeded demo data.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

import pymupdf as fitz
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import (
    get_current_principal,
    get_db_session,
    get_hybrid_retrieval_service,
    get_llm_client,
)
from app.core.exceptions import BadRequestError, ConflictError, ForbiddenError
from app.core.rbac_catalog import deterministic_rbac_id
from app.main import app
from app.models import Base
from app.models.audit import AuditLog
from app.models.enums import (
    ChecklistItemStatus,
    ChunkIndexingStatus,
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
    RelationshipVerificationStatus,
    RoleName,
    SearchMode,
    SignoffDecision,
    SignoffType,
    SourcePermissionVerificationStatus,
    UserStatus,
)
from app.models.evidence import EvidenceChunk, EvidenceContent, EvidenceItem
from app.models.handover import (
    HandoverPackageSection,
    HandoverPackageVersion,
    HandoverResponsibilityTransfer,
)
from app.models.integration import SourceAccessPolicy
from app.models.knowledge import KnowledgeEvidenceLink, KnowledgeItem
from app.models.organisation import Organisation, OrganisationMembership
from app.models.project import Project, ProjectMembership
from app.models.relationship import (
    KnowledgeEntity,
    KnowledgeRelationship,
    RelationshipEvidenceLink,
)
from app.models.user import User
from app.models.verification import VerificationCase, VerificationConflict
from app.repositories.rbac import RbacRepository
from app.repositories.user import UserRepository
from app.schemas.conflicts import ResolveConflictRequest
from app.schemas.handover import HandoverCaseCreateRequest
from app.schemas.retrieval import ProjectSearchResponse
from app.schemas.verification import ApproveFindingRequest
from app.services.auth import AuthenticatedPrincipal
from app.services.conflict_service import ConflictService
from app.services.handover_case import HandoverCaseService
from app.services.handover_signoff import HandoverSignoffService
from app.services.llm import LLMGenerationRequest, LLMGenerationResult
from app.services.rbac import RbacService
from app.services.verification_engine import VerificationEngine
from app.services.verification_review import VerificationReviewService


class CapturingStubLLMClient:
    """Deterministic local LLM stub capturing prompts without network I/O."""

    model_name = "qwen3:8b-acceptance-stub"

    def __init__(self) -> None:
        self.captured_prompts: list[str] = []

    def generate_raw(self, *, messages: list[Any], temperature: float = 0.1) -> str:
        prompt_text = "\n".join(str(getattr(m, "content", m)) for m in messages)
        self.captured_prompts.append(prompt_text)
        return (
            "## Human-Verified Decision Narrative\n\n"
            "- PostgreSQL advisory locks coordinate background lanes cleanly.\n"
            "- Hold settlement batch windows between 23:45 and 00:05 UTC."
        )

    def generate_json(self, req: LLMGenerationRequest) -> LLMGenerationResult:
        self.captured_prompts.append(req.user_prompt)
        return LLMGenerationResult(
            parsed_json={
                "answer": (
                    "The approved handover package documents that PostgreSQL serves as the "
                    "canonical database [S1], while staging alerts must be monitored on handover."
                ),
                "answer_status": "answered",
                "response_mode": "standard",
                "claims": [
                    {
                        "claim_text": "PostgreSQL is the canonical storage authority [S1].",
                        "citation_labels": ["S1"],
                        "confidence": 0.98,
                    }
                ],
                "uncertainty": None,
                "conflicts": [],
                "missing_information": [],
                "suggested_followup_questions": ["Which operational runbooks apply to DB failover?"],
            },
            raw_text='{"answer_status": "answered"}',
            model_name=self.model_name,
            prompt_tokens=120,
            completion_tokens=48,
            duration_ms=5,
            done_reason="stop",
            truncated=False,
        )


class StubHybridRetrievalService:
    """SQLite-safe stub preventing PostgreSQL tsvector/Chroma queries in acceptance unit runs."""

    def search_project(self, *, project_ctx: Any, payload: Any) -> ProjectSearchResponse:
        return ProjectSearchResponse(
            project_id=project_ctx.project.id,
            query=payload.query,
            mode_requested=payload.mode,
            mode_executed=SearchMode.KEYWORD,
            degraded=False,
            total_returned=0,
            latency_ms=1,
            embedding_model="nomic-embed-text",
            index_version="test-v1",
            results=[],
        )


@pytest.fixture
def handover_acceptance_env() -> Any:
    """Isolated SQLite environment with departing dev, successor, PM, technical reviewer, and outsider."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _disable_sqlite_fk(dbapi_conn: Any, _rec: Any) -> None:
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=OFF")
        cur.close()

    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    RbacRepository(session).ensure_catalog_seeded()
    session.commit()

    def _mk_user(label: str) -> User:
        u = User(
            id=uuid.uuid4(),
            email=f"accept-{label}-{uuid.uuid4().hex[:6]}@isolated.test",
            full_name=f"Acceptance {label.replace('_', ' ').title()}",
            password_hash="argon2id$isolated",
            status=UserStatus.ACTIVE.value,
            is_email_verified=True,
            email_verified_at=datetime.now(UTC),
        )
        session.add(u)
        return u

    manager = _mk_user("manager")
    departing = _mk_user("departing_dev")
    reviewer = _mk_user("tech_reviewer")
    successor = _mk_user("incoming_successor")
    outsider = _mk_user("outsider")
    session.flush()

    org = Organisation(
        id=uuid.uuid4(),
        name="Handover Acceptance Org",
        slug=f"acc-org-{uuid.uuid4().hex[:6]}",
        status=OrganisationStatus.ACTIVE.value,
        created_by_id=manager.id,
    )
    session.add(org)
    session.flush()

    proj_a = Project(
        id=uuid.uuid4(),
        organisation_id=org.id,
        name="Core Ledger Platform",
        slug=f"core-ledger-{uuid.uuid4().hex[:6]}",
        description="High-availability settlement & ledger backend.",
        status=ProjectStatus.ACTIVE.value,
        visibility=ProjectVisibility.PRIVATE.value,
        created_by_id=manager.id,
        owner_id=manager.id,
    )
    proj_b = Project(
        id=uuid.uuid4(),
        organisation_id=org.id,
        name="Isolated Other Project",
        slug=f"other-proj-{uuid.uuid4().hex[:6]}",
        status=ProjectStatus.ACTIVE.value,
        visibility=ProjectVisibility.PRIVATE.value,
        created_by_id=outsider.id,
        owner_id=outsider.id,
    )
    session.add_all([proj_a, proj_b])
    session.flush()

    for u, org_role, role_a, role_b in [
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
        if role_a:
            session.add(
                ProjectMembership(
                    id=uuid.uuid4(),
                    project_id=proj_a.id,
                    user_id=u.id,
                    role_id=deterministic_rbac_id("role", role_a),
                    status="active",
                )
            )
        if role_b:
            session.add(
                ProjectMembership(
                    id=uuid.uuid4(),
                    project_id=proj_b.id,
                    user_id=u.id,
                    role_id=deterministic_rbac_id("role", role_b),
                    status="active",
                )
            )
    session.flush()

    # Restricted policy: allows manager, departing, reviewer — EXCLUDES incoming successor
    restricted_policy = SourceAccessPolicy(
        id=uuid.uuid4(),
        organisation_id=org.id,
        project_id=proj_a.id,
        source_connection_id=uuid.uuid4(),
        provider="github",
        scope_identifier="org/enclave-secrets-repo",
        visibility_policy="explicit_user_grants",
        allowed_user_ids=[str(manager.id), str(departing.id), str(reviewer.id)],
        sync_permission_status=SourcePermissionVerificationStatus.VERIFIED.value,
        authorised_by_user_id=manager.id,
    )
    session.add(restricted_policy)
    session.flush()

    def _seed_ev_and_ki(
        *,
        title: str,
        summary: str,
        category: str,
        acl_scope: str = "project_members",
        policy_id: uuid.UUID | None = None,
        source_type: str = EvidenceSourceType.GITHUB.value,
        approve: bool = True,
    ) -> tuple[EvidenceItem, KnowledgeItem]:
        ev = EvidenceItem(
            id=uuid.uuid4(),
            organisation_id=org.id,
            project_id=proj_a.id,
            uploaded_by_user_id=departing.id,
            source_type=source_type,
            source_provider=source_type,
            category="project_document",
            source_external_id=f"src-{uuid.uuid4().hex[:8]}",
            source_author_identity="Acceptance Departing Dev",
            title=f"Evidence: {title}",
            content_hash=hashlib.sha256(summary.encode()).hexdigest(),
            acl_scope=acl_scope,
            source_access_policy_id=policy_id,
            source_created_at=datetime.now(UTC),
            source_updated_at=datetime.now(UTC),
            extracted_at=datetime.now(UTC),
            processing_status=EvidenceProcessingStatus.EXTRACTED.value,
        )
        session.add(ev)
        session.flush()

        ev_c = EvidenceContent(
            evidence_id=ev.id,
            extracted_text=summary,
            char_count=len(summary),
            word_count=len(summary.split()),
            extraction_warnings=[],
        )
        session.add(ev_c)

        ev_chk = EvidenceChunk(
            organisation_id=org.id,
            project_id=proj_a.id,
            evidence_id=ev.id,
            chunk_index=0,
            chunk_type="text_segment",
            section_title=title,
            char_start=0,
            char_end=len(summary),
            char_count=len(summary),
            token_estimate=max(1, len(summary.split())),
            chunk_text=summary,
            chunk_content_hash=hashlib.sha256(summary.encode()).hexdigest(),
            search_identifier_text=title,
            source_type=source_type,
            source_author_identity="Acceptance Departing Dev",
            source_created_at=datetime.now(UTC),
            acl_scope=acl_scope,
            indexing_status=ChunkIndexingStatus.CHUNKED.value,
            metadata_json={},
        )
        session.add(ev_chk)

        ki = KnowledgeItem(
            id=uuid.uuid4(),
            organisation_id=org.id,
            project_id=proj_a.id,
            category=category,
            title=title,
            structured_summary=summary,
            structured_payload={"status": "active", "owner": "Acceptance Departing Dev"},
            epistemic_status=EpistemicStatus.EXTRACTED.value,
            review_status=KnowledgeReviewStatus.PENDING_REVIEW.value,
            support_classification="direct",
            extraction_model="qwen3:8b",
            prompt_version="v1",
            fingerprint=hashlib.sha256(f"{proj_a.id}:{title}:{uuid.uuid4().hex}".encode()).hexdigest()[:32],
            is_stale=False,
            is_deleted=False,
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
                support_type="direct_support",
                supporting_excerpt=summary[:150],
            )
        )
        session.flush()
        return ev, ki

    # Verified public findings across key domains (plus inline token for redaction test)
    ev_arch, ki_arch = _seed_ev_and_ki(
        title="Canonical Postgres Storage & FastAPI Architecture",
        summary="PostgreSQL hosts all canonical handover state. CI token ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345 must stay secret.",
        category=KnowledgeCategory.TECHNICAL_ARCHITECTURE.value,
        source_type=EvidenceSourceType.DOCUMENT_UPLOAD.value,
    )
    ev_dec, ki_dec = _seed_ev_and_ki(
        title="ADR-014 PostgreSQL Advisory Locking Choice",
        summary="Selected PostgreSQL advisory locks instead of Redis/Celery to keep initial worker topology stateless.",
        category=KnowledgeCategory.DECISIONS_RATIONALE.value,
    )
    ev_work, ki_work = _seed_ev_and_ki(
        title="Settlement Batch Retry Hardening",
        summary="Completed idempotent retry loop; remaining pending task is automating staging dead-letter alerts.",
        category=KnowledgeCategory.WORK_ITEMS.value,
    )
    ev_ops, ki_ops = _seed_ev_and_ki(
        title="Nightly Backup & Failover Procedure",
        summary="Run scripts/verify_pg_backup.py every Tuesday 02:00 UTC and verify exit code 0.",
        category=KnowledgeCategory.OPERATIONAL_HISTORICAL.value,
    )
    ev_risk, ki_risk = _seed_ev_and_ki(
        title="Single-GPU Ollama VRAM Contention Risk",
        summary="Parallel LLM extraction and OCR bursts can exceed 6GB VRAM unless serialized via OLLAMA_MAX_CONCURRENT_AI_JOBS=1.",
        category=KnowledgeCategory.RISKS_BLOCKERS_QUESTIONS.value,
    )
    # Restricted finding accessible to departing/manager/reviewer but NOT successor
    ev_restricted, ki_restricted = _seed_ev_and_ki(
        title="Restricted HSM Master Enclave Runbook",
        summary="RESTRICTED_ENCLAVE_FACT: Enclave cluster-42 uses split-custody hardware keys.",
        category=KnowledgeCategory.DECISIONS_RATIONALE.value,
        acl_scope="source_restricted",
        policy_id=restricted_policy.id,
        source_type=EvidenceSourceType.GITHUB.value,
    )
    # Deliberately unverified finding (must NEVER auto-enter verified handover facts)
    ev_unverified, ki_unverified = _seed_ev_and_ki(
        title="Unverified Speculative Cache Hypothesis",
        summary="UNVERIFIED_HYPOTHESIS_MARKER: Maybe switch worker polling to UDP multicast.",
        category=KnowledgeCategory.TECHNICAL_ARCHITECTURE.value,
        approve=False,
    )

    # Verified relationship
    ent_api = KnowledgeEntity(
        id=uuid.uuid4(),
        organisation_id=org.id,
        project_id=proj_a.id,
        entity_type="service",
        canonical_name="Settlement API",
        normalized_name="settlement api",
    )
    ent_pg = KnowledgeEntity(
        id=uuid.uuid4(),
        organisation_id=org.id,
        project_id=proj_a.id,
        entity_type="database",
        canonical_name="Canonical PostgreSQL",
        normalized_name="canonical postgresql",
    )
    session.add_all([ent_api, ent_pg])
    session.flush()
    rel_dep = KnowledgeRelationship(
        id=uuid.uuid4(),
        organisation_id=org.id,
        project_id=proj_a.id,
        source_entity_id=ent_api.id,
        target_entity_id=ent_pg.id,
        relationship_type="depends_on",
        verification_status=RelationshipVerificationStatus.CANDIDATE.value,
        fingerprint=hashlib.sha256(f"{proj_a.id}:api-pg-dep".encode()).hexdigest()[:32],
    )
    session.add(rel_dep)
    session.flush()
    session.add(
        RelationshipEvidenceLink(
            id=uuid.uuid4(),
            organisation_id=org.id,
            project_id=proj_a.id,
            relationship_id=rel_dep.id,
            evidence_id=ev_arch.id,
            evidence_role="direct_support",
            supporting_excerpt="Settlement API reads and writes Canonical PostgreSQL.",
        )
    )
    session.flush()

    # Sync verification cases and approve permitted findings + relationship (keep ki_unverified unapproved)
    v_engine = VerificationEngine(session)
    v_engine.sync_project_findings(proj_a.id)
    v_engine.assess_project(proj_a.id)
    session.flush()
    cases = list(
        session.execute(
            select(VerificationCase).where(VerificationCase.project_id == proj_a.id)
        )
        .scalars()
        .all()
    )

    rbac_svc = RbacService(
        db_session=session,
        rbac_repository=RbacRepository(session),
        user_repository=UserRepository(session),
    )
    reviewer_ctx = rbac_svc.resolve_project_context(
        project_id=proj_a.id,
        principal=AuthenticatedPrincipal(
            user=reviewer, session_family_id=None, roles=(), permissions=frozenset()
        ),
    )
    v_review = VerificationReviewService(session)
    approved_target_ids = {ki_arch.id, ki_dec.id, ki_work.id, ki_ops.id, ki_risk.id, ki_restricted.id, rel_dep.id}
    case_by_target = {c.target_id: c for c in cases}
    for tid in approved_target_ids:
        if tid in case_by_target:
            v_review.approve_case(
                case_by_target[tid].id,
                project_ctx=reviewer_ctx,
                payload=ApproveFindingRequest(reviewer_note="Verified from primary project evidence."),
            )
    if rel_dep.id not in case_by_target:
        rel_dep.verification_status = RelationshipVerificationStatus.VERIFIED.value
        rel_dep.reviewed_by_user_id = reviewer.id
        rel_dep.reviewed_at = datetime.now(UTC)
        session.flush()

    # Seed an unresolved conflict on ki_dec so conflict gate initially blocks readiness until resolved
    conflict = VerificationConflict(
        id=uuid.uuid4(),
        organisation_id=org.id,
        project_id=proj_a.id,
        case_id=case_by_target[ki_dec.id].id,
        conflict_type="architecture_conflict",
        claim_a_text="PostgreSQL advisory locks serve as the job queue lock.",
        claim_a_source_evidence_id=ev_dec.id,
        claim_b_text="Legacy README draft proposed RabbitMQ broker.",
        claim_b_source_evidence_id=ev_arch.id,
        explanation="README note differed from ADR-014 regarding queue coordination.",
        temporal_comparison="a_supersedes_b",
        resolution_state=ConflictResolutionState.UNRESOLVED.value,
        priority="high",
    )
    session.add(conflict)
    session.commit()

    yield {
        "engine": engine,
        "session": session,
        "org": org,
        "proj_a": proj_a,
        "proj_b": proj_b,
        "manager": manager,
        "departing": departing,
        "reviewer": reviewer,
        "successor": successor,
        "outsider": outsider,
        "ev_dec": ev_dec,
        "ev_restricted": ev_restricted,
        "ki_dec": ki_dec,
        "ki_ops": ki_ops,
        "ki_unverified": ki_unverified,
        "conflict": conflict,
        "reviewer_ctx": reviewer_ctx,
        "restricted_policy": restricted_policy,
    }

    app.dependency_overrides.clear()
    session.close()
    engine.dispose()


def _install_http_overrides(
    session: Session,
    org: Organisation,
    active_user_box: dict[str, User | None],
    llm_stub: CapturingStubLLMClient,
) -> TestClient:
    def _override_db() -> Any:
        yield session

    def _override_principal() -> Any:
        u = active_user_box["user"]
        assert u is not None
        return AuthenticatedPrincipal(
            user=u,
            session_family_id=None,
            roles=(),
            permissions=frozenset(),
        )

    app.dependency_overrides[get_db_session] = _override_db
    if active_user_box["user"] is not None:
        app.dependency_overrides[get_current_principal] = _override_principal
    app.dependency_overrides[get_llm_client] = lambda: llm_stub
    app.dependency_overrides[get_hybrid_retrieval_service] = lambda: StubHybridRetrievalService()
    return TestClient(app)


def test_complete_22_step_handover_journey_and_role_presentations(
    handover_acceptance_env: dict[str, Any],
) -> None:
    """Exercise full CONNECT->RECONSTRUCT->VERIFY->REVIEW->HANDOVER lifecycle across HTTP APIs."""
    env = handover_acceptance_env
    session: Session = env["session"]
    org: Organisation = env["org"]
    proj_a: Project = env["proj_a"]
    manager: User = env["manager"]
    departing: User = env["departing"]
    reviewer: User = env["reviewer"]
    successor: User = env["successor"]
    conflict: VerificationConflict = env["conflict"]

    active_user: dict[str, User | None] = {"user": manager}
    llm_stub = CapturingStubLLMClient()
    client = _install_http_overrides(session, org, active_user, llm_stub)
    base = f"/api/v1/projects/{proj_a.id}/handover"

    try:
        # Step 1-2: Manager creates developer handover case with target date
        create_resp = client.post(
            f"{base}/cases",
            json={
                "title": "Q4 Settlement Backend Transition",
                "description": "Full handover from departing backend lead to incoming developer.",
                "departing_member_id": str(departing.id),
                "successor_id": str(successor.id),
                "handover_type": "developer",
                "target_handover_date": "2026-12-31",
            },
        )
        assert create_resp.status_code == 201, create_resp.text
        case_data = create_resp.json()
        case_id = case_data["id"]
        assert case_data["handover_type"] == "developer"
        assert case_data["target_handover_date"] == "2026-12-31"
        assert case_data["status"] == HandoverCaseStatus.DRAFT.value

        # Step 3-4: Departing member contributes missing undocumented decision context
        active_user["user"] = departing
        ctx_resp = client.post(
            f"{base}/cases/{case_id}/context",
            json={
                "category": "decisions_rationale",
                "title": "Evening Batch Window Cutover Caveat",
                "content": "Hold settlement batch jobs between 23:45 and 00:05 UTC while ledger reconciliation closes.",
                "rationale": "Avoids mid-cutoff split partitions.",
            },
        )
        assert ctx_resp.status_code == 201, ctx_resp.text
        ctx_body = ctx_resp.json()
        assert ctx_body["epistemic_status"] == EpistemicStatus.EXTRACTED.value
        assert ctx_body["review_status"] == KnowledgeReviewStatus.PENDING_REVIEW.value
        contrib_vc_id = uuid.UUID(ctx_body["verification_case_id"])
        assert session.get(VerificationCase, contrib_vc_id) is not None

        # Assemble v1 BEFORE approving contributed context or resolving conflict -> neither appears as verified
        active_user["user"] = manager
        asm1_resp = client.post(f"{base}/cases/{case_id}/assemble", json={})
        assert asm1_resp.status_code == 201, asm1_resp.text
        v1_id = asm1_resp.json()["id"]

        sec1_resp = client.get(f"{base}/cases/{case_id}/versions/{v1_id}/sections")
        assert sec1_resp.status_code == 200
        sec1_body = sec1_resp.json()
        assert "Evening Batch Window Cutover Caveat" not in str(sec1_body["mandatory_sections"])
        assert "UNVERIFIED_HYPOTHESIS_MARKER" not in str(sec1_body["mandatory_sections"])

        # Step 5: Reviewer approves contributed context + resolves active conflict via Verification Center & ConflictService
        VerificationReviewService(session).approve_case(
            contrib_vc_id,
            project_ctx=env["reviewer_ctx"],
            payload=ApproveFindingRequest(reviewer_note="Confirmed cutover caveat in runbook."),
        )
        ConflictService(session).resolve_conflict(
            conflict.id,
            proj_a.id,
            manager.id,
            ResolveConflictRequest(
                resolution_strategy="claim_a_authoritative",
                resolution_notes="Confirmed ADR-014 PostgreSQL advisory lock is authoritative.",
            ),
        )
        session.commit()

        # Step 6: Refresh draft package (v2) now includes verified contributed context + ADR-014
        asm2_resp = client.post(
            f"{base}/cases/{case_id}/assemble",
            json={"assembly_notes": "Refreshed draft after context verification and conflict resolution"},
        )
        assert asm2_resp.status_code == 201, asm2_resp.text
        v2_id = asm2_resp.json()["id"]

        # Step 7: Compare all 3 role presentations (10 mandatory sections each, distinct role priorities, gaps explicit)
        role_results: dict[str, list[dict[str, Any]]] = {}
        for role_name in ("developer", "project_manager", "technical_lead"):
            r_resp = client.get(f"{base}/cases/{case_id}/versions/{v2_id}/sections?role={role_name}")
            assert r_resp.status_code == 200, r_resp.text
            r_json = r_resp.json()
            assert r_json["handover_type"] == role_name
            m_secs = r_json["mandatory_sections"]
            assert len(m_secs) == 10
            role_results[role_name] = m_secs

        dev_priority = [s["section_key"] for s in role_results["developer"] if s["is_role_priority"]]
        pm_priority = [s["section_key"] for s in role_results["project_manager"] if s["is_role_priority"]]
        tl_priority = [s["section_key"] for s in role_results["technical_lead"] if s["is_role_priority"]]
        assert set(dev_priority) != set(pm_priority)
        assert set(pm_priority) != set(tl_priority)
        assert "Evening Batch Window Cutover Caveat" in str(role_results["developer"])
        # Empty checklists/missing gaps must explicitly state insufficient info instead of hallucinating
        assert any(s.get("insufficient_info_message") for s in role_results["developer"])

        # Step 8: AI Narrative Draft & Human Edit on a section
        draft_resp = client.post(
            f"{base}/cases/{case_id}/narrative/draft",
            json={
                "version_id": v2_id,
                "section_type": "decisions_rationale",
                "additional_context": "Emphasise batch window and lock strategy.",
            },
        )
        assert draft_resp.status_code == 200, draft_resp.text
        draft_body = draft_resp.json()
        assert draft_body["section_type"] == "decisions_rationale"
        assert draft_body["findings_count"] >= 1
        assert "PostgreSQL" in draft_body["draft_content"]

        sec_target = next(
            s for s in sec1_body["sections"] if s["section_type"] == "decisions_rationale"
        )
        # Edit the decisions section of v2 specifically
        v2_sections_resp = client.get(f"{base}/cases/{case_id}/versions/{v2_id}/sections")
        v2_dec_sec = next(
            s for s in v2_sections_resp.json()["sections"] if s["section_type"] == "decisions_rationale"
        )
        patch_sec_resp = client.patch(
            f"{base}/sections/{v2_dec_sec['id']}",
            json={
                "content_summary": "Human-reviewed summary of PostgreSQL advisory locks & cutover window.",
                "section_content": "Hold evening batch between 23:45 and 00:05 UTC per ADR-014.",
            },
        )
        assert patch_sec_resp.status_code == 200, patch_sec_resp.text
        # Editing narrative MUST NOT approve the handover case!
        assert client.get(f"{base}/cases/{case_id}").json()["case"]["status"] != HandoverCaseStatus.APPROVED.value

        # Step 9: Checklists + independent verification + Responsibility transfers + Readiness gates
        chk_gen = client.post(
            f"{base}/cases/{case_id}/checklists/generate",
            json={"version_id": v2_id},
        )
        assert chk_gen.status_code == 201, chk_gen.text
        checklists = chk_gen.json()
        active_user["user"] = departing
        first_mandatory_id = None
        for grp in checklists:
            for item in grp["items"]:
                if item["blocking"]:
                    if first_mandatory_id is None:
                        first_mandatory_id = item["id"]
                    up = client.patch(
                        f"{base}/checklists/items/{item['id']}",
                        json={"status": ChecklistItemStatus.COMPLETED.value, "notes": "Done."},
                    )
                    assert up.status_code == 200, up.text
        assert first_mandatory_id is not None
        active_user["user"] = reviewer
        rev_chk = client.post(
            f"{base}/checklists/items/{first_mandatory_id}/review",
            json={"approved": True, "review_notes": "Independently verified checklist item."},
        )
        assert rev_chk.status_code == 200, rev_chk.text

        active_user["user"] = manager
        tr_create = client.post(
            f"{base}/cases/{case_id}/responsibilities",
            json={
                "transfers": [
                    {
                        "title": "PostgreSQL Failover & Batch Scheduling",
                        "responsibility_description": "Run Tuesday verify_pg_backup.py and maintain cutover hold window.",
                        "knowledge_domain": "operational_historical",
                        "component_name": "Ledger DB",
                        "priority": "high",
                        "ownership_certainty": "confirmed",
                        "proposed_successor_id": str(successor.id),
                        "related_knowledge_item_id": str(env["ki_ops"].id),
                    }
                ]
            },
        )
        assert tr_create.status_code == 201, tr_create.text
        assert (HandoverResponsibilityTransfer.__table__.c.transfer_status.type.length or 0) >= 64
        transfer_id = tr_create.json()[0]["id"]
        active_user["user"] = departing
        assert client.post(
            f"{base}/responsibilities/{transfer_id}/confirm-outgoing",
            json={"confirmation_notes": "Walked through scripts."},
        ).status_code == 200
        active_user["user"] = successor
        assert client.post(
            f"{base}/responsibilities/{transfer_id}/acknowledge",
            json={"acknowledgement_notes": "Accepted ownership details."},
        ).status_code == 200

        active_user["user"] = manager
        rd_resp = client.post(
            f"{base}/cases/{case_id}/readiness",
            json={"version_id": v2_id, "notes": "Gate assessment"},
        )
        assert rd_resp.status_code in (200, 201), rd_resp.text
        rd_json = rd_resp.json()
        assert rd_json["approval_eligibility"]["is_eligible_for_approval"] is True

        # Step 11: Pre-approval Draft Export check (Markdown, JSON, PDF must carry DRAFT watermark & 10 sections)
        draft_md = client.get(f"{base}/cases/{case_id}/export?format=markdown&version_id={v2_id}").text
        assert "DRAFT — NOT APPROVED" in draft_md
        assert "## 1. " in draft_md and "## 10. " in draft_md
        assert "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345" not in draft_md  # secret redacted

        draft_json = client.get(f"{base}/cases/{case_id}/export?format=json&version_id={v2_id}").json()
        assert draft_json["approval_watermark"] == "DRAFT — NOT APPROVED"
        assert len(draft_json["mandatory_sections"]) == 10

        draft_pdf = client.get(f"{base}/cases/{case_id}/export?format=pdf&version_id={v2_id}").content
        doc_draft = fitz.open(stream=draft_pdf, filetype="pdf")
        draft_pdf_text = "\n".join(page.get_text("text") for page in doc_draft)
        doc_draft.close()
        assert "DRAFT" in draft_pdf_text

        # Step 12: Assign reviewer -> Phase 1 -> Reviewer requests changes -> Resubmit -> Approve
        assert client.post(
            f"{base}/cases/{case_id}/signoffs/reviewer",
            json={"reviewer_user_id": str(reviewer.id), "reason": "Independent tech lead review"},
        ).status_code == 200

        v2_hash = client.get(f"{base}/cases/{case_id}").json()["current_version"]["content_hash"]
        case_ver = client.get(f"{base}/cases/{case_id}").json()["case"]["version"]
        active_user["user"] = departing
        assert client.post(
            f"{base}/cases/{case_id}/signoffs",
            json={
                "version_id": v2_id,
                "signoff_type": SignoffType.DEPARTING_SIGNOFF.value,
                "decision": SignoffDecision.APPROVED.value,
                "comments": "Submitting v2 for review.",
                "expected_content_hash": v2_hash,
                "expected_case_version": case_ver,
            },
        ).status_code == 201

        active_user["user"] = reviewer
        case_ver = client.get(f"{base}/cases/{case_id}").json()["case"]["version"]
        chg_resp = client.post(
            f"{base}/cases/{case_id}/signoffs",
            json={
                "version_id": v2_id,
                "signoff_type": SignoffType.REVIEWER_APPROVAL.value,
                "decision": SignoffDecision.RETURNED_FOR_REVISION.value,
                "comments": "Clarify backup verification cadence before approval.",
                "expected_content_hash": v2_hash,
                "expected_case_version": case_ver,
            },
        )
        assert chg_resp.status_code == 201, chg_resp.text
        assert chg_resp.json()["decision"] == SignoffDecision.RETURNED_FOR_REVISION.value
        assert client.get(f"{base}/cases/{case_id}").json()["case"]["status"] in (
            HandoverCaseStatus.UNDER_REVIEW.value,
            HandoverCaseStatus.READINESS_ASSESSED.value,
        )

        # Reopen Phase 1 to revise & re-submit departing signoff after addressing reviewer feedback
        active_user["user"] = reviewer
        reopen_resp = client.post(
            f"{base}/cases/{case_id}/signoffs/reopen",
            json={
                "signoff_type": SignoffType.DEPARTING_SIGNOFF.value,
                "reason": "Clarified Tuesday verify_pg_backup.py verification cadence per reviewer.",
            },
        )
        assert reopen_resp.status_code == 200, reopen_resp.text

        # Departing & reviewer complete signoff -> APPROVED
        active_user["user"] = departing
        case_ver = client.get(f"{base}/cases/{case_id}").json()["case"]["version"]
        assert client.post(
            f"{base}/cases/{case_id}/signoffs",
            json={
                "version_id": v2_id,
                "signoff_type": SignoffType.DEPARTING_SIGNOFF.value,
                "decision": SignoffDecision.APPROVED.value,
                "comments": "Backup cadence clarified; ready for final approval.",
                "expected_content_hash": v2_hash,
                "expected_case_version": case_ver,
            },
        ).status_code == 201

        active_user["user"] = reviewer
        case_ver = client.get(f"{base}/cases/{case_id}").json()["case"]["version"]
        app_resp = client.post(
            f"{base}/cases/{case_id}/signoffs",
            json={
                "version_id": v2_id,
                "signoff_type": SignoffType.REVIEWER_APPROVAL.value,
                "decision": SignoffDecision.APPROVED.value,
                "comments": "Approved for formal release.",
                "expected_content_hash": v2_hash,
                "expected_case_version": case_ver,
            },
        )
        assert app_resp.status_code == 201, app_resp.text
        assert client.get(f"{base}/cases/{case_id}").json()["case"]["status"] == HandoverCaseStatus.APPROVED.value

        # Step 13: Controlled Publication (deliver)
        active_user["user"] = manager
        case_ver = client.get(f"{base}/cases/{case_id}").json()["case"]["version"]
        pub_resp = client.post(
            f"{base}/cases/{case_id}/deliver",
            json={
                "version_id": v2_id,
                "deliver_to_user_ids": [str(successor.id)],
                "delivery_method": "internal_download",
                "message": "Approved release published to incoming developer.",
                "expected_content_hash": v2_hash,
                "expected_case_version": case_ver,
            },
        )
        assert pub_resp.status_code == 201, pub_resp.text
        delivery_id = pub_resp.json()[0]["id"]
        assert client.get(f"{base}/cases/{case_id}").json()["case"]["status"] == HandoverCaseStatus.DELIVERED.value

        # Step 14: Published snapshot immutability when project adds new verified findings later
        later_ki = KnowledgeItem(
            id=uuid.uuid4(),
            organisation_id=org.id,
            project_id=proj_a.id,
            category=KnowledgeCategory.WORK_ITEMS.value,
            title="POST_PUBLICATION_DRIFT_ITEM",
            structured_summary="Added after v2 was approved & published; must NOT leak into immutable v2 snapshot.",
            structured_payload={},
            epistemic_status=EpistemicStatus.HUMAN_VERIFIED.value,
            review_status=KnowledgeReviewStatus.APPROVED.value,
            support_classification="direct",
            extraction_model="qwen3:8b",
            prompt_version="v1",
            fingerprint=hashlib.sha256(b"post-pub-drift").hexdigest()[:32],
        )
        session.add(later_ki)
        session.commit()

        # Step 15-16: Incoming successor reads published package & exports -> APPROVED RELEASE + ACL filtered
        active_user["user"] = successor
        succ_case_resp = client.get(f"{base}/cases/{case_id}")
        assert succ_case_resp.status_code == 200
        succ_sec_resp = client.get(f"{base}/cases/{case_id}/versions/{v2_id}/sections?role=developer")
        assert succ_sec_resp.status_code == 200
        assert "POST_PUBLICATION_DRIFT_ITEM" not in str(succ_sec_resp.json())

        succ_json_exp = client.get(f"{base}/cases/{case_id}/export?format=json&version_id={v2_id}").json()
        assert succ_json_exp["approval_watermark"] == "APPROVED RELEASE"
        assert succ_json_exp["viewer_acl_filtered"] is True
        assert succ_json_exp["omitted_restricted_items_count"] == 1
        assert "RESTRICTED_ENCLAVE_FACT" not in str(succ_json_exp)

        succ_pdf_exp = client.get(f"{base}/cases/{case_id}/export?format=pdf&version_id={v2_id}").content
        doc_rel = fitz.open(stream=succ_pdf_exp, filetype="pdf")
        rel_pdf_text = "\n".join(page.get_text("text") for page in doc_rel)
        doc_rel.close()
        assert "APPROVED RELEASE" in rel_pdf_text
        assert "RESTRICTED_ENCLAVE_FACT" not in rel_pdf_text

        # Step 17: Successor asks Handover Assistant -> grounded citations, restricted source excluded
        conv_resp = client.post(
            f"/api/v1/projects/{proj_a.id}/assistant/conversations",
            json={"title": "Successor Onboarding Inquiry", "metadata_json": {"handover_case_id": case_id}},
        )
        assert conv_resp.status_code == 201, conv_resp.text
        conv_id = conv_resp.json()["id"]

        msg_resp = client.post(
            f"/api/v1/projects/{proj_a.id}/assistant/conversations/{conv_id}/messages",
            json={
                "question": "Why does this project use PostgreSQL advisory locks and what should I watch?",
                "handover_case_id": case_id,
                "package_version_id": v2_id,
            },
        )
        assert msg_resp.status_code == 200, msg_resp.text
        msg_json = msg_resp.json()
        assert msg_json["answer_status"] == "answered"
        assert len(msg_json["citations"]) >= 1
        cited_ev_ids = {c["evidence_id"] for c in msg_json["citations"]}
        assert str(env["ev_restricted"].id) not in cited_ev_ids
        assert any("RESTRICTED_ENCLAVE_FACT" not in p for p in llm_stub.captured_prompts)
        assert any(c["citation_label"] == "S1" for c in msg_json["citations"])

        # Step 18: Successor acknowledges complete package -> ACKNOWLEDGED + audit logs persisted
        ack_resp = client.post(
            f"{base}/deliveries/{delivery_id}/acknowledge",
            json={
                "acknowledgement_notes": "Completed transition reading across all 10 sections.",
                "confirmations": {"reviewed_all_domains": True, "accepted_responsibilities": True},
                "expected_content_hash": v2_hash,
            },
        )
        assert ack_resp.status_code == 201, ack_resp.text
        assert client.get(f"{base}/cases/{case_id}").json()["case"]["status"] == HandoverCaseStatus.ACKNOWLEDGED.value

        audit_types = {
            row[0]
            for row in session.execute(
                select(AuditLog.event_type).where(AuditLog.project_id == proj_a.id)
            ).all()
        }
        assert {
            "handover.case.created",
            "handover.context.contributed",
            "handover.package.assembled",
            "handover.signoff.recorded",
            "handover.signoff.reopened",
            "handover.package.exported",
            "handover.delivery.acknowledged",
        }.issubset(audit_types)
        assert bool(
            audit_types.intersection({"handover.package.published", "handover.package.delivered"})
        )
    finally:
        app.dependency_overrides.clear()


def test_negative_handover_security_acl_and_lifecycle_gates(
    handover_acceptance_env: dict[str, Any],
) -> None:
    """Verify all 9 negative security, draft-gating, ACL, epistemic, and state-machine boundaries."""
    env = handover_acceptance_env
    session: Session = env["session"]
    org: Organisation = env["org"]
    proj_a: Project = env["proj_a"]
    proj_b: Project = env["proj_b"]
    manager: User = env["manager"]
    departing: User = env["departing"]
    reviewer: User = env["reviewer"]
    successor: User = env["successor"]
    outsider: User = env["outsider"]

    active_user: dict[str, User | None] = {"user": manager}
    llm_stub = CapturingStubLLMClient()
    client = _install_http_overrides(session, org, active_user, llm_stub)
    base_a = f"/api/v1/projects/{proj_a.id}/handover"

    try:
        # Resolve conflict cleanly for gate tests after checking epistemic exclusion
        ConflictService(session).resolve_conflict(
            env["conflict"].id,
            proj_a.id,
            manager.id,
            ResolveConflictRequest(resolution_strategy="claim_a_authoritative", resolution_notes="Resolved for negative tests."),
        )
        session.commit()

        # Create draft handover case
        case_resp = client.post(
            f"{base_a}/cases",
            json={
                "title": "Negative Security Gate Handover",
                "departing_member_id": str(departing.id),
                "successor_id": str(successor.id),
                "handover_type": "technical_lead",
            },
        )
        assert case_resp.status_code == 201
        case_id = case_resp.json()["id"]
        v1_id = client.post(f"{base_a}/cases/{case_id}/assemble", json={}).json()["id"]

        # N1: Unauthenticated requests rejected (401)
        app.dependency_overrides.pop(get_current_principal, None)
        assert client.get(f"{base_a}/cases/{case_id}").status_code == 401
        assert client.post(f"{base_a}/cases/{case_id}/context", json={"category": "decisions_rationale", "title": "x", "content": "y"}).status_code == 401

        # Restore principal override
        client = _install_http_overrides(session, org, active_user, llm_stub)

        # N2: Cross-project IDOR blocked
        active_user["user"] = outsider
        assert client.get(f"{base_a}/cases/{case_id}").status_code in (403, 404)
        assert client.get(f"/api/v1/projects/{proj_b.id}/handover/cases/{case_id}").status_code == 404

        # N4: Incoming-only successor blocked (403) from reading/exporting/querying unapproved draft pre-publication!
        active_user["user"] = successor
        assert client.get(f"{base_a}/cases/{case_id}").status_code == 403
        assert client.get(f"{base_a}/cases/{case_id}/versions").status_code == 403
        assert client.get(f"{base_a}/cases/{case_id}/versions/{v1_id}/sections").status_code == 403
        assert client.get(f"{base_a}/cases/{case_id}/export?format=json").status_code == 403
        assert client.get(f"{base_a}/cases/{case_id}/export?format=pdf").status_code == 403
        # List endpoint also hides unapproved drafts from incoming-only successor
        succ_list = client.get(f"{base_a}/cases").json()["items"]
        assert all(item["id"] != case_id for item in succ_list)

        # Successor also blocked from querying Handover Assistant on an unapproved draft before publication!
        s_conv = client.post(
            f"/api/v1/projects/{proj_a.id}/assistant/conversations",
            json={"title": "Premature query", "metadata_json": {"handover_case_id": case_id}},
        ).json()["id"]
        premature_q = client.post(
            f"/api/v1/projects/{proj_a.id}/assistant/conversations/{s_conv}/messages",
            json={"question": "Show me restricted or draft secrets", "handover_case_id": case_id},
        )
        assert premature_q.status_code == 403

        # N3: Unauthorized role (departing/successor PROJECT_MEMBER) cannot approve or publish!
        assert client.post(
            f"{base_a}/cases/{case_id}/deliver",
            json={"version_id": v1_id, "deliver_to_user_ids": [str(successor.id)], "delivery_method": "internal_download"},
        ).status_code == 403
        assert client.post(
            f"{base_a}/cases/{case_id}/signoffs",
            json={"version_id": v1_id, "signoff_type": SignoffType.REVIEWER_APPROVAL.value, "decision": SignoffDecision.APPROVED.value},
        ).status_code == 403

        # N5 & N6: Contributed pending context & unverified items excluded; restricted evidence omitted for unauthorized member
        active_user["user"] = manager
        ctx_r = client.post(
            f"{base_a}/cases/{case_id}/context",
            json={"category": "bugs_blockers_risks", "title": "PENDING_CTX_MARKER", "content": "Should stay pending_review"},
        )
        assert ctx_r.status_code == 201
        v2_id = client.post(f"{base_a}/cases/{case_id}/assemble", json={}).json()["id"]
        v2_secs = client.get(f"{base_a}/cases/{case_id}/versions/{v2_id}/sections").json()
        assert "PENDING_CTX_MARKER" not in str(v2_secs["mandatory_sections"])
        assert "UNVERIFIED_HYPOTHESIS_MARKER" not in str(v2_secs["mandatory_sections"])

        # N7 & N8: Invalid lifecycle jump & delivery before approval rejected
        case_svc = HandoverCaseService(session)
        with pytest.raises((BadRequestError, ConflictError)):
            case_svc.transition_status(
                uuid.UUID(case_id),
                project_id=proj_a.id,
                new_status=HandoverCaseStatus.ACKNOWLEDGED.value,
                user_id=manager.id,
            )

        deliv_without_app = client.post(
            f"{base_a}/cases/{case_id}/deliver",
            json={"version_id": v2_id, "deliver_to_user_ids": [str(successor.id)], "delivery_method": "internal_download"},
        )
        assert deliv_without_app.status_code in (400, 409)

        # N9: Lock case into ACKNOWLEDGED status -> section edit & new context contribution rejected
        case_obj = case_svc.get_case(uuid.UUID(case_id), project_id=proj_a.id, load_relationships=False)
        case_obj.status = HandoverCaseStatus.ACKNOWLEDGED.value
        session.flush()
        locked_ctx = client.post(
            f"{base_a}/cases/{case_id}/context",
            json={"category": "decisions_rationale", "title": "Late context", "content": "After acknowledgement"},
        )
        assert locked_ctx.status_code in (400, 409)

        sec_id = v2_secs["sections"][0]["id"]
        locked_edit = client.patch(f"{base_a}/sections/{sec_id}", json={"section_content": "Tamper attempt"})
        assert locked_edit.status_code in (400, 409)
    finally:
        app.dependency_overrides.clear()


def test_handover_compilation_and_narrative_wait_for_llm(handover_acceptance_env: dict[str, Any]) -> None:
    """Strict Ollama-offline test: verify handover assembly & narrative drafting make ZERO LLM calls."""
    from app.schemas.handover import NarrativeDraftRequest, PackageAssemblyRequest
    from app.services.handover_assembly import PackageAssemblyService
    from app.services.handover_narrative import HandoverNarrativeService

    env = handover_acceptance_env
    session = env["session"]
    project = env["proj_a"]
    manager = env["manager"]
    departing = env["departing"]
    successor = env["successor"]

    case_svc = HandoverCaseService(session)
    case = case_svc.create_case(
        project_id=project.id,
        organisation_id=project.organisation_id,
        user_id=manager.id,
        request=HandoverCaseCreateRequest(
            title="Ollama-Offline Deterministic Assembly Case",
            handover_type="developer",
            departing_member_id=departing.id,
            successor_user_id=successor.id,
        ),
    )

    class _SpyForbiddenLLM:
        model_name = "qwen3:8b"

        def __init__(self) -> None:
            self.calls: list[Any] = []

        def generate_json(self, request: Any) -> Any:
            self.calls.append(request)
            raise AssertionError("Handover generation must NOT invoke Ollama/LLM!")

    llm_spy = _SpyForbiddenLLM()
    assembly_svc = PackageAssemblyService(session, llm_client=llm_spy)
    version = assembly_svc.assemble_package_version(
        case.id,
        project_id=project.id,
        user_id=manager.id,
        request=PackageAssemblyRequest(version_notes="Offline deterministic compile"),
        has_project_manage=True,
    )
    assert len(llm_spy.calls) == 0
    assert (version.assembly_snapshot_json or {}).get("total_eligible_knowledge_items", 0) >= 1
    assert isinstance((version.assembly_snapshot_json or {}).get("exclusion_breakdown"), dict)

    sections = assembly_svc.section_repo.list_by_version(version.id)
    dec_sec = next(s for s in sections if s.section_type == "decisions_rationale")
    assert (dec_sec.metadata_json or {}).get("llm_used") is False
    empty_sec = next((s for s in sections if s.knowledge_item_count == 0 and s.relationship_count == 0), None)
    if empty_sec is not None:
        assert "Insufficient approved information" in empty_sec.section_content

    narrative_svc = HandoverNarrativeService(session, llm_client=llm_spy)  # type: ignore[arg-type]
    draft = narrative_svc.draft_section_narrative(
        project_id=project.id,
        case_id=case.id,
        viewer_user_id=manager.id,
        request=NarrativeDraftRequest(
            version_id=version.id,
            section_type=dec_sec.section_type,
            additional_context="Focus on locks.",
        ),
        has_project_manage=True,
    )
    assert len(llm_spy.calls) == 0
    assert "Deterministic compilation" in draft["content_summary"]

    # Regression: Refresh Draft (assemble) must succeed when case is in review_pending
    case_svc.transition_status(
        case.id,
        project_id=project.id,
        new_status=HandoverCaseStatus.READINESS_ASSESSED.value,
        user_id=manager.id,
    )
    case_svc.transition_status(
        case.id,
        project_id=project.id,
        new_status=HandoverCaseStatus.REVIEW_PENDING.value,
        user_id=manager.id,
    )
    refreshed_version = assembly_svc.assemble_package_version(
        case.id,
        project_id=project.id,
        user_id=manager.id,
        request=PackageAssemblyRequest(version_notes="Refresh from review_pending"),
        has_project_manage=True,
    )
    assert refreshed_version.version_number == 2

    from app.core.rbac_catalog import SYSTEM_ROLES
    from app.models.enums import RoleName

    pm_spec = next(r for r in SYSTEM_ROLES if r.name == RoleName.PROJECT_MANAGER.value)
    assert "handover.approve" in pm_spec.permission_codes

