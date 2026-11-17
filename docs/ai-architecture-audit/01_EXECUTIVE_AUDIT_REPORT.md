# Executive Audit Report — Phase AI-0: AI Architecture & Existing-System Audit

**Platform**: The Handover (Intelligent Project Knowledge Reconstruction & Handover Platform)  
**Document**: Document 1 of 7 — Comprehensive AI Architecture & Existing-System Audit  
**Phase**: Phase AI-0 (Audit & Integration Feasibility)  
**Date**: November 2026  
**Auditor Roles**: Principal AI Systems Architect, Senior Python Backend Engineer, AI Infrastructure Engineer, Application Security Auditor  
**Audit Scope**: Strict Read-Only Audit of Entire Repository, Models, Infrastructure, Gateway, and Database  

---

## 1. Executive Summary & Overall Architecture Readiness

The Handover platform is an intelligent knowledge reconstruction and transition management platform engineered to solve critical organizational memory loss when key personnel transition out of teams or projects.

This audit evaluates the platform's current technical state against the finalized **Project Intelligence Engine** architecture. That architecture requires a hybrid intelligence agent with tool execution, graph-based workflows, specialized dynamic agents, persistent memory across PostgreSQL and ChromaDB, and real-time streaming UX (SSE).

### Overall Architecture Readiness Score: **72% (Strong Foundation, Targeted AI Gaps)**

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                    THE HANDOVER PLATFORM: READINESS SCORECARD               │
├───────────────────────────────┬────────────┬────────────────────────────────┤
│ Subsystem                     │ Readiness  │ Implementation Status          │
├───────────────────────────────┼────────────┼────────────────────────────────┤
│ 1. Canonical Store & Models   │    92%     │ Verified (Alembic 0001–0020)   │
│ 2. Platform Auth & RBAC       │    95%     │ Verified (FastAPI JWT/Argon2id)│
│ 3. Fail-Closed Source ACLs    │    90%     │ Verified (Pre-retrieval gates) │
│ 4. Hybrid Retrieval & RRF     │    88%     │ Verified (PG FTS + ChromaDB)   │
│ 5. Local Inference Gateway    │    85%     │ Verified (HMAC + GPU lock)     │
│ 6. AI Assistant Engine        │    78%     │ Verified (Multi-mode reasoning)│
│ 7. Streaming & Real-time (SSE)│    15%     │ Missing (Synchronous POST only)│
│ 8. Multi-Agent Orchestration  │    20%     │ Partial / Conceptual only      │
│ 9. Tool Calling & Execution   │    10%     │ Missing (No tool registry)     │
│ 10. Background Worker State   │    80%     │ Verified (DB-backed lease lock)│
└───────────────────────────────┴────────────┴────────────────────────────────┘
```

The Handover possesses an unusually robust, enterprise-grade data foundation and permission infrastructure. The project is not starting from zero. In fact, **Module 5 (Project Knowledge Assistant)** already features a sophisticated prompt engine with epistemic validation, hallucination checks, multi-mode reasoning (`standard`, `deep_research`, `deep_think`, `deep_extract`), and a hardened local inference gateway.

However, the leap from the current single-turn structured Qwen3 8B reasoner to the **Phase AI Agentic Project Intelligence Engine** requires bridging critical architecture gaps:
1. Transforming the synchronous REST response model into **Server-Sent Events (SSE)**.
2. Introducing a **Deterministic Tool Registry** with strict parameter validation and human-approval gates.
3. Implementing **Agent Registry & Dynamic Instantiation (Option C)** without bloat.
4. Enabling **multi-step graph workflows (LangGraph or custom lightweight graph)** while respecting the single-GPU RTX 4050 (6GB VRAM) concurrency barrier.

---

## 2. Key Findings Across the 10 Audit Areas

### Area A: Repository Structure & Existing Modules
- **Modular Monolith**: Clean separation across `backend/app/api`, `core`, `db`, `models`, `repositories`, `schemas`, and `services`.
- **Infrastructure Isolation**: `infrastructure/docker` holds Docker Compose services (Postgres 16, ChromaDB, Redis 7.2); `infrastructure/gateway` contains an isolated FastAPI Inference Gateway for loopback GPU access.
- **Frontend Alignment**: Next.js 16 (App Router) in `frontend/src/` with a dedicated 3-column Assistant Workspace (`frontend/src/components/assistant/AssistantWorkspaceView.tsx`).

### Area B: Existing AI Assistant Implementation
- **Chat Endpoints**: Fully implemented in `backend/app/api/routes/assistant.py` (`POST /conversations`, `POST /conversations/{id}/messages`, `GET /conversations/{id}`, `POST /messages/{id}/feedback`, `GET /diagnostics/retrieval/{run_id}`).
- **Persistence**: PostgreSQL tables `assistant_conversations`, `assistant_messages`, `assistant_citations`, `assistant_retrieval_runs`, `assistant_feedback` backed by Alembic migration `20261113_0015_assistant_workspace.py`.
- **Epistemic Validation**: `backend/app/services/assistant_validation.py` enforces claim attribution, filters ungrounded citations, and prevents premature abstention (`insufficient_evidence` vs `partially_answered`).
- **Critical Weakness**: The assistant endpoint is strictly synchronous HTTP POST. Complex modes (`deep_research`, `deep_think`) take 15–45 seconds, risking HTTP timeouts on cloud proxies (e.g., Render 100s limit).

### Area C: Model Runtime & Inference Gateway
- **Primary LLM**: `qwen3:8b` via Ollama (`http://localhost:11434` or via Inference Gateway `http://127.0.0.1:8002`).
- **Embedding Model**: `nomic-embed-text` producing unified 768-dimensional vectors.
- **OCR Engine**: `glm-ocr:latest` via Ollama with sequential GPU locking.
- **GPU Protection**: `_OLLAMA_INFERENCE_LOCK` in Python backend and `asyncio.Semaphore(1)` in the Inference Gateway prevent RTX 4050 (6GB VRAM) out-of-memory faults.
- **Tool Calling Reality**: Qwen3 8B generates JSON schemas reliably when constrained by system prompts, but native Ollama function calling via the OpenAI-compatible endpoint is unbenchmarked in this repo.

