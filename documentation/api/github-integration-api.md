# GitHub Connected Source — API Specification

**Document Version:** 1.0.0  
**Date:** 2026-11-16  
**System:** The Handover  
**Base URL:** `/api/v1`  
**Authentication:** Bearer JWT in `Authorization: Bearer <access_token>`  

---

## 1. Overview

The GitHub Connected Source provides REST API endpoints to:
1. Connect an organisation's GitHub account using a Fine-Grained Personal Access Token (PAT).
2. Discover accessible repositories with metadata, topics, language, and project collision status.
3. Map repositories to specific projects with granular sync scope configuration.
4. Trigger and monitor background synchronisation of documentation, commits, PRs, issues, and code.
5. Ingest and query evidence items with complete branch and contributor provenance.

---

## 2. Authentication & Source Connection

### 2.1 Register GitHub Source Connection
Validate a Fine-Grained Personal Access Token (PAT), automatically discover the authenticated GitHub account profile, and securely store encrypted credentials.

- **Method / Route**: `POST /organisations/{organisation_id}/sources`
- **Required Permission**: `org.sources.manage` (Org Owner or Org Admin)
- **Request Body (`RegisterSourceConnectionRequest`)**:
```json
{
  "provider": "github",
  "secret_token": "github_pat_11A...",
  "account_identifier": "auto",
  "display_name": null,
  "scopes": ["repo", "read:org"]
}
```
*Note: If `account_identifier` is `"auto"` or omitted, the backend executes `GET /user` against the GitHub API to discover the authenticated login (`login`) and user ID automatically.*

- **Response (`201 Created`)**:
```json
{
  "id": "e4b6c8d2-1111-4444-9999-abcdef123456",
  "organisation_id": "6ba6ac46-1675-4143-b775-71eddc3fecdf",
  "provider": "github",
  "account_identifier": "octocat",
  "display_name": "GitHub (@octocat)",
  "status": "connected",
  "created_at": "2026-11-16T12:00:00Z",
  "last_synced_at": null,
  "error_message": null
}
```

- **Error Responses**:
  - `400 Bad Request`: `INTEGRATION_AUTH_ERROR` — PAT is invalid, expired, or rejected by GitHub.
  - `403 Forbidden`: `FORBIDDEN` — Caller lacks `org.sources.manage` permission.

---

## 3. Repository Discovery

### 3.1 Discover Repositories for GitHub Connection
Fetch repositories accessible to the connected token, enriched with repository metadata and project mapping status.

- **Method / Route**: `GET /integrations/connections/{connection_id}/github/repositories`
- **Required Permission**: `org.sources.read`
- **Query Parameters**:
  - `project_id` (optional, UUID): Target Handover project ID. When provided, candidates mapped to this project will have `already_mapped: true`.
  - `page` (optional, default `1`): Pagination page.
  - `per_page` (optional, default `30`, max `100`): Results per page.

- **Response (`200 OK`)**:
```json
{
  "items": [
    {
      "external_resource_id": "789101",
      "name": "skillpassport-core",
      "full_name": "shubham-dev/skillpassport-core",
      "owner_login": "shubham-dev",
      "description": "Core backend services and credential engine",
      "is_private": true,
      "default_branch": "main",
      "language": "Python",
      "topics": ["fastapi", "credentials"],
      "already_mapped": false,
      "open_issues_count": 5,
      "is_fork": false,
      "is_archived": false,
      "created_at": "2024-01-15T08:30:00Z",
      "pushed_at": "2026-11-16T10:00:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "per_page": 30,
  "has_more": false
}
```

---

## 4. Repository Mapping & Sync Scope

### 4.1 Create Project Repository Mapping
Map a discovered repository to a project with fine-grained sync scope options.

- **Method / Route**: `POST /projects/{project_id}/integrations/github/mappings`
- **Required Permission**: `project.integrations.manage`
- **Request Body (`CreateGitHubMappingRequest`)**:
```json
{
  "source_connection_id": "e4b6c8d2-1111-4444-9999-abcdef123456",
  "owner": "shubham-dev",
  "repo": "skillpassport-core",
  "branch_scope": "all",
  "selected_branches": ["main", "staging"],
  "commit_scope": "all",
  "commit_since": null,
  "pr_scope": "all",
  "issue_scope": "all",
  "include_docs": true,
  "include_commits": true,
  "include_pull_requests": true,
  "include_reviews": true,
  "include_issues": true,
  "include_comments": true,
  "include_code": false
}
```

- **Response (`201 Created`)**:
```json
{
  "id": "c1a2b3c4-2222-5555-8888-fedcba654321",
  "project_id": "ed33c53a-7678-4d5b-8212-64c233897142",
  "source_connection_id": "e4b6c8d2-1111-4444-9999-abcdef123456",
  "provider": "github",
  "external_resource_id": "789101",
  "external_resource_key": "shubham-dev/skillpassport-core",
  "status": "active",
  "sync_config_json": {
    "branch_scope": "all",
    "selected_branches": ["main", "staging"],
    "commit_scope": "all",
    "commit_since": null,
    "pr_scope": "all",
    "issue_scope": "all",
    "include_docs": true,
    "include_commits": true,
    "include_pull_requests": true,
    "include_reviews": true,
    "include_issues": true,
    "include_comments": true,
    "include_code": false
  },
  "created_at": "2026-11-16T12:05:00Z",
  "last_synced_at": null
}
```

---

## 5. Synchronisation & Worker Triggering

### 5.1 Trigger Mapping Synchronisation
Enqueue an asynchronous background sync job for the mapping.

- **Method / Route**: `POST /projects/{project_id}/integrations/mappings/{mapping_id}/sync`
- **Required Permission**: `project.integrations.sync`
- **Request Body**:
```json
{
  "sync_mode": "manual"
}
```

- **Response (`202 Accepted`)**:
```json
{
  "job_id": "b9f8e7d6-3333-6666-7777-123456789abc",
  "mapping_id": "c1a2b3c4-2222-5555-8888-fedcba654321",
  "status": "queued",
  "message": "GitHub synchronization job queued successfully."
}
```

---

## 6. Evidence Querying & Provenance

### 6.1 List Project Evidence
Retrieve ingested GitHub evidence items with complete branch and PR attribution metadata.

- **Method / Route**: `GET /projects/{project_id}/evidence`
- **Required Permission**: `project.read`
- **Query Parameters**:
  - `provider` (optional): Filter by provider (e.g. `github`).
  - `category` (optional): Filter by category (`commit`, `pull_request`, `issue`, `design_document`).
  - `limit` (optional, default `20`): Page limit.
  - `offset` (optional, default `0`): Page offset.

- **Example Response Item (`EvidenceItemSummary`)**:
```json
{
  "id": "7a8b9c0d-4444-7777-8888-0987654321fe",
  "project_id": "ed33c53a-7678-4d5b-8212-64c233897142",
  "provider": "github",
  "category": "commit",
  "external_id": "a1b2c3d4e5f678901234567890abcdef12345678",
  "title": "feat(auth): Add Argon2id password hashing and session rotation",
  "author": "octocat",
  "metadata_json": {
    "branches": ["main", "feature-auth"],
    "sha": "a1b2c3d4e5f678901234567890abcdef12345678",
    "committer": "octocat",
    "commit_date": "2026-11-15T14:30:00Z",
    "changed_files_count": 4,
    "additions": 120,
    "deletions": 15
  },
  "created_at": "2026-11-16T12:10:00Z"
}
```
