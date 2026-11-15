# Supabase Provider Configuration Guide

## Objective
Configure Google OAuth as an authentication provider in the Supabase Dashboard, set redirect URL allowlists, and prepare the client credentials.

---

## 1. Enable Google Provider in Supabase
1. Log in to the [Supabase Dashboard](https://supabase.com/dashboard).
2. Select your Handover project.
3. In the left navigation, click on **Authentication** > **Providers**.
4. Locate **Google** in the provider list and toggle **Enable Sign in with Google** to **ON**.
5. Paste the credentials obtained from Google Cloud Console:
   - **Client ID**: Paste your Google OAuth Client ID.
   - **Client Secret**: Paste your Google OAuth Client Secret.
6. Verify the Callback URL matches what was entered in GCP:
   ```text
   https://<project-ref>.supabase.co/auth/v1/callback
   ```
7. Click **Save**.

---

## 2. Configure URL Configuration (Redirect Allow List)
1. In the left navigation, click on **Authentication** > **URL Configuration**.
2. **Site URL**:
   - For local development: `http://localhost:3000`
   - For production: `https://your-domain.com`
3. **Redirect URLs**:
   Add the following paths to the allowed redirect list:
   - `http://localhost:3000/auth/callback`
   - `http://localhost:3000/**`
   - Production URL equivalent: `https://your-domain.com/auth/callback`
4. Click **Save**.

---

## 3. Environment Variable Provisioning

### Backend (`.env` or server runtime):
```bash
# Supabase Auth Configuration
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_AUTH_ENABLED=true
SUPABASE_AUTH_AUDIENCE=authenticated
# Optional: explicitly configure if different from default URL:
# SUPABASE_AUTH_ISSUER=https://<project-ref>.supabase.co/auth/v1
# SUPABASE_AUTH_JWKS_URL=https://<project-ref>.supabase.co/auth/v1/.well-known/jwks.json
```

### Frontend (`frontend/.env.local`):
```bash
# Public Supabase credentials for client-side PKCE flow
NEXT_PUBLIC_SUPABASE_URL=https://<project-ref>.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJhbGciOi...
```

> **Security Rule**: The `NEXT_PUBLIC_SUPABASE_ANON_KEY` is a client-safe publishable key. Never place `SUPABASE_SERVICE_ROLE_KEY` or Google Client Secrets in frontend environment variables.
