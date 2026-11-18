"""Focused Tests for DEF-08: Conflict-Detection Heuristic Precision.

Platform: The Handover
Remediation: Post-Stage-7 — DEF-08 (MEDIUM)

Verifies principled, explainable contradiction classification:
1. Sequential Git commits (direct parent, multi-hop ancestry, merge commits, same-branch history)
   changing the same file/subsystem are treated as chronological evolution, NOT contradictions.
2. Explicit conflicting values in independent sources (DB paradigm, Auth paradigm, explicit ownership,
   status) are accurately detected with provenance.
3. Superseded historical migration narratives are not misclassified as simultaneous contradictions.
4. Non-auth "session" references (JSONL session logs, session reports, SQLAlchemy db session)
   do NOT trigger JWT-vs-Session auth conflicts, whereas genuine cookie/server-side session auth does.
5. Genuine simultaneous contradictions are preserved.
6. Diverged Git branches or commits with unavailable/ambiguous ancestry asserting mutually exclusive
   specifications are preserved with clear provenance explanation.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

from app.models.enums import ConflictType
from app.services.verification_intelligence import AdvancedContradictionEvaluator


def _mk_ref(
    *,
    title: str,
    excerpt: str,
    provider: str = "github",
    ts: datetime | None = None,
    category: str = "project_document",
    metadata: dict[str, Any] | None = None,
) -> Any:
    ev_id = uuid.uuid4()
    ev = SimpleNamespace(
        id=ev_id,
        title=title,
        category=category,
        source_type=provider,
        source_provider=provider,
        source_created_at=ts,
        metadata_json=metadata or {},
    )
    return SimpleNamespace(
        evidence_item_id=ev_id,
        chunk_id=uuid.uuid4(),
        original_title=title,
        excerpt=excerpt,
        source_provider=provider,
        source_timestamp=ts,
        evidence_item=ev,
    )


def _mk_case(
    *,
    domain: str,
    title: str,
    claim: str,
    person_name: str | None = None,
    provider: str = "github",
    refs: list[Any] | None = None,
    created_at: datetime | None = None,
) -> Any:
    return SimpleNamespace(
        id=uuid.uuid4(),
        target_type="knowledge_item",
        target_id=uuid.uuid4(),
        source_id=None,
        domain=domain,
        title=title,
        current_claim=claim,
        person_name=person_name,
        source_provider=provider,
        evidence_refs=refs or [],
        created_at=created_at or datetime.now(UTC),
    )


def test_sequential_git_commits_on_same_branch_do_not_create_false_conflicts() -> None:
    """Sequential commits and merge commits by different authors on main are chronological evolution, not conflicts."""
    t0 = datetime(2026, 10, 24, 21, 0, tzinfo=UTC)
    t1 = t0 + timedelta(hours=1)
    t2 = t0 + timedelta(hours=2)

    ref_c1 = _mk_ref(
        title="repo@aaa111: Integrate recruiter portal onboarding and career intelligence",
        excerpt="Integrate recruiter portal onboarding and career intelligence",
        provider="github",
        ts=t0,
        category="commit",
        metadata={
            "github_item_type": "commit",
            "repository": "org/skill-passport",
            "sha": "aaa111",
            "parent_shas": ["000000"],
            "branches": ["main"],
        },
    )
    ref_c2 = _mk_ref(
        title="repo@bbb222: Incorporate latest recruiter portal onboarding fixes and career intelligence",
        excerpt="Incorporate latest recruiter portal onboarding fixes and career intelligence",
        provider="github",
        ts=t1,
        category="commit",
        metadata={
            "github_item_type": "commit",
            "repository": "org/skill-passport",
            "sha": "bbb222",
            "parent_shas": ["aaa111"],
            "branches": ["main"],
        },
    )
    ref_merge = _mk_ref(
        title="repo@ccc333: Merge origin/main into main: incorporate recruiter portal onboarding fixes",
        excerpt="Merge origin/main into main: incorporate recruiter portal onboarding fixes",
        provider="github",
        ts=t2,
        category="commit",
        metadata={
            "github_item_type": "commit",
            "repository": "org/skill-passport",
            "sha": "ccc333",
            "parent_shas": ["bbb222", "fff999"],
            "branches": ["main"],
        },
    )

    c1 = _mk_case(
        domain="work_items",
        title="Integrate recruiter portal onboarding",
        claim="Integrate recruiter portal onboarding and career intelligence",
        person_name="dev-alice",
        refs=[ref_c1],
        created_at=t0,
    )
    c2 = _mk_case(
        domain="work_items",
        title="Recruiter portal onboarding fixes",
        claim="Incorporate latest recruiter portal onboarding fixes and career intelligence",
        person_name="dev-bob",
        refs=[ref_c2],
        created_at=t1,
    )
    c3 = _mk_case(
        domain="work_items",
        title="Merge origin/main into main",
        claim="Merge origin/main into main: incorporate recruiter portal onboarding fixes",
        person_name="dev-carol",
        refs=[ref_merge],
        created_at=t2,
    )

    evaluator = AdvancedContradictionEvaluator()
    all_cases = [c1, c2, c3]
    for c in all_cases:
        assert evaluator.evaluate(c, c.evidence_refs, all_cases) == []


def test_session_log_references_do_not_trigger_jwt_auth_conflicts() -> None:
    """Words like 'session logs', 'session reports', or 'db session' must NOT conflict with JWT authentication."""
    now = datetime.now(UTC)
    jwt_case = _mk_case(
        domain="decisions_rationale",
        title="JWT Auth & RBAC Implementation",
        claim="Platform uses JWT bearer token authentication with RBAC guards.",
        provider="github",
        refs=[_mk_ref(title="auth.md", excerpt="JWT bearer token auth", ts=now)],
    )
    log_case = _mk_case(
        domain="technical_architecture",
        title="Stats Tool Session Reports",
        claim="Estimated savings are derived from JSONL session logs and excluded from session reports.",
        provider="github",
        refs=[_mk_ref(title="stats.md", excerpt="JSONL session logs and session reports", ts=now)],
    )
    db_session_case = _mk_case(
        domain="technical_architecture",
        title="Database Session Lifecycle",
        claim="Each FastAPI request opens a scoped SQLAlchemy db session committed atomically.",
        provider="document_upload",
        refs=[_mk_ref(title="db.md", excerpt="SQLAlchemy db session", ts=now)],
    )

    evaluator = AdvancedContradictionEvaluator()
    all_cases = [jwt_case, log_case, db_session_case]
    assert evaluator.evaluate(jwt_case, jwt_case.evidence_refs, all_cases) == []
    assert evaluator.evaluate(log_case, log_case.evidence_refs, all_cases) == []
    assert evaluator.evaluate(db_session_case, db_session_case.evidence_refs, all_cases) == []


def test_genuine_simultaneous_contradictions_across_independent_sources_are_detected() -> None:
    """Explicit conflicting values (JWT vs cookie-based session auth, Postgres vs MongoDB, competing explicit owners) are detected."""
    now = datetime.now(UTC)
    # 1. Genuine auth contradiction
    jwt_spec = _mk_case(
        domain="decisions_rationale",
        title="Auth ADR: Stateless JWT",
        claim="All API clients authenticate strictly via stateless JWT bearer tokens.",
        provider="document_upload",
        refs=[_mk_ref(title="ADR-01.md", excerpt="Stateless JWT bearer tokens", provider="document_upload", ts=now)],
    )
    cookie_spec = _mk_case(
        domain="decisions_rationale",
        title="Security Spec: Server-Side Session Auth",
        claim="All API clients must use server-side session auth with cookie-based authentication.",
        provider="jira",
        refs=[_mk_ref(title="SEC-42", excerpt="server-side session auth", provider="jira", ts=now)],
    )
    evaluator = AdvancedContradictionEvaluator()
    auth_conflicts = evaluator.evaluate(jwt_spec, jwt_spec.evidence_refs, [jwt_spec, cookie_spec])
    assert len(auth_conflicts) == 1
    assert auth_conflicts[0].conflict_type == ConflictType.DECISION_CONFLICT.value
    assert "JWT vs State Session" in auth_conflicts[0].explanation

    # 2. Genuine DB contradiction
    pg_spec = _mk_case(
        domain="technical_architecture",
        title="Canonical Database: PostgreSQL",
        claim="Canonical application records are stored exclusively in PostgreSQL.",
        provider="document_upload",
        refs=[_mk_ref(title="arch-v1.md", excerpt="PostgreSQL", provider="document_upload", ts=now)],
    )
    mongo_spec = _mk_case(
        domain="technical_architecture",
        title="Storage Design: MongoDB",
        claim="Application state and handover records are stored in MongoDB collections.",
        provider="slack",
        refs=[_mk_ref(title="#architecture", excerpt="MongoDB collections", provider="slack", ts=now)],
    )
    db_conflicts = evaluator.evaluate(pg_spec, pg_spec.evidence_refs, [pg_spec, mongo_spec])
    assert len(db_conflicts) == 1
    assert db_conflicts[0].conflict_type == ConflictType.TECHNICAL_CONFLICT.value

    # 3. Genuine explicit ownership contradiction across independent sources
    own_a = _mk_case(
        domain="responsibilities_ownership",
        title="Billing Pipeline Ownership",
        claim="Alice is the primary owner responsible for the billing settlement pipeline and Stripe webhooks.",
        person_name="Alice",
        provider="document_upload",
        refs=[_mk_ref(title="roster.docx", excerpt="Alice owns billing settlement pipeline", provider="document_upload", ts=now)],
    )
    own_b = _mk_case(
        domain="responsibilities_ownership",
        title="Billing Pipeline Maintainer",
        claim="Bob is the sole owner responsible for the billing settlement pipeline and Stripe webhooks.",
        person_name="Bob",
        provider="jira",
        refs=[_mk_ref(title="OPS-12", excerpt="Bob is sole owner of billing settlement pipeline", provider="jira", ts=now)],
    )
    own_conflicts = evaluator.evaluate(own_a, own_a.evidence_refs, [own_a, own_b])
    assert len(own_conflicts) == 1
    assert own_conflicts[0].conflict_type == ConflictType.OWNERSHIP_CONFLICT.value


def test_superseded_historical_migration_narrative_is_not_flagged_as_simultaneous_conflict() -> None:
    """Historical migration statements documenting evolution over time must not trigger false contradictions."""
    t_old = datetime(2026, 1, 10, 10, 0, tzinfo=UTC)
    t_new = datetime(2026, 6, 15, 10, 0, tzinfo=UTC)

    old_doc = _mk_case(
        domain="decisions_rationale",
        title="Prototype DB Note",
        claim="Initial prototype uses MongoDB for rapid schema iteration.",
        provider="document_upload",
        refs=[_mk_ref(title="proto.md", excerpt="MongoDB", provider="document_upload", ts=t_old)],
        created_at=t_old,
    )
    migration_adr = _mk_case(
        domain="decisions_rationale",
        title="ADR-05: Database Migration",
        claim="We migrated from MongoDB to PostgreSQL for relational integrity and auditability.",
        provider="document_upload",
        refs=[_mk_ref(title="ADR-05.md", excerpt="migrated from MongoDB to PostgreSQL", provider="document_upload", ts=t_new)],
        created_at=t_new,
    )

    evaluator = AdvancedContradictionEvaluator()
    assert evaluator.evaluate(old_doc, old_doc.evidence_refs, [old_doc, migration_adr]) == []
    assert evaluator.evaluate(migration_adr, migration_adr.evidence_refs, [old_doc, migration_adr]) == []


def test_branch_divergence_and_ambiguous_ancestry_preserve_contradictions() -> None:
    """Commits on diverged branches (or with unavailable ancestry) asserting incompatible specs remain flagged."""
    now = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)

    # Disjoint branches without parent-child ancestry
    ref_branch_a = _mk_ref(
        title="repo@111aaa: Use PostgreSQL as primary store",
        excerpt="Use PostgreSQL as primary store",
        provider="github",
        ts=now,
        category="commit",
        metadata={
            "github_item_type": "commit",
            "repository": "org/platform",
            "sha": "111aaa",
            "parent_shas": ["000base"],
            "branches": ["feature/postgres-canonical"],
        },
    )
    ref_branch_b = _mk_ref(
        title="repo@222bbb: Use MongoDB as primary store",
        excerpt="Use MongoDB as primary store",
        provider="github",
        ts=now + timedelta(minutes=30),
        category="commit",
        metadata={
            "github_item_type": "commit",
            "repository": "org/platform",
            "sha": "222bbb",
            "parent_shas": ["000base"],
            "branches": ["feature/mongo-store"],
        },
    )
    c_a = _mk_case(
        domain="technical_architecture",
        title="Postgres Branch Spec",
        claim="Primary datastore is PostgreSQL.",
        refs=[ref_branch_a],
    )
    c_b = _mk_case(
        domain="technical_architecture",
        title="Mongo Branch Spec",
        claim="Primary datastore is MongoDB.",
        refs=[ref_branch_b],
    )

    evaluator = AdvancedContradictionEvaluator()
    div_conflicts = evaluator.evaluate(c_a, c_a.evidence_refs, [c_a, c_b])
    assert len(div_conflicts) == 1
    assert "diverged branches" in div_conflicts[0].explanation

    # Unavailable / ambiguous branch & ancestry metadata
    ref_amb_a = _mk_ref(
        title="repo@999a: REST API architecture",
        excerpt="REST API architecture",
        provider="github",
        ts=now,
        category="commit",
        metadata={"github_item_type": "commit", "repository": "org/platform", "sha": "999a"},
    )
    ref_amb_b = _mk_ref(
        title="repo@999b: GraphQL API architecture",
        excerpt="GraphQL API architecture",
        provider="github",
        ts=now + timedelta(hours=3),
        category="commit",
        metadata={"github_item_type": "commit", "repository": "org/platform", "sha": "999b"},
    )
    c_amb_a = _mk_case(
        domain="technical_architecture",
        title="REST API Spec",
        claim="Public backend exposes a RESTful API architecture.",
        refs=[ref_amb_a],
    )
    c_amb_b = _mk_case(
        domain="technical_architecture",
        title="GraphQL API Spec",
        claim="Public backend exposes a GraphQL gateway.",
        refs=[ref_amb_b],
    )
    amb_conflicts = evaluator.evaluate(c_amb_a, c_amb_a.evidence_refs, [c_amb_a, c_amb_b])
    assert len(amb_conflicts) == 1
    assert "ancestry unavailable/ambiguous" in amb_conflicts[0].explanation
