"""Transactional email provider implementations (Resend REST API, Mock, Disabled)."""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

import resend
from resend.exceptions import (
    ApplicationError,
    InvalidApiKeyError,
    MissingApiKeyError,
    MissingRequiredFieldsError,
    RateLimitError,
    ResendError,
    ValidationError,
)

from app.services.email.base import EmailDeliveryResult, EmailMessage
from app.services.email.errors import (
    EmailAuthenticationError,
    EmailConfigurationError,
    EmailConnectionTimeoutError,
    EmailProviderError,
    EmailRateLimitError,
    EmailRecipientRejectedError,
    EmailValidationError,
)

logger = logging.getLogger("app.services.email.providers")

_SENSITIVE_PATTERN = re.compile(r"(re_[a-zA-Z0-9_-]{20,}|Bearer\s+[a-zA-Z0-9._-]+)", re.IGNORECASE)


def _sanitize_string(text: str) -> str:
    """Scrub potential API keys or tokens from error text."""
    return _SENSITIVE_PATTERN.sub("[REDACTED]", text)


class DisabledEmailProvider:
    """No-op provider used when outbound email delivery is disabled or unconfigured."""

    @property
    def provider_name(self) -> str:
        return "none"

    def send(self, message: EmailMessage) -> EmailDeliveryResult:
        return EmailDeliveryResult(
            status="not_configured",
            provider=self.provider_name,
            error_message="Outbound email delivery is disabled or not configured.",
        )

    async def send_async(self, message: EmailMessage) -> EmailDeliveryResult:
        return self.send(message)

    def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: str | None = None,
    ) -> EmailDeliveryResult:
        """Convenience adapter adhering to functional interface contract."""
        return self.send(
            EmailMessage(
                to_email=to_email,
                subject=subject,
                html_body=html_content,
                text_body=text_content or html_content,
            )
        )


class MockEmailProvider:
    """In-memory mock provider for automated tests and safe local verification."""

    def __init__(self, *, should_fail: bool = False, failure_message: str = "Mock failure") -> None:
        self.sent_messages: list[EmailMessage] = []
        self._should_fail = should_fail
        self._failure_message = failure_message

    @property
    def provider_name(self) -> str:
        return "mock"

    def send(self, message: EmailMessage) -> EmailDeliveryResult:
        if self._should_fail:
            return EmailDeliveryResult(
                status="failed",
                provider=self.provider_name,
                error_message=self._failure_message,
            )
        self.sent_messages.append(message)
        return EmailDeliveryResult(
            status="submitted",
            provider=self.provider_name,
            provider_message_id=f"mock-{uuid.uuid4()}",
        )

    async def send_async(self, message: EmailMessage) -> EmailDeliveryResult:
        return self.send(message)

    def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: str | None = None,
    ) -> EmailDeliveryResult:
        """Convenience adapter adhering to functional interface contract."""
        return self.send(
            EmailMessage(
                to_email=to_email,
                subject=subject,
                html_body=html_content,
                text_body=text_content or html_content,
            )
        )


