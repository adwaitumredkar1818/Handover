# AI Implementation Roadmap — Phase AI-1 to Phase AI-7

**Platform**: The Handover (Intelligent Project Knowledge Reconstruction & Handover Platform)  
**Document**: Document 6 of 7 — Comprehensive AI Architecture & Existing-System Audit  
**Phase**: Phase AI-0 (Audit & Integration Feasibility)  
**Date**: November 2026  

---

## 1. Phased Architecture Evolution Overview

```text
Phase AI-0: Architecture & System Audit (Current Phase - Completed)
    │
    ▼
Phase AI-1: Core Orchestration, State Graph & SSE Streaming
    │
    ▼
Phase AI-2: Advanced RAG, Graph Traversal & Working Memory
    │
    ▼
Phase AI-3: Permanent Agent Registry & Dynamic Worker Factory (Option C)
    │
    ▼
Phase AI-4: Multi-Step Graph Workflows & Deep Interactive Research
    │
    ▼
Phase AI-5: Deterministic Tool Registry & Consequential Approval UI
    │
    ▼
Phase AI-6: Production Inference Hardening & Priority Gateway Queue
    │
    ▼
Phase AI-7: Systematic AI Evaluation, Benchmarking & Grounding Metrics
```

---

## 2. Phase-by-Phase Task Specifications

### Phase AI-1: Core Orchestration, State Graph & SSE Streaming

- **Goal**: Replace the monolithic synchronous POST execution turn with a modular state graph engine and real-time Server-Sent Events (SSE) streaming.
- **Affected Existing Files**:
  - `backend/app/api/routes/assistant.py` (Add SSE streaming endpoint `POST /projects/{id}/assistant/conversations/{id}/stream`)
  - `backend/app/services/assistant.py` (Deconstruct monolithic procedural turn into step functions)
  - `backend/app/services/llm.py` (Add streaming generator method `stream_chat()` to `StructuredLLMClient` and `OllamaLLMClient`)
  - `frontend/src/lib/api.ts` (Add `streamQuestion()` consuming SSE stream via `ReadableStream`)
  - `frontend/src/components/assistant/AssistantWorkspaceView.tsx` (Handle live token chunks, progress indicators, and status updates)
- **Proposed New Files**:
  - `backend/app/services/ai/orchestrator.py` (Central state graph coordinator)
  - `backend/app/services/ai/state.py` (Typed Pydantic state container `InvestigationState`)
  - `backend/app/services/ai/events.py` (SSE event frame definitions and serialization)
- **Dependencies**: None. Can be built on existing models and services.
- **Risk**: Moderate (ensuring SSE stream does not drop across Cloudflare Tunnel and proxies).
- **Acceptance Criteria**: Assistant responds with first token under 2.5s; frontend displays live status badges (`retrieving`, `reasoning`, `validating`).
- **Test Requirements**: Unit test for SSE event framing; integration test for streaming endpoint with simulated gateway responses.

---

### Phase AI-2: Advanced RAG, Graph Traversal & Working Memory

- **Goal**: Elevate retrieval precision across complex multi-hop project questions, integrate relationship graph traversal directly into semantic retrieval, and establish project memory.
- **Affected Existing Files**:
  - `backend/app/services/assistant_retrieval.py` (Upgrade candidate ranking, add entity-aware graph expansion)
  - `backend/app/services/retrieval.py` (Benchmark and tune RRF weights: semantic vs keyword)
  - `backend/app/services/relationship_coordinator.py` (Expose subgraph neighborhood extractor for query entities)
- **Proposed New Files**:
  - `backend/app/services/ai/memory.py` (Working memory manager: synthesizes, caches, and retrieves project-level context)
  - `backend/app/models/memory.py` (PostgreSQL model for persistent project memory records)
  - `infrastructure/database/migrations/versions/20261118_0021_ai_memory_and_investigations.py` (Alembic migration)
- **Dependencies**: Migration 0021 execution after database security gate clearance.
- **Risk**: Low-Moderate (schema migration and index tuning).
- **Acceptance Criteria**: Retrieval recall on multi-hop questions increases by $\ge 25\%$; citations include direct graph relationship context.
- **Test Requirements**: Verification tests for permission-filtered graph traversal; regression tests for `SourceAccessPolicyService`.

---

### Phase AI-3: Permanent Agent Registry & Dynamic Worker Factory (Option C)

- **Goal**: Implement Option C architecture—define immutable, approved agent blueprints and dynamically instantiate scoped temporary worker agents for specialized tasks.
- **Affected Existing Files**:
  - `backend/app/services/assistant_llm.py` (Refactor hardcoded prompt strings into modular agent definitions)
- **Proposed New Files**:
  - `backend/app/services/ai/agent_registry.py` (Static approved library: KnowledgeAgent, EngineeringAgent, DecisionAgent, SecurityAgent, etc.)
  - `backend/app/services/ai/agent_factory.py` (Dynamic factory instantiating temporary worker agents bound to user `ProjectContext`)
  - `backend/app/services/ai/agents/base.py` (Base agent class with scratchpad memory, tool boundaries, and token tracking)
  - `backend/app/services/ai/agents/knowledge_agent.py`
  - `backend/app/services/ai/agents/engineering_agent.py`
  - `backend/app/services/ai/agents/decision_agent.py`
  - `backend/app/services/ai/agents/security_agent.py`
