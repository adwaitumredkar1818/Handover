# HANDOVER — M4.2.2 CLOUDFLARE TUNNEL PRE-DEPLOYMENT VERIFICATION AUDIT

**Project:** The Handover — Intelligent Project Knowledge Reconstruction & Handover Platform  
**Milestone:** M4.2.2 — Cloudflare Tunnel Pre-Deployment Verification  
**Audit Timestamp:** 2026-11-15T15:48:00+05:30  
**Target Architecture:** Local AI Inference Gateway (`127.0.0.1:8002`) &rarr; Cloudflare Tunnel &rarr; Render Staging Backend (`https://the-handover-api.onrender.com`)  
**Audit Mode:** Read-Only Verification (No services modified, no credentials leaked, no tunnels launched)  

---

## 1. Executive Summary

Milestone **M4.2.2** performed a comprehensive, strict read-only audit of the local Windows environment, Cloudflare Tunnel (`cloudflared`) installation, the FastAPI Local Inference Gateway (`127.0.0.1:8002`), local AI infrastructure (Ollama, ChromaDB, Redis), Docker container networking, and Windows Firewall posture.

### Key Audit Findings:
1. **Cloudflared Installation:** **VERIFIED**. `cloudflared.exe` version `2026.11.0` is installed at `C:\Program Files (x86)\cloudflared\cloudflared.exe` and is registered in the Machine system `PATH`.
2. **Local AI Infrastructure (Ollama, ChromaDB, Redis):** **HEALTHY & SECURE**. Ollama (`127.0.0.1:11434`), ChromaDB (`127.0.0.1:8001`), and Redis (`127.0.0.1:6379`) are active, passing TCP connectivity tests, and bound strictly to localhost loopback interfaces.
3. **Gateway Architecture & Security Controls:** **PASS (CODE AUDIT)**. The gateway implementation in `infrastructure/gateway/` enforces strict loopback binding assertions (`127.0.0.1`), constant-time API token validation (`hmac.compare_digest`), multi-tenant boundary scoping (`organisation_id` + `project_id`), request body limits (1 MB), sliding-window rate limiting (60 req/min), disabled documentation UI (`docs_url=None`), and single concurrency for RTX 4050 6GB VRAM protection.
4. **Current Gateway Process State:** **OFFLINE (PORT 8002 NOT LISTENING)**. The Local Inference Gateway process is currently stopped following the clean closeout of milestone M3.3.7/M3.3.8. Port `8002` returned `TcpTestSucceeded = False`.
5. **Firewall & Network Exposure:** **SECURE**. All upstream local AI ports (11434, 8001, 6379) are bound strictly to `127.0.0.1` and not exposed to the public Internet or LAN. No inbound allow rules exist for port 8002.
6. **Overall Readiness Decision:** **READY WITH CONDITIONS**. The environment and security architecture are fully compliant. To establish the Cloudflare Tunnel in M4.2.3, the gateway process must first be started on loopback `127.0.0.1:8002` with an active `INFERENCE_GATEWAY_API_KEY`.

---

## 2. Cloudflared Installation Verification

