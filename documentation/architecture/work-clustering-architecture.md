# Evidence-Based Work Grouping Architecture

## Design Decision
Per the project specification override, work grouping uses deterministic evidence-based technical grouping backed by PostgreSQL (`WorkGroupingService` in `backend/app/services/work_grouping.py`), without requiring HDBSCAN, K-means, Agglomerative Clustering, or a separate vector/graph database.

## Grouping Pipeline
1. **Inputs**: `ContributionAttribution` records enriched with GitHub `changed_files` paths, PR labels, commit messages, and Jira issues.
2. **Deterministic Classification (`classify_contribution_domains`)**:
   - Stage 1: Configurable file-path rules (`frontend/`, `migrations/`, `/auth`, `embedding/`, `/ocr`, `/llm`, `integrations/`, `/api/`, `tests/`, `docs/`, `Dockerfile`, `backend/`).
   - Stage 2: Title, message, and label keyword matching.
   - Stage 3: Bounded Qwen3 8B fallback (`llm_client`) invoked only during background jobs when deterministic rules return `["Other"]`.
3. **Persistence**:
   - Groups contributions into canonical `EntityType.WORK_CLUSTER` entities in `knowledge_entities` (`Frontend`, `Backend`, `Authentication`, `Database`, `API`, `AI/ML`, `RAG`, `OCR`, `Infrastructure`, `Testing`, `Documentation`, `Security`, `Integration`).
   - Isolated/unclassified items remain visible under `Other / Unclustered Contributions`.
   - Persists `PERSON --CONTRIBUTED_TO--> WORK_CLUSTER` and `COMMIT/PULL_REQUEST/WORK_ITEM --BELONGS_TO_WORK_CLUSTER--> WORK_CLUSTER` relationships with `RelationshipEvidenceLink` provenance and `RelationshipReconstructionRun` metadata.
