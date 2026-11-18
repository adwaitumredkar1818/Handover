"use client";

import React from "react";
import {
  CheckCircle2,
  XCircle,
  Edit3,
  HelpCircle,
  AlertCircle,
  UserCheck,
  RefreshCw,
  AlertTriangle,
  FileCheck,
  Layers,
  MessageSquare,
} from "lucide-react";
import { VerificationHistoryTimeline } from "./VerificationHistoryTimeline";
import type { ReviewerActionPanelProps } from "./types";

export const ReviewerActionPanel: React.FC<ReviewerActionPanelProps> = ({
  caseDetail,
  reviewerNote,
  onReviewerNoteChange,
  actionLoading,
  concurrencyConflict,
  onReloadLatest,
  onApprove,
  onReject,
  onOpenEditModal,
  onOpenRequestContextModal,
  onMarkUnresolved,
  onAssignReviewer,
  members,
  currentUserId: _currentUserId,
}) => {
  if (!caseDetail) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-8 text-center text-slate-400">
        <FileCheck className="size-10 text-slate-300 mb-3" />
        <h3 className="text-sm font-semibold text-slate-700">No Case Selected</h3>
        <p className="text-xs text-slate-500 mt-1 max-w-xs">
          Select a candidate finding to perform verification sign-off, request team clarification, or record audit notes.
        </p>
      </div>
    );
  }

  const status = caseDetail.case_status || "pending_review";
  const version = caseDetail.version || 1;
  const isVerified = status === "verified" || status === "approved";
  const isRejected = status === "rejected";
  const isUnresolved = status === "unresolved";

  const assignedUser = members.find(
    (m) =>
      m.user_id === caseDetail.assigned_reviewer_id ||
      m.user?.id === caseDetail.assigned_reviewer_id ||
      m.id === caseDetail.assigned_reviewer_id
  );

  return (
    <div className="flex flex-col h-full bg-white overflow-y-auto p-5 space-y-4">
      {/* Panel Header & Monotonic Version Badge */}
      <div className="flex items-center justify-between pb-2 border-b border-slate-200">
        <div>
          <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2">
            <FileCheck className="size-4 text-teal-700" />
            Reviewer Decision & Actions
          </h2>
          <p className="text-[11px] text-slate-500 mt-0.5">
            Epistemic sign-off with audit trail provenance
          </p>
        </div>

        {/* Optimistic Concurrency Version Badge */}
        <div
          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-mono font-bold bg-slate-100 text-slate-800 border border-slate-200 shadow-2xs"
          title="Monotonic snapshot version for optimistic concurrency control"
        >
          <Layers className="size-3 text-slate-500" />
          <span>v{version}</span>
        </div>
      </div>

      {/* HTTP 409 Concurrency Conflict Alert Banner */}
      {concurrencyConflict?.isConflict && (
        <div className="p-3.5 bg-amber-50 border-l-4 border-amber-500 rounded-r-xl shadow-xs space-y-2 animate-in fade-in-50">
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-start gap-2">
              <AlertTriangle className="size-4 text-amber-600 shrink-0 mt-0.5" />
              <div>
                <h4 className="text-xs font-bold text-amber-900">
                  Concurrent Modification Detected
                </h4>
                <p className="text-[11px] text-amber-800 mt-0.5 leading-snug">
                  {concurrencyConflict.message ||
                    "Another reviewer updated this finding in the database. Your version is out of date."}
                </p>
              </div>
            </div>

            <button
              type="button"
              onClick={onReloadLatest}
              className="shrink-0 px-3 py-1.5 bg-amber-600 hover:bg-amber-700 text-white text-xs font-semibold rounded-lg shadow-2xs transition flex items-center gap-1.5 cursor-pointer"
            >
              <RefreshCw className="size-3.5" />
              <span>Reload Latest</span>
            </button>
          </div>
          <p className="text-[10px] text-amber-700 italic">
            * Your unsaved reviewer note in the textarea below is preserved!
          </p>
        </div>
      )}

      {/* Decision Status Banner */}
      <div
        className={`p-3 rounded-xl border flex items-center gap-2.5 ${
          isVerified
            ? "bg-emerald-50 border-emerald-200 text-emerald-900"
            : isRejected
            ? "bg-rose-50 border-rose-200 text-rose-900"
            : isUnresolved
            ? "bg-amber-50 border-amber-200 text-amber-900"
            : "bg-blue-50 border-blue-200 text-blue-900"
        }`}
      >
        {isVerified ? (
          <CheckCircle2 className="size-5 text-emerald-600 shrink-0" />
        ) : isRejected ? (
          <XCircle className="size-5 text-rose-600 shrink-0" />
        ) : isUnresolved ? (
          <AlertCircle className="size-5 text-amber-600 shrink-0" />
        ) : (
          <HelpCircle className="size-5 text-blue-600 shrink-0" />
        )}

        <div>
          <div className="text-xs font-bold uppercase tracking-wide">
            {isVerified
              ? "Human-Verified Truth"
              : isRejected
              ? "Rejected Finding"
              : isUnresolved
              ? "Marked Unresolved"
              : "Awaiting Human Review"}
          </div>
          <div className="text-[11px] opacity-80 leading-snug">
            {isVerified
              ? "Approved for downstream handover dossiers."
              : isRejected
              ? "Excluded from downstream handover compilation."
              : isUnresolved
              ? "Consensus not established. Requires domain expert."
              : "Carefully inspect supporting citations before promoting."}
          </div>
        </div>
      </div>

      {/* Reviewer Assignment Row */}
      <div className="p-3 bg-slate-50/80 rounded-xl border border-slate-200 space-y-1.5">
        <label className="text-xs font-bold text-slate-700 flex items-center gap-1.5">
          <UserCheck className="size-3.5 text-slate-500" />
          Assigned Reviewer
        </label>
        <div className="flex items-center gap-2">
          <select
            value={caseDetail.assigned_reviewer_id || ""}
            onChange={(e) => onAssignReviewer(e.target.value || null)}
            disabled={actionLoading}
            className="flex-1 text-xs bg-white border border-slate-200 rounded-lg p-2 text-slate-800 focus:outline-none focus:ring-2 focus:ring-teal-500 cursor-pointer disabled:opacity-50"
          >
            <option value="">-- Unassigned (Available in Queue) --</option>
            {members.map((m) => {
              const uId = m.user_id || m.user?.id || m.id;
              const name = m.user?.name || m.user?.email || `Member (${uId.slice(0, 8)})`;
              return (
                <option key={uId} value={uId}>
                  {name}
                </option>
              );
            })}
          </select>
          {assignedUser && (
            <span className="text-[11px] text-teal-700 font-semibold px-2 py-1 bg-teal-50 rounded border border-teal-200">
              Assigned
            </span>
          )}
        </div>
      </div>

      {/* Reviewer Rationale / Notes Textarea */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between text-xs font-bold text-slate-700">
          <span>Reviewer Notes & Rationale</span>
          <span className="text-[10px] text-slate-600 font-normal">
            Appended to audit trail
          </span>
        </div>
        <textarea
          value={reviewerNote}
          onChange={(e) => onReviewerNoteChange(e.target.value)}
          placeholder="Provide rationale or audit justification for your verification decision..."
          rows={3}
          disabled={actionLoading}
          className="w-full text-xs p-3 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-teal-500 focus:bg-white text-slate-900 leading-relaxed disabled:opacity-50 transition"
        />
      </div>

      {/* Primary Actions Grid */}
      <div className="space-y-2">
        <div className="grid grid-cols-2 gap-2">
          {/* Approve Button */}
          <button
            type="button"
            onClick={onApprove}
            disabled={actionLoading}
            className="w-full py-2.5 px-3 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-xs font-bold shadow-xs hover:shadow transition flex items-center justify-center gap-1.5 disabled:opacity-50 cursor-pointer"
          >
            <CheckCircle2 className="size-4" />
            <span>Approve Finding</span>
          </button>

          {/* Reject Button */}
          <button
            type="button"
            onClick={onReject}
            disabled={actionLoading}
            className="w-full py-2.5 px-3 bg-rose-600 hover:bg-rose-700 text-white rounded-xl text-xs font-bold shadow-xs hover:shadow transition flex items-center justify-center gap-1.5 disabled:opacity-50 cursor-pointer"
          >
            <XCircle className="size-4" />
            <span>Reject Finding</span>
          </button>
        </div>

        {/* Secondary Actions Row */}
        <div className="grid grid-cols-3 gap-2 text-xs">
          <button
            type="button"
            onClick={onOpenEditModal}
            disabled={actionLoading}
            className="py-2 px-2.5 bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 rounded-lg font-medium transition shadow-2xs flex items-center justify-center gap-1 disabled:opacity-50 cursor-pointer"
            title="Edit finding title or summary"
          >
            <Edit3 className="size-3.5 text-teal-600" />
            <span>Edit</span>
          </button>

          <button
            type="button"
            onClick={onOpenRequestContextModal}
            disabled={actionLoading}
            className="py-2 px-2.5 bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 rounded-lg font-medium transition shadow-2xs flex items-center justify-center gap-1 disabled:opacity-50 cursor-pointer"
            title="Ask clarification from project team members"
          >
            <MessageSquare className="size-3.5 text-purple-600" />
            <span>Ask Context</span>
          </button>

          <button
            type="button"
            onClick={onMarkUnresolved}
            disabled={actionLoading}
            className="py-2 px-2.5 bg-white border border-amber-200 hover:bg-amber-50 text-amber-800 rounded-lg font-medium transition shadow-2xs flex items-center justify-center gap-1 disabled:opacity-50 cursor-pointer"
            title="Flag finding as unresolved"
          >
            <AlertCircle className="size-3.5 text-amber-600" />
            <span>Unresolved</span>
          </button>
        </div>
      </div>

      {/* Audit History Timeline */}
      <div className="pt-2">
        <VerificationHistoryTimeline
          events={caseDetail.review_events || []}
          contextRequests={caseDetail.context_requests || []}
        />
      </div>
    </div>
  );
};
