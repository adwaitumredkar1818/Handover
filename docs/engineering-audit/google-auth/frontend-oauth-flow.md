# Frontend OAuth Flow Specification

## Overview
The Handover frontend implements standard OAuth 2.0 with Proof Key for Code Exchange (PKCE) via the official Supabase SSR package (`@supabase/ssr` and `@supabase/supabase-js`).

---

## 1. OAuth Initiation
When the user clicks "Continue with Google" or "Sign up with Google" on `/login` or `/signup`:
1. `loginWithGoogle()` in `LiveAppContext.tsx` invokes:
   ```ts
   const supabase = createClient()
   await supabase.auth.signInWithOAuth({
     provider: 'google',
     options: {
       redirectTo: `${window.location.origin}/auth/callback`,
       queryParams: {
         access_type: 'offline',
         prompt: 'consent',
       },
     },
   })
   ```
2. The browser generates a PKCE code verifier and code challenge, stores the verifier securely in cookies, and redirects the user to Google.

---

## 2. Callback Handling & PKCE Exchange
1. Google redirects the user back to `/auth/callback?code=...`.
2. The Next.js route handler (`src/app/auth/callback/route.ts`):
   - Validates that `code` is present.
   - Uses `createServerClient` to exchange the code for a Supabase session:
     ```ts
     const { error } = await supabase.auth.exchangeCodeForSession(code)
     ```
   - Mitigates open-redirect attacks by ensuring any `next` parameter is a strictly relative path.
   - On error, redirects to `/login?oauth_error=<message>`.
   - On success, redirects the browser to `${origin}/overview?supabase_auth=success`.

---

## 3. Client Identity Exchange & Session Hydration
1. On initial page load or following redirect, `LiveAppContext.tsx` detects the active Supabase session:
   ```ts
   const { data } = await supabase.auth.getSession()
   if (data?.session?.access_token) {
     const res = await api.auth.exchangeSupabaseToken(data.session.access_token)
     setStoredToken(res.access_token)
     setToken(res.access_token)
     setUser(res.user)
   }
   ```
2. Once exchanged:
   - The Handover access token is stored in `localStorage` (`handover_access_token`).
   - The Handover refresh token is stored in the `HttpOnly` cookie by FastAPI.
   - User profile and permitted organisations/projects load cleanly via existing React queries.

---

## 4. Error & Edge Case Handling
- **User Cancellation**: If the user aborts Google consent, Google redirects with `?error=access_denied`. The callback route captures this and redirects to `/login` displaying a friendly warning.
- **Network / Backend Failure**: Handled with toast messages and clear UI feedback; no half-authenticated sessions persist.
- **Revocation / Expiry**: Handover sessions follow existing 15-minute rotation and 30-day family expiration.
