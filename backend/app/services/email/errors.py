"""Email subsystem custom exception hierarchy."""

from __future__ import annotations


class EmailProviderError(Exception):
    """Base exception for email provider errors."""


class EmailConfigurationError(EmailProviderError):
    """Raised when provider configuration is incomplete or invalid."""


class EmailAuthenticationError(EmailProviderError):
    """Raised when SMTP authentication with Google fails (e.g. invalid App Password)."""


class EmailConnectionTimeoutError(EmailProviderError):
    """Raised when connection or handshake with smtp.gmail.com times out."""


class EmailRecipientRejectedError(EmailProviderError):
    """Raised when SMTP server refuses recipient or sender address."""
