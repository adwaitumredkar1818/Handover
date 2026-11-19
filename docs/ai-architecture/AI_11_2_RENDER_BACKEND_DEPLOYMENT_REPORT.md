# AI-11.2 — Render Backend Deployment & Live Telemetry Report

**Execution Date:** 2026-11-18  
**Target Environment:** Render.com Web Service  
**Service Name:** `the-handover-api`  
**Region:** Singapore (`singapore`)  
**Plan:** Free Tier  
**Live Endpoint:** `https://the-handover-api.onrender.com`  
**Certification Authority:** Senior Backend Engineer & DevOps Engineer  

---

## 1. Service Configuration Audit

In `render.yaml`, the backend service specification defines:
- **Build Command**: `pip install --upgrade pip && pip install -r requirements.txt`
- **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1 --proxy-headers --forwarded-allow-ips='*'`
- **Health Check Path**: `/health`
- **SSL / Security**: `POSTGRES_SSL_MODE=require`, `COOKIE_SECURE=true`, `COOKIE_SAMESITE=none`
- **Storage Provider**: `supabase_storage` via `SUPABASE_URL` and `SUPABASE_STORAGE_BUCKET=project-evidence`

---

## 2. Empirical Telemetry Probes

Direct HTTP probes were dispatched to `the-handover-api.onrender.com`:

### Probe 1: Liveness Check (`GET /health`)
```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "status": "ok",
  "service": "Intelligent Project Knowledge Reconstruction & Handover Platform",
  "environment": "production",
  "api_version": "v1",
  "request_id": "0c53656e-f566-4a0a-8694-a99110c638e4"
}
```
*Result: PASS. Application web server is alive, executing FastAPI router middleware, and attaching correlation request IDs.*

### Probe 2: Readiness & Dependency Check (`GET /health/ready`)
```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "status": "degraded",
  "request_id": "09b14c85-5c7e-4848-a8e7-2c39955a7d56",
  "application": {
    "status": "ok"
  },
  "database": {
    "status": "ok",
    "required": true,
    "latency_ms": 284.33,
    "message": "Reachable"
  },
  "external_services": {
    "ollama": {
      "status": "unavailable",
      "required": false,
      "latency_ms": null,
      "message": "Inference Gateway service unreachable."
    },
    "chromadb": {
      "status": "unavailable",
      "required": false,
      "latency_ms": null,
      "message": "Inference Gateway service unreachable."
    }
  }
}
```
*Analysis*:
1. **Database**: 100% operational (`latency_ms: 284.33`, `message: "Reachable"`).
2. **Degraded State Mechanism**: The lifespan correctly classifies Ollama and ChromaDB as optional/degraded background dependencies (`required: false`), allowing the web application to serve REST authentication, organisation management, and project browsing even when the local GPU workstation tunnel is sleeping.

---

## 3. Certification Verdict

**Verdict:** **PASS — RENDER BACKEND IS LIVE AND OPERATIONAL**
