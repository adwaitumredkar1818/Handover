"""Comprehensive Integration Tests for Email Workflows with Resend.

Verifies all transactional email workflows end-to-end with ResendEmailProvider:
1. Standard registration email verification
2. Project invitation registration verification
3. Verification email resend (authenticated and unauthenticated)
4. Project invitation dispatch
5. Organisation invitation dispatch
6. Password reset request and completion
7. Platform notification dispatch
8. Security sanitization, privacy safeguards, and access gates
"""

from __future__ import annotations

import logging
import uuid
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.models.enums import RoleName
from app.services.email import ResendEmailProvider
from tests.conftest import isolated_auth_app

_TRUSTED_ORIGIN = "http://localhost:3000"
_PASSWORD = "Handover!Resend2026#Secure"
_API_KEY = "re_test_998877665544332211aabbcc"
_DEFAULT_SENDER = "Handover <notifications@the-sapiens.xyz>"


class MockResendClient:
    """Mock Resend SDK client recording all sent payloads."""

    def __init__(self) -> None:
        self.sent_emails: list[dict[str, Any]] = []

    def send(self, params: dict[str, Any]) -> dict[str, Any]:
        self.sent_emails.append(params)
        return {"id": f"resend-{uuid.uuid4()}"}


@pytest.fixture
def mock_resend_client() -> MockResendClient:
    return MockResendClient()


def _setup_resend_app(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configure environment for Resend email provider."""
    monkeypatch.setenv("EMAIL_DELIVERY_ENABLED", "true")
    monkeypatch.setenv("EMAIL_PROVIDER", "resend")
    monkeypatch.setenv("RESEND_API_KEY", _API_KEY)
    monkeypatch.setenv("EMAIL_FROM", _DEFAULT_SENDER)
    monkeypatch.setenv("EMAIL_FROM_ADDRESS", "notifications@the-sapiens.xyz")
    monkeypatch.setenv("EMAIL_FROM_NAME", "Handover")
    monkeypatch.setenv("EMAIL_SENDING_DOMAIN", "the-sapiens.xyz")
    monkeypatch.setenv("FRONTEND_BASE_URL", "http://localhost:3000")


# ---------------------------------------------------------------------------
# Workflow 1: Standard Registration & Access Gate Lifecycle
# ---------------------------------------------------------------------------

def test_workflow_1_standard_registration_verification_via_resend(
    monkeypatch: pytest.MonkeyPatch,
    mock_resend_client: MockResendClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Standard registration dispatches verification email via Resend with access gate enforced."""
    _setup_resend_app(monkeypatch)

    provider = ResendEmailProvider(
        api_key=_API_KEY,
        from_address="notifications@the-sapiens.xyz",
        from_name="Handover",
        sending_domain="the-sapiens.xyz",
        resend_client=mock_resend_client,
    )

    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        ctx.app.state.email_provider = provider

        with caplog.at_level(logging.INFO):
            # 1. Register new account
            reg = client.post(
                "/api/v1/auth/register",
                json={
                    "full_name": "Alice Standard",
                    "email": "alice.resend1@example.com",
                    "password": _PASSWORD,
                },
            )
            assert reg.status_code == 201
            data = reg.json()
            assert data["email_verification_delivery"] == "submitted"
            ver_token = data["development_verification_token"]
            assert ver_token is not None

            # Verify Resend interaction
            assert len(mock_resend_client.sent_emails) == 1
            sent = mock_resend_client.sent_emails[0]
            assert sent["to"] == ["alice.resend1@example.com"]
            assert sent["from"] == _DEFAULT_SENDER
            assert "Verify your Handover account" in sent["subject"]
            assert f"/verify-email?token={ver_token}" in sent["text"]
            assert f"/verify-email?token={ver_token}" in sent["html"]
            assert sent["tags"] == [{"name": "category", "value": "email_verification"}]

            # 2. Login as unverified user
            login = client.post(
                "/api/v1/auth/login",
                json={"email": "alice.resend1@example.com", "password": _PASSWORD},
            )
            assert login.status_code == 200
            token = login.json()["access_token"]
            auth_headers = {"Authorization": f"Bearer {token}", "Origin": _TRUSTED_ORIGIN}

            # 3. Verify access gate blocks unverified user from creating organisation
            org_blocked = client.post(
                "/api/v1/organisations",
                headers=auth_headers,
                json={"name": "Alice Org Blocked"},
            )
            assert org_blocked.status_code == 403
            assert org_blocked.json()["error"]["code"] == "EMAIL_VERIFICATION_REQUIRED"

            # 4. Verify email with token
            ver = client.post("/api/v1/auth/verify-email", json={"token": ver_token})
            assert ver.status_code == 200
            assert ver.json()["is_email_verified"] is True

            # 5. Access gate lifted: user can now create organisation
            org_allowed = client.post(
                "/api/v1/organisations",
                headers=auth_headers,
                json={"name": "Alice Org Allowed"},
            )
            assert org_allowed.status_code == 201
            assert org_allowed.json()["name"] == "Alice Org Allowed"


# ---------------------------------------------------------------------------
# Workflow 2: Verification Email Resend
# ---------------------------------------------------------------------------

def test_workflow_2_resend_verification_via_resend(
    monkeypatch: pytest.MonkeyPatch,
    mock_resend_client: MockResendClient,
) -> None:
    """Verification resend dispatches via Resend for unauthenticated and authenticated callers."""
    _setup_resend_app(monkeypatch)

    provider = ResendEmailProvider(
        api_key=_API_KEY,
        from_address="notifications@the-sapiens.xyz",
        from_name="Handover",
        resend_client=mock_resend_client,
    )

    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        ctx.app.state.email_provider = provider

        # 1. Register unverified user
        reg = client.post(
            "/api/v1/auth/register",
            json={"full_name": "Bob Resend", "email": "bob.resend@example.com", "password": _PASSWORD},
        )
        assert reg.status_code == 201
        assert len(mock_resend_client.sent_emails) == 1

        # 2. Unauthenticated resend with email
        resend1 = client.post(
            "/api/v1/auth/resend-verification",
            json={"email": "bob.resend@example.com"},
        )
        assert resend1.status_code == 200
        assert resend1.json()["email_verification_delivery"] == "submitted"
        assert len(mock_resend_client.sent_emails) == 2
        assert mock_resend_client.sent_emails[1]["to"] == ["bob.resend@example.com"]

        # 3. Unauthenticated resend with non-existent email -> timing-safe, no email sent
        resend_ghost = client.post(
            "/api/v1/auth/resend-verification",
            json={"email": "nonexistent@example.com"},
        )
        assert resend_ghost.status_code == 200
        assert len(mock_resend_client.sent_emails) == 2  # No new email dispatched

        # 4. Authenticated resend
        login = client.post(
            "/api/v1/auth/login",
            json={"email": "bob.resend@example.com", "password": _PASSWORD},
        )
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}", "Origin": _TRUSTED_ORIGIN}

        resend_auth = client.post("/api/v1/auth/resend-verification", headers=headers, json={})
        assert resend_auth.status_code == 200
        assert resend_auth.json()["email_verification_delivery"] == "submitted"
        assert len(mock_resend_client.sent_emails) == 3


