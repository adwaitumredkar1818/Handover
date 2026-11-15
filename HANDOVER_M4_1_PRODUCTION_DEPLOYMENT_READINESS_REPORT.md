# THE HANDOVER — M4.1 PRODUCTION DEPLOYMENT READINESS AUDIT REPORT

**Project:** The Handover — Intelligent Project Knowledge Reconstruction & Handover Platform  
**Phase:** M4.1  
**Execution Mode:** STRICT READ-ONLY AUDIT  
**Deployment Target:** Vercel (Frontend) & Render (Backend)  
**Database/Auth/Storage:** Supabase (Sydney, Australia: `ap-southeast-2`)  
**Inference Architecture:** Local GPU Inference Gateway (Windows Developer Laptop)  
**Domain Policy:** Platform-provided URLs only (No custom domain purchased)  
**Audit Date:** November 15, 2026  

---

## 1. EXECUTIVE SUMMARY

An exhaustive, non-destructive, read-only audit of the entire codebase and infrastructure configuration was conducted for Milestone M4.1. The system architecture strictly adheres to the established design:
- **Frontend:** Next.js 16.4.6 with React 19 and Turbopack targeted for Vercel.
- **Backend:** FastAPI (Python 3.11, SQLAlchemy 2.1, Psycopg 3) targeted for Render Web Service.
- **Data, Auth & Storage:** Supabase PostgreSQL (Session Pooler port 5432), Supabase Auth (Google OAuth & password reset token exchange), and Supabase Storage private encrypted bucket (`project-evidence`).
- **Inference & Vector Store:** Local Windows laptop hosting Ollama (`qwen3:8b`, `glm-ocr`, `nomic-embed-text`), ChromaDB v2 HTTP, and Redis coordination, bridged via a local FastAPI Inference Gateway (`127.0.0.1:8002`) with Cloudflare Tunnel & Access headers supported in settings.

### Summary of Audit Outcome
- **Vercel Readiness:** **90%** (Clean TypeScript validation, successful production build `npm run build` with 66 routes optimized; however, production build configuration in `next.config.ts` currently has `typescript.ignoreBuildErrors: true` and a hardcoded local rewrite rule to `http://127.0.0.1:8000/api/v1/:path*` which must be corrected before deploying to Vercel).
- **Render Readiness:** **75%** (Code structure, Uvicorn lifespan, graceful shutdown, health endpoints, and database connection pooling are well-engineered; however, the deployment blueprint `render.yaml` is absent, and the backend relies on Ollama & ChromaDB directly in `deps.py` for embeddings and vector search unless specifically refactored or guarded).
- **Worker Architecture:** **CRITICAL FINDING**. The background worker (`app.worker.py`) is designed as a direct local execution process on the developer's laptop. It directly imports `OllamaEmbeddingService`, `ChromaV2HttpVectorStore`, `OllamaLLMClient`, `OllamaGLMOCRService`, and local `RedisConnectionManager`. **Under no circumstances should this worker process be launched on Render.** Doing so would cause fatal startup crashes or attempted connections to localhost GPU services that do not exist in the Render container.
- **Database Role & Security Blocker:** **CRITICAL BLOCKER (P0)**. The backend and worker connect using the Supabase `postgres` superuser/admin role (`BYPASSRLS=true`). While PostgreSQL migration `0016_rls_hardening` enabled RLS across all 61 public tables to neutralize PostgREST exposure for `anon` and `authenticated` roles, the backend's direct SQL connection operates completely outside PostgreSQL RLS. Tenant isolation depends 100% on application-level filtering in SQLAlchemy repositories.

---

## 2. READINESS SCORE & SCORING METHODOLOGY

### Scoring Formula
The deployment readiness score is calculated as a weighted composite across 6 key architectural dimensions:
$$\text{Score} = \sum (\text{Weight}_i \times \text{Dimension Score}_i)$$

