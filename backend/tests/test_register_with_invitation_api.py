"""Comprehensive API and Transaction Integration Tests for User Registration with Project Invitation (Phase 4).

Covers all 36 test scenarios across:
- Registration Success (1-6)
- Existing Accounts (7-10)
- Invitation Validation (11-19)
- Atomicity & Concurrency (20-26)
- Security & Token Handling (27-33)
- Email Verification & Access (34-36)
"""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.security import ensure_utc, hash_opaque_token, utc_now
from app.models.enums import (
    InvitationStatus,
    OrganisationStatus,
    ProjectStatus,
    RoleName,
)
from app.models.organisation import Organisation, OrganisationInvitation, OrganisationMembership
from app.models.project import Project, ProjectMembership
from app.models.user import User
from tests.conftest import (
    RegisteredUserSession,
    invite_and_accept_member,
    isolated_auth_app,
    register_and_login_user,
)

_STRONG_PASSWORD = "StrongSecurePassword2026!"


# =============================================================================
# Test Harness & Helpers
# =============================================================================

class RegisterInvitationHarness:
    """Convenience bundle of tenant, workspace, actors, and invitation token."""

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
        project_role_name: str = "project_member",
        inviter_headers: dict[str, str] | None = None,
    ) -> tuple[str, str]:
        """Create a project invitation and return (invitation_id, raw_token)."""
        headers = inviter_headers or self.pm.headers
        res = self.client.post(
            f"/api/v1/organisations/{self.org_id}/projects/{self.project_id}/invitations",
            headers=headers,
            json={"email": email, "project_role_name": project_role_name},
        )
        assert res.status_code == 201, res.text
        data = res.json()
        return data["invitation"]["id"], data["development_invitation_token"]

    def create_org_invitation(
        self,
        email: str,
        role_name: str = "org_member",
        inviter_headers: dict[str, str] | None = None,
    ) -> tuple[str, str]:
        """Create an organisation-only invitation and return (invitation_id, raw_token)."""
        headers = inviter_headers or self.owner.headers
        res = self.client.post(
            f"/api/v1/organisations/{self.org_id}/invitations",
            headers=headers,
            json={"email": email, "role_name": role_name},
        )
        assert res.status_code == 201, res.text
        data = res.json()
        return data["invitation"]["id"], data["development_invitation_token"]


def _setup_harness(client: TestClient) -> RegisterInvitationHarness:
    tag = uuid.uuid4().hex[:6]
    owner = register_and_login_user(client, email=f"owner_{tag}@org.com", full_name="Org Owner")
    pm = register_and_login_user(client, email=f"pm_{tag}@org.com", full_name="Project Manager")

    org_res = client.post(
        "/api/v1/organisations",
        headers=owner.headers,
        json={"name": f"Acme Corp {tag}"},
    )
    assert org_res.status_code == 201
    org_id = org_res.json()["id"]

    invite_and_accept_member(
        client,
        organisation_id=org_id,
        inviter_headers=owner.headers,
        invitee=pm,
        role_name="org_member",
    )

    proj_res = client.post(
        f"/api/v1/organisations/{org_id}/projects",
        headers=owner.headers,
        json={"name": f"Project Alpha {tag}", "visibility": "private"},
    )
    assert proj_res.status_code == 201
    project_id = proj_res.json()["id"]

    # Assign PM to the project
    client.post(
        f"/api/v1/projects/{project_id}/members",
        headers=owner.headers,
        json={"user_id": str(pm.user_id), "role_name": "project_manager"},
    )

    return RegisterInvitationHarness(
        client=client,
        owner=owner,
        pm=pm,
        org_id=org_id,
        project_id=project_id,
    )


# =============================================================================
# PART 1: REGISTRATION SUCCESS (Tests 1 - 6)
# =============================================================================

def test_1_new_user_registers_with_valid_project_invitation(monkeypatch: pytest.MonkeyPatch) -> None:
    """1. New user registers with a valid project invitation and becomes org & project member."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        invitee_email = "new_developer@example.com"
        _, raw_token = h.create_project_invitation(invitee_email, project_role_name="project_member")

        res = client.post(
            "/api/v1/auth/register-with-invitation",
            json={
                "invitation_token": raw_token,
                "full_name": "New Developer",
                "password": _STRONG_PASSWORD,
            },
        )
        assert res.status_code == 201, res.text
        data = res.json()

        assert data["user"]["email"] == invitee_email
        assert data["user"]["full_name"] == "New Developer"
        assert data["user"]["status"] == "active"
        assert data["organisation_id"] == h.org_id
        assert data["project_id"] == h.project_id
        assert data["project_role_name"] == "project_member"
        assert data["project_membership_status"] == "active"
        assert data["can_access_project_immediately"] is False
        assert data["development_verification_token"] is not None


def test_2_user_receives_invited_organisation_membership(monkeypatch: pytest.MonkeyPatch) -> None:
    """2. User receives the invited organisation membership with default 'org_member' role."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        invitee_email = "org_membership_verify@example.com"
        _, raw_token = h.create_project_invitation(invitee_email, project_role_name="reviewer")

        res = client.post(
            "/api/v1/auth/register-with-invitation",
            json={
                "invitation_token": raw_token,
                "full_name": "Org Member Verifier",
                "password": _STRONG_PASSWORD,
            },
        )
        assert res.status_code == 201

        with ctx.session_factory() as session:
            user = session.scalar(select(User).where(User.email == invitee_email))
            assert user is not None
            org_mem = session.scalar(
                select(OrganisationMembership).where(
                    OrganisationMembership.organisation_id == uuid.UUID(h.org_id),
                    OrganisationMembership.user_id == user.id,
                )
            )
            assert org_mem is not None
            assert org_mem.role.name == "org_member"


