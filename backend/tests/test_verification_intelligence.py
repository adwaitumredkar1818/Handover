"""Comprehensive automated test suite for Verification Intelligence (Phase 3).

Verifies:
1. Claim Support & Evidence Grounding Engine (verbatim, fuzzy token overlap, unsupported, hallucinated)
2. Temporal Precedence Evaluation (timezone-aware datetimes and ISO strings)
3. Cross-Source Conflict Detection (Jira, GitHub PRs, markdown docs, Slack)
4. Freshness, Staleness & Supersession Analysis (STALE_KNOWLEDGE)
5. Structural & Semantic Duplicate Detection (fingerprints, title similarity, duplicate relationships)
6. Calibrated Composite Confidence Scoring (authority, coverage, freshness, penalties)
7. Advisory AI Integration (Ollama qwen3:8b, 5s timeout, deterministic fallbacks, non-blocking safety)
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.core.rbac_catalog import deterministic_rbac_id
from app.models.enums import (
    ConflictResolutionState,
    ConflictType,
    EpistemicStatus,
    EvidenceProcessingStatus,
    EvidenceSourceType,
    IssueResolutionState,
    KnowledgeReviewStatus,
    MachineAssessmentStatus,
    OrganisationStatus,
    ProjectStatus,
    ProjectVisibility,
    RelationshipBasis,
    RoleName,
    TemporalComparison,
    UserStatus,
    VerificationCaseStatus,
    VerificationIssueType,
    VerificationPriority,
    VerificationSeverity,
    VerificationTargetType,
)
from app.models.evidence import EvidenceChunk, EvidenceItem
from app.models.knowledge import KnowledgeEvidenceLink, KnowledgeItem
from app.models.organisation import Organisation
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
    VerificationIssue,
)
from app.services.conflict_detection import (
    ConflictDetectionEngine,
    evaluate_temporal_precedence,
)
from app.services.llm import LLMExecutionError, LLMGenerationRequest, LLMGenerationResult, StructuredLLMClient
from app.services.verification_ai import (
    AIAssistedVerificationService,
    _deterministic_fallback_clarifications,
    _deterministic_fallback_conflict_explanation,
)
from app.services.verification_engine import (
    DeterministicVerificationEngine,
    VerificationIntelligenceEngine,
    calculate_composite_confidence,
    verify_claim_support,
    verify_excerpt_grounding,
)
from app.services.verification_taxonomy import (
    get_severity_penalty,
    get_source_authority_weight,
    get_taxonomy_entry,
    is_handover_blocking_issue,
)
from tests.conftest import create_isolated_auth_context


def _create_test_context(session: Session) -> tuple[User, Organisation, Project]:
    """Helper creating active User, Organisation, and Project."""
    user = User(
        id=uuid.uuid4(),
        email=f"intel-reviewer-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$fakehash",
        full_name="Verification Intelligence Reviewer",
        status=UserStatus.ACTIVE,
    )
    session.add(user)
    session.flush()

    org = Organisation(
        id=uuid.uuid4(),
        name=f"Intel Org {uuid.uuid4().hex[:6]}",
        slug=f"intel-org-{uuid.uuid4().hex[:6]}",
        created_by_id=user.id,
        status=OrganisationStatus.ACTIVE,
    )
    session.add(org)
    session.flush()

    project = Project(
        id=uuid.uuid4(),
        organisation_id=org.id,
        created_by_id=user.id,
        owner_id=user.id,
        name=f"Intel Project {uuid.uuid4().hex[:6]}",
        slug=f"intel-proj-{uuid.uuid4().hex[:6]}",
        visibility=ProjectVisibility.ORGANISATION,
        status=ProjectStatus.ACTIVE,
    )
    session.add(project)
    session.flush()

    membership = ProjectMembership(
        id=uuid.uuid4(),
        project_id=project.id,
        user_id=user.id,
        role_id=deterministic_rbac_id("role", RoleName.REVIEWER.value),
        status="active",
    )
    session.add(membership)
    session.flush()

    return user, org, project


def _create_test_evidence(
    session: Session,
    org: Organisation,
    project: Project,
    user: User,
    *,
    title: str = "Test Spec.pdf",
    source_type: str = EvidenceSourceType.DOCUMENT_UPLOAD.value,
    status: str = EvidenceProcessingStatus.EXTRACTED.value,
    source_created_at: datetime | None = None,
) -> EvidenceItem:
    content_hash = hashlib.sha256(f"{title}-{uuid.uuid4()}".encode()).hexdigest()
    ev = EvidenceItem(
        id=uuid.uuid4(),
        organisation_id=org.id,
        project_id=project.id,
        uploaded_by_user_id=user.id,
        source_type=source_type,
        source_provider="local_upload",
        category="pdf_document",
        source_external_id=uuid.uuid4().hex,
        title=title,
        original_filename=title.lower().replace(" ", "_"),
        content_hash=content_hash,
        file_size_bytes=2048,
        mime_type="application/pdf",
        source_created_at=source_created_at or datetime.now(UTC),
        processing_status=status,
        acl_scope="project_members",
    )
    session.add(ev)
    session.flush()
    return ev


def _create_test_chunk(
    session: Session,
    org: Organisation,
    project: Project,
    ev: EvidenceItem,
    *,
    chunk_text: str,
    chunk_index: int = 0,
) -> EvidenceChunk:
    chunk_hash = hashlib.sha256(chunk_text.encode()).hexdigest()
    chunk = EvidenceChunk(
        id=uuid.uuid4(),
        organisation_id=org.id,
        project_id=project.id,
        evidence_id=ev.id,
        chunk_index=chunk_index,
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
    return chunk


def _create_test_knowledge_item(
    session: Session,
    org: Organisation,
    project: Project,
    *,
    title: str,
    category: str = "technical_architecture",
    primary_domain: str = "technical_and_architectural",
    summary: str = "Test knowledge summary description.",
    fingerprint: str | None = None,
    is_stale: bool = False,
    superseded_by_id: uuid.UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> KnowledgeItem:
    item = KnowledgeItem(
        id=uuid.uuid4(),
        organisation_id=org.id,
        project_id=project.id,
        category=category,
        primary_domain=primary_domain,
        title=title,
        structured_summary=summary,
        structured_payload=payload or {},
        support_classification="direct",
        extraction_model="qwen3:8b",
        prompt_version="1.0.0",
        fingerprint=fingerprint or uuid.uuid4().hex,
        epistemic_status=EpistemicStatus.EXTRACTED.value,
        review_status=KnowledgeReviewStatus.PENDING_REVIEW.value,
        is_stale=is_stale,
        superseded_by_id=superseded_by_id,
    )
    session.add(item)
    session.flush()
    return item


def _create_test_link(
    session: Session,
    org: Organisation,
    project: Project,
    item: KnowledgeItem,
    ev: EvidenceItem,
    chunk: EvidenceChunk | None = None,
    supporting_excerpt: str = "Supporting text excerpt",
) -> KnowledgeEvidenceLink:
    link = KnowledgeEvidenceLink(
        id=uuid.uuid4(),
        organisation_id=org.id,
        project_id=project.id,
        knowledge_item_id=item.id,
        evidence_id=ev.id,
        evidence_chunk_id=chunk.id if chunk else None,
        support_type="direct",
        supporting_excerpt=supporting_excerpt,
    )
    session.add(link)
    session.flush()
    return link


# ==============================================================================
# 1. Claim Support & Evidence Grounding Engine Tests
# ==============================================================================


def test_grounding_engine_verbatim_matching() -> None:
    """Verbatim matching accurately handles normalized whitespace, case, and curly quotes."""
    chunk = "Architecture Section 4: The system uses PostgreSQL for relational data and ChromaDB for embeddings."
    excerpt_exact = "The system uses PostgreSQL for relational data and ChromaDB for embeddings."
    excerpt_whitespace = "The  system   uses  PostgreSQL\nfor relational data and ChromaDB for embeddings."
    excerpt_curly = "“The system uses PostgreSQL for relational data and ChromaDB for embeddings.”"

    is_gr1, score1, mode1, _ = verify_excerpt_grounding(excerpt_exact, chunk)
    assert is_gr1 is True
    assert score1 == 1.0
    assert mode1 == "verbatim"

    is_gr2, score2, mode2, _ = verify_excerpt_grounding(excerpt_whitespace, chunk)
    assert is_gr2 is True
    assert score2 == 1.0
    assert mode2 == "verbatim"

    is_gr3, score3, mode3, _ = verify_excerpt_grounding(excerpt_curly, chunk)
    assert is_gr3 is True
    assert score3 == 1.0


def test_grounding_engine_fuzzy_semantic_token_matching() -> None:
    """Fuzzy token overlap matches excerpts with slight phrasing variations (>= 0.85)."""
    chunk = (
        "In our core backend design, we employ PostgreSQL to store all relational entities, "
        "while ChromaDB handles vector embeddings for semantic document search and similarity indexing."
    )
    # Excerpt has high token containment despite slight phrasing divergence
    excerpt = "We employ PostgreSQL to store relational entities while ChromaDB handles vector embeddings for search."

    is_gr, score, mode, details = verify_excerpt_grounding(excerpt, chunk)
    assert is_gr is True
    assert score >= 0.85
    assert mode == "fuzzy_token_overlap"
    assert details["containment_ratio"] >= 0.85


def test_grounding_engine_unsupported_and_hallucinated_claims(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ungrounded or hallucinated excerpts raise UNSUPPORTED_CLAIM with appropriate severity."""
    ctx = create_isolated_auth_context(monkeypatch)
    with ctx.session_factory() as session:
        user, org, project = _create_test_context(session)
        ev = _create_test_evidence(session, org, project, user, title="PaymentGateway.pdf")
        chunk = _create_test_chunk(
            session, org, project, ev,
            chunk_text="Payment integration uses Stripe Elements with server-side webhooks.",
        )
        item = _create_test_knowledge_item(
            session, org, project,
            title="Crypto Payment Processor",
            summary="System accepts Bitcoin and Ethereum via custom smart contract node.",
        )
        # Completely ungrounded claim
        _create_test_link(
            session, org, project, item, ev, chunk,
            supporting_excerpt="We explicitly support Bitcoin payments through our custom Web3 gateway.",
        )
        session.commit()

        engine = VerificationIntelligenceEngine(session)
        res = engine.assess_knowledge_item(item)

        assert res.machine_status == MachineAssessmentStatus.ISSUES_DETECTED
        assert res.priority == VerificationPriority.HIGH
        unsupported_issues = [i for i in res.issues if i["issue_type"] == VerificationIssueType.UNSUPPORTED_CLAIM]
        assert len(unsupported_issues) == 1
        assert unsupported_issues[0]["severity"] == VerificationSeverity.HIGH
        assert unsupported_issues[0]["details_json"]["match_mode"] == "unsupported"


