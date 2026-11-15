# Local Inference Gateway Configuration & Verification

## 1. Local Architecture Overview

In local development and testing, both the FastAPI backend and the Local Inference Gateway run on the Windows 11 host.

- **Local Backend**: `http://127.0.0.1:8000`
- **Local Inference Gateway**: `http://127.0.0.1:8002`
- **Ollama**: `http://127.0.0.1:11434`
- **ChromaDB**: `http://127.0.0.1:8001`
- **Redis**: `http://127.0.0.1:6379`

---

## 2. Environment Variables

To route backend requests through the local inference gateway, configure the following variables in `.env`:

```env
# Enable Gateway Routing
INFERENCE_GATEWAY_ENABLED=true
INFERENCE_GATEWAY_BASE_URL=http://127.0.0.1:8002
INFERENCE_GATEWAY_TOKEN=local-dev-gateway-bearer-token-1234567890
INFERENCE_GATEWAY_TIMEOUT_SECONDS=120.0

# Cloudflare Access Tokens (leave empty for local loopback)
CF_ACCESS_CLIENT_ID=
CF_ACCESS_CLIENT_SECRET=
```

For the Gateway itself (configured via `infrastructure/gateway/core/config.py`):
```env
GATEWAY_HOST=127.0.0.1
GATEWAY_PORT=8002
GATEWAY_AUTH_TOKEN=local-dev-gateway-bearer-token-1234567890
OLLAMA_BASE_URL=http://127.0.0.1:11434
CHROMA_HOST=127.0.0.1
CHROMA_PORT=8001
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
```

---

## 3. Starting the Services

### Step 1: Start Supporting Docker Containers
```powershell
docker compose -f infrastructure/docker/docker-compose.yml up -d chromadb redis
```

### Step 2: Ensure Ollama is Running
Verify models are present:
```powershell
ollama list
```
Required models:
- `qwen3:8b`
- `nomic-embed-text:latest`
- `glm-ocr:latest`

### Step 3: Run the Local Inference Gateway
```powershell
# From repository root
backend\.venv\Scripts\python.exe infrastructure/gateway/main.py
```
Gateway binds strictly to `127.0.0.1:8002`.

### Step 4: Run the FastAPI Backend
```powershell
# In another terminal
cd backend
..\backend\.venv\Scripts\uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

---

## 4. Health Verification Commands

### Gateway Basic Health Probe
```powershell
curl -i http://127.0.0.1:8002/health
```
Expected output:
```json
HTTP/1.1 200 OK
{"status":"healthy","service":"local-inference-gateway","timestamp":"..."}
```

### Gateway Detailed Health Probe (Requires Bearer Auth)
```powershell
curl -i -H "Authorization: Bearer local-dev-gateway-bearer-token-1234567890" http://127.0.0.1:8002/health/detailed
```
Expected output:
```json
HTTP/1.1 200 OK
{
  "status":"healthy",
  "components":{
    "ollama":{"status":"reachable"},
    "chromadb":{"status":"reachable"},
    "redis":{"status":"reachable"}
  }
}
```

---

## 5. Automated Verification Test Suite

To run the complete automated test suite verifying both the gateway security policies and backend integration:

```powershell
backend\.venv\Scripts\python.exe -m pytest -o pythonpath=". backend" backend/tests/test_inference_gateway_integration.py infrastructure/gateway/tests
```
Expected result: **50 passed** tests covering client lifecycle, chunk batching, retries, error mapping, and multi-tenant scoping.
