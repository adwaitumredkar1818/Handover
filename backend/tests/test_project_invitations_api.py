"""Comprehensive API tests for Project Invitations & Dual-Membership Integration (Phase 3).

Covers all 30 required test cases across:
- Creation (1-12)
- Listing (13-18)
- Revocation (19-26)
- Acceptance Compatibility (27-30)
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.models.enums import RoleName
from tests.conftest import (
    RegisteredUserSession,
    invite_and_accept_member,
    isolated_auth_app,
    register_and_login_user,
)


# =============================================================================
# Test Harness & Setup Fixtures
# =============================================================================

class ProjectApiHarness:
    """Convenience bundle of authenticated actors and project workspaces."""

    def __init__(
        self,
        client: TestClient,
        *,
        owner: RegisteredUserSession,
        admin: RegisteredUserSession,
        pm: RegisteredUserSession,
        member: RegisteredUserSession,
        reviewer: RegisteredUserSession,
        org_id: str,
        project_id: str,
    ) -> None:
        self.client = client
        self.owner = owner
        self.admin = admin
        self.pm = pm
        self.member = member
        self.reviewer = reviewer
        self.org_id = org_id
        self.project_id = project_id


def _setup_harness(client: TestClient) -> ProjectApiHarness:
    tag = uuid.uuid4().hex[:6]
    owner = register_and_login_user(client, email=f"owner_{tag}@org.com", full_name="Org Owner")
    admin = register_and_login_user(client, email=f"admin_{tag}@org.com", full_name="Org Admin")
    pm = register_and_login_user(client, email=f"pm_{tag}@org.com", full_name="Project Manager")
    member = register_and_login_user(client, email=f"member_{tag}@org.com", full_name="Project Member")
    reviewer = register_and_login_user(client, email=f"reviewer_{tag}@org.com", full_name="Project Reviewer")

    org_res = client.post(
        "/api/v1/organisations",
        headers=owner.headers,
        json={"name": f"Acme Tenant {tag}"},
    )
    assert org_res.status_code == 201
    org_id = org_res.json()["id"]

    # Add admin to org
    invite_and_accept_member(
        client,
        organisation_id=org_id,
        inviter_headers=owner.headers,
        invitee=admin,
        role_name="org_admin",
    )
    # Add PM, member, reviewer to org as org_member
    for u in (pm, member, reviewer):
        invite_and_accept_member(
            client,
            organisation_id=org_id,
            inviter_headers=owner.headers,
            invitee=u,
            role_name="org_member",
        )

    # Create project in organisation
    proj_res = client.post(
        f"/api/v1/organisations/{org_id}/projects",
        headers=owner.headers,
        json={"name": f"Project Alpha {tag}", "visibility": "private"},
    )
    assert proj_res.status_code == 201
    project_id = proj_res.json()["id"]

    # Assign PM, member, and reviewer to the project
    client.post(
        f"/api/v1/projects/{project_id}/members",
        headers=owner.headers,
        json={"user_id": str(pm.user_id), "role_name": "project_manager"},
    )
    client.post(
        f"/api/v1/projects/{project_id}/members",
        headers=owner.headers,
        json={"user_id": str(member.user_id), "role_name": "project_member"},
    )
    client.post(
        f"/api/v1/projects/{project_id}/members",
        headers=owner.headers,
        json={"user_id": str(reviewer.user_id), "role_name": "reviewer"},
    )

    return ProjectApiHarness(
        client=client,
        owner=owner,
        admin=admin,
        pm=pm,
        member=member,
        reviewer=reviewer,
        org_id=org_id,
        project_id=project_id,
    )


# =============================================================================
# PART 1: CREATION (Tests 1 - 12)
# =============================================================================

def test_1_project_manager_creates_project_invitation_successfully(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """1. Authenticated Project Manager creates a project invitation successfully."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        resp = client.post(
            f"/api/v1/organisations/{h.org_id}/projects/{h.project_id}/invitations",
            headers=h.pm.headers,
            json={"email": "candidate@example.com", "project_role_name": "project_member"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["invitation"]["email"] == "candidate@example.com"
        assert data["invitation"]["project_id"] == h.project_id
        assert data["invitation"]["project_role_name"] == "project_member"
        assert data["invitation"]["role_name"] == "org_member"
        assert data["invitation"]["status"] == "pending"
        assert data["invitation_delivery"] == "not_configured"
        assert data["development_invitation_token"] is not None


def test_2_project_member_forbidden_from_creating_invitations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """2. Regular Project Member is forbidden from creating invitations (403)."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        resp = client.post(
            f"/api/v1/organisations/{h.org_id}/projects/{h.project_id}/invitations",
            headers=h.member.headers,
            json={"email": "candidate@example.com", "project_role_name": "project_member"},
        )
        assert resp.status_code == 403


def test_3_reviewer_forbidden_from_creating_invitations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """3. Reviewer is forbidden from creating invitations (403)."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        resp = client.post(
            f"/api/v1/organisations/{h.org_id}/projects/{h.project_id}/invitations",
            headers=h.reviewer.headers,
            json={"email": "candidate@example.com", "project_role_name": "project_member"},
        )
        assert resp.status_code == 403


