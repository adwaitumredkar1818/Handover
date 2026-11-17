# Knowledge Intelligence — Product Specification

## Purpose
Knowledge Intelligence reconstructs what a project is, which technologies are used, how the architecture is structured, which features exist and how they behave, and organizes evidence-backed findings across the eight canonical handover domains.

## Four Implemented Views (`frontend/src/components/knowledge/KnowledgeIntelligenceWorkspace.tsx`)
1. **Technology Stack Graph (`technology-stack`)**: Displays detected technologies grouped by category (`frontend`, `backend`, `database`, `ai_ml`, `storage`, `infrastructure`, `testing`, `external_integrations`), preserving version strings, canonical aliases, and usage basis (`declared_dependency`, `configured_infrastructure`, `documented`, `implemented`, `verified`, `proposed`).
2. **System Architecture Graph (`system-architecture`)**: Layered `@xyflow/react` projection (`project`, `ui`, `api_backend`, `core_services`, `data_storage`, `ai_processing`, `external_integrations`) distinguishing `documented_only`, `implementation_evidenced`, `verified_implementation`, `proposed`, and `superseded` states.
3. **Features & Workflows Graph (`features-workflows`)**: Projects canonical `feature`, `requirement`, and `operational_procedure` entities linked to Jira work items, GitHub PRs/commits, and components with multi-signal statuses (`PLANNED`, `IN_PROGRESS`, `IMPLEMENTATION_EVIDENCED`, `TEST_EVIDENCED`, `HUMAN_VERIFIED`, `BLOCKED`, `UNCERTAIN`, `CONFLICTED`, `SUPERSEDED`).
4. **Knowledge Domains Register (`domains`)**: Displays non-stale `KnowledgeItem`s across all 8 canonical domains (`backend/app/services/knowledge_domains.py`) with search, domain/verification filtering, `Open Evidence`, `Explore Relationships`, and real Verification Center actions (`api.verification.*`).

## Epistemic & Empty-State Invariants
- Never fabricates synthetic findings or graph nodes (`useCanonicalFindings` returns `[]` when empty; displays `"No knowledge has been reconstructed from this project's evidence yet."`).
- Normal graph browsing uses persisted PostgreSQL records via `/api/v1/projects/{project_id}/knowledge-intelligence/graphs/{graph_type}` without calling Ollama/Qwen3.
