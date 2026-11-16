# Knowledge Intelligence API Specification

## Graph Projection Endpoints (`backend/app/api/routes/knowledge_intelligence.py`)

### `GET /api/v1/projects/{project_id}/knowledge-intelligence/graphs/{graph_type}`
- **Path Parameters**: `graph_type` in `technology-stack | system-architecture | features-workflows`.
- **Query Parameters**: `search`, `status`, `source_type`, `verification_state`, `limit` (1–500, default 150), `cursor`, `include_suggested` (bool, default `true`).
- **Response (`KnowledgeGraphProjectionResponse`)**:
  - `graph_type`, `project_id`, `nodes` (`KnowledgeGraphNode[]`), `edges` (`KnowledgeGraphEdge[]`), `summary` (`node_count`, `edge_count`, `categories`), `next_cursor`.
- **Security**: Requires `project.read`; filters all nodes, edges, and `evidence_ids` through fail-closed source ACLs (`_build_accessible_evidence_clause`).

### `GET /api/v1/projects/{project_id}/knowledge-intelligence/graphs/{graph_type}/nodes/{node_id}`
- **Response (`KnowledgeGraphNodeDetailResponse`)**: Returns the canonical `node`, `adjacent_edges`, `related_nodes`, and authorised `evidence_refs` (`evidence_id`, `title`, `source_type`, `source_url`, `supporting_excerpt`).

## Existing 8-Domain Endpoints
- `GET /projects/{project_id}/knowledge-intelligence/domains`
- `GET /projects/{project_id}/knowledge-intelligence/summary`
- `GET /projects/{project_id}/knowledge-intelligence/findings`
- `GET /projects/{project_id}/knowledge-intelligence/findings/{finding_id}`
- `GET /projects/{project_id}/knowledge-intelligence/timeline`
- `POST /projects/{project_id}/knowledge-intelligence/extract`
- `GET /projects/{project_id}/knowledge-intelligence/runs`
- `GET /projects/{project_id}/knowledge-intelligence/quality`
