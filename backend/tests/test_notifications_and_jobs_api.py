"""Integration tests for persistent notifications and active background jobs APIs."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models.enums import BackgroundJobStatus, NotificationType
from app.models.job import BackgroundJob
from app.models.notification import NotificationItem
from tests.conftest import isolated_auth_app, register_and_login_user


def test_notifications_and_active_jobs_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test creating, listing, unread count tracking, marking read, and active job telemetry."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        db_factory = ctx.session_factory
        user = register_and_login_user(
            client,
            email="notif.user@example.com",
            full_name="Notification Tester",
        )

        org_res = client.post(
            "/api/v1/organisations",
            headers=user.headers,
            json={"name": "Notif Org", "slug": f"notif-org-{uuid.uuid4().hex[:6]}"},
        )
        org_id = org_res.json()["id"]

        proj_res = client.post(
            f"/api/v1/organisations/{org_id}/projects",
            headers=user.headers,
            json={"name": "Notif Project", "slug": f"notif-proj-{uuid.uuid4().hex[:6]}"},
        )
        project_id = proj_res.json()["id"]

        user_id = str(user.user_id)

        # 1. Seed notifications in database
        notif1_id = uuid.uuid4()
        notif2_id = uuid.uuid4()
        with db_factory() as db:
            n1 = NotificationItem(
                id=notif1_id,
                organisation_id=uuid.UUID(org_id),
                project_id=uuid.UUID(project_id),
                user_id=uuid.UUID(user_id),
                notification_type=NotificationType.SOURCE_SYNC_COMPLETED,
                title="GitHub Synchronisation Complete",
                body="Successfully ingested 14 commits, 3 pull requests, and 8 issues.",
                severity="success",
                is_read=False,
                metadata_json={"source": "github", "items_count": 25},
            )
            n2 = NotificationItem(
                id=notif2_id,
                organisation_id=uuid.UUID(org_id),
                project_id=uuid.UUID(project_id),
                user_id=uuid.UUID(user_id),
                notification_type=NotificationType.ROSTER_EXTRACTED,
                title="Team Roster Extracted",
                body="Extracted 6 team members and reconciled roles.",
                severity="info",
                is_read=False,
                metadata_json={"category": "team_roster", "members_count": 6},
            )
            db.add_all([n1, n2])
            db.commit()

        # 2. List notifications via API
        list_res = client.get("/api/v1/notifications", headers=user.headers)
        assert list_res.status_code == 200
        data = list_res.json()
        assert data["total"] == 2
        assert data["unread_count"] == 2
        assert len(data["items"]) == 2

        # 3. Mark single notification as read
        patch_res = client.patch(f"/api/v1/notifications/{notif1_id}/read", headers=user.headers)
        assert patch_res.status_code == 200
        assert patch_res.json()["is_read"] is True

        # Check updated unread count
        list_res2 = client.get("/api/v1/notifications", headers=user.headers)
        assert list_res2.status_code == 200
        data2 = list_res2.json()
        assert data2["unread_count"] == 1

        # 4. Mark all read
        mark_all_res = client.post("/api/v1/notifications/mark-all-read", headers=user.headers)
        assert mark_all_res.status_code == 200
        assert mark_all_res.json()["marked_read"] >= 1

        list_res3 = client.get("/api/v1/notifications", headers=user.headers)
        assert list_res3.json()["unread_count"] == 0

        # 5. Active jobs endpoint test
        job_id = uuid.uuid4()
        with db_factory() as db:
            active_job = BackgroundJob(
                id=job_id,
                organisation_id=uuid.UUID(org_id),
                project_id=uuid.UUID(project_id),
                job_type="source_sync",
                status=BackgroundJobStatus.RUNNING.value,
                attempt_count=1,
                payload_json={
                    "stage": "syncing_github_commits",
                    "progress_percent": 45,
                    "current_item": "Ingesting commit batch 2 of 5",
                },
            )
            db.add(active_job)
            db.commit()

        jobs_res = client.get(f"/api/v1/projects/{project_id}/jobs/active", headers=user.headers)
        assert jobs_res.status_code == 200
        jobs_data = jobs_res.json()
        assert len(jobs_data) == 1
        assert jobs_data[0]["job_type"] == "source_sync"
        assert jobs_data[0]["progress_percent"] == 45
        assert jobs_data[0]["stage"] == "syncing_github_commits"
        assert jobs_data[0]["message"] == "Ingesting commit batch 2 of 5"

        # Complete the job
        with db_factory() as db:
            j = db.get(BackgroundJob, job_id)
            if j:
                j.status = BackgroundJobStatus.SUCCEEDED.value
                db.commit()

        # Should now be empty in active jobs
        jobs_res2 = client.get(f"/api/v1/projects/{project_id}/jobs/active", headers=user.headers)
        assert jobs_res2.status_code == 200
        assert len(jobs_res2.json()) == 0
