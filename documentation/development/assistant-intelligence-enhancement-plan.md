# Project Knowledge Assistant: Intelligence & Multi-Mode Enhancement Plan

**Platform**: The Handover (Intelligent Project Knowledge Reconstruction & Handover Platform)  
**Module**: Module 5 — Project Knowledge Assistant / AI Assistant Area  
**Document Type**: Engineering Implementation Plan  
**Date**: November 2026  

---

## 1. Objectives

1. **Eliminate Premature Abstention**: Ensure that when relevant authorized project evidence exists (even partial or indirect), the assistant provides the most complete supported answer possible (`ANSWERED` or `PARTIALLY_ANSWERED`), clearly explaining what is known and detailing remaining gaps.
2. **Implement Three Intelligent Response Modes**:
   - **STANDARD**: Direct hybrid RAG answers with atomic claim citations and confidence scores.
   - **DEEP RESEARCH**: Multi-query decomposition, broad source search across all categories, cross-source comparison, and comprehensive structured research reports.
   - **DEEP THINK**: Causal and dependency reasoning, multi-hop analysis, alternative explanations, and structured reasoning summaries.
   - **DEEP EXTRACT**: Targeted entity and attribute extraction into structured tables / JSON with schema validation and field-level citations.
3. **Advanced Multi-Source Retrieval Pipeline**:
   - Query expansion generating 3–5 targeted subqueries and technical synonyms.
   - Multi-source coverage spanning Document Chunks, Knowledge Intelligence (8 domains), Relationship Explorer (graph traversal), Verification Center, and Project Timeline.
   - Full PostgreSQL text and provenance hydration.
   - Authority weighting favoring human-verified and architectural records.
4. **Preserve and Elevate Frontend UI**:
   - Preserve canonical 3-column layout (Conversation History | Answer Workspace | Source Evidence Details).
   - Add Mode Selector toggle in the composer.
   - Render mode-specific components: Structured Research Reports, Causal Reasoning Chains, and Interactive Data Tables with JSON export.

---

## 2. Technical Architecture & Data Flow

```text
                  ┌────────────────────────────────────────────────────────┐
                  │                 User Query & Selected Mode             │
                  │        (STANDARD / DEEP_RESEARCH / DEEP_THINK / EXTRACT)│
                  └───────────────────────────┬────────────────────────────┘
                                              │
                                              ▼
                  ┌────────────────────────────────────────────────────────┐
                  │           Assistant Query Expansion & Classifier       │
                  │   - Entity extraction (Jira, PR, Commit, Files)        │
                  │   - 3-5 technical subqueries & semantic variants       │
                  └───────────────────────────┬────────────────────────────┘
                                              │
                                              ▼
                  ┌────────────────────────────────────────────────────────┐
                  │        Permission-Aware Multi-Source Retriever         │
                  │   - Source Access Policy Check (Fail Closed)           │
                  │   - ChromaDB Vector Search (Semantic)                  │
                  │   - PostgreSQL Full-Text Search (tsvector / ILIKE)     │
                  │   - Knowledge Intelligence Domain Fetch (8 categories) │
                  │   - Relationship Explorer Graph Traversal              │
                  │   - Project Timeline Chronological Events              │
                  │   - Verification Center Findings                       │
                  └───────────────────────────┬────────────────────────────┘
                                              │
                                              ▼
                  ┌────────────────────────────────────────────────────────┐
                  │       PostgreSQL Canonical Hydration & Authority RRF   │
                  │   - Hydrate full text, author, timestamp, section title│
                  │   - Authority weighting (Verified > Draft > Raw)       │
                  │   - Deduplication & Citation Manifest Assignment [S1..]│
                  └───────────────────────────┬────────────────────────────┘
                                              │
                                              ▼
                  ┌────────────────────────────────────────────────────────┐
                  │           Mode-Specific Execution Engine               │
                  │   - STANDARD: Direct synthesis & atomic claim badges   │
                  │   - DEEP RESEARCH: Multi-section report & matrix       │
                  │   - DEEP THINK: Causal chain & trade-off analysis      │
                  │   - DEEP EXTRACT: Schema validation & tabular records  │
                  └───────────────────────────┬────────────────────────────┘
                                              │
                                              ▼
                  ┌────────────────────────────────────────────────────────┐
                  │          Epistemic Validator & Anti-Hallucination      │
                  │   - Verify [S#] citations against manifest             │
                  │   - Nuanced status (ANSWERED / PARTIALLY_ANSWERED)     │
                  │   - Uncertainty & missing information disclosure       │
                  └───────────────────────────┬────────────────────────────┘
                                              │
                                              ▼
                  ┌────────────────────────────────────────────────────────┐
                  │      Frontend 3-Column Workspace Rendering             │
                  │   - Left: Thread management & suggested prompts        │
                  │   - Center: Rich mode-specific answer views & composer │
                  │   - Right: Active citation cards with evidence links   │
                  └────────────────────────────────────────────────────────┘
```

