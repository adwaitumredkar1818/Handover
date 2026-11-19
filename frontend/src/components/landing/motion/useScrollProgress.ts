"use client";

import { useState, useEffect } from "react";

export interface ScrollProgressState {
  progress: number;       // 0 to 1 (document scroll progress)
  scrollY: number;        // Current vertical scroll in pixels
  direction: "up" | "down" | null;
  isScrolled: boolean;    // true if scrollY > 20px (for sticky navbar transition)
  isPastHero: boolean;    // true if scrollY > 420px (for floating back-to-top trigger)
}

/**
 * High-performance scroll progress hook using requestAnimationFrame.
 * Does not thrash layout or perform continuous allocations.
 */
export function useScrollProgress(): ScrollProgressState {
  const [state, setState] = useState<ScrollProgressState>({
    progress: 0,
    scrollY: 0,
    direction: null,
    isScrolled: false,
    isPastHero: false,
  });

  useEffect(() => {
    if (typeof window === "undefined") return;

    let rafId: number | null = null;
    let lastScrollY = window.scrollY;

    const updateScroll = () => {
      const currentScrollY = window.scrollY;
      const docHeight = document.documentElement.scrollHeight - window.innerHeight;
      const progress = docHeight > 0 ? Math.min(1, Math.max(0, currentScrollY / docHeight)) : 0;
      const direction = currentScrollY > lastScrollY ? "down" : currentScrollY < lastScrollY ? "up" : null;

      setState({
        progress,
        scrollY: currentScrollY,
        direction,
        isScrolled: currentScrollY > 20,
        isPastHero: currentScrollY > 420,
      });

      lastScrollY = currentScrollY;
      rafId = null;
    };

    const handleScroll = () => {
      if (rafId === null) {
        rafId = window.requestAnimationFrame(updateScroll);
      }
    };

    // Initial measurement
    updateScroll();

    window.addEventListener("scroll", handleScroll, { passive: true });
    window.addEventListener("resize", handleScroll, { passive: true });

    return () => {
      if (rafId !== null) window.cancelAnimationFrame(rafId);
      window.removeEventListener("scroll", handleScroll);
      window.removeEventListener("resize", handleScroll);
    };
  }, []);

  return state;
}
