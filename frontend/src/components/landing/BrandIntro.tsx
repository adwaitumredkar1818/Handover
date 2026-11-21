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

export function BrandIntro() {
  const [lifecycle, setLifecycle] = useState<IntroLifecycleState>("COMPLETED");
  const [progress, setProgress] = useState<number>(0.08);
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([]);
  const hasInitializedRef = useRef(false);

  const clearAllTimers = useCallback(() => {
    timersRef.current.forEach(clearTimeout);
    timersRef.current = [];
  }, []);

  const dismissIntro = useCallback((isSkip = false) => {
    clearAllTimers();
    setLifecycle(isSkip ? "SKIPPED" : "COMPLETED");
    document.body.style.overflow = "";
    try {
      sessionStorage.setItem("handover_intro_seen", "1");
    } catch {
      // ignore storage errors
    }
  }, [clearAllTimers]);

  const runCinematicTimeline = useCallback((reduced: boolean) => {
    clearAllTimers();

    if (reduced) {
      setLifecycle("PLAYING");
      setProgress(1.0);
      const t1 = setTimeout(() => setLifecycle("PAGE_REVEAL"), 500);
      const t2 = setTimeout(() => dismissIntro(), 900);
      timersRef.current = [t1, t2];
      return;
    }

    setLifecycle("PLAYING");
    setProgress(0.15);

    // Stately, cinematic 3.2s timeline synchronized to renderer readiness
    // 1. Particles converge toward center & filaments emerge (0 -> 600ms)
    const t0 = setTimeout(() => {
      setProgress(0.48);
    }, 120);

    // 2. Organic knowledge sphere forms & stabilizes (600ms -> 1350ms)
    const t1 = setTimeout(() => {
      setProgress(0.82);
    }, 650);

    // 3. Handover identity and mark illuminate (1350ms -> 2150ms)
    const t2 = setTimeout(() => {
      setProgress(1.0);
      setLifecycle("HOLD");
    }, 1400);

    // 4. Completed scene holds briefly for cognitive absorption (2150ms -> 2650ms)
    const t3 = setTimeout(() => {
      setLifecycle("PAGE_REVEAL");
    }, 2350);

    // 5. Smooth light veil transition into Hero section (2650ms -> 3150ms)
    const t4 = setTimeout(() => {
      dismissIntro();
    }, 3100);

    timersRef.current = [t0, t1, t2, t3, t4];
  }, [clearAllTimers, dismissIntro]);

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
    if (!forceReplay) {
      setLifecycle("COMPLETED");
      return;
    }
    setLifecycle("INITIALIZING");

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        dismissIntro(true);
      }
    };
    window.addEventListener("keydown", onKeyDown);

    // Safety fallback: if renderer does not report readiness within 1200ms, start anyway
    const fallbackTimer = setTimeout(() => {
      if (!hasInitializedRef.current) {
        hasInitializedRef.current = true;
        const prefersReduced =
          typeof window !== "undefined" &&
          window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        setLifecycle("FALLBACK");
        runCinematicTimeline(prefersReduced);
      }
    }, 1200);

    timersRef.current.push(fallbackTimer);

    return () => {
      window.removeEventListener("keydown", onKeyDown);
      clearAllTimers();
    };
  }, [runCinematicTimeline, clearAllTimers, dismissIntro]);

  const handleSkip = () => {
    dismissIntro(true);
  };

  if (lifecycle === "COMPLETED" || lifecycle === "SKIPPED") {
    return null;
  }

  const isRevealingHero = lifecycle === "PAGE_REVEAL";
  const showIdentity =
    lifecycle === "HOLD" ||
    lifecycle === "PAGE_REVEAL" ||
    (lifecycle === "PLAYING" && progress >= 0.8);

  return (
    <div
      className={`fixed inset-0 z-50 flex flex-col items-center justify-center overflow-hidden bg-[#112034] transition-all duration-700 ease-out select-none ${
        isRevealingHero ? "opacity-0 pointer-events-none scale-[1.02]" : "opacity-100 pointer-events-auto"
      }`}
      role="region"
      aria-label="Handover Brand Introduction"
    >
      {/* Subtle Blue & Teal Ambient Glows */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(circle at 50% 45%, rgba(49,95,186,0.32), rgba(41,155,128,0.12) 45%, rgba(17,32,52,0.98) 78%)",
        }}
      />

      {/* Organic 3D Sphere Emergence powered by OrganicScene */}
      <div className="pointer-events-none absolute inset-0 flex items-center justify-center opacity-90">
        <OrganicScene
          variant="cinematic"
          dark={true}
          progress={progress}
          showTags={false}
          interactive={false}
          onReady={handleRendererReady}
          className="h-full w-full max-w-[960px] max-h-[760px]"
          label="Organic knowledge particles converging into a unified sphere"
        />
      </div>

      {/* Skip Control — Non-blocking at every instant */}
      <button
        onClick={handleSkip}
        className="absolute top-6 right-6 z-20 rounded-full border border-white/20 bg-white/10 px-4 py-1.5 font-mono text-[11px] uppercase tracking-wider text-white hover:bg-white/20 transition cursor-pointer focus-visible:ring-2 focus-visible:ring-[#315FBA] backdrop-blur-xs flex items-center gap-1.5"
        aria-label="Skip brand intro"
      >
        <span>Skip Intro</span>
        <span className="text-[10px] text-white/50 border border-white/20 rounded px-1 py-0.2">ESC</span>
      </button>

      {/* Brand Identity Reveal */}
      <div className="relative z-10 flex flex-col items-center justify-center text-center px-6">
        <div
          className={`flex flex-col items-center transition-all duration-700 ease-out ${
            showIdentity
              ? "opacity-100 scale-100 translate-y-0"
              : "opacity-0 scale-95 translate-y-2"
          }`}
        >
          <div className="mb-3 flex size-14 items-center justify-center rounded-2xl border border-white/15 bg-white/5 backdrop-blur-md shadow-[0_0_40px_rgba(49,95,186,0.35)]">
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
            className="h-10 sm:h-12 w-auto object-contain brightness-0 invert drop-shadow-[0_4px_20px_rgba(49,95,186,0.35)]"
          />
        </div>

        <p
          className={`mt-4 font-mono text-[11px] sm:text-[12px] font-semibold uppercase tracking-[0.24em] text-[#A5A0D9] transition-all duration-500 ease-out ${
            showIdentity
              ? "opacity-100 translate-y-0"
              : "opacity-0 translate-y-2"
          }`}
        >
          Knowledge Continues.
        </p>
        <p
          className={`mt-1.5 text-[12px] text-[#c3cfe0]/75 transition-all duration-500 delay-75 ease-out ${
            showIdentity
              ? "opacity-100 translate-y-0"
              : "opacity-0 translate-y-1"
          }`}
        >
          Prevent Critical Knowledge From Leaving With People.
        </p>
      </div>
    </div>
  );
}

export default BrandIntro;