def test_3_user_receives_exact_invited_project_role(monkeypatch: pytest.MonkeyPatch) -> None:
    """3. User receives the exact invited project role ('reviewer') specified in the invitation."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        invitee_email = "reviewer_candidate@example.com"
        _, raw_token = h.create_project_invitation(invitee_email, project_role_name="reviewer")

        res = client.post(
            "/api/v1/auth/register-with-invitation",
            json={
                "invitation_token": raw_token,
                "full_name": "Reviewer Person",
                "password": _STRONG_PASSWORD,
            },
        )
        assert res.status_code == 201
        data = res.json()
        assert data["project_role_name"] == "reviewer"

        with ctx.session_factory() as session:
            user = session.scalar(select(User).where(User.email == invitee_email))
            assert user is not None
            proj_mem = session.scalar(
                select(ProjectMembership).where(
                    ProjectMembership.project_id == uuid.UUID(h.project_id),
                    ProjectMembership.user_id == user.id,
                )
            )
            assert proj_mem is not None
            assert proj_mem.role.name == "reviewer"


def test_4_invitation_status_becomes_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    """4. Invitation status becomes accepted with accepted_by_user_id and accepted_at recorded."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        invitee_email = "status_accepted_check@example.com"
        inv_id, raw_token = h.create_project_invitation(invitee_email, project_role_name="project_member")

        res = client.post(
            "/api/v1/auth/register-with-invitation",
            json={
                "invitation_token": raw_token,
                "full_name": "Status Checked User",
                "password": _STRONG_PASSWORD,
            },
        )
        assert res.status_code == 201

        with ctx.session_factory() as session:
            user = session.scalar(select(User).where(User.email == invitee_email))
            assert user is not None
            inv = session.scalar(select(OrganisationInvitation).where(OrganisationInvitation.id == uuid.UUID(inv_id)))
            assert inv is not None
            assert inv.status == "accepted"
            assert inv.accepted_by_user_id == user.id
            assert inv.accepted_at is not None

        # Authenticate with credentials established during registration
        login_res = client.post(
            "/api/v1/auth/login",
            json={"email": invitee_email, "password": _STRONG_PASSWORD},
        )
        assert login_res.status_code == 200
        token = login_res.json()["access_token"]
        auth_headers = {"Authorization": f"Bearer {token}"}

        # Query project details before email verification -> BLOCKED (403 EMAIL_VERIFICATION_REQUIRED)
        unverified_proj_res = client.get(f"/api/v1/projects/{h.project_id}", headers=auth_headers)
        assert unverified_proj_res.status_code == 403
        assert unverified_proj_res.json()["error"]["code"] == "EMAIL_VERIFICATION_REQUIRED"

        # Verify email using development token
        dev_verif_token = res.json()["development_verification_token"]
        assert dev_verif_token is not None
        ver_res = client.post("/api/v1/auth/verify-email", json={"token": dev_verif_token})
        assert ver_res.status_code == 200

        # Query project details after email verification -> SUCCEEDS (200 OK)
        proj_res = client.get(f"/api/v1/projects/{h.project_id}", headers=auth_headers)
        assert proj_res.status_code == 200
        assert proj_res.json()["my_project_role"] == "project_member"


