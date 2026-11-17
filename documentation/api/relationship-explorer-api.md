# Relationship Explorer API Specification

## People-Centric Contributor Graph, Identity Review & Work Cluster Endpoints (`backend/app/api/routes/relationships.py`)

### `GET /api/v1/projects/{project_id}/relationships/contributors/graph`
- **Query Parameters**: `contributor_type`, `work_cluster`, `repository`, `verification_state`, `search`, `include_external`, `include_bots`, `expand_contributor_key`, `expand_cluster_name`, `limit` (1–500).
- **Response (`ContributorGraphResponse`)**: Bounded contributor, work-cluster, and expanded artefact nodes + edges + summary counts (`contributor_count`, `cluster_count`, `confirmed_members`, `external_contributors`, `unidentified_contributors`, `bots`, `pending_reviews`).

### `GET /api/v1/projects/{project_id}/relationships/contributors`
- **Response (`ContributorIdentitySummaryResponse[]`)**: Lists aggregated contributor identities filtered by accessible evidence. Masks `git_author_email` when caller lacks `project.manage`.

### `GET /api/v1/projects/{project_id}/relationships/contributors/{contributor_key}`
- **Response (`ContributorIdentitySummaryResponse`)**: Returns full contributor profile, counts, repositories, work areas, declared responsibility, evidence references, and review history.

### `POST /api/v1/projects/{project_id}/relationships/contributors/{contributor_key}/review`
- **Permissions**: Requires `project.manage`.
- **Body (`ContributorIdentityReviewRequest`)**: `action` (`match_member`, `mark_external`, `mark_bot`, `leave_unidentified`, `reject_match`, `revert`), optional `project_membership_id`, `roster_member_id`, `notes`.
- **Side Effects**: Updates matching `ContributionAttribution` rows, recalculates responsibility alignment, appends `review_history`, and logs an immutable `AuditLog` event.

### `GET /api/v1/projects/{project_id}/relationships/work-clusters`
### `GET /api/v1/projects/{project_id}/relationships/work-clusters/{cluster_id}`
### `POST /api/v1/projects/{project_id}/relationships/work-clusters/rebuild`
- Lists, inspects, and deterministically rebuilds ACL-filtered technical work area clusters (`WorkClusterResponse`, `WorkClusterRebuildResponse`).
