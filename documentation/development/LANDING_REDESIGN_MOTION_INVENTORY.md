# Handover Landing Page Redesign — Motion Inventory & Tokens
## Deliverable: `LANDING_REDESIGN_MOTION_INVENTORY.md` (Milestone 3)

**Date**: November 18, 2026  
**Platform**: Handover — Intelligent Project Knowledge Reconstruction & Handover Platform  
**Author**: Motion Design Engineer & Creative Frontend Architect  
**Architecture**: Canvas 2D/3D custom volumetric renderer + CSS token architecture + viewport-relative scroll hooks

---

## 1. Centralized Motion Tokens (`motionConfig.ts`)

| Token Name | Value | Purpose & Target Application |
| :--- | :--- | :--- |
| `MOTION_DURATIONS.instant` | 120ms | Button active press, checkbox tick, micro-feedback |
| `MOTION_DURATIONS.fast` | 220ms | Tag hover, icon bounce, badge pulses (180–280ms band) |
| `MOTION_DURATIONS.standard` | 420ms | Tab selection, accordion expand, detail drawer update (350–500ms band) |
| `MOTION_DURATIONS.medium` | 450ms | Card lift, drawer slide-in, modal reveal |
| `MOTION_DURATIONS.reveal` | 600ms | Viewport section reveal, heading stagger entrance (450–750ms band) |
| `MOTION_DURATIONS.sectionTransition` | 750ms | Light/dark scene transitions, atmospheric veil (600–900ms band) |
| `MOTION_DURATIONS.extended` | 800ms | Cinematic particle convergence, knowledge core transformations |
| `MOTION_DURATIONS.graphDrawing` | 1200ms | SVG relationship connection line path draw |
| `MOTION_DURATIONS.dossierAssembly` | 1600ms | Complete handover dossier multi-strata assembly sequence |

### Easing Functions:
- **`standard`**: `cubic-bezier(0.22, 1, 0.36, 1)` — Apple-smooth deceleration for SaaS layouts.
- **`interactive`**: `cubic-bezier(0.4, 0, 0.2, 1)` — Responsive state transitions (hover, active, tab switch).
- **`entrance`**: `cubic-bezier(0, 0, 0.2, 1)` — Natural deceleration into viewport.
- **`springGentle`**: `cubic-bezier(0.16, 1, 0.3, 1)` — Organic bounce for floating nodes and pills.
- **`linear`**: `linear` — Traveling laser pulse beam and continuous background particle drift.

---

## 2. Complete Section-by-Section Motion Inventory

| Section | Component | Animation Name | Trigger Type | Start Condition | End Condition | Duration / Progress Range | Easing | Reduced Motion Fallback | Mobile Behavior |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **01** | `BrandIntro` | Cinematic Convergence | Mount / OnReady | Canvas context painted | Page reveal fade | 3100ms total | `springGentle` | Instant brand mark, 500ms hold | Same unhurried sequence, full-width canvas |
| **02** | `HeroSection` | Full-Bleed Atmosphere | Mount & Scroll | Viewport enter | Scroll fold passed | `scrollY` 0 -> 400px | `standard` | Static 3D sphere, no parallax drift | Centered background globe, scale 0.85 |
| **02** | `HeroSection` | Orbiting Node Floating | Continuous | Mount | Continuous | 4.2s cycle | `linear` | Static node positions | Stacked below headline, zero overflow |
| **03** | `ProblemSection` | Knowledge Fragmentation | Scroll | Element enters 75% | Element leaves 25% | `progress` 0.0 -> 1.0 | `standard` | Static 3 problem cards | Sequential stack with subtle divider |
| **04** | `IntroducingSection` | Reconstruction Core | Scroll & Tab | Element in view | Scroll fold passed | `progress` 0.2 -> 1.0 | `standard` | Static multi-layer card | Stacked sequential cards |
| **05** | `HowItWorksSection` | 5-Stage Stepper | Scroll & Click | User scroll or click | Step change | 420ms transition | `interactive` | Instant tab switch | Vertical sequence with embedded preview |
| **06** | `ConnectedSourcesSection` | ACL Stream Flow | Continuous | In view | Scrolled off | 2.2s pulse loop | `linear` | Static connector lines | 2-column mobile card grid |
| **07** | `EvidenceCenterSection` | Provenance Chain | Click / Filter | User clicks row | Panel update | 350ms fade/slide | `interactive` | Instant panel update | Segmented tab switcher (Panel A/B/C) |
| **08** | `IntelligenceSection` | 8-Domain Radial Pulse | Click / Hover | Domain selected | Finding update | 300ms ring scale | `interactive` | Instant finding update | 2-column grid selector + card |
| **09** | `ExplorerSection` | Node Relationship Graph | Click / Hover | Node selected | Drawer reveal | 350ms drawer slide | `interactive` | Instant drawer update | Touch-friendly pan/zoom & reset |
| **10** | `KnowledgeAssistantSection` | Grounded Answer Typewriter | Click Sample | Sample selected | Answer complete | 450ms fade | `standard` | Instant answer display | Full-width chat window |
| **11** | `HandoversSection` | Dossier Strata Assembly | Scroll & Tab | Scroll progress | Step 7 reached | `progress` 0.0 -> 1.0 | `springGentle` | Static complete dossier | Tabbed role view with metric bar |
| **12** | `RolesSection` | In-Place Role Continuity | Click Role | Bridge tab clicked | Active role change | 350ms crossfade | `interactive` | Instant view swap | Sticky top pills + active showcase |
| **13** | `TrustSection` | 4-Tier Epistemic Reveal | Viewport / Click | Scroll into view | Tier selected | 500ms stagger | `standard` | All 4 tiers expanded | Vertical card stack with color coding |
| **14** | `FaqSection` | Accordion Expansion | Click | Header clicked | Drawer open | 350ms height auto | `interactive` | Instant open/close | Full-width touch accordions |
| **15** | `FinalCtaSection` | Continuity Sphere Glow | Scroll into view | Viewport enter | In view | 750ms entrance | `springGentle` | Static glowing sphere | High-contrast stacked CTAs |