def test_claim_substantive_support_check() -> None:
    """verify_claim_support checks whether title and summary terms are grounded in source chunks."""
    chunks = [
        "FastAPI service dispatches asynchronous background tasks to Redis queue with Celery workers.",
    ]
    supported, ratio, missing = verify_claim_support(
        "Celery Redis Task Queue",
        "FastAPI uses Celery workers and Redis for async task processing.",
        chunks,
    )
    assert supported is True
    assert ratio >= 0.70
    assert len(missing) <= 2

    # Hallucinated assertion
    supported_hallucinated, ratio_h, missing_h = verify_claim_support(
        "Kafka Streaming Pipeline",
        "Kafka message broker handles real-time distributed stream telemetry ingestion.",
        chunks,
    )
    assert supported_hallucinated is False
    assert ratio_h < 0.30
    assert "kafka" in missing_h


def test_grounding_engine_missing_evidence_critical(monkeypatch: pytest.MonkeyPatch) -> None:
    """Finding with zero evidence links triggers MISSING_EVIDENCE with CRITICAL severity."""
    ctx = create_isolated_auth_context(monkeypatch)
    with ctx.session_factory() as session:
        user, org, project = _create_test_context(session)
        item = _create_test_knowledge_item(
            session, org, project,
            title="Unanchored Specification Note",
        )
        session.commit()

        engine = VerificationIntelligenceEngine(session)
        res = engine.assess_knowledge_item(item)

        assert res.machine_status == MachineAssessmentStatus.INSUFFICIENT_EVIDENCE
        assert res.priority == VerificationPriority.CRITICAL
        assert any(
            i["issue_type"] == VerificationIssueType.MISSING_EVIDENCE and i["severity"] == VerificationSeverity.CRITICAL
            for i in res.issues
        )


# ==============================================================================
# 2. Temporal Precedence Evaluation & Cross-Source Conflict Detection
# ==============================================================================