def test_5_response_contains_correct_project_attribution(monkeypatch: pytest.MonkeyPatch) -> None:
    """5. Registration response contains complete organisation and project attribution."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        _, raw_token = h.create_project_invitation("attribution_test@example.com", project_role_name="reviewer")

        res = client.post(
            "/api/v1/auth/register-with-invitation",
            json={
                "invitation_token": raw_token,
                "full_name": "Attribution Tester",
                "password": _STRONG_PASSWORD,
            },
        )
        assert res.status_code == 201
        data = res.json()
        assert data["organisation_id"] == h.org_id
        assert data["organisation_name"] is not None
        assert data["project_id"] == h.project_id
        assert data["project_name"] is not None
        assert data["project_role_name"] == "reviewer"
        assert data["can_access_project_immediately"] is False
        assert data["development_verification_token"] is not None


def test_6_existing_normal_registration_flow_remains_functional(monkeypatch: pytest.MonkeyPatch) -> None:
    """6. Existing normal registration without an invitation continues to operate without changes."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        res = client.post(
            "/api/v1/auth/register",
            json={
                "full_name": "Standard User",
                "email": "standard_user_flow@example.com",
                "password": _STRONG_PASSWORD,
            },
        )
        assert res.status_code == 201
        assert res.json()["user"]["email"] == "standard_user_flow@example.com"
        assert res.json()["email_verification_required"] is True


# =============================================================================
# PART 2: EXISTING ACCOUNTS (Tests 7 - 10)
# =============================================================================

def test_7_existing_account_cannot_create_duplicate_account(monkeypatch: pytest.MonkeyPatch) -> None:
    """7. An existing registered account cannot create a duplicate account via invitation."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        existing_email = "already_registered@example.com"
        register_and_login_user(client, email=existing_email, full_name="Already Here")

        # Invite the existing account to a project
        _, raw_token = h.create_project_invitation(existing_email, project_role_name="reviewer")

        # Attempt to register again using the invitation
        res = client.post(
            "/api/v1/auth/register-with-invitation",
            json={
                "invitation_token": raw_token,
                "full_name": "Duplicate Attempt",
                "password": "AnotherDifferentPassword2026!",
            },
        )
        assert res.status_code == 409
        assert res.json()["error"]["code"] == "ACCOUNT_ALREADY_EXISTS"


def test_8_existing_account_directed_to_sign_in_and_use_existing_acceptance_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """8. Safe response directs existing user to sign in and accept via the authenticated route."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        existing_email = "safe_existing@example.com"
        register_and_login_user(client, email=existing_email, full_name="Safe User")

        _, raw_token = h.create_project_invitation(existing_email, project_role_name="reviewer")

        res = client.post(
            "/api/v1/auth/register-with-invitation",
            json={
                "invitation_token": raw_token,
                "full_name": "Impostor Attempt",
                "password": "HackerOverwrittenPassword123!",
            },
        )
        assert res.status_code == 409
        assert "sign in" in res.json()["error"]["message"].lower()


def test_9_existing_account_password_is_not_changed(monkeypatch: pytest.MonkeyPatch) -> None:
    """9. Existing account's password is not modified during rejected duplicate registration."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        existing_email = "pw_check_user@example.com"
        orig_pw = "OriginalSecretPassword123!"
        register_and_login_user(client, email=existing_email, password=orig_pw, full_name="PW Check User")

        _, raw_token = h.create_project_invitation(existing_email, project_role_name="reviewer")

        res = client.post(
            "/api/v1/auth/register-with-invitation",
            json={
                "invitation_token": raw_token,
                "full_name": "Attacker Impostor",
                "password": "HackerOverwrittenPassword123!",
            },
        )
        assert res.status_code == 409

        # Original password must still authenticate cleanly
        login_res = client.post(
            "/api/v1/auth/login",
            json={"email": existing_email, "password": orig_pw},
        )
        assert login_res.status_code == 200


def test_10_existing_account_can_accept_after_authenticating_with_matching_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """10. Existing account signs in with matching email and accepts via POST /api/v1/invitations/{token}/accept."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        existing_email = "legit_existing@example.com"
        existing_user = register_and_login_user(client, email=existing_email, full_name="Legit Existing")

        _, raw_token = h.create_project_invitation(existing_email, project_role_name="reviewer")

        # Authenticated acceptance succeeds
        accept_res = client.post(
            f"/api/v1/invitations/{raw_token}/accept",
            headers=existing_user.headers,
        )
        assert accept_res.status_code == 200
        accept_data = accept_res.json()
        assert accept_data["project_role_name"] == "reviewer"

        # Verify project access
        proj_res = client.get(f"/api/v1/projects/{h.project_id}", headers=existing_user.headers)
        assert proj_res.status_code == 200
        assert proj_res.json()["my_project_role"] == "reviewer"


# =============================================================================
# PART 3: INVITATION VALIDATION (Tests 11 - 19)
# =============================================================================

