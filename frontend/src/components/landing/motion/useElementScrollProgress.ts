"use client";

import { useEffect, useRef, useState } from "react";
import { useReducedMotion } from "./useReducedMotion";

export interface ElementScrollOptions {
  /** Offset factor relative to viewport height when tracking starts/ends */
  startOffset?: number;
  endOffset?: number;
}

export interface ElementScrollState<T extends HTMLElement> {
  ref: React.RefObject<T | null>;
  /** Normalized scroll progression through the element (0.0 -> 1.0) */
  progress: number;
  /** True when the element is intersecting or passing through the viewport */
  isInView: boolean;
}

/**
 * Tracks an element's scroll progression (0 -> 1) cleanly via requestAnimationFrame.
 * Ideal for sticky storytelling sections, scroll-driven canvas morphing, and dossier assembly.
 * Respects `prefers-reduced-motion: reduce` by returning static completion state (`progress: 1`).
 */
export function useElementScrollProgress<T extends HTMLElement>(
  options: ElementScrollOptions = {}
): ElementScrollState<T> {
  const { startOffset = 0.85, endOffset = 0.2 } = options;
  const ref = useRef<T | null>(null);
  const reducedMotion = useReducedMotion();
  const [state, setState] = useState<{ progress: number; isInView: boolean }>({
    progress: reducedMotion ? 1 : 0,
    isInView: false,
  });

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (reducedMotion) {
      setState({ progress: 1, isInView: true });
      return;
    }

    let rafId: number | null = null;
    let lastProgress = -1;
    let lastInView = false;

    const measure = () => {
      rafId = null;
      const el = ref.current;
      if (!el) return;

      const rect = el.getBoundingClientRect();
      const vh = window.innerHeight || 800;

      // In non-layout environments (e.g. JSDOM tests) rect height/width are 0: keep initial progress at 0
      if (rect.height <= 0 && rect.width <= 0) {
        if (lastProgress !== 0 || lastInView !== false) {
          lastProgress = 0;
          lastInView = false;
          setState({ progress: 0, isInView: false });
        }
        return;
      }

      const isInView = rect.top < vh && rect.bottom > 0;
      const totalTravel = Math.max(1, rect.height + vh * (startOffset - endOffset));
      const traveled = vh * startOffset - rect.top;
      const raw = traveled / totalTravel;
      const progress = Math.max(0, Math.min(1, Number(raw.toFixed(3))));

      if (Math.abs(progress - lastProgress) >= 0.005 || isInView !== lastInView) {
        lastProgress = progress;
        lastInView = isInView;
        setState({ progress, isInView });
      }
    };

    const scheduleMeasure = () => {
      if (rafId === null) {
        rafId = window.requestAnimationFrame(measure);
      }
    };

    measure();
    window.addEventListener("scroll", scheduleMeasure, { passive: true });
    window.addEventListener("resize", scheduleMeasure, { passive: true });

    return () => {
      if (rafId !== null) window.cancelAnimationFrame(rafId);
      window.removeEventListener("scroll", scheduleMeasure);
      window.removeEventListener("resize", scheduleMeasure);
    };
  }, [startOffset, endOffset, reducedMotion]);

  return {
    ref,
    progress: reducedMotion ? 1 : state.progress,
    isInView: reducedMotion ? true : state.isInView,
  };
}
