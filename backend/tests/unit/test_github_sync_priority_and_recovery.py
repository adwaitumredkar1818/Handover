"""Unit & regression tests for GitHub document-first sync order, timeouts, and stale-lease recovery."""

from __future__ import annotations

import base64
import uuid
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.core.security import utc_now
from app.db.base import Base
from app.models.enums import (
    BackgroundJobStatus,
    BackgroundJobType,
    EvidenceCategory,
    EvidenceIndexingStatus,
    EvidenceSourceType,
    SourceConnectionStatus,
    SourcePermissionVerificationStatus,
    SourceSyncRunStatus,
    SourceVisibilityPolicy,
)
from app.models.evidence import EvidenceItem
from app.models.integration import (
    ProjectSourceMapping,
    SourceAccessPolicy,
    SourceConnection,
    SourceSyncRun,
)
from app.models.job import BackgroundJob
from app.models.organisation import Organisation
from app.models.project import Project
from app.models.user import User
from app.repositories.evidence import EvidenceRepository
from app.repositories.integration import IntegrationRepository
from app.repositories.job import BackgroundJobRepository
from app.services.fast_extractor import is_evidence_semantic_eligible
from app.services.integrations.access_policy import SourceAccessPolicyService
from app.services.integrations.errors import IntegrationProviderError
from app.services.integrations.evidence_ingestor import SourceEvidenceIngestor
from app.services.integrations.github_client import (
    GitHubClient,
    _is_candidate_doc_path,
)
from app.services.integrations.github_sync import GitHubSyncOrchestrator


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _make_sqlite_session_factory() -> sessionmaker:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _seed_mapping(session) -> tuple[User, Project, ProjectSourceMapping, SourceAccessPolicy, SourceSyncRun, BackgroundJob]:
    now = utc_now()
    user = User(
        id=uuid.uuid4(),
        email="owner@example.com",
        password_hash="hashed",
        full_name="Repo Owner",
        status="active",
        is_email_verified=True,
        email_verified_at=now,
    )
    org = Organisation(
        id=uuid.uuid4(),
        name="Test Org",
        slug=f"test-org-{uuid.uuid4().hex[:6]}",
        status="active",
        created_by_id=user.id,
    )
    project = Project(
        id=uuid.uuid4(),
        organisation_id=org.id,
        name="ConArk Test",
        slug=f"conark-test-{uuid.uuid4().hex[:6]}",
        status="active",
        created_by_id=user.id,
        owner_id=user.id,
    )
    conn = SourceConnection(
        id=uuid.uuid4(),
        organisation_id=org.id,
        provider="github",
        display_name="GitHub Connection",
        status=SourceConnectionStatus.ACTIVE.value,
        created_by_user_id=user.id,
    )
    policy = SourceAccessPolicy(
        id=uuid.uuid4(),
        organisation_id=org.id,
        project_id=project.id,
        source_connection_id=conn.id,
        provider="github",
        scope_identifier="github:1334895737",
        visibility_policy=SourceVisibilityPolicy.PROJECT_MEMBERS_VERIFIED.value,
        provider_visibility="public",
        sync_permission_status=SourcePermissionVerificationStatus.VERIFIED.value,
    )
    mapping = ProjectSourceMapping(
        id=uuid.uuid4(),
        organisation_id=org.id,
        project_id=project.id,
        source_connection_id=conn.id,
        source_access_policy_id=policy.id,
        created_by_user_id=user.id,
        provider="github",
        resource_type="github_repository",
        external_site_id="github.com",
        external_resource_id="1334895737",
        external_resource_key="acme/conark-app",
        external_resource_name="conark-app",
        default_branch="main",
        provider_visibility="public",
        status="active",
        sync_config_json={
            "include_docs": True,
            "include_commits": True,
            "include_issues": False,
            "include_pull_requests": False,
            "include_discussions": False,
            "branch_scope": "default",
        },
    )
    job = BackgroundJob(
        id=uuid.uuid4(),
        organisation_id=org.id,
        project_id=project.id,
        triggered_by_user_id=user.id,
        job_type=BackgroundJobType.SOURCE_SYNC.value,
        status=BackgroundJobStatus.QUEUED.value,
        priority=50,
        attempt_count=0,
        max_attempts=3,
        payload_json={"mapping_id": str(mapping.id)},
    )
    sync_run = SourceSyncRun(
        id=uuid.uuid4(),
        organisation_id=org.id,
        project_id=project.id,
        project_source_mapping_id=mapping.id,
        source_connection_id=conn.id,
        background_job_id=job.id,
        triggered_by_user_id=user.id,
        provider="github",
        sync_mode="initial",
        status=SourceSyncRunStatus.QUEUED.value,
    )
    session.add_all([user, org, project, conn, policy, mapping, job, sync_run])
    session.commit()
    return user, project, mapping, policy, sync_run, job


