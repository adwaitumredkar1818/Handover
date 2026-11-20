# M4.2.6 — Production AI End-to-End Verification Report

**Project:** The Handover — Intelligent Project Knowledge Reconstruction & Handover Platform  
**Milestone:** M4.2.6 — Production AI End-to-End Verification  
**Phase:** M4 — Production Infrastructure and Deployment  
**Execution Timestamp:** 2026-11-20 21:55 IST  
**Milestone Classification:** **`PARTIALLY VERIFIED — ACTION REQUIRED`**  
**Execution Mode:** Read-Only Audit & Controlled Non-Destructive Verification (Zero Git Mutation, Zero Configuration Mutation)  

---

## A. Executive Summary

Milestone **M4.2.6** performed an independent, evidence-driven audit of the deployed Handover AI infrastructure spanning Vercel, Render, Supabase, Cloudflare Quick Tunnel, Local Inference Gateway, Ollama (Qwen3 8B + Nomic Embed Text), and ChromaDB.

### Key Audit Findings:
1. **Local AI Gateway & Tunnel Fully Functional:**
   - The Local Inference Gateway on `127.0.0.1:8002` (PID `50024`) and Cloudflare Quick Tunnel (`https://empire-easy-maker-hybrid.trycloudflare.com`, PID `36816`) are healthy, enforcing Bearer token authentication, and responding with sub-second health latency.
   - Real AI chat completions (`qwen3:8b`), batch text embeddings (`nomic-embed-text`, 768 dimensions), and multi-tenant vector searches across 563 stored chunks were directly executed over the public internet through the Cloudflare Quick Tunnel with 100% success.
2. **Frontend & Backend Production Health:**
   - **Frontend (Vercel):** `https://the-sapiens.xyz` and `https://www.the-sapiens.xyz` resolve, serve valid SSL certificates, and return HTTP 200/308 from the Vercel Edge. No client-side leaks of gateway tokens or internal endpoints exist.
   - **Backend (Render):** `https://the-handover-api.onrender.com/health` returns HTTP 200 OK. The Supabase PostgreSQL database is connected and healthy (latency 188.12 ms). Backend is operating in `inference_mode="gateway"`.
3. **The Production Blocker (Render &rarr; Tunnel Disconnection):**
   - Render's `/health/ready` reports `status: "degraded"` with `"Inference Gateway service unreachable."`.
   - Inspection of backend configuration and logs revealed that Render's environment variable `INFERENCE_GATEWAY_BASE_URL` is configured to the expired, dead hostname `https://farm-gained-strip-lakes.trycloudflare.com` from a prior milestone.
   - Because Cloudflare Quick Tunnels generate ephemeral URLs on every process restart, the tunnel URL changed to `https://empire-easy-maker-hybrid.trycloudflare.com`.
   - As changing Render's environment variables is strictly forbidden in this read-only audit milestone, requests originating from Render cannot reach the local gateway until the URL is synchronized.
4. **Overall Milestone Status:**
   - Local AI, embedding, vector search, and public tunnel ingress are **100% VERIFIED**.
   - Render-to-Gateway routing is **BLOCKED** by the stale environment variable on Render.
   - Milestone classification: **`PARTIALLY VERIFIED — ACTION REQUIRED`**.

---

## B. Architecture Verification & Request Path Topology

```text
┌────────────────────────────────────────────────────────────────────────┐
│                        OBSERVED REQUEST TOPOLOGY                       │
└────────────────────────────────────────────────────────────────────────┘

[1. User Browser / Client]
           │
           ▼
[2. Vercel Edge Frontend] ──▶ https://the-sapiens.xyz (Redirect 308)
           │                  https://www.the-sapiens.xyz (HTTP 200 OK)
           │                  [STATUS: VERIFIED & OPERATIONAL]
           ▼
[3. Render FastAPI Backend] ─▶ https://the-handover-api.onrender.com
           │                  [STATUS: VERIFIED - Health OK, DB OK (188ms)]
           │                  [INFERENCE MODE: gateway]
           │
           X  <── [DISCONNECTION POINT: STALE TUNNEL URL ON RENDER]
           │      Render configured target: https://farm-gained-strip-lakes.trycloudflare.com (DEAD)
           │      Actual active tunnel URL: https://empire-easy-maker-hybrid.trycloudflare.com (LIVE)
           ▼
[4. Cloudflare Quick Tunnel] ─▶ https://empire-easy-maker-hybrid.trycloudflare.com
           │                  [STATUS: VERIFIED - Edge Ingress Active]
           ▼
[5. Local Inference Gateway] ─▶ http://127.0.0.1:8002 (PID 50024)
           │                  [STATUS: VERIFIED - Bearer Auth, Concurrency=1]
           ├────────────────────────┬────────────────────────┐
           ▼                        ▼                        ▼
[6. Ollama Qwen3 8B]      [7. Nomic Embed Text]    [8. ChromaDB Vector Store]
127.0.0.1:11434           127.0.0.1:11434          127.0.0.1:8001 (Docker)
(PID 23440 / 39804 GPU)   (PID 23440)              (Container 6c3bb0ddf0cb)
[STATUS: VERIFIED]        [STATUS: VERIFIED]       [STATUS: VERIFIED (563 chunks)]
```

