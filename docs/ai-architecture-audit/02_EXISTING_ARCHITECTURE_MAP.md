# Existing Architecture Map — Phase AI-0

**Platform**: The Handover (Intelligent Project Knowledge Reconstruction & Handover Platform)  
**Document**: Document 2 of 7 — Comprehensive AI Architecture & Existing-System Audit  
**Phase**: Phase AI-0 (Audit & Integration Feasibility)  
**Date**: November 2026  

---

## 1. Actual Repository Structure Map

```text
The Handover/
├── backend/                              # Core Python 3.11 FastAPI Modular Monolith
│   ├── app/
│   │   ├── api/                          # Routing, endpoints, dependency injection
│   │   │   ├── deps.py                   # FastAPI Depends (auth, rbac, db, llm, retrieval)
│   │   │   ├── routes/                   # Route controllers by domain
│   │   │   │   ├── assistant.py          # Assistant chat, conversations, feedback
│   │   │   │   ├── auth.py               # Platform identity, JWT, sessions
│   │   │   │   ├── evidence.py           # Evidence upload, triage, extraction status
│   │   │   │   ├── handover.py           # Handover cases, packages, readiness
│   │   │   │   ├── integrations.py       # GitHub/Jira/Slack OAuth & PAT connectors
│   │   │   │   ├── knowledge.py          # 8-domain reconstructed knowledge items
│   │   │   │   ├── relationships.py      # Relationship graph explorer API
│   │   │   │   ├── retrieval.py          # Direct hybrid retrieval search endpoints
│   │   │   │   ├── sources.py            # Connected sources management
│   │   │   │   └── verification.py       # Human verification center queue & conflicts
│   │   │   └── v1/router.py              # Root API v1 routing aggregate
│   │   ├── core/                         # Global configuration, security, caching
│   │   │   ├── config.py                 # Pydantic Settings loaded from .env
│   │   │   ├── exceptions.py             # Custom exception hierarchy
│   │   │   └── cache/                    # Redis 7.2 client & LRU fallback
│   │   ├── db/                           # Database session & base declarative models
│   │   ├── models/                       # SQLAlchemy 2.x declarative entity models
│   │   │   ├── assistant.py              # Conversations, messages, citations, retrieval runs
│   │   │   ├── evidence.py               # Evidence items, document chunks, OCR metadata
│   │   │   ├── knowledge.py              # 8-domain knowledge items & evidence links
│   │   │   ├── relationship.py           # Entities, relationships, timeline events
│   │   │   └── verification.py           # Verification cases, conflicts, decisions
│   │   ├── repositories/                 # Data access repositories (CRUD, queries)
│   │   │   └── assistant.py              # Conversation, message, citation repos
│   │   ├── schemas/                      # Pydantic v2 request/response contracts
│   │   │   └── assistant.py              # QuestionRequest, AssistantAnswerResponse, modes
│   │   └── services/                     # Business logic and domain orchestrators
│   │       ├── assistant.py              # ProjectKnowledgeAssistantService (Controller)
│   │       ├── assistant_llm.py          # Prompt engineering, Qwen3 reasoner
│   │       ├── assistant_query.py        # Query classifier & entity extraction
│   │       ├── assistant_retrieval.py    # Multi-source permission-filtered retriever
│   │       ├── assistant_validation.py   # Claim validation, epistemic gate, anti-hallucination
│   │       ├── llm.py                    # OllamaLLMClient, GatewayLLMAdapter, protocol
│   │       ├── ocr.py                    # GLM OCR service & single-GPU lock
│   │       ├── retrieval.py              # HybridRetrievalService (RRF fusion)
│   │       ├── vector_store.py           # ChromaDB client & collection manager
│   │       └── integrations/access_policy.py # Fail-closed source ACL evaluator
│   └── tests/                            # Over 50 unit, integration & regression tests
├── frontend/                             # Next.js 16 (React 19, TypeScript strict mode)
│   ├── src/
│   │   ├── app/                          # Next.js App Router pages
│   │   │   ├── assistant/page.tsx        # Standalone Project Knowledge Assistant page
│   │   │   ├── projects/[id]/            # Project-scoped workspace layouts
│   │   │   │   ├── evidence/page.tsx     # Evidence Center
│   │   │   │   ├── intelligence/page.tsx # Knowledge Intelligence
│   │   │   │   ├── relationships/page.tsx# Relationship Explorer
│   │   │   │   └── handover/page.tsx     # Handover Workspace
│   │   ├── components/                   # UI components (shadcn/ui, Tailwind CSS v4)
│   │   │   └── assistant/
│   │   │       ├── AssistantWorkspaceView.tsx # Canonical 3-column AI Assistant layout
│   │   │       └── AssistantWorkspace.tsx     # Wrapper export
│   │   ├── context/LiveAppContext.tsx    # Global project, org, user state context
│   │   └── lib/api.ts                    # Strongly typed API client methods
├── infrastructure/
│   ├── database/migrations/versions/     # 20 Alembic migrations (0001 to 0020)
│   ├── docker/docker-compose.yml         # Local Postgres 16, ChromaDB, Redis 7.2
│   └── gateway/                          # Hardened Local Inference Gateway
│       ├── main.py                       # Loopback FastAPI service (127.0.0.1:8002)
│       ├── auth.py                       # Bearer token HMAC timing-resistant auth
│       ├── middleware.py                 # GPU Semaphore(1) lock, body size bounds
│       └── services/                     # Ollama & ChromaDB forwarders
└── docs/ & documentation/                # Architecture specs, roadmaps, security audits
```

