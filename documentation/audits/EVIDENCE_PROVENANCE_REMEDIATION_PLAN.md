# Evidence Provenance & Data Authenticity — Remediation Plan

**Platform**: The Handover — Intelligent Project Knowledge Reconstruction & Handover Platform  
**Date**: 2026-11-18  
**Companion Audit**: [EVIDENCE_PROVENANCE_AUDIT.md](EVIDENCE_PROVENANCE_AUDIT.md) · [EVIDENCE_PROVENANCE_RECORD_MATRIX.md](EVIDENCE_PROVENANCE_RECORD_MATRIX.md)  
**Status**: **PLAN ONLY — NOT IMPLEMENTED** (per strictly read-only audit constraints)

---

## Prioritized Issue Register

| ID | Severity | Category | Affected Component(s) | Summary |
| :--- | :--- | :--- | :--- | :--- |
| **PROV-01** | **HIGH** | Security (ACL) | `backend/app/services/conflict_service.py` (L66–L113), `backend/app/repositories/conflict.py` (L92–L102) | `list_conflicts` performs zero `SourceAccessPolicyService` checks; exposes restricted source titles/explanations and allows SQL `search` keyword-oracle over restricted claims (`ACL-01`). |
| **PROV-02** | **HIGH** | Security (ACL) | `backend/app/services/conflict_service.py` (L127–L175) | `get_conflict_details` fails open (`allow_a/b = True`) on missing `EvidenceItem` and leaves `side_a.title`, `side_b.title`, `explanation`, and `authoritative_claim_text` unredacted when a side is restricted (`ACL-02`). |
| **PROV-03** | **HIGH** | Security (ACL) | `backend/app/services/verification_review.py` (L117–L155, L281, L374–L382) | `get_case_detail` returns unfiltered `machine_assessment_json` (`contradiction_analysis.contradictions[]`, `freshness_assessment.superseded_by_record_title`), `conflicts[].explanation`, `issues[].description`, `current_claim`, `original_ai_claim`, and `revisions`; `list_queue` applies no per-viewer ACL filter (`ACL-03`, `ACL-04`). |
| **PROV-04** | **MEDIUM** | Detection / Data Governance | Live PostgreSQL `verification_conflicts` (`28` rows on `Skill Passport-Siddhesh`) + `verification_engine.py` | All `28/28` historical conflicts are pre-DEF-08 false positives (`4` false JWT-vs-session collisions + `24` merge-commit/multi-author ownership false positives collapsing to `10` unique pairs with symmetric A↔B duplication). |
| **PROV-05** | **MEDIUM** | Data Hygiene | Live PostgreSQL (`Handover Test Project fa1a46` [`62ca67c9`] & `Handover Test Project 7cbb1d` [`44863232`]) | `6` orphaned synthetic test `VerificationCase` rows (plus `6` fake `arch_doc.pdf` `EvidenceItem` rows with `storage_object_key=NULL`, `0` chunks) left behind in the live PostgreSQL database in two test organisations. |
| **PROV-06** | **MEDIUM** | UI / API Contract | `frontend/src/app/projects/[id]/conflicts/page.tsx`, `frontend/src/components/verification/ConflictsWorkspace.tsx` | `/projects/[id]/conflicts` mounts deprecated `ConflictsWorkspace.tsx`, which silently swallows API errors (`.catch(() => null)`), auto-prefills hardcoded adjudication notes, and posts legacy resolve fields incompatible with `ResolveConflictRequest` (`UI-01`). |
| **PROV-07** | **MEDIUM** | Data Integrity / Schema | `backend/app/models/verification.py` (L72, L254–L266) | `VerificationConflict.claim_a/b_source_evidence_id` uses `ON DELETE CASCADE` (hard-deleting evidence silently deletes conflict audit records) and `VerificationCase.target_id` has no DB-enforced FK or deletion cleanup trigger. |
| **PROV-08** | **MEDIUM** | Detection / Provenance Fidelity | `backend/app/services/verification_intelligence.py`, `backend/app/services/verification_engine.py` | Conflict creation stores AI-paraphrased `KnowledgeItem` summaries in `claim_a_text`/`claim_b_text` without storing the verbatim `EvidenceChunk` quote alongside them, and emits symmetric A↔B duplicate conflict pairs. |
| **PROV-09** | **LOW** | UI / Labeling | `frontend/src/components/conflicts/ConflictDashboardBar.tsx` (L146–L149) | `"Needs Attention"` card appends a hardcoded `"critical"` suffix to `attention_required_count` (`28`), displaying `"28 critical"` when `critical_priority = 0` (`UI-02`). |
| **PROV-10** | **LOW** | UI / Routing | `frontend/src/components/verification/VerificationCenterWorkspace.tsx`, `/projects/[id]/verification`, `/projects/[id]/conflicts` | `VerificationCenterWorkspace` ignores `?case_id=` query parameter linked from Conflict Management; `/projects/[id]/*` routes ignore the `[id]` path parameter and rely exclusively on `LiveAppContext.activeProject` (`UI-03`). |
| **PROV-11** | **LOW** | Detection / UI Copy | `backend/app/services/verification_intelligence.py`, `backend/app/services/verification_engine.py`, `frontend/src/components/verification/FindingWorkspacePanel.tsx` | (a) Automated recommendation text says `"Finding is verified by automated checks: ... and corroborated"` on single-source (`Corroboration: Single Source`) findings; (b) `priority_reason` on conflicted cases reads `(0 conflict(s))`; (c) GitHub commits/READMEs display `location_label = "Page 1"` instead of commit SHA / file path (`UI-04`). |

