# Backend ↔ Local Inference Gateway Architecture

## 1. Overview and Mission

The Handover platform adopts a hybrid production topology:
- **Cloud Backend**: FastAPI application deployed on Render.
- **Canonical Cloud Datastore**: Supabase PostgreSQL + Auth in Sydney (`ap-southeast-2`).
- **Cloud Storage**: Supabase Storage (`project-evidence` bucket).
- **Local AI Infrastructure**: Windows 11 host with NVIDIA RTX 4050 (6GB VRAM) running Ollama (`qwen3:8b`, `nomic-embed-text`, `glm-ocr:latest`), ChromaDB (dedicated HTTP), and Redis.
- **Local Inference Gateway**: Dedicated FastAPI microservice (`127.0.0.1:8002`) providing a hardened, authenticated, rate-limited, and tenant-scoped interface to the local AI services.

The purpose of the **Backend ↔ Inference Gateway Integration** is to bridge the FastAPI backend and the Local Inference Gateway through a clean, unified Python client abstraction (`InferenceGatewayClient`). This enables the backend to execute LLM inferences, text embeddings, and vector similarity searches over standard HTTP whether running locally on loopback or across Cloudflare Access and Cloudflare Tunnel in production.

---

## 2. Request and Data Flow

```text
+-----------------------------------------------------------------------------------------+
|                                    RENDER BACKEND                                       |
|                                                                                         |
|  [Incoming HTTP Request]                                                                |
|           │                                                                             |
|           ▼                                                                             |
|  [Auth Middleware & Dependencies]                                                       |
|    - Supabase Auth JWT / Argon2id Token Verified                                        |
|    - Active User & Organization Resolved                                                |
|    - Project Access & Role-Based Permissions Evaluated                                  |
|           │                                                                             |
|           ▼ (Context: User, Org ID, Project ID)                                         |
|  [Application Services] (Assistant RAG, Query Embeddings, Vector Search)                |
|           │                                                                             |
|           ▼ (Method Calls)                                                              |
|  [InferenceGatewayClient]                                                               |
|    - Injects Authorization: Bearer <INFERENCE_GATEWAY_TOKEN>                            |
|    - Injects CF-Access-Client-Id & CF-Access-Client-Secret (if Cloudflare configured)   |
|    - Enforces mandatory organisation_id + project_id in vector searches                 |
|    - Bounded retries (tenacity) on transient 5xx & connection errors                    |
+-----------------------------------------------------------------------------------------+
                                           │
                                           │ HTTPS (or HTTP loopback)
                                           ▼
+-----------------------------------------------------------------------------------------+
|                        LOCAL INFERENCE GATEWAY (127.0.0.1:8002)                         |
|                                                                                         |
|  [Security & Rate Limiting]                                                             |
|    - Constant-time Bearer token verification                                            |
|    - Sliding window IP rate limiter                                                     |
|    - Mandatory Tenant Scope Validation (organisation_id + project_id)                   |
|           │                                                                             |
|           ▼                                                                             |
|  [Router Layer]                                                                         |
|    - /health & /health/detailed                                                         |
|    - /v1/chat/completions (Strict Model Whitelist: qwen3:8b)                            |
|    - /v1/embeddings (Strict Model Whitelist: nomic-embed-text)                          |
|    - /v1/vectors/search (Strict ChromaDB Project Collection & Tenant Filter)            |
|           │                                                                             |
|           +──────────────────────+──────────────────────+                               |
|           │                      │                      │                               |
|           ▼                      ▼                      ▼                               |
|    [Ollama 11434]         [ChromaDB 8001]        [Redis 6379]                           |
|    - Qwen3 8B             - Project Isolation    - Rate limit & cache                   |
|    - Nomic Embed Text     - Collection filter                                           |
+-----------------------------------------------------------------------------------------+
```

---

## 3. Client Design (`InferenceGatewayClient`)

The client is implemented in `backend/app/services/inference_gateway.py` with configuration provided via `InferenceGatewaySettings` in `backend/app/core/config.py`.

### 3.1 Key Capabilities
1. **Dynamic Configuration**: Controlled via `INFERENCE_GATEWAY_ENABLED`, `INFERENCE_GATEWAY_BASE_URL`, `INFERENCE_GATEWAY_TOKEN`, and `INFERENCE_GATEWAY_TIMEOUT_SECONDS`.
2. **Cloudflare Access Header Injection**: Automatically attaches `CF-Access-Client-Id` and `CF-Access-Client-Secret` if configured.
3. **Chunk Batching**: Automatically breaks large embedding requests into batches of 16 chunks to avoid HTTP payload bottlenecks and Ollama buffer overflows.
4. **Resilience & Retries**: Utilizes `tenacity` with exponential backoff (`min=0.5s`, `max=5.0s`, `stop_after_attempt=3`) specifically on network timeouts, connect errors, and HTTP 502/503/504 status codes. Client-side errors (4xx) are NOT retried.
5. **Strict Tenant Isolation**: `search_vectors()` mandates non-empty `organisation_id` and `project_id`. Supplying empty or missing values raises `ValueError` before any network request is issued.
6. **Sanitized Telemetry**: Logging suppresses all secrets, headers, and access tokens, outputting only URL paths, chunk counts, latency, and sanitized HTTP status codes.

---

## 4. Security & Tenant Isolation Enforcement

### 4.1 Strict Authority Separation
- **The backend is the sole authority** on user authentication, project membership, and data permissions.
- The Local Inference Gateway is an **internal infrastructure worker**. It verifies that calls originate from an authorized caller (via Bearer token + optional Cloudflare Access Service Token), and that tenant context is explicitly provided.
- Clients/browsers NEVER interact with the Local Inference Gateway directly. Direct exposure to the public internet without mutual authentication is strictly prohibited.

### 4.2 Multi-Tenant Safeguards in Vector Search
In `InferenceGatewayClient.search_vectors()`:
- `organisation_id` and `project_id` are required arguments.
- The gateway transforms these into ChromaDB `$and` filter clauses:
  ```json
  {
    "$and": [
      {"organisation_id": {"$eq": organisation_id}},
      {"project_id": {"$eq": project_id}}
    ]
  }
  ```
- This prevents cross-tenant data leakage even if vector collections are aggregated or queried concurrently.

---

## 5. Offline and Failure Behavior

When the local AI infrastructure is offline, asleep, or undergoing model switching:
1. **Health Probes**: `check_health()` returns `False` immediately upon connection timeout without crashing the backend service.
2. **Graceful Error Mapping**:
   - `401 Unauthorized` maps to `InferenceGatewayUnauthorizedError`.
   - `403 Forbidden` maps to `InferenceGatewayForbiddenError`.
   - `422 Unprocessable Content` maps to `InferenceGatewayValidationError`.
   - `502 / 503 / 504 / ConnectTimeout` maps to `InferenceGatewayServiceUnavailableError`.
3. **Assistant Degradation**: The Project Knowledge Assistant detects `InferenceGatewayServiceUnavailableError` and returns an explicit, uncertainty-disclosing response:
   > *"Local AI inference is temporarily unavailable. Knowledge retrieval and AI generation cannot be completed at this time."*
   The system never fabricates answers or falls back to unauthorized cloud models.
