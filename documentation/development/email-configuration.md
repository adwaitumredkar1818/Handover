# Transactional Email Configuration & Developer Guide

This guide details how to configure, test, and troubleshoot outbound transactional email delivery in **The Handover** platform, with a special focus on using **Gmail SMTP** during active local development and staging.

---

## 1. Overview & Provider Strategy

Outbound transactional emails are essential for critical security and collaboration flows:
- **Email Verification**: Delivering single-use cryptographic verification tokens upon user registration.
- **Access Gate Lifting**: Lifting the HTTP 403 `EMAIL_VERIFICATION_REQUIRED` barrier once verified.
- **Team Invitations**: Inviting participants to organisations and project workspaces with scoped roles.
- **Password Reset**: Delivering secure, time-limited password reset tokens.

The platform employs a pluggable provider pattern implementing `EmailProviderProtocol`, supporting four provider modes:

| Provider Mode (`EMAIL_PROVIDER`) | Recommended Environment | Zero DNS Setup? | Delivers to Any Inbox? | Key Characteristic |
| :--- | :--- | :---: | :---: | :--- |
| `none` | Unit Tests / Offline Dev | Yes | No | Delivery disabled. Verification and invitation tokens are returned in API responses. |
| `mock` | Automated Headless Tests | Yes | No | Captures emails in-memory with call history (`backend/tests/`). |
| `gmail_smtp` | **Active Local Dev & Staging** | **Yes** | **Yes** | **Recommended for development**. Connects to `smtp.gmail.com:587` via STARTTLS using a 16-character Google App Password. |
| `resend` | **Cloud Production** | No (requires domain) | Yes | High-throughput transactional REST API requiring a verified custom domain and `RESEND_API_KEY`. |

---

## 2. Why Gmail SMTP for Development?

