# Stage 8A — Evidence-Level ACL Enforcement & Provenance Security Remediation Report

**Platform**: The Handover — Intelligent Project Knowledge Reconstruction & Handover Platform  
**Date**: 2026-11-18  
**Baseline Audit**: [EVIDENCE_PROVENANCE_AUDIT.md](EVIDENCE_PROVENANCE_AUDIT.md) · [EVIDENCE_PROVENANCE_REMEDIATION_PLAN.md](EVIDENCE_PROVENANCE_REMEDIATION_PLAN.md)  
**Scope**: Backend-first remediation of the four confirmed evidence-level ACL gaps (`ACL-01`–`ACL-04` / `PROV-01`–`PROV-03`) in Verification Center and Conflict Management. Zero changes to conflict detection, conflict classifications, existing findings, reviewer decisions, evidence records, or database schema.

---

## A. Executive Summary

- **Security Issues Investigated**: All four confirmed ACL gaps from the Evidence Provenance Audit (`ACL-01` Conflict Listing & Search/Dashboard, `ACL-02` Conflict Detail Redaction & Fail-Open Null Handling, `ACL-03` Verification Detail Derived-Data & Revision Leakage, `ACL-04` Verification Queue/Summary/Facets Filtering).
- **Issues Confirmed**: All four gaps (`4/4`) were confirmed present in the codebase prior to remediation.
- **Issues Fixed**: All four gaps (`4/4`) have been remediated at the backend service boundary using the canonical `SourceAccessPolicyService` and `redact_secrets` utilities, with `O(1)` batched SQL ACL evaluation and comprehensive fail-closed unit/integration tests (`47 passed, 0 failed` across 11 test suites).
- **Data Integrity Preserved**: Live PostgreSQL records on `Skill Passport-Siddhesh` (`fa71b2e5-140e-4040-b1ea-4ac6036382b9`) were verified read-only to be completely untouched (`460` verification cases, `28` unresolved conflicts: `4` `decision_conflict`, `24` `ownership_conflict`).

---

## B. Root-Cause Analysis

| Defect ID | Audit Ref | Root Cause |
| :--- | :--- | :--- |
| **ACL-01** | `PROV-01` | `ConflictService.list_conflicts()` and `ConflictService.get_dashboard_metrics()` did not accept a caller identity or call `SourceAccessPolicyService`. `ConflictRepository.list_conflicts()` also applied SQL `LIKE` search directly across unredacted `claim_a_text`, `claim_b_text`, `side_a_source_title`, `side_b_source_title`, and `explanation`, creating a search-oracle and aggregate count leak over restricted sources. |
| **ACL-02** | `PROV-02` | `ConflictService.get_conflict_details()` defaulted `allow_a = True` and `allow_b = True` when `ev_a is None` or `ev_b is None` (fail-open on null/missing evidence). Even when `allow_a=False` or `allow_b=False`, `side_a.title`, `side_b.title`, `explanation`, `authoritative_claim_text`, `investigation_notes`, `resolution_notes`, `audit_history[].notes`, and `related_finding_title` were returned unredacted, and fully restricted conflicts returned `200` metadata instead of failing closed. |
| **ACL-03** | `PROV-03` | `VerificationReviewService.get_case_detail()` filtered `evidence_references` and `conflicts[].side_a/side_b`, but returned raw `machine_assessment_json` (including `contradiction_analysis.contradictions[]` and `freshness_assessment.superseded_by_record_title`), `conflicts[].explanation`, `issues[].description`/`details`, `current_claim`, `original_ai_claim`, `title`, `revisions[]`, `review_events[]`, and `context_requests[]` without per-viewer ACL sanitization. |
| **ACL-04** | `PROV-03` | `VerificationReviewService.list_queue()`, `get_summary()`, and `list_context_requests()` did not evaluate per-viewer source ACLs. `VerificationRepository.list_project_cases()` ran SQL `ILIKE` search across restricted claims/titles and `list_filter_facets()` exposed domains, source providers, and person labels derived from restricted findings. |