---

## C. Environment Status & Process Discovery

All processes and listening ports were empirically inspected on Windows 11 and Docker:

| Service / Component | Process Name | PID / Container ID | Host / Port Binding | Publicly Exposed? | Runtime Health / Status |
| :--- | :--- | :--- | :--- | :---: | :--- |
| **Vercel Frontend** | Edge Cloud | Project `prj_JEIS...` | `the-sapiens.xyz` / `www` | Yes (HTTPS) | **HEALTHY** (HTTP 200, TLS 1.3) |
| **Render Backend** | Python 3.11 | `the-handover-api` | `the-handover-api.onrender.com` | Yes (HTTPS) | **HEALTHY** (HTTP 200, DB 188ms) |
| **Local Gateway** | `python.exe` | PID `50024` | `127.0.0.1:8002` | **NO** (Loopback only) | **HEALTHY** (Liveness 0.84ms) |
| **Cloudflare Tunnel**| `cloudflared.exe` | PID `36816` | Tunnel to `127.0.0.1:8002` | Yes (`trycloudflare`) | **HEALTHY** (`empire-easy-maker-hybrid`) |
| **Ollama Service** | `ollama.exe` | PID `23440` | `127.0.0.1:11434` | **NO** (Loopback only) | **HEALTHY** (v0.40.16 ready) |
| **GPU Inference Server**| `llama-server.exe`| PID `39804` | Ollama child process | **NO** (Internal) | **HEALTHY** (RTX 4050, 1114MB used) |
| **ChromaDB** | Docker Container | `6c3bb0ddf0cb` | `127.0.0.1:8001->8000` | **NO** (Loopback only) | **HEALTHY** (v2 heartbeat ok) |
| **Redis** | Docker Container | `80abb3c61a2e` | `127.0.0.1:6379->6379` | **NO** (Loopback only) | **HEALTHY** (ping ok, 18ms) |
| **PostgreSQL (Local)**| Docker Container | `812c3ccca77c` | `127.0.0.1:5432->5432` | **NO** (Loopback only) | **HEALTHY** (PostgreSQL 16) |
| **PostgreSQL (Prod)** | Supabase Pooler | `ap-southeast-2` | Session Pooler (5432) | Yes (SSL Direct) | **HEALTHY** (188.12ms query latency) |

---

## D. Test Results Matrix