def test_document_first_sync_order_excludes_noise_and_queues_high_priority_indexing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """High-value docs/manifests must ingest and commit before commits while .agents/.vite are excluded."""
    SessionFactory = _make_sqlite_session_factory()
    # Stub side-effect hooks from FastAPI main module
    monkeypatch.setattr("app.main.signal_worker_activity", lambda: None, raising=False)
    monkeypatch.setattr(
        "app.services.pipeline_coordinator.invalidate_project_status_cache",
        lambda *_a, **_k: None,
        raising=False,
    )

    api_call_order: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        api_call_order.append(path)
        if path == "/repos/acme/conark-app":
            return httpx.Response(
                200,
                json={
                    "id": 1334895737,
                    "name": "conark-app",
                    "full_name": "acme/conark-app",
                    "private": False,
                    "visibility": "public",
                    "default_branch": "main",
                    "description": "Construction intelligence platform.",
                    "html_url": "https://github.com/acme/conark-app",
                    "updated_at": "2026-11-10T10:00:00Z",
                    "owner": {"login": "acme"},
                    "permissions": {"pull": True},
                },
            )
        if path == "/repos/acme/conark-app/readme":
            return httpx.Response(
                200,
                json={
                    "path": "README.md",
                    "sha": "sha-readme",
                    "html_url": "https://github.com/acme/conark-app/blob/main/README.md",
                    "encoding": "base64",
                    "size": 120,
                    "content": _b64("# ConArk\n\nPrimary architecture and setup instructions for construction appraisal.\n" * 2),
                },
            )
        if path == "/repos/acme/conark-app/git/trees/main":
            return httpx.Response(
                200,
                json={
                    "tree": [
                        {"path": ".agents/skills/supabase/SKILL.md", "type": "blob", "size": 300},
                        {"path": ".vite/deps/package.json", "type": "blob", "size": 300},
                        {"path": "CHANGELOG.md", "type": "blob", "size": 300},
                        {"path": "requirements.txt", "type": "blob", "size": 80},
                        {"path": "TRD.md", "type": "blob", "size": 150},
                        {"path": "PRD.md", "type": "blob", "size": 150},
                        {"path": "docs/architecture.md", "type": "blob", "size": 150},
                    ]
                },
            )
        content_map = {
            "/repos/acme/conark-app/contents/requirements.txt": "fastapi>=0.115.0\nxgboost>=2.1.0\n",
            "/repos/acme/conark-app/contents/docs/architecture.md": "# Architecture\nFastAPI + Next.js + PostgreSQL system boundaries and services.\n",
            "/repos/acme/conark-app/contents/PRD.md": "# Product Requirements\nCost estimation and handover workflows for field teams.\n",
            "/repos/acme/conark-app/contents/TRD.md": "# Technical Requirements\nPostgreSQL schema, XGBoost model serving, and API contracts.\n",
        }
        if path in content_map:
            text = content_map[path]
            return httpx.Response(
                200,
                json={
                    "path": path.split("/contents/", 1)[1],
                    "sha": f"sha-{len(text)}",
                    "encoding": "base64",
                    "size": len(text),
                    "content": _b64(text),
                },
            )
        if path == "/repos/acme/conark-app/commits":
            return httpx.Response(
                200,
                headers={"ETag": '"c-etag"'},
                json=[
                    {
                        "sha": "1111111111111111",
                        "html_url": "https://github.com/acme/conark-app/commit/1111111111111111",
                        "author": {"login": "alice"},
                        "commit": {
                            "author": {"name": "Alice", "email": "a@acme.dev", "date": "2026-11-11T09:00:00Z"},
                            "message": "Initial commit of FastAPI backend",
                        },
                    }
                ],
            )
        if path == "/repos/acme/conark-app/commits/1111111111111111":
            return httpx.Response(200, json={"files": [{"filename": "main.py", "status": "added", "additions": 10, "deletions": 0, "changes": 10}]})
        if path == "/repos/acme/conark-app/contributors":
            return httpx.Response(200, json=[{"login": "alice", "contributions": 5}])
        return httpx.Response(404, json={"message": "Not Found"})

    settings = Settings()
    transport = httpx.MockTransport(handler)
    with SessionFactory() as session:
        user, project, mapping, policy, sync_run, _job = _seed_mapping(session)
        orchestrator = GitHubSyncOrchestrator(
            settings=settings,
            github_client=GitHubClient(settings=settings, transport=transport),
            integration_repo=IntegrationRepository(session),
            ingestor=SourceEvidenceIngestor(session=session, evidence_repository=EvidenceRepository(session)),
            access_policy_service=SourceAccessPolicyService(),
        )
        report = orchestrator.execute_sync(
            mapping=mapping,
            policy=policy,
            access_token="gho_test",
            actor_user_id=user.id,
            external_user_id="999",
            external_username="tester",
            sync_mode="initial",
            sync_run=sync_run,
        )
        session.commit()

        assert report.items_discovered == 7  # repo + 5 docs/manifests + 1 commit
        assert report.items_created == 7
        assert sync_run.cursor_after_json is not None
        assert sync_run.cursor_after_json["current_phase"] == "completed"
        assert "last_progress_at" in sync_run.cursor_after_json

        # Verify README / git tree fetched BEFORE commits
        assert api_call_order.index("/repos/acme/conark-app/readme") < api_call_order.index(
            "/repos/acme/conark-app/commits"
        )
        # Verify priority ordering: architecture -> PRD -> TRD
        assert api_call_order.index("/repos/acme/conark-app/contents/requirements.txt") < api_call_order.index(
            "/repos/acme/conark-app/contents/PRD.md"
        )
        assert api_call_order.index("/repos/acme/conark-app/contents/docs/architecture.md") < api_call_order.index(
            "/repos/acme/conark-app/contents/PRD.md"
        )

        # Verify excluded files never created evidence items
        titles = {
            ev.title
            for ev in session.execute(select(EvidenceItem).where(EvidenceItem.project_id == project.id)).scalars().all()
        }
        assert not any(".agents" in t or ".vite" in t or "CHANGELOG.md" in t for t in titles)
        assert any("PRD.md" in t for t in titles)
        assert any("TRD.md" in t for t in titles)

        # Verify non-commit indexing jobs got higher priority (80) than commit indexing jobs (110)
        idx_jobs = session.execute(
            select(BackgroundJob).where(
                BackgroundJob.project_id == project.id,
                BackgroundJob.job_type == BackgroundJobType.EVIDENCE_INDEXING.value,
            )
        ).scalars().all()
        priorities_by_cat = {}
        for j in idx_jobs:
            ev = session.get(EvidenceItem, j.evidence_id)
            if ev is not None:
                priorities_by_cat[ev.category] = j.priority
        assert priorities_by_cat[EvidenceCategory.DESIGN_DOCUMENT.value] == 80
        assert priorities_by_cat[EvidenceCategory.COMMIT.value] == 110