| Check Item | Result | Evidence / Value | Status |
| :--- | :--- | :--- | :--- |
| **Executable Path** | Verified | `C:\Program Files (x86)\cloudflared\cloudflared.exe` | **PASS** |
| **Binary Version** | Verified | `2026.11.0` (built `2026-11-12T03:21 UTC`) | **PASS** |
| **System Registry PATH** | Verified | Present in Machine `Path` registry (`C:\Program Files (x86)\cloudflared\`) | **PASS** |
| **Command Resolution** | Verified | Resolves via PowerShell session (`Get-Command cloudflared`) | **PASS** |

---

## 3. Local Gateway Availability & Health

| Metric / Check | Target Expectation | Observed Status | Status | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **Port 8002 Listener** | `127.0.0.1:8002` | Closed / Not Listening | **WARNING** | Process intentionally stopped after M3.3.8 closeout |
| **Process ID (PID)** | Running Python process | None on port 8002 | **WARNING** | Needs process launch before tunnel creation |
| **TCP Connection Test** | `TcpTestSucceeded = True` | `TcpTestSucceeded = False` | **WARNING** | Connection refused (port idle) |
| **Unauthenticated Health (`/health`)** | HTTP 200 `{"status": "ok"}` | Not reachable (process down) | **NOT RUN** | Documented in `infrastructure/gateway/main.py:106` |
| **Authenticated Health (`/v1/health`)** | HTTP 200 with Bearer token | Not reachable (process down) | **NOT RUN** | Documented in `infrastructure/gateway/main.py:112` |

---

## 4. Authentication & Access Security

An audit of the authentication implementation in `infrastructure/gateway/auth.py` and `config.py` confirms:

| Control | Mechanism | Implementation Detail | Status |
| :--- | :--- | :--- | :--- |
| **Auth Scheme** | HTTP Bearer Token | `HTTPBearer(auto_error=False)` enforced on all `/v1/*` routes | **PASS** |
| **Timing Attack Defense** | Constant-Time Comparison | Enforces `hmac.compare_digest(provided_token.encode(), expected_token.encode())` | **PASS** |
| **Unauthenticated Route Isolation** | Strict Path Partitioning | Only `/health` is unauthenticated (returns minimal `{"status": "ok"}`). `/v1/health`, `/v1/chat`, `/v1/embed`, and `/v1/vector/search` strictly require valid Bearer token. | **PASS** |
| **Missing/Invalid Header Behavior** | HTTP 401 Unauthorized | Returns `UNAUTHORIZED` (`401`) on missing credentials, wrong scheme, empty token, or invalid key. | **PASS** |
| **Token Minimum Entropy** | Pydantic Field Validation | `inference_gateway_api_key` enforces minimum 32 characters; rejects blank/empty tokens. | **PASS** |
| **Secret Sanitization** | `SecretStr` Encapsulation | Token values are typed as `SecretStr`, preventing inadvertent leakage in logs, stack traces, or exception dumps. | **PASS** |

---

## 5. Gateway Security Architecture Audit

The gateway code (`infrastructure/gateway/`) was audited against production exposure standards:

1. **Loopback Binding Assertion (`main.py:42-49`)**:
   ```python
   if settings.inference_gateway_host not in ("127.0.0.1", "localhost"):
       msg = f"FATAL SECURITY VIOLATION: Local Inference Gateway must bind strictly to 127.0.0.1!"
       logger.critical(msg)
       raise RuntimeError(msg)
   ```
   *Verdict:* **PASS**. Gateway hard-aborts if bound to `0.0.0.0` or any external interface.
2. **API Documentation Surface (`main.py:66-68`)**:
   - `docs_url = None`
   - `redoc_url = None`
   - `openapi_url = None`
   *Verdict:* **PASS**. Prevents OpenAPI/Swagger reconnaissance by unauthorized parties.
3. **CORS Configuration (`main.py:89-92`)**:
   - `allow_origins = ["http://127.0.0.1", "http://localhost"]`
   *Verdict:* **PASS**. Restricts browser origin access strictly to local host.
4. **Multi-Tenant Scoping (`main.py:149-160`)**:
   - `/v1/vector/search` requires both `organisation_id` and `project_id`. Rejects unscoped requests with HTTP 422 `TENANT_SCOPE_REQUIRED`.
   *Verdict:* **PASS**. Prevents cross-tenant vector leakage.
5. **Model Allowlists (`config.py:46-55`)**:
   - `allowed_chat_models = ["qwen3:8b", "qwen3:latest"]`
   - `allowed_embed_models = ["nomic-embed-text", "nomic-embed-text:latest"]`
   - `allowed_chroma_collections = ["ipkrh_evidence_chunks_nomic-embed-text_v1"]`
   *Verdict:* **PASS**. Prevents arbitrary model execution or collection traversal.
6. **Hardware & DoS Protections (`config.py:58-67`, `middleware.py:25-72`)**:
   - `gateway_max_concurrency = 1` (Protects RTX 4050 6GB VRAM from OOM crashes).
   - `gateway_max_body_bytes = 1,048,576` (Rejects payloads > 1 MB with HTTP 413).
   - In-memory sliding window rate limiter: 60 requests/minute per client key.
   *Verdict:* **PASS**.

---

## 6. Local AI Infrastructure Status

Live verification of local upstream services backing the gateway:

| Service | Target Port | TCP Test | Process / Container | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Ollama Inference Engine** | `127.0.0.1:11434` | **TcpTestSucceeded = True** | Windows Process `ollama.exe` (PID 32116) | **PASS (READY)** |
| **ChromaDB Vector Store** | `127.0.0.1:8001` | **TcpTestSucceeded = True** | Docker Container `ipkrh-chromadb` (healthy) | **PASS (READY)** |
| **Redis Cache / State** | `127.0.0.1:6379` | **TcpTestSucceeded = True** | Docker Container `ipkrh-redis` (healthy) | **PASS (READY)** |
| **PostgreSQL Canonical DB**| `127.0.0.1:5432` | N/A (Docker verified) | Docker Container `ipkrh-postgres` (healthy) | **PASS (READY)** |

All local AI backends are healthy, active, and responsive.

---

## 7. Docker Container Status

Command output from `docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"`:

```text
NAMES            STATUS                  PORTS
ipkrh-redis      Up 31 hours (healthy)   127.0.0.1:6379->6379/tcp
ipkrh-postgres   Up 31 hours (healthy)   127.0.0.1:5432->5432/tcp
ipkrh-chromadb   Up 31 hours (healthy)   127.0.0.1:8001->8000/tcp
```

**Docker Security Assessment:**
- All ports map exclusively to `127.0.0.1` (loopback).
- Zero containers map to `0.0.0.0`.
- All containers report `(healthy)` with over 31 hours of continuous uptime.

---

## 8. Windows Firewall & Network Exposure Review

1. **Firewall Profiles:**
   - Domain: `Enabled = True`
   - Private: `Enabled = True`
   - Public: `Enabled = True`
2. **Inbound Rule Analysis:**
   - Verified that no inbound allow rules exist for port `8002`, `11434`, `8001`, or `6379`.
   - The loopback pseudo-interface (`127.0.0.1`) routes internally and is not exposed across physical network adapters.
3. **Tunnel Ingress Model:**
   - Cloudflare Quick Tunnel operates via **outbound TLS connections** over port 443 to the Cloudflare edge.
   - It requires **zero inbound open ports** on the Windows Firewall or router NAT.
   - This architecture completely protects the local environment from inbound port scanning.

---

## 9. Findings Classification

| Finding ID | Category | Description | Severity | Remediation / Action |
| :--- | :--- | :--- | :--- | :--- |
| **F-01** | `cloudflared` | CLI installed and resolves in Machine PATH | **PASS** | None required |
| **F-02** | Upstream AI | Ollama, ChromaDB, and Redis all healthy on loopback | **PASS** | None required |
| **F-03** | Gateway Security | Authentication, rate limiting, body bounding, model allowlists verified in code | **PASS** | None required |
| **F-04** | Container Isolation | Docker ports bound strictly to `127.0.0.1` | **PASS** | None required |
| **F-05** | Network Exposure | Zero external listening ports; firewall profiles enabled | **PASS** | None required |
| **F-06** | Gateway Liveness | Gateway process not currently running on `127.0.0.1:8002` | **WARNING** | Start gateway prior to running tunnel |

---

## 10. Deployment Readiness Decision

### Decision: `READY WITH CONDITIONS`

**Reasoning:**
- The host environment, binary installations, Docker infrastructure, and security posture pass all pre-deployment requirements.
- The single condition is that the Local Inference Gateway service must be started on `127.0.0.1:8002` immediately prior to establishing the Cloudflare Tunnel.

---

## 11. Recommended Next Steps (Milestone M4.2.3 Plan)

When transitioning to Milestone M4.2.3 (Quick Tunnel Launch & Verification):

1. **Start the Local Inference Gateway:**
   - Execute in background / dedicated terminal:
     ```powershell
     $env:INFERENCE_GATEWAY_HOST="127.0.0.1"
     $env:INFERENCE_GATEWAY_PORT="8002"
     $env:INFERENCE_GATEWAY_API_KEY="<cryptographically_secure_token_min_32_chars>"
     python -m uvicorn infrastructure.gateway.main:create_gateway_app --factory --host 127.0.0.1 --port 8002
     ```
2. **Verify Gateway Liveness on Loopback:**
   - `Invoke-RestMethod http://127.0.0.1:8002/health` &rarr; Expected: `{"status": "ok"}`
   - Verify unauthenticated `/v1/health` returns HTTP 401.
3. **Launch Outbound Cloudflare Quick Tunnel:**
   - Execute:
     ```powershell
     cloudflared tunnel --url http://127.0.0.1:8002
     ```
   - Capture the assigned public hostname (e.g., `https://<random>.trycloudflare.com`).
4. **Conduct Tunnel Verification:**
   - Verify public `/health` endpoint over the tunnel.
   - Verify public `/v1/health` rejects unauthenticated requests (HTTP 401).
   - Verify public `/v1/health` succeeds with the Bearer token (HTTP 200).
5. **Configure Render Backend:**
   - Update `INFERENCE_GATEWAY_URL` in Render Dashboard with the tunnel URL.
   - Update `INFERENCE_GATEWAY_TOKEN` in Render Dashboard with the gateway token.
   - Trigger Render deployment and observe `/health/ready` transitioning to HTTP 200.
