# Transactional Email Configuration & Developer Guide: Resend

This guide details how to configure, test, and troubleshoot outbound transactional email delivery in **The Handover** platform using **Resend** as the single centralized email provider and **`the-sapiens.xyz`** as the registered sending domain.

---

## 1. Overview & Architecture

Outbound transactional emails power all user-facing verification, security, and team collaboration flows:
- **Email Verification**: Delivering single-use cryptographic verification tokens upon user registration (`/verify-email?token=...`).
- **Access Gate Lifting**: Lifting the HTTP 403 `EMAIL_VERIFICATION_REQUIRED` barrier once the recipient verifies their email address.
- **Organisation Invitations**: Inviting participants to organisations with scoped roles (`/invitations/{token}`).
- **Project Workspace Invitations**: Inviting collaborators and reviewers to project workspaces (`/invitations/{token}`).
- **Password Reset**: Delivering secure, time-limited password reset tokens (`/reset-password?token=...`).
- **Platform Notifications**: Emitting system, source sync, and handover milestone alerts.

All email operations pass exclusively through the centralized `TransactionalEmailService` and `ResendEmailProvider`.

### Supported Provider Modes

| Provider Mode (`EMAIL_PROVIDER`) | Recommended Environment | Zero External Setup? | Delivers to Inboxes? | Key Characteristic |
| :--- | :--- | :---: | :---: | :--- |
| `none` | Unit Tests / Offline Dev | Yes | No | Delivery disabled. Verification and invitation tokens are returned directly in API responses for non-production environments. |
| `mock` | Automated Headless Tests | Yes | No | Captures emails in-memory (`MockEmailProvider.sent_messages`) for headless test suites (`backend/tests/`). |
| `resend` | **Active Dev, Staging & Production** | Requires `RESEND_API_KEY` | **Yes** | **Canonical delivery provider**. Submits via official Resend Python SDK with sending domain `the-sapiens.xyz` and sender `Handover <notifications@the-sapiens.xyz>`. |

> ⚠️ **Provider Policy**: Resend is the sole transactional email delivery service. Gmail SMTP and other legacy SMTP relays are completely removed and are not supported as fallbacks.

---

## 2. Domain & Sender Identity Configuration

| Setting | Value |
|---|---|
| Platform | Handover |
| Email provider | Resend |
| Sending domain | `the-sapiens.xyz` |
| Default sender name | Handover |
| Default sender address | `notifications@the-sapiens.xyz` |
| Default sender identity | `Handover <notifications@the-sapiens.xyz>` |
| Integration | Official Resend Python SDK (`resend>=2.0.0`) |
| Backend | FastAPI (Python 3.11) |

---

## 3. Environment Configuration

### Minimal `.env` Configuration for Resend
Add the following configuration block to your root `.env` file:

```ini
# ==============================================================================
# Transactional Email Delivery (Resend Provider)
# ==============================================================================
EMAIL_DELIVERY_ENABLED=true
EMAIL_PROVIDER=resend

# Resend API Key from https://resend.com/api-keys
RESEND_API_KEY=re_your_api_key_here

# Outbound Sender Identity
EMAIL_FROM="Handover <notifications@the-sapiens.xyz>"
EMAIL_FROM_ADDRESS=notifications@the-sapiens.xyz
EMAIL_FROM_NAME="Handover"
EMAIL_SENDING_DOMAIN=the-sapiens.xyz
EMAIL_HTTP_TIMEOUT_SECONDS=10.0

# Base URL for frontend email verification links and invitation links
# In production, this MUST use HTTPS when EMAIL_DELIVERY_ENABLED=true.
FRONTEND_BASE_URL=http://localhost:3000
```

### Complete Environment Variable Reference

| Variable | Type | Default | Aliases | Description |
| :--- | :--- | :--- | :--- | :--- |
| `EMAIL_DELIVERY_ENABLED` | boolean | `false` | `enable_email_delivery` | Master delivery switch. When `false`, outbound delivery is suppressed and tokens are returned in responses in development mode. |
| `EMAIL_PROVIDER` | string | `"resend"` | `mail_provider` | Active provider: `"none"`, `"mock"`, `"resend"`. |
| `RESEND_API_KEY` | SecretStr | `None` | `resend_key` | Secret API key generated from the Resend Dashboard. Never expose to frontend or commit to Git. |
| `EMAIL_FROM` | string | `None` | `mail_from` | Formatted sender identity e.g. `Handover <notifications@the-sapiens.xyz>`. Automatically parses name and address. |
| `EMAIL_FROM_ADDRESS` | string | `"notifications@the-sapiens.xyz"` | `from_email`, `from_address` | Fallback envelope sender email address. |
| `EMAIL_FROM_NAME` | string | `"Handover"` | `email_name`, `from_name` | Display name for outbound emails. |
| `EMAIL_SENDING_DOMAIN` | string | `"the-sapiens.xyz"` | `sending_domain`, `email_domain` | Verified sending domain. |
| `EMAIL_HTTP_TIMEOUT_SECONDS` | float | `10.0` | `email_timeout_seconds` | Request timeout for Resend API calls (seconds). |
| `FRONTEND_BASE_URL` | string | `"http://localhost:3000"` | `app_url`, `frontend_url` | Root URL used to format links in email templates. Must use `https://` in production. |

