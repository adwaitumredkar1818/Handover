import React from "react";

export interface CardSkeletonProps {
  variant?: "metric" | "domain" | "project" | "default";
  count?: number;
  className?: string;
}

export function CardSkeleton({
  variant = "default",
  count = 1,
  className = "",
}: CardSkeletonProps) {
  const items = Array.from({ length: count }, (_, i) => i);

  if (variant === "metric") {
    return (
      <>
        {items.map((i) => (
          <div
            key={i}
            className={`p-4 rounded-xl border border-[#DCE3EB] bg-white shadow-2xs animate-pulse ${className}`}
            aria-hidden="true"
          >
            <div className="flex items-center justify-between mb-2">
              <div className="h-3 w-24 bg-[#E2E8F0] rounded" />
              <div className="w-5 h-5 bg-[#E2E8F0] rounded-full" />
            </div>
            <div className="h-7 w-20 bg-[#CBD5E1] rounded mb-1.5" />
            <div className="h-2.5 w-32 bg-[#E2E8F0] rounded" />
          </div>
        ))}
      </>
    );
  }

  if (variant === "domain") {
    return (
      <>
        {items.map((i) => (
          <div
            key={i}
            className={`p-4 rounded-xl border border-[#DCE3EB] bg-white shadow-2xs animate-pulse space-y-3 ${className}`}
            aria-hidden="true"
          >
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-[#E2E8F0]" />
                <div className="space-y-1">
                  <div className="h-3.5 w-32 bg-[#CBD5E1] rounded" />
                  <div className="h-2.5 w-20 bg-[#E2E8F0] rounded" />
                </div>
              </div>
              <div className="h-5 w-12 bg-[#E2E8F0] rounded-full" />
            </div>
            <div className="h-2.5 w-full bg-[#F1F5F9] rounded" />
            <div className="flex items-center justify-between pt-2 border-t border-[#F1F5F9]">
              <div className="h-2.5 w-24 bg-[#E2E8F0] rounded" />
              <div className="h-3 w-3 bg-[#E2E8F0] rounded" />
            </div>
          </div>
        ))}
      </>
    );
  }

  if (variant === "project") {
    return (
      <>
        {items.map((i) => (
          <div
            key={i}
            className={`p-5 rounded-xl border border-[#DCE3EB] bg-white shadow-2xs animate-pulse space-y-4 ${className}`}
            aria-hidden="true"
          >
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-[#E2E8F0]" />
                <div className="space-y-1.5">
                  <div className="h-4 w-40 bg-[#CBD5E1] rounded" />
                  <div className="h-3 w-24 bg-[#E2E8F0] rounded" />
                </div>
              </div>
              <div className="h-5 w-16 bg-[#E2E8F0] rounded-full" />
            </div>
            <div className="space-y-1.5">
              <div className="h-2.5 w-full bg-[#F1F5F9] rounded" />
              <div className="h-2.5 w-4/5 bg-[#F1F5F9] rounded" />
            </div>
            <div className="flex items-center justify-between pt-3 border-t border-[#F1F5F9]">
              <div className="h-3 w-28 bg-[#E2E8F0] rounded" />
              <div className="h-7 w-20 bg-[#E2E8F0] rounded-lg" />
            </div>
          </div>
        ))}
      </>
    );
  }

  // Default Card Skeleton
  return (
    <>
      {items.map((i) => (
        <div
          key={i}
          className={`p-5 rounded-xl border border-[#DCE3EB] bg-white shadow-2xs animate-pulse space-y-3 ${className}`}
          aria-hidden="true"
        >
          <div className="h-4 w-1/3 bg-[#CBD5E1] rounded" />
          <div className="space-y-2">
            <div className="h-3 w-full bg-[#E2E8F0] rounded" />
            <div className="h-3 w-5/6 bg-[#E2E8F0] rounded" />
          </div>
          <div className="h-8 w-24 bg-[#E2E8F0] rounded-lg mt-2" />
        </div>
      ))}
    </>
  );
}

export default CardSkeleton;
