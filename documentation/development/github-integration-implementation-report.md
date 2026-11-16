# GitHub Connected Source — Complete Implementation Report

**Document Status:** Complete & Verified  
**Date:** 2026-11-16  
**System:** The Handover (Intelligent Project Knowledge Reconstruction & Handover Platform)  
**Module:** Connected Sources → GitHub Connected Source  

---

## 1. Executive Summary

The GitHub Connected Source has been fully implemented into **The Handover** platform as a unified, first-class source provider in the **Connected Sources** and **Evidence Center** modules.

In accordance with architectural principles:
1. **Single Source Provider**: GitHub is connected once per organisation using a Fine-Grained Personal Access Token (PAT). Contribution intelligence and team attribution are integrated directly into this single connection—no secondary contributor tokens or duplicate connection flows are created.
2. **Automatic Identity Discovery**: The user provides only their Fine-Grained PAT. The backend calls `GET /user` to validate credentials, retrieve the authenticated username (`login`), numeric user ID, avatar, and OAuth scopes automatically, eliminating manual handle entry errors.
3. **Dynamic Repository Discovery**: Repositories accessible to the token are discovered in real time, enriched with metadata (language, topics, visibility, open issues, fork/archived flags), and cross-referenced against existing project mappings with an `already_mapped` indicator.
4. **Granular Sync Scope**: Users configure repository sync scope via an intuitive 4-step modal: Documentation/README, Branch Scope (default branch vs. all accessible branches), Commit History (full history vs. date cutoff), Pull Requests (all vs. open, with reviews), Issues (all vs. open, with comments), and experimental Source Code indexing.
5. **Multi-Branch Deduplication & Full Provenance**: Commits existing on multiple branches are deduplicated into a single canonical evidence record while preserving all associated branch labels in `metadata_json.branches`. Pull requests preserve associated commit SHAs.
6. **Contributor Intelligence & Identity Resolution**: Git authors, committers, and PR/issue authors are resolved against the approved **Team Roster** using a deterministic confidence hierarchy (numeric user ID $\to$ verified login $\to$ commit email $\to$ GitHub noreply address $\to$ ambiguous display name). Each contribution is classified across 17 technical categories and evaluated for responsibility alignment.
7. **Production Execution**: Backed entirely by PostgreSQL job records and worker leases with ChromaDB vector indexing (`nomic-embed-text`). Zero synthetic or fabricated data is introduced into production paths.

---

## 2. Architecture & Components

```
┌────────────────────────────────────────────────────────────────────────┐
│                        Next.js Frontend (React 19)                     │
│  ┌─────────────────────────┐         ┌──────────────────────────────┐  │
│  │ Connected Sources Page  │ ──────▶ │ 4-Step GitHub Connect Wizard │  │
│  └─────────────────────────┘         └──────────────────────────────┘  │
└─────────────────────────────────────┬──────────────────────────────────┘
                                      │ REST APIs / HTTPS
                                      ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        FastAPI Modular Backend                         │
│  ┌─────────────────────────┐         ┌──────────────────────────────┐  │
│  │ routes/sources.py       │ ──────▶ │ routes/integrations.py       │  │
│  │ (PAT Auto-Validation)   │         │ (Repo Discovery & Mappings)  │  │
│  └─────────────────────────┘         └──────────────────────────────┘  │
│               │                                     │                  │
│               ▼                                     ▼                  │
│  ┌─────────────────────────┐         ┌──────────────────────────────┐  │
│  │ TokenEncryptionService  │         │ GitHubSyncService            │  │
│  │ (AES-256-GCM Envelope)  │         │ (Multi-Branch & PR Commits)  │  │
│  └─────────────────────────┘         └──────────────────────────────┘  │
│                                                     │                  │
│                                                     ▼                  │
│                                      ┌──────────────────────────────┐  │
│                                      │ ContributionAttributionSvc   │  │
│                                      │ (Roster Matching & 17 Classes)│ │
│                                      └──────────────────────────────┘  │
└─────────────────────────────────────┬──────────────────────────────────┘
                                      │
            ┌─────────────────────────┴─────────────────────────┐
            ▼                                                   ▼
┌──────────────────────┐                             ┌──────────────────────┐
│  PostgreSQL (Truth)  │                             │ ChromaDB (Secondary) │
│ - source_connections │                             │ - nomic-embed-text   │
│ - project_mappings   │                             │ - project-isolated   │
│ - evidence_items     │                             │   collections        │
│ - background_jobs    │                             │ - hybrid search      │
│ - audit_logs         │                             └──────────────────────┘
└──────────────────────┘
```

---

## 3. Key Implementation Details

### 3.1 Personal Access Token Validation & Auto-Discovery
- **Endpoint**: `POST /api/v1/organisations/{org_id}/sources`
- When `provider: "github"` is received, the backend instantiates `GitHubClient` and executes `GET /user` against the GitHub API.
- Upon success, `gh_profile.login` and `gh_profile.id` are extracted.
- The `account_identifier` and `display_name` are automatically set to `@{login}` without requiring the user to type their username.
- The PAT is encrypted at rest using AES-256-GCM envelope encryption via `LocalTokenEncryptionService`.
- If an invalid PAT is submitted, GitHub's 401 response is surfaced as an actionable `IntegrationAuthError`.

