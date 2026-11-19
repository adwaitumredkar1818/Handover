# Handover Stage 6 — Signoff, Approval, Publication & Recipient Acknowledgement Report

**Date**: 2026-11-18  
**Project**: The Handover — Intelligent Project Knowledge Reconstruction & Handover Platform  
**Stage**: Stage 6 — Signoff, Approval, Publication & Recipient Acknowledgement  
**Status**: Completed & Verified (Backend 25/25 Pytest Passing · Frontend `tsc --noEmit` 0 Errors · Live Read-Only Authenticated Browser QA Passed)

---

## 1. Executive Summary

Stage 6 delivers the complete managerial governance, three-phase signoff, authoritative 4-gate approval eligibility, SHA-256 package integrity binding, rejection/change-request lifecycle, controlled publication, and complete-package recipient acknowledgement + clarification workflow for the Handover Workspace.

All legacy mock `figmaStore` review and recipient screens—including broken header action dialogs that previously sent invalid enum strings (`departing_verification`, `in_app`) and optimistically mutated local mock state—have been eliminated and replaced by PostgreSQL-backed, RBAC-enforced, SHA-256-verified governance endpoints and UI panels.

The live validation case **HO-9435** (`Skill Passport-Siddhesh`) was verified strictly **read-only** in an authenticated browser session; zero approvals, publications, or acknowledgements were fabricated or executed against real project data.

---

## 2. Pre-Implementation Audit Findings

Before writing Stage 6 code, we audited the existing backend and frontend Handover architecture and identified seven concrete defects/gaps:

1. **Schema/Model Mismatch on `HandoverDelivery`**: `HandoverDeliveryResponse` exposed `message: Optional[str]`, while the `handover_deliveries` table lacked a `message` column and clarification history column (`clarifications_json`).
2. **Missing Reviewer Assignment & Integrity Binding Columns**: `HandoverCase` had no `assigned_reviewer_id`, and `HandoverSignoff` lacked `package_content_hash`, `affected_sections_json`, and `is_superseded` tracking for version supersession.
3. **Weak Approval Gating & Missing Separation of Duties**: Existing signoff code did not enforce the authoritative 4-gate `HandoverReadinessEngine` eligibility check, did not block departing members from approving their own handover, and did not verify exact package `content_hash` or optimistic concurrency `case.version`.
4. **Cross-Project Leakage & Phase RBAC Bug**:
   - `GET /cases/{case_id}/signoffs` did not verify `case.project_id == project_id`.
   - `POST /cases/{case_id}/signoffs` unconditionally required `handover.review`, blocking `PROJECT_MEMBER` users (who hold `handover.edit` + `handover.acknowledge`, not `handover.review`) from submitting Phase 1 departing sign-off or Phase 3 acknowledgement.
5. **Broken Frontend API Contract**: `api.handover.acknowledgeDelivery` previously sent `{ acknowledgement_statement, clarification_notes, confidence_level }` instead of `{ acknowledgement_notes, confirmations, expected_content_hash }`.
6. **Legacy Mock `Review` and `RecipientWorkspace` Pages**: Both `/handovers/[id]/review` and `/handovers/[id]/recipient` in `HandoverDetailPage.tsx` still rendered `figmaStore` synthetic findings, fabricated notes, and hardcoded mock dates (`Jun 18, 2025`).
7. **Broken Header Action Dialogs in `HandoverLayout`**: Legacy header buttons in `HandoversPage.tsx` optimistically mutated `figmaStore` and fired invalid enum values (`departing_verification`, `in_app`).

---

## 3. Authoritative Lifecycle State Machine

