# GitHub Integration Implementation Plan
**The Handover — Intelligent Project Knowledge Reconstruction & Handover Platform**
**Module**: Connected Sources → GitHub Integration
**Date**: November 16, 2026

---

## 1. Objectives & Principles

1. **One Central GitHub Connected Source**: GitHub remains ONE card in Connected Sources. The user connects once with a Fine-Grained Personal Access Token (PAT).
2. **Automatic Resource Discovery**: Repositories accessible to the PAT are discovered automatically via `GET https://api.github.com/user/repos` without manual user entry of owner/repo names or URLs.
3. **Multi-Repository Selection & Granular Sync Configuration**: The user selects multiple repositories, chooses branch scope (default branch vs all branches), commit scope (all history vs date range), documentation, PRs, issues, reviews/comments, and optional source code indexing.
4. **Persistent Background Execution**: Ingestion runs via PostgreSQL worker leases, returning HTTP 202 immediately, updating live job tracking, and sending persistent in-app notifications upon completion or failure.
5. **Team Contributor Intelligence**: Match GitHub commit authors and PR creators against the project's uploaded and approved Team Roster using a conservative matching hierarchy, classify work across 17 technical domains, and evaluate responsibility alignment.
6. **Dual Storage & Vector Indexing**: Structured records and provenance stored in PostgreSQL; chunked text embedded via `nomic-embed-text` into project-isolated ChromaDB collections (`ipkrh_{project_id}`).
7. **Zero Fabrication**: All records stem from authorized GitHub REST APIs or uploaded documents.

---

## 2. Technical Architecture & Phased Workflows

