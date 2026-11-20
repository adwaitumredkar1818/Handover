"use client";

import React, { useRef, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";

export interface ButtonLoaderProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  isLoading?: boolean;
  loadingText?: string;
  children: React.ReactNode;
  icon?: React.ReactNode;
  variant?: "primary" | "secondary" | "danger" | "ghost" | "teal" | "outline";
}

export function ButtonLoader({
  isLoading = false,
  loadingText,
  children,
  icon,
  variant = "primary",
  className = "",
  disabled,
  onClick,
  ...props
}: ButtonLoaderProps) {
  const buttonRef = useRef<HTMLButtonElement>(null);
  const [minWidth, setMinWidth] = useState<number | undefined>(undefined);

  // Measure initial resolved button width to keep button width rock-solid during loading
  useEffect(() => {
    if (buttonRef.current && !isLoading && minWidth === undefined) {
      const currentWidth = buttonRef.current.getBoundingClientRect().width;
      if (currentWidth > 0) {
        setMinWidth(currentWidth);
      }
    }
  }, [isLoading, minWidth, children]);

  const variantStyles = {
    primary:
      "bg-[#315FBA] hover:bg-[#254A94] text-white border-transparent focus:ring-[#315FBA]/40",
    secondary:
      "bg-[#F0F4F9] hover:bg-[#E2EAF4] text-[#203653] border-[#DCE3EB] focus:ring-[#315FBA]/20",
    teal:
      "bg-[#299B80] hover:bg-[#1E7762] text-white border-transparent focus:ring-[#299B80]/40",
    danger:
      "bg-rose-600 hover:bg-rose-700 text-white border-transparent focus:ring-rose-500/40",
    outline:
      "bg-transparent hover:bg-[#F8FAFC] text-[#203653] border border-[#DCE3EB] focus:ring-[#315FBA]/20",
    ghost:
      "bg-transparent hover:bg-[#F0F4F9] text-[#69778D] hover:text-[#203653] border-transparent",
  };

  return (
    <button
      ref={buttonRef}
      disabled={isLoading || disabled}
      aria-busy={isLoading}
      onClick={isLoading ? undefined : onClick}
      style={minWidth ? { minWidth: `${minWidth}px` } : undefined}
      className={`relative inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg font-semibold text-xs border transition-all duration-150 select-none cursor-pointer focus:outline-none focus:ring-2 disabled:opacity-60 disabled:cursor-not-allowed shadow-2xs ${
        variantStyles[variant]
      } ${className}`}
      {...props}
    >
      {isLoading ? (
        <>
          <Loader2 className="w-3.5 h-3.5 animate-spin shrink-0" />
          <span>{loadingText || children}</span>
        </>
      ) : (
        <>
          {icon && <span className="shrink-0">{icon}</span>}
          <span>{children}</span>
        </>
      )}
    </button>
  );
}

export default ButtonLoader;
