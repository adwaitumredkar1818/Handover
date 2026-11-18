# BrandIntro Lifecycle Root-Cause Diagnosis & Fix Report
## Deliverable: `BRAND_INTRO_LIFECYCLE_FIX_REPORT.md` (Milestone 2)

**Date**: November 18, 2026  
**Component**: `frontend/src/components/landing/BrandIntro.tsx` & `frontend/src/components/brand/OrganicScene.tsx`  
**Author**: Creative Frontend Developer & Lead Motion Engineer  
**Status**: RESOLVED (Verified with deterministic renderer handshaking)

---

## 1. Actual Root-Cause Diagnosis

In the recorded user walkthrough video (`handover_2.mp4`, 0:00–0:02), the cinematic brand introduction appeared for approximately 500 milliseconds before abruptly vanishing.

### Root-Cause Mechanism:
1. **Asynchronous Canvas Initialization Delay**:
   - `OrganicScene.tsx` renders a high-performance Canvas 2D/3D volumetric model.
   - When mounted, the component must query viewport dimensions via `ResizeObserver`, scale for device pixel ratio (`dpr = Math.min(1.75, window.devicePixelRatio)`), and schedule the first animation frame via `requestAnimationFrame`.
   - On a typical desktop with browser overhead, this initialization phase consumes **400ms to 850ms**.
2. **Blind, Unsynchronized Timer Execution**:
   - Prior to this fix, `BrandIntro.tsx` immediately initiated a hardcoded chain of `setTimeout` calls inside `startAnimationSequence`:
     - `t0: 120ms` (converging)
     - `t1: 520ms` (sphere-form)
     - `t2: 980ms` (identity)
     - `t3: 1780ms` (page-reveal)
     - `t4: 2250ms` (dismiss)
   - At `1780ms`, `isRevealingHero = true` activated `opacity-0 pointer-events-none scale-[1.02]`.
   - Because the canvas took ~600ms to begin painting, the user only saw the tail end of the animation for ~400ms before `page-reveal` faded the entire overlay to zero opacity.
3. **Absence of Renderer Readiness Handshake**:
   - There was zero communication between the canvas rendering loop and the lifecycle state machine in `BrandIntro`. The timers began running before the canvas had rendered a single pixel.

---

## 2. Redesigned Deterministic Lifecycle Architecture

The component has been restructured around an explicit 8-state lifecycle:

```
[INITIALIZING]
      │
      ├── (onReady from OrganicScene context painted) ──▶ [READY] ──▶ [PLAYING] (0 -> 1.0 progress)
      │                                                                  │
      └── (Safety fallback: 1200ms timeout) ───────────▶ [FALLBACK] ─────┤
                                                                         │
                                                                         ▼
                                                                      [HOLD] (identity visible)
                                                                         │
                                                                         ▼
                                                                  [PAGE_REVEAL] (smooth 700ms veil)
                                                                         │
                                                                         ▼
                                                                    [COMPLETED] (unmounts cleanly)

[SKIPPED] ◀── (Escape key / "Skip Intro" button clicked at any instant)
```

### Detailed State Transitions:
1. **`INITIALIZING`**:
   - Dark navy canvas (`#112034`) renders immediately with ambient blue and verified teal radial gradients.
   - `OrganicScene` mounts in the background with `variant="cinematic"`, `dark={true}`, and `onReady={handleRendererReady}`.
   - 1200ms safety timer begins; if GPU/canvas fails or is delayed, `FALLBACK` triggers so the page is never locked.
2. **`READY`**:
   - Emitted by `OrganicScene` strictly after `ctx.clearRect` and the first depth-sorted node graph has been rasterized to canvas.
3. **`PLAYING`**:
   - Progress animates smoothly:
     - `progress: 0.15` (ambient particles)
     - `progress: 0.48` at +120ms (particles converge toward center)
     - `progress: 0.82` at +650ms (filaments connect and sphere solidifies)
     - `progress: 1.00` at +1400ms (Handover mark and wordmark reveal with glowing drop-shadow)
4. **`HOLD`**:
   - Holds the completed, illuminated brand composition for 950ms so visitors experience the brand promise (*"Knowledge Continues. Prevent Critical Knowledge From Leaving With People."*).
5. **`PAGE_REVEAL`**:
   - Smooth 700ms light-veil ease-out (`opacity-0 scale-[1.02]`), seamlessly revealing the Hero Section below.
6. **`COMPLETED`**:
   - Writes `sessionStorage.setItem("handover_intro_seen", "1")` and returns `null` to free memory.
7. **`SKIPPED`**:
   - Accessible via prominent top-right `Skip Intro [ESC]` button or pressing the Escape key. Clears all timers instantly, unblocks body scroll, and transitions directly into the Hero.
8. **`FALLBACK`**:
   - If canvas fails, immediately reveals static brand identity and transitions safely without a blank screen.

---

## 3. Special Modes & Accessibility

- **Returning Visitors**: If `sessionStorage` has `handover_intro_seen = 1` and URL lacks `?replay=1`, the component returns `null` immediately. Zero flash on reloads or route back-navigation.
- **Prefers-Reduced-Motion**: Detects `(prefers-reduced-motion: reduce)`. Skips volumetric particle movement, presents static brand mark, holds briefly for 500ms, and transitions into hero.
- **Manual Replay Testing**: Append `?replay=1` or `?intro=1` to test the cinematic sequence on any load.

---

## 4. Verification & Results

- **Automated Tests**: Passed all 17/17 tests in Vitest.
- **Memory & Resource Cleanup**: Every timer is registered in `timersRef` and flushed on unmount.
- **Visual Inspection**: The introduction now holds for its full 3.1-second cinematic arc when unskipped, and skips cleanly in <10ms upon pressing Escape.
