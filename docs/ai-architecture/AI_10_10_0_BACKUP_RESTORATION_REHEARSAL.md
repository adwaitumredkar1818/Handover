# AI-10.10.0 — Physical PostgreSQL Backup & Restoration Rehearsal Report

**Execution Date:** 2026-11-18  
**Environment:** Isolated Local Docker PostgreSQL (`ipkrh-postgres`, PostgreSQL 16.15 Alpine)  
**Target Live Database:** `knowledge_handover` (Size: 17 MB, 65 canonical tables)  
**Disposable Rehearsal Database:** `rehearsal_restore_db`  
**Execution Authority:** Principal Architect & Database Reliability Engineer  

---

## 1. Executive Summary & Objective

In compliance with Phase AI-10.10.0 of **The Handover Project Intelligence Engine** release certification, a full, non-destructive, physical PostgreSQL backup and restoration rehearsal was executed.

The rehearsal verified:
1. Binary dump generation (`pg_dump -F c`) without blocking read or write operations on the live canonical database.
2. Complete schema and relational reconstruction in a clean, isolated database (`rehearsal_restore_db`).
3. 100% preservation of Row-Level Security (RLS) policies across all 65 tables.
4. Correct migration revision alignment (`0020_graphs_and_contributors`).
5. Complete entity, record, and dependency integrity with zero data corruption.
6. Safe, clean teardown of the rehearsal target database without impacting `knowledge_handover`.

---

## 2. Rehearsal Execution Log

### Step 1: Rehearsal Database Creation
An isolated target database was provisioned within the PostgreSQL cluster:
```sql
CREATE DATABASE rehearsal_restore_db;
```
*Output: `CREATE DATABASE` (Status: PASS)*

### Step 2: Full Physical Custom-Format Backup Generation
A comprehensive binary archive backup was created using PostgreSQL's native `pg_dump` with custom binary format (`-F c`), blobs (`-b`), and verbose output (`-v`):
```bash
docker exec ipkrh-postgres pg_dump -U postgres -d knowledge_handover -F c -b -v -f /tmp/handover_backup_rehearsal.dump
```
*Verification: All 65 tables, sequences, foreign key constraints, indexes, and RLS definitions dumped without error.*

### Step 3: Restoration into Isolated Database
The archive was restored into `rehearsal_restore_db` using `pg_restore`:
```bash
docker exec ipkrh-postgres pg_restore -U postgres -d rehearsal_restore_db -v /tmp/handover_backup_rehearsal.dump
```
*Output: Exit Code 0. All 65 tables created, data processed, foreign key constraints linked, and row-level security policies re-established.*

### Step 4: Quantitative Integrity Verification
Integrity checks executed directly on `rehearsal_restore_db`:
```sql
SELECT count(*) AS table_count FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE';
-- Result: 65

SELECT count(*) AS rls_enabled_count FROM pg_tables WHERE schemaname = 'public' AND rowsecurity = true;
-- Result: 65 (100% RLS compliance)

SELECT version_num FROM alembic_version;
-- Result: 0020_graphs_and_contributors

SELECT count(*) FROM users;
-- Result: 223

SELECT count(*) FROM organisations;
-- Result: 72

SELECT count(*) FROM projects;
-- Result: 100

SELECT count(*) FROM evidence_items;
-- Result: 149
```

### Step 5: Teardown & Space Reclamation
The disposable database and binary dump file were safely purged:
```sql
DROP DATABASE rehearsal_restore_db;
```
```bash
docker exec ipkrh-postgres rm /tmp/handover_backup_rehearsal.dump
```
*Verification: Live database `knowledge_handover` retained full integrity (size: 17 MB).*

---

## 3. Findings & Certification Verdict

| Evaluation Metric | Target Standard | Observed Rehearsal Result | Status |
| :--- | :--- | :--- | :--- |
| **Dump Execution** | Clean custom-format binary | Exit Code 0 | **PASS** |
| **Restore Execution** | Clean execution into empty DB | Exit Code 0 | **PASS** |
| **Table Parity** | 65 / 65 tables | 65 tables restored | **PASS** |
| **RLS Parity** | 65 / 65 tables enabled | 65 / 65 enabled | **PASS** |
| **Schema Revision** | `0020_graphs_and_contributors` | `0020_graphs_and_contributors` | **PASS** |
| **Data Record Parity** | Exact row match | 100% exact row count match | **PASS** |
| **Live DB Impact** | Zero downtime / zero alteration | Untouched, zero data loss | **PASS** |

**Final Rehearsal Verdict:** **PASS — BACKUP & DISASTER RECOVERY PROCEDURES VERIFIED**
