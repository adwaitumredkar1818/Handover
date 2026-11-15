"use client";

import React, { useState, useEffect } from "react";
import { Logo } from "./brand";

interface BrandLoadingScreenProps {
  isLoading: boolean;
  message?: string;
}

export function BrandLoadingScreen({
  isLoading,
  message = "Verifying workspace session…",
}: BrandLoadingScreenProps) {
  const [shouldRender, setShouldRender] = useState(isLoading);
  const [isFading, setIsFading] = useState(false);

  useEffect(() => {
    if (isLoading) {
      setShouldRender(true);
      setIsFading(false);
    } else {
      setIsFading(true);
      const timer = setTimeout(() => {
        setShouldRender(false);
        setIsFading(false);
      }, 500);
      return () => clearTimeout(timer);
    }
  }, [isLoading]);

  if (!shouldRender) return null;

  return (
    <div
      className={`fixed inset-0 z-50 flex flex-col items-center justify-center bg-white select-none transition-opacity duration-500 ease-out ${
        isFading ? "opacity-0 pointer-events-none" : "opacity-100 pointer-events-auto"
      }`}
      aria-label="Loading workspace"
      role="status"
      aria-live="polite"
    >
      {/* Subtle Ambient Radial Glow */}
      <div
        className="pointer-events-none absolute inset-0 z-0"
        style={{
          background:
            "radial-gradient(circle 500px at 50% 50%, rgba(49, 95, 186, 0.05), transparent 70%)",
        }}
      />

      {/* Faint Brand Dot Grid */}
      <div
        className="pointer-events-none absolute inset-0 z-0 opacity-40"
        style={{
          backgroundImage: "radial-gradient(#D9E1F0 1px, transparent 1px)",
          backgroundSize: "24px 24px",
        }}
      />

      {/* Center Brand Identity Lockup */}
      <div className="relative z-10 flex flex-col items-center justify-center text-center px-6">
        {/* Logo with Soft Floating Pulse */}
        <div className="relative flex items-center justify-center">
          <div className="absolute -inset-4 rounded-full bg-[#315FBA]/5 blur-lg animate-pulse" />
          <Logo size={36} />
        </div>

        {/* Traveling Synaptic Light Line */}
        <div className="mt-5 relative h-0.5 w-40 bg-[#E8EEF5] rounded-full overflow-hidden">
          <div
            className="absolute inset-y-0 w-20 bg-gradient-to-r from-transparent via-[#315FBA] to-transparent animate-beam"
            style={{ animationDuration: "1.8s" }}
          />
        </div>

        {/* Brand Tagline */}
        <p className="mt-4 font-mono text-[11px] sm:text-[12px] font-semibold uppercase tracking-[0.24em] text-[#7997BE]">
          Knowledge Continues.
        </p>

        {/* Dynamic Status Label */}
        <p className="mt-2 text-xs text-[#69778D] font-medium tracking-tight">
          {message}
        </p>
      </div>
    </div>
  );
}

export default BrandLoadingScreen;