def test_4_org_owner_can_create_project_invitation_within_org(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """4. Organisation Owner can create an invitation within their organisation."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        resp = client.post(
            f"/api/v1/organisations/{h.org_id}/projects/{h.project_id}/invitations",
            headers=h.owner.headers,
            json={"email": "dev1@example.com", "project_role_name": "project_manager"},
        )
        assert resp.status_code == 201
        assert resp.json()["invitation"]["project_role_name"] == "project_manager"


def test_5_org_admin_can_create_project_invitation_within_org(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """5. Organisation Admin can create an invitation within their organisation."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        resp = client.post(
            f"/api/v1/organisations/{h.org_id}/projects/{h.project_id}/invitations",
            headers=h.admin.headers,
            json={"email": "dev2@example.com", "project_role_name": "reviewer"},
        )
        assert resp.status_code == 201
        assert resp.json()["invitation"]["project_role_name"] == "reviewer"


def test_6_org_owner_admin_cannot_use_override_in_another_organisation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """6. Organisation Owner/Admin cannot use their override in another organisation."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h1 = _setup_harness(client)
        h2 = _setup_harness(client)

        # Owner 1 attempts to invite into Organisation 2's project
        resp = client.post(
            f"/api/v1/organisations/{h2.org_id}/projects/{h2.project_id}/invitations",
            headers=h1.owner.headers,
            json={"email": "cross@example.com", "project_role_name": "project_member"},
        )
        assert resp.status_code in (403, 404)


def test_7_invalid_project_role_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """7. Invalid or non-project role is rejected (400 / 422)."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        resp = client.post(
            f"/api/v1/organisations/{h.org_id}/projects/{h.project_id}/invitations",
            headers=h.pm.headers,
            json={"email": "dev@example.com", "project_role_name": "org_admin"},
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "INVALID_ROLE_SCOPE"


