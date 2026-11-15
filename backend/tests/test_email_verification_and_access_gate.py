"""Comprehensive Verification & Gate Integration Tests for Email Verification Policy (Phase 4.1).

Covers all 12 test scenarios mandated by Section 7:
1. Unverified invited user cannot access project resources.
2. Unverified invited user cannot access organisation resources requiring membership.
3. Unverified invited user cannot bypass restriction through another project API.
4. Valid email verification enables intended access.
5. Verification retry works safely.
6. Failed verification does not grant access.
7. Invitation cannot be consumed by a different account.
8. Existing verified users retain access.
9. Normal registration behaviour remains compatible.
10. Existing organisation-only invitation acceptance remains functional.
11. Existing project invitation acceptance remains functional.
12. RBAC and tenant-isolation tests remain passing.
"""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.security import ensure_utc, generate_email_verification_token, hash_opaque_token, utc_now
from app.models.enums import RoleName, UserStatus
from app.models.organisation import Organisation, OrganisationInvitation, OrganisationMembership
from app.models.project import Project, ProjectMembership
from app.models.user import User
from tests.conftest import (
    RegisteredUserSession,
    isolated_auth_app,
    register_and_login_user,
)

_STRONG_PASSWORD = "StrongSecurePassword2026!"


# =============================================================================
# Test Harness & Helpers
# =============================================================================

class GateTestHarness:
    """Convenience bundle of verified tenant owner, PM, workspace, and invitation generator."""

    def __init__(
        self,
        client: TestClient,
        *,
        owner: RegisteredUserSession,
        pm: RegisteredUserSession,
        org_id: str,
        project_id: str,
    ) -> None:
        self.client = client
        self.owner = owner
        self.pm = pm
        self.org_id = org_id
        self.project_id = project_id

    def create_project_invitation(
        self,
        email: str,
        project_role_name: str = "reviewer",
    ) -> tuple[str, str]:
        """Create a project invitation and return (invitation_id, raw_token)."""
        res = self.client.post(
            f"/api/v1/organisations/{self.org_id}/projects/{self.project_id}/invitations",
            headers=self.pm.headers,
            json={"email": email, "project_role_name": project_role_name},
        )
        assert res.status_code == 201, res.text
        data = res.json()
        return data["invitation"]["id"], data["development_invitation_token"]

    def create_org_invitation(
        self,
        email: str,
        role_name: str = "org_member",
    ) -> tuple[str, str]:
        """Create an organisation-only invitation and return (invitation_id, raw_token)."""
        res = self.client.post(
            f"/api/v1/organisations/{self.org_id}/invitations",
            headers=self.owner.headers,
            json={"email": email, "role_name": role_name},
        )
        assert res.status_code == 201, res.text
        data = res.json()
        return data["invitation"]["id"], data["development_invitation_token"]


def _setup_gate_harness(client: TestClient) -> GateTestHarness:
    tag = uuid.uuid4().hex[:6]
    owner = register_and_login_user(client, email=f"owner_{tag}@org.com", full_name="Org Owner", verified=True)
    pm = register_and_login_user(client, email=f"pm_{tag}@org.com", full_name="Project Manager", verified=True)

    org_res = client.post(
        "/api/v1/organisations",
        headers=owner.headers,
        json={"name": f"Acme Gate {tag}"},
    )
    assert org_res.status_code == 201
    org_id = org_res.json()["id"]

    # Invite and accept PM into org
    pm_inv_res = client.post(
        f"/api/v1/organisations/{org_id}/invitations",
        headers=owner.headers,
        json={"email": pm.email, "role_name": "org_member"},
    )
    assert pm_inv_res.status_code == 201
    pm_token = pm_inv_res.json()["development_invitation_token"]
    accept_pm = client.post(f"/api/v1/invitations/{pm_token}/accept", headers=pm.headers)
    assert accept_pm.status_code == 200

    proj_res = client.post(
        f"/api/v1/organisations/{org_id}/projects",
        headers=owner.headers,
        json={"name": f"Project Gate {tag}", "visibility": "private"},
    )
    assert proj_res.status_code == 201
    project_id = proj_res.json()["id"]

    # Assign PM to the project
    client.post(
        f"/api/v1/projects/{project_id}/members",
        headers=owner.headers,
        json={"user_id": str(pm.user_id), "role_name": "project_manager"},
    )

    return GateTestHarness(
        client=client,
        owner=owner,
        pm=pm,
        org_id=org_id,
        project_id=project_id,
    )


