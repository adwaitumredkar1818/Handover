# Existing vs Proposed Architecture Matrix — Phase AI-0

**Platform**: The Handover (Intelligent Project Knowledge Reconstruction & Handover Platform)  
**Document**: Document 3 of 7 — Comprehensive AI Architecture & Existing-System Audit  
**Phase**: Phase AI-0 (Audit & Integration Feasibility)  
**Date**: November 2026  

---

## 1. System-Wide Architecture Comparison Matrix

The table below contrasts each capability required by the finalized **Handover AI Architecture (Project Intelligence Engine)** against the current code implementation.

Status classifications:
- **Existing & Reusable**: Implemented, verified, matches architectural constraints.
- **Existing but Requires Improvement**: Implemented in part or in older pattern; needs extension or refactoring.
- **Missing**: Not present in the codebase; must be constructed.
- **Blocked**: Cannot be safely implemented until an upstream dependency or security gate is resolved.
- **Unverified**: Implemented in code but lacks complete integration test or operational benchmark.

| Proposed Architecture Capability | Existing Component / Implementation | Status | Detailed Analysis & Evolution Path |
|---|---|---|---|
| **A. Assistant Role** | | | |
| 1. Project Context Answering | `services/assistant.py`, `services/assistant_retrieval.py` | **Existing & Reusable** | Fully operational across 8 knowledge domains, document chunks, graph relationships, and timelines. |
| 2. Controlled Tool Execution | None | **Missing** | No tool registry, execution sandbox, or parameter validation exists. Must be implemented in Phase AI-1/AI-5. |
| 3. Consequential Action Approval | Handover Signoff pattern (`services/handover_signoff.py`) | **Existing but Requires Improvement** | Approval models exist for Handovers and Verification, but generic conversational action approvals are missing. |
| **B. Model Strategy** | | | |
| 1. Primary Model: Qwen3 8B | `app/services/llm.py` (`OllamaLLMClient`), `app/core/config.py` | **Existing & Reusable** | Configured as `qwen3:8b`, with context window parameters ($num\_ctx=8192$, $temp=0.1$). |
| 2. Runtime: Ollama / Gateway | `infrastructure/gateway/` & direct `http://localhost:11434` | **Existing & Reusable** | Hardened gateway with semaphore queue protecting RTX 4050 6GB VRAM. |
| 3. Embedding: nomic-embed-text | `app/services/embedding.py`, `app/services/vector_store.py` | **Existing & Reusable** | Unified 768-dim embeddings across documents, GitHub, Jira, and Slack. |
| 4. OCR: GLM OCR | `app/services/ocr.py` (`glm-ocr:latest`) | **Existing & Reusable** | Bounded context, sequential thread lock `_OLLAMA_INFERENCE_LOCK`. |
| **C. Orchestration** | | | |
| 1. Direct Tool Execution | None | **Missing** | Direct execution path does not exist. |
| 2. Graph-Based Workflows | Monolithic turn in `assistant.py` | **Missing** | Current flow is linear procedural code; lacks cyclic or branching state graphs. |
| 3. Specialized Dynamic Agents | Conceptual only (`assistant_llm.py` role prompts) | **Missing** | System prompts simulate roles, but no dynamic agent instantiation or worker lifecycle exists. |
| 4. Interactive Human-in-the-Loop | None in assistant turn | **Missing** | Assistant cannot pause mid-investigation to ask clarifying questions and resume state. |
| **D. Agent Architecture** | | | |
| 1. Option C: Permanent Registry | None | **Missing** | Needs `AgentRegistry` with approved definitions (`KnowledgeAgent`, `EngineeringAgent`, etc.). |
| 2. Dynamic Agent Instantiation | None | **Missing** | Needs `AgentFactory` spawning transient execution instances bound to user `ProjectContext`. |
| 3. Proposed 10 Logical Agents | Distinct system prompt roles in `assistant_llm.py` | **Existing but Requires Improvement** | Specialized prompt personas exist, but they lack independent toolsets, memory scratchpads, and execution scopes. |
| **E. Memory Architecture** | | | |
| 1. Conversation History (PG) | `assistant_conversations`, `assistant_messages` | **Existing & Reusable** | Persisted per-user and per-project in PostgreSQL with foreign key cascades. |
| 2. Project Memory & Summaries | `knowledge_items` (8 domains) | **Existing but Requires Improvement** | Holds reconstructed knowledge, but lacks persistent semantic working memory for evolving assistant insights. |
| 3. Investigation Checkpoints | None | **Missing** | PostgreSQL lacks tables for saving multi-step investigation graphs, branch states, and pending tool approvals. |
| 4. Semantic Knowledge (ChromaDB) | `app/services/vector_store.py` (project collections) | **Existing & Reusable** | Strictly project-isolated ChromaDB collections with metadata filtering. |
| 5. Traceability to Evidence | `assistant_citations`, `knowledge_evidence_links` | **Existing & Reusable** | Fully grounded citations with explicit page numbers, excerpts, external URLs, and verification flags. |
| **F. Deep Research Modes** | | | |
| 1. Multi-Query Decomposition | `app/services/assistant_query.py` | **Existing & Reusable** | Generates 3–5 expanded subqueries, technical keyword extraction, and query typing. |
| 2. Autonomous Scope Expansion | Pre-set limits ($top\_k=14$) in `assistant_retrieval.py` | **Existing but Requires Improvement** | Currently bounded to a single retrieval pass; cannot iteratively search based on intermediate findings. |
| 3. Interactive Pausing / Resumption | None | **Missing** | Cannot pause execution to request scope expansion or credentials. |
| **G. Tool Execution UX & Streaming** | | | |
| 1. SSE Real-Time Streaming | Monolithic JSON POST in `assistant.py` | **Missing** | Current API returns entire response at once; frontend shows loading spinner. Must be replaced with SSE. |
| 2. Live Investigation Plan Display | `frontend/src/components/assistant/` | **Existing but Requires Improvement** | Frontend displays structured research reports and causal steps, but only after complete request finishes. |
| 3. Tool Execution & Approval UI | None | **Missing** | Frontend lacks UI widgets for interactive tool approval buttons or live tool execution logs. |
| **H. Security & Authorization** | | | |
| 1. Pre-Retrieval Source ACL Gates | `SourceAccessPolicyService` | **Existing & Reusable** | Strict fail-closed checking on private GitHub, Jira, and Slack sources. |
| 2. User Permission Inheritance | `ProjectContext` dependency | **Existing & Reusable** | Ensures assistant cannot execute actions beyond caller's verified project role. |
| 3. Indirect Prompt Injection Defense | `_BASE_SAFEGUARDS` in `assistant_llm.py` | **Existing & Reusable** | Explicit delimiters (`<project_evidence>`), untrusted data rules, and validator output sanitization. |

