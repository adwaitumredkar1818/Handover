"""Transactional email provider implementations (Gmail SMTP, Mock, Disabled)."""

from __future__ import annotations

import email.utils
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid
import logging
import socket
import ssl
import smtplib
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
import uuid
from typing import Any

from app.services.email.base import EmailDeliveryResult, EmailMessage
from app.services.email.errors import (
    EmailAuthenticationError,
    EmailConfigurationError,
    EmailConnectionTimeoutError,
    EmailProviderError,
    EmailRecipientRejectedError,
)

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


class GmailSMTPEmailProvider:
    """Gmail SMTP provider dispatching via smtp.gmail.com:587 with STARTTLS and Google App Passwords."""

    def __init__(
        self,
        *,
        host: str = "smtp.gmail.com",
        port: int = 587,
        username: str | None = None,
        app_password: str | None = None,
        use_tls: bool = True,
        from_address: str = "noreply@handover.local",
        from_name: str = "The Handover",
        timeout_seconds: float = 10.0,
        smtp_client_factory: Any | None = None,
    ) -> None:
        self._host = (host or "smtp.gmail.com").strip()
        self._port = port
        self._username = (username or "").strip()
        self._app_password = (app_password or "").strip()
        self._use_tls = use_tls
        self._from_address = (from_address or "noreply@handover.local").strip()
        self._from_name = (from_name or "The Handover").strip()
        self._timeout_seconds = float(timeout_seconds)
        self._smtp_client_factory = smtp_client_factory
        self._executor = ThreadPoolExecutor(
            max_workers=4,
            thread_name_prefix="smtp-worker",
        )

    @property
    def provider_name(self) -> str:
        return "gmail_smtp"

    def _build_mime_message(self, message: EmailMessage) -> MIMEMultipart:
        mime_msg = MIMEMultipart("alternative")
        from_header = (
            f"{self._from_name} <{self._from_address}>"
            if self._from_name
            else self._from_address
        )
        mime_msg["From"] = from_header
        mime_msg["To"] = message.to_email
        mime_msg["Subject"] = message.subject
        mime_msg["Date"] = formatdate(localtime=True)
        mime_msg["Message-ID"] = make_msgid()
        if message.reply_to:
            mime_msg["Reply-To"] = message.reply_to

        # Plain text alternative attached first
        part_text = MIMEText(message.text_body or message.html_body, "plain", "utf-8")
        mime_msg.attach(part_text)

        # HTML alternative attached second (preferred by HTML email clients)
        part_html = MIMEText(message.html_body or message.text_body, "html", "utf-8")
        mime_msg.attach(part_html)

        return mime_msg

    def _send_sync(
        self,
        message: EmailMessage,
        *,
        raise_exceptions: bool = False,
    ) -> EmailDeliveryResult:
        recipient_domain = message.to_email.split("@")[-1] if "@" in message.to_email else "unknown"
        try:
            if not self._username or not self._app_password:
                raise EmailConfigurationError(
                    "Gmail SMTP configuration is incomplete: username or app password is not configured."
                )

            mime_msg = self._build_mime_message(message)
            msg_id = mime_msg["Message-ID"]

            if self._smtp_client_factory is not None:
                try:
                    client = self._smtp_client_factory(
                        self._host, self._port, timeout=self._timeout_seconds
                    )
                except TypeError:
                    client = self._smtp_client_factory(self._host, self._port)
            else:
                client = smtplib.SMTP(self._host, self._port, timeout=self._timeout_seconds)

            try:
                client.ehlo()
                if self._use_tls:
                    context = ssl.create_default_context()
                    client.starttls(context=context)
                    client.ehlo()
                client.login(self._username, self._app_password)
                refused = client.send_message(
                    mime_msg,
                    from_addr=self._from_address,
                    to_addrs=[message.to_email],
                )
                if refused:
                    raise smtplib.SMTPRecipientsRefused(refused)
            finally:
                try:
                    client.quit()
                except Exception:
                    try:
                        client.close()
                    except Exception:
                        pass

            logger.info(
                "Gmail SMTP email submitted successfully (message_id=%s, recipient_domain=@%s).",
                msg_id,
                recipient_domain,
            )
            return EmailDeliveryResult(
                status="submitted",
                provider=self.provider_name,
                provider_message_id=msg_id,
            )
        except EmailConfigurationError as exc:
            logger.warning("Gmail SMTP delivery skipped: username or app password is not configured.")
            if raise_exceptions:
                raise
            return EmailDeliveryResult(
                status="failed",
                provider=self.provider_name,
                error_message=str(exc),
            )
        except smtplib.SMTPAuthenticationError as exc:
            err_msg = (
                "Gmail SMTP authentication failed. Please verify your Google account email and "
                "16-character App Password (2-Step Verification required)."
            )
            logger.warning(
                "Gmail SMTP delivery failed for recipient domain '@%s': %s",
                recipient_domain,
                err_msg,
            )
            if raise_exceptions:
                raise EmailAuthenticationError(err_msg) from exc
            return EmailDeliveryResult(
                status="failed",
                provider=self.provider_name,
                error_message=err_msg,
            )
        except (socket.timeout, TimeoutError) as exc:
            err_msg = f"Gmail SMTP connection timed out after {self._timeout_seconds}s."
            logger.warning(
                "Gmail SMTP delivery failed for recipient domain '@%s': %s",
                recipient_domain,
                err_msg,
            )
            if raise_exceptions:
                raise EmailConnectionTimeoutError(err_msg) from exc
            return EmailDeliveryResult(
                status="failed",
                provider=self.provider_name,
                error_message=err_msg,
            )
        except (smtplib.SMTPConnectError, ConnectionRefusedError, smtplib.SMTPServerDisconnected) as exc:
            err_msg = f"Gmail SMTP failed to connect to {self._host}:{self._port}."
            logger.warning(
                "Gmail SMTP delivery failed for recipient domain '@%s': %s",
                recipient_domain,
                err_msg,
            )
            if raise_exceptions:
                raise EmailProviderError(err_msg) from exc
            return EmailDeliveryResult(
                status="failed",
                provider=self.provider_name,
                error_message=err_msg,
            )
        except smtplib.SMTPRecipientsRefused as exc:
            details = []
            for addr, resp in exc.recipients.items():
                if isinstance(resp, tuple) and len(resp) >= 2:
                    code, msg = resp[0], resp[1]
                    msg_str = msg.decode("utf-8", errors="replace") if isinstance(msg, bytes) else str(msg)
                    details.append(f"{code} {msg_str.strip()}")
                else:
                    details.append(str(resp))
            sanitized_detail = "; ".join(details) if details else "server refused recipient"
            err_msg = f"Gmail SMTP rejected recipient address: {sanitized_detail}."
            logger.warning(
                "Gmail SMTP delivery failed for recipient domain '@%s': %s",
                recipient_domain,
                err_msg,
            )
            if raise_exceptions:
                raise EmailRecipientRejectedError(err_msg) from exc
            return EmailDeliveryResult(
                status="failed",
                provider=self.provider_name,
                error_message=err_msg,
            )
        except smtplib.SMTPSenderRefused as exc:
            err_msg = "Gmail SMTP sender address refused by server."
            logger.warning(
                "Gmail SMTP delivery failed for recipient domain '@%s': %s",
                recipient_domain,
                err_msg,
            )
            if raise_exceptions:
                raise EmailProviderError(err_msg) from exc
            return EmailDeliveryResult(
                status="failed",
                provider=self.provider_name,
                error_message=err_msg,
            )
        except (ssl.SSLError, smtplib.SMTPNotSupportedError) as exc:
            err_msg = "Gmail SMTP TLS negotiation failed."
            logger.warning(
                "Gmail SMTP delivery failed for recipient domain '@%s': %s",
                recipient_domain,
                err_msg,
            )
            if raise_exceptions:
                raise EmailProviderError(err_msg) from exc
            return EmailDeliveryResult(
                status="failed",
                provider=self.provider_name,
                error_message=err_msg,
            )
        except (smtplib.SMTPException, OSError) as exc:
            err_msg = f"Gmail SMTP network communication error: {type(exc).__name__}."
            logger.warning(
                "Gmail SMTP delivery failed for recipient domain '@%s': %s",
                recipient_domain,
                err_msg,
            )
            if raise_exceptions:
                raise EmailProviderError(err_msg) from exc
            return EmailDeliveryResult(
                status="failed",
                provider=self.provider_name,
                error_message=err_msg,
            )

    def send(self, message: EmailMessage) -> EmailDeliveryResult:
        """Submit outbound email asynchronously via bounded thread pool with hard timeout."""
        if not self._username or not self._app_password:
            logger.warning("Gmail SMTP delivery skipped: username or app password is not configured.")
            return EmailDeliveryResult(
                status="failed",
                provider=self.provider_name,
                error_message="Gmail SMTP configuration is incomplete: username or app password is not configured.",
            )

        try:
            future = self._executor.submit(self._send_sync, message)
            return future.result(timeout=self._timeout_seconds)
        except FutureTimeoutError:
            recipient_domain = message.to_email.split("@")[-1] if "@" in message.to_email else "unknown"
            err_msg = f"Gmail SMTP connection timed out after {self._timeout_seconds}s."
            logger.warning(
                "Gmail SMTP delivery failed for recipient domain '@%s': %s",
                recipient_domain,
                err_msg,
            )
            return EmailDeliveryResult(
                status="failed",
                provider=self.provider_name,
                error_message=err_msg,
            )
        except Exception as exc:
            recipient_domain = message.to_email.split("@")[-1] if "@" in message.to_email else "unknown"
            err_msg = f"Gmail SMTP unexpected error: {type(exc).__name__}."
            logger.warning(
                "Gmail SMTP delivery failed for recipient domain '@%s': %s",
                recipient_domain,
                err_msg,
            )
            return EmailDeliveryResult(
                status="failed",
                provider=self.provider_name,
                error_message=err_msg,
            )

    def send_sync(
        self,
        message: EmailMessage,
        *,
        raise_exceptions: bool = False,
    ) -> EmailDeliveryResult:
        """Direct synchronous invocation (primarily for testing and specialized synchronous pipelines)."""
        return self._send_sync(message, raise_exceptions=raise_exceptions)

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
        """Shut down internal thread pool executor."""
        self._executor.shutdown(wait=False)

    def __del__(self) -> None:
        try:
            self._executor.shutdown(wait=False)
        except Exception:
            pass