---

## 2. Existing Component Responsibilities & Dependencies

| Module | Exact Path | Core Responsibility | Key Dependencies | Primary Consumers | Status | Recommendation |
|---|---|---|---|---|---|---|
| **Assistant Route** | `backend/app/api/routes/assistant.py` | Exposes REST endpoints for conversations, turns, feedback, diagnostics | FastAPI, `ProjectContext`, `assistant_service` | Frontend `frontend/src/lib/api.ts` | Verified | **Extend**: Add SSE streaming endpoint `POST .../stream` |
| **Assistant Orchestrator** | `backend/app/services/assistant.py` | Coordinates turn pipeline (History → Query → Retrieval → LLM → Validation → Persist) | `assistant_query`, `assistant_retrieval`, `assistant_llm`, `assistant_validation` | `api/routes/assistant.py` | Verified | **Refactor**: Decouple monolithic turn into graph state steps |
| **LLM Reasoner** | `backend/app/services/assistant_llm.py` | Builds system prompts for 4 modes, formats context tags, calls LLM client | `StructuredLLMClient`, Qwen3 prompts, Pydantic schemas | `services/assistant.py` | Verified | **Extend**: Add tool calling prompt schema & agent system prompts |
| **Retrieval Engine** | `backend/app/services/assistant_retrieval.py` | Multi-source query expansion, pre-retrieval ACL filtering, candidate hydration | `HybridRetrievalService`, `SourceAccessPolicyService`, SQLAlchemy | `services/assistant.py` | Verified | **Reuse & Extend**: Add agent-specific scoped retrieval filters |
| **Answer Validator** | `backend/app/services/assistant_validation.py` | Anti-hallucination checks, claim citation validation, epistemic status resolution | Pydantic schemas, Citation manifest | `services/assistant.py` | Verified | **Reuse**: Indispensable epistemic safeguard |
| **LLM Client Protocol** | `backend/app/services/llm.py` | Structured JSON generation, Ollama direct adapter, Gateway client adapter | `httpx`, Pydantic, JSON parser | `services/assistant_llm.py`, `extraction.py` | Verified | **Extend**: Add streaming token generator (`stream_chat`) |
| **Inference Gateway** | `infrastructure/gateway/main.py` | Loopback GPU reverse proxy, concurrency queue semaphore, telemetry | FastAPI, `asyncio.Semaphore(1)`, Ollama, ChromaDB | Cloud backend via `cloudflared` | Verified | **Reuse**: Protects RTX 4050 6GB VRAM from crash |
| **Access Policy** | `backend/app/services/integrations/access_policy.py` | Fail-closed ACL verification for GitHub, Jira, Slack, Uploads | SQLAlchemy, `EvidenceItem`, `ProjectContext` | `assistant_retrieval.py`, `evidence.py` | Verified | **Reuse**: Mandatory zero-privilege enforcement |

---

## 3. End-to-End Request Lifecycle (Current Implementation)

