# Critical Blockers & Prerequisite Gates — Phase AI-0

**Platform**: The Handover (Intelligent Project Knowledge Reconstruction & Handover Platform)  
**Document**: Document 7 of 7 — Comprehensive AI Architecture & Existing-System Audit  
**Phase**: Phase AI-0 (Audit & Integration Feasibility)  
**Date**: November 2026  

---

## 1. Prioritized Blocker Hierarchy

Before commencing implementation in Phase AI-1 and beyond, the following critical technical, security, and infrastructure blockers must be explicitly addressed.

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                       CRITICAL PREREQUISITE GATES                           │
├──────────────┬──────────────────────────────────┬──────────────┬────────────┤
│ Priority     │ Blocker Domain                   │ Severity     │ Gate Status│
├──────────────┼──────────────────────────────────┼──────────────┼────────────┤
│ 1. Gate 1    │ Synchronous Request Timeout (SSE)│ CRITICAL     │ BLOCKED    │
│ 2. Gate 2    │ RTX 4050 6GB VRAM Contention     │ HIGH         │ MITIGATED  │
│ 3. Gate 3    │ Database Security & Migration    │ HIGH         │ HELD       │
│ 4. Gate 4    │ Tool Authorization Sandbox       │ HIGH         │ BLOCKED    │
│ 5. Gate 5    │ Cloudflare Tunnel Availability   │ MEDIUM       │ MONITORED  │
└──────────────┴──────────────────────────────────┴──────────────┴────────────┘
```

---

## 2. Detailed Blocker Analysis & Resolution Plans

### Blocker 1: Synchronous Request Timeout on Deep Agent Operations (CRITICAL)
- **Domain**: Architecture & Network Infrastructure
- **Description**: Cloud hosting platforms (Render, Cloudflare Tunnel, Vercel) enforce strict HTTP proxy timeouts (typically 100 seconds on Render, 30–60 seconds on cloud edges). The existing assistant endpoint (`POST /projects/{id}/assistant/conversations/{id}/messages`) is entirely synchronous. When `deep_research` or multi-step agent investigations execute, total turnaround time will exceed 30–60 seconds, resulting in `504 Gateway Timeout` or aborted connections.
- **Why It Blocks Implementation**: We cannot introduce multi-agent investigations or multi-step graph exploration on top of the current synchronous HTTP POST pipeline without immediately causing network timeouts in production.
- **Required Resolution**:
  - Implement a Server-Sent Events (SSE) streaming endpoint (`POST .../conversations/{id}/stream`) as the **very first task of Phase AI-1**.
  - Dispatch heartbeat event frames (`event: ping`) every 5 seconds during long-running background reasoning steps to keep HTTP connections alive through proxies.

---

### Blocker 2: Hardware VRAM Contention on Local Host (RTX 4050 6GB) (HIGH)
- **Domain**: Infrastructure & Model Runtime
- **Description**: The local GPU environment is an NVIDIA RTX 4050 Laptop GPU with 6GB of VRAM. This GPU must host:
  - `qwen3:8b` (~5.2GB VRAM at 4-bit quant, or CPU-offloaded)
  - `nomic-embed-text` (~0.6GB VRAM)
  - `glm-ocr:latest` (~4.5GB VRAM)
  If the platform attempts to run parallel agent workers simultaneously or processes document OCR while an assistant query is running, the GPU driver will experience CUDA Out-of-Memory faults or aggressive system RAM paging (causing 10x latency spikes).
- **Current Mitigations**:
  - `_OLLAMA_INFERENCE_LOCK` in backend `app/services/ocr.py`.
  - `asyncio.Semaphore(1)` in `infrastructure/gateway/middleware.py`.
- **Remaining Risk & Resolution**:
  - Multi-agent orchestration must **never** instantiate parallel LLM calls to the local Ollama instance. Dynamic agents must execute sequentially or share a single prioritized inference queue.
  - Context size must remain strictly bounded: $num\_ctx \le 8192$.
  - In Phase AI-6, introduce a Priority Queue in the gateway ensuring conversational assistant turns jump ahead of background batch OCR tasks.

---

### Blocker 3: Database Security & Migration Freeze Gate (HIGH)
- **Domain**: Database & Security
- **Description**: A strict project rule mandates that no database migrations may be run or database state modified during this audit phase. Furthermore, any future tables added to PostgreSQL must pass rigorous Row-Level Security (RLS) and multi-tenant isolation audits.
- **Why It Blocks Implementation**: Adding new tables for investigation checkpoints (`assistant_investigations`) or dynamic agent logs (`assistant_agent_runs`) cannot occur until the active audit gate is officially closed and Migration 0021 is formally reviewed.
- **Interim Resolution**:
  - For Phase AI-1, the core orchestrator and state graph must utilize the existing `structured_payload_json` field on `assistant_messages` to store agent traces and investigation states. This enables immediate agent progress without requiring schema migrations on Day 1.
  - Formalize Migration 0021 only after Phase AI-1 completes.

---

### Blocker 4: Tool Authorization & Privilege Escalation Boundary (HIGH)
- **Domain**: Application Security
- **Description**: In an agentic system with tool execution, an agent running under one user's prompt might attempt to call tools that modify project data (e.g. approve a handover, edit project settings, or access another user's private repository).
- **Why It Blocks Implementation**: Tools must not be wired to LLM function calling until a zero-privilege execution sandbox is constructed.
- **Required Resolution**:
  - The tool execution runtime must strictly impersonate the calling user by taking the active `ProjectContext`.
  - Tools must be bifurcated into **Read-Only** (e.g., query graph, read search results) which can execute autonomously, and **Consequential** (e.g., change verification status, update settings, create handover records) which **must** halt execution and emit an approval event requiring an explicit user button click in the UI.

---

### Blocker 5: Cloudflare Tunnel & Local Gateway Availability (MEDIUM)
- **Domain**: Infrastructure & Availability
- **Description**: In cloud deployments (Render backend), conversational AI functionality is dependent on the local Windows 11 host being powered on, `cloudflared` running, and the Inference Gateway listening on `127.0.0.1:8002`.
- **Remaining Risk & Resolution**:
  - The cloud backend must gracefully handle gateway disconnections (`502 Bad Gateway`, `503 Service Unavailable`, or connection timeouts).
  - The UI must clearly indicate gateway health status to users with actionable instructions rather than hanging or displaying cryptic stack traces.

---

## 3. Prerequisite Sign-Off Checklist Before AI-1 Coding

- [x] Full codebase audit completed and verified read-only.
- [x] Zero source files, configurations, or database records modified.
- [x] Repository architecture map and component dependencies documented.
- [x] Existing AI Assistant and hybrid retrieval pipeline traced.
- [x] Hardware constraints (RTX 4050 6GB) verified and protected by gateway semaphore.
- [x] Security boundaries (platform auth vs delegated source ACLs) established.
- [ ] Technical approval of Phase AI-1 implementation plan (SSE + State Graph).
- [ ] Database security gate clearance for proposed schema additions (Migration 0021).