def test_temporal_precedence_timezone_aware_iso_and_datetime() -> None:
    """Temporal precedence handles native datetimes and ISO-8601 strings with offsets."""
    # 1. ISO strings with Z and offset
    ts_earlier_iso = "2026-11-16T10:00:00Z"
    ts_later_iso = "2026-11-16T12:00:00+00:00"
    assert evaluate_temporal_precedence(ts_earlier_iso, ts_later_iso) == TemporalComparison.B_SUPERSEDES_A
    assert evaluate_temporal_precedence(ts_later_iso, ts_earlier_iso) == TemporalComparison.A_SUPERSEDES_B

    # 2. Different timezone representations of identical moment
    ts_utc = "2026-11-16T12:00:00Z"
    ts_est = "2026-11-16T07:00:00-05:00"  # Equivalent to 12:00:00 UTC
    assert evaluate_temporal_precedence(ts_utc, ts_est) == TemporalComparison.SIMULTANEOUS

    # 3. Datetime objects (aware and naive)
    dt_a = datetime(2026, 11, 16, 8, 0, tzinfo=UTC)
    dt_b = datetime(2026, 11, 16, 14, 0, tzinfo=timezone(timedelta(hours=2)))  # 12:00 UTC
    # dt_b is 4 hours after dt_a
    assert evaluate_temporal_precedence(dt_a, dt_b) == TemporalComparison.B_SUPERSEDES_A

    # 4. Ambiguous when missing
    assert evaluate_temporal_precedence(None, ts_later_iso) == TemporalComparison.AMBIGUOUS
    assert evaluate_temporal_precedence(ts_earlier_iso, None) == TemporalComparison.AMBIGUOUS


def test_cross_source_conflict_detection_status_jira_vs_pr(monkeypatch: pytest.MonkeyPatch) -> None:
    """Contradiction detected when Jira status is Closed but external commit/PR shows in-progress."""
    ctx = create_isolated_auth_context(monkeypatch)
    with ctx.session_factory() as session:
        user, org, project = _create_test_context(session)
        ev_jira = _create_test_evidence(
            session, org, project, user,
            title="PROJ-104: Implement SSO",
            source_type=EvidenceSourceType.JIRA.value,
        )
        ev_gh = _create_test_evidence(
            session, org, project, user,
            title="PR #42: Work in progress SSO branch",
            source_type=EvidenceSourceType.GITHUB.value,
        )
        item = _create_test_knowledge_item(
            session, org, project,
            title="Single Sign-On Integration",
            summary="SSO integration is completed and verified.",
        )
        _create_test_link(session, org, project, item, ev_jira, supporting_excerpt="Ticket closed as Done.")
        session.commit()

        engine = VerificationIntelligenceEngine(session)
        res = engine.assess_knowledge_item(item)
        case = engine.persist_assessment(res)
        session.commit()

        conflict_engine = ConflictDetectionEngine(session)
        conflicts = conflict_engine.detect_cross_source_conflicts(
            case=case,
            primary_evidence_id=ev_jira.id,
            primary_claim_text="SSO integration is completed and verified.",
            primary_source_type="jira",
            observed_sources=[
                {
                    "evidence_id": ev_gh.id,
                    "source_type": "github",
                    "claim_text": "PR #42: WIP branch with pending reviews.",
                    "status": "in_progress",
                    "timestamp": datetime.now(UTC),
                }
            ],
        )
        session.commit()

        assert len(conflicts) == 1
        assert conflicts[0].conflict_type == ConflictType.STATUS_CONFLICT
        assert case.case_status == VerificationCaseStatus.CONFLICTED
        assert case.machine_assessment_status == MachineAssessmentStatus.CONFLICT_DETECTED


def test_cross_source_conflict_detection_architecture_auth_and_db(monkeypatch: pytest.MonkeyPatch) -> None:
    """Architectural decision divergence (Argon2id vs Supabase) is identified across sources."""
    ctx = create_isolated_auth_context(monkeypatch)
    with ctx.session_factory() as session:
        user, org, project = _create_test_context(session)
        ev_doc = _create_test_evidence(
            session, org, project, user,
            title="Architecture RFC-001.md",
            source_type=EvidenceSourceType.DOCUMENT_UPLOAD.value,
            source_created_at=datetime(2026, 11, 1, 10, 0, tzinfo=UTC),
        )
        ev_code = _create_test_evidence(
            session, org, project, user,
            title="commit: feat(auth): integrate supabase oauth",
            source_type=EvidenceSourceType.GITHUB.value,
            source_created_at=datetime(2026, 11, 10, 15, 0, tzinfo=UTC),
        )
        item = _create_test_knowledge_item(
            session, org, project,
            title="Authentication Framework Decision",
            summary="Authentication uses Argon2id password hashing with local session cookies.",
        )
        _create_test_link(session, org, project, item, ev_doc, supporting_excerpt="FastAPI Argon2id hashing.")
        session.commit()

        engine = VerificationIntelligenceEngine(session)
        case = engine.persist_assessment(engine.assess_knowledge_item(item))
        session.commit()

        conflict_engine = ConflictDetectionEngine(session)
        conflicts = conflict_engine.detect_cross_source_conflicts(
            case=case,
            primary_evidence_id=ev_doc.id,
            primary_claim_text="Authentication uses Argon2id password hashing with local session cookies.",
            primary_source_type="document_upload",
            primary_timestamp="2026-11-01T10:00:00Z",
            observed_sources=[
                {
                    "evidence_id": ev_code.id,
                    "source_type": "github",
                    "claim_text": "Live commit introduces Supabase OAuth authentication.",
                    "technical_decision": "supabase",
                    "timestamp": "2026-11-10T15:00:00Z",
                }
            ],
        )
        session.commit()

        assert len(conflicts) == 1
        conf = conflicts[0]
        assert conf.conflict_type == ConflictType.DECISION_CONFLICT
        assert conf.temporal_comparison == TemporalComparison.B_SUPERSEDES_A
        assert "Argon2id" in conf.claim_a_text
        assert "Supabase" in conf.claim_b_text


def test_detect_project_conflicts_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    """Project-wide conflict detection identifies architectural contradictions."""
    ctx = create_isolated_auth_context(monkeypatch)
    with ctx.session_factory() as session:
        user, org, project = _create_test_context(session)
        ev_doc = _create_test_evidence(
            session, org, project, user,
            title="Skill Passport Architecture Specification.pdf",
            source_type=EvidenceSourceType.DOCUMENT_UPLOAD.value,
        )
        ev_gh = _create_test_evidence(
            session, org, project, user,
            title="feat(auth): integrate supabase oauth login",
            source_type=EvidenceSourceType.GITHUB.value,
        )
        item = _create_test_knowledge_item(
            session, org, project,
            title="Platform Identity and Argon2id Hashing",
            summary="Specifies internal Argon2id hashing.",
        )
        _create_test_link(session, org, project, item, ev_doc)
        session.commit()

        engine = VerificationIntelligenceEngine(session)
        engine.persist_assessment(engine.assess_knowledge_item(item))
        session.commit()

        conflict_engine = ConflictDetectionEngine(session)
        created = conflict_engine.detect_project_conflicts(project.id)
        session.commit()

        assert len(created) >= 1
        assert created[0].conflict_type == ConflictType.DECISION_CONFLICT