---

## Detailed Remediation Specifications

### PROV-01 & PROV-02 — Enforce Fail-Closed Source ACLs Across Conflict List, Search & Detail (HIGH · Security)
- **Evidence**: `backend/app/services/conflict_service.py` L66–L175; `backend/app/repositories/conflict.py` L92–L102.
- **Recommended Correction**:
  1. Pass `user_id` and `has_manage` into `ConflictService.list_conflicts()`. Eager-load `claim_a_evidence` and `claim_b_evidence` and run `SourceAccessPolicyService.can_user_access_evidence()` on both sides before returning rows.
  2. When either side is restricted (`allow_a=False` or `allow_b=False`), redact `side_a.title` / `side_b.title` to `"[Restricted source]"`, redact `explanation` and `authoritative_claim_text`, and exclude restricted rows from matching SQL `search` queries on `claim_a_text` / `claim_b_text` / `side_*_source_title` (preventing keyword-oracle leakage).
  3. Change `get_conflict_details()` defaults from `allow_a = True` / `allow_b = True` to **fail closed** (`allow_a = False` if `ev_a is None` or `ev_a.deleted_at is not None`).
  4. Add unit & API integration tests verifying restricted viewers cannot read restricted titles, explanations, authoritative claims, or search-probe restricted conflicts.

### PROV-03 — Enforce Fail-Closed Source ACLs in Verification Queue & Detail Assessment Payload (HIGH · Security)
- **Evidence**: `backend/app/services/verification_review.py` L117–L155, L281, L374–L382.
- **Recommended Correction**:
  1. Pass `project_ctx` (`user_id`, `has_manage`) into `VerificationReviewService.list_queue()`. When **all** evidence references for a case are restricted for the viewer, mask `title`/`current_claim`/`original_ai_claim` (or omit from search matches) and surface a safe restricted-access indicator.
  2. In `VerificationReviewService.get_case_detail()`, filter `machine_assessment_json` (specifically `contradiction_analysis.contradictions[]` and `freshness_assessment.superseded_by_record_title`), `conflicts[].explanation`, `issues[].description`, `revisions`, and `current_claim`/`original_ai_claim` whenever underlying evidence is restricted (`restricted_count > 0` or `allow_a/allow_b` is `False`).
  3. Add regression tests in `backend/tests/test_verification_security_e2e.py` verifying zero leakage through `machine_assessment_json`, `contradiction_analysis`, or queue search.

### PROV-04 — Human Triage of 28 Historical Pre-DEF-08 Conflicts & Pair Deduplication (MEDIUM · Detection / Data)
- **Evidence**: `28/28` live conflicts in `Skill Passport-Siddhesh` (`4` false JWT-vs-session + `24` merge-commit ownership pairs collapsing to `10` unique pairs); see [EVIDENCE_PROVENANCE_RECORD_MATRIX.md](EVIDENCE_PROVENANCE_RECORD_MATRIX.md).
- **Recommended Correction**:
  1. **Governance Triage (Human Action Only)**: Have an authorized Project Reviewer/Admin inspect and resolve the `28` legacy rows via `POST /api/v1/projects/{project_id}/conflicts/{conflict_id}/resolve` using `resolution_strategy="dismissed_false_positive"` with an explicit audit rationale. Do **not** hard-delete rows or run silent SQL updates.
  2. **Symmetric Pair Deduplication (Code)**: In `VerificationEngine` / `ConflictDetectionEngine`, canonicalize evidence pair ordering `(min(ev_a, ev_b), max(ev_a, ev_b), conflict_type)` when persisting conflicts so A↔B mirror duplicates are never materialized twice.

### PROV-05 — Purge Orphaned Synthetic Test Tenants & Enforce Test DB Isolation (MEDIUM · Data)
- **Evidence**: Live PostgreSQL contains `Handover Test Project fa1a46` (`62ca67c9-f505-4dc3-b9bf-a58dd53c11f6`) and `Handover Test Project 7cbb1d` (`44863232-65f8-4efd-91e5-83f0a3e72a3c`) with `6` synthetic `VerificationCase` rows and `6` placeholder `arch_doc.pdf` rows (`storage_object_key=NULL`, `0` chunks).
- **Recommended Correction**:
  1. Perform an audited, operator-approved cleanup of the two test organisations (`80a8a864-a16f-49ce-908c-eb8324ba3b4b` and `cf1081ac-bde4-4f6e-9cdc-26b627db0c1e`) from the live PostgreSQL instance after verifying no real user belongs to them.
  2. Add a pytest/conftest guard ensuring integration tests cannot target a non-isolated / production `DATABASE_URL`.