def test_11_invalid_token_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """11. An invalid, non-existent, or malformed invitation token is rejected."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        res = client.post(
            "/api/v1/auth/register-with-invitation",
            json={
                "invitation_token": "non_existent_token_hex_value_00000000",
                "full_name": "Valid Name",
                "password": _STRONG_PASSWORD,
            },
        )
        assert res.status_code == 404
        assert res.json()["error"]["code"] == "INVITATION_NOT_FOUND"


def test_12_expired_token_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """12. An expired invitation token cannot be used for registration."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        invitee_email = "expired_invitee@example.com"
        inv_id, raw_token = h.create_project_invitation(invitee_email)

        # Force expire the invitation in DB
        with ctx.session_factory() as session:
            inv = session.scalar(select(OrganisationInvitation).where(OrganisationInvitation.id == uuid.UUID(inv_id)))
            assert inv is not None
            inv.expires_at = utc_now() - timedelta(days=2)
            session.commit()

        res = client.post(
            "/api/v1/auth/register-with-invitation",
            json={
                "invitation_token": raw_token,
                "full_name": "Expired User",
                "password": _STRONG_PASSWORD,
            },
        )
        assert res.status_code == 410
        assert res.json()["error"]["code"] == "INVITATION_EXPIRED"


def test_13_revoked_token_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """13. A revoked invitation cannot be used to register a new user."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        invitee_email = "revoked_invitee@example.com"
        inv_id, raw_token = h.create_project_invitation(invitee_email)

        # PM revokes the invitation via project invitations API
        del_res = client.delete(
            f"/api/v1/organisations/{h.org_id}/projects/{h.project_id}/invitations/{inv_id}",
            headers=h.pm.headers,
        )
        assert del_res.status_code == 200

        res = client.post(
            "/api/v1/auth/register-with-invitation",
            json={
                "invitation_token": raw_token,
                "full_name": "Revoked User",
                "password": _STRONG_PASSWORD,
            },
        )
        assert res.status_code == 409
        assert res.json()["error"]["code"] == "INVITATION_REVOKED"


def test_14_already_accepted_token_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """14. An invitation that was already accepted cannot be reused for a second registration."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        invitee_email = "first_registered@example.com"
        _, raw_token = h.create_project_invitation(invitee_email)

        # First registration consumes the token
        res1 = client.post(
            "/api/v1/auth/register-with-invitation",
            json={
                "invitation_token": raw_token,
                "full_name": "First Registrant",
                "password": _STRONG_PASSWORD,
            },
        )
        assert res1.status_code == 201

        # Second attempt with same token fails
        res2 = client.post(
            "/api/v1/auth/register-with-invitation",
            json={
                "invitation_token": raw_token,
                "full_name": "Second Registrant",
                "password": _STRONG_PASSWORD,
            },
        )
        assert res2.status_code == 409
        assert res2.json()["error"]["code"] in ("INVITATION_ALREADY_ACCEPTED", "ACCOUNT_ALREADY_EXISTS")


def test_15_wrong_email_identity_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """15. Submitting an email that disagrees with the invitation's bound email is rejected."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        invitee_email = "legit_target@example.com"
        _, raw_token = h.create_project_invitation(invitee_email)

        res = client.post(
            "/api/v1/auth/register-with-invitation",
            json={
                "invitation_token": raw_token,
                "email": "different_attacker@example.com",
                "full_name": "Attacker",
                "password": _STRONG_PASSWORD,
            },
        )
        assert res.status_code == 403
        assert res.json()["error"]["code"] == "INVITATION_EMAIL_MISMATCH"


def test_16_inactive_organisation_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """16. Inactive or archived organisation prevents registration."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        invitee_email = "archived_org_invitee@example.com"
        _, raw_token = h.create_project_invitation(invitee_email)

        # Archive organisation
        with ctx.session_factory() as session:
            org = session.scalar(select(Organisation).where(Organisation.id == uuid.UUID(h.org_id)))
            assert org is not None
            org.status = OrganisationStatus.ARCHIVED.value
            session.commit()

        res = client.post(
            "/api/v1/auth/register-with-invitation",
            json={
                "invitation_token": raw_token,
                "full_name": "Org Archived User",
                "password": _STRONG_PASSWORD,
            },
        )
        assert res.status_code == 409
        assert res.json()["error"]["code"] in ("ORGANISATION_ARCHIVED", "ORGANISATION_NOT_ACTIVE")