---

## C. Implementation Details

### Files & Services Modified
1. **`backend/app/services/integrations/access_policy.py`** *(Canonical ACL Authority — reused & extended, no competing system)*:
   - Hardened `can_user_access_evidence()` to fail closed on `None`, `deleted_at is not None`, or `processing_status == 'deleted'`.
   - Added `can_user_access_evidence_safe()` enforcing `project_id` scoping, deletion checks, and `try/except` fail-closed handling on ACL evaluation errors (`ACL-T07`).
   - Added `evaluate_evidence_batch()` running at most `2` SQL queries (`EvidenceItem` `IN` query + `selectinload(EvidenceItem.source_access_policy)`) with zero cross-user caching.
   - Added `list_restricted_titles_for_viewer()` to identify viewer-inaccessible project evidence titles in a single batched query for scrubbing derived assessments.
2. **`backend/app/repositories/conflict.py` & `backend/app/services/conflict_service.py` & `backend/app/api/routes/conflicts.py`**:
   - Added `ConflictRepository.list_project_conflicts_for_acl()` (non-text structural filters only + `selectinload` eager loading; text search never pushed into SQL before ACL filtering).
   - Added `_verify_viewer_access()` validating active `User` and active `ProjectMembership` (unless verified `project.manage`).
   - Enforced batched per-side ACL evaluation (`_resolve_side_access()`) across `get_dashboard_metrics()`, `list_conflicts()`, `get_conflict_details()`, and mutation return paths (`has_manage=True`).
   - Null, missing, deleted, cross-project, or exception-throwing evidence references fail closed (`is_accessible=False`).
   - Fully inaccessible conflicts (`not allow_a and not allow_b`) are omitted from dashboard metrics, list items, `total_count`, search, and pagination, and raise generic `403 ForbiddenError` (`SOURCE_ACCESS_DENIED`) on direct detail fetch with zero leaked source strings.
   - Partially accessible conflicts (`allow_a != allow_b`) redact the restricted side (`title="[Restricted source]"`, `provider="restricted"`, `claim_text="[Content redacted: insufficient source permissions]"`, null IDs/URL/author/timestamp, generic `redaction_reason`) as well as cross-side derived fields (`explanation`, `authoritative_claim_text`, `investigation_notes`, `resolution_notes`, `audit_history[].notes`, `related_finding_title`) and restrict `search` strictly to viewer-authorized fields.
3. **`backend/app/repositories/verification.py` & `backend/app/services/verification_review.py` & `backend/app/api/routes/verification.py`**:
   - Added `VerificationRepository.list_project_cases_for_acl()` (structural filters + eager `selectinload` on `issues`, `evidence_refs`, `conflicts`, `context_requests`, `assigned_reviewer`).
   - Updated `GET /verification/summary`, `GET /verification/queue`, and `GET /verification/context-requests` routes to pass `project_ctx` to `VerificationReviewService`.
   - Enforced batched case ACL evaluation (`_batch_evaluate_cases_acl()` — covering `evidence_refs`, `conflicts`, `issues`, `machine_assessment_json` UUIDs, and defensive `KnowledgeEvidenceLink`/`RelationshipEvidenceLink` checks when `evidence_refs` is empty).
   - `list_queue()` and `get_summary()` omit fully restricted cases from results, `total`, status counts, open issue/conflict/context counts, pagination, filter facets (`available_domains`, `available_sources`, `available_people`), and post-ACL `search`/`person`/`category` filtering.
   - `get_case_detail()` sanitizes all direct and derived fields: `title`, `original_ai_claim`, `current_claim`, `person_name`, `source_provider`, `uncertainty_note`, `evidence_references`, `conflicts` (sides + `explanation`), `issues` (`description`, `details`, `conflicting_evidence_id`), `revisions` (`claim_text`, `edit_reason`), `review_events`, `context_requests`, `handover_eligible`, and `machine_assessment` + all derived sub-assessments (`contradiction_analysis.contradictions[]`, `freshness_assessment.superseded_by_record_title`, `monitoring_status`, `completeness_assessment`, `reliability_assessment`, `corroboration_assessment`, `recommendation`, `priority_reason`) via `_sanitize_machine_assessment()` and `redact_secrets()`.
