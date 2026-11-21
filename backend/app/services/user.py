"""Platform user identity management service enforcing RBAC and user isolation."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import BadRequestError, ForbiddenError, NotFoundError
from app.core.logging import log_security_event
from app.core.security import utc_now
from app.models.enums import RevocationReason, UserStatus
from app.models.organisation import OrganisationMembership
from app.repositories.auth import RefreshSessionRepository
from app.repositories.user import UserRepository
from app.schemas.user import (
    AuthenticatedUserResponse,
    UpdateMyProfileRequest,
    UpdateUserStatusRequest,
    UserListResponse,
    UserSummaryResponse,
)
from app.services.auth import build_authenticated_user, build_user_summary
from app.services.rbac import AuthenticatedPrincipal, RbacService
from app.services.storage_factory import build_storage_backend

_MAX_AVATAR_BYTES = 2 * 1024 * 1024


def _sniff_avatar_image(content: bytes) -> tuple[str, str]:
    """Verify actual image magic bytes (PNG, JPEG, WEBP); never trust client headers."""
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", "png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", "jpg"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp", "webp"
    raise BadRequestError(
        "Unsupported image format. Please upload a valid PNG, JPEG, or WebP image.",
        code="INVALID_AVATAR_FORMAT",
    )


class UserService:
    """Identity management operations with strict permission and isolation boundaries."""

    def __init__(
        self,
        *,
        db_session: Session,
        user_repository: UserRepository,
        refresh_repository: RefreshSessionRepository,
        rbac_service: RbacService,
    ) -> None:
        self._db = db_session
        self._user_repo = user_repository
        self._refresh_repo = refresh_repository
        self._rbac_service = rbac_service

    def get_user_profile(
        self,
        *,
        target_user_id: uuid.UUID,
        acting_principal: AuthenticatedPrincipal,
    ) -> UserSummaryResponse:
        """Enforce self-read (`account.profile.read`) vs cross-user read (`platform.users.read`)."""
        if target_user_id == acting_principal.user.id:
            self._rbac_service.require_permissions(
                acting_principal,
                ("account.profile.read",),
            )
        else:
            self._rbac_service.require_permissions(
                acting_principal,
                ("platform.users.read",),
            )

        user = self._user_repo.get_by_id(target_user_id)
        if user is None:
            raise NotFoundError("User account was not found.", code="USER_NOT_FOUND")
        return build_user_summary(user)

    def list_users(self, *, limit: int = 50, offset: int = 0) -> UserListResponse:
        """List platform user accounts cleanly."""
        users = self._user_repo.list_users(limit=limit, offset=offset)
        total = self._user_repo.count_users()
        return UserListResponse(
            items=[build_user_summary(u) for u in users],
            total=total,
        )

    def update_user_status(
        self,
        *,
        target_user_id: uuid.UUID,
        payload: UpdateUserStatusRequest,
        acting_principal: AuthenticatedPrincipal,
    ) -> UserSummaryResponse:
        """Update user lifecycle status and revoke active sessions if deactivated."""
        if (
            target_user_id == acting_principal.user.id
            and payload.status != UserStatus.ACTIVE.value
        ):
            raise BadRequestError(
                "You cannot deactivate or lock your own account.",
                code="SELF_STATUS_CHANGE_FORBIDDEN",
            )

        user = self._user_repo.get_by_id(target_user_id)
        if user is None:
            raise NotFoundError("User account was not found.", code="USER_NOT_FOUND")

        self._user_repo.update_status(user, payload.status)
        if payload.status != UserStatus.ACTIVE.value:
            self._refresh_repo.revoke_all_for_user(
                user_id=user.id,
                reason=RevocationReason.USER_DISABLED.value,
                now=utc_now(),
            )

        self._db.commit()
        refreshed = self._user_repo.get_by_id(user.id) or user

        log_security_event(
            event_type="user.status_updated",
            outcome="success",
            actor_user_id=str(acting_principal.user.id),
            message=f"Updated account '{refreshed.id}' status to '{refreshed.status}'.",
        )
        return build_user_summary(refreshed)

    def update_my_profile(
        self,
        *,
        acting_principal: AuthenticatedPrincipal,
        payload: UpdateMyProfileRequest,
    ) -> AuthenticatedUserResponse:
        """Update the authenticated user's own profile and UI preferences."""
        user = self._user_repo.get_by_id(acting_principal.user.id)
        if user is None:
            raise NotFoundError("User account was not found.", code="USER_NOT_FOUND")

        fields_set = payload.model_fields_set
        if "full_name" in fields_set and payload.full_name is not None:
            user.full_name = payload.full_name
        if "job_title" in fields_set:
            user.job_title = payload.job_title
        if "bio" in fields_set:
            user.bio = payload.bio
        if "timezone" in fields_set and payload.timezone is not None:
            user.timezone = payload.timezone
        if payload.preferences is not None:
            existing_prefs: dict[str, Any] = dict(user.preferences_json or {})
            ui_prefs: dict[str, Any] = dict(existing_prefs.get("ui") or {})
            pref_patch = payload.preferences.model_dump(exclude_none=True)
            ui_prefs.update(pref_patch)
            existing_prefs["ui"] = ui_prefs
            user.preferences_json = existing_prefs

        user.updated_at = utc_now()
        self._db.commit()
        refreshed = self._user_repo.get_by_id(user.id) or user

        log_security_event(
            event_type="account.profile_updated",
            outcome="success",
            actor_user_id=str(refreshed.id),
            message="User updated personal profile and preferences.",
        )
        return build_authenticated_user(
            refreshed,
            roles=acting_principal.roles,
            permissions=acting_principal.permissions,
        )

    def upload_my_avatar(
        self,
        *,
        acting_principal: AuthenticatedPrincipal,
        content: bytes,
        settings: Settings,
    ) -> AuthenticatedUserResponse:
        """Validate image magic bytes and store encrypted avatar in private storage."""
        if not content:
            raise BadRequestError("Avatar file is empty.", code="EMPTY_AVATAR_FILE")
        if len(content) > _MAX_AVATAR_BYTES:
            raise BadRequestError(
                "Avatar image must be 2 MB or smaller.",
                code="AVATAR_TOO_LARGE",
            )

        content_type, ext = _sniff_avatar_image(content)
        user = self._user_repo.get_by_id(acting_principal.user.id)
        if user is None:
            raise NotFoundError("User account was not found.", code="USER_NOT_FOUND")

        storage = build_storage_backend(settings)
        stored = storage.store_encrypted_bytes(
            organisation_id=user.id,
            project_id=user.id,
            data=content,
        )

        old_key = user.avatar_storage_key
        user.avatar_storage_key = stored.storage_object_key
        user.avatar_content_type = content_type
        user.updated_at = utc_now()
        self._db.commit()

        if old_key:
            try:
                storage.delete_object(storage_object_key=old_key)
            except Exception:
                pass

        refreshed = self._user_repo.get_by_id(user.id) or user
        log_security_event(
            event_type="account.avatar_updated",
            outcome="success",
            actor_user_id=str(refreshed.id),
            message="User uploaded a new profile avatar.",
        )
        return build_authenticated_user(
            refreshed,
            roles=acting_principal.roles,
            permissions=acting_principal.permissions,
        )

    def delete_my_avatar(
        self,
        *,
        acting_principal: AuthenticatedPrincipal,
        settings: Settings,
    ) -> AuthenticatedUserResponse:
        """Remove the authenticated user's stored avatar."""
        user = self._user_repo.get_by_id(acting_principal.user.id)
        if user is None:
            raise NotFoundError("User account was not found.", code="USER_NOT_FOUND")

        old_key = user.avatar_storage_key
        user.avatar_storage_key = None
        user.avatar_content_type = None
        user.updated_at = utc_now()
        self._db.commit()

        if old_key:
            try:
                build_storage_backend(settings).delete_object(storage_object_key=old_key)
            except Exception:
                pass

        refreshed = self._user_repo.get_by_id(user.id) or user
        log_security_event(
            event_type="account.avatar_removed",
            outcome="success",
            actor_user_id=str(refreshed.id),
            message="User removed profile avatar.",
        )
        return build_authenticated_user(
            refreshed,
            roles=acting_principal.roles,
            permissions=acting_principal.permissions,
        )

    def get_user_avatar(
        self,
        *,
        target_user_id: uuid.UUID,
        acting_principal: AuthenticatedPrincipal,
        settings: Settings,
    ) -> tuple[bytes, str]:
        """Stream decrypted avatar bytes if caller is self or shares an active organisation."""
        if target_user_id != acting_principal.user.id:
            my_orgs = select(OrganisationMembership.organisation_id).where(
                OrganisationMembership.user_id == acting_principal.user.id,
                OrganisationMembership.status == "active",
            )
            shared = self._db.scalar(
                select(OrganisationMembership.id).where(
                    OrganisationMembership.user_id == target_user_id,
                    OrganisationMembership.status == "active",
                    OrganisationMembership.organisation_id.in_(my_orgs),
                )
            )
            if shared is None and "platform.users.read" not in acting_principal.permissions:
                raise ForbiddenError(
                    "You do not have permission to view this user's avatar.",
                    code="AVATAR_ACCESS_DENIED",
                )

        user = self._user_repo.get_by_id(target_user_id)
        if user is None or not user.avatar_storage_key:
            raise NotFoundError("Profile avatar was not found.", code="AVATAR_NOT_FOUND")

        data = build_storage_backend(settings).read_decrypted_bytes(
            storage_object_key=user.avatar_storage_key,
            organisation_id=user.id,
            project_id=user.id,
        )
        return data, user.avatar_content_type or "image/png"
