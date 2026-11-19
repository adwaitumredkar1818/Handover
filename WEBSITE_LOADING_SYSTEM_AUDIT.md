# Handover — Complete Website-Wide Loading System, Processing States & User Feedback Audit

**Document Version:** 1.0.0  
**Status:** Audit Completed  
**Scope:** Entire Handover Web Application (Next.js 15, React 19, TypeScript, Tailwind CSS, FastAPI Backend)  
**Author:** Principal Frontend Architect, UX Engineer & Performance Lead  

---

## 1. Executive Summary & Audit Scope

This audit provides an exhaustive evaluation of all asynchronous data lifecycles, background tasks, user feedback mechanisms, and loading states across **The Handover** application. 

Currently, asynchronous states are fragmented across the codebase:
- Over 390 instances of ad-hoc `isLoading`, `loading`, `isSubmitting`, and `isExtracting` boolean flags exist across components without a centralized state contract.
- Loading indicators are visually inconsistent, ranging from Lucide `RefreshCw` spin animations in `EvidenceCenterView.tsx`, `Loader2` in `FindingInspectionPanel.tsx`, spinning `Bot` icons in `AssistantWorkspaceView.tsx`, to plain unstyled text placeholders (`"Loading threads..."`, `"Loading conversation history..."`).
- Crucial data-driven views (Dashboard metrics, Handover dossier cases, Knowledge Intelligence graphs) momentarily render zeroed-out numbers (`0%`, `0 items`) or blank canvases while initial queries are in-flight, creating severe layout shifts and perceived instability.
- Route transitions lack top navigation progress bars, leaving users unsure if a link click was registered.
- User-triggered actions (document uploads, source synchronizations, verification actions) lack standardized button loaders with stable dimensions and explicit duplicate submission guards.

This audit establishes the baseline facts required to design and implement a unified, organic, accessible, and high-performance loading ecosystem under the design ethos **"ORGANIC INTELLIGENCE IN MOTION"**.

---

## 2. Current Loading Architecture & Existing Components

### 2.1 Existing Loading Assets
1. **`BrandLoadingScreen.tsx`** (`frontend/src/components/brand/`):
   - Full-screen branded loader featuring the Handover logo, subtle ambient blue radial glow, traveling synaptic light line, and dynamic status message.
   - *Current limitation*: Rendered inside `AppLayout.tsx`'s `<main>` element rather than at the root overlay level, causing underlying TopNav/Sidebar elements to flash or mount prematurely.
2. **Ad-hoc Lucide Spinners**:
   - `RefreshCw` with `animate-spin` used in `EvidenceCenterView.tsx`, `ConflictsWorkspace.tsx`.
   - `Loader2` with `animate-spin` used in `FindingInspectionPanel.tsx`, `DashboardAttentionList.tsx`.
   - `Bot` with `animate-spin` used in `AssistantWorkspaceView.tsx`.
3. **Ad-hoc Text Placeholders**:
   - `<div>Loading threads...</div>` in `AssistantWorkspaceView.tsx:766`.
   - `<div>Loading conversation history...</div>` in `AssistantWorkspaceView.tsx:861`.
   - `<div>Loading project contradictions...</div>` in `ConflictsWorkspace.tsx:572`.
4. **Ad-hoc Button Label Swaps**:
   - `"Adding..."` in `AddMemberModal.tsx`.
   - `"Ingesting & Encrypting..."` in `UploadDocumentModal.tsx`.
   - `"Assembling Package..."` in `HandoverWorkspaceView.tsx`.
   - *Limitation*: Shifts button width when text changes, risking mis-clicks, and does not provide an integrated spinner or accessible ARIA busy attributes.

---

## 3. Comprehensive Defect Analysis by Route & Module

