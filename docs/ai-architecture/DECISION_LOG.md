# Decision Log — The Handover Project Intelligence Engine

**Platform**: The Handover (Intelligent Project Knowledge Reconstruction & Handover Platform)  
**Document**: Architectural & Security Decision Log  
**Date**: November 2026  

---

## Record 001: Orchestration Mechanism Selection
- **Date**: 2026-11-17
- **Decision**: Implement a **Typed Lightweight State Graph Engine** natively in Python rather than introducing heavy external dependencies (such as CrewAI, AutoGen, or immediate LangGraph packages).
- **Reasoning**:
  1. Handover's modular monolith requires strict type-safety (Pydantic v2) and direct integration with existing SQLAlchemy sessions and `ProjectContext`.
  2. A native state machine provides deterministic transitions, bounded execution loops (max iterations, timeout guards), and seamless SSE event dispatch without hidden framework magic.
  3. The state machine primitives (`State`, `Node`, `Edge`, `Checkpoint`) will follow standard graph semantics, ensuring complete compatibility with LangGraph if migration is desired in the future.
- **Trade-offs**: Requires implementing the state dispatch and checkpoint logic directly, but avoids 40+ transitive dependencies, version conflicts with Pydantic v2.9, and uncontrolled agent background processes.

---

## Record 002: Durable Investigation Checkpoints & Database Strategy
- **Date**: 2026-11-17
- **Decision**: In Phase AI-1, persist investigation states and agent traces into `assistant_messages.structured_payload_json` and an in-memory/Redis state store, while preparing Alembic Migration `20261118_0021` for dedicated checkpoint tables (`assistant_investigations`, `assistant_agent_runs`, `assistant_tool_executions`).
- **Reasoning**:
  1. The database security gate strictly forbids unreviewed migrations to remote databases during active development.
  2. `structured_payload_json` is already an indexed PostgreSQL `JSONB` column on `assistant_messages` capable of storing arbitrary typed investigation trees and claim manifests.
  3. Dedicated tables will be introduced cleanly with full RLS policies under Migration 0021 after local verification.
- **Trade-offs**: Enables immediate AI-1 and AI-2 feature delivery without breaking database migration history or risking production downtime.

---

## Record 003: SSE Streaming Over WebSockets
- **Date**: 2026-11-17
- **Decision**: Use **Server-Sent Events (SSE)** via HTTP GET (`/investigations/{id}/events`) as the primary streaming transport, initiated by an HTTP POST (`/investigations`).
- **Reasoning**:
  1. SSE works seamlessly through standard HTTP reverse proxies, Cloudflare Tunnels, and Vercel edge networks without persistent two-way socket state or sticky session requirements.
  2. Standard `Last-Event-ID` header allows automatic stream resumption and replay if the client temporarily disconnects.
  3. Rejection of WebSocket eliminates stateful connection leaks and complex auth re-handshakes on proxy restarts.
- **Trade-offs**: Client cannot send user messages through the stream directly (must use REST POST endpoints), which is actually desirable for clean RESTful request authorization.

---

## Record 004: Dedicated Database Session in Background Async Tasks
- **Date**: 2026-11-17
- **Decision**: Investigation background tasks (`_execute_investigation_in_background`) spawned from the REST API endpoint must obtain their own database session from `app.state.session_factory` instead of reusing the request-scoped dependency session.
- **Reasoning**:
  1. FastAPI disposes and closes the request-scoped `Session` as soon as the HTTP 201 response is sent to the client.
  2. If a background task shares the closed session, subsequent flushes or commits raise `sqlalchemy.exc.IllegalStateChangeError: Method 'close()' can't be called here`.
  3. Providing a dedicated context-managed session to the background orchestrator ensures clean lifecycle management and isolated rollback semantics.
- **Trade-offs**: Slightly higher session pool checkout overhead, but fully prevents race conditions and closed session crashes.

---

## Record 005: Redis-Backed Durable Checkpoints for In-Flight Investigations
- **Date**: 2026-11-17
- **Decision**: In `InvestigationRuntimeRegistry`, back active `InvestigationState` and `SSEEventFrame` buffers with Redis keys (`investigation:{id}:state` and `investigation:{id}:events`) while retaining in-memory listener queues for SSE subscribers.
- **Reasoning**:
  1. Process memory is volatile; if FastAPI or uvicorn worker restarts during an investigation, in-flight execution states and event streams are lost.
  2. Redis lists (`rpush`/`lrange`) naturally preserve strict monotonically increasing sequence order and survive worker process restarts.
  3. Avoids executing unreviewed schema migrations to production/remote databases while providing sub-millisecond restart recovery.
- **Trade-offs**: Redis must be accessible for event replay after process restart (verified against local Redis 7.2 container).

---

## Record 006: Idempotent Consequential Tool Execution Gating
- **Date**: 2026-11-17
- **Decision**: Consequential tool execution in `ToolRegistry` enforces a SHA-256 fingerprint binding the tool ID, caller user ID, project ID, and canonical sorted JSON arguments.
- **Reasoning**:
  1. Once a consequential action (e.g. `approve_handover_task`) is approved by a human and executed, replaying the same approval or duplicated request must not re-execute the underlying handler.
  2. Prevents race conditions and duplicate approvals from executing operations twice.
- **Trade-offs**: If a user genuinely wishes to run the tool again later with identical arguments, a distinct invocation timestamp or run ID can be supplied in the request.


