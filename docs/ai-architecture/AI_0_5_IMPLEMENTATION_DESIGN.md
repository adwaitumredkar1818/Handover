# AI-0.5 Implementation Design & Security Validation

**Platform**: The Handover (Intelligent Project Knowledge Reconstruction & Handover Platform)  
**Document**: Phase AI-0.5 Deliverable — Implementation Design & Security Architecture  
**Date**: November 2026  
**Status**: APPROVED FOR IMPLEMENTATION  

---

## 1. Verified Existing Architecture & Baseline

From our AST Graphify indexing (10,903 nodes) and code audit, the core Handover platform operates under these proven architectural contracts:

1. **Identity & Authentication**: Custom FastAPI JWT with Argon2id password hashing and SHA-256 HttpOnly refresh sessions.
2. **PostgreSQL RLS Architecture**:
   - Migration `0016_rls_hardening.py` enabled RLS across all 61 public base tables.
   - The application connects as `postgres` or `service_role` (which possess `BYPASSRLS=true` in PostgreSQL).
   - Non-BYPASSRLS roles (e.g. Supabase anon/authenticated) have **zero permissive policies**, enforcing default-deny at the PostgREST layer.
   - Application-level multi-tenancy and project isolation are strictly enforced by FastAPI dependencies (`ProjectContext` in `backend/app/services/rbac.py`).
   - **Crucial Security Rule**: We do **not** use `auth.uid()` for RLS policies, because Handover does not use Supabase Auth for platform identity.
3. **Pre-Retrieval Source ACLs**:
   - `SourceAccessPolicyService` in `backend/app/services/integrations/access_policy.py` filters evidence items based on verified source permissions before retrieval candidates can enter the context.
4. **Local Inference Gateway**:
   - Hardened loopback proxy on `127.0.0.1:8002` serializes model execution via `asyncio.Semaphore(1)` to safeguard the RTX 4050 (6GB VRAM) against concurrency collisions between Qwen3 8B, Nomic Embed, and GLM OCR.

---

## 2. Orchestration Architecture Decision: Native Typed State Graph

### 2.1 Why Native State Graph?
We evaluated LangGraph, AutoGen, and a native typed state graph.
**Decision**: Implement a **Native Typed State Graph Engine** (`backend/app/services/ai/orchestrator.py` & `backend/app/services/ai/state.py`).
- **Zero Heavyweight Dependencies**: No transitive dependency chaos with Pydantic v2.9 or Python 3.11.
- **Deterministic Transitions**: Explicit nodes with strict execution budgets, iteration limits ($\le 5$), and timeout guards.
- **Seamless SSE Dispatch**: State transitions directly emit typed SSE event frames to connected subscribers.
- **LangGraph Alignment**: Node signatures `(state: InvestigationState) -> InvestigationState` mirror standard graph primitives, allowing future migration if needed.

### 2.2 Typed Investigation State Container (`InvestigationState`)

```python
class InvestigationState(BaseModel):
    """Immutable, typed state container passed through graph execution nodes."""
    investigation_id: uuid.UUID
    conversation_id: uuid.UUID
    project_id: uuid.UUID
    organisation_id: uuid.UUID
    user_id: uuid.UUID
    user_role: str
    
    # User Request & Mode
    query: str
    response_mode: AssistantResponseMode = AssistantResponseMode.STANDARD
    
    # Graph Execution Tracking
    status: InvestigationStatus = InvestigationStatus.CREATED
    current_node: str = "init"
    iteration_count: int = 0
    max_iterations: int = 5
    plan_steps: list[InvestigationPlanStep] = Field(default_factory=list)
    
    # Telemetry & Budgets
    token_budget: int = 8192
    tokens_consumed: int = 0
    started_at: datetime
    updated_at: datetime
    
    # Multi-Source Evidence & Findings
    expanded_queries: list[str] = Field(default_factory=list)
    retrieved_candidates: list[RetrievedEvidenceCandidate] = Field(default_factory=list)
    citation_manifest: list[AssistantCitationResponse] = Field(default_factory=list)
    agent_findings: list[AgentFinding] = Field(default_factory=list)
    
    # Tool Execution & Approvals
    pending_tool_call: ToolCallRequest | None = None
    approval_required: bool = False
    
    # Final Validated Output
    validated_answer: ValidatedAssistantAnswer | None = None
    error_message: str | None = None
```

