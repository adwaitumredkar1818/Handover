"""Tests for Supabase token verification and /api/v1/auth/supabase/exchange endpoint."""

from __future__ import annotations

import datetime
import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.exceptions import ConflictError, UnauthorizedError
from app.models.enums import RoleName, UserStatus
from app.models.user import User
from app.services.auth import AuthService
from app.services.supabase_verifier import SupabaseTokenVerifier, VerifiedSupabaseIdentity


# Generate a throwaway HMAC secret for symmetric testing
TEST_SECRET = "super-secret-test-key-which-is-at-least-32-chars-long"
TEST_ISSUER = "https://example-project.supabase.co/auth/v1"
TEST_AUDIENCE = "authenticated"


@pytest.fixture
def mock_settings() -> Settings:
    settings = MagicMock(spec=Settings)
    auth_config = MagicMock()
    auth_config.enabled = True
    auth_config.audience = TEST_AUDIENCE
    auth_config.issuer = TEST_ISSUER
    auth_config.jwks_url = None
    auth_config.jwt_secret = MagicMock()
    auth_config.jwt_secret.get_secret_value.return_value = TEST_SECRET

    settings.supabase_auth = auth_config
    settings.security = MagicMock()
    settings.security.jwt_refresh_token_expire_days = 30
    settings.security.refresh_cookie_name = "refresh_token"
    settings.security.jwt_access_token_expire_minutes = 15
    settings.security.jwt_issuer = "https://handover.local"
    settings.security.jwt_audience = "handover_app"
    settings.security.jwt_algorithm = "HS256"
    settings.security.jwt_secret_key = MagicMock()
    settings.security.jwt_secret_key.get_secret_value.return_value = "handover-app-test-secret-at-least-32-chars"
    return settings


def create_test_jwt(
    claims: dict[str, Any],
    secret: str = TEST_SECRET,
    alg: str = "HS256",
    headers: dict[str, Any] | None = None,
) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    base_claims = {
        "iss": TEST_ISSUER,
        "aud": TEST_AUDIENCE,
        "sub": "supabase-user-123",
        "email": "developer@example.com",
        "email_verified_at": now.isoformat(),
        "exp": int((now + datetime.timedelta(hours=1)).timestamp()),
        "nbf": int(now.timestamp()),
        "iat": int(now.timestamp()),
        "user_metadata": {
            "full_name": "Test Google User",
            "email_verified": True,
        },
    }
    base_claims.update(claims)
    return jwt.encode(base_claims, secret, algorithm=alg, headers=headers)


class TestSupabaseTokenVerifier:
    def test_verify_valid_token(self, mock_settings: Settings) -> None:
        verifier = SupabaseTokenVerifier(mock_settings)
        token = create_test_jwt({"sub": "sub-12345", "email": "alice@company.org"})

        identity = verifier.verify_token(token)

        assert identity.supabase_user_id == "sub-12345"
        assert identity.email == "alice@company.org"
        assert identity.is_email_verified is True
        assert identity.full_name == "Test Google User"

    def test_verify_expired_token_raises_unauthorized(self, mock_settings: Settings) -> None:
        verifier = SupabaseTokenVerifier(mock_settings)
        past = int((datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=2)).timestamp())
        token = create_test_jwt({"exp": past})

        with pytest.raises(UnauthorizedError) as exc_info:
            verifier.verify_token(token)
        assert exc_info.value.code == "SUPABASE_TOKEN_EXPIRED"

    def test_verify_wrong_audience_raises_unauthorized(self, mock_settings: Settings) -> None:
        verifier = SupabaseTokenVerifier(mock_settings)
        token = create_test_jwt({"aud": "wrong-audience"})

        with pytest.raises(UnauthorizedError) as exc_info:
            verifier.verify_token(token)
        assert exc_info.value.code == "SUPABASE_TOKEN_AUDIENCE_MISMATCH"

    def test_verify_wrong_issuer_raises_unauthorized(self, mock_settings: Settings) -> None:
        verifier = SupabaseTokenVerifier(mock_settings)
        token = create_test_jwt({"iss": "https://attacker.supabase.co/auth/v1"})

        with pytest.raises(UnauthorizedError) as exc_info:
            verifier.verify_token(token)
        assert exc_info.value.code == "SUPABASE_TOKEN_ISSUER_MISMATCH"

    def test_verify_invalid_signature_raises_unauthorized(self, mock_settings: Settings) -> None:
        verifier = SupabaseTokenVerifier(mock_settings)
        token = create_test_jwt({}, secret="wrong-secret-signature-key-min-32-chars")

        with pytest.raises(UnauthorizedError) as exc_info:
            verifier.verify_token(token)
        assert exc_info.value.code == "SUPABASE_TOKEN_INVALID"

    def test_verify_missing_subject_raises_unauthorized(self, mock_settings: Settings) -> None:
        verifier = SupabaseTokenVerifier(mock_settings)
        token = create_test_jwt({"sub": ""})

        with pytest.raises(UnauthorizedError) as exc_info:
            verifier.verify_token(token)
        assert exc_info.value.code in {"SUPABASE_TOKEN_MISSING_SUBJECT", "SUPABASE_TOKEN_INVALID"}