```
┌─────────────────────────────────────────────────────────────┐
│ 1. PAT AUTHENTICATION (Modal Step 1)                       │
│    User enters Fine-Grained PAT (Metadata, Contents,        │
│    Pull requests, Issues read-only)                         │
│    Backend validates GET /user, retrieves GitHub identity, │
│    encrypts token with AES-256-GCM, stores SourceConnection │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│ 2. DYNAMIC DISCOVERY & SELECTION (Modal Step 2)             │
│    GET /integrations/connections/{id}/github/repositories   │
│    Discovers all accessible repos (private, public, orgs)   │
│    Multi-select with search, filters, already-mapped badge │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│ 3. SYNC SCOPE CONFIGURATION (Modal Step 3)                  │
│    Branch Scope (default vs all), History (all vs date),    │
│    Toggles: Docs, Commits, PRs, Issues, Reviews, Code       │
│    Batch mappings created via POST .../batch-mappings       │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│ 4. BACKGROUND SYNCHRONISATION (PostgreSQL Worker Daemon)     │
│    - Repo metadata & README/Docs (Contents API)             │
│    - Branch discovery & multi-branch commit extraction      │
│    - PRs (reviews, inline comments, changed files, commits) │
│    - Issues (comments, labels, milestones, exclude PRs)     │
│    - Incremental sync checkpoints (ETags, cursors)          │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│ 5. CONTRIBUTOR INTELLIGENCE & CLASSIFICATION                │
│    - Conservative identity match against Team Roster        │
│    - Classification into 17 technical categories            │
│    - Responsibility alignment evaluation (ALIGNED, etc.)    │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│ 6. PERSISTENCE, INDEXING & NOTIFICATIONS                    │
│    - PostgreSQL evidence_items & evidence_contents          │
│    - nomic-embed-text embeddings into ChromaDB collection   │
│    - Persistent NotificationItem generated for user         │
│    - Top nav active job indicator & toast completion        │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Step-by-Step Implementation Strategy

### Stage 1: Backend Client & Schema Enhancements
1. **GitHub Client Extensions (`github_client.py`)**:
   - Add `fetch_user_profile(access_token)` -> validates PAT, retrieves identity, rate limit.
   - Add `fetch_branches(owner, repo, access_token)` -> retrieves repository branches.
   - Add `fetch_commit_detail(owner, repo, sha, access_token)` -> retrieves file changes, additions, deletions, patch stats.
   - Add `fetch_contributors(owner, repo, access_token)` -> retrieves contributor statistics.
   - Add `fetch_pull_request_commits(owner, repo, pr_number, access_token)` -> retrieves commit SHAs associated with a PR.
   - Update `_repo_candidate_from_json` to include language, topics, created_at, pushed_at, is_fork, is_archived, is_disabled, open_issues_count.
2. **Schema Enhancements (`schemas/integrations.py`)**:
   - Update `GitHubRepositoryCandidate` with new discovery metadata and `already_mapped: bool`.
   - Update `CreateGitHubMappingRequest` and sync configs to accept `branch_scope`, `selected_branches`, `commit_scope`, `commit_since`, `include_reviews`, `include_comments`, `include_code`.

### Stage 2: PAT Connection Endpoint Refinement
1. Refine `POST /organisations/{org_id}/sources` in `backend/app/api/routes/sources.py`:
   - When `provider == "github"`, call `GitHubClient.fetch_user_profile` with the submitted token.
   - If invalid/expired or rate-limited, immediately return clear typed error.
   - Automatically extract and populate GitHub username (`login`), numeric ID, and profile metadata.
   - Encrypt token with AES-256-GCM and store in `SourceConnection` and `UserSourceAuthorisation`.

### Stage 3: Repository Discovery with Mapped Indicator
1. In `SourceIntegrationService.discover_github_repositories`:
   - Accept optional `project_id`.
   - Query existing `ProjectSourceMapping` records for that project.
   - Mark matching repositories with `already_mapped = True`.

### Stage 4: Multi-Branch Commit Extraction & Metadata Preservation
1. In `GitHubSyncOrchestrator`:
   - Check `config.get("branch_scope")`:
     - If `"all"`, fetch branches via `_client.fetch_branches`, iterate through branches, and fetch commits.
     - Deduplicate commits by SHA while recording all branches where the SHA was seen in `metadata_json["branches"]`.
   - Parse `Co-authored-by:` trailers in commit message and save as candidate attribution co-authors.
   - Flag `unlinked_git_author: bool` if `github_author_login` is None.
   - Store `parent_shas`, signature verification status, and commit stats.
   - Call `_client.fetch_contributors` to record contributor statistics as supplementary evidence.
   - Link PR associated commits in PR evidence metadata.

### Stage 5: Identity Matching Refinement
1. In `ContributionAttributionService`:
   - Support GitHub noreply mapping (`username@users.noreply.github.com` and `ID+username@users.noreply.github.com`).
   - Treat display-name-only matches as ambiguous candidates (`AMBIGUOUS` with 0.5 confidence).
   - Support `VERIFIED_MATCH`, `CANDIDATE_MATCH`, `AMBIGUOUS`, `UNMATCHED`, `REJECTED_MATCH`.

### Stage 6: Frontend Connected Sources & Modal Overhaul
1. In `ConnectSourceModal.tsx`:
   - Multi-step flow for GitHub:
     - Step 1: PAT input with show/hide password toggle, clear instructions, and expandable permission guide.
     - Step 2: Live discovery list with search, visibility filters (All, Private, Public, Owned, Collaborator, Org), pagination, already-mapped badge, and multi-selection checkboxes.
     - Step 3: Granular sync configuration:
       - Documentation toggle (README + Markdown docs)
       - Branch scope: Default branch vs All accessible branches
       - Commit history: All history vs Custom date range
       - Pull requests toggle (All vs Open)
       - Issues toggle (All vs Open)
       - Reviews & Comments toggle
       - Source code indexing toggle
     - Step 4: Confirmation screen showing selected project, GitHub account, repository count, and scope summary -> calls `batch_create_mappings` + triggers background sync.
2. In `KnowledgePage.tsx`:
   - Update GitHub source card:
     - Real dynamic status badges (`Connected`, `Sync Running`, `Sync Completed`, `Sync Failed`, `Reauthorisation Required`, `Not Connected`).
     - Display authenticated GitHub account `@login`.
     - Display mapped repositories count and total imported records.
     - Action buttons: "Connect GitHub" (when disconnected), "Manage Repositories", "Sync Now", "Sync History".

### Stage 7: Automated Test Suite & Quality Verification
1. Run pytest suite covering:
   - PAT validation (valid, invalid, expired).
   - Repository discovery (pagination, filters, already-mapped).
   - Multi-branch commit extraction & SHA deduplication.
   - PR & issue ingestion with associated commits and review comments.
   - Identity matching with noreply emails and ambiguous candidates.
   - Contribution classification across 17 technical categories.
   - Incremental sync idempotency.
2. Run end-to-end browser verification via CDP script and capture high-resolution screenshots.
