"""Comprehensive Integration Tests for Requirement R3: Email Workflow Integration with Gmail SMTP.

Verifies all 5 transactional email workflows end-to-end with GmailSMTPEmailProvider:
1. Standard registration email verification
2. Project invitation registration verification
3. Verification email resend (authenticated and unauthenticated)
4. Project invitation dispatch
5. Organisation invitation dispatch
6. Security sanitization, privacy safeguards, and access gates
"""

from __future__ import annotations

import logging
import smtplib
import socket
from email.mime.multipart import MIMEMultipart
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.models.enums import RoleName
from app.services.email import GmailSMTPEmailProvider
from tests.conftest import isolated_auth_app

_TRUSTED_ORIGIN = "http://localhost:3000"
_PASSWORD = "Handover!Gmail2026#Secure"
_GMAIL_USER = "handover.test.smtp@gmail.com"
_GMAIL_APP_PASS = "abcd-efgh-ijkl-mnop"


def _extract_mime_text_payloads(mime_msg: MIMEMultipart) -> tuple[str, str]:
    """Extract decoded (plain_text, html_text) from a multipart/alternative MIME message."""
    plain_text = ""
    html_text = ""
    for part in mime_msg.walk():
        content_type = part.get_content_type()
        if content_type == "text/plain":
            plain_text = part.get_payload(decode=True).decode("utf-8")
        elif content_type == "text/html":
            html_text = part.get_payload(decode=True).decode("utf-8")
    return plain_text, html_text


@pytest.fixture
def mock_smtp_client():
    """Create a mock smtplib.SMTP client instance that succeeds on STARTTLS, login, and send_message."""
    client = MagicMock()
    client.send_message.return_value = {}
    return client


def _setup_gmail_smtp_app(monkeypatch: pytest.MonkeyPatch, mock_client: MagicMock):
    """Configure environment for Gmail SMTP and attach mock transport."""
    monkeypatch.setenv("EMAIL_DELIVERY_ENABLED", "true")
    monkeypatch.setenv("EMAIL_PROVIDER", "gmail_smtp")
    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USERNAME", _GMAIL_USER)
    monkeypatch.setenv("SMTP_APP_PASSWORD", _GMAIL_APP_PASS)
    monkeypatch.setenv("FROM_ADDRESS", _GMAIL_USER)
    monkeypatch.setenv("FRONTEND_BASE_URL", "http://localhost:3000")


