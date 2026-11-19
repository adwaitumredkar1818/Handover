# Handover — Website-Wide Loading System Architecture Specification

**Document Version:** 1.0.0  
**Design Ethos:** "ORGANIC INTELLIGENCE IN MOTION"  
**Scope:** Core Design System, Component APIs, State Models & Lifecycle Governance  

---

## 1. Architectural Philosophy & Design Tokens

Handover is an **Intelligent Project Knowledge Reconstruction & Handover Platform**. Asynchronous operations within the platform represent the computational transition from fragmented documentation and code into verified, permanent organizational memory.

Loading indicators must never feel like generic third-party spinners or static placeholders. They must reflect **Organic Intelligence in Motion** — clean, disciplined, mathematically grounded, and calm.

### 1.1 Canonical Design Tokens
- **Canvas / Background**: `#F6F8FC`
- **Surface White**: `#FFFFFF`
- **Deep Navy (Brand Primary Text / Structure)**: `#203653`
- **Brand Blue (Active Transition / Primary Action)**: `#315FBA`
- **Verified Teal (Deterministic Verification / Provenance)**: `#299B80`
- **AI Indigo (Semantic Reconstruction / Reasoning)**: `#8B78C9`
- **Amber Warning / Attention**: `#D39B43`
- **Rose Error / Destruction**: `#E05252`
- **Border Subtle**: `#DCE3EB`
- **Border Active**: `#CBD5E1`
- **Skeleton Shimmer**: `linear-gradient(90deg, #F0F4F8 0%, #E2E8F0 50%, #F0F4F8 100%)`

### 1.2 Core Interaction Rules
1. **Zero Cumulative Layout Shift (CLS = 0)**:
   - Skeletons must exactly mirror the bounding box, padding, row height, and border radius of the resolved content.
   - Skeletons must not bounce, stretch, or pop in during data arrival.
2. **Deterministic vs. Indeterminate Truthfulness**:
   - Deterministic progress (file upload bytes) must reflect true network transfer metrics.
   - Indeterminate progress (LLM knowledge extraction, vector embedding, graph clustering) must report the true active stage name (`"Extracting semantic decisions..."`) with a smooth organic pulse rather than a fake increasing percentage.
3. **Double-Submission & Mutation Protection**:
   - When a user triggers an asynchronous mutation, the initiating button immediately enters loading mode, disables pointer events, and maintains its exact pixel width to prevent layout jump and duplicate requests.
4. **Accessible Semantics**:
   - Containers actively loading data must declare `aria-busy="true"` and `role="status"`.
   - Critical status changes must be announced via a polite `aria-live="polite"` region.
   - Skeletons must declare `aria-hidden="true"`.
   - `prefers-reduced-motion: reduce` must disable all pulsing, shimmer translation, and particle animation, substituting high-contrast static indicators.

---

## 2. Centralized State Model & Lifecycle Contract

### 2.1 State Model (`LoadingState`)
```typescript
export type AsyncOperationStatus =
  | "idle"
  | "initializing"
  | "loading"
  | "processing"
  | "uploading"
  | "refreshing"
  | "success"
  | "empty"
  | "error"
  | "cancelled";

export interface OperationState<T = unknown> {
  status: AsyncOperationStatus;
  data: T | null;
  error: Error | string | null;
  stage?: string;
  progressPercent?: number; // 0 - 100, only when deterministic
  startedAt?: number;
  completedAt?: number;
}
```

### 2.2 Lifecycle State Transitions

```text
       ┌───────────────► INITIALIZING ──────────────┐
       │                                            ▼
     IDLE ─────────────► LOADING ────────────────► SUCCESS (or EMPTY)
       │                    │                       ▲
       │                    ├────────► ERROR        │
       │                    │                       │
       │                    └────────► CANCELLED    │
       │                                            │
       └───────────────► UPLOADING ──► PROCESSING ──┘
```

1. **Simple Data Queries**: `IDLE` &rarr; `LOADING` &rarr; `SUCCESS` (or `EMPTY` or `ERROR`).
2. **Background Mutations**: `IDLE` &rarr; `PROCESSING` &rarr; `SUCCESS` (or `ERROR`).
3. **Document Ingestion**: `IDLE` &rarr; `UPLOADING` &rarr; `PROCESSING` (OCR / Chunking) &rarr; `SUCCESS`.
4. **Stale-While-Revalidate**: `SUCCESS` &rarr; `REFRESHING` (data stays visible with subtle corner badge) &rarr; `SUCCESS`.

---

## 3. Ten Canonical Loading Component Specifications

### Type 1: Full-Screen Application Loading (`AppLoadingScreen.tsx`)
- **Usage**: Cold application bootstrap, session restoration, authentication exchange.
- **Visuals**: Centered brand mark with soft floating pulse, ambient `#315FBA` radial glow (0.05 opacity), traveling synaptic light line, brand tagline, and dynamic status message.
- **Exit Motion**: 500ms opacity transition to zero with `pointer-events: none`.

### Type 2: Skeleton Loading Suite
- **`CardSkeleton.tsx`**: KPI cards, metric blocks, small summary widgets.
- **`TableSkeleton.tsx`**: Evidence records, audit logs, team rosters, conflict queues. Configurable row count and column widths.
- **`ListSkeleton.tsx`**: Activity streams, notifications, conversation threads, source lists.
- **`FormSkeleton.tsx`**: Settings pages, user profiles, project configuration forms.
- **`PageSkeleton.tsx`**: Full-page layout skeleton with header, metric grid, and 2-column or 3-panel layout.