### Area D: RAG & Knowledge Retrieval
- **Hybrid Fusion**: PostgreSQL `tsvector` full-text search combined with ChromaDB vector search using Reciprocal Rank Fusion (RRF, $k=60$) in `backend/app/services/retrieval.py`.
- **Pre-Retrieval Security Gate**: `SourceAccessPolicyService` in `backend/app/services/integrations/access_policy.py` checks user access before chunks or knowledge records enter prompt context.
- **Multi-Domain Expansion**: Query expansion generates 3–5 subqueries and hydrates candidates across Document Chunks, 8 Knowledge Domains, Relationship Graph records, and Project Timeline events.

### Area E: Project Context & Authorization Boundaries
- **FastAPI Auth**: Sole identity authority (Argon2id, JWT access token, SHA-256 HttpOnly refresh cookies).
- **Tenant & Project RBAC**: Enforced via `ProjectContext` dependency (`backend/app/services/rbac.py`).
- **Delegated Credentials**: Third-party source tokens (GitHub, Jira, Slack) are encrypted at rest with AES-256-GCM using `token_encryption_key`. Project membership does **not** grant automatic source access.

### Area F: Database & Memory Architecture
- **Canonical Store**: PostgreSQL 16 is authoritative for all application state, knowledge records, and audit logs.
- **Memory Gaps**: Current tables track conversational messages and retrieval logs, but lack tables for **Long-term Project Memory**, **Investigation Checkpoints**, **Agent Run State**, and **Tool Execution Audits**.