# ==============================================================================
# 3. Freshness, Staleness & Duplicate Detection Tests
# ==============================================================================


def test_freshness_and_staleness_supersession(monkeypatch: pytest.MonkeyPatch) -> None:
    """Failed processing evidence or finding flagged stale triggers STALE_KNOWLEDGE issue."""
    ctx = create_isolated_auth_context(monkeypatch)
    with ctx.session_factory() as session:
        user, org, project = _create_test_context(session)
        ev_failed = _create_test_evidence(
            session, org, project, user,
            title="Legacy Requirements 2023.pdf",
            status="failed",
        )
        chunk = _create_test_chunk(session, org, project, ev_failed, chunk_text="Legacy requirement text.")
        newer_item = _create_test_knowledge_item(
            session, org, project,
            title="Updated Architecture Requirements 2026",
        )
        session.flush()

        item = _create_test_knowledge_item(
            session, org, project,
            title="Legacy Requirement Finding",
            is_stale=True,
            superseded_by_id=newer_item.id,
        )
        _create_test_link(session, org, project, item, ev_failed, chunk, supporting_excerpt="Legacy requirement text.")
        session.commit()

        engine = VerificationIntelligenceEngine(session)
        res = engine.assess_knowledge_item(item)

        stale_issues = [i for i in res.issues if i["issue_type"] == VerificationIssueType.STALE_KNOWLEDGE]
        assert len(stale_issues) >= 1
        assert stale_issues[0]["severity"] == VerificationSeverity.HIGH
        assert is_handover_blocking_issue(VerificationIssueType.STALE_KNOWLEDGE) is True


def test_duplicate_detection_fingerprint_and_semantic_title(monkeypatch: pytest.MonkeyPatch) -> None:
    """Structural fingerprint and semantic title duplicates are detected and flagged."""
    ctx = create_isolated_auth_context(monkeypatch)
    with ctx.session_factory() as session:
        user, org, project = _create_test_context(session)

        # 1. Exact fingerprint match
        fp = "fingerprint-shared-12345"
        item1 = _create_test_knowledge_item(
            session, org, project,
            title="Database Connection Pool Configuration",
            fingerprint=fp,
        )
        item2 = _create_test_knowledge_item(
            session, org, project,
            title="Database Connection Pool Tuning",
            fingerprint=fp,
        )
        session.commit()

        engine = VerificationIntelligenceEngine(session)
        res2 = engine.assess_knowledge_item(item2)
        assert any(i["issue_type"] == VerificationIssueType.DUPLICATE_RECORD for i in res2.issues)

        # 2. Semantic title overlap (> 85% word overlap)
        item3 = _create_test_knowledge_item(
            session, org, project,
            title="Deploy FastAPI Application to Render Production",
        )
        item4 = _create_test_knowledge_item(
            session, org, project,
            title="Deploy FastAPI Backend Application on Render Production",
        )
        session.commit()

        res4 = engine.assess_knowledge_item(item4)
        assert any(i["issue_type"] == VerificationIssueType.DUPLICATE_RECORD for i in res4.issues)


def test_duplicate_relationship_edge_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    """Duplicate relationship connecting the same entities flags DUPLICATE_RECORD."""
    ctx = create_isolated_auth_context(monkeypatch)
    with ctx.session_factory() as session:
        user, org, project = _create_test_context(session)
        source = KnowledgeEntity(
            id=uuid.uuid4(), organisation_id=org.id, project_id=project.id,
            entity_type="service", canonical_name="Service Alpha", normalized_name="service_alpha",
        )
        target = KnowledgeEntity(
            id=uuid.uuid4(), organisation_id=org.id, project_id=project.id,
            entity_type="database", canonical_name="Database Main", normalized_name="database_main",
        )
        session.add_all([source, target])
        session.flush()

        rel1 = KnowledgeRelationship(
            id=uuid.uuid4(), organisation_id=org.id, project_id=project.id,
            source_entity_id=source.id, target_entity_id=target.id,
            relationship_type="connects_to", relationship_basis=RelationshipBasis.EXPLICIT,
            fingerprint=uuid.uuid4().hex,
        )
        rel2 = KnowledgeRelationship(
            id=uuid.uuid4(), organisation_id=org.id, project_id=project.id,
            source_entity_id=source.id, target_entity_id=target.id,
            relationship_type="connects_to", relationship_basis=RelationshipBasis.EXPLICIT,
            fingerprint=uuid.uuid4().hex,
        )
        session.add_all([rel1, rel2])
        session.commit()

        engine = VerificationIntelligenceEngine(session)
        res = engine.assess_relationship(rel2)

        assert any(i["issue_type"] == VerificationIssueType.DUPLICATE_RECORD for i in res.issues)


# ==============================================================================
# 4. Confidence & Uncertainty Scoring Tests
# ==============================================================================