| Dimension | Weight | Score | Weighted | Key Justification |
|:---|:---:|:---:|:---:|:---|
| **1. Frontend Build & Vercel Compatibility** | 20% | 88/100 | 17.6 | Turbopack build succeeds (66 pages); SSR Auth callback implemented; must strip `typescript.ignoreBuildErrors: true` and remove dev rewrite in `next.config.ts`. |
| **2. Backend Runtime & Render Compatibility** | 20% | 75/100 | 15.0 | FastAPI lifespan, health endpoints, graceful shutdown, and CORS are robust; missing `render.yaml` declarative specification; embedding/vector endpoints in `deps.py` need remote isolation. |
| **3. Database, RLS & Storage Integrity** | 25% | 70/100 | 17.5 | Supabase session pooler on port 5432 verified; RLS enabled on all tables; storage envelope encryption verified; **docked due to `postgres` BYPASSRLS connection role**. |
| **4. Worker & Inference Gateway Isolation** | 20% | 85/100 | 17.0 | `InferenceGatewayClient` and `GatewayLLMClient` unit and integration tests passed (51/51 in 2.2s); worker correctly bounded to developer laptop. |
| **5. Environment & Secret Governance** | 10% | 80/100 | 8.0 | Exhaustive templates prepared; no exposed secrets in client JavaScript; missing production deployment inventory. |
| **6. Git & Working Tree Preservation** | 5% | 90/100 | 4.5 | Uncommitted working tree intact; zero destructive actions taken; all pending modifications cataloged. |
| **COMPOSITE READINESS SCORE** | **100%** | — | **79.6%** | **PROCEED CONDITIONALLY AFTER RESOLVING P0/P1 ITEMS** |

---

## 3. AUDIT A — VERCEL FRONTEND READINESS

### A. Framework and Build Characteristics
- **Next.js Version:** `16.4.6` (Turbopack enabled)
- **React Version:** `19.3.0` (`react`, `react-dom`)
- **Package Manager:** `npm` (with `package-lock.json` present)
- **Node.js Compatibility:** Compatible with Node.js 20.x and 22.x (Vercel standard)
- **TypeScript Typecheck:** Verified via `node ./node_modules/next/dist/bin/next typegen && node ./node_modules/typescript/bin/tsc --noEmit`. Exited with code `0`.
- **Production Build:** Verified via `node ./node_modules/next/dist/bin/next build`. Compiled successfully in 3.1s; 66 routes generated statically (○), partial prerendered (◐), or dynamic server functions (ƒ).
- **Static vs Dynamic Distribution:**
  - Dynamic Server Function (ƒ): `/auth/callback` (OAuth code exchange route handler).
  - Partial Prerender (◐): Dynamic workspaces under `/projects/[id]/*` and `/handovers/[id]/*`.
  - Static Pages (○): Dashboard, Overview, Team, Evidence, Intelligence, Settings, etc.

### B. Environment Configuration & Secrets Exposure
- **Public Variables Inspected:**
  1. `NEXT_PUBLIC_API_BASE_URL`: Base URL for FastAPI backend. In `frontend/src/lib/api.ts` line 21, falls back to `http://127.0.0.1:8000/api/v1` during SSR if unset.
  2. `NEXT_PUBLIC_SUPABASE_URL`: Supabase project URL (`https://rjntmboskzyrsqcetzil.supabase.co`).
  3. `NEXT_PUBLIC_SUPABASE_ANON_KEY`: Supabase public publishable key. Safe for browser exposure.
  4. `NEXT_PUBLIC_ENABLE_AGENTATION`: Dev tool flag. Disabled in production (`process.env.NODE_ENV !== "development"` guard in `AgentationToolbar.tsx` line 17).
- **Secret Leaks in Client Code:** **Zero**. No `SUPABASE_SERVICE_ROLE_KEY`, `JWT_SECRET_KEY`, `DATABASE_URL`, or encryption keys are referenced or bundled into frontend JavaScript.

### C. Critical Frontend Build & Runtime Hazards Identified
1. **`typescript.ignoreBuildErrors: true` in `next.config.ts` (Line 6):**
   - *Hazard:* Masking build errors can allow subtle type regressions into production. Although `npm run typecheck` passed cleanly, production Vercel builds should enforce standard compilation.