### Area G: Orchestration & Multi-Agent Architecture
- **Current State**: Single-turn pipeline (Classify → Retrieve → Reason → Validate → Persist).
- **Missing Capabilities**: Dynamic worker dispatch, multi-step agent scratchpads, iterative graph loops, tool execution sandbox, and approval workflows.

### Area E/H: Frontend & Streaming UX
- **Rich UI**: Frontend supports 3-column layout, response mode selector, claim badge expansion, and structured tables.
- **Streaming Gap**: Does not currently consume SSE streams. All state updates occur on complete message resolution.

### Area I: Cloud & Local Infrastructure Topology
- **Topology**: Render hosts cloud FastAPI backend; Windows 11 host runs Ollama, ChromaDB, and Redis.
- **Bridge**: `cloudflared` tunnel connects Render backend to `infrastructure/gateway` via mTLS / Cloudflare Access with Bearer token authentication.

### Area J: Testing & Verification Discipline
- **Extensive Test Suite**: Over 50 backend test files in `backend/tests/` verifying RBAC, retrieval, chunking, tenant isolation, and assistant prompt generation.
- **Missing Tests**: No end-to-end multi-agent execution tests, tool authorization tests, or automated benchmark suites for citation precision / recall.

---

## 3. Major Architectural Risks & Critical Vulnerabilities

| # | Risk / Vulnerability | Severity | Impact | Mitigation Strategy |
|---|---|---|---|---|
| **R1** | **Synchronous HTTP Timeout on Deep Operations** | **CRITICAL** | Investigations running >30s will trigger cloud 504 Gateway Timeouts. | Implement SSE streaming (`text/event-stream`) with incremental token and step dispatch. |
| **R2** | **RTX 4050 6GB VRAM Contention Under Multi-Agent Load** | **HIGH** | Spawning multiple concurrent agent LLM calls will trigger CUDA OOM or swap thrashing. | Maintain strict sequential GPU queue (`Semaphore(1)`), bound context window ($num\_ctx \le 8192$), and use lightweight worker models. |
| **R3** | **Unbounded Tool Execution & Privilege Escalation** | **HIGH** | Dynamic agents executing actions could bypass user RBAC or execute destructive operations. | Impose strict Read-Only default, user-context impersonation (no service-role inheritance), and mandatory human-in-the-loop approval. |
| **R4** | **Missing Agent Checkpoint / Resume Persistence** | **MEDIUM** | Network drops or user approval pauses during deep research would lose all progress. | Introduce `assistant_agent_runs` and `assistant_investigations` checkpoint tables in PostgreSQL. |
| **R5** | **Direct Source Ingestion Poisoning (Indirect Prompt Injection)** | **MEDIUM** | Malicious content in GitHub PRs, Jira tickets, or uploaded PDFs attempting prompt override. | Maintain epistemic delimiter boundaries (`<project_evidence>`), anti-injection system safeguards, and output validation. |

---

## 4. Key Architectural Recommendations & Go-Forward Decisions

1. **Adopt Custom Lightweight State Graph (LangGraph-Compatible Semantics)**: Rather than adding heavy external dependencies immediately, implement a clean, typed state machine in Python with explicit checkpointing to PostgreSQL. Ensure the design maps cleanly to LangGraph primitives if migration is desired later.
2. **Implement Agent Registry (Option C)**: Define immutable, registered agent specifications (`KnowledgeAgent`, `EngineeringAgent`, `DecisionAgent`, `SecurityAgent`, etc.) as code definitions, and instantiate temporary stateful execution instances with restricted scopes per task.
3. **Upgrade to SSE Streaming**: Replace the monolithic JSON POST response with an SSE pipeline emitting typed event frames (`agent_started`, `retrieval_progress`, `tool_executed`, `token_chunk`, `citation_emitted`, `approval_required`, `completed`).
4. **Enforce Zero-Privilege Agent Security**: Every agent run must execute strictly under the requesting user's `ProjectContext` and source access ACLs. Agents must never inherit administrative bypasses.