def test_8_project_from_another_organisation_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """8. Project from another organisation is rejected with 404."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h1 = _setup_harness(client)
        h2 = _setup_harness(client)

        # Mismatch: org_id from h1, but project_id from h2
        resp = client.post(
            f"/api/v1/organisations/{h1.org_id}/projects/{h2.project_id}/invitations",
            headers=h1.owner.headers,
            json={"email": "candidate@example.com", "project_role_name": "project_member"},
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "PROJECT_NOT_FOUND"


def test_9_inactive_or_archived_project_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """9. Inactive or archived project is rejected (409 PROJECT_ARCHIVED)."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        # Archive the project
        arch_res = client.post(
            f"/api/v1/projects/{h.project_id}/archive",
            headers=h.owner.headers,
        )
        assert arch_res.status_code == 200

        # Attempt to issue invitation
        resp = client.post(
            f"/api/v1/organisations/{h.org_id}/projects/{h.project_id}/invitations",
            headers=h.owner.headers,
            json={"email": "archived@example.com", "project_role_name": "project_member"},
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "PROJECT_ARCHIVED"


def test_10_duplicate_pending_invitation_returns_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """10. Duplicate pending invitation for the same email and project returns 409."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        # First invitation succeeds
        res1 = client.post(
            f"/api/v1/organisations/{h.org_id}/projects/{h.project_id}/invitations",
            headers=h.pm.headers,
            json={"email": "dup@example.com", "project_role_name": "project_member"},
        )
        assert res1.status_code == 201

        # Second invitation returns 409
        res2 = client.post(
            f"/api/v1/organisations/{h.org_id}/projects/{h.project_id}/invitations",
            headers=h.pm.headers,
            json={"email": "dup@example.com", "project_role_name": "project_member"},
        )
        assert res2.status_code == 409
        assert res2.json()["error"]["code"] == "INVITATION_ALREADY_EXISTS"


def test_11_existing_active_project_member_cannot_be_invited_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """11. Existing active project member cannot be invited again (409)."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        resp = client.post(
            f"/api/v1/organisations/{h.org_id}/projects/{h.project_id}/invitations",
            headers=h.pm.headers,
            json={"email": h.member.email, "project_role_name": "project_member"},
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "MEMBERSHIP_ALREADY_EXISTS"


def test_12_unauthenticated_caller_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """12. Unauthenticated caller is rejected with 401."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        resp = client.post(
            f"/api/v1/organisations/{h.org_id}/projects/{h.project_id}/invitations",
            json={"email": "anon@example.com", "project_role_name": "project_member"},
        )
        assert resp.status_code == 401


# =============================================================================
# PART 2: LISTING (Tests 13 - 18)
# =============================================================================

def test_13_authorised_project_manager_can_list_project_invitations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """13. Authorised Project Manager can list project invitations."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        client.post(
            f"/api/v1/organisations/{h.org_id}/projects/{h.project_id}/invitations",
            headers=h.pm.headers,
            json={"email": "list1@example.com", "project_role_name": "project_member"},
        )
        resp = client.get(
            f"/api/v1/organisations/{h.org_id}/projects/{h.project_id}/invitations",
            headers=h.pm.headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert any(item["email"] == "list1@example.com" for item in data["items"])


def test_14_org_owner_and_admin_can_list_project_invitations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """14. Organisation Owner/Admin can list invitations within their organisation."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        client.post(
            f"/api/v1/organisations/{h.org_id}/projects/{h.project_id}/invitations",
            headers=h.pm.headers,
            json={"email": "list2@example.com", "project_role_name": "project_member"},
        )
        # Org Owner can list
        resp_owner = client.get(
            f"/api/v1/organisations/{h.org_id}/projects/{h.project_id}/invitations",
            headers=h.owner.headers,
        )
        assert resp_owner.status_code == 200
        # Org Admin can list
        resp_admin = client.get(
            f"/api/v1/organisations/{h.org_id}/projects/{h.project_id}/invitations",
            headers=h.admin.headers,
        )
        assert resp_admin.status_code == 200


def test_15_project_member_and_reviewer_cannot_list_project_invitations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """15. Project Member and Reviewer cannot list project invitations (403)."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        resp_member = client.get(
            f"/api/v1/organisations/{h.org_id}/projects/{h.project_id}/invitations",
            headers=h.member.headers,
        )
        assert resp_member.status_code == 403

        resp_rev = client.get(
            f"/api/v1/organisations/{h.org_id}/projects/{h.project_id}/invitations",
            headers=h.reviewer.headers,
        )
        assert resp_rev.status_code == 403


def test_16_invitations_from_another_project_never_returned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """16. Invitations from Project A are never returned when listing Project B."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        # Create second project in same organisation
        proj2_res = client.post(
            f"/api/v1/organisations/{h.org_id}/projects",
            headers=h.owner.headers,
            json={"name": "Project Beta", "visibility": "private"},
        )
        proj2_id = proj2_res.json()["id"]

        # Invite into Project 1
        client.post(
            f"/api/v1/organisations/{h.org_id}/projects/{h.project_id}/invitations",
            headers=h.owner.headers,
            json={"email": "only_proj1@example.com", "project_role_name": "project_member"},
        )
        # Invite into Project 2
        client.post(
            f"/api/v1/organisations/{h.org_id}/projects/{proj2_id}/invitations",
            headers=h.owner.headers,
            json={"email": "only_proj2@example.com", "project_role_name": "project_member"},
        )

        # List Project 1
        res1 = client.get(
            f"/api/v1/organisations/{h.org_id}/projects/{h.project_id}/invitations",
            headers=h.owner.headers,
        )
        items1 = [it["email"] for it in res1.json()["items"]]
        assert "only_proj1@example.com" in items1
        assert "only_proj2@example.com" not in items1

        # List Project 2
        res2 = client.get(
            f"/api/v1/organisations/{h.org_id}/projects/{proj2_id}/invitations",
            headers=h.owner.headers,
        )
        items2 = [it["email"] for it in res2.json()["items"]]
        assert "only_proj2@example.com" in items2
        assert "only_proj1@example.com" not in items2


def test_17_invitation_list_does_not_expose_raw_tokens_or_hashes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """17. Invitation list endpoint does not expose raw tokens or token hashes."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        client.post(
            f"/api/v1/organisations/{h.org_id}/projects/{h.project_id}/invitations",
            headers=h.pm.headers,
            json={"email": "notoken@example.com", "project_role_name": "project_member"},
        )
        resp = client.get(
            f"/api/v1/organisations/{h.org_id}/projects/{h.project_id}/invitations",
            headers=h.pm.headers,
        )
        assert resp.status_code == 200
        for item in resp.json()["items"]:
            assert "token" not in item
            assert "raw_token" not in item
            assert "token_hash" not in item
            assert "development_invitation_token" not in item


