"""Tests for Phase 4.3 transactional email delivery and Phase 6 invitation preview."""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import Settings
from app.core.security import utc_now
from app.models.enums import InvitationStatus
from app.models.organisation import OrganisationInvitation
from app.services.email import (
    EmailDeliveryResult,
    EmailMessage,
    MockEmailProvider,
    ResendEmailProvider,
    TransactionalEmailService,
)
from app.services.email.templates import render_password_reset
from tests.conftest import isolated_auth_app

_TRUSTED_ORIGIN = "http://localhost:3000"
_PASSWORD = "Handover!Email2026#Secure"


def _register_verify_login(
    client: TestClient,
    *,
    full_name: str,
    email: str,
) -> tuple[str, dict[str, str]]:
    reg = client.post(
        "/api/v1/auth/register",
        json={"full_name": full_name, "email": email, "password": _PASSWORD},
    )
    assert reg.status_code == 201
    token = reg.json()["development_verification_token"]
    assert token

    ver = client.post("/api/v1/auth/verify-email", json={"token": token})
    assert ver.status_code == 200

    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": _PASSWORD},
    )
    assert login.status_code == 200
    access = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {access}", "Origin": _TRUSTED_ORIGIN}
    return access, headers


def test_verification_and_invitation_emails_sent_via_mock_provider_without_token_leakage(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("EMAIL_DELIVERY_ENABLED", "true")
    monkeypatch.setenv("EMAIL_PROVIDER", "mock")
    monkeypatch.setenv("FRONTEND_BASE_URL", "http://localhost:3000")

    mock_provider = MockEmailProvider()

    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        ctx.app.state.email_provider = mock_provider

        with caplog.at_level(logging.INFO):
            # 1. Standard registration triggers verification email
            reg = client.post(
                "/api/v1/auth/register",
                json={
                    "full_name": "Alice Manager",
                    "email": "alice.manager@example.com",
                    "password": _PASSWORD,
                },
            )
            assert reg.status_code == 201
            reg_body = reg.json()
            assert reg_body["email_verification_delivery"] == "submitted"
            dev_ver_token = reg_body["development_verification_token"]
            assert dev_ver_token
            assert len(mock_provider.sent_messages) == 1
            ver_msg = mock_provider.sent_messages[0]
            assert ver_msg.to_email == "alice.manager@example.com"
            assert f"/verify-email?token={dev_ver_token}" in ver_msg.text_body
            assert f"/verify-email?token={dev_ver_token}" in ver_msg.html_body

            # Resend verification sends another email
            resend = client.post(
                "/api/v1/auth/resend-verification",
                json={"email": "alice.manager@example.com"},
            )
            assert resend.status_code == 200
            assert resend.json()["email_verification_delivery"] == "submitted"
            assert len(mock_provider.sent_messages) == 2

            # Verify and login Alice
            assert client.post("/api/v1/auth/verify-email", json={"token": dev_ver_token}).status_code == 200
            login = client.post(
                "/api/v1/auth/login",
                json={"email": "alice.manager@example.com", "password": _PASSWORD},
            )
            assert login.status_code == 200
            headers = {
                "Authorization": f"Bearer {login.json()['access_token']}",
                "Origin": _TRUSTED_ORIGIN,
            }

            # 2. Create org & project, then invite Bob to the project
            org_resp = client.post(
                "/api/v1/organisations",
                headers=headers,
                json={"name": "Acme Handover Org"},
            )
            assert org_resp.status_code == 201
            org_id = org_resp.json()["id"]

            proj_resp = client.post(
                f"/api/v1/organisations/{org_id}/projects",
                headers=headers,
                json={"name": "Phoenix Migration", "description": "Core system handover"},
            )
            assert proj_resp.status_code == 201
            project_id = proj_resp.json()["id"]

            inv_resp = client.post(
                f"/api/v1/organisations/{org_id}/projects/{project_id}/invitations",
                headers=headers,
                json={"email": "bob.successor@example.com", "role_name": "project_member"},
            )
            assert inv_resp.status_code == 201
            inv_body = inv_resp.json()
            assert inv_body["invitation_delivery"] == "submitted"
            inv_token = inv_body["development_invitation_token"]
            assert inv_token
            assert len(mock_provider.sent_messages) == 3

            inv_msg = mock_provider.sent_messages[2]
            assert inv_msg.to_email == "bob.successor@example.com"
            assert "invited to" in inv_msg.subject.lower()
            assert "Phoenix Migration" in inv_msg.text_body
            assert "Acme Handover Org" in inv_msg.text_body
            assert "project member" in inv_msg.text_body.lower()
            assert f"/invitations/{inv_token}" in inv_msg.text_body

            # 3. Registration with invitation also sends verification email
            reg_inv = client.post(
                "/api/v1/auth/register-with-invitation",
                json={
                    "invitation_token": inv_token,
                    "full_name": "Bob Successor",
                    "password": _PASSWORD,
                },
            )
            assert reg_inv.status_code == 201
            reg_inv_body = reg_inv.json()
            assert reg_inv_body["email_verification_delivery"] == "submitted"
            bob_ver_token = reg_inv_body["development_verification_token"]
            assert len(mock_provider.sent_messages) == 4
            assert f"/verify-email?token={bob_ver_token}" in mock_provider.sent_messages[3].text_body

            # Raw tokens must never appear in logs
            assert dev_ver_token not in caplog.text
            assert inv_token not in caplog.text
            assert bob_ver_token not in caplog.text


def test_resend_provider_handles_success_http_error_timeout_and_missing_key() -> None:
    msg = EmailMessage(
        to_email="user@example.com",
        subject="Verify your email",
        html_body="<p>Hello</p>",
        text_body="Hello",
    )

    # 1. Missing API key fails gracefully
    missing_key_provider = ResendEmailProvider(
        api_key=None,
        from_address="noreply@example.com",
        from_name="The Handover",
    )
    res_missing = missing_key_provider.send(msg)
    assert res_missing.status == "failed"
    assert res_missing.error_message and "not configured" in res_missing.error_message.lower()

    # 2. HTTP 200 success with mocked transport
    def ok_handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer re_test_key"
        return httpx.Response(200, json={"id": "msg_123"})

    ok_provider = ResendEmailProvider(
        api_key="re_test_key",
        from_address="noreply@example.com",
        from_name="The Handover",
        http_client=httpx.Client(transport=httpx.MockTransport(ok_handler)),
    )
    res_ok = ok_provider.send(msg)
    assert res_ok == EmailDeliveryResult(
        status="submitted",
        provider="resend",
        provider_message_id="msg_123",
    )

    # 3. HTTP 422 / 500 error fails gracefully without throwing
    def err_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"message": "Invalid from domain"})

    err_provider = ResendEmailProvider(
        api_key="re_test_key",
        from_address="noreply@example.com",
        from_name="The Handover",
        http_client=httpx.Client(transport=httpx.MockTransport(err_handler)),
    )
    res_err = err_provider.send(msg)
    assert res_err.status == "failed"
    assert res_err.error_message and "422" in res_err.error_message

    # 4. Timeout fails gracefully without throwing
    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    timeout_provider = ResendEmailProvider(
        api_key="re_test_key",
        from_address="noreply@example.com",
        from_name="The Handover",
        http_client=httpx.Client(transport=httpx.MockTransport(timeout_handler)),
    )
    res_timeout = timeout_provider.send(msg)
    assert res_timeout.status == "failed"
    assert res_timeout.error_message and "timed out" in res_timeout.error_message.lower()


