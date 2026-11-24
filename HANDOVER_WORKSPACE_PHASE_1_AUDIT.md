# HANDOVER WORKSPACE — PHASE 1 AUDIT & REFINEMENT SPECIFICATION
## Visual Hierarchy, Header, Navigation & Workspace Composition

**Document Version:** 1.0.0  
**Status:** Audit Completed & Approved for Implementation  
**Target Module:** Handover Workspace (`/handover`, `/handovers/[id]`)

---

## 1. Executive Summary & Product Mission

**The Handover** is an Intelligent Project Knowledge Reconstruction and Handover Platform designed to prevent critical organizational knowledge from leaving with people. The platform operates on the canonical workflow:
```text
CONNECT ──▶ RECONSTRUCT ──▶ VERIFY ──▶ REVIEW ──▶ HANDOVER
```

The Handover Workspace is the definitive delivery environment of the platform. It must communicate three core truths with immediate clarity and calm enterprise authority:
1. **What knowledge has been reconstructed?** (Structured coverage across the 8 canonical knowledge domains).
2. **What knowledge has been verified and what still requires attention?** (Clear, unmistakable distinction between human-verified findings and pending candidate items).
3. **How ready is the handover for approval and transfer?** (Multi-dimensional operational readiness assessment vs. epistemic verification gates).

---

## 2. Existing Architecture & Component Map

### 2.1 Route & Entry Point Hierarchy
- **Primary Route**: `/handover` (`frontend/src/app/handover/page.tsx`)
  - Renders `<HandoversPage view="workspace" />`.
- **Detail Route**: `/handovers/[id]` (`frontend/src/app/handovers/[id]/page.tsx`)
  - Delegates to `HandoverDetailPage` which renders `<HandoverWorkspace id={handoverId} initialTab="overview" />`.
- **Canonical Tab Destinations**:
  - `overview`: `/handovers/[id]` (Project Overview & Strategic Context)
  - `readiness`: `/handovers/[id]?tab=readiness` (Readiness Intelligence Panel)
  - `checklists`: `/handovers/[id]?tab=checklists` (Transition Checklists Panel)
  - `decisions`: `/handovers/[id]?tab=decisions` (Canonical Domain 2)
  - `architecture`: `/handovers/[id]?tab=architecture` (Canonical Domain 3)
  - `tasks`: `/handovers/[id]?tab=tasks` (Canonical Domain 4)
  - `responsibilities`: `/handovers/[id]?tab=responsibilities` (Canonical Domain 5)
  - `dependencies`: `/handovers/[id]?tab=dependencies` (Canonical Domain 6)
  - `risks`: `/handovers/[id]?tab=risks` (Canonical Domain 7)
  - `operations`: `/handovers/[id]?tab=operations` (Canonical Domain 8)
  - `evidence`: `/handovers/[id]?tab=evidence` (Canonical Evidence Provenance Table)
  - `review`: `/handovers/[id]/review` (Sign-Off & Approval Panel)
  - `report`: `/handovers/[id]/report` (Formal Dossier / Report)

### 2.2 Component Hierarchy & Data Flow
```text
frontend/src/components/figma-pages/HandoversPage.tsx
├── HandoversPage (view="workspace")
│   └── HandoverWorkspace ({ id, initialTab })
│       └── HandoverLayout ({ id, tab, children })
│           ├── Header Card (Identity, Metadata, Actions, Verified Ring, Readiness)
│           ├── Lifecycle Stepper Tracker (STAGE_LABELS 6-step progress)
│           ├── Package Version & Immutable SHA-256 Footer
│           ├── Workspace Tabs Navigation (H_TABS 13-tab strip)
│           ├── Tab Content Container (children)
│           │   ├── CanonicalSectionPanel (Domain 1: Project Overview & Context)
│           │   ├── ReadinessIntelligencePanel (Tab: readiness)
│           │   ├── TransitionChecklistsPanel (Tab: checklists)
│           │   ├── ResponsibilityTransferPanel (Tab: responsibilities)
│           │   ├── SignoffApprovalPanel (Tab: review)
│           │   ├── CanonicalEvidenceTable (Tab: evidence)
│           │   └── CanonicalSectionPanel (Domains 2–8)
│           └── Edit Handover Details Modal
└── frontend/src/components/handover/CanonicalSectionView.tsx
    ├── Contribution, Drafting & Epistemic Notice Bar
    ├── Section Narrative Summary Card
    └── Domain 1 Overview & Strategic Context Body
```

