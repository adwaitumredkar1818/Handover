"""Pydantic request and response schemas for platform users and RBAC."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal
from zoneinfo import available_timezones

from pydantic import AfterValidator, Field, field_validator

from app.core.validators import normalize_and_validate_email
from app.schemas.common import BaseSchema

NormalisedEmail = Annotated[str, AfterValidator(normalize_and_validate_email)]

_VALID_TIMEZONES = available_timezones()


class UserPreferencesSchema(BaseSchema):
    """Persisted user-level UI, appearance, and workspace preferences."""

    theme: Literal["light", "dark", "system"] = "light"
    date_format: Literal["DD MMM YYYY", "MM/DD/YYYY", "YYYY-MM-DD"] = "DD MMM YYYY"
    density: Literal["comfortable", "compact"] = "comfortable"
    reduced_motion: bool = False
    default_landing_page: Literal["/dashboard", "/projects", "/handovers/received"] = "/dashboard"


class UserPreferencesUpdate(BaseSchema):
    """Partial update payload for user preferences."""

    theme: Literal["light", "dark", "system"] | None = None
    date_format: Literal["DD MMM YYYY", "MM/DD/YYYY", "YYYY-MM-DD"] | None = None
    density: Literal["comfortable", "compact"] | None = None
    reduced_motion: bool | None = None
    default_landing_page: Literal["/dashboard", "/projects", "/handovers/received"] | None = None


class UserSummaryResponse(BaseSchema):
    """Public/authenticated safe projection of a platform user (never exposes secrets)."""

    id: uuid.UUID
    full_name: str
    email: str
    status: str
    is_email_verified: bool
    email_verified_at: datetime | None
    job_title: str | None = None
    bio: str | None = None
    timezone: str = "UTC"
    has_avatar: bool = False
    avatar_url: str | None = None
    auth_method: Literal["password", "oauth", "hybrid"] = "password"
    preferences: UserPreferencesSchema = Field(default_factory=UserPreferencesSchema)
    roles: list[str]
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None


class UpdateMyProfileRequest(BaseSchema):
    """Self-service profile and preferences update payload."""

    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    job_title: str | None = Field(default=None, max_length=120)
    bio: str | None = Field(default=None, max_length=500)
    timezone: str | None = Field(default=None, max_length=64)
    preferences: UserPreferencesUpdate | None = None

    @field_validator("full_name")
    @classmethod
    def _clean_full_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        if len(cleaned) < 2:
            raise ValueError("Full name must be at least 2 characters.")
        return cleaned

    @field_validator("job_title", "bio")
    @classmethod
    def _clean_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if cleaned != "UTC" and cleaned not in _VALID_TIMEZONES:
            raise ValueError(f"Unsupported timezone '{cleaned}'. Use a valid IANA timezone.")
        return cleaned


class AuthenticatedUserResponse(UserSummaryResponse):
    """Authenticated user projection including resolved platform permissions."""

    permissions: list[str]


class UserListResponse(BaseSchema):
    """Paginated list of platform user accounts."""

    items: list[UserSummaryResponse]
    total: int


class UpdateUserStatusRequest(BaseSchema):
    """Request payload for administrative user account lifecycle updates."""

    status: Literal["active", "disabled", "locked"]


class RoleResponse(BaseSchema):
    """RBAC role metadata including its explicit scope boundary and permission codes."""

    id: uuid.UUID
    name: str
    display_name: str
    description: str | None
    scope_type: str
    is_system: bool
    permissions: list[str]


class RoleListResponse(BaseSchema):
    """Catalog of defined RBAC roles."""

    items: list[RoleResponse]


class AssignRoleRequest(BaseSchema):
    """Request to assign a platform-scoped role to a user account."""

    role_name: str = Field(min_length=1, max_length=64)

    @field_validator("role_name")
    @classmethod
    def _clean_role_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Role name must not be empty.")
        return cleaned


class AssignRoleResponse(BaseSchema):
    """Confirmation of a platform-level role assignment."""

    user_id: uuid.UUID
    role_name: str
    scope_type: str
    assigned_at: datetime
