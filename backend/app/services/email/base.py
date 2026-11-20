"""Core types and provider protocol for transactional email delivery."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

EmailDeliveryStatus = Literal["submitted", "failed", "not_configured"]


@dataclass(frozen=True, slots=True)
class EmailMessage:
    """Structured outbound transactional email payload."""

    to_email: str
    subject: str
    html_body: str
    text_body: str
    reply_to: str | None = None
    tags: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EmailDeliveryResult:
    """Accurate provider submission outcome (never conflates submission with inbox receipt)."""

    status: EmailDeliveryStatus
    provider: str
    provider_message_id: str | None = None
    error_message: str | None = None


# Alias for contract compatibility
EmailDispatchResult = EmailDeliveryResult


class EmailProviderProtocol(Protocol):
    """Pluggable provider interface for transactional email delivery (Resend, mock, disabled)."""

    @property
    def provider_name(self) -> str:
        """Canonical provider identifier."""
        ...

    def send(self, message: EmailMessage) -> EmailDeliveryResult:
        """Submit an outbound email message synchronously and return an explicit delivery status."""
        ...

    async def send_async(self, message: EmailMessage) -> EmailDeliveryResult:
        """Submit an outbound email message asynchronously and return an explicit delivery status."""
        ...

    def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: str | None = None,
    ) -> EmailDeliveryResult:
        """Convenience adapter adhering to functional interface contract."""
        ...