# =============================================================================
# SCENARIOS 1 - 12
# =============================================================================

def test_1_unverified_invited_user_cannot_access_project_resources(monkeypatch: pytest.MonkeyPatch) -> None:
    """1. An unverified invited user cannot access project resources."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_gate_harness(client)
        email = "unverified_project_access@example.com"
        _, raw_token = h.create_project_invitation(email, project_role_name="reviewer")

        reg_res = client.post(
            "/api/v1/auth/register-with-invitation",
            json={"invitation_token": raw_token, "full_name": "Unverified User", "password": _STRONG_PASSWORD},
        )
        assert reg_res.status_code == 201
        reg_data = reg_res.json()
        assert reg_data["user"]["is_email_verified"] is False
        assert reg_data["can_access_project_immediately"] is False

        # Authenticate and obtain JWT access token
        login_res = client.post("/api/v1/auth/login", json={"email": email, "password": _STRONG_PASSWORD})
        assert login_res.status_code == 200
        headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

        # Attempt project access -> FAIL CLOSED with 403 EMAIL_VERIFICATION_REQUIRED
        proj_res = client.get(f"/api/v1/projects/{h.project_id}", headers=headers)
        assert proj_res.status_code == 403
        assert proj_res.json()["error"]["code"] == "EMAIL_VERIFICATION_REQUIRED"


def test_2_unverified_invited_user_cannot_access_organisation_resources_requiring_membership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """2. An unverified invited user cannot access organisation resources requiring membership."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_gate_harness(client)
        email = "unverified_org_access@example.com"
        _, raw_token = h.create_project_invitation(email, project_role_name="reviewer")

        client.post(
            "/api/v1/auth/register-with-invitation",
            json={"invitation_token": raw_token, "full_name": "Unverified User 2", "password": _STRONG_PASSWORD},
        )
        login_res = client.post("/api/v1/auth/login", json={"email": email, "password": _STRONG_PASSWORD})
        headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

        # Attempt organisation endpoints -> FAIL CLOSED with 403 EMAIL_VERIFICATION_REQUIRED
        list_orgs_res = client.get("/api/v1/organisations", headers=headers)
        assert list_orgs_res.status_code == 403
        assert list_orgs_res.json()["error"]["code"] == "EMAIL_VERIFICATION_REQUIRED"

        org_res = client.get(f"/api/v1/organisations/{h.org_id}", headers=headers)
        assert org_res.status_code == 403
        assert org_res.json()["error"]["code"] == "EMAIL_VERIFICATION_REQUIRED"

        members_res = client.get(f"/api/v1/organisations/{h.org_id}/members", headers=headers)
        assert members_res.status_code == 403
        assert members_res.json()["error"]["code"] == "EMAIL_VERIFICATION_REQUIRED"

        # Attempt organisation creation -> FAIL CLOSED with 403 EMAIL_VERIFICATION_REQUIRED
        create_org_res = client.post("/api/v1/organisations", headers=headers, json={"name": "Attacker Org"})
        assert create_org_res.status_code == 403
        assert create_org_res.json()["error"]["code"] == "EMAIL_VERIFICATION_REQUIRED"