class TestSupabaseAuthExchangeService:
    def test_case_c_new_google_user_registration(
        self,
        mock_settings: Settings,
    ) -> None:
        mock_user_repo = MagicMock()
        mock_refresh_repo = MagicMock()
        mock_rbac_repo = MagicMock()
        mock_db = MagicMock()
        mock_verifier = MagicMock()

        # No user exists by sub or email
        mock_user_repo.get_by_supabase_auth_id.return_value = None
        mock_user_repo.get_by_email.return_value = None

        now = datetime.datetime.now(datetime.timezone.utc)
        new_user = User(
            id=uuid.uuid4(),
            full_name="New Google User",
            email="newuser@example.com",
            supabase_auth_id="google-sub-999",
            status=UserStatus.ACTIVE.value,
            is_email_verified=True,
            created_at=now,
            updated_at=now,
        )
        mock_user_repo.create.return_value = new_user
        mock_role = MagicMock()
        mock_role.id = uuid.uuid4()
        mock_role.name = RoleName.STANDARD_USER.value
        mock_rbac_repo.get_role_by_name.return_value = mock_role
        mock_rbac_repo.get_user_platform_roles_and_permissions.return_value = (
            [RoleName.STANDARD_USER.value],
            ["workspace.overview.read"],
        )

        mock_verifier.verify_token.return_value = VerifiedSupabaseIdentity(
            supabase_user_id="google-sub-999",
            email="newuser@example.com",
            is_email_verified=True,
            full_name="New Google User",
        )

        service = AuthService(
            settings=mock_settings,
            db_session=mock_db,
            user_repository=mock_user_repo,
            refresh_repository=mock_refresh_repo,
            rbac_repository=mock_rbac_repo,
            supabase_verifier=mock_verifier,
        )

        res, refresh_token = service.exchange_supabase_token(access_token="fake-supabase-token")

        assert res.access_token is not None
        assert res.user.email == "newuser@example.com"
        assert res.user.full_name == "New Google User"
        assert refresh_token is not None
        mock_user_repo.create.assert_called_once()
        mock_rbac_repo.assign_role.assert_called_once()

    def test_case_a_existing_linked_account(
        self,
        mock_settings: Settings,
    ) -> None:
        mock_user_repo = MagicMock()
        mock_refresh_repo = MagicMock()
        mock_rbac_repo = MagicMock()
        mock_db = MagicMock()
        mock_verifier = MagicMock()

        now = datetime.datetime.now(datetime.timezone.utc)
        existing_user = User(
            id=uuid.uuid4(),
            full_name="Existing User",
            email="existing@example.com",
            supabase_auth_id="google-sub-111",
            status=UserStatus.ACTIVE.value,
            is_email_verified=True,
            created_at=now,
            updated_at=now,
        )
        mock_user_repo.get_by_supabase_auth_id.return_value = existing_user
        mock_user_repo.get_by_email.return_value = existing_user
        mock_rbac_repo.get_user_platform_roles_and_permissions.return_value = (
            [RoleName.STANDARD_USER.value],
            ["workspace.overview.read"],
        )

        mock_verifier.verify_token.return_value = VerifiedSupabaseIdentity(
            supabase_user_id="google-sub-111",
            email="existing@example.com",
            is_email_verified=True,
            full_name="Existing User",
        )

        service = AuthService(
            settings=mock_settings,
            db_session=mock_db,
            user_repository=mock_user_repo,
            refresh_repository=mock_refresh_repo,
            rbac_repository=mock_rbac_repo,
            supabase_verifier=mock_verifier,
        )

        res, refresh_token = service.exchange_supabase_token(access_token="fake-token")

        assert res.user.id == existing_user.id
        mock_user_repo.create.assert_not_called()
        mock_user_repo.link_supabase_auth_id.assert_not_called()

    def test_case_b_existing_unlinked_account_links_safely(
        self,
        mock_settings: Settings,
    ) -> None:
        mock_user_repo = MagicMock()
        mock_refresh_repo = MagicMock()
        mock_rbac_repo = MagicMock()
        mock_db = MagicMock()
        mock_verifier = MagicMock()

        now = datetime.datetime.now(datetime.timezone.utc)
        unlinked_user = User(
            id=uuid.uuid4(),
            full_name="Unlinked User",
            email="unlinked@example.com",
            supabase_auth_id=None,
            status=UserStatus.ACTIVE.value,
            is_email_verified=False,
            created_at=now,
            updated_at=now,
        )
        mock_user_repo.get_by_supabase_auth_id.return_value = None
        mock_user_repo.get_by_email.return_value = unlinked_user
        mock_rbac_repo.get_user_platform_roles_and_permissions.return_value = (
            [RoleName.STANDARD_USER.value],
            ["workspace.overview.read"],
        )

        mock_verifier.verify_token.return_value = VerifiedSupabaseIdentity(
            supabase_user_id="google-sub-222",
            email="unlinked@example.com",
            is_email_verified=True,
            full_name="Unlinked User",
        )

        service = AuthService(
            settings=mock_settings,
            db_session=mock_db,
            user_repository=mock_user_repo,
            refresh_repository=mock_refresh_repo,
            rbac_repository=mock_rbac_repo,
            supabase_verifier=mock_verifier,
        )

        res, refresh_token = service.exchange_supabase_token(access_token="fake-token")

        assert res.user.id == unlinked_user.id
        mock_user_repo.link_supabase_auth_id.assert_called_once()

    def test_case_b_refuses_linking_unverified_email(
        self,
        mock_settings: Settings,
    ) -> None:
        mock_user_repo = MagicMock()
        mock_refresh_repo = MagicMock()
        mock_rbac_repo = MagicMock()
        mock_db = MagicMock()
        mock_verifier = MagicMock()

        unlinked_user = User(
            id=uuid.uuid4(),
            full_name="Unlinked User",
            email="unlinked@example.com",
            supabase_auth_id=None,
            status=UserStatus.ACTIVE.value,
        )
        mock_user_repo.get_by_supabase_auth_id.return_value = None
        mock_user_repo.get_by_email.return_value = unlinked_user

        mock_verifier.verify_token.return_value = VerifiedSupabaseIdentity(
            supabase_user_id="google-sub-222",
            email="unlinked@example.com",
            is_email_verified=False,  # Unverified!
            full_name="Unlinked User",
        )

        service = AuthService(
            settings=mock_settings,
            db_session=mock_db,
            user_repository=mock_user_repo,
            refresh_repository=mock_refresh_repo,
            rbac_repository=mock_rbac_repo,
            supabase_verifier=mock_verifier,
        )

        with pytest.raises(UnauthorizedError) as exc_info:
            service.exchange_supabase_token(access_token="fake-token")
        assert exc_info.value.code == "UNVERIFIED_EMAIL"
        mock_user_repo.link_supabase_auth_id.assert_not_called()

    def test_case_d_identity_conflict_rejected(
        self,
        mock_settings: Settings,
    ) -> None:
        mock_user_repo = MagicMock()
        mock_refresh_repo = MagicMock()
        mock_rbac_repo = MagicMock()
        mock_db = MagicMock()
        mock_verifier = MagicMock()

        user_a = User(
            id=uuid.uuid4(),
            full_name="User A",
            email="usera@example.com",
            supabase_auth_id="google-sub-333",
            status=UserStatus.ACTIVE.value,
        )
        user_b = User(
            id=uuid.uuid4(),
            full_name="User B",
            email="userb@example.com",
            supabase_auth_id=None,
            status=UserStatus.ACTIVE.value,
        )

        # sub points to User A, but token email points to User B!
        mock_user_repo.get_by_supabase_auth_id.return_value = user_a
        mock_user_repo.get_by_email.return_value = user_b

        mock_verifier.verify_token.return_value = VerifiedSupabaseIdentity(
            supabase_user_id="google-sub-333",
            email="userb@example.com",
            is_email_verified=True,
        )

        service = AuthService(
            settings=mock_settings,
            db_session=mock_db,
            user_repository=mock_user_repo,
            refresh_repository=mock_refresh_repo,
            rbac_repository=mock_rbac_repo,
            supabase_verifier=mock_verifier,
        )

        with pytest.raises(ConflictError) as exc_info:
            service.exchange_supabase_token(access_token="fake-token")
        assert exc_info.value.code == "IDENTITY_CONFLICT"

    def test_disabled_user_rejected(
        self,
        mock_settings: Settings,
    ) -> None:
        mock_user_repo = MagicMock()
        mock_refresh_repo = MagicMock()
        mock_rbac_repo = MagicMock()
        mock_db = MagicMock()
        mock_verifier = MagicMock()

        disabled_user = User(
            id=uuid.uuid4(),
            full_name="Disabled User",
            email="disabled@example.com",
            supabase_auth_id="google-sub-444",
            status=UserStatus.DISABLED.value,
        )
        mock_user_repo.get_by_supabase_auth_id.return_value = disabled_user
        mock_user_repo.get_by_email.return_value = disabled_user

        mock_verifier.verify_token.return_value = VerifiedSupabaseIdentity(
            supabase_user_id="google-sub-444",
            email="disabled@example.com",
            is_email_verified=True,
        )

        service = AuthService(
            settings=mock_settings,
            db_session=mock_db,
            user_repository=mock_user_repo,
            refresh_repository=mock_refresh_repo,
            rbac_repository=mock_rbac_repo,
            supabase_verifier=mock_verifier,
        )

        with pytest.raises(UnauthorizedError) as exc_info:
            service.exchange_supabase_token(access_token="fake-token")
        assert exc_info.value.code == "ACCOUNT_INACTIVE"
