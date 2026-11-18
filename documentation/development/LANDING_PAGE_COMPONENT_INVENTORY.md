# The Handover — Landing Page Component Inventory

**Document Version**: 2.0  
**Date**: November 18, 2026  
**Location**: `frontend/src/components/landing/`  

---

## 1. Directory Map & Component Hierarchy

```text
frontend/src/components/landing/
├── hooks/
│   └── useReveal.ts                  # Shared IntersectionObserver scroll-reveal hook
├── LandingMockData.ts                # Centralized illustrative Payment Platform sample data
├── LandingPage.tsx                   # Master page orchestrator assembling all 15 sections
├── LandingNav.tsx                    # Top navigation bar with Product & Solutions menus
├── BrandIntro.tsx                    # Canvas 3D particle sphere brand intro transition
├── HeroSection.tsx                   # Hero banner with OrganicScene hero variant
├── SectionDivider.tsx                # Monospaced travelling light beam divider
├── ProblemSection.tsx                # 3 animated problem cards (fragile knowledge)
├── IntroducingSection.tsx            # 3-column architecture progression + assemble canvas
├── HowItWorksSection.tsx             # 5-step interactive workflow stepper
├── EvidenceCenterSection.tsx         # [NEW] Three-panel evidence workspace showcase
├── IntelligenceSection.tsx           # 8-domain knowledge intelligence explorer
├── ExplorerSection.tsx               # Interactive SVG relationship knowledge graph
├── KnowledgeAssistantSection.tsx     # [NEW] Grounded AI assistant chat preview
├── HandoversSection.tsx              # Certified transition dossier with 8-domain breakdown
├── RolesSection.tsx                  # 3 role personas with transmission bridge
├── TrustSection.tsx                  # 4-tier epistemic separation & guarantees
├── FaqSection.tsx                    # 8-item accessible accordion
├── FinalCtaSection.tsx               # Dark continuity CTA with canvas
├── LandingFooter.tsx                 # 5-column deep navy footer
└── index.ts                          # Central barrel export file
```

---

## 2. Component Specifications

### 2.1 Core Utilities & Shared Data

#### `hooks/useReveal.ts`
- **Purpose**: Attaches an IntersectionObserver to a section container to smoothly trigger `.reveal.is-in` CSS animations.
- **Hook Signature**: `useReveal<T extends HTMLElement>(): React.RefObject<T>`
- **Threshold**: `0.12`
- **Dependencies**: React `useEffect`, `useRef`.

#### `LandingMockData.ts`
- **Purpose**: Single source of truth for illustrative mock data to maintain cross-section narrative consistency.
- **Entities**:
  - `PEOPLE`: `outgoing` (Alex Chen), `reviewer` (Jordan Lee), `incoming` (Priya Shah).
  - `PROJECT`: `Payment Platform`, `HO-1042`.
  - `EVIDENCE`: `pr4827`, `proj103`, `dep014`, `slackArch`, `adr007`, `adr012`, `runbook`.
  - `KNOWLEDGE_DOMAINS`: 8 domains with icons, colors, descriptions, sample findings, and counts totaling 58.
  - `WORKFLOW_STEPS`: Connect, Reconstruct, Verify, Review, Handover.
  - `EPISTEMIC_TIERS`: Tiers 1 through 4 with semantic hex tokens.

---

### 2.2 Navigation & Master Orchestrator

#### `LandingPage.tsx`
- **Role**: Root orchestrator component rendered at `/` and `/landing`.
- **Children**: 15 distinct sections separated by `SectionDivider` with monospaced Theme B labels (`SEC_01` through `SEC_11`).
- **Scroll Behavior**: Automatic scroll-to-top reset on initial mount when no URL hash is present.

#### `LandingNav.tsx`
- **Role**: Fixed/sticky navigation header with blurred glass backdrop upon scroll (`scrollY > 12`).
- **Product Menu Items**:
  - Knowledge Intelligence (`#intelligence`)
  - Evidence Center (`#evidence`)
  - Knowledge Explorer (`#explorer`)
  - Knowledge Assistant (`#assistant`)
  - Structured Handovers (`#handovers`)
  - Trust & Governance (`#security`)
- **Solutions Menu Items**:
  - Departing Members (`#roles`)
  - Technical Reviewers (`#roles`)
  - Incoming Successors (`#roles`)
- **Accessibility & UX**:
  - Keyboard Escape listener to dismiss dropdowns and mobile menu.
  - Body scroll lock during active mobile menu.
  - Smooth anchor scrolling via `scrollIntoView`.
  - Authentication-aware CTAs via `useLiveApp()`.

---

### 2.3 Product & Workflow Sections