- **Dependencies**: Phase AI-1 Orchestrator.
- **Risk**: Low (logical capabilities running inside the existing Python process).
- **Acceptance Criteria**: Central orchestrator successfully delegates sub-tasks to specialized dynamic workers; workers cannot exceed calling user's permissions.
- **Test Requirements**: Unit tests for `AgentRegistry` validation; test for dynamic worker context boundary enforcement.

---

### Phase AI-4: Multi-Step Graph Workflows & Deep Interactive Research

- **Goal**: Enable iterative, multi-hop deep investigations that can autonomously explore hypotheses, search iteratively, and pause for user clarification or approval.
- **Affected Existing Files**:
  - `backend/app/services/assistant.py` (Support pause/resume and investigation branching)
  - `frontend/src/components/assistant/AssistantWorkspaceView.tsx` (Add interactive plan tree visualizer and input pause prompts)
- **Proposed New Files**:
  - `backend/app/services/ai/workflows/graph.py` (State machine implementing cycle loops, branch conditions, and termination guards)
  - `backend/app/services/ai/workflows/deep_research.py` (Graph workflow for exhaustive multi-source investigations)
  - `backend/app/services/ai/workflows/deep_think.py` (Graph workflow for causal and dependency analysis)
- **Dependencies**: Phase AI-2 (Memory) and Phase AI-3 (Agents).
- **Risk**: Moderate (preventing infinite exploration loops; bound max iterations to 5).
- **Acceptance Criteria**: Assistant investigates multi-step query, updates plan in real time, and pauses cleanly when user clarification is requested.
- **Test Requirements**: Mock graph execution tests simulating multi-turn iterative expansion; timeout and max-depth termination guard tests.

---

### Phase AI-5: Deterministic Tool Registry & Consequential Approval UI

- **Goal**: Build a typed tool registry enabling the assistant to execute authorized project operations (read-only and approved consequential mutations).
- **Affected Existing Files**:
  - `backend/app/api/routes/assistant.py` (Add tool approval endpoints: `POST /investigations/{id}/approve` and `POST /investigations/{id}/reject`)
  - `frontend/src/components/assistant/AssistantWorkspaceView.tsx` (Add Action Approval Card with Confirm/Reject actions)
- **Proposed New Files**:
  - `backend/app/services/ai/tools/registry.py` (Tool catalog, Pydantic argument schemas, permission checks)
  - `backend/app/services/ai/tools/read_tools.py` (Codebase search, Jira issue lookup, relationship query, timeline fetch)
  - `backend/app/services/ai/tools/action_tools.py` (Handover item creation, verification finding review, tag update)
  - `backend/app/services/ai/tools/executor.py` (Secure sandbox executing tools strictly under caller's `ProjectContext`)
- **Dependencies**: Phase AI-4 Graph Workflows.
- **Risk**: High (potential unauthorized data mutation if permissions fail).
- **Acceptance Criteria**: Consequential actions halt execution and require explicit user click in UI; all tool executions logged to audit trail.
- **Test Requirements**: Comprehensive permission bypass tests (e.g. viewer trying to approve handover item via tool); argument fuzzing tests.

---

### Phase AI-6: Production Inference Hardening & Priority Gateway Queue

- **Goal**: Upgrade Local Inference Gateway to support prioritized requests (conversational assistant queries jump ahead of background batch OCR jobs) and ensure resilient tunnel reconnects.
- **Affected Existing Files**:
  - `infrastructure/gateway/main.py` (Implement priority queue with `asyncio.PriorityQueue` ahead of GPU semaphore)
  - `infrastructure/gateway/middleware.py` (Enforce separate rate limits for conversational vs batch traffic)
  - `backend/app/services/inference_gateway.py` (Add exponential backoff retry and circuit breaker logic)
- **Dependencies**: Local Windows 11 host access.
- **Risk**: Moderate (tuning queue latency under heavy OCR load).
- **Acceptance Criteria**: Conversational assistant queries start processing within 500ms even when background OCR worker is active.
- **Test Requirements**: Load test with concurrent simulated OCR and chat requests to verify no VRAM crash and priority ordering.

---

### Phase AI-7: Systematic AI Evaluation, Benchmarking & Grounding Metrics

- **Goal**: Establish continuous automated benchmark suites measuring retrieval precision/recall, citation accuracy, unsupported claim rate, and latency.
- **Affected Existing Files**:
  - `backend/tests/` (Add automated benchmark test runners)
- **Proposed New Files**:
  - `backend/tests/evaluations/benchmark_retrieval.py` (Computes Recall@K, MRR across synthetic & real query datasets)
  - `backend/tests/evaluations/benchmark_grounding.py` (Measures hallucination rate, ungrounded citation count, claim precision)
  - `backend/tests/evaluations/test_dataset.json` (Grounded query-evidence ground-truth evaluation pairs)
- **Dependencies**: Phase AI-1 through AI-6.
- **Risk**: Low (read-only test suite).
- **Acceptance Criteria**: Automated report generated showing $\text{Recall@10} \ge 85\%$, $\text{Citation Precision} \ge 98\%$, $\text{Unsupported Claim Rate} = 0\%$.
- **Test Requirements**: Automated CI pipeline execution on pull requests affecting AI services.