### 2.3 Authoritative Data Sources
- **Handover Case**: `api.handover.listCases(projectId)` & `useHandover(id)` → status, code (`HO-1042`), scope, incoming/outgoing owners, due dates.
- **Package Versions**: `api.handover.getVersions(projectId, caseId)` → version number, immutable SHA-256 hash, assembly timestamp.
- **Eight-Domain Sections**: `api.handover.getVersionSections(projectId, caseId, versionId)` → epistemic summary (`human_verified_included`, `pending_verification`, `unresolved_conflicts`), 8 section items, narratives.
- **Readiness Intelligence**: `api.handover.getReadiness(projectId, caseId, versionId)` → composite score (e.g. 87/100), 8 category evaluations, blocker count, warning count, approval eligibility gates.

---

## 3. Audit Findings: Identified Deficiencies & Opportunities

### 3.1 Header Visual Chaos
- **Flat badge soup**: The top row bunches together `h.code`, `StatusBadge`, `HandoverType`, `RoleBadge`, `PackageVersion`, and `ReadinessPill` in an undifferentiated wrap.
- **Diminished project title**: The project title and handover scope lack clear dominance and hierarchy.
- **Unstructured action row**: 5 to 6 button actions (`Previous`, `Edit Details`, `Refresh Draft`, `Ask Assistant`, `Sign-Off & Approval`, `Report`) sit in an arbitrary array with equal or competing visual weight. The critical primary action (**Sign-Off & Approval**) does not stand out clearly as the primary milestone action.
- **Unclear verified knowledge ring**: The 56px SVG ring displays `verifiedCount / totalCandidates` (e.g. 0% when 0 verified and 119 pending) but lacks explicit explanation of the epistemic boundary.

### 3.2 Readiness Score (87/100) vs. Zero Verified Findings (0/119)
- **The Core Paradox**: Users are puzzled seeing **Readiness 87/100** next to **0 Verified findings**.
- **Backend Ground Truth**: Inspection of `HandoverReadinessEngine` (`backend/app/services/handover_readiness.py`) reveals readiness is a weighted multi-dimensional composite across 8 categories:
  1. Evidence Coverage (15%)
  2. Verification Completeness (20%)
  3. Conflict Resolution (15%)
  4. Knowledge Freshness (10%)
  5. Relationship Validation (10%)
  6. Responsibility Coverage (15%)
  7. Risk Assessment (5%)
  8. Dependency Mapping (10%)
- If evidence is 100% cited, conflicts are 0, checklists are complete, and ownership is mapped, the weighted sum reaches **87/100** even with 0% verification completeness ($0 \times 0.20 = 0$).
- **Crucial Rule**: The backend enforces `verification_gate_passed = (total_kis == 0) or (ver_cov_pct >= 50 and len(verified_kis) > 0)` for final sign-off eligibility. High readiness does **not** allow approval without verification.
- **UI Flaw**: The interface failed to explain this distinction, causing confusion. An informative explanatory popover/tooltip must make this crystal clear.

### 3.3 Lifecycle Tracker Presentation
- Rendered as 6 thin horizontal bars (`h-1.5 rounded-full`) without connected milestones or status icons.
- Stage labels are completely hidden on mobile/tablet (`hidden sm:block`), leaving abstract green/blue ticks.
- Does not expose real dates (e.g. creation date, assembly date, approval date) even when known in the case.

### 3.4 Navigation Overload
- 13 tabs arranged in a single unbroken horizontal strip.
- Cluttered with redundant zero counts (`0` across 7 domain tabs) which adds noise rather than signal.
- Lacks semantic grouping into **Overview**, **Knowledge Domains**, **Transfer Activities**, and **Output**.
- Lacks compact sticky positioning on desktop when reading long section content.

### 3.5 Fragmentation of Project Overview & Section Narrative
- `CanonicalSectionView.tsx` currently renders:
  1. Notice bar: "Project Overview & Strategic Context" + buttons.
  2. Separate card: "Section Narrative Summary".
  3. Separate card: "Project Overview & Strategic Context" with project background, metadata list, and focus areas.
  4. Separate card: "Epistemic Integrity Gate".
- This creates 3 stacked cards with duplicate titles and disjointed controls.

---

## 4. Refinement Implementation Plan

