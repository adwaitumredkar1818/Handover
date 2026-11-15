# Backend Token Verification Specification

## Overview
FastAPI verifies incoming Supabase access tokens using `SupabaseTokenVerifier` (`backend/app/services/supabase_verifier.py`).

---

## 1. Verification Mechanism

1. **Unverified Header Inspection**:
   - Inspects the JWT header for `alg` and `kid`.
   - Supports asymmetric algorithms: `RS256`, `RS384`, `RS512`, `ES256`, `ES384`, `ES512`.
   - Supports symmetric algorithms (when configured with `SUPABASE_JWT_SECRET`): `HS256`, `HS384`, `HS512`.
2. **JWKS Fetching & Caching**:
   - Uses PyJWT's `PyJWKClient` to fetch signing keys from `${SUPABASE_URL}/auth/v1/.well-known/jwks.json`.
   - In-memory key caching (`cache_keys=True`) prevents redundant network round-trips on every request.
3. **Claim Validation**:
   - `iss`: Matches configured Supabase Auth issuer (`${SUPABASE_URL}/auth/v1`).
   - `aud`: Matches expected audience (`authenticated`).
   - `exp`: Validates expiration with standard clock drift tolerance.
   - `nbf`: Validates token is not active before its activation time.
   - `sub`: Validates non-empty Supabase user identifier UUID.
4. **Email & Metadata Extraction**:
   - Extracts email address and downcases it.
   - Inspects `email_confirmed_at`, `user_metadata.email_verified`, or `app_metadata.email_verified`.
   - Extracts `full_name` or `name` from user metadata.

---

## 2. Security Boundaries & Invariants
- **No Service Role Key for Verification**: The Supabase service-role key is **never** used to verify user tokens; verification uses public JWKS or standard HMAC signature checks.
- **Fail Closed**: Any signature failure, claim mismatch, or malformed header immediately raises `UnauthorizedError(HTTP 401)`.
- **Audit Logging**: All verification failures and successes are recorded in the security audit log (`log_security_event`).
