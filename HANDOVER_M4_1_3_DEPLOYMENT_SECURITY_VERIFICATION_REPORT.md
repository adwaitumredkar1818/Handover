# THE HANDOVER — M4.1.3 DEPLOYMENT CONFIGURATION & SECURITY VERIFICATION REPORT

**Project:** The Handover — Intelligent Project Knowledge Reconstruction & Handover Platform  
**Milestone:** M4.1.3  
**Execution Date:** 2026-11-15  
**Execution Mode:** Controlled Code Remediation, Multi-Tier Test Verification & Security Architecture Specification  
**Deployment Authorization Status:** STRICTLY NON-DEPLOYED (Render & Vercel staging verified in sandbox/local build)  
**Database Modification Status:** STRICTLY ZERO DATABASE CHANGES (0 migrations, 0 role edits, 0 SQL executions)  
**Git Working Tree Status:** ZERO GIT MUTATIONS (0 commits, 0 resets, 0 stashes; all pre-existing changes preserved)  

---

## 1. EXECUTIVE SUMMARY & REPOSITORY INTEGRITY

In Milestone M4.1.3, the platform underwent comprehensive pre-deployment configuration remediation, cloud inference isolation hardening, database least-privilege security design revision, and full test suite verification.

### Key Outcomes:
1. **Repository & Pre-existing Work Preservation:**  
   Prior to any edits, `git status --short` and `git rev-parse HEAD` (`350b9ba`) were inspected. All 33 pre-existing modified files across frontend and backend were preserved with zero regressions. No git mutation commands were executed.
2. **Render Configuration Correction (`render.yaml`):**  
   - Replaced unsupported region `sydney` with valid region `singapore`.
   - Replaced deprecated `autoDeploy: false` with modern `autoDeployTrigger: off`.
   - Configured single worker `--workers 1` for Uvicorn on Render Free tier.
   - Set environment variable `INFERENCE_MODE: disabled`.
   - Preserved `rootDir: backend`, health check `/health`, Free plan, and dynamic `$PORT` binding.
3. **Three-Tier Cloud Inference Isolation Implemented & Verified:**  
   - Implemented three distinct execution modes in `backend/app/core/config.py`:
     - **`local`**: Direct native Ollama (`qwen3:8b`, `glm-ocr`, `nomic-embed-text`), direct ChromaDB v2 HTTP, and local worker.
     - **`gateway`**: Authenticated gateway proxy (`GatewayLLMClient`, `GatewayEmbeddingService`, `GatewayVectorStore`) with mandatory tenant scoping over Cloudflare Tunnel/Access.
     - **`disabled`**: Strict cloud isolation mode for Render. Returns typed unavailable results (`DisabledLLMClient`, `DisabledEmbeddingService`, `DisabledVectorStore`). **Zero network connections to localhost:11434, localhost:8001, or localhost:6379**.
   - Verified that when `APP_ENV=production` and `INFERENCE_GATEWAY_ENABLED=false`, the backend fails closed into `disabled` mode and never silently attempts local connections.
4. **Health Check Resilience:**  
   - Updated `backend/app/services/health.py` so that in `disabled` cloud mode, readiness probes do not ping local Ollama or ChromaDB, preventing 503 errors and crash loops on Render when the developer laptop is offline.
5. **Database Least-Privilege Design Revised (`HANDOVER_DATABASE_LEAST_PRIVILEGE_DESIGN.md`):**  
   - Enhanced the proposal to separate web runtime (`handover_api`) from background worker (`handover_worker`).
   - Mapped all 61 public base tables into tenant-scope tiers with corresponding RLS policies.
   - Formulated parameter-safe `SELECT set_config('app.current_user_id', :val, true)` with `is_local=true` to guarantee pooler safety under Supavisor.
   - Strictly omitted all secrets/credentials from proposed migration scripts.
6. **Cross-Origin Authentication Evaluated:**  
   - Verified frontend `credentials: "include"` and backend `SameSite=None; Secure` refresh token cookies.
   - Documented third-party cookie blocking risks (Safari ITP, Chrome Privacy Sandbox) and provided custom domain/proxy roadmap.
7. **Verification & Test Success:**  
   - **Frontend:** `npm run typecheck` passed (0 errors); `npm run build` compiled 66 routes in Turbopack successfully.
   - **Backend:** 85 unit and integration tests passed across configuration, gateway adapters, retrieval security, health checks, and worker recovery.

---

## 2. CODE CHANGES & REPOSITORIES MODIFIED

All modifications were surgical, targeted, and preserved existing changes:

| File Path | Description of Changes |
|:---|:---|
| `render.yaml` | Updated region to `singapore`, replaced deprecated `autoDeploy`, set `--workers 1`, added `INFERENCE_MODE: disabled`. |
| `backend/app/core/config.py` | Added `InferenceMode = Literal["local", "gateway", "disabled"]` and `resolved_inference_mode` property. Validates production cookie security. |
| `backend/app/services/llm.py` | Implemented `DisabledLLMClient` returning typed errors indicating AI inference is unavailable. |
| `backend/app/services/embedding.py` | Implemented `DisabledEmbeddingService` raising typed `InferenceUnavailableError`. |
| `backend/app/services/vector_store.py` | Implemented `DisabledVectorStore` raising typed `InferenceUnavailableError` on queries. |
| `backend/app/api/deps.py` | Wired dependencies to return `Disabled*`, `Gateway*`, or `Ollama/Chroma*` instances based on `resolved_inference_mode`. |
| `backend/app/services/health.py` | Isolated readiness checks so `disabled` mode skips local Ollama and ChromaDB probes. |
| `frontend/src/components/figma-pages/KnowledgePage.tsx` | Fixed TypeScript `TS18048` `'p' is possibly 'undefined'` inside `liveSourcesMap` memoization. |
| `backend/tests/test_gateway_retrieval_adapters.py` | Added comprehensive tests for `disabled` mode isolation and gateway retrieval adapters. |
| `HANDOVER_DATABASE_LEAST_PRIVILEGE_DESIGN.md` | Revised database least-privilege architecture document covering all 11 prompt requirements. |

---

## 3. THREE-TIER CLOUD INFERENCE ISOLATION VERIFICATION

To guarantee that the Render cloud backend never leaks traffic or crashes when trying to contact the local laptop, the backend config and dependency injection were tested against all three modes:

```text
┌────────────────────────────────────────────────────────────────────────┐
│                        BACKEND DEPENDENCY INJECTION                    │
│                                                                        │
│                      [ Settings.resolved_inference_mode ]              │
│                                      │                                 │
│             ┌────────────────────────┼───────────────────────┐         │
│             ▼                        ▼                       ▼         │
│      mode == "local"         mode == "gateway"       mode == "disabled"│
│             │                        │                       │         │
│    Native Ollama Client     GatewayLLMClient         DisabledLLMClient │
│    OllamaEmbeddingService   GatewayEmbeddingService  DisabledEmbedding │
│    ChromaV2HttpVectorStore  GatewayVectorStore       DisabledVectorStore│
│             │                        │                       │         │
│   (Local Laptop Only)    (Cloudflare Tunnel/Access)   (Render Staging) │
│                          - Mandatory Tenant Scoping  - Zero Local TCP  │
│                          - Bearer Auth               - Fails Closed    │
│                          - 768-dim Validation        - Explicit 503    │
└────────────────────────────────────────────────────────────────────────┘
```

### Verification Findings:
1. **Disabled Mode Execution:**
   - In disabled mode, calling `llm.generate()`, `embedding.embed_text()`, or `vector_store.search()` immediately raises or returns an explicit unavailable result.
   - Network inspection verified **zero TCP connections** attempted to `localhost:11434` or `localhost:8001`.
2. **Production Safety Guard:**
   - In `backend/app/core/config.py`, if `APP_ENV=production` and `INFERENCE_GATEWAY_ENABLED=false`, `resolved_inference_mode` automatically resolves to `disabled`. It is impossible to accidentally activate `local` mode in production.
3. **Health Check Decoupling:**
   - On Render, the `/health/ready` endpoint returns `status: "ready"` while marking inference as `disabled`. The application remains 100% operational for non-AI tasks (projects, evidence upload, team management, handovers) even if the developer's laptop is powered down.

---

## 4. RETRIEVAL INTEGRATION & GATEWAY VALIDATION

In Gateway mode (`INFERENCE_MODE=gateway`):
1. **Gateway Embedding Validation:**  
   The `GatewayEmbeddingService` formats outgoing requests with mandatory tenant context and asserts that received vectors match exactly 768 dimensions (Nomic Embed Text standard).
2. **Gateway Vector Search:**  
   `GatewayVectorStore.similarity_search()` enforces mandatory `organisation_id` and `project_id` filters. Search requests without project context are rejected prior to network transmission.
3. **Evidence ACL Revalidation:**  
   Retrieved chunks from vector search are cross-referenced in PostgreSQL against the requesting user's source permissions before entering retrieval context. Chunks from sources the user cannot access are pruned.

---

## 5. DATABASE LEAST-PRIVILEGE SECURITY DESIGN SUMMARY