def test_18_pagination_and_status_filters_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """18. Pagination (limit, offset) and status filtering work as expected."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        for i in range(3):
            client.post(
                f"/api/v1/organisations/{h.org_id}/projects/{h.project_id}/invitations",
                headers=h.pm.headers,
                json={"email": f"page_{i}@example.com", "project_role_name": "project_member"},
            )

        resp = client.get(
            f"/api/v1/organisations/{h.org_id}/projects/{h.project_id}/invitations?limit=2&offset=0",
            headers=h.pm.headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["total"] == 3

        # Filter by pending status
        resp_pending = client.get(
            f"/api/v1/organisations/{h.org_id}/projects/{h.project_id}/invitations?status=pending",
            headers=h.pm.headers,
        )
        assert resp_pending.status_code == 200
        assert all(it["status"] == "pending" for it in resp_pending.json()["items"])


# =============================================================================
# PART 3: REVOCATION (Tests 19 - 26)
# =============================================================================

def test_19_authorised_project_manager_can_revoke_pending_invitation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """19. Authorised Project Manager can revoke a pending invitation."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        create_res = client.post(
            f"/api/v1/organisations/{h.org_id}/projects/{h.project_id}/invitations",
            headers=h.pm.headers,
            json={"email": "rev1@example.com", "project_role_name": "project_member"},
        )
        inv_id = create_res.json()["invitation"]["id"]

        del_res = client.delete(
            f"/api/v1/organisations/{h.org_id}/projects/{h.project_id}/invitations/{inv_id}",
            headers=h.pm.headers,
        )
        assert del_res.status_code == 200
        assert del_res.json()["status"] == "revoked"


def test_20_org_owner_and_admin_can_revoke_project_invitation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """20. Organisation Owner/Admin can revoke invitations within their organisation."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        # Create invitation as PM
        create_res = client.post(
            f"/api/v1/organisations/{h.org_id}/projects/{h.project_id}/invitations",
            headers=h.pm.headers,
            json={"email": "rev2@example.com", "project_role_name": "project_member"},
        )
        inv_id = create_res.json()["invitation"]["id"]

        # Org Owner can revoke
        del_res = client.delete(
            f"/api/v1/organisations/{h.org_id}/projects/{h.project_id}/invitations/{inv_id}",
            headers=h.owner.headers,
        )
        assert del_res.status_code == 200
        assert del_res.json()["status"] == "revoked"


def test_21_unauthorised_project_member_cannot_revoke_invitation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """21. Unauthorised Project Member cannot revoke an invitation (403)."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        create_res = client.post(
            f"/api/v1/organisations/{h.org_id}/projects/{h.project_id}/invitations",
            headers=h.pm.headers,
            json={"email": "rev3@example.com", "project_role_name": "project_member"},
        )
        inv_id = create_res.json()["invitation"]["id"]

        del_res = client.delete(
            f"/api/v1/organisations/{h.org_id}/projects/{h.project_id}/invitations/{inv_id}",
            headers=h.member.headers,
        )
        assert del_res.status_code == 403