2. **Hardcoded Development Rewrite in `next.config.ts` (Lines 8–15):**
   - *Code:*
     ```typescript
     async rewrites() {
       return [
         {
           source: "/api/v1/:path*",
           destination: "http://127.0.0.1:8000/api/v1/:path*",
         },
       ];
     }
     ```
   - *Hazard:* In Vercel production, client browser requests to `/api/v1/*` will attempt to rewrite to `http://127.0.0.1:8000` inside the Vercel serverless environment, resulting in instant `500/502 Connection Refused` errors.
   - *Required Fix:* In production, `NEXT_PUBLIC_API_BASE_URL` should point to the Render backend domain (e.g. `https://the-handover-api.onrender.com/api/v1`), and client fetches must target that absolute URL (or use environment-conditional rewrites).
3. **Client-Side vs Server-Side Routing in `api.ts` (Lines 18–21):**
   - *Code:*
     ```typescript
     const API_BASE_URL =
       typeof window !== "undefined"
         ? "/api/v1"
         : (process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000/api/v1");
     ```
   - *Hazard:* On client browsers (`typeof window !== "undefined"`), `API_BASE_URL` is set to the relative path `"/api/v1"`. Because Vercel and Render are hosted on separate origins (e.g. `https://the-handover.vercel.app` vs `https://the-handover-api.onrender.com`), relative calls to `/api/v1` will fail unless Next.js explicitly proxies all `/api/v1/*` requests to the Render backend.
   - *Recommendation:* Configure `next.config.ts` rewrites dynamically based on `BACKEND_INTERNAL_URL` or set `API_BASE_URL` directly to `process.env.NEXT_PUBLIC_API_BASE_URL`.

### D. Authentication & Security
- **OAuth Callback Flow:** `frontend/src/app/auth/callback/route.ts` safely handles Google OAuth redirection, validates URL parameters, validates relative redirects to prevent open-redirect vulnerabilities (`safeNext`), exchanges authorization codes for sessions via Supabase SSR, and returns cleanly to `/login` with descriptive errors if the exchange fails.
- **XSS & Content Sanitization:** No instances of `dangerouslySetInnerHTML` were found in `frontend/src`.
- **Session Refresh:** `LiveAppContext.tsx` implements background token refresh, intercepts `handover:session-expired` events, and maintains active state synchronization.

---

## 4. AUDIT B — RENDER BACKEND READINESS

### A. Runtime Configuration & Entrypoint
- **Runtime:** Python 3.11.9
- **Entrypoint:** `backend/app/main.py:app`
- **Dependencies:** `backend/requirements.txt` compiled cleanly via `uv` from `pyproject.toml`. Includes `fastapi==0.162.4`, `uvicorn==0.54.0`, `sqlalchemy==2.1.8`, `psycopg==3.3.8`, `pydantic==2.14.3`, `cryptography==50.0.2`, `pyjwt==2.15.1`.
- **Recommended Render Start Command:**
  ```bash
  uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 2 --proxy-headers --forwarded-allow-ips='*'
  ```
- **Lifespan Management:** Verified in `_build_lifespan` in `app/main.py`:
  - Logs application startup.
  - Initializes database engine, connection pool, and verifies connectivity (`verify_database_connection`).
  - Sets up shared `httpx.AsyncClient` and `httpx.Client`.
  - Gracefully handles SIGTERM/shutdown by closing HTTP clients, flushing Redis/memory managers, and disposing of SQLAlchemy engine pools (`engine.dispose()`).
- **Health Endpoints:**
  - `GET /health`: Lightweight, zero-dependency liveness probe returning HTTP 200. Perfect for Render health checks.
  - `GET /health/ready`: Dependency-aware probe verifying PostgreSQL connection. Returns HTTP 503 if PostgreSQL is unavailable.