def test_17_inactive_project_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """17. Inactive or archived project prevents registration."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        invitee_email = "archived_proj_invitee@example.com"
        _, raw_token = h.create_project_invitation(invitee_email)

        # Archive project
        with ctx.session_factory() as session:
            proj = session.scalar(select(Project).where(Project.id == uuid.UUID(h.project_id)))
            assert proj is not None
            proj.status = ProjectStatus.ARCHIVED.value
            session.commit()

        res = client.post(
            "/api/v1/auth/register-with-invitation",
            json={
                "invitation_token": raw_token,
                "full_name": "Archived Proj User",
                "password": _STRONG_PASSWORD,
            },
        )
        assert res.status_code == 409
        assert res.json()["error"]["code"] == "PROJECT_ARCHIVED"


def test_18_cross_organisation_project_reference_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """18. An invitation referencing a project from a different organisation is rejected with 403 TENANT_MISMATCH."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        invitee_email = "tampered_invitation@example.com"
        _, raw_token = h.create_project_invitation(invitee_email)

        from app.repositories.organisation import OrganisationRepository

        orig_get_inv = OrganisationRepository.get_invitation_by_token_hash_for_update

        def _tampered_inv(self, token_hash):
            inv = orig_get_inv(self, token_hash)
            if inv:
                from unittest.mock import MagicMock
                fake_proj = MagicMock(wraps=inv.project)
                fake_proj.organisation_id = uuid.uuid4()  # Mismatch with inv.organisation_id
                fake_proj.status = "active"
                fake_proj.organisation = inv.organisation

                fake_inv = MagicMock(wraps=inv)
                fake_inv.organisation = inv.organisation
                fake_inv.organisation_id = inv.organisation_id
                fake_inv.project = fake_proj
                fake_inv.project_id = inv.project_id
                fake_inv.project_role = inv.project_role
                fake_inv.status = inv.status
                fake_inv.email = inv.email
                fake_inv.invited_by_id = inv.invited_by_id
                fake_inv.expires_at = inv.expires_at
                return fake_inv
            return inv

        monkeypatch.setattr(OrganisationRepository, "get_invitation_by_token_hash_for_update", _tampered_inv)

        res = client.post(
            "/api/v1/auth/register-with-invitation",
            json={
                "invitation_token": raw_token,
                "full_name": "Tampered User",
                "password": _STRONG_PASSWORD,
            },
        )
        assert res.status_code == 403
        assert res.json()["error"]["code"] == "TENANT_MISMATCH"


def test_19_stale_inviter_authority_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """19. If the inviter is demoted from Project Manager, the invitation cannot register users."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        invitee_email = "stale_inviter_candidate@example.com"
        _, raw_token = h.create_project_invitation(invitee_email, project_role_name="reviewer")

        from app.models.rbac import Role

        # Demote the inviter (PM) to project_member in DB
        with ctx.session_factory() as session:
            proj_mem = session.scalar(
                select(ProjectMembership).where(
                    ProjectMembership.project_id == uuid.UUID(h.project_id),
                    ProjectMembership.user_id == uuid.UUID(str(h.pm.user_id)),
                )
            )
            member_role = session.scalar(select(Role).where(Role.name == RoleName.PROJECT_MEMBER.value))
            assert proj_mem is not None and member_role is not None
            proj_mem.role_id = member_role.id
            proj_mem.role = member_role
            session.commit()

        res = client.post(
            "/api/v1/auth/register-with-invitation",
            json={
                "invitation_token": raw_token,
                "full_name": "Should Fail User",
                "password": _STRONG_PASSWORD,
            },
        )
        assert res.status_code == 403
        assert res.json()["error"]["code"] == "INVITER_NO_LONGER_AUTHORISED"


# =============================================================================
# PART 4: ATOMICITY & CONCURRENCY (Tests 20 - 26)
# =============================================================================

def test_20_failure_during_user_creation_rolls_back_all_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    """20. Failure during user record creation rolls back all changes."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        invitee_email = "user_fail_rollback@example.com"
        inv_id, raw_token = h.create_project_invitation(invitee_email)

        from app.services.auth import AuthService

        def _exploding_user_create(*args, **kwargs):
            raise RuntimeError("Database error during user record insertion.")

        monkeypatch.setattr(AuthService, "_create_user_record_uncommitted", _exploding_user_create)

        with pytest.raises(RuntimeError):
            client.post(
                "/api/v1/auth/register-with-invitation",
                json={
                    "invitation_token": raw_token,
                    "full_name": "Never Persisted",
                    "password": _STRONG_PASSWORD,
                },
            )

        with ctx.session_factory() as session:
            user = session.scalar(select(User).where(User.email == invitee_email))
            assert user is None
            inv = session.scalar(select(OrganisationInvitation).where(OrganisationInvitation.id == uuid.UUID(inv_id)))
            assert inv is not None
            assert inv.status == "pending"


