"use client";

import React from "react";
import { AssistantThinking3D } from "../assistant/AssistantThinking3D";
import { Sparkles, Database, Clock, Loader2, CheckCircle2, Search, ShieldCheck } from "lucide-react";

export interface AIAssistantThinkingProps {
  stage?: "initiating" | "planning" | "retrieving" | "synthesizing" | "delegating" | "streaming" | string | null;
  events?: string[];
  className?: string;
  label?: string;
  elapsedSeconds?: number;
}

export function AIAssistantThinking({
  stage = "retrieving",
  events = [],
  className = "",
  label,
  elapsedSeconds,
}: AIAssistantThinkingProps) {
  const stageLabels: Record<string, string> = {
    initiating: "Initiating multi-domain investigation...",
    planning: "Query planning & subquery expansion...",
    retrieving: "Hybrid retrieval (ChromaDB vectors + PostgreSQL FTS)...",
    synthesizing: "Synthesizing evidence-grounded answer...",
    delegating: "Validating pre-retrieval ACL & permissions...",
    streaming: "Finalizing response...",
  };

  const currentLabel =
    label ||
    (stage && stageLabels[stage]) ||
    stage ||
    "Synthesizing verified project intelligence...";

  // Determine stage step index (0 to 3)
  const normStage = (stage || "retrieving").toLowerCase();
  let activeStep = 1;
  if (normStage.includes("init") || normStage.includes("plan")) {
    activeStep = 0;
  } else if (normStage.includes("retriev") || normStage.includes("search")) {
    activeStep = 1;
  } else if (normStage.includes("delegat") || normStage.includes("validat") || normStage.includes("acl")) {
    activeStep = 2;
  } else if (normStage.includes("synth") || normStage.includes("stream")) {
    activeStep = 3;
  }

  const steps = [
    { label: "Plan", icon: Search },
    { label: "Retrieve", icon: Database },
    { label: "Verify ACL", icon: ShieldCheck },
    { label: "Synthesize", icon: Sparkles },
  ];

  return (
    <div
      className={`p-5 rounded-2xl border border-blue-100 bg-white/95 backdrop-blur-md shadow-[0_8px_30px_rgb(0,0,0,0.06)] space-y-4 animate-fade-in ${className}`}
      role="status"
      aria-live="polite"
    >
      {/* 3D Stacked Glass Thinking Animation Lockup */}
      <div className="flex flex-col sm:flex-row items-center gap-4">
        <AssistantThinking3D size="sm" isThinking={true} />
        <div className="flex-1 text-center sm:text-left space-y-1">
          <div className="flex items-center justify-center sm:justify-start gap-2">
            <span className="text-xs font-bold text-slate-900">
              Knowledge Assistant
            </span>
            <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 bg-blue-50 text-blue-700 border border-blue-200/60 rounded-full">
              <span className="size-1.5 rounded-full bg-blue-500 animate-ping" />
              Thinking
            </span>
            {typeof elapsedSeconds === "number" && (
              <span className="inline-flex items-center gap-1 text-[10px] font-mono font-medium text-slate-500 bg-slate-100 px-2 py-0.5 rounded-full border border-slate-200">
                <Clock className="size-2.5 text-slate-400" />
                {elapsedSeconds}s
              </span>
            )}
          </div>
          <p className="text-xs font-medium text-slate-700">{currentLabel}</p>
          <p className="text-[10px] text-slate-400">
            Authorized project sources only · Zero fabrication
          </p>
        </div>
      </div>

      {/* 4-Step Progressive Stage Indicator */}
      <div className="grid grid-cols-4 gap-1.5 pt-1 border-t border-slate-100">
        {steps.map((st, i) => {
          const isDone = i < activeStep;
          const isCurrent = i === activeStep;
          const StepIcon = st.icon;
          return (
            <div
              key={st.label}
              className={`flex items-center gap-1.5 px-2 py-1.5 rounded-lg border text-[11px] font-medium transition-all ${
                isCurrent
                  ? "bg-blue-50/80 border-blue-300 text-blue-900 shadow-2xs font-semibold"
                  : isDone
                  ? "bg-slate-50 border-slate-200 text-slate-700"
                  : "bg-white border-dashed border-slate-200 text-slate-400"
              }`}
            >
              {isDone ? (
                <CheckCircle2 className="size-3 text-teal-600 shrink-0" />
              ) : isCurrent ? (
                <Loader2 className="size-3 text-blue-600 animate-spin shrink-0" />
              ) : (
                <StepIcon className="size-3 text-slate-300 shrink-0" />
              )}
              <span className="truncate">{st.label}</span>
            </div>
          );
        })}
      </div>

      {/* Simulated Response Shimmer Placeholder */}
      <div className="p-3 bg-slate-50/60 border border-slate-100 rounded-xl space-y-2 animate-pulse" aria-hidden="true">
        <div className="h-2.5 bg-slate-200/80 rounded w-11/12" />
        <div className="h-2.5 bg-slate-200/80 rounded w-4/5" />
        <div className="h-2.5 bg-slate-200/80 rounded w-2/3" />
      </div>
    </div>
  );
}

export default AIAssistantThinking;
