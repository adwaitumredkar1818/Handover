"""Comprehensive test suite for GitHub PAT authentication, repository discovery,
multi-branch commit deduplication, PR/issue extraction, contributor identity matching,
and contribution classification.
"""

from __future__ import annotations

import base64
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.models.enums import (
    ContributionCategory,
    EvidenceCategory,
    IdentityMatchMethod,
    ResponsibilityAlignment,
    SourceSyncRunStatus,
)
from app.models.evidence import EvidenceItem
from app.models.team_roster import TeamRosterMember
from app.services.contribution_attribution import (
    ContributionAttributionService,
    classify_contribution_domain,
    evaluate_alignment,
)
from app.services.integrations.github_client import GitHubClient
from app.services.integrations.sync_worker import SourceSyncWorkerService
from app.services.token_encryption import LocalTokenEncryptionService
from fastapi.testclient import TestClient
from tests.conftest import isolated_auth_app, register_and_login_user


def test_github_pat_validation_and_user_profile(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Test A: GitHub PAT validation - valid token vs invalid token."""
    def fake_handler(request: httpx.Request) -> httpx.Response:
        auth_hdr = request.headers.get("Authorization", "")
        if "valid_pat_token" in auth_hdr:
            return httpx.Response(
                200,
                json={
                    "login": "octocat",
                    "id": 583231,
                    "avatar_url": "https://avatars.githubusercontent.com/u/583231",
                    "name": "The Octocat",
                    "email": "octocat@github.com",
                    "plan": {"name": "pro"},
                },
                headers={
                    "x-oauth-scopes": "repo, read:org",
                    "x-ratelimit-remaining": "4990",
                    "x-ratelimit-limit": "5000",
                },
            )
        return httpx.Response(401, json={"message": "Bad credentials"})

    transport = httpx.MockTransport(fake_handler)
    with isolated_auth_app(
        monkeypatch,
        upload_storage_path=tmp_path / "pat_uploads",
        github_enabled=True,
        github_client_id="gh-cid",
        github_client_secret="gh-csec",
    ) as ctx:
        client = GitHubClient(settings=ctx.settings, transport=transport)

        # Valid token
        profile = client.fetch_user_profile(access_token="valid_pat_token")
        assert profile["login"] == "octocat"
        assert profile["id"] == 583231
        assert profile["_rate_limit"]["remaining"] == "4990"

        # Invalid token raises IntegrationProviderError (401)
        with pytest.raises(Exception) as exc_info:
            client.fetch_user_profile(access_token="invalid_token")
        assert getattr(exc_info.value, "status_code", None) == 401 or "github" in str(exc_info.value).lower()


def test_contributor_identity_matching_hierarchy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Test F & G: Contributor identity matching hierarchy and contribution classification."""
    # 1. Test domain classification across categories
    cat_db = classify_contribution_domain("Add PostgreSQL connection pool migration")
    assert cat_db == ContributionCategory.DATABASE_ENGINEERING

    cat_auth = classify_contribution_domain("Fix JWT session authentication error")
    assert cat_auth == ContributionCategory.AUTHENTICATION

    cat_ui = classify_contribution_domain("Update Next.js Tailwind component layout")
    assert cat_ui == ContributionCategory.FRONTEND_DEVELOPMENT

    cat_sec = classify_contribution_domain("Implement AES-256 encryption at rest")
    assert cat_sec == ContributionCategory.SECURITY

    with isolated_auth_app(
        monkeypatch,
        upload_storage_path=tmp_path / "roster_attr_uploads",
        github_enabled=True,
        github_client_id="gh-cid",
        github_client_secret="gh-csec",
    ) as ctx:
        with TestClient(ctx.app) as client:
            user = register_and_login_user(client, email="alice@company.com", full_name="Alice Developer")
            org_id = client.post(
                "/api/v1/organisations",
                headers=user.headers,
                json={"name": "Dev Org"},
            ).json()["id"]
            proj_id = client.post(
                f"/api/v1/organisations/{org_id}/projects",
                headers=user.headers,
                json={"name": "Handover Proj", "status": "active", "visibility": "private"},
            ).json()["id"]

            with ctx.session_factory() as session:
                dummy_hash = "a" * 64
                roster_ev = EvidenceItem(
                    organisation_id=uuid.UUID(org_id),
                    project_id=uuid.UUID(proj_id),
                    uploaded_by_user_id=user.user_id,
                    category="team_roster",
                    source_type="document_upload",
                    source_provider="local_upload",
                    source_external_id="doc_roster_1",
                    source_author_identity="hr@org.com",
                    title="Team Roster 2026",
                    content_hash=dummy_hash,
                )
                session.add(roster_ev)
                session.commit()

                # Create roster members
                rm_alice = TeamRosterMember(
                    project_id=uuid.UUID(proj_id),
                    evidence_item_id=roster_ev.id,
                    full_name="Alice Developer",
                    email="alice@company.com",
                    github_username="alicedev",
                    role_name="Frontend Lead",
                    primary_responsibilities=["React", "UI", "Tailwind CSS"],
                )
                rm_bob = TeamRosterMember(
                    project_id=uuid.UUID(proj_id),
                    evidence_item_id=roster_ev.id,
                    full_name="Bob Architect",
                    email="bob@company.com",
                    github_username="bobarch",
                    role_name="Backend Architect",
                    primary_responsibilities=["PostgreSQL", "Database", "FastAPI"],
                )
                session.add_all([rm_alice, rm_bob])
                session.commit()

                # Test alignment
                align_bob, exp_bob = evaluate_alignment(cat_db, rm_bob)
                assert align_bob == ResponsibilityAlignment.ALIGNED

                align_alice, exp_alice = evaluate_alignment(cat_db, rm_alice)
                assert align_alice in (
                    ResponsibilityAlignment.OUTSIDE_DECLARED_RESPONSIBILITY,
                    ResponsibilityAlignment.PARTIALLY_ALIGNED,
                )

                service = ContributionAttributionService(session=session)

                # 1. Exact GitHub username match -> 1.0 confidence
                ev_1 = EvidenceItem(
                    organisation_id=uuid.UUID(org_id),
                    project_id=uuid.UUID(proj_id),
                    uploaded_by_user_id=user.user_id,
                    category="commit",
                    source_type="github",
                    source_provider="github",
                    source_external_id="c_1",
                    source_author_identity="alicedev",
                    title="Update layout component",
                    content_hash="b" * 64,
                    metadata_json={"github_author_login": "alicedev"},
                )
                session.add(ev_1)
                session.commit()

                attr_1 = service.attribute_evidence(ev_1)
                assert attr_1 is not None
                assert attr_1.matched_roster_member_id == rm_alice.id
                assert attr_1.match_method == IdentityMatchMethod.EXACT_GITHUB_USERNAME.value
                assert attr_1.match_confidence == 1.0

                # 2. Exact Git commit email match -> 0.95 confidence
                ev_2 = EvidenceItem(
                    organisation_id=uuid.UUID(org_id),
                    project_id=uuid.UUID(proj_id),
                    uploaded_by_user_id=user.user_id,
                    category="commit",
                    source_type="github",
                    source_provider="github",
                    source_external_id="c_2",
                    source_author_identity="bob@company.com",
                    title="Add database migration",
                    content_hash="c" * 64,
                    metadata_json={"git_author_email": "bob@company.com"},
                )
                session.add(ev_2)
                session.commit()

                attr_2 = service.attribute_evidence(ev_2)
                assert attr_2 is not None
                assert attr_2.matched_roster_member_id == rm_bob.id
                assert attr_2.match_method == "exact_git_commit_email"
                assert attr_2.match_confidence == 0.95
                assert attr_2.responsibility_alignment == ResponsibilityAlignment.ALIGNED.value

                # 3. GitHub noreply email mapping -> 0.95 confidence
                ev_3 = EvidenceItem(
                    organisation_id=uuid.UUID(org_id),
                    project_id=uuid.UUID(proj_id),
                    uploaded_by_user_id=user.user_id,
                    category="commit",
                    source_type="github",
                    source_provider="github",
                    source_external_id="c_3",
                    source_author_identity="12345+alicedev@users.noreply.github.com",
                    title="Fix frontend css",
                    content_hash="d" * 64,
                    metadata_json={"git_author_email": "12345+alicedev@users.noreply.github.com"},
                )
                session.add(ev_3)
                session.commit()

                attr_3 = service.attribute_evidence(ev_3)
                assert attr_3 is not None
                assert attr_3.matched_roster_member_id == rm_alice.id
                assert attr_3.match_method == "github_noreply_email_mapping"
                assert attr_3.match_confidence == 0.95

                # 4. Ambiguous display name match -> 0.50 confidence with warning flag
                ev_4 = EvidenceItem(
                    organisation_id=uuid.UUID(org_id),
                    project_id=uuid.UUID(proj_id),
                    uploaded_by_user_id=user.user_id,
                    category="commit",
                    source_type="github",
                    source_provider="github",
                    source_external_id="c_4",
                    source_author_identity="Bob Architect",
                    title="Refactor backend service",
                    content_hash="e" * 64,
                    metadata_json={"git_author_name": "Bob Architect", "git_author_email": "unrelated@email.org"},
                )
                session.add(ev_4)
                session.commit()

                attr_4 = service.attribute_evidence(ev_4)
                assert attr_4 is not None
                assert attr_4.matched_roster_member_id == rm_bob.id
                assert attr_4.match_method == "ambiguous_name"
                assert attr_4.match_confidence == 0.50
                assert "ambiguous" in attr_4.alignment_explanation.lower()


def test_multi_branch_commit_deduplication_and_pr_extraction(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Test C, D, E & H: Multi-branch commit deduplication, PR commits, issue extraction."""
    shared_commit_sha = "a1b2c3d4e5f678901234567890abcdef12345678"

    def gh_mock_handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        path = request.url.path

        if path == "/user":
            return httpx.Response(
                200,
                json={"login": "testdev", "id": 9999, "avatar_url": None, "name": "Test Dev"},
                headers={"x-oauth-scopes": "repo, read:org"},
            )

        if path == "/user/repos":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": 101,
                        "node_id": "R_101",
                        "name": "sample-repo",
                        "full_name": "testdev/sample-repo",
                        "owner": {"login": "testdev"},
                        "private": True,
                        "html_url": "https://github.com/testdev/sample-repo",
                        "description": "Sample test repo",
                        "default_branch": "main",
                        "language": "Python",
                        "topics": ["fastapi", "ai"],
                        "created_at": "2024-01-01T00:00:00Z",
                        "pushed_at": "2024-06-01T00:00:00Z",
                        "open_issues_count": 3,
                        "permissions": {"admin": True, "push": True, "pull": True},
                    }
                ],
                headers={"link": ""},
            )

        if path == "/repos/testdev/sample-repo":
            return httpx.Response(
                200,
                json={
                    "id": 101,
                    "name": "sample-repo",
                    "full_name": "testdev/sample-repo",
                    "owner": {"login": "testdev"},
                    "private": True,
                    "visibility": "private",
                    "default_branch": "main",
                    "html_url": "https://github.com/testdev/sample-repo",
                    "description": "Sample test repo",
                    "permissions": {"pull": True},
                },
            )

        if path == "/repos/testdev/sample-repo/branches":
            return httpx.Response(
                200,
                json=[
                    {"name": "main", "commit": {"sha": shared_commit_sha}},
                    {"name": "feature-auth", "commit": {"sha": shared_commit_sha}},
                ],
            )

        if "/repos/testdev/sample-repo/commits" in path:
            return httpx.Response(
                200,
                json=[
                    {
                        "sha": shared_commit_sha,
                        "commit": {
                            "author": {
                                "name": "Test Dev",
                                "email": "testdev@company.com",
                                "date": "2024-06-01T12:00:00Z",
                            },
                            "committer": {
                                "name": "GitHub",
                                "email": "noreply@github.com",
                                "date": "2024-06-01T12:00:00Z",
                            },
                            "message": "feat: integrate auth\n\nCo-authored-by: Collaborator <collab@company.com>",
                            "verification": {"verified": True, "reason": "valid"},
                        },
                        "author": {"login": "testdev", "id": 9999},
                        "committer": None,
                        "parents": [{"sha": "0000000000000000000000000000000000000000"}],
                        "html_url": f"https://github.com/testdev/sample-repo/commit/{shared_commit_sha}",
                    }
                ],
            )

        if path == "/repos/testdev/sample-repo/issues":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": 501,
                        "number": 1,
                        "title": "Setup OAuth flow",
                        "body": "Configure OAuth scopes for integrations",
                        "state": "open",
                        "user": {"login": "testdev", "id": 9999},
                        "created_at": "2024-05-01T00:00:00Z",
                        "updated_at": "2024-05-02T00:00:00Z",
                        "html_url": "https://github.com/testdev/sample-repo/issues/1",
                        "labels": [{"name": "auth"}],
                    },
                    {
                        "id": 502,
                        "number": 2,
                        "title": "PR: Add auth models",
                        "body": "Implements user session storage",
                        "state": "closed",
                        "user": {"login": "testdev", "id": 9999},
                        "created_at": "2024-05-03T00:00:00Z",
                        "updated_at": "2024-05-04T00:00:00Z",
                        "html_url": "https://github.com/testdev/sample-repo/pull/2",
                        "pull_request": {"url": "https://api.github.com/repos/testdev/sample-repo/pulls/2"},
                    },
                ],
            )

        if "/pulls/2/commits" in path:
            return httpx.Response(
                200,
                json=[{"sha": shared_commit_sha}],
            )

        if "/pulls/2" in path:
            return httpx.Response(
                200,
                json={
                    "id": 502,
                    "number": 2,
                    "title": "PR: Add auth models",
                    "body": "Implements user session storage",
                    "state": "closed",
                    "merged": True,
                    "user": {"login": "testdev", "id": 9999},
                    "base": {"ref": "main"},
                    "head": {"ref": "feature-auth"},
                    "html_url": "https://github.com/testdev/sample-repo/pull/2",
                    "created_at": "2024-05-03T00:00:00Z",
                    "updated_at": "2024-05-04T00:00:00Z",
                },
            )

        if "/comments" in path or "/reviews" in path:
            return httpx.Response(200, json=[])

        if "/files" in path:
            return httpx.Response(
                200,
                json=[{"filename": "backend/app/auth.py", "status": "added", "additions": 45, "deletions": 0}],
            )

        if "/contents" in path:
            return httpx.Response(
                200,
                json={
                    "name": "README.md",
                    "path": "README.md",
                    "content": base64.b64encode(b"# Sample Repo\nArchitecture overview.").decode("ascii"),
                    "encoding": "base64",
                },
            )

        if "/contributors" in path:
            return httpx.Response(
                200,
                json=[{"login": "testdev", "id": 9999, "contributions": 15}],
            )

        return httpx.Response(200, json={})

    transport = httpx.MockTransport(gh_mock_handler)

    with isolated_auth_app(
        monkeypatch,
        upload_storage_path=tmp_path / "uploads",
        github_enabled=True,
        github_client_id="gh-cid",
        github_client_secret="gh-csec",
    ) as ctx:
        ctx.app.state.integration_http_transport = transport
        token_key = ctx.settings.security.token_encryption_key.get_secret_value()
        sync_worker = SourceSyncWorkerService(
            session_factory=ctx.session_factory,
            settings=ctx.settings,
            token_encryption=LocalTokenEncryptionService(token_encryption_key=token_key),
            http_transport=transport,
            worker_id="test-sync",
        )

        with TestClient(ctx.app) as client:
            user = register_and_login_user(client, email="lead@org.com", full_name="Dev Org")
            org_id = client.post(
                "/api/v1/organisations",
                headers=user.headers,
                json={"name": "Dev Org"},
            ).json()["id"]
            proj_id = client.post(
                f"/api/v1/organisations/{org_id}/projects",
                headers=user.headers,
                json={"name": "Sample Repo Project", "status": "active", "visibility": "private"},
            ).json()["id"]

            # 1. Connect GitHub source using PAT (backend auto-resolves username)
            conn_res = client.post(
                f"/api/v1/organisations/{org_id}/sources",
                headers=user.headers,
                json={
                    "provider": "github",
                    "secret_token": "valid_pat_token_test",
                    "account_identifier": "auto",
                },
            )
            assert conn_res.status_code == 201
            conn_data = conn_res.json()
            conn_id = conn_data["id"]
            assert conn_data["account_identifier"] == "testdev"

            # 2. Discover repositories
            disco_res = client.get(
                f"/api/v1/integrations/connections/{conn_id}/github/repositories?project_id={proj_id}",
                headers=user.headers,
            )
            assert disco_res.status_code == 200
            disco_data = disco_res.json()
            assert len(disco_data["items"]) == 1
            repo = disco_data["items"][0]
            assert repo["full_name"] == "testdev/sample-repo"
            assert repo["language"] == "Python"
            assert repo["already_mapped"] is False

            # 3. Create mapping with multi-branch sync scope
            map_res = client.post(
                f"/api/v1/projects/{proj_id}/integrations/github/mappings",
                headers=user.headers,
                json={
                    "source_connection_id": conn_id,
                    "owner": "testdev",
                    "repo": "sample-repo",
                    "branch_scope": "all",
                    "include_commits": True,
                    "include_pull_requests": True,
                    "include_issues": True,
                    "include_docs": True,
                },
            )
            assert map_res.status_code == 201
            mapping_id = map_res.json()["id"]

            # 4. Trigger sync and process via sync worker
            sync_res = client.post(
                f"/api/v1/projects/{proj_id}/integrations/mappings/{mapping_id}/sync",
                headers=user.headers,
                json={"sync_mode": "manual"},
            )
            assert sync_res.status_code == 202

            # Run worker job
            job_done = sync_worker.process_next_job()
            assert job_done is True

            # Verify evidence records
            evidence_res = client.get(
                f"/api/v1/projects/{proj_id}/evidence",
                headers=user.headers,
            )
            assert evidence_res.status_code == 200
            evidence_data = evidence_res.json()
            items = evidence_data.get("items", evidence_data if isinstance(evidence_data, list) else [])
            assert len(items) >= 3

            # Check commit deduplication across branches
            commits = [i for i in items if i["category"] == EvidenceCategory.COMMIT.value]
            # Must be exactly 1 commit record despite existing on both 'main' and 'feature-auth'
            assert len(commits) == 1
            commit_item = commits[0]
            branches = commit_item["metadata_json"].get("branches", [])
            assert "main" in branches
            assert "feature-auth" in branches

            # Check PR evidence with associated commit SHAs
            prs = [i for i in items if i["category"] == EvidenceCategory.PULL_REQUEST.value]
            assert len(prs) == 1
            pr_item = prs[0]
            assert shared_commit_sha in pr_item["metadata_json"].get("associated_commit_shas", [])

            # Check Issue evidence (distinct from PR)
            issues = [i for i in items if i["category"] == EvidenceCategory.ISSUE.value]
            assert len(issues) == 1
            assert issues[0]["metadata_json"].get("number") == 1
