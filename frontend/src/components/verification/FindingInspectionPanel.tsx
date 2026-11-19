"use client";

import React, { useState } from "react";
import {
  FileText,
  Edit3,
  Code,
  Copy,
  Check,
  Sparkles,
  Info,
  ChevronDown,
  ChevronUp,
  Tag,
  Loader2,
} from "lucide-react";
import { HandoverEligibilityBadge } from "./HandoverEligibilityBadge";
import type { FindingInspectionPanelProps } from "./types";

export const FindingInspectionPanel: React.FC<FindingInspectionPanelProps> = ({
  caseDetail,
  eligibility,
  loadingEligibility,
  loading,
  onOpenEditModal,
}) => {
  const [showRawPayload, setShowRawPayload] = useState(false);
  const [copiedPayload, setCopiedPayload] = useState(false);

  if (loading && !caseDetail) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-8 text-center text-slate-400">
        <Loader2 className="size-6 animate-spin text-teal-600 mb-2" />
        <p className="text-xs">Loading finding details...</p>
      </div>
    );
  }

  if (!caseDetail) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-8 text-center text-slate-400">
        <FileText className="size-10 text-slate-300 mb-3" />
        <h3 className="text-sm font-semibold text-slate-700">No Finding Selected</h3>
        <p className="text-xs text-slate-500 mt-1 max-w-xs">
          Select a candidate finding from the queue on the left to inspect its extracted details, supporting citations, and review status.
        </p>
      </div>
    );
  }

  const targetData = caseDetail.target_data || {};
  const title = targetData.title || `Finding ${caseDetail.target_id.slice(0, 8)}`;
  const summary = targetData.summary || "No structured summary recorded for this knowledge item.";
  const domain = targetData.knowledge_domain || "Architecture";
  const category = targetData.category || "General";
  const epistemicStatus = targetData.epistemic_status || "extracted";
  const reviewStatus = targetData.review_status || caseDetail.case_status;
  const confidence =
    targetData.confidence_score !== null && targetData.confidence_score !== undefined
      ? Math.round(targetData.confidence_score * 100)
      : null;

  const payload = targetData.item_payload || caseDetail.machine_assessment_json || {};

  const handleCopyPayload = () => {
    navigator.clipboard.writeText(JSON.stringify(payload, null, 2));
    setCopiedPayload(true);
    setTimeout(() => setCopiedPayload(false), 2000);
  };

  const getEpistemicBadge = (status: string) => {
    switch (status.toLowerCase()) {
      case "human_verified":
        return {
          label: "HUMAN-VERIFIED TRUTH",
          classes: "bg-emerald-100 text-emerald-900 border-emerald-300",
        };
      case "inferred":
        return {
          label: "AI INFERRED KNOWLEDGE",
          classes: "bg-indigo-100 text-indigo-900 border-indigo-300",
        };
      case "disputed":
        return {
          label: "DISPUTED CLAIM",
          classes: "bg-rose-100 text-rose-900 border-rose-300",
        };
      case "extracted":
      default:
        return {
          label: "EXTRACTED FACT",
          classes: "bg-slate-100 text-slate-800 border-slate-300",
        };
    }
  };

  const epistemic = getEpistemicBadge(epistemicStatus);

  return (
    <div className="flex flex-col h-full bg-white overflow-y-auto p-5 space-y-4">
      {/* Header and Action row */}
      <div>
        <div className="flex items-center justify-between gap-3 mb-2">
          {/* Domain & Category tags */}
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-bold bg-teal-50 text-teal-800 border border-teal-200">
              <Tag className="size-3" />
              {domain}
            </span>
            <span className="px-2 py-0.5 rounded-md text-xs bg-slate-100 text-slate-700 border border-slate-200">
              {category}
            </span>
            <span className="text-xs text-slate-600 font-mono">
              ID: {caseDetail.target_id.slice(0, 8)}
            </span>
          </div>

          {/* Edit Finding CTA Button */}
          <button
            type="button"
            onClick={onOpenEditModal}
            className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium text-slate-700 bg-white border border-slate-200 rounded-lg hover:bg-slate-50 hover:text-slate-900 transition shadow-xs cursor-pointer"
            title="Edit finding title, summary, or structured properties"
          >
            <Edit3 className="size-3.5 text-teal-600" />
            <span>Edit Finding</span>
          </button>
        </div>

        {/* Finding Title */}
        <h2 className="text-base font-bold text-slate-900 tracking-tight leading-snug">
          {title}
        </h2>
      </div>

      {/* Epistemic Status & Handover Gate Row */}
      <div className="flex flex-wrap items-center justify-between gap-2.5 py-2.5 px-3 bg-slate-50/80 rounded-xl border border-slate-200">
        <div className="flex items-center gap-2">
          <span
            className={`px-2.5 py-0.5 rounded-full text-[11px] font-mono font-bold border tracking-wide uppercase ${epistemic.classes}`}
            title="Epistemic status tier of this knowledge item"
          >
            {epistemic.label}
          </span>
          <span className="text-[11px] text-slate-500">
            Review Status: <strong className="text-slate-800 uppercase">{reviewStatus}</strong>
          </span>
        </div>

        {/* Handover Gatekeeper Badge */}
        <HandoverEligibilityBadge
          eligibility={eligibility}
          loading={loadingEligibility}
        />
      </div>

      {/* Structured Summary Card */}
      <div className="space-y-1.5">
        <div className="text-xs font-bold text-slate-700 flex items-center gap-1.5">
          <FileText className="size-3.5 text-slate-500" />
          Structured Summary
        </div>
        <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200/80 text-xs text-slate-800 leading-relaxed whitespace-pre-wrap font-sans">
          {summary}
        </div>
      </div>

      {/* Advisory Confidence Meter */}
      <div className="p-3 rounded-xl border border-teal-100 bg-teal-50/40 space-y-2">
        <div className="flex items-center justify-between text-xs">
          <div className="flex items-center gap-1.5 font-semibold text-teal-900">
            <Sparkles className="size-3.5 text-teal-600" />
            Advisory Extraction Confidence
          </div>
          <span className="font-bold text-teal-800">
            {confidence !== null ? `${confidence}%` : "Unscored"}
          </span>
        </div>

        {/* Progress bar */}
        {confidence !== null && (
          <div className="w-full h-2 bg-teal-100 rounded-full overflow-hidden">
            <div
              className={`h-full transition-all duration-500 ${
                confidence >= 80
                  ? "bg-teal-600"
                  : confidence >= 50
                  ? "bg-amber-500"
                  : "bg-rose-500"
              }`}
              style={{ width: `${Math.min(100, Math.max(0, confidence))}%` }}
            />
          </div>
        )}

        <div className="flex items-start gap-1.5 text-[11px] text-slate-600">
          <Info className="size-3 text-teal-600 shrink-0 mt-0.5" />
          <span>
            Calibrated model score is advisory only. Human verification is strictly required for authoritative sign-off.
          </span>
        </div>
      </div>

      {/* Collapsible Raw Item Payload JSON Viewer */}
      <div className="border border-slate-200 rounded-xl overflow-hidden">
        <button
          type="button"
          onClick={() => setShowRawPayload(!showRawPayload)}
          className="w-full flex items-center justify-between p-3 bg-slate-50 hover:bg-slate-100 text-xs font-semibold text-slate-700 transition cursor-pointer"
        >
          <div className="flex items-center gap-1.5">
            <Code className="size-3.5 text-slate-500" />
            <span>Raw Item Payload & Assessment Data</span>
          </div>
          {showRawPayload ? (
            <ChevronUp className="size-3.5 text-slate-500" />
          ) : (
            <ChevronDown className="size-3.5 text-slate-500" />
          )}
        </button>

        {showRawPayload && (
          <div className="p-3 bg-slate-900 text-slate-200 text-[11px] font-mono overflow-x-auto relative max-h-64 overflow-y-auto">
            <div className="absolute right-2 top-2 z-10">
              <button
                type="button"
                onClick={handleCopyPayload}
                className="px-2 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded text-[10px] font-sans flex items-center gap-1 border border-slate-700 transition cursor-pointer"
                title="Copy JSON to clipboard"
              >
                {copiedPayload ? (
                  <>
                    <Check className="size-3 text-emerald-400" />
                    <span>Copied!</span>
                  </>
                ) : (
                  <>
                    <Copy className="size-3" />
                    <span>Copy JSON</span>
                  </>
                )}
              </button>
            </div>
            <pre>{JSON.stringify(payload, null, 2)}</pre>
          </div>
        )}
      </div>
    </div>
  );
};
