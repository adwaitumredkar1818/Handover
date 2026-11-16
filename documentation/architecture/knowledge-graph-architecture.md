# Knowledge Graph Architecture

## Canonical Data Flow
```text
EvidenceItem / EvidenceContent / EvidenceChunk
  -> Qwen3 8B Extraction (structured JSON schema) -> KnowledgeItem + KnowledgeEvidenceLink (PostgreSQL)
  -> RelationshipCoordinatorService + TechnologyManifestParser -> KnowledgeEntity + EntityAlias + KnowledgeRelationship + RelationshipEvidenceLink (PostgreSQL)
  -> KnowledgeGraphProjectionService (ACL-filtered) -> React Flow (@xyflow/react)
```

## Shared Canonical Entity Store (`backend/app/models/relationship.py`, `backend/app/models/enums.py`)
- Single PostgreSQL canonical entity table `knowledge_entities` extended with `technology`, `work_cluster`, `service`, `api`, `database`, `framework`, and `library` in `EntityType`.
- `EntityAlias` stores canonicalized technology and contributor aliases (e.g. `Postgres` -> `PostgreSQL`; `GitHub Actions` stays distinct from `GitHub API`).
- `KnowledgeRelationship` stores directed edges with explicit `relationship_basis` (`explicit`, `inferred`, `human_confirmed`), `verification_status`, and `RelationshipEvidenceLink` provenance.
- `KnowledgeItem.superseded_by_id` links stale findings to non-verified replacement items on re-extraction.

## Deterministic Manifest Ingestion (`backend/app/services/technology_manifest_parser.py`)
- `GitHubClient._is_candidate_doc_path` includes `package.json`, `requirements.txt`, `pyproject.toml`, `Dockerfile`, and `docker-compose.yml` / `compose.yaml`.
- Safe non-executing parsers extract declared dependencies and container infrastructure metadata (`usage_basis="declared_dependency"` / `"configured_infrastructure"`).

## Security & ACL Enforcement
- `KnowledgeGraphProjectionService` (`backend/app/services/knowledge_graphs.py`) and `DependencyIntelligenceService` (`backend/app/services/dependency_intelligence.py`) enforce `_build_accessible_evidence_clause` fail-closed source ACLs before returning any node, edge, or evidence reference.
- Migration `0020_graphs_and_contributors` enables default-deny PostgreSQL RLS on `notifications`, `team_roster_members`, and `contribution_attributions`.
