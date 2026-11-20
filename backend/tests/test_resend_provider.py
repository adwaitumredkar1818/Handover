"""Comprehensive Unit Test Suite for ResendEmailProvider.

Covers all unit test specifications for Resend Provider:
1. Valid configuration, sender identity formatting, and default sending domain ('the-sapiens.xyz').
2. Missing credentials handling (missing RESEND_API_KEY -> returns status="failed" with sanitized message).
3. Successful submission with HTML and plain-text alternatives, tags, and reply-to.
4. Asynchronous send_async submission adhering to async protocol.
5. Authentication failure (InvalidApiKeyError / 401 / 403 -> returns status="failed" without leaking API key).
6. Rate limiting (RateLimitError -> returns status="failed" with backoff guidance).
7. Payload validation error (ValidationError -> returns status="failed" with sanitized error message).
8. Connection and request timeouts -> returns status="failed" with timeout message.
9. Unverified domain error -> surfaces clear domain verification guidance for the-sapiens.xyz.
10. Error sanitization: ensure API keys and sensitive tokens never appear in error messages or logs.
11. Factory integration in build_email_provider(settings).
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from resend.exceptions import (
    ApplicationError,
    InvalidApiKeyError,
    MissingApiKeyError,
    RateLimitError,
    ResendError,
    ValidationError,
)

from app.core.config import Settings
from app.services.email.base import EmailDeliveryResult, EmailMessage
from app.services.email.errors import (
    EmailAuthenticationError,
    EmailConfigurationError,
    EmailConnectionTimeoutError,
    EmailProviderError,
    EmailRateLimitError,
    EmailValidationError,
)
from app.services.email.providers import ResendEmailProvider, _sanitize_string
from app.services.email.service import build_email_provider

_TEST_API_KEY = "re_test_abcdef1234567890abcdef12"
_TEST_RECIPIENT = "developer.candidate@example.org"
_DEFAULT_SENDER = "Handover <notifications@the-sapiens.xyz>"


@pytest.fixture
def sample_message() -> EmailMessage:
    """Create a sample transactional email message."""
    return EmailMessage(
        to_email=_TEST_RECIPIENT,
        subject="Welcome to Handover Platform",
        html_body="<h1>Welcome to Handover</h1><p>Please click the button to verify.</p>",
        text_body="Welcome to Handover. Please visit the link to verify.",
        reply_to="support@the-sapiens.xyz",
        tags={"category": "email_verification"},
    )


# ---------------------------------------------------------------------------
# 1. Configuration & Identity Tests
# ---------------------------------------------------------------------------

def test_provider_metadata_and_defaults() -> None:
    """Verify provider name, initialization defaults, sender identity, and properties."""
    provider = ResendEmailProvider(
        api_key=_TEST_API_KEY,
        from_address="notifications@the-sapiens.xyz",
        from_name="Handover",
        sending_domain="the-sapiens.xyz",
    )
    assert provider.provider_name == "resend"
    assert provider.from_address == "notifications@the-sapiens.xyz"
    assert provider.from_name == "Handover"
    assert provider.sending_domain == "the-sapiens.xyz"
    assert provider.sender_identity == "Handover <notifications@the-sapiens.xyz>"


def test_provider_custom_sender_identity() -> None:
    """Verify provider formats custom sender identity correctly."""
    provider = ResendEmailProvider(
        api_key=_TEST_API_KEY,
        from_address="alerts@the-sapiens.xyz",
        from_name="Handover Alerts",
    )
    assert provider.sender_identity == "Handover Alerts <alerts@the-sapiens.xyz>"


def test_provider_unnamed_sender_identity() -> None:
    """Verify bare email when from_name is empty."""
    provider = ResendEmailProvider(
        api_key=_TEST_API_KEY,
        from_address="notifications@the-sapiens.xyz",
        from_name="",
    )
    assert provider.sender_identity == "notifications@the-sapiens.xyz"


# ---------------------------------------------------------------------------
# 2. Missing Credentials Handling
# ---------------------------------------------------------------------------

def test_missing_api_key_returns_failed_status(sample_message: EmailMessage) -> None:
    """When API key is missing and raise_exceptions=False, returns status='failed' safely."""
    provider = ResendEmailProvider(api_key=None)
    result = provider.send(sample_message)
    assert result.status == "failed"
    assert result.provider == "resend"
    assert "RESEND_API_KEY required" in (result.error_message or "")


def test_missing_api_key_raises_exception_when_requested(sample_message: EmailMessage) -> None:
    """When API key is missing and raise_exceptions=True, raises EmailConfigurationError."""
    provider = ResendEmailProvider(api_key="")
    with pytest.raises(EmailConfigurationError, match="RESEND_API_KEY required"):
        provider.send(sample_message, raise_exceptions=True)


# ---------------------------------------------------------------------------
# 3. Successful Synchronous & Asynchronous Sending
# ---------------------------------------------------------------------------

def test_successful_synchronous_send(sample_message: EmailMessage) -> None:
    """Verify sync send formats params correctly and returns submitted status."""
    mock_client = MagicMock()
    mock_client.send.return_value = {"id": "resend-msg-12345"}

    provider = ResendEmailProvider(
        api_key=_TEST_API_KEY,
        from_address="notifications@the-sapiens.xyz",
        from_name="Handover",
        resend_client=mock_client,
    )

    result = provider.send(sample_message)

    assert result.status == "submitted"
    assert result.provider == "resend"
    assert result.provider_message_id == "resend-msg-12345"

    mock_client.send.assert_called_once()
    call_args = mock_client.send.call_args[0][0]
    assert call_args["from"] == "Handover <notifications@the-sapiens.xyz>"
    assert call_args["to"] == [_TEST_RECIPIENT]
    assert call_args["subject"] == sample_message.subject
    assert call_args["html"] == sample_message.html_body
    assert call_args["text"] == sample_message.text_body
    assert call_args["reply_to"] == "support@the-sapiens.xyz"
    assert call_args["tags"] == [{"name": "category", "value": "email_verification"}]


@pytest.mark.anyio
async def test_successful_asynchronous_send(sample_message: EmailMessage) -> None:
    """Verify async send_async formats params correctly and returns submitted status."""
    mock_client = MagicMock()
    mock_client.send_async = AsyncMock(return_value={"id": "async-msg-9999"})

    provider = ResendEmailProvider(
        api_key=_TEST_API_KEY,
        resend_client=mock_client,
    )

    result = await provider.send_async(sample_message)

    assert result.status == "submitted"
    assert result.provider == "resend"
    assert result.provider_message_id == "async-msg-9999"
    mock_client.send_async.assert_awaited_once()


# ---------------------------------------------------------------------------
# 4. Error Handling & Sanitization Tests
# ---------------------------------------------------------------------------

def test_invalid_api_key_error(sample_message: EmailMessage) -> None:
    """InvalidApiKeyError maps to authentication failure without credential leak."""
    mock_client = MagicMock()
    mock_client.send.side_effect = InvalidApiKeyError(
        code=401,
        message="API key is invalid",
        error_type="invalid_api_key",
    )

    provider = ResendEmailProvider(api_key=_TEST_API_KEY, resend_client=mock_client)
    result = provider.send(sample_message)

    assert result.status == "failed"
    assert "authentication failed" in (result.error_message or "").lower()
    assert _TEST_API_KEY not in (result.error_message or "")


def test_invalid_api_key_raises_when_requested(sample_message: EmailMessage) -> None:
    """InvalidApiKeyError raises EmailAuthenticationError when raise_exceptions=True."""
    mock_client = MagicMock()
    mock_client.send.side_effect = InvalidApiKeyError(
        code=401,
        message="API key is invalid",
        error_type="invalid_api_key",
    )

    provider = ResendEmailProvider(api_key=_TEST_API_KEY, resend_client=mock_client)
    with pytest.raises(EmailAuthenticationError):
        provider.send(sample_message, raise_exceptions=True)


def test_rate_limit_error(sample_message: EmailMessage) -> None:
    """RateLimitError maps to rate limit failure with retry guidance."""
    mock_client = MagicMock()
    mock_client.send.side_effect = RateLimitError(
        code=429,
        message="Too many requests",
        error_type="rate_limit_exceeded",
    )

    provider = ResendEmailProvider(api_key=_TEST_API_KEY, resend_client=mock_client)
    result = provider.send(sample_message)

    assert result.status == "failed"
    assert "rate limit exceeded" in (result.error_message or "").lower()


def test_validation_error(sample_message: EmailMessage) -> None:
    """ValidationError maps to validation error."""
    mock_client = MagicMock()
    mock_client.send.side_effect = ValidationError(
        code=422,
        message="The 'to' field is invalid",
        error_type="validation_error",
    )

    provider = ResendEmailProvider(api_key=_TEST_API_KEY, resend_client=mock_client)
    result = provider.send(sample_message)

    assert result.status == "failed"
    assert "validation error" in (result.error_message or "").lower()


def test_timeout_error(sample_message: EmailMessage) -> None:
    """Timeout maps to EmailConnectionTimeoutError."""
    mock_client = MagicMock()
    mock_client.send.side_effect = TimeoutError("Request timed out")

    provider = ResendEmailProvider(api_key=_TEST_API_KEY, resend_client=mock_client)
    result = provider.send(sample_message)

    assert result.status == "failed"
    assert "timed out" in (result.error_message or "").lower()


def test_unverified_domain_error_guidance(sample_message: EmailMessage) -> None:
    """Unverified domain error from Resend provides guidance for the-sapiens.xyz."""
    mock_client = MagicMock()
    mock_client.send.side_effect = ResendError(
        code=403,
        message="Domain the-sapiens.xyz is not verified. Please verify domain in Resend.",
        error_type="domain_not_verified",
        suggested_action="",
    )

    provider = ResendEmailProvider(
        api_key=_TEST_API_KEY,
        sending_domain="the-sapiens.xyz",
        resend_client=mock_client,
    )
    result = provider.send(sample_message)

    assert result.status == "failed"
    assert "the-sapiens.xyz" in (result.error_message or "")
    assert "verification required" in (result.error_message or "").lower()


def test_scrub_sensitive_api_keys_and_tokens() -> None:
    """Verify that _sanitize_string scrubs API keys and Bearer tokens."""
    raw = f"Error with key {_TEST_API_KEY} and token Bearer xyz1234567890abcdef"
    clean = _sanitize_string(raw)
    assert _TEST_API_KEY not in clean
    assert "[REDACTED]" in clean


# ---------------------------------------------------------------------------
# 5. Factory Integration
# ---------------------------------------------------------------------------

def test_build_email_provider_returns_resend(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify build_email_provider constructs ResendEmailProvider when configured."""
    monkeypatch.setenv("EMAIL_DELIVERY_ENABLED", "true")
    monkeypatch.setenv("EMAIL_PROVIDER", "resend")
    monkeypatch.setenv("RESEND_API_KEY", _TEST_API_KEY)
    monkeypatch.setenv("EMAIL_FROM", "Handover <notifications@the-sapiens.xyz>")

    settings = Settings()
    provider = build_email_provider(settings)

    assert isinstance(provider, ResendEmailProvider)
    assert provider.provider_name == "resend"
    assert provider.from_address == "notifications@the-sapiens.xyz"
    assert provider.from_name == "Handover"
    assert provider.sender_identity == "Handover <notifications@the-sapiens.xyz>"
    assert provider.sending_domain == "the-sapiens.xyz"
