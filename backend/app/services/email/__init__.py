"""Transactional email package exports."""

from app.services.email.base import EmailDeliveryResult, EmailDeliveryStatus, EmailMessage, EmailProviderProtocol
from app.services.email.providers import DisabledEmailProvider, MockEmailProvider, ResendEmailProvider
from app.services.email.service import TransactionalEmailService, build_email_provider

__all__ = [
    "DisabledEmailProvider",
    "EmailDeliveryResult",
    "EmailDeliveryStatus",
    "EmailMessage",
    "EmailProviderProtocol",
    "MockEmailProvider",
    "ResendEmailProvider",
    "TransactionalEmailService",
    "build_email_provider",
]