```text
1. Frontend User Action:
   User selects Response Mode (e.g., DEEP_RESEARCH) and submits query in `AssistantWorkspaceView.tsx`.
                          │
                          ▼ (HTTP POST JSON)
2. API Layer & Dependency Injection:
   `POST /api/v1/projects/{project_id}/assistant/conversations/{id}/messages`
   - `deps.require_project_permission("assistant.chat")` verifies JWT and project membership.
   - Resolves `ProjectContext` (Organisation, Project, Principal User, Role).
                          │
                          ▼
3. Conversation & Message Staging:
   `ProjectKnowledgeAssistantService.ask_question()`:
   - Validates conversation ownership (user can only access their own conversations).
   - Persists user prompt message into PostgreSQL table `assistant_messages`.
   - Hydrates past 6 turns from `assistant_messages` for conversation history context.
                          │
                          ▼
4. Query Classification & Expansion:
   `AssistantQueryClassifier.classify(question)`:
   - Extracts technical identifiers (PRs, Jira keys, commit hashes, filenames).
   - Generates 3–5 expanded subqueries and assigns `AssistantQueryType`.
                          │
                          ▼
5. Permission-Aware Multi-Source Retrieval:
   `AssistantRetrievalService.retrieve()`:
   - Step A: Executes multi-pass hybrid search (ChromaDB semantic + PG `tsvector`) with RRF fusion ($k=60$).
   - Step B: Fetches 8-domain reconstructed `KnowledgeItem` records matching keywords.
   - Step C: Traverses `KnowledgeRelationship` (graph) and `KnowledgeTimelineEvent` records.
   - Step D (CRITICAL SECURITY): Evaluates `SourceAccessPolicyService.can_user_access_evidence()`.
             Fail-closed: Any candidate linked to unauthorized private sources is discarded.
   - Step E: Assembles `<project_evidence id="S#">` XML prompt block and builds citation manifest.
                          │
                          ▼
6. Structured LLM Generation:
   `AssistantLLMReasoner.generate_answer()`:
   - Selects system prompt based on mode (`STANDARD`, `DEEP_RESEARCH`, `DEEP_THINK`, `DEEP_EXTRACT`).
   - Dispatches structured generation request to `StructuredLLMClient` (via Inference Gateway or Ollama).
   - Single-GPU lock ensures exclusive access to Qwen3 8B.
                          │
                          ▼
7. Citation & Epistemic Validation:
   `AssistantAnswerValidator.validate()`:
   - Strips ungrounded citations (cites `[S9]` when only `[S1..S4]` exist).
   - Verifies claim badges against supporting excerpts.
   - Computes final status: `ANSWERED`, `PARTIALLY_ANSWERED`, or `INSUFFICIENT_EVIDENCE`.
                          │
                          ▼
8. Persistence & Response Assembly:
   - Records retrieval telemetry in `assistant_retrieval_runs`.
   - Persists assistant turn in `assistant_messages` (with `structured_payload_json`).
   - Persists validated citations in `assistant_citations`.
   - Returns monolithic `AssistantAnswerResponse` to Next.js frontend.
```

---

## 4. Infrastructure Topology

```text
┌──────────────────────────────────────────────┐
│             Vercel / Cloud CDN               │
│         Next.js 16 Web Application           │
└──────────────────────┬───────────────────────┘
                       │ HTTPS (REST API)
                       ▼
┌──────────────────────────────────────────────┐
│           Render Cloud Backend               │
│       FastAPI Modular Monolith (Web)         │
│  - Platform Auth (JWT / Argon2id)            │
│  - RBAC & ProjectContext Enforcement         │
│  - Fail-Closed Source ACL Gatekeeper         │
│  - Supabase PostgreSQL 16 (Canonical Store)  │
└──────────────────────┬───────────────────────┘
                       │ HTTPS via Cloudflare Tunnel
                       │ (mTLS / CF Access Service Token + Bearer Token)
                       ▼
┌──────────────────────────────────────────────┐
│       Windows 11 Local Host (RTX 4050 6GB)   │
│                                              │
│  ┌────────────────────────────────────────┐  │
│  │ cloudflared Tunnel Daemon              │  │
│  └───────────────────┬────────────────────┘  │
│                      │ Loopback (127.0.0.1)  │
│                      ▼                       │
│  ┌────────────────────────────────────────┐  │
│  │ Local Inference Gateway (:8002)        │  │
│  │ - Constant-time HMAC Auth Verification │  │
│  │ - asyncio.Semaphore(1) GPU Lock        │  │
│  │ - 1MB Body / Context Truncation Guards │  │
│  └───────┬──────────────────┬─────────────┘  │
│          │                  │                │
│          ▼                  ▼                │
│  ┌───────────────┐  ┌─────────────────────┐  │
│  │ Ollama Server │  │ ChromaDB HTTP (:8001)│  │
│  │ (:11434)      │  │ Docker Container    │  │
│  │ - Qwen3 8B    │  │ Project-Isolated    │  │
│  │ - Nomic Embed │  │ Vector Collections  │  │
│  │ - GLM OCR     │  └─────────────────────┘  │
│  └───────────────┘                           │
└──────────────────────────────────────────────┘
```
