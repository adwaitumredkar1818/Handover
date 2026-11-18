"use client";

import React from "react";
import { ArrowUp } from "lucide-react";
import { useScrollProgress } from "./motion/useScrollProgress";
import { useReducedMotion } from "./motion/useReducedMotion";

/**
 * Floating Back-to-Top Control
 *
 * Appears smoothly once user scrolls past the hero section (> 420px).
 * Safely handles smooth scroll-to-top with keyboard accessibility.
 */
export function BackToTop() {
  const { isPastHero } = useScrollProgress();
  const reducedMotion = useReducedMotion();

  const scrollToTop = () => {
    window.scrollTo({
      top: 0,
      behavior: reducedMotion ? "auto" : "smooth",
    });
  };

  return (
    <button
      type="button"
      onClick={scrollToTop}
      aria-label="Back to top of page"
      className={`fixed bottom-6 right-6 z-40 flex size-11 items-center justify-center rounded-full border border-[#D9E1F0] bg-white/95 text-[#203653] shadow-card backdrop-blur-md transition-all duration-300 hover:border-[#315FBA] hover:bg-white hover:text-[#315FBA] hover:shadow-pop focus-visible:outline-2 focus-visible:outline-[#315FBA] active:scale-95 ${
        isPastHero
          ? "opacity-100 translate-y-0 pointer-events-auto"
          : "opacity-0 translate-y-4 pointer-events-none"
      }`}
    >
      <ArrowUp className="size-4 transition-transform duration-200 group-hover:-translate-y-0.5" />
    </button>
  );
}