### 3.2 Repository Discovery & Project Conflict Detection
- **Endpoint**: `GET /api/v1/integrations/connections/{conn_id}/github/repositories?project_id={proj_id}`
- Repositories accessible to the PAT are retrieved via `GET /user/repos`.
- For each candidate, the service checks active `ProjectSourceMapping` records in the target project.
- If a repository is already mapped to the project, `already_mapped: true` is populated, disabling duplicate mapping in the UI.

### 3.3 Granular Sync Scope Configuration
- Mappings are created via `POST /api/v1/projects/{proj_id}/integrations/github/mappings` with:
  - `branch_scope`: `"default"` or `"all"`.
  - `selected_branches`: explicit branch list (optional).
  - `commit_scope`: `"all"` or `"since"`.
  - `commit_since`: ISO 8601 timestamp cutoff.
  - `pr_scope`: `"all"` or `"open"`.
  - `issue_scope`: `"all"` or `"open"`.
  - `include_docs`: boolean (README and docs folder).
  - `include_commits`: boolean.
  - `include_pull_requests`: boolean.
  - `include_reviews`: boolean.
  - `include_issues`: boolean.
  - `include_comments`: boolean.
  - `include_code`: boolean (experimental symbol extraction).
- Settings are persisted in `sync_config_json` on the `project_source_mappings` table.

### 3.4 Multi-Branch Deduplication & PR Ingestion
- `GitHubSyncService` discovers all branches via `GET /repos/{owner}/{repo}/branches` when `branch_scope == "all"`.
- Commits are fetched per branch. A dictionary `seen_shas_to_branches: dict[str, set[str]]` tracks every branch where a commit SHA appears.
- Commits are deduplicated across branches: exactly one `EvidenceItem` is stored per unique SHA, with all branch names recorded in `metadata_json["branches"]`.
- Pull requests are fetched with `fetch_pull_request_commits`, linking associated commit SHAs in `metadata_json["associated_commit_shas"]`.
- Issues are extracted separately with `fetch_issues`, excluding pull request items.

### 3.5 Contributor Attribution & Identity Resolution
- Implemented in `backend/app/services/contribution_attribution.py`:
  - **Hierarchy**:
    1. Numeric GitHub user ID match against roster (`confidence: 1.00`).
    2. Verified GitHub username match (`confidence: 1.00`).
    3. Git commit author email match (`confidence: 0.95`).
    4. GitHub private noreply email (`username@users.noreply.github.com` or `ID+username@users.noreply.github.com`, `confidence: 0.95`).
    5. Ambiguous author display name (`confidence: 0.50`, flagged with `warning: "ambiguous_name_match"`).
  - **17 Technical Contribution Categories**:
    - `core_architecture`, `api_design`, `backend_logic`, `frontend_ui`, `database_migrations`, `security_auth`, `devops_ci_cd`, `testing_qa`, `documentation`, `performance_optimization`, `dependency_management`, `refactoring`, `bug_fixing`, `code_review`, `project_management`, `infrastructure_config`, `data_pipeline`.
  - **Responsibility Alignment**: Compares contribution category against team roster assigned responsibilities (`aligned`, `unaligned`, `unassigned`).

---

## 4. UI/UX Verification & Screenshots

The 4-step GitHub modal in `frontend/src/components/modals/ConnectSourceModal.tsx` and the Connected Sources overview were verified in Chrome headless via CDP:

| Screenshot | Description | Artifact Path |
| :--- | :--- | :--- |
| **ui_github_01_sources_overview.png** | Connected Sources page showing GitHub source card with status & repository stats | `C:\Users\Shubham\.gemini\antigravity\brain\f1e70b6b-09c5-4a12-819b-9553d61aef02\ui_github_01_sources_overview.png` |
| **ui_github_02_modal_step1_pat.png** | Step 1: Fine-Grained PAT input with password reveal & expanded permissions guide | `C:\Users\Shubham\.gemini\antigravity\brain\f1e70b6b-09c5-4a12-819b-9553d61aef02\ui_github_02_modal_step1_pat.png` |
| **ui_github_03_modal_step2_discovery.png** | Step 2: Discovered repositories list with search, category filters & already-mapped pills | `C:\Users\Shubham\.gemini\antigravity\brain\f1e70b6b-09c5-4a12-819b-9553d61aef02\ui_github_03_modal_step2_discovery.png` |
| **ui_github_04_modal_step3_scope.png** | Step 3: Granular sync scope (branches, commits date range, PR reviews, issue comments) | `C:\Users\Shubham\.gemini\antigravity\brain\f1e70b6b-09c5-4a12-819b-9553d61aef02\ui_github_04_modal_step3_scope.png` |
| **ui_github_05_modal_step4_confirm.png** | Step 4: Review summary card, background worker queue notice, and confirm action | `C:\Users\Shubham\.gemini\antigravity\brain\f1e70b6b-09c5-4a12-819b-9553d61aef02\ui_github_05_modal_step4_confirm.png` |

---

## 5. Security & Governance Compliance

- **No Hardcoded Secrets**: All tokens stored encrypted with AES-256-GCM.
- **Fail-Closed ACLs**: `ProjectSourceMapping` and `UserSourceAuthorisation` records enforce that project membership does not grant source read access unless the user holds a valid delegated source authorisation.
- **Single Inference Coordination**: Sync workers respect `OLLAMA_MAX_CONCURRENT_AI_JOBS=1` to prevent VRAM exhaustion on RTX 4050.
- **Audit Logging**: Every source registration, token rotation, repository discovery, mapping creation, and sync trigger is recorded in the immutable PostgreSQL `audit_logs` table.