Stage 6 preserves and enforces the canonical 14-state `HandoverCaseStatus` lifecycle in [`backend/app/services/handover_case.py`](file:///Users/siddheshbirewar/Downloads/HandOver/backend/app/services/handover_case.py):

| Governance Stage | Canonical `HandoverCaseStatus` Values |
| :--- | :--- |
| Draft | `draft`, `assembling` |
| Verification & Readiness | `assembled`, `readiness_pending`, `readiness_assessed` |
| Review & Approval | `review_pending`, `under_review`, `rejected` |
| Approved | `approved` |
| Published | `delivered` |
| Acknowledged & Finalised | `acknowledged`, `transferred`, `archived`, `superseded` |

**Added Valid Transitions (`VALID_TRANSITIONS`)**:
- `UNDER_REVIEW -> ASSEMBLED` (allows reassembly after change-request revisions)
- `APPROVED -> ASSEMBLED` (allows assembling a new version if underlying knowledge changes; automatically supersedes prior approvals)

---

## 4. Database Schema & Additive Migration (`0023_stage6_signoff_pub`)

Created and applied additive Alembic migration [`infrastructure/database/migrations/versions/20261118_0023_stage6_signoff_publication.py`](file:///Users/siddheshbirewar/Downloads/HandOver/infrastructure/database/migrations/versions/20261118_0023_stage6_signoff_publication.py) (`0022_stage5_checklists_resp -> 0023_stage6_signoff_pub`) matching updated ORM models in [`backend/app/models/handover.py`](file:///Users/siddheshbirewar/Downloads/HandOver/backend/app/models/handover.py):

- `handover_cases`:
  - `assigned_reviewer_id` (`UUID`, FK `users.id` ON DELETE SET NULL, indexed)
- `handover_signoffs`:
  - `package_content_hash` (`VARCHAR(64)`, nullable)
  - `affected_sections_json` (`JSONB`, server default `'[]'`)
  - `is_superseded` (`BOOLEAN`, NOT NULL, server default `false`)
- `handover_deliveries`:
  - `message` (`TEXT`, nullable)
  - `clarifications_json` (`JSONB`, server default `'[]'`)

Verified applied cleanly on live PostgreSQL: `alembic current` reports `0023_stage6_signoff_pub (head)`.

---

## 5. Three-Phase Signoff Governance

Implemented in [`backend/app/services/handover_signoff.py`](file:///Users/siddheshbirewar/Downloads/HandOver/backend/app/services/handover_signoff.py):

1. **Phase 1 — Departing Member Verification & Sign-Off (`departing_signoff`)**:
   - Assigned to the case's `departing_user_id` (or project manager/org admin when designated).
   - Confirms the compiled package version (`version_id` + exact `package_content_hash`) is ready for independent review.
   - Transitions case to `review_pending` / `under_review`.
2. **Phase 2 — Independent Reviewer / Manager Approval (`reviewer_approval`)**:
   - Strictly blocked until Phase 1 is complete on the **same package version**.
   - Requires `handover.approve` permission and strict **separation of duties**: the departing member can **never** be assigned as reviewer or approve their own handover.
   - If `assigned_reviewer_id` is set, only that assigned reviewer (or an `ORG_ADMIN` override) can execute Phase 2.
   - Supports three governed decisions: `approved`, `returned_for_revision`, and `rejected`.
3. **Phase 3 — Published Package Recipient Acknowledgement (`recipient_acknowledgement`)**:
   - Opens **only after controlled publication** (`delivered` status with an active `HandoverDelivery` record).
   - Distinct from Stage 5 individual responsibility acknowledgements and distinct from managerial approval (per `AGENTS.md` Section 5.4: recipient acknowledgement **cannot** substitute for reviewer approval).

---

## 6. Authoritative 4-Gate Approval Eligibility & Separation of Duties

Before Phase 2 `approved` can succeed, `HandoverSignoffService` invokes `HandoverReadinessEngine.get_readiness_intelligence()` in real time and enforces all 4 readiness gates:

1. **Readiness Score Gate**: Overall readiness score `>= 70/100`.
2. **Verification Gate**: Zero unverified candidate findings included in eligibility scope.
3. **Conflict Gate**: Zero unresolved cross-source contradictions.
4. **Checklist Gate**: Zero incomplete mandatory/blocking transition checklist items.

**Blocker Enforcement & Governed Admin Override**:
- Non-admin reviewers (`REVIEWER`, `PROJECT_MANAGER`) are strictly blocked (`400 Bad Request` / `ValidationError`) whenever any readiness blocker exists.
- `ORG_ADMIN` override requires explicit `conditions` documentation (`>= 10` characters) and writes an immutable `handover.signoff.blocker_override` PostgreSQL audit log entry.

---

## 7. Package Integrity (SHA-256) & Version Supersession

- Every signoff, publication, and acknowledgement validates:
  - `expected_content_hash` against `HandoverPackageVersion.content_hash` (SHA-256). Any mismatch rejects with `ConflictError` (`409`).
  - `expected_case_version` optimistic concurrency token against `HandoverCase.version`. Stale UI state rejects with `ConflictError` (`409`).
- **Automatic Supersession on Reassembly** ([`backend/app/services/handover_assembly.py`](file:///Users/siddheshbirewar/Downloads/HandOver/backend/app/services/handover_assembly.py)):
  - Whenever `next_version_num > 1` is assembled, all prior non-superseded `HandoverSignoff` rows are marked `is_superseded = True` (preserving historical rows immutably—never deleting them) and logged under `handover.signoff.superseded_by_new_version`.
  - Phase 1 and Phase 2 must be re-executed on the new package version before publication.

---

## 8. Rejection, Change-Request & Phase Reopen Workflows

- **Mandatory Rationale & Affected Sections**: Both `REJECTED` and `RETURNED_FOR_REVISION` decisions require a documented reason (`comments >= 5` characters) and persist structured `affected_sections_json` targeting the exact canonical knowledge domains requiring rework.
- **State Transitions**:
  - `RETURNED_FOR_REVISION` returns the case cleanly for rework without deleting historical signoff records.
  - `REJECTED` transitions the case to `rejected` while preserving full audit trail.
- **Controlled Phase Reopen (`POST /cases/{case_id}/signoffs/reopen`)**:
  - Allows authorised managers/admins to reopen a rejected/returned or approved phase with a documented reason, superseding prior active decisions on that version and logging `handover.signoff.phase_reopened`.

---

## 9. Controlled Publication & Delivery

- `POST /cases/{case_id}/deliver` enforces:
  - Case must be in `approved` status.
  - Active, non-superseded Phase 1 (`departing_signoff`) and Phase 2 (`reviewer_approval`) approvals must exist on the exact target `version_id`.
  - Exact `expected_content_hash` and `expected_case_version` checks.
  - Recipients must be active members of the project (prevents cross-project or non-member delivery).
  - Prevents duplicate publication of the same package version to the same recipient (`ConflictError`).
- Persists `HandoverDelivery` with `delivery_method` (`internal_download`, `link_share`, `email_export`), `message`, `delivered_by`, `delivered_at`, and empty `clarifications_json`, transitioning case status to `delivered`.

---

## 10. Complete-Package Recipient Acknowledgement & Clarifications

- **Formal Acknowledgement (`POST /deliveries/{delivery_id}/acknowledge`)**:
  - Strictly enforces recipient identity (`current_user.id == delivery.delivered_to_user_id`, no impersonation).
  - Validates `expected_content_hash` matches the delivered package version.
  - Prevents duplicate acknowledgements (`ConflictError`).
  - Records structured `confirmations` checklist + `acknowledgement_notes`, creates immutable `HandoverAcknowledgement` + Phase 3 `HandoverSignoff`, and transitions case to `acknowledged` once all active deliveries for the current version are acknowledged.
- **Clarification Thread (`POST /deliveries/{delivery_id}/clarify`)**:
  - Allows the designated recipient to submit structured clarification questions (`question` + optional `section_type`) and allows the departing owner / manager / reviewer to post persisted answers in `clarifications_json` with timestamps, actor attribution, and immutable audit entries (`handover.delivery.clarification_requested` / `handover.delivery.clarification_answered`).

---

## 11. RBAC & Security Enforcement

- **Phase-Specific Route Authorization** ([`backend/app/api/routes/handover.py`](file:///Users/siddheshbirewar/Downloads/HandOver/backend/app/api/routes/handover.py)):
  - `departing_signoff`: requires `handover.edit` or `handover.review` + departing-owner / manager identity check.
  - `reviewer_approval`: requires `handover.approve` + separation-of-duties check + assigned reviewer check.
  - `recipient_acknowledgement`: requires `handover.acknowledge` + exact recipient identity check.
  - Reviewer assignment & phase reopen: requires `handover.approve` / manager authority.
  - Publication (`deliver`): requires `handover.deliver`.
- **Cross-Project Isolation**: Fixed `GET /cases/{case_id}/signoffs` and enforced `case.project_id == project_id` across all Stage 6 endpoints.
- **Zero Fabrication**: Eligible independent reviewers and publication recipients are populated exclusively from real active PostgreSQL `ProjectMember` rows; when no independent member exists, the UI explicitly displays `"No eligible independent reviewer available"` with submission disabled.

---

## 12. Audit Logging & Immutability

Every Stage 6 governance action records an immutable PostgreSQL `AuditLog` entry with actor ID, project ID, case/version/delivery metadata, and content hash:
- `handover.signoff.reviewer_assigned`
- `handover.signoff.submitted`
- `handover.signoff.blocker_override`
- `handover.signoff.phase_reopened`
- `handover.signoff.superseded_by_new_version`
- `handover.package.delivered`
- `handover.delivery.acknowledged`
- `handover.delivery.clarification_requested`
- `handover.delivery.clarification_answered`

Historical `HandoverSignoff` rows are never deleted or overwritten; supersession sets `is_superseded = True` so the full governance chronology remains auditable.

---

## 13. Backend APIs & Schemas Delivered

- **Schemas** ([`backend/app/schemas/handover.py`](file:///Users/siddheshbirewar/Downloads/HandOver/backend/app/schemas/handover.py)):
  - Enriched `SignoffRequest`, `DeliveryRequest`, `AcknowledgementRequest`, `HandoverSignoffResponse`, `HandoverDeliveryResponse`, `HandoverAcknowledgementResponse`.
  - Added `ReviewerAssignRequest`, `SignoffPhaseReopenRequest`, `DeliveryClarificationRequest`, `DeliveryClarificationEntry`, `SignoffPhaseDetail`, `SignoffLifecycleSummary`, `SignoffPublicationStatus`, `HandoverSignoffWorkspaceResponse`.
- **Endpoints** ([`backend/app/api/routes/handover.py`](file:///Users/siddheshbirewar/Downloads/HandOver/backend/app/api/routes/handover.py)):
  - `GET /api/v1/projects/{project_id}/handover/cases/{case_id}/signoffs/workspace`
  - `POST /api/v1/projects/{project_id}/handover/cases/{case_id}/signoffs`
  - `POST /api/v1/projects/{project_id}/handover/cases/{case_id}/signoffs/reviewer`
  - `POST /api/v1/projects/{project_id}/handover/cases/{case_id}/signoffs/reopen`
  - `POST /api/v1/projects/{project_id}/handover/cases/{case_id}/deliver`
  - `POST /api/v1/projects/{project_id}/handover/deliveries/{delivery_id}/acknowledge`
  - `POST /api/v1/projects/{project_id}/handover/deliveries/{delivery_id}/clarify`

---

## 14. Frontend Architecture & Legacy Mock Removal

- **Typed Contracts & API Client**:
  - Updated [`frontend/src/lib/types.ts`](file:///Users/siddheshbirewar/Downloads/HandOver/frontend/src/lib/types.ts) with complete Stage 6 TypeScript interfaces.
  - Updated [`frontend/src/lib/api.ts`](file:///Users/siddheshbirewar/Downloads/HandOver/frontend/src/lib/api.ts) with `getSignoffWorkspace`, `submitSignoff`, `assignReviewer`, `reopenSignoffPhase`, `deliverPackage`, `acknowledgeDelivery` (fixed contract), and `clarifyDelivery`.
- **Unified Stage 6 Panel**:
  - Created [`frontend/src/components/handover/SignoffApprovalPanel.tsx`](file:///Users/siddheshbirewar/Downloads/HandOver/frontend/src/components/handover/SignoffApprovalPanel.tsx) implementing:
    - Authoritative Lifecycle & Participants header with `Assign Independent Reviewer` modal
    - Live 4-Gate Approval Eligibility panel with direct links to `Readiness`, `Checklists`, `Ownership`, `Conflicts`, and `Verification`
    - Side-by-side Three-Phase Signoff Governance cards with phase-specific decision modals (`Submit Phase 1`, `Approve / Request Changes / Reject`, `Reopen Phase`)
    - Controlled Publication & Delivery card + Publish modal
    - Complete-Package Recipient Acknowledgement & Clarification Thread panel
    - Immutable Signoff Decision History & Governance Audit Activity timeline
- **Route Integration & Mock Removal**:
  - Wired `SignoffApprovalPanel` into `Review` (`/handovers/[id]/review`) and `RecipientWorkspace` (`/handovers/[id]/recipient`, paired with the live Canonical 8-Domain Package Reader) in [`frontend/src/components/figma-pages/HandoverDetailPage.tsx`](file:///Users/siddheshbirewar/Downloads/HandOver/frontend/src/components/figma-pages/HandoverDetailPage.tsx), deleting 780 lines of mock `figmaStore` prototype code.
  - Cleaned up [`frontend/src/components/figma-pages/HandoversPage.tsx`](file:///Users/siddheshbirewar/Downloads/HandOver/frontend/src/components/figma-pages/HandoversPage.tsx): renamed `review` tab to `Sign-Off & Approval`, removed all 5 legacy mock `figmaStore`-mutating header dialogs (`submit`, `start`, `approve`, `publish`, `changes`), replaced header buttons with clean navigation to `/review` and `/recipient`, and wired `?tab=review` in `HandoverWorkspace`.

---

## 15. Automated Backend Verification (Pytest)

Created dedicated Stage 6 integration test suite [`backend/tests/test_handover_stage6_signoff_and_publication.py`](file:///Users/siddheshbirewar/Downloads/HandOver/backend/tests/test_handover_stage6_signoff_and_publication.py) covering:
- Full 3-phase lifecycle (`draft -> assembled -> readiness_assessed -> review_pending -> approved -> delivered -> acknowledged`)
- Separation of duties (departing owner blocked from reviewer assignment and Phase 2 approval)
- 4-gate readiness blocker rejection for non-admin vs documented `ORG_ADMIN` override with audit trail
- SHA-256 `expected_content_hash` mismatch rejection (`409`) and optimistic concurrency `expected_case_version` enforcement (`409`)
- Mandatory rejection/return rationale + `affected_sections_json` persistence + controlled phase reopen
- Reassembly (`v2`) automatic supersession of `v1` signoffs (`is_superseded = True`) while preserving historical rows
- Duplicate approval, duplicate publication, duplicate acknowledgement, and recipient impersonation rejections
- Recipient clarification question + owner/manager reply persistence & audit events
- Cross-project access isolation (`404` / `403`)

**Command Executed**:
```bash
cd backend && .venv/bin/pytest \
  tests/test_handover_eligibility_and_assembly.py \
  tests/test_handover_stage3_canonical_sections.py \
  tests/test_handover_stage4_readiness_intelligence.py \
  tests/test_handover_stage5_checklists_and_responsibilities.py \
  tests/test_handover_stage6_signoff_and_publication.py -v
```
**Observed Result**: **`25 passed, 0 failed in 2.19s`**.

---

## 16. Frontend TypeScript Strict Verification

**Command Executed**:
```bash
cd frontend && npx tsc --noEmit
```
**Observed Result**: **Exit code `0`, 0 TypeScript errors**.

---

## 17. Live Authenticated Browser QA (Strictly Read-Only on `HO-9435`)

Verified in an authenticated browser session on `http://localhost:3000` (signed in as `siddhesh Birewar`, `project_manager` on `Skill Passport-Siddhesh`, Case `HO-9435` `9435d897-9b63-48d5-af4e-b2eef987a906`). **Zero mutations were executed against the live case.**

| Check | Target | Observed Result |
| :--- | :--- | :--- |
| Workspace API | `GET .../cases/9435d897-.../signoffs/workspace` | **HTTP 200 OK**, 0 failed requests (4xx/5xx), 0 runtime console errors |
| Lifecycle & Package Binding | `/handovers/9435d897-.../review` | `Readiness Assessed`, `Package v1 (Current)`, `SHA-256: 542ed862743522…`, Outgoing Owner `siddhesh Birewar`, Independent Reviewer `Not assigned yet`, Designated Successor `Not assigned yet` |
| 4-Gate Approval Eligibility | `/handovers/9435d897-.../review` | `Blocked`: Score `56/100 < 70/100`, `460` unverified items, `22` unresolved conflicts, `6` incomplete mandatory checklist items; working navigation pills to Readiness/Checklists/Ownership/Conflicts/Verification |
| Three-Phase Signoff Governance | `/handovers/9435d897-.../review` | Phase 1: `Action Required` (`siddhesh Birewar`, `Submit Phase 1 Sign-Off` visible, left unclicked); Phase 2: `Blocked by Gates` with explicit `"Separation of duties: the departing member cannot approve their own handover."`; Phase 3: `Pending` (`Recipient acknowledgement opens only after controlled publication.`) |
| Controlled Publication | `/handovers/9435d897-.../review` | `Not Eligible to Publish`, `Publish Approved Package` button disabled, 3 exact blocking reasons rendered |
| Assign Reviewer Modal | Click `Assign` -> inspect -> `Cancel` | Cleanly reports `"No eligible independent reviewer available"`, zero synthetic users listed, submit button disabled |
| Reload Persistence | Browser reload on `/review` | Exact persisted state, gates, and 3 PostgreSQL audit log events survived reload with 0 errors |
| Recipient Workspace | `/handovers/9435d897-.../recipient` | `[data-testid="recipient-workspace"]` rendered cleanly with 0 API/console errors; displays `"No published deliveries exist yet"` + live Canonical 8-Domain Handover Package Reader |
| Host-Verified Visual Evidence | `final_step_26.png` | Visually inspected; layout, typography, badges, gates, phase cards, publication block, and audit trail verified clean |

---

## 18. Known Scope Boundaries & Stage 7 Readiness

- **Scope Boundaries Respected**:
  - PDF/export formatting improvements were intentionally excluded per Stage 6 instructions.
  - Live project case `HO-9435` remains untouched (`readiness_assessed`) with zero fabricated approvals, publications, or acknowledgements.
  - No git commits, pushes, PRs, or deployments were performed.
- **Graphify Synchronisation**: Executed `graphify update .` cleanly (`11,242 nodes`, `37,702 edges`, `399 communities`).
- **Stage 7 Readiness**: The Handover Workspace now has complete end-to-end persistence, canonical 8-domain packaging, live 4-gate readiness intelligence, transition checklists, responsibility transfer, three-phase signoff, controlled publication, and complete-package recipient acknowledgement ready for Stage 7 (Published Handovers directory / export & finalisation workflows).
