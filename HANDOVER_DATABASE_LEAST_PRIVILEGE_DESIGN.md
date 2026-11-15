# THE HANDOVER — DATABASE LEAST-PRIVILEGE SECURITY DESIGN PROPOSAL (REVISED M4.1.3)

**Project:** The Handover — Intelligent Project Knowledge Reconstruction & Handover Platform  
**Document Type:** Architecture & Security Design Review Artifact (STRICTLY NON-EXECUTED PROPOSAL)  
**Milestones Covered:** M4.1.2 & M4.1.3  
**Target Environment:** Supabase PostgreSQL 15+ (Sydney, Australia: `ap-southeast-2`)  
**Status:** DRAFT PROPOSAL FOR ARCHITECTURAL REVIEW ONLY — ZERO DATABASE CHANGES EXECUTED  

---

## 1. CURRENT PRIVILEGE MODEL & THREAT ANALYSIS

### 1.1 Current Connection Configuration
The platform's backend application (FastAPI on Render) and local worker (`CompositeWorkerService`) currently connect to Supabase PostgreSQL using:
- **Connection Role:** `postgres` (or `postgres.<project-ref>`)
- **Port:** `5432` (Supabase Session Pooler via Supavisor)
- **Database Catalog Attributes:**
  - `rolsuper`: `true` (Superuser / platform administrator)
  - `rolbypassrls`: `true` (Absolute bypass of Row Level Security)
  - **Table Ownership:** Owner of all 61 public application base tables and sequences.

### 1.2 The Fundamental Security Problem
1. **The Absolute Precedence of `BYPASSRLS`:**
   In PostgreSQL, the `BYPASSRLS` attribute is evaluated at the server engine level prior to policy qualification. PostgreSQL documentation explicitly states:
   > *"FORCE ROW LEVEL SECURITY: This causes row security policies to be applied to table owners. (Normal users are always subject to row security anyway.) **Note that this does NOT affect superusers, nor does it affect roles with the BYPASSRLS attribute.**"*
2. **Current Defense-in-Depth Posture:**
   - In Milestone M3 / Phase B, migration `20261113_0016_rls_hardening.py` enabled RLS across all 61 public base tables with **zero permissive policies** for `anon` and `authenticated`.
   - This successfully and completely neutralized data exposure through Supabase's auto-generated PostgREST HTTP APIs (`https://<ref>.supabase.co/rest/v1/*`), ensuring direct HTTP queries return 0 rows.
   - However, for direct SQLAlchemy connections over TCP port 5432, because the connecting role is `postgres` (`BYPASSRLS=true`), PostgreSQL evaluates **zero RLS policies**.
3. **Threat Vector:**
   - If an application code defect or raw SQL query inadvertently omits `WHERE project_id = :project_id` or `WHERE organisation_id = :organisation_id`, the database engine will not block cross-tenant data retrieval.
   - Any SQL injection vulnerability could compromise the entire database instance because the connection role holds superuser DDL and DML privileges.

---

## 2. RLS COMPATIBILITY & DIRECT SQL CONSTRAINTS

### 2.1 The Supabase Auth vs. Direct SQLAlchemy Disconnect
In standard Supabase architectures, RLS policies rely heavily on built-in JWT claim functions:
- `auth.uid()`: Resolves `current_setting('request.jwt.claim.sub', true)::uuid`
- `auth.jwt()`: Returns the full parsed JWT claims JSON object

**Crucial Technical Finding:**
When connecting via direct SQLAlchemy (`postgresql+psycopg://...`), **no HTTP request headers or Supabase JWT claims exist in the PostgreSQL connection session**. Therefore:
- Standard Supabase RLS policies written with `auth.uid()` evaluate to `NULL` for direct SQL connections.
- If a role with `NOBYPASSRLS` connects without session variables, every query targeting `auth.uid()` will return 0 rows or fail.

### 2.2 Parameterized SQL & `SET LOCAL` Syntax Requirements
In PostgreSQL, `SET LOCAL parameter = $1` is **invalid syntax**; the SQL standard `SET` statement does not support bind parameters.  
Instead, the correct, robust, parameterizable, and injection-safe mechanism is to invoke the native PostgreSQL function:
```sql
SELECT set_config('app.current_user_id', :val, true);
```
Setting the third argument `is_local = true` ensures that the setting is scoped **strictly to the current transaction** and is automatically discarded on `COMMIT` or `ROLLBACK`.