4. **Tests Added / Updated**:
   - Created `backend/tests/test_stage8a_evidence_acl.py` covering `ACL-T01` through `ACL-T14`, list/detail consistency, error-message safety, and `O(1)` SQL query budget assertions.
   - Updated legacy null-evidence fixtures in `backend/tests/test_conflict_management.py` to attach real project-accessible `EvidenceItem` records (rather than weakening fail-closed null handling).
   - Updated `test_tier4_fail_closed_evidence_acl_masking_and_eligibility` in `backend/tests/test_verification_security_e2e.py` to assert the newly enforced queue omission (`total == 0`) and full detail redaction for revoked policies.

---

## D. Testing Results

### Executed Test Command
```bash
cd backend && .venv/bin/pytest \
  tests/test_stage8a_evidence_acl.py \
  tests/test_verification_center.py \
  tests/test_verification_security_e2e.py \
  tests/test_conflict_management.py \
  tests/test_source_authorization_policy.py \
  tests/test_evidence_isolation.py \
  tests/test_tenant_isolation.py \
  tests/test_rbac_and_constraints.py \
  tests/test_handover_stage3_canonical_sections.py \
  tests/test_handover_export_acl.py \
  tests/test_handover_stage6_signoff_and_publication.py -v
```

### Results (`47 passed, 0 failed, 0 skipped` in `26.75s`)

| Test Suite | Passed | Failed | Skipped | Coverage |
| :--- | :---: | :---: | :---: | :--- |
| `tests/test_stage8a_evidence_acl.py` *(new)* | `5` | `0` | `0` | `ACL-T01`–`ACL-T14`, list/detail consistency, error safety, `O(1)` batch SQL budget |
| `tests/test_verification_center.py` | `3` | `0` | `0` | Verification sync, 5 reviewer actions, source ACL & RBAC |
| `tests/test_verification_security_e2e.py` | `17` | `0` | `0` | Full post-0020 Verification Center security, RBAC, tenant isolation & revoked ACL |
| `tests/test_conflict_management.py` | `3` | `0` | `0` | Conflict dashboard, lifecycle actions, partial-side ACL redaction |
| `tests/test_source_authorization_policy.py` | `2` | `0` | `0` | Canonical `SourceAccessPolicyService` classification & enforcement |
| `tests/test_evidence_isolation.py` | `1` | `0` | `0` | Evidence Center tenant & source isolation |
| `tests/test_tenant_isolation.py` | `3` | `0` | `0` | Multi-tenant organisation & project isolation |
| `tests/test_rbac_and_constraints.py` | `3` | `0` | `0` | Platform RBAC & database integrity constraints |
| `tests/test_handover_stage3_canonical_sections.py` | `5` | `0` | `0` | Handover section source ACL & provenance hydration |
| `tests/test_handover_export_acl.py` | `2` | `0` | `0` | Per-viewer Handover export ACL & secret redaction |
| `tests/test_handover_stage6_signoff_and_publication.py` | `3` | `0` | `0` | Separation of duties, reviewer approval, publication & acknowledgement |
| **Total** | **`47`** | **`0`** | **`0`** | **100% passing; no frontend/schema changes required** |

---

## E. Performance