---

## 3. Phased Implementation Roadmap

### Phase 1: Models & Schemas Extension
- Add `AssistantResponseMode` enum to `app.models.enums`.
- Update `QuestionRequest` in `app.schemas.assistant` to accept `response_mode`.
- Add structured response schemas:
  - `ResearchReportPayload` (executive summary, domain findings, cross-source matrix, timeline evolution, recommendations).
  - `DeepThinkPayload` (causal chain, decisions & consequences, alternatives considered, trade-offs).
  - `DeepExtractPayload` (table columns, rows, field citations, missing fields).
  - Update `AssistantAnswerResponse` and `AssistantAnswerPayload` to include mode-specific structured fields.

### Phase 2: Query Expansion & Multi-Source Retrieval
- Update `app.services.assistant_query` to implement deterministic and domain-aware query expansion.
- Update `app.services.assistant_retrieval` to:
  - Query multiple search variants.
  - Search across `EvidenceChunk`, `KnowledgeItem`, `KnowledgeRelationship`, `KnowledgeTimelineEvent`, and `VerificationItem`.
  - Apply authority weighting (`is_verified` boost, primary domain boost).
  - Assemble rich XML evidence prompt with full metadata.

### Phase 3: Mode-Specific Reasoners in `AssistantLLMReasoner`
- Create versioned system prompts for each response mode in `app.services.assistant_prompts` (or modular methods in `assistant_llm.py`).
- Implement execution strategies:
  - `generate_standard_answer()`
  - `generate_deep_research_report()`
  - `generate_deep_think_analysis()`
  - `generate_deep_extract_table()`
- Revise prompt instructions to strictly prevent premature abstention when partial evidence exists.

### Phase 4: Service Orchestration & Validation
- Update `ProjectKnowledgeAssistantService.ask_question()` to route to the appropriate execution strategy based on `request.response_mode`.
- Update `AssistantAnswerValidator` to validate mode-specific outputs (table cells, report sections, causal chains) against the citation manifest.

### Phase 5: Frontend UI Enhancements
- Update `frontend/src/lib/types.ts` with `AssistantResponseMode` and mode-specific payload interfaces.
- Update `frontend/src/lib/api.ts` to accept `response_mode`.
- Update `frontend/src/components/assistant/AssistantWorkspaceView.tsx`:
  - Add Mode Selector pill toggle in composer (Standard, Deep Research, Deep Think, Deep Extract).
  - Create specialized UI renderers for:
    - Deep Research reports (collapsible sections, source matrices, badge indicators).
    - Deep Think causal trees and trade-off blocks.
    - Deep Extract interactive tables with field citation tooltips and copy JSON button.
  - Retain 3-column layout and active citation synchronization.

### Phase 6: Verification & Quality Assurance
- Run backend unit and integration tests.
- Verify frontend TypeScript types (`npm run typecheck`).
- Test query scenarios on active project to ensure non-abstention on partial evidence.
- Run Graphify update.
