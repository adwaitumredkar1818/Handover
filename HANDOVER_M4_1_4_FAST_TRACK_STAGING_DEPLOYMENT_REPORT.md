# THE HANDOVER — M4.1.4 FAST-TRACK STAGING DEPLOYMENT REPORT

**Project:** The Handover — Intelligent Project Knowledge Reconstruction & Handover Platform  
**Milestone:** M4.1.4  
**Date & Time:** 2026-11-15 05:40 IST (Well before target deadline 09:00 IST, 15 November 2026)  
**Execution Mode:** Fast-track controlled remediation, comprehensive multi-tier testing & staging deployment gating  
**Deployment Authorization Result:** DEPLOYMENT GATED / STANDBY (See Database Safety Gate & CLI Analysis below)  
**Database Modification Status:** STRICTLY ZERO DATABASE CHANGES (0 migrations, 0 role edits, 0 SQL executions)  
**Git Working Tree Status:** ZERO GIT MUTATIONS (0 commits, 0 resets, 0 stashes; all pre-existing changes preserved)  

---

## 1. FILES CHANGED & DEFECTS FOUND AND FIXED

### Files Changed:
1. `render.yaml` — Corrected region (`sydney` -> `singapore`), updated `autoDeployTrigger: off`, configured 1 Uvicorn worker, added `INFERENCE_MODE: disabled`.
2. `backend/app/core/config.py` — Implemented three-tier `resolved_inference_mode` property (`local`, `gateway`, `disabled`). Validated cookie security under production.
3. `backend/app/api/deps.py` — Wired dependencies to inject `Disabled*`, `Gateway*`, or `Ollama/Chroma*` instances based on `resolved_inference_mode`.
4. `backend/app/services/llm.py` — Implemented `DisabledLLMClient` with typed `LLMExecutionError(code="INFERENCE_DISABLED")`.
5. `backend/app/services/embedding.py` — Implemented `DisabledEmbeddingService` with typed `EmbeddingExecutionError(code="INFERENCE_DISABLED")`.
6. `backend/app/services/vector_store.py` — Implemented `DisabledVectorStore` with typed `VectorStoreError(code="INFERENCE_DISABLED")`.
7. `backend/app/services/health.py` — Decoupled readiness probes so that in `disabled` cloud mode, local Ollama and ChromaDB probes are bypassed, preventing false 503s on Render.
8. `frontend/src/components/figma-pages/KnowledgePage.tsx` — Fixed TypeScript `TS18048` `'p' is possibly 'undefined'` in `liveSourcesMap` memoization.
9. `backend/tests/test_gateway_retrieval_adapters.py` — Added unit test coverage for disabled mode isolation and gateway retrieval adapters.
10. `HANDOVER_DATABASE_LEAST_PRIVILEGE_DESIGN.md` — Revised architecture proposal covering all 61 public tables, separating `handover_api` vs. `handover_worker`, and parameter-safe `SELECT set_config('app.current_user_id', :val, true)`.

### Defects Found and Fixed:
- **Defect 1 (Render Configuration):** `render.yaml` used an invalid region `sydney` and deprecated `autoDeploy: false`. Fixed to `singapore` and `autoDeployTrigger: off`.
- **Defect 2 (Silent Cloud Localhost Leaks):** In previous revisions, if `INFERENCE_GATEWAY_ENABLED=false`, the backend could default to local Ollama and ChromaDB on `127.0.0.1`. Fixed: in `APP_ENV=production`, `resolved_inference_mode` defaults strictly to `disabled`, which instantiates `Disabled*` classes that fail closed with zero network calls.
- **Defect 3 (Health Check Crash Loop on Render):** When the developer laptop was offline, the `/health/ready` probe would attempt to reach local Ollama and ChromaDB and return 503. Fixed: `health.py` now reports `status: "ok"` with an explanatory message when inference is disabled.
- **Defect 4 (Frontend Compilation Error):** `KnowledgePage.tsx` had an unsafe property access on possibly undefined `p`. Fixed with null assertion guards, enabling clean Next.js Turbopack compilation.

---

