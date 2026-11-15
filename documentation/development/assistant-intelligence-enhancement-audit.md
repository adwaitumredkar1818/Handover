# Project Knowledge Assistant: Intelligence & Retrieval Enhancement Audit

**Platform**: The Handover (Intelligent Project Knowledge Reconstruction & Handover Platform)  
**Module**: Module 5 — Project Knowledge Assistant / AI Assistant Area  
**Document Type**: Engineering & Intelligence Audit  
**Date**: November 2026  

---

## 1. Executive Summary

This audit assesses the intelligence, retrieval architecture, context assembly, and answer generation of the **Project Knowledge Assistant** in *The Handover*.

While the foundation of the assistant (3-column UI layout, PostgreSQL message persistence, ChromaDB vector indexing, and Ollama Qwen3 8B integration) is operational, user interaction highlighted a critical shortcoming:
**The assistant frequently retrieves multiple relevant sources (e.g. `[S1]` through `[S7]`), but prematurely abstains by declaring an `INSUFFICIENT-EVIDENCE STATE` with a single generic refusal sentence.**

This audit identifies the root causes across 5 distinct system layers and defines the architectural remedies necessary to transform the assistant into a resilient, multi-source, deep-reasoning project intelligence system.

---

## 2. Root Cause Analysis of Premature Abstention

### 2.1 Single-Pass, Narrow Keyword Retrieval
- **Current Behavior**: `AssistantRetrievalService` executes a single query pass using `classified_query.raw_query`. For a question like *"How are citation priorities determined across different evidence types?"*, only exact-phrase or naive semantic embeddings are calculated.
- **Deficiency**: The query is not expanded into domain synonyms or related technical concepts (e.g. `reciprocal rank fusion`, `RRF`, `authority weighting`, `evidence scoring`, `verification status`, `relevance ranking`).
- **Impact**: Chunks containing the actual architectural mechanisms or adjacent specifications may receive low similarity scores or be crowded out by surface-level text matches.

### 2.2 Lack of Multi-Source Aggregation
- **Current Behavior**: Chunk retrieval (`HybridRetrievalService`) dominates candidate selection. Knowledge items, entity relationships, timeline events, and verification findings are either minimally fetched or filtered out if exact keyword matches fail.
- **Deficiency**: When raw document chunks do not contain a verbatim definition, structured knowledge in PostgreSQL (e.g. decisions in `knowledge_items`, verification findings in `verification_items`, entity relations in `knowledge_relationships`) is overlooked.
- **Impact**: The assistant acts like a naive document searcher rather than a holistic project intelligence assistant that synthesizes knowledge across all 8 project domains.

### 2.3 Strict & Binary Prompt Guardrails in LLM Reasoner
- **Current Behavior**: In `backend/app/services/assistant_llm.py`, the system prompt strictly instructs Qwen3 8B:
  ```text
  "insufficient_evidence": The provided evidence does not contain information to answer the question. Explicitly communicate that the project evidence lacks this information and state what is missing.
  ```
- **Deficiency**: When the retrieved evidence provides partial, contextual, or adjacent information (for example, chunk `[S2]` detailing evidence citations in an API specification), the LLM opts for complete abstention rather than explaining what *is* known and scoping what remains missing under `PARTIALLY_ANSWERED`.
- **Impact**: The assistant delivers zero informational value to the user, completely disregarding the context present in the retrieved sources.

### 2.4 Vector vs Canonical Text Hydration
- **Current Behavior**: ChromaDB provides chunk IDs and similarity distances. In some query branches, only truncated excerpts or raw chunk snippets without metadata context (section hierarchy, document parent title, author identity, timestamp) are provided.
- **Deficiency**: Qwen3 8B receives fragmented strings without hierarchical provenance.
- **Impact**: The LLM cannot reason across document structure or understand whether a snippet is an authoritative architectural decision or a peripheral comment.

### 2.5 Uniform Execution Mode (No Specialized Reasoning)
- **Current Behavior**: Every user prompt runs through the identical single-pass pipeline regardless of whether the user needs:
  1. A broad, multi-angle research report (`DEEP RESEARCH`).
  2. A causal analysis of architectural trade-offs and bugs (`DEEP THINK`).
  3. A structured tabular extraction of entities and attributes (`DEEP EXTRACT`).
- **Deficiency**: A single prompt cannot simultaneously serve concise Q&A, comprehensive multi-section research, causal chain tracing, and schema-validated entity extraction.
- **Impact**: Complex queries fail due to token limits or superficial answers.

---

## 3. Detailed Component Audit

| Component | Current Implementation | Identified Bottleneck | Target Enhancement |
| :--- | :--- | :--- | :--- |
| **Query Understanding** | Regex-based `AssistantQueryClassifier` with 12 static rules. | No query expansion; misses conceptual synonyms and technical jargon. | Sub-query generator + expansion dictionary + Qwen-assisted multi-query expansion. |
| **Retrieval Engine** | Top-k vector + PostgreSQL FTS on raw query string. | Single pass; biased towards chunk text; ignores relationship graph and verification states. | Multi-pass cross-source retriever querying Chunks, Knowledge Items, Timeline, Graph Entities, and Verification Center. |
| **Context Assembly** | Simple list of XML `<project_evidence>` tags. | Flat list; no categorization by evidence type, authority weight, or corroboration status. | Structured context partitioning: Verified Findings, Document Specifications, Commits/PRs, Timeline Context, and Cross-References. |
| **Reasoning Engine** | Single `generate_answer()` with static prompt. | Binary answered/insufficient dichotomy; Qwen defaults to abstention on complex questions. | 4 distinct execution modes (`STANDARD`, `DEEP_RESEARCH`, `DEEP_THINK`, `DEEP_EXTRACT`) with specialized prompts and nuance guidelines. |
| **Attribution & Claims** | Post-generation regex matching `[S#]`. | Validates syntax but does not ensure claims cite the most specific underlying chunk or section. | Strict claim-to-citation validator with field-level attribution and hallucination stripping. |
| **Frontend UI** | 3-column layout with basic prompt composer and right-side evidence panel. | No mode selector for Deep Research / Deep Think / Deep Extract; no specialized rendering for tables or reasoning trees. | Add Mode Selector toggle in composer; render rich research reports, causal chains, and extractable tables with copyable JSON. |

---

## 4. Architectural Boundaries & Safeguards

In accordance with `AGENTS.md`:
1. **Zero Fabrication**: The assistant must never invent facts, commit hashes, Jira keys, or citation tags. Every claim must trace to a verified database record.
2. **Project Membership != Source Access**: Source ACLs must be verified *before* retrieval candidates enter the LLM prompt. Restricted sources must fail closed.
3. **No Direct Vector Text Substitution**: ChromaDB is an index; raw text, metadata, and author provenance must be hydrated from PostgreSQL.
4. **RTX 4050 Hardware Boundary**: Keep Ollama execution strictly serialized (`OLLAMA_MAX_CONCURRENT_AI_JOBS=1`). Avoid excessive context window sizes that trigger VRAM swapping (keep context around 4096 tokens).
5. **Human Approval Principle**: The assistant provides intelligence and draft recommendations; it cannot approve handovers or resolve conflicts without human oversight.

---

## 5. Next Steps

Proceed directly with the implementation plan defined in `documentation/development/assistant-intelligence-enhancement-plan.md`.