| Route / Module | Current Loading Behavior | UX Defect / Problem | Proposed Centralized Pattern |
| :--- | :--- | :--- | :--- |
| **App Root & Auth (`/`)** | `BrandLoadingScreen` rendered inside `<main>` of `AppLayout`. | TopNav mounts underneath; layout shift on auth resolve. | `AppLoadingScreen` mounted at root layout level with smooth exit fade and organic particles. |
| **Route Navigation** | Next.js App Router default navigation without top feedback. | Screen feels frozen during data-heavy route changes (`/evidence` &rarr; `/knowledge`). | `PageLoadingBar`: 2.5px gradient bar at viewport top with smooth cubic-bezier easing. |
| **Dashboard (`/dashboard`)** | `DashboardRouter.tsx` ignores `isLoadingOverview`, rendering 0 metrics before data arrives. | Layout flash; metrics show `0%`, `0 items` for 300-800ms. | `PageSkeleton` + `CardSkeleton` cluster preserving 4-metric KPI grid and activity stream. |
| **Evidence Center (`/evidence`)** | Panel A shows "No Sources", Panel B shows spinning `RefreshCw`, Panel C has no loading state for detail inspection. | Fragmented spinners; sudden layout jump when evidence rows populate. | `TableSkeleton` for Panel B; `ListSkeleton` for Panel A; `CardSkeleton` for Panel C detail inspection. |
| **Document Upload Modal** | Button swaps to `"Ingesting & Encrypting..."` with simple disabled boolean. | No progress breakdown between upload bytes and backend OCR/vector indexing. | `UploadProgress`: Stage-based timeline (`SELECTED` &rarr; `UPLOADING` &rarr; `EXTRACTING` &rarr; `INDEXING` &rarr; `COMPLETED`). |
| **Knowledge Intelligence (`/knowledge`)** | Canvas renders empty grey area when `loading === true` and `nodes.length === 0`. | Screen looks empty or broken rather than loading. | `GraphSkeleton`: Central node with placeholder orbits, subtle connection lines, and contextual text. |
| **Relationship Explorer (`/relationships`)** | Canvas initial layout calculation runs synchronously; no placeholder shown during ELK layout. | Freezes momentarily on 50+ node graphs. | `GraphSkeleton` + `SectionLoader` with status `"Computing hierarchical layout..."`. |
| **Knowledge Assistant (`/assistant`)** | Raw text `"Loading threads..."` and `"Loading conversation history..."`; spinning `Bot` icon. | Primitive text feedback; no message skeleton; spinning bot icon is visually jarring. | `ListSkeleton` for threads; message skeleton with simulated bubble heights; organic `AIAssistantThinking` state. |
| **Handover Dossier (`/handover`)** | Renders 0 active cases, 0% readiness while `loadHandoverData` runs. | Misleads user into thinking no handover cases exist. | `PageSkeleton` with 4-card metric placeholder and dossier section skeletons. |
| **Handover Generation** | Modal/button switches to `"Assembling..."` without stage visibility. | User cannot tell whether AI is extracting or packaging. | `AILoadingState`: Multi-stage organic pulse (`Aggregating Evidence` &rarr; `Evaluating Decisions` &rarr; `Compiling Dossier`). |
| **Verification Center (`/verification`)** | Panel shows `Loader2` spinner; summary cards render empty counts. | Disconnected visual indicators; card count layout shift. | `TableSkeleton` for review queue; metric card pulse skeletons; `ButtonLoader` for Approve/Reject. |
| **Settings & Team (`/settings`, `/team`)** | Member list table flashes empty state before query resolves. | Inconsistent table loading; button loaders absent on invite. | `TableSkeleton` + `FormSkeleton` + `ButtonLoader`. |

---

## 4. Asynchronous Operation Mapping

The application conducts 14 distinct categories of asynchronous operations:

1. **Session & Auth Restoration**: `api.auth.me()`, `api.auth.refreshToken()`, Supabase token exchange.
2. **Project & Workspace Initialization**: `api.projects.list()`, `api.projects.get()`, `api.projects.getOverview()`.
3. **Source Connections**: `api.sources.listOrgConnections()`, `api.sources.connectSource()`, OAuth callbacks.
4. **Source Synchronization**: `api.sources.syncMapping()`, polling job status.
5. **Document Upload & OCR**: `api.evidence.upload()`, multipart streaming, GLM-OCR background queue.
6. **Evidence Library Retrieval & Filtering**: `api.evidence.list()`, `api.evidence.get()`, full-text FTS search.
7. **Knowledge Reconstruction & Extraction**: `api.knowledgeIntelligence.listFindings()`, Qwen3 8B semantic extraction.
8. **Knowledge Graph Queries & Layout**: `api.knowledgeIntelligence.getGraph()`, ELK layered layout computation.
9. **Verification Queue & Human Actions**: `api.verification.listCases()`, `verifyItem()`, `rejectItem()`, `bulkVerify()`.
10. **Contradiction Detection**: `api.conflicts.detect()`, `resolveConflict()`.
11. **Assistant Hybrid RAG Inquiries**: `api.assistant.ask()`, SSE event stream, ChromaDB vector + PostgreSQL retrieval.
12. **Handover Dossier Compilation**: `api.handover.createCase()`, `api.handover.compile()`, PDF generation.
13. **Member Management & Invitations**: `api.members.add()`, `api.invitations.create()`.
14. **Settings & Profile Mutations**: `api.organisations.update()`, `api.users.updateProfile()`.

