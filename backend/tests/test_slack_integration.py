"""Integration tests for delegated Slack workspace channel discovery, sync, and evidence creation."""

from __future__ import annotations

import json
import uuid
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import Settings
from app.models.enums import BackgroundJobStatus, SourceSyncRunStatus
from app.models.evidence import EvidenceContent, EvidenceItem
from app.models.integration import ProjectSourceMapping, SourceConnection
from app.models.job import BackgroundJob
from app.models.notification import NotificationItem
from app.services.integrations.slack_client import SlackClient, SlackChannelCandidate
from app.services.integrations.slack_sync import SlackSyncOrchestrator
from app.services.integrations.sync_worker import SourceSyncWorkerService
from app.services.token_encryption import LocalTokenEncryptionService
from tests.conftest import isolated_auth_app, register_and_login_user


def test_slack_client_auth_test_and_discovery(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test SlackClient.auth_test, list_channels, and get_users_map against mock Slack API."""
    def slack_transport_handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        assert request.headers.get("Authorization") == "Bearer xoxb-mock-bot-token"

        if path == "/api/auth.test":
            return httpx.Response(200, json={
                "ok": True,
                "team": "Acme Engineering",
                "team_id": "T012345678",
                "user": "handover-bot",
                "user_id": "U012345678",
            })
        elif path == "/api/conversations.list":
            return httpx.Response(200, json={
                "ok": True,
                "channels": [
                    {
                        "id": "C001",
                        "name": "architecture-decisions",
                        "is_private": False,
                        "num_members": 24,
                        "topic": {"value": "RFCs and system design"},
                        "purpose": {"value": "Engineering architecture discussions"},
                    },
                    {
                        "id": "C002",
                        "name": "oncall-incidents",
                        "is_private": False,
                        "num_members": 15,
                        "topic": {"value": "Live incidents and retros"},
                        "purpose": {"value": "Incident coordination"},
                    },
                ],
                "response_metadata": {"next_cursor": ""},
            })
        elif path == "/api/users.list":
            return httpx.Response(200, json={
                "ok": True,
                "members": [
                    {
                        "id": "U001",
                        "name": "alice",
                        "real_name": "Alice Smith",
                        "profile": {"display_name": "asmith", "email": "alice@acme.com"},
                        "is_bot": False,
                    },
                ],
            })
        return httpx.Response(404, json={"ok": False, "error": "not_found"})

    monkeypatch.setattr(
        "app.services.integrations.slack_client.create_integration_http_client",
        lambda **kw: httpx.Client(transport=httpx.MockTransport(slack_transport_handler)),
    )

    settings = Settings()
    slack = SlackClient(settings=settings)

    auth = slack.auth_test("xoxb-mock-bot-token")
    assert auth["ok"] is True
    assert auth["team"] == "Acme Engineering"
    assert auth["team_id"] == "T012345678"

    channels = slack.list_channels("xoxb-mock-bot-token", types="public_channel")
    assert len(channels) == 2
    assert channels[0].name == "architecture-decisions"
    assert channels[0].id == "C001"
    assert channels[1].name == "oncall-incidents"

    users_map = slack.get_users_map("xoxb-mock-bot-token")
    assert "U001" in users_map
    assert users_map["U001"]["real_name"] == "Alice Smith"
    assert users_map["U001"]["email"] == "alice@acme.com"


def test_slack_api_routes_discovery_and_batch_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test FastAPI routes for Slack connection creation, dynamic channel discovery, and batch mapping."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        db_factory = ctx.session_factory
        user = register_and_login_user(
            client,
            email="slack_admin@example.com",
            full_name="Slack Admin",
        )

        # 1. Create org and project
        org_res = client.post(
            "/api/v1/organisations",
            headers=user.headers,
            json={"name": "Slack Test Org", "slug": f"slack-test-org-{uuid.uuid4().hex[:6]}"},
        )
        assert org_res.status_code == 201
        org_id = org_res.json()["id"]

        proj_res = client.post(
            f"/api/v1/organisations/{org_id}/projects",
            headers=user.headers,
            json={"name": "Slack Handover Project", "slug": f"slack-handover-{uuid.uuid4().hex[:6]}"},
        )
        assert proj_res.status_code == 201
        project_id = proj_res.json()["id"]

        # 2. Connect Slack source with mock bot token
        conn_res = client.post(
            f"/api/v1/organisations/{org_id}/sources",
            headers=user.headers,
            json={
                "provider": "slack",
                "secret_token": "xoxb-mock-bot-token-123",
                "account_identifier": "T099999",
                "display_name": "Acme Workspace",
            },
        )
        assert conn_res.status_code in (200, 201)
        conn_data = conn_res.json()
        connection_id = conn_data["id"]
        assert conn_data["provider"] == "slack"

        # 3. Discover channels with mock handler
        def slack_handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/conversations.list":
                return httpx.Response(200, json={
                    "ok": True,
                    "channels": [
                        {"id": "C_ARCH", "name": "arch-discussion", "is_private": False, "num_members": 10},
                        {"id": "C_DEVOPS", "name": "devops-alerts", "is_private": False, "num_members": 5},
                    ],
                })
            return httpx.Response(200, json={"ok": True})

        monkeypatch.setattr(
            "app.services.integrations.slack_client.create_integration_http_client",
            lambda **kw: httpx.Client(transport=httpx.MockTransport(slack_handler)),
        )

        disc_res = client.get(
            f"/api/v1/integrations/connections/{connection_id}/slack/channels",
            headers=user.headers,
        )
        assert disc_res.status_code == 200
        disc_data = disc_res.json()
        assert len(disc_data["items"]) == 2
        assert disc_data["items"][0]["id"] == "C_ARCH"

        # 4. Batch create mappings
        batch_res = client.post(
            f"/api/v1/projects/{project_id}/integrations/batch-mappings",
            headers=user.headers,
            json={
                "source_connection_id": connection_id,
                "mappings": [
                    {
                        "external_resource_key": "C_ARCH",
                        "external_resource_name": "arch-discussion",
                        "resource_type": "slack_channel",
                    },
                    {
                        "external_resource_key": "C_DEVOPS",
                        "external_resource_name": "devops-alerts",
                        "resource_type": "slack_channel",
                    },
                ],
            },
        )
        assert batch_res.status_code == 201
        batch_data = batch_res.json()
        assert batch_data["created_count"] == 2
        assert len(batch_data.get("mappings") or batch_data.get("created_mappings") or []) == 2


def test_slack_sync_worker_evidence_and_notification(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test SlackSyncOrchestrator ingesting messages, threads, and creating Evidence items + notifications."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        db_factory = ctx.session_factory
        user = register_and_login_user(
            client,
            email="slack_sync_owner@example.com",
            full_name="Sync Owner",
        )

        org_res = client.post(
            "/api/v1/organisations",
            headers=user.headers,
            json={"name": "Sync Org", "slug": f"sync-org-{uuid.uuid4().hex[:6]}"},
        )
        org_id = org_res.json()["id"]

        proj_res = client.post(
            f"/api/v1/organisations/{org_id}/projects",
            headers=user.headers,
            json={"name": "Sync Project", "slug": f"sync-proj-{uuid.uuid4().hex[:6]}"},
        )
        project_id = proj_res.json()["id"]

        conn_res = client.post(
            f"/api/v1/organisations/{org_id}/sources",
            headers=user.headers,
            json={
                "provider": "slack",
                "secret_token": "xoxb-test-sync-token",
                "account_identifier": "T08888",
                "display_name": "Acme Sync Workspace",
            },
        )
        assert conn_res.status_code in (200, 201)
        connection_id = conn_res.json()["id"]

        # Map channel C_HANDOVER
        map_res = client.post(
            f"/api/v1/projects/{project_id}/integrations/slack/mappings",
            headers=user.headers,
            json={
                "source_connection_id": connection_id,
                "external_resource_key": "C_HANDOVER",
                "external_resource_name": "project-handover",
            },
        )
        assert map_res.status_code == 201
        mapping_id = map_res.json()["id"]

        # Mock Slack API for sync
        def slack_sync_handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path == "/api/conversations.history":
                return httpx.Response(200, json={
                    "ok": True,
                    "messages": [
                        {
                            "type": "message",
                            "user": "U101",
                            "text": "Critical architectural decision: migrating from PostgreSQL tsvector to ChromaDB hybrid search.",
                            "ts": "1700000001.000100",
                            "reply_count": 2,
                            "thread_ts": "1700000001.000100",
                        },
                        {
                            "type": "message",
                            "user": "U102",
                            "text": "Acknowledged. Encryption envelope will remain AES-256-GCM.",
                            "ts": "1700000002.000200",
                        },
                    ],
                    "response_metadata": {"next_cursor": ""},
                })
            elif path == "/api/conversations.replies":
                return httpx.Response(200, json={
                    "ok": True,
                    "messages": [
                        {
                            "type": "message",
                            "user": "U101",
                            "text": "Parent message",
                            "ts": "1700000001.000100",
                        },
                        {
                            "type": "message",
                            "user": "U103",
                            "text": "Thread reply: benchmark shows sub-50ms latency with nomic-embed-text.",
                            "ts": "1700000001.000200",
                        },
                    ],
                })
            elif path == "/api/chat.getPermalink":
                return httpx.Response(200, json={
                    "ok": True,
                    "permalink": "https://acme.slack.com/archives/C_HANDOVER/p1700000001000100",
                })
            elif path == "/api/users.list":
                return httpx.Response(200, json={
                    "ok": True,
                    "members": [
                        {"id": "U101", "name": "lead_arch", "real_name": "Lead Architect", "profile": {"email": "arch@acme.com"}},
                        {"id": "U102", "name": "sec_eng", "real_name": "Security Engineer", "profile": {"email": "sec@acme.com"}},
                        {"id": "U103", "name": "perf_eng", "real_name": "Performance Engineer", "profile": {"email": "perf@acme.com"}},
                    ],
                })
            return httpx.Response(200, json={"ok": True})

        monkeypatch.setattr(
            "app.services.integrations.slack_client.create_integration_http_client",
            lambda **kw: httpx.Client(transport=httpx.MockTransport(slack_sync_handler)),
        )

        # Trigger sync
        sync_res = client.post(
            f"/api/v1/projects/{project_id}/integrations/mappings/{mapping_id}/sync",
            headers=user.headers,
        )
        assert sync_res.status_code in (200, 202)
        sync_data = sync_res.json()
        run_id = sync_data.get("sync_run", {}).get("id") or sync_data.get("sync_run_id")

        # Run sync worker
        worker = SourceSyncWorkerService(
            session_factory=db_factory,
            settings=ctx.settings,
            http_transport=httpx.MockTransport(slack_sync_handler),
            worker_id="test-slack-worker",
        )

        processed = worker.process_next_job()
        assert processed is True

        # Verify Evidence created in database
        with db_factory() as db:
            ev_items = db.scalars(
                select(EvidenceItem).where(
                    EvidenceItem.project_id == uuid.UUID(project_id),
                    EvidenceItem.source_type == "slack",
                )
            ).all()
            assert len(ev_items) >= 2
            thread_ev = next(e for e in ev_items if "1700000001.000100" in e.source_external_id)
            assert thread_ev.category == "discussion_thread"
            assert "Lead Architect" in (thread_ev.source_author_identity or "")

            content = db.scalars(
                select(EvidenceContent).where(EvidenceContent.evidence_id == thread_ev.id)
            ).first()
            assert content is not None
            assert "ChromaDB hybrid search" in content.extracted_text
            assert "Thread reply: benchmark shows sub-50ms latency" in content.extracted_text

            # Verify persistent notification created
            notifications = db.scalars(
                select(NotificationItem).where(
                    NotificationItem.project_id == uuid.UUID(project_id)
                )
            ).all()
            assert len(notifications) >= 1
            sync_notif = notifications[0]
            assert sync_notif.notification_type == "source_sync_completed"
            assert "Slack" in sync_notif.title
