# Knowledge Intelligence & Relationship Explorer Testing Guide

## Backend Automated Tests (`backend/tests/test_knowledge_and_contributor_graphs.py`)
Execute with:
```powershell
cd backend
.\.venv\Scripts\pytest.exe tests/test_knowledge_and_contributor_graphs.py -v
```
Covers:
- Migration `0020_graphs_and_contributors` RLS and column metadata.
- `DependencyIntelligenceService` fail-closed source ACL enforcement.
- Manifest parsing (`package.json`, `requirements.txt`), alias canonicalisation (`Postgres` -> `PostgreSQL`, `GitHub Actions` != `GitHub API`), and `proposed` vs `declared_dependency` technology status.
- System Architecture component seeding (`documented_only` vs `implementation_evidenced`) and Features & Workflows projections.
- `KnowledgeItem.superseded_by_id` linking on re-extraction.
- GitHub contributor identity matching (`github_author_id`, `github_username`, `git_author_email`, ambiguous display-name protection), bot detection, email masking for non-managers, Contributor Identity Review (`match_member`, `mark_external`, RBAC 403 enforcement), and Evidence-Based Work Grouping (`WorkGroupingService` + `Other / Unclustered Contributions`).

## Frontend Automated Tests (`frontend/src/__tests__/KnowledgeAndRelationship.test.tsx`)
Execute with:
```powershell
cd frontend
npm.cmd test
npm.cmd run typecheck
```
Covers:
- Empty-state enforcement (zero fabricated findings/nodes).
- Switching across all 4 Knowledge Intelligence views (`technology-stack`, `system-architecture`, `features-workflows`, `domains`).
- Dangling-edge removal (`filterVisibleGraphEdges`).
- Contributor Identity Review banner and review action submission.
