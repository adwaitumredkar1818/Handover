"""Transactional email provider implementations (Resend, Mock, Disabled)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx

from app.services.email.base import EmailDeliveryResult, EmailMessage

logger = logging.getLogger("app.services.email.providers")


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


class ResendEmailProvider:
    """Resend HTTP API provider (`POST https://api.resend.com/emails`)."""

    _RESEND_ENDPOINT = "https://api.resend.com/emails"

    def __init__(
        self,
        *,
        api_key: str | None,
        from_address: str,
        from_name: str,
        timeout_seconds: float = 10.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._api_key = (api_key or "").strip()
        self._from_address = from_address.strip()
        self._from_name = from_name.strip()
        self._timeout_seconds = timeout_seconds
        self._http_client = http_client

    @property
    def provider_name(self) -> str:
        return "resend"

    def send(self, message: EmailMessage) -> EmailDeliveryResult:
        if not self._api_key:
            logger.warning("Resend email delivery skipped: RESEND_API_KEY is missing.")
            return EmailDeliveryResult(
                status="failed",
                provider=self.provider_name,
                error_message="Resend API key is not configured.",
            )

        from_header = (
            f"{self._from_name} <{self._from_address}>"
            if self._from_name
            else self._from_address
        )
        payload: dict[str, Any] = {
            "from": from_header,
            "to": [message.to_email],
            "subject": message.subject,
            "html": message.html_body,
            "text": message.text_body,
        }
        if message.reply_to:
            payload["reply_to"] = message.reply_to
        if message.tags:
            payload["tags"] = [
                {"name": k, "value": v} for k, v in message.tags.items()
            ]

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            if self._http_client is not None:
                resp = self._http_client.post(
                    self._RESEND_ENDPOINT,
                    json=payload,
                    headers=headers,
                    timeout=self._timeout_seconds,
                )
            else:
                with httpx.Client(timeout=self._timeout_seconds) as client:
                    resp = client.post(
                        self._RESEND_ENDPOINT,
                        json=payload,
                        headers=headers,
                    )

            if 200 <= resp.status_code < 300:
                data = resp.json() if resp.content else {}
                msg_id = str(data.get("id")) if isinstance(data, dict) and data.get("id") else None
                return EmailDeliveryResult(
                    status="submitted",
                    provider=self.provider_name,
                    provider_message_id=msg_id,
                )

            # Never log payload/tokens; log only HTTP status and sanitized error summary.
            err_summary = f"Resend API rejected request with HTTP {resp.status_code}."
            logger.warning(err_summary)
            return EmailDeliveryResult(
                status="failed",
                provider=self.provider_name,
                error_message=err_summary,
            )
        except httpx.TimeoutException:
            logger.warning("Resend email delivery timed out after %.1fs.", self._timeout_seconds)
            return EmailDeliveryResult(
                status="failed",
                provider=self.provider_name,
                error_message="Email provider request timed out.",
            )
        except httpx.HTTPError as exc:
            logger.warning("Resend email delivery network error: %s", type(exc).__name__)
            return EmailDeliveryResult(
                status="failed",
                provider=self.provider_name,
                error_message="Email provider network communication error.",
            )
