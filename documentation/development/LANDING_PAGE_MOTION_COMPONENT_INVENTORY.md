# The Handover — Landing Page Motion Component Inventory
## Milestone M1: Architecture, Tokens, Components, and Hooks Inventory

**Platform**: The Handover  
**Document**: Motion Component Inventory  
**Date**: November 18, 2026  
**Scope**: All frontend motion modules, custom hooks, tokens, and landing sections  

---

## 1. Central Motion Tokens

**File**: `frontend/src/components/landing/motion/motionConfig.ts`

| Token Category | Token Key | Value | Typical Usage |
| :--- | :--- | :--- | :--- |
| **Durations** | `instant` | `100ms` | Micro-toggles, active state pills |
| | `fast` | `180ms` | Button hovers, badge elevations, tab switches |
| | `normal` | `280ms` | Card reveals, accordions, panel slides |
| | `medium` | `450ms` | Stage transitions, drawer entrances |
| | `slow` | `700ms` | Canvas transformations, scene fades |
| | `narrative` | `1200ms` | Brand intro sequence, complex assembly |
| **Staggers** | `tight` | `40ms` | Citations list, metadata tags |
| | `normal` | `80ms` | Feature grids, workflow steps |
| | `relaxed` | `120ms` | Section headlines, problem pillars |
| **Easings** | `standard` | `cubic-bezier(0.2, 0, 0, 1)` | General interface transitions |
| | `decelerate` | `cubic-bezier(0, 0, 0.2, 1)` | Entrances, modals, drawers |
| | `accelerate` | `cubic-bezier(0.3, 0, 1, 1)` | Exits, dismissals |
| | `spring` | `cubic-bezier(0.34, 1.56, 0.64, 1)` | Pills, badges, selection bumps |

---

## 2. Shared Custom Motion Hooks

### 2.1 `useReducedMotion`
- **Location**: `frontend/src/components/landing/motion/useReducedMotion.ts`
- **Purpose**: SSR-safe detection of user's OS-level reduced motion preference (`(prefers-reduced-motion: reduce)`).
- **Return Value**: `boolean` (`prefersReducedMotion`).
- **Used In**: `OrganicScene`, `HeroSection`, `ReadingProgressBar`, `HowItWorksSection`, `RolesSection`.

### 2.2 `useScrollProgress`
- **Location**: `frontend/src/components/landing/motion/useScrollProgress.ts`
- **Purpose**: High-efficiency, non-blocking window scroll monitoring utilizing `requestAnimationFrame`.
- **Return Values**:
  - `progress`: Number between `0.0` and `1.0` (overall page scroll ratio).
  - `scrollY`: Raw vertical pixel offset.
  - `isScrolled`: Boolean (`scrollY > 20px`), used for navbar glassmorphism.
  - `isPastHero`: Boolean (`scrollY > 420px`), used for back-to-top button appearance.
- **Used In**: `LandingNav`, `ReadingProgressBar`, `BackToTop`, `HeroSection`.

### 2.3 `useSectionReveal` & `useReveal`
- **Location**: `frontend/src/components/landing/motion/useSectionReveal.ts` and `frontend/src/components/landing/hooks/useReveal.ts`
- **Purpose**: Wrapper around `IntersectionObserver` providing staggered, directional reveal animations when sections enter the viewport.
- **Parameters**: `threshold` (default 0.15), `rootMargin` (default "0px 0px -40px 0px"), `staggerDelay` (ms).
- **Return Values**: `ref`, `isVisible`, `revealClasses`.
- **Used In**: All 15 landing page content sections.

---

## 3. Global Motion Components

### 3.1 `ReadingProgressBar`
- **Location**: `frontend/src/components/landing/ReadingProgressBar.tsx`
- **Role**: Renders a fixed 2.5px gradient reading progress bar at the very top of the browser viewport.
- **Motion Characteristics**: GPU-accelerated `transform: scaleX(progress)` with `will-change: transform`. Respects `prefers-reduced-motion` by remaining hidden.

### 3.2 `BackToTop`
- **Location**: `frontend/src/components/landing/BackToTop.tsx`
- **Role**: Renders an accessible floating pill at bottom-right when scrolled past the hero section.
- **Motion Characteristics**: Spring entrance (`scale-100 opacity-100` vs `scale-90 opacity-0 pointer-events-none`). Smooth scroll behavior on click.

---

## 4. Section Component Inventory & Motion Mapping

