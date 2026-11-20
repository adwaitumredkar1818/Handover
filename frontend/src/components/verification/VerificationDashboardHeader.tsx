"use client";

import React from "react";
import Link from "next/link";
import {
  ShieldCheck,
  RefreshCw,
  Sparkles,
  GitCompare,
  CheckCircle,
} from "lucide-react";
import type { DashboardHeaderProps } from "./types";

export const VerificationDashboardHeader: React.FC<DashboardHeaderProps> = ({
  summary,
  loading,
  assessing,
  onRefresh,
  onAssessAll,
  projectName,
}) => {
  return (
    <div className="bg-white border-b border-slate-200 px-6 py-4">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        {/* Title and breadcrumbs */}
        <div>
          <div className="flex items-center gap-2 text-xs text-slate-500 mb-1">
            <span>Project</span>
            <span>/</span>
            <span className="font-medium text-slate-700">{projectName || "Current Workspace"}</span>
            <span>/</span>
            <span className="text-teal-700 font-semibold">Verification Center</span>
          </div>
          <div className="flex items-center gap-2.5">
            <div className="size-8 rounded-lg bg-teal-50 border border-teal-200 flex items-center justify-center text-teal-700">
              <ShieldCheck className="size-5" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-slate-900 tracking-tight">
                Verification Center
              </h1>
              <p className="text-xs text-slate-500">
                Evidence-driven human verification and approval workspace.{" "}
                <span className="text-slate-600 italic">
                  Confidence is not correctness — uncertainty shown, not hidden.
                </span>
              </p>
            </div>
          </div>
        </div>

        {/* Action Controls & Navigation Shortcuts */}
        <div className="flex flex-wrap items-center gap-2.5">
          <Link
            href="/conflicts"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 bg-white text-xs font-medium text-slate-700 hover:bg-slate-50 hover:text-slate-900 transition shadow-xs"
          >
            <GitCompare className="size-3.5 text-indigo-600" />
            <span>Cross-Source Conflicts</span>
            {summary && summary.conflicts_count > 0 && (
              <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-indigo-100 text-indigo-800 font-bold">
                {summary.conflicts_count}
              </span>
            )}
          </Link>

          <button
            type="button"
            onClick={onRefresh}
            disabled={loading}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 bg-white text-xs font-medium text-slate-700 hover:bg-slate-50 hover:text-slate-900 disabled:opacity-50 transition shadow-xs cursor-pointer"
            title="Refresh queue and summary data"
          >
            <RefreshCw className={`size-3.5 ${loading ? "animate-spin text-teal-600" : "text-slate-500"}`} />
            <span>{loading ? "Refreshing..." : "Refresh Queue"}</span>
          </button>

          <button
            type="button"
            onClick={onAssessAll}
            disabled={assessing}
            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-teal-700 hover:bg-teal-800 text-white text-xs font-semibold shadow-xs hover:shadow transition disabled:opacity-50 cursor-pointer"
            title="Trigger full automated verification assessment across all candidate items"
          >
            {assessing ? (
              <RefreshCw className="size-3.5 animate-spin" />
            ) : (
              <Sparkles className="size-3.5" />
            )}
            <span>{assessing ? "Assessing..." : "Assess All Findings"}</span>
          </button>
        </div>
      </div>

      {/* Epistemic Guidance Banner */}
      <div className="mt-3.5 pt-2.5 border-t border-slate-100 flex items-center justify-between text-[11px] text-slate-500">
        <div className="flex items-center gap-4">
          <span className="flex items-center gap-1.5 text-emerald-700 font-medium">
            <CheckCircle className="size-3 text-emerald-600" />
            Human gatekeeper required before downstream handover compilation
          </span>
          <span className="hidden sm:inline text-slate-300">•</span>
          <span className="hidden sm:inline text-slate-600">
            Advisory AI extraction confidence is never equated with verified truth
          </span>
        </div>
        {summary?.open_issues_count !== undefined && summary.open_issues_count > 0 && (
          <span className="text-amber-800 font-medium">
            {summary.open_issues_count} open validation {summary.open_issues_count === 1 ? "flag" : "flags"}
          </span>
        )}
      </div>
    </div>
  );
};
