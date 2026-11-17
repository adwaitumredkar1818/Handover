# Graphify Codebase Analysis — The Handover AI Architecture

**Platform**: The Handover (Intelligent Project Knowledge Reconstruction & Handover Platform)  
**Document**: Section 3 Deliverable — Graphify Codebase Analysis  
**Date**: November 2026  
**Graph Snapshot**: Updated at `HEAD` (AST deterministic parse: 10,903 nodes, 35,150 edges, 394 communities)  
**Tooling**: Graphify CLI (`graphify update .`, `graphify query`) & graphify MCP server  

---

## 1. Graph Overview & System Complexity

The Handover platform's codebase was re-indexed with Graphify's tree-sitter AST parser:
- **Total Nodes**: 10,903
- **Total Edges**: 35,150
- **Total Communities**: 394
- **Extraction Mode**: 100% Deterministic AST Code Extraction across 318 active source files (Python 3.11 backend and TypeScript/React 19 frontend).

### High-Coupling Architectural Hubs (God Nodes)
From the graph traversal, the key central coordination nodes identified are:
1. `ProjectContext` (`backend/app/services/rbac.py`): The security foundation. Every API request, service call, and retrieval query depends on this principal container.
2. `Settings` (`backend/app/core/config.py`): Central Pydantic settings singleton injecting configuration across database, ChromaDB, Ollama, Redis, and security layers.
3. `ProjectKnowledgeAssistantService` (`backend/app/services/assistant.py`): The primary orchestrator for Module 5 (AI Assistant Area), directly coupling conversation repositories, query classifiers, retrieval services, LLM reasoners, and answer validators.
4. `HybridRetrievalService` (`backend/app/services/retrieval.py`): Core search hub linking ChromaDB collections and PostgreSQL full-text search (`tsvector`) via Reciprocal Rank Fusion ($k=60$).
5. `SourceAccessPolicyService` (`backend/app/services/integrations/access_policy.py`): The zero-trust gatekeeper evaluating fail-closed access to connected GitHub, Jira, and Slack sources.

---

## 2. Assistant Dependency Cluster (`ask_question` Lifecycle)

A BFS traversal of `ProjectKnowledgeAssistantService.ask_question()` reveals the following direct callers, callees, and dependencies:

```text
                               ┌────────────────────────────────────────────────────────┐
                               │       FastAPI Route: /assistant/conversations/         │
                               │          backend/app/api/routes/assistant.py           │
                               └───────────────────────────┬────────────────────────────┘
                                                           │
                                                           ▼
                               ┌────────────────────────────────────────────────────────┐
                               │          ProjectKnowledgeAssistantService              │
                               │            backend/app/services/assistant.py           │
                               └───────┬──────────────┬──────────────┬──────────────┬───┘
                                       │              │              │              │
                   ┌───────────────────┘              │              │              └──────────────────┐
                   ▼                                  ▼              ▼                                 ▼
   ┌──────────────────────────────┐    ┌──────────────────┐  ┌───────────────────────┐  ┌──────────────────────────────┐
   │ AssistantConversationRepo    │    │ AssistantQuery   │  │ AssistantRetrieval    │  │ AssistantLLMReasoner         │
   │ AssistantMessageRepo         │    │ Classifier       │  │ Service               │  │ (backend/app/services/       │
   │ (backend/app/repositories/)  │    │ (Query typing &  │  │ (Multi-source search  │  │  assistant_llm.py)           │
   └──────────────────────────────┘    │  entity extract) │  │  & SourceAccessPolicy)│  └──────────────┬───────────────┘
                                       └──────────────────┘  └───────────┬───────────┘                 │
                                                                         │                             ▼
                                                                         ▼                 ┌───────────────────────────┐
                                                             ┌───────────────────────┐     │ OllamaLLMClient / Gateway │
                                                             │ HybridRetrievalService│     │ (infrastructure/gateway)  │
                                                             │ (ChromaDB + PG FTS)   │     └──────────────┬────────────┘
                                                             └───────────────────────┘                    │
                                                                                                          ▼
                                                                                           ┌───────────────────────────┐
                                                                                           │ AssistantAnswerValidator  │
                                                                                           │ (Claim & Citation check)  │
                                                                                           └───────────────────────────┘
```