### 2.3 Limitations of Custom Application-Settable GUCs
Using custom settings like `app.current_user_id` is an application-mediated defense-in-depth pattern:
- The database engine enforces row filtering according to the GUC values provided.
- **However**, the identity is still asserted by the application layer (the backend FastAPI process), which must authenticate the user and issue the `set_config` call.
- It protects against accidental cross-tenant queries, missing WHERE clauses, and ORM leakage, but does not substitute for application-level authentication.

---

## 3. SEPARATION OF ROLES: `handover_api` VS. `handover_worker`

To satisfy both web request isolation and asynchronous background job processing, privileges must be partitioned into two distinct application roles:

```text
┌────────────────────────────────────────────────────────────────────────┐
│                          SUPABASE POSTGRESQL                           │
│                                                                        │
│  1. Role: postgres (rolbypassrls = true)                               │
│     - Owns all tables, types, triggers, sequences                      │
│     - Runs Alembic DDL migrations only                                 │
│                                                                        │
│  2. Role: handover_api (rolbypassrls = false)                          │
│     - Used by: FastAPI Web Backend (Render)                            │
│     - SELECT, INSERT, UPDATE, DELETE on tenant data                    │
│     - Zero DDL permissions                                             │
│     - Bound strictly by transaction-scoped RLS policies                │
│                                                                        │
│  3. Role: handover_worker (rolbypassrls = false, elevated queue DML)   │
│     - Used by: CompositeWorkerService (Local Laptop Background Worker) │
│     - Global access to background_jobs, sync_jobs, audit_logs          │
│     - Can claim multi-tenant jobs using SKIP LOCKED                    │
│     - Sets transaction context dynamically per claimed job             │
│                                                                        │
│  4. Roles: anon / authenticated (PostgREST HTTP API)                   │
│     - Explicit default-deny: 0 rows accessible                         │
└────────────────────────────────────────────────────────────────────────┘
```

### 3.1 Role & Privilege Comparison Matrix

| Database Role | Login? | Bypass RLS? | Allowed Schemas | Table Permissions | DDL Permissions | Intended Component |
|:---|:---:|:---:|:---|:---|:---|:---|
| `postgres` | Yes | **YES** | `public`, `auth`, `storage`, `app` | ALL PRIVILEGES (Table Owner) | Full DDL (CREATE, ALTER, DROP) | Alembic Migrations & Disaster Recovery |
| `handover_api` | Yes | **NO** | `public`, `app` | `SELECT, INSERT, UPDATE, DELETE` on public base tables; `USAGE, SELECT` on sequences | **NONE** (Zero DDL permissions) | FastAPI Web Backend (Render) |
| `handover_worker` | Yes | **NO** | `public`, `app` | `SELECT, INSERT, UPDATE, DELETE` on public base tables; `USAGE, SELECT` on sequences | **NONE** (Zero DDL permissions) | Local Worker (`CompositeWorkerService`) |
| `anon` | No direct TCP | **NO** | `public` | None (Default Deny) | None | PostgREST (Blocked) |
| `authenticated`| No direct TCP | **NO** | `public` | None (Default Deny) | None | PostgREST (Blocked) |

---

## 4. TENANT SCOPE CLASSIFICATION ACROSS ALL 61 PUBLIC TABLES

All 61 public application base tables are categorized into 4 tenant isolation tiers:

| Tier | Tenant Scope | Description | Table Names |
|:---|:---|:---|:---|
| **Tier 1** | **Global / Shared Reference** | Tables containing global configuration, system settings, or cross-cutting metadata. | `alembic_version`, `system_settings`, `feature_flags`, `integration_types`, `audit_logs` |
| **Tier 2** | **Organisation-Scoped** | Entities belonging directly to an organisation; accessible by organisation members. | `organisations`, `organisation_memberships`, `oauth_connections`, `oauth_states`, `credential_storage` |
| **Tier 3** | **Project-Scoped** | Core domain knowledge, evidence, and transfer records belonging to a specific project. | `projects`, `project_members`, `evidence_items`, `documents`, `extracted_items`, `relationships`, `conflicts`, `verifications`, `handover_packages`, `handover_revisions`, `handover_approvals`, `handover_acknowledgements`, `vector_sync_states`, `inference_audit_logs` |
| **Tier 4** | **User-Scoped / Session** | Private user data, credentials, and refresh tokens. | `users`, `refresh_sessions`, `password_reset_tokens`, `user_notification_preferences` |
| **Tier 5** | **Queue / Worker Coordination** | Asynchronous task and synchronization job tables. | `background_jobs`, `sync_jobs`, `pipeline_runs`, `dead_letter_queue` |

---

## 5. POLICY MATRIX ACROSS THE 61 PUBLIC TABLES

