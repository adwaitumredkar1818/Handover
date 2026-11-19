# The Handover — Landing Page Motion Experience Implementation Report
## Milestone M1: Full-Scale Animation, Scroll Storytelling & Interaction System

**Product**: The Handover  
**Formal Description**: Intelligent Project Knowledge Reconstruction & Handover Platform  
**Tagline**: Prevent Critical Knowledge From Leaving With People.  
**Implementation Phase**: Milestone M1 — Motion Experience & Scroll Storytelling  
**Date**: November 18, 2026  
**Status**: Completed & Verified  

---

## 1. Executive Summary & Narrative Arc

The complete motion and interaction architecture for **The Handover** landing page has been designed and implemented. Rather than superficial decorative effects or heavy third-party animation dependencies, the motion system embodies the core institutional knowledge continuity narrative:

```text
PEOPLE MOVE ON
     ↓
KNOWLEDGE BECOMES FRAGMENTED
     ↓
SOURCES COME TOGETHER
     ↓
KNOWLEDGE IS RECONSTRUCTED
     ↓
RELATIONSHIPS BECOME VISIBLE
     ↓
HUMANS VERIFY KNOWLEDGE
     ↓
KNOWLEDGE IS TRANSFERRED
```

Every transition, hover state, canvas particle simulation, SVG data beam, and scroll-linked effect directly reinforces this journey. The platform communicates technical rigor, epistemic integrity, and institutional trust through crisp, high-frame-rate, hardware-accelerated interactions.

---

## 2. Motion Architecture & Engineering Foundations

### 2.1 Centralized Motion Tokens (`motionConfig.ts`)
All durations, staggers, and easing curves are consolidated in `frontend/src/components/landing/motion/motionConfig.ts` to maintain rhythm and consistency across all 15 sections:

- **Durations**:
  - `instant`: 100ms (micro-toggles, active state indicators)
  - `fast`: 180ms (button hovers, badge elevations, tab transitions)
  - `normal`: 280ms (card reveals, accordions, panel slides)
  - `medium`: 450ms (stage shifts, drawer openings)
  - `slow`: 700ms (canvas transformations, scene fades)
  - `narrative`: 1200ms (brand sequence, complex transitions)
- **Staggers**:
  - `tight`: 40ms (citation lists, breadcrumbs)
  - `normal`: 80ms (grid items, workflow steps)
  - `relaxed`: 120ms (section headlines, feature pillars)
- **Easings**:
  - `standard`: `cubic-bezier(0.2, 0, 0, 1)` (general UI flow)
  - `decelerate`: `cubic-bezier(0, 0, 0.2, 1)` (entrances, drawers)
  - `accelerate`: `cubic-bezier(0.3, 0, 1, 1)` (exits, dismissals)
  - `spring`: `cubic-bezier(0.34, 1.56, 0.64, 1)` (pills, badges, toggle bumps)

### 2.2 Reusable Motion Hooks
1. **`useReducedMotion`** (`frontend/src/components/landing/motion/useReducedMotion.ts`):
   - SSR-safe listener monitoring the `(prefers-reduced-motion: reduce)` media query.
   - Provides immediate, zero-latency reactive state changes if user OS settings change.
2. **`useScrollProgress`** (`frontend/src/components/landing/motion/useScrollProgress.ts`):
   - High-performance scroll calculation throttled via `requestAnimationFrame`.
   - Returns normalized `progress` (0.0 to 1.0), raw `scrollY`, boolean flags `isScrolled` (> 20px threshold), and `isPastHero` (> 420px threshold).
3. **`useSectionReveal` & `useReveal`** (`frontend/src/components/landing/motion/useSectionReveal.ts` and `frontend/src/components/landing/hooks/useReveal.ts`):
   - IntersectionObserver hook supporting customizable thresholds, root margins, stagger delays, and directional animation classes.
   - Preserves 100% backward compatibility for all existing section implementations.