### PROV-06 — Replace Deprecated `ConflictsWorkspace.tsx` on `/projects/[id]/conflicts` (MEDIUM · UI)
- **Evidence**: `frontend/src/app/projects/[id]/conflicts/page.tsx` mounts `frontend/src/components/verification/ConflictsWorkspace.tsx`, which swallows errors via `.catch(() => null)`, pre-fills hardcoded adjudication notes (L153/L157), and submits legacy resolve fields (`resolution_state`, `preferred_claim`).
- **Recommended Correction**:
  1. Update `frontend/src/app/projects/[id]/conflicts/page.tsx` to render `ConflictManagementWorkspace` (the canonical component used by `/conflicts`).
  2. Deprecate and remove `ConflictsWorkspace.tsx` and legacy `api.conflicts` methods from `frontend/src/lib/api.ts` once unused.

### PROV-07 — Harden Conflict Evidence Deletion Semantics & Polymorphic Target Integrity (MEDIUM · Data / Schema)
- **Evidence**: `backend/app/models/verification.py` L72 (`target_id` without FK), L254–L266 (`ON DELETE CASCADE` on `claim_a/b_source_evidence_id`).
- **Recommended Correction**:
  1. Create a forward Alembic migration changing `verification_conflicts.claim_a_source_evidence_id` and `claim_b_source_evidence_id` from `ON DELETE CASCADE` to `ON DELETE SET NULL` (preserving immutable conflict audit records even if evidence is purged, paired with `PROV-02`'s fail-closed null check).
  2. Ensure soft-deletion of `KnowledgeItem` or `KnowledgeRelationship` updates or archives corresponding `VerificationCase` records cleanly.

### PROV-08 — Separate Verbatim Source Excerpts from AI-Reconstructed Claims in Conflicts (MEDIUM · Provenance)
- **Evidence**: On the `4` `decision_conflict` rows and `2` README `ownership_conflict` rows, `claim_a_text` / `claim_b_text` hold LLM-paraphrased `KnowledgeItem` statements rather than verbatim `EvidenceChunk` excerpts (e.g., `000e354a` Side B paraphrasing `.agents/skills/cavecrew/README.md` chunk 6).
- **Recommended Correction**:
  1. Persist and return both `claim_text` (AI-extracted claim) and `verbatim_source_excerpt` (exact substring from `EvidenceChunk`) on `VerificationConflict` / `ConflictEvidenceSide`, clearly labeling AI summary vs verbatim source quote in the UI per `AGENTS.md` §5.8 (Four-Tier Epistemic Separation).

### PROV-09 — Fix Misleading `"critical"` Label on Conflict Dashboard Attention Card (LOW · UI)
- **Evidence**: `frontend/src/components/conflicts/ConflictDashboardBar.tsx` L146–L149 renders `{metrics?.attention_required_count ?? 0}` followed by hardcoded `"critical"` (confirmed in `final_step_39.png`: `"28 critical"` when `critical_priority = 0`).
- **Recommended Correction**:
  1. Change the subtitle to `"pending review"` / `"need attention"` (or display `metrics?.critical_priority ?? 0` if the card is intended to show critical-priority count).

### PROV-10 — Support `?case_id=` Deep-Linking & `[id]` Route Scoping (LOW · UI)
- **Evidence**: `ConflictInvestigationWorkspace.tsx` L438 links to `/verification?case_id=...`, but `VerificationCenterWorkspace.tsx` ignores `useSearchParams().get("case_id")`; `/projects/[id]/verification` and `/projects/[id]/conflicts` ignore `[id]`.
- **Recommended Correction**:
  1. Read `useSearchParams().get("case_id")` in `VerificationCenterWorkspace.tsx` to select the linked verification case directly.
  2. Read `useParams().id` on `/projects/[id]/verification` and `/projects/[id]/conflicts` and sync/scope requests to the route's project ID.

### PROV-11 — Fix Automated Check Copy, `priority_reason` Count & GitHub `location_label` (LOW · Detection / UI)
- **Evidence**: Observed in `final_step_45.png` and `audited_26_cases.json`:
  - Recommendation text says `"Finding is verified by automated checks: evidence is complete, fresh, and corroborated..."` on single-source findings (`003331fd`).
  - `priority_reason` prints `"Contradictory findings detected across sources (0 conflict(s))"` on conflicted cases (`556d1785`, `5c58f483`, `621bbd60`).
  - `VerificationEvidenceRef.location_label` displays `"Page 1"` on GitHub commits and Markdown READMEs.
- **Recommended Correction**:
  1. Reword `RecommendationEngine` copy to avoid saying `"verified by automated checks"` (reserve `"verified"` strictly for human verification per `AGENTS.md` §5.8) and only state `"corroborated"` when `independent_sources_count >= 2`.
  2. Compute `priority_reason` conflict count from persisted + newly detected conflicts so it matches actual open conflicts.
  3. Format `location_label` by source type: commit SHA (`commit <sha[:8]>`) for GitHub commits, file path (`<path>`) for GitHub documentation, PR/issue number (`PR #<n>`) for GitHub PRs/issues, and `Page <n>` only for paginated uploaded documents.
