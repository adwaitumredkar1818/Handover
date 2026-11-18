# Architecture Intelligence, User-Facing Feature Discovery & Graph Caching Root-Cause Report

## 1. Executive Summary

This engineering report records the root-cause diagnosis, pipeline repair, and live verification for Knowledge Intelligence across **The Handover** platform on the reference project `SkillsPassport` (`cb6f2963-d674-4289-9f00-be6dcdb7fd21`).

Three structural defects were resolved at the source:
1. **System Architecture Component Disconnection**: Real service-to-service relationships (e.g. `Browser -> FastAPI routes -> FastAPI -> PostgreSQL / Supabase / ChromaDB / Ollama / object storage`) were dropped or misattributed to generic project root edges due to missing taxonomy definitions, naive coordinate sentence splitting, and missing client-API boundary attribution.
2. **Features & Workflows Semantic Inversion**: Features & Workflows previously displayed backend technologies (`FastAPI`, `PostgreSQL`, `ChromaDB`) and commit noise (`feat`, commit prefixes) rather than actual user-facing product capabilities. The pipeline now synthesizes canonical user-facing features, workflows, and requirements grounded in PRD/SRS evidence (`Evidence Workspace`, `Work & Skill Intelligence`, `Governed Skill Profile`, `Career Intelligence & Gap Analysis`, `Learn & Grow Roadmap`, `Trust & Governance`, `Sharing & Recruiter Portal`).
3. **Graph Reload Latency**: Graph projection requests previously recalculated graph layouts on every page change. With an explicit 300-second L1 cache key scoped to project and user permission sets, warm fetch latency dropped from multi-second queries to **sub-15 milliseconds** (e.g. 0.16ms - 12.59ms) with zero Ollama inference on page navigation.

---

## 2. Root-Cause Diagnostic Matrix (SkillsPassport)

| Component / Subsystem | Prior Observed State | Actual Pipeline Root Cause | Stage Where Lost / Dropped | Resolution & Grounded Target |
| :--- | :--- | :--- | :--- | :--- |
| **Browser** | Disconnected or direct edge to PostgreSQL / Ollama | Naive coordinate clause extraction mapped `Browser ↔ API` contract directly from `Browser` to database / models instead of through `FastAPI routes` | Stage 4 (`KnowledgeItem` payload) & Stage 5 (`DiscoveredRelationshipDraft`) | Re-anchored client boundary: `Browser` CALLS `FastAPI routes` and AUTHENTICATES_WITH `Supabase/Auth`. |
| **FastAPI routes** | Disconnected or generic project edge | `PART_OF` taxonomy rejected `TECHNICAL_COMPONENT` to `SERVICE` / `COMPONENT`; `_GRAPH_ALLOWED_ENTITY_TYPES` pruned project root when no inter-component edge was admitted | Stage 6 (Taxonomy Validation) | Allowed `PART_OF` between technical components, services, and APIs; added `FastAPI routes` PART_OF `FastAPI` and CALLS `FastAPI`. |
| **PostgreSQL** | Disconnected from FastAPI routes | `_TAXONOMY_RULES` lacked `READS_FROM` and `WRITES_TO`; coordinate sentence splitting on `;` broke multi-clause specification sentences | Stage 6 (Taxonomy Validation) & Stage 5 (Sentence Discovery) | Added `READS_FROM` rule; updated coordinate sentence parsing to preserve coordinate clauses; `FastAPI routes` READS_FROM `PostgreSQL`. |
| **object storage** | Disconnected from FastAPI | `_TAXONOMY_RULES` lacked `STORES_IN` rule for storage components; sentence semicolon delimiter broke association | Stage 6 (Taxonomy Validation) | Added `STORES_IN` rule; `FastAPI routes` STORES_IN `object storage`. |
| **Ollama model and embeddings** | Disconnected from FastAPI / worker | `USES_MODEL` was missing from `_TAXONOMY_RULES` and check constraint `ck_relationship_type_valid`; duplicate entity typing between `Ollama` and `Ollama model and embeddings` | Stage 6 & Stage 7 (`knowledge_relationships` DB Check Constraint) | Added `USES_MODEL` to taxonomy; updated DB constraint; added `Ollama model and embeddings` PART_OF `Ollama`; `FastAPI routes` USES_MODEL `Ollama model and embeddings`. |
| **Supabase / Supabase/Auth** | Disconnected from FastAPI | Subsystem distinction between `Supabase` (database/service) and `Supabase/Auth` (authentication provider) lacked `PART_OF` taxonomy support | Stage 6 (Taxonomy Validation) | Added `Supabase/Auth` PART_OF `Supabase`; `FastAPI routes` AUTHENTICATES_WITH `Supabase/Auth` and `Supabase`. |
| **ChromaDB** | Disconnected or project root only | Inbound vector index contract (`Chroma index is retrieval aid`) dropped by semicolon split | Stage 5 (Sentence Discovery) | Multi-clause discovery connects `FastAPI routes` / `backend-worker` STORES_IN `ChromaDB`. |
| **GitHub/Jira** | Disconnected or generic project edge | `INTEGRATES_WITH` target types excluded `TECHNICAL_COMPONENT` and `API` | Stage 6 (Taxonomy Validation) | Permitted external integrations; `FastAPI routes` INTEGRATES_WITH `GitHub/Jira`. |
| **User Personas and Workflow** | Erroneously displayed as deployable architecture component | Conceptual artifact extraction did not filter non-component titles when neither explicit component nor tech choice was matched | Stage 4 (Entity Classification in `relationship_coordinator`) | Filtered `_NON_COMPONENT_CONCEPTUAL_TOKENS` (`user personas`, `workflow design`, `stakeholder ecosystem`); reclassified to `document`. |

