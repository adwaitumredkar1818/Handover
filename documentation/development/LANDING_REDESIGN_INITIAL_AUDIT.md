# Handover — Complete Landing Page Redesign & Walkthrough Audit
## Deliverable: `LANDING_REDESIGN_INITIAL_AUDIT.md` (Milestone 1)

**Date**: November 18, 2026  
**Product**: Handover — Intelligent Project Knowledge Reconstruction & Handover Platform  
**Target Walkthrough Video**: `handover_2.mp4` (`media_1795007793810_df9ca807.mp4`)  
**Design Direction**: Organic Intelligence in Motion  
**Audit Author**: Principal Product Designer & Frontend Architecture Team

---

## 1. Executive Summary & Audit Scope

This document provides the mandatory architectural and visual walkthrough audit of the Handover landing page prior to execution. It incorporates:
1. Complete component inventory and route boundaries across `frontend/src/components/landing/`.
2. Exhaustive frame-by-frame analysis of the user walkthrough video recording (`handover_2.mp4`, 139.4s, 1920×1032 @ 30fps).
3. Root-cause diagnosis of **Critical Fix 1 (BrandIntro premature dismissal)** and **Critical Fix 2 (Hero Globe boxed containment)**.
4. Comprehensive defect catalog across all 15 canonical sections.
5. Technical risks, shared motion contracts, and multi-milestone execution architecture.

---

## 2. Route Structure & Application Boundaries

- **`/` (`frontend/src/app/page.tsx`)**: Renders `<LandingPage />` directly as a Client Component. All landing page sections, navigation, and brand assets reside in `frontend/src/components/landing/` and `frontend/src/components/brand/`.
- **Application Routes (`/overview`, `/projects`, `/evidence`, `/knowledge`, `/relationships`, `/handovers`, `/assistant`)**: Authenticated workspace routes governed by FastAPI auth and PostgreSQL RBAC. Must remain completely unaffected.
- **Auth Routes (`/login`, `/signup`)**: Handled by platform authentication. Landing page CTAs navigate cleanly to `/signup` or `/overview` depending on live session status.

---

## 3. Current Component Inventory & Status

| Section | Component | File Path | Current Status & Audit Findings |
| :--- | :--- | :--- | :--- |
| **01** | `BrandIntro` | `BrandIntro.tsx` | **CRITICAL FIX 1**: Prematurely vanishes after ~500ms; lacks renderer readiness handshakes and relies on arbitrary timers. |
| **Global** | `LandingNav` | `LandingNav.tsx` | Functional glassmorphic nav; verified dropdown toggles and Escape dismiss. |
| **02** | `HeroSection` | `HeroSection.tsx` | **CRITICAL FIX 2**: Globe is trapped inside a boxed right-column grid container with visible edges; must become a true full-bleed background. |
| **03** | `ProblemSection` | `ProblemSection.tsx` | Asymmetrical card heights and excessive empty white space in Card 03. |
| **04** | `IntroducingSection` | `IntroducingSection.tsx` | **MAJOR DEFECT**: Canvas detaches on scroll leaving a giant empty void; duplicates the 3 stages twice in succession. |
| **05** | `HowItWorksSection` | `HowItWorksSection.tsx` | **MAJOR DEFECT**: 5-step stepper pushes preview card to columns 4–5, leaving columns 1–3 (60% of screen) completely blank. |
| **06** | `ConnectedSourcesSection` | `ConnectedSourcesSection.tsx` | **MAJOR DEFECT**: Severe text truncation on desktop (`Code Repositor...`, `Project & Transi...`, `Restricted Private...`). |
| **07** | `EvidenceCenterSection` | `EvidenceCenterSection.tsx` | 3-panel architecture works well; needs minor padding polish at bottom of Panel C. |
| **08** | `IntelligenceSection` | `IntelligenceSection.tsx` | **MAJOR DEFECT**: Background `OrganicScene` is unmasked and bleeds stray connection lines into Section 09 below. |
| **09** | `ExplorerSection` | `ExplorerSection.tsx` | Interactive SVG graph works well; needs auto-fit/centering to eliminate empty left margin. |
| **10** | `KnowledgeAssistantSection`| `KnowledgeAssistantSection.tsx` | Minor truncation in citation pill under Sample 03 (`human r...`). |
| **11** | `HandoversSection` | `HandoversSection.tsx` | **MAJOR DEFECT**: Asymmetrical column heights leave lingering ghost buttons in an empty white screen on scroll. |
| **12** | `RolesSection` | `RolesSection.tsx` | **MAJOR DEFECT**: Top bridge tabs do not switch views in-place; forces 1,500px scroll through 3 stacked showcases; stray floating pill. |
| **13** | `TrustSection` | `TrustSection.tsx` | Four epistemic layers function properly with distinct colors. |
| **14** | `FaqSection` | `FaqSection.tsx` | Accordions expand and collapse cleanly. |
| **15** | `FinalCtaSection` | `FinalCtaSection.tsx` | **DEFECT**: Low-contrast dark teal/grey CTA buttons against dark navy card; awkward card cutoff above footer. |
| **Global** | `LandingFooter` | `LandingFooter.tsx` | Footer navigation is intact; needs smooth gradient blend from Final CTA. |
| **Utility**| `ReadingProgressBar` | `ReadingProgressBar.tsx` | Functional 2.5px gradient scroll indicator. |
| **Utility**| `BackToTop` | `BackToTop.tsx` | Functional floating back-to-top control past hero fold. |
| **Utility**| `SectionDivider` | `SectionDivider.tsx` | Hairline dividers with traveling light beam and monospaced section tags. |