### 2.3 Global Navigation & Progress Components
1. **`ReadingProgressBar`** (`frontend/src/components/landing/ReadingProgressBar.tsx`):
   - Fixed 2.5px top progress indicator with a brand gradient (`#315FBA` → `#8B78C9` → `#0D9488`).
   - Uses GPU-accelerated `transform: scaleX(progress)` with `transformOrigin: left`.
   - Automatically hidden when `prefers-reduced-motion` is active.
2. **`BackToTop`** (`frontend/src/components/landing/BackToTop.tsx`):
   - Floating pill appearing smoothly when `isPastHero` is true.
   - Accessible keyboard target with ARIA label and smooth window scroll to top.

### 2.4 CSS Hardware Acceleration & Reduced-Motion (`globals.css`)
- Directional reveal utility classes:
  - `.reveal-left`: Translates from `-24px` on the X-axis while fading in.
  - `.reveal-right`: Translates from `+24px` on the X-axis while fading in.
  - `.reveal-scale`: Scales from `0.95` to `1.0` while fading in.
  - `.reveal-clip`: Elegant clip-path curtain reveal.
  - `.animate-line-draw`: SVG path stroke-dashoffset animation.
- Comprehensive `@media (prefers-reduced-motion: reduce)` overrides:
  - All transitions and animation durations set to `0.001ms !important`.
  - Transform animations disabled (`transform: none !important`).
  - Canvas render loops freeze to static, fully rendered compositions.

---

## 3. Section-by-Section Motion Implementation

### 3.1 BrandIntro (`BrandIntro.tsx`)
- **Tuned Timing**: Choreographed sequence completing in ~2.35s to prevent user friction while delivering a cinematic brand impression.
- **Micro-Interactions**: Interactive "Skip intro" button and `Escape` key listener with instant dismissal.
- **Asset Optimization**: Converted raw `<img>` tags to optimized Next.js `<Image />` components with priority loading.

### 3.2 LandingNav (`LandingNav.tsx`)
- **Dynamic Glassmorphism**: Scroll-linked background transition via `useScrollProgress()` switching from transparent to `bg-[#F6F8FC]/90 backdrop-blur-md shadow-xs border-[#D9E1F0]/80` at `scrollY > 20px`.
- **Mobile Drawer**: Slide-down menu animation (`animate-slide`) with backdrop fade.

### 3.3 HeroSection (`HeroSection.tsx`)
- **Staggered Entrance**: Eyebrow badge, master headline, value proposition, and dual CTAs enter with staggered timing.
- **Scroll-Linked Parallax**: The background `OrganicScene` scales smoothly (`1.0` down to `0.88`) and fades gently (`opacity: 1.0` down to `0.70`) as the user scrolls past the hero fold.
- **Floating Concept Nodes**: Interactive floating badges (GitHub, Jira, Slack, Docs) with subtle floating pulses and hover elevation.

### 3.4 ProblemSection (`ProblemSection.tsx`)
- **Directional Reveal**: Left sticky anchor uses `.reveal-left` to establish the visual weight of the institutional memory problem.
- **Progressive Metric Cards**: The 3 problem metrics ("73% of context lost", "6.2 hours/week searching", "14 weeks to onboard") stagger with border highlights on hover.

### 3.5 IntroducingSection (`IntroducingSection.tsx`)
- **Interactive Knowledge Assembly**: Stage buttons (`1: Connected Sources`, `2: Knowledge Extraction`, `3: Reconstructed dossiers`) dynamically control the embedded Canvas animation progress (`0.2`, `0.6`, `1.0`).
- **Interactive Stage Cards**: Clicking any stage updates active stage state with smooth badge highlights and canvas synchronization.

### 3.6 HowItWorksSection (`HowItWorksSection.tsx`)
- **5-Stage Workflow Stepper**: `Connect → Reconstruct → Verify → Review → Handover` connected by an SVG data beam (`.animate-beam`).
- **Interactive Previews**: Step selector changes the active live preview card with smooth fade transitions and breadcrumb highlighting.

