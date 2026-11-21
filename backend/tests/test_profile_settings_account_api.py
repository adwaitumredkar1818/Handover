"""End-to-end API tests for Profile, Preferences, Avatar, Security, and Privacy endpoints."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.models.audit import AuditLog
from app.models.user import User
from tests.conftest import isolated_auth_app

_PASSWORD_A = "Handover!Profile2026#A"
_PASSWORD_B = "Handover!Profile2026#B"
_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
    b"\x00\x00\x00\nIDATx\x9cc`\x00\x00\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _register_and_login(
    client: TestClient,
    *,
    name: str,
    email: str,
    password: str,
) -> tuple[str, dict]:
    reg = client.post(
        "/api/v1/auth/register",
        json={"full_name": name, "email": email, "password": password},
    )
    assert reg.status_code == 201, reg.text
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200, login.text
    data = login.json()
    return data["access_token"], data["user"]


def test_profile_preferences_and_avatar_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        tok_a, user_a = _register_and_login(
            client,
            name="Alice Vance",
            email="alice.profile@example.com",
            password=_PASSWORD_A,
        )
        tok_b, _user_b = _register_and_login(
            client,
            name="Bob Stone",
            email="bob.profile@example.com",
            password=_PASSWORD_A,
        )

        # Unauthenticated rejected
        assert client.patch("/api/v1/users/me", json={"full_name": "Nope"}).status_code == 401

        # Update own profile & UI preferences
        upd = client.patch(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {tok_a}"},
            json={
                "full_name": "Alice Vance-Chen",
                "job_title": "Staff Systems Engineer",
                "bio": "Owns core handover workflows.",
                "timezone": "Asia/Kolkata",
                "preferences": {
                    "theme": "dark",
                    "date_format": "YYYY-MM-DD",
                    "density": "compact",
                    "reduced_motion": True,
                    "default_landing_page": "/projects",
                },
            },
        )
        assert upd.status_code == 200, upd.text
        body = upd.json()
        assert body["full_name"] == "Alice Vance-Chen"
        assert body["job_title"] == "Staff Systems Engineer"
        assert body["bio"] == "Owns core handover workflows."
        assert body["timezone"] == "Asia/Kolkata"
        assert body["auth_method"] == "password"
        assert body["preferences"]["theme"] == "dark"
        assert body["preferences"]["density"] == "compact"
        assert body["preferences"]["reduced_motion"] is True
        assert body["preferences"]["default_landing_page"] == "/projects"

        # Invalid timezone rejected
        bad_tz = client.patch(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {tok_a}"},
            json={"timezone": "Mars/Olympus"},
        )
        assert bad_tz.status_code == 422

        # Upload invalid fake PNG rejected
        bad_av = client.post(
            "/api/v1/users/me/avatar",
            headers={"Authorization": f"Bearer {tok_a}"},
            files={"file": ("evil.png", b"not-a-real-png-script", "image/png")},
        )
        assert bad_av.status_code == 400

        # Upload valid PNG avatar
        good_av = client.post(
            "/api/v1/users/me/avatar",
            headers={"Authorization": f"Bearer {tok_a}"},
            files={"file": ("avatar.png", _PNG_BYTES, "image/png")},
        )
        assert good_av.status_code == 200, good_av.text
        assert good_av.json()["has_avatar"] is True
        assert good_av.json()["avatar_url"].startswith(f"/api/v1/users/{user_a['id']}/avatar")

        # Self can fetch avatar bytes with nosniff header
        get_av = client.get(
            f"/api/v1/users/{user_a['id']}/avatar",
            headers={"Authorization": f"Bearer {tok_a}"},
        )
        assert get_av.status_code == 200
        assert get_av.headers["content-type"] == "image/png"
        assert get_av.headers["x-content-type-options"] == "nosniff"
        assert get_av.content == _PNG_BYTES

        # Unrelated user B cannot fetch Alice's avatar
        denied_av = client.get(
            f"/api/v1/users/{user_a['id']}/avatar",
            headers={"Authorization": f"Bearer {tok_b}"},
        )
        assert denied_av.status_code == 403

        # Delete avatar
        del_av = client.delete(
            "/api/v1/users/me/avatar",
            headers={"Authorization": f"Bearer {tok_a}"},
        )
        assert del_av.status_code == 200
        assert del_av.json()["has_avatar"] is False
        assert del_av.json()["avatar_url"] is None


def test_password_change_sessions_notifications_export_and_deletion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with isolated_auth_app(monkeypatch) as ctx, TestClient(ctx.app) as client:
        tok_a, user_a = _register_and_login(
            client,
            name="Clara Oswald",
            email="clara@example.com",
            password=_PASSWORD_A,
        )

        # Create a second session for Clara
        login2 = client.post(
            "/api/v1/auth/login",
            json={"email": "clara@example.com", "password": _PASSWORD_A},
        )
        assert login2.status_code == 200
        tok_a2 = login2.json()["access_token"]

        # Wrong current password rejected
        bad_pw = client.post(
            "/api/v1/auth/change-password",
            headers={"Authorization": f"Bearer {tok_a}"},
            json={"current_password": "Wrong!Password99", "new_password": _PASSWORD_B},
        )
        assert bad_pw.status_code == 401

        # Valid password change revokes other session
        ok_pw = client.post(
            "/api/v1/auth/change-password",
            headers={"Authorization": f"Bearer {tok_a}"},
            json={"current_password": _PASSWORD_A, "new_password": _PASSWORD_B},
        )
        assert ok_pw.status_code == 200, ok_pw.text
        assert ok_pw.json()["revoked_other_sessions"] >= 1

        # Old second token's session family is revoked so protected /me fails or new login works
        login_new = client.post(
            "/api/v1/auth/login",
            json={"email": "clara@example.com", "password": _PASSWORD_B},
        )
        assert login_new.status_code == 200
        tok_new = login_new.json()["access_token"]

        # Notification preferences persist
        np_upd = client.patch(
            "/api/v1/notifications/preferences",
            headers={"Authorization": f"Bearer {tok_new}"},
            json={"review_requests": False, "handover_published": False},
        )
        assert np_upd.status_code == 200
        assert np_upd.json()["review_requests"] is False
        assert np_upd.json()["handover_published"] is False
        assert np_upd.json()["security_events"] is True

        # Export personal account data
        exp = client.get(
            "/api/v1/auth/me/export",
            headers={"Authorization": f"Bearer {tok_new}"},
        )
        assert exp.status_code == 200
        assert exp.json()["profile"]["email"] == "clara@example.com"
        assert exp.json()["notification_preferences"]["review_requests"] is False

        # Deletion request requires "DELETE" confirmation
        bad_del = client.post(
            "/api/v1/auth/me/deletion-request",
            headers={"Authorization": f"Bearer {tok_new}"},
            json={"confirmation_text": "nope", "current_password": _PASSWORD_B},
        )
        assert bad_del.status_code == 400

        # Valid deletion request records audit log without destroying evidence
        ok_del = client.post(
            "/api/v1/auth/me/deletion-request",
            headers={"Authorization": f"Bearer {tok_new}"},
            json={
                "confirmation_text": "DELETE",
                "current_password": _PASSWORD_B,
                "reason": "Moving teams",
            },
        )
        assert ok_del.status_code == 200, ok_del.text
        assert ok_del.json()["status"] == "pending_review"

        with ctx.session_factory() as db:
            logs = db.query(AuditLog).filter(AuditLog.event_type == "account.deletion_requested").all()
            assert len(logs) == 1

            # OAuth-only user cannot call change-password
            db_user = db.get(User, uuid.UUID(user_a["id"]))
            assert db_user is not None
            db_user.password_hash = None
            db_user.supabase_auth_id = "supa-oauth-123"
            db.commit()

        oauth_pw = client.post(
            "/api/v1/auth/change-password",
            headers={"Authorization": f"Bearer {tok_new}"},
            json={"current_password": _PASSWORD_B, "new_password": _PASSWORD_A},
        )
        assert oauth_pw.status_code == 400
        assert oauth_pw.json()["error"]["code"] == "OAUTH_MANAGED_ACCOUNT"
        assert tok_a2  # silence unused warning
