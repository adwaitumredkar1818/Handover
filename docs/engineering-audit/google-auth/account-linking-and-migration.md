# Account Linking, Resolution & Database Migration Analysis

## Overview
This document evaluates the database schema, migration history, and identity resolution policy for linking Supabase Google identities with existing Handover user records.

---

## 1. Migration Inspection
- **Migration 0009**:
  - File: `infrastructure/database/migrations/versions/20261113_0009_supabase_auth_and_vector_indexes.py`
  - Already executed and verified in test baseline.
  - Adds nullable column `users.supabase_auth_id` (VARCHAR 128) with unique index `ix_users_supabase_auth_id`.
  - Alters `users.password_hash` to be nullable (`nullable=True`), accommodating pure-OAuth users.
- **ORM Model Alignment**:
  - `backend/app/models/user.py` maps `supabase_auth_id` with `unique=True`, `index=True`, `nullable=True`.
- **Verdict**:
  - **No new Alembic migrations or schema changes are needed.**
  - Zero duplicate tables, zero duplicate columns.

---

## 2. Identity Resolution Cases

### Case A: Existing Linked Account
- **Scenario**: User authenticates with Google, and their `sub` matches an existing `users.supabase_auth_id`.
- **Behavior**: Authenticate the user directly. Update `last_login_at`. Issue standard Handover session.

### Case B: Existing Unlinked Account (Safe Auto-Linking)
- **Scenario**: An existing Handover user registered previously with email `developer@company.org`. They now sign in with Google using that same email.
- **Safety Gate**:
  - The incoming Google email MUST be confirmed (`is_email_verified=True`).
  - If unconfirmed, linking is strictly rejected (`UNVERIFIED_EMAIL`, 401).
  - If confirmed, set `user.supabase_auth_id = sub` and mark `user.is_email_verified = True`.
  - Security audit log records `auth.supabase.link`.

### Case C: New Google User
- **Scenario**: Neither `supabase_auth_id` nor `email` exists in PostgreSQL.
- **Behavior**:
  - Create user record with `password_hash = None`, `supabase_auth_id = sub`, `is_email_verified = True`.
  - Assign default platform role (`standard_user`).
  - Do NOT grant organisation or project access.
  - Security audit log records `auth.supabase.register`.

### Case D: Identity Conflict (Account Takeover Prevention)
- **Scenario**: A Google token has `sub = X` and `email = userB@example.com`, but `sub = X` is already linked to User A.
- **Behavior**:
  - Reject with 409 Conflict (`IDENTITY_CONFLICT`).
  - Emit security audit alert.
  - Never merge accounts automatically.
