# Google Cloud Platform: OAuth 2.0 Credentials Setup Guide

## Objective
Configure an OAuth 2.0 Client ID in Google Cloud Platform (GCP) for Supabase Auth to broker Google Sign-In on behalf of **The Handover**.

---

## 1. Prerequisites
- Access to [Google Cloud Console](https://console.cloud.google.com/).
- A GCP project for The Handover or your organisation.
- Your Supabase Project URL (`https://<project-ref>.supabase.co`).

---

## 2. Step-by-Step Configuration

### Step 1: Configure OAuth Consent Screen
1. In Google Cloud Console, navigate to **APIs & Services** > **OAuth consent screen**.
2. Select User Type:
   - **Internal**: If authentication is restricted to your Google Workspace organization.
   - **External**: If allowing users from arbitrary Google accounts (testing or multi-tenant production).
3. Fill in App Information:
   - **App name**: `The Handover`
   - **User support email**: Your admin/support email.
   - **App logo**: Optional.
   - **Application home page**: `http://localhost:3000` (or production domain).
   - **Authorized domains**: Add `supabase.co` (and your production domain).
   - **Developer contact information**: Your technical contact email.
4. Scopes:
   - Ensure the standard OpenID scopes are selected:
     - `.../auth/userinfo.email`
     - `.../auth/userinfo.profile`
     - `openid`
5. Test Users (if External and in "Testing" status):
   - Add the email addresses of users who will test Google Sign-In during development.
6. Click **Save and Continue**.

### Step 2: Create OAuth 2.0 Client Credentials
1. Navigate to **APIs & Services** > **Credentials**.
2. Click **Create Credentials** > **OAuth client ID**.
3. Select Application type: **Web application**.
4. Set **Name**: `The Handover - Supabase Auth Broker`.
5. Under **Authorized JavaScript origins**:
   - Local: `http://localhost:3000`
   - Production: `https://your-production-domain.com`
   - Supabase project URL: `https://<project-ref>.supabase.co`
6. Under **Authorized redirect URIs**:
   - Provide the Supabase callback URI:
     ```text
     https://<project-ref>.supabase.co/auth/v1/callback
     ```
   *(Note: This URI is displayed in your Supabase Dashboard under Authentication > Providers > Google).*
7. Click **Create**.
8. Copy the generated:
   - **Client ID** (e.g., `1234567890-abcdefg.apps.googleusercontent.com`)
   - **Client Secret** (e.g., `GOCSPX-xxxxxxxxxxxxxxxxxxxxxxxx`)

---

## 3. Security Warning
- **Never commit the Google Client Secret to Git.**
- **Never put Google Client Secret into frontend environment variables.**
- The Client Secret must be configured **only** in the Supabase Dashboard.
