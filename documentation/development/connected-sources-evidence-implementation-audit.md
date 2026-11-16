# Connected Sources & Evidence Center — Comprehensive Implementation Audit

**Platform**: The Handover (Intelligent Project Knowledge Reconstruction & Handover Platform)  
**Modules**: Module 2 (Evidence Workspace), Module 1 (Project Workspace / Team Identity), Core Integrations (GitHub, Jira, Slack, Document Uploads)  
**Date**: November 2026  
**Auditor**: Antigravity Platform Agent  

---

## Executive Summary

This document performs an exhaustive, capability-by-capability architectural audit of **The Handover**'s existing source connection, evidence ingestion, document extraction, vector indexing, background synchronisation, team identity resolution, and notification systems.

The platform already possesses a robust, secure backend foundation:
- Symmetric credential encryption via AES-256-GCM (`LocalTokenEncryptionService`)
- PostgreSQL canonical storage with strict constraints, tenancy isolation, and foreign keys
- Dual private storage backend (local encrypted default and Supabase Storage)
- Fine-grained RBAC and fail-closed source ACL checks (`SourceAccessPolicyService`)
- Unified evidence ledger (`evidence_items`, `evidence_extracted_contents`, `evidence_pages`, `document_chunks`)
- Dual-pass hybrid retrieval (PostgreSQL full-text search + project-isolated ChromaDB HTTP vectors via `nomic-embed-text`)
- OCR pipeline via local Ollama GLM OCR (`glm-ocr:latest`) and text extraction via PyMuPDF and `python-docx`
- Background worker architecture backed by PostgreSQL job records (`background_jobs`)

However, significant gaps exist between the current codebase and the target state:
1. **GitHub Connection & Selection**: GitHub connection requires manually typing repository names instead of dynamically discovering and presenting accessible repositories via `GET /user/repos`.
2. **Jira Connection & Selection**: Jira modal asks users for a manual `Target Jira Project Key` instead of automatically discovering accessible sites and projects via Atlassian REST APIs.
3. **Slack Integration**: Slack is partially defined in enums and frontend mocks, but lacks a backend client (`SlackClient`), sync orchestrator (`SlackSyncOrchestrator`), check constraint support in `models/integration.py`, and dynamic channel discovery.
4. **Document Category Architecture**: The upload system treats all documents as generic PDF/DOCX files. It lacks the three canonical categories: (A) Team Roster & Member Responsibilities, (B) Meeting Notes, and (C) Project Documents (with subtypes PRD, SRS, TRD, DD, ADD, API Spec, DB Design, etc.).
5. **Team Roster Extraction & Reconciliation**: No structured parser currently maps roster tables to team member profiles, roles, and declared responsibilities.
6. **Contributor Identity Resolution & Contribution Classification**: Commit author and committer metadata are partially collapsed. There is no automated classification of contributions (e.g., Frontend, Backend, Auth, DB) or comparison against declared responsibilities (ALIGNED, PARTIALLY_ALIGNED, OUTSIDE_DECLARED_RESPONSIBILITY).
7. **Persistent Notifications & Task Tracking**: The frontend top navigation bell and notifications route currently query dummy local `figmaStore` state instead of a persistent PostgreSQL `notifications` table. Cross-page task tracking during background sync needs global state persistence in the application shell.

---

## Capability-by-Capability Audit Matrix

### 1. Platform Identity, Authentication & User Profiles
- **Existing Implementation Files**:
  - `backend/app/api/routes/auth.py`
  - `backend/app/services/auth.py`
  - `backend/app/models/user.py`, `backend/app/models/auth.py`
  - `backend/app/schemas/auth.py`
- **Database Tables**: `users`, `refresh_sessions`, `password_reset_tokens`
- **Current Status**: **Complete and verified**
- **Findings**: Sole authority is FastAPI-managed auth (Argon2id password hashing, short-lived JWT access tokens, SHA-256 `RefreshSession` rotation in `HttpOnly` cookies, and PostgreSQL RBAC). No Supabase Auth runtime dependency for platform identity.
- **Required Changes**: None for core platform auth.

