"use client";

import { useEffect, useRef } from "react";
import { useReducedMotion } from "./useReducedMotion";

export interface SectionRevealOptions {
  threshold?: number;
  rootMargin?: string;
  staggerDelayMs?: number;
  once?: boolean;
}

/**
 * Enhanced scroll reveal hook.
 *
 * Attaches an IntersectionObserver to a section container.
 * Any descendant with `.reveal`, `.reveal-left`, `.reveal-right`,
 * `.reveal-scale`, or `.reveal-clip` receives the `.is-in` class
 * when it scrolls into view.
 *
 * Automatically handles stagger delays if children have `data-stagger`
 * or when `staggerDelayMs` is provided.
 *
 * Disconnects immediately once all elements have entered view.
 */
export function useSectionReveal<T extends HTMLElement>(options: SectionRevealOptions = {}) {
  const ref = useRef<T>(null);
  const reducedMotion = useReducedMotion();
  const { threshold = 0.12, rootMargin = "0px 0px -40px 0px", staggerDelayMs = 0, once = true } = options;

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const targets = el.querySelectorAll<HTMLElement>(
      ".reveal, .reveal-left, .reveal-right, .reveal-scale, .reveal-clip, .reveal-stagger"
    );

    if (targets.length === 0) return;

    if (reducedMotion) {
      targets.forEach((target) => {
        target.classList.add("is-in");
      });
      return;
    }

    let remainingCount = targets.length;

    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            const target = entry.target as HTMLElement;
            const staggerIndex = target.getAttribute("data-stagger-index");
            const delay = staggerIndex ? Number(staggerIndex) * 80 : staggerDelayMs;

            if (delay > 0) {
              window.setTimeout(() => {
                target.classList.add("is-in");
              }, delay);
            } else {
              target.classList.add("is-in");
            }

            if (once) {
              io.unobserve(target);
              remainingCount--;
              if (remainingCount <= 0) {
                io.disconnect();
              }
            }
          }
        });
      },
      { threshold, rootMargin }
    );

    targets.forEach((n) => io.observe(n));

    return () => io.disconnect();
  }, [threshold, rootMargin, staggerDelayMs, once, reducedMotion]);

  return ref;
}
