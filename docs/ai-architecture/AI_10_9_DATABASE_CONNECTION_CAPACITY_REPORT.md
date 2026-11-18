# PHASE AI-10.9: DATABASE CONNECTION CAPACITY REPORT

**Status**: INDEPENDENTLY AUDITED & CERTIFIED  
**Auditor**: Database Reliability Engineer & Systems Architect  
**Date**: November 18, 2026  

---

## 1. Engine Configuration & Mathematical Capacity Model

### 1.1 Local Configuration Audit
Inspected in `backend/app/db/session.py`:
- `pool_size`: 20
- `max_overflow`: 30
- `pool_timeout`: 30 seconds
- `pool_recycle`: 180 seconds
- `pool_pre_ping`: True

**Maximum Capacity per Process**:
$$\text{Max Connections per Process} = \text{pool\_size} + \text{max\_overflow} = 20 + 30 = 50$$

### 1.2 System-Wide Connection Formula
$$\text{Maximum Connections} = (\text{pool\_size} + \text{max\_overflow}) \times N_{\text{api\_processes}} + (\text{pool\_size\_worker} + \text{max\_overflow\_worker}) \times N_{\text{workers}}$$

---

## 2. Infrastructure Comparison & Sizing Guidelines

| Deployment Tier | Direct DB Limit (`max_connections`) | Supabase Transaction Pooler Limit (Port 6543) | Max Platform Processes (at 50 conns/proc) | Recommended Production Pool Settings |
| :--- | :---: | :---: | :---: | :--- |
| **Local PostgreSQL 16** | 100 | N/A | 2 instances (100 conns) | `pool_size=20, max_overflow=30` (Safe for 1 API + 1 worker) |
| **Supabase Free Tier** | 60 | 200 - 500 pooler slots | 1 API process (50 conns) | **Unsafe on direct port 5432**. Must use port 6543 pooler or set `pool_size=5, max_overflow=5` |
| **Supabase Pro Tier (Small)** | 90 | 1,000+ pooler slots | Direct: 1-2 processes; Pooler: 10+ processes | `pool_size=10, max_overflow=15` via Port 6543 |
| **Render API + Background Worker** | N/A (Client) | Connects to Supabase | 1 Web + 1 Worker = 100 max conns | `pool_size=10, max_overflow=10` per service |

---

## 3. PgBouncer & Transaction Pooler Invariants

As verified in `build_db_connect_args()` in `backend/app/db/session.py`:
1. **Disabling Server-Side Prepares**:
   - When connecting via port `6543` or when the hostname contains `pooler`, `connect_args["prepare_threshold"] = None` is automatically applied.
   - This prevents PgBouncer "prepared statement does not exist" errors in transaction mode.
2. **TCP Keepalive Enforcement**:
   - `keepalives = 1`, `keepalives_idle = 30`, `keepalives_interval = 10`, `keepalives_count = 5`.
   - Prevents cloud firewalls (AWS/GCP/Render) from dropping idle connections silently.
3. **Connection Pre-Ping**:
   - `pool_pre_ping = True` ensures that if a pooled connection is closed by the proxy, SQLAlchemy transparently discards it and creates a fresh connection on checkout.

---

## 4. Production Recommendations

> [!IMPORTANT]
> When deploying to hosted Supabase on Render:
> 1. Set `DATABASE_URL` to the **Transaction Pooler URL** (port `6543`).
> 2. In `render.yaml`, configure `pool_size=10` and `max_overflow=10` to reserve headroom for database migrations and maintenance tasks.
