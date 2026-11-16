# Transactional Email Subsystem Architecture

This document defines the architectural design, security boundaries, provider abstractions, and workflow integrations of the **Transactional Email Subsystem** in **The Handover** platform.

---

## 1. Executive Summary & Domain Boundaries

The **Transactional Email Subsystem** (`backend/app/services/email/`) is responsible for generating, rendering, and dispatching all outbound administrative and security-critical communications across the platform lifecycle:
1. **User Identity & Access Verification**: Verifying email ownership before granting access to project evidence and organizational assets.
2. **Multi-Tenant Collaboration**: Delivering single-use invitation tokens to incoming team members and transition participants.
3. **Security Recovery**: Delivering time-limited password reset tokens.

### Core Architectural Principles
- **Pluggable Provider Pattern**: Decouples domain services from concrete mail delivery transports via `EmailProviderProtocol`.
- **Honest Delivery Reporting (Epistemic Integrity)**: When delivery is not enabled, the system honestly reports `"not_configured"` rather than fabricating a delivery state. In local/test environments, verification tokens are returned in the response payload to allow automated testing without external dependencies.
- **Fail-Safe & Non-Blocking**: Outbound email failures never corrupt user registration, database transactions, or invitation creation. Synchronous socket I/O is isolated from FastAPI's asynchronous event loop.
- **Zero Credential Leaks**: Strict error sanitization traps raw transport exceptions and removes all user credentials, tokens, and private identifiers from logs, exception strings, and API error envelopes.
- **Two-Tier Access Gating**: Protects platform endpoints with an explicit `require_verified_email` security dependency that rejects unverified users with HTTP 403 `EMAIL_VERIFICATION_REQUIRED`.

---

## 2. Subsystem Topology & Class Hierarchy

```text
                                  ┌────────────────────────┐
                                  │      FastAPI App       │
                                  │  (Routes & Controller) │
                                  └───────────┬────────────┘
                                              │ Calls high-level workflow
                                              ▼
                                  ┌────────────────────────┐
                                  │ TransactionalEmail     │
                                  │        Service         │
                                  └───────────┬────────────┘
                                              │ Uses
                                              ▼
                                  ┌────────────────────────┐
                                  │   build_email_provider │
                                  │      (Factory)         │
                                  └───────────┬────────────┘
                                              │ Instantiates
                         ┌────────────────────┼────────────────────┐
                         │                    │                    │
                         ▼                    ▼                    ▼
               ┌───────────────────┐┌───────────────────┐┌───────────────────┐
               │ DisabledEmail     ││ ResendEmail       ││ GmailSMTPEmail    │
               │ Provider (none)   ││ Provider (resend) ││ Provider (smtp)   │
               └───────────────────┘└───────────────────┘└─────────┬─────────┘
                                                                   │ Submits to
                                                                   ▼
                                                        ┌─────────────────────┐
                                                        │ ThreadPoolExecutor  │
                                                        │ (max_workers=4)     │
                                                        └──────────┬──────────┘
                                                                   │ Non-blocking
                                                                   ▼
                                                        ┌─────────────────────┐
                                                        │ smtplib.SMTP        │
                                                        │ smtp.gmail.com:587  │
                                                        └─────────────────────┘
```

### 2.1 Interface Contract (`EmailProviderProtocol`)
All email providers adhere to the `EmailProviderProtocol` defined in `backend/app/services/email/base.py`:

```python
class EmailProviderProtocol(Protocol):
    """Protocol for transactional email provider implementations."""

    @property
    def provider_name(self) -> str:
        """Return the unique canonical provider name."""
        ...

    def send(self, message: EmailMessage) -> EmailDeliveryResult:
        """Send an email message synchronously or via worker pool."""
        ...

    def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
    ) -> EmailDeliveryResult:
        """Convenience method sending to a single recipient."""
        ...
```

### 2.2 Canonical Data Structures
- **`EmailMessage`**: Encapsulates `to_email`, `subject`, `html_content`, optional `text_content`, optional `reply_to`, and optional structured `metadata`.
- **`EmailDeliveryResult`** (aliased as `EmailDispatchResult`): Standardized return envelope:
  * `status`: `"sent"` | `"failed"` | `"not_configured"`
  * `provider`: Canonical provider identifier (`"none"`, `"mock"`, `"resend"`, `"gmail_smtp"`)
  * `message_id`: Provider-assigned or RFC-2822 generated Message-ID (or `None`)
  * `error_message`: Sanitized error description (or `None`)

