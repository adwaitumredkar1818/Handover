"use client";

import React from "react";
import { useScrollProgress } from "./motion/useScrollProgress";
import { useReducedMotion } from "./motion/useReducedMotion";

/**
 * Global Reading Progress Bar
 *
 * Fixed 2.5px height indicator at the top of the viewport.
 * Uses hardware-accelerated `transform: scaleX(...)` with `transformOrigin: "left"`
 * to ensure zero reflows and smooth 60fps tracking.
 */
export function ReadingProgressBar() {
  const { progress } = useScrollProgress();
  const reducedMotion = useReducedMotion();

  if (reducedMotion) return null;

  return (
    <div
      className="fixed top-0 left-0 right-0 z-50 h-[2.5px] w-full pointer-events-none bg-slate-200/20"
      aria-hidden="true"
    >
      <div
        className="h-full w-full bg-gradient-to-r from-[#315FBA] via-[#8B78C9] to-[#0D9488] transition-transform duration-75 ease-out origin-left shadow-[0_0_8px_rgba(49,95,186,0.35)]"
        style={{
          transform: `scaleX(${progress})`,
        }}
      />
    </div>
  );
}