Setting up a production transactional provider like Resend or AWS SES requires:
1. Owning a registered domain name (e.g. `yourdomain.com`).
2. Creating and verifying DNS records (`TXT` for SPF, `CNAME` for DKIM, `TXT` for DMARC).
3. Waiting for DNS propagation.
4. Working around free-tier sandbox restrictions (e.g., Resend free tier only delivers to the account owner's single email address).

**Gmail SMTP completely eliminates these barriers for development**:
- Uses your existing personal Gmail or Google Workspace account.
- Zero DNS records or domain purchases required.
- Delivers immediately to **any real recipient email address** (colleagues, personal test accounts, maildrop inboxes).
- Allows end-to-end testing of real email client rendering (HTML + plain text alternatives).

---

## 3. Step-by-Step Google App Password Setup

To use Gmail SMTP, you must generate a dedicated **16-character Google App Password**. Standard Google account passwords **will not work**.

### Why Regular Google Account Passwords Fail (SMTP Code 535)
In 2022, Google permanently deprecated "Less Secure Apps" access for Google Accounts. Sending raw account passwords over basic SMTP authentication is blocked by Google's authentication servers and will immediately fail with:
```text
535 5.7.8 Username and Password not accepted.
```
Google requires dedicated **App Passwords** that bypass interactive 2FA while keeping your primary account password secure.

### Step 1: Enable 2-Step Verification
App Passwords are only available on accounts with 2-Step Verification active:
1. Open your web browser and go to [Google Account Security](https://myaccount.google.com/security).
2. Under the **How you sign in to Google** section, click on **2-Step Verification**.
3. If not already active, follow the prompts to enable it (using Google Authenticator, phone SMS, or Google Prompt).

### Step 2: Generate the 16-Character App Password
1. Navigate directly to the [Google App Passwords Portal](https://myaccount.google.com/apppasswords).
   *(Alternatively, in Google Account Security, search for "App passwords" in the search box at the top).*
2. In the **App name** input field, type:
   ```text
   The Handover Dev
   ```
3. Click the **Create** button.
4. Google will display a popup modal containing a **16-character password** inside a yellow box (e.g., `abcd efgh ijkl mnop`).
5. Copy this password immediately. Once you close the dialog, Google will never show it again.

---

## 4. Environment Configuration

### Minimal `.env` Configuration for Gmail SMTP
Add the following configuration block to your root `.env` file:

```ini
# ==============================================================================
# Transactional Email Delivery (Gmail SMTP Mode)
# ==============================================================================
EMAIL_DELIVERY_ENABLED=true
EMAIL_PROVIDER=gmail_smtp

# Gmail SMTP Connection Details
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-account@gmail.com
SMTP_APP_PASSWORD=abcdefghijklmnop
SMTP_USE_TLS=true
SMTP_TIMEOUT_SECONDS=10.0

# Sender Identity
EMAIL_FROM_ADDRESS=your-account@gmail.com
EMAIL_FROM_NAME="The Handover"

# Frontend Link Construction
FRONTEND_BASE_URL=http://localhost:3000
```

### Complete Environment Variable Reference

| Variable | Type | Default | Validation Aliases | Description |
| :--- | :--- | :--- | :--- | :--- |
| `EMAIL_DELIVERY_ENABLED` | boolean | `false` | `enable_email_delivery` | Master switch. When `false`, emails are not sent and tokens are returned in responses in non-production environments. |
| `EMAIL_PROVIDER` | string | `"none"` | `mail_provider` | Active provider: `"none"`, `"mock"`, `"resend"`, `"gmail_smtp"`. |
| `SMTP_HOST` | string | `"smtp.gmail.com"` | `gmail_smtp_host` | Hostname of the SMTP relay server. |
| `SMTP_PORT` | integer | `587` | `gmail_smtp_port` | Submission port (standard STARTTLS port is `587`). |
| `SMTP_USERNAME` | string | `None` | `smtp_user`, `gmail_smtp_user`, `gmail_user` | Authenticated Google email address. |
| `SMTP_APP_PASSWORD` | SecretStr | `None` | `smtp_password`, `gmail_app_password` | 16-character Google App Password (spaces optional; normalized automatically). |
| `SMTP_USE_TLS` | boolean | `true` | `smtp_tls`, `gmail_smtp_tls` | Whether to issue the `STARTTLS` command before authentication. |
| `SMTP_TIMEOUT_SECONDS` | float | `10.0` | `gmail_smtp_timeout_seconds` | Socket connection and command timeout in seconds (0.5 to 60.0). |
| `EMAIL_FROM_ADDRESS` | string | `"noreply@handover.local"` | `email_from`, `mail_from`, `from_email`, `from_address` | Header sender email. Subject to automatic alignment (see below). |
| `EMAIL_FROM_NAME` | string | `"The Handover"` | `email_name`, `from_name` | Display name for outbound emails. |
| `FRONTEND_BASE_URL` | string | `"http://localhost:3000"` | `frontend_url`, `app_url` | Root URL used to format links in email templates. Must use `https://` in production. |

### Automatic Sender Address Alignment
Gmail's SMTP servers strictly require that the `From:` header matches the authenticated account or a configured Google alias. If a foreign or default address (such as `noreply@handover.local` or `onboarding@resend.dev`) is supplied in `EMAIL_FROM_ADDRESS`, Gmail will reject the email with an `SMTPSenderRefused` error.

To provide a seamless developer experience:
- If `EMAIL_PROVIDER=gmail_smtp` and `EMAIL_FROM_ADDRESS` is set to `noreply@handover.local`, `onboarding@resend.dev`, or any address ending in `.local` or `.invalid`, the backend **automatically aligns** `EMAIL_FROM_ADDRESS` to `SMTP_USERNAME`.
- If you explicitly set a valid email in `EMAIL_FROM_ADDRESS`, that value is preserved (allowing verified Google "Send mail as" aliases to be used).

---

## 5. Non-Blocking Async Architecture

Python's standard `smtplib` library is synchronous and performs blocking network socket I/O. If called directly inside FastAPI's async event loop, slow SMTP handshakes could freeze the entire application server.

The `GmailSMTPEmailProvider` solves this through an internal bounded thread pool:
- Outbound delivery calls (`send()`) are executed in a dedicated `ThreadPoolExecutor(max_workers=4, thread_name_prefix="smtp-worker")`.
- Execution timeouts are enforced via `future.result(timeout=self._timeout_seconds)`.
- Socket errors, timeouts, and authentication failures are caught, logged with sanitized metadata (zero credential or token leaks), and converted into clean `EmailDeliveryResult` objects.

```text
FastAPI Request (async def)
       │
       ▼
TransactionalEmailService.send_verification_email()
       │
       ▼
GmailSMTPEmailProvider.send()
       │
       ▼  (Dispatched to ThreadPoolExecutor worker)
┌────────────────────────────────────────────────────────┐
│ 1. smtplib.SMTP(smtp.gmail.com, 587, timeout=10.0)      │
│ 2. EHLO                                                │
│ 3. STARTTLS (ssl.create_default_context())             │
│ 4. EHLO                                                │
│ 5. LOGIN (smtp_username, smtp_app_password)            │
│ 6. SEND_MESSAGE (MIMEMultipart alternative: HTML+Text) │
│ 7. QUIT                                                │
└────────────────────────────────────────────────────────┘
       │
       ▼  (Future resolved with timeout check)
EmailDeliveryResult(status="sent", provider="gmail_smtp")
```

---

## 6. Testing & Verifying Email Delivery

### 1. Run Automated Unit Tests (Mocked Transport)
The unit test suite verifies all provider behaviors, protocol states, MIME construction, and error scenarios without making live network calls:
```powershell
backend\.venv\Scripts\pytest backend/tests/test_gmail_smtp_provider.py -v
```
*Expected: 32 passed.*

### 2. Run Workflow Integration Tests
Verifies all 5 transactional dispatch workflows with Gmail SMTP configured:
```powershell
backend\.venv\Scripts\pytest backend/tests/test_email_workflows_gmail_smtp.py -v
```
*Expected: 10 passed.*

### 3. Run Transactional Email Baseline Tests
Verifies template rendering, fallback behavior, and service contracts:
```powershell
backend\.venv\Scripts\pytest backend/tests/test_transactional_email.py -v
```
*Expected: 11 passed.*

### 4. Interactive Command-Line Test
You can test live dispatch from your terminal using Python:
```powershell
backend\.venv\Scripts\python -c "
import sys; sys.path.insert(0, 'backend')
from app.core.config import get_settings
from app.services.email import build_email_provider, EmailMessage

settings = get_settings()
print(f'Provider: {settings.email.provider}, Enabled: {settings.email.delivery_enabled}')

provider = build_email_provider(settings)
msg = EmailMessage(
    to_email=settings.email.smtp_username,
    subject='The Handover — SMTP Test',
    html_content='<h1>SMTP Verified!</h1><p>Gmail SMTP delivery is working perfectly.</p>',
    text_content='SMTP Verified! Gmail SMTP delivery is working perfectly.'
)
result = provider.send(msg)
print('Delivery Result:', result.status, result.error_message or 'Success!')
"
```

---

## 7. Troubleshooting Guide

### Issue 1: Authentication Failed (Code 535)
**Verbatim Error Message**:
```text
Gmail SMTP authentication failed. Please verify your Google account email and 16-character App Password (2-Step Verification required).
(535, b'5.7.8 Username and Password not accepted.')
```
**Causes & Resolutions**:
1. **Using normal Google password**: You cannot use your regular account password. Follow Section 3 above to generate an App Password.
2. **2-Step Verification disabled**: If 2-Step Verification is turned off, the App Password portal is inaccessible and existing App Passwords are automatically revoked. Ensure 2FA is active.
3. **Typo in username or password**: Ensure `SMTP_USERNAME` matches the Google account that generated the App Password.
4. **Spaces in password**: The backend strips spaces automatically, but verify there are no hidden control characters or quotation mark errors in `.env`.

### Issue 2: Connection Timeout
**Verbatim Error Message**:
```text
Gmail SMTP connection timed out after 10.0s.
```
**Causes & Resolutions**:
1. **Firewall / ISP blocking port 587**: Some hotel, university, or corporate Wi-Fi networks block outbound traffic on SMTP ports (25, 465, 587) to prevent spam.
   - Test connectivity: Run `Test-NetConnection -ComputerName smtp.gmail.com -Port 587` in PowerShell.
   - If `TcpTestSucceeded : False`, your network is blocking outbound SMTP. Switch to another network or mobile hotspot.
2. **Timeout threshold too strict**: Under high latency or VPN connections, increase the timeout:
   ```ini
   SMTP_TIMEOUT_SECONDS=25.0
   ```

### Issue 3: Recipient Refused (Code 550 / 553)
**Verbatim Error Message**:
```text
Gmail SMTP rejected recipient address: Recipient address rejected or invalid.
(550, b'5.1.1 The email account that you tried to reach does not exist...')
```
**Causes & Resolutions**:
1. The destination mailbox does not exist or has exceeded quota.
2. Google flagged the destination address or domain.
3. Verify recipient email address syntax.

### Issue 4: Sender Address Refused
**Verbatim Error Message**:
```text
Gmail SMTP sender address refused by server.
(553, b'5.7.1 The from-address does not match the authenticated user...')
```
**Causes & Resolutions**:
1. You explicitly configured an `EMAIL_FROM_ADDRESS` that does not match your `SMTP_USERNAME`.
2. Resolution: Either leave `EMAIL_FROM_ADDRESS` empty (so auto-alignment sets it to `SMTP_USERNAME`), or set `EMAIL_FROM_ADDRESS` to match `SMTP_USERNAME`.
3. If you need to send from an alias (e.g. `support@yourdomain.com`), configure that alias under **Settings > Accounts and Import > Send mail as** in your Gmail web interface first.

### Issue 5: TLS Negotiation Failure
**Verbatim Error Message**:
```text
Gmail SMTP TLS negotiation failed.
```
**Causes & Resolutions**:
1. Corporate SSL inspection proxies (e.g., Zscaler, BlueCoat) intercepting TLS handshakes with untrusted certificates.
2. Python environment root certificates outdated. Run `pip install --upgrade certifi`.

---

## 8. Development vs. Production Architecture

| Attribute | Development (`gmail_smtp`) | Production (`resend` / Enterprise Relay) |
| :--- | :--- | :--- |
| **Intended Scope** | Local dev workstations, staging, CI functional tests | Production web services (Render, AWS, GCP) |
| **Delivery Quota** | ~500 emails/day (personal) / ~2,000 (Workspace) | Hundreds of thousands per month |
| **Domain Authentication** | None (uses Google's sender authority) | Strict SPF (`v=spf1`), DKIM (`CNAME`), DMARC (`p=reject`) |
| **Protocol** | Synchronous SMTP over port 587 + STARTTLS | HTTPS REST API over port 443 |
| **Concurrency Model** | Bounded `ThreadPoolExecutor(max_workers=4)` | Async non-blocking HTTPX client pool |
| **Deliverability Tracking** | Terminal logs, recipient inbox | Webhook ingestion (delivered, opened, clicked, bounced) |

> 🔒 **Security Notice**: Never commit `.env` containing your real `SMTP_APP_PASSWORD` to Git. The `.gitignore` file enforces that `.env` is never tracked.
