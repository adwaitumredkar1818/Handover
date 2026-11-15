"""Phase 4.2.2 targeted tests for connected-source authorization policy and project sync RBAC."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models.integration import SourceConnection
from app.models.job import BackgroundJob
from tests.conftest import isolated_auth_app, register_and_login_user

_PASSWORD = "Strong!PolicyPass2026"


def _invite_accept(
    client: TestClient,
    *,
    org_id: str,
    inviter_headers: dict[str, str],
    invitee_email: str,
    invitee_headers: dict[str, str],
    role_name: str,
) -> None:
    inv = client.post(
        f"/api/v1/organisations/{org_id}/invitations",
        headers=inviter_headers,
        json={"email": invitee_email, "role_name": role_name},
    )
    assert inv.status_code == 201, inv.text
    token = inv.json()["development_invitation_token"]
    acc = client.post(f"/api/v1/invitations/{token}/accept", headers=invitee_headers)
    assert acc.status_code == 200, acc.text


def test_source_authorization_policy_and_creator_bypass_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify org_owner/org_admin authority, creator-bypass prevention, and project-role isolation."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        owner = register_and_login_user(
            client, full_name="Org Owner", email="owner.p422@example.com", password=_PASSWORD
        )
        admin = register_and_login_user(
            client, full_name="Org Admin", email="admin.p422@example.com", password=_PASSWORD
        )
        member = register_and_login_user(
            client, full_name="Org Member", email="member.p422@example.com", password=_PASSWORD
        )
        outsider = register_and_login_user(
            client, full_name="Outsider", email="outsider.p422@example.com", password=_PASSWORD
        )

        # Owner creates org & project
        org_res = client.post(
            "/api/v1/organisations",
            headers=owner.headers,
            json={"name": "Policy Audit Org", "slug": "policy-audit-org"},
        )
        assert org_res.status_code == 201
        org_id = org_res.json()["id"]

        proj_res = client.post(
            f"/api/v1/organisations/{org_id}/projects",
            headers=owner.headers,
            json={"name": "Audit Project", "slug": "audit-project", "status": "active"},
        )
        assert proj_res.status_code == 201
        proj_id = proj_res.json()["id"]

        _invite_accept(
            client,
            org_id=org_id,
            inviter_headers=owner.headers,
            invitee_email=admin.email,
            invitee_headers=admin.headers,
            role_name="org_admin",
        )
        _invite_accept(
            client,
            org_id=org_id,
            inviter_headers=owner.headers,
            invitee_email=member.email,
            invitee_headers=member.headers,
            role_name="org_member",
        )

        # Grant member a project_manager role in the project — must NOT grant org source authority!
        add_pm = client.post(
            f"/api/v1/projects/{proj_id}/members",
            headers=owner.headers,
            json={"user_id": str(member.user_id), "role_name": "project_manager"},
        )
        assert add_pm.status_code == 201

        # Project manager (who is org_member) CANNOT create org-level source connection
        mem_create = client.post(
            f"/api/v1/organisations/{org_id}/sources",
            headers=member.headers,
            json={
                "provider": "github",
                "account_identifier": "blocked-member",
                "secret_token": "ghp_BlockedMemberToken2026",
            },
        )
        assert mem_create.status_code == 403
        assert mem_create.json()["error"]["code"] == "FORBIDDEN"

        # Org admin CAN create, view, patch, and disconnect a source connection
        admin_create = client.post(
            f"/api/v1/organisations/{org_id}/sources",
            headers=admin.headers,
            json={
                "provider": "github",
                "account_identifier": "admin-github",
                "secret_token": "ghp_AdminSecretToken2026",
                "is_shared": False,
            },
        )
        assert admin_create.status_code == 201
        conn_id = admin_create.json()["id"]

        # Simulate a legacy connection whose created_by_user_id happens to be the org_member
        with ctx.session_factory() as db:
            conn_obj = db.get(SourceConnection, uuid.UUID(conn_id))
            assert conn_obj is not None
            conn_obj.created_by_user_id = member.user_id
            db.commit()

        # Even as creator, org_member CANNOT patch or disconnect the connection
        mem_patch = client.patch(
            f"/api/v1/sources/{conn_id}",
            headers=member.headers,
            json={"is_shared": True},
        )
        assert mem_patch.status_code == 403

        mem_disc = client.post(f"/api/v1/sources/{conn_id}/disconnect", headers=member.headers)
        assert mem_disc.status_code == 403

        mem_integ_disc = client.post(
            f"/api/v1/integrations/connections/{conn_id}/disconnect",
            headers=member.headers,
        )
        assert mem_integ_disc.status_code == 403

        # Org owner CAN patch and disconnect
        owner_patch = client.patch(
            f"/api/v1/sources/{conn_id}",
            headers=owner.headers,
            json={"is_shared": True},
        )
        assert owner_patch.status_code == 200
        assert owner_patch.json()["is_shared"] is True

        # Cross-org outsider is denied (404)
        assert client.get(f"/api/v1/sources/{conn_id}", headers=outsider.headers).status_code == 404
        assert (
            client.post(f"/api/v1/sources/{conn_id}/disconnect", headers=outsider.headers).status_code
            == 404
        )

        # Org admin CAN disconnect
        admin_disc = client.post(f"/api/v1/sources/{conn_id}/disconnect", headers=admin.headers)
        assert admin_disc.status_code == 200
        assert admin_disc.json()["status"] == "disconnected"


def test_project_source_sync_least_privilege_and_duplicate_prevention(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify reviewer cannot enqueue sync jobs, contributor/manager can, and duplicates are rejected."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        owner = register_and_login_user(
            client, full_name="Sync Owner", email="sync.owner@example.com", password=_PASSWORD
        )
        reviewer = register_and_login_user(
            client, full_name="Sync Reviewer", email="sync.reviewer@example.com", password=_PASSWORD
        )
        contributor = register_and_login_user(
            client, full_name="Sync Contrib", email="sync.contrib@example.com", password=_PASSWORD
        )

        org_id = client.post(
            "/api/v1/organisations",
            headers=owner.headers,
            json={"name": "Sync Org", "slug": "sync-org"},
        ).json()["id"]
        proj_id = client.post(
            f"/api/v1/organisations/{org_id}/projects",
            headers=owner.headers,
            json={"name": "Sync Project", "slug": "sync-project", "status": "active"},
        ).json()["id"]

        for usr in (reviewer, contributor):
            _invite_accept(
                client,
                org_id=org_id,
                inviter_headers=owner.headers,
                invitee_email=usr.email,
                invitee_headers=usr.headers,
                role_name="org_member",
            )

        client.post(
            f"/api/v1/projects/{proj_id}/members",
            headers=owner.headers,
            json={"user_id": str(reviewer.user_id), "role_name": "reviewer"},
        )
        client.post(
            f"/api/v1/projects/{proj_id}/members",
            headers=owner.headers,
            json={"user_id": str(contributor.user_id), "role_name": "project_member"},
        )

        conn_id = client.post(
            f"/api/v1/organisations/{org_id}/sources",
            headers=owner.headers,
            json={
                "provider": "github",
                "account_identifier": "sync-org-gh",
                "secret_token": "ghp_SyncOwnerToken2026",
                "is_shared": True,
            },
        ).json()["id"]

        # Reviewer cannot map sources
        rev_map = client.post(
            f"/api/v1/projects/{proj_id}/sources/mappings",
            headers=reviewer.headers,
            json={"source_connection_id": conn_id, "external_resource_id": "sync/repo"},
        )
        assert rev_map.status_code == 403

        # Owner maps source
        map_res = client.post(
            f"/api/v1/projects/{proj_id}/sources/mappings",
            headers=owner.headers,
            json={"source_connection_id": conn_id, "external_resource_id": "sync/repo"},
        )
        assert map_res.status_code == 201
        mapping_id = map_res.json()["id"]

        # Reviewer CANNOT trigger sync and no job is enqueued
        rev_sync = client.post(
            f"/api/v1/projects/{proj_id}/sources/mappings/{mapping_id}/sync",
            headers=reviewer.headers,
        )
        assert rev_sync.status_code == 403

        with ctx.session_factory() as db:
            jobs = db.execute(select(BackgroundJob)).scalars().all()
            assert len(jobs) == 0

        # Project contributor CAN trigger sync
        contrib_sync = client.post(
            f"/api/v1/projects/{proj_id}/sources/mappings/{mapping_id}/sync",
            headers=contributor.headers,
        )
        assert contrib_sync.status_code == 202

        # Duplicate sync while queued is rejected (409 SYNC_ALREADY_ACTIVE)
        dup_sync = client.post(
            f"/api/v1/projects/{proj_id}/sources/mappings/{mapping_id}/sync",
            headers=owner.headers,
        )
        assert dup_sync.status_code == 409
        assert dup_sync.json()["error"]["code"] == "SYNC_ALREADY_ACTIVE"