def test_calibrated_composite_confidence_scoring(monkeypatch: pytest.MonkeyPatch) -> None:
    """Calibrated confidence scoring integrates source authority, coverage, freshness, and penalties."""
    ctx = create_isolated_auth_context(monkeypatch)
    with ctx.session_factory() as session:
        user, org, project = _create_test_context(session)

        # Case A: High authority (GitHub commit) + 2 verified links + fresh -> Score >= 0.85
        ev_gh = _create_test_evidence(
            session, org, project, user,
            title="commit: production architecture",
            source_type=EvidenceSourceType.GITHUB.value,
        )
        chunk1 = _create_test_chunk(
            session, org, project, ev_gh,
            chunk_text="Production Architecture deployed on AWS ECS cluster: " + "A" * 150,
            chunk_index=0,
        )
        chunk2 = _create_test_chunk(
            session, org, project, ev_gh,
            chunk_text="Production Architecture database persistence configuration: " + "B" * 150,
            chunk_index=1,
        )
        item_a = _create_test_knowledge_item(
            session, org, project,
            title="Production Architecture",
            summary="Production Architecture deployed on AWS ECS cluster with database persistence.",
        )
        _create_test_link(
            session, org, project, item_a, ev_gh, chunk1,
            supporting_excerpt="Production Architecture deployed on AWS ECS cluster",
        )
        _create_test_link(
            session, org, project, item_a, ev_gh, chunk2,
            supporting_excerpt="Production Architecture database persistence configuration",
        )
        session.commit()

        engine = VerificationIntelligenceEngine(session)
        res_a = engine.assess_knowledge_item(item_a)
        score_a = res_a.assessment_metadata["confidence_score"]
        breakdown_a = res_a.assessment_metadata["confidence_breakdown"]

        assert 0.80 <= score_a <= 1.00
        assert breakdown_a["authority_score"] == 0.95
        assert breakdown_a["freshness_score"] == 1.00
        assert breakdown_a["issue_penalty"] == 0.0

        # Case B: Stale item with open conflict penalty
        score_b, breakdown_b = calculate_composite_confidence(
            target_type=VerificationTargetType.KNOWLEDGE_ITEM,
            evidence_links=[],
            issues=[{"severity": VerificationSeverity.HIGH}],
            conflicts_count=1,
            is_stale=True,
        )
        assert score_b <= 0.20
        assert breakdown_b["conflict_penalty"] == 0.25
        assert breakdown_b["issue_penalty"] == 0.15

        # Check bounds
        assert 0.00 <= score_b <= 1.00


# ==============================================================================
# 5. Advisory LLM Integration Tests (Non-Blocking & Deterministic Fallbacks)
# ==============================================================================


class _MockStructuredLLMClient:
    """Mock StructuredLLMClient simulating successful responses and timeouts."""

    def __init__(self, mode: str = "success") -> None:
        self.mode = mode

    @property
    def model_name(self) -> str:
        return "qwen3:8b"

    def generate_json(self, request: LLMGenerationRequest) -> LLMGenerationResult:
        if self.mode == "timeout":
            raise LLMExecutionError(code="LLM_TIMEOUT", message="Local Ollama LLM inference timed out.")
        elif self.mode == "error":
            raise LLMExecutionError(code="LLM_UNAVAILABLE", message="Connection refused to 127.0.0.1:11434.")

        # Successful response
        if "nuance" in request.user_prompt or "Claim A" in request.user_prompt:
            parsed = {
                "likely_cause": "Decision updated during sprint 4.",
                "nuance_explanation": "Source A represents the initial spec, whereas Source B is the active code.",
                "reconciliation_recommendation": "Adopt Source B code commit as ground truth.",
                "clarification_questions": ["Did the team officially sign off on this migration?"],
            }
        else:
            parsed = {
                "questions": [
                    {"question": "What database driver is used?", "purpose": "Ensure dependency parity."}
                ]
            }

        return LLMGenerationResult(
            parsed_json=parsed,
            raw_text="{}",
            model_name="qwen3:8b",
            prompt_tokens=100,
            completion_tokens=50,
            duration_ms=250,
            done_reason="stop",
            truncated=False,
        )


def test_advisory_ai_ollama_client_success() -> None:
    """AIAssistedVerificationService successfully returns structured explanations when LLM is available."""
    mock_client = _MockStructuredLLMClient(mode="success")
    service = AIAssistedVerificationService(llm_client=mock_client)

    explanation = service.explain_conflict(
        claim_a="Argon2id hashing in FastAPI",
        claim_b="Supabase OAuth in production",
        context="Sprint 4 auth refactor",
    )
    assert "likely_cause" in explanation
    assert "reconciliation_recommendation" in explanation
    assert len(explanation["clarification_questions"]) >= 1

    questions = service.suggest_clarifications(
        title="Database Config",
        domain="Architecture",
        summary="PostgreSQL configuration",
        missing_context="rationale",
    )
    assert len(questions) >= 1
    assert "question" in questions[0]
    assert "purpose" in questions[0]


def test_advisory_ai_timeout_and_deterministic_fallback() -> None:
    """Strict non-blocking safety: LLM timeout or offline status seamlessly invokes deterministic fallbacks."""
    # 1. Timeout simulation
    timeout_client = _MockStructuredLLMClient(mode="timeout")
    service_timeout = AIAssistedVerificationService(llm_client=timeout_client, timeout_seconds=5.0)

    fallback_expl = service_timeout.explain_conflict(
        claim_a="Platform specifies Argon2id password hashing",
        claim_b="Commit implements Supabase OAuth authentication",
    )
    assert isinstance(fallback_expl, dict)
    assert "likely_cause" in fallback_expl
    assert "nuance_explanation" in fallback_expl
    assert "clarification_questions" in fallback_expl
    assert len(fallback_expl["clarification_questions"]) >= 1

    fallback_questions = service_timeout.suggest_clarifications(
        title="Cache Invalidation Strategy",
        domain="Architecture",
        summary="Redis cache with TTL",
        missing_context="operational_procedure",
    )
    assert isinstance(fallback_questions, list)
    assert len(fallback_questions) >= 1
    assert "runbook" in fallback_questions[0]["question"].lower() or "operational" in fallback_questions[0]["question"].lower()

    # 2. Offline / Connection error simulation
    offline_client = _MockStructuredLLMClient(mode="error")
    service_offline = AIAssistedVerificationService(llm_client=offline_client)
    offline_expl = service_offline.explain_conflict(
        claim_a="Task status: Completed",
        claim_b="Jira ticket: In Progress",
    )
    assert "likely_cause" in offline_expl
    assert "reconciliation_recommendation" in offline_expl


def test_advisory_ai_invariant_never_mutates_review_status() -> None:
    """Advisory AI service contains zero mutating methods: cannot approve, reject, or mark verified."""
    service = AIAssistedVerificationService()
    prohibited_methods = ["approve_finding", "reject_finding", "mark_verified", "set_status"]
    for method in prohibited_methods:
        assert not hasattr(service, method), f"AI service must not implement mutating method: {method}"


# ==============================================================================
# 6. Full Verification Intelligence Pipeline Integration Test
# ==============================================================================


