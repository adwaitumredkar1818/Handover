# Implementation Plan: Google Sign-In Using Supabase Auth & FastAPI Identity Exchange

## Executive Summary
This document outlines the architectural plan for implementing secure Google Sign-In for **The Handover** using Supabase Auth as the OAuth identity provider, while preserving the existing FastAPI-managed authentication, JWT issuance, Argon2id hashing, session lifecycle, rotation, and PostgreSQL RBAC/source-level ACL systems.

This integration follows an **identity exchange pattern**, not an authentication replacement:
```
Google OAuth (PKCE) ──▶ Supabase Auth ──▶ Verified Identity Exchange ──▶ FastAPI Session & JWTs ──▶ Handover Access
```

---

## 1. Inspection Findings

### 1.1 Existing Database Schema & Migration 0009
- Migration `0009_supabase_and_vector_indexes` (`20261113_0009_supabase_auth_and_vector_indexes.py`):
  - Already added `supabase_auth_id VARCHAR(128)` to the `users` table with a unique index `ix_users_supabase_auth_id`.
  - Relaxed `password_hash` to be nullable (`nullable=True`), enabling accounts created via OAuth or SSO without a local password hash.
- SQLAlchemy User Model (`backend/app/models/user.py`):
  - Field `supabase_auth_id: Mapped[str | None] = mapped_column(String(128), unique=True, index=True, nullable=True)`.
  - Field `is_email_verified: Mapped[bool]`.
  - Field `email_verified_at: Mapped[datetime | None]`.
  - Field `status: Mapped[str]` (CheckConstraint: active, disabled, locked, pending).
- **Conclusion**: The schema is **100% prepared**. No new database migration or schema alteration is necessary.

### 1.2 Existing Authentication & Session Lifecycle
- FastAPI is the single platform identity authority:
  - Issues short-lived access tokens (`jwt_access_token_expire_minutes`, default 15 min).
  - Rotates opaque refresh tokens (`jwt_refresh_token_expire_days`, default 30 days) stored as SHA-256 digests in `refresh_sessions` with family revocation on reuse detection.
  - Deliver refresh tokens via `HttpOnly`, `SameSite=lax`, `Secure` cookies (`refresh_token`).
  - Strict CSRF origin validation on refresh and logout (`validate_csrf_origin`).
  - Roles and permissions resolved strictly from PostgreSQL tables `user_roles`, `roles`, `permissions`.
  - Source ACLs and project membership are distinct; project membership != source access.

### 1.3 Supabase & Environment Configuration
- Existing backend settings (`app.core.config.Settings`):
  - Has `supabase_url`, `supabase_service_role_key`, `supabase_storage_bucket`.
  - `supabase_service_role_key` is strictly reserved for server-side object storage (`STORAGE_PROVIDER=supabase_storage`).
- Missing settings to add for Supabase Auth identity verification:
  - `SUPABASE_AUTH_AUDIENCE` (default: `"authenticated"`).
  - `SUPABASE_AUTH_ISSUER` (default: derived from `SUPABASE_URL + "/auth/v1"`).
  - `SUPABASE_AUTH_JWKS_URL` (default: derived from `SUPABASE_URL + "/auth/v1/.well-known/jwks.json"`).
  - Supabase client verification mode (JWKS asymmetric verification via PyJWKClient).
- Frontend settings:
  - `NEXT_PUBLIC_SUPABASE_URL`
  - `NEXT_PUBLIC_SUPABASE_ANON_KEY`

---

## 2. Target Architecture & Identity Exchange

### 2.1 Complete Flow
1. **Initiation**: User clicks "Continue with Google" on `/login` or `/signup`.
2. **PKCE Flow**: Browser Supabase client initiates OAuth with Google:
   `supabase.auth.signInWithOAuth({ provider: 'google', options: { redirectTo: `${origin}/auth/callback` } })`
3. **Google Consent & Redirect**: Google authenticates user and redirects back to `/auth/callback?code=...`.
4. **Callback & Code Exchange**:
   - Next.js route `/auth/callback` exchanges the code for a Supabase session using `@supabase/ssr`.
   - Obtains Supabase access token (JWT signed by Supabase).
5. **FastAPI Identity Exchange**:
   - Client calls `POST /api/v1/auth/supabase/exchange` with payload `{ access_token: "<supabase_jwt>" }`.
6. **Backend Verification**:
   - Fetches / caches Supabase JWKS from `${SUPABASE_URL}/auth/v1/.well-known/jwks.json`.
   - Validates JWT signature (RS256 / ES256).
   - Validates claims: `iss == ${SUPABASE_URL}/auth/v1`, `aud == "authenticated"`, `exp > now`, `sub == supabase_user_id`.
   - Validates email verification (`email_verified == true`).
7. **Identity Resolution (4 Cases)**:
   - **Case A (Linked)**: Existing user with matching `supabase_auth_id` -> Authenticate.
   - **Case B (Unlinked Match)**: Existing user with matching confirmed email:
     - Verify Supabase email is confirmed.
     - Safely link `user.supabase_auth_id = supabase_sub`.
     - Log security audit event `auth.oauth.linked`.
     - Authenticate.
   - **Case C (New User)**: No user with email or supabase_auth_id:
     - Create user record with `supabase_auth_id`, `password_hash = None`, `is_email_verified = True`.
     - Assign default role (`standard_user`).
     - Log security audit event `auth.oauth.registered`.
     - Authenticate.
   - **Case D (Conflict)**: Supabase ID maps to User X, but token email belongs to User Y -> Reject with HTTP 409 CONFLICT (`IDENTITY_CONFLICT`).
8. **Session Issuance**:
   - Creates new `RefreshSession` token family in PostgreSQL.
   - Issues Handover access token (JWT).
   - Sets `refresh_token` in `HttpOnly` cookie.
   - Returns `AccessTokenResponse` with user summary, platform roles, and permissions.

---

## 3. Implementation Steps

1. **Backend**:
   - Add Supabase Auth configuration to `Settings` (`supabase_auth_audience`, `supabase_auth_issuer_url`, `supabase_auth_jwks_url`).
   - Implement `SupabaseTokenVerifier` using `jwt.PyJWKClient` with in-memory caching and fallback URL logic.
   - Update `AuthService` with `exchange_supabase_token(access_token, session_metadata)`.
   - Update `AuthSchemas` with `SupabaseExchangeRequest`.
   - Add endpoint `POST /api/v1/auth/supabase/exchange` to `backend/app/api/routes/auth.py`.
   - Add security audit logging for all OAuth exchange events.
2. **Frontend**:
   - Configure `@supabase/ssr` browser and server clients in `frontend/src/lib/supabase/`.
   - Implement Next.js callback route in `frontend/src/app/auth/callback/route.ts` with error handling, PKCE code exchange, and redirection.
   - Update `api.auth` in `frontend/src/lib/api.ts` with `exchangeSupabaseToken()`.
   - Update `LiveAppContext.tsx` with `loginWithGoogle()` and `handleOAuthExchange()`.
   - Update `AuthPage.tsx` Google button to initiate Google OAuth.
3. **Testing**:
   - Write unit and integration tests for `SupabaseTokenVerifier` and `/auth/supabase/exchange`.
   - Verify Cases A, B, C, D, invalid signature, wrong issuer, expired token, unverified email, disabled account.
   - Run backend test suite.
   - Run frontend typecheck and build.
4. **Documentation**:
   - Provide complete set of audit and setup documents in `docs/engineering-audit/google-auth/`.
