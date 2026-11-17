# Knowledge Intelligence & Relationship Explorer Implementation Report

## Summary of Implemented Changes
1. **Security & Migration (`0020_graphs_and_contributors`)**:
   - Enabled PostgreSQL RLS on `notifications`, `team_roster_members`, and `contribution_attributions` and added contributor review columns + indexes on `contribution_attributions`.
   - Enforced source ACL filtering in `DependencyIntelligenceService.analyze_dependencies`.
   - Removed hardcoded synthetic findings from `useCanonicalFindings` (`frontend/src/components/figma-ui/domain.tsx`) and connected `FindingDrawer` verification buttons to `api.verification.*`.
2. **Extraction Correctness & Shared Canonical Entities**:
   - Passed category-specific Pydantic `json_schema` into `OllamaLLMClient.generate_json` from `ReconstructionWorkerService`.
   - Linked stale superseded `KnowledgeItem`s via `superseded_by_id` in `KnowledgeRepository.upsert_validated_draft`.
   - Built `technology_manifest_parser.py` and upgraded `RelationshipCoordinatorService` + `RelationshipDiscoveryEngine` to unpack `structured_payload` technologies, components, features, operational procedures, manifests, PR-to-commit links, and commit authors.
3. **Knowledge Intelligence Graphs & UI**:
   - Added `KnowledgeGraphProjectionService` (`backend/app/services/knowledge_graphs.py`) and `/knowledge-intelligence/graphs/{graph_type}` endpoints.
   - Implemented `@xyflow/react` `KnowledgeIntelligenceWorkspace.tsx` with Technology Stack, System Architecture, Features & Workflows, and 8-Domain Register views.
4. **Relationship Explorer, GitHub Enrichment & Work Grouping**:
   - Added commit `changed_files` retrieval, bot recognition (`is_bot_identity`), and post-sync `"Contributor identities require review."` notifications in `github_sync.py`.
   - Upgraded `ContributionAttributionService` with deterministic path/keyword classification, Qwen fallback, strict identity matching, review actions, and email masking.
   - Created `WorkGroupingService` (`backend/app/services/work_grouping.py`), contributor/work-cluster endpoints in `routes/relationships.py`, and upgraded `RelationshipWorkspace.tsx` (7 tabs, dangling-edge filter fix, node/contributor drawers, and Identity Review UI).
