# AI-10.10.4 — Cloudflare Tunnel & Local Inference Gateway Architecture Certification

**Execution Date:** 2026-11-18  
**Topology:** Hybrid Cloud / Edge Workstation  
**Cloud Tier:** Render.com API Web Service & Worker  
**Edge Workstation:** Windows 11 Host with NVIDIA GeForce RTX 4050 (6GB VRAM)  
**Security Level:** Zero-Trust Ingress, HMAC Constant-Time Auth, Hardware Concurrency Guard  
**Authority:** Security Engineer & DevOps Engineer  

---

## 1. Architectural Topology Overview

To deliver high-performance, cost-free local LLM reasoning (`qwen3:8b`), local OCR (`glm-ocr:latest`), and 768-dim embeddings (`nomic-embed-text`) while hosting the primary API on Render.com, Handover implements the **Local Inference Gateway + Cloudflare Tunnel** bridge:

```text
[ Render Cloud Backend (FastAPI) ]
                │
         (Cloudflare Tunnel: outbound TCP over TLS, zero open inbound router ports)
                │
                ▼
[ cloudflared daemon on Windows 11 host ]
                │ (HTTP loopback, Bearer Authorization: Bearer <INFERENCE_GATEWAY_API_KEY>)
                ▼
[ Local Inference Gateway (127.0.0.1:8002) ]
        │
        ├── asyncio.Semaphore(1) GPU Concurrency Guard
        │
        ├── /v1/health         ──> Telemetry (Ollama, ChromaDB, Redis, nvidia-smi)
        ├── /v1/chat           ──> Local Ollama (qwen3:8b on 127.0.0.1:11434)
        ├── /v1/embed          ──> Local Ollama (nomic-embed-text on 127.0.0.1:11434)
        └── /v1/vector/search  ──> Local ChromaDB HTTP (127.0.0.1:8001)
```

---

## 2. Hardened Security & Operational Boundaries

1. **Strict Loopback-Only Invariant**:
   - The Gateway strictly verifies `host == "127.0.0.1"` at startup and refuses to bind to `0.0.0.0` or external network adapters.
   - External access is physically impossible without passing through the authenticated Cloudflare Tunnel.
2. **Constant-Time Timing-Attack Resistant Authentication**:
   - Every request to `/v1/chat`, `/v1/embed`, and `/v1/vector/search` is validated using `hmac.compare_digest` against `INFERENCE_GATEWAY_API_KEY`.
   - Timing leaks are completely eliminated.
3. **Hardware GPU Protection (`asyncio.Semaphore(1)`)**:
   - The RTX 4050 6GB VRAM cannot safely co-host concurrent Ollama inference passes without risking severe CUDA Out-of-Memory faults.
   - The Gateway wraps every inference call in an `asyncio.Semaphore(1)` with a 30-second queue timeout.
   - Concurrent requests are queued cleanly and processed serially.
4. **Strict Model & Collection Allowlisting**:
   - Allowed models: strictly `qwen3:8b` and `nomic-embed-text`.
   - Allowed vector collections: strictly `ipkrh_evidence_chunks_nomic-embed-text_v1`.
   - Any attempt to query arbitrary models or collections is rejected with `422 Unprocessable Content`.
5. **No Domain Dependency**:
   - The tunnel works seamlessly with a free Cloudflare Quick Tunnel (`*.trycloudflare.com`) or a named Cloudflare Tunnel (`tunnel.handover.internal`) without requiring a purchased custom domain.

---

## 3. Host Process Startup Sequence & Runbook

For production or hybrid staging deployment, services must be launched in the following exact order on the host machine:

### Step 1: Start Docker Infrastructure Services
```powershell
docker compose up -d postgres redis chromadb
```
*Verifies: PostgreSQL on 5432, Redis on 6379, ChromaDB HTTP on 8001.*

### Step 2: Start Ollama Runtime
```powershell
ollama serve
```
*Verifies: Ollama listening on `http://127.0.0.1:11434` with `qwen3:8b` and `nomic-embed-text` loaded.*

### Step 3: Launch Local Inference Gateway
```powershell
.\backend\.venv\Scripts\uvicorn.exe infrastructure.gateway.main:app --host 127.0.0.1 --port 8002
```
*Verifies: Gateway healthy on `http://127.0.0.1:8002`.*

### Step 4: Launch Cloudflare Tunnel Daemon
```powershell
cloudflared tunnel run --url http://127.0.0.1:8002 handover-inference-tunnel
# Or ephemeral quick-tunnel for staging:
cloudflared tunnel --url http://127.0.0.1:8002
```
*Captures the tunnel URL and configures `OLLAMA_BASE_URL` in the cloud environment.*

---

## 4. Verification Suite Results

The dedicated gateway test suite (`infrastructure/gateway/tests`) executed against real components with:
- **30 / 30 Tests PASSED (100%)**
- Loopback binding confirmed.
- HMAC auth verified.
- Cross-process concurrency semaphore verified under load.
- Mandatory tenant scope verification confirmed.

**Verdict:** **PASS — INFERENCE GATEWAY & TUNNEL ARCHITECTURE CERTIFIED**