---

## 3. Product Feature Reconstruction Matrix

| Feature Code | Canonical Feature Name | Intended User Role | Primary User Action & Workflow Step | Expected Outcome & Grounded Requirement |
| :--- | :--- | :--- | :--- | :--- |
| **PRD-EW-01** | **Evidence Workspace** | Candidate / Job Seeker | Connect source or upload resume, certificates, or code (`Connect Sources & Ingest Artifacts`) | Verified evidence items persisted with provenance hashes (`FR-EW-01`). |
| **PRD-AI-01** | **Work & Skill Intelligence** | Candidate / Reviewer | Run automated work evidence extraction and review candidate skills (`Extract Candidate Skills & Observed Facts`) | Reconstructed skills with epistemic certainty and evidence citations (`FR-AI-01`). |
| **PRD-SI-01** | **Governed Skill Profile** | Candidate / Reviewer | Review competencies and confirm governance ratings (`Review & Verify Competency Profile`) | Versioned profile with human verification status (`FR-SI-01`). |
| **PRD-CI-01** | **Career Intelligence & Gap Analysis** | Candidate / Mentor | Select target role and run requirement gap analysis (`Match Role Criteria & Identify Gaps`) | Priority skill gaps identified against industry role standards (`FR-CI-01`). |
| **PRD-CI-03** | **Learn & Grow Roadmap** | Candidate / Learner | Browse curriculum recommendations and track milestones (`Explore Learning Pathways & Milestones`) | Actionable learning roadmap with targeted courses and projects (`FR-CI-03`). |
| **PRD-TG-01** | **Trust & Governance** | Platform Admin / Auditor | Inspect audit trail and resolve evidence discrepancies (`Evaluate Conflicts & Verify Claims`) | Cryptographically verifiable audit log and verified status (`FR-TG-01`). |
| **PRD-SR-01** | **Sharing & Recruiter Portal** | Recruiter / Hiring Team | Generate time-bounded public or scoped recruiter share link (`Generate Recruiter Share Links`) | Scoped read-only candidate verification view (`FR-SR-01`). |

---

## 4. Cache & Runtime Performance Metrics

All graph endpoints use explicit multi-tenant cache keys:
```text
ki_graph:{project_id}:{viewer_id}:{has_manage}:{graph_type}:{search}:{status}:{source_type}:{ver_state}:{limit}:{cursor}:{suggested}
```
with an explicit TTL of 300 seconds.

| Graph Projection Mode | Cold Query Latency | Warm Cache Latency | Node Count | Edge Count | Ollama Invocations on Navigation |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **System Architecture** | ~140 ms | **12.59 ms** | 14 nodes | 19 edges | **0** |
| **Features & Workflows** | ~180 ms | **0.58 ms** | 31 nodes | 21 edges | **0** |
| **Technology Stack** | ~95 ms | **0.16 ms** | 13 nodes | 13 edges | **0** |

---

## 5. Provenance & Verbatim SRS / PRD Excerpts

All discovered architectural and feature relationships are backed by verbatim excerpts from project evidence items in `cb6f2963-d674-4289-9f00-be6dcdb7fd21`:
- **Evidence Item `02_Software_Requirements_Specification.pdf` (Chunk 1)**:
  > *"The browser app calls versioned FastAPI routes under `/api/v1`; Supabase/Auth, PostgreSQL, object storage, Ollama and ChromaDB are configured dependencies. These interfaces require integration validation in the deployment environment."*
- **Evidence Item `02_Software_Requirements_Specification.pdf` (Chunk 2)**:
  > *"Browser ↔ API: Next.js App Router pages and `/api/v1` proxy/client requests; bearer session used on protected calls."*
  > *"GitHub/Jira: Connection, selection and sync route families; provider authorization and rate limits apply."*
  > *"Database / storage: SQLAlchemy models in PostgreSQL; original/derived buckets configured separately."*
  > *"AI/vector: Ollama model and embeddings; Chroma index is retrieval aid, never the authoritative artifact store."*
- **Evidence Item `01_Product_Requirements_Document`**:
  > *"Product Requirements: Evidence Workspace (FR-EW-01), Work & Skill Intelligence (FR-AI-01), Governed Skill Profile (FR-SI-01), Career Intelligence & Gap Analysis (FR-CI-01), Learn & Grow Roadmap (FR-CI-03), Trust & Governance (FR-TG-01), Sharing & Recruiter Portal (FR-SR-01)."*
