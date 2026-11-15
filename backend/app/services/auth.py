"""Platform authentication, Argon2id password, JWT, and rotated refresh session service."""

from __future__ import annotations

import logging
import secrets
import uuid
from datetime import timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ServiceUnavailableError,
    UnauthorizedError,
)
from app.core.logging import log_security_event
from app.core.security import (
    create_access_token,
    ensure_utc,
    generate_refresh_token,
    hash_opaque_token,
    hash_password,
    hash_refresh_token,
    utc_now,
    verify_dummy_password,
    verify_password,
)
from app.models.enums import RevocationReason, RoleName, RoleScopeType, UserStatus
from app.models.user import User
from app.repositories.auth import PasswordResetTokenRepository, RefreshSessionRepository
from app.repositories.rbac import RbacRepository
from app.repositories.user import UserRepository
from app.schemas.auth import (
    AccessTokenResponse,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    LogoutResponse,
    RefreshSessionSummary,
    RegisterRequest,
    RegisterResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
    RevokeSessionResponse,
    SessionListResponse,
)
from app.schemas.user import AuthenticatedUserResponse, UserSummaryResponse
from app.services.rbac import AuthenticatedPrincipal
from app.services.supabase_verifier import SupabaseTokenVerifier, VerifiedSupabaseIdentity


def build_user_summary(user: User, roles: list[str] | None = None) -> UserSummaryResponse:
    """Map User ORM entity to safe UserSummaryResponse without secret fields."""
    if roles is None:
        resolved_roles = sorted(
            ur.role.name
            for ur in user.user_roles
            if ur.role is not None and ur.role.scope_type == RoleScopeType.PLATFORM.value
        )
    else:
        resolved_roles = sorted(roles)
    return UserSummaryResponse(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        status=user.status,
        is_email_verified=user.is_email_verified,
        email_verified_at=user.email_verified_at,
        roles=resolved_roles,
        created_at=user.created_at,
        updated_at=user.updated_at,
        last_login_at=user.last_login_at,
    )


def build_authenticated_user(
    user: User,
    *,
    roles: list[str] | tuple[str, ...],
    permissions: frozenset[str] | list[str],
) -> AuthenticatedUserResponse:
    """Build AuthenticatedUserResponse including platform roles and permissions."""
    return AuthenticatedUserResponse(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        status=user.status,
        is_email_verified=user.is_email_verified,
        email_verified_at=user.email_verified_at,
        roles=sorted(roles),
        permissions=sorted(permissions),
        created_at=user.created_at,
        updated_at=user.updated_at,
        last_login_at=user.last_login_at,
    )