def test_3_unverified_invited_user_cannot_bypass_restriction_through_another_project_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """3. An unverified invited user cannot bypass restriction through alternate project APIs."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_gate_harness(client)
        email = "unverified_bypass_test@example.com"
        _, raw_token = h.create_project_invitation(email, project_role_name="reviewer")

        client.post(
            "/api/v1/auth/register-with-invitation",
            json={"invitation_token": raw_token, "full_name": "Bypass Tester", "password": _STRONG_PASSWORD},
        )
        login_res = client.post("/api/v1/auth/login", json={"email": email, "password": _STRONG_PASSWORD})
        headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

        # Attempt various project endpoints across different capabilities
        endpoints = [
            f"/api/v1/projects/{h.project_id}",
            f"/api/v1/projects/{h.project_id}/overview",
            f"/api/v1/projects/{h.project_id}/activity",
            f"/api/v1/projects/{h.project_id}/members",
            f"/api/v1/projects/{h.project_id}/transition",
            f"/api/v1/organisations/{h.org_id}/projects/{h.project_id}/invitations",
            f"/api/v1/projects/{h.project_id}/evidence",
            f"/api/v1/projects/{h.project_id}/evidence/metrics",
        ]
        for ep in endpoints:
            res = client.get(ep, headers=headers)
            assert res.status_code == 403, f"Endpoint {ep} unexpectedly allowed access ({res.status_code})"
            assert res.json()["error"]["code"] == "EMAIL_VERIFICATION_REQUIRED"


def test_4_valid_email_verification_enables_intended_access(monkeypatch: pytest.MonkeyPatch) -> None:
    """4. Valid email verification enables the intended organisation and project access."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_gate_harness(client)
        email = "verif_activation_test@example.com"
        _, raw_token = h.create_project_invitation(email, project_role_name="reviewer")

        reg_res = client.post(
            "/api/v1/auth/register-with-invitation",
            json={"invitation_token": raw_token, "full_name": "Activation Tester", "password": _STRONG_PASSWORD},
        )
        assert reg_res.status_code == 201
        verif_token = reg_res.json()["development_verification_token"]
        assert verif_token is not None

        login_res = client.post("/api/v1/auth/login", json={"email": email, "password": _STRONG_PASSWORD})
        headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

        # Pre-verification: access is blocked
        assert client.get(f"/api/v1/projects/{h.project_id}", headers=headers).status_code == 403

        # Verify email using the signed token
        ver_res = client.post("/api/v1/auth/verify-email", json={"token": verif_token})
        assert ver_res.status_code == 200
        ver_data = ver_res.json()
        assert ver_data["is_email_verified"] is True
        assert ver_data["can_access_project_immediately"] is True

        # Post-verification: project access immediately succeeds
        proj_res = client.get(f"/api/v1/projects/{h.project_id}", headers=headers)
        assert proj_res.status_code == 200
        assert proj_res.json()["my_project_role"] == "reviewer"

        # Organisation access also immediately succeeds
        org_res = client.get(f"/api/v1/organisations/{h.org_id}", headers=headers)
        assert org_res.status_code == 200
        assert org_res.json()["my_role"] == "org_member"


def test_5_verification_retry_works_safely(monkeypatch: pytest.MonkeyPatch) -> None:
    """5. Verification retry works safely and requesting verification link again is idempotent."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_gate_harness(client)
        email = "retry_verification_test@example.com"
        _, raw_token = h.create_project_invitation(email)

        reg_res = client.post(
            "/api/v1/auth/register-with-invitation",
            json={"invitation_token": raw_token, "full_name": "Retry User", "password": _STRONG_PASSWORD},
        )
        assert reg_res.status_code == 201
        first_token = reg_res.json()["development_verification_token"]

        # Request fresh verification token
        req_res = client.post("/api/v1/auth/request-email-verification", json={"email": email})
        assert req_res.status_code == 200
        second_token = req_res.json()["development_verification_token"]
        assert second_token is not None

        # Verify with second token
        v1 = client.post("/api/v1/auth/verify-email", json={"token": second_token})
        assert v1.status_code == 200
        assert v1.json()["is_email_verified"] is True

        # Idempotent retry on already-verified user
        v2 = client.post("/api/v1/auth/verify-email", json={"token": second_token})
        assert v2.status_code == 200
        assert "already verified" in v2.json()["message"].lower()

        # Requesting verification again after account is verified returns safe response
        req_again = client.post("/api/v1/auth/request-email-verification", json={"email": email})
        assert req_again.status_code == 200
        assert "already verified" in req_again.json()["message"].lower()


def test_6_failed_verification_does_not_grant_access(monkeypatch: pytest.MonkeyPatch) -> None:
    """6. Failed verification (invalid or expired token) does not grant access."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_gate_harness(client)
        email = "failed_verif_test@example.com"
        _, raw_token = h.create_project_invitation(email)

        client.post(
            "/api/v1/auth/register-with-invitation",
            json={"invitation_token": raw_token, "full_name": "Failed Verif User", "password": _STRONG_PASSWORD},
        )
        login_res = client.post("/api/v1/auth/login", json={"email": email, "password": _STRONG_PASSWORD})
        headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

        # Attempt verification with malformed token
        bad_res = client.post("/api/v1/auth/verify-email", json={"token": "completely_invalid_garbage_token"})
        assert bad_res.status_code == 400
        assert bad_res.json()["error"]["code"] == "INVALID_VERIFICATION_TOKEN"

        # User is still unverified and blocked
        assert client.get(f"/api/v1/projects/{h.project_id}", headers=headers).status_code == 403