def test_email_delivery_failure_does_not_abort_registration_or_invitation_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EMAIL_DELIVERY_ENABLED", "true")
    monkeypatch.setenv("EMAIL_PROVIDER", "resend")
    monkeypatch.delenv("RESEND_API_KEY", raising=False)

    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        reg = client.post(
            "/api/v1/auth/register",
            json={
                "full_name": "Fallback User",
                "email": "fallback@example.com",
                "password": _PASSWORD,
            },
        )
        assert reg.status_code == 201
        assert reg.json()["email_verification_delivery"] == "failed"


def test_production_email_settings_require_https_frontend_url() -> None:
    settings = Settings(
        app_env="production",
        database_url="postgresql+psycopg://postgres:postgres@localhost:5432/handover",
        jwt_secret_key="x" * 64,
        token_encryption_key="MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
        cookie_secure=True,
        email_delivery_enabled=True,
        email_provider="resend",
        resend_api_key="re_live_123",
        frontend_base_url="http://localhost:3000",
    )
    with pytest.raises(ValueError, match="https://"):
        _ = settings.email


def test_invitation_preview_endpoint_states(monkeypatch: pytest.MonkeyPatch) -> None:
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        _, headers = _register_verify_login(
            client,
            full_name="Owner User",
            email="owner.preview@example.com",
        )
        org = client.post("/api/v1/organisations", headers=headers, json={"name": "Preview Org"}).json()
        project = client.post(
            f"/api/v1/organisations/{org['id']}/projects",
            headers=headers,
            json={"name": "Preview Project"},
        ).json()

        # 1. Valid pending project invitation
        inv1 = client.post(
            f"/api/v1/organisations/{org['id']}/projects/{project['id']}/invitations",
            headers=headers,
            json={"email": "invitee1@example.com", "role_name": "project_manager"},
        ).json()
        tok1 = inv1["development_invitation_token"]
        prev1 = client.get(f"/api/v1/invitations/{tok1}")
        assert prev1.status_code == 200
        p1 = prev1.json()
        assert p1["email"] == "invitee1@example.com"
        assert p1["organisation_name"] == "Preview Org"
        assert p1["project_name"] == "Preview Project"
        assert p1["project_role_name"] == "project_manager"
        assert p1["inviter_name"] == "Owner User"
        assert p1["status"] == "pending"
        assert p1["is_actionable"] is True
        assert "has_existing_account" not in p1

        # 2. Revoked invitation preview
        inv1_id = inv1["invitation"]["id"]
        rev = client.delete(
            f"/api/v1/organisations/{org['id']}/projects/{project['id']}/invitations/{inv1_id}",
            headers=headers,
        )
        assert rev.status_code == 200
        prev1_rev = client.get(f"/api/v1/invitations/{tok1}")
        assert prev1_rev.status_code == 200
        assert prev1_rev.json()["status"] == "revoked"
        assert prev1_rev.json()["is_actionable"] is False

        # 3. Expired invitation preview
        inv2 = client.post(
            f"/api/v1/organisations/{org['id']}/projects/{project['id']}/invitations",
            headers=headers,
            json={"email": "invitee2@example.com", "role_name": "reviewer"},
        ).json()
        tok2 = inv2["development_invitation_token"]
        with ctx.session_factory() as db:
            row = db.execute(
                select(OrganisationInvitation).where(
                    OrganisationInvitation.id == uuid.UUID(inv2["invitation"]["id"])
                )
            ).scalar_one()
            row.expires_at = utc_now() - timedelta(hours=2)
            row.status = InvitationStatus.PENDING.value
            db.commit()

        prev2 = client.get(f"/api/v1/invitations/{tok2}")
        assert prev2.status_code == 200
        assert prev2.json()["status"] == "expired"
        assert prev2.json()["is_actionable"] is False

        # 4. Unknown token returns 404
        missing = client.get("/api/v1/invitations/nonexistent-token-value")
        assert missing.status_code == 404