---

## 5. Technical Risks & Constraints

1. **No Fake Progress**: Progress indicators must be truthful. If an operation does not emit byte-level progress (e.g. backend LLM reconstruction), the UI must display a truthful indeterminate state with the active stage name rather than a synthetic incrementing percentage timer.
2. **No Layout Shift (CLS)**: Skeletons must strictly adhere to the exact padding, aspect ratio, row height, and typography line-heights of the rendered components to achieve zero Cumulative Layout Shift.
3. **Double-Click & Concurrent Mutation Guard**: Action buttons must disable pointer events immediately upon click while maintaining layout dimensions to prevent accidental duplicate API calls.
4. **Reduced Motion Accessibility**: Users with `prefers-reduced-motion: reduce` must receive static contrast-compliant indicators and opacity transitions rather than pulsing gradients or particle physics.
5. **SSR Hydration Safety**: All loading states must initialize safely without client/server mismatch errors (no conditional `typeof window !== 'undefined'` divergence before mount).

---

## 6. Proposed Shared Component Architecture

To centralize all loading patterns, we propose establishing a dedicated `frontend/src/components/loading/` package:

```text
frontend/src/components/loading/
├── AppLoadingScreen.tsx      # Type 1: Full-Screen Application Bootstrap
├── PageLoadingBar.tsx        # Type 7: Top 2.5px Gradient Route Transition Bar
├── PageSkeleton.tsx          # Type 2: Full-Page Layout Skeleton
├── CardSkeleton.tsx          # Type 2: KPI & Metric Card Skeleton
├── TableSkeleton.tsx         # Type 2: Data Table & Evidence Row Skeleton
├── ListSkeleton.tsx          # Type 2: Sidebar, Queue & Feed Item Skeleton
├── FormSkeleton.tsx          # Type 2: Settings & Profile Form Skeleton
├── GraphSkeleton.tsx         # Type 8: Knowledge Graph & Flowchart Skeleton
├── SectionLoader.tsx         # Type 3: Inline Panel & Widget Loader
├── ButtonLoader.tsx          # Type 4: Unified Button Loading with Stable Width
├── AILoadingState.tsx        # Type 5: Organic Connected-Node AI Processing Experience
├── AIAssistantThinking.tsx   # Type 9: Dedicated Assistant Thinking & Retrieval State
├── UploadProgress.tsx        # Type 6: Document Upload & Multi-Stage Processing Feedback
├── EmptyState.tsx            # Type 10: Standardized Zero-Data Recovery State
├── ErrorState.tsx            # Type 10: Standardized Failure & Retry State
├── SuccessState.tsx          # Type 10: Standardized Completion & Confirmation State
├── LoadingBoundary.tsx       # Type 10: Declarative Loading/Error/Data Wrapper
└── index.ts                  # Public Barrels Export
```

Accompanied by shared hooks in `frontend/src/hooks/`:
- `useLoadingState.ts`: Manages multi-state lifecycle (`idle`, `loading`, `success`, `error`, `cancelled`).
- `useOperationStatus.ts`: Tracks async operations with timeout protection and retry callbacks.
- `useProgressState.ts`: Handles deterministic vs indeterminate stage progress tracking.

---

## 7. Audit Sign-off

The repository audit is complete. No application code has been altered during this audit phase. We are ready to proceed with authoring the Architecture Specification, State Inventory, and executing the centralized implementation.