def test_sync_resume_is_idempotent_without_duplicating_committed_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Re-running sync after an interruption partway through preserves committed evidence with zero duplicates."""
    SessionFactory = _make_sqlite_session_factory()
    monkeypatch.setattr("app.main.signal_worker_activity", lambda: None, raising=False)
    monkeypatch.setattr(
        "app.services.pipeline_coordinator.invalidate_project_status_cache",
        lambda *_a, **_k: None,
        raising=False,
    )

    fail_on_commits = True

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/repos/acme/conark-app":
            return httpx.Response(
                200,
                json={
                    "id": 1334895737,
                    "name": "conark-app",
                    "full_name": "acme/conark-app",
                    "private": False,
                    "visibility": "public",
                    "default_branch": "main",
                    "html_url": "https://github.com/acme/conark-app",
                    "updated_at": "2026-11-10T10:00:00Z",
                    "owner": {"login": "acme"},
                    "permissions": {"pull": True},
                },
            )
        if path == "/repos/acme/conark-app/readme":
            return httpx.Response(
                200,
                json={
                    "path": "README.md",
                    "sha": "sha-readme",
                    "encoding": "base64",
                    "size": 90,
                    "content": _b64("# ConArk\n" + "Architecture notes and setup instructions.\n" * 3),
                },
            )
        if path == "/repos/acme/conark-app/git/trees/main":
            return httpx.Response(200, json={"tree": []})
        if path == "/repos/acme/conark-app/commits":
            if fail_on_commits:
                raise httpx.ReadTimeout("Simulated GitHub read timeout")
            return httpx.Response(
                200,
                json=[
                    {
                        "sha": "deadbeef12345678",
                        "author": {"login": "alice"},
                        "commit": {
                            "author": {"name": "Alice", "email": "a@acme.dev", "date": "2026-11-11T09:00:00Z"},
                            "message": "Recovered commit",
                        },
                    }
                ],
            )
        if path == "/repos/acme/conark-app/commits/deadbeef12345678":
            return httpx.Response(200, json={"files": []})
        if path == "/repos/acme/conark-app/contributors":
            return httpx.Response(200, json=[])
        return httpx.Response(404)

    settings = Settings()
    transport = httpx.MockTransport(handler)
    with SessionFactory() as session:
        user, project, mapping, policy, sync_run, _job = _seed_mapping(session)
        orchestrator = GitHubSyncOrchestrator(
            settings=settings,
            github_client=GitHubClient(settings=settings, transport=transport),
            integration_repo=IntegrationRepository(session),
            ingestor=SourceEvidenceIngestor(session=session, evidence_repository=EvidenceRepository(session)),
            access_policy_service=SourceAccessPolicyService(),
        )
        # First attempt fails on commit timeout AFTER README checkpoint committed
        with pytest.raises(IntegrationProviderError) as exc_info:
            orchestrator.execute_sync(
                mapping=mapping,
                policy=policy,
                access_token="gho_test",
                actor_user_id=user.id,
                external_user_id="999",
                external_username="tester",
                sync_mode="initial",
                sync_run=sync_run,
            )
        assert exc_info.value.retryable is True
        assert exc_info.value.code == "GITHUB_TIMEOUT"

        # Verify README + repo overview ALREADY persisted from earlier phase checkpoints!
        persisted = session.execute(select(EvidenceItem).where(EvidenceItem.project_id == project.id)).scalars().all()
        assert len(persisted) == 2

        # Second attempt succeeds cleanly and does not duplicate README or repo overview
        fail_on_commits = False
        orchestrator_retry = GitHubSyncOrchestrator(
            settings=settings,
            github_client=GitHubClient(settings=settings, transport=transport),
            integration_repo=IntegrationRepository(session),
            ingestor=SourceEvidenceIngestor(session=session, evidence_repository=EvidenceRepository(session)),
            access_policy_service=SourceAccessPolicyService(),
        )
        report = orchestrator_retry.execute_sync(
            mapping=mapping,
            policy=policy,
            access_token="gho_test",
            actor_user_id=user.id,
            external_user_id="999",
            external_username="tester",
            sync_mode="initial",
            sync_run=sync_run,
        )
        session.commit()
        assert report.items_discovered == 3
        assert report.items_unchanged == 2
        assert report.items_created == 1
        final_items = session.execute(select(EvidenceItem).where(EvidenceItem.project_id == project.id)).scalars().all()
        assert len(final_items) == 3


def test_stale_heartbeat_and_expired_lease_recovery_prevents_double_claim() -> None:
    """Stale RUNNING jobs must be reclaimable after heartbeat lapse without duplicate active claims."""
    SessionFactory = _make_sqlite_session_factory()
    with SessionFactory() as session:
        user, project, mapping, policy, sync_run, job = _seed_mapping(session)
        repo = BackgroundJobRepository(session)
        t0 = utc_now() - timedelta(minutes=10)

        claimed_1 = repo.claim_next_job(
            worker_id="dead-remote-worker",
            lease_seconds=1800,  # Long 30-min lease, but heartbeat stops!
            now=t0,
            job_type=BackgroundJobType.SOURCE_SYNC.value,
        )
        assert claimed_1 is not None
        assert claimed_1.id == job.id
        # Simulate updated_at also frozen at t0
        claimed_1.updated_at = t0
        session.commit()

        # Immediately 60s later: still within 180s stale heartbeat window -> second worker gets None
        t_soon = t0 + timedelta(seconds=60)
        assert (
            repo.claim_next_job(
                worker_id="second-worker",
                lease_seconds=180,
                now=t_soon,
                job_type=BackgroundJobType.SOURCE_SYNC.value,
                stale_heartbeat_seconds=180,
            )
            is None
        )

        # After 4 minutes (> 180s stale heartbeat, even though lease_expires_at is still 26 min away): reclaimed cleanly!
        t_stale = t0 + timedelta(minutes=4)
        reclaimed = repo.claim_next_job(
            worker_id="healthy-local-worker",
            lease_seconds=180,
            now=t_stale,
            job_type=BackgroundJobType.SOURCE_SYNC.value,
            stale_heartbeat_seconds=180,
        )
        assert reclaimed is not None
        assert reclaimed.id == job.id
        assert reclaimed.locked_by == "healthy-local-worker"
        assert reclaimed.attempt_count == 2
        session.commit()

        # Third worker cannot double-claim while healthy-local-worker holds the fresh lease
        assert (
            repo.claim_next_job(
                worker_id="third-worker",
                lease_seconds=180,
                now=t_stale + timedelta(seconds=10),
                job_type=BackgroundJobType.SOURCE_SYNC.value,
                stale_heartbeat_seconds=180,
            )
            is None
        )


def test_semantic_and_doc_filtering_rules() -> None:
    """Reject .agents/.vite/boilerplate markdown while keeping README, PRD, TRD eligible."""
    assert _is_candidate_doc_path("PRD.md", include_code=False) is True
    assert _is_candidate_doc_path("TRD.md", include_code=False) is True
    assert _is_candidate_doc_path("RENDER_DEPLOYMENT.md", include_code=False) is True
    assert _is_candidate_doc_path("frontend/package.json", include_code=False) is True
    assert _is_candidate_doc_path(".agents/skills/supabase/SKILL.md", include_code=False) is False
    assert _is_candidate_doc_path(".vite/deps/package.json", include_code=False) is False
    assert _is_candidate_doc_path("CHANGELOG.md", include_code=False) is False

    assert (
        is_evidence_semantic_eligible(
            category=EvidenceCategory.DESIGN_DOCUMENT.value,
            title="acme/repo: PRD.md",
            mime_type="text/markdown",
            text_len=250,
            metadata_json={"github_item_type": "documentation", "path": "PRD.md"},
        )
        is True
    )
    assert (
        is_evidence_semantic_eligible(
            category=EvidenceCategory.DESIGN_DOCUMENT.value,
            title="acme/repo: .agents/skills/supabase/SKILL.md",
            mime_type="text/markdown",
            text_len=1500,
            metadata_json={"github_item_type": "documentation", "path": ".agents/skills/supabase/SKILL.md"},
        )
        is False
    )
    assert (
        is_evidence_semantic_eligible(
            category=EvidenceCategory.DESIGN_DOCUMENT.value,
            title="acme/repo: CHANGELOG.md",
            mime_type="text/markdown",
            text_len=800,
            metadata_json={"github_item_type": "documentation", "path": "CHANGELOG.md"},
        )
        is False
    )