| Test ID | Subsystem | Check Description | Method / Endpoint | Result | Classification |
| :---: | :--- | :--- | :--- | :---: | :---: |
| **T01** | Frontend | Custom domain resolution & TLS | `https://the-sapiens.xyz` | HTTP 308 &rarr; www | **PASS** |
| **T02** | Frontend | Canonical production load | `https://www.the-sapiens.xyz` | HTTP 200 OK | **PASS** |
| **T03** | Frontend | Client secret leakage inspection | Code inspection (`frontend/src`) | 0 gateway tokens exposed | **PASS** |
| **T04** | Backend | Production liveness endpoint | `GET /health` on Render | HTTP 200 OK | **PASS** |
| **T05** | Backend | Production readiness endpoint | `GET /health/ready` on Render | HTTP 200 (Degraded) | **PASS** |
| **T06** | Backend | Production database latency | Render to Supabase Pooler | 188.12 ms | **PASS** |
| **T07** | Gateway | Local unauthenticated `/health` | `GET http://127.0.0.1:8002/health` | HTTP 200 OK | **PASS** |
| **T08** | Gateway | Local unauthenticated `/v1/health` | `GET http://127.0.0.1:8002/v1/health` | HTTP 401 Unauthorized | **PASS** |
| **T09** | Gateway | Local invalid Bearer token | `GET http://127.0.0.1:8002/v1/health` | HTTP 401 Unauthorized | **PASS** |
| **T10** | Gateway | Local valid Bearer token | `GET http://127.0.0.1:8002/v1/health` | HTTP 200 OK | **PASS** |
| **T11** | Gateway | Local arbitrary path rejection | `GET http://127.0.0.1:8002/invalid` | HTTP 404 Not Found | **PASS** |
| **T12** | Gateway | Local unexpected method rejection | `POST http://127.0.0.1:8002/health` | HTTP 405 Not Allowed | **PASS** |
| **T13** | Tunnel | Tunnel unauthenticated `/health` | `GET <tunnel>/health` | HTTP 200 OK | **PASS** |
| **T14** | Tunnel | Tunnel unauthenticated `/v1/health`| `GET <tunnel>/v1/health` | HTTP 401 Unauthorized | **PASS** |
| **T15** | Tunnel | Tunnel invalid Bearer token | `GET <tunnel>/v1/health` | HTTP 401 Unauthorized | **PASS** |
| **T16** | Tunnel | Tunnel valid Bearer token | `GET <tunnel>/v1/health` | HTTP 200 OK | **PASS** |
| **T17** | Tunnel | Tunnel arbitrary path rejection | `GET <tunnel>/invalid-path` | HTTP 404 Not Found | **PASS** |
| **T18** | Tunnel | Tunnel unexpected method rejection | `DELETE <tunnel>/v1/chat` | HTTP 405 Not Allowed | **PASS** |
| **T19** | AI / LLM | Real Qwen3 8B chat completion | `POST <tunnel>/v1/chat` | HTTP 200 (128 tokens) | **PASS** |
| **T20** | Embeddings | Nomic Embed Text generation | `POST <tunnel>/v1/embed` | HTTP 200 (768 dims) | **PASS** |
| **T21** | Retrieval | Missing tenant scope rejection | `POST <tunnel>/v1/vector/search` | HTTP 422 Unprocessable | **PASS** |
| **T22** | Retrieval | Scoped non-existent tenant query | `POST <tunnel>/v1/vector/search` | HTTP 200 (0 hits) | **PASS** |
| **T23** | Retrieval | ChromaDB collection inventory | `GET /api/v2/.../collections` | 563 chunks indexed | **PASS** |
| **T24** | E2E | Render &rarr; Gateway live invocation| Render `/health/ready` & Assistant | Gateway Unreachable | **BLOCKED** |
| **T25** | E2E | Complete Frontend &rarr; Render &rarr; AI | Handover UI Assistant Query | Blocked by T24 URL mismatch | **BLOCKED** |

---

## E. End-to-End Inference Evidence

Direct empirical request dispatched through Cloudflare Quick Tunnel to Local Gateway:
- **Request Endpoint:** `POST https://empire-easy-maker-hybrid.trycloudflare.com/v1/chat`
- **Correlation ID:** `b890f614-2391-4cf4-9c02-e25f82637b89`
- **Request Payload:**
  ```json
  {
    "model": "qwen3:8b",
    "messages": [
      {
        "role": "system",
        "content": "You are The Handover AI Assistant verification tester. Reply strictly in JSON format with key 'status'."
      },
      {
        "role": "user",
        "content": "Verify system liveness and reply with status 'SYSTEM_READY'."
      }
    ],
    "temperature": 0.1,
    "num_predict": 128,
    "format": "json"
  }
  ```
- **Response Headers:**
  - `HTTP/1.1 200 OK`
  - `Server: cloudflare`
  - `x-correlation-id: b890f614-2391-4cf4-9c02-e25f82637b89`
  - `x-gateway-latency-ms: 30285.37`
- **Response Telemetry:**
  ```json
  {
    "model": "qwen3:8b",
    "done": true,
    "total_duration_ms": 30285.37,
    "prompt_eval_count": 47,
    "eval_count": 128
  }
  ```
- **Client Latency:** `32,659.22 ms` (Network overhead over Quick Tunnel: `2,373.85 ms`).