def test_full_intelligence_engine_assessment_and_persistence(monkeypatch: pytest.MonkeyPatch) -> None:
    """Full lifecycle: assessment computes calibrated confidence, detects issues, and persists VerificationCase."""
    ctx = create_isolated_auth_context(monkeypatch)
    with ctx.session_factory() as session:
        user, org, project = _create_test_context(session)
        ev = _create_test_evidence(
            session, org, project, user,
            title="System Architecture Specification 2026.pdf",
            source_type=EvidenceSourceType.DOCUMENT_UPLOAD.value,
        )
        chunk = _create_test_chunk(
            session, org, project, ev,
            chunk_text="FastAPI backend persists operational state in PostgreSQL and uses ChromaDB for semantic search.",
        )
        item = _create_test_knowledge_item(
            session, org, project,
            title="Hybrid Storage Architecture",
            summary="FastAPI backend persists operational state in PostgreSQL and uses ChromaDB for semantic search.",
        )
        _create_test_link(
            session, org, project, item, ev, chunk,
            supporting_excerpt="FastAPI backend persists operational state in PostgreSQL and uses ChromaDB for semantic search.",
        )
        session.commit()

        engine = VerificationIntelligenceEngine(session)
        res = engine.assess_knowledge_item(item)

        assert res.machine_status == MachineAssessmentStatus.PASSED
        assert res.priority == VerificationPriority.LOW
        assert len(res.issues) == 0

        # Persist assessment to PostgreSQL
        case = engine.persist_assessment(res)
        session.commit()

        assert case is not None
        assert case.target_id == item.id
        assert case.case_status == VerificationCaseStatus.CANDIDATE
        assert case.machine_assessment_status == MachineAssessmentStatus.PASSED
        assert "confidence_score" in case.machine_assessment_json
        assert case.machine_assessment_json["confidence_score"] >= 0.80

        # Refresh KnowledgeItem and check persisted confidence metadata
        session.refresh(item)
        assert item.confidence_metadata_json is not None
        assert "confidence_score" in item.confidence_metadata_json


# ==============================================================================
# 7. Phase 3 Remediation Regression Tests
# ==============================================================================


def _create_test_relationship_with_links(
    session: Session,
    org: Organisation,
    project: Project,
    ev: EvidenceItem,
    chunk: EvidenceChunk | None = None,
    *,
    relationship_type: str = "connects_to",
    supporting_excerpt: str = "Service A connects to Database Main",
) -> tuple[KnowledgeRelationship, RelationshipEvidenceLink]:
    """Helper creating KnowledgeEntities, KnowledgeRelationship, and RelationshipEvidenceLink."""
    source = KnowledgeEntity(
        id=uuid.uuid4(),
        organisation_id=org.id,
        project_id=project.id,
        entity_type="service",
        canonical_name=f"Service-{uuid.uuid4().hex[:6]}",
        normalized_name=f"service_{uuid.uuid4().hex[:6]}",
    )
    target = KnowledgeEntity(
        id=uuid.uuid4(),
        organisation_id=org.id,
        project_id=project.id,
        entity_type="database",
        canonical_name=f"Database-{uuid.uuid4().hex[:6]}",
        normalized_name=f"database_{uuid.uuid4().hex[:6]}",
    )
    session.add_all([source, target])
    session.flush()

    rel = KnowledgeRelationship(
        id=uuid.uuid4(),
        organisation_id=org.id,
        project_id=project.id,
        source_entity_id=source.id,
        target_entity_id=target.id,
        relationship_type=relationship_type,
        relationship_basis=RelationshipBasis.EXPLICIT,
        fingerprint=uuid.uuid4().hex,
        confidence_score=0.95,
    )
    session.add(rel)
    session.flush()

    link = RelationshipEvidenceLink(
        id=uuid.uuid4(),
        organisation_id=org.id,
        project_id=project.id,
        relationship_id=rel.id,
        evidence_id=ev.id,
        evidence_chunk_id=chunk.id if chunk else None,
        evidence_role="direct_support",
        supporting_excerpt=supporting_excerpt,
        source_location_json={"section": "architecture"},
    )
    session.add(link)
    session.flush()
    return rel, link


def test_regression_assess_relationship_with_evidence_chunk_and_confidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression Defect 1 & 3: assess_relationship resolves EvidenceChunk and calculates confidence correctly."""
    ctx = create_isolated_auth_context(monkeypatch)
    with ctx.session_factory() as session:
        user, org, project = _create_test_context(session)
        ev = _create_test_evidence(
            session,
            org,
            project,
            user,
            title="Architecture_Topology.pdf",
            source_type=EvidenceSourceType.DOCUMENT_UPLOAD.value,
        )
        chunk_text = (
            "Network Architecture Section 3: The Payment Gateway service connects directly to "
            "the Main PostgreSQL Cluster over a dedicated TLS tunnel on port 5432 with mTLS auth."
        )
        chunk = _create_test_chunk(session, org, project, ev, chunk_text=chunk_text)

        # 1. Valid grounded relationship excerpt
        rel_valid, _link_valid = _create_test_relationship_with_links(
            session,
            org,
            project,
            ev,
            chunk,
            relationship_type="connects_to",
            supporting_excerpt="The Payment Gateway service connects directly to the Main PostgreSQL Cluster",
        )
        session.commit()

        engine = VerificationIntelligenceEngine(session)
        res_valid = engine.assess_relationship(rel_valid)

        # Must execute lines 567-597 without NameError and pass
        assert res_valid.machine_status == MachineAssessmentStatus.PASSED
        assert len(res_valid.issues) == 0
        breakdown = res_valid.assessment_metadata["confidence_breakdown"]
        # Source authority must be 0.90 (from Document Upload), not default 0.50
        assert breakdown["authority_score"] == 0.90
        # Coverage must reflect chunk text length (> 100 chars) and grounded excerpt, not collapse to 0.084
        assert breakdown["coverage_score"] >= 0.60
        assert res_valid.assessment_metadata["confidence_score"] >= 0.75

        # 2. Relationship with ungrounded excerpt
        rel_unsupported, _link_unsupported = _create_test_relationship_with_links(
            session,
            org,
            project,
            ev,
            chunk,
            relationship_type="connects_to",
            supporting_excerpt="Payment Gateway writes transaction ledgers directly to Cassandra NoSQL",
        )
        session.commit()

        res_unsupported = engine.assess_relationship(rel_unsupported)
        assert res_unsupported.machine_status == MachineAssessmentStatus.ISSUES_DETECTED
        unsupported_issues = [
            i for i in res_unsupported.issues if i["issue_type"] == VerificationIssueType.UNSUPPORTED_CLAIM
        ]
        assert len(unsupported_issues) == 1
        assert unsupported_issues[0]["severity"] == VerificationSeverity.HIGH


def test_regression_assess_knowledge_item_detecting_unsupported_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression Defect 2: assess_knowledge_item calls verify_claim_support and catches ungrounded claims."""
    ctx = create_isolated_auth_context(monkeypatch)
    with ctx.session_factory() as session:
        user, org, project = _create_test_context(session)
        ev = _create_test_evidence(session, org, project, user, title="Payment_Gateway.pdf")
        chunk_text = (
            "Payment integration uses Stripe Elements with server-side webhooks for card processing."
        )
        chunk = _create_test_chunk(session, org, project, ev, chunk_text=chunk_text)

        # Finding with a verbatim excerpt from Stripe, but hallucinated title and summary
        item = _create_test_knowledge_item(
            session,
            org,
            project,
            title="Crypto Smart Contract Settlement Node",
            summary="System accepts Bitcoin, Ethereum, and Solana payments via custom Web3 smart contracts.",
        )
        # Excerpt matches chunk verbatim
        _create_test_link(
            session,
            org,
            project,
            item,
            ev,
            chunk,
            supporting_excerpt="Payment integration uses Stripe Elements with server-side webhooks",
        )
        session.commit()

        engine = VerificationIntelligenceEngine(session)
        res = engine.assess_knowledge_item(item)

        # verify_claim_support MUST flag UNSUPPORTED_CLAIM because Crypto/Web3 is not supported in Stripe chunk
        assert res.machine_status == MachineAssessmentStatus.ISSUES_DETECTED
        unsupported_issues = [
            i for i in res.issues if i["issue_type"] == VerificationIssueType.UNSUPPORTED_CLAIM
        ]
        assert len(unsupported_issues) == 1
        assert unsupported_issues[0]["severity"] == VerificationSeverity.HIGH
        assert unsupported_issues[0]["details_json"]["support_ratio"] < 0.40


