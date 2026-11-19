"use client";

import React from "react";
import { Sparkles, Brain, Check, Layers, Cpu } from "lucide-react";

export interface AIProcessingStage {
  id: string;
  label: string;
  description?: string;
}

export interface AILoadingStateProps {
  title?: string;
  subtitle?: string;
  stages?: AIProcessingStage[];
  activeStageId?: string;
  className?: string;
}

const DEFAULT_STAGES: AIProcessingStage[] = [
  { id: "collect", label: "Collecting & parsing verified evidence" },
  { id: "extract", label: "Extracting architectural & operational facts" },
  { id: "correlate", label: "Cross-referencing decisions with code commits" },
  { id: "reconstruct", label: "Reconstructing ownership & dependencies" },
  { id: "synthesize", label: "Synthesizing handover knowledge dossier" },
];

export function AILoadingState({
  title = "Reconstructing Project Knowledge",
  subtitle = "Our AI reasoning engine is analyzing evidence across connected sources and documents",
  stages = DEFAULT_STAGES,
  activeStageId,
  className = "",
}: AILoadingStateProps) {
  const currentStageIndex = activeStageId
    ? Math.max(0, stages.findIndex((s) => s.id === activeStageId))
    : 0;

  return (
    <div
      className={`p-6 bg-white rounded-xl border border-[#DCE3EB] shadow-sm select-none ${className}`}
      role="status"
      aria-live="polite"
    >
      {/* Top Lockup with Organic AI Breathing Node */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-[#F1F5F9]">
        <div className="flex items-center gap-3.5">
          <div className="relative flex items-center justify-center">
            {/* Ambient Pulsing Halo */}
            <div
              className="absolute -inset-2 rounded-2xl bg-gradient-to-r from-[#315FBA]/20 via-[#8B78C9]/30 to-[#299B80]/20 blur-md animate-pulse"
              style={{ animationDuration: "2.4s" }}
            />
            <div className="relative w-12 h-12 rounded-xl bg-gradient-to-br from-[#203653] to-[#315FBA] flex items-center justify-center text-white shadow-md">
              <Brain className="w-6 h-6 text-white animate-pulse" />
            </div>
          </div>

          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-bold text-[#203653]">{title}</h3>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-[#8B78C9]/15 text-[#8B78C9] border border-[#8B78C9]/30 flex items-center gap-1">
                <Sparkles className="w-2.5 h-2.5" />
                <span>Qwen3 8B</span>
              </span>
            </div>
            <p className="text-xs text-[#69778D] mt-0.5">{subtitle}</p>
          </div>
        </div>

        {/* Status Chip */}
        <div className="flex items-center gap-2 self-start sm:self-center px-3 py-1.5 rounded-lg bg-[#F8FAFC] border border-[#DCE3EB] text-xs font-semibold text-[#203653]">
          <Cpu className="w-3.5 h-3.5 text-[#315FBA] animate-spin" style={{ animationDuration: "3s" }} />
          <span>Stage {currentStageIndex + 1} of {stages.length}</span>
        </div>
      </div>

      {/* Truthful Stage Timeline */}
      <div className="mt-5 space-y-3">
        {stages.map((stage, idx) => {
          const isDone = idx < currentStageIndex;
          const isCurrent = idx === currentStageIndex;
          const isPending = idx > currentStageIndex;

          return (
            <div
              key={stage.id}
              className={`flex items-start gap-3 p-3 rounded-lg border transition-all duration-300 ${
                isCurrent
                  ? "bg-[#F8FAFC] border-[#315FBA]/30 shadow-2xs"
                  : isDone
                  ? "bg-white border-[#E2E8F0]/70 opacity-90"
                  : "bg-white/40 border-transparent opacity-45"
              }`}
            >
              {/* Stage Step Indicator */}
              <div
                className={`w-6 h-6 rounded-full flex items-center justify-center shrink-0 mt-0.5 text-xs font-bold transition-colors ${
                  isDone
                    ? "bg-[#299B80] text-white"
                    : isCurrent
                    ? "bg-[#315FBA] text-white shadow-[0_0_8px_rgba(49,95,186,0.5)]"
                    : "bg-[#E2E8F0] text-[#69778D]"
                }`}
              >
                {isDone ? (
                  <Check className="w-3.5 h-3.5 stroke-[2.5]" />
                ) : isCurrent ? (
                  <div className="w-2 h-2 rounded-full bg-white animate-ping" />
                ) : (
                  <span>{idx + 1}</span>
                )}
              </div>

              {/* Stage Label & Details */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between">
                  <span
                    className={`text-xs font-semibold truncate ${
                      isCurrent
                        ? "text-[#203653]"
                        : isDone
                        ? "text-[#475569]"
                        : "text-[#94A3B8]"
                    }`}
                  >
                    {stage.label}
                  </span>
                  {isCurrent && (
                    <span className="text-[11px] font-mono font-medium text-[#315FBA] animate-pulse">
                      In progress...
                    </span>
                  )}
                  {isDone && (
                    <span className="text-[11px] font-semibold text-[#299B80]">
                      Verified
                    </span>
                  )}
                </div>
                {stage.description && (
                  <p className="text-[11px] text-[#69778D] mt-0.5">
                    {stage.description}
                  </p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default AILoadingState;
