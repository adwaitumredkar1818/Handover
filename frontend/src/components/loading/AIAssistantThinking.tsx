"use client";

import React from "react";
import { AssistantThinking3D } from "../assistant/AssistantThinking3D";
import { Sparkles, Database } from "lucide-react";

export interface AIAssistantThinkingProps {
  stage?: "initiating" | "planning" | "retrieving" | "synthesizing" | "delegating" | "streaming" | string | null;
  events?: string[];
  className?: string;
}

export function AIAssistantThinking({
  stage = "retrieving",
  events = [],
  className = "",
}: AIAssistantThinkingProps) {
  const stageLabels: Record<string, string> = {
    initiating: "Understanding your question...",
    planning: "Searching project knowledge...",
    retrieving: "Reviewing relevant evidence...",
    delegating: "Consulting specialized project intelligence...",
    synthesizing: "Preparing your answer...",
    streaming: "Finalizing response...",
  };

  const currentLabel =
    (stage && stageLabels[stage]) ||
    stage ||
    "Searching project knowledge...";

  return (
    <div
      className={`p-5 rounded-2xl border border-blue-100 bg-white/90 backdrop-blur-md shadow-[0_8px_30px_rgb(0,0,0,0.06)] space-y-4 animate-fade-in ${className}`}
      role="status"
      aria-live="polite"
    >
      {/* 3D Stacked Glass Thinking Animation Lockup */}
      <div className="flex flex-col sm:flex-row items-center gap-4">
        <AssistantThinking3D size="sm" isThinking={true} />
        <div className="flex-1 text-center sm:text-left space-y-1">
          <div className="flex items-center justify-center sm:justify-start gap-2">
            <span className="text-xs font-bold text-slate-900">
              Project Knowledge Assistant
            </span>
            <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 bg-blue-50 text-blue-700 border border-blue-200/60 rounded-full">
              <span className="size-1.5 rounded-full bg-blue-500 animate-ping" />
              Thinking
            </span>
          </div>
          <p className="text-xs font-medium text-slate-700">{currentLabel}</p>
          <p className="text-[10px] text-slate-400">
            Authorized project sources only · Zero fabrication
          </p>
        </div>
      </div>

      {/* Simulated Citation Resolving Pills */}
      <div className="pt-2 border-t border-slate-100 flex items-center justify-center sm:justify-start gap-2 overflow-hidden" aria-hidden="true">
        <div className="h-6 w-32 bg-blue-50/60 border border-blue-100 rounded-md animate-pulse flex items-center gap-1.5 px-2">
          <Database className="w-3 h-3 text-blue-400" />
          <div className="h-2 w-20 bg-blue-200/70 rounded" />
        </div>
        <div className="h-6 w-36 bg-blue-50/60 border border-blue-100 rounded-md animate-pulse flex items-center gap-1.5 px-2">
          <Sparkles className="w-3 h-3 text-blue-400" />
          <div className="h-2 w-24 bg-blue-200/70 rounded" />
        </div>
      </div>
    </div>
  );
}

export default AIAssistantThinking;