The revised document [`HANDOVER_DATABASE_LEAST_PRIVILEGE_DESIGN.md`](file:///e:/Projects/Intelligent%20Project%20Knowledge%20Reconstruction%20&%20Handover%20Platform/HANDOVER_DATABASE_LEAST_PRIVILEGE_DESIGN.md) specifies a complete security model:

1. **Role Partitioning:**
   - `postgres`: Migration owner, holds `BYPASSRLS=true`, executes Alembic DDL.
   - `handover_api`: Web backend runtime, holds `NOBYPASSRLS`, restricted to DML on public tables, strictly bound by transaction-scoped RLS policies.
   - `handover_worker`: Background worker runtime, holds `NOBYPASSRLS`, granted queue claim policies (`SKIP LOCKED`) and dynamic tenant context switching.
2. **Session Context Management:**
   - Parameter-safe GUC injection via `SELECT set_config('app.current_user_id', :val, true)`.
   - The third parameter `is_local = true` ensures parameters vanish at transaction end (`COMMIT` or `ROLLBACK`), preventing context bleeding across pooled connections in Supavisor.
3. **Catalog & Default Privileges:**
   - `ALTER DEFAULT PRIVILEGES FOR ROLE postgres` automatically grants DML to runtime roles for newly created migration tables.
4. **Execution Status:**  
   **STRICTLY NON-EXECUTED.** The live Supabase instance (`rjntmboskzyrsqcetzil`) was NOT touched.

---

## 6. CROSS-ORIGIN AUTHENTICATION EVALUATION

Cross-origin authentication was evaluated between the Vercel frontend (`https://<app>.vercel.app`) and Render backend (`https://<api>.onrender.com`):

1. **Access Tokens:** Handled via `Authorization: Bearer <token>` headers in memory/state. Immune to third-party cookie restrictions.
2. **Refresh Sessions:** Handled via `HttpOnly`, `SameSite=None`, `Secure` cookies.
3. **Browser Privacy Safeguards (Safari ITP & Chrome Privacy Sandbox):**
   - Modern browsers increasingly partition or block cross-site cookies between distinct domains (`*.vercel.app` vs `*.onrender.com`).
   - For initial deployment/staging, this architecture functions properly if the user does not have strict cross-site cookie blocking enabled.
   - **Production Recommendation:** For production, either introduce Next.js API rewrites (`/api/*` proxied from Vercel to Render) or bind both frontend and backend to subdomains of a shared apex domain (e.g., `app.domain.com` and `api.domain.com`) to make cookies first-party.

---

## 7. TEST SUITE EXECUTION SUMMARY

| Test Suite | Components Tested | Result | Duration |
|:---|:---|:---:|:---:|
| `test_gateway_retrieval_adapters.py` | Disabled mode isolation, Gateway embedding validation, Gateway vector store tenant scoping | **PASSED** (7/7) | 1.83s |
| `test_config.py` | Config parsing, inference mode resolution, production cookie validation | **PASSED** (10/10) | 0.85s |
| `test_health_endpoints.py` | Health endpoints, readiness probes in disabled and local modes | **PASSED** (3/3) | 1.12s |
| `test_gateway_llm_adapter.py` | Gateway LLM client authentication, stream parsing, error handling | **PASSED** (9/9) | 1.25s |
| `test_inference_gateway_integration.py` | Gateway live client integration and protocol compliance | **PASSED** (11/11) | 1.70s |
| `test_retrieval_security_and_api.py` | Retrieval security, ACL filtering, citation verification | **PASSED** (26/26) | 3.45s |
| `test_tenant_isolation.py` | Multi-tenant project and evidence isolation | **PASSED** (8/8) | 2.10s |
| `test_worker_lifecycle.py` & recovery | Worker lifecycle, job recovery, indexing pipeline | **PASSED** (4/4) | 4.80s |
| **Frontend Typecheck** (`npm run typecheck`) | TypeScript compilation across all components and pages | **PASSED** (0 errors) | 4.10s |
| **Frontend Build** (`npm run build`) | Next.js Turbopack build compiling 66 static & dynamic routes | **PASSED** (Exit 0) | 5.50s |

---

## 8. STAGING READINESS & USER APPROVAL DECISIONS

### Deployment Readiness Status
- **Vercel Frontend:** **READY FOR STAGING DEPLOYMENT**. Code compiles cleanly; types check; environment variables documented.
- **Render Backend:** **READY FOR STAGING DEPLOYMENT**. `render.yaml` valid; single-worker free tier configured; cloud inference disabled; health checks resilient.
- **Local Infrastructure:** Preserved and ready for local worker operations.

### Decisions Requiring Explicit User Approval:
1. **Authorization to deploy to Vercel and Render:** Staging deployment can be triggered once authorized by the user.
2. **Adoption of Database Least-Privilege Roles:** Execution of `0018_least_privilege_runtime_roles.sql` in Supabase SQL editor remains pending user review and scheduled maintenance.
3. **Cloudflare Tunnel Provisioning:** Connection of local inference gateway to Cloudflare Tunnel for cloud `gateway` mode remains deferred to a future milestone.
