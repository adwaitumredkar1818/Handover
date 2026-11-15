# Troubleshooting Guide: Google Sign-In & Supabase Auth

## Common Issues & Resolutions

### 1. "Supabase Auth is not configured. Please check environment variables."
- **Cause**: `NEXT_PUBLIC_SUPABASE_URL` or `NEXT_PUBLIC_SUPABASE_ANON_KEY` is missing in `frontend/.env.local` or process environment.
- **Resolution**: Provide both variables with valid Supabase project details and restart the Next.js development server.

---

### 2. "redirect_uri_mismatch" Error on Google OAuth Screen
- **Cause**: The authorized redirect URI configured in Google Cloud Console does not match Supabase's callback URL.
- **Resolution**:
  - In Google Cloud Console > Credentials > OAuth 2.0 Client IDs, add:
    `https://<project-ref>.supabase.co/auth/v1/callback`
  - In Supabase Dashboard > Authentication > URL Configuration > Redirect URLs, add:
    `http://localhost:3000/auth/callback` (and production domain equivalent).

---

### 3. "Supabase token signature verification failed" (HTTP 401)
- **Cause**: FastAPI cannot verify the JWT signature.
  - If using asymmetric keys (RS256): FastAPI could not fetch or match the key in `${SUPABASE_URL}/auth/v1/.well-known/jwks.json`.
  - If using symmetric keys (HS256): `SUPABASE_JWT_SECRET` does not match the Supabase project JWT secret.
- **Resolution**:
  - Confirm `SUPABASE_URL` in `.env` is accessible from the backend container/process.
  - Test reaching `curl https://<project-ref>.supabase.co/auth/v1/.well-known/jwks.json`.

---

### 4. "Google email address is not verified. Account linking refused." (HTTP 401)
- **Cause**: The Google account email was reported as unverified, or the claim `email_verified` / `email_confirmed_at` was missing.
- **Resolution**: Log into the Google account and complete Google's email verification prompt, or configure Supabase to require verified emails.

---

### 5. "An account linking conflict was detected" (HTTP 409)
- **Cause**: An existing account in PostgreSQL is already linked to a different `supabase_auth_id`, or the Supabase ID is mapped to User A while the incoming email belongs to User B.
- **Resolution**: Investigate via PostgreSQL `SELECT id, email, supabase_auth_id FROM users WHERE email = '...';`. Never manually overwrite identities without administrative review.