def test_regression_semantic_duplicate_inverted_phrasing_and_stopwords(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression Defect 4: Inverted phrasing and stopword differences are detected as DUPLICATE_RECORD."""
    ctx = create_isolated_auth_context(monkeypatch)
    with ctx.session_factory() as session:
        user, org, project = _create_test_context(session)

        # Finding A: "Use Argon2id for password hashing"
        item_a = _create_test_knowledge_item(
            session,
            org,
            project,
            title="Use Argon2id for password hashing",
            category="decisions_rationale",
            primary_domain="decisions_and_rationale",
        )
        # Finding B: Inverted phrasing with different stopwords ("using" vs "for", "use")
        item_b = _create_test_knowledge_item(
            session,
            org,
            project,
            title="Password hashing using Argon2id",
            category="decisions_rationale",
            primary_domain="decisions_and_rationale",
        )
        session.commit()

        engine = VerificationIntelligenceEngine(session)
        res_b = engine.assess_knowledge_item(item_b)

        # Finding B must be detected as duplicate of Finding A
        dup_issues = [
            i for i in res_b.issues if i["issue_type"] == VerificationIssueType.DUPLICATE_RECORD
        ]
        assert len(dup_issues) == 1
        assert str(item_a.id) in dup_issues[0]["details_json"]["duplicate_item_ids"]

        # Distinct items sharing boilerplate stopwords must NOT be detected as duplicates
        item_redis = _create_test_knowledge_item(
            session,
            org,
            project,
            title="Use Redis for user session caching",
            category="decisions_rationale",
            primary_domain="decisions_and_rationale",
        )
        item_postgres = _create_test_knowledge_item(
            session,
            org,
            project,
            title="Use PostgreSQL for relational data persistence",
            category="decisions_rationale",
            primary_domain="decisions_and_rationale",
        )
        session.commit()

        res_redis = engine.assess_knowledge_item(item_redis)
        dup_redis = [
            i for i in res_redis.issues if i["issue_type"] == VerificationIssueType.DUPLICATE_RECORD
        ]
        assert len(dup_redis) == 0

        res_postgres = engine.assess_knowledge_item(item_postgres)
        dup_postgres = [
            i for i in res_postgres.issues if i["issue_type"] == VerificationIssueType.DUPLICATE_RECORD
        ]
        assert len(dup_postgres) == 0


def test_regression_conflict_detection_word_boundaries_and_negations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression Defect 5: Word boundaries and negations avoid false status and decision conflicts."""
    ctx = create_isolated_auth_context(monkeypatch)
    with ctx.session_factory() as session:
        user, org, project = _create_test_context(session)
        ev_primary = _create_test_evidence(session, org, project, user, title="Spec.pdf")
        ev_other = _create_test_evidence(
            session,
            org,
            project,
            user,
            title="JiraTicket",
            source_type=EvidenceSourceType.JIRA.value,
        )

        item = _create_test_knowledge_item(session, org, project, title="Feature Workflow")
        case = VerificationCase(
            organisation_id=org.id,
            project_id=project.id,
            target_type=VerificationTargetType.KNOWLEDGE_ITEM,
            target_id=item.id,
            case_status=VerificationCaseStatus.PENDING_REVIEW,
            priority=VerificationPriority.MEDIUM,
            version=1,
        )
        session.add(case)
        session.commit()

        detector = ConflictDetectionEngine(session)

        # 1. "done" inside "abandoned" must NOT trigger status conflict with open ticket
        conflicts_abandoned = detector.detect_cross_source_conflicts(
            case=case,
            primary_evidence_id=ev_primary.id,
            primary_claim_text="Project was abandoned due to budget reallocation.",
            primary_source_type="document_upload",
            observed_sources=[{
                "evidence_id": ev_other.id,
                "source_type": "jira",
                "status": "open",
                "claim_text": "Jira ticket is open",
            }],
        )
        assert len(conflicts_abandoned) == 0

        # 2. Negation "not completed" must NOT be treated as completed
        conflicts_not_done = detector.detect_cross_source_conflicts(
            case=case,
            primary_evidence_id=ev_primary.id,
            primary_claim_text="Authentication module is not completed yet.",
            primary_source_type="document_upload",
            observed_sources=[{
                "evidence_id": ev_other.id,
                "source_type": "jira",
                "status": "open",
                "claim_text": "Jira ticket is open",
            }],
        )
        assert len(conflicts_not_done) == 0

        # 3. Negation "undone" must NOT be treated as completed
        conflicts_undone = detector.detect_cross_source_conflicts(
            case=case,
            primary_evidence_id=ev_primary.id,
            primary_claim_text="The schema migration remains undone.",
            primary_source_type="document_upload",
            observed_sources=[{
                "evidence_id": ev_other.id,
                "source_type": "jira",
                "status": "open",
                "claim_text": "Jira ticket is open",
            }],
        )
        assert len(conflicts_undone) == 0

        # 4. Legitimate status conflict: completed primary vs in_progress external
        conflicts_real = detector.detect_cross_source_conflicts(
            case=case,
            primary_evidence_id=ev_primary.id,
            primary_claim_text="Authentication module is completed and tested.",
            primary_source_type="document_upload",
            observed_sources=[{
                "evidence_id": ev_other.id,
                "source_type": "jira",
                "status": "in_progress",
                "claim_text": "Jira ticket is in progress",
            }],
        )
        assert len(conflicts_real) == 1
        assert conflicts_real[0].conflict_type == ConflictType.STATUS_CONFLICT

        # 5. Migration narrative mentioning both SQLite and PostgreSQL must NOT trigger decision conflict
        conflicts_migration = detector.detect_cross_source_conflicts(
            case=case,
            primary_evidence_id=ev_primary.id,
            primary_claim_text="We migrated our persistence layer from SQLite to PostgreSQL.",
            primary_source_type="document_upload",
            observed_sources=[{
                "evidence_id": ev_other.id,
                "source_type": "github",
                "technical_decision": "postgresql",
                "claim_text": "Using PostgreSQL for persistence",
            }],
        )
        assert len(conflicts_migration) == 0


def test_assess_relationship_inferred_basis(monkeypatch: pytest.MonkeyPatch) -> None:
    """Assess relationship with RelationshipBasis.INFERRED runs cleanly without AttributeError,
    records UNCERTAIN_RELATIONSHIP issue, and applies inferred relationship confidence adjustment.
    """
    ctx = create_isolated_auth_context(monkeypatch)
    with ctx.session_factory() as session:
        user, org, project = _create_test_context(session)
        ev = _create_test_evidence(
            session,
            org,
            project,
            user,
            title="Architecture_Topology.pdf",
            source_type=EvidenceSourceType.DOCUMENT_UPLOAD.value,
        )
        chunk_text = (
            "Network Architecture Section 3: The Payment Gateway service connects directly to "
            "the Main PostgreSQL Cluster over a dedicated TLS tunnel on port 5432 with mTLS auth."
        )
        chunk = _create_test_chunk(session, org, project, ev, chunk_text=chunk_text)

        # 1. Explicit baseline relationship
        source_exp = KnowledgeEntity(
            id=uuid.uuid4(),
            organisation_id=org.id,
            project_id=project.id,
            entity_type="service",
            canonical_name="Service Explicit",
            normalized_name="service_explicit",
        )
        target_exp = KnowledgeEntity(
            id=uuid.uuid4(),
            organisation_id=org.id,
            project_id=project.id,
            entity_type="database",
            canonical_name="Database Explicit",
            normalized_name="database_explicit",
        )
        session.add_all([source_exp, target_exp])
        session.flush()

        rel_explicit = KnowledgeRelationship(
            id=uuid.uuid4(),
            organisation_id=org.id,
            project_id=project.id,
            source_entity_id=source_exp.id,
            target_entity_id=target_exp.id,
            relationship_type="connects_to",
            relationship_basis=RelationshipBasis.EXPLICIT,
            fingerprint=uuid.uuid4().hex,
            confidence_score=0.95,
        )
        session.add(rel_explicit)
        session.flush()

        link_exp = RelationshipEvidenceLink(
            id=uuid.uuid4(),
            organisation_id=org.id,
            project_id=project.id,
            relationship_id=rel_explicit.id,
            evidence_id=ev.id,
            evidence_chunk_id=chunk.id,
            evidence_role="direct_support",
            supporting_excerpt="The Payment Gateway service connects directly to the Main PostgreSQL Cluster",
            source_location_json={"section": "architecture"},
        )
        session.add(link_exp)

        # 2. Inferred relationship
        source_inf = KnowledgeEntity(
            id=uuid.uuid4(),
            organisation_id=org.id,
            project_id=project.id,
            entity_type="service",
            canonical_name="Service Inferred",
            normalized_name="service_inferred",
        )
        target_inf = KnowledgeEntity(
            id=uuid.uuid4(),
            organisation_id=org.id,
            project_id=project.id,
            entity_type="database",
            canonical_name="Database Inferred",
            normalized_name="database_inferred",
        )
        session.add_all([source_inf, target_inf])
        session.flush()

        rel_inferred = KnowledgeRelationship(
            id=uuid.uuid4(),
            organisation_id=org.id,
            project_id=project.id,
            source_entity_id=source_inf.id,
            target_entity_id=target_inf.id,
            relationship_type="connects_to",
            relationship_basis=RelationshipBasis.INFERRED,
            discovery_method="contextual_match",
            fingerprint=uuid.uuid4().hex,
            confidence_score=0.85,
        )
        session.add(rel_inferred)
        session.flush()

        link_inf = RelationshipEvidenceLink(
            id=uuid.uuid4(),
            organisation_id=org.id,
            project_id=project.id,
            relationship_id=rel_inferred.id,
            evidence_id=ev.id,
            evidence_chunk_id=chunk.id,
            evidence_role="direct_support",
            supporting_excerpt="The Payment Gateway service connects directly to the Main PostgreSQL Cluster",
            source_location_json={"section": "architecture"},
        )
        session.add(link_inf)
        session.commit()

        engine = VerificationIntelligenceEngine(session)

        # Explicit assessment
        res_exp = engine.assess_relationship(rel_explicit)
        assert res_exp.machine_status == MachineAssessmentStatus.PASSED
        cov_exp = res_exp.assessment_metadata["confidence_breakdown"]["coverage_score"]

        # Inferred assessment: must not raise AttributeError
        res_inf = engine.assess_relationship(rel_inferred)
        assert res_inf is not None
        assert res_inf.machine_status == MachineAssessmentStatus.UNCERTAIN
        assert res_inf.priority == VerificationPriority.LOW

        # Record UNCERTAIN_RELATIONSHIP issue with inference_reason
        uncertain_issues = [
            i for i in res_inf.issues if i["issue_type"] == VerificationIssueType.UNCERTAIN_RELATIONSHIP
        ]
        assert len(uncertain_issues) == 1
        issue = uncertain_issues[0]
        assert issue["severity"] == VerificationSeverity.LOW
        assert issue["details_json"]["inference_reason"] == "contextual_match"
        assert issue["details_json"]["confidence_score"] == 0.85

        # Check inferred relationship confidence adjustment (0.80 coverage multiplier)
        cov_inf = res_inf.assessment_metadata["confidence_breakdown"]["coverage_score"]
        assert cov_inf == pytest.approx(cov_exp * 0.80, rel=1e-3)
        assert res_inf.assessment_metadata["confidence_score"] < res_exp.assessment_metadata["confidence_score"]