---

### 2. Organisation & Project Membership, RBAC & Invitations
- **Existing Implementation Files**:
  - `backend/app/models/organisation.py`, `backend/app/models/project.py`, `backend/app/models/rbac.py`
  - `backend/app/services/organisation.py`, `backend/app/services/project.py`, `backend/app/services/rbac.py`
  - `backend/app/core/rbac_catalog.py`
  - `infrastructure/database/migrations/versions/20261115_0018_project_invitations.py`
- **Database Tables**: `organisations`, `organisation_memberships`, `organisation_invitations`, `projects`, `project_memberships`, `project_transitions`, `roles`, `permissions`, `role_permissions`
- **Current Status**: **Complete and verified**
- **Findings**: Project invitations with email dispatch, token hashing, and RBAC gate are implemented and verified. Project membership includes `responsibility_description`.
- **Missing Features**: Linking approved team roster candidates to project members and their responsibility profiles.
- **Required Changes**: Add roster reconciliation service to associate external identities and verified responsibilities with `project_memberships`.

---

### 3. Credential Encryption & Security
- **Existing Implementation Files**:
  - `backend/app/core/security.py`
  - `backend/app/services/token_encryption.py`
  - `backend/app/models/integration.py` (`UserSourceAuthorisation`)
- **Database Tables**: `user_source_authorisations` (`encrypted_access_token`, `encrypted_refresh_token`, `token_encryption_algorithm='AES-256-GCM'`)
- **Current Status**: **Complete and verified**
- **Findings**: Symmetrically encrypts credentials at rest with AES-256-GCM using unique 12-byte nonces and 16-byte authentication tags. Tokens are never exposed in public schemas or returned to the browser.
- **Required Changes**: Ensure Slack bot tokens and Jira API tokens reuse this identical encryption service.

---

### 4. GitHub Connector & Credential Handling
- **Existing Implementation Files**:
  - `backend/app/api/routes/sources.py`, `backend/app/api/routes/integrations.py`
  - `backend/app/services/integrations/github_client.py`
  - `backend/app/services/integrations/service.py`
  - `frontend/src/components/modals/ConnectSourceModal.tsx`
- **Database Tables**: `source_connections`, `user_source_authorisations`, `project_source_mappings`
- **Current Status**: **Implemented but incomplete**
- **Gaps**:
  - `ConnectSourceModal.tsx` currently prompts for a manual repository name string.
  - The backend has `discover_github_repositories` in `SourceIntegrationService` calling `GitHubClient.list_repositories()`, but the modal flow does not connect token validation to dynamic repository list fetching.
  - Fine-Grained PAT permissions are not documented in the UI modal.
- **Required Changes**:
  - Update `ConnectSourceModal.tsx` to a two-step flow: Step 1 (PAT input & validation) -> Step 2 (Selectable list of discovered repositories with search, filter, and multi-selection).
  - Add backend route `POST /api/v1/integrations/github/validate-and-discover` returning accessible repositories immediately upon token verification before mapping.

---

### 5. GitHub Ingestion Coverage & Incremental Sync
- **Existing Implementation Files**:
  - `backend/app/services/integrations/github_sync.py`
  - `backend/app/services/integrations/github_client.py`
  - `backend/app/services/integrations/evidence_ingestor.py`
- **Database Tables**: `evidence_items`, `evidence_extracted_contents`, `evidence_pages`, `source_sync_runs`
- **Current Status**: **Implemented but incomplete**
- **Gaps**:
  - `_normalize_commit` currently collapses `author` and `committer` into a single `author_identity` string. It does not retain separate fields for `git_author_name`, `git_author_email`, `git_committer_name`, `git_committer_email`, `github_author_login`, and `github_committer_login`.
  - Ingestion does not yet support an optional scope for indexing selected source code files (respecting extension allowlists and exclusion patterns).
