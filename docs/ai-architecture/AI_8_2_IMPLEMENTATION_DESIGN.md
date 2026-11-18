# AI-8.2 Implementation Design: Durability, Real Agent Orchestration & Live Frontend

**Platform**: The Handover (Intelligent Project Knowledge Reconstruction & Handover Platform)  
**Date**: November 2026  
**Status**: APPROVED DESIGN  

---

## 1. Existing System Architecture & Codebase Inspection

### 1.1 Source-of-Truth Modules
- `backend/app/services/ai/orchestrator.py`: Implements `ProjectIntelligenceOrchestrator` running 5-node graph (`classify_and_plan`, `retrieve`, `synthesize`, `validate`, `persist`).
- `backend/app/services/ai/registry.py`: `InvestigationRuntimeRegistry` currently holds state (`_states`), event buffers (`_event_history`), and subscriber queues (`_subscribers`) in process memory.
- `backend/app/services/ai/agent_registry.py` & `agent_factory.py`: Implements 10 approved blueprints and `DynamicAgentFactory`.
- `backend/app/services/ai/tools.py`: Implements `ToolRegistry` and sandboxed execution with RBAC gating and human approval enforcement.
- `backend/app/api/routes/assistant.py`: REST endpoints for conversations, synchronous `ask_question`, investigations (`POST .../investigations`), and SSE stream (`GET .../investigations/{id}/events`).
- `frontend/src/components/assistant/AssistantWorkspaceView.tsx`: Currently dispatches queries via `api.assistant.askQuestion` with a static pulse loader (`REASONING & RETRIEVING...`).

---

## 2. Confirmed Implementation Gaps & Objectives

1. **Process Durability**: When the backend process restarts during an investigation, in-flight state and event history are wiped from memory. We need PostgreSQL-persisted checkpoints and event frames, with safe startup recovery.
2. **Orchestrator Agent Dispatch**: `orchestrator.py` does not currently invoke `DynamicAgentFactory`. When complex investigations or deep research queries are received, the orchestrator must dynamically dispatch specialized agents (e.g. `engineering_agent`, `decision_agent`, `database_agent`), enforce concurrency and permission boundaries, collect `AgentFinding`s, and merge them into synthesis.
3. **Frontend Live SSE Integration**: `AssistantWorkspaceView.tsx` must switch from synchronous HTTP blocking to initiating investigations via `api.assistant.startInvestigation` and streaming live SSE events (planning, retrieval, agent dispatch, token deltas, validation, completion) with automatic reconnection.
4. **SSE Cursor & Event Reliability**: Fix cursor validation for `Last-Event-ID`. Distinguish valid resume, future/stale cursors (> latest), malformed strings, and provide an explicit resync/reset protocol.
5. **Approval Gating Durability**: Ensure consequential tool approval requests are recorded in PostgreSQL/state with immutable argument binding, preventing replay or double-execution across server restarts.

---

## 3. Data Architecture & Storage Strategy

### 3.1 Durable PostgreSQL Store (Canonical Record)
To preserve the canonical application database architecture without unreviewed remote schema changes during local testing:
- We implement durable checkpointing on PostgreSQL:
  - Table / Entity: `AssistantInvestigation` (or recorded in `assistant_messages` checkpoint payload and migration).
  - Checkpoint metadata: `investigation_id`, `conversation_id`, `project_id`, `user_id`, `status` (`CREATED`, `QUEUED`, `RUNNING`, `WAITING_FOR_USER`, `WAITING_FOR_APPROVAL`, `COMPLETED`, `FAILED`, `CANCELLED`), `current_stage`, `checkpoint_data` (JSONB), `error_message`, `created_at`, `updated_at`.
- Checkpoints are saved on every state graph node transition.

### 3.2 Redis (Event Transport & Locks)
- Investigation events are published to Redis pub/sub or stream `investigation:{id}:events` in addition to durable PostgreSQL checkpointing.
- Process locks protect GPU model execution (`_OLLAMA_INFERENCE_LOCK`).

---

## 4. Agent Dispatch Policy

When `query_classifier` detects multi-domain or deep technical investigation:
1. Orchestrator inspects classified intent (e.g. Architecture/Decisions -> `decision_agent`, Code/Commits -> `engineering_agent`, Schema/DB -> `database_agent`).
2. Orchestrator checks caller's permissions for the agent's required scopes.
3. Worker is instantiated via `DynamicAgentFactory.create_worker(agent_id=..., project_ctx=project_ctx)`.
4. Emits `agent_selected`, `agent_started`, `agent_completed` SSE events.
5. Worker executes bounded subtask under the single-thread inference semaphore lock.
6. Returns `AgentFinding` (claim text, confidence, citations).
7. Findings are validated and merged into `state.agent_findings` and provided to Node 3 synthesis.

---

## 5. Frontend Live Experience Design

In `AssistantWorkspaceView.tsx`:
1. When user clicks Send:
   - Optimistically append user message.
   - Set state `currentInvestigation = { id, stage: "starting", events: [], planSteps: [], activeAgent: null }`.
   - Call `api.assistant.startInvestigation(activeProject.id, targetConvId, { question, ... })`.
   - Open SSE connection: `const es = new EventSource(...)` or fetch streaming reader with `Last-Event-ID` tracking.
2. Render interactive investigation panel above/inside the message stream:
   - Progress bar / timeline: Planning -> Retrieval -> Agent Analysis -> Synthesis -> Validation.
   - Active agent indicator (e.g., "Engineering Agent analyzing pull requests...").
   - Live streaming token chunks.
3. On `investigation_completed`:
   - Replace active panel with completed `AssistantMessage` containing final answer, verified citations, and claims.
   - Close SSE connection cleanly.
4. On browser refresh or disconnect:
   - Reconnect with `Last-Event-ID: <lastId>`.
   - If stream closed, fetch `GET /investigations/{id}` for terminal state.

---

## 6. Safety, Verification & Regression Plan

- **Gateway Baseline**: Maintain 30/30 passed.
- **Local Real Services**: Execute live runs against local Postgres, ChromaDB, and Ollama `qwen3:8b`.
- **Zero Fabrication**: All citations and claims grounded in actual local files.
- **Non-Destructive**: Preserve all existing user tables and conversations.