### Critical Request Lifecycle Findings:
1. **Procedural Tight Coupling**: In `services/assistant.py`, `ask_question()` synchronously executes lines 226 to 395 in one continuous thread without intermediate event yielding or state serialization.
2. **Repository Boundary**: Conversations, messages, citations, and retrieval telemetry are decoupled into clean repository patterns (`AssistantConversationRepository`, `AssistantMessageRepository`, `AssistantCitationRepository`, `AssistantRetrievalRunRepository`). These can be reused directly without schema changes.
3. **Validator Isolation**: `AssistantAnswerValidator.validate()` in `assistant_validation.py` is completely pure and stateless, taking `AssistantAnswerPayload` and `citations_manifest` and returning `ValidatedAssistantAnswer`. It can immediately serve as a terminal validation node in any graph orchestrator.

---

## 3. Database Relationship & Entity Graph

The database models in `backend/app/models/` form clear domain partitions:
- **Tenant & Workspace Partition**: `organisations` → `projects` → `project_members` → `users`.
- **Evidence & Document Partition**: `evidence_sources` → `evidence_items` → `evidence_chunks` (with full tsvector index).
- **Reconstructed Knowledge Partition**: `knowledge_items` (8 categories) → `knowledge_evidence_links` → `evidence_items`.
- **Graph & Timeline Partition**: `knowledge_entities` ↔ `knowledge_relationships`, `knowledge_timeline_events`.
- **Assistant Partition**: `assistant_conversations` → `assistant_messages` → `assistant_citations`, `assistant_retrieval_runs`, `assistant_feedback`.

### Safe Refactoring Boundaries:
- `assistant_messages.structured_payload_json` is an unconstrained PostgreSQL `JSONB` column. It already stores `claims`, `uncertainty`, `conflicts`, `research_report`, `deep_think`, and `deep_extract`.
- **Architectural Leverage**: We can store full multi-step agent scratchpads, node execution traces, and investigation plans directly inside `structured_payload_json` during Phase AI-1 without requiring an immediate database migration.

---

## 4. Frontend Component Graph

In `frontend/src/`:
- **Page Container**: `frontend/src/app/assistant/page.tsx` renders `AssistantWorkspaceView`.
- **Workspace Hub**: `frontend/src/components/assistant/AssistantWorkspaceView.tsx` (1,230 lines) manages:
  - 3-column responsive layout (Thread History | Main Answer Canvas | Evidence Detail Panel).
  - Mode toggle: `standard`, `deep_research`, `deep_think`, `deep_extract`.
  - API dispatch via `api.assistant.askQuestion()` in `frontend/src/lib/api.ts`.
- **Streaming Refactoring Point**:
  - `frontend/src/lib/api.ts` line 2006: `askQuestion()` uses standard `fetch()` returning a Promise.
  - Adding `streamInvestigation()` via Server-Sent Events (`ReadableStream` / `fetch-event-source`) cleanly attaches to `AssistantWorkspaceView.tsx` without breaking the non-streaming fallback.

---

## 5. Circular Dependency & Coupling Analysis

- **Circular Dependencies**: Zero circular imports found in `backend/app/services/assistant*`. The service dependencies flow strictly downward:
  `api/routes/assistant.py` → `services/assistant.py` → `services/assistant_{query,retrieval,llm,validation}.py` → `repositories/assistant.py` → `models/assistant.py`.
- **Gateway Decoupling**: The Inference Gateway in `infrastructure/gateway/` is completely standalone and communicates with the backend solely over HTTP loopback (`127.0.0.1:8002`) with HMAC token authentication.
