"""Pydantic request and response schemas for platform authentication and sessions."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import ConfigDict, Field, field_validator, model_validator

from app.core.validators import validate_password_strength
from app.schemas.common import BaseSchema
from app.schemas.user import AuthenticatedUserResponse, NormalisedEmail, UserSummaryResponse


class RegisterRequest(BaseSchema):
    """Platform registration payload (email normalised; password strength enforced)."""

    full_name: str = Field(min_length=2, max_length=255)
    email: NormalisedEmail
    password: str

    @field_validator("full_name")
    @classmethod
    def _normalize_full_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) < 2:
            raise ValueError("Full name must contain at least 2 non-whitespace characters.")
        return cleaned

    @model_validator(mode="after")
    def _validate_password(self) -> RegisterRequest:
        validate_password_strength(self.password, email=self.email)
        return self


class RegisterResponse(BaseSchema):
    """Registration result clearly stating email verification delivery status."""

    user: UserSummaryResponse
    email_verification_required: bool = True
    email_verification_delivery: Literal["not_configured", "submitted", "failed"] = "not_configured"
    development_verification_token: str | None = None
    message: str


class RegisterWithInvitationRequest(BaseSchema):
    """Platform registration payload using an invitation token."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    invitation_token: str = Field(min_length=1, max_length=512)
    full_name: str = Field(min_length=2, max_length=255)
    password: str = Field(min_length=12, max_length=128)
    email: NormalisedEmail | None = None

    @field_validator("full_name")
    @classmethod
    def _normalize_full_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) < 2:
            raise ValueError("Full name must contain at least 2 non-whitespace characters.")
        return cleaned

    @field_validator("invitation_token")
    @classmethod
    def _normalize_token(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Invitation token cannot be empty.")
        return cleaned

    @model_validator(mode="after")
    def _validate_password(self) -> RegisterWithInvitationRequest:
        validate_password_strength(self.password, email=self.email)
        return self


class RegisterWithInvitationResponse(BaseSchema):
    """Result of registering a new account using an invitation."""

    user: UserSummaryResponse
    email_verification_required: bool = True
    email_verification_delivery: Literal["not_configured", "submitted", "failed"] = "not_configured"
    organisation_id: uuid.UUID
    organisation_name: str
    project_id: uuid.UUID | None = None
    project_name: str | None = None
    project_role_name: str | None = None
    project_membership_status: str | None = None
    can_access_project_immediately: bool = False
    development_verification_token: str | None = None
    message: str


class VerifyEmailRequest(BaseSchema):
    """Payload to confirm account email verification using signed token."""

    token: str = Field(min_length=16, max_length=2048, description="Signed email verification token")


class VerifyEmailResponse(BaseSchema):
    """Confirmation of successful email verification."""

    message: str
    email: str
    is_email_verified: bool
    can_access_project_immediately: bool


class RequestEmailVerificationRequest(BaseSchema):
    """Payload to request or re-send email verification instructions."""

    email: NormalisedEmail | None = Field(default=None, description="Account email address")


class RequestEmailVerificationResponse(BaseSchema):
    """Confirmation of email verification request."""

    message: str
    email_verification_delivery: Literal["not_configured", "submitted", "failed"] = "not_configured"
    development_verification_token: str | None = None


class LoginRequest(BaseSchema):
    """Platform email/password login credentials."""

    email: NormalisedEmail
    password: str = Field(min_length=1, max_length=128)


class AccessTokenResponse(BaseSchema):
    """Short-lived access token response; refresh token travels solely via HttpOnly cookie."""

    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105
    expires_in: int
    user: AuthenticatedUserResponse


class LogoutResponse(BaseSchema):
    """Logout result after revoking the active refresh session and clearing cookie."""

    message: str
    revoked: bool


class RefreshSessionSummary(BaseSchema):
    """Safe metadata projection of a user's refresh session (never exposes hashes/tokens)."""

    id: uuid.UUID
    token_family_id: uuid.UUID
    created_at: datetime
    expires_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None
    revoked_reason: str | None
    is_current_family: bool
    session_metadata: dict[str, str] | None


class SessionListResponse(BaseSchema):
    """List of refresh sessions belonging strictly to the authenticated user."""

    items: list[RefreshSessionSummary]


class RevokeSessionResponse(BaseSchema):
    """Confirmation of revoking a specific session."""

    session_id: uuid.UUID
    revoked: bool
    message: str


class SupabaseExchangeRequest(BaseSchema):
    """Payload for exchanging a verified Supabase access token for a Handover session."""

    access_token: str = Field(min_length=1, max_length=4096, description="Supabase user access token (JWT)")


class ForgotPasswordRequest(BaseSchema):
    """Payload for requesting a password reset link."""

    email: NormalisedEmail = Field(description="Account email address")



class ForgotPasswordResponse(BaseSchema):
    """Generic confirmation response (preventing user enumeration)."""

    message: str = Field(description="Human-readable status message")
    reset_token: str | None = Field(
        default=None,
        description="Password reset token returned ONLY in development/testing mode when email delivery is not configured.",
    )
    email_delivery: Literal["not_configured", "submitted", "failed"] | None = Field(
        default=None,
        description="Status of the transactional password reset email dispatch.",
    )


class ResetPasswordRequest(BaseSchema):
    """Payload for resetting account password using token."""

    token: str = Field(min_length=16, max_length=256, description="Password reset token")
    new_password: str = Field(min_length=8, max_length=128, description="New account password")

    @classmethod
    def validate_new_password(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        return value


class ResetPasswordResponse(BaseSchema):
    """Confirmation of successful password reset."""

    message: str = Field(description="Human-readable success message")


class ChangePasswordRequest(BaseSchema):
    """Authenticated user password change payload."""

    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class ChangePasswordResponse(BaseSchema):
    """Confirmation of password update and other-session revocation."""

    message: str
    revoked_other_sessions: int = 0


class ChangeEmailRequest(BaseSchema):
    """Authenticated user email update payload requiring password confirmation."""

    new_email: NormalisedEmail
    current_password: str = Field(min_length=1, max_length=128)


class ChangeEmailResponse(BaseSchema):
    """Confirmation of email update and verification status."""

    email: str
    is_email_verified: bool
    email_delivery: Literal["not_configured", "submitted", "failed"] | None = None
    message: str


class RevokeOtherSessionsResponse(BaseSchema):
    """Confirmation of bulk session revocation."""

    revoked_count: int
    scope: Literal["others", "all"]
    message: str


class AccountDeletionRequest(BaseSchema):
    """High-risk account deletion request requiring explicit confirmation."""

    confirmation_text: str = Field(min_length=1, max_length=32)
    current_password: str | None = Field(default=None, max_length=128)
    reason: str | None = Field(default=None, max_length=500)


class AccountDeletionImpact(BaseSchema):
    """Pre-deletion impact assessment across memberships, handovers, and retention."""

    active_organisations: int
    sole_owner_organisations: int
    active_projects: int
    active_handover_participations: int
    canonical_evidence_preserved: bool = True
    audit_logs_preserved: bool = True


class AccountDeletionRequestResponse(BaseSchema):
    """Response for an account deletion request (never silently cascades shared evidence)."""

    status: Literal["pending_review", "blocked"]
    message: str
    impact: AccountDeletionImpact


class AccountDataExportResponse(BaseSchema):
    """Structured personal data export scoped strictly to the authenticated user."""

    exported_at: datetime
    profile: UserSummaryResponse
    organisation_memberships: list[dict[str, Any]]
    project_memberships: list[dict[str, Any]]
    sessions: list[RefreshSessionSummary]
    notification_preferences: dict[str, Any]
    recent_audit_events: list[dict[str, Any]]


