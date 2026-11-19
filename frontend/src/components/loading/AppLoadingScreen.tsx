"use client";

import React, { useState, useEffect } from "react";
import { Logo } from "../brand/brand";

export interface AppLoadingScreenProps {
  isLoading: boolean;
  message?: string;
  subMessage?: string;
}

export function AppLoadingScreen({
  isLoading,
  message = "Verifying workspace session…",
  subMessage = "Restoring cryptographic credentials and project context",
}: AppLoadingScreenProps) {
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
      className={`fixed inset-0 z-50 flex flex-col items-center justify-center bg-[#F6F8FC] select-none transition-opacity duration-500 ease-out ${
        isFading ? "opacity-0 pointer-events-none" : "opacity-100 pointer-events-auto"
      }`}
      aria-label="Loading workspace"
      role="status"
      aria-live="polite"
    >
      {/* Soft Ambient Radial Glow */}
      <div
        className="pointer-events-none absolute inset-0 z-0"
        style={{
          background:
            "radial-gradient(circle 600px at 50% 50%, rgba(49, 95, 186, 0.08), transparent 70%)",
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

      {/* Organic Floating Synaptic Nodes */}
      <div className="pointer-events-none absolute inset-0 z-0 overflow-hidden" aria-hidden="true">
        <div className="absolute top-1/4 left-1/3 w-2 h-2 rounded-full bg-[#315FBA]/20 animate-pulse" />
        <div className="absolute top-2/3 right-1/4 w-3 h-3 rounded-full bg-[#299B80]/20 animate-pulse" style={{ animationDelay: "0.5s" }} />
        <div className="absolute bottom-1/4 left-1/2 w-2 h-2 rounded-full bg-[#8B78C9]/25 animate-pulse" style={{ animationDelay: "1.2s" }} />
      </div>

      {/* Center Brand Identity Lockup */}
      <div className="relative z-10 flex flex-col items-center justify-center text-center px-6">
        {/* Logo with Soft Floating Pulse */}
        <div className="relative flex items-center justify-center">
          <div className="absolute -inset-4 rounded-full bg-[#315FBA]/10 blur-xl animate-pulse" />
          <Logo size={42} />
        </div>

        {/* Traveling Synaptic Light Line */}
        <div className="mt-6 relative h-1 w-44 bg-[#E2E8F0] rounded-full overflow-hidden shadow-inner">
          <div
            className="absolute inset-y-0 w-24 bg-gradient-to-r from-transparent via-[#315FBA] to-transparent animate-beam"
            style={{ animationDuration: "1.8s" }}
          />
        </div>

        {/* Brand Tagline */}
        <p className="mt-5 font-mono text-[11px] sm:text-[12px] font-semibold uppercase tracking-[0.24em] text-[#315FBA]">
          Knowledge Continues.
        </p>

        {/* Dynamic Status Label */}
        <p className="mt-2 text-sm text-[#203653] font-semibold tracking-tight">
          {message}
        </p>
        {subMessage && (
          <p className="mt-1 text-xs text-[#69778D] font-normal max-w-sm leading-relaxed">
            {subMessage}
          </p>
        )}
      </div>
    </div>
  );
}

export default AppLoadingScreen;
