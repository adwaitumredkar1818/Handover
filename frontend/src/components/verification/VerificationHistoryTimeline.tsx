"use client";

import React, { useState } from "react";
import {
  History,
  CheckCircle2,
  XCircle,
  Edit3,
  HelpCircle,
  UserCheck,
  Clock,
  ChevronDown,
  ChevronUp,
  AlertCircle,
  MessageSquare,
} from "lucide-react";
import type { VerificationReviewEvent, VerificationContextRequest } from "./types";

interface VerificationHistoryTimelineProps {
  events: VerificationReviewEvent[];
  contextRequests?: VerificationContextRequest[];
}

export const VerificationHistoryTimeline: React.FC<VerificationHistoryTimelineProps> = ({
  events,
  contextRequests = [],
}) => {
  const [isExpanded, setIsExpanded] = useState(true);
  const [expandedDiffs, setExpandedDiffs] = useState<Record<string, boolean>>({});

  const toggleDiff = (eventId: string) => {
    setExpandedDiffs((prev) => ({ ...prev, [eventId]: !prev[eventId] }));
  };

  const getActionBadge = (action: string) => {
    switch (action.toLowerCase()) {
      case "approve":
      case "approved":
        return {
          icon: CheckCircle2,
          label: "Approved",
          classes: "bg-emerald-100 text-emerald-800 border-emerald-200",
        };
      case "reject":
      case "rejected":
        return {
          icon: XCircle,
          label: "Rejected",
          classes: "bg-rose-100 text-rose-800 border-rose-200",
        };
      case "edit":
      case "edited":
      case "patch":
        return {
          icon: Edit3,
          label: "Finding Corrected",
          classes: "bg-blue-100 text-blue-800 border-blue-200",
        };
      case "assign":
      case "assigned":
        return {
          icon: UserCheck,
          label: "Reviewer Assigned",
          classes: "bg-indigo-100 text-indigo-800 border-indigo-200",
        };
      case "mark_unresolved":
      case "unresolved":
        return {
          icon: AlertCircle,
          label: "Marked Unresolved",
          classes: "bg-amber-100 text-amber-800 border-amber-200",
        };
      case "context_request":
        return {
          icon: HelpCircle,
          label: "Context Requested",
          classes: "bg-purple-100 text-purple-800 border-purple-200",
        };
      default:
        return {
          icon: Clock,
          label: action,
          classes: "bg-slate-100 text-slate-800 border-slate-200",
        };
    }
  };

  return (
    <div className="border border-slate-200 rounded-xl overflow-hidden bg-white shadow-2xs">
      {/* Collapsible Header */}
      <button
        type="button"
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between p-3.5 bg-slate-50 hover:bg-slate-100 text-xs font-bold text-slate-800 transition cursor-pointer"
      >
        <div className="flex items-center gap-2">
          <History className="size-4 text-teal-700" />
          <span>Audit Event Provenance & History ({events.length})</span>
        </div>
        {isExpanded ? (
          <ChevronUp className="size-4 text-slate-500" />
        ) : (
          <ChevronDown className="size-4 text-slate-500" />
        )}
      </button>

      {isExpanded && (
        <div className="p-4 space-y-4">
          {/* Clarification Q&A Inquiries if any */}
          {contextRequests.length > 0 && (
            <div className="space-y-2 mb-3 pb-3 border-b border-slate-100">
              <span className="text-[11px] font-bold text-slate-700 flex items-center gap-1">
                <MessageSquare className="size-3 text-purple-600" />
                Team Clarification Inquiries ({contextRequests.length})
              </span>
              <div className="space-y-2">
                {contextRequests.map((req) => (
                  <div
                    key={req.id}
                    className="p-2.5 bg-purple-50/50 border border-purple-200 rounded-lg text-xs space-y-1.5"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-purple-900">
                        Type: {req.requested_information_type.replace(/_/g, " ")}
                      </span>
                      <span
                        className={`px-1.5 py-0.2 rounded text-[10px] font-bold uppercase ${
                          req.status === "responded"
                            ? "bg-emerald-100 text-emerald-800"
                            : "bg-amber-100 text-amber-800"
                        }`}
                      >
                        {req.status}
                      </span>
                    </div>
                    <p className="text-slate-800 italic">&ldquo;{req.question}&rdquo;</p>
                    {req.response_text && (
                      <div className="mt-1 pt-1 border-t border-purple-200 text-emerald-900">
                        <strong>Response:</strong> {req.response_text}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Audit Events List */}
          {events.length === 0 ? (
            <p className="text-xs text-slate-500 italic text-center py-2">
              No audit review events recorded yet for this candidate finding.
            </p>
          ) : (
            <div className="relative pl-4 space-y-4 before:absolute before:left-1.5 before:top-2 before:bottom-2 before:w-0.5 before:bg-slate-200">
              {events.map((evt) => {
                const badge = getActionBadge(evt.action || evt.event_type || "REVIEW");
                const Icon = badge.icon;
                const noteText = evt.review_notes || evt.notes;
                const hasDiff = Boolean(
                  evt.finding_patch_json ||
                  (evt.previous_snapshot_json && evt.new_snapshot_json)
                );
                const isDiffOpen = expandedDiffs[evt.id] || false;

                const prevSnap = evt.previous_snapshot_json || {};
                const newSnap = evt.new_snapshot_json || {};

                return (
                  <div key={evt.id} className="relative space-y-1">
                    {/* Event Dot */}
                    <div className="absolute -left-4 top-1 size-3 rounded-full bg-white border-2 border-teal-600 ring-2 ring-white" />

                    {/* Event Header row */}
                    <div className="flex items-center justify-between gap-2 text-xs">
                      <div className="flex items-center gap-1.5">
                        <span
                          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold border uppercase ${badge.classes}`}
                        >
                          <Icon className="size-2.5" />
                          {badge.label}
                        </span>
                        <span className="text-[11px] text-slate-500">
                          by <strong className="text-slate-700 font-mono text-[10px]">{evt.reviewer_user_id?.slice(0, 8)}</strong>
                        </span>
                      </div>
                      <span className="text-[10px] text-slate-600 font-mono">
                        {new Date(evt.created_at).toLocaleString()}
                      </span>
                    </div>

                    {/* Reviewer Note */}
                    {noteText && (
                      <p className="text-xs text-slate-700 bg-slate-50 p-2 rounded-lg border border-slate-100 font-sans">
                        {noteText}
                      </p>
                    )}

                    {/* Visual Diff Viewer for finding modifications */}
                    {hasDiff && (
                      <div className="pt-1">
                        <button
                          type="button"
                          onClick={() => toggleDiff(evt.id)}
                          className="text-[11px] font-medium text-teal-700 hover:text-teal-900 flex items-center gap-1 cursor-pointer"
                        >
                          <span>{isDiffOpen ? "Hide Snapshot Diff ▲" : "View Snapshot Diff ▼"}</span>
                        </button>

                        {isDiffOpen && (
                          <div className="mt-2 p-3 bg-slate-900 text-slate-200 rounded-lg text-[11px] font-mono space-y-2 max-h-48 overflow-y-auto">
                            {/* Before snapshot */}
                            {Boolean(prevSnap.title) && (
                              <div className="space-y-1">
                                <span className="text-rose-400 font-bold block text-[10px]">
                                  - PREVIOUS TITLE:
                                </span>
                                <div className="p-1 bg-rose-950/60 rounded line-through text-rose-300">
                                  {String(prevSnap.title)}
                                </div>
                              </div>
                            )}

                            {/* After snapshot */}
                            {Boolean(newSnap.title) && (
                              <div className="space-y-1">
                                <span className="text-emerald-400 font-bold block text-[10px]">
                                  + NEW TITLE:
                                </span>
                                <div className="p-1 bg-emerald-950/60 rounded text-emerald-300">
                                  {String(newSnap.title)}
                                </div>
                              </div>
                            )}

                            {/* Patch data raw display */}
                            {evt.finding_patch_json && (
                              <div className="pt-1">
                                <span className="text-cyan-400 text-[10px] font-bold block">
                                  PATCH PAYLOAD:
                                </span>
                                <pre className="text-[10px] text-slate-300 overflow-x-auto">
                                  {JSON.stringify(evt.finding_patch_json, null, 2)}
                                </pre>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
