"""Comprehensive Unit Test Suite for GmailSMTPEmailProvider (Requirement R4).

Covers all unit test specifications for Gmail SMTP Provider:
1. Valid configuration and successful submission with MIME multipart (HTML and text alternatives), STARTTLS, and App Password authentication.
2. Missing credentials handling (username or app password missing -> returns status="failed" with sanitized message).
3. Connection timeouts (socket.timeout and FutureTimeoutError -> returns status="failed" with sanitized message).
4. Authentication rejection (HTTP/SMTP code 535 / SMTPAuthenticationError -> returns status="failed" with guidance for Google App Passwords and zero credentials leaked).
5. Recipient/message rejection (SMTPRecipientsRefused, SMTPSenderRefused -> returns status="failed" with sanitized recipient detail).
6. Sender address auto-alignment when from_address is default/non-routable (noreply@handover.local).
7. Error sanitization: ensure credentials, App Passwords, and raw tokens never appear in exception strings, delivery error messages, or logs.
8. Rejection of normal Gmail passwords (documenting/testing that standard Google passwords fail with 535 and require App Passwords).
9. Protocol compliance: provider_name, send(), send_sync(), send_email(), close().
10. Factory integration in build_email_provider(settings).
"""

from __future__ import annotations

import logging
import smtplib
import socket
import ssl
from concurrent.futures import Future, TimeoutError as FutureTimeoutError
from email.mime.multipart import MIMEMultipart
from unittest.mock import MagicMock, patch

import pytest

from app.core.config import Settings
from app.services.email.base import EmailDeliveryResult, EmailMessage
from app.services.email.errors import (
    EmailAuthenticationError,
    EmailConfigurationError,
    EmailConnectionTimeoutError,
    EmailProviderError,
    EmailRecipientRejectedError,
)
from app.services.email.providers import GmailSMTPEmailProvider
from app.services.email.service import build_email_provider


# ---------------------------------------------------------------------------
# Test Fixtures and Helpers
# ---------------------------------------------------------------------------

_TEST_GMAIL_USER = "handover.test.smtp@gmail.com"
_TEST_APP_PASSWORD = "abcd-efgh-ijkl-mnop"
_TEST_NORMAL_PASSWORD = "MyNormalGooglePassword123!"
_TEST_RECIPIENT = "developer.candidate@example.org"
_SECRET_VERIFICATION_TOKEN = "sec-tok-8899aabbccddeeff00112233"


def _extract_mime_payloads(mime_msg: MIMEMultipart) -> tuple[str, str]:
    """Extract decoded plain-text and html payloads from a multipart/alternative MIME message."""
    plain_text = ""
    html_text = ""
    for part in mime_msg.walk():
        content_type = part.get_content_type()
        if content_type == "text/plain":
            plain_text = part.get_payload(decode=True).decode("utf-8")
        elif content_type == "text/html":
            html_text = part.get_payload(decode=True).decode("utf-8")
    return plain_text, html_text


@pytest.fixture
def mock_smtp_client():
    """Create a mock smtplib.SMTP client instance configured for success."""
    client = MagicMock()
    client.send_message.return_value = {}
    return client


@pytest.fixture
def standard_message() -> EmailMessage:
    """Create a standard test email message with both HTML and plain-text alternatives."""
    return EmailMessage(
        to_email=_TEST_RECIPIENT,
        subject="Welcome to Handover Platform",
        html_body="<h1>Welcome to Handover</h1><p>Please click the button to verify.</p>",
        text_body="Welcome to Handover. Please visit the link to verify.",
        reply_to="support@handover.org",
    )


# ---------------------------------------------------------------------------
# 1. Configuration & MIME Multipart Message Assembly Tests
# ---------------------------------------------------------------------------

def test_provider_metadata_and_defaults() -> None:
    """Verify provider name, initialization defaults, and internal properties."""
    provider = GmailSMTPEmailProvider(
        username=_TEST_GMAIL_USER,
        app_password=_TEST_APP_PASSWORD,
    )
    assert provider.provider_name == "gmail_smtp"
    assert provider._host == "smtp.gmail.com"
    assert provider._port == 587
    assert provider._use_tls is True
    assert provider._timeout_seconds == 10.0
    provider.close()