- **Batch ACL Evaluation (`O(1)` SQL Queries)**:
  - Measured directly via SQLAlchemy `before_cursor_execute` instrumentation on a project with `15` cases and `15` conflicts (`30` evidence references):
    - **`GET /conflicts`**: `4` data/ACL SQL queries (`verification_conflicts`, `verification_cases`, `verification_evidence_refs`, `evidence_items` batch) — **0 N+1 queries**.
    - **`GET /verification/queue`**: `7` data/ACL SQL queries (`verification_cases`, `verification_conflicts`, `verification_context_requests`, `verification_evidence_refs`, `verification_issues`, `evidence_items` batch, restricted-title batch) — **0 N+1 queries**.
  - Authorization decisions are computed per request and **never cached across users**.
- **Trade-off Noted**: Because post-ACL text search and pagination execute in Python after fetching non-archived project rows, projects scaling beyond several thousand verification cases or conflicts would benefit from a future SQL-level ACL predicate pushdown (e.g., indexed policy membership join). At current project sizes (`460` cases, `28` conflicts), in-memory filtering over batched rows completes in milliseconds.

---

## F. Security Limitations

1. **Runtime Multi-Viewer ACL Behaviour on Live PostgreSQL (`NOT VERIFIED` in live production data)**:
   - All `14` ACL scenarios (`ACL-T01`–`ACL-T14`) were verified via isolated automated integration tests using FastAPI `TestClient` and real SQLAlchemy/RBAC/ACL pipelines.
   - However, the live `Skill Passport-Siddhesh` workspace currently has only `1` active project member and `0` `source_restricted` evidence items (its connected GitHub repo is `public` with `acl_scope = 'project_members'`), and Stage 8A prohibits creating test users or synthetic records in the active project. Multi-viewer runtime verification against live private GitHub/Jira/Slack connectors remains to be observed when private sources and additional team members are onboarded.
2. **Substring Title Matching in Derived Assessments**:
   - `_text_mentions_restricted()` scrubs derived prose containing exact restricted evidence titles (case-insensitive, length `>= 3`). If an LLM paraphrases sensitive content from a restricted evidence item into an unrelated public finding without referencing the restricted evidence ID or title, title-based scrubbing alone cannot detect unlinked paraphrases—making strict `evidence_refs` / `evidence_id` linkage essential upstream.
3. **Unchanged Scope Items (Deferred to Later Stages)**:
   - The `28` pre-DEF-08 live conflicts, legacy `/projects/[id]/conflicts` UI route, and schema FK/CASCADE adjustments were intentionally not modified in Stage 8A.

---

## G. Final Defect Status

| Defect ID | Area | Final Status | Basis |
| :--- | :--- | :--- | :--- |
| **ACL-01** | Conflict Management list, search, pagination & dashboard ACL enforcement | **FIXED AND TESTED** | Remediated in `ConflictService` / `ConflictRepository` / `conflicts.py`; verified by `ACL-T01`–`ACL-T09`, `ACL-T13`, `ACL-T14` + `O(1)` query check |
| **ACL-02** | Conflict Management detail redaction & fail-closed null/missing/exception handling | **FIXED AND TESTED** | Remediated in `ConflictService.get_conflict_details()` & `SourceAccessPolicyService`; verified by `ACL-T01`–`ACL-T07`, `ACL-T13`, `ACL-T14` |
| **ACL-03** | Verification Center detail derived assessments, claims, issues, conflicts & revision ACL | **FIXED AND TESTED** | Remediated in `VerificationReviewService.get_case_detail()` & `_sanitize_machine_assessment()`; verified by `ACL-T07`, `ACL-T10`, `ACL-T11`, `ACL-T12`, `test_verification_security_e2e.py` |
| **ACL-04** | Verification Center queue, summary, search, facets, pagination & context-requests ACL | **FIXED AND TESTED** | Remediated in `VerificationReviewService.list_queue()` / `get_summary()` / `list_context_requests()`; verified by `ACL-T07`, `ACL-T08`, `ACL-T09`, `ACL-T12`, `ACL-T13`, `ACL-T14` + `O(1)` query check |