class AuthService:
    """Service orchestrating FastAPI-managed registration, login, rotation, and sessions."""

    def __init__(
        self,
        *,
        settings: Settings,
        db_session: Session,
        user_repository: UserRepository,
        refresh_repository: RefreshSessionRepository,
        rbac_repository: RbacRepository,
        reset_token_repository: PasswordResetTokenRepository | None = None,
        supabase_verifier: SupabaseTokenVerifier | None = None,
    ) -> None:
        self._settings = settings
        self._db = db_session
        self._user_repo = user_repository
        self._refresh_repo = refresh_repository
        self._rbac_repo = rbac_repository
        self._reset_token_repo = reset_token_repository or PasswordResetTokenRepository(db_session)
        self._supabase_verifier = supabase_verifier or SupabaseTokenVerifier(settings)

    def register(self, payload: RegisterRequest) -> RegisterResponse:
        """Create a new platform account with Argon2id password hash and default role."""
        if self._user_repo.get_by_email(payload.email) is not None:
            log_security_event(
                event_type="auth.register",
                outcome="denied",
                message="Rejected duplicate account registration attempt.",
            )
            raise ConflictError(
                "An account with this email address already exists.",
                code="ACCOUNT_ALREADY_EXISTS",
            )

        default_role = self._rbac_repo.get_role_by_name(RoleName.STANDARD_USER.value)
        if default_role is None:
            raise ServiceUnavailableError(
                "Platform role catalog is not initialised.",
                code="RBAC_CATALOG_NOT_READY",
            )

        password_digest = hash_password(payload.password)
        try:
            user = self._user_repo.create(
                full_name=payload.full_name,
                email=payload.email,
                password_hash=password_digest,
                status=UserStatus.ACTIVE.value,
            )
            self._rbac_repo.assign_role(
                user_id=user.id,
                role_id=default_role.id,
                assigned_by_id=None,
            )
            self._db.commit()
            self._db.refresh(user)
        except IntegrityError as exc:
            self._db.rollback()
            raise ConflictError(
                "An account with this email address already exists.",
                code="ACCOUNT_ALREADY_EXISTS",
            ) from exc

        log_security_event(
            event_type="auth.register",
            outcome="success",
            actor_user_id=str(user.id),
            message="Registered new platform account with default standard_user role.",
        )
        return RegisterResponse(
            user=build_user_summary(user, roles=[default_role.name]),
            email_verification_required=True,
            email_verification_delivery="not_configured",
            message=(
                "Account registered. Email verification delivery is not yet configured "
                "in this environment."
            ),
        )

    def login(
        self,
        *,
        payload: LoginRequest,
        session_metadata: dict[str, str] | None = None,
    ) -> tuple[AccessTokenResponse, str]:
        """Authenticate credentials cleanly and start a new refresh token family."""
        user = self._user_repo.get_by_email(payload.email)
        if user is None or not user.password_hash:
            verify_dummy_password(payload.password)
            log_security_event(
                event_type="auth.login",
                outcome="denied",
                actor_user_id=str(user.id) if user is not None else None,
                message="Rejected login due to invalid credentials.",
            )
            raise UnauthorizedError(
                "Invalid email or password.",
                code="INVALID_CREDENTIALS",
            )

        if not verify_password(payload.password, user.password_hash):
            log_security_event(
                event_type="auth.login",
                outcome="denied",
                actor_user_id=str(user.id),
                message="Rejected login due to invalid credentials.",
            )
            raise UnauthorizedError(
                "Invalid email or password.",
                code="INVALID_CREDENTIALS",
            )

        if user.status != UserStatus.ACTIVE.value:
            log_security_event(
                event_type="auth.login",
                outcome="denied",
                actor_user_id=str(user.id),
                message=f"Rejected login for non-active user status '{user.status}'.",
                level=logging.WARNING,
            )
            raise UnauthorizedError(
                "Invalid email or password.",
                code="INVALID_CREDENTIALS",
            )

        now = utc_now()
        token_family_id = uuid.uuid4()
        raw_refresh_token = generate_refresh_token()
        token_hash = hash_refresh_token(raw_refresh_token)
        expires_at = now + timedelta(days=self._settings.security.jwt_refresh_token_expire_days)

        self._refresh_repo.create(
            user_id=user.id,
            token_family_id=token_family_id,
            token_hash=token_hash,
            expires_at=expires_at,
            session_metadata=session_metadata,
        )
        self._user_repo.update_last_login(user, now)
        roles, permissions = self._rbac_repo.get_user_platform_roles_and_permissions(user.id)
        access_token, expires_in = create_access_token(
            user_id=user.id,
            session_family_id=token_family_id,
            settings=self._settings,
            now=now,
        )
        self._db.commit()
        self._db.refresh(user)

        log_security_event(
            event_type="auth.login",
            outcome="success",
            actor_user_id=str(user.id),
            message="Authenticated platform user and created refresh session family.",
        )
        return (
            AccessTokenResponse(
                access_token=access_token,
                expires_in=expires_in,
                user=build_authenticated_user(
                    user,
                    roles=roles,
                    permissions=permissions,
                ),
            ),
            raw_refresh_token,
        )

    def refresh(self, raw_refresh_token: str | None) -> tuple[AccessTokenResponse, str]:
        """Rotate refresh token securely with reuse detection and family revocation."""
        if not raw_refresh_token:
            raise UnauthorizedError(
                "Refresh session cookie is missing.",
                code="REFRESH_TOKEN_MISSING",
                clear_refresh_cookie=True,
            )

        now = utc_now()
        token_hash = hash_refresh_token(raw_refresh_token)
        existing = self._refresh_repo.get_by_token_hash_for_update(token_hash)
        if existing is None:
            log_security_event(
                event_type="auth.refresh",
                outcome="denied",
                message="Rejected unrecognised refresh token.",
                level=logging.WARNING,
            )
            raise UnauthorizedError(
                "Refresh session is invalid.",
                code="INVALID_REFRESH_TOKEN",
                clear_refresh_cookie=True,
            )

        if existing.revoked_at is not None:
            self._refresh_repo.revoke_family(
                token_family_id=existing.token_family_id,
                reason=RevocationReason.TOKEN_REUSE_DETECTED.value,
                now=now,
            )
            self._db.commit()
            log_security_event(
                event_type="auth.refresh.reuse_detected",
                outcome="denied",
                actor_user_id=str(existing.user_id),
                message=(
                    f"Detected reuse of revoked refresh token; revoked session family "
                    f"'{existing.token_family_id}'."
                ),
                level=logging.WARNING,
            )
            raise UnauthorizedError(
                "Refresh session is no longer valid.",
                code="REFRESH_TOKEN_REUSED",
                clear_refresh_cookie=True,
            )

        if ensure_utc(existing.expires_at) <= now:
            existing.revoked_at = now
            existing.revoked_reason = RevocationReason.EXPIRED.value
            self._db.commit()
            log_security_event(
                event_type="auth.refresh.expired",
                outcome="denied",
                actor_user_id=str(existing.user_id),
                message="Rejected expired refresh session.",
            )
            raise UnauthorizedError(
                "Refresh session has expired.",
                code="REFRESH_TOKEN_EXPIRED",
                clear_refresh_cookie=True,
            )

        user = existing.user or self._user_repo.get_by_id(existing.user_id)
        if user is None or user.status != UserStatus.ACTIVE.value:
            self._refresh_repo.revoke_family(
                token_family_id=existing.token_family_id,
                reason=RevocationReason.USER_DISABLED.value,
                now=now,
            )
            self._db.commit()
            raise UnauthorizedError(
                "Refresh session is no longer valid.",
                code="SESSION_USER_INACTIVE",
                clear_refresh_cookie=True,
            )

        new_raw_token = generate_refresh_token()
        new_token_hash = hash_refresh_token(new_raw_token)
        new_expires_at = now + timedelta(days=self._settings.security.jwt_refresh_token_expire_days)

        new_session = self._refresh_repo.create(
            user_id=user.id,
            token_family_id=existing.token_family_id,
            token_hash=new_token_hash,
            expires_at=new_expires_at,
            session_metadata=existing.session_metadata,
        )
        self._refresh_repo.mark_rotated(
            session_record=existing,
            replaced_by_id=new_session.id,
            reason=RevocationReason.ROTATED.value,
            now=now,
        )

        roles, permissions = self._rbac_repo.get_user_platform_roles_and_permissions(user.id)
        access_token, expires_in = create_access_token(
            user_id=user.id,
            session_family_id=existing.token_family_id,
            settings=self._settings,
            now=now,
        )
        self._db.commit()

        log_security_event(
            event_type="auth.refresh",
            outcome="success",
            actor_user_id=str(user.id),
            message="Rotated refresh session cleanly.",
        )
        return (
            AccessTokenResponse(
                access_token=access_token,
                expires_in=expires_in,
                user=build_authenticated_user(
                    user,
                    roles=roles,
                    permissions=permissions,
                ),
            ),
            new_raw_token,
        )

    def logout(self, raw_refresh_token: str | None) -> LogoutResponse:
        """Revoke the active refresh session family if present."""
        if not raw_refresh_token:
            return LogoutResponse(message="Logged out successfully.", revoked=False)

        now = utc_now()
        token_hash = hash_refresh_token(raw_refresh_token)
        existing = self._refresh_repo.get_by_token_hash_for_update(token_hash)
        if existing is None:
            return LogoutResponse(message="Logged out successfully.", revoked=False)

        revoked_count = self._refresh_repo.revoke_family(
            token_family_id=existing.token_family_id,
            reason=RevocationReason.LOGOUT.value,
            now=now,
        )
        self._db.commit()

        log_security_event(
            event_type="auth.logout",
            outcome="success",
            actor_user_id=str(existing.user_id),
            message="Revoked refresh session family on logout.",
        )
        return LogoutResponse(message="Logged out successfully.", revoked=revoked_count > 0)

    def list_my_sessions(self, principal: AuthenticatedPrincipal) -> SessionListResponse:
        """Return sessions belonging strictly to the authenticated user."""
        now = utc_now()
        sessions = self._refresh_repo.list_for_user(
            user_id=principal.user.id,
            include_revoked=True,
        )
        items = [
            RefreshSessionSummary(
                id=s.id,
                token_family_id=s.token_family_id,
                created_at=s.created_at,
                expires_at=s.expires_at,
                last_used_at=s.last_used_at,
                revoked_at=s.revoked_at,
                revoked_reason=s.revoked_reason,
                is_current_family=(
                    s.token_family_id == principal.session_family_id
                    and s.revoked_at is None
                    and ensure_utc(s.expires_at) > now
                ),
                session_metadata=s.session_metadata,
            )
            for s in sessions
        ]
        return SessionListResponse(items=items)

    def revoke_my_session(
        self,
        *,
        session_id: uuid.UUID,
        principal: AuthenticatedPrincipal,
    ) -> RevokeSessionResponse:
        """Revoke one session family owned strictly by the authenticated user."""
        target = self._refresh_repo.get_by_id_for_user(
            session_id=session_id,
            user_id=principal.user.id,
        )
        if target is None:
            raise NotFoundError("Refresh session was not found.", code="SESSION_NOT_FOUND")

        now = utc_now()
        revoked_count = self._refresh_repo.revoke_family(
            token_family_id=target.token_family_id,
            reason=RevocationReason.REVOKED_BY_USER.value,
            now=now,
        )
        self._db.commit()

        log_security_event(
            event_type="auth.session_revoked",
            outcome="success",
            actor_user_id=str(principal.user.id),
            message=f"User revoked session '{session_id}' (family '{target.token_family_id}').",
        )
        return RevokeSessionResponse(
            session_id=session_id,
            revoked=revoked_count > 0,
            message="Session revoked successfully.",
        )

    def exchange_supabase_token(
        self,
        *,
        access_token: str,
        session_metadata: dict[str, str] | None = None,
    ) -> tuple[AccessTokenResponse, str]:
        """Authenticate or link a verified Supabase identity and issue a Handover session."""
        identity: VerifiedSupabaseIdentity = self._supabase_verifier.verify_token(access_token)
        now = utc_now()

        # Step 1: Check if Supabase identity already maps to a Handover user
        user_by_sub = self._user_repo.get_by_supabase_auth_id(identity.supabase_user_id)
        user_by_email = self._user_repo.get_by_email(identity.email)

        # Case D: Conflict detection
        # If user_by_sub exists and points to User A, but user_by_email exists and is User B != User A
        if user_by_sub is not None and user_by_email is not None and user_by_sub.id != user_by_email.id:
            log_security_event(
                event_type="auth.supabase.exchange",
                outcome="denied",
                actor_user_id=str(user_by_sub.id),
                message=(
                    f"Identity conflict: Supabase sub '{identity.supabase_user_id}' linked to "
                    f"user '{user_by_sub.id}', but email belongs to user '{user_by_email.id}'."
                ),
                level=logging.WARNING,
            )
            raise ConflictError(
                "An account linking conflict was detected. Please contact support.",
                code="IDENTITY_CONFLICT",
            )

        user: User
        if user_by_sub is not None:
            # Case A: Existing linked account
            user = user_by_sub
            log_security_event(
                event_type="auth.supabase.exchange",
                outcome="success",
                actor_user_id=str(user.id),
                message=f"Authenticated existing linked Supabase user '{identity.supabase_user_id}'.",
            )
        elif user_by_email is not None:
            # Case B: Existing unlinked account with matching email
            # Security Rule: Never silently link unverified emails. Supabase email must be confirmed!
            if not identity.is_email_verified:
                log_security_event(
                    event_type="auth.supabase.exchange",
                    outcome="denied",
                    actor_user_id=str(user_by_email.id),
                    message=(
                        f"Refused to link unverified Supabase email '{identity.email}' "
                        f"to existing account '{user_by_email.id}'."
                    ),
                    level=logging.WARNING,
                )
                raise UnauthorizedError(
                    "Google email address is not verified. Account linking refused.",
                    code="UNVERIFIED_EMAIL",
                )

            # Check if existing user already has a different supabase_auth_id linked
            if user_by_email.supabase_auth_id and user_by_email.supabase_auth_id != identity.supabase_user_id:
                log_security_event(
                    event_type="auth.supabase.exchange",
                    outcome="denied",
                    actor_user_id=str(user_by_email.id),
                    message=(
                        f"Account '{user_by_email.id}' is already linked to another identity "
                        f"'{user_by_email.supabase_auth_id}'."
                    ),
                    level=logging.WARNING,
                )
                raise ConflictError(
                    "This account is already linked to a different identity provider account.",
                    code="IDENTITY_CONFLICT",
                )

            # Safely link account
            self._user_repo.link_supabase_auth_id(
                user_by_email,
                identity.supabase_user_id,
                mark_email_verified=True,
                verified_at=now,
            )
            self._db.commit()
            self._db.refresh(user_by_email)
            user = user_by_email

            log_security_event(
                event_type="auth.supabase.link",
                outcome="success",
                actor_user_id=str(user.id),
                message=(
                    f"Linked verified Supabase identity '{identity.supabase_user_id}' "
                    f"to existing user '{user.id}' ({user.email})."
                ),
            )
        else:
            # Case C: New Google user
            default_role = self._rbac_repo.get_role_by_name(RoleName.STANDARD_USER.value)
            if default_role is None:
                raise ServiceUnavailableError(
                    "Platform role catalog is not initialised.",
                    code="RBAC_CATALOG_NOT_READY",
                )

            full_name = identity.full_name or identity.email.split("@")[0].capitalize()
            try:
                user = self._user_repo.create(
                    full_name=full_name,
                    email=identity.email,
                    password_hash=None,
                    supabase_auth_id=identity.supabase_user_id,
                    status=UserStatus.ACTIVE.value,
                    is_email_verified=identity.is_email_verified,
                    email_verified_at=now if identity.is_email_verified else None,
                )
                self._rbac_repo.assign_role(
                    user_id=user.id,
                    role_id=default_role.id,
                    assigned_by_id=None,
                )
                self._db.commit()
                self._db.refresh(user)
            except IntegrityError as exc:
                self._db.rollback()
                raise ConflictError(
                    "An account with this email address already exists.",
                    code="ACCOUNT_ALREADY_EXISTS",
                ) from exc

            log_security_event(
                event_type="auth.supabase.register",
                outcome="success",
                actor_user_id=str(user.id),
                message=(
                    f"Registered new platform user '{user.id}' via Google/Supabase Auth "
                    f"with default standard_user role."
                ),
            )

        # Eligibility check: Ensure account status is active
        if user.status != UserStatus.ACTIVE.value:
            log_security_event(
                event_type="auth.supabase.exchange",
                outcome="denied",
                actor_user_id=str(user.id),
                message=f"Rejected Supabase exchange for user with non-active status '{user.status}'.",
                level=logging.WARNING,
            )
            raise UnauthorizedError(
                "Your account is inactive or disabled. Please contact an administrator.",
                code="ACCOUNT_INACTIVE",
            )

        # Issue standard Handover tokens and refresh session family
        token_family_id = uuid.uuid4()
        raw_refresh_token = generate_refresh_token()
        token_hash = hash_refresh_token(raw_refresh_token)
        expires_at = now + timedelta(days=self._settings.security.jwt_refresh_token_expire_days)

        self._refresh_repo.create(
            user_id=user.id,
            token_family_id=token_family_id,
            token_hash=token_hash,
            expires_at=expires_at,
            session_metadata=session_metadata,
        )
        self._user_repo.update_last_login(user, now)
        roles, permissions = self._rbac_repo.get_user_platform_roles_and_permissions(user.id)
        access_token_jwt, expires_in = create_access_token(
            user_id=user.id,
            session_family_id=token_family_id,
            settings=self._settings,
            now=now,
        )
        self._db.commit()
        self._db.refresh(user)

        log_security_event(
            event_type="auth.supabase.session_created",
            outcome="success",
            actor_user_id=str(user.id),
            message="Issued Handover session for verified Supabase identity.",
        )

        return (
            AccessTokenResponse(
                access_token=access_token_jwt,
                expires_in=expires_in,
                user=build_authenticated_user(
                    user,
                    roles=roles,
                    permissions=permissions,
                ),
            ),
            raw_refresh_token,
        )

    def request_password_reset(
        self,
        payload: ForgotPasswordRequest,
        session_metadata: dict[str, str] | None = None,
    ) -> ForgotPasswordResponse:
        """Issue password reset token for valid active user without revealing account existence."""
        user = self._user_repo.get_by_email(payload.email)
        now = utc_now()

        # Constant message to prevent user enumeration
        generic_message = (
            "If an account exists with this email address, password reset instructions have been generated."
        )

        if user is None:
            # Protect timing attack
            verify_dummy_password("dummy_password_for_timing")
            log_security_event(
                event_type="auth.password_reset.requested",
                outcome="denied",
                message=f"Password reset requested for non-existent email '{payload.email}'.",
                level=logging.INFO,
            )
            return ForgotPasswordResponse(message=generic_message, reset_token=None)

        if user.status != UserStatus.ACTIVE.value:
            log_security_event(
                event_type="auth.password_reset.requested",
                outcome="denied",
                actor_user_id=str(user.id),
                message=f"Password reset requested for inactive account '{user.id}' (status: {user.status}).",
                level=logging.WARNING,
            )
            return ForgotPasswordResponse(message=generic_message, reset_token=None)

        # Invalidate any existing unused reset tokens for this user
        self._reset_token_repo.invalidate_active_tokens_for_user(user.id, now)

        # Generate fresh opaque high-entropy token (30-minute validity)
        raw_reset_token = secrets.token_urlsafe(32)
        token_hash = hash_opaque_token(raw_reset_token)
        expires_at = now + timedelta(minutes=30)

        self._reset_token_repo.create(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
            request_metadata=session_metadata,
        )
        self._db.commit()

        log_security_event(
            event_type="auth.password_reset.token_issued",
            outcome="success",
            actor_user_id=str(user.id),
            message=f"Issued password reset token for user '{user.id}'.",
        )

        # In development/local environments (APP_ENV!=production), expose the reset_token
        # so developers and automated tests can complete the reset flow without an SMTP relay.
        is_dev = self._settings.app_env.lower() in ("development", "test", "testing", "local")
        return ForgotPasswordResponse(
            message=generic_message,
            reset_token=raw_reset_token if is_dev else None,
        )

    def reset_password(
        self,
        payload: ResetPasswordRequest,
    ) -> ResetPasswordResponse:
        """Validate reset token, update password hash, invalidate token, and revoke active refresh sessions."""
        now = utc_now()
        token_hash = hash_opaque_token(payload.token)

        token_record = self._reset_token_repo.get_by_token_hash_for_update(token_hash)
        if token_record is None:
            log_security_event(
                event_type="auth.password_reset.reset",
                outcome="denied",
                message="Password reset attempt with invalid or non-existent token.",
                level=logging.WARNING,
            )
            raise UnauthorizedError(
                "Invalid or expired password reset token.",
                code="INVALID_RESET_TOKEN",
            )

        if token_record.used_at is not None:
            log_security_event(
                event_type="auth.password_reset.reset",
                outcome="denied",
                actor_user_id=str(token_record.user_id),
                message="Password reset attempt with already used token.",
                level=logging.WARNING,
            )
            raise UnauthorizedError(
                "This password reset link has already been used.",
                code="RESET_TOKEN_ALREADY_USED",
            )

        # Ensure timezone-aware comparison
        expires_at_utc = ensure_utc(token_record.expires_at)
        if expires_at_utc <= now:
            log_security_event(
                event_type="auth.password_reset.reset",
                outcome="denied",
                actor_user_id=str(token_record.user_id),
                message="Password reset attempt with expired token.",
                level=logging.WARNING,
            )
            raise UnauthorizedError(
                "This password reset link has expired.",
                code="RESET_TOKEN_EXPIRED",
            )

        user = token_record.user
        if user is None or user.status != UserStatus.ACTIVE.value:
            log_security_event(
                event_type="auth.password_reset.reset",
                outcome="denied",
                actor_user_id=str(token_record.user_id),
                message="Password reset attempt for non-active user.",
                level=logging.WARNING,
            )
            raise UnauthorizedError(
                "Account is not eligible for password reset.",
                code="ACCOUNT_NOT_ELIGIBLE",
            )

        # Mark token as used
        self._reset_token_repo.mark_used(token_record, now)

        # Update password hash with Argon2id
        new_password_digest = hash_password(payload.new_password)
        self._user_repo.update_password_hash(user, new_password_digest)

        # Revoke all existing active refresh sessions to secure account
        self._refresh_repo.revoke_all_for_user(
            user_id=user.id,
            reason="PASSWORD_RESET",
            now=now,
        )

        self._db.commit()

        log_security_event(
            event_type="auth.password_reset.success",
            outcome="success",
            actor_user_id=str(user.id),
            message=f"Password successfully reset for user '{user.id}'. All active refresh sessions revoked.",
        )

        return ResetPasswordResponse(
            message="Your password has been successfully reset. Please log in with your new password.",
        )