def test_mime_multipart_assembly_both_alternatives(standard_message: EmailMessage) -> None:
    """Verify MIME structure has multipart/alternative, correct headers, and parts order."""
    provider = GmailSMTPEmailProvider(
        username=_TEST_GMAIL_USER,
        app_password=_TEST_APP_PASSWORD,
        from_address=_TEST_GMAIL_USER,
        from_name="The Handover Team",
    )

    mime_msg = provider._build_mime_message(standard_message)
    assert isinstance(mime_msg, MIMEMultipart)
    assert mime_msg.get_content_type() == "multipart/alternative"
    assert mime_msg["From"] == f"The Handover Team <{_TEST_GMAIL_USER}>"
    assert mime_msg["To"] == _TEST_RECIPIENT
    assert mime_msg["Subject"] == "Welcome to Handover Platform"
    assert mime_msg["Reply-To"] == "support@handover.org"
    assert mime_msg["Date"] is not None
    assert mime_msg["Message-ID"] is not None

    payload_parts = mime_msg.get_payload()
    assert len(payload_parts) == 2
    # Part 0 must be plain text
    assert payload_parts[0].get_content_type() == "text/plain"
    assert payload_parts[0].get_content_charset() == "utf-8"
    # Part 1 must be html
    assert payload_parts[1].get_content_type() == "text/html"
    assert payload_parts[1].get_content_charset() == "utf-8"

    plain, html = _extract_mime_payloads(mime_msg)
    assert "Welcome to Handover. Please visit the link to verify." in plain
    assert "<h1>Welcome to Handover</h1>" in html
    provider.close()


def test_mime_multipart_assembly_fallback_bodies() -> None:
    """Verify fallback body behavior when only text_body or only html_body is provided."""
    provider = GmailSMTPEmailProvider(
        username=_TEST_GMAIL_USER,
        app_password=_TEST_APP_PASSWORD,
    )

    # Only HTML provided -> text_body falls back to html_body
    html_only_msg = EmailMessage(
        to_email=_TEST_RECIPIENT,
        subject="HTML Only",
        html_body="<p>Only HTML</p>",
        text_body="",
    )
    mime1 = provider._build_mime_message(html_only_msg)
    plain1, html1 = _extract_mime_payloads(mime1)
    assert plain1 == "<p>Only HTML</p>"
    assert html1 == "<p>Only HTML</p>"

    # Only text provided -> html_body falls back to text_body
    text_only_msg = EmailMessage(
        to_email=_TEST_RECIPIENT,
        subject="Text Only",
        html_body="",
        text_body="Only Plain Text",
    )
    mime2 = provider._build_mime_message(text_only_msg)
    plain2, html2 = _extract_mime_payloads(mime2)
    assert plain2 == "Only Plain Text"
    assert html2 == "Only Plain Text"
    provider.close()


def test_mime_multipart_unicode_handling() -> None:
    """Verify UTF-8 multi-byte unicode characters in subject and content are preserved."""
    provider = GmailSMTPEmailProvider(
        username=_TEST_GMAIL_USER,
        app_password=_TEST_APP_PASSWORD,
        from_name="Handover 智能平台",
    )
    unicode_msg = EmailMessage(
        to_email=_TEST_RECIPIENT,
        subject="验证您的 Handover 账户 — Événement Sécurisé 🚀",
        html_body="<p>欢迎使用 Handover 平台。请点击确认：€100 / ¥1000</p>",
        text_body="欢迎使用 Handover 平台。请点击确认：€100 / ¥1000",
    )
    mime = provider._build_mime_message(unicode_msg)
    plain, html = _extract_mime_payloads(mime)
    assert "智能平台" in mime["From"]
    assert "验证您的 Handover 账户" in mime["Subject"]
    assert "€100 / ¥1000" in plain
    assert "€100 / ¥1000" in html
    provider.close()


