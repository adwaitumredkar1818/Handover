"use client";

import React, { useState } from "react";
import {
  AlertTriangle,
  GitCompare,
  Clock,
  Sparkles,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  FileCode,
  FileText,
  MessageSquare,
} from "lucide-react";
import type { SideBySideConflictCardProps } from "./types";

export const SideBySideConflictCard: React.FC<SideBySideConflictCardProps> = ({
  conflict,
  onResolve,
  resolving = false,
}) => {
  const [showResolveForm, setShowResolveForm] = useState(false);
  const [resolutionChoice, setResolutionChoice] = useState<string>("superseded");
  const [preferredClaim, setPreferredClaim] = useState<string>("claim_b");
  const [resolutionNotes, setResolutionNotes] = useState<string>("");
  const [errorMsg, setErrorMsg] = useState<string>("");

  const getSourceIcon = (sourceType?: string | null) => {
    switch (sourceType?.toLowerCase()) {
      case "github":
      case "github_pull_request":
      case "github_commit":
        return <FileCode className="size-3.5 text-slate-700" />;
      case "jira":
      case "jira_issue":
        return <FileText className="size-3.5 text-blue-600" />;
      case "slack":
      case "slack_message":
        return <MessageSquare className="size-3.5 text-emerald-600" />;
      default:
        return <FileText className="size-3.5 text-slate-600" />;
    }
  };

  const getTemporalBadge = (temporal: string) => {
    switch (temporal) {
      case "b_supersedes_a":
        return {
          label: "Source B Supersedes Source A",
          classes: "bg-purple-100 text-purple-900 border-purple-300",
        };
      case "a_supersedes_b":
        return {
          label: "Source A Supersedes Source B",
          classes: "bg-blue-100 text-blue-900 border-blue-300",
        };
      case "simultaneous":
        return {
          label: "Simultaneous Claims (Direct Contradiction)",
          classes: "bg-rose-100 text-rose-900 border-rose-300",
        };
      case "ambiguous":
      default:
        return {
          label: "Ambiguous Temporal Precedence",
          classes: "bg-amber-100 text-amber-900 border-amber-300",
        };
    }
  };

  const temporal = getTemporalBadge(conflict.temporal_comparison || "ambiguous");
  const isUnresolved = conflict.resolution_state === "unresolved";

  const handleConfirmResolve = async () => {
    if (!resolutionNotes.trim()) {
      setErrorMsg("Please provide an adjudication note for the audit record.");
      return;
    }
    setErrorMsg("");
    if (onResolve) {
      await onResolve(
        conflict.id,
        resolutionChoice,
        resolutionNotes.trim(),
        preferredClaim
      );
      setShowResolveForm(false);
    }
  };

  return (
    <div className="border border-purple-200 bg-purple-50/20 rounded-xl p-4 space-y-3 shadow-xs">
      {/* Header */}
      <div className="flex items-center justify-between gap-2 flex-wrap pb-2 border-b border-purple-100">
        <div className="flex items-center gap-2">
          <GitCompare className="size-4 text-purple-600" />
          <span className="text-xs font-bold text-slate-900 uppercase">
            {(conflict.conflict_type || "Contradiction").replace(/_/g, " ")}
          </span>
          <span
            className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase border ${
              isUnresolved
                ? "bg-rose-100 text-rose-800 border-rose-200"
                : "bg-emerald-100 text-emerald-800 border-emerald-200"
            }`}
          >
            {conflict.resolution_state}
          </span>
        </div>

        {/* Temporal comparison badge */}
        <span
          className={`px-2 py-0.5 rounded-full text-[10px] font-semibold border flex items-center gap-1 ${temporal.classes}`}
        >
          <Clock className="size-3" />
          {temporal.label}
        </span>
      </div>

      {/* Side-by-side Claims Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {/* Claim A Card */}
        <div className="bg-white border border-slate-200 rounded-lg p-3 space-y-2">
          <div className="flex items-center justify-between text-[11px] pb-1 border-b border-slate-100">
            <span className="font-bold text-slate-700 flex items-center gap-1">
              {getSourceIcon(conflict.claim_a_source_type)}
              {conflict.claim_a_source_title || "Claim A Source"}
            </span>
            {conflict.claim_a_source_timestamp && (
              <span className="text-[10px] text-slate-600">
                {new Date(conflict.claim_a_source_timestamp).toLocaleDateString()}
              </span>
            )}
          </div>
          <div className="text-xs text-slate-800 font-serif italic bg-slate-50 p-2.5 rounded border border-slate-100 leading-relaxed">
            &ldquo;{conflict.claim_a_text}&rdquo;
          </div>
        </div>

        {/* Claim B Card */}
        <div className="bg-white border border-purple-200 rounded-lg p-3 space-y-2">
          <div className="flex items-center justify-between text-[11px] pb-1 border-b border-purple-100">
            <span className="font-bold text-purple-900 flex items-center gap-1">
              {getSourceIcon(conflict.claim_b_source_type)}
              {conflict.claim_b_source_title || "Claim B Source"}
            </span>
            {conflict.claim_b_source_timestamp && (
              <span className="text-[10px] text-slate-600">
                {new Date(conflict.claim_b_source_timestamp).toLocaleDateString()}
              </span>
            )}
          </div>
          <div className="text-xs text-slate-800 font-serif italic bg-purple-50/50 p-2.5 rounded border border-purple-100 leading-relaxed">
            &ldquo;{conflict.claim_b_text}&rdquo;
          </div>
        </div>
      </div>

      {/* AI Explanation / Nuance Note */}
      {conflict.explanation && (
        <div className="p-2.5 rounded-lg bg-indigo-50/60 border border-indigo-100 flex items-start gap-2 text-xs text-indigo-950">
          <Sparkles className="size-4 text-indigo-600 shrink-0 mt-0.5" />
          <div className="leading-relaxed">
            <strong className="text-indigo-900">AI Contradiction Analysis: </strong>
            {conflict.explanation}
          </div>
        </div>
      )}

      {/* Resolution status / Adjudication Trigger */}
      {isUnresolved && onResolve && (
        <div className="pt-1">
          {!showResolveForm ? (
            <button
              type="button"
              onClick={() => setShowResolveForm(true)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-purple-700 hover:bg-purple-800 text-white rounded-lg text-xs font-semibold shadow-xs transition cursor-pointer"
            >
              <span>Adjudicate Contradiction</span>
              <ChevronDown className="size-3.5" />
            </button>
          ) : (
            <div className="bg-white border border-slate-200 rounded-xl p-3.5 space-y-3 animate-in fade-in-50">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-slate-900">
                  Adjudicate Conflict Resolution
                </span>
                <button
                  type="button"
                  onClick={() => setShowResolveForm(false)}
                  className="text-xs text-slate-500 hover:text-slate-700 cursor-pointer"
                >
                  <ChevronUp className="size-4" />
                </button>
              </div>

              {/* Resolution state radio choices */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
                {[
                  { id: "superseded", label: "Superseded" },
                  { id: "reconciled", label: "Reconciled" },
                  { id: "dismissed", label: "Dismissed" },
                ].map((choice) => (
                  <label
                    key={choice.id}
                    className={`flex items-center justify-center p-2 rounded-lg border cursor-pointer font-medium text-center transition ${
                      resolutionChoice === choice.id
                        ? "bg-purple-50 border-purple-500 text-purple-900 font-bold"
                        : "bg-slate-50 border-slate-200 text-slate-700 hover:bg-slate-100"
                    }`}
                  >
                    <input
                      type="radio"
                      name={`resolution_${conflict.id}`}
                      value={choice.id}
                      checked={resolutionChoice === choice.id}
                      onChange={() => setResolutionChoice(choice.id)}
                      className="sr-only"
                    />
                    {choice.label}
                  </label>
                ))}
              </div>

              {/* Preferred Claim selection */}
              {resolutionChoice === "superseded" && (
                <div className="space-y-1">
                  <span className="text-[11px] font-semibold text-slate-700">
                    Which claim is authoritative?
                  </span>
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <label
                      className={`flex items-center gap-1.5 p-2 rounded border cursor-pointer ${
                        preferredClaim === "claim_a"
                          ? "bg-blue-50 border-blue-400 text-blue-900"
                          : "bg-slate-50 border-slate-200"
                      }`}
                    >
                      <input
                        type="radio"
                        name={`preferred_${conflict.id}`}
                        value="claim_a"
                        checked={preferredClaim === "claim_a"}
                        onChange={() => setPreferredClaim("claim_a")}
                        className="sr-only"
                      />
                      <span>Claim A (Earlier)</span>
                    </label>
                    <label
                      className={`flex items-center gap-1.5 p-2 rounded border cursor-pointer ${
                        preferredClaim === "claim_b"
                          ? "bg-purple-50 border-purple-400 text-purple-900"
                          : "bg-slate-50 border-slate-200"
                      }`}
                    >
                      <input
                        type="radio"
                        name={`preferred_${conflict.id}`}
                        value="claim_b"
                        checked={preferredClaim === "claim_b"}
                        onChange={() => setPreferredClaim("claim_b")}
                        className="sr-only"
                      />
                      <span>Claim B (Later)</span>
                    </label>
                  </div>
                </div>
              )}

              {/* Rationale Textarea */}
              <div className="space-y-1">
                <label className="text-[11px] font-semibold text-slate-700">
                  Adjudication Rationale / Audit Notes (Required)
                </label>
                <textarea
                  value={resolutionNotes}
                  onChange={(e) => setResolutionNotes(e.target.value)}
                  placeholder="Explain why this resolution was selected for the audit trail..."
                  rows={2}
                  className="w-full text-xs p-2 bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500 text-slate-900"
                />
              </div>

              {errorMsg && (
                <div className="text-xs text-rose-700 flex items-center gap-1">
                  <AlertTriangle className="size-3.5 text-rose-600" />
                  <span>{errorMsg}</span>
                </div>
              )}

              <div className="flex items-center justify-end gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => setShowResolveForm(false)}
                  className="px-3 py-1.5 rounded-lg border border-slate-200 text-xs text-slate-600 hover:bg-slate-50 cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleConfirmResolve}
                  disabled={resolving}
                  className="px-3.5 py-1.5 rounded-lg bg-purple-700 hover:bg-purple-800 text-white text-xs font-semibold shadow-xs transition disabled:opacity-50 cursor-pointer"
                >
                  {resolving ? "Saving..." : "Confirm Adjudication"}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* If already resolved, show notes */}
      {!isUnresolved && conflict.resolution_notes && (
        <div className="p-2.5 rounded-lg bg-emerald-50/70 border border-emerald-200 text-xs text-emerald-950 flex items-start gap-2">
          <CheckCircle2 className="size-3.5 text-emerald-600 shrink-0 mt-0.5" />
          <div>
            <strong>Adjudication Rationale:</strong> {conflict.resolution_notes}
          </div>
        </div>
      )}
    </div>
  );
};