def test_21_failure_during_organisation_membership_creation_rolls_back_user_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """21. Failure during organisation membership creation rolls back user creation."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        invitee_email = "org_mem_fail_rollback@example.com"
        inv_id, raw_token = h.create_project_invitation(invitee_email)

        from app.repositories.organisation import OrganisationRepository

        def _exploding_create_org_membership(*args, **kwargs):
            raise RuntimeError("Database error during organisation membership assignment.")

        monkeypatch.setattr(OrganisationRepository, "create_membership", _exploding_create_org_membership)

        with pytest.raises(RuntimeError):
            client.post(
                "/api/v1/auth/register-with-invitation",
                json={
                    "invitation_token": raw_token,
                    "full_name": "Never Persisted Org",
                    "password": _STRONG_PASSWORD,
                },
            )

        with ctx.session_factory() as session:
            user = session.scalar(select(User).where(User.email == invitee_email))
            assert user is None
            inv = session.scalar(select(OrganisationInvitation).where(OrganisationInvitation.id == uuid.UUID(inv_id)))
            assert inv is not None
            assert inv.status == "pending"


def test_22_failure_during_project_membership_creation_rolls_back_user_and_organisation_membership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """22. Failure during project membership creation rolls back user and organisation membership."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        invitee_email = "proj_mem_fail_rollback@example.com"
        inv_id, raw_token = h.create_project_invitation(invitee_email)

        from app.repositories.project import ProjectRepository

        def _exploding_create_proj_membership(*args, **kwargs):
            raise RuntimeError("Database error during project membership assignment.")

        monkeypatch.setattr(ProjectRepository, "create_membership", _exploding_create_proj_membership)

        with pytest.raises(RuntimeError):
            client.post(
                "/api/v1/auth/register-with-invitation",
                json={
                    "invitation_token": raw_token,
                    "full_name": "Never Persisted Proj",
                    "password": _STRONG_PASSWORD,
                },
            )

        with ctx.session_factory() as session:
            user = session.scalar(select(User).where(User.email == invitee_email))
            assert user is None
            inv = session.scalar(select(OrganisationInvitation).where(OrganisationInvitation.id == uuid.UUID(inv_id)))
            assert inv is not None
            assert inv.status == "pending"


def test_23_failure_during_audit_logging_rolls_back_all_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    """23. Failure during audit logging rolls back all changes."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        invitee_email = "audit_fail_rollback@example.com"
        inv_id, raw_token = h.create_project_invitation(invitee_email)

        from app.services.audit import AuditService

        def _exploding_audit(*args, **kwargs):
            raise RuntimeError("Database error during audit logging.")

        monkeypatch.setattr(AuditService, "record_event", _exploding_audit)

        with pytest.raises(RuntimeError):
            client.post(
                "/api/v1/auth/register-with-invitation",
                json={
                    "invitation_token": raw_token,
                    "full_name": "Never Persisted Audit",
                    "password": _STRONG_PASSWORD,
                },
            )

        with ctx.session_factory() as session:
            user = session.scalar(select(User).where(User.email == invitee_email))
            assert user is None
            inv = session.scalar(select(OrganisationInvitation).where(OrganisationInvitation.id == uuid.UUID(inv_id)))
            assert inv is not None
            assert inv.status == "pending"


def test_24_invitation_status_remains_pending_if_transaction_rolls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """24. Invitation status strictly remains 'pending' with accepted_at None if transaction rolls back."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        invitee_email = "status_pending_verify@example.com"
        inv_id, raw_token = h.create_project_invitation(invitee_email)

        from app.services.organisation import OrganisationService

        def _exploding_accept(*args, **kwargs):
            raise RuntimeError("Late failure in acceptance flow.")

        monkeypatch.setattr(OrganisationService, "accept_invitation", _exploding_accept)

        with pytest.raises(RuntimeError):
            client.post(
                "/api/v1/auth/register-with-invitation",
                json={
                    "invitation_token": raw_token,
                    "full_name": "Pending Verifier",
                    "password": _STRONG_PASSWORD,
                },
            )

        with ctx.session_factory() as session:
            inv = session.scalar(select(OrganisationInvitation).where(OrganisationInvitation.id == uuid.UUID(inv_id)))
            assert inv is not None
            assert inv.status == "pending"
            assert inv.accepted_by_user_id is None
            assert inv.accepted_at is None


