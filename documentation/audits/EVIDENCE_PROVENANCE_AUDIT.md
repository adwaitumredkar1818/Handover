# Evidence Provenance & Data Authenticity Audit

**Platform**: The Handover — Intelligent Project Knowledge Reconstruction & Handover Platform  
**Audit Date**: 2026-11-18  
**Audit Type**: Strictly Read-Only Data Provenance, Authenticity, ACL & UI/Backend Consistency Audit  
**Modules Audited**: Verification Center & Conflict Management  
**Final Verdict**: **`VERIFIED WITH LIMITATIONS`**

---

## 1. Executive Summary

A strictly read-only audit of **Verification Center** and **Conflict Management** was performed across PostgreSQL (`SET TRANSACTION READ ONLY`), backend models/services/repositories/API routes, frontend components/API clients, and host-verified read-only visual captures of the live application (`http://localhost:3000/verification` and `http://localhost:3000/conflicts`).

**Core Answer:**
- On the active live project (**`Skill Passport-Siddhesh`**, `fa71b2e5-140e-4040-b1ea-4ac6036382b9`), **100% of Verification Center findings (`460/460`) and 100% of Conflict Management records (`28/28`) originate from real, persisted GitHub evidence** synced from `shubham392007-sketch/HackMatrix-5.0-MISC02` (72 evidence items, 463 chunks, 1 non-synthetic `qwen3:8b` extraction run). Every single `VerificationEvidenceRef` excerpt (`520/520`, 100%) matches verbatim inside its linked PostgreSQL `EvidenceChunk.chunk_text`. Neither `/verification` nor `/conflicts` contains hardcoded findings, hardcoded conflicts, `figmaStore` mock bindings, or silent synthetic API fallbacks.
- **However, four material limitations and confirmed defects prevent an unqualified `VERIFIED` verdict:**
  1. **100% of persisted conflicts (`28/28`) are `D. Potentially Misclassified`**: All `28` conflicts stem from pre-DEF-08 heuristics (`4` false JWT-vs-session collisions against SQLAlchemy `session.py` / `"session reports"` / `"JSONL session"` / `"API session default"`, plus `24` Git merge-commit / multi-developer collaboration false positives collapsing into `10` unique pairs duplicated symmetrically A↔B).
  2. **`6` orphaned synthetic test findings reside in the live PostgreSQL database**: Two leftover test tenants (`Handover Test Project fa1a46` and `Handover Test Project 7cbb1d`) contain `6` synthetic `VerificationCase` rows backed by placeholder `arch_doc.pdf` records (`storage_object_key = NULL`, `0` chunks, `0` `VerificationEvidenceRef`). They are tenant-isolated from `Skill Passport-Siddhesh` by RBAC, so real project users never see them, but synthetic test residue remains in the live database.
  3. **4 backend source-ACL enforcement gaps (`ACL-01`–`ACL-04`)**: Although `Skill Passport-Siddhesh` currently has `0` restricted evidence items (`public` repo, `acl_scope = 'project_members'`), code inspection confirmed that if `source_restricted` evidence is present, `ConflictService.list_conflicts`, `ConflictService.get_conflict_details` (titles, explanation, fail-open on null evidence), `VerificationReviewService.list_queue`, and `VerificationReviewService.get_case_detail` (`machine_assessment_json.contradiction_analysis`, claims, issues) would leak restricted metadata/claims.
  4. **4 frontend/backend consistency defects (`UI-01`–`UI-04`)** and **no outbound live GitHub HTTP verification**: External GitHub URLs were verified against local Evidence Center copies only (no outbound GitHub fetch executed during this read-only audit); the legacy `/projects/[id]/conflicts` route still mounts deprecated `ConflictsWorkspace.tsx` (which swallows API errors and sends legacy resolve payloads); `ConflictDashboardBar` labels `28` non-critical attention items with a static `"critical"` suffix; and `/verification` ignores `?case_id=` deep-links.

### Exact Audit Totals