---

## 3. Provider Implementations

### 3.1 `GmailSMTPEmailProvider` (`EMAIL_PROVIDER=gmail_smtp`)
Designed for **active local development, staging, and functional integration testing**:
- **Protocol & Security**: Submits via `smtp.gmail.com:587` with explicit `STARTTLS` negotiation using Python's `ssl.create_default_context()`.
- **Authentication**: Requires a 16-character Google App Password (spaces normalized automatically). Rejects standard Google passwords with descriptive guidance.
- **Asynchronous Execution Model**: Because `smtplib.SMTP` performs blocking socket operations, `send()` dispatches delivery tasks to an internal bounded `ThreadPoolExecutor(max_workers=4, thread_name_prefix="smtp-worker")`. This guarantees:
  1. FastAPI's event loop is never blocked by network latency or SMTP socket operations.
  2. Execution timeouts (`future.result(timeout=self._timeout_seconds)`) strictly prevent hanging worker threads.
- **Message Assembly**: Generates compliant RFC-2822 `multipart/alternative` MIME payloads containing both UTF-8 `text/plain` and `text/html` components, ensuring compatibility with all email clients.
- **Sender Auto-Alignment**: If `EMAIL_FROM_ADDRESS` is set to default non-routable domains (`noreply@handover.local`, `onboarding@resend.dev`, `*.local`), the provider automatically aligns the `From:` header with `SMTP_USERNAME` to prevent Gmail from rejecting unauthorized envelope senders.

### 3.2 `ResendEmailProvider` (`EMAIL_PROVIDER=resend`)
Designed for **cloud production deployments**:
- **Protocol**: Dispatches requests via Resend's transactional REST API (`https://api.resend.com/emails`) using HTTPX with connection pooling and configurable request timeouts.
- **Domain Authentication**: Requires verified custom domain records (`SPF`, `DKIM`, and `DMARC`).
- **Sandbox Fallback**: If using Resend's free evaluation sandbox without a verified domain, automatically falls back to `onboarding@resend.dev` (delivering exclusively to the registered Resend account owner).

### 3.3 `MockEmailProvider` (`EMAIL_PROVIDER=mock`)
Designed for **headless automated test execution**:
- Captures all outbound messages in an in-memory `sent_messages: list[EmailMessage]` queue.
- Exposes query methods (`get_last_message()`, `clear()`) for assertion in unit and integration test fixtures.
- Simulates realistic delivery results with generated UUID message IDs.

### 3.4 `DisabledEmailProvider` (`EMAIL_PROVIDER=none`)
Default out-of-the-box mode:
- Returns `EmailDeliveryResult(status="not_configured", provider="none")`.
- When active in non-production environments, endpoints return generated verification and invitation tokens in the API response JSON to support immediate developer onboarding without mail infrastructure.

---

## 4. Exception Hierarchy & Error Sanitization

The subsystem implements a fine-grained, strongly typed exception hierarchy rooted in `EmailProviderError` (`backend/app/services/email/errors.py`):

```text
EmailProviderError (Base)
├── EmailConfigurationError         (Missing host, port, username, or credentials)
├── EmailAuthenticationError        (Code 535 / Google App Password rejection)
├── EmailConnectionTimeoutError     (Socket connect/read timeout)
└── EmailRecipientRejectedError     (Code 550 / 553 recipient refusal)
```

### Privacy & Sanitization Safeguards
1. **Zero Secret Leaks**: User passwords, Google App Passwords, API keys, and raw verification tokens are never logged or exposed in `error_message` attributes.
2. **PII Masking**: Outbound delivery logs record only the recipient domain (`recipient_domain=@gmail.com`) rather than full email addresses to prevent PII exposure in centralized logging systems.
3. **Structured Diagnostics**: In failure scenarios, error messages provide actionable resolution steps (e.g., reminding developers that 2-Step Verification is required for Google App Passwords) without leaking sensitive credentials.