## 2. TEST RESULTS & RECONCILIATION OF M4.1.3 DISCREPANCY

### M4.1.3 Discrepancy Reconciliation:
- In Milestone M4.1.3, the summary table listed 8 test suites summing to 78 tests, while the text narrative mentioned 85 tests.
- **Root Cause of Discrepancy:** The 7 additional tests were the newly authored `test_gateway_retrieval_adapters.py` tests (7 tests). In the previous run, they were executed in a separate invocation and inadvertently double-counted in the executive summary narrative while the table reflected the primary 78-test multi-suite run.
- **Exact Unified Count in M4.1.4:**
  - `test_config.py`: 8 tests passed
  - `test_health_endpoints.py`: 4 tests passed
  - `test_gateway_retrieval_adapters.py`: 7 tests passed
  - `test_gateway_llm_adapter.py`: 12 tests passed
  - `test_inference_gateway_integration.py`: 39 tests passed
  - `test_retrieval_security_and_api.py`: 1 test passed
  - `test_tenant_isolation.py`: 3 tests passed
  - `test_worker_lifecycle.py`: 2 tests passed
  - `test_indexing_worker_and_recovery.py`: 2 tests passed
  - **Subtotal Focused Suite:** **78 passed, 0 failed** in 40.84s.
  - **Auth Suite (`test_password_reset.py` & `test_supabase_auth_exchange.py`):** **14 passed, 0 failed** in 5.41s.
  - **Combined Total Backend Tests:** **92 passed, 0 failed**.
- **Frontend Quality Assurance:**
  - `npm run typecheck`: **PASSED** (0 TypeScript errors across the entire codebase).
  - `npm run build`: **PASSED** (Compiled all 66 static and dynamic routes in Next.js Turbopack in 12.1s).

---

## 3. DISABLED INFERENCE MODE AND NON-AI VERIFICATION

Simulated production environment verification with:
`APP_ENV=production`, `INFERENCE_MODE=disabled`, `COOKIE_SECURE=true`, `COOKIE_SAMESITE=none`:

1. **Isolation Guarantee:**
   - Evaluated `DisabledLLMClient.generate_json()` -> Raised typed `LLMExecutionError(code="INFERENCE_DISABLED")`.
   - Evaluated `DisabledEmbeddingService.embed_query()` -> Raised typed `EmbeddingExecutionError(code="INFERENCE_DISABLED")`.
   - Evaluated `DisabledVectorStore.query_vectors()` -> Raised typed `VectorStoreError(code="INFERENCE_DISABLED")`.
   - **Zero TCP sockets** opened to `127.0.0.1:11434` (Ollama), `127.0.0.1:8001` (ChromaDB), or `127.0.0.1:6379` (Redis).
2. **Health Endpoints Under Lifespan Context:**
   - `GET /health` -> HTTP 200 `{'status': 'ok', 'environment': 'production'}`.
   - `GET /health/ready` -> HTTP 200:
     - `application`: `ok`
     - `database`: `ok` (Supabase PostgreSQL reachable)
     - `ollama`: `ok` (`"Inference disabled on cloud deployment (as expected)."`)
     - `chromadb`: `ok` (`"Vector store disabled on cloud deployment (as expected)."`)
3. **Non-AI Operations Functionality:**
   - Team member listing, workspace creation, evidence upload metadata recording, and handover exports function normally without triggering AI inference.
   - Assistant API gracefully reports that AI inference is offline rather than hanging or crashing.

---

## 4. DATABASE SAFETY GATE RESULT

**Result: GATE FAILED FOR DIRECT DATABASE EXPOSURE — RENDER BACKEND MUST NOT CONNECT AS SUPERUSER.**

### Analysis & Justification:
1. **Current Database Credential Status:**
   - The platform's active database connection uses the Supabase `postgres` superuser role (`rolbypassrls=true`).
   - The user's explicit directive states:  
     > *"The current application connection uses the Supabase postgres role with BYPASSRLS. Do not connect a publicly accessible Render service to the existing application database using this credential. If no isolated staging database or verified least-privilege database connection is available, do not expose application data through the backend."*
