"""Transactional email package exports."""

from app.services.email.base import (
    EmailDeliveryResult,
    EmailDeliveryStatus,
    EmailDispatchResult,
    EmailMessage,
    EmailProviderProtocol,
)
from app.services.email.errors import (
    EmailAuthenticationError,
    EmailConfigurationError,
    EmailConnectionTimeoutError,
    EmailProviderError,
    EmailRateLimitError,
    EmailRecipientRejectedError,
    EmailValidationError,
)
from app.services.email.providers import (
    DisabledEmailProvider,
    MockEmailProvider,
    ResendEmailProvider,
)
from app.services.email.service import TransactionalEmailService, build_email_provider

__all__ = [
    "DisabledEmailProvider",
    "EmailAuthenticationError",
    "EmailConfigurationError",
    "EmailConnectionTimeoutError",
    "EmailDeliveryResult",
    "EmailDeliveryStatus",
    "EmailDispatchResult",
    "EmailMessage",
    "EmailProviderError",
    "EmailProviderProtocol",
    "EmailRateLimitError",
    "EmailRecipientRejectedError",
    "EmailValidationError",
    "MockEmailProvider",
    "ResendEmailProvider",
    "TransactionalEmailService",
    "build_email_provider",
]