def test_22_invitation_belonging_to_another_project_cannot_be_revoked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """22. Invitation belonging to Project A cannot be revoked through Project B route (404)."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        # Create project 2
        proj2_id = client.post(
            f"/api/v1/organisations/{h.org_id}/projects",
            headers=h.owner.headers,
            json={"name": "Project 2", "visibility": "private"},
        ).json()["id"]

        # Create invitation in Project 1
        inv1_id = client.post(
            f"/api/v1/organisations/{h.org_id}/projects/{h.project_id}/invitations",
            headers=h.owner.headers,
            json={"email": "cross_proj@example.com", "project_role_name": "project_member"},
        ).json()["invitation"]["id"]

        # Attempt to revoke through Project 2's route
        del_res = client.delete(
            f"/api/v1/organisations/{h.org_id}/projects/{proj2_id}/invitations/{inv1_id}",
            headers=h.owner.headers,
        )
        assert del_res.status_code == 404
        assert del_res.json()["error"]["code"] == "INVITATION_NOT_FOUND"


def test_23_invitation_belonging_to_another_organisation_cannot_be_revoked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """23. Invitation belonging to another organisation cannot be revoked (404)."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h1 = _setup_harness(client)
        h2 = _setup_harness(client)

        inv1_id = client.post(
            f"/api/v1/organisations/{h1.org_id}/projects/{h1.project_id}/invitations",
            headers=h1.owner.headers,
            json={"email": "cross_org@example.com", "project_role_name": "project_member"},
        ).json()["invitation"]["id"]

        # Attempt to revoke from Org 2
        del_res = client.delete(
            f"/api/v1/organisations/{h2.org_id}/projects/{h1.project_id}/invitations/{inv1_id}",
            headers=h2.owner.headers,
        )
        assert del_res.status_code in (403, 404)


def test_24_accepted_invitation_cannot_be_revoked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """24. Accepted invitation cannot be revoked (409 Conflict)."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        newbie = register_and_login_user(client, email="newbie@example.com", full_name="Newbie")

        create_res = client.post(
            f"/api/v1/organisations/{h.org_id}/projects/{h.project_id}/invitations",
            headers=h.pm.headers,
            json={"email": "newbie@example.com", "project_role_name": "project_member"},
        )
        token = create_res.json()["development_invitation_token"]
        inv_id = create_res.json()["invitation"]["id"]

        # Accept invitation
        client.post(f"/api/v1/invitations/{token}/accept", headers=newbie.headers)

        # Attempt to revoke already accepted invitation
        del_res = client.delete(
            f"/api/v1/organisations/{h.org_id}/projects/{h.project_id}/invitations/{inv_id}",
            headers=h.pm.headers,
        )
        assert del_res.status_code == 409
        assert del_res.json()["error"]["code"] == "INVITATION_ALREADY_ACCEPTED"


def test_25_revocation_does_not_remove_organisation_membership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """25. Revoking a project invitation never removes an existing organisation membership."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        # Member is already in the organisation
        create_res = client.post(
            f"/api/v1/organisations/{h.org_id}/projects/{h.project_id}/invitations",
            headers=h.owner.headers,
            json={"email": "candidate_ext@example.com", "project_role_name": "reviewer"},
        )
        inv_id = create_res.json()["invitation"]["id"]

        # Revoke invitation
        client.delete(
            f"/api/v1/organisations/{h.org_id}/projects/{h.project_id}/invitations/{inv_id}",
            headers=h.owner.headers,
        )

        # Confirm Org members list still has all 5 members intact
        org_members = client.get(
            f"/api/v1/organisations/{h.org_id}/members",
            headers=h.owner.headers,
        )
        assert org_members.status_code == 200
        assert org_members.json()["total"] >= 5


def test_26_repeated_revocation_returns_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """26. Repeated revocation of already-revoked invitation returns 409 Conflict."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        create_res = client.post(
            f"/api/v1/organisations/{h.org_id}/projects/{h.project_id}/invitations",
            headers=h.pm.headers,
            json={"email": "repeat_rev@example.com", "project_role_name": "project_member"},
        )
        inv_id = create_res.json()["invitation"]["id"]

        # First revocation succeeds
        del1 = client.delete(
            f"/api/v1/organisations/{h.org_id}/projects/{h.project_id}/invitations/{inv_id}",
            headers=h.pm.headers,
        )
        assert del1.status_code == 200

        # Second revocation returns 409 INVITATION_REVOKED
        del2 = client.delete(
            f"/api/v1/organisations/{h.org_id}/projects/{h.project_id}/invitations/{inv_id}",
            headers=h.pm.headers,
        )
        assert del2.status_code == 409
        assert del2.json()["error"]["code"] == "INVITATION_REVOKED"


# =============================================================================
# PART 4: ACCEPTANCE COMPATIBILITY (Tests 27 - 30)
# =============================================================================

def test_27_existing_organisation_only_invitation_acceptance_still_works(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """27. Existing organisation-only invitation acceptance still functions via /invitations/{token}/accept."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        user = register_and_login_user(client, email="orgonly_api@example.com", full_name="Org Only")

        create_res = client.post(
            f"/api/v1/organisations/{h.org_id}/invitations",
            headers=h.owner.headers,
            json={"email": "orgonly_api@example.com", "role_name": "org_member"},
        )
        token = create_res.json()["development_invitation_token"]
        assert token is not None

        accept_res = client.post(
            f"/api/v1/invitations/{token}/accept",
            headers=user.headers,
        )
        assert accept_res.status_code == 200
        data = accept_res.json()
        assert data["organisation_id"] == h.org_id
        assert data["role_name"] == "org_member"
        assert data["project_id"] is None
        assert data["project_name"] is None
        assert data["project_role_name"] is None
        assert data["is_new_organisation_member"] is True