def test_resend_provider_parses_testing_domain_and_unverified_domain_errors() -> None:
    msg = EmailMessage(
        to_email="colleague@example.com",
        subject="Verify your email",
        html_body="<p>Link</p>",
        text_body="Link",
    )

    # 1. Resend sandbox testing domain limitation (422)
    def sandbox_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={
                "statusCode": 422,
                "name": "validation_error",
                "message": "You can only send testing emails to your own email address (owner@domain.com) while using onboarding@resend.dev.",
            },
        )

    provider_sandbox = ResendEmailProvider(
        api_key="re_test_key",
        from_address="onboarding@resend.dev",
        from_name="The Handover",
        http_client=httpx.Client(transport=httpx.MockTransport(sandbox_handler)),
    )
    res_sandbox = provider_sandbox.send(msg)
    assert res_sandbox.status == "failed"
    assert "Resend sandbox limitation" in res_sandbox.error_message
    assert "resend.com/domains" in res_sandbox.error_message

    # 2. Resend unverified custom domain error (403)
    def domain_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={
                "statusCode": 403,
                "name": "validation_error",
                "message": "The domain mycustomdomain.com is not verified. Please verify your domain in the dashboard.",
            },
        )

    provider_domain = ResendEmailProvider(
        api_key="re_test_key",
        from_address="noreply@mycustomdomain.com",
        from_name="The Handover",
        http_client=httpx.Client(transport=httpx.MockTransport(domain_handler)),
    )
    res_domain = provider_domain.send(msg)
    assert res_domain.status == "failed"
    assert "Resend sender domain error" in res_domain.error_message
    assert "onboarding@resend.dev" in res_domain.error_message


def test_authenticated_resend_verification_uses_persisted_user_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EMAIL_DELIVERY_ENABLED", "true")
    monkeypatch.setenv("EMAIL_PROVIDER", "mock")
    monkeypatch.setenv("FRONTEND_BASE_URL", "http://localhost:3000")

    mock_provider = MockEmailProvider()

    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        ctx.app.state.email_provider = mock_provider

        # 1. Register unverified user
        reg = client.post(
            "/api/v1/auth/register",
            json={
                "full_name": "Charlie Unverified",
                "email": "charlie@trusted.org",
                "password": _PASSWORD,
            },
        )
        assert reg.status_code == 201

        # 2. Login to get authenticated session while unverified
        login = client.post(
            "/api/v1/auth/login",
            json={"email": "charlie@trusted.org", "password": _PASSWORD},
        )
        assert login.status_code == 200
        auth_token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {auth_token}", "Origin": _TRUSTED_ORIGIN}

        # Clear registration email from mock sent list
        mock_provider.sent_messages.clear()

        # 3. Authenticated resend with spoofed email in body — must ignore body and use charlie@trusted.org
        resend_spoofed = client.post(
            "/api/v1/auth/resend-verification",
            headers=headers,
            json={"email": "attacker@victim.com"},
        )
        assert resend_spoofed.status_code == 200
        assert resend_spoofed.json()["email_verification_delivery"] == "submitted"
        assert len(mock_provider.sent_messages) == 1
        assert mock_provider.sent_messages[0].to_email == "charlie@trusted.org"

        # 4. Authenticated resend with empty body — succeeds and targets charlie@trusted.org
        resend_empty = client.post(
            "/api/v1/auth/resend-verification",
            headers=headers,
            json={},
        )
        assert resend_empty.status_code == 200
        assert resend_empty.json()["email_verification_delivery"] == "submitted"
        assert len(mock_provider.sent_messages) == 2
        assert mock_provider.sent_messages[1].to_email == "charlie@trusted.org"


