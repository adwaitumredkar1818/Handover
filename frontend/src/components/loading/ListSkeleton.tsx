import React from "react";

export interface ListSkeletonProps {
  variant?: "activity" | "thread" | "source" | "default";
  count?: number;
  className?: string;
}

export function ListSkeleton({
  variant = "default",
  count = 4,
  className = "",
}: ListSkeletonProps) {
  const items = Array.from({ length: count }, (_, i) => i);

  if (variant === "activity") {
    return (
      <div className={`space-y-4 animate-pulse ${className}`} aria-hidden="true">
        {items.map((i) => (
          <div key={i} className="flex items-start gap-3">
            <div className="w-7 h-7 rounded-full bg-[#E2E8F0] shrink-0 mt-0.5" />
            <div className="flex-1 space-y-1.5 min-w-0">
              <div className="flex items-center justify-between">
                <div className="h-3 w-40 bg-[#CBD5E1] rounded" />
                <div className="h-2.5 w-16 bg-[#E2E8F0] rounded" />
              </div>
              <div className="h-2.5 w-3/4 bg-[#F1F5F9] rounded" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (variant === "thread") {
    return (
      <div className={`space-y-2 animate-pulse ${className}`} aria-hidden="true">
        {items.map((i) => (
          <div
            key={i}
            className="p-3 rounded-lg border border-[#E2E8F0] bg-white space-y-2"
          >
            <div className="flex items-center justify-between">
              <div className="h-3.5 w-36 bg-[#CBD5E1] rounded" />
              <div className="h-2 w-12 bg-[#E2E8F0] rounded" />
            </div>
            <div className="h-2.5 w-24 bg-[#F1F5F9] rounded" />
          </div>
        ))}
      </div>
    );
  }

  if (variant === "source") {
    return (
      <div className={`space-y-3 animate-pulse ${className}`} aria-hidden="true">
        {items.map((i) => (
          <div
            key={i}
            className="p-3.5 rounded-xl border border-[#DCE3EB] bg-white space-y-3"
          >
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-[#E2E8F0]" />
                <div className="space-y-1">
                  <div className="h-3.5 w-28 bg-[#CBD5E1] rounded" />
                  <div className="h-2 w-20 bg-[#E2E8F0] rounded" />
                </div>
              </div>
              <div className="h-4 w-12 bg-[#E2E8F0] rounded-full" />
            </div>
            <div className="h-7 w-full bg-[#F1F5F9] rounded-lg" />
          </div>
        ))}
      </div>
    );
  }

  // Default List
  return (
    <div className={`divide-y divide-[#F1F5F9] animate-pulse ${className}`} aria-hidden="true">
      {items.map((i) => (
        <div key={i} className="py-3 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0 flex-1">
            <div className="w-8 h-8 rounded-lg bg-[#E2E8F0] shrink-0" />
            <div className="space-y-1 flex-1 min-w-0">
              <div className="h-3 w-48 bg-[#CBD5E1] rounded" />
              <div className="h-2.5 w-28 bg-[#E2E8F0] rounded" />
            </div>
          </div>
          <div className="h-6 w-16 bg-[#E2E8F0] rounded shrink-0" />
        </div>
      ))}
    </div>
  );
}

export default ListSkeleton;
