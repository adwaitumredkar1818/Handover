"""Tests for forgot password and reset password functionality."""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.security import hash_opaque_token, hash_password, utc_now
from app.models.auth import PasswordResetToken, RefreshSession
from app.models.enums import UserStatus
from app.models.user import User
from app.services.email import EmailDeliveryResult, MockEmailProvider
from tests.conftest import isolated_auth_app

_TRUSTED_ORIGIN = "http://localhost:3000"
_VALID_PASSWORD = "Handover!Auth2026#Secure"
_NEW_PASSWORD = "NewHandover!Auth2026#Secure"


def test_forgot_password_and_reset_flow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        test_email = f"reset.user.{uuid.uuid4().hex[:8]}@example.com"

        # 1. Register a user
        reg = client.post(
            "/api/v1/auth/register",
            json={
                "full_name": "Reset Test User",
                "email": test_email,
                "password": _VALID_PASSWORD,
            },
        )
        assert reg.status_code == 201

        # 2. Request password reset
        forgot_res = client.post(
            "/api/v1/auth/forgot-password",
            json={"email": test_email},
        )
        assert forgot_res.status_code == 200
        forgot_data = forgot_res.json()
        assert "instructions have been generated" in forgot_data["message"]
        # In test/dev environment, reset_token is returned
        token = forgot_data.get("reset_token")
        assert token is not None

        # Check DB record exists and is hashed
        with ctx.session_factory() as session:
            token_hash = hash_opaque_token(token)
            stmt = select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
            db_token = session.scalar(stmt)
            assert db_token is not None
            assert db_token.used_at is None

        # 3. Request reset with non-existent email (prevents enumeration, returns 200 without token)
        forgot_unknown = client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "nonexistent@example.com"},
        )
        assert forgot_unknown.status_code == 200
        assert forgot_unknown.json().get("reset_token") is None

        # 4. Attempt reset with invalid token
        invalid_res = client.post(
            "/api/v1/auth/reset-password",
            json={"token": "invalid-token-that-does-not-exist", "new_password": _NEW_PASSWORD},
        )
        assert invalid_res.status_code == 401
        assert invalid_res.json()["error"]["code"] == "INVALID_RESET_TOKEN"

        # 5. Reset password successfully
        reset_res = client.post(
            "/api/v1/auth/reset-password",
            json={"token": token, "new_password": _NEW_PASSWORD},
        )
        assert reset_res.status_code == 200
        assert "successfully reset" in reset_res.json()["message"]

        # 6. Verify token is marked as used
        with ctx.session_factory() as session:
            token_hash = hash_opaque_token(token)
            stmt = select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
            db_token = session.scalar(stmt)
            assert db_token is not None
            assert db_token.used_at is not None

        # 7. Attempting to use the same token again fails
        reuse_res = client.post(
            "/api/v1/auth/reset-password",
            json={"token": token, "new_password": "AnotherPassword123!"},
        )
        assert reuse_res.status_code == 401
        assert reuse_res.json()["error"]["code"] == "RESET_TOKEN_ALREADY_USED"

        # 8. Verify login with old password fails
        old_login = client.post(
            "/api/v1/auth/login",
            json={"email": test_email, "password": _VALID_PASSWORD},
        )
        assert old_login.status_code == 401

        # 9. Verify login with new password succeeds
        new_login = client.post(
            "/api/v1/auth/login",
            json={"email": test_email, "password": _NEW_PASSWORD},
        )
        assert new_login.status_code == 200
        assert "access_token" in new_login.json()


def test_expired_reset_token_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        test_email = f"expired.user.{uuid.uuid4().hex[:8]}@example.com"
        reg = client.post(
            "/api/v1/auth/register",
            json={
                "full_name": "Expired Test User",
                "email": test_email,
                "password": _VALID_PASSWORD,
            },
        )
        assert reg.status_code == 201
        user_id = uuid.UUID(reg.json()["user"]["id"])

        raw_token = "expired_token_raw_string_1234567890"
        token_hash = hash_opaque_token(raw_token)
        now = utc_now()
        with ctx.session_factory() as session:
            expired_token = PasswordResetToken(
                user_id=user_id,
                token_hash=token_hash,
                expires_at=now - timedelta(minutes=5),
            )
            session.add(expired_token)
            session.commit()

        res = client.post(
            "/api/v1/auth/reset-password",
            json={"token": raw_token, "new_password": _NEW_PASSWORD},
        )
        assert res.status_code == 401
        assert res.json()["error"]["code"] == "RESET_TOKEN_EXPIRED"