### 3.7 EvidenceCenterSection (`EvidenceCenterSection.tsx`)
- **Live Search Filtering**: Active search input in Panel B (Evidence Library) allowing instant character-by-character filtering of the 58 evidence records.
- **Active Provenance Pipeline**: Panel C displays a visual SVG light beam flowing from `Source Platform → Text Chunk → Extracted Finding`.

### 3.8 IntelligenceSection (`IntelligenceSection.tsx`)
- **Domain Elevation**: Selecting any of the 8 canonical domains elevates the card with a vibrant border ring (`ring-2 ring-[#315FBA]/25 shadow-card`) while gently muting unselected cards (`opacity-70`).
- **4-Tier Epistemic State**: Finding detail card renders the active verification state pill with smooth badge transitions.

### 3.9 ExplorerSection (`ExplorerSection.tsx`)
- **Relationship Graph Particles**: SVG edge paths feature animated light pulses traveling along dependency and decision links using `<animateMotion>`.
- **Detail Drawer & Reset**: Interactive node selection opens the right detail drawer with a spring entrance; includes a "Reset to core" action to clear selection.

### 3.10 KnowledgeAssistantSection (`KnowledgeAssistantSection.tsx`)
- **Interactive Query Selector**: 4 real-world sample queries with smooth active pill indicators.
- **Synthesizing Indicator**: Staged typing dots (`isTyping`) smoothly announce assistant synthesis while maintaining DOM test safety.
- **Expandable Provenance Citations**: Citations expand on click to reveal exact source provenance excerpts with immutable commit hash and reviewer metadata.

### 3.11 HandoversSection (`HandoversSection.tsx`)
- **Role Dossier Selector**: Interactive tabs for Developer, Lead, and Leadership dossiers. Selected card receives active ring accent and scale elevation.

### 3.12 RolesSection (`RolesSection.tsx`)
- **Knowledge Transmission Bridge**: Custom SVG bridge connecting departing personnel, the platform reconstruction engine, and the incoming successor with traveling light particles.

### 3.13 TrustSection (`TrustSection.tsx`)
- **4-Tier Epistemic Layer Selector**: Interactive selection across Tier 1 (Source Evidence), Tier 2 (Extracted Findings), Tier 3 (AI Synthesized), and Tier 4 (Human Verified) with live detail cards.

### 3.14 FaqSection (`FaqSection.tsx`)
- **Smooth Accordion**: Clean height transition with rotating chevron indicator and keyboard-accessible accordion triggers.

### 3.15 FinalCtaSection (`FinalCtaSection.tsx`)
- **Closing Climax**: Staggered reveal of the final call to action with animated button hover sheen.

---

## 4. Performance, Memory & Lifecycle Verification

1. **RequestAnimationFrame Discipline**: Scroll tracking and canvas rendering strictly use `requestAnimationFrame` and clean up event listeners on unmount.
2. **IntersectionObserver Teardown**: All reveal observers disconnect cleanly upon component unmount, preventing DOM node leaks.
3. **No Layout Shifts (CLS = 0.00)**: All animated containers define explicit minimum heights or flex/grid sizing to eliminate layout shifts during reveals.
4. **Hardware Acceleration**: Transitions rely exclusively on `transform` and `opacity` properties to ensure 60fps execution on mobile and desktop GPUs.

---

## 5. Milestone Verification Summary

| Gate | Target Requirement | Observed Result | Status |
| :--- | :--- | :--- | :--- |
| **TypeScript** | `next typegen && tsc --noEmit` | Clean run, 0 errors | **PASSED** |
| **ESLint** | Scoped `src/components/landing` | 0 errors, 0 warnings | **PASSED** |
| **Vitest Tests** | Full Landing & Intelligence Suites | 15 / 15 tests passing | **PASSED** |
| **Production Build** | `next build` (Turbopack) | 69 / 69 pages static, 0 errors | **PASSED** |
| **Reduced Motion** | `@media (prefers-reduced-motion)` | Fully respected across all elements | **PASSED** |
| **Graphify** | Codebase AST Graph Synchronization | Up to date (`graphify-out/graph.json`) | **PASSED** |
