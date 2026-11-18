"use client";

import React from "react";
import { useReducedMotion } from "./useReducedMotion";

export interface AnimatedConnectorProps {
  /** SVG viewBox coordinates for line or cubic curve */
  d: string;
  stroke?: string;
  active?: boolean;
  highlightColor?: string;
  width?: number;
  dashed?: boolean;
  showPulse?: boolean;
  pulseDuration?: string;
  className?: string;
  viewBox?: string;
}

/**
 * Reusable organic SVG filament connector with optional traveling knowledge pulse
 * and draw-in motion, with clean static rendering under `prefers-reduced-motion`.
 */
export function AnimatedConnector({
  d,
  stroke = "#D9E1F0",
  active = false,
  highlightColor = "#315FBA",
  width = 1.5,
  dashed = false,
  showPulse = true,
  pulseDuration = "2.2s",
  className = "",
  viewBox = "0 0 120 24",
}: AnimatedConnectorProps) {
  const reducedMotion = useReducedMotion();

  return (
    <svg
      viewBox={viewBox}
      fill="none"
      className={`overflow-visible ${className}`}
      aria-hidden="true"
    >
      <path
        d={d}
        stroke={active ? highlightColor : stroke}
        strokeOpacity={active ? 0.85 : 0.75}
        strokeWidth={active ? width + 0.5 : width}
        strokeDasharray={dashed && !active ? "4 5" : undefined}
        className={`transition-colors duration-300 ${
          active && !reducedMotion ? "animate-stream-flow" : ""
        }`}
      />
      {showPulse && active && !reducedMotion && (
        <circle r={width + 1.4} fill={highlightColor} opacity="0.95">
          <animateMotion path={d} dur={pulseDuration} repeatCount="indefinite" />
        </circle>
      )}
    </svg>
  );
}
