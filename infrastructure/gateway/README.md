# Local Inference Gateway (Phase M3.1)

A hardened, authenticated, loopback-only reverse proxy service mediating access between the cloud backend (Render) and local AI infrastructure (Ollama & ChromaDB) running on the Windows 11 host.

---

## 1. Architectural Role

In Phase M3.1, this gateway runs locally at `127.0.0.1:8002`. In Phase M3.2, a Cloudflare Tunnel daemon (`cloudflared`) on the Windows host will securely route incoming requests from the Render backend to this gateway.

```text
[ Render Cloud Backend (FastAPI) ]
                │
         (Cloudflare Tunnel)
                │
                ▼
[ cloudflared on Windows 11 host ]
                │ (HTTP, Bearer Auth)
                ▼
[ Local Inference Gateway (127.0.0.1:8002) ]
        ├── /v1/health   ──> Telemetry (Ollama, ChromaDB, Redis, GPU nvidia-smi)
        ├── /v1/chat     ──> Local Ollama (Qwen3 8B, 127.0.0.1:11434)
        ├── /v1/embed    ──> Local Ollama (Nomic Embed Text, 127.0.0.1:11434)
        └── /v1/vector/search ──> Local ChromaDB (127.0.0.1:8001)
```

---

## 2. Security Controls

1. **Strict Loopback Binding**: Binds exclusively to `127.0.0.1:8002`. The application enforces this at startup with an invariant check.
2. **Timing-Attack Resistant Authentication**: Constant-time HMAC comparison (`hmac.compare_digest`) for all inference and vector endpoints via Bearer token (`INFERENCE_GATEWAY_API_KEY`).
3. **Hardware Protection Semaphore**: Serializes GPU inference via `asyncio.Semaphore(1)` with a 30s queue timeout to prevent out-of-memory (OOM) faults on the RTX 4050 6GB VRAM.
4. **Strict Request Bounds**:
   - Max body size: 1 MB (`gateway_max_body_bytes`).
   - Max chat messages: 50.
   - Max prompt length: 32,768 characters.
   - Max embedding batch: 16 items.
   - Allowed models: `qwen3:8b`, `nomic-embed-text`.
   - Allowed Chroma collections: `ipkrh_evidence_chunks_nomic-embed-text_v1`.
5. **No Binary Ingestion**: Heavy document processing, PDF conversion, and OCR remain inside the local worker daemon (`app.worker`) and do NOT pass through this gateway.

---

## 3. Running the Gateway

```powershell
# From repository root:
.\backend\.venv\Scripts\uvicorn.exe infrastructure.gateway.main:app --host 127.0.0.1 --port 8002
```

---

## 4. Endpoints Summary

- `GET /v1/health` — Probes Ollama version, ChromaDB heartbeat, Redis ping, and GPU metrics (nvidia-smi).
- `POST /v1/chat` — Authenticated chat completion.
- `POST /v1/embed` — Authenticated embedding generation (768 dimensions).
- `POST /v1/vector/search` — Authenticated vector similarity search against ChromaDB.