### B. Database Connection & Supabase Session Pooler
- **Driver:** `psycopg` (v3) with binary wheels.
- **Pooler Architecture:** Configured for Supabase AWS Sydney Session Pooler on port `5432`:
  - `aws-1-ap-southeast-2.pooler.supabase.com:5432`
  - Uses `NullPool` or bounded `QueuePool` with `max_overflow=0`, `pool_pre_ping=True`, and `pool_recycle=300`.
  - Explicitly adheres to architecture rule: **Never switch to transaction pooler on port 6543** (preserves prepared statements and advisory locks).
- **SSL Mode:** `POSTGRES_SSL_MODE=require` enforced.

### C. Authentication & Authorization
- **FastAPI-Managed JWT Platform Identity:** Argon2id password hashing, short-lived JWT access tokens (15 minutes), SHA-256 `RefreshSession` rotation stored in `HttpOnly`, `SameSite=None`, `Secure` cookies.
- **Supabase Google OAuth Exchange:** `POST /api/v1/auth/supabase-token-exchange` verifies Supabase JWTs against JWKS endpoint (`https://rjntmboskzyrsqcetzil.supabase.co/auth/v1/.well-known/jwks.json`) and issues platform session tokens with automatic account creation/linking.
- **Tenant Isolation:** Enforced at the application repository layer via mandatory `project_id` and `organisation_id` filters in all queries.

### D. CORS and Security Headers
- **CORS Configuration:** Enforced via FastAPI `CORSMiddleware`.
  - Configurable via `CORS_ALLOWED_ORIGINS` (comma-separated list).
  - Credentials allowed (`allow_credentials=True`).
  - Strict method allowlist: `GET, POST, PUT, PATCH, DELETE, OPTIONS`.
  - Header allowlist: `Authorization, Content-Type, X-Request-ID, X-Correlation-ID`.
  - Wildcard `*` origins are strictly blocked when credentials are enabled.

### E. Inference Gateway Integration
- **Client Implementation:** Verified in `backend/app/services/inference_gateway.py`.
- **LLM Adapter:** `GatewayLLMClient` in `backend/app/services/llm.py` cleanly maps chat completions to the gateway.
- **Fail-Closed Semantics:** When `INFERENCE_GATEWAY_ENABLED=true`, if the gateway is unreachable or unconfigured, the system raises `InferenceGatewayClientError(GATEWAY_NOT_INITIALIZED)`. **No silent cloud fallback exists.**
- **Integration Tests:** 51 unified tests in `test_gateway_llm_adapter.py` and `test_inference_gateway_integration.py` passed with 100% success.

---

## 5. AUDIT C — SUPABASE PRODUCTION READINESS

### A. Database State & Configuration
- **Region:** Sydney, Australia (`ap-southeast-2`, project reference `rjntmboskzyrsqcetzil`).
- **Connection Host:** `aws-1-ap-southeast-2.pooler.supabase.com:5432`.
- **Migration Status:** 17 Alembic migration versions present in `infrastructure/database/migrations/versions`:
  - Latest migration: `20261115_0017_password_reset_tokens.py` (Revises `0016_rls_hardening`).
  - Migration `0016_rls_hardening` enabled RLS across all 61 public tables.
  - Migration `0017_password_reset_tokens` also explicitly enables RLS on the newly added `password_reset_tokens` table.

### B. Storage Buckets & Policies
- **Bucket:** `project-evidence` (Private bucket).
- **Backend Access:** Backend uses server-only `SUPABASE_SERVICE_ROLE_KEY` with AES-256-GCM envelope encryption at rest (`FILE_ENCRYPTION_KEY`).
- **Download Security:** No public URLs or signed client URLs are generated. All document downloads are backend-mediated and streamed via authenticated API routes after checking project membership and source ACLs.

