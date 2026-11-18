"use client";

import { useSectionReveal, SectionRevealOptions } from "../motion/useSectionReveal";

/**
 * Shared scroll-reveal hook.
 *
 * Returns a ref to attach to a container element.
 * Any descendant with `.reveal`, `.reveal-left`, `.reveal-right`, etc.
 * receives the `is-in` class once it enters view.
 *
 * Uses IntersectionObserver; observed elements are unobserved after entrance
 * so there is zero per-frame cost.
 */
export function useReveal<T extends HTMLElement>(options?: SectionRevealOptions) {
  return useSectionReveal<T>(options);
}
