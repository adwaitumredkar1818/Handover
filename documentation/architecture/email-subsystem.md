# Transactional Email Subsystem Architecture

This document defines the architectural design, security boundaries, provider abstractions, and workflow integrations of the **Transactional Email Subsystem** in **The Handover** platform.

---

## 1. Executive Summary & Domain Boundaries

The **Transactional Email Subsystem** (`backend/app/services/email/`) is responsible for generating, rendering, and dispatching all outbound administrative and security-critical communications across the platform lifecycle:
1. **User Identity & Access Verification**: Verifying email ownership before granting access to project evidence and organizational assets.
2. **Multi-Tenant Collaboration**: Delivering single-use invitation tokens to incoming team members and transition participants.
3. **Security Recovery**: Delivering time-limited password reset tokens.
4. **Platform & Handover Notifications**: Emitting system, source sync, and handover milestone alerts.

### Core Architectural Principles
- **Centralized Provider Pattern**: Decouples domain services from mail delivery transport via `EmailProviderProtocol`, with **Resend** as the single authoritative production provider.
- **Honest Delivery Reporting (Epistemic Integrity)**: When delivery is not enabled, the system honestly reports `"not_configured"` rather than fabricating a delivery state. In local/test environments, verification tokens are returned in the response payload to allow automated testing without external dependencies.
- **Fail-Safe & Non-Blocking**: Outbound email failures never corrupt user registration, database transactions, or invitation creation. Both synchronous and asynchronous interfaces (`send()`, `send_async()`) are provided.
- **Zero Credential Leaks**: Strict error sanitization traps raw transport exceptions and removes all user credentials, tokens, API keys (`re_*`), and private identifiers from logs, exception strings, and API error envelopes.
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
               │ DisabledEmail     ││ MockEmailProvider ││ ResendEmail       │
               │ Provider (none)   ││ (mock in-memory)  ││ Provider (resend) │
               └───────────────────┘└───────────────────┘└─────────┬─────────┘
                                                                   │ Submits via
                                                                   ▼
                                                        ┌─────────────────────┐
                                                        │ Resend REST API SDK │
                                                        │ api.resend.com:443  │
                                                        │ the-sapiens.xyz     │
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
        """Submit an email message synchronously and return delivery outcome."""
        ...

    async def send_async(self, message: EmailMessage) -> EmailDeliveryResult:
        """Submit an email message asynchronously and return delivery outcome."""
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
- **`EmailMessage`**: Encapsulates `to_email`, `subject`, `html_body`, `text_body`, optional `reply_to`, and optional structured `tags`.
- **`EmailDeliveryResult`** (aliased as `EmailDispatchResult`): Standardized return envelope:
  * `status`: `"submitted"` | `"failed"` | `"not_configured"`
  * `provider`: Canonical provider identifier (`"resend"`, `"mock"`, `"none"`)
  * `provider_message_id`: Provider-assigned Message ID (or `None`)
  * `error_message`: Sanitized error description (or `None`)

---

## 3. Provider Implementations

### 3.1 `ResendEmailProvider` (`EMAIL_PROVIDER=resend`)
The canonical transactional email delivery service for Handover:
- **Provider Identity**: Registered sending domain **`the-sapiens.xyz`**, default sender **`Handover <notifications@the-sapiens.xyz>`**.
- **Transport**: Dispatches requests via the official Resend Python SDK (`resend>=2.0.0`) targeting `api.resend.com:443`.
- **Asynchronous & Synchronous Interfaces**: Supports both `send()` and `send_async()` to avoid blocking the event loop during REST API calls.
- **Domain Verification**: Enforces strict SPF (`v=spf1 include:resend.com ~all`), DKIM (`resend._domainkey.the-sapiens.xyz`), and DMARC (`_dmarc.the-sapiens.xyz`).
- **Tagging & Metadata**: Categorizes outbound emails with structured tags (e.g. `category=email_verification`, `category=project_invitation`, `category=password_reset`).

### 3.2 `MockEmailProvider` (`EMAIL_PROVIDER=mock`)
Designed for **headless automated test execution**:
- Captures all outbound messages in an in-memory `sent_messages: list[EmailMessage]` list.
- Simulates realistic delivery results with generated UUID message IDs.
- Zero network I/O, completely safe for continuous integration.

### 3.3 `DisabledEmailProvider` (`EMAIL_PROVIDER=none`)
Default out-of-the-box mode when delivery is turned off (`EMAIL_DELIVERY_ENABLED=false`):
- Returns `EmailDeliveryResult(status="not_configured", provider="none")`.
- In non-production environments, endpoints return generated verification and invitation tokens in the API response JSON to support immediate local development without mail credentials.

---

## 4. Exception Hierarchy & Error Sanitization

The subsystem implements a fine-grained, strongly typed exception hierarchy rooted in `EmailProviderError` (`backend/app/services/email/errors.py`):