### 5.1 Tier 1: Global / System Tables
- **`handover_api`:** Read-only (`SELECT`) on system settings; `INSERT` on `audit_logs`.
- **`handover_worker`:** Read-only (`SELECT`) on system settings; `INSERT` on `audit_logs`.
- **Policy Pattern:**
  ```sql
  CREATE POLICY audit_logs_insert_policy ON public.audit_logs
      FOR INSERT TO handover_api, handover_worker WITH CHECK (true);
  CREATE POLICY audit_logs_select_policy ON public.audit_logs
      FOR SELECT TO handover_api, handover_worker USING (
          organisation_id = app.current_organisation_id()
          OR app.current_is_admin() = true
      );
  ```

### 5.2 Tier 2: Organisation-Scoped Tables
- **`handover_api`:** Filtered by `organisation_id = app.current_organisation_id()`.
- **Policy Pattern:**
  ```sql
  CREATE POLICY organisation_tenant_isolation ON public.organisations
      FOR ALL TO handover_api
      USING (id = app.current_organisation_id())
      WITH CHECK (id = app.current_organisation_id());
  ```

### 5.3 Tier 3: Project-Scoped Tables
- **`handover_api`:** Filtered by `project_id = app.current_project_id() AND organisation_id = app.current_organisation_id()`.
- **Policy Pattern:**
  ```sql
  CREATE POLICY evidence_items_tenant_isolation ON public.evidence_items
      FOR ALL TO handover_api
      USING (
          project_id = app.current_project_id()
          AND (organisation_id = app.current_organisation_id() OR organisation_id IS NULL)
      )
      WITH CHECK (
          project_id = app.current_project_id()
          AND (organisation_id = app.current_organisation_id() OR organisation_id IS NULL)
      );
  ```

### 5.4 Tier 4: User-Scoped Tables
- **`handover_api`:** Users can read and update their own record; password hashes and reset tokens restricted.
- **Policy Pattern:**
  ```sql
  CREATE POLICY refresh_sessions_user_isolation ON public.refresh_sessions
      FOR ALL TO handover_api
      USING (user_id = app.current_user_id())
      WITH CHECK (user_id = app.current_user_id());
  ```

### 5.5 Tier 5: Background Jobs & Worker Queue Claiming
Background workers claim jobs across multiple projects without pre-existing tenant context:
- In SQL:
  ```sql
  SELECT * FROM public.background_jobs
  WHERE status = 'queued' AND scheduled_at <= NOW()
  ORDER BY priority DESC, created_at ASC
  LIMIT 1
  FOR UPDATE SKIP LOCKED;
  ```
- **Policy Strategy for `background_jobs`:**
  - For `handover_api`: Can only view/cancel jobs where `project_id = app.current_project_id()`.
  - For `handover_worker`: Granted a dedicated bypass policy on `background_jobs` and `sync_jobs`:
    ```sql
    CREATE POLICY worker_queue_claim_policy ON public.background_jobs
        FOR ALL TO handover_worker
        USING (true)
        WITH CHECK (true);
    ```
  - Once `handover_worker` claims a job, it inspects `job.project_id` and calls `SELECT app.set_tenant_context(:user_id, :org_id, :proj_id)` before processing domain tables.

---

## 6. TENANT CONTEXT HELPER FUNCTIONS & POOLING SAFETY

### 6.1 Schema & Function Definitions
We establish a dedicated non-public schema `app` to hold tenant context functions.

```sql
CREATE SCHEMA IF NOT EXISTS app;
GRANT USAGE ON SCHEMA app TO handover_api, handover_worker;

CREATE OR REPLACE FUNCTION app.current_user_id() RETURNS uuid AS $$
    SELECT NULLIF(current_setting('app.current_user_id', true), '')::uuid;
$$ LANGUAGE sql STABLE SECURITY DEFINER;

CREATE OR REPLACE FUNCTION app.current_organisation_id() RETURNS uuid AS $$
    SELECT NULLIF(current_setting('app.current_organisation_id', true), '')::uuid;
$$ LANGUAGE sql STABLE SECURITY DEFINER;

CREATE OR REPLACE FUNCTION app.current_project_id() RETURNS uuid AS $$
    SELECT NULLIF(current_setting('app.current_project_id', true), '')::uuid;
$$ LANGUAGE sql STABLE SECURITY DEFINER;

CREATE OR REPLACE FUNCTION app.current_is_admin() RETURNS boolean AS $$
    SELECT COALESCE(NULLIF(current_setting('app.current_is_admin', true), '')::boolean, false);
$$ LANGUAGE sql STABLE SECURITY DEFINER;
```

### 6.2 Application Context Setup via SQLAlchemy
At the beginning of each database transaction (e.g., via FastAPI dependency or SQLAlchemy event):