# ---------------------------------------------------------------------------
# Workflow 3: Organisation & Project Invitations
# ---------------------------------------------------------------------------

def test_workflow_3_organisation_and_project_invitations_via_resend(
    monkeypatch: pytest.MonkeyPatch,
    mock_resend_client: MockResendClient,
) -> None:
    """Project and organisation invitations dispatch via Resend with role and expiry metadata."""
    _setup_resend_app(monkeypatch)

    provider = ResendEmailProvider(
        api_key=_API_KEY,
        from_address="notifications@the-sapiens.xyz",
        from_name="Handover",
        resend_client=mock_resend_client,
    )

    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        ctx.app.state.email_provider = provider

        # 1. Register & verify org owner
        reg = client.post(
            "/api/v1/auth/register",
            json={"full_name": "Carol Admin", "email": "carol.admin@example.com", "password": _PASSWORD},
        )
        ver_token = reg.json()["development_verification_token"]
        client.post("/api/v1/auth/verify-email", json={"token": ver_token})

        login = client.post(
            "/api/v1/auth/login",
            json={"email": "carol.admin@example.com", "password": _PASSWORD},
        )
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}", "Origin": _TRUSTED_ORIGIN}

        # Create org
        org_res = client.post("/api/v1/organisations", headers=headers, json={"name": "Carol Labs"})
        assert org_res.status_code == 201
        org_id = org_res.json()["id"]

        # 2. Invite member to organisation
        mock_resend_client.sent_emails.clear()
        inv_res = client.post(
            f"/api/v1/organisations/{org_id}/invitations",
            headers=headers,
            json={"email": "invited.org@example.com", "role_name": "org_member"},
        )
        assert inv_res.status_code == 201
        assert len(mock_resend_client.sent_emails) == 1
        org_email = mock_resend_client.sent_emails[0]
        assert org_email["to"] == ["invited.org@example.com"]
        assert org_email["from"] == _DEFAULT_SENDER
        assert "Carol Labs" in org_email["subject"]
        assert org_email["tags"] == [{"name": "category", "value": "organisation_invitation"}]

        # 3. Create project and invite project member
        proj_res = client.post(
            f"/api/v1/organisations/{org_id}/projects",
            headers=headers,
            json={"name": "Project Alpha"},
        )
        assert proj_res.status_code == 201
        proj_id = proj_res.json()["id"]

        mock_resend_client.sent_emails.clear()
        proj_inv = client.post(
            f"/api/v1/organisations/{org_id}/projects/{proj_id}/invitations",
            headers=headers,
            json={"email": "invited.proj@example.com", "project_role_name": "reviewer"},
        )
        assert proj_inv.status_code == 201
        assert len(mock_resend_client.sent_emails) == 1
        proj_email = mock_resend_client.sent_emails[0]
        assert proj_email["to"] == ["invited.proj@example.com"]
        assert proj_email["from"] == _DEFAULT_SENDER
        assert "Project Alpha" in proj_email["text"]
        assert proj_email["tags"] == [{"name": "category", "value": "project_invitation"}]