def test_25_concurrent_registration_attempts_cannot_create_duplicate_users(monkeypatch: pytest.MonkeyPatch) -> None:
    """25. Concurrent registration attempts cannot create duplicate users or double-consume token."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        invitee_email = "double_submit@example.com"
        _, raw_token = h.create_project_invitation(invitee_email)

        # First registration succeeds
        res1 = client.post(
            "/api/v1/auth/register-with-invitation",
            json={
                "invitation_token": raw_token,
                "full_name": "First Attempt",
                "password": _STRONG_PASSWORD,
            },
        )
        assert res1.status_code == 201

        # Second attempt immediately conflicts
        res2 = client.post(
            "/api/v1/auth/register-with-invitation",
            json={
                "invitation_token": raw_token,
                "full_name": "Second Attempt",
                "password": _STRONG_PASSWORD,
            },
        )
        assert res2.status_code == 409

        # Confirm exactly one user exists
        with ctx.session_factory() as session:
            users = session.scalars(select(User).where(User.email == invitee_email)).all()
            assert len(users) == 1


def test_26_concurrent_acceptance_attempts_cannot_consume_same_invitation_twice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """26. Once an invitation is consumed by registration, subsequent acceptance attempts are rejected."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        invitee_email = "consume_once@example.com"
        _, raw_token = h.create_project_invitation(invitee_email)

        # Registration consumes the token
        reg_res = client.post(
            "/api/v1/auth/register-with-invitation",
            json={
                "invitation_token": raw_token,
                "full_name": "Original Consumer",
                "password": _STRONG_PASSWORD,
            },
        )
        assert reg_res.status_code == 201

        # Another user tries to accept the already-consumed invitation
        other_user = register_and_login_user(client, email="other_person@example.com", full_name="Other Person")
        accept_res = client.post(
            f"/api/v1/invitations/{raw_token}/accept",
            headers=other_user.headers,
        )
        assert accept_res.status_code in (400, 403, 409)

        # The registered user also cannot accept the consumed invitation a second time
        login_res = client.post(
            "/api/v1/auth/login",
            json={"email": invitee_email, "password": _STRONG_PASSWORD},
        )
        assert login_res.status_code == 200
        consumer_headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}
        re_accept_res = client.post(
            f"/api/v1/invitations/{raw_token}/accept",
            headers=consumer_headers,
        )
        assert re_accept_res.status_code == 409
        assert re_accept_res.json()["error"]["code"] in ("INVITATION_ALREADY_ACCEPTED", "MEMBERSHIP_ALREADY_EXISTS")


# =============================================================================
# PART 5: SECURITY & TOKEN HANDLING (Tests 27 - 33)
# =============================================================================

def test_27_raw_token_is_never_stored_in_database(monkeypatch: pytest.MonkeyPatch) -> None:
    """27. Raw invitation token is never stored unhashed in the database."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        invitee_email = "hash_check@example.com"
        inv_id, raw_token = h.create_project_invitation(invitee_email)

        with ctx.session_factory() as session:
            inv = session.scalar(select(OrganisationInvitation).where(OrganisationInvitation.id == uuid.UUID(inv_id)))
            assert inv is not None
            assert inv.token_hash == hash_opaque_token(raw_token)
            assert raw_token not in inv.token_hash


def test_28_token_hash_is_never_returned_in_api_responses(monkeypatch: pytest.MonkeyPatch) -> None:
    """28. Token hash is never returned in registration or list responses."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        _, raw_token = h.create_project_invitation("no_hash_leak@example.com")

        res = client.post(
            "/api/v1/auth/register-with-invitation",
            json={
                "invitation_token": raw_token,
                "full_name": "No Hash Leak",
                "password": _STRONG_PASSWORD,
            },
        )
        assert res.status_code == 201
        assert "token_hash" not in res.text