---

## 4. Domain Verification & DNS Setup Procedure

The sending domain is **`the-sapiens.xyz`**. It must be added to the Resend Dashboard and verified before sending production emails to arbitrary recipient inboxes.

### Step-by-Step Verification Process

1. **Add Domain in Resend Dashboard**:
   - Log into [Resend Dashboard](https://resend.com/domains).
   - Click **Add Domain**.
   - Enter `the-sapiens.xyz` and select your target region (e.g., `us-east-1` or `eu-west-1`).
   - Click **Add**.

2. **Retrieve Exact DNS Records**:
   - Resend displays the exact DNS records required for SPF and DKIM.
   - Do **NOT** invent values or assume tokens. Always copy the exact values generated by Resend.

3. **Required DNS Records Reference**:

| Record Type | Hostname / Name | Priority | Expected Value / Target | Purpose |
| :--- | :--- | :---: | :--- | :--- |
| **MX** | `feedback-smtp.resend.com` (or as shown in Resend) | `10` | `feedback-smtp.resend.com` | Mail exchange for delivery bounces and feedback loops. |
| **TXT** (SPF) | `the-sapiens.xyz` (or `bounces.the-sapiens.xyz`) | - | `v=spf1 include:resend.com ~all` | Authorizes Resend mail servers to send emails on behalf of `the-sapiens.xyz`. |
| **TXT / CNAME** (DKIM) | `resend._domainkey.the-sapiens.xyz` | - | (Generated cryptographic token from Resend) | Cryptographically verifies that the email was sent by Handover and was not altered in transit. |
| **TXT** (DMARC) | `_dmarc.the-sapiens.xyz` | - | `v=DMARC1; p=none; rua=mailto:dmarc-reports@the-sapiens.xyz; sp=none; aspf=r; adkim=r` | Specifies domain handling policy and reporting address for unauthorized emails. |

### Critical DNS Safety Rules

> ⚠️ **MANDATORY RULES FOR ADMINISTRATORS**:
> 1. **Check Existing SPF Before Adding**: An RFC 7208 compliant domain can only have **one** SPF `TXT` record. If `the-sapiens.xyz` already has an SPF record (e.g. from Google Workspace or Microsoft 365), **never add a second record**. Instead, merge `include:resend.com` into the existing record:
>    `v=spf1 include:_spf.google.com include:resend.com ~all`
> 2. **Never Overwrite Existing DNS**: Preserve existing `A`, `AAAA`, `CNAME`, nameserver, and website records for `the-sapiens.xyz`.
> 3. **Manual Approval Only**: All DNS changes must be applied manually through your domain registrar (e.g., Cloudflare, Namecheap, GoDaddy). Never use automated scripts to mutate production DNS records without review.
> 4. **Wait for Propagation**: DNS propagation may take from 5 minutes up to 48 hours. Click **Verify Domain** in the Resend dashboard only after the records propagate.

---

## 5. Testing & Verification

### 1. Automated Provider Unit Tests
Verifies provider initialization, default domain, sender identity formatting, error handling, rate limiting, and sanitization:
```powershell
backend\.venv\Scripts\pytest backend/tests/test_resend_provider.py -v
```

### 2. End-to-End Workflow Integration Tests
Verifies all 5 transactional flows with Resend (registration verification, resend, org invites, project invites, password reset, and access gate):
```powershell
backend\.venv\Scripts\pytest backend/tests/test_email_workflows_resend.py -v
```

### 3. All Transactional Email Tests
Runs all unit and integration email suites together:
```powershell
backend\.venv\Scripts\pytest backend/tests/test_resend_provider.py backend/tests/test_email_workflows_resend.py backend/tests/test_transactional_email.py backend/tests/test_email_verification_and_access_gate.py backend/tests/test_password_reset.py -v
```

### 4. Interactive Live Verification Script
To test live delivery to a real inbox using your configured `RESEND_API_KEY`:
```powershell
backend\.venv\Scripts\python scripts/verify_live_resend.py --email user@example.com --direct
```

---

## 6. Security & Privacy Safeguards

- **Backend-Only Secrets**: `RESEND_API_KEY` is loaded exclusively into backend memory (`Settings.email.resend_api_key`) and is never exposed to the frontend or browser bundles.
- **Sanitized Logging**: All raw tokens, passwords, and API keys are redacted before writing to log streams. Error messages scrub any string resembling `re_*` or `Bearer *`.
- **Pre-Retrieval Authorization**: Project and organisation membership does not grant source access. All invitation and verification actions enforce strict backend RBAC.
- **Zero Fallback to Gmail SMTP**: No fallback or silent relay to Gmail SMTP exists. If Resend delivery fails, the error is handled cleanly through standard error channels.
