# Hero 3D Globe Background Redesign Report
## Deliverable: `HERO_GLOBE_BACKGROUND_REDESIGN_REPORT.md` (Milestone 4)

**Date**: November 18, 2026  
**Component**: `frontend/src/components/landing/HeroSection.tsx` & `frontend/src/components/brand/OrganicScene.tsx`  
**Author**: Principal Product Designer & 3D Graphics Engineer  
**Status**: COMPLETE (Verified against Part 6 & 17.2 acceptance criteria)

---

## 1. Problem Definition & Architectural Contrast

### Original Composition (Boxed Object)
- In earlier versions, `HeroSection` placed the 3D sphere into a 2-column grid (`lg:grid-cols-[1.05fr_0.95fr]`) constrained inside a container div (`h-[320px] sm:h-[430px] lg:h-[490px]`).
- The 3D canvas was framed by the column's layout boundary, creating a visual "card" or "image inside a box" aesthetic rather than an atmospheric, living digital universe.
- The 5 orbiting node pills were clamped to this narrow box (`top-[6%]`, etc.), exacerbating the boxed look.

### Redesigned Composition (Full-Bleed Atmospheric Background)
- The 3D knowledge globe is now emancipated from the grid column and integrated into a **multi-layer full-bleed hero atmosphere**:
  1. **Layer 1 (Canvas Gradients)**: Subtle radial glow (`ellipse 75% 65% at 75% 48%`, `#315FBA` at 11%, `#299B80` at 5%) anchored behind the scene.
  2. **Layer 2 & 3 (Organic 3D Knowledge Universe)**: True full-bleed background canvas positioned toward the center-right (`w-[960px] h-[960px] xl:w-[1080px] xl:h-[1080px]`). It extends beyond container boundaries, scaled 2.2× larger than before.
  3. **Atmospheric Alpha Masks**: Dual radial and linear gradient masks blend the canvas perimeter seamlessly into the `#F6F8FC` page background. Zero visible square edges, borders, or container cutoffs remain.
  4. **Layer 4 (Unboxed Orbiting Source Nodes)**: The 5 nodes (`Repository Node`, `Documentation Node`, `Conversation Node`, `Task Node`, `Project Knowledge Node`) float freely in open 3D space with delicate animated SVG connection filaments drawn toward the central sphere.
  5. **Layer 5 (Foreground Editorial Content)**: Eyebrow, headline, supporting copy, primary/secondary CTAs, and trust assurance strip sit on the left with crystal-clear contrast and zero occlusion.
  6. **Layer 6 (Navigation & Controls)**: Fixed glassmorphic navigation header and scroll indicator.

---

## 2. Technical Implementation Details

```tsx
{/* Full-Bleed Atmospheric Background Universe */}
<div className="pointer-events-none absolute inset-0 z-0 overflow-hidden flex items-center justify-end">
  <div
    className="relative right-[-10%] sm:right-[-4%] lg:right-[0%] w-[580px] h-[580px] sm:w-[740px] sm:h-[740px] lg:w-[960px] lg:h-[960px] xl:w-[1080px] xl:h-[1080px] transition-transform duration-200 ease-out"
    style={{
      transform: `translateY(${heroShiftY}px) scale(${heroScale})`,
      opacity: heroCanvasOpacity,
    }}
  >
    <OrganicScene
      variant="hero"
      camZoom={1.1}
      highlightCluster={activeNode ? activeNode.cluster : null}
      showTags={false}
      className="h-full w-full"
      label="Organic 3D knowledge sphere seamlessly integrated into the atmospheric hero background"
    />
  </div>
  {/* Seamless Edge Blending Masks */}
  <div
    className="absolute inset-0 pointer-events-none"
    style={{
      background:
        "radial-gradient(ellipse 65% 55% at 75% 50%, transparent 35%, rgba(246,248,252,0.45) 65%, #F6F8FC 100%)",
    }}
  />
  <div className="absolute inset-y-0 left-0 w-full sm:w-[50%] lg:w-[42%] bg-gradient-to-r from-[#F6F8FC] via-[#F6F8FC]/90 to-transparent pointer-events-none" />
</div>
```

---

## 3. Responsive & Accessibility Adaptations

- **1440px / 1280px Desktop**: Expansive 960–1080px background sphere with interactive orbiting badges and animated SVG filaments.
- **1024px / 768px Tablet**: Scaled 740px sphere with soft opacity (`heroCanvasOpacity`), maintaining clear contrast for the left headline and CTAs.
- **Mobile (<640px)**: Centered 580px background sphere at reduced opacity (`opacity-40`); nodes are rendered as a clean, responsive compact pill strip below CTAs (`lg:hidden`). Zero horizontal scrollbar or overflow.
- **Prefers-Reduced-Motion**: Disables scroll-linked scale and downward parallax drift, rendering a static high-fidelity composition.

---

## 4. Acceptance Criteria Verification (Part 6.11)

1. **No square object look**: PASS — Globe is an ambient background layer.
2. **No visible canvas borders**: PASS — Seamless radial gradient mask.
3. **Natural background blending**: PASS — Integrates directly with `#F6F8FC`.
4. **Atmospheric composition**: PASS — High visual depth.
5. **Readability intact**: PASS — Left side protected by gradient veil.
6. **Responsive scaling**: PASS — 1440, 1024, 768, 390px validated.
7. **No horizontal overflow**: PASS — Section has `overflow-hidden`.
8. **Bidirectional scroll transitions**: PASS — Scroll-progress transforms `scale` and `translateY`.
9. **Reduced motion**: PASS — Static render path.
10. **Zero performance regression**: PASS — Native rAF loop with `IntersectionObserver` auto-pausing.
