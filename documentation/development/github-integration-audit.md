# GitHub Integration Comprehensive Audit Report
**The Handover — Intelligent Project Knowledge Reconstruction & Handover Platform**
**Date**: November 16, 2026
**Scope**: Connected Sources → GitHub Integration, PAT Authentication, Dynamic Repository Discovery, Multi-Branch & Commit Extraction, Pull Requests, Issues, Contributor Intelligence, Team Roster Reconciliation, and ChromaDB Vector Indexing.

---

## 1. Executive Summary & Audit Overview

The Handover requires a unified, production-grade GitHub Connected Source enabling project teams to connect GitHub using Fine-Grained Personal Access Tokens (PATs), discover all permitted repositories dynamically, configure ingestion scope (documentation, commits across default/all branches, PRs, issues, reviews, comments, and optional source code indexing), run persistent background synchronisation via PostgreSQL worker leases, and automatically resolve contributor identities against the project's human-approved Team Roster.

This audit evaluates the codebase across 10 critical architectural layers to ensure zero data fabrication, strict fail-closed security (project membership != source access), and complete end-to-end evidence persistence.

---

## 2. Inventory of Existing Implementation & Working Components

### 2.1 Backend Core Services & Models
1. **GitHub REST Client (`backend/app/services/integrations/github_client.py`)**:
   - `GitHubClient` implements read-only GitHub REST API calls (`/user`, `/user/repos`, `/repos/{owner}/{repo}`, `/issues`, `/pulls`, `/commits`, `/readme`, `/git/trees`, `/contents/{path}`, `/discussions`).
   - Standard headers: `X-GitHub-Api-Version: 2022-11-28`, `Accept: application/vnd.github+json`, User-Agent, and ETag conditional requests (`If-None-Match`).
   - Rate-limit detection (`is_rate_limit_response`), error mapping (`raise_for_provider_error`), and pagination link parsing (`_has_next_link`).
2. **GitHub Sync Orchestrator (`backend/app/services/integrations/github_sync.py`)**:
   - `GitHubSyncOrchestrator` normalises repository metadata, issues, pull requests (with inline review comments and changed files), commits (with author and committer separation), documentation, and discussions into canonical `NormalizedSourceEvidence` items.
   - Enforces read-time repository permission checks before ingestion.
   - Updates incremental sync cursors (`last_updated_since`, `issues_etag`, `commits_etag`, `last_completed_at`).
3. **Database Models & Tables (`backend/app/models/`)**:
   - `SourceConnection`: Encrypted external workspace connection metadata.
   - `UserSourceAuthorisation`: Delegated per-user encrypted access tokens (`encrypted_access_token`).
   - `SourceAccessPolicy`: Granular read-time source ACL policy (`open`, `organisation_members`, `verified_users_only`).
   - `ProjectSourceMapping`: Binds a specific external resource (e.g. `owner/repo`) to a project.
   - `SourceSyncRun`: Durable record of every sync execution with metrics, cursors, warnings, and duration.
   - `EvidenceItem` & `EvidenceContent`: Canonical evidence records in PostgreSQL.
   - `TeamRosterMember` & `ContributionAttribution`: Roster reconciliation and contribution classification across 17 technical categories with responsibility alignment.
   - `NotificationItem`: Persistent user notifications for sync success, partial sync, and failures.
4. **Token Encryption Architecture**:
   - `LocalTokenEncryptionService`: AES-256-GCM envelope encryption with unique nonce and HMAC authentication for all source tokens at rest.
5. **Background Worker Daemon (`backend/app/worker.py` & `sync_worker.py`)**:
   - PostgreSQL row leases (`locked_by`, `lease_expires_at`, `attempt_count`) ensuring that long-running ingestion survives browser refresh, page transitions, and worker restarts.

---

## 3. Existing Endpoints Inventory

