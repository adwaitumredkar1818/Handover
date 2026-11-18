"use client";

import React from "react";
import Link from "next/link";
import { Loader2, AlertCircle, RefreshCw, Cpu, ExternalLink, Network } from "lucide-react";
import type { ProjectProcessingStatus } from "@/lib/types";

interface LiveProcessingBannerProps {
  status: ProjectProcessingStatus | null;
  onRetry?: () => void;
  retrying?: boolean;
  projectId?: string;
}

/**
 * Never render a floating banner over existing interactive graphs.
 */
export function LiveProcessingBanner(_props: LiveProcessingBannerProps) {
  return null;
}

/**
 * Minimal, accurate empty state rendered ONLY when no graph nodes exist.
 */
export function ProcessingEmptyStateCard({
  status,
  onRetry,
  retrying = false,
  projectId,
}: LiveProcessingBannerProps) {
  // 1. Failure state: Show actual error and allow retry
  if (status?.state === "failed") {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center p-8 max-w-md mx-auto">
        <div className="w-12 h-12 rounded-full bg-rose-50 border border-rose-200 flex items-center justify-center mb-3">
          <AlertCircle className="w-6 h-6 text-rose-600" />
        </div>
        <h3 className="text-base font-semibold text-slate-900 mb-1">
          Knowledge extraction paused
        </h3>
        <p className="text-xs text-slate-500 mb-4 leading-relaxed">
          {status.error_message ||
            "The background knowledge reconstruction encountered an error. You can retry processing."}
        </p>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            disabled={retrying}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-medium text-xs shadow-xs transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${retrying ? "animate-spin" : ""}`} />
            {retrying ? "Retrying…" : "Retry processing"}
          </button>
        )}
      </div>
    );
  }

  // 2. Active processing state: Minimal and accurate
  if (status && (status.is_processing || status.state === "queued" || status.state === "processing")) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center p-8 max-w-md mx-auto">
        <div className="w-12 h-12 rounded-2xl bg-blue-50 border border-blue-200 flex items-center justify-center mb-3 shadow-xs">
          <Loader2 className="w-6 h-6 text-blue-600 animate-spin" />
        </div>
        <h3 className="text-base font-semibold text-slate-900 mb-1">
          Reconstructing project knowledge…
        </h3>
        <p className="text-xs text-slate-500 mb-3 max-w-sm leading-relaxed">
          New evidence is being analyzed in the background. Graphs will populate automatically when complete.
        </p>
        {status.stage_label && (
          <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-blue-50 border border-blue-200 text-[11px] text-blue-800 font-medium">
            <span className="w-1.5 h-1.5 rounded-full bg-blue-600 animate-pulse" />
            <span>{status.stage_label}</span>
          </div>
        )}
        {status.total_evidence_count > 0 && (
          <span className="text-[11px] text-slate-400 mt-2">
            {status.processed_evidence_count} of {status.total_evidence_count} evidence items indexed
          </span>
        )}
      </div>
    );
  }

  // 3. Completed without sufficient evidence
  return (
    <div className="flex flex-col items-center justify-center h-full text-center p-8 max-w-md mx-auto">
      <div className="w-12 h-12 rounded-full bg-slate-100 border border-slate-200 flex items-center justify-center mb-3">
        <Network className="w-6 h-6 text-slate-400" />
      </div>
      <h3 className="text-base font-medium text-slate-800 mb-1">
        No knowledge has been reconstructed from this project&apos;s evidence yet.
      </h3>
      <p className="text-xs text-slate-500 mb-4 max-w-sm leading-relaxed">
        The available evidence does not contain sufficient structured relationships for this view. Upload project documents or connect GitHub sources in Evidence Center.
      </p>
      {projectId && (
        <Link
          href={`/projects/${projectId}/evidence`}
          className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium transition-colors"
        >
          <span>Open Evidence Center</span>
          <ExternalLink className="w-3.5 h-3.5" />
        </Link>
      )}
    </div>
  );
}
