"use client";

import React, { useState } from "react";
import { CheckCircle2, AlertTriangle, ShieldAlert, ChevronDown, ChevronUp, Loader2 } from "lucide-react";
import type { HandoverEligibilityBadgeProps } from "./types";

export const HandoverEligibilityBadge: React.FC<HandoverEligibilityBadgeProps> = ({
  eligibility,
  loading,
}) => {
  const [expanded, setExpanded] = useState(false);

  if (loading) {
    return (
      <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-slate-100 text-slate-500 border border-slate-200 animate-pulse">
        <Loader2 className="size-3 animate-spin text-slate-400" />
        <span>Evaluating Handover Gate...</span>
      </div>
    );
  }

  if (!eligibility) {
    return null;
  }

  const isEligible = eligibility.is_eligible;
  const blockers = eligibility.blockers || [];
  const warnings = eligibility.warnings || [];

  return (
    <div className="relative inline-block text-left">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold border transition shadow-xs cursor-pointer ${
          isEligible
            ? "bg-emerald-50 text-emerald-800 border-emerald-200 hover:bg-emerald-100"
            : "bg-amber-50 text-amber-900 border-amber-300 hover:bg-amber-100"
        }`}
        title="Click to view Handover Gate criteria and blockers"
      >
        {isEligible ? (
          <CheckCircle2 className="size-3.5 text-emerald-600 shrink-0" />
        ) : (
          <ShieldAlert className="size-3.5 text-amber-600 shrink-0" />
        )}
        <span>{isEligible ? "Handover Eligible" : "Blocked from Handover"}</span>
        {!isEligible && blockers.length > 0 && (
          <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-amber-200 text-amber-900 font-bold ml-0.5">
            {blockers.length}
          </span>
        )}
        {expanded ? (
          <ChevronUp className="size-3 text-slate-500 ml-0.5" />
        ) : (
          <ChevronDown className="size-3 text-slate-500 ml-0.5" />
        )}
      </button>

      {expanded && (
        <div className="absolute left-0 mt-2 w-80 sm:w-96 p-3.5 bg-white rounded-xl shadow-xl border border-slate-200 z-50 text-xs text-slate-700 animate-in fade-in-50 zoom-in-95 duration-100">
          <div className="flex items-center justify-between pb-2 mb-2 border-b border-slate-100">
            <span className="font-bold text-slate-900 text-xs flex items-center gap-1.5">
              <ShieldAlert className="size-4 text-slate-600" />
              Handover Gatekeeper Status
            </span>
            <span
              className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
                isEligible
                  ? "bg-emerald-100 text-emerald-800"
                  : "bg-rose-100 text-rose-800"
              }`}
            >
              {isEligible ? "PASSED" : "BLOCKED"}
            </span>
          </div>

          <div className="space-y-2 mb-3">
            <div className="flex items-center justify-between text-[11px] text-slate-600">
              <span>Case Status:</span>
              <span className="font-mono font-medium text-slate-900">{eligibility.case_status}</span>
            </div>
            <div className="flex items-center justify-between text-[11px] text-slate-600">
              <span>Epistemic Status:</span>
              <span className="font-mono font-medium text-slate-900">{eligibility.epistemic_status}</span>
            </div>
          </div>

          {blockers.length > 0 && (
            <div className="mb-2">
              <div className="text-[11px] font-bold text-rose-800 mb-1 flex items-center gap-1">
                <AlertTriangle className="size-3 text-rose-600" />
                Active Blockers ({blockers.length})
              </div>
              <ul className="space-y-1 pl-1">
                {blockers.map((blocker, idx) => (
                  <li
                    key={idx}
                    className="text-[11px] text-rose-700 bg-rose-50/80 p-1.5 rounded border border-rose-100 flex items-start gap-1.5 leading-snug"
                  >
                    <span className="text-rose-500 font-bold">•</span>
                    <span>{blocker}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {warnings.length > 0 && (
            <div className="mb-2">
              <div className="text-[11px] font-bold text-amber-800 mb-1 flex items-center gap-1">
                <AlertTriangle className="size-3 text-amber-600" />
                Advisory Warnings ({warnings.length})
              </div>
              <ul className="space-y-1 pl-1">
                {warnings.map((warning, idx) => (
                  <li
                    key={idx}
                    className="text-[11px] text-amber-700 bg-amber-50/80 p-1.5 rounded border border-amber-100 flex items-start gap-1.5 leading-snug"
                  >
                    <span className="text-amber-500 font-bold">•</span>
                    <span>{warning}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {isEligible && blockers.length === 0 && (
            <p className="text-[11px] text-emerald-700 bg-emerald-50 p-2 rounded border border-emerald-100 leading-relaxed">
              All epistemic and verification quality criteria have been satisfied. This finding will be compiled into downstream handover dossiers.
            </p>
          )}

          <div className="mt-2.5 pt-2 border-t border-slate-100 text-[10px] text-slate-600 text-right">
            Click badge again to close
          </div>
        </div>
      )}
    </div>
  );
};
