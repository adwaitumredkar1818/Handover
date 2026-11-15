# Security Review: Google Sign-In & Supabase Identity Exchange

## Overview
A comprehensive security review was conducted covering authentication, authorization, cryptographic verification, token rotation, and threat vectors.

---

## 1. Threat Modeling & Mitigation Analysis

| Threat | Risk Level | Mitigation Strategy & Verification |
| :--- | :--- | :--- |
| **Token Forgery / Spoofing** | Critical | FastAPI verifies token signatures against Supabase JWKS using public keys or HMAC secret. Unsigned or invalidly signed tokens return HTTP 401. |
| **Issuer / Audience Confusion** | High | `iss` must match `${SUPABASE_URL}/auth/v1` and `aud` must match `authenticated`. Cross-tenant tokens from other Supabase projects are rejected. |
| **Account Takeover via Unverified Email** | Critical | Unverified emails in Google OAuth tokens are never linked to existing password-based accounts. Case B strictly checks `is_email_verified`. |
| **Account Takeover via Conflicting Identity** | Critical | If a Supabase `sub` is mapped to User A, but token email belongs to User B, exchange is aborted with HTTP 409 `IDENTITY_CONFLICT`. |
| **Open Redirect via OAuth Callback** | Medium | The Next.js `/auth/callback` route validates `next` to ensure it is a relative path starting with `/` and not `//`. |
| **Session Fixation / Replay** | High | Refresh sessions use SHA-256 hashed rotation. If a previously rotated or revoked refresh token is presented, the entire session family is revoked immediately. |
| **RBAC / Tenant Escalation** | Critical | Google login grants zero organisation or project memberships. Roles and permissions are strictly resolved from PostgreSQL `user_roles`. |
| **Credential Exposure** | Critical | `SUPABASE_SERVICE_ROLE_KEY` is never exposed in frontend code, `.env.local`, or returned in API responses. Only `NEXT_PUBLIC_SUPABASE_ANON_KEY` is client-visible. |

---

## 2. Cookie Security
- `refresh_token` cookie attributes:
  - `HttpOnly`: true (inaccessible to browser JavaScript)
  - `SameSite`: lax (mitigates cross-site request forgery)
  - `Secure`: true in production / HTTPS
  - `Path`: `/api/v1/auth`
- Handover access tokens are short-lived (15 minutes).