# ---------------------------------------------------------------------------
# 2. Successful Submission (STARTTLS, Auth, Protocol Execution)
# ---------------------------------------------------------------------------

def test_successful_submission_via_send(
    mock_smtp_client: MagicMock,
    standard_message: EmailMessage,
) -> None:
    """Verify end-to-end successful submission with STARTTLS, login, and send_message."""
    provider = GmailSMTPEmailProvider(
        username=_TEST_GMAIL_USER,
        app_password=_TEST_APP_PASSWORD,
        from_address=_TEST_GMAIL_USER,
        smtp_client_factory=lambda *a, **kw: mock_smtp_client,
    )

    result = provider.send(standard_message)
    assert result.status == "submitted"
    assert result.provider == "gmail_smtp"
    assert result.provider_message_id is not None
    assert result.error_message is None

    # Verify SMTP client interactions
    assert mock_smtp_client.ehlo.call_count == 2
    assert mock_smtp_client.starttls.called
    tls_kwargs = mock_smtp_client.starttls.call_args[1]
    assert isinstance(tls_kwargs["context"], ssl.SSLContext)
    mock_smtp_client.login.assert_called_once_with(_TEST_GMAIL_USER, _TEST_APP_PASSWORD)
    assert mock_smtp_client.send_message.called
    sent_args, sent_kwargs = mock_smtp_client.send_message.call_args
    assert sent_kwargs["from_addr"] == _TEST_GMAIL_USER
    assert sent_kwargs["to_addrs"] == [_TEST_RECIPIENT]
    mock_smtp_client.quit.assert_called_once()
    provider.close()


def test_successful_submission_via_send_sync(
    mock_smtp_client: MagicMock,
    standard_message: EmailMessage,
) -> None:
    """Verify send_sync directly invokes transport without thread pool."""
    provider = GmailSMTPEmailProvider(
        username=_TEST_GMAIL_USER,
        app_password=_TEST_APP_PASSWORD,
        from_address=_TEST_GMAIL_USER,
        smtp_client_factory=lambda *a, **kw: mock_smtp_client,
    )

    result = provider.send_sync(standard_message, raise_exceptions=True)
    assert result.status == "submitted"
    assert result.provider == "gmail_smtp"
    assert result.provider_message_id is not None
    provider.close()


def test_send_email_convenience_method(
    mock_smtp_client: MagicMock,
) -> None:
    """Verify send_email convenience adapter packages EmailMessage and returns result."""
    provider = GmailSMTPEmailProvider(
        username=_TEST_GMAIL_USER,
        app_password=_TEST_APP_PASSWORD,
        smtp_client_factory=lambda *a, **kw: mock_smtp_client,
    )

    res = provider.send_email(
        to_email=_TEST_RECIPIENT,
        subject="Convenience Method Test",
        html_content="<p>Hello HTML</p>",
        text_content="Hello Plain",
    )
    assert res.status == "submitted"
    assert res.provider == "gmail_smtp"
    assert mock_smtp_client.send_message.called
    provider.close()


# ---------------------------------------------------------------------------
# 3. Missing Credentials Handling
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "username,app_password",
    [
        (None, _TEST_APP_PASSWORD),
        ("", _TEST_APP_PASSWORD),
        ("   ", _TEST_APP_PASSWORD),
        (_TEST_GMAIL_USER, None),
        (_TEST_GMAIL_USER, ""),
        (_TEST_GMAIL_USER, "   "),
        (None, None),
        ("", ""),
    ],
)
def test_missing_credentials_returns_failed_status(
    username: str | None,
    app_password: str | None,
    standard_message: EmailMessage,
) -> None:
    """Verify missing username or app_password returns status='failed' without invoking SMTP."""
    mock_factory = MagicMock()
    provider = GmailSMTPEmailProvider(
        username=username,
        app_password=app_password,
        smtp_client_factory=mock_factory,
    )

    result = provider.send(standard_message)
    assert result.status == "failed"
    assert result.provider == "gmail_smtp"
    assert "configuration is incomplete" in result.error_message
    assert "username or app password is not configured" in result.error_message
    assert not mock_factory.called
    provider.close()