```python
from sqlalchemy import event, text
from sqlalchemy.orm import Session

def set_db_tenant_context(session: Session, user_id: str | None, org_id: str | None, project_id: str | None, is_admin: bool = False):
    """Set transaction-scoped GUCs via parameterized set_config."""
    connection = session.connection()
    if user_id:
        connection.execute(text("SELECT set_config('app.current_user_id', :val, true)"), {"val": str(user_id)})
    if org_id:
        connection.execute(text("SELECT set_config('app.current_organisation_id', :val, true)"), {"val": str(org_id)})
    if project_id:
        connection.execute(text("SELECT set_config('app.current_project_id', :val, true)"), {"val": str(project_id)})
    connection.execute(text("SELECT set_config('app.current_is_admin', :val, true)"), {"val": "true" if is_admin else "false"})
```

**Connection Pooling Guarantee:**
Because `is_local = true` is passed to `set_config()`, PostgreSQL automatically restores the settings to default when the transaction is committed or rolled back. No state bleeds into subsequent transactions pooled by Supavisor.

---

## 7. MIGRATION & DEFAULT PRIVILEGE STRATEGY

### 7.1 Owner vs. Runtime Role
- All database objects are created and owned by `postgres` (the migration owner).
- `handover_api` and `handover_worker` are strictly runtime execution roles.
- `ALTER DEFAULT PRIVILEGES` must be executed by `postgres` so that future tables created by Alembic automatically grant DML privileges to the runtime roles.

### 7.2 Non-Executed Draft Migration Script

> [!CAUTION]
> **DO NOT EXECUTE.** This SQL script is provided for architecture review only. Modifying live roles requires scheduled maintenance and pooler credential coordination. No passwords or secrets are embedded.

```sql
-- ============================================================================
-- DRAFT SPECIFICATION: 0018_least_privilege_runtime_roles.sql
-- ============================================================================

-- 1. Create app context schema
CREATE SCHEMA IF NOT EXISTS app;

-- 2. Create roles (passwords injected via environment variables)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'handover_api') THEN
        CREATE ROLE handover_api WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS INHERIT;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'handover_worker') THEN
        CREATE ROLE handover_worker WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS INHERIT;
    END IF;
END $$;

-- 3. Schema Usage Grants
GRANT USAGE ON SCHEMA public TO handover_api, handover_worker;
GRANT USAGE ON SCHEMA app TO handover_api, handover_worker;

-- 4. DML Table Permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO handover_api, handover_worker;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO handover_api, handover_worker;

-- 5. Default Privileges for future Alembic migrations run as postgres
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO handover_api, handover_worker;

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO handover_api, handover_worker;

-- 6. Revoke Administrative & System Schemas
REVOKE CREATE ON SCHEMA public FROM handover_api, handover_worker;
REVOKE ALL PRIVILEGES ON SCHEMA auth FROM handover_api, handover_worker;
REVOKE ALL PRIVILEGES ON SCHEMA storage FROM handover_api, handover_worker;
```

---

## 8. ROLLBACK & DISASTER RECOVERY PLAN

If any permission error, pooler stall, or query regression occurs after deploying these roles:

1. **Instant Application Rollback (< 30 seconds):**
   - Revert Render environment variable `DATABASE_URL` back to the existing `postgres` connection string.
   - Restart the Render web service.
   - Revert local worker environment variable `DATABASE_URL` back to `postgres`.
   - Result: Immediate restoration of full operational capability.
2. **Database Catalog Reversion:**
   Run the following cleanup script as `postgres`:
   ```sql
   ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ALL ON TABLES FROM handover_api, handover_worker;
   ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ALL ON SEQUENCES FROM handover_api, handover_worker;
   REVOKE ALL ON ALL TABLES IN SCHEMA public FROM handover_api, handover_worker;
   REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM handover_api, handover_worker;
   REVOKE USAGE ON SCHEMA public, app FROM handover_api, handover_worker;
   DROP SCHEMA IF EXISTS app CASCADE;
   DROP ROLE IF EXISTS handover_api;
   DROP ROLE IF EXISTS handover_worker;
   ```

---

## 9. EXPLICIT APPROVAL REQUIREMENTS

Before executing this design in any future phase:
- [ ] Benchmarking `set_config` transaction overhead under simulated Render request concurrency.
- [ ] Comprehensive verification of `handover_worker` claiming multi-tenant jobs via `SKIP LOCKED`.
- [ ] Verification of Alembic migrations running as `postgres` against existing databases.
- [ ] Formal user sign-off to provision roles and issue passwords in Supabase.