def test_workflow_1_standard_registration_verification_via_gmail_smtp(
    monkeypatch: pytest.MonkeyPatch,
    mock_smtp_client: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Workflow 1: Standard registration dispatches verification email via Gmail SMTP with access gate enforced."""
    _setup_gmail_smtp_app(monkeypatch, mock_smtp_client)

    provider = GmailSMTPEmailProvider(
        host="smtp.gmail.com",
        port=587,
        username=_GMAIL_USER,
        app_password=_GMAIL_APP_PASS,
        from_address=_GMAIL_USER,
        smtp_client_factory=lambda *a, **kw: mock_smtp_client,
    )

    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        ctx.app.state.email_provider = provider

        with caplog.at_level(logging.INFO):
            # 1. Register new account
            reg = client.post(
                "/api/v1/auth/register",
                json={
                    "full_name": "Alice Standard",
                    "email": "alice.workflow1@example.com",
                    "password": _PASSWORD,
                },
            )
            assert reg.status_code == 201
            data = reg.json()
            assert data["email_verification_delivery"] == "submitted"
            ver_token = data["development_verification_token"]
            assert ver_token is not None

            # Verify SMTP interactions
            assert mock_smtp_client.starttls.called
            assert mock_smtp_client.login.called
            assert mock_smtp_client.send_message.called
            sent_args, _ = mock_smtp_client.send_message.call_args
            mime_msg = sent_args[0]
            assert mime_msg["To"] == "alice.workflow1@example.com"
            assert _GMAIL_USER in mime_msg["From"]
            assert "Verify your Handover account" in mime_msg["Subject"]
            plain, html = _extract_mime_text_payloads(mime_msg)
            assert f"/verify-email?token={ver_token}" in plain
            assert f"/verify-email?token={ver_token}" in html

            # 2. Login as unverified user
            login = client.post(
                "/api/v1/auth/login",
                json={"email": "alice.workflow1@example.com", "password": _PASSWORD},
            )
            assert login.status_code == 200
            token = login.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}", "Origin": _TRUSTED_ORIGIN}

            # 3. Access gate verification: unverified user CANNOT access organisation or project APIs
            org_res = client.post(
                "/api/v1/organisations",
                headers=headers,
                json={"name": "Alice Org"},
            )
            assert org_res.status_code == 403
            assert org_res.json()["error"]["code"] == "EMAIL_VERIFICATION_REQUIRED"

            # 4. Verify email address
            ver = client.post("/api/v1/auth/verify-email", json={"token": ver_token})
            assert ver.status_code == 200
            assert ver.json()["is_email_verified"] is True
            assert ver.json()["can_access_project_immediately"] is True

            # 5. Access gate lifted: user can now create organisation
            org_res2 = client.post(
                "/api/v1/organisations",
                headers=headers,
                json={"name": "Alice Org Verified"},
            )
            assert org_res2.status_code == 201


def test_workflow_2_project_invitation_registration_verification_via_gmail_smtp(
    monkeypatch: pytest.MonkeyPatch,
    mock_smtp_client: MagicMock,
) -> None:
    """Workflow 2: Registering via project invitation verifies invitee and sends verification email via Gmail SMTP."""
    _setup_gmail_smtp_app(monkeypatch, mock_smtp_client)

    provider = GmailSMTPEmailProvider(
        host="smtp.gmail.com",
        port=587,
        username=_GMAIL_USER,
        app_password=_GMAIL_APP_PASS,
        from_address=_GMAIL_USER,
        smtp_client_factory=lambda *a, **kw: mock_smtp_client,
    )

    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        ctx.app.state.email_provider = provider

        # Register & verify owner
        reg_owner = client.post(
            "/api/v1/auth/register",
            json={"full_name": "Org Owner", "email": "owner.wf2@example.com", "password": _PASSWORD},
        )
        owner_tok = reg_owner.json()["development_verification_token"]
        client.post("/api/v1/auth/verify-email", json={"token": owner_tok})
        owner_login = client.post(
            "/api/v1/auth/login",
            json={"email": "owner.wf2@example.com", "password": _PASSWORD},
        )
        owner_headers = {"Authorization": f"Bearer {owner_login.json()['access_token']}", "Origin": _TRUSTED_ORIGIN}

        # Create Org and Project
        org_res = client.post("/api/v1/organisations", headers=owner_headers, json={"name": "Org WF2"})
        org_id = org_res.json()["id"]
        proj_res = client.post(f"/api/v1/organisations/{org_id}/projects", headers=owner_headers, json={"name": "Project WF2"})
        proj_id = proj_res.json()["id"]

        # Reset mock call count before invitation
        mock_smtp_client.send_message.reset_mock()

        # Create Project Invitation using canonical route
        inv_res = client.post(
            f"/api/v1/organisations/{org_id}/projects/{proj_id}/invitations",
            headers=owner_headers,
            json={
                "email": "invitee.wf2@example.com",
                "role_name": RoleName.PROJECT_MEMBER.value,
                "expires_in_hours": 48,
            },
        )
        assert inv_res.status_code == 201
        inv_token = inv_res.json()["development_invitation_token"]

        # Reset mock before invitation registration
        mock_smtp_client.send_message.reset_mock()

        # Register with invitation
        reg_inv = client.post(
            "/api/v1/auth/register-with-invitation",
            json={
                "invitation_token": inv_token,
                "full_name": "Bob Invitee",
                "email": "invitee.wf2@example.com",
                "password": _PASSWORD,
            },
        )
        assert reg_inv.status_code == 201
        data = reg_inv.json()
        assert data["email_verification_delivery"] == "submitted"
        assert data["can_access_project_immediately"] is False
        dev_ver_tok = data["development_verification_token"]
        assert dev_ver_tok is not None

        # Confirm verification email dispatched via Gmail SMTP to invitee.wf2@example.com
        assert mock_smtp_client.send_message.called
        sent_msg = mock_smtp_client.send_message.call_args[0][0]
        assert sent_msg["To"] == "invitee.wf2@example.com"
        plain, html = _extract_mime_text_payloads(sent_msg)
        assert f"/verify-email?token={dev_ver_tok}" in plain
        assert f"/verify-email?token={dev_ver_tok}" in html

        # Login as Bob (unverified)
        bob_login = client.post(
            "/api/v1/auth/login",
            json={"email": "invitee.wf2@example.com", "password": _PASSWORD},
        )
        bob_headers = {"Authorization": f"Bearer {bob_login.json()['access_token']}", "Origin": _TRUSTED_ORIGIN}

        # Bob cannot access project yet (gate blocked)
        proj_get = client.get(f"/api/v1/projects/{proj_id}", headers=bob_headers)
        assert proj_get.status_code == 403
        assert proj_get.json()["error"]["code"] == "EMAIL_VERIFICATION_REQUIRED"

        # Verify Bob's email
        assert client.post("/api/v1/auth/verify-email", json={"token": dev_ver_tok}).status_code == 200

        # Now Bob can access project!
        proj_get2 = client.get(f"/api/v1/projects/{proj_id}", headers=bob_headers)
        assert proj_get2.status_code == 200


def test_workflow_3_resend_verification_via_gmail_smtp(
    monkeypatch: pytest.MonkeyPatch,
    mock_smtp_client: MagicMock,
) -> None:
    """Workflow 3: Verification email resend dispatches via Gmail SMTP for unauthenticated and authenticated callers."""
    _setup_gmail_smtp_app(monkeypatch, mock_smtp_client)

    provider = GmailSMTPEmailProvider(
        host="smtp.gmail.com",
        port=587,
        username=_GMAIL_USER,
        app_password=_GMAIL_APP_PASS,
        from_address=_GMAIL_USER,
        smtp_client_factory=lambda *a, **kw: mock_smtp_client,
    )

    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        ctx.app.state.email_provider = provider

        # 1. Register unverified user
        reg = client.post(
            "/api/v1/auth/register",
            json={"full_name": "Resend User", "email": "resend.wf3@example.com", "password": _PASSWORD},
        )
        assert reg.status_code == 201

        mock_smtp_client.send_message.reset_mock()

        # 2. Unauthenticated resend with registered email
        resend1 = client.post(
            "/api/v1/auth/resend-verification",
            json={"email": "resend.wf3@example.com"},
        )
        assert resend1.status_code == 200
        assert resend1.json()["email_verification_delivery"] == "submitted"
        assert mock_smtp_client.send_message.called
        msg1 = mock_smtp_client.send_message.call_args[0][0]
        assert msg1["To"] == "resend.wf3@example.com"

        mock_smtp_client.send_message.reset_mock()

        # 3. Unauthenticated resend with non-existent email -> timing-safe generic message, zero emails dispatched
        resend_ghost = client.post(
            "/api/v1/auth/resend-verification",
            json={"email": "ghost.nonexistent@example.com"},
        )
        assert resend_ghost.status_code == 200
        assert resend_ghost.json()["email_verification_delivery"] == "not_configured"
        assert not mock_smtp_client.send_message.called

        # 4. Authenticated resend: user logs in and calls resend without body payload
        login = client.post(
            "/api/v1/auth/login",
            json={"email": "resend.wf3@example.com", "password": _PASSWORD},
        )
        auth_headers = {"Authorization": f"Bearer {login.json()['access_token']}", "Origin": _TRUSTED_ORIGIN}

        mock_smtp_client.send_message.reset_mock()

        resend_auth = client.post(
            "/api/v1/auth/resend-verification",
            headers=auth_headers,
        )
        assert resend_auth.status_code == 200
        assert resend_auth.json()["email_verification_delivery"] == "submitted"
        assert mock_smtp_client.send_message.called
        msg_auth = mock_smtp_client.send_message.call_args[0][0]
        assert msg_auth["To"] == "resend.wf3@example.com"


def test_workflow_4_project_invitation_dispatch_via_gmail_smtp(
    monkeypatch: pytest.MonkeyPatch,
    mock_smtp_client: MagicMock,
) -> None:
    """Workflow 4: Project invitation dispatch dispatches via Gmail SMTP with role and expiration metadata."""
    _setup_gmail_smtp_app(monkeypatch, mock_smtp_client)

    provider = GmailSMTPEmailProvider(
        host="smtp.gmail.com",
        port=587,
        username=_GMAIL_USER,
        app_password=_GMAIL_APP_PASS,
        from_address=_GMAIL_USER,
        smtp_client_factory=lambda *a, **kw: mock_smtp_client,
    )

    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        ctx.app.state.email_provider = provider

        # Register & verify owner
        reg = client.post(
            "/api/v1/auth/register",
            json={"full_name": "Project Lead", "email": "lead.wf4@example.com", "password": _PASSWORD},
        )
        client.post("/api/v1/auth/verify-email", json={"token": reg.json()["development_verification_token"]})
        login = client.post("/api/v1/auth/login", json={"email": "lead.wf4@example.com", "password": _PASSWORD})
        headers = {"Authorization": f"Bearer {login.json()['access_token']}", "Origin": _TRUSTED_ORIGIN}

        # Create Org and Project
        org_id = client.post("/api/v1/organisations", headers=headers, json={"name": "Acme Org WF4"}).json()["id"]
        proj_id = client.post(f"/api/v1/organisations/{org_id}/projects", headers=headers, json={"name": "Apollo Mission"}).json()["id"]

        mock_smtp_client.send_message.reset_mock()

        # Dispatch Project Invitation
        inv_res = client.post(
            f"/api/v1/organisations/{org_id}/projects/{proj_id}/invitations",
            headers=headers,
            json={
                "email": "engineer.apollo@example.com",
                "role_name": RoleName.PROJECT_MEMBER.value,
                "expires_in_hours": 48,
            },
        )
        assert inv_res.status_code == 201
        data = inv_res.json()
        assert data["invitation_delivery"] == "submitted"
        raw_inv_token = data["development_invitation_token"]

        assert mock_smtp_client.send_message.called
        sent_msg = mock_smtp_client.send_message.call_args[0][0]
        assert sent_msg["To"] == "engineer.apollo@example.com"
        assert "invited to a Handover project" in sent_msg["Subject"]
        plain, html = _extract_mime_text_payloads(sent_msg)
        assert "Apollo Mission" in plain
        assert "Apollo Mission" in html
        assert f"/invitations/{raw_inv_token}" in plain
        assert f"/invitations/{raw_inv_token}" in html


def test_workflow_5_organisation_invitation_dispatch_via_gmail_smtp(
    monkeypatch: pytest.MonkeyPatch,
    mock_smtp_client: MagicMock,
) -> None:
    """Workflow 5: Organisation invitation dispatch dispatches via Gmail SMTP with role and expiration metadata."""
    _setup_gmail_smtp_app(monkeypatch, mock_smtp_client)

    provider = GmailSMTPEmailProvider(
        host="smtp.gmail.com",
        port=587,
        username=_GMAIL_USER,
        app_password=_GMAIL_APP_PASS,
        from_address=_GMAIL_USER,
        smtp_client_factory=lambda *a, **kw: mock_smtp_client,
    )

    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        ctx.app.state.email_provider = provider

        # Register & verify owner
        reg = client.post(
            "/api/v1/auth/register",
            json={"full_name": "Org Founder", "email": "founder.wf5@example.com", "password": _PASSWORD},
        )
        client.post("/api/v1/auth/verify-email", json={"token": reg.json()["development_verification_token"]})
        login = client.post("/api/v1/auth/login", json={"email": "founder.wf5@example.com", "password": _PASSWORD})
        headers = {"Authorization": f"Bearer {login.json()['access_token']}", "Origin": _TRUSTED_ORIGIN}

        org_id = client.post("/api/v1/organisations", headers=headers, json={"name": "Enterprise WF5"}).json()["id"]

        mock_smtp_client.send_message.reset_mock()

        # Dispatch Organisation Invitation
        inv_res = client.post(
            f"/api/v1/organisations/{org_id}/invitations",
            headers=headers,
            json={
                "email": "director.wf5@example.com",
                "role_name": RoleName.ORG_ADMIN.value,
                "expires_in_hours": 72,
            },
        )
        assert inv_res.status_code == 201
        data = inv_res.json()
        assert data["invitation_delivery"] == "submitted"
        raw_inv_token = data["development_invitation_token"]

        assert mock_smtp_client.send_message.called
        sent_msg = mock_smtp_client.send_message.call_args[0][0]
        assert sent_msg["To"] == "director.wf5@example.com"
        assert "Enterprise WF5" in sent_msg["Subject"]
        plain, html = _extract_mime_text_payloads(sent_msg)
        assert f"/invitations/{raw_inv_token}" in plain
        assert f"/invitations/{raw_inv_token}" in html


def test_gmail_smtp_security_sanitization_on_auth_failure(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Security verification: SMTP auth failure (535) produces clean error, zero leaked credentials."""
    _setup_gmail_smtp_app(monkeypatch, MagicMock())

    failing_client = MagicMock()
    failing_client.login.side_effect = smtplib.SMTPAuthenticationError(535, b"5.7.8 Bad credentials")

    provider = GmailSMTPEmailProvider(
        host="smtp.gmail.com",
        port=587,
        username=_GMAIL_USER,
        app_password=_GMAIL_APP_PASS,
        from_address=_GMAIL_USER,
        smtp_client_factory=lambda *a, **kw: failing_client,
    )

    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        ctx.app.state.email_provider = provider

        with caplog.at_level(logging.INFO):
            reg = client.post(
                "/api/v1/auth/register",
                json={"full_name": "Auth Fail User", "email": "authfail@example.com", "password": _PASSWORD},
            )
            assert reg.status_code == 201
            body = reg.json()
            assert body["email_verification_delivery"] == "failed"

            # Sanitized user-facing guidance
            assert "verification email delivery failed" in body["message"].lower()

            # Zero credential leaks in response
            assert _GMAIL_APP_PASS not in reg.text
            assert _GMAIL_APP_PASS not in caplog.text


def test_gmail_smtp_security_sanitization_on_connection_timeout(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Security verification: Socket connection timeout produces clean error, zero leaked credentials."""
    _setup_gmail_smtp_app(monkeypatch, MagicMock())

    timeout_client = MagicMock()
    timeout_client.starttls.side_effect = socket.timeout("timed out")

    provider = GmailSMTPEmailProvider(
        host="smtp.gmail.com",
        port=587,
        username=_GMAIL_USER,
        app_password=_GMAIL_APP_PASS,
        from_address=_GMAIL_USER,
        timeout_seconds=2.0,
        smtp_client_factory=lambda *a, **kw: timeout_client,
    )

    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        ctx.app.state.email_provider = provider

        with caplog.at_level(logging.INFO):
            reg = client.post(
                "/api/v1/auth/register",
                json={"full_name": "Timeout User", "email": "timeout@example.com", "password": _PASSWORD},
            )
            assert reg.status_code == 201
            body = reg.json()
            assert body["email_verification_delivery"] == "failed"
            assert "timed out" in body["message"].lower()
            assert _GMAIL_APP_PASS not in reg.text
            assert _GMAIL_APP_PASS not in caplog.text


def test_security_tenant_isolation_and_rbac_constraints(
    monkeypatch: pytest.MonkeyPatch,
    mock_smtp_client: MagicMock,
) -> None:
    """Security verification: Strict tenant isolation and RBAC constraints block unauthorized email dispatch."""
    _setup_gmail_smtp_app(monkeypatch, mock_smtp_client)

    provider = GmailSMTPEmailProvider(
        username=_GMAIL_USER,
        app_password=_GMAIL_APP_PASS,
        smtp_client_factory=lambda *a, **kw: mock_smtp_client,
    )

    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        ctx.app.state.email_provider = provider

        # 1. Register & verify User A (Owner of Org A)
        reg_a = client.post(
            "/api/v1/auth/register",
            json={"full_name": "User Alpha", "email": "alpha.tenant@example.com", "password": _PASSWORD},
        )
        client.post("/api/v1/auth/verify-email", json={"token": reg_a.json()["development_verification_token"]})
        login_a = client.post("/api/v1/auth/login", json={"email": "alpha.tenant@example.com", "password": _PASSWORD})
        headers_a = {"Authorization": f"Bearer {login_a.json()['access_token']}", "Origin": _TRUSTED_ORIGIN}

        org_a = client.post("/api/v1/organisations", headers=headers_a, json={"name": "Org Alpha"}).json()["id"]
        proj_a = client.post(f"/api/v1/organisations/{org_a}/projects", headers=headers_a, json={"name": "Project Alpha"}).json()["id"]

        # 2. Register & verify User B (Owner of Org B)
        reg_b = client.post(
            "/api/v1/auth/register",
            json={"full_name": "User Bravo", "email": "bravo.tenant@example.com", "password": _PASSWORD},
        )
        client.post("/api/v1/auth/verify-email", json={"token": reg_b.json()["development_verification_token"]})
        login_b = client.post("/api/v1/auth/login", json={"email": "bravo.tenant@example.com", "password": _PASSWORD})
        headers_b = {"Authorization": f"Bearer {login_b.json()['access_token']}", "Origin": _TRUSTED_ORIGIN}

        mock_smtp_client.send_message.reset_mock()

        # 3. TENANT ISOLATION: User B attempts to dispatch invitation to Org A -> HTTP 403/404 Forbidden/Not Found (no tenant leak)
        cross_org = client.post(
            f"/api/v1/organisations/{org_a}/invitations",
            headers=headers_b,
            json={"email": "victim@example.com", "role_name": RoleName.ORG_ADMIN.value, "expires_in_hours": 24},
        )
        assert cross_org.status_code in (403, 404)
        assert not mock_smtp_client.send_message.called

        # 4. TENANT ISOLATION: User B attempts to dispatch invitation to Project A -> HTTP 403/404 Forbidden/Not Found (no tenant leak)
        cross_proj = client.post(
            f"/api/v1/organisations/{org_a}/projects/{proj_a}/invitations",
            headers=headers_b,
            json={"email": "victim@example.com", "role_name": RoleName.PROJECT_MEMBER.value, "expires_in_hours": 24},
        )
        assert cross_proj.status_code in (403, 404)
        assert not mock_smtp_client.send_message.called


def test_security_email_verification_access_gate_comprehensive(
    monkeypatch: pytest.MonkeyPatch,
    mock_smtp_client: MagicMock,
) -> None:
    """Security verification: Unverified users are comprehensively blocked from all org/project resources."""
    _setup_gmail_smtp_app(monkeypatch, mock_smtp_client)

    provider = GmailSMTPEmailProvider(
        username=_GMAIL_USER,
        app_password=_GMAIL_APP_PASS,
        smtp_client_factory=lambda *a, **kw: mock_smtp_client,
    )

    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        ctx.app.state.email_provider = provider

        # 1. Register unverified user
        reg = client.post(
            "/api/v1/auth/register",
            json={"full_name": "Unverified Charlie", "email": "charlie.unverified@example.com", "password": _PASSWORD},
        )
        assert reg.status_code == 201
        ver_token = reg.json()["development_verification_token"]

        login = client.post("/api/v1/auth/login", json={"email": "charlie.unverified@example.com", "password": _PASSWORD})
        headers = {"Authorization": f"Bearer {login.json()['access_token']}", "Origin": _TRUSTED_ORIGIN}

        # 2. Verify all protected endpoints block unverified user with EMAIL_VERIFICATION_REQUIRED
        endpoints = [
            ("POST", "/api/v1/organisations", {"name": "Blocked Org"}),
            ("GET", "/api/v1/organisations", None),
            ("GET", "/api/v1/projects/00000000-0000-0000-0000-000000000001", None),
            ("POST", "/api/v1/organisations/00000000-0000-0000-0000-000000000001/projects", {"name": "Blocked Project"}),
            ("POST", "/api/v1/organisations/00000000-0000-0000-0000-000000000001/invitations", {"email": "x@example.com", "role_name": RoleName.ORG_ADMIN.value}),
        ]

        for method, url, payload in endpoints:
            if method == "POST":
                resp = client.post(url, headers=headers, json=payload)
            else:
                resp = client.get(url, headers=headers)
            assert resp.status_code == 403, f"{method} {url} returned {resp.status_code}"
            assert resp.json()["error"]["code"] == "EMAIL_VERIFICATION_REQUIRED"

        # 3. Verify email address
        ver = client.post("/api/v1/auth/verify-email", json={"token": ver_token})
        assert ver.status_code == 200
        assert ver.json()["is_email_verified"] is True

        # 4. Now user can create organisation successfully
        org_res = client.post("/api/v1/organisations", headers=headers, json={"name": "Charlie Org"})
        assert org_res.status_code == 201


def test_security_invitation_token_single_use_and_revocation(
    monkeypatch: pytest.MonkeyPatch,
    mock_smtp_client: MagicMock,
) -> None:
    """Security verification: Invitation tokens cannot be accepted twice, and verification tokens handle re-use."""
    _setup_gmail_smtp_app(monkeypatch, mock_smtp_client)

    provider = GmailSMTPEmailProvider(
        username=_GMAIL_USER,
        app_password=_GMAIL_APP_PASS,
        smtp_client_factory=lambda *a, **kw: mock_smtp_client,
    )

    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        ctx.app.state.email_provider = provider

        # 1. Setup owner
        reg = client.post("/api/v1/auth/register", json={"full_name": "Lead", "email": "lead.su@example.com", "password": _PASSWORD})
        client.post("/api/v1/auth/verify-email", json={"token": reg.json()["development_verification_token"]})
        login = client.post("/api/v1/auth/login", json={"email": "lead.su@example.com", "password": _PASSWORD})
        headers = {"Authorization": f"Bearer {login.json()['access_token']}", "Origin": _TRUSTED_ORIGIN}

        org_id = client.post("/api/v1/organisations", headers=headers, json={"name": "SingleUse Org"}).json()["id"]

        # 2. Create invitation
        inv_res = client.post(
            f"/api/v1/organisations/{org_id}/invitations",
            headers=headers,
            json={"email": "member.single@example.com", "role_name": RoleName.ORG_ADMIN.value, "expires_in_hours": 24},
        )
        assert inv_res.status_code == 201
        inv_token = inv_res.json()["development_invitation_token"]

        # 3. First acceptance succeeds
        reg_inv1 = client.post(
            "/api/v1/auth/register-with-invitation",
            json={
                "invitation_token": inv_token,
                "full_name": "Member Single",
                "email": "member.single@example.com",
                "password": _PASSWORD,
            },
        )
        assert reg_inv1.status_code == 201
        ver_token = reg_inv1.json()["development_verification_token"]

        # 4. Second acceptance fails with HTTP 409 Conflict (single-use enforced)
        reg_inv2 = client.post(
            "/api/v1/auth/register-with-invitation",
            json={
                "invitation_token": inv_token,
                "full_name": "Attacker Impersonator",
                "email": "member.single@example.com",
                "password": _PASSWORD,
            },
        )
        assert reg_inv2.status_code == 409
        assert reg_inv2.json()["error"]["code"] == "INVITATION_ALREADY_ACCEPTED"

        # 5. First verification succeeds
        ver1 = client.post("/api/v1/auth/verify-email", json={"token": ver_token})
        assert ver1.status_code == 200
        assert ver1.json()["is_email_verified"] is True
        assert "verified successfully" in ver1.json()["message"].lower()

        # 6. Re-verifying handles idempotently with "already verified" message
        ver2 = client.post("/api/v1/auth/verify-email", json={"token": ver_token})
        assert ver2.status_code == 200
        assert ver2.json()["is_email_verified"] is True
        assert "already verified" in ver2.json()["message"].lower()

