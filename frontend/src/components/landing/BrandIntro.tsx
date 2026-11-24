"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";
import Image from "next/image";
import { OrganicScene } from "../brand/OrganicScene";

export type IntroLifecycleState =
  | "INITIALIZING"
  | "READY"
  | "PLAYING"
  | "HOLD"
  | "PAGE_REVEAL"
  | "COMPLETED"
  | "SKIPPED"
  | "FALLBACK";

const CONVERGE_DURATION_MS = 2800;
const IDENTITY_REVEAL_MS = 1750;
const TAGLINE_REVEAL_MS = 2150;
const PAGE_REVEAL_MS = 3900;
const DISMISS_MS = 4800;

export function BrandIntro() {
  const [lifecycle, setLifecycle] = useState<IntroLifecycleState>("INITIALIZING");
  const [showLogo, setShowLogo] = useState<boolean>(false);
  const [showTagline, setShowTagline] = useState<boolean>(false);
  const progressRef = useRef<number>(0.02);
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([]);
  const rafRef = useRef<number | null>(null);
  const hasInitializedRef = useRef(false);

  const clearAllTimers = useCallback(() => {
    timersRef.current.forEach(clearTimeout);
    timersRef.current = [];
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
  }, []);

  const restoreBodyScroll = useCallback(() => {
    if (typeof document !== "undefined") {
      document.body.style.overflow = "";
    }
  }, []);

  const dismissIntro = useCallback(
    (isSkip = false) => {
      clearAllTimers();
      setLifecycle(isSkip ? "SKIPPED" : "COMPLETED");
      restoreBodyScroll();
      try {
        sessionStorage.setItem("handover_intro_seen", "1");
      } catch {
        // ignore storage errors
      }
    },
    [clearAllTimers, restoreBodyScroll]
  );

  const runCinematicTimeline = useCallback(
    (reduced: boolean) => {
      clearAllTimers();

      if (reduced) {
        setLifecycle("PLAYING");
        progressRef.current = 1.0;
        setShowLogo(true);
        setShowTagline(true);
        const t1 = setTimeout(() => {
          restoreBodyScroll();
          setLifecycle("PAGE_REVEAL");
        }, 650);
        const t2 = setTimeout(() => dismissIntro(), 1100);
        timersRef.current = [t1, t2];
        return;
      }

      setLifecycle("PLAYING");
      progressRef.current = 0.02;
      setShowLogo(false);
      setShowTagline(false);

      const startTime = performance.now();
      const tick = (now: number) => {
        const elapsed = now - startTime;
        const linear = Math.min(1, elapsed / CONVERGE_DURATION_MS);
        // Smooth cubic ease-in-out for a calm, cinematic convergence & settle
        progressRef.current =
          linear < 0.5
            ? 4 * linear * linear * linear
            : 1 - Math.pow(-2 * linear + 2, 3) / 2;

        if (linear < 1) {
          rafRef.current = requestAnimationFrame(tick);
        } else {
          rafRef.current = null;
        }
      };
      rafRef.current = requestAnimationFrame(tick);

      const tLogo = setTimeout(() => {
        setShowLogo(true);
      }, IDENTITY_REVEAL_MS);

      const tTagline = setTimeout(() => {
        setShowTagline(true);
      }, TAGLINE_REVEAL_MS);

      const tHold = setTimeout(() => {
        progressRef.current = 1.0;
        setLifecycle("HOLD");
      }, CONVERGE_DURATION_MS);

      const tReveal = setTimeout(() => {
        restoreBodyScroll();
        setLifecycle("PAGE_REVEAL");
      }, PAGE_REVEAL_MS);

      const tDismiss = setTimeout(() => {
        dismissIntro();
      }, DISMISS_MS);

      timersRef.current = [tLogo, tTagline, tHold, tReveal, tDismiss];
    },
    [clearAllTimers, dismissIntro, restoreBodyScroll]
  );

  // Renderer readiness callback from OrganicScene canvas context
  const handleRendererReady = useCallback(() => {
    if (hasInitializedRef.current) return;
    hasInitializedRef.current = true;

    const prefersReduced =
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    setLifecycle("READY");
    runCinematicTimeline(prefersReduced);
  }, [runCinematicTimeline]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const forceReplay = params.get("replay") === "1" || params.get("intro") === "1";
    let alreadySeen = false;
    try {
      alreadySeen = sessionStorage.getItem("handover_intro_seen") === "1";
    } catch {
      alreadySeen = false;
    }

    if (alreadySeen && !forceReplay) {
      clearAllTimers();
      restoreBodyScroll();
      setLifecycle("COMPLETED");
      return;
    }

    document.body.style.overflow = "hidden";
    setLifecycle("INITIALIZING");

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        dismissIntro(true);
      }
    };
    window.addEventListener("keydown", onKeyDown);

    // Safety fallback: if renderer does not report readiness within 900ms, start anyway
    const fallbackTimer = setTimeout(() => {
      if (!hasInitializedRef.current) {
        hasInitializedRef.current = true;
        const prefersReduced =
          typeof window !== "undefined" &&
          window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        setLifecycle("FALLBACK");
        runCinematicTimeline(prefersReduced);
      }
    }, 900);

    timersRef.current.push(fallbackTimer);

    return () => {
      window.removeEventListener("keydown", onKeyDown);
      clearAllTimers();
      restoreBodyScroll();
    };
  }, [runCinematicTimeline, clearAllTimers, dismissIntro, restoreBodyScroll]);

  const handleSkip = () => {
    dismissIntro(true);
  };

  if (lifecycle === "COMPLETED" || lifecycle === "SKIPPED") {
    return null;
  }

  const isRevealingHero = lifecycle === "PAGE_REVEAL";
  const identityVisible = showLogo || lifecycle === "HOLD" || lifecycle === "PAGE_REVEAL";
  const taglineVisible = showTagline || lifecycle === "HOLD" || lifecycle === "PAGE_REVEAL";

  return (
    <div
      className={`fixed inset-0 z-50 flex flex-col items-center justify-center overflow-hidden bg-[#112034] transform-gpu will-change-opacity transition-opacity duration-900 ease-in-out select-none ${
        isRevealingHero
          ? "opacity-0 pointer-events-none"
          : "opacity-100 pointer-events-auto"
      }`}
      role="region"
      aria-label="Handover Brand Introduction"
    >
      {/* Subtle Blue & Teal Ambient Glows */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(circle at 50% 48%, rgba(49,95,186,0.34), rgba(41,155,128,0.14) 44%, rgba(17,32,52,0.98) 78%)",
        }}
      />

      {/* Full-Viewport Organic 3D Sphere Emergence powered by OrganicScene */}
      <div className="pointer-events-none absolute inset-0 flex items-center justify-center opacity-95">
        <OrganicScene
          variant="cinematic"
          dark={true}
          progressRef={progressRef}
          showTags={false}
          interactive={false}
          onReady={handleRendererReady}
          className="h-full w-full"
          label="Organic knowledge particles converging into a unified sphere"
        />
      </div>

      {/* Skip Control — Non-blocking at every instant */}
      <button
        type="button"
        onClick={handleSkip}
        className="absolute top-6 right-6 z-20 rounded-full border border-white/20 bg-white/10 px-4 py-1.5 font-mono text-[11px] uppercase tracking-wider text-white hover:bg-white/20 transition cursor-pointer focus-visible:ring-2 focus-visible:ring-[#315FBA] backdrop-blur-xs flex items-center gap-1.5"
        aria-label="Skip brand intro"
      >
        <span>Skip Intro</span>
        <span className="text-[10px] text-white/50 border border-white/20 rounded px-1 py-0.2">
          ESC
        </span>
      </button>

      {/* Brand Identity Reveal */}
      <div className="relative z-10 flex flex-col items-center justify-center text-center px-6 py-8">
        {/* Soft radial scrim to keep logo & typography legible over bright sphere core */}
        <div
          className={`pointer-events-none absolute -inset-x-16 -inset-y-10 -z-10 rounded-full transition-opacity duration-700 ${
            identityVisible ? "opacity-100" : "opacity-0"
          }`}
          style={{
            background:
              "radial-gradient(ellipse 70% 65% at 50% 50%, rgba(17,32,52,0.72) 0%, rgba(17,32,52,0.38) 55%, transparent 100%)",
          }}
        />

        <div
          className={`flex flex-col items-center transform-gpu transition-all duration-700 ease-out ${
            identityVisible
              ? "opacity-100 scale-100 translate-y-0"
              : "opacity-0 scale-95 translate-y-3"
          }`}
        >
          <div className="mb-3.5 flex size-14 items-center justify-center rounded-2xl border border-white/20 bg-white/10 backdrop-blur-md shadow-[0_0_40px_rgba(49,95,186,0.4)]">
            <Image
              src="/handover-mark.png"
              alt="Handover Symbol"
              width={40}
              height={40}
              priority
              className="h-7 w-auto object-contain brightness-0 invert"
            />
          </div>
          <Image
            src="/handover-logo.png"
            alt="Handover"
            width={176}
            height={44}
            priority
            className="h-10 sm:h-12 w-auto object-contain brightness-0 invert drop-shadow-[0_4px_24px_rgba(17,32,52,0.85)]"
          />
        </div>

        <p
          className={`mt-4 font-mono text-[11px] sm:text-[12px] font-semibold uppercase tracking-[0.24em] text-[#B8B4E8] drop-shadow-[0_2px_10px_rgba(17,32,52,0.9)] transform-gpu transition-all duration-500 ease-out ${
            taglineVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-2"
          }`}
        >
          Knowledge Continues.
        </p>
        <p
          className={`mt-1.5 text-[12.5px] sm:text-[13px] text-[#DCE6F4] drop-shadow-[0_2px_10px_rgba(17,32,52,0.9)] transform-gpu transition-all duration-500 delay-75 ease-out ${
            taglineVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-1.5"
          }`}
        >
          Prevent Critical Knowledge From Leaving With People.
        </p>
      </div>
    </div>
  );
}

export default BrandIntro;
