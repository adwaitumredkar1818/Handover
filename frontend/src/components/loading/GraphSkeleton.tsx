"use client";

import React from "react";
import { Share2, Sparkles } from "lucide-react";

export interface GraphSkeletonProps {
  label?: string;
  className?: string;
}

export function GraphSkeleton({
  label = "Computing knowledge relationships...",
  className = "",
}: GraphSkeletonProps) {
  return (
    <div
      className={`relative w-full h-[550px] min-h-[400px] rounded-xl border border-[#DCE3EB] bg-[#F8FAFC] overflow-hidden flex items-center justify-center select-none ${className}`}
      role="status"
      aria-label={label}
    >
      {/* Subtle Dot Grid Background */}
      <div
        className="pointer-events-none absolute inset-0 z-0 opacity-40"
        style={{
          backgroundImage: "radial-gradient(#CBD5E1 1px, transparent 1px)",
          backgroundSize: "20px 20px",
        }}
      />

      {/* SVG Connecting Lines Placeholder */}
      <svg
        className="absolute inset-0 w-full h-full pointer-events-none"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
      >
        <line
          x1="50%"
          y1="50%"
          x2="25%"
          y2="30%"
          stroke="#E2E8F0"
          strokeWidth="2"
          strokeDasharray="4 4"
        />
        <line
          x1="50%"
          y1="50%"
          x2="75%"
          y2="30%"
          stroke="#E2E8F0"
          strokeWidth="2"
          strokeDasharray="4 4"
        />
        <line
          x1="50%"
          y1="50%"
          x2="20%"
          y2="70%"
          stroke="#E2E8F0"
          strokeWidth="2"
          strokeDasharray="4 4"
        />
        <line
          x1="50%"
          y1="50%"
          x2="80%"
          y2="70%"
          stroke="#E2E8F0"
          strokeWidth="2"
          strokeDasharray="4 4"
        />
        <line
          x1="50%"
          y1="50%"
          x2="50%"
          y2="20%"
          stroke="#E2E8F0"
          strokeWidth="2"
          strokeDasharray="4 4"
        />
      </svg>

      {/* Satellite Placeholder Nodes */}
      <div className="absolute top-[30%] left-[25%] -translate-x-1/2 -translate-y-1/2 p-2 rounded-lg bg-white border border-[#E2E8F0] shadow-2xs animate-pulse">
        <div className="h-3 w-20 bg-[#E2E8F0] rounded" />
      </div>
      <div className="absolute top-[30%] right-[25%] translate-x-1/2 -translate-y-1/2 p-2 rounded-lg bg-white border border-[#E2E8F0] shadow-2xs animate-pulse">
        <div className="h-3 w-24 bg-[#E2E8F0] rounded" />
      </div>
      <div className="absolute bottom-[30%] left-[20%] -translate-x-1/2 translate-y-1/2 p-2 rounded-lg bg-white border border-[#E2E8F0] shadow-2xs animate-pulse">
        <div className="h-3 w-20 bg-[#E2E8F0] rounded" />
      </div>
      <div className="absolute bottom-[30%] right-[20%] translate-x-1/2 translate-y-1/2 p-2 rounded-lg bg-white border border-[#E2E8F0] shadow-2xs animate-pulse">
        <div className="h-3 w-28 bg-[#E2E8F0] rounded" />
      </div>
      <div className="absolute top-[20%] left-1/2 -translate-x-1/2 -translate-y-1/2 p-2 rounded-lg bg-white border border-[#E2E8F0] shadow-2xs animate-pulse">
        <div className="h-3 w-16 bg-[#E2E8F0] rounded" />
      </div>

      {/* Central Knowledge Node */}
      <div className="relative z-10 flex flex-col items-center">
        <div className="relative flex items-center justify-center">
          <div className="absolute -inset-4 rounded-full bg-[#315FBA]/10 blur-md animate-ping" style={{ animationDuration: "3s" }} />
          <div className="w-16 h-16 rounded-2xl bg-white border-2 border-[#315FBA] shadow-md flex items-center justify-center text-[#315FBA]">
            <Share2 className="w-7 h-7 animate-pulse text-[#315FBA]" />
          </div>
        </div>

        {/* Status Pill Badge */}
        <div className="mt-4 px-3.5 py-1.5 rounded-full bg-white/90 backdrop-blur-xs border border-[#DCE3EB] shadow-2xs flex items-center gap-2 text-xs font-semibold text-[#203653]">
          <Sparkles className="w-3.5 h-3.5 text-[#315FBA] animate-spin" style={{ animationDuration: "4s" }} />
          <span>{label}</span>
        </div>
      </div>
    </div>
  );
}

export default GraphSkeleton;