### C. Known Security Issue: `postgres` Superuser Role (`BYPASSRLS=true`)
- **Investigation:**
  - The SQLAlchemy engine in `app/db/session.py` connects with username `postgres.rjntmboskzyrsqcetzil`.
  - In PostgreSQL, the `postgres` role owns the tables and holds `rolbypassrls = true`.
  - As established in architectural audit `docs/engineering-audit/phase-b2/phase-b2-1-rls-corrections.md`, PostgreSQL skips all RLS policy evaluations for roles with `BYPASSRLS=true`, regardless of `FORCE ROW LEVEL SECURITY`.
  - Migration `0016_rls_hardening` deliberately created **zero permissive policies** for `anon` and `authenticated`. This successfully neutralized data leakage through Supabase's automatic PostgREST HTTP APIs (`https://<ref>.supabase.co/rest/v1/*`), ensuring public/anon queries return 0 rows.
  - However, for any backend or worker query executed over SQLAlchemy, **PostgreSQL RLS provides zero isolation**.
  - **Risk Assessment:** If an application bug omits `WHERE project_id = :project_id`, cross-tenant data will be returned.
  - **Verdict:** Must remain classified as a production security concern with formal verification of repository-layer isolation before high-consequence enterprise deployment.

---

## 6. AUDIT D — WORKER DEPLOYMENT STRATEGY & ISOLATION

### Inspection of `backend/app/worker.py`
The background worker is structured as a `CompositeWorkerService` polling 5 queues sequentially:
1. `IngestionWorkerService` (Document OCR, text extraction, page parsing).
2. `SourceSyncWorkerService` (GitHub, Jira, Slack polling and sync).
3. `IndexingWorkerService` (Chunking, vector embedding, ChromaDB indexing).
4. `ReconstructionWorkerService` (Qwen3 8B knowledge extraction).
5. `RelationshipWorkerService` (Knowledge graph and dependency linking).

### Direct Local Dependencies in Worker
Inspecting lines 226–333 of `app/worker.py` reveals:
```python
ocr_service = OllamaGLMOCRService(base_url=settings.ollama.base_url, ...)
embedding_service = OllamaEmbeddingService(base_url=settings.ollama.base_url, ...)
vector_store = ChromaV2HttpVectorStore(base_url=settings.chroma.base_url, ...)
llm_client = OllamaLLMClient(base_url=settings.ollama.base_url, ...)
```

### Architectural Verdict
- **Worker Execution Location:** **Developer's Windows Laptop ONLY.**
- **Consequences of running worker on Render:**
  - Render has no GPU, no Ollama runtime, no local ChromaDB instance, and no Redis daemon.
  - If a background worker is started on Render, it will immediately fail or crash attempting to connect to `127.0.0.1:11434` or `127.0.0.1:8001`.
  - Even if configured with the remote gateway URL, the worker would compete with itself and does not currently use `GatewayLLMClient`.
- **Durable Offline Behavior:**
  - When the developer's laptop is closed or offline, jobs dispatched by users (e.g. document uploads, sync triggers, reconstruction requests) remain safely queued in PostgreSQL in `status = 'queued'` with durable payload data.
  - When the developer starts the local worker process (`python -m app.worker`), the worker immediately claims pending jobs using `FOR UPDATE SKIP LOCKED` and processes them sequentially.
  - The Render cloud backend remains 100% available for viewing existing evidence, reviewing findings, generating handovers, and chatting (via gateway when laptop is active, or returning clean error state when inactive).

---

## 7. AUDIT E — ENVIRONMENT VARIABLES & SECRET INVENTORY