### Type 3: Inline Component Loading (`SectionLoader.tsx`)
- **Usage**: Refreshing a single widget, loading evidence details into Panel C, updating graph node details.
- **Visuals**: Preserves parent container dimensions with soft light-blue tint, small organic spinner or synaptic pulse, and contextual text (`"Loading evidence details..."`).

### Type 4: Button & Action Loading (`ButtonLoader.tsx`)
- **Usage**: Every asynchronous button click (`"Create Project"`, `"Add to Project"`, `"Save Changes"`, `"Verify Finding"`).
- **Behavior**:
  - Dynamically measures its own width on render so transitioning to loading state retains the exact pixel width.
  - Replaces icon with a small 14px organic spinner.
  - Updates text (`"Save Changes"` &rarr; `"Saving..."`).
  - Sets `disabled={true}` and `aria-busy="true"`.

### Type 5: AI Processing Experience (`AILoadingState.tsx`)
- **Usage**: Knowledge reconstruction, evidence extraction, AI analysis, finding classification, handover generation.
- **Visuals**: Organic connected-node visualization with 3-5 orbiting synaptic nodes, pulsing central node, indigo/blue glow (`#8B78C9` / `#315FBA`), and a truthful stage timeline:
  1. Evidence Aggregation & Chunking
  2. Syntactic & Architectural Extraction
  3. Knowledge Reconstruction & Cross-Source Correlation
  4. Decision & Dependency Mapping
  5. Dossier Synthesis & Provenance Verification

### Type 6: Document Upload & Multi-Stage Processing (`UploadProgress.tsx`)
- **Usage**: File ingestion modal, repository sync.
- **Visuals**:
  - Distinct byte upload bar (e.g. `1.4 MB / 2.8 MB (50%)`) during active file transmission.
  - Post-upload stage transitions: `Uploaded` &rarr; `AES-256 Envelope Encrypting` &rarr; `OCR Analysis (GLM-OCR)` &rarr; `Chunking & Nomics Embedding` &rarr; `Complete`.
  - Individual file status cards with retry and cancellation options.

### Type 7: Route Navigation Transitions (`PageLoadingBar.tsx`)
- **Usage**: Next.js App Router route transitions.
- **Visuals**: Fixed 2.5px height bar at viewport top (`z-index: 9999`) with gradient `linear-gradient(90deg, #315FBA, #299B80)`.
- **Easing**: Exponential ease-out up to 85% while route is pending, rapid 100% resolve and fade-out upon mount.

### Type 8: Knowledge Graph Loading (`GraphSkeleton.tsx`)
- **Usage**: Relationship Explorer, Knowledge Intelligence Flowcharts, Dependency Graphs.
- **Visuals**: Preserves canvas dimensions. Renders a central project root node surrounded by subtle placeholder nodes and faint dashed bezier connections, overlaid with an ambient status pill: `"Computing knowledge relationships..."`.

### Type 9: Knowledge Assistant Thinking Indicator (`AIAssistantThinking.tsx`)
- **Usage**: Assistant chat stream between user prompt and answer streaming.
- **Visuals**: Organic 3-dot synaptic pulse or breathing intelligence orb, real-time investigation stage indicator (`"QUERY PLANNING & EXPANSION..."` &rarr; `"HYBRID RETRIEVAL (CHROMADB + POSTGRESQL)..."` &rarr; `"SYNTHESIZING ANSWER..."`), and citation placeholders while references are actively resolving.

### Type 10: State Resolution Suite (`EmptyState.tsx`, `ErrorState.tsx`, `SuccessState.tsx`, `LoadingBoundary.tsx`)
- **`EmptyState.tsx`**: Standardized zero-data display with contextual illustration, title, description, and primary CTA button.
- **`ErrorState.tsx`**: Clean, non-leaking error presentation with clear diagnosis, retry button, and support guidance.
- **`SuccessState.tsx`**: Restrained checkmark animation and confirmation message.
- **`LoadingBoundary.tsx`**: Unified wrapper component accepting `isLoading`, `isError`, `isEmpty`, `skeleton`, and `errorFallback` props.

---

## 4. Reusable Custom Hooks Specification

1. **`useLoadingState(initialStatus = "idle")`**:
   - Returns `{ status, isLoading, isSuccess, isError, startLoading, setSuccess, setError, reset }`.
   - Automatically handles unmounted component safety via `useRef`.
2. **`useOperationStatus<T>(asyncFn, options)`**:
   - Wraps any asynchronous promise with automatic error catching, toast dispatch, retry capability, and timeout detection.
3. **`useProgressState(stages: string[])`**:
   - Tracks stage progression through complex multi-step pipelines (e.g. Ingestion, Handover Compilation).

---

## 5. Performance, Accessibility & Hydration Guarantees

1. **Bundle Budget**: All loading components combined must add less than 15 KB gzipped. Zero external animation runtime dependencies; standard Tailwind CSS utility classes and CSS keyframes are utilized.
2. **SSR Compatibility**: All skeletons render valid HTML identical on server and client, ensuring zero hydration mismatches.
3. **Strict Accessible Attributes**:
   - `aria-busy="true"` on loading containers.
   - `aria-live="polite"` for dynamic announcements.
   - `aria-hidden="true"` on decorative skeleton elements.
   - High-contrast fallbacks for all text and icons.