| Method | Endpoint | Description | Status |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/organisations/{org_id}/sources` | Register source credential (PAT/OAuth) | Active |
| `GET` | `/api/v1/organisations/{org_id}/sources` | List connected sources for an organisation | Active |
| `GET` | `/api/v1/organisations/{org_id}/integrations/connections` | List source connections with user auth status | Active |
| `GET` | `/api/v1/integrations/connections/{id}/github/repositories` | Discover accessible GitHub repositories | Active |
| `POST` | `/api/v1/projects/{project_id}/integrations/github/mappings` | Map single repository to project | Active |
| `POST` | `/api/v1/projects/{project_id}/integrations/batch-mappings` | Batch map repositories / projects / channels | Active |
| `GET` | `/api/v1/projects/{project_id}/integrations/mappings` | List active source mappings for project | Active |
| `DELETE` | `/api/v1/projects/{project_id}/integrations/mappings/{id}` | Disable mapping (preserves historical evidence) | Active |
| `POST` | `/api/v1/projects/{project_id}/integrations/mappings/{id}/sync` | Trigger background sync (returns HTTP 202) | Active |
| `GET` | `/api/v1/projects/{project_id}/integrations/sync-runs` | List sync runs history | Active |
| `GET` | `/api/v1/integrations/sync-runs/{id}` | Inspect sync run details | Active |
| `POST` | `/api/v1/integrations/sync-runs/{id}/cancel` | Cancel queued or running sync job | Active |
| `GET` | `/api/v1/projects/{project_id}/roster/members` | List extracted team roster members | Active |
| `PATCH` | `/api/v1/projects/{project_id}/roster/members/{id}/reconcile`| Reconcile candidate against project membership | Active |
| `GET` | `/api/v1/projects/{project_id}/roster/attributions` | List commit and PR attributions & alignments | Active |
| `GET` | `/api/v1/notifications` | List user persistent notifications | Active |
| `GET` | `/api/v1/projects/{project_id}/jobs/active` | Live tracking of background jobs | Active |

---

## 4. Identified Architectural Gaps & Implementation Needs

1. **GitHub PAT Connection Workflow**:
   - The user must only input the Fine-Grained PAT (and optional Display Name). The backend must automatically validate the PAT against `GET https://api.github.com/user`, retrieve GitHub username, numeric ID, avatar URL, check rate-limits, and encrypt the token with AES-256-GCM.
2. **Repository Discovery Metadata**:
   - `GitHubRepositoryCandidate` currently returns 11 basic fields. Part 4.1 requires: `language`, `topics`, `created_at`, `pushed_at`, `is_fork`, `is_archived`, `is_disabled`, `open_issues_count`, and `already_mapped` relative to the current project.
3. **Multi-Branch Commit History Extraction**:
   - `fetch_commits` currently defaults to `default_branch` only. Part 8 requires branch discovery (`GET /repos/{owner}/{repo}/branches`), supporting "all accessible branches", branch-specific extraction (`GET /repos/{owner}/{repo}/commits?sha={branch}`), deduplicating identical commit SHAs across branches, and storing the complete list of discovered branches in metadata.
4. **Commit Metadata & Unlinked Identity Extraction**:
   - Commit records must preserve `parent_shas`, GPG signature verification status, unlinked author flags (`unlinked_git_author`), commit stats (additions, deletions, changes), and parse `Co-authored-by:` trailers as attribution candidates.
5. **Supplementary Contributor Statistics**:
   - Implement `fetch_contributors` (`GET /repos/{owner}/{repo}/contributors`) to capture contributor profiles, numeric IDs, and contribution counts as supplementary evidence without replacing repository-first commit extraction.
6. **PR Associated Commits & Reviews**:
   - Fetch associated commit SHAs for pull requests (`GET /repos/{owner}/{repo}/pulls/{number}/commits`) to preserve PR-to-commit relationships.
7. **Identity Matching Hierarchy Enhancement**:
   - Support GitHub noreply email mapping (`username@users.noreply.github.com` and `ID+username@users.noreply.github.com`), treat display-name-only matches as ambiguous candidates (`AMBIGUOUS`), and preserve distinct author vs committer records.
8. **Connected Sources UI (GitHub Card & Modal)**:
   - Enhance the GitHub source card to reflect all dynamic states: Not Connected, Connected, Repository Selection Required, Sync Queued, Sync Running, Sync Completed, Partially Completed, Sync Failed, Reauthorisation Required.
   - Implement the multi-step GitHub modal: Step 1 (PAT input & permission guide), Step 2 (automatic repository discovery with search, filters, multi-select), Step 3 (sync configuration: branches, history, docs, commits, PRs, issues, reviews/comments, code indexing), Step 4 (final confirmation & instant background launch).

---

## 5. Security & Isolation Audit

- **Project Membership != Source Access**: Verified. Project members cannot query private repository evidence unless their own user identity has a valid delegated authorisation on the `SourceAccessPolicy`.
- **Credential Storage**: No raw tokens are ever persisted in PostgreSQL or returned in API responses. All PATs are encrypted with AES-256-GCM envelope encryption.
- **Fail-Closed Retrieval**: ChromaDB vector retrieval and PostgreSQL tsvector search enforce source ACL checks before surfacing evidence chunks or entering LLM context.
- **Read-Only Scope**: All GitHub REST API operations use strict GET requests; no repository modification, commit creation, or issue state tampering occurs.