| Variable | Component | Required | Secret | Production Value Source | Current Status | Deployment Destination |
|:---|:---|:---:|:---:|:---|:---:|:---|
| `NEXT_PUBLIC_API_BASE_URL` | Frontend | Yes | No | Render Backend URL (`https://<app>.onrender.com/api/v1`) | Needs Render domain | Vercel |
| `NEXT_PUBLIC_SUPABASE_URL` | Frontend | Yes | No | Supabase Project URL (`https://rjntmboskzyrsqcetzil.supabase.co`) | Present | Vercel |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Frontend | Yes | No | Supabase Dashboard (Anon Public Key) | Present in `.env.local` | Vercel |
| `NEXT_PUBLIC_ENABLE_AGENTATION` | Frontend | No | No | Fixed `false` | Present (`false`) | Vercel |
| `APP_ENV` | Backend | Yes | No | Fixed `production` | Set in template | Render |
| `LOG_LEVEL` | Backend | Yes | No | `INFO` | Set in template | Render |
| `BACKEND_HOST` | Backend | Yes | No | `0.0.0.0` | Set in template | Render |
| `BACKEND_PORT` | Backend | Yes | No | Supplied automatically by Render (`$PORT`) | Render managed | Render |
| `CORS_ALLOWED_ORIGINS` | Backend | Yes | No | Vercel domain (`https://<project>.vercel.app`) | Needs Vercel domain | Render |
| `DATABASE_URL` | Backend | Yes | **YES** | Supabase Session Pooler (port 5432) URL | Present in `.env` | Render |
| `POSTGRES_SSL_MODE` | Backend | Yes | No | `require` | Set in template | Render |
| `JWT_SECRET_KEY` | Backend | Yes | **YES** | Cryptographically generated 32-byte secret | Present in `.env` | Render |
| `TOKEN_ENCRYPTION_KEY` | Backend | Yes | **YES** | Cryptographically generated 32-byte Fernet key | Present in `.env` | Render |
| `FILE_ENCRYPTION_KEY` | Backend | Yes | **YES** | Cryptographically generated 32-byte key | Present in `.env` | Render |
| `COOKIE_SECURE` | Backend | Yes | No | `true` (HTTPS cross-site) | Set in template | Render |
| `COOKIE_SAMESITE` | Backend | Yes | No | `none` (Required for cross-site Vercel/Render) | Set in template | Render |
| `SUPABASE_AUTH_ENABLED` | Backend | Yes | No | `true` | Set in template | Render |
| `SUPABASE_AUTH_URL` | Backend | Yes | No | `https://rjntmboskzyrsqcetzil.supabase.co` | Present | Render |
| `SUPABASE_AUTH_JWKS_URL` | Backend | Yes | No | `.../auth/v1/.well-known/jwks.json` | Present | Render |
| `STORAGE_PROVIDER` | Backend | Yes | No | `supabase_storage` | Set in template | Render |
| `SUPABASE_URL` | Backend | Yes | No | `https://rjntmboskzyrsqcetzil.supabase.co` | Present | Render |
| `SUPABASE_SERVICE_ROLE_KEY` | Backend | Yes | **YES** | Supabase Dashboard Service Role Secret | Present in `.env` | Render |
| `SUPABASE_STORAGE_BUCKET` | Backend | Yes | No | `project-evidence` | Present | Render |
| `INFERENCE_GATEWAY_ENABLED` | Backend | Yes | No | `false` initially; `true` when tunnel active | Set in template | Render |
| `INFERENCE_GATEWAY_BASE_URL` | Backend | If GW | No | Cloudflare Tunnel URL | Deferred | Render |
| `INFERENCE_GATEWAY_TOKEN` | Backend | If GW | **YES** | Shared Bearer token | Rotated in M3.3.7 | Render & Gateway |
| `CF_ACCESS_CLIENT_ID` | Backend | If GW | **YES** | Cloudflare Access Service Token | Deferred | Render |
| `CF_ACCESS_CLIENT_SECRET` | Backend | If GW | **YES** | Cloudflare Access Service Token Secret | Deferred | Render |
| `CF_ACCESS_ALLOWED_HOST` | Backend | If GW | No | Cloudflare Tunnel Hostname | Deferred | Render |
| `REDIS_ENABLED` | Backend | Yes | No | `false` on Render | Set in template | Render |

---

## 8. AUDIT F — DEPLOYMENT COSTS & PLATFORM LIMITATIONS

### A. Vercel (Frontend)
- **Plan:** Hobby (Free tier)
- **Limits:**
  - Bandwidth: 100 GB/month.
  - Serverless Function Execution: 10s default execution timeout.
  - Builds: 6,000 build minutes/month (ample for this project).
- **Cold Starts:** Not applicable to static assets; serverless API routes (`/auth/callback`) warm up in < 300ms.
- **Suitability:** **100% suitable** for The Handover frontend.

