"use client";

import React from "react";
import { Loader2 } from "lucide-react";

export interface SectionLoaderProps {
  label?: string;
  size?: "sm" | "md" | "lg";
  className?: string;
  overlay?: boolean;
}

export function SectionLoader({
  label = "Loading...",
  size = "md",
  className = "",
  overlay = false,
}: SectionLoaderProps) {
  const sizeMap = {
    sm: "size-4 text-xs",
    md: "size-5 text-xs",
    lg: "size-7 text-sm",
  };

  const spinnerMap = {
    sm: "size-4",
    md: "size-5",
    lg: "size-7",
  };

  const content = (
    <div
      className={`flex flex-col items-center justify-center gap-2 p-6 text-center select-none ${className}`}
      role="status"
      aria-live="polite"
    >
      <div className="relative flex items-center justify-center">
        <div className="absolute -inset-2 rounded-full bg-[#315FBA]/10 blur-xs animate-pulse" />
        <Loader2 className={`${spinnerMap[size]} text-[#315FBA] animate-spin`} />
      </div>
      {label && (
        <span className={`font-medium text-[#69778D] tracking-tight ${sizeMap[size].split(" ")[1]}`}>
          {label}
        </span>
      )}
    </div>
  );

  if (overlay) {
    return (
      <div className="absolute inset-0 z-20 flex items-center justify-center bg-white/70 backdrop-blur-2xs rounded-xl">
        {content}
      </div>
    );
  }

  return content;
}

export default SectionLoader;
