# PHASE AI-8.3 — ARCHITECTURE INTEGRITY AUDIT & ACCEPTANCE GATE REPORT
**Date**: November 18, 2026  
**Project**: The Handover — Intelligent Project Knowledge Reconstruction & Handover Platform  
**System**: Project Intelligence Engine  
**Auditor**: Principal AI Systems Architect, Senior Application Security Auditor & Database Architect  
**Initial Gate Verdict**: **CONDITIONAL PASS (REMEDIATION REQUIRED BEFORE FINAL PASS)**

---

## 1. Executive Summary & Audit Mandate

Following the completion of Phase AI-8.2, this independent engineering audit was conducted to verify that:
1. The implemented Project Intelligence Engine strictly adheres to the approved architecture and governance rules defined in `AGENTS.md`.
2. PostgreSQL remains the canonical source of truth for all structured data, investigation state, and audit logs.
3. Consequential tool execution and approvals are strictly atomic, idempotent, and resilient against server restarts and race conditions.
4. Dynamic agent orchestration supports bounded multi-agent collaboration with complete evidence grounding and context isolation.
5. Server-Sent Events (SSE) provide gapless event streaming with robust cursor validation (`Last-Event-ID`).
6. Security boundaries (RBAC, ProjectContext, tenant isolation) and inference protections (Ollama concurrency semaphore on RTX 4050 6GB VRAM) are enforced without bypasses.

---

## 2. Audit Findings Matrix

| Audit Area | Subsystem | Initial Status | Defect Severity | Core Finding / Architecture Vulnerability |
| :--- | :--- | :--- | :--- | :--- |
| **Audit A** | Storage Boundary & Durability | **DEFICIENT** | **CRITICAL** | `InvestigationRuntimeRegistry` uses memory and Redis keys (`investigation:{id}:state` and `investigation:{id}:events`) for in-flight state and event replay buffer. In-flight investigations and events are not checkpointed into PostgreSQL until the terminal node `_node_persist`. If Redis restarts or evicts keys during an active investigation, active state and replay history are permanently lost. |
| **Audit B** | Tool Execution & Idempotency | **DEFICIENT** | **CRITICAL** | `ToolRegistry._executed_approvals` is implemented as an in-memory Python `set[str]`. This set is cleared on any backend process restart and is not shared across multi-process workers. Concurrent or replayed requests can re-execute consequential actions (e.g. archiving repositories, modifying project roles). |
| **Audit C** | Dynamic Agent Dispatch | **PARTIAL** | **HIGH** | `ProjectIntelligenceOrchestrator._node_delegate_agents` selects at most **one** specialized agent via an `if-elif` chain. Complex queries spanning multiple architectural facets (e.g. database schema + ADR decisions) only execute the first matching agent. Multi-agent delegation policy needs to support bounded multi-agent dispatch (max 2 agents) sequentially under GPU inference lock. |
| **Audit D** | SSE & Frontend Durability | **PASS WITH OBSERVATION** | **MEDIUM** | SSE route correctly emits `cursor_reset` for malformed cursors and `cursor_error` for future cursors. In the frontend, `AssistantWorkspaceView.tsx` creates a synthetic ID (`inv-msg-${invId}`) for the final assistant message upon investigation completion; while working, thread reloads should ensure conversation messages fetched from backend reconcile cleanly with investigation IDs. |
| **Audit E** | Security, RBAC & Isolation | **VERIFIED PASS** | **NONE** | All API routes enforce `require_project_permission`. All tool handlers receive caller's `ProjectContext`. Tenant scoping is validated across gateway (30/30 tests passing). |
| **Audit F** | Inference & Hardware Protection | **VERIFIED PASS** | **NONE** | Gateway and LLM client enforce `_OLLAMA_INFERENCE_LOCK` / cross-process semaphore(1). RTX 4050 6GB VRAM is safeguarded against concurrent model contention. |
| **Audit G** | Quality, Tests & Build | **VERIFIED PASS** | **NONE** | Gateway tests (30/30 passed), Backend AI tests (11/11 passed), Next.js frontend builds with 0 errors across 69 routes. |

---

## 3. Detailed Technical Defect Analysis

### Defect 1 (Critical): Tool Idempotency Bypassed on Restart (`backend/app/services/ai/tools.py`)
- **Location**: `ToolRegistry._executed_approvals: set[str] = set()`
- **Vulnerability**: 
  1. If a consequential tool (e.g., project archiving, access revocation) is approved and executed, its SHA-256 fingerprint is recorded only in process memory.
  2. If the FastAPI process restarts or if multiple worker processes handle requests, a duplicate approval payload with the same fingerprint bypasses the gate and executes again.
  3. No immutable audit log entry was being generated upon consequential tool execution in `ToolRegistry`.
- **Mandatory Remediation**:
  - Replace the in-memory set with atomic Redis `SET NX` with TTL (e.g. 7 days).
  - Persist an immutable `AuditLog` entry via `AuditService` in PostgreSQL capturing the approval fingerprint, user ID, project ID, tool ID, and execution outcome.

### Defect 2 (Critical): In-Flight Checkpointing Bypasses PostgreSQL (`backend/app/services/ai/registry.py`)
- **Location**: `InvestigationRuntimeRegistry`
- **Vulnerability**:
  - The registry holds in-flight state and events exclusively in memory and Redis.
  - While PostgreSQL is updated upon investigation completion in `_node_persist`, intermediate nodes (`classify_and_plan`, `retrieve_evidence`, `delegate_agents`, `synthesize_findings`) do not record durable checkpoints in PostgreSQL.
  - If Redis fails, in-flight state cannot be recovered.
- **Mandatory Remediation**:
  - Store durable checkpoints in PostgreSQL via an investigation checkpoint mechanism or structured investigation state updates.
  - Ensure `InvestigationRuntimeRegistry` uses Redis as an ephemeral acceleration and pubsub bus, with fallback to persistent database storage.

### Defect 3 (High): Multi-Domain Query Dispatches Only Single Agent (`backend/app/services/ai/orchestrator.py`)
- **Location**: `ProjectIntelligenceOrchestrator._node_delegate_agents`
- **Vulnerability**:
  - Queries containing both "architecture decisions" and "database schema" only match the first `elif` condition (`decision_agent`), completely skipping the `database_agent`.
  - The orchestrator claims to support multi-agent collaboration, but structurally restricted execution to `n=1`.
- **Mandatory Remediation**:
  - Update `_node_delegate_agents` to evaluate multiple domain keywords and select up to **two** specialized agents (e.g. `[decision_agent, database_agent]`).
  - Sequentially execute each agent worker to respect the single-GPU concurrency lock.
  - Collect and attribute `AgentFinding`s from each worker into `state.agent_findings`.
  - Include all accepted agent findings in the prompt for `_node_synthesize`.

---

## 4. Remediation Plan

1. **Fix Audit B**: Atomic tool idempotency via Redis distributed lock + PostgreSQL audit log logging in `backend/app/services/ai/tools.py`.
2. **Fix Audit C**: Bounded multi-agent dispatch in `backend/app/services/ai/orchestrator.py`.
3. **Fix Audit A**: Canonical checkpoint persistence in `backend/app/services/ai/registry.py` and `backend/app/services/ai/orchestrator.py`.
4. **Empirical Verification**:
   - Run unit and integration tests verifying idempotency rejection, multi-agent dispatch, and checkpointing.
   - Run full regression suites (Gateway 30/30, Backend AI 11/11, Next.js build).
5. **Issue Final Acceptance Gate Verdict**.
