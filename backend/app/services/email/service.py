"""Application-level transactional email service decoupled from provider details."""

from __future__ import annotations

import logging
from urllib.parse import urlencode

from app.core.config import Settings
from app.services.email.base import EmailDeliveryResult, EmailMessage, EmailProviderProtocol
from app.services.email.providers import (
    DisabledEmailProvider,
    GmailSMTPEmailProvider,
    MockEmailProvider,
)
from app.services.email.templates import (
    render_email_verification,
    render_organisation_invitation,
    render_password_reset,
    render_project_invitation,
)

logger = logging.getLogger("app.services.email.service")

_ROLE_DISPLAY_MAP: dict[str, str] = {
    "project_manager": "Project Manager",
    "project_member": "Project Member",
    "reviewer": "Reviewer",
    "org_owner": "Organisation Owner",
    "org_admin": "Organisation Administrator",
    "org_member": "Organisation Member",
}


def build_email_provider(settings: Settings) -> EmailProviderProtocol:
    """Resolve configured email provider while failing safely when disabled or unconfigured."""
    email_cfg = settings.email
    if not email_cfg.delivery_enabled or email_cfg.provider == "none":
        return DisabledEmailProvider()
    if email_cfg.provider == "mock":
        return MockEmailProvider()
    if email_cfg.provider == "gmail_smtp":
        app_password = (
            email_cfg.smtp_app_password.get_secret_value()
            if email_cfg.smtp_app_password is not None
            else None
        )
        return GmailSMTPEmailProvider(
            host=email_cfg.smtp_host,
            port=email_cfg.smtp_port,
            username=email_cfg.smtp_username,
            app_password=app_password,
            use_tls=email_cfg.smtp_use_tls,
            from_address=email_cfg.from_address,
            from_name=email_cfg.from_name,
            timeout_seconds=email_cfg.smtp_timeout_seconds,
        )
    return DisabledEmailProvider()