| Section Component | File Path | Key Motion & Interaction Features |
| :--- | :--- | :--- |
| **BrandIntro** | `frontend/src/components/landing/BrandIntro.tsx` | Sequenced SVG line drawing, letter stagger, ~2.35s total duration, escape key dismissal, skip button |
| **LandingNav** | `frontend/src/components/landing/LandingNav.tsx` | Glassmorphic scroll trigger (`scrollY > 20px`), mobile slide-down drawer, nav item hover underlines |
| **HeroSection** | `frontend/src/components/landing/HeroSection.tsx` | Staggered entrance, scroll-linked canvas scaling/fade, floating interactive source nodes (GitHub, Jira, Slack, Docs) |
| **SectionDivider** | `frontend/src/components/landing/SectionDivider.tsx` | Subtle geometric transition lines between high-contrast section backgrounds |
| **ProblemSection** | `frontend/src/components/landing/ProblemSection.tsx` | Sticky left anchor with `.reveal-left`, staggered problem metric cards with hover borders |
| **IntroducingSection** | `frontend/src/components/landing/IntroducingSection.tsx` | Dynamic knowledge assembly canvas synchronized with 3 interactive stage buttons |
| **HowItWorksSection** | `frontend/src/components/landing/HowItWorksSection.tsx` | 5-stage workflow stepper (`Connect → Reconstruct → Verify → Review → Handover`) with animated beam |
| **EvidenceCenterSection** | `frontend/src/components/landing/EvidenceCenterSection.tsx` | Three-panel layout, live text search filter in Panel B, active Provenance Pipeline beam in Panel C |
| **IntelligenceSection** | `frontend/src/components/landing/IntelligenceSection.tsx` | 8 domain cards with hover elevation & active ring accent, epistemic status pill transitions |
| **ExplorerSection** | `frontend/src/components/landing/ExplorerSection.tsx` | Interactive SVG relationship graph, traveling edge light pulses (`<animateMotion>`), node detail drawer |
| **KnowledgeAssistantSection** | `frontend/src/components/landing/KnowledgeAssistantSection.tsx` | 4 sample query triggers, animated typing synthesis dots, expandable provenance excerpts |
| **HandoversSection** | `frontend/src/components/landing/HandoversSection.tsx` | Role dossier package switcher (`Developer`, `Lead`, `Leadership`) with card elevation |
| **RolesSection** | `frontend/src/components/landing/RolesSection.tsx` | Knowledge Transmission Bridge with traveling SVG particles connecting departing and incoming roles |
| **TrustSection** | `frontend/src/components/landing/TrustSection.tsx` | 4-tier epistemic depth selector with interactive layer cards and elevation highlights |
| **FaqSection** | `frontend/src/components/landing/FaqSection.tsx` | Smooth height accordion with rotating chevrons and keyboard accessibility |
| **FinalCtaSection** | `frontend/src/components/landing/FinalCtaSection.tsx` | Staggered reveal of closing proposition and dual high-contrast action buttons |
| **LandingFooter** | `frontend/src/components/landing/LandingFooter.tsx` | Clean organizational links, copyright notices, and back-to-top interaction |

---

## 5. CSS Motion Utilities (`globals.css`)

```css
/* Directional and transform-based reveals */
.reveal-left { opacity: 0; transform: translateX(-24px); transition: opacity 0.6s cubic-bezier(0.2, 0, 0, 1), transform 0.6s cubic-bezier(0.2, 0, 0, 1); }
.reveal-right { opacity: 0; transform: translateX(24px); transition: opacity 0.6s cubic-bezier(0.2, 0, 0, 1), transform 0.6s cubic-bezier(0.2, 0, 0, 1); }
.reveal-scale { opacity: 0; transform: scale(0.95); transition: opacity 0.6s cubic-bezier(0.2, 0, 0, 1), transform 0.6s cubic-bezier(0.2, 0, 0, 1); }
.reveal-clip { clip-path: inset(0 100% 0 0); transition: clip-path 0.7s cubic-bezier(0.2, 0, 0, 1); }

.revealed.reveal-left,
.revealed.reveal-right { opacity: 1; transform: translateX(0); }
.revealed.reveal-scale { opacity: 1; transform: scale(1); }
.revealed.reveal-clip { clip-path: inset(0 0 0 0); }

/* SVG and Canvas animations */
.animate-line-draw { stroke-dasharray: 1000; stroke-dashoffset: 1000; animation: lineDraw 1.8s cubic-bezier(0.2, 0, 0, 1) forwards; }
.animate-beam { animation: beamTravel 2.4s linear infinite; }
```