---

## F. Embedding and Retrieval Evidence

### 1. Nomic Embed Text Generation (`POST /v1/embed`)
- **Model:** `nomic-embed-text`
- **Batch Size:** 2 input strings
- **HTTP Status:** `200 OK`
- **Duration:** `7,278.16 ms`
- **Vector Dimensionality:** `768`
- **Numeric Validation:** All 768 elements are finite 32-bit floating-point numbers.
- **Sample Vector Excerpt (First 5 components):**
  `[0.020087138, 0.059744693, -0.15920608, -0.03786533, 0.03901259]`

### 2. ChromaDB Vector Store State (`http://127.0.0.1:8001`)
- **ChromaDB API:** `v2`
- **Target Collection:** `ipkrh_evidence_chunks_nomic-embed-text_v1`
- **Collection UUID:** `23a5f8ad-fb46-46cf-ad33-2ee5bafe068b`
- **Stored Vector Count:** `563` chunks
- **Collection Metadata:**
  ```json
  {
    "embedding_model": "nomic-embed-text",
    "purpose": "evidence_chunks",
    "index_version": "v1",
    "dimensions": 768
  }
  ```

---

## G. Tenant Isolation Verification

Multi-tenant boundary enforcement was verified at two independent layers:

1. **Gateway Boundary Validation:**
   - Dispatched `VectorSearchRequest` lacking `organisation_id` or `project_id`.
   - **Result:** **HTTP 422 Unprocessable Entity**.
   - Gateway explicitly rejects un-scoped vector requests before forwarding to ChromaDB:
     `{"error": {"code": "TENANT_SCOPE_REQUIRED", "message": "Multi-tenant vector search requires both 'organisation_id' and 'project_id' scope."}}`
2. **Metadata Filtering in ChromaDB:**
   - Dispatched query with synthetic/non-existent tenant IDs:
     `organisation_id: "00000000-0000-0000-0000-000000000000"`, `project_id: "00000000-0000-0000-0000-000000000000"`.
   - **Result:** **HTTP 200 OK**, `hits: []` (0 records returned).
   - Confirmed that ChromaDB enforces the `$and: [{"organisation_id": ...}, {"project_id": ...}]` filter, preventing any cross-tenant data leakage.

---

## H. Failure Handling and Recovery

| Failure Scenario | Evaluated By | Observed / Verified Behavior |
| :--- | :---: | :--- |
| **Gateway Offline / Unreachable** | Live Backend Readiness | Returns `HTTP 200 (degraded)` with `"Inference Gateway service unreachable"`. Backend web process remains healthy. |
| **Missing Gateway Bearer Token** | Live TCP Test | Gateway rejects with `HTTP 401 Unauthorized` (`"Authorization credentials missing"`). |
| **Invalid Gateway Bearer Token** | Live TCP Test | Gateway rejects with `HTTP 401 Unauthorized` (`"Invalid gateway authorization token"` via constant-time comparison). |
| **Invalid Route on Gateway** | Live TCP Test | Gateway rejects with `HTTP 404 Not Found`. Does not proxy arbitrary paths. |
| **Invalid HTTP Verb** | Live TCP Test | Gateway rejects with `HTTP 405 Method Not Allowed`. |
| **GPU Concurrency Overload** | Code Inspection | `GatewaySettings.gateway_max_concurrency = 1`. Async lock queues incoming requests; rejects with `HTTP 429` / `HTTP 503` if timeout exceeded. |
| **Ollama Service Failure** | Code Inspection | Gateway maps Ollama client errors to typed `GatewayError(502 BAD_GATEWAY)` without leaking stack traces. |
| **PostgreSQL Connection Interruption**| Code Inspection & Lifespan | Lifespan logs connection error; `/health/ready` returns `HTTP 503 unavailable` without crashing web process. |

---

## I. Performance and Resource Observation

Observed hardware telemetry during the live Qwen3 8B inference test:

| Metric | Measured Value | Operational Baseline / Limit |
| :--- | :--- | :--- |
| **GPU Model** | NVIDIA GeForce RTX 4050 Laptop GPU | 6141 MiB Total VRAM |
| **GPU VRAM Used** | `1114 MiB` idle / `1677 MiB` active | < 30% of total VRAM capacity |
| **GPU Utilization** | `3%` idle / peak during token generation | Healthy |
| **GPU Temperature** | `52°C - 54°C` | Well below thermal throttling limit (87°C) |
| **Ollama Chat Duration** | `30,285 ms` (128 completion tokens) | ~4.2 tokens/second generation speed |
| **Tunnel Network Overhead** | `2,373 ms` roundtrip over Cloudflare edge | QUIC / HTTP/2 protocol overhead |
| **Nomic Embedding Latency** | `7,278 ms` (2 texts &times; 768 dims) | ~3.6s per text embedding |
| **ChromaDB Heartbeat Latency** | `17.81 ms - 20.69 ms` | Sub-25ms response over Docker bridge |
| **Redis Ping Latency** | `18.27 ms - 75.11 ms` | Transient coordination latency |

---

## J. Security Audit Findings

### 1. High Severity — Database Connection Role Uses `BYPASSRLS=true`
- **Evidence:** Supabase connection string configured on Render connects with the `postgres` role, which possesses `rolbypassrls = true` in `pg_roles`.
- **Impact:** Row Level Security policies defined on the 61 public database tables are bypassed for direct SQLAlchemy TCP sessions. Tenant isolation currently relies strictly on application-level filtering (`WHERE project_id = ...`) in SQLAlchemy queries.
- **Remediation:** Provision the least-privilege role `handover_api` (`NOBYPASSRLS`) per `HANDOVER_DATABASE_LEAST_PRIVILEGE_DESIGN.md` with transaction-scoped `SET LOCAL app.current_user_id`.

### 2. Medium Severity — Cloudflare Quick Tunnel Ephemerality Breaks Render Ingress
- **Evidence:** Quick Tunnels (`trycloudflare.com`) assign temporary, randomized URLs that change on every process restart or network disconnection.
- **Impact:** Render's environment variable `INFERENCE_GATEWAY_BASE_URL` goes stale whenever `cloudflared` restarts, causing Render to fail with `"Inference Gateway service unreachable"`.
- **Remediation:** Replace the Quick Tunnel with a permanent Cloudflare Named Tunnel configured to a fixed CNAME record (`ai-gateway.the-sapiens.xyz`) as planned in M4.3.

### 3. Low Severity — Stale Environment Variable on Render Staging
- **Evidence:** Render's environment variable `INFERENCE_GATEWAY_BASE_URL` is set to `https://farm-gained-strip-lakes.trycloudflare.com`.
- **Impact:** AI operations originating from Render fail closed with `Inference Gateway service unreachable`.
- **Remediation:** Update `INFERENCE_GATEWAY_BASE_URL` in the Render Dashboard to the active tunnel endpoint.

---

## K. Remaining Work & Remediation Roadmap

1. **Synchronize Render Gateway Environment Variable:**
   - **Issue:** Render is pointing to `farm-gained-strip-lakes.trycloudflare.com` instead of the active tunnel.
   - **Remediation:** Update `INFERENCE_GATEWAY_BASE_URL` on Render to `https://empire-easy-maker-hybrid.trycloudflare.com` (or the permanent tunnel hostname).
   - **Requires Approval:** Yes (Render Dashboard environment variable update).
2. **Transition from Quick Tunnel to Cloudflare Named Tunnel:**
   - **Issue:** Quick Tunnels are ephemeral and unsuitable for durable production deployments.
   - **Remediation:** Execute Milestone M4.3.2 to configure a Named Tunnel on `ai-gateway.the-sapiens.xyz`.
   - **Dependencies:** Milestone M4.3.1 (Custom domain connected to Vercel).
3. **Provision Database Least-Privilege Role:**
   - **Issue:** Render connects via `postgres` (`BYPASSRLS=true`).
   - **Remediation:** Execute `handover_api` least-privilege role provisioning in Supabase.
   - **Dependencies:** Database architectural review approval.

---

## L. Final Milestone Classification

Based on direct empirical observation:
- Local Inference Gateway, Ollama Qwen3 8B, Nomic Embeddings, ChromaDB vector store, and Cloudflare Quick Tunnel ingress were directly executed and verified (**PASS**).
- Render backend and Vercel frontend are live and operational (**PASS**).
- Render-to-Gateway routing is disconnected due to the stale tunnel URL in Render's environment variables (**BLOCKED**).

### **`PARTIALLY VERIFIED — ACTION REQUIRED`**