def test_7_invitation_cannot_be_consumed_by_different_account(monkeypatch: pytest.MonkeyPatch) -> None:
    """7. An invitation consumed by an unverified registration cannot be consumed by a different account."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_gate_harness(client)
        email = "target_consumer@example.com"
        _, raw_token = h.create_project_invitation(email)

        # First registration consumes the invitation
        reg_res = client.post(
            "/api/v1/auth/register-with-invitation",
            json={"invitation_token": raw_token, "full_name": "Target Consumer", "password": _STRONG_PASSWORD},
        )
        assert reg_res.status_code == 201

        # A different account attempts to use the same invitation token
        hacker = register_and_login_user(client, email="attacker@example.com", full_name="Attacker", verified=True)
        accept_res = client.post(f"/api/v1/invitations/{raw_token}/accept", headers=hacker.headers)
        assert accept_res.status_code in (400, 403, 409)

        # Another registration attempt with the token is also rejected
        reg_dup = client.post(
            "/api/v1/auth/register-with-invitation",
            json={"invitation_token": raw_token, "full_name": "Impostor", "password": _STRONG_PASSWORD},
        )
        assert reg_dup.status_code == 409


def test_8_existing_verified_users_retain_access(monkeypatch: pytest.MonkeyPatch) -> None:
    """8. Existing verified users retain access and can query projects immediately."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_gate_harness(client)
        # Owner and PM were registered with verified=True
        owner_proj = client.get(f"/api/v1/projects/{h.project_id}", headers=h.owner.headers)
        assert owner_proj.status_code == 200

        pm_proj = client.get(f"/api/v1/projects/{h.project_id}", headers=h.pm.headers)
        assert pm_proj.status_code == 200
        assert pm_proj.json()["my_project_role"] == "project_manager"


def test_9_normal_registration_behaviour_remains_compatible(monkeypatch: pytest.MonkeyPatch) -> None:
    """9. Normal registration without invitation remains compatible and can be verified."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        email = "normal_compat_user@example.com"
        reg_res = client.post(
            "/api/v1/auth/register",
            json={"full_name": "Normal Compat", "email": email, "password": _STRONG_PASSWORD},
        )
        assert reg_res.status_code == 201
        reg_data = reg_res.json()
        assert reg_data["user"]["is_email_verified"] is False
        assert reg_data["email_verification_required"] is True
        token = reg_data["development_verification_token"]
        assert token is not None

        # Verify email
        ver = client.post("/api/v1/auth/verify-email", json={"token": token})
        assert ver.status_code == 200
        assert ver.json()["is_email_verified"] is True


def test_10_existing_organisation_only_invitation_acceptance_remains_functional(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """10. Existing organisation-only invitations register users safely and gate access until verified."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_gate_harness(client)
        email = "org_only_gate_user@example.com"
        _, raw_token = h.create_org_invitation(email, role_name="org_member")

        reg_res = client.post(
            "/api/v1/auth/register-with-invitation",
            json={"invitation_token": raw_token, "full_name": "Org Only User", "password": _STRONG_PASSWORD},
        )
        assert reg_res.status_code == 201
        data = reg_res.json()
        assert data["project_id"] is None
        token = data["development_verification_token"]

        login_res = client.post("/api/v1/auth/login", json={"email": email, "password": _STRONG_PASSWORD})
        headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

        # Blocked before verification
        assert client.get(f"/api/v1/organisations/{h.org_id}", headers=headers).status_code == 403

        # Verify email
        client.post("/api/v1/auth/verify-email", json={"token": token})

        # Accessible after verification
        assert client.get(f"/api/v1/organisations/{h.org_id}", headers=headers).status_code == 200