---

## 5. Integrated Transactional Workflows

The platform integrates the transactional email subsystem across five canonical workflows:

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              5 Transactional Workflows                                │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ 1. User Registration Verification:                                                    │
│    POST /api/v1/auth/register                                                         │
│    --> Creates user (is_email_verified=False)                                         │
│    --> Generates SHA-256 hashed verification token                                    │
│    --> Dispatches HTML+Text verification email with /verify-email?token= link          │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ 2. Project Invitation Registration Verification:                                      │
│    POST /api/v1/auth/register?invitation_token=...                                    │
│    --> Validates invitation, creates user, joins project/org                          │
│    --> Dispatches verification email (access gate remains until verified)             │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ 3. Verification Resend (Timing-Safe):                                                 │
│    POST /api/v1/auth/resend-verification                                              │
│    --> Authenticated path (current user) or unauthenticated path (email body)         │
│    --> Rate-limited (3 attempts/min) with constant-time response (anti-enumeration)   │
│    --> Dispatches fresh verification token                                            │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ 4. Project Invitation Dispatch:                                                       │
│    POST /api/v1/projects/{project_id}/invitations                                     │
│    --> Evaluates inviter RBAC authority                                               │
│    --> Generates single-use invitation token (stored as SHA-256 hash)                 │
│    --> Dispatches invitation email with project role and expiration metadata          │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ 5. Organisation Invitation Dispatch:                                                  │
│    POST /api/v1/organisations/{org_id}/invitations                                    │
│    --> Evaluates inviter rank authority                                               │
│    --> Dispatches invitation email with organisation role and expiration metadata     │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Security Architecture & Access Gates

### 6.1 Two-Tier Email Verification Access Gate
The platform enforces email verification using the `require_verified_email` dependency:
- Unverified users can authenticate (login) to receive a valid JWT session.
- When an unverified user attempts to access protected evidence, projects, organizations, or knowledge endpoints, the request is rejected immediately with:
  ```json
  {
    "detail": {
      "error_code": "EMAIL_VERIFICATION_REQUIRED",
      "message": "Email verification is required before accessing this resource.",
      "email": "user@example.com"
    }
  }
  ```
- As soon as the user completes verification via `GET /api/v1/auth/verify-email?token=...`, `users.is_email_verified` is flipped to `True` and the access gate immediately lifts.

### 6.2 Token Security & Single-Use Guarantees
- **Cryptographic Generation**: Verification and invitation tokens are generated using `secrets.token_urlsafe(32)` (256 bits of cryptographically secure entropy).
- **Zero Raw Token Storage**: The platform hashes tokens with SHA-256 before persisting them to PostgreSQL (`token_hash = sha256(raw_token)`). Database compromise does not expose usable tokens.
- **Single-Use Enforcement**:
  * Verification tokens are invalidated upon use (`token_expires_at = now()`, `is_email_verified = True`). Re-verification is idempotent, returning HTTP 200 with `"already verified"`.
  * Invitation tokens transition to status `"accepted"` atomically upon consumption. Subsequent acceptance attempts are rejected with HTTP 409 `INVITATION_ALREADY_ACCEPTED`.

### 6.3 Multi-Tenant Isolation
- Invitation creation requires live permission checks verifying that the inviter belongs to the target organisation/project and holds authorization to grant the requested role.
- Cross-tenant invitation attempts fail with HTTP 403 or 404, preventing tenant enumeration and triggering zero outbound emails.

---

## 7. Production Deployment & Readiness Controls

When deploying to production:
1. **Enforce HTTPS**: `FRONTEND_BASE_URL` must start with `https://`. When `APP_ENV=production` and `EMAIL_DELIVERY_ENABLED=true`, the backend validates this requirement at startup and refuses to launch if unencrypted HTTP URLs are configured.
2. **Provider Selection**: Use `EMAIL_PROVIDER=resend` (or enterprise SMTP relay). Personal Gmail accounts are bounded by Google's ~500 emails/day rolling limit and are restricted to development and staging environments.
3. **Secret Separation**: All SMTP passwords and API keys must be injected via runtime environment variables (e.g. Render Dashboard or Kubernetes Secrets) and never committed to version control.