def test_28_project_invitation_acceptance_creates_dual_memberships_and_returns_attribution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """28. Project invitation acceptance creates dual memberships and returns project attribution fields."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        user = register_and_login_user(client, email="dual_api@example.com", full_name="Dual User")

        # Create project invitation
        create_res = client.post(
            f"/api/v1/organisations/{h.org_id}/projects/{h.project_id}/invitations",
            headers=h.pm.headers,
            json={"email": "dual_api@example.com", "project_role_name": "reviewer"},
        )
        token = create_res.json()["development_invitation_token"]
        assert token is not None

        # Accept project invitation via canonical acceptance route
        accept_res = client.post(
            f"/api/v1/invitations/{token}/accept",
            headers=user.headers,
        )
        assert accept_res.status_code == 200
        data = accept_res.json()

        # Attribution fields populated
        assert data["organisation_id"] == h.org_id
        assert data["is_new_organisation_member"] is True
        assert data["role_name"] == "org_member"
        assert data["project_id"] == h.project_id
        assert data["project_role_name"] == "reviewer"
        assert data["project_membership_status"] == "active"
        assert data["project_name"] is not None

        # Verify actual active project and organisation memberships via API
        proj_detail = client.get(
            f"/api/v1/projects/{h.project_id}",
            headers=user.headers,
        )
        assert proj_detail.status_code == 200
        assert proj_detail.json()["my_project_role"] == "reviewer"


def test_29_project_invitation_acceptance_for_existing_org_member_reuses_membership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """29. Project invitation acceptance for user who already belongs to org reuses existing org membership."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        user = register_and_login_user(client, email="existing_org_user@example.com", full_name="Existing Org User")

        # First invite user to org and accept
        org_inv_res = client.post(
            f"/api/v1/organisations/{h.org_id}/invitations",
            headers=h.owner.headers,
            json={"email": "existing_org_user@example.com", "role_name": "org_member"},
        )
        org_token = org_inv_res.json()["development_invitation_token"]
        client.post(f"/api/v1/invitations/{org_token}/accept", headers=user.headers)

        # Now invite to project
        proj_inv_res = client.post(
            f"/api/v1/organisations/{h.org_id}/projects/{h.project_id}/invitations",
            headers=h.pm.headers,
            json={"email": "existing_org_user@example.com", "project_role_name": "project_member"},
        )
        proj_token = proj_inv_res.json()["development_invitation_token"]

        # Accept project invitation
        accept_res = client.post(
            f"/api/v1/invitations/{proj_token}/accept",
            headers=user.headers,
        )
        assert accept_res.status_code == 200
        data = accept_res.json()

        # Should indicate existing org membership was reused
        assert data["organisation_id"] == h.org_id
        assert data["is_new_organisation_member"] is False
        assert data["role_name"] == "org_member"
        assert data["project_id"] == h.project_id
        assert data["project_role_name"] == "project_member"
        assert data["project_membership_status"] == "active"


def test_30_raw_token_and_token_hash_never_exposed_in_invitation_responses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """30. Raw token and token hash are never exposed in listing or summary schemas."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        create_res = client.post(
            f"/api/v1/organisations/{h.org_id}/projects/{h.project_id}/invitations",
            headers=h.pm.headers,
            json={"email": "audit_token@example.com", "project_role_name": "project_member"},
        )
        assert create_res.status_code == 201
        create_data = create_res.json()

        # Token hash is never returned
        assert "token_hash" not in create_data
        assert "token_hash" not in create_data["invitation"]

        # List invitations
        list_res = client.get(
            f"/api/v1/organisations/{h.org_id}/projects/{h.project_id}/invitations",
            headers=h.pm.headers,
        )
        assert list_res.status_code == 200
        for item in list_res.json()["items"]:
            assert "token" not in item
            assert "raw_token" not in item
            assert "token_hash" not in item
            assert "development_invitation_token" not in item