---

## 4. Root-Cause Analysis: Critical Fixes

### 4.1 Critical Fix 1: BrandIntro Premature Dismissal
- **Observed Behavior**: In `handover_2.mp4` (0:00–0:02), the dark introduction appears for ~500ms and abruptly vanishes into the hero before particles converge or the identity resolves.
- **Root Cause**:
  1. `BrandIntro.tsx` (lines 52–58) hardcodes arbitrary `setTimeout` delays (`t0: 120ms`, `t1: 520ms`, `t2: 980ms`, `t3: 1780ms`, `t4: 2250ms`).
  2. At `1780ms`, `isRevealingHero` activates CSS `opacity-0 scale-[1.02]`.
  3. Crucially, `OrganicScene` requires ~500–800ms on first mount to calculate canvas DPI, establish WebGL/2D contexts, and run the first requestAnimationFrame frame.
  4. By the time `OrganicScene` actually paints its first visible frame, the timer chain is already at `page-reveal` and fading away, giving the illusion of a broken 500ms flash.
  5. There was **no renderer readiness callback (`onReady`)** between `OrganicScene` and `BrandIntro`.
- **Solution**:
  - Add an explicit `onReady` prop to `OrganicScene` that fires strictly after the first valid frame is painted.
  - Implement a deterministic 6-state lifecycle in `BrandIntro`: `INITIALIZING -> READY -> PLAYING -> COMPLETED` (with `SKIPPED` and `FALLBACK` handlers).
  - Do not start the particle convergence timeline until `READY` is signaled by the renderer.

### 4.2 Critical Fix 2: Hero Globe Boxed Containment
- **Observed Behavior**: In `frame_002.jpg`, the hero globe is visually constrained within the right grid column (`lg:grid-cols-[1.05fr_0.95fr]`) inside an explicit `h-[320px] sm:h-[430px] lg:h-[490px]` box with orbiting pill buttons clamped inside that same box.
- **Root Cause**: The 3D canvas is treated as a column child inside an inline flex/grid layout rather than an atmospheric, full-bleed environment background.
- **Solution**:
  - Redesign `HeroSection.tsx` into a layered architectural composition:
    - **Layer 1 (Atmosphere)**: Soft radial glow and canvas gradient (`#F6F8FC`).
    - **Layer 2 & 3 (Organic 3D Scene)**: Full-bleed background canvas positioned toward the center-right, extending beyond standard container bounds, blended seamlessly using radial gradient alpha masks (zero box boundaries).
    - **Layer 4 (Orbiting Source Nodes)**: Interactive nodes floating in space around the globe with animated connection filaments.
    - **Layer 5 (Foreground Editorial)**: Headline, copy, CTAs, and trust assurance strip positioned cleanly on the left with high contrast and zero visual obstruction.
    - **Layer 6 (Navigation)**: Sticky glass navbar overhead.

