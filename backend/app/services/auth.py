"""Platform authentication, Argon2id password, JWT, and rotated refresh session service."""

from __future__ import annotations

import logging
import secrets
import uuid
from datetime import timedelta

from typing import TYPE_CHECKING

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    GoneError,
    NotFoundError,
    ServiceUnavailableError,
    UnauthorizedError,
)
from app.core.logging import log_security_event
from app.core.rbac_catalog import ORG_ROLE_RANK, PROJECT_ROLE_RANK
from app.core.security import (
    create_access_token,
    decode_email_verification_token,
    ensure_utc,
    generate_email_verification_token,
    generate_refresh_token,
    hash_opaque_token,
    hash_password,
    hash_refresh_token,
    utc_now,
    verify_dummy_password,
    verify_password,
)
from app.core.validators import validate_password_strength
from app.models.enums import (
    InvitationStatus,
    OrganisationStatus,
    ProjectStatus,
    RevocationReason,
    RoleName,
    RoleScopeType,
    UserStatus,
)
from app.models.user import User
from app.repositories.auth import PasswordResetTokenRepository, RefreshSessionRepository
from app.repositories.organisation import OrganisationRepository
from app.repositories.project import ProjectRepository
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
    RegisterWithInvitationRequest,
    RegisterWithInvitationResponse,
    RequestEmailVerificationRequest,
    RequestEmailVerificationResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
    RevokeSessionResponse,
    SessionListResponse,
    VerifyEmailRequest,
    VerifyEmailResponse,
)

if TYPE_CHECKING:
    from app.services.organisation import OrganisationService
