# Phase AI-1: Core Orchestration, Investigation Lifecycle & SSE

**Platform**: The Handover (Intelligent Project Knowledge Reconstruction & Handover Platform)  
**Document**: Phase AI-1 Deliverable — Architecture & Verification Report  
**Date**: November 2026  
**Status**: VERIFIED & COMPLETE  

---

## 1. Executive Summary

Phase AI-1 introduces the foundational execution engine for the Project Intelligence Engine. It deconstructs the legacy synchronous `ask_question()` procedural flow into a **modular, typed State Graph** and exposes a **W3C-compliant Server-Sent Events (SSE)** real-time streaming protocol.

### Key Deliverables Implemented & Verified:
1. **Typed State Machine (`InvestigationState`)**: Defined in `backend/app/services/ai/state.py` capturing plan steps, multi-source evidence manifests, agent findings, token consumption, and epistemic claims.
2. **Durable SSE Protocol (`SSEEventFrame`)**: Serializer in `backend/app/services/ai/events.py` delivering typed event frames with monotonic sequence numbering and full `Last-Event-ID` recovery support.
3. **In-Flight Runtime Registry (`InvestigationRuntimeRegistry`)**: Thread-safe in-memory/Redis state store in `backend/app/services/ai/registry.py` managing subscriber queues, event history buffering, and heartbeat keep-alives.
4. **Project Intelligence Orchestrator (`ProjectIntelligenceOrchestrator`)**: Discrete state machine in `backend/app/services/ai/orchestrator.py` executing:
   - `_node_classify_and_plan`: Technical entity recognition and plan formulation.
   - `_node_retrieve`: Permission-aware hybrid search across ChromaDB and PostgreSQL.
   - `_node_synthesize`: Qwen3 8B reasoning with streaming token deltas.
   - `_node_validate`: Epistemic anti-hallucination and claim-citation verification.
   - `_node_persist`: Canonical persistence to `assistant_messages` and `assistant_citations`.
5. **API Endpoints**:
   - `POST /api/v1/projects/{project_id}/assistant/conversations/{conversation_id}/investigations`: Creates an asynchronous investigation and returns tracking metadata.
   - `GET /api/v1/projects/{project_id}/assistant/investigations/{investigation_id}/events`: SSE stream with keep-alives and reconnection replay.
   - `GET /api/v1/projects/{project_id}/assistant/investigations/{investigation_id}`: Current state query.
6. **Frontend Integration**: Updated `frontend/src/lib/api.ts` with `api.assistant.startInvestigation()`.

---

## 2. Test Verification Evidence

- Executed `backend/tests/test_ai_orchestration_and_sse.py`:
  - `test_sse_event_frame_formatting`: **PASSED** (W3C standard compliance).
  - `test_investigation_runtime_registry_lifecycle`: **PASSED** (state registration, monotonic sequencing, subscriber fanout, `Last-Event-ID` replay).
- Executed `backend/tests/test_assistant_enhanced_modes.py`:
  - All 6 multi-mode reasoning regression tests: **PASSED** (100% backward compatibility maintained for existing endpoints).