### B. Render (Backend)
- **Plan Options:**
  1. *Free Web Service ($0/mo):*
     - **Limitation:** Spins down after 15 minutes of inactivity. Cold start delay is **50–70 seconds**.
     - **Limitation:** 512 MB RAM limit. Python 3.11 with SQLAlchemy, FastAPI, and Pydantic will operate near 180–250 MB RAM, which is within the limit, but cold starts severely degrade UX during authentication redirects.
     - **Outbound Bandwidth:** 100 GB/month included.
  2. *Starter Web Service ($7/mo):*
     - No spin-down (always on). 512 MB RAM, 0.5 CPU. Instant API responses.
- **Audit Recommendation:**
  - For initial staging/verification under M4, Render Free Web Service is technically capable of running the API, provided users anticipate the initial 60s wake-up spin-up.
  - Zero paid subscriptions are authorized without explicit approval.

### C. Supabase (Database, Auth, Storage)
- **Plan:** Free Tier (Sydney `ap-southeast-2`)
- **Limits:**
  - Database: 500 MB (current usage < 25 MB).
  - Storage: 1 GB (current encrypted evidence files < 50 MB).
  - Monthly Active Users (Auth): 50,000.
  - Inactivity: Pauses after 7 days of zero database activity. Active API usage prevents pausing.
- **Suitability:** **100% suitable**.

---

## 9. AUDIT G — GIT & REPOSITORY PRESERVATION REPORT

A strict read-only audit of Git status confirmed that the repository is completely clean of destructive operations:
- **Current Branch:** `main` (Up to date with `origin/main`).
- **HEAD Commit:** `350b9ba feat(validation): implement Conflicts & Contradictions workspace and automated detection engine` (Sun Nov 15 03:24:30 2026 +0530).
- **Tracked Modifications in Working Tree:** 33 modified files across frontend and backend (e.g. Supabase auth routes, Figma pages, verification components).
- **Untracked Milestone Reports & Utilities:** All Milestone reports (M3.3.2 through M4.0.1) and testing scripts preserved untouched.
- **Zero Discarded Work:** No commits, resets, stashes, or file overwrites occurred during this audit.

---

## 10. AUDIT H — END-TO-END GAP ANALYSIS & REMEDIATION MATRIX

| Level | Issue & Location | Why It Matters | Required Remediation | Dependencies | DB Change? | Approval Required? |
|:---:|:---|:---|:---|:---:|:---:|:---:|
| **P0** | **Database Role BYPASSRLS Connection**<br>`backend/app/db/session.py` | Connection as `postgres` bypasses PostgreSQL RLS. Multi-tenant isolation rests entirely on application query filters. | Formulate dedicated least-privilege role strategy (e.g. `handover_app` with `NOBYPASSRLS`) or formalize repository-level verification suite. | Supabase user privileges | Yes (Future) | **YES** |
| **P1** | **Hardcoded Dev Rewrite in Next.js**<br>`frontend/next.config.ts:8-15` | Rewrites `/api/v1/*` to `127.0.0.1:8000`. On Vercel, this causes instant `502 Bad Gateway` for all client API calls. | Replace with dynamic environment proxy or remove rewrite in favor of direct cross-origin calls to Render. | Vercel domain | No | No |
| **P1** | **Frontend Client `api.ts` Relative URL**<br>`frontend/src/lib/api.ts:18-21` | Client browser sets `API_BASE_URL = "/api/v1"`. When frontend is on Vercel and backend is on Render, relative calls will fail. | Ensure `NEXT_PUBLIC_API_BASE_URL` is used consistently across browser and SSR fetches. | Vercel & Render URLs | No | No |
| **P1** | **`typescript.ignoreBuildErrors: true`**<br>`frontend/next.config.ts:5-7` | Masks TypeScript compilation issues during Vercel builds. | Remove `ignoreBuildErrors: true` to enforce strict type checking on Vercel. | None | No | No |
| **P1** | **Render Declarative Configuration Missing**<br>`render.yaml` | Without `render.yaml`, manual configuration of build commands, start commands, and environment variables on Render is error-prone. | Create production `render.yaml` defining Web Service, Python 3.11, start command, and health check path `/health`. | None | No | No |
| **P1** | **Cross-Site Cookie Configuration**<br>`backend/app/core/config.py` | Cross-origin authentication (Vercel frontend calling Render backend) requires `SameSite=None` and `Secure=true`. | Ensure `COOKIE_SECURE=true` and `COOKIE_SAMESITE=none` are explicitly set in Render environment. | Render HTTPS | No | No |
| **P2** | **Worker Accidental Launch Prevention**<br>`backend/app/worker.py` | If a worker service is accidentally configured on Render, it will crash attempting to reach Ollama on localhost. | Add environment guard `FAIL_ON_MISSING_LOCAL_AI=true` or prevent worker entrypoint from booting if running in cloud `APP_ENV=production`. | None | No | No |
| **P2** | **Hybrid Retrieval Fallback on Cloud Backend**<br>`backend/app/api/deps.py:312-364` | `HybridRetrievalService` in backend API currently directly instantiates `OllamaEmbeddingService` and `ChromaV2HttpVectorStore`. | Wrap embedding & vector retrieval behind gateway client or graceful empty fallback when gateway is inactive. | Gateway | No | No |
| **P3** | **Render Free Tier Spin-Down Mitigation** | 50–70s cold start on Render free tier causes user sign-in timeouts on first morning load. | Implement graceful loading state / retry logic in frontend `LiveAppContext` when backend is waking up. | None | No | No |

