"""Email subsystem custom exception hierarchy."""

from __future__ import annotations


class EmailProviderError(Exception):
    """Base exception for email provider errors."""


class EmailConfigurationError(EmailProviderError):
    """Raised when provider configuration is incomplete or invalid (e.g. missing RESEND_API_KEY)."""


class EmailAuthenticationError(EmailProviderError):
    """Raised when Resend API authentication fails (e.g. invalid or revoked RESEND_API_KEY)."""


class EmailConnectionTimeoutError(EmailProviderError):
    """Raised when API connection or HTTP request times out."""


class EmailRecipientRejectedError(EmailProviderError):
    """Raised when provider or mail server refuses recipient or sender address."""


class EmailRateLimitError(EmailProviderError):
    """Raised when Resend API rate limits are encountered."""


class EmailValidationError(EmailProviderError):
    """Raised when email payload fails provider validation."""
