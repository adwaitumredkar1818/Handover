# HANDOVER WORKSPACE — STEP-BY-STEP IMPLEMENTATION ROADMAP

> **Platform**: The Handover — Intelligent Project Knowledge Reconstruction & Handover Platform  
> **Module**: Handover Workspace (`/handover`, `/handovers`, `/generated-handovers`)  
> **Date**: November 17, 2026  
> **Status**: Implementation Roadmap Derived from Comprehensive Audit  
> **Active Target Project**: `fa71b2e5-140e-4040-b1ea-4ac6036382b9` (`Skill Passport-Siddhesh`)  

---

## 1. Roadmap Architecture & Execution Principles

This roadmap outlines the precise, phased execution plan to transition the Handover Workspace from its current state (a robust backend disconnected from a prototype Figma frontend) to a fully functional, production-ready, and verifiable module.

### Core Architectural Directives
1. **Zero Database Migrations Required**: All 14 tables and relationships already exist in PostgreSQL and match backend requirements.
2. **Backend-First Verification**: Resolve the eligibility method defect and verify package assembly before altering frontend code.
3. **Decouple from Figma Mock Store**: Replace in-memory mock data, hardcoded UUIDs, and synthetic users with live API bindings to `api.handover.*`.
4. **Epistemic Integrity**: Only human-verified knowledge records enter the compiled package. Unresolved conflicts must block signoff.
5. **Separation of Duties**: Enforce role checks in the UI matching backend authorization policies.

---

## 2. Phased Implementation Sequence