---

## 3. Durable Execution & Checkpointing Strategy

1. **In-Flight & Memory State**: An in-memory/Redis state registry (`InvestigationRuntimeRegistry`) tracks active running investigations, handles worker timeouts, and buffers live SSE events.
2. **PostgreSQL Persistence**:
   - The final investigation outcome and claim citations are persisted into `assistant_messages` and `assistant_citations`.
   - The full graph execution trace, plan steps, and agent findings are stored in `assistant_messages.structured_payload_json`.
   - Checkpoint state for paused or resumable investigations is persisted so browser refresh or network disconnect never loses investigation progress.

---

## 4. Server-Sent Events (SSE) Protocol Specification

### Endpoints
- `POST /api/v1/projects/{project_id}/assistant/conversations/{conversation_id}/investigations`: Creates an investigation, initializes the state graph, and returns `investigation_id`.
- `GET /api/v1/projects/{project_id}/assistant/investigations/{investigation_id}/events`: SSE subscription endpoint emitting `text/event-stream`.
- `POST /api/v1/projects/{project_id}/assistant/investigations/{investigation_id}/cancel`: Aborts active investigation.
- `POST /api/v1/projects/{project_id}/assistant/investigations/{investigation_id}/resume`: Resumes paused investigation with user feedback.

### Event Format
```text
event: <event_type>
id: <sequence_number>
data: {"event_id": "...", "investigation_id": "...", "timestamp": "...", "payload": {...}}
```

### Event Types
- `investigation_created`: Emitted when queued.
- `plan_created`: Initial investigation step list.
- `node_started` / `node_completed`: Step progress.
- `retrieval_started` / `retrieval_progress`: Candidate counts.
- `evidence_discovered`: High-scoring citation cards discovered.
- `agent_started` / `agent_completed`: Dynamic worker dispatch.
- `token_delta`: Incremental text streaming.
- `approval_required`: Emitted when a consequential tool pauses for user click.
- `final_answer`: Complete validated answer with epistemic status.
- `investigation_completed` / `investigation_failed`.

---

## 5. Security & Authorization Matrix

| Access Checkpoint | Enforcement Mechanism | Failure Behavior |
|---|---|---|
| **API Entry** | `require_project_permission("assistant.chat")` | `403 Forbidden` (`INSUFFICIENT_PROJECT_PERMISSIONS`) |
| **Conversation Access** | User ID match or `assistant.admin` permission | `403 Forbidden` (`FORBIDDEN_CONVERSATION`) |
| **Evidence Retrieval** | `SourceAccessPolicyService.can_user_access_evidence()` | Discarded pre-prompt; fail-closed |
| **Dynamic Agent Context** | Worker bound strictly to caller's `ProjectContext` | Worker cannot access unpermitted tools |
| **Tool Execution** | Deterministic argument validation & user impersonation | Blocked; consequential requires human approval |
| **GPU Protection** | `asyncio.Semaphore(1)` on Gateway + `_OLLAMA_INFERENCE_LOCK` | Sequential queueing; 30s timeout guard |

---

## 6. Implementation Gate Clearance

- [x] Verified existing architecture and database models.
- [x] Graphify dependency analysis complete.
- [x] Orchestrator and state machine architecture decided (Native Typed State Graph).
- [x] Durable worker and SSE streaming protocol designed.
- [x] Security gates and RLS boundaries established.
- **STATUS: APPROVED TO PROCEED TO PHASE AI-1.**