```text
EmailProviderError (Base)
├── EmailConfigurationError         (Missing RESEND_API_KEY or unverified sending domain)
├── EmailAuthenticationError        (Invalid or revoked RESEND_API_KEY)
├── EmailConnectionTimeoutError     (API request timeout)
├── EmailRecipientRejectedError     (Mailbox or domain refused)
├── EmailRateLimitError             (Resend 429 rate limit exceeded)
└── EmailValidationError            (Payload or recipient validation error)
```

### Privacy & Sanitization Safeguards
1. **Zero Secret Leaks**: User passwords, API keys (`re_*`), Bearer tokens, and raw verification tokens are automatically scrubbed via regex before error messages or logs are emitted.
2. **PII Masking**: Outbound delivery logs record only the recipient domain (`recipient_domain=@example.com`) rather than full email addresses to prevent PII exposure in centralized logging systems.
3. **Structured Diagnostics**: In failure scenarios, error messages provide clear resolution steps (e.g., domain verification requirements for `the-sapiens.xyz`) without leaking sensitive credentials.

---

## 5. Integrated Transactional Workflows

The platform integrates the transactional email subsystem across all critical workflows:

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              Transactional Workflows                                   │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ 1. User Registration Verification:                                                    │
│    POST /api/v1/auth/register                                                         │
│    --> Creates user (is_email_verified=False)                                         │
│    --> Generates SHA-256 hashed verification token                                    │
│    --> Dispatches HTML+Text verification email via Resend with /verify-email?token=    │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ 2. Project Invitation Registration Verification:                                      │
│    POST /api/v1/auth/register-with-invitation                                         │
│    --> Validates invitation, creates user, joins project/org                          │
│    --> Dispatches verification email (access gate remains until verified)             │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ 3. Verification Resend (Timing-Safe):                                                 │
│    POST /api/v1/auth/resend-verification                                              │
│    --> Authenticated path (current user) or unauthenticated path (email body)         │
│    --> Rate-limited (3 attempts/min) with constant-time response (anti-enumeration)   │
│    --> Dispatches fresh verification token via Resend                                 │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ 4. Project Invitation Dispatch:                                                       │
│    POST /api/v1/organisations/{org_id}/projects/{project_id}/invitations              │
│    --> Evaluates inviter RBAC authority                                               │
│    --> Generates single-use invitation token (stored as SHA-256 hash)                 │
│    --> Dispatches invitation email with project role and expiration metadata          │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ 5. Organisation Invitation Dispatch:                                                  │
│    POST /api/v1/organisations/{org_id}/invitations                                    │
│    --> Evaluates inviter rank authority                                               │
│    --> Dispatches invitation email with organisation role and expiration metadata     │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ 6. Password Reset:                                                                    │
│    POST /api/v1/auth/forgot-password                                                  │
│    --> Generates time-limited reset token                                             │
│    --> Dispatches reset email with /reset-password?token= link                        │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ 7. Platform Notifications:                                                            │
│    TransactionalEmailService.send_platform_notification_email                         │
│    --> Emits task completion, document reconstruction, and milestone alerts           │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Security Architecture & Access Gates

### 6.1 Two-Tier Email Verification Access Gate
The platform enforces email verification using the `require_verified_email` dependency:
- Unverified users can authenticate (login) to receive a valid JWT session.
- When an unverified user attempts to access protected evidence, projects, organizations, or knowledge endpoints, the request is rejected immediately with HTTP 403 `EMAIL_VERIFICATION_REQUIRED`.
- As soon as the user completes verification via `POST /api/v1/auth/verify-email`, `users.is_email_verified` is flipped to `True` and the access gate immediately lifts.

### 6.2 Token Security & Single-Use Guarantees
- **Cryptographic Generation**: Verification, invitation, and reset tokens are generated using `secrets.token_urlsafe(32)` (256 bits of cryptographically secure entropy).
- **Zero Raw Token Storage**: The platform hashes tokens with SHA-256 before persisting them to PostgreSQL (`token_hash = sha256(raw_token)`). Database compromise does not expose usable tokens.
- **Single-Use Enforcement**: Verification and reset tokens are invalidated immediately upon use.

### 6.3 Multi-Tenant Isolation
- Invitation creation requires live permission checks verifying that the inviter belongs to the target organisation/project and holds authorization to grant the requested role.
- Project membership does NOT grant source access: external GitHub, Jira, or Slack access controls are evaluated separately at read-time.

---

## 7. Production Deployment & Readiness Controls

When deploying to production:
1. **Enforce HTTPS**: `FRONTEND_BASE_URL` must start with `https://`. When `APP_ENV=production` and `EMAIL_DELIVERY_ENABLED=true`, the backend validates this requirement at startup and refuses to launch if unencrypted HTTP URLs are configured.
2. **Provider Selection**: `EMAIL_PROVIDER=resend` is mandatory for live delivery.
3. **Domain Verification**: Verify `the-sapiens.xyz` in the Resend Dashboard with SPF, DKIM, and DMARC before promoting to production traffic.
4. **Secret Separation**: `RESEND_API_KEY` must be injected via runtime environment variables (e.g. Render Dashboard or Kubernetes Secrets) and never committed to version control.