def test_missing_credentials_send_sync_raises_configuration_error(
    standard_message: EmailMessage,
) -> None:
    """Verify send_sync with raise_exceptions=True raises EmailConfigurationError."""
    provider = GmailSMTPEmailProvider(username="", app_password="")
    with pytest.raises(EmailConfigurationError) as exc_info:
        provider.send_sync(standard_message, raise_exceptions=True)
    assert "Gmail SMTP configuration is incomplete" in str(exc_info.value)
    provider.close()


# ---------------------------------------------------------------------------
# 4. Authentication Rejection (Code 535) & Normal Password Rejection
# ---------------------------------------------------------------------------

def test_smtp_authentication_error_code_535(
    standard_message: EmailMessage,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify HTTP/SMTP code 535 produces sanitized guidance for App Passwords and zero leaks."""
    failing_client = MagicMock()
    failing_client.login.side_effect = smtplib.SMTPAuthenticationError(
        535,
        b"5.7.8 Username and Password not accepted. Learn more at https://support.google.com/mail/?p=BadCredentials",
    )

    provider = GmailSMTPEmailProvider(
        username=_TEST_GMAIL_USER,
        app_password=_TEST_APP_PASSWORD,
        smtp_client_factory=lambda *a, **kw: failing_client,
    )

    with caplog.at_level(logging.WARNING):
        result = provider.send(standard_message)

    assert result.status == "failed"
    assert result.provider == "gmail_smtp"
    expected_guidance = (
        "Gmail SMTP authentication failed. Please verify your Google account email and "
        "16-character App Password (2-Step Verification required)."
    )
    assert result.error_message == expected_guidance

    # SECURITY ASSERTIONS: Credentials must never appear in error message or logs
    assert _TEST_APP_PASSWORD not in result.error_message
    assert _TEST_GMAIL_USER not in result.error_message
    assert _TEST_APP_PASSWORD not in caplog.text
    # Privacy verification: Recipient domain only
    assert "@example.org" in caplog.text
    assert "developer.candidate" not in caplog.text
    provider.close()


def test_rejection_of_standard_gmail_password_documentation(
    standard_message: EmailMessage,
) -> None:
    """Document and test that standard Google account passwords fail with 535 and require App Passwords.

    Since May 30, 2022, Google deprecated standard password authentication for SMTP (Less Secure Apps).
    Using an actual Google account password returns 535 authentication failure. The Handover provider
    explicitly guides the user toward generating a 16-character Google App Password under 2-Step Verification.
    """
    normal_pass_client = MagicMock()
    normal_pass_client.login.side_effect = smtplib.SMTPAuthenticationError(
        535,
        b"5.7.8 Application-specific password required. Learn more at https://support.google.com/mail/?p=InvalidSecondFactor",
    )

    provider = GmailSMTPEmailProvider(
        username=_TEST_GMAIL_USER,
        app_password=_TEST_NORMAL_PASSWORD,
        smtp_client_factory=lambda *a, **kw: normal_pass_client,
    )

    result = provider.send(standard_message)
    assert result.status == "failed"
    # Actionable guidance instructs user to use a 16-character App Password
    assert "16-character App Password (2-Step Verification required)" in result.error_message
    assert _TEST_NORMAL_PASSWORD not in result.error_message

    # Test raise_exceptions=True raises EmailAuthenticationError with sanitized message
    with pytest.raises(EmailAuthenticationError) as exc_info:
        provider.send_sync(standard_message, raise_exceptions=True)
    assert "16-character App Password" in str(exc_info.value)
    assert _TEST_NORMAL_PASSWORD not in str(exc_info.value)
    provider.close()


# ---------------------------------------------------------------------------
# 5. Connection Timeouts (socket.timeout and FutureTimeoutError)
# ---------------------------------------------------------------------------

def test_connection_timeout_socket_timeout(
    standard_message: EmailMessage,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify socket.timeout during connection returns status='failed' with sanitized message."""
    timeout_client = MagicMock()
    timeout_client.starttls.side_effect = socket.timeout("Operation timed out")

    provider = GmailSMTPEmailProvider(
        username=_TEST_GMAIL_USER,
        app_password=_TEST_APP_PASSWORD,
        timeout_seconds=3.0,
        smtp_client_factory=lambda *a, **kw: timeout_client,
    )

    with caplog.at_level(logging.WARNING):
        result = provider.send(standard_message)

    assert result.status == "failed"
    assert result.error_message == "Gmail SMTP connection timed out after 3.0s."
    assert _TEST_APP_PASSWORD not in caplog.text

    # With raise_exceptions=True
    with pytest.raises(EmailConnectionTimeoutError) as exc_info:
        provider.send_sync(standard_message, raise_exceptions=True)
    assert "timed out after 3.0s" in str(exc_info.value)
    provider.close()


def test_connection_timeout_future_timeout_error(
    standard_message: EmailMessage,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify ThreadPoolExecutor FutureTimeoutError returns sanitized timeout message."""
    provider = GmailSMTPEmailProvider(
        username=_TEST_GMAIL_USER,
        app_password=_TEST_APP_PASSWORD,
        timeout_seconds=2.0,
    )

    mock_future = MagicMock(spec=Future)
    mock_future.result.side_effect = FutureTimeoutError("Thread pool timeout")

    with patch.object(provider._executor, "submit", return_value=mock_future):
        with caplog.at_level(logging.WARNING):
            result = provider.send(standard_message)

    assert result.status == "failed"
    assert result.error_message == "Gmail SMTP connection timed out after 2.0s."
    assert "@example.org" in caplog.text
    provider.close()


# ---------------------------------------------------------------------------
# 6. Recipient and Message Rejection Handling
# ---------------------------------------------------------------------------

def test_recipient_refused_via_smtp_recipients_refused(
    standard_message: EmailMessage,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify SMTPRecipientsRefused returns sanitized recipient failure detail."""
    refused_client = MagicMock()
    refused_client.login.return_value = (235, b"2.7.0 Accepted")
    refused_client.send_message.side_effect = smtplib.SMTPRecipientsRefused(
        {
            _TEST_RECIPIENT: (550, b"5.1.1 The email account that you tried to reach does not exist."),
        }
    )

    provider = GmailSMTPEmailProvider(
        username=_TEST_GMAIL_USER,
        app_password=_TEST_APP_PASSWORD,
        smtp_client_factory=lambda *a, **kw: refused_client,
    )

    with caplog.at_level(logging.WARNING):
        result = provider.send(standard_message)

    assert result.status == "failed"
    assert "Gmail SMTP rejected recipient address:" in result.error_message
    assert "550 5.1.1 The email account that you tried to reach does not exist" in result.error_message
    assert _TEST_APP_PASSWORD not in result.error_message
    assert _TEST_APP_PASSWORD not in caplog.text

    # With raise_exceptions=True
    with pytest.raises(EmailRecipientRejectedError) as exc_info:
        provider.send_sync(standard_message, raise_exceptions=True)
    assert "rejected recipient address" in str(exc_info.value)
    provider.close()


def test_recipient_refused_via_send_message_return_dict(
    standard_message: EmailMessage,
) -> None:
    """Verify when send_message returns a non-empty recipient refusal dictionary."""
    refused_client = MagicMock()
    # smtplib.send_message returns dict of refused recipients
    refused_client.send_message.return_value = {
        _TEST_RECIPIENT: (553, b"5.3.0 Invalid mailbox"),
    }

    provider = GmailSMTPEmailProvider(
        username=_TEST_GMAIL_USER,
        app_password=_TEST_APP_PASSWORD,
        smtp_client_factory=lambda *a, **kw: refused_client,
    )

    result = provider.send(standard_message)
    assert result.status == "failed"
    assert "Gmail SMTP rejected recipient address: 553 5.3.0 Invalid mailbox." in result.error_message
    provider.close()


def test_sender_refused_smtp_sender_refused(
    standard_message: EmailMessage,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify SMTPSenderRefused returns sanitized sender refusal message."""
    refused_client = MagicMock()
    refused_client.send_message.side_effect = smtplib.SMTPSenderRefused(
        553,
        b"5.7.1 Sender address rejected: unverified domain",
        "unverified@handover.local",
    )

    provider = GmailSMTPEmailProvider(
        username=_TEST_GMAIL_USER,
        app_password=_TEST_APP_PASSWORD,
        from_address="unverified@handover.local",
        smtp_client_factory=lambda *a, **kw: refused_client,
    )

    with caplog.at_level(logging.WARNING):
        result = provider.send(standard_message)

    assert result.status == "failed"
    assert result.error_message == "Gmail SMTP sender address refused by server."
    assert _TEST_APP_PASSWORD not in result.error_message

    # With raise_exceptions=True
    with pytest.raises(EmailProviderError) as exc_info:
        provider.send_sync(standard_message, raise_exceptions=True)
    assert "sender address refused" in str(exc_info.value)
    provider.close()


# ---------------------------------------------------------------------------
# 7. Network, TLS, and Connection Failures
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "exception_to_raise",
    [
        smtplib.SMTPConnectError(421, b"Service not available"),
        ConnectionRefusedError("Connection refused by host"),
        smtplib.SMTPServerDisconnected("Server disconnected unexpectedly"),
    ],
)
def test_connection_refused_and_disconnect_errors(
    exception_to_raise: Exception,
    standard_message: EmailMessage,
) -> None:
    """Verify connection refusal, disconnect, and connect error return sanitized message."""
    client = MagicMock()
    client.starttls.side_effect = exception_to_raise

    provider = GmailSMTPEmailProvider(
        host="smtp.gmail.com",
        port=587,
        username=_TEST_GMAIL_USER,
        app_password=_TEST_APP_PASSWORD,
        smtp_client_factory=lambda *a, **kw: client,
    )

    result = provider.send(standard_message)
    assert result.status == "failed"
    assert result.error_message == "Gmail SMTP failed to connect to smtp.gmail.com:587."
    provider.close()


def test_tls_negotiation_failure(
    standard_message: EmailMessage,
) -> None:
    """Verify SSL/TLS failure returns sanitized TLS error message."""
    client = MagicMock()
    client.starttls.side_effect = ssl.SSLError("CERTIFICATE_VERIFY_FAILED")

    provider = GmailSMTPEmailProvider(
        username=_TEST_GMAIL_USER,
        app_password=_TEST_APP_PASSWORD,
        smtp_client_factory=lambda *a, **kw: client,
    )

    result = provider.send(standard_message)
    assert result.status == "failed"
    assert result.error_message == "Gmail SMTP TLS negotiation failed."
    provider.close()


def test_general_smtp_exception(
    standard_message: EmailMessage,
) -> None:
    """Verify unexpected SMTPException returns sanitized communication error."""
    client = MagicMock()
    client.send_message.side_effect = smtplib.SMTPDataError(554, b"Transaction failed")

    provider = GmailSMTPEmailProvider(
        username=_TEST_GMAIL_USER,
        app_password=_TEST_APP_PASSWORD,
        smtp_client_factory=lambda *a, **kw: client,
    )

    result = provider.send(standard_message)
    assert result.status == "failed"
    assert result.error_message == "Gmail SMTP network communication error: SMTPDataError."
    provider.close()


# ---------------------------------------------------------------------------
# 8. Error Sanitization & Secret Token Leak Prevention
# ---------------------------------------------------------------------------

def test_error_sanitization_guarantees_zero_token_and_credential_leaks(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Security verification: Raw verification tokens and App Passwords never appear in error outputs or logs."""
    sensitive_message = EmailMessage(
        to_email="confidential.executive@enterprise.org",
        subject="Confidential Invitation",
        html_body=f"<p>Your secret token is: {_SECRET_VERIFICATION_TOKEN}</p>",
        text_body=f"Your secret token is: {_SECRET_VERIFICATION_TOKEN}",
    )

    # Simulate an authentication crash
    auth_fail_client = MagicMock()
    auth_fail_client.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Auth failure")

    provider = GmailSMTPEmailProvider(
        username=_TEST_GMAIL_USER,
        app_password=_TEST_APP_PASSWORD,
        smtp_client_factory=lambda *a, **kw: auth_fail_client,
    )

    with caplog.at_level(logging.DEBUG):
        result = provider.send(sensitive_message)

    assert result.status == "failed"
    # Zero credential leaks in result
    assert _TEST_APP_PASSWORD not in (result.error_message or "")
    assert _SECRET_VERIFICATION_TOKEN not in (result.error_message or "")
    # Zero credential leaks in logs
    assert _TEST_APP_PASSWORD not in caplog.text
    assert _SECRET_VERIFICATION_TOKEN not in caplog.text
    # Privacy check: full email username 'confidential.executive' must NOT appear in outbound log
    assert "confidential.executive" not in caplog.text
    assert "@enterprise.org" in caplog.text
    provider.close()


# ---------------------------------------------------------------------------
# 9. Sender Address Auto-Alignment & Settings Integration
# ---------------------------------------------------------------------------

def test_sender_address_auto_alignment_in_settings() -> None:
    """Verify Settings auto-aligns from_address with smtp_username when from_address is default/non-routable."""
    # Default from_address noreply@handover.local aligns to smtp_username
    s1 = Settings(
        email_delivery_enabled=True,
        email_provider="gmail_smtp",
        smtp_username="my.account@gmail.com",
        smtp_app_password="app-pass-token",
        from_address="noreply@handover.local",
    )
    assert s1.email.from_address == "my.account@gmail.com"

    # Non-routable .local aligns to smtp_username under gmail_smtp
    s2 = Settings(
        email_delivery_enabled=True,
        email_provider="gmail_smtp",
        smtp_username="my.account@gmail.com",
        smtp_app_password="app-pass-token",
        from_address="noreply@service.local",
    )
    assert s2.email.from_address == "my.account@gmail.com"

    # Custom routable domain is preserved
    s3 = Settings(
        email_delivery_enabled=True,
        email_provider="gmail_smtp",
        smtp_username="my.account@gmail.com",
        smtp_app_password="app-pass-token",
        from_address="notifications@company.org",
    )
    assert s3.email.from_address == "notifications@company.org"


def test_build_email_provider_factory_gmail_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify build_email_provider instantiates GmailSMTPEmailProvider without silent fallback."""
    monkeypatch.delenv("EMAIL_FROM_ADDRESS", raising=False)
    settings = Settings(
        email_delivery_enabled=True,
        email_provider="gmail_smtp",
        email_from_address="dev.mailer@gmail.com",
        smtp_host="smtp.gmail.com",
        smtp_port=587,
        smtp_username="dev.mailer@gmail.com",
        smtp_app_password="16-char-app-pass",
        smtp_use_tls=True,
        smtp_timeout_seconds=8.0,
    )

    provider = build_email_provider(settings)
    assert isinstance(provider, GmailSMTPEmailProvider)
    assert provider.provider_name == "gmail_smtp"
    assert provider._host == "smtp.gmail.com"
    assert provider._port == 587
    assert provider._username == "dev.mailer@gmail.com"
    assert provider._app_password == "16-char-app-pass"
    assert provider._use_tls is True
    assert provider._timeout_seconds == 8.0
    assert provider._from_address == "dev.mailer@gmail.com"
    provider.close()


def test_resource_cleanup_close() -> None:
    """Verify close() terminates the ThreadPoolExecutor cleanly."""
    provider = GmailSMTPEmailProvider(
        username=_TEST_GMAIL_USER,
        app_password=_TEST_APP_PASSWORD,
    )
    assert not provider._executor._shutdown
    provider.close()
    assert provider._executor._shutdown
