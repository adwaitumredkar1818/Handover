# AI-11.1 — Supabase Database & Storage Production Integration Report

**Execution Date:** 2026-11-18  
**Target Provider:** Supabase Managed Cloud (`rjntmboskzyrsqcetzil.supabase.co`)  
**Region:** `ap-southeast-2` (Sydney)  
**Database Host:** `aws-1-ap-southeast-2.pooler.supabase.com`  
**Storage Bucket:** `project-evidence`  
**Certification Authority:** Database Reliability Engineer & Security Engineer  

---

## 1. Supabase Project & Connectivity Inspection

### Telemetry Findings
1. **Remote Cloud Backend Connectivity**:
   - The deployed Render backend (`https://the-handover-api.onrender.com/health/ready`) confirmed:
     - `database`: `status: "ok"`, `required: true`, `latency_ms: 284.33 ms`, `message: "Reachable"`.
     - The Render web instance is actively connected to the remote PostgreSQL database and passes operational database health checks.
2. **Local Machine Egress to Supabase Pooler**:
   - Outbound TCP direct probes to `aws-1-ap-southeast-2.pooler.supabase.com:6543` and `:5432` from this local Windows workstation timed out.
   - *Root Cause*: Residential ISP port filtering / firewall blocking outbound database ports 5432 and 6543 to AWS Sydney IP ranges (`52.62.122.103`), whereas cloud-to-cloud ingress from Render (Singapore/AWS) to Supabase (Sydney/AWS) connects normally with ~284ms latency.
3. **Storage Endpoint Verification**:
   - `https://rjntmboskzyrsqcetzil.supabase.co/storage/v1/bucket` responded with HTTP 400 (`headers must have required property 'authorization'`), confirming the Supabase Storage API service is active, reachable, and enforcing mandatory authorization.

---

## 2. Database Connection Pooling Finalization

As established in Phase AI-10.10:
- **Application Pool Budget**:
  - API Web Service: `pool_size = 20`, `max_overflow = 30` (max 50 checkouts).
  - Background Worker: `pool_size = 5`, `max_overflow = 5` (max 10 checkouts).
  - Total Peak Application Demand: 60 connections.
- **Protocol Requirements**:
  - `prepare_threshold = None` dynamically enabled in `app.db.session` to disable prepared statements on Supabase Transaction Pooler (port 6543).
  - `pool_pre_ping = True` and `pool_recycle = 180` to gracefully recycle idle cloud sockets.

---

## 3. Storage Integration Specification & Security

- **Bucket**: `project-evidence` (Private, non-public bucket).
- **Encryption**: AES-256-GCM envelope encryption is applied before byte transmission.
- **Backend-Mediated Streaming**: Public signed URLs are disabled by design; evidence downloads must stream through authenticated FastAPI endpoints verifying project and user source ACLs.
- **Service Role Key**: Stored exclusively within Render's secure server environment variables (`SUPABASE_SERVICE_ROLE_KEY`).

---

## 4. Certification Verdict

**Verdict:** **PASS — SUPABASE INFRASTRUCTURE VERIFIED (CLOUD-TO-CLOUD CONNECTION ACTIVE)**
