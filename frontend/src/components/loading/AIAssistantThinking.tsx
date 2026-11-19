"use client";

import React from "react";
import { Bot, Sparkles, Database, Search } from "lucide-react";

export interface AIAssistantThinkingProps {
  stage?: "initiating" | "planning" | "retrieving" | "synthesizing" | string | null;
  events?: string[];
  className?: string;
}

export function AIAssistantThinking({
  stage = "retrieving",
  events = [],
  className = "",
}: AIAssistantThinkingProps) {
  const stageLabels: Record<string, string> = {
    initiating: "Initiating multi-domain investigation...",
    planning: "Query planning & subquery expansion...",
    retrieving: "Hybrid retrieval (ChromaDB vectors + PostgreSQL FTS)...",
    synthesizing: "Synthesizing evidence-grounded answer...",
  };

  const currentLabel =
    (stage && stageLabels[stage]) ||
    stage ||
    "Synthesizing verified project intelligence...";

  return (
    <div
      className={`p-4 rounded-xl border border-[#DCE3EB] bg-white shadow-2xs space-y-3 animate-fade-in ${className}`}
      role="status"
      aria-live="polite"
    >
      {/* Assistant Header Lockup */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <div className="relative flex items-center justify-center">
            <div className="absolute -inset-1 rounded-full bg-[#8B78C9]/20 blur-xs animate-pulse" />
            <div className="w-7 h-7 rounded-lg bg-[#203653] text-white flex items-center justify-center">
              <Bot className="w-4 h-4 text-[#8B78C9]" />
            </div>
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-bold text-[#203653]">
                Knowledge Assistant
              </span>
              <span className="text-[10px] font-semibold px-1.5 py-0.2 bg-[#8B78C9]/10 text-[#8B78C9] rounded">
                Thinking
              </span>
            </div>
          </div>
        </div>

        {/* Organic 3-Dot Breathing Indicator */}
        <div className="flex items-center gap-1 px-2.5 py-1 rounded-full bg-[#F8FAFC] border border-[#E2E8F0]" aria-hidden="true">
          <div className="w-1.5 h-1.5 rounded-full bg-[#315FBA] animate-bounce" style={{ animationDelay: "0ms" }} />
          <div className="w-1.5 h-1.5 rounded-full bg-[#299B80] animate-bounce" style={{ animationDelay: "150ms" }} />
          <div className="w-1.5 h-1.5 rounded-full bg-[#8B78C9] animate-bounce" style={{ animationDelay: "300ms" }} />
        </div>
      </div>

      {/* Real-time Subquery Investigation Stage */}
      <div className="p-2.5 rounded-lg bg-[#F8FAFC] border border-[#E2E8F0] flex items-center gap-2 text-xs text-[#203653]">
        <Search className="w-3.5 h-3.5 text-[#315FBA] animate-spin" style={{ animationDuration: "3s" }} />
        <span className="font-medium truncate">{currentLabel}</span>
      </div>

      {/* Simulated Citation Cards Resolving */}
      <div className="pt-1 flex items-center gap-2 overflow-hidden" aria-hidden="true">
        <div className="h-6 w-28 bg-[#F1F5F9] border border-[#E2E8F0] rounded-md animate-pulse flex items-center gap-1.5 px-2">
          <Database className="w-3 h-3 text-[#94A3B8]" />
          <div className="h-2 w-16 bg-[#CBD5E1] rounded" />
        </div>
        <div className="h-6 w-32 bg-[#F1F5F9] border border-[#E2E8F0] rounded-md animate-pulse flex items-center gap-1.5 px-2">
          <Sparkles className="w-3 h-3 text-[#94A3B8]" />
          <div className="h-2 w-20 bg-[#CBD5E1] rounded" />
        </div>
      </div>
    </div>
  );
}

export default AIAssistantThinking;