class TransactionalEmailService:
    """Coordinates template rendering, URL generation, and safe provider submission."""

    def __init__(
        self,
        settings: Settings,
        provider: EmailProviderProtocol | None = None,
    ) -> None:
        self._settings = settings
        self._provider = provider or build_email_provider(settings)

    @property
    def provider(self) -> EmailProviderProtocol:
        return self._provider

    def _validated_frontend_base_url(self) -> str | None:
        base_url = self._settings.email.frontend_base_url.strip().rstrip("/")
        if not base_url:
            return None
        if self._settings.is_production and not base_url.startswith("https://"):
            logger.error("Invalid FRONTEND_BASE_URL in production: HTTPS is required.")
            return None
        if not (base_url.startswith("https://") or base_url.startswith("http://")):
            logger.error("Invalid FRONTEND_BASE_URL scheme.")
            return None
        return base_url

    def send_verification_email(
        self,
        *,
        to_email: str,
        recipient_name: str,
        raw_token: str,
    ) -> EmailDeliveryResult:
        """Render and send account email verification link without ever logging the token."""
        if not self._settings.email.delivery_enabled:
            return EmailDeliveryResult(status="not_configured", provider="none")

        base_url = self._validated_frontend_base_url()
        if base_url is None:
            return EmailDeliveryResult(
                status="failed",
                provider=self._provider.provider_name,
                error_message="Frontend base URL configuration is invalid.",
            )

        query = urlencode({"token": raw_token})
        verification_url = f"{base_url}/verify-email?{query}"
        rendered = render_email_verification(
            verification_url=verification_url,
            recipient_name=recipient_name,
            expires_hours=24,
        )
        result = self._provider.send(
            EmailMessage(
                to_email=to_email,
                subject=rendered.subject,
                html_body=rendered.html_body,
                text_body=rendered.text_body,
                tags={"category": "email_verification"},
            )
        )
        recipient_domain = to_email.split("@")[-1] if "@" in to_email else "unknown"
        logger.info(
            "Verification email dispatch completed: provider=%s status=%s recipient_domain=@%s",
            result.provider,
            result.status,
            recipient_domain,
        )
        if result.status == "failed":
            logger.warning("Verification email delivery failed: %s", result.error_message)
        return result

    def send_password_reset_email(
        self,
        *,
        to_email: str,
        recipient_name: str,
        raw_token: str,
        expires_in_minutes: int = 30,
    ) -> EmailDeliveryResult:
        """Render and send password reset link without ever logging the raw token."""
        if not self._settings.email.delivery_enabled:
            return EmailDeliveryResult(status="not_configured", provider="none")

        base_url = self._validated_frontend_base_url()
        if base_url is None:
            return EmailDeliveryResult(
                status="failed",
                provider=self._provider.provider_name,
                error_message="Frontend base URL configuration is invalid.",
            )

        query = urlencode({"token": raw_token})
        reset_url = f"{base_url}/reset-password?{query}"
        rendered = render_password_reset(
            reset_url=reset_url,
            recipient_name=recipient_name,
            expires_in_minutes=expires_in_minutes,
        )
        result = self._provider.send(
            EmailMessage(
                to_email=to_email,
                subject=rendered.subject,
                html_body=rendered.html_body,
                text_body=rendered.text_body,
                tags={"category": "password_reset"},
            )
        )
        recipient_domain = to_email.split("@")[-1] if "@" in to_email else "unknown"
        logger.info(
            "Password reset email dispatch completed: provider=%s status=%s recipient_domain=@%s",
            result.provider,
            result.status,
            recipient_domain,
        )
        if result.status == "failed":
            logger.warning("Password reset email delivery failed: %s", result.error_message)
        return result

    def send_project_invitation_email(
        self,
        *,
        to_email: str,
        raw_token: str,
        organisation_name: str,
        project_name: str,
        project_role_name: str,
        inviter_name: str | None,
        expires_in_hours: int,
    ) -> EmailDeliveryResult:
        """Render and send project invitation link without ever logging the raw token."""
        if not self._settings.email.delivery_enabled:
            return EmailDeliveryResult(status="not_configured", provider="none")

        base_url = self._validated_frontend_base_url()
        if base_url is None:
            return EmailDeliveryResult(
                status="failed",
                provider=self._provider.provider_name,
                error_message="Frontend base URL configuration is invalid.",
            )

        invitation_url = f"{base_url}/invitations/{raw_token}"
        role_display = _ROLE_DISPLAY_MAP.get(project_role_name, project_role_name)
        rendered = render_project_invitation(
            invitation_url=invitation_url,
            organisation_name=organisation_name,
            project_name=project_name,
            project_role_display=role_display,
            inviter_name=inviter_name,
            expires_in_hours=expires_in_hours,
        )
        result = self._provider.send(
            EmailMessage(
                to_email=to_email,
                subject=rendered.subject,
                html_body=rendered.html_body,
                text_body=rendered.text_body,
                tags={"category": "project_invitation"},
            )
        )
        logger.info(
            "Project invitation email dispatch completed: provider=%s status=%s",
            result.provider,
            result.status,
        )
        return result

    def send_organisation_invitation_email(
        self,
        *,
        to_email: str,
        raw_token: str,
        organisation_name: str,
        role_name: str,
        inviter_name: str | None,
        expires_in_hours: int,
    ) -> EmailDeliveryResult:
        """Render and send organisation invitation link without ever logging the raw token."""
        if not self._settings.email.delivery_enabled:
            return EmailDeliveryResult(status="not_configured", provider="none")

        base_url = self._validated_frontend_base_url()
        if base_url is None:
            return EmailDeliveryResult(
                status="failed",
                provider=self._provider.provider_name,
                error_message="Frontend base URL configuration is invalid.",
            )

        invitation_url = f"{base_url}/invitations/{raw_token}"
        role_display = _ROLE_DISPLAY_MAP.get(role_name, role_name)
        rendered = render_organisation_invitation(
            invitation_url=invitation_url,
            organisation_name=organisation_name,
            role_display=role_display,
            inviter_name=inviter_name,
            expires_in_hours=expires_in_hours,
        )
        result = self._provider.send(
            EmailMessage(
                to_email=to_email,
                subject=rendered.subject,
                html_body=rendered.html_body,
                text_body=rendered.text_body,
                tags={"category": "organisation_invitation"},
            )
        )
        logger.info(
            "Organisation invitation email dispatch completed: provider=%s status=%s",
            result.provider,
            result.status,
        )
        return result