from app.schemas.user import AuthenticatedUserResponse, UserSummaryResponse
from app.services.email import EmailDeliveryStatus, TransactionalEmailService, build_email_provider
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
        org_repository: OrganisationRepository | None = None,
        project_repository: ProjectRepository | None = None,
        org_service: OrganisationService | None = None,
        email_service: TransactionalEmailService | None = None,
    ) -> None:
        self._settings = settings
        self._db = db_session
        self._user_repo = user_repository
        self._refresh_repo = refresh_repository
        self._rbac_repo = rbac_repository
        self._reset_token_repo = reset_token_repository or PasswordResetTokenRepository(db_session)
        self._supabase_verifier = supabase_verifier or SupabaseTokenVerifier(settings)
        self._org_repo = org_repository or OrganisationRepository(db_session)
        self._project_repo = project_repository or ProjectRepository(db_session)
        self._org_service = org_service
        self._email_service = email_service or TransactionalEmailService(
            settings=settings,
            provider=build_email_provider(settings),
        )

    def _get_or_create_org_service(self) -> OrganisationService:
        if self._org_service is not None:
            return self._org_service
        from app.repositories.audit import AuditLogRepository
        from app.services.audit import AuditService
        from app.services.organisation import OrganisationService
        from app.services.rbac import RbacService

        rbac_service = RbacService(
            rbac_repository=self._rbac_repo,
            organisation_repository=self._org_repo,
            project_repository=self._project_repo,
        )
        audit_service = AuditService(audit_repository=AuditLogRepository(self._db))
        return OrganisationService(
            settings=self._settings,
            db_session=self._db,
            org_repository=self._org_repo,
            project_repository=self._project_repo,
            rbac_repository=self._rbac_repo,
            user_repository=self._user_repo,
            rbac_service=rbac_service,
            audit_service=audit_service,
            email_service=self._email_service,
        )

    def _dispatch_verification_email(
        self, *, user: User, raw_token: str
    ) -> tuple[EmailDeliveryStatus, str]:
        """Dispatch email verification message and return (delivery_status, user_message)."""
        result = self._email_service.send_verification_email(
            to_email=user.email,
            recipient_name=user.full_name,
            raw_token=raw_token,
        )
        if result.status == "submitted":
            return (
                "submitted",
                "Verification email sent. Please check your inbox and spam folder to verify your email address.",
            )
        if result.status == "failed":
            log_security_event(
                event_type="auth.email_verification_delivery_failed",
                outcome="failed",
                actor_user_id=str(user.id),
                message=f"Verification email delivery failed via provider '{result.provider}'.",
            )
            err_detail = f": {result.error_message}" if result.error_message else "."
            return (
                "failed",
                f"Verification email delivery failed{err_detail} Please request a new verification email.",
            )
        return (
            "not_configured",
            "Email verification delivery is not yet configured in this environment.",
        )

    def _dispatch_password_reset_email(
        self, *, user: User, raw_token: str
    ) -> tuple[EmailDeliveryStatus, str]:
        """Dispatch password reset message and return (delivery_status, user_message)."""
        result = self._email_service.send_password_reset_email(
            to_email=user.email,
            recipient_name=user.full_name,
            raw_token=raw_token,
            expires_in_minutes=30,
        )
        if result.status == "submitted":
            return (
                "submitted",
                "Password reset email dispatched successfully.",
            )
        if result.status == "failed":
            log_security_event(
                event_type="auth.password_reset_delivery_failed",
                outcome="failed",
                actor_user_id=str(user.id),
                message=f"Password reset email delivery failed via provider '{result.provider}'.",
            )
            err_detail = f": {result.error_message}" if result.error_message else "."
            return (
                "failed",
                f"Password reset email delivery failed{err_detail}",
            )
        return (
            "not_configured",
            "Password reset email delivery is not configured in this environment.",
        )

    def _create_user_record_uncommitted(
        self,
        *,
        full_name: str,
        email: str,
        password: str,
    ) -> tuple[User, Any]:
        """Create a platform user and assign standard_user role within the current transaction."""
        if self._user_repo.get_by_email(email) is not None:
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

        password_digest = hash_password(password)
        user = self._user_repo.create(
            full_name=full_name,
            email=email,
            password_hash=password_digest,
            status=UserStatus.ACTIVE.value,
            is_email_verified=False,
        )
        self._rbac_repo.assign_role(
            user_id=user.id,
            role_id=default_role.id,
            assigned_by_id=None,
        )
        self._db.flush()
        return user, default_role

    def register(self, payload: RegisterRequest) -> RegisterResponse:
        """Create a new platform account with Argon2id password hash and default role."""
        try:
            user, default_role = self._create_user_record_uncommitted(
                full_name=payload.full_name,
                email=payload.email,
                password=payload.password,
            )
            self._db.commit()
            self._db.refresh(user)
        except IntegrityError as exc:
            self._db.rollback()
            raise ConflictError(
                "An account with this email address already exists.",
                code="ACCOUNT_ALREADY_EXISTS",
            ) from exc

        now = utc_now()
        log_security_event(
            event_type="auth.register",
            outcome="success",
            actor_user_id=str(user.id),
            message="Registered new platform account with default standard_user role.",
        )
        token = generate_email_verification_token(
            user_id=user.id,
            email=user.email,
            settings=self._settings,
            now=now,
        )
        delivery_status, delivery_message = self._dispatch_verification_email(
            user=user,
            raw_token=token,
        )
        is_dev = self._settings.app_env.lower() in ("development", "test", "testing", "local")
        return RegisterResponse(
            user=build_user_summary(user, roles=[default_role.name]),
            email_verification_required=True,
            email_verification_delivery=delivery_status,
            development_verification_token=token if is_dev else None,
            message=(
                "Account registered. Email verification delivery is not yet configured "
                "in this environment."
                if delivery_status == "not_configured"
                else delivery_message
            ),
        )

    def register_with_invitation(
        self,
        payload: RegisterWithInvitationRequest,
        org_service: OrganisationService | None = None,
    ) -> RegisterWithInvitationResponse:
        """Register a new platform user account and accept an invitation atomically in one transaction."""
        cleaned_token = payload.invitation_token.strip()
        if not cleaned_token:
            raise NotFoundError("Invitation was not found.", code="INVITATION_NOT_FOUND")

        token_hash = hash_opaque_token(cleaned_token)
        invitation = self._org_repo.get_invitation_by_token_hash_for_update(token_hash)
        if invitation is None:
            raise NotFoundError("Invitation was not found.", code="INVITATION_NOT_FOUND")

        # Verify email match if client submitted email
        if payload.email is not None and payload.email != invitation.email:
            raise ForbiddenError(
                "This invitation was issued for a different email address.",
                code="INVITATION_EMAIL_MISMATCH",
            )

        # Pre-validate invitation status
        if invitation.status == InvitationStatus.ACCEPTED.value:
            raise ConflictError(
                "This invitation has already been accepted.",
                code="INVITATION_ALREADY_ACCEPTED",
            )
        if invitation.status == InvitationStatus.REVOKED.value:
            raise ConflictError(
                "This invitation has been revoked.",
                code="INVITATION_REVOKED",
            )

        now = utc_now()
        if (
            invitation.status == InvitationStatus.EXPIRED.value
            or ensure_utc(invitation.expires_at) <= now
        ):
            if invitation.status == InvitationStatus.PENDING.value:
                invitation.status = InvitationStatus.EXPIRED.value
                self._db.commit()
            raise GoneError(
                "This invitation has expired.",
                code="INVITATION_EXPIRED",
            )

        # Pre-validate organisation
        organisation = invitation.organisation
        if organisation.status == OrganisationStatus.ARCHIVED.value:
            raise ConflictError("Organisation is archived.", code="ORGANISATION_ARCHIVED")
        if organisation.status != OrganisationStatus.ACTIVE.value:
            raise ConflictError("Organisation is not active.", code="ORGANISATION_NOT_ACTIVE")

        # Pre-validate inviter authority
        inviter_org_membership = self._org_repo.get_active_membership(
            organisation_id=invitation.organisation_id,
            user_id=invitation.invited_by_id,
        )
        if inviter_org_membership is None:
            raise ForbiddenError(
                "The inviter no longer holds authority to grant this role.",
                code="INVITER_NO_LONGER_AUTHORISED",
            )

        # Pre-validate project if project invitation
        if invitation.project_id is not None:
            project = invitation.project or self._project_repo.get_by_id(invitation.project_id)
            if project is None:
                raise NotFoundError("Project was not found.", code="PROJECT_NOT_FOUND")
            if project.status == ProjectStatus.ARCHIVED.value:
                raise ConflictError("Project is archived.", code="PROJECT_ARCHIVED")
            if project.organisation_id != invitation.organisation_id:
                raise ForbiddenError(
                    "Project does not belong to the invitation organisation.",
                    code="TENANT_MISMATCH",
                )

            target_project_role = invitation.project_role
            if (
                target_project_role is None
                or target_project_role.scope_type != RoleScopeType.PROJECT.value
            ):
                raise ForbiddenError("Invalid project role scope.", code="INVALID_ROLE_SCOPE")

            is_inviter_org_admin = inviter_org_membership.role.name in (
                RoleName.ORG_OWNER.value,
                RoleName.ORG_ADMIN.value,
            )
            if not is_inviter_org_admin:
                inviter_proj_membership = self._project_repo.get_active_membership(
                    project_id=project.id,
                    user_id=invitation.invited_by_id,
                )
                inviter_proj_perms = (
                    {
                        rp.permission.code
                        for rp in inviter_proj_membership.role.role_permissions
                        if rp.permission is not None
                    }
                    if inviter_proj_membership is not None
                    else set()
                )
                inviter_proj_rank = (
                    PROJECT_ROLE_RANK.get(inviter_proj_membership.role.name, 0)
                    if inviter_proj_membership is not None
                    else 0
                )
                target_proj_rank = PROJECT_ROLE_RANK.get(target_project_role.name, 999)

                if (
                    inviter_proj_membership is None
                    or "project.invitations.manage" not in inviter_proj_perms
                    or inviter_proj_rank < target_proj_rank
                ):
                    raise ForbiddenError(
                        "The inviter no longer holds authority to grant this project role.",
                        code="INVITER_NO_LONGER_AUTHORISED",
                    )
        else:
            target_role = invitation.role
            if target_role is None or target_role.scope_type != RoleScopeType.ORGANISATION.value:
                raise ForbiddenError("Invalid invitation role scope.", code="INVALID_ROLE_SCOPE")

            inviter_perms = {
                rp.permission.code
                for rp in inviter_org_membership.role.role_permissions
                if rp.permission is not None
            }
            inviter_rank = ORG_ROLE_RANK.get(inviter_org_membership.role.name, 0)
            if (
                "organisation.invitations.manage" not in inviter_perms
                or inviter_rank < ORG_ROLE_RANK.get(target_role.name, 999)
            ):
                raise ForbiddenError(
                    "The inviter no longer holds authority to grant this organisation role.",
                    code="INVITER_NO_LONGER_AUTHORISED",
                )

        # Check if an account already exists for this email
        existing_user = self._user_repo.get_by_email(invitation.email)
        if existing_user is not None:
            raise ConflictError(
                "An account with this email address already exists. Please sign in to accept your invitation.",
                code="ACCOUNT_ALREADY_EXISTS",
            )

        # Validate password strength against invitation.email
        validate_password_strength(payload.password, email=invitation.email)

        active_org_service = org_service or self._get_or_create_org_service()

        # Atomic transaction boundary
        try:
            user, default_role = self._create_user_record_uncommitted(
                full_name=payload.full_name,
                email=invitation.email,
                password=payload.password,
            )

            acting_principal = AuthenticatedPrincipal(
                user=user,
                session_family_id=uuid.uuid4(),
                roles=(default_role.name,),
                permissions=frozenset(),
            )

            accept_res = active_org_service.accept_invitation(
                raw_token=cleaned_token,
                acting_principal=acting_principal,
                commit=False,
            )

            log_security_event(
                event_type="auth.register",
                outcome="success",
                actor_user_id=str(user.id),
                message="Registered new platform account via invitation.",
            )

            self._db.commit()
            self._db.refresh(user)
        except Exception:
            self._db.rollback()
            raise

        token = generate_email_verification_token(
            user_id=user.id,
            email=user.email,
            settings=self._settings,
            now=now,
        )
        delivery_status, delivery_message = self._dispatch_verification_email(
            user=user,
            raw_token=token,
        )
        is_dev = self._settings.app_env.lower() in ("development", "test", "testing", "local")
        can_access = bool(user.is_email_verified)

        if not can_access:
            if delivery_status == "submitted":
                reg_inv_msg = "Account registered and invitation accepted. Verification email sent. Please check your inbox and spam folder."
            elif delivery_status == "failed":
                reg_inv_msg = f"Account registered and invitation accepted, but verification email delivery failed ({delivery_message}). Please request a new verification email."
            else:
                reg_inv_msg = "Account registered and invitation accepted. Email verification delivery is not yet configured in this environment."
        else:
            reg_inv_msg = "Account registered and invitation accepted successfully."

        return RegisterWithInvitationResponse(
            user=build_user_summary(user, roles=[default_role.name]),
            email_verification_required=True,
            email_verification_delivery=delivery_status,
            organisation_id=accept_res.organisation_id,
            organisation_name=accept_res.organisation_name,
            project_id=accept_res.project_id,
            project_name=accept_res.project_name,
            project_role_name=accept_res.project_role_name,
            project_membership_status=accept_res.project_membership_status,
            can_access_project_immediately=can_access,
            development_verification_token=token if is_dev else None,
            message=reg_inv_msg,
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

            # If existing user has a different supabase_auth_id, safely update/re-link it
            # since the email ownership is cryptographically verified by the identity provider.
            if user_by_email.supabase_auth_id and user_by_email.supabase_auth_id != identity.supabase_user_id:
                log_security_event(
                    event_type="auth.supabase.relink",
                    outcome="success",
                    actor_user_id=str(user_by_email.id),
                    message=(
                        f"Re-linked verified Supabase identity from '{user_by_email.supabase_auth_id}' "
                        f"to '{identity.supabase_user_id}' for user '{user_by_email.id}' ({user_by_email.email})."
                    ),
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

        # Dispatch transactional password reset email
        delivery_status, _ = self._dispatch_password_reset_email(
            user=user,
            raw_token=raw_reset_token,
        )

        # In development/local environments (APP_ENV!=production), expose the reset_token
        # so developers and automated tests can complete the reset flow without an SMTP relay.
        is_dev = self._settings.app_env.lower() in ("development", "test", "testing", "local")
        return ForgotPasswordResponse(
            message=generic_message,
            reset_token=raw_reset_token if is_dev else None,
            email_delivery=delivery_status,
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

        # If user was unverified, resetting password via token received at email proves ownership
        if not user.is_email_verified:
            user.is_email_verified = True
            user.email_verified_at = now

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

    def verify_email(self, *, token: str) -> VerifyEmailResponse:
        """Verify signed email verification token and activate email verified status."""
        user_id, token_email = decode_email_verification_token(token, self._settings)
        user = self._user_repo.get_by_id(user_id)
        if user is None:
            log_security_event(
                event_type="auth.email_verification.failed",
                outcome="denied",
                message=f"Email verification failed: user '{user_id}' not found.",
                level=logging.WARNING,
            )
            raise NotFoundError("User account was not found.", code="USER_NOT_FOUND")

        if user.email.lower() != token_email.lower():
            log_security_event(
                event_type="auth.email_verification.failed",
                outcome="denied",
                actor_user_id=str(user.id),
                message=f"Email verification failed: token email '{token_email}' != account '{user.email}'.",
                level=logging.WARNING,
            )
            raise ForbiddenError(
                "This verification link was issued for a different email address.",
                code="INVITATION_EMAIL_MISMATCH",
            )

        now = utc_now()
        if not user.is_email_verified:
            user.is_email_verified = True
            user.email_verified_at = now
            self._db.commit()
            self._db.refresh(user)

            log_security_event(
                event_type="auth.email_verified",
                outcome="success",
                actor_user_id=str(user.id),
                message=f"Successfully verified email address for user '{user.id}' ({user.email}).",
            )
            message = "Email address verified successfully. You may now access your organisation and project workspaces."
        else:
            message = "Email address is already verified."

        can_access = bool(user.status == UserStatus.ACTIVE.value and user.is_email_verified)
        return VerifyEmailResponse(
            message=message,
            email=user.email,
            is_email_verified=user.is_email_verified,
            can_access_project_immediately=can_access,
        )

    def request_email_verification(
        self,
        *,
        payload: RequestEmailVerificationRequest,
    ) -> RequestEmailVerificationResponse:
        """Generate email verification link for unverified account without disclosing existence."""
        normalised_email = str(payload.email).strip().lower()
        user = self._user_repo.get_by_email(normalised_email)
        now = utc_now()

        generic_message = (
            "If an account exists with this email address and is not yet verified, "
            "verification instructions have been generated."
        )

        if user is None:
            verify_dummy_password("dummy_timing_padding")
            log_security_event(
                event_type="auth.email_verification.requested",
                outcome="denied",
                message=f"Email verification requested for non-existent email '{normalised_email}'.",
            )
            return RequestEmailVerificationResponse(
                message=generic_message,
                email_verification_delivery="not_configured",
                development_verification_token=None,
            )

        if user.is_email_verified:
            return RequestEmailVerificationResponse(
                message="This email address is already verified.",
                email_verification_delivery="not_configured",
                development_verification_token=None,
            )

        token = generate_email_verification_token(
            user_id=user.id,
            email=user.email,
            settings=self._settings,
            now=now,
        )
        delivery_status, delivery_message = self._dispatch_verification_email(
            user=user,
            raw_token=token,
        )
        log_security_event(
            event_type="auth.email_verification.token_issued",
            outcome="success",
            actor_user_id=str(user.id),
            message=f"Issued email verification token for user '{user.id}'. Delivery status: {delivery_status}.",
        )

        is_dev = self._settings.app_env.lower() in ("development", "test", "testing", "local")
        return RequestEmailVerificationResponse(
            message=delivery_message,
            email_verification_delivery=delivery_status,
            development_verification_token=token if is_dev else None,
        )

    def request_email_verification_for_user(
        self,
        *,
        user: User,
    ) -> RequestEmailVerificationResponse:
        """Generate and dispatch verification email for a known authenticated user using their persisted email."""
        fresh_user = self._user_repo.get_by_id(user.id)
        if fresh_user is None or fresh_user.status != UserStatus.ACTIVE.value:
            raise UnauthorizedError("User account is inactive or not found.", code="USER_INACTIVE")

        if fresh_user.is_email_verified:
            return RequestEmailVerificationResponse(
                message="This email address is already verified.",
                email_verification_delivery="not_configured",
                development_verification_token=None,
            )

        now = utc_now()
        token = generate_email_verification_token(
            user_id=fresh_user.id,
            email=fresh_user.email,
            settings=self._settings,
            now=now,
        )
        delivery_status, delivery_message = self._dispatch_verification_email(
            user=fresh_user,
            raw_token=token,
        )
        log_security_event(
            event_type="auth.email_verification.resend_authenticated",
            outcome="success",
            actor_user_id=str(fresh_user.id),
            message=f"Resent email verification token for authenticated user '{fresh_user.id}'. Delivery status: {delivery_status}.",
        )

        is_dev = self._settings.app_env.lower() in ("development", "test", "testing", "local")
        return RequestEmailVerificationResponse(
            message=delivery_message,
            email_verification_delivery=delivery_status,
            development_verification_token=token if is_dev else None,
        )