def test_11_existing_project_invitation_acceptance_remains_functional(monkeypatch: pytest.MonkeyPatch) -> None:
    """11. An already verified existing user accepting via /api/v1/invitations/{token}/accept accesses project immediately."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_gate_harness(client)
        existing_email = "verified_existing_member@example.com"
        existing_user = register_and_login_user(
            client, email=existing_email, full_name="Verified Existing", verified=True
        )

        _, raw_token = h.create_project_invitation(existing_email, project_role_name="reviewer")

        # Accept invitation as authenticated user
        accept_res = client.post(f"/api/v1/invitations/{raw_token}/accept", headers=existing_user.headers)
        assert accept_res.status_code == 200
        assert accept_res.json()["project_role_name"] == "reviewer"

        # Immediate project access is granted because user is already verified
        proj_res = client.get(f"/api/v1/projects/{h.project_id}", headers=existing_user.headers)
        assert proj_res.status_code == 200
        assert proj_res.json()["my_project_role"] == "reviewer"


def test_12_rbac_and_tenant_isolation_tests_remain_passing(monkeypatch: pytest.MonkeyPatch) -> None:
    """12. Verified users still respect strict RBAC and tenant isolation boundaries."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_gate_harness(client)

        # Create another isolated organization and project
        other_owner = register_and_login_user(
            client, email="other_org_owner@example.com", full_name="Other Owner", verified=True
        )
        other_org_res = client.post(
            "/api/v1/organisations",
            headers=other_owner.headers,
            json={"name": "Foreign Org"},
        )
        other_org_id = other_org_res.json()["id"]

        other_proj_res = client.post(
            f"/api/v1/organisations/{other_org_id}/projects",
            headers=other_owner.headers,
            json={"name": "Foreign Project", "visibility": "private"},
        )
        other_proj_id = other_proj_res.json()["id"]

        # PM from Org 1 attempts to access Org 2's project -> strictly 404/403 TENANT ISOLATION
        cross_res = client.get(f"/api/v1/projects/{other_proj_id}", headers=h.pm.headers)
        assert cross_res.status_code == 404
        assert cross_res.json()["error"]["code"] == "PROJECT_NOT_FOUND"


def test_13_suspended_user_verification_does_not_reactivate_account_and_access_remains_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """13. A disabled account completing email verification does not regain active status or access."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        email = "disabled_user@example.com"
        reg = client.post(
            "/api/v1/auth/register",
            json={"full_name": "Disabled User", "email": email, "password": _STRONG_PASSWORD},
        )
        assert reg.status_code == 201
        token = reg.json()["development_verification_token"]
        user_id = uuid.UUID(reg.json()["user"]["id"])

        # Manually disable user in database
        with ctx.session_factory() as db:
            user = db.get(User, user_id)
            assert user is not None
            user.status = UserStatus.DISABLED.value
            db.commit()

        # User attempts to verify email
        ver_res = client.post("/api/v1/auth/verify-email", json={"token": token})
        assert ver_res.status_code == 200
        ver_data = ver_res.json()
        assert ver_data["is_email_verified"] is True
        # can_access_project_immediately must be False because account is disabled!
        assert ver_data["can_access_project_immediately"] is False

        # Status in DB remains disabled
        with ctx.session_factory() as db:
            user = db.get(User, user_id)
            assert user is not None
            assert user.status == UserStatus.DISABLED.value

        # Attempt to login fails with 401 INVALID_CREDENTIALS
        login_res = client.post("/api/v1/auth/login", json={"email": email, "password": _STRONG_PASSWORD})
        assert login_res.status_code == 401
        assert login_res.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_14_refreshed_access_tokens_for_unverified_users_remain_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """14. A refreshed access token for an unverified account remains blocked from protected resources."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_gate_harness(client)
        email = "unverified_refresh_test@example.com"
        _, raw_token = h.create_project_invitation(email, project_role_name="reviewer")

        client.post(
            "/api/v1/auth/register-with-invitation",
            json={"invitation_token": raw_token, "full_name": "Refresh Tester", "password": _STRONG_PASSWORD},
        )
        # Login and obtain refresh cookie
        login_res = client.post("/api/v1/auth/login", json={"email": email, "password": _STRONG_PASSWORD})
        assert login_res.status_code == 200

        # Perform token refresh via HttpOnly cookie with Origin header
        refresh_res = client.post("/api/v1/auth/refresh", headers={"Origin": "http://localhost:3000"})
        assert refresh_res.status_code == 200
        new_access_token = refresh_res.json()["access_token"]
        new_headers = {"Authorization": f"Bearer {new_access_token}"}

        # New token remains blocked by email verification gate
        proj_res = client.get(f"/api/v1/projects/{h.project_id}", headers=new_headers)
        assert proj_res.status_code == 403
        assert proj_res.json()["error"]["code"] == "EMAIL_VERIFICATION_REQUIRED"