def test_password_reset_email_dispatch_and_no_token_leakage(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify forgot-password dispatches branded email with FRONTEND_BASE_URL link and does not leak token."""
    monkeypatch.setenv("EMAIL_DELIVERY_ENABLED", "true")
    monkeypatch.setenv("EMAIL_PROVIDER", "mock")
    monkeypatch.setenv("FRONTEND_BASE_URL", "http://localhost:3000")

    mock_provider = MockEmailProvider()

    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        ctx.app.state.email_provider = mock_provider
        test_email = f"reset.email.{uuid.uuid4().hex[:8]}@example.com"

        # Register unverified user
        reg = client.post(
            "/api/v1/auth/register",
            json={
                "full_name": "Email Reset User",
                "email": test_email,
                "password": _VALID_PASSWORD,
            },
        )
        assert reg.status_code == 201

        # Check user is initially unverified in DB
        with ctx.session_factory() as session:
            stmt = select(User).where(User.email == test_email)
            db_user = session.scalar(stmt)
            assert db_user is not None
            assert db_user.is_email_verified is False
            assert db_user.email_verified_at is None

        # Clear mock sent messages from registration
        mock_provider.sent_messages.clear()

        with caplog.at_level(logging.INFO):
            forgot_res = client.post(
                "/api/v1/auth/forgot-password",
                json={"email": test_email},
            )
            assert forgot_res.status_code == 200
            forgot_data = forgot_res.json()
            assert forgot_data["email_delivery"] == "submitted"
            raw_token = forgot_data.get("reset_token")
            assert raw_token is not None

            # Check email was dispatched via provider
            assert len(mock_provider.sent_messages) == 1
            msg = mock_provider.sent_messages[0]
            assert msg.to_email == test_email
            assert "Reset your Handover password" in msg.subject
            expected_link = f"http://localhost:3000/reset-password?token={raw_token}"
            assert expected_link in msg.text_body
            assert f"/reset-password?token={raw_token}" in msg.html_body
            assert "30 minutes" in msg.text_body
            assert "Security notice" in msg.text_body
            assert msg.tags.get("category") == "password_reset"

            # Verify raw token is NEVER logged in application log output
            for record in caplog.records:
                assert raw_token not in record.getMessage()

        # Reset password and verify unverified user becomes email verified
        reset_res = client.post(
            "/api/v1/auth/reset-password",
            json={"token": raw_token, "new_password": _NEW_PASSWORD},
        )
        assert reset_res.status_code == 200

        with ctx.session_factory() as session:
            stmt = select(User).where(User.email == test_email)
            updated_user = session.scalar(stmt)
            assert updated_user is not None
            assert updated_user.is_email_verified is True
            assert updated_user.email_verified_at is not None


def test_password_reset_email_delivery_failure_is_resilient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that email delivery failure does not return 500 error or abort password reset request."""
    monkeypatch.setenv("EMAIL_DELIVERY_ENABLED", "true")
    monkeypatch.setenv("EMAIL_PROVIDER", "mock")
    monkeypatch.setenv("FRONTEND_BASE_URL", "http://localhost:3000")

    mock_provider = MockEmailProvider(should_fail=True)

    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        ctx.app.state.email_provider = mock_provider
        test_email = f"fail.reset.{uuid.uuid4().hex[:8]}@example.com"

        reg = client.post(
            "/api/v1/auth/register",
            json={
                "full_name": "Failure Resilience User",
                "email": test_email,
                "password": _VALID_PASSWORD,
            },
        )
        assert reg.status_code == 201

        forgot_res = client.post(
            "/api/v1/auth/forgot-password",
            json={"email": test_email},
        )
        # Must return 200 with generic message and failed delivery status, NOT 500
        assert forgot_res.status_code == 200
        forgot_data = forgot_res.json()
        assert "instructions have been generated" in forgot_data["message"]
        assert forgot_data["email_delivery"] == "failed"


def test_password_reset_revokes_active_refresh_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that completing a password reset revokes all existing refresh sessions."""
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        test_email = f"session.user.{uuid.uuid4().hex[:8]}@example.com"

        reg = client.post(
            "/api/v1/auth/register",
            json={
                "full_name": "Session User",
                "email": test_email,
                "password": _VALID_PASSWORD,
            },
        )
        assert reg.status_code == 201
        dev_ver_token = reg.json()["development_verification_token"]
        assert client.post("/api/v1/auth/verify-email", json={"token": dev_ver_token}).status_code == 200

        # Login to establish active session
        login_res = client.post(
            "/api/v1/auth/login",
            json={"email": test_email, "password": _VALID_PASSWORD},
        )
        assert login_res.status_code == 200
        assert "access_token" in login_res.json()

        # Verify active session in DB
        with ctx.session_factory() as session:
            stmt = select(User).where(User.email == test_email)
            user = session.scalar(stmt)
            assert user is not None
            user_id = user.id

            sess_stmt = select(RefreshSession).where(
                RefreshSession.user_id == user_id,
                RefreshSession.revoked_at.is_(None),
            )
            active_sessions = session.scalars(sess_stmt).all()
            assert len(active_sessions) >= 1

        # Request reset
        forgot_res = client.post(
            "/api/v1/auth/forgot-password",
            json={"email": test_email},
        )
        assert forgot_res.status_code == 200
        token = forgot_res.json()["reset_token"]
        assert token is not None

        # Reset password
        reset_res = client.post(
            "/api/v1/auth/reset-password",
            json={"token": token, "new_password": _NEW_PASSWORD},
        )
        assert reset_res.status_code == 200

        # Verify all sessions are now revoked with reason PASSWORD_RESET
        with ctx.session_factory() as session:
            sess_stmt = select(RefreshSession).where(RefreshSession.user_id == user_id)
            all_sessions = session.scalars(sess_stmt).all()
            assert len(all_sessions) >= 1
            for s in all_sessions:
                assert s.revoked_at is not None
                assert s.revoked_reason == "PASSWORD_RESET"


def test_password_reset_nonexistent_and_inactive_users_enumeration_protection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify anti-enumeration returns 200 generic message without token or email for missing or inactive users."""
    monkeypatch.setenv("EMAIL_DELIVERY_ENABLED", "true")
    monkeypatch.setenv("EMAIL_PROVIDER", "mock")

    mock_provider = MockEmailProvider()

    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        ctx.app.state.email_provider = mock_provider

        # Non-existent email
        res1 = client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "nobody@example.com"},
        )
        assert res1.status_code == 200
        data1 = res1.json()
        assert "instructions have been generated" in data1["message"]
        assert data1.get("reset_token") is None
        assert data1.get("email_delivery") is None
        assert len(mock_provider.sent_messages) == 0

        # Inactive user
        test_email = f"inactive.{uuid.uuid4().hex[:8]}@example.com"
        reg = client.post(
            "/api/v1/auth/register",
            json={
                "full_name": "Inactive User",
                "email": test_email,
                "password": _VALID_PASSWORD,
            },
        )
        assert reg.status_code == 201

        # Clear registration email from sent messages
        mock_provider.sent_messages.clear()

        # Disable user
        with ctx.session_factory() as session:
            stmt = select(User).where(User.email == test_email)
            u = session.scalar(stmt)
            assert u is not None
            u.status = UserStatus.DISABLED.value
            session.commit()

        res2 = client.post(
            "/api/v1/auth/forgot-password",
            json={"email": test_email},
        )
        assert res2.status_code == 200
        data2 = res2.json()
        assert "instructions have been generated" in data2["message"]
        assert data2.get("reset_token") is None
        assert data2.get("email_delivery") is None
        assert len(mock_provider.sent_messages) == 0