#### `HeroSection.tsx`
- **Headline**: "People move on. Knowledge shouldn't."
- **Eyebrow**: "INTELLIGENT PROJECT KNOWLEDGE RECONSTRUCTION & HANDOVER PLATFORM"
- **Background Visual**: `OrganicScene` (`variant="hero"`), with contrast masks.
- **Trust Strip**: Connect Your Tools · Reconstruct Knowledge · Human-Verified · Role-Tailored Handovers.

#### `ProblemSection.tsx`
- **Heading**: "Project knowledge is fragile."
- **Failure Modes**:
  1. `Context Lives in Silos` (animated floating tool badges).
  2. `Unwritten Knowledge Walks Out` (decision card with shimmering unrecorded fields).
  3. `Recovery Becomes Slow and Risky` (spinning cycle with unanswerable questions).

#### `IntroducingSection.tsx`
- **Heading**: "One platform to reconstruct, verify, and hand over project knowledge."
- **Canvas Visual**: `OrganicScene` (`variant="assemble"`).
- **Columns**: `01 · Bring It Together` → `02 · Reconstruct & Structure` → `03 · Verify & Handover`.

#### `HowItWorksSection.tsx`
- **Heading**: "From fragmented information to a certified handover."
- **Steps**:
  1. `Connect` (Repo selector preview).
  2. `Reconstruct` (Reconstruction progress bar & item counts).
  3. `Verify` (Human review finding with Verify / Edit / Reject).
  4. `Review` (Technical lead review with 4 domain counts).
  5. `Handover` (AC → PS transition card with progress ring).

#### `EvidenceCenterSection.tsx` (NEW)
- **Heading**: "Every finding traced to its source."
- **Panels**:
  - Panel A (Sources): GitHub, Jira, Slack, Uploaded Documents.
  - Panel B (Library): Filterable table (All, GitHub, Jira, Slack, Docs) with row selection.
  - Panel C (Details): Metadata, snippet, linked findings, and cryptographic SHA-256 hash.
- **Mobile Support**: Tabbed single-panel switcher (Sources | Library | Details).

#### `IntelligenceSection.tsx`
- **Heading**: "Eight domains of project knowledge. One connected intelligence layer."
- **Domains Represented**:
  1. Decisions & Rationale
  2. Technical & Architectural Knowledge
  3. Completed & Unfinished Work
  4. Responsibilities & Ownership
  5. Dependencies
  6. Bugs, Blockers & Risks
  7. Operational Procedures
  8. Historical Discussions & Context
- **Visuals**: `OrganicScene` (`variant="network"`), Raw evidence chunks → Structured finding with AI confidence and verification status.

#### `ExplorerSection.tsx`
- **Heading**: "See how your project knowledge connects."
- **Features**: Interactive SVG canvas, 9 nodes, 11 edges, animated active streams, drawer detail card, related entities traversal, supporting evidence citations.

#### `KnowledgeAssistantSection.tsx` (NEW)
- **Heading**: "Ask your project anything. Get verified answers."
- **Guarantees**: Source Citations, Explicit Uncertainty Disclosure, Source-Level Permissions, Human-Governed Handover Approval.
- **Interactive Queries**:
  - Sample 1: Redis vs Memcached architectural trade-off.
  - Sample 2: Acquirer credential rotation ownership.
  - Sample 3: Database disaster recovery gap (insufficient evidence disclosure).

#### `HandoversSection.tsx`
- **Heading**: "Verified knowledge. Ready for the next person."
- **Dossier Features**: Completion ring (86%), 6 workflow stages, 8-domain breakdown table (58 items), 6 overview blocks, 3 persona packages (Developer, Lead, Leadership).

#### `RolesSection.tsx`
- **Heading**: "A smoother transition for everyone."
- **Personas**:
  1. Departing Member (Verification queue preview).
  2. Technical Reviewer (Attention required & readiness meters).
  3. Directional Knowledge Transmission Bridge.
  4. Incoming Successor (Onboarding checklist & RAG query).

#### `TrustSection.tsx`
- **Heading**: "Built for accuracy, transparency and control."
- **Visual**: 4-Tier Epistemic Separation Model (Source Evidence → Extracted Information → AI Interpretation → Human-Verified Knowledge).
- **Core Guarantees**: Zero Data Fabrication, Human-in-the-Loop Governance, Strict Source-Level Permissions, Cryptographic Provenance.

#### `FaqSection.tsx`
- **Heading**: "Common questions about The Handover."
- **Accordion**: 8 detailed questions with animated CSS grid-rows expand/collapse.

#### `FinalCtaSection.tsx`
- **Heading**: "Keep your project knowledge continuous, verifiable and ready to hand over."
- **Visual**: Deep navy container with `OrganicScene` (`variant="continuity"`).
- **Actions**: "Get started with Handover" (primary) + "Explore Questions" (secondary).

#### `LandingFooter.tsx`
- **Layout**: 5 columns (Brand, Product, Solutions, Resources, Platform) + subfooter with dynamic year and legal links.
