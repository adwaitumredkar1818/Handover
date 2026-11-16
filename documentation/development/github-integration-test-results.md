# GitHub Connected Source — Comprehensive Test Results Report

**Document Status:** Complete & Verified  
**Date:** 2026-11-16  
**System:** The Handover  
**Scope:** GitHub PAT Authentication, Resource Discovery, Multi-Branch Synchronisation, and Contributor Intelligence  

---

## 1. Test Execution Summary

| Test Suite / Target | Command | Result | Duration |
| :--- | :--- | :--- | :--- |
| **GitHub Integration Core** | `pytest backend/tests/test_github_integration.py` | **1 Passed** | 2.81s |
| **GitHub PAT & Intelligence** | `pytest backend/tests/test_github_pat_and_contributor_intelligence.py` | **3 Passed** | 22.37s |
| **Source Authorization Policy** | `pytest backend/tests/test_source_authorization_policy.py` | **2 Passed** | 20.78s |
| **Team Roster & Attribution** | `pytest backend/tests/test_team_roster_and_attribution.py` | **3 Passed** | 12.45s |
| **Jira Integration Regression** | `pytest backend/tests/test_jira_integration.py` | **1 Passed** | 3.12s |
| **Slack Integration Regression** | `pytest backend/tests/test_slack_integration.py` | **3 Passed** | 8.90s |
| **Frontend Production Build** | `cd frontend && npm run build` | **69/69 Pages Passed** | 21.5s |
| **CDP UI Verification** | `node scripts/verify_github_ui.mjs` | **5/5 Screenshots Captured** | 24.2s |

---

## 2. Functional Test Specifications (Tests A through H)

### Test A: Personal Access Token Validation & Auto-Discovery
- **File**: `backend/tests/test_github_pat_and_contributor_intelligence.py::test_github_pat_validation_and_user_profile`
- **Objective**: Verify that submitting a Fine-Grained PAT triggers `GET /user`, automatically resolves `account_identifier` and `display_name` without requiring manual typing, stores the encrypted token with AES-256-GCM, and properly handles invalid credentials.
- **Observed Behavior**:
  - Valid PAT returned HTTP 201 with `account_identifier: "octocat"` and `display_name: "GitHub (@octocat)"`.
  - Stored token record verified encrypted using `LocalTokenEncryptionService`.
  - Bad PAT rejected with HTTP 400 and `error.code: "INTEGRATION_AUTH_ERROR"`.
- **Status**: **PASS**

### Test B: Dynamic Repository Discovery & Pre-Existing Mapping Flagging
- **File**: `backend/tests/test_github_pat_and_contributor_intelligence.py::test_multi_branch_commit_deduplication_and_pr_extraction`
- **Objective**: Verify that repositories accessible to the PAT are discovered, mapped, and cross-referenced with `already_mapped` flag against project source mappings.
- **Observed Behavior**:
  - `GET /api/v1/integrations/connections/{id}/github/repositories?project_id={proj_id}` returned candidate repositories.
  - Candidates returned language (`Python`), topics (`["fastapi", "ai"]`), and initial `already_mapped: false`.
  - After mapping, subsequent discovery correctly marked `already_mapped: true`.
- **Status**: **PASS**

### Test C: Multi-Branch Synchronisation & Commit Deduplication
- **File**: `backend/tests/test_github_pat_and_contributor_intelligence.py::test_multi_branch_commit_deduplication_and_pr_extraction`
- **Objective**: Verify that commits present across multiple branches (e.g. `main` and `feature-auth`) are deduplicated into a single `EvidenceItem` while preserving all branch names in `metadata_json["branches"]`.
- **Observed Behavior**:
  - Sync worker discovered branches `main` and `feature-auth` with identical commit SHA `a1b2c3d4...`.
  - Querying project evidence returned exactly 1 commit record.
  - `commit_item["metadata_json"]["branches"]` contained both `"main"` and `"feature-auth"`.
- **Status**: **PASS**

### Test D: Pull Request Extraction with Associated Commits
- **File**: `backend/tests/test_github_pat_and_contributor_intelligence.py::test_multi_branch_commit_deduplication_and_pr_extraction`
- **Objective**: Verify that pull requests are extracted with associated commit SHAs preserved in metadata.
- **Observed Behavior**:
  - Pull request #1 extracted as `EvidenceCategory.PULL_REQUEST`.
  - `pr_item["metadata_json"]["associated_commit_shas"]` contained `["a1b2c3d4..."]`.
- **Status**: **PASS**

### Test E: Issue Extraction Distinct from Pull Requests
- **File**: `backend/tests/test_github_pat_and_contributor_intelligence.py::test_multi_branch_commit_deduplication_and_pr_extraction`
- **Objective**: Verify that GitHub issues are extracted separately from pull requests without collision.
- **Observed Behavior**:
  - Issue #1 extracted as `EvidenceCategory.ISSUE`.
  - `metadata_json["number"] == 1` and `metadata_json["state"] == "open"`.
- **Status**: **PASS**

### Test F: Contributor Identity Hierarchy Resolution
- **File**: `backend/tests/test_github_pat_and_contributor_intelligence.py::test_contributor_identity_matching_hierarchy`
- **Objective**: Verify deterministic matching order against the approved team roster: Numeric ID $\to$ Username $\to$ Author Email $\to$ Noreply Email $\to$ Ambiguous Name.
- **Observed Behavior**:
  - Exact GitHub numeric ID matched with confidence `1.00`.
  - GitHub username matched with confidence `1.00`.
  - Direct commit author email matched with confidence `0.95`.
  - GitHub noreply email (`username@users.noreply.github.com`) matched with confidence `0.95`.
  - Display name match without email or ID returned confidence `0.50` with `ambiguous_name_match` warning.
  - Unknown contributor categorized as `unmatched_contributor` with confidence `0.00`.
- **Status**: **PASS**

### Test G: Technical Contribution Classification (17 Categories)
- **File**: `backend/tests/test_team_roster_and_attribution.py`
- **Objective**: Verify commit messages and file changes are classified into 17 domain categories.
- **Observed Behavior**:
  - Commits modifying API endpoints classified as `api_design` and `backend_logic`.
  - Commits modifying SQL/Alembic classified as `database_migrations`.
  - Commits modifying React/Next.js classified as `frontend_ui`.
  - Commits modifying Docker/Actions classified as `devops_ci_cd`.
- **Status**: **PASS**

### Test H: Responsibility Alignment Evaluation
- **File**: `backend/tests/test_team_roster_and_attribution.py`
- **Objective**: Verify contribution categories are compared against team roster assigned responsibilities.
- **Observed Behavior**:
  - Backend engineer contributing API code marked `responsibility_alignment: "aligned"`.
  - Frontend engineer committing database migrations marked `responsibility_alignment: "unaligned"`.
- **Status**: **PASS**

---

## 3. UI/Browser Automated Verification

Automated headless Chrome CDP execution verified all modal steps without errors:
- `ui_github_01_sources_overview.png`: Connected Sources dashboard with GitHub card.
- `ui_github_02_modal_step1_pat.png`: Fine-Grained PAT input with password reveal & expanded permissions accordion.
- `ui_github_03_modal_step2_discovery.png`: Repository list with search, category filtering, language badges, and `already_mapped` badges.
- `ui_github_04_modal_step3_scope.png`: Granular scope controls (Branches, Commits date range, PR reviews, Issue comments, Code indexing).
- `ui_github_05_modal_step4_confirm.png`: Review summary card and worker lease notice.

---

## 4. Conclusion

All functional requirements, architectural constraints, and security standards have been met. All tests pass with zero regressions across existing integration and evidence modules.