class ResendEmailProvider:
    """Centralized transactional email delivery via the official Resend Python SDK.

    Uses sending domain the-sapiens.xyz and identity 'Handover <notifications@the-sapiens.xyz>'.
    Provides both synchronous and asynchronous sending with rigorous error sanitization.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        from_address: str = "notifications@the-sapiens.xyz",
        from_name: str | None = "Handover",
        sending_domain: str = "the-sapiens.xyz",
        timeout_seconds: float = 10.0,
        resend_client: Any | None = None,
    ) -> None:
        self._api_key = (api_key or "").strip()
        self._from_address = (from_address or "notifications@the-sapiens.xyz").strip()
        self._from_name = (from_name or "").strip()
        self._sending_domain = (sending_domain or "the-sapiens.xyz").strip()
        self._timeout_seconds = float(timeout_seconds)
        self._resend_client = resend_client

        if self._api_key:
            resend.api_key = self._api_key

    @property
    def provider_name(self) -> str:
        return "resend"

    @property
    def sender_identity(self) -> str:
        if self._from_name:
            return f"{self._from_name} <{self._from_address}>"
        return self._from_address

    @property
    def from_address(self) -> str:
        return self._from_address

    @property
    def from_name(self) -> str:
        return self._from_name

    @property
    def sending_domain(self) -> str:
        return self._sending_domain

    def _build_params(self, message: EmailMessage) -> dict[str, Any]:
        params: dict[str, Any] = {
            "from": self.sender_identity,
            "to": [message.to_email] if isinstance(message.to_email, str) else list(message.to_email),
            "subject": message.subject,
            "html": message.html_body,
            "text": message.text_body or message.html_body,
        }
        if message.reply_to:
            params["reply_to"] = message.reply_to
        if message.tags:
            params["tags"] = [{"name": str(k), "value": str(v)} for k, v in message.tags.items()]
        return params

    def _extract_message_id(self, response: Any) -> str:
        if isinstance(response, dict):
            return str(response.get("id") or response.get("message_id") or uuid.uuid4())
        if hasattr(response, "id"):
            return str(response.id)
        return str(response)

    def _handle_exception(
        self,
        exc: Exception,
        recipient_domain: str,
        raise_exceptions: bool = False,
    ) -> EmailDeliveryResult:
        if isinstance(exc, (InvalidApiKeyError, MissingApiKeyError)):
            err_msg = "Resend API authentication failed: invalid or missing API key."
            logger.warning("Resend delivery failed for recipient domain '@%s': %s", recipient_domain, err_msg)
            if raise_exceptions:
                raise EmailAuthenticationError(err_msg) from exc
            return EmailDeliveryResult(status="failed", provider=self.provider_name, error_message=err_msg)

        if isinstance(exc, RateLimitError):
            err_msg = "Resend API rate limit exceeded. Please retry after backoff."
            logger.warning("Resend delivery rate limited for recipient domain '@%s': %s", recipient_domain, err_msg)
            if raise_exceptions:
                raise EmailRateLimitError(err_msg) from exc
            return EmailDeliveryResult(status="failed", provider=self.provider_name, error_message=err_msg)

        if isinstance(exc, (ValidationError, MissingRequiredFieldsError)):
            safe_detail = _sanitize_string(str(exc))
            err_msg = f"Resend validation error: {safe_detail}"
            logger.warning(
                "Resend delivery rejected invalid payload for recipient domain '@%s': %s",
                recipient_domain,
                err_msg,
            )
            if raise_exceptions:
                raise EmailValidationError(err_msg) from exc
            return EmailDeliveryResult(status="failed", provider=self.provider_name, error_message=err_msg)

        if isinstance(exc, (TimeoutError,)):
            err_msg = f"Resend request timed out after {self._timeout_seconds}s."
            logger.warning("Resend delivery timed out for recipient domain '@%s': %s", recipient_domain, err_msg)
            if raise_exceptions:
                raise EmailConnectionTimeoutError(err_msg) from exc
            return EmailDeliveryResult(status="failed", provider=self.provider_name, error_message=err_msg)

        safe_msg = _sanitize_string(str(exc))
        if "domain" in safe_msg.lower() and ("verify" in safe_msg.lower() or "not verified" in safe_msg.lower()):
            err_msg = f"Resend domain verification required for '{self._sending_domain}': {safe_msg}"
            logger.warning(
                "Resend delivery failed: domain '%s' requires verification in Resend dashboard: %s",
                self._sending_domain,
                safe_msg,
            )
            if raise_exceptions:
                raise EmailConfigurationError(err_msg) from exc
            return EmailDeliveryResult(status="failed", provider=self.provider_name, error_message=err_msg)

        err_msg = f"Resend delivery failed: {safe_msg}"
        logger.warning("Resend delivery failed for recipient domain '@%s': %s", recipient_domain, err_msg)
        if raise_exceptions:
            raise EmailProviderError(err_msg) from exc
        return EmailDeliveryResult(status="failed", provider=self.provider_name, error_message=err_msg)

    def send(
        self,
        message: EmailMessage,
        *,
        raise_exceptions: bool = False,
    ) -> EmailDeliveryResult:
        """Submit outbound email synchronously via Resend REST API."""
        recipient_domain = message.to_email.split("@")[-1] if "@" in message.to_email else "unknown"

        if not self._api_key and not self._resend_client:
            err_msg = "Resend API key is not configured (RESEND_API_KEY required)."
            logger.warning("Resend delivery skipped: %s", err_msg)
            if raise_exceptions:
                raise EmailConfigurationError(err_msg)
            return EmailDeliveryResult(status="failed", provider=self.provider_name, error_message=err_msg)

        params = self._build_params(message)

        try:
            if self._resend_client is not None:
                if hasattr(self._resend_client, "send"):
                    resp = self._resend_client.send(params)
                elif hasattr(self._resend_client, "Emails"):
                    resp = self._resend_client.Emails.send(params)
                else:
                    resp = self._resend_client(params)
            else:
                resend.api_key = self._api_key
                resp = resend.Emails.send(params)

            if isinstance(resp, dict) and "error" in resp and resp["error"]:
                err_dict = resp["error"]
                safe_err = _sanitize_string(str(err_dict.get("message") or err_dict))
                logger.warning("Resend API rejected email for recipient domain '@%s': %s", recipient_domain, safe_err)
                return EmailDeliveryResult(
                    status="failed",
                    provider=self.provider_name,
                    error_message=f"Resend rejected email: {safe_err}",
                )

            msg_id = self._extract_message_id(resp)
            logger.info(
                "Resend email submitted successfully (message_id=%s, recipient_domain=@%s).",
                msg_id,
                recipient_domain,
            )
            return EmailDeliveryResult(
                status="submitted",
                provider=self.provider_name,
                provider_message_id=msg_id,
            )
        except Exception as exc:
            return self._handle_exception(exc, recipient_domain, raise_exceptions=raise_exceptions)

    async def send_async(
        self,
        message: EmailMessage,
        *,
        raise_exceptions: bool = False,
    ) -> EmailDeliveryResult:
        """Submit outbound email asynchronously via Resend REST API SDK."""
        recipient_domain = message.to_email.split("@")[-1] if "@" in message.to_email else "unknown"

        if not self._api_key and not self._resend_client:
            err_msg = "Resend API key is not configured (RESEND_API_KEY required)."
            logger.warning("Resend delivery skipped: %s", err_msg)
            if raise_exceptions:
                raise EmailConfigurationError(err_msg)
            return EmailDeliveryResult(status="failed", provider=self.provider_name, error_message=err_msg)

        params = self._build_params(message)

        try:
            if self._resend_client is not None:
                if hasattr(self._resend_client, "send_async"):
                    resp = await self._resend_client.send_async(params)
                elif hasattr(self._resend_client, "Emails") and hasattr(self._resend_client.Emails, "send_async"):
                    resp = await self._resend_client.Emails.send_async(params)
                else:
                    return self.send(message, raise_exceptions=raise_exceptions)
            else:
                resend.api_key = self._api_key
                resp = await resend.Emails.send_async(params)

            if isinstance(resp, dict) and "error" in resp and resp["error"]:
                err_dict = resp["error"]
                safe_err = _sanitize_string(str(err_dict.get("message") or err_dict))
                logger.warning("Resend API rejected email for recipient domain '@%s': %s", recipient_domain, safe_err)
                return EmailDeliveryResult(
                    status="failed",
                    provider=self.provider_name,
                    error_message=f"Resend rejected email: {safe_err}",
                )

            msg_id = self._extract_message_id(resp)
            logger.info(
                "Resend email submitted successfully (async, message_id=%s, recipient_domain=@%s).",
                msg_id,
                recipient_domain,
            )
            return EmailDeliveryResult(
                status="submitted",
                provider=self.provider_name,
                provider_message_id=msg_id,
            )
        except Exception as exc:
            return self._handle_exception(exc, recipient_domain, raise_exceptions=raise_exceptions)

    def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: str | None = None,
    ) -> EmailDeliveryResult:
        """Convenience adapter adhering to functional interface contract."""
        return self.send(
            EmailMessage(
                to_email=to_email,
                subject=subject,
                html_body=html_content,
                text_body=text_content or html_content,
            )
        )

    def close(self) -> None:
        """No-op for HTTP-based provider, kept for lifecycle compatibility."""
        pass