- **Required Changes**:
  - Update `_normalize_commit` in `github_sync.py` to preserve distinct author and committer fields in `metadata_json` and `EvidenceItem`.
  - Add optional source code file indexing scope (`include_code_files=True`) with security checks (excluding secrets, `.env`, binaries, `node_modules`).

---

### 6. Jira Connector & Credential Handling
- **Existing Implementation Files**:
  - `backend/app/services/integrations/jira_client.py`
  - `backend/app/services/integrations/jira_sync.py`
  - `backend/app/services/integrations/service.py`
  - `backend/app/api/routes/integrations.py`
- **Database Tables**: `source_connections`, `user_source_authorisations`, `project_source_mappings`
- **Current Status**: **Implemented but incomplete**
- **Gaps**:
  - `ConnectSourceModal.tsx` asks for a manual `jiraProjectKey`.
  - Modal must be updated to validate credentials (Atlassian site URL + email + API token or OAuth) and automatically fetch accessible Jira projects.
  - SSRF protection on Jira site URL needs strict validation against legitimate Atlassian domains (`*.atlassian.net`) or validated custom domains, rejecting RFC 1918 internal IPs.
- **Required Changes**:
  - Remove manual project key input in modal.
  - Implement two-step modal with dynamic project selector.
  - Add SSRF validator for Jira site URL.

---

### 7. Jira Ingestion Coverage
- **Existing Implementation Files**:
  - `backend/app/services/integrations/jira_sync.py`
  - `backend/app/services/integrations/jira_client.py`
- **Database Tables**: `evidence_items`, `evidence_extracted_contents`, `evidence_pages`, `source_sync_runs`
- **Current Status**: **Implemented but incomplete**
- **Gaps**:
  - `jira_sync.py` syncs issues, descriptions, and comments, but needs complete ingestion of issue links, changelog history (status transitions, assignment changes), and parent/child subtask relationships.
- **Required Changes**:
  - Ingest changelog transitions and link relationships into `metadata_json` and structured evidence text for complete provenance.

---

### 8. Slack Integration (Connector, Discovery & Sync)
- **Existing Implementation Files**: None in backend (only mentioned in `frontend/src/lib/figmaStore.ts` and `enums.py`).
- **Database Tables**: `source_connections` (check constraint currently excludes `'slack'`).
- **Current Status**: **Missing**
- **Gaps**:
  - `backend/app/services/integrations/slack_client.py` does not exist.
  - `backend/app/services/integrations/slack_sync.py` does not exist.
  - `models/integration.py` constraints: `provider IN ('github', 'jira')` must be updated to include `'slack'`.
  - Database migration needed to update check constraints.
- **Required Changes**:
  - Create `SlackClient` with methods: `auth_test()`, `team_info()`, `list_channels()`, `fetch_channel_history()`, `fetch_thread_replies()`.
  - Create `SlackSyncOrchestrator` to normalize messages, threads, timestamps, and permalinks into `EvidenceItem`.
  - Create Alembic migration to update `source_connections`, `oauth_states`, `source_access_policies`, `project_source_mappings`, and `source_sync_runs` constraints to allow `'slack'` and `'slack_channel'`.

---

### 9. Document Ingestion, PDF/DOCX Extraction & OCR
- **Existing Implementation Files**:
  - `backend/app/api/routes/evidence.py`
  - `backend/app/services/evidence.py`
  - `backend/app/services/document_extraction.py`
  - `backend/app/services/ocr.py`
  - `backend/app/services/storage_factory.py`, `backend/app/services/supabase_storage.py`
- **Database Tables**: `evidence_items`, `evidence_extracted_contents`, `evidence_pages`
- **Current Status**: **Complete and verified for general documents; Missing category-specific intelligence**
- **Gaps**:
  - `upload_project_document` only accepts raw file bytes; it has no parameters for `document_category` (Team Roster, Meeting Notes, Project Document) or `document_subtype` (PRD, TRD, DD, etc.).
  - `EvidenceCategory` enum does not have `team_roster`, `meeting_notes`, `project_document`.
  - Category-specific chunking and extraction pipelines do not exist.
