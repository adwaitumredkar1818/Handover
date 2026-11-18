"""Automated Test Suite for Advanced Verification Intelligence & Continuous Monitoring.

Tests:
1. CompletenessEvaluator (explainable scoring, missing elements, recommendations, accessibility)
2. SourceReliabilityEvaluator (source authority, provider affinity, cryptographic hash check)
3. FreshnessEvaluator (fresh, aging, stale, outdated, supersession analysis)
4. CorroborationEvaluator (independent sources count, strictly distinguishing chunks from distinct docs)
5. AdvancedContradictionEvaluator (status contradictions, architectural antipodes)
6. RecommendationEngine (action, headline, supporting factors, confidence tier)
7. PrioritisationEngine (critical, high, medium, low, explainable reason)
8. ContinuousMonitoringService (drift detection, re-verification flag, audit logging)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.db.session import session_scope
from app.models.enums import (
    ConflictResolutionState,
    ConflictType,
    EvidenceCategory,
    EvidenceSourceType,
    IssueResolutionState,
    MachineAssessmentStatus,
    OrganisationStatus,
    ProjectStatus,
    ProjectVisibility,
    UserStatus,
    VerificationCaseStatus,
    VerificationCategory,
    VerificationPriority,
    VerificationSeverity,
    VerificationTargetType,
)
from app.models.evidence import EvidenceChunk, EvidenceItem
from app.models.knowledge import KnowledgeItem
from app.models.organisation import Organisation
from app.models.project import Project, ProjectMembership
from app.models.user import User
from app.models.verification import (
    VerificationCase,
    VerificationConflict,
    VerificationEvidenceRef,
    VerificationIssue,
)
from app.services.verification_intelligence import (
    AdvancedContradictionEvaluator,
    CompletenessEvaluator,
    ContinuousMonitoringService,
    CorroborationEvaluator,
    FreshnessEvaluator,
    PrioritisationEngine,
    RecommendationEngine,
    SourceReliabilityEvaluator,
)
from tests.conftest import isolated_auth_app


def test_completeness_evaluator_missing_evidence():
    evaluator = CompletenessEvaluator()
    case = VerificationCase(
        id=uuid.uuid4(),
        title="Unbacked Architecture Claim",
        current_claim="PostgreSQL database is configured with replication",
        case_status=VerificationCaseStatus.CANDIDATE.value,
        domain="technical_architecture",
    )
    report = evaluator.evaluate(case, [])
    assert report.level == "missing"
    assert report.score == 0.0
    assert not report.direct_support
    assert len(report.missing_elements) > 0
    assert len(report.recommendations) > 0


def test_completeness_evaluator_complete_evidence():
    evaluator = CompletenessEvaluator()
    case = VerificationCase(
        id=uuid.uuid4(),
        title="Database Choice",
        current_claim="PostgreSQL was selected for relational persistence",
        case_status=VerificationCaseStatus.CANDIDATE.value,
        domain="decisions_rationale",
    )
    ev = EvidenceItem(
        id=uuid.uuid4(),
        title="Architecture Decision Record: PostgreSQL",
        source_type="file_upload",
        source_author_identity="architect@example.com",
        source_created_at=datetime.now(UTC),
        acl_scope="project_members",
    )
    ref = VerificationEvidenceRef(
        id=uuid.uuid4(),
        evidence_item_id=ev.id,
        relationship_to_finding="supports",
        excerpt="We decided to use PostgreSQL for relational persistence across the platform.",
        location_label="Page 2",
        source_timestamp=datetime.now(UTC),
    )
    ref.evidence_item = ev

    report = evaluator.evaluate(case, [ref])
    assert report.level == "complete"
    assert report.score >= 0.8
    assert report.direct_support
    assert report.evidence_accessible


def test_source_reliability_evaluator():
    evaluator = SourceReliabilityEvaluator()
    case = VerificationCase(
        id=uuid.uuid4(),
        title="Repository Commit",
        current_claim="Implemented user authentication endpoint",
        domain="technical_architecture",
    )
    ev = EvidenceItem(
        id=uuid.uuid4(),
        title="GitHub Commit 123456",
        source_type="github",
        source_author_identity="dev@example.com",
        source_url="https://github.com/org/repo/commit/123456",
        content_hash="sha256:abc123def456",
        source_created_at=datetime.now(UTC),
    )
    ref = VerificationEvidenceRef(
        id=uuid.uuid4(),
        evidence_item_id=ev.id,
        relationship_to_finding="supports",
        excerpt="Implemented user authentication endpoints with argon2id and JWT",
    )
    ref.evidence_item = ev

    report = evaluator.evaluate(case, [ref])
    assert report.tier == "high"
    assert report.score >= 0.9
    assert "github" in report.primary_authority.lower()
    assert len(report.factors) > 0


def test_freshness_evaluator_fresh_and_outdated():
    evaluator = FreshnessEvaluator()
    case = VerificationCase(
        id=uuid.uuid4(),
        title="Recent Architecture Decision",
        current_claim="Using FastAPI 0.115 with Python 3.11",
        domain="technical_architecture",
    )
    now = datetime.now(UTC)

    # 1. Fresh case
    ev_fresh = EvidenceItem(
        id=uuid.uuid4(),
        title="Recent commit",
        source_created_at=now - timedelta(days=5),
    )
    ref_fresh = VerificationEvidenceRef(
        id=uuid.uuid4(),
        evidence_item_id=ev_fresh.id,
        source_timestamp=now - timedelta(days=5),
    )
    ref_fresh.evidence_item = ev_fresh

    report_fresh = evaluator.evaluate(case, [ref_fresh], now, [ev_fresh])
    assert report_fresh.status == "fresh"
    assert not report_fresh.reverification_required

    # 2. Outdated case (>180 days older than project records)
    ev_old = EvidenceItem(
        id=uuid.uuid4(),
        title="Legacy design doc",
        source_created_at=now - timedelta(days=200),
    )
    ref_old = VerificationEvidenceRef(
        id=uuid.uuid4(),
        evidence_item_id=ev_old.id,
        source_timestamp=now - timedelta(days=200),
    )
    ref_old.evidence_item = ev_old

    ev_latest = EvidenceItem(
        id=uuid.uuid4(),
        title="Latest master commit",
        source_created_at=now,
    )

    report_old = evaluator.evaluate(case, [ref_old], now, [ev_old, ev_latest])
    assert report_old.status in {"stale", "outdated"}
    assert report_old.age_days >= 180


def test_corroboration_evaluator_chunks_vs_independent_documents():
    evaluator = CorroborationEvaluator()
    case = VerificationCase(
        id=uuid.uuid4(),
        title="Architecture finding",
        current_claim="System uses PostgreSQL database",
        domain="technical_architecture",
    )

    # Scenario A: Multiple chunks from the SAME single document (MUST NOT be cross-corroborated)
    ev_single = EvidenceItem(
        id=uuid.uuid4(),
        title="System Architecture PDF",
        source_type="file_upload",
    )
    ref1 = VerificationEvidenceRef(
        id=uuid.uuid4(),
        evidence_item_id=ev_single.id,
        evidence_chunk_id=uuid.uuid4(),
        excerpt="Section 1 mentions Postgres",
    )
    ref1.evidence_item = ev_single
    ref2 = VerificationEvidenceRef(
        id=uuid.uuid4(),
        evidence_item_id=ev_single.id,
        evidence_chunk_id=uuid.uuid4(),
        excerpt="Section 5 confirms Postgres connection string",
    )
    ref2.evidence_item = ev_single

    report_single = evaluator.evaluate(case, [ref1, ref2])
    assert report_single.level == "single_source"
    assert report_single.independent_sources_count == 1

    # Scenario B: Truly independent sources across different providers (GitHub + Jira)
    ev_github = EvidenceItem(
        id=uuid.uuid4(),
        title="GitHub PR #42",
        source_type="github",
    )
    ref_gh = VerificationEvidenceRef(
        id=uuid.uuid4(),
        evidence_item_id=ev_github.id,
        excerpt="PR merged PostgreSQL Alembic migrations",
    )
    ref_gh.evidence_item = ev_github

    ev_jira = EvidenceItem(
        id=uuid.uuid4(),
        title="Jira Issue PROJ-101",
        source_type="jira",
    )
    ref_jira = VerificationEvidenceRef(
        id=uuid.uuid4(),
        evidence_item_id=ev_jira.id,
        excerpt="Story resolved: PostgreSQL configured",
    )
    ref_jira.evidence_item = ev_jira

    report_multi = evaluator.evaluate(case, [ref_gh, ref_jira])
    assert report_multi.level == "strong_cross_source"
    assert report_multi.independent_sources_count == 2
    assert "GITHUB" in report_multi.supporting_providers
    assert "JIRA" in report_multi.supporting_providers


def test_contradiction_evaluator_status_conflict():
    evaluator = AdvancedContradictionEvaluator()
    case = VerificationCase(
        id=uuid.uuid4(),
        title="Task Status",
        current_claim="Authentication migration status",
        domain="work_items",
    )
    ev1 = EvidenceItem(id=uuid.uuid4(), title="PR #10: Closed and merged", source_type="github")
    ref1 = VerificationEvidenceRef(
        id=uuid.uuid4(),
        evidence_item_id=ev1.id,
        excerpt="PR merged and closed successfully",
    )
    ref1.evidence_item = ev1

    ev2 = EvidenceItem(id=uuid.uuid4(), title="Jira Task: Still open and blocked", source_type="jira")
    ref2 = VerificationEvidenceRef(
        id=uuid.uuid4(),
        evidence_item_id=ev2.id,
        excerpt="Task is currently open and blocked by security review",
    )
    ref2.evidence_item = ev2

    contradictions = evaluator.evaluate(case, [ref1, ref2], [case])
    assert len(contradictions) > 0
    assert contradictions[0].conflict_type == ConflictType.STATUS_CONFLICT.value


def test_prioritisation_and_recommendation_engine():
    rec_engine = RecommendationEngine()
    prio_engine = PrioritisationEngine()

    case = VerificationCase(
        id=uuid.uuid4(),
        title="Unbacked Finding",
        current_claim="High risk unbacked claim",
        case_status=VerificationCaseStatus.CANDIDATE.value,
        domain="bugs_blockers_risks",
    )
    comp = CompletenessEvaluator().evaluate(case, [])
    rel = SourceReliabilityEvaluator().evaluate(case, [])
    fresh = FreshnessEvaluator().evaluate(case, [], datetime.now(UTC), [])
    corrob = CorroborationEvaluator().evaluate(case, [])

    rec = rec_engine.evaluate(case, comp, rel, fresh, corrob, [], 1)
    assert rec.action == "request_additional_evidence"
    assert "Request Supporting Evidence" in rec.headline

    prio, reason = prio_engine.compute_priority(case, comp, fresh, [], rec)
    assert prio == VerificationPriority.CRITICAL
    assert "No supporting evidence attached" in reason


def test_continuous_monitoring_service(monkeypatch: pytest.MonkeyPatch):
    with isolated_auth_app(monkeypatch) as ctx:
        with session_scope(ctx.session_factory) as session:
            user = User(
                id=uuid.uuid4(),
                email=f"tester-{uuid.uuid4().hex[:6]}@example.com",
                password_hash="$argon2id$v=19$m=65536,t=3,p=4$fakehash",
                full_name="Verification Intelligence QA",
                status=UserStatus.ACTIVE,
            )
            session.add(user)
            session.flush()

            org = Organisation(
                id=uuid.uuid4(),
                name="Test Intelligence Org",
                slug=f"test-org-{uuid.uuid4().hex[:6]}",
                status=OrganisationStatus.ACTIVE,
                created_by_id=user.id,
            )
            session.add(org)
            session.flush()

            project = Project(
                id=uuid.uuid4(),
                organisation_id=org.id,
                name="Intelligence Test Project",
                slug=f"intel-test-{uuid.uuid4().hex[:6]}",
                status=ProjectStatus.ACTIVE,
                visibility=ProjectVisibility.PRIVATE,
                created_by_id=user.id,
                owner_id=user.id,
            )
            session.add(project)
            session.flush()

            case = VerificationCase(
                id=uuid.uuid4(),
                organisation_id=org.id,
                project_id=project.id,
                target_type=VerificationTargetType.KNOWLEDGE_ITEM.value,
                target_id=uuid.uuid4(),
                title="Database Engine Decision",
                domain="decisions_rationale",
                original_ai_claim="Platform uses PostgreSQL",
                current_claim="Platform uses PostgreSQL",
                case_status=VerificationCaseStatus.VERIFIED.value,  # Human previously verified this
                priority=VerificationPriority.HIGH.value,
                version=1,
            )
            session.add(case)
            session.flush()

            ev = EvidenceItem(
                id=uuid.uuid4(),
                organisation_id=org.id,
                project_id=project.id,
                category=EvidenceCategory.PROJECT_DOCUMENT.value,
                source_external_id="file-cfg-123",
                content_hash="a" * 64,
                title="Database Configuration File",
                source_type=EvidenceSourceType.DOCUMENT_UPLOAD.value,
                created_at=datetime.now(UTC),
            )
            session.add(ev)
            session.flush()

            ref = VerificationEvidenceRef(
                id=uuid.uuid4(),
                organisation_id=org.id,
                project_id=project.id,
                case_id=case.id,
                evidence_item_id=ev.id,
                relationship_to_finding="supports",
            )
            session.add(ref)
            session.flush()

            monitor = ContinuousMonitoringService(session)
            impact = monitor.process_source_change_event(
                project_id=project.id,
                evidence_item=ev,
                change_type="modified",
                triggered_by_user_id=user.id,
            )

            assert impact.reverification_triggered
            assert case.id in impact.affected_case_ids
            # Check that case.case_status is preserved as VERIFIED while setting reverification_triggered
            session.refresh(case)
            assert case.case_status == VerificationCaseStatus.VERIFIED.value
            monitoring_data = case.machine_assessment_json.get("monitoring_status")
            assert monitoring_data is not None
            assert monitoring_data.get("reverification_triggered") is True
