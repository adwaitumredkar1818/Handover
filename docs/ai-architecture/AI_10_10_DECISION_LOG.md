# AI-10.10 — Decision Log

**Date:** 2026-11-18  
**Phase:** AI-10.10 Final Production Cutover Preparation  

---

## Decision 1: Physical Rehearsal in Isolated Database (`rehearsal_restore_db`)
- **Context:** AI-10.9 required an empirical verification of PostgreSQL physical backup and restore without endangering live production data or violating zero-fabrication rules.
- **Decision:** Generated a native custom binary archive (`pg_dump -F c`) of the live 17 MB `knowledge_handover` database and restored it into an isolated disposable database `rehearsal_restore_db` using `pg_restore`.
- **Outcome:** Full parity confirmed across all 65 tables, 65 RLS policies, revision `0020_graphs_and_contributors`, and exact row counts. Discarded `rehearsal_restore_db` cleanly.

---

## Decision 2: Driver-Level Prepared Statement Deactivation for Transaction Pooler
- **Context:** Supabase and PgBouncer in transaction pooling mode (port 6543) break when client drivers attempt to cache or reuse prepared SQL statements (`PREPARE`), as different transactions map to distinct physical backend processes.
- **Decision:** Confirmed and benchmarked Psycopg 3 configuration `prepare_threshold = None` dynamically triggered whenever port 6543 or "pooler" is present in the database connection URL.
- **Outcome:** Zero prepared statement collisions, safe multiplexing, and passing multi-threaded saturation stress test (50 queries, 25 threads, 0 leaks).

---

## Decision 3: ChromaDB Single-Collection Multi-Tenant Topology (Architecture B)
- **Context:** Past test failures attempted to invoke per-project collection creation in ChromaDB, which would create thousands of small HNSW graphs and degrade memory and search performance.
- **Decision:** Certified Architecture B: a unified collection per embedding model and version (`ipkrh_evidence_chunks_nomic-embed-text_v1`) with mandatory metadata filtering (`project_id`, `organisation_id`) at query time, backed by secondary PostgreSQL ACL revalidation before LLM prompting.
- **Outcome:** 100% vector isolation confirmed on live ChromaDB HTTP service with identical vector test probes.

---

## Decision 4: Zero Custom Domain Purchase Requirement for Cutover
- **Context:** The deployment architecture connects cloud Render API to local host GPU inference via Cloudflare Tunnel.
- **Decision:** Validated that Cloudflare Tunnel functions using free quick-tunnels (`*.trycloudflare.com`) or named internal tunnels without requiring a purchased custom domain. Deployment can proceed immediately.
- **Outcome:** Eliminates external blocking dependency on domain registrar transactions.