- **Required Changes**:
  - Add `document_category` and `document_subtype` to upload schema and `evidence_items`.
  - Update `UploadDocumentModal.tsx` with a category selection screen (Category A: Team Roster, Category B: Meeting Notes, Category C: Project Documents with subcategories).

---

### 10. Team Roster Extraction & Member Responsibilities
- **Existing Implementation Files**: None specifically for roster parsing.
- **Database Tables**: `project_memberships` has `responsibility_description`.
- **Current Status**: **Missing**
- **Gaps**:
  - No parser extracts member rows, designation, project role, declared responsibilities, GitHub handles, Git commit emails, Jira accounts, or Slack IDs from PDF/DOCX.
  - No reconciliation workflow exists to compare extracted members against existing `ProjectMembership` records.
- **Required Changes**:
  - Implement `RosterExtractionService` using PyMuPDF/python-docx + Qwen3 8B with strict Pydantic output schema (`RosterExtractionResult`).
  - Implement `MemberReconciliationService` to compare candidates against `project_memberships` (MATCHED, POSSIBLE_MATCH, NEW_CANDIDATE, AMBIGUOUS).
  - Add API endpoints to review, approve, edit, and apply roster mappings to project membership responsibility profiles.

---

### 11. Contributor Identity Resolution & Contribution Attribution
- **Existing Implementation Files**:
  - `backend/app/services/identity_resolution.py`
  - `backend/app/models/relationship.py` (`KnowledgeEntity`, `EntityAlias`, `IdentityResolutionCandidate`)
- **Database Tables**: `knowledge_entities`, `entity_aliases`, `identity_resolution_candidates`
- **Current Status**: **Implemented but not integrated with GitHub sync**
- **Gaps**:
  - Identity resolution currently exists in Relationship Explorer for graph entities, but is not run during or after GitHub sync to attribute commits to project members based on verified accounts and emails.
  - No contribution classification service classifies commits into categories (Frontend, Backend, Database, Auth, etc.) or evaluates responsibility alignment (ALIGNED, OUTSIDE_DECLARED_RESPONSIBILITY, etc.).
- **Required Changes**:
  - Implement `ContributionAttributionService` that takes GitHub commits, matches authors using the conservative priority (verified GitHub ID -> verified username -> commit email -> confirmed cross-provider identity -> unverified candidate), classifies the technical domain, and evaluates alignment with the member's declared roster responsibilities.

---

### 12. Meeting Notes Intelligence
- **Existing Implementation Files**: Generic extraction in `document_extraction.py`.
- **Database Tables**: `evidence_items`, `knowledge_items`
- **Current Status**: **Missing dedicated extraction profile**
- **Gaps**:
  - No dedicated prompt/extractor parses meeting metadata (date, type, attendees) and separates discussions, proposals, accepted decisions, and action items with owners and deadlines.
- **Required Changes**:
  - Implement `MeetingNotesExtractionService` using Qwen3 8B structured output with strict epistemic separation between discussed topics and approved decisions.

---

### 13. Project Document Intelligence (PRD, TRD, DD, Architecture, APIs)
- **Existing Implementation Files**: Generic extraction in `extraction_prompts.py`.
- **Current Status**: **Implemented but incomplete**
- **Gaps**:
  - System prompts in `extraction_prompts.py` extract across the 8 knowledge domains, but do not provide subtype-tailored structured extraction for PRD requirements, TRD architecture components, API specs, and database designs.
- **Required Changes**:
  - Add subtype-specific extraction profiles in `document_extraction.py` and `extraction_prompts.py`.

---

### 14. Background Synchronisation & Persistent Jobs
- **Existing Implementation Files**:
  - `backend/app/models/job.py` (`BackgroundJob`)
  - `backend/app/repositories/job.py`
  - `backend/app/worker.py`
  - `backend/app/services/integrations/sync_worker.py`