---

## 5. Walkthrough Defect Catalog (`handover_2.mp4`)

| Defect ID | Section | Timestamps | Description | Root Cause |
| :--- | :--- | :--- | :--- | :--- |
| **DEF-01** | `IntroducingSection` | `0:10–0:22`, `2:14–2:18` | Sticky canvas detaches, leaving a massive empty white screen; then duplicate 3-stage cards scroll underneath. | Competing 2-column sticky block + 3-column card block stacked consecutively without coordination. |
| **DEF-02** | `HowItWorksSection` | `0:18–0:28`, `2:11–2:15` | Preview card placed at columns 4–5, leaving columns 1–3 (60% of viewport) completely blank. | Hardcoded `gridColumnStart: Math.min(activeStep+1, 4), span 2` in a 5-column grid without left context card. |
| **DEF-03** | `ConnectedSourcesSection` | `0:24–0:38` | Card titles and subtexts truncated with ellipses (`Code Repositor...`, etc.). | Cards constrained to `w-[265px]` with premature `truncate` on ~120px available title container. |
| **DEF-04** | `IntelligenceSection` | `0:46–0:58` | Background 3D network bleeds stray node lines into Section 09 header below. | Canvas is unclipped and bottom gradient mask (`h-20`) is too shallow. |
| **DEF-05** | `KnowledgeAssistantSection` | `1:14–1:20` | Citation button in Sample 03 truncates text as `human r...`. | Overly aggressive `truncate` class on citation label. |
| **DEF-06** | `HandoversSection` | `1:20–1:36` | Asymmetrical column height leaves lingering package buttons on an empty white screen on scroll. | Left narrative stack is taller than the right dossier card. |
| **DEF-07** | `RolesSection` | `1:34–1:50` | Clicking bridge tabs does not update screen in place; 3 roles are stacked vertically over 1,500px; floating stray pill. | Bridge tabs only toggle border ring of distant cards; layout lacks tabbed in-place switching. |
| **DEF-08** | `FinalCtaSection` | `2:04–2:10` | `Get Started` and `Review FAQ` buttons suffer from low contrast against dark navy card; card cutoff above footer. | Dim `#299B80` button color and low-opacity secondary border on dark container. |

---

## 6. Shared Motion Architecture & Tokens

- **Centralized Engine**: Canvas 2D/3D custom renderer (`OrganicScene.tsx`) with zero heavy runtime dependencies.
- **Scroll Tracking**: `useScrollProgress.ts` (global window scroll) and `useElementScrollProgress.ts` (element-relative `0..1` progress via rAF).
- **Reduced Motion**: Full compliance via `useReducedMotion.ts` (`prefers-reduced-motion: reduce`) providing static high-quality compositions.
- **Motion Tokens**:
  - `duration-fast`: 200ms
  - `duration-normal`: 350ms
  - `duration-reveal`: 500ms
  - `duration-cinematic`: 750ms
  - Easing: `cubic-bezier(0.16, 1, 0.3, 1)` (apple-smooth deceleration)

---

## 7. Execution Phasing & Test Governance

All modifications must strictly preserve passing status across the existing 17 automated tests:
- `LandingPageAudit.test.tsx` (13 tests): Structural integrity, canonical 5-stage workflow, Evidence Center 3-panel architecture, 8 knowledge domains, Relationship Explorer SVG graph, Assistant uncertainty disclosure, HO-1042 58 verified items, 4-tier Trust separation, FAQ accordion, Section 06 Connected Sources, Hero nodes.
- `KnowledgeAndRelationship.test.tsx` (4 tests): Dashboard view switches.