| Metric | Exact Count | Coverage |
| :--- | :---: | :--- |
| **Total `VerificationCase` rows in PostgreSQL** | `466` | `460` in `Skill Passport-Siddhesh` + `6` in `2` leftover test tenants |
| **Verification findings audited (record-level)** | **`26`** | Stratified sample of `20/460` real cases + `6/6` (100%) of leftover test cases |
| ↳ **A. Fully Traceable findings** | **`16`** | Real `Skill Passport-Siddhesh` cases with full local lineage & verbatim excerpts |
| ↳ **B. Partially Traceable findings** | **`1`** | Real case flagged `missing_evidence` / `sparse` completeness (`7dad3155`) |
| ↳ **C. Untraceable findings** | **`0`** | `0/460` broken refs on real project (`6` unref'd test rows classified as E) |
| ↳ **D. Potentially Misclassified findings** | **`3`** | Real merge-commit cases marked `conflicted` by pre-DEF-08 heuristics (`556d1785`, `5c58f483`, `621bbd60`) |
| ↳ **E. Synthetic / Hardcoded findings** | **`6`** | `3` in `Handover Test Project fa1a46` + `3` in `Handover Test Project 7cbb1d` (tenant-isolated leftover test fixtures) |
| **Total `VerificationConflict` rows in PostgreSQL** | `28` | `28` in `Skill Passport-Siddhesh`, `0` in all other projects |
| **Conflicts audited (record-level)** | **`28`** | **100% full-population audit** |
| ↳ **A. Fully Traceable conflicts** | **`0`** | None have a valid supported contradiction classification |
| ↳ **B. Partially Traceable conflicts** | **`0`** | — |
| ↳ **C. Untraceable conflicts** | **`0`** | All `28/28` trace to real `EvidenceItem` + `EvidenceChunk` rows |
| ↳ **D. Potentially Misclassified conflicts** | **`28`** | `4` false `decision_conflict` + `24` merge-commit `ownership_conflict` (10 unique pairs) |
| ↳ **E. Synthetic / Hardcoded conflicts** | **`0`** | — |
| **Confirmed ACL violations / code gaps** | **`4`** | `0` live data leaks on `Skill Passport-Siddhesh` (`public` repo); `4` confirmed backend code defects (`ACL-01`–`ACL-04`) |
| **Confirmed Frontend/Backend mismatches** | **`4`** | `UI-01` (legacy `/projects/[id]/conflicts` route), `UI-02` (static `"critical"` label), `UI-03` (ignored `?case_id=` / `[id]` params), `UI-04` (misleading single-source/automated-verification copy + `priority_reason` `(0 conflict(s))` + `"Page 1"` on commits) |

---

## 2. Scope & Methodology

- **Strictly Read-Only Execution**: All PostgreSQL queries ran inside explicit `SET TRANSACTION READ ONLY` transactions with `db.rollback()`. Zero `INSERT`, `UPDATE`, `DELETE`, sync, reconstruction, ingestion, or LLM calls were executed. No production code was modified.
- **Lineage & Code Inspection**: Used `graphify query` and direct source inspection across backend ORM models, repositories, services, API routes, frontend pages, API clients, and components.
- **Population + Record-Level Verification**: Computed full-population integrity statistics across all `466` `VerificationCase` rows, `520` `VerificationEvidenceRef` rows, `207` `VerificationIssue` rows, `78` `EvidenceItem` rows, `463` `EvidenceChunk` rows, and `28` `VerificationConflict` rows; audited `26` Verification findings and **100% (`28/28`)** of Conflicts at record level (see [EVIDENCE_PROVENANCE_RECORD_MATRIX.md](EVIDENCE_PROVENANCE_RECORD_MATRIX.md)).
- **Live Read-Only Visual Consistency Check**: Captured host-verified screenshots of the already-authenticated local UI at `http://localhost:3000/verification` (`final_step_45.png`) and `http://localhost:3000/conflicts` (`final_step_39.png`) without clicking any mutation controls or bypassing authentication.
- **PII & Secret Redaction**: Email addresses (`git_author_email`, `git_committer_email`, user emails), credentials, and tokens were strictly excluded from all audit reports.

---

## 3. Complete Data Lineage Architecture

Actual repository models, tables, services, repositories, API routes, and UI components verified against the codebase and live PostgreSQL schema:

```text
External GitHub Repo (shubham392007-sketch/HackMatrix-5.0-MISC02)
  └─ SourceConnection (source_connections) + ProjectSourceMapping (project_source_mappings)
       + SourceAccessPolicy (source_access_policies) + UserSourceAuthorisation (user_source_authorisations)
  ▼ [app/services/integrations/evidence_ingestor.py]
EvidenceItem (evidence_items)  ──▶  EvidenceContent (evidence_contents)
                               ──▶  EvidencePageContent (evidence_page_contents)
                               ──▶  EvidenceChunk (evidence_chunks)
  ▼ [app/services/knowledge.py · KnowledgeExtractionRun (knowledge_extraction_runs)]
KnowledgeItem (knowledge_items)        ──▶  KnowledgeEvidenceLink (knowledge_evidence_links)
KnowledgeRelationship (knowledge_relationships) ──▶ RelationshipEvidenceLink (relationship_evidence_links)
  ▼ [app/services/verification_engine.py · VerificationEngine.sync_project_findings() & assess_project()]
VerificationCase (verification_cases)  ──▶  VerificationEvidenceRef (verification_evidence_refs)
                                       ──▶  VerificationIssue (verification_issues)
                                       ──▶  VerificationFindingRevision (verification_finding_revisions)
                                       ──▶  VerificationReviewEvent (verification_review_events)
                                       ──▶  VerificationContextRequest (verification_context_requests)
  ▼ [app/services/verification_intelligence.py · AdvancedContradictionEvaluator / conflict_detection.py]
VerificationConflict (verification_conflicts)
  ▼ [Routes: app/api/routes/verification.py & app/api/routes/conflicts.py]
  ▼ [Services: VerificationReviewService & ConflictService | Repos: VerificationRepository & ConflictRepository]
  ▼ [Clients: frontend/src/lib/verificationApi.ts & frontend/src/lib/conflictsApi.ts]
UI: /verification (VerificationCenterWorkspace) & /conflicts (ConflictManagementWorkspace)
    [Legacy route /projects/[id]/conflicts mounts deprecated ConflictsWorkspace.tsx]
```

### Transition-by-Transition Lineage Verification

| Transition | Referencing Column(s) | Persisted vs Runtime | Project-Scoped? | Source Still Present? | Authorized App Path? | Provenance Retained on Update? |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Source → `EvidenceItem` | `evidence_items.source_connection_id`, `source_access_policy_id`, `source_external_id`, `source_url`, `content_hash` | Persisted (FK `SET NULL`) | Yes (`project_id`) | Yes (`72/72` on real project; `6/6` test docs have `storage_object_key=NULL`) | Yes (`GET /projects/{id}/evidence`) | Yes (re-sync preserves `content_hash` / `source_external_id`) |
| `EvidenceItem` → `EvidenceChunk` | `evidence_chunks.evidence_id` (FK `CASCADE`) | Persisted | Yes (`project_id`) | Yes (`463` chunks on `72/72` real items; `0` on `6` test items) | Yes (Evidence Detail & RAG) | Yes |
| `EvidenceItem`/`Chunk` → `KnowledgeItem` | `knowledge_evidence_links.knowledge_item_id`, `evidence_id`, `evidence_chunk_id`, `supporting_excerpt`; `knowledge_items.extraction_run_id` | Persisted (FK `CASCADE` / `SET NULL`) | Yes (`project_id`) | Yes (`590` links on `460` real items; `3+3` on test items) | Yes (`/projects/{id}/knowledge`) | Yes |
| `KnowledgeItem` → `VerificationCase` | `verification_cases.target_type`, `target_id` (polymorphic UUID — **no DB FK constraint**) | Persisted | Yes (`project_id`) | Yes (`466/466` targets present, `0` cross-project) | Yes (`GET /verification/cases/{id}`) | **Yes**: `edit_finding` preserves `original_ai_claim`, appends `VerificationFindingRevision`, keeps `target_id` & `evidence_refs` |
| `KnowledgeEvidenceLink` → `VerificationEvidenceRef` | `verification_evidence_refs.case_id`, `evidence_item_id`, `evidence_chunk_id`, `excerpt` | Persisted (deduplicated per `(case, evidence, chunk)`) | Yes (`project_id`) | Yes (`520/520` on real project = 100% of `520` unique `(ki, ev, chunk)` triples; `0` on `6` test cases) | Yes (ACL-filtered in `VerificationReviewService.get_case_detail`) | Yes |
| `VerificationCase`/`EvidenceItem` → `VerificationConflict` | `verification_conflicts.case_id`, `related_finding_id`, `claim_a_source_evidence_id`, `claim_b_source_evidence_id`, `claim_a_chunk_id`, `claim_b_chunk_id` | Persisted (`claim_*_source_evidence_id` nullable, `ON DELETE CASCADE`) | Yes (`project_id`) | Yes (`28/28` valid same-project `EvidenceItem` & `EvidenceChunk` refs) | Partial (ACL gaps `ACL-01`/`ACL-02` documented in §8) | **Warning**: `ON DELETE CASCADE` on `evidence_items.id` would silently drop conflict history if an evidence item is hard-deleted; `resolve_conflict` retains Side A/B links |

### Lineage Gaps Identified
1. **No DB FK on `verification_cases.target_id`**: Polymorphic reference (`target_type` + `target_id`) is not FK-enforced at the database level (`0` broken rows today, structural risk).
2. **`ON DELETE CASCADE` on `VerificationConflict.claim_a/b_source_evidence_id`**: Hard-deleting an `EvidenceItem` cascades deletion to `verification_conflicts` instead of retaining an immutable conflict tombstone.
3. **LLM-Paraphrased Conflict Claims vs Raw Excerpts**: On the `4` `decision_conflict` rows and `2` README-based `ownership_conflict` rows, `claim_a_text` / `claim_b_text` store the AI-reconstructed `KnowledgeItem` statement rather than a verbatim `EvidenceChunk` quote (all verified grounded in underlying chunk text, but the UI renders them in monospace boxes that appear like direct quotes).
4. **Generic `"Page 1"` `location_label` on GitHub Items**: Because GitHub evidence chunks default `page_number = 1`, `VerificationEvidenceRef.location_label` renders `"Page 1"` on GitHub commits and Markdown READMEs rather than commit SHA / file path (exact SHA/path is preserved in `source_url` and `source_external_id`).

---

## 4. Verification Center Provenance Findings

### Full Population Breakdown (`466` Total Cases in PostgreSQL)

| Dimension | `Skill Passport-Siddhesh` (`fa71b2e5`) | Leftover Test Tenants (`62ca67c9` + `44863232`) | Combined DB Total |
| :--- | :---: | :---: | :---: |
| **Total `VerificationCase` rows** | `460` | `6` (`3` + `3`) | **`466`** |
| **Target type = `knowledge_item`** | `460` (`0` relationships) | `6` | `466` |
| **By Status** | `candidate`: `447`, `conflicted`: `12`, `verified`: `1`, `pending_review`: `0`, `unresolved`: `0`, `rejected`: `0` | `verified`: `6` | `candidate`: `447`, `conflicted`: `12`, `verified`: `7` |
| **By Priority** | `critical`: `12`, `high`: `105`, `medium`: `174`, `low`: `169` | `medium`: `6` | `critical`: `12`, `high`: `105`, `medium`: `180`, `low`: `169` |
| **By Verification Category** *(cases with issues)* | `duplicate_findings`: `172`, `missing_evidence`: `23`, `conflicting_evidence`: `12`, `(no_issues)`: `264` *(11 cases have 2 categories)* | `(no_issues)`: `6` | `duplicate_findings`: `172`, `missing_evidence`: `23`, `conflicting_evidence`: `12`, `(no_issues)`: `270` |
| **Cases with `VerificationEvidenceRef`** | `460` (`100%`; `38` with `>=2` refs) | `0` (`0%`) | `460` with / `6` without |
| **Cases with `KnowledgeEvidenceLink` on target** | `460` (`590` links → `520` unique `(ki,ev,chunk)` → `520` refs) | `6` (`6` links, unmaterialized) | `466` with / `0` without |
| **Missing/deleted or cross-project target** | `0` | `0` | **`0`** |
| **Missing/deleted or cross-project `EvidenceItem` / `EvidenceChunk` ref** | `0` | N/A (`0` refs) | **`0`** |
| **`VerificationEvidenceRef.excerpt` verbatim match in `EvidenceChunk`** | **`520 / 520` (`100%` `exact_in_chunk`)** | N/A (`0` refs; `0` chunks) | `520 / 520` |
| **Cases with `acl_scope != 'project_members'`** | `0` | `0` | `0` |
| **Cases missing `KnowledgeExtractionRun` metadata** | `0` (`460/460` link to `357bfc02`, `qwen3:8b`, `is_synthetic=False`) | `6` (`extraction_run_id = NULL`) | `6` |
| **Cases missing both issues & recommendation explanation** | `0` | `6` | `6` |
| **`VerificationFindingRevision` / `ReviewEvent`** | `460` revisions / `2` review events (assign + approve on `003331fd`) | `0` / `0` | `460` / `2` |

### Key Findings from Population + 26-Record Audit
- **Real Project Integrity**: All `460` cases on `Skill Passport-Siddhesh` trace cleanly to real synced GitHub commits (`50`), documentation READMEs (`20`), or Pull Request `#1` (`1`), extracted by real Ollama `qwen3:8b` run `357bfc02-454c-4a44-9d8b-e6ab50a70fcb` (`463` chunks evaluated, `1,212` candidates generated, `134` ungrounded rejected, `460` persisted; status `partially_completed` due to `LLM_TIMEOUT` on `25` items).
- **`missing_evidence` Category Meaning**: All `23` `missing_evidence` issues on `Skill Passport-Siddhesh` actually have `1` valid `VerificationEvidenceRef`; they were flagged because `CompletenessEvaluator` scored their evidence as `sparse` / tangentially related (e.g., `7dad3155`, `"Role-Based Access Matrix"` citing a Markdown table header row).
- **`priority_reason` Count Bug**: Conflicted cases (e.g., `556d1785`, `5c58f483`, `621bbd60`) store `"Contradictory findings detected across sources (0 conflict(s))"` in `machine_assessment_json.priority_reason` despite having active conflicts.
- **Leftover Synthetic Test Tenants**: `Handover Test Project fa1a46` (`62ca67c9`) and `Handover Test Project 7cbb1d` (`44863232`) contain `6` synthetic `verified` cases with blank `VerificationCase.title`/`current_claim`, backed by `KnowledgeItem` fixtures (`"Adopt Microservices & FastAPI"`, `"PostgreSQL as Canonical Store"`, `"Q4 Handover Milestone"`) and fake `arch_doc.pdf` rows (`2048` bytes, `storage_object_key=NULL`, `0` `EvidenceContent`, `0` `EvidenceChunk`).

---

## 5. Conflict Management Provenance Findings (100% Population — 28/28 Audited)

All **28** persisted `VerificationConflict` rows belong to `Skill Passport-Siddhesh` (`fa71b2e5-140e-4040-b1ea-4ac6036382b9`) and remain `unresolved`:

1. **Lineage & Referential Integrity (`28/28` Valid)**:
   - `28/28` reference valid, same-project `EvidenceItem` and `EvidenceChunk` rows for both Side A and Side B (`0` broken refs, `0` cross-project refs).
   - `28/28` have non-null `related_finding_id`, `side_a_source_title`, `side_b_source_title`, `explanation`, and `source_url` pointing to `shubham392007-sketch/HackMatrix-5.0-MISC02`.
2. **Classification Validity (`28/28` = `D. Potentially Misclassified`)**:
   - **4 `decision_conflict` rows (`c3353875`, `5f172a9d`, `4e6d7c62`, `000e354a`)**: All pair `skillpassport-powered-by-growthlens/README.md` (`"JWT auth, RBAC & Fernet security implementation"`) against non-authentication occurrences of the word `"session"` (`fix(db)... in session.py`, `"session reports"`, `"JSONL session"`, and `"API session default"` in `.agents/skills/cavecrew/README.md`). Direct chunk inspection verified that every Side A and Side B claim is genuinely grounded in its underlying README/commit chunk (paraphrased by `qwen3:8b`), **but** none represents an authentication architecture contradiction.
   - **24 `ownership_conflict` rows**:
     - **24/24 (`100%`)** involve at least one Git **merge commit** (`parent_count >= 2` / `Merge origin/...`).
     - **22/24** compare sequential commits on the same **`main`** branch (`14/24` with verified direct or transitive Git parent-SHA ancestry).
     - **2/24** (`f40f3492`, `4e723953`) compare `LEARN_AND_GROW_README.md` against merge commit `976d5f12`.
     - **Symmetric & Multi-Case Duplication**: The `24` rows collapse into only **`10` unique evidence pairs**, duplicated symmetrically (A↔B) and across multiple findings extracted from the same commit (e.g., `2a5d1927` vs `f39285ec` appears **4 times**; `f39285ec` vs `dc3a4f54` appears **4 times**).
     - Note: Post-Stage-7 DEF-08 already upgraded `AdvancedContradictionEvaluator` so new runs produce `0` false positives on these `460` cases; these `28` historical rows remain persisted awaiting explicit human triage in Conflict Management (never silently deleted).

---

## 6. Original Source Authenticity

| Source Layer | Verified State | Authenticity Distinction |
| :--- | :--- | :--- |
| **Connected GitHub Repository (`Skill Passport-Siddhesh`)** | `SourceConnection` `8cb117c8` (`GitHub (@shubham392007-sketch)`, `active`, `delegated_per_user`) + `ProjectSourceMapping` `04d731aa` (`shubham392007-sketch/HackMatrix-5.0-MISC02`, `public`, `active`) + `SourceAccessPolicy` `e458c6cf` (`project_members_verified`, `verified`) | **Original evidence preserved in local Evidence Center.** Outbound live GitHub HTTP verification was **NOT** executed during this read-only audit (`NOT VERIFIED` externally). |
| **GitHub Commits (`50` items)** | `50/50` have 40-char commit `sha`, `parent_shas`, `branches`, `repository`, `source_url`, `source_author_identity`, 64-char SHA-256 `content_hash`, `EvidenceContent`, and `EvidenceChunk`. | **Local Evidence Center copy verified.** Multi-hop parent-SHA graph forms a consistent real Git DAG on `main`. |
| **GitHub PR (`1`) & Docs (`20`) & Repo (`1`)** | `22/22` have `source_url` (`.../pull/1`, `.../blob/main/...`), 64-char SHA-256 `content_hash`, `EvidenceContent`, `EvidencePageContent`, and `EvidenceChunk`. | **Local Evidence Center copy verified.** External GitHub blob fetch **NOT** executed. |
| **Uploaded Documents (`6` items in leftover test projects)** | `6/6` in `Handover Test Project fa1a46` & `7cbb1d` (`arch_doc.pdf`, `file_size_bytes=2048`, `storage_provider=NULL`, `storage_object_key=NULL`, `0` `EvidenceContent`, `0` `EvidenceChunk`). | **Source reference retained as synthetic test fixture; original file content unavailable / never stored.** |

---

## 7. Hardcoded & Synthetic Data Investigation

Scanned all Verification Center and Conflict Management code paths (`frontend/src/app/verification`, `frontend/src/app/conflicts`, `frontend/src/app/projects/[id]/verification`, `frontend/src/app/projects/[id]/conflicts`, `frontend/src/components/verification/*`, `frontend/src/components/conflicts/*`, `frontend/src/lib/verificationApi.ts`, `frontend/src/lib/conflictsApi.ts`, `frontend/src/lib/api.ts`, and backend services/routes):

- **Active `/verification` (`VerificationCenterWorkspace.tsx`) & `/conflicts` (`ConflictManagementWorkspace.tsx`)**:
  - **ZERO** hardcoded finding arrays, conflict arrays, mock UUIDs, fake GitHub commits, placeholder excerpts, static counts, or `figmaStore` imports.
  - Only acceptable static UI configuration (status badges, category labels, input `placeholder="..."` attributes, workflow action modals).
  - API failures surface explicit error banners/toasts rather than silently falling back to demo data.
- **Deprecated Route `/projects/[id]/conflicts` (`frontend/src/components/verification/ConflictsWorkspace.tsx`)**:
  - Still mounted on `/projects/[id]/conflicts/page.tsx`! While it contains no hardcoded conflict arrays, lines 94–95 silently swallow API errors (`.catch(() => null)`), lines 153 & 157 auto-prefill hardcoded adjudication notes (`"Verified newer repository implementation supersedes previous specification claim."` / `"Harmonized contextual scope across sources."`), and line 184 posts a legacy payload (`resolution_state`, `preferred_claim`) incompatible with current `ResolveConflictRequest` (`resolution_strategy`).
- **Live PostgreSQL Residue**:
  - As detailed in §4, `6` synthetic test `VerificationCase` rows exist in two separate test tenants (`Handover Test Project fa1a46` and `Handover Test Project 7cbb1d`), completely isolated from `Skill Passport-Siddhesh` but still stored in the live database.

---

## 8. Frontend-to-Backend Authenticity & Consistency

Verified directly against live PostgreSQL and host-verified read-only browser screenshots (`final_step_45.png` for `/verification`, `final_step_39.png` for `/conflicts`):

| Check | PostgreSQL Value | Live UI Screenshot Value | Match? |
| :--- | :--- | :--- | :---: |
| `/verification` Total / Statuses (`Skill Passport-Siddhesh`) | `460` total (`447` candidate, `0` pending, `12` conflicted, `0` unresolved, `1` verified, `0` rejected) | `460 findings matching filters`; `447 / 0 / 12 / 0 / 1 / 0` (`final_step_45.png`) | **Exact Match** |
| `/verification` Item #1 Detail (`003331fd`) | `Implement Context-Aware Product Help`, `decisions_rationale`, `verified`, `v1`, `medium`, claim matches verbatim | Identical title, badge, version, priority, claim, assigned reviewer (`final_step_45.png`) | **Exact Match** |
| `/conflicts` Total / States / Categories | `28` total (`28` open/unresolved, `0` investigating/awaiting/resolved/reopened; `24` ownership, `4` decisions; `0` critical, `4` high, `24` medium) | `28 / 28 / 0 / 0 / 0 / 0`; `All 28`, `Ownership 24`, `Decisions 4` (`final_step_39.png`) | **Exact Match** |
| `/conflicts` Item #1 (`4e723953`) | `ownership_conflict`, `medium`, `unresolved`, Side A `976d5f12` vs Side B `File-by-File Inventory Owner`, `created_at = 2026-11-17T21:41:34Z` (`18/11/2026 03:11:34` IST) | Identical heading, badges, explanation, sides, and timestamp (`final_step_39.png`) | **Exact Match** |

### Confirmed UI / Backend Mismatches (`4`)
1. **`UI-01` (MEDIUM)**: `/projects/[id]/conflicts` mounts deprecated `ConflictsWorkspace.tsx` with silent `.catch(() => null)`, hardcoded pre-filled adjudication notes, and incompatible resolve payload schema.
2. **`UI-02` (LOW)**: `ConflictDashboardBar.tsx` (L146–L149) appends hardcoded `"critical"` to `attention_required_count` (`28`), displaying `"28 critical"` when `critical_priority = 0` (`final_step_39.png`).
3. **`UI-03` (LOW)**: `ConflictInvestigationWorkspace.tsx` (L438) deep-links to `/verification?case_id=<uuid>`, but `VerificationCenterWorkspace.tsx` never reads `useSearchParams().get("case_id")`. Additionally, `/projects/[id]/verification` and `/projects/[id]/conflicts` ignore the `[id]` path parameter and rely solely on `LiveAppContext.activeProject`.
4. **`UI-04` (LOW)**: `VerificationCenterWorkspace` (`final_step_45.png`) displays `"Finding is verified by automated checks: evidence is complete, fresh, and corroborated..."` on single-source (`Corroboration: Single Source`) findings; `priority_reason` displays `(0 conflict(s))` on conflicted cases; and GitHub items display `location_label = "Page 1"`.

---

## 9. Security & Source-Level ACL Findings

- **Live Project State (`Skill Passport-Siddhesh`)**: All `72` evidence items have `acl_scope = 'project_members'` under `SourceAccessPolicy` `e458c6cf` (`visibility_policy = 'project_members_verified'`, `sync_permission_status = 'verified'`, `provider_visibility = 'public'`). Therefore, **0 live evidence items are currently restricted**, and **no live ACL violation occurs on `Skill Passport-Siddhesh` today**.
- **Confirmed Code-Level ACL Defects (`4`)** (would leak restricted data on any project containing `acl_scope = 'source_restricted'` evidence):
  1. **`ACL-01` (HIGH)**: `ConflictService.list_conflicts()` (`backend/app/services/conflict_service.py` L66–L113) and `ConflictRepository.list_conflicts()` (`backend/app/repositories/conflict.py` L92–L102) perform **no** `SourceAccessPolicyService` checks — exposing restricted `side_a_source_title`, `side_b_source_title`, `explanation`, and allowing SQL `search` keyword-oracle probing over `claim_a_text` / `claim_b_text`.
  2. **`ACL-02` (HIGH)**: `ConflictService.get_conflict_details()` (`backend/app/services/conflict_service.py` L127–L175) defaults `allow_a = True` / `allow_b = True` when `ev_a is None` / `ev_b is None` (**fail-open**), and even when `allow_a=False` / `allow_b=False` still returns `side_a.title`, `side_b.title`, `explanation`, and `authoritative_claim_text` unredacted.
  3. **`ACL-03` (HIGH)**: `VerificationReviewService.get_case_detail()` (`backend/app/services/verification_review.py` L281, L374–L382) filters `evidence_references` and `conflicts[].side_a/side_b`, **but** returns unfiltered `machine_assessment_json` (including `contradiction_analysis.contradictions[]` with `side_a_title`, `side_a_claim`, `side_b_title`, `side_b_claim`, and `freshness_assessment.superseded_by_record_title`), `conflicts[].explanation`, `issues[].description`, `current_claim`, `original_ai_claim`, and `revisions`.
  4. **`ACL-04` (MEDIUM)**: `VerificationReviewService.list_queue()` (`backend/app/services/verification_review.py` L117–L155) performs **no** per-viewer source ACL filtering on queue titles, claims, or SQL search.
- **Confirmed Passing Controls**: Project-scoped queries (`project_id` filtering on all repo queries), JWT + RBAC route guards (`project.read`, `project.knowledge.review`, `project.manage`), cross-project IDOR isolation, and `VerificationReviewService.get_case_detail` filtering of `evidence_references` and `conflicts[].side_a/side_b` are enforced.

---

## 10. Audit Limitations & Checks Marked `NOT VERIFIED`

1. **External Live GitHub Verification (`NOT VERIFIED`)**: No outbound HTTP requests were sent to `https://github.com/shubham392007-sketch/HackMatrix-5.0-MISC02` during this read-only audit. All GitHub commit SHAs, parent-SHA DAG structure, README content, and SHA-256 content hashes were verified against the local persisted Evidence Center copies only.
2. **Sampled vs Full-Population Verification Finding Inspection**: Population-level referential/excerpt/lineage checks ran across **100% (`466/466`)** of `VerificationCase` rows and **100% (`520/520`)** of `VerificationEvidenceRef` rows, while deep manual claim-to-evidence review covered **`26`** records (`20` stratified real cases + `6` leftover test cases). Sampling does not guarantee semantic perfection of every one of the remaining `440` `qwen3:8b`-extracted summaries.
3. **Runtime Multi-Viewer Restricted-ACL Testing (`NOT VERIFIED` against live DB)**: Because `Skill Passport-Siddhesh` has only `1` active member and `0` restricted evidence items (and creating test records or bypassing auth is forbidden in this audit), `ACL-01`–`ACL-04` were confirmed via deterministic backend code audit rather than live exploitation.
4. **Relationship Targets (`NOT VERIFIED` in live data)**: `0` `KnowledgeRelationship` rows exist in PostgreSQL (`knowledge_relationships = 0`), so the `relationship` branch of `VerificationCase` provenance could only be verified by code inspection, not live persisted rows.

---

## 11. Final Verdict

### **`VERIFIED WITH LIMITATIONS`**

- **Genuine Core Data**: On the active project (`Skill Passport-Siddhesh`), all `460` Verification Center findings and all `28` Conflict Management records trace cleanly to genuine persisted GitHub evidence (`520/520` verbatim `exact_in_chunk` excerpts, real `qwen3:8b` extraction run `357bfc02`), and the active `/verification` and `/conflicts` pages render live backend data with zero mock fallbacks.
- **Material Limitations Requiring Remediation (see [EVIDENCE_PROVENANCE_REMEDIATION_PLAN.md](EVIDENCE_PROVENANCE_REMEDIATION_PLAN.md))**:
  1. All `28/28` existing conflicts are `Potentially Misclassified` legacy pre-DEF-08 artifacts (plus symmetric duplicates) awaiting explicit human triage.
  2. `6` orphaned synthetic test `VerificationCase` rows remain persisted in `2` separate test tenants in the live PostgreSQL database.
  3. `4` confirmed backend source-ACL gaps (`ACL-01`–`ACL-04`) must be closed before onboarding private/restricted external sources.
  4. `4` frontend/backend consistency defects (`UI-01`–`UI-04`) should be resolved (especially replacing legacy `ConflictsWorkspace.tsx` on `/projects/[id]/conflicts`).