- **Database Tables**: `background_jobs`, `source_sync_runs`
- **Current Status**: **Complete backend engine; Missing persistent frontend task tracking**
- **Gaps**:
  - Backend worker claims and runs jobs asynchronously via PostgreSQL leases.
  - However, frontend has no global persistent task provider in `AppLayout.tsx`. When navigating across pages or refreshing, active sync jobs are not tracked in a persistent top navigation activity indicator.
- **Required Changes**:
  - Add `GET /api/v1/projects/{project_id}/jobs/active` and `/jobs/recent` endpoints.
  - Implement `SyncTaskProvider` in `frontend/src/context/SyncTaskContext.tsx` with bounded polling and recovery on browser refresh.
  - Add global sync activity indicator in `TopNav.tsx`.

---

### 15. Cross-Page Notification System
- **Existing Implementation Files**: None in backend; frontend has mock UI in `AdminPage.tsx`.
- **Database Tables**: None for notifications.
- **Current Status**: **Missing**
- **Gaps**:
  - No database table or backend service for user/project notifications.
  - Job completion in `sync_worker.py` does not create notification records.
- **Required Changes**:
  - Create `notifications` database table and model (`NotificationItem`).
  - Create `NotificationService` and API routes (`/api/v1/notifications`).
  - Trigger persistent notifications on sync completion, partial completion, or failure.
  - Connect frontend top nav bell icon and `/notifications` page to the real notification API.

---

### 16. Unified Evidence Center (UI Panels A, B, C)
- **Existing Implementation Files**:
  - `frontend/src/components/views/EvidenceCenterView.tsx`
  - `frontend/src/components/figma-pages/KnowledgePage.tsx` (`EvidenceLibrary`)
  - `frontend/src/components/views/ConnectedSourcesView.tsx`
- **Current Status**: **Implemented but incomplete**
- **Gaps**:
  - `KnowledgePage.tsx` hardcoded dummy counts (`72`, `23`) and mock source cards.
  - `EvidenceCenterView.tsx` has full 3-panel layout but lacks the dedicated Member Mapping tab for roster documents, and needs full wiring to the updated document categories and Slack sources.
- **Required Changes**:
  - Ensure `/sources` and `/evidence` routes render the live `ConnectedSourcesView` and `EvidenceCenterView` cleanly.
  - Replace hardcoded counts with real backend data from `api.sources.listMappings` and `api.evidence.getMetrics`.
  - Add Member Mapping tab in Panel C for Team Roster evidence.

---

## Overall Classification Summary

| Feature Area | Classification | Priority |
| :--- | :--- | :--- |
| **GitHub PAT Connection & Dynamic Repo Discovery** | Implemented but incomplete | High (Phase 2) |
| **GitHub Ingestion & Separate Author/Committer Tracking** | Implemented but incomplete | High (Phase 3) |
| **Jira Credential Validation & Dynamic Project Discovery** | Implemented but incomplete | High (Phase 4) |
| **Jira Ingestion & Relationships** | Implemented but incomplete | High (Phase 5) |
| **Slack Integration (Connector, Discovery, Ingestion)** | Missing | High (Phase 6 & 7) |
| **Persistent Background Task Engine & Global State** | Implemented but not integrated in UI | High (Phase 8) |
| **Document Category System (Roster, Meetings, Specs)** | Implemented but incomplete | High (Phase 9) |
| **Team Roster Extraction & Member Reconciliation** | Missing | High (Phase 10) |
| **Contributor Identity Resolution & Attribution** | Implemented but not integrated | High (Phase 10) |
| **Meeting Notes & Project Document Intelligence** | Implemented but incomplete | Medium (Phase 9/10) |
| **Persistent Notification System (Backend & UI)** | Missing | High (Phase 8/13) |
| **Unified Evidence Center (3 Panels & Real Counts)** | Implemented but incomplete | High (Phase 11/13) |
| **End-to-End Acceptance Tests & Quality Verification** | Requires new tests | High (Phase 14) |
