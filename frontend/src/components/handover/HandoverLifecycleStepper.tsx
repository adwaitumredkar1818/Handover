"use client";

import React from "react";
import { Check, Clock } from "lucide-react";
import { cn, Tooltip } from "../figma-ui/index";

export interface LifecycleStageMeta {
  key: string;
  label: string;
  description: string;
  timestamp?: string | null;
}

export const CANONICAL_LIFECYCLE_STAGES: readonly LifecycleStageMeta[] = [
  {
    key: "draft",
    label: "Draft",
    description: "Initial knowledge capture and package structuring.",
  },
  {
    key: "in_progress",
    label: "Verification",
    description: "Human review of extracted findings and conflict resolution.",
  },
  {
    key: "pending_review",
    label: "Manager Review",
    description: "Formal readiness review by project leadership.",
  },
  {
    key: "approved",
    label: "Approved",
    description: "Sign-off recorded by designated project reviewer.",
  },
  {
    key: "published",
    label: "Published",
    description: "Handover package locked, cryptographically hashed, and delivered.",
  },
  {
    key: "completed",
    label: "Acknowledged",
    description: "Incoming successor has reviewed and confirmed receipt.",
  },
] as const;

interface HandoverLifecycleStepperProps {
  currentStatus: string;
  createdDate?: string | null;
  assembledDate?: string | null;
  publishedDate?: string | null;
  acknowledgedDate?: string | null;
  className?: string;
}

export function HandoverLifecycleStepper({
  currentStatus,
  createdDate,
  assembledDate,
  publishedDate,
  acknowledgedDate,
  className,
}: HandoverLifecycleStepperProps) {
  const normalizedStatus = (currentStatus || "").toLowerCase();
  const currentIdx = CANONICAL_LIFECYCLE_STAGES.findIndex(
    (s) => s.key === normalizedStatus
  );
  const activeIdx = currentIdx >= 0 ? currentIdx : 0;

  // Real timestamps mapped to stages (zero fabrication)
  const stageDateMap: Record<string, string | undefined | null> = {
    draft: createdDate,
    in_progress: assembledDate,
    published: publishedDate,
    completed: acknowledgedDate,
  };

  const activeStage =
    CANONICAL_LIFECYCLE_STAGES[activeIdx] ?? CANONICAL_LIFECYCLE_STAGES[0]!;

  return (
    <div className={cn("w-full select-none", className)}>
      {/* Mobile/Compact view (< 640px) */}
      <div className="flex flex-col gap-2 sm:hidden">
        <div className="flex items-center justify-between text-xs">
          <span className="font-semibold text-slate-500 uppercase tracking-wider text-[11px]">
            Lifecycle Stage {activeIdx + 1} of {CANONICAL_LIFECYCLE_STAGES.length}
          </span>
          <span className="inline-flex items-center gap-1 font-semibold text-blue-700 bg-blue-50 px-2 py-0.5 rounded-full border border-blue-200/60">
            <span className="size-1.5 rounded-full bg-blue-600 animate-pulse" />
            {activeStage.label}
          </span>
        </div>
        <div className="grid grid-cols-6 gap-1.5">
          {CANONICAL_LIFECYCLE_STAGES.map((stage, i) => {
            const isCompleted = i < activeIdx;
            const isCurrent = i === activeIdx;
            return (
              <Tooltip
                key={stage.key}
                content={`${stage.label}: ${stage.description}`}
              >
                <div
                  className={cn(
                    "h-2 rounded-full transition-all duration-300",
                    isCompleted
                      ? "bg-teal-500"
                      : isCurrent
                      ? "bg-blue-600 ring-2 ring-blue-300/60"
                      : "bg-slate-200"
                  )}
                />
              </Tooltip>
            );
          })}
        </div>
        <p className="text-[11.5px] text-slate-500 line-clamp-1">
          {activeStage.description}
        </p>
      </div>

      {/* Desktop & Tablet horizontal connected stepper (>= 640px) */}
      <div className="hidden sm:block">
        <ol className="flex items-center w-full">
          {CANONICAL_LIFECYCLE_STAGES.map((stage, i) => {
            const isCompleted = i < activeIdx;
            const isCurrent = i === activeIdx;
            const isUpcoming = i > activeIdx;
            const isLast = i === CANONICAL_LIFECYCLE_STAGES.length - 1;
            const date = stageDateMap[stage.key];

            return (
              <li
                key={stage.key}
                className={cn(
                  "relative flex-1 flex flex-col items-center",
                  !isLast && "after:content-[''] after:w-full after:h-0.5 after:border-b after:inline-block after:absolute after:top-3.5 after:left-[50%] after:z-0",
                  !isLast && (isCompleted ? "after:border-teal-500" : isCurrent ? "after:border-slate-200" : "after:border-slate-200")
                )}
              >
                <Tooltip
                  content={
                    <div className="text-left space-y-0.5 max-w-xs">
                      <p className="font-semibold text-white">
                        {i + 1}. {stage.label}
                        {isCompleted ? " (Completed)" : isCurrent ? " (Active)" : " (Upcoming)"}
                      </p>
                      <p className="text-[11.5px] text-slate-200">{stage.description}</p>
                      {date && (
                        <p className="text-[10px] text-teal-300 font-mono pt-1">
                          Timestamp: {date}
                        </p>
                      )}
                    </div>
                  }
                >
                  <div className="flex flex-col items-center relative z-10 group cursor-default">
                    {/* Step Icon / Circle */}
                    <div
                      className={cn(
                        "size-7 rounded-full flex items-center justify-center text-xs font-bold transition-all duration-300",
                        isCompleted &&
                          "bg-teal-500 text-white shadow-xs ring-4 ring-teal-50 hover:ring-teal-100",
                        isCurrent &&
                          "bg-blue-600 text-white shadow-sm ring-4 ring-blue-100 animate-none",
                        isUpcoming &&
                          "border border-slate-300 bg-white text-slate-400 group-hover:border-slate-400"
                      )}
                    >
                      {isCompleted ? (
                        <Check className="size-3.5 stroke-[2.8]" />
                      ) : (
                        <span>{i + 1}</span>
                      )}
                    </div>

                    {/* Step Label */}
                    <div className="mt-2 text-center min-w-[70px] max-w-[120px]">
                      <p
                        className={cn(
                          "text-xs tracking-tight transition-colors",
                          isCurrent
                            ? "font-semibold text-blue-700"
                            : isCompleted
                            ? "font-medium text-slate-800"
                            : "font-normal text-slate-400"
                        )}
                      >
                        {stage.label}
                      </p>
                      {date ? (
                        <p className="mt-0.5 text-[10px] text-slate-400 font-mono truncate">
                          {date}
                        </p>
                      ) : isCurrent ? (
                        <span className="inline-block mt-0.5 text-[10px] text-blue-600 font-medium tracking-tight">
                          Active stage
                        </span>
                      ) : null}
                    </div>
                  </div>
                </Tooltip>
              </li>
            );
          })}
        </ol>
      </div>
    </div>
  );
}