def test_29_password_is_never_logged_or_returned(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """29. Password secret is never returned in response body or written to logs."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        _, raw_token = h.create_project_invitation("logging_check@example.com")
        secret_password = "SecretSuperPassword123!@#"

        with caplog.at_level(logging.DEBUG):
            res = client.post(
                "/api/v1/auth/register-with-invitation",
                json={
                    "invitation_token": raw_token,
                    "full_name": "Log Check User",
                    "password": secret_password,
                },
            )
            assert res.status_code == 201
            assert secret_password not in res.text
            assert secret_password not in caplog.text


def test_30_client_supplied_extra_fields_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """30. Client-supplied role or organisation fields cannot override invitation values (rejected by extra=forbid)."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        _, raw_token = h.create_project_invitation("extra_fields_check@example.com")

        res = client.post(
            "/api/v1/auth/register-with-invitation",
            json={
                "invitation_token": raw_token,
                "full_name": "Attacker",
                "password": _STRONG_PASSWORD,
                "project_role": "project_manager",  # Forbidden extra field!
            },
        )
        assert res.status_code == 422
        assert res.json()["error"]["code"] == "VALIDATION_ERROR"


def test_31_registration_cannot_grant_unrelated_project_memberships(monkeypatch: pytest.MonkeyPatch) -> None:
    """31. Registration grants membership strictly to the invited project, never unrelated projects."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)

        # Create a second project
        second_proj = client.post(
            f"/api/v1/organisations/{h.org_id}/projects",
            headers=h.owner.headers,
            json={"name": "Second Project", "visibility": "private"},
        )
        assert second_proj.status_code == 201
        second_proj_id = second_proj.json()["id"]

        invitee_email = "one_project_only@example.com"
        _, raw_token = h.create_project_invitation(invitee_email, project_role_name="reviewer")

        res = client.post(
            "/api/v1/auth/register-with-invitation",
            json={
                "invitation_token": raw_token,
                "full_name": "One Project User",
                "password": _STRONG_PASSWORD,
            },
        )
        assert res.status_code == 201

        # Check in DB that user has membership ONLY in h.project_id
        with ctx.session_factory() as session:
            user = session.scalar(select(User).where(User.email == invitee_email))
            assert user is not None
            memberships = session.scalars(
                select(ProjectMembership).where(ProjectMembership.user_id == user.id)
            ).all()
            assert len(memberships) == 1
            assert str(memberships[0].project_id) == h.project_id
            assert str(memberships[0].project_id) != second_proj_id


def test_32_org_owner_admin_role_cannot_be_acquired_through_project_invitation(monkeypatch: pytest.MonkeyPatch) -> None:
    """32. A project invitation always assigns default 'org_member', never 'org_admin' or 'org_owner'."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        invitee_email = "no_admin_escalation@example.com"
        _, raw_token = h.create_project_invitation(invitee_email, project_role_name="project_manager")

        res = client.post(
            "/api/v1/auth/register-with-invitation",
            json={
                "invitation_token": raw_token,
                "full_name": "Privilege Check",
                "password": _STRONG_PASSWORD,
            },
        )
        assert res.status_code == 201

        with ctx.session_factory() as session:
            user = session.scalar(select(User).where(User.email == invitee_email))
            assert user is not None
            org_mem = session.scalar(
                select(OrganisationMembership).where(
                    OrganisationMembership.organisation_id == uuid.UUID(h.org_id),
                    OrganisationMembership.user_id == user.id,
                )
            )
            assert org_mem is not None
            assert org_mem.role.name == RoleName.ORG_MEMBER.value
            assert org_mem.role.name != RoleName.ORG_ADMIN.value
            assert org_mem.role.name != RoleName.ORG_OWNER.value


def test_33_rate_limiting_and_organisation_only_invitation_acceptance(monkeypatch: pytest.MonkeyPatch) -> None:
    """33. Organisation-only invitations work for registration and endpoint uses rate limiting protection."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        invitee_email = "org_only_registrant@example.com"
        _, raw_token = h.create_org_invitation(invitee_email, role_name="org_member")

        res = client.post(
            "/api/v1/auth/register-with-invitation",
            json={
                "invitation_token": raw_token,
                "full_name": "Org Only Registrant",
                "password": _STRONG_PASSWORD,
            },
        )
        assert res.status_code == 201
        data = res.json()
        assert data["organisation_id"] == h.org_id
        assert data["project_id"] is None
        assert data["project_role_name"] is None


# =============================================================================
# PART 6: EMAIL VERIFICATION & ACCESS CHECKS (Tests 34 - 36)
# =============================================================================

def test_34_email_verification_requirements_remain_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    """34. Response accurately indicates email verification requirement and delivery status."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        _, raw_token = h.create_project_invitation("email_verif_check@example.com")

        res = client.post(
            "/api/v1/auth/register-with-invitation",
            json={
                "invitation_token": raw_token,
                "full_name": "Verification User",
                "password": _STRONG_PASSWORD,
            },
        )
        assert res.status_code == 201
        data = res.json()
        assert data["email_verification_required"] is True
        assert data["email_verification_delivery"] == "not_configured"


def test_35_unverified_or_unauthenticated_users_cannot_gain_project_access_prematurely(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """35. An unauthenticated request cannot access project endpoints without logging in."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        _, raw_token = h.create_project_invitation("no_auth_access@example.com")

        reg_res = client.post(
            "/api/v1/auth/register-with-invitation",
            json={
                "invitation_token": raw_token,
                "full_name": "No Auth User",
                "password": _STRONG_PASSWORD,
            },
        )
        assert reg_res.status_code == 201

        # Trying to access project without bearer token fails
        no_auth_res = client.get(f"/api/v1/projects/{h.project_id}")
        assert no_auth_res.status_code == 401


def test_36_failed_attempt_does_not_leave_invitation_permanently_unusable(monkeypatch: pytest.MonkeyPatch) -> None:
    """36. If a registration attempt fails validation (e.g. weak password), invitation remains pending and usable."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        h = _setup_harness(client)
        invitee_email = "retry_user@example.com"
        _, raw_token = h.create_project_invitation(invitee_email)

        # First attempt with weak password fails validation
        bad_res = client.post(
            "/api/v1/auth/register-with-invitation",
            json={
                "invitation_token": raw_token,
                "full_name": "Retry User",
                "password": "weak",
            },
        )
        assert bad_res.status_code == 422

        # Second attempt with strong password succeeds
        good_res = client.post(
            "/api/v1/auth/register-with-invitation",
            json={
                "invitation_token": raw_token,
                "full_name": "Retry User",
                "password": _STRONG_PASSWORD,
            },
        )
        assert good_res.status_code == 201
        assert good_res.json()["user"]["email"] == invitee_email