def test_unauthenticated_resend_verification_requires_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        # Unauthenticated with empty body returns 400
        res = client.post("/api/v1/auth/resend-verification", json={})
        assert res.status_code == 400
        assert res.json()["error"]["code"] == "EMAIL_REQUIRED"


def test_resend_defaults_sender_to_onboarding_domain_when_local() -> None:
    # 1. When local/default from_address is used, fallback to onboarding@resend.dev
    settings_default = Settings(
        database_url="postgresql+psycopg://postgres:postgres@localhost:5432/handover",
        jwt_secret_key="x" * 64,
        token_encryption_key="MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
        email_provider="resend",
        email_from_address="noreply@handover.local",
    )
    assert settings_default.email.from_address == "onboarding@resend.dev"

    # 2. When a custom domain is explicitly configured, preserve it
    settings_custom = Settings(
        database_url="postgresql+psycopg://postgres:postgres@localhost:5432/handover",
        jwt_secret_key="x" * 64,
        token_encryption_key="MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
        email_provider="resend",
        email_from_address="notifications@mycompany.com",
    )
    assert settings_custom.email.from_address == "notifications@mycompany.com"


def test_render_password_reset_template() -> None:
    """Verify render_password_reset contains branding, secure reset URL, expiration, and security notices."""
    reset_url = "http://localhost:3000/reset-password?token=secret123"
    rendered = render_password_reset(
        reset_url=reset_url,
        recipient_name="Dana Scully",
        expires_in_minutes=30,
    )
    assert rendered.subject == "Reset your Handover password"
    # Branding colors
    assert "#1E3F35" in rendered.html_body
    assert "#2E6F5E" in rendered.html_body
    assert "#A7D7C5" in rendered.html_body
    assert "#245C4F" in rendered.html_body
    # Content and links
    assert "Reset Your Password" in rendered.html_body
    assert "Reset Password" in rendered.html_body
    assert "Dana Scully" in rendered.html_body
    assert reset_url in rendered.html_body
    assert "30 minutes" in rendered.html_body
    assert "Security notice" in rendered.html_body
    assert "If you did not request a password reset" in rendered.html_body
    # Plain text alternative
    assert reset_url in rendered.text_body
    assert "30 minutes" in rendered.text_body
    assert "Dana Scully" in rendered.text_body
    assert "If you did not request a password reset" in rendered.text_body


def test_transactional_email_service_send_password_reset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify TransactionalEmailService.send_password_reset_email dispatches correctly."""
    mock_provider = MockEmailProvider()
    settings = Settings(
        database_url="postgresql+psycopg://postgres:postgres@localhost:5432/handover",
        jwt_secret_key="x" * 64,
        token_encryption_key="MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
        email_delivery_enabled=True,
        email_provider="mock",
        frontend_base_url="http://localhost:3000",
    )
    svc = TransactionalEmailService(settings=settings, provider=mock_provider)

    res = svc.send_password_reset_email(
        to_email="test.recipient@example.com",
        recipient_name="Test Recipient",
        raw_token="raw_reset_token_xyz_987",
        expires_in_minutes=30,
    )
    assert res.status == "submitted"
    assert res.provider == "mock"
    assert len(mock_provider.sent_messages) == 1
    sent = mock_provider.sent_messages[0]
    assert sent.to_email == "test.recipient@example.com"
    assert sent.tags.get("category") == "password_reset"
    assert "http://localhost:3000/reset-password?token=raw_reset_token_xyz_987" in sent.text_body

    # Test delivery disabled
    disabled_settings = Settings(
        database_url="postgresql+psycopg://postgres:postgres@localhost:5432/handover",
        jwt_secret_key="x" * 64,
        token_encryption_key="MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
        email_delivery_enabled=False,
    )
    disabled_svc = TransactionalEmailService(settings=disabled_settings)
    res_disabled = disabled_svc.send_password_reset_email(
        to_email="test.recipient@example.com",
        recipient_name="Test Recipient",
        raw_token="raw_reset_token_xyz_987",
    )
    assert res_disabled.status == "not_configured"