### Phase 1.1: Handover Header Redesign (`HandoverLayout`)
1. **Visual Grouping**:
   - **Top Metadata Row**: Handover ID code pill (`HO-1042`), lifecycle status badge, handover role type badge, package version badge (`v1 (Current)`), and interactive readiness score pill with explanatory tooltip.
   - **Dominant Title Area**: Bold, clean project title (24–28px font), subtle scope subtitle, and perspective role indicator.
   - **Transfer Corridor**: Clean outgoing → incoming participant card row with avatars, role labels, last updated timestamp, and target handover due date.
2. **Action Hierarchy**:
   - **Primary Action**: `Sign-Off & Approval` (prominent blue CTA with shield icon, high contrast).
   - **Secondary Actions**: `Ask Assistant` and `Edit Details`.
   - **Tertiary Actions**: `Refresh Draft` and `Report`.
   - Responsive overflow menu on tablet/mobile so primary action is never obstructed.
3. **Verified Knowledge vs. Readiness Clarity**:
   - Verified findings ring chart enhanced with explicit breakdown: `X verified` (teal) · `Y pending verification` (amber).
   - Tooltip explaining: *“Readiness evaluates operational transfer completion across 8 dimensions. Verification completeness is an independent gate required before handover approval.”*

### Phase 1.2: Lifecycle Stepper Redesign
1. Six canonical stages: `Draft` → `Verification` → `Manager Review` → `Approved` → `Published` → `Acknowledged`.
2. Connected horizontal stepper with milestone dots, stage numbers/checkmarks:
   - Completed stages: Verified teal (`#299B80`) with checkmark.
   - Active stage: Primary blue (`#315FBA`) with active glow.
   - Upcoming stages: Subtle grey (`#D9E1F0`) with muted text.
3. Responsive behavior with compact milestone badges on tablet/mobile that never clip or collide.

### Phase 1.3: Structured Workspace Navigation
1. Semantic grouping:
   - **Overview**: Overview, Readiness
   - **Knowledge**: Decisions, Architecture, Tasks & Work, Ownership, Dependencies, Risks & Issues, Operations, Evidence
   - **Transfer**: Checklists, Sign-Off & Approval
   - **Output**: Report
2. Clean segmented/tab navigation with subtle count indicators that hide when 0 (unless indicating outstanding blockers/checklists).
3. Smooth responsive horizontal scroll with gradient indicators and sticky positioning on desktop.

### Phase 1.4: Unified Project Overview & Strategic Context
1. In `CanonicalSectionView.tsx`, consolidate the fragmented notice bar, narrative summary card, and domain 1 overview into a single, cohesive **Project Overview & Strategic Context** section.
2. Unified card hierarchy:
   - Section header with title, scope badges, and dual action buttons (`Contribute Missing Context`, `Draft / Edit Section Narrative`).
   - Section metadata summary grid (Project status, Start/Target date, Package snapshot, Scope areas).
   - Authoritative Section Narrative area (rendered Markdown with edit shortcut, or high-quality empty state with guidance to draft the strategic summary).
   - Preserved epistemic breakdown and integrity callout.

### Phase 1.5: Verification, Quality Assurance & Documentation
1. Run TypeScript type checks (`tsc --noEmit`).
2. Run test suites (`vitest run`).
3. Generate:
   - `HANDOVER_WORKSPACE_PHASE_1_IMPLEMENTATION_REPORT.md`
   - `HANDOVER_WORKSPACE_PHASE_1_QA_REPORT.md`

---

## 5. Design Tokens & Constraints

| Token Name | Hex Code | Purpose |
|:---|:---|:---|
| **Canvas** | `#F6F8FC` | Main application background |
| **Surface** | `#FFFFFF` | Card surfaces, containers |
| **Deep Navy** | `#203653` | Primary headings, titles |
| **Primary Blue** | `#315FBA` | Primary actions, active navigation |
| **Brand Dark** | `#284F9C` | Primary hover states |
| **Verified Teal** | `#299B80` | Verified indicators, completed stages |
| **AI Indigo** | `#8B78C9` | AI/synthesized metadata badges |
| **Pending Amber** | `#D39B43` | Pending review, warning alerts |
| **Line Border** | `#D9E1F0` | Structural card and element borders |
| **Muted Text** | `#718096` | Subtitles, helper text |

**Absolute Constraints**:
- Zero fabrication: no mock findings, synthetic metrics, or fake dates.
- Zero functional regressions: preserve all event handlers, routes, modals, and API calls.