```
┌────────────────────────────────────────────────────────────────────────┐
│ STAGE 1: Core Backend Defect Fix & Assembly Verification               │
│ - Fix `VerificationCaseRepository.get_by_target` call signature        │
│ - Run automated assembly test on active project (22 verified findings) │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ STAGE 2: Project Context & Real Participant Binding                    │
│ - Bind creation wizard to active project context (remove mock UUIDs)   │
│ - Replace mock user array with `api.projects.getMembers`               │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ STAGE 3: Canonical 8-Domain Package Section Rendering                  │
│ - Wire `/handovers/[id]` to `GET /cases/{id}/versions/{v}/sections`    │
│ - Render markdown & structured findings per domain with citations      │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ STAGE 4: Live 9-Category Readiness & Conflict Blocker Banners          │
│ - Bind readiness widget to `GET /cases/{id}/readiness`                 │
│ - Display blocking conflict warnings linking directly to `/conflicts`  │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ STAGE 5: Checklists, Responsibility Transfers & Optimistic Locking     │
│ - Wire checklist tab to live API (remove mock fallback)                │
│ - Implement Responsibility Transfers list and assignment modal         │
│ - Add `lock_version` to state transition payloads                      │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ STAGE 6: Signoff Workflow, Separation of Duties & Recipient Flow       │
│ - Wire 3-phase signoff modal with real user authentication             │
│ - Disable signoff when user is outgoing author or readiness < 100%     │
│ - Wire Recipient Acknowledgement flow (`POST .../acknowledgement`)     │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ STAGE 7: Multi-Format Export Verification & End-to-End Browser QA      │
│ - Test Markdown, JSON, and PDF downloads against compiled versions     │
│ - Authenticated browser QA in Next.js frontend                         │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Detailed Stage Specifications

### Stage 1: Core Backend Defect Fix & Assembly Verification
- **Goal**: Unblock package version compilation across the backend platform.
- **Dependencies**: None.
- **Backend Tasks**:
  1. Inspect [backend/app/services/handover_eligibility.py](file:///Users/siddheshbirewar/Downloads/HandOver/backend/app/services/handover_eligibility.py) at line 212 and line 282.
  2. Correct the method call to `self.case_repo.get_by_target`:
     ```python
     # Corrected call matching VerificationCaseRepository signature:
     case = self.case_repo.get_by_target(
         project_id=item.project_id,
         target_type=VerificationTargetType.KNOWLEDGE_ITEM,
         target_id=item.id,
     )
     ```
  3. Verify that `active_only` filtering is handled via the returned case's `status` or repository method if needed.
- **Testing Requirements**:
  - Run `backend/tests/run_handover_workspace_audit.py` using Python virtual environment.
  - Assert that `PackageAssemblyService.assemble_package_version` executes successfully and writes `HandoverPackageVersion`, 8 `HandoverPackageSection` records, and corresponding `HandoverContentLink` records.
- **Acceptance Criteria**:
  - Zero `TypeError` exceptions during assembly.
  - Package version compiled with 8 non-empty canonical sections.

---

### Stage 2: Project Context & Real Participant Binding
- **Goal**: Eliminate hardcoded mock IDs and mock users from the handover creation workflow.
- **Dependencies**: Stage 1.
- **Frontend Tasks**:
  1. In [frontend/src/components/figma-pages/HandoversPage.tsx](file:///Users/siddheshbirewar/Downloads/HandOver/frontend/src/components/figma-pages/HandoversPage.tsx):
     - Replace hardcoded project UUIDs (`'ed33c53a-7678-4d5b-8212-64c233897142'`) with `useProject().currentProject?.id`.
     - Fetch project team members via `api.projects.getMembers(projectId)`.
     - Bind the Outgoing, Incoming, and Supervisor dropdowns in the creation wizard to real project members.
  2. Handle case creation API response properly: navigate user to `/handovers/${createdCase.id}` upon successful creation.
- **Testing Requirements**:
  - Open `/handovers` in browser; click "New Handover".
  - Verify team member dropdown contains real project users (`siddheshbirewar77@gmail.com`).
  - Create a new HandoverCase and verify record is inserted into `handover_cases` in PostgreSQL.
- **Acceptance Criteria**:
  - Case created with valid foreign keys to real project and user records.
  - No references to dummy IDs in network requests.

---

### Stage 3: Canonical 8-Domain Package Section Rendering
- **Goal**: Replace mock findings and fake cards with real assembled knowledge sections.
- **Dependencies**: Stage 1, Stage 2.
- **Frontend Tasks**:
  1. In [frontend/src/components/figma-pages/HandoverDetailPage.tsx](file:///Users/siddheshbirewar/Downloads/HandOver/frontend/src/components/figma-pages/HandoverDetailPage.tsx):
     - On component mount, call `api.handover.getVersions(caseId)` to identify latest compiled version.
     - Call `api.handover.getSections(caseId, latestVersionId)` to load the 8 canonical sections.
     - Replace mock store rendering in the tabs:
       - **Architecture & Technical Decisions**: Render `detailed_markdown` and citation links from `architecture_technical` section.
       - **Key Decisions & Rationale**: Render `decisions_rationale` section.
       - **Work Status**: Render `work_status` section.
       - **Ownership & Roles**: Render `ownership_responsibilities` section.
       - **Dependencies**: Render `dependencies` section.
       - **Risks & Blockers**: Render `risks_blockers` section.
       - **Runbooks**: Render `operational_runbooks` section.
  2. Display epistemic status badge (`Verified` / `Approved`) next to each reconstructed finding.
- **Testing Requirements**:
  - Navigate to `/handovers/[id]`.
  - Verify network tab shows successful `GET /sections` call.
  - Confirm real findings extracted from Skill Passport evidence appear in UI.
- **Acceptance Criteria**:
  - UI displays real verified project findings with citations to source files/issues.
  - `figmaStore.findings` is completely bypassed.

---

### Stage 4: Live 9-Category Readiness Assessment & Conflict Blocker Banners
- **Goal**: Surface true project readiness and prevent handover progression when conflicts exist.
- **Dependencies**: Stage 3.
- **Frontend Tasks**:
  1. In [frontend/src/components/figma-pages/HandoverDetailPage.tsx](file:///Users/siddheshbirewar/Downloads/HandOver/frontend/src/components/figma-pages/HandoverDetailPage.tsx):
     - Replace mock percentage gauge with live data from `api.handover.getReadiness(caseId)`.
     - Render detailed breakdown modal showing the 9 weighted categories:
       - Scope Completeness
       - Verification Coverage
       - Conflict Resolution
       - Checklist Completion
       - Documentation Quality
       - Ownership Clarity
       - Access Readiness
       - Operational Readiness
       - Recipient Readiness
  2. If `readiness.conflict_resolution < 100%` or unresolved conflicts are detected:
     - Render a high-priority alert banner at the top of the workspace:
       *"Handover blocked: Unresolved contradictions detected across connected sources. [Investigate in Conflict Management →]"*
     - Add deep link routing to `/conflicts`.
- **Testing Requirements**:
  - Trigger readiness evaluation via `POST /cases/{id}/readiness/evaluate`.
  - Assert that open conflicts lower score and display warning banner.
- **Acceptance Criteria**:
  - Readiness metric precisely matches backend calculation.
  - User can click through directly to Conflict Management workspace.

---

### Stage 5: Checklists, Responsibility Transfers & Optimistic Locking
- **Goal**: Operationalize transition tasks, system reassignments, and concurrency protection.
- **Dependencies**: Stage 4.
- **Backend & Frontend Tasks**:
  1. **Checklists**:
     - Ensure `api.handover.getChecklists(caseId)` correctly loads phase checklists.
     - Toggle item completion via `PUT .../checklists/items/{itemId}`.
  2. **Responsibility Transfers**:
     - Bind Transfers tab to `GET /cases/{id}/transfers`.
     - Implement "Add Responsibility Transfer" modal calling `POST /cases/{id}/transfers` with source asset, outgoing owner, incoming owner, and handover status.
  3. **Optimistic Locking**:
     - Include `lock_version` in all `PUT /cases/{id}` and `POST /cases/{id}/status` payloads.
     - Handle HTTP 409 Conflict gracefully by alerting the user that the record was modified by another session.
- **Testing Requirements**:
  - Toggle checklist items and verify persistence in `handover_checklist_items`.
  - Add a responsibility transfer and verify persistence in `handover_responsibility_transfers`.
- **Acceptance Criteria**:
  - Checklists and transfers persist to canonical PostgreSQL tables.

---

### Stage 6: Signoff Workflow, Separation of Duties & Recipient Flow
- **Goal**: Implement governance approvals and recipient receipt confirmation.
- **Dependencies**: Stage 5.
- **Frontend Tasks**:
  1. **Signoffs**:
     - Wire signoff submission modal to `POST /cases/{id}/signoffs`.
     - Inspect authenticated user's role against case participants:
       - If current user == `outgoing_user_id`, disable Peer Review and Supervisor signoff buttons.
       - If `readiness.is_ready == false`, disable signoff buttons with informative tooltip.
  2. **Recipient Acknowledgement**:
     - In `/handovers/[id]/recipient` view:
       - Bind "Acknowledge Handover" button to `POST /cases/{id}/acknowledgement`.
       - Capture recipient notes and acknowledgement timestamp.
- **Testing Requirements**:
  - Test signoff with project manager credentials.
  - Verify transition from `IN_REVIEW` to `APPROVED`.
  - Test recipient acknowledgement and verify transition to `ACKNOWLEDGED`.
- **Acceptance Criteria**:
  - Full audit trail recorded in `handover_status_histories`.
  - Separation of duties strictly enforced.

---

### Stage 7: Multi-Format Export Verification & End-to-End Browser QA
- **Goal**: Ensure export formats function flawlessly and conduct comprehensive browser verification.
- **Dependencies**: Stage 6.
- **Tasks**:
  1. **Export Testing**:
     - Test Markdown export (`/cases/{id}/export/markdown`) and verify downloaded file contains full table of contents and citations.
     - Test JSON export (`/cases/{id}/export/json`) and verify machine-readable schema.
     - Test PDF export (`/cases/{id}/export/pdf`) and verify layout.
  2. **Browser QA Session**:
     - Execute complete end-to-end verification in authenticated browser session on `http://localhost:3000/handovers`.
     - Verify zero console errors, zero mock store leaks, and full responsiveness.
- **Acceptance Criteria**:
  - All export formats stream cleanly without 500 errors.
  - Final QA signoff report produced.