---

## 11. RECOMMENDED DEPLOYMENT SEQUENCE

When authorized to proceed to Milestone M4.2, the deployment must follow this strict sequence:

```text
PHASE 1: PRE-FLIGHT CODE REMEDIATION (Local Repo)
  1. Fix frontend/next.config.ts (remove hardcoded 127.0.0.1 rewrite, remove ignoreBuildErrors).
  2. Standardize frontend/src/lib/api.ts API_BASE_URL resolution.
  3. Author infrastructure/render.yaml declarative service definition.
  4. Verify local git working tree remains clean and fully tested.

PHASE 2: RENDER BACKEND DEPLOYMENT
  1. Create Render Web Service linked to repository (Python 3.11).
  2. Configure Environment Variables from documentation/deployment/render.env.example.
  3. Deploy FastAPI backend service.
  4. Verify liveness at https://<render-subdomain>.onrender.com/health.
  5. Verify database readiness at https://<render-subdomain>.onrender.com/health/ready.
  6. Record canonical backend URL: https://<render-subdomain>.onrender.com.

PHASE 3: VERCEL FRONTEND DEPLOYMENT
  1. Create Vercel Project linked to frontend directory.
  2. Set NEXT_PUBLIC_API_BASE_URL to https://<render-subdomain>.onrender.com/api/v1.
  3. Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY.
  4. Trigger initial Vercel production build.
  5. Record canonical frontend URL: https://<vercel-subdomain>.vercel.app.

PHASE 4: CROSS-ORIGIN SECURITY & AUTH HANDSHAKE
  1. Update Render backend CORS_ALLOWED_ORIGINS with https://<vercel-subdomain>.vercel.app.
  2. Add https://<vercel-subdomain>.vercel.app/auth/callback to Supabase Redirect URLs in Supabase Dashboard.
  3. Conduct end-to-end verification: Email sign-in, Google OAuth, project creation, document upload.
```

---

## 12. QUESTIONS & DECISIONS REQUIRING USER APPROVAL

Before deploying, user approval is required on the following:
1. **Render Service Tier:** Do you approve using Render's **Free Tier** (with the understanding that the first request after 15 minutes of inactivity will experience a ~60s cold start spin-up)?
2. **Database Role Remediation Strategy:** Do you approve keeping the current Supabase `postgres` connection for initial staging deployment (mitigated by strict repository query filtering and PostgREST neutralization), while scheduling a dedicated non-superuser role (`handover_app`) for a post-deployment security update?
3. **Frontend API Routing Strategy:** Do you approve updating `frontend/src/lib/api.ts` to connect directly to the Render backend origin (`https://<render-app>.onrender.com/api/v1`) with CORS credentials, rather than proxying through Next.js rewrites?