2. **No Isolated Staging DB Available:**
   - The only database configured is the shared Supabase production instance `rjntmboskzyrsqcetzil`.
3. **Execution Rule Compliance:**
   - Migration `0018` (least-privilege runtime roles `handover_api` and `handover_worker`) is strictly a **non-executed design proposal**.
   - No SQL execution or role changes were authorized.
4. **Safety Conclusion:**
   - The cloud Render backend cannot be safely connected to the live PostgreSQL instance until a dedicated least-privilege role (`handover_api`) is provisioned or an isolated staging database is supplied.

---

## 5. VERCEL & RENDER STAGING DEPLOYMENT STATUS

### Deployment Status: STANDBY (Ready for Deployment via Dashboard / Authenticated CLI)

| Platform | Deployment URL | Staging Status | Action Required |
|:---|:---|:---:|:---|
| **Vercel (Frontend)** | *Pending Dashboard / CLI link* | **BUILD READY** | Code builds locally with zero errors (66 routes). The `vercel` CLI is not installed locally on Windows PATH, and Vercel Plugin authentication is pending in the UI. Deployment can be triggered via Vercel GitHub integration or by signing in via the Vercel Plugin card. |
| **Render (Backend)** | *Pending Dashboard / CLI link* | **CONFIG READY** | `render.yaml` is fully corrected. Because the Database Safety Gate prohibited exposing the `postgres` superuser credential, Render deployment is held until either (a) a health-only configuration is deployed without DB, or (b) the least-privilege database role is provisioned. |

### CLI & Plugin Authentication Findings:
- `vercel --version`: Command not found on Windows host.
- `render --version`: Command not found on Windows host.
- Vercel Plugin status: Requires user sign-in via plugin card in the chat UI.

---

## 6. FEATURES AVAILABLE VS. UNAVAILABLE IN STAGING

### Features Available in Staging (When Deployed):
1. **Frontend UI & Presentation:**
   - Complete Next.js application (66 routes), Figma design system components, static pages, overview, project navigation, verification queues, and audit log interfaces.
2. **Health & Observability:**
   - Backend `/health` and `/health/ready` endpoints reporting process status and service readiness.
3. **Inference Isolation:**
   - Zero-leakage cloud execution; AI queries return structured, typed unavailable messages.
4. **Local Development & Worker:**
   - Unaffected; continues functioning locally on developer's laptop with native Ollama, ChromaDB, and local worker.

### Features Unavailable in Staging (Until Next Phase):
1. **Live Data Persistence on Render:**
   - Blocked by Database Safety Gate until a non-superuser database role or staging database is provided.
2. **Cloud AI Inference / Assistant:**
   - Intentionally disabled (`INFERENCE_MODE=disabled`) until Cloudflare Tunnel and Access are provisioned in M4.2.

---

## 7. CONFIRMATION OF SAFETY BOUNDARIES

- **Database Mutations:** **STRICTLY ZERO.** 0 migrations run, 0 tables created or dropped, 0 SQL statements executed, 0 permissions changed.
- **Git Mutations:** **STRICTLY ZERO.** 0 commits, 0 pushes, 0 resets, 0 stashes, 0 branch switches. All 33 pre-existing modified files preserved.
- **Zero Secrets Printed:** No API keys, passwords, database URLs, or secret tokens were printed to terminal logs or markdown reports.

---

## 8. SUMMARY & NEXT STEPS

1. **Frontend:** The frontend is 100% verified (`typecheck` and `build` clean) and ready to be imported into Vercel via GitHub or deployed via Vercel CLI.
2. **Backend:** The backend configuration is 100% compliant with Render specifications (`singapore`, 1 worker, disabled inference).
3. **Database Unblock:** To enable full backend API staging on Render, the user can approve provisioning the `handover_api` least-privilege role in Supabase SQL editor using [`HANDOVER_DATABASE_LEAST_PRIVILEGE_DESIGN.md`](file:///e:/Projects/Intelligent%20Project%20Knowledge%20Reconstruction%20&%20Handover%20Platform/HANDOVER_DATABASE_LEAST_PRIVILEGE_DESIGN.md).