---

## 2. Deep-Dive Gap Analysis

### Gap 1: Orchestration Mechanism (Procedural vs Graph-Based)
- **Current State**: `ProjectKnowledgeAssistantService.ask_question()` is a single 150-line procedural method. It runs synchronously from step 1 to step 10. If an error occurs at step 7, the entire turn fails and no partial state is retained.
- **Required State**: A modular state graph where each step (`IntentRouting`, `Retrieve`, `AgentDispatch`, `ToolExecute`, `Synthesize`, `Validate`, `AwaitApproval`) is an isolated node that modifies a shared state container.
- **Feasibility**: Highly feasible. Can be implemented as a clean Python state graph or with LangGraph without breaking existing APIs.

### Gap 2: Streaming Architecture (SSE vs Monolithic JSON)
- **Current State**: The frontend uses `fetch()` in `api.ts` expecting a complete `AssistantAnswerResponse` JSON object. Deep research turns take 20–40 seconds of blank waiting.
- **Required State**: An SSE endpoint (`POST /projects/{id}/assistant/conversations/{id}/stream`) emitting event frames:
  - `event: plan_created` (investigation steps)
  - `event: agent_active` (which logical agent is running)
  - `event: retrieval_progress` (candidate discovery count)
  - `event: text_delta` (incremental token streaming)
  - `event: citation_found` (incremental citation card)
  - `event: approval_required` (pauses stream for human click)
  - `event: final_answer` (final validated payload)
- **Feasibility**: FastAPI natively supports `StreamingResponse(event_generator(), media_type="text/event-stream")`. The Next.js frontend can use `fetch-event-source` or native `ReadableStream`.

### Gap 3: Tool Execution & Dynamic Agent Framework
- **Current State**: Zero tool invocation capability. The assistant is strictly a reader/synthesizer.
- **Required State**: A secure `ToolRegistry` exposing project operations:
  - `search_codebase(query, repo)` (Read-only)
  - `get_jira_issue(issue_key)` (Read-only)
  - `query_relationships(entity_name)` (Read-only)
  - `verify_knowledge_finding(finding_id, decision)` (Consequential — requires approval)
  - `create_handover_task(title, assignee)` (Consequential — requires approval)
- **Feasibility**: High. Tools can directly invoke existing service classes (`HybridRetrievalService`, `RelationshipCoordinatorService`, `VerificationReviewService`) under the caller's `ProjectContext`.
