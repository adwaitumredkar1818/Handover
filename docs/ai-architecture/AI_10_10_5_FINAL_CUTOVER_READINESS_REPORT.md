# AI-10.10.5 — Final Production Cutover Readiness & Deployment Runbook

**Execution Date:** 2026-11-18  
**Release Target:** The Handover Project Intelligence Engine v1.0.0-prod  
**Deployment Model:** Hybrid Cloud Architecture (Render.com + Supabase + Cloudflare Tunnel + Local GPU Worker)  
**Authorizing Panel:** Principal Software Architect, SRE Lead, Database Reliability Engineer, Application Security Engineer  

---

## 1. System Deployment Topology Matrix

| Component | Target Infrastructure | Host / Runtime | Port / Protocol | Health Check / Probe |
| :--- | :--- | :--- | :--- | :--- |
| **Frontend Web App** | Vercel / Render Static Web | Next.js 16.4.6, React 19, TypeScript | HTTPS (443) | `GET /` (Static 200 OK) |
| **Backend REST & SSE API** | Render.com Web Service | Python 3.11, FastAPI, Uvicorn | HTTPS (443) -> HTTP (8000) | `GET /api/v1/system/health` |
| **Background Job Worker** | Render.com Background Worker | Python 3.11, SQLAlchemy 2.x | Internal async worker loop | PostgreSQL `background_jobs` table |
| **Relational Database** | Supabase Pro / Managed PG 16 | PostgreSQL 16, Psycopg 3 | Port 6543 (Transaction Pooler) | `SELECT 1;` |
| **Object Storage** | Supabase Storage Private Bucket | `project-evidence` bucket | HTTPS via Service Role Key | S3/Supabase Storage API |
| **Vector Store** | Local Host / ChromaDB | ChromaDB HTTP (`chromadb/chroma`) | Port 8001 (Loopback) | `GET /api/v1/heartbeat` |
| **Inference Gateway** | Windows 11 Host | FastAPI + Uvicorn (`asyncio.Semaphore(1)`) | Port 8002 (Loopback) | `GET /v1/health` (Telemetry) |
| **Inference Runtime** | Windows 11 Host | Ollama (`qwen3:8b`, `nomic-embed-text`) | Port 11434 (Loopback) | `GET /api/tags` |
| **Zero-Trust Tunnel** | Windows 11 Host | Cloudflare Tunnel (`cloudflared`) | Outbound TLS to Cloudflare | Tunnel Daemon Status |

---

## 2. Step-by-Step Production Cutover Execution Plan

```text
[PHASE 1: HOST PREPARATION] ──▶ [PHASE 2: DB & STORAGE PROVISIONING] ──▶ [PHASE 3: BACKEND LAUNCH] ──▶ [PHASE 4: FRONTEND PROMOTION] ──▶ [PHASE 5: POST-CUTOVER SANITY]
```

### Phase 1: Local Host Edge Infrastructure Initialization
1. Ensure Docker Desktop is active. Launch persistent storage containers:
   ```powershell
   docker compose up -d postgres redis chromadb
   ```
2. Start Ollama and verify model readiness:
   ```powershell
   ollama list
   # Verify qwen3:8b, nomic-embed-text, and glm-ocr:latest are listed
   ```
3. Launch Local Inference Gateway:
   ```powershell
   .\backend\.venv\Scripts\uvicorn.exe infrastructure.gateway.main:app --host 127.0.0.1 --port 8002
   ```
4. Start Cloudflare Tunnel:
   ```powershell
   cloudflared tunnel run handover-inference-tunnel
   ```

### Phase 2: Remote Database Migration & Private Storage Setup
1. Verify target database connectivity:
   ```powershell
   & "backend/.venv/Scripts/python.exe" -c "from app.db.session import create_db_engine, verify_database_connection; from app.core.config import get_settings; print(verify_database_connection(create_db_engine(get_settings())))"
   ```
2. Run Alembic migrations up to head revision (`0020_graphs_and_contributors`):
   ```powershell
   & "backend/.venv/Scripts/alembic.exe" -c backend/alembic.ini upgrade head
   ```
3. Confirm all 65 tables have RLS enabled:
   ```sql
   SELECT count(*) FROM pg_tables WHERE schemaname = 'public' AND rowsecurity = true;
   -- Must return 65
   ```

### Phase 3: Cloud Backend & Worker Deployment
1. Set all mandatory environment variables in Render Dashboard (`render.yaml`).
2. Deploy Backend API Web Service.
3. Deploy Background Worker Service.
4. Verify `/api/v1/system/health` returns `200 OK` with database, redis, and vector store healthy.

### Phase 4: Frontend Promotion & Domain Mapping
1. Deploy frontend to Vercel or Render.
2. Verify environment variable `NEXT_PUBLIC_API_URL` points to production backend URL.
3. Verify `npm run build` compiles with 69/69 routes generated.

### Phase 5: Post-Cutover Sanity Verification
1. Register primary platform admin.
2. Verify verification email flow.
3. Create organization and project.
4. Upload test sample PDF. Confirm OCR extraction, chunking, and ChromaDB indexing.
5. Create investigation in Project Intelligence Assistant. Confirm live SSE event streaming.

---

## 3. Emergency Rollback Strategy

If any unrecoverable failure occurs during the cutover window:
1. **Frontend**: Roll back deployment to previous release tag immediately via hosting dashboard (e.g. Vercel instant rollback).
2. **Backend**: Revert Render deployment to previous stable Git commit SHA.
3. **Database**:
   - If schema migration fails midway, Alembic automatically rolls back transactional DDL.
   - For complete data restoration, restore from pre-cutover binary dump:
     ```bash
     pg_restore -U postgres -d knowledge_handover -c -v pre_cutover_backup.dump
     ```
4. **Tunnel**: Terminate `cloudflared` process on host to sever external access to local inference runtime.

---

## 4. Cutover Readiness Decision

All prerequisites, architectural bounds, and verification criteria for production deployment have been satisfied.

**Final Release Decision:** **APPROVED FOR PRODUCTION CUTOVER**