def test_15_unverified_user_cannot_access_or_register_connected_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """15. An unverified user cannot list, register, or modify connected sources."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_gate_harness(client)
        email = "unverified_sources_test@example.com"
        _, raw_token = h.create_project_invitation(email, project_role_name="reviewer")

        client.post(
            "/api/v1/auth/register-with-invitation",
            json={"invitation_token": raw_token, "full_name": "Sources Tester", "password": _STRONG_PASSWORD},
        )
        login_res = client.post("/api/v1/auth/login", json={"email": email, "password": _STRONG_PASSWORD})
        headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

        # List sources in org -> 403 EMAIL_VERIFICATION_REQUIRED
        list_src = client.get(f"/api/v1/organisations/{h.org_id}/sources", headers=headers)
        assert list_src.status_code == 403
        assert list_src.json()["error"]["code"] == "EMAIL_VERIFICATION_REQUIRED"

        # Register source in org -> 403 EMAIL_VERIFICATION_REQUIRED
        create_src = client.post(
            f"/api/v1/organisations/{h.org_id}/sources",
            headers=headers,
            json={
                "provider": "github",
                "account_identifier": "unverified-account",
                "secret_token": "ghp_TestTokenUnverified123",
                "scopes": ["repo"],
                "is_shared": False,
            },
        )
        assert create_src.status_code == 403
        assert create_src.json()["error"]["code"] == "EMAIL_VERIFICATION_REQUIRED"


def test_16_connected_sources_authorization_matrix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """16. Rigorous connected-source authorization matrix across roles, creators, and tenants."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_gate_harness(client)

        # 1. Organisation Manager (org_owner) can create a source connection
        create_resp = client.post(
            f"/api/v1/organisations/{h.org_id}/sources",
            headers=h.owner.headers,
            json={
                "provider": "github",
                "account_identifier": "owner-repo",
                "secret_token": "ghp_ManagerSecretToken2026",
                "scopes": ["repo", "read:org"],
                "is_shared": False,
            },
        )
        assert create_resp.status_code == 201
        conn_id = create_resp.json()["id"]

        # 2. Org manager can view source details and modify sharing state
        detail_resp = client.get(f"/api/v1/sources/{conn_id}", headers=h.owner.headers)
        assert detail_resp.status_code == 200
        assert detail_resp.json()["id"] == conn_id

        patch_resp = client.patch(
            f"/api/v1/sources/{conn_id}",
            headers=h.owner.headers,
            json={"is_shared": True},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["is_shared"] is True

        # 3. Create a verified read-only organisation member (org_member)
        member_email = "readonly.orgmember@example.com"
        reg_resp = client.post(
            "/api/v1/auth/register",
            json={"full_name": "Read-Only Member", "email": member_email, "password": _STRONG_PASSWORD},
        )
        assert reg_resp.status_code == 201
        v_token = reg_resp.json()["development_verification_token"]
        assert client.post("/api/v1/auth/verify-email", json={"token": v_token}).status_code == 200

        login_resp = client.post("/api/v1/auth/login", json={"email": member_email, "password": _STRONG_PASSWORD})
        assert login_resp.status_code == 200
        member_headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

        # Invite and accept to Org with role 'org_member'
        inv_resp = client.post(
            f"/api/v1/organisations/{h.org_id}/invitations",
            headers=h.owner.headers,
            json={"email": member_email, "role_name": "org_member"},
        )
        assert inv_resp.status_code == 201
        inv_token = inv_resp.json()["development_invitation_token"]
        assert client.post(f"/api/v1/invitations/{inv_token}/accept", headers=member_headers).status_code == 200

        # 4. Read-only member CAN list sources
        list_resp = client.get(f"/api/v1/organisations/{h.org_id}/sources", headers=member_headers)
        assert list_resp.status_code == 200
        assert list_resp.json()["total"] >= 1

        # 5. Read-only member CAN view source details
        member_detail = client.get(f"/api/v1/sources/{conn_id}", headers=member_headers)
        assert member_detail.status_code == 200

        # 6. Read-only member CANNOT create a source connection
        member_create = client.post(
            f"/api/v1/organisations/{h.org_id}/sources",
            headers=member_headers,
            json={
                "provider": "github",
                "account_identifier": "member-repo",
                "secret_token": "ghp_MemberSecretToken2026",
                "scopes": ["repo"],
                "is_shared": False,
            },
        )
        assert member_create.status_code == 403
        assert member_create.json()["error"]["code"] == "FORBIDDEN"

        # 7. Read-only member CANNOT modify source configuration
        member_patch = client.patch(
            f"/api/v1/sources/{conn_id}",
            headers=member_headers,
            json={"is_shared": False},
        )
        assert member_patch.status_code == 403
        assert member_patch.json()["error"]["code"] == "FORBIDDEN"

        # 8. Read-only member CANNOT disconnect source
        member_disconnect = client.post(
            f"/api/v1/sources/{conn_id}/disconnect",
            headers=member_headers,
        )
        assert member_disconnect.status_code == 403
        assert member_disconnect.json()["error"]["code"] == "FORBIDDEN"

        # Also via integration service disconnect route
        member_integ_disconnect = client.post(
            f"/api/v1/integrations/connections/{conn_id}/disconnect",
            headers=member_headers,
        )
        assert member_integ_disconnect.status_code == 403
        assert member_integ_disconnect.json()["error"]["code"] == "FORBIDDEN"

        # 9. Cross-organisation user cannot access or disconnect source
        outsider_email = "outsider@othercorp.com"
        reg_out = client.post(
            "/api/v1/auth/register",
            json={"full_name": "Outsider User", "email": outsider_email, "password": _STRONG_PASSWORD},
        )
        assert client.post("/api/v1/auth/verify-email", json={"token": reg_out.json()["development_verification_token"]}).status_code == 200
        out_login = client.post("/api/v1/auth/login", json={"email": outsider_email, "password": _STRONG_PASSWORD})
        out_headers = {"Authorization": f"Bearer {out_login.json()['access_token']}"}

        out_list = client.get(f"/api/v1/organisations/{h.org_id}/sources", headers=out_headers)
        assert out_list.status_code == 404
        assert out_list.json()["error"]["code"] == "ORGANISATION_NOT_FOUND"

        out_disconnect = client.post(f"/api/v1/sources/{conn_id}/disconnect", headers=out_headers)
        assert out_disconnect.status_code == 404

        # 10. Org manager CAN disconnect source cleanly
        mgr_disconnect = client.post(
            f"/api/v1/sources/{conn_id}/disconnect",
            headers=h.owner.headers,
        )
        assert mgr_disconnect.status_code == 200
        assert mgr_disconnect.json()["status"] == "disconnected"


def test_17_email_verification_rate_limiting_enforces_configured_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """17. Email verification endpoint triggers rate limiting after exceeding the 5 attempts/minute limit."""
    with isolated_auth_app(
        monkeypatch,
        auth_rate_limit_enabled=True,
        auth_rate_limit_verify_email_max_attempts=5,
        auth_rate_limit_resend_verification_max_attempts=3,
        auth_rate_limit_window_seconds=60,
    ) as ctx, TestClient(ctx.app) as client:
        # First 5 verification attempts are processed by auth logic (returning 400 for bad token)
        for _ in range(5):
            res = client.post("/api/v1/auth/verify-email", json={"token": "invalid.jwt.token"})
            assert res.status_code == 400
            assert res.json()["error"]["code"] == "INVALID_VERIFICATION_TOKEN"

        # 6th attempt exceeds configured rate limit of 5 per minute -> 429 RATE_LIMIT_EXCEEDED
        rate_limited = client.post("/api/v1/auth/verify-email", json={"token": "invalid.jwt.token"})
        assert rate_limited.status_code == 429
        assert rate_limited.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"
        assert int(rate_limited.headers["retry-after"]) >= 1

        # Resend verification has its own independent bucket ("resend_verification") and is NOT blocked
        resend_res = client.post(
            "/api/v1/auth/resend-verification",
            json={"email": "somebody@example.com"},
        )
        assert resend_res.status_code == 200

        # Login has its own independent bucket ("login") and is NOT blocked
        login_res = client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "wrong"},
        )
        assert login_res.status_code == 401
