"""Tests for forgot password and reset password functionality."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.security import hash_opaque_token, hash_password, utc_now
from app.models.auth import PasswordResetToken
from app.models.enums import UserStatus
from app.models.user import User
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