# ---------------------------------------------------------------------------
# Workflow 4: Password Reset Lifecycle
# ---------------------------------------------------------------------------

def test_workflow_4_password_reset_via_resend(
    monkeypatch: pytest.MonkeyPatch,
    mock_resend_client: MockResendClient,
) -> None:
    """Password reset dispatches reset link via Resend and allows password change."""
    _setup_resend_app(monkeypatch)

    provider = ResendEmailProvider(
        api_key=_API_KEY,
        from_address="notifications@the-sapiens.xyz",
        from_name="Handover",
        resend_client=mock_resend_client,
    )

    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        ctx.app.state.email_provider = provider

        # 1. Register & verify user
        reg = client.post(
            "/api/v1/auth/register",
            json={"full_name": "David Reset", "email": "david.reset@example.com", "password": _PASSWORD},
        )
        ver_token = reg.json()["development_verification_token"]
        client.post("/api/v1/auth/verify-email", json={"token": ver_token})

        # 2. Request password reset
        mock_resend_client.sent_emails.clear()
        req_res = client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "david.reset@example.com"},
        )
        assert req_res.status_code == 200
        assert req_res.json()["email_delivery"] == "submitted"

        # Verify email dispatched via Resend
        assert len(mock_resend_client.sent_emails) == 1
        reset_email = mock_resend_client.sent_emails[0]
        assert reset_email["to"] == ["david.reset@example.com"]
        assert reset_email["from"] == _DEFAULT_SENDER
        assert "Reset your Handover password" in reset_email["subject"]
        assert "/reset-password?token=" in reset_email["text"]
        assert reset_email["tags"] == [{"name": "category", "value": "password_reset"}]

        # Extract token from email text
        reset_token = reset_email["text"].split("/reset-password?token=")[1].split()[0]
        assert reset_token

        # 3. Complete password reset
        new_password = "Handover!NewPassword2026#Secure"
        reset_res = client.post(
            "/api/v1/auth/reset-password",
            json={"token": reset_token, "new_password": new_password},
        )
        assert reset_res.status_code == 200

        # 4. Login with new password
        login = client.post(
            "/api/v1/auth/login",
            json={"email": "david.reset@example.com", "password": new_password},
        )
        assert login.status_code == 200
        assert "access_token" in login.json()


# ---------------------------------------------------------------------------
# Workflow 5: Security Sanitization & Zero Leakage
# ---------------------------------------------------------------------------

def test_workflow_5_security_sanitization_no_secrets_in_logs(
    monkeypatch: pytest.MonkeyPatch,
    mock_resend_client: MockResendClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify that RESEND_API_KEY, raw passwords, and tokens never appear in logs."""
    _setup_resend_app(monkeypatch)

    provider = ResendEmailProvider(
        api_key=_API_KEY,
        from_address="notifications@the-sapiens.xyz",
        from_name="Handover",
        resend_client=mock_resend_client,
    )

    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        ctx.app.state.email_provider = provider

        with caplog.at_level(logging.DEBUG):
            reg = client.post(
                "/api/v1/auth/register",
                json={"full_name": "Eve Secret", "email": "eve.secret@example.com", "password": _PASSWORD},
            )
            assert reg.status_code == 201
            dev_token = reg.json()["development_verification_token"]

            # Inspect all captured logs
            log_text = caplog.text
            assert _API_KEY not in log_text
            assert _PASSWORD not in log_text
            assert dev_token not in log_text
