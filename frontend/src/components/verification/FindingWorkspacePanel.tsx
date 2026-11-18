"use client";

import React, { useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  Compass,
  Edit3,
  ExternalLink,
  FileCheck2,
  FileSearch,
  GitCompare,
  GitFork,
  HelpCircle,
  Layers,
  Lock,
  Maximize2,
  MessageSquarePlus,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  User as UserIcon,
  XCircle,
} from "lucide-react";
import type { ProjectMember } from "../../lib/types";
import type {
  EvidenceReferenceDetail,
  VerificationCaseDetail,
} from "../../lib/verificationApi";
import {
  CATEGORY_LABELS,
  STATUS_META,
  formatDomainLabel,
  formatTimestamp,
} from "./verificationTheme";
import { EvidenceSourceDrawer } from "./EvidenceSourceDrawer";

// ─────────────────────────────────────────────
//  Reviewer Decision Bar (inline, bottom of panel)
// ─────────────────────────────────────────────

type FormMode =
  | "none"
  | "confirm_approve"
  | "confirm_reject"
  | "edit"
  | "context"
  | "confirm_unresolved";

interface ReviewerDecisionBarProps {
  detail: VerificationCaseDetail;
  members: ProjectMember[];
  busy: boolean;
  onApprove: (note: string, reason: string) => Promise<void>;
  onReject: (reason: string, note: string) => Promise<void>;
  onEditFinding: (claim: string, domain: string, editReason: string, note: string) => Promise<void>;
  onRequestContext: (recipientUserId: string, question: string, note: string) => Promise<void>;
  onMarkUnresolved: (reason: string, note: string) => Promise<void>;
  onAssignReviewer: (reviewerId: string | null) => Promise<void>;
}

function ReviewerDecisionBar({
  detail,
  members,
  busy,
  onApprove,
  onReject,
  onEditFinding,
  onRequestContext,
  onMarkUnresolved,
  onAssignReviewer,
}: ReviewerDecisionBarProps) {
  const [mode, setMode] = useState<FormMode>("none");
  const [reviewerNote, setReviewerNote] = useState("");
  const [decisionReason, setDecisionReason] = useState("");
  const [editClaim, setEditClaim] = useState(detail.current_claim);
  const [editDomain, setEditDomain] = useState(detail.domain);
  const [editReason, setEditReason] = useState("");
  const [contextRecipient, setContextRecipient] = useState(members[0]?.user_id ?? "");
  const [contextQuestion, setContextQuestion] = useState("");

  // Reset forms when finding changes
  useEffect(() => {
    setMode("none");
    setReviewerNote("");
    setDecisionReason("");
    setEditClaim(detail.current_claim);
    setEditDomain(detail.domain);
    setEditReason("");
    setContextQuestion("");
    if (members[0] && !contextRecipient) setContextRecipient(members[0].user_id);
  }, [detail.id]);

  const isRejected = detail.case_status === "rejected";
  const isVerified = detail.case_status === "verified";
  const isConflicted = detail.case_status === "conflicted";

  const closeAndReset = () => {
    setMode("none");
    setReviewerNote("");
    setDecisionReason("");
    setEditReason("");
    setContextQuestion("");
  };

  return (
    <div className="border-t border-slate-200 bg-slate-50/80 px-5 py-4 space-y-3 shrink-0">
      {/* Reviewer assignment */}
      <div className="flex items-center gap-3 text-xs">
        <label htmlFor="assign-reviewer-bar" className="font-medium text-slate-600 shrink-0">
          Reviewer:
        </label>
        <select
          id="assign-reviewer-bar"
          disabled={busy}
          value={detail.assigned_reviewer_id ?? ""}
          onChange={(e) => void onAssignReviewer(e.target.value || null)}
          className="text-xs px-2.5 py-1.5 rounded-lg border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 flex-1 max-w-xs"
        >
          <option value="">Unassigned</option>
          {members.map((m) => (
            <option key={m.user_id} value={m.user_id}>
              {m.full_name || m.email} ({m.role_name})
            </option>
          ))}
        </select>
      </div>

      {/* Inline sub-forms */}
      {mode === "confirm_approve" && (
        <div className="p-3.5 rounded-lg border border-emerald-200 bg-emerald-50 space-y-2.5">
          <p className="text-xs font-medium text-emerald-900">
            Confirm approval? This marks the finding as Verified and eligible for the Handover Workspace.
          </p>
          {isConflicted && !decisionReason.trim() && (
            <p className="text-[11px] text-rose-700">
              A decision reason is required to resolve this conflicted finding.
            </p>
          )}
          <input
            type="text"
            value={reviewerNote}
            onChange={(e) => setReviewerNote(e.target.value)}
            placeholder="Optional reviewer note..."
            className="w-full text-xs px-2.5 py-1.5 rounded border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          {isConflicted && (
            <input
              type="text"
              value={decisionReason}
              onChange={(e) => setDecisionReason(e.target.value)}
              placeholder="Decision reason (required for conflicted findings)..."
              className="w-full text-xs px-2.5 py-1.5 rounded border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          )}
          <div className="flex gap-2">
            <button
              type="button"
              disabled={busy || (isConflicted && !decisionReason.trim())}
              onClick={async () => {
                await onApprove(reviewerNote, decisionReason);
                closeAndReset();
              }}
              className="flex-1 py-1.5 rounded bg-emerald-600 text-white text-xs font-semibold hover:bg-emerald-700 disabled:opacity-50"
            >
              {busy ? "Saving..." : "Confirm Approve"}
            </button>
            <button type="button" onClick={closeAndReset} className="px-3 py-1.5 rounded border border-slate-300 bg-white text-xs text-slate-700">
              Cancel
            </button>
          </div>
        </div>
      )}

      {mode === "confirm_reject" && (
        <div className="p-3.5 rounded-lg border border-rose-200 bg-rose-50 space-y-2.5">
          <p className="text-xs font-medium text-rose-900">
            Confirm rejection? The finding is retained in audit history and excluded from handover.
          </p>
          <input
            type="text"
            value={decisionReason}
            onChange={(e) => setDecisionReason(e.target.value)}
            placeholder="Rejection reason (required)..."
            className="w-full text-xs px-2.5 py-1.5 rounded border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <input
            type="text"
            value={reviewerNote}
            onChange={(e) => setReviewerNote(e.target.value)}
            placeholder="Optional reviewer note..."
            className="w-full text-xs px-2.5 py-1.5 rounded border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <div className="flex gap-2">
            <button
              type="button"
              disabled={busy || !decisionReason.trim()}
              onClick={async () => {
                await onReject(decisionReason.trim(), reviewerNote);
                closeAndReset();
              }}
              className="flex-1 py-1.5 rounded bg-rose-600 text-white text-xs font-semibold hover:bg-rose-700 disabled:opacity-50"
            >
              {busy ? "Saving..." : "Confirm Reject"}
            </button>
            <button type="button" onClick={closeAndReset} className="px-3 py-1.5 rounded border border-slate-300 bg-white text-xs text-slate-700">
              Cancel
            </button>
          </div>
        </div>
      )}

      {mode === "edit" && (
        <div className="p-3.5 rounded-lg border border-blue-200 bg-blue-50/50 space-y-2.5">
          <p className="text-xs font-semibold text-blue-900">Edit Finding (AI original preserved)</p>
          <textarea
            rows={3}
            value={editClaim}
            onChange={(e) => setEditClaim(e.target.value)}
            placeholder="Updated structured claim..."
            className="w-full text-xs px-2.5 py-1.5 rounded border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <input
            type="text"
            value={editDomain}
            onChange={(e) => setEditDomain(e.target.value)}
            placeholder="Domain (optional override)..."
            className="w-full text-xs px-2.5 py-1.5 rounded border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <input
            type="text"
            value={editReason}
            onChange={(e) => setEditReason(e.target.value)}
            placeholder="Mandatory correction reason..."
            className="w-full text-xs px-2.5 py-1.5 rounded border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <div className="flex gap-2">
            <button
              type="button"
              disabled={busy || !editClaim.trim() || !editReason.trim()}
              onClick={async () => {
                await onEditFinding(editClaim.trim(), editDomain.trim(), editReason.trim(), reviewerNote);
                closeAndReset();
              }}
              className="flex-1 py-1.5 rounded bg-blue-600 text-white text-xs font-semibold hover:bg-blue-700 disabled:opacity-50"
            >
              {busy ? "Saving..." : "Save Revision"}
            </button>
            <button type="button" onClick={closeAndReset} className="px-3 py-1.5 rounded border border-slate-300 bg-white text-xs text-slate-700">
              Cancel
            </button>
          </div>
        </div>
      )}

      {mode === "context" && (
        <div className="p-3.5 rounded-lg border border-slate-300 bg-slate-50 space-y-2.5">
          <p className="text-xs font-semibold text-slate-800">Request Additional Context</p>
          <select
            value={contextRecipient}
            onChange={(e) => setContextRecipient(e.target.value)}
            className="w-full text-xs px-2.5 py-1.5 rounded border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            {members.map((m) => (
              <option key={m.user_id} value={m.user_id}>
                {m.full_name || m.email} ({m.role_name})
              </option>
            ))}
          </select>
          <textarea
            rows={2}
            value={contextQuestion}
            onChange={(e) => setContextQuestion(e.target.value)}
            placeholder="What clarification or source record is needed?"
            className="w-full text-xs px-2.5 py-1.5 rounded border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <div className="flex gap-2">
            <button
              type="button"
              disabled={busy || !contextRecipient || !contextQuestion.trim()}
              onClick={async () => {
                await onRequestContext(contextRecipient, contextQuestion.trim(), reviewerNote);
                closeAndReset();
              }}
              className="flex-1 py-1.5 rounded bg-slate-900 text-white text-xs font-semibold hover:bg-slate-800 disabled:opacity-50"
            >
              {busy ? "Sending..." : "Send Request"}
            </button>
            <button type="button" onClick={closeAndReset} className="px-3 py-1.5 rounded border border-slate-300 bg-white text-xs text-slate-700">
              Cancel
            </button>
          </div>
        </div>
      )}

      {mode === "confirm_unresolved" && (
        <div className="p-3.5 rounded-lg border border-amber-200 bg-amber-50 space-y-2.5">
          <p className="text-xs font-medium text-amber-900">
            Mark as Unresolved? This blocks the finding from approved handover.
          </p>
          <input
            type="text"
            value={decisionReason}
            onChange={(e) => setDecisionReason(e.target.value)}
            placeholder="Explanation reason (required)..."
            className="w-full text-xs px-2.5 py-1.5 rounded border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <div className="flex gap-2">
            <button
              type="button"
              disabled={busy || !decisionReason.trim()}
              onClick={async () => {
                await onMarkUnresolved(decisionReason.trim(), reviewerNote);
                closeAndReset();
              }}
              className="flex-1 py-1.5 rounded bg-amber-600 text-white text-xs font-semibold hover:bg-amber-700 disabled:opacity-50"
            >
              {busy ? "Saving..." : "Confirm Unresolved"}
            </button>
            <button type="button" onClick={closeAndReset} className="px-3 py-1.5 rounded border border-slate-300 bg-white text-xs text-slate-700">
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Five action buttons */}
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={busy || isRejected || isVerified}
          onClick={() => setMode("confirm_approve")}
          className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-emerald-600 text-white text-xs font-semibold hover:bg-emerald-700 disabled:opacity-40 transition-colors"
        >
          <CheckCircle2 className="w-3.5 h-3.5" />
          Approve
        </button>

        <button
          type="button"
          disabled={busy || isRejected}
          onClick={() => setMode("confirm_reject")}
          className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-rose-300 bg-rose-50 text-rose-800 text-xs font-semibold hover:bg-rose-100 disabled:opacity-40 transition-colors"
        >
          <XCircle className="w-3.5 h-3.5" />
          Reject
        </button>

        <button
          type="button"
          disabled={busy}
          onClick={() => setMode("edit")}
          className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-slate-300 bg-white text-slate-800 text-xs font-semibold hover:bg-slate-50 disabled:opacity-40 transition-colors"
        >
          <Edit3 className="w-3.5 h-3.5" />
          Edit Finding
        </button>

        <button
          type="button"
          disabled={busy || members.length === 0}
          onClick={() => setMode("context")}
          className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-slate-300 bg-white text-slate-800 text-xs font-semibold hover:bg-slate-50 disabled:opacity-40 transition-colors"
        >
          <MessageSquarePlus className="w-3.5 h-3.5" />
          Request Context
        </button>

        <button
          type="button"
          disabled={busy || isRejected}
          onClick={() => setMode("confirm_unresolved")}
          className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-amber-300 bg-amber-50 text-amber-900 text-xs font-semibold hover:bg-amber-100 disabled:opacity-40 transition-colors"
        >
          <HelpCircle className="w-3.5 h-3.5" />
          Mark Unresolved
        </button>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────
//  Main Finding Workspace Panel
// ─────────────────────────────────────────────

interface FindingWorkspacePanelProps {
  detail: VerificationCaseDetail | null;
  loading: boolean;
  members: ProjectMember[];
  busy: boolean;
  onApprove: (note: string, reason: string) => Promise<void>;
  onReject: (reason: string, note: string) => Promise<void>;
  onEditFinding: (claim: string, domain: string, editReason: string, note: string) => Promise<void>;
  onRequestContext: (recipientUserId: string, question: string, note: string) => Promise<void>;
  onMarkUnresolved: (reason: string, note: string) => Promise<void>;
  onAssignReviewer: (reviewerId: string | null) => Promise<void>;
  onRespondContextRequest: (requestId: string, responseText: string) => Promise<void>;
}

export function FindingWorkspacePanel({
  detail,
  loading,
  members,
  busy,
  onApprove,
  onReject,
  onEditFinding,
  onRequestContext,
  onMarkUnresolved,
  onAssignReviewer,
  onRespondContextRequest,
}: FindingWorkspacePanelProps) {
  const [drawerEvidence, setDrawerEvidence] = useState<EvidenceReferenceDetail | null>(null);
  const [replyDrafts, setReplyDrafts] = useState<Record<string, string>>({});
  const [submittingReqId, setSubmittingReqId] = useState<string | null>(null);
  const detailScrollRef = useRef<HTMLDivElement | null>(null);

  // Close drawer and reset right-panel scroll position when switching findings
  useEffect(() => {
    setDrawerEvidence(null);
    if (detailScrollRef.current) {
      detailScrollRef.current.scrollTop = 0;
    }
  }, [detail?.id]);

  // Loading skeleton
  if (loading) {
    return (
      <section className="bg-white border border-slate-200 rounded-xl shadow-sm p-6 space-y-4 flex flex-col min-h-0 md:max-h-full">
        <div className="h-6 w-2/3 bg-slate-100 rounded animate-pulse" />
        <div className="h-28 bg-slate-100 rounded animate-pulse" />
        <div className="h-44 bg-slate-100 rounded animate-pulse" />
        <div className="h-28 bg-slate-100 rounded animate-pulse" />
      </section>
    );
  }

  // Empty state
  if (!detail) {
    return (
      <section className="bg-white border border-slate-200 rounded-xl shadow-sm flex flex-col items-center justify-center text-center p-10 min-h-[260px] md:max-h-full">
        <FileSearch className="w-10 h-10 text-slate-300 mb-3" />
        <h2 className="text-base font-semibold text-slate-800">Select a finding to review</h2>
        <p className="text-sm text-slate-500 max-w-sm mt-1">
          Choose any finding from the left queue to inspect its evidence, contradictions, and verification status.
        </p>
      </section>
    );
  }

  const statusMeta = STATUS_META[detail.case_status] ?? STATUS_META.candidate;
  const claimChanged =
    detail.current_claim.trim() !== detail.original_ai_claim.trim() &&
    detail.original_ai_claim.trim().length > 0;

  const supportingEvidence = detail.evidence_references.filter(
    (e) => e.relationship_to_finding !== "opposing"
  );
  const opposingEvidence = detail.evidence_references.filter(
    (e) => e.relationship_to_finding === "opposing"
  );

  return (
    <>
      <section
        aria-label="Finding review workspace"
        className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden flex flex-col min-h-0 md:max-h-full"
      >
        {/* Panel Header (pinned at top of right panel) */}
        <div className="px-5 py-4 border-b border-slate-200 bg-slate-50/70 shrink-0">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="px-2 py-0.5 rounded bg-slate-200/70 text-slate-700 text-xs font-medium">
                {formatDomainLabel(detail.domain)}
              </span>
              <span
                className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border ${statusMeta.badgeClass}`}
              >
                <span className={`w-1.5 h-1.5 rounded-full ${statusMeta.dotClass}`} />
                {statusMeta.label}
              </span>
              <span className="text-xs text-slate-500 font-mono">v{detail.version}</span>
              {detail.priority && (
                <span className="text-xs text-slate-500 capitalize">· {detail.priority} priority</span>
              )}
            </div>

            <span
              className={`inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-md border ${
                detail.handover_eligible
                  ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                  : "bg-slate-100 text-slate-600 border-slate-200"
              }`}
            >
              {detail.handover_eligible ? (
                <CheckCircle2 className="w-3.5 h-3.5" />
              ) : (
                <ShieldAlert className="w-3.5 h-3.5" />
              )}
              {detail.handover_eligible ? "Handover Eligible" : "Blocked from Handover"}
            </span>
          </div>

          <h2 className="text-lg font-semibold text-slate-900 mt-2">{detail.title}</h2>
          <p className="text-xs text-slate-500 mt-0.5">{detail.handover_eligibility_reason}</p>
          {detail.assigned_reviewer_name && (
            <p className="text-xs text-slate-500 mt-0.5 flex items-center gap-1">
              <UserIcon className="w-3 h-3" />
              Assigned to {detail.assigned_reviewer_name}
            </p>
          )}
        </div>

        {/* Scrollable body (content-driven up to available viewport max-height on md+; document flow on mobile) */}
        <div
          ref={detailScrollRef}
          data-testid="finding-detail-scroll"
          className="p-5 space-y-6 md:flex-auto md:min-h-0 md:overflow-y-auto md:overscroll-contain scrollbar-thin"
        >
          {/* Active Contradiction Banner */}
          {detail.case_status === "conflicted" && (
            <div className="p-4 rounded-xl border border-rose-300 bg-rose-50/90 flex items-start justify-between gap-3 shadow-sm">
              <div className="flex items-start gap-3">
                <GitCompare className="w-5 h-5 text-rose-600 shrink-0 mt-0.5" />
                <div className="space-y-1">
                  <h4 className="text-xs font-semibold uppercase tracking-wider text-rose-900">
                    Active Contradiction Detected
                  </h4>
                  <p className="text-xs text-rose-800 leading-relaxed">
                    This finding contains contradictory evidence or claims that require side-by-side comparative investigation.
                  </p>
                </div>
              </div>
              <a
                href={`/conflicts?case_id=${detail.id}`}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-rose-600 text-white text-xs font-semibold hover:bg-rose-700 shadow-sm shrink-0 transition-colors"
              >
                Resolve in Conflicts Workspace
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            </div>
          )}

          {/* Continuous Monitoring Notice */}
          {detail.monitoring_status?.reverification_triggered && (
            <div className="p-4 rounded-xl border border-rose-300 bg-rose-50/90 flex items-start gap-3 shadow-sm">
              <AlertCircle className="w-5 h-5 text-rose-600 shrink-0 mt-0.5" />
              <div className="space-y-1">
                <h4 className="text-xs font-semibold uppercase tracking-wider text-rose-900">
                  Continuous Project Intelligence · Re-Verification Triggered
                </h4>
                <p className="text-xs text-rose-800 leading-relaxed">
                  {detail.monitoring_status.reverification_reason}
                </p>
                <div className="flex items-center gap-3 text-[11px] text-rose-700 pt-1">
                  <span>Change type: <strong className="uppercase">{detail.monitoring_status.change_type}</strong></span>
                  {detail.monitoring_status.last_monitored_at && (
                    <span>Evaluated: {formatTimestamp(detail.monitoring_status.last_monitored_at)}</span>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Explainable Verification Recommendation Banner */}
          {detail.recommendation && (
            <div className="p-4 rounded-xl border border-blue-200 bg-gradient-to-r from-blue-50/90 via-indigo-50/50 to-slate-50 space-y-2.5 shadow-sm">
              <div className="flex items-center justify-between gap-2">
                <span className="inline-flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-blue-900">
                  <Sparkles className="w-4 h-4 text-blue-600" />
                  Quality Recommendation: {detail.recommendation.headline}
                </span>
                <span
                  className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider border ${
                    detail.recommendation.confidence_tier === "high"
                      ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                      : detail.recommendation.confidence_tier === "medium"
                      ? "bg-amber-50 text-amber-700 border-amber-200"
                      : "bg-slate-100 text-slate-700 border-slate-200"
                  }`}
                >
                  {detail.recommendation.confidence_tier} confidence
                </span>
              </div>
              <p className="text-xs text-slate-800 leading-relaxed font-medium">
                {detail.recommendation.reason}
              </p>
              {detail.recommendation.supporting_factors.length > 0 && (
                <div className="pt-2 border-t border-blue-200/60 flex flex-wrap gap-1.5">
                  {detail.recommendation.supporting_factors.map((factor, idx) => (
                    <span
                      key={idx}
                      className="inline-flex items-center gap-1 text-[11px] text-slate-700 bg-white/90 px-2.5 py-0.5 rounded-full border border-blue-100 shadow-2xs"
                    >
                      <span className="w-1 h-1 rounded-full bg-blue-500" />
                      {factor}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Section A: AI Claim vs. Current Finding */}
          <div className="space-y-3">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-600">
              AI Claim vs. Current Finding
            </h3>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {/* AI Original */}
              <div className={`p-4 rounded-lg border ${claimChanged ? "bg-amber-50/40 border-amber-200" : "bg-slate-50 border-slate-200"}`}>
                <span className="text-[11px] font-semibold uppercase tracking-wider text-amber-800 block mb-1.5">
                  Original AI-Generated Statement
                </span>
                <p className="text-xs text-slate-700 leading-relaxed whitespace-pre-wrap">
                  {detail.original_ai_claim}
                </p>
              </div>

              {/* Current claim */}
              <div className="p-4 rounded-lg bg-slate-50 border border-slate-200">
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-700">
                    Current Structured Claim
                    {claimChanged && (
                      <span className="ml-2 text-blue-700 font-normal normal-case">
                        (edited)
                      </span>
                    )}
                  </span>
                  {detail.evidence_completeness && (
                    <span className="text-[11px] text-slate-500 capitalize">
                      {detail.evidence_completeness}
                    </span>
                  )}
                </div>
                <p className="text-xs text-slate-900 leading-relaxed whitespace-pre-wrap">
                  {detail.current_claim}
                </p>
              </div>
            </div>

            {/* Confidence / Uncertainty */}
            {(detail.model_confidence !== null || detail.uncertainty_note) && (
              <div className="flex flex-wrap items-center gap-4 text-xs text-slate-600 px-1">
                {detail.model_confidence !== null && (
                  <span>
                    Model confidence:{" "}
                    <strong className="text-slate-900">
                      {Math.round(detail.model_confidence * 100)}%
                    </strong>
                  </span>
                )}
                {detail.uncertainty_note && (
                  <span className="text-amber-800">Uncertainty: {detail.uncertainty_note}</span>
                )}
              </div>
            )}
          </div>

          {/* Quality & Evidence Intelligence Suite */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-600 flex items-center gap-1.5">
                <Compass className="w-3.5 h-3.5 text-slate-500" />
                Evidence Intelligence &amp; Quality Analysis
              </h3>
              {detail.priority_reason && (
                <span className="text-[11px] text-slate-500 italic max-w-sm truncate" title={detail.priority_reason}>
                  Priority reason: {detail.priority_reason}
                </span>
              )}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
              {/* Card 1: Completeness */}
              <div className="p-3.5 rounded-lg border border-slate-200 bg-slate-50/70 space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-semibold text-slate-700 flex items-center gap-1">
                    <FileCheck2 className="w-3.5 h-3.5 text-blue-600" />
                    Completeness
                  </span>
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider border ${
                    detail.completeness_assessment?.level === "complete"
                      ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                      : detail.completeness_assessment?.level === "partial"
                      ? "bg-amber-50 text-amber-700 border-amber-200"
                      : "bg-rose-50 text-rose-700 border-rose-200"
                  }`}>
                    {detail.completeness_assessment?.level ?? detail.evidence_completeness ?? "Unknown"}
                  </span>
                </div>
                <div className="flex items-baseline justify-between text-xs">
                  <span className="text-[11px] text-slate-500">Score</span>
                  <strong className="text-slate-900 font-mono text-sm">
                    {detail.completeness_assessment ? `${Math.round(detail.completeness_assessment.score * 100)}%` : "N/A"}
                  </strong>
                </div>
                <p className="text-[11px] text-slate-600 leading-snug line-clamp-3" title={detail.completeness_assessment?.explanation}>
                  {detail.completeness_assessment?.explanation ?? "No completeness metrics available."}
                </p>
                {detail.completeness_assessment?.missing_elements && detail.completeness_assessment.missing_elements.length > 0 && (
                  <div className="pt-1.5 border-t border-slate-200 text-[10px] text-amber-800">
                    <span className="font-semibold block">Missing:</span>
                    <ul className="list-disc list-inside space-y-0.5 mt-0.5">
                      {detail.completeness_assessment.missing_elements.slice(0, 2).map((m, i) => (
                        <li key={i} className="truncate">{m}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>

              {/* Card 2: Source Reliability */}
              <div className="p-3.5 rounded-lg border border-slate-200 bg-slate-50/70 space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-semibold text-slate-700 flex items-center gap-1">
                    <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
                    Source Reliability
                  </span>
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider border ${
                    detail.reliability_assessment?.tier === "high"
                      ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                      : detail.reliability_assessment?.tier === "medium"
                      ? "bg-blue-50 text-blue-700 border-blue-200"
                      : "bg-amber-50 text-amber-700 border-amber-200"
                  }`}>
                    {detail.reliability_assessment?.tier ?? "Standard"}
                  </span>
                </div>
                <div className="flex items-baseline justify-between text-xs">
                  <span className="text-[11px] text-slate-500">Authority Weight</span>
                  <strong className="text-slate-900 font-mono text-sm">
                    {detail.reliability_assessment ? `${Math.round(detail.reliability_assessment.score * 100)}%` : "N/A"}
                  </strong>
                </div>
                <p className="text-[11px] text-slate-600 leading-snug line-clamp-3" title={detail.reliability_assessment?.explanation}>
                  {detail.reliability_assessment?.explanation ?? "Direct platform source."}
                </p>
                {detail.reliability_assessment?.factors && detail.reliability_assessment.factors.length > 0 && (
                  <div className="pt-1.5 border-t border-slate-200 text-[10px] text-slate-500">
                    <span className="truncate block font-mono">
                      {detail.reliability_assessment.factors[0]}
                    </span>
                  </div>
                )}
              </div>

              {/* Card 3: Freshness & Supersession */}
              <div className="p-3.5 rounded-lg border border-slate-200 bg-slate-50/70 space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-semibold text-slate-700 flex items-center gap-1">
                    <Clock className="w-3.5 h-3.5 text-indigo-600" />
                    Freshness
                  </span>
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider border ${
                    detail.freshness_assessment?.status === "fresh"
                      ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                      : detail.freshness_assessment?.status === "aging"
                      ? "bg-blue-50 text-blue-700 border-blue-200"
                      : detail.freshness_assessment?.status === "stale"
                      ? "bg-amber-50 text-amber-700 border-amber-200"
                      : "bg-rose-50 text-rose-700 border-rose-200"
                  }`}>
                    {detail.freshness_assessment?.status ?? "Current"}
                  </span>
                </div>
                <div className="flex items-baseline justify-between text-xs">
                  <span className="text-[11px] text-slate-500">Evidence Age</span>
                  <strong className="text-slate-900 font-mono text-sm">
                    {detail.freshness_assessment?.age_days !== null && detail.freshness_assessment?.age_days !== undefined
                      ? `${detail.freshness_assessment.age_days}d`
                      : "<1d"}
                  </strong>
                </div>
                <p className="text-[11px] text-slate-600 leading-snug line-clamp-3" title={detail.freshness_assessment?.explanation}>
                  {detail.freshness_assessment?.explanation ?? "Synchronized with active project documents."}
                </p>
                {detail.freshness_assessment?.superseded_by_record_title && (
                  <div className="pt-1.5 border-t border-rose-200 text-[10px] text-rose-800">
                    <span className="font-semibold block truncate">
                      Superseded by: {detail.freshness_assessment.superseded_by_record_title}
                    </span>
                  </div>
                )}
              </div>

              {/* Card 4: Independent Corroboration */}
              <div className="p-3.5 rounded-lg border border-slate-200 bg-slate-50/70 space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-semibold text-slate-700 flex items-center gap-1">
                    <Layers className="w-3.5 h-3.5 text-purple-600" />
                    Corroboration
                  </span>
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider border ${
                    detail.corroboration_assessment?.level === "strong_cross_source"
                      ? "bg-purple-50 text-purple-700 border-purple-200"
                      : detail.corroboration_assessment?.level === "moderate_multi_source"
                      ? "bg-blue-50 text-blue-700 border-blue-200"
                      : "bg-slate-100 text-slate-700 border-slate-200"
                  }`}>
                    {detail.corroboration_assessment?.level === "strong_cross_source"
                      ? "Cross-Source"
                      : detail.corroboration_assessment?.level === "moderate_multi_source"
                      ? "Multi-Doc"
                      : "Single Source"}
                  </span>
                </div>
                <div className="flex items-baseline justify-between text-xs">
                  <span className="text-[11px] text-slate-500">Independent Records</span>
                  <strong className="text-slate-900 font-mono text-sm">
                    {detail.corroboration_assessment?.independent_sources_count ?? detail.evidence_references.length}
                  </strong>
                </div>
                <p className="text-[11px] text-slate-600 leading-snug line-clamp-3" title={detail.corroboration_assessment?.explanation}>
                  {detail.corroboration_assessment?.explanation ?? "Assessing supporting documents."}
                </p>
                <div className="pt-1.5 border-t border-slate-200 text-[10px] text-slate-500 truncate">
                  Evaluates independent files (not multiple chunk excerpts)
                </div>
              </div>
            </div>
          </div>

          {/* Section B: Automated Verification Checks */}
          {detail.issues.length > 0 && (
            <div className="space-y-2.5">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-600">
                Automated Verification Checks ({detail.issues.length})
              </h3>
              <div className="space-y-2">
                {detail.issues.map((issue) => {
                  const origTs = issue.details?.original_timestamp as string | undefined;
                  const newerTs = issue.details?.newer_timestamp as string | undefined;
                  return (
                    <div
                      key={issue.id}
                      className="p-3.5 rounded-lg border border-amber-200 bg-amber-50/40 space-y-1"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-amber-900">
                          <AlertCircle className="w-3.5 h-3.5 text-amber-600" />
                          {CATEGORY_LABELS[issue.verification_category] ?? issue.verification_category}
                        </span>
                        <span className="text-[11px] uppercase font-medium px-2 py-0.5 rounded bg-white border border-amber-200 text-amber-800">
                          {issue.severity}
                        </span>
                      </div>
                      <p className="text-xs text-slate-700">{issue.description}</p>
                      {(origTs || newerTs) && (
                        <p className="text-[11px] text-slate-500">
                          Evidence timestamp: {formatTimestamp(origTs)} · Newer record:{" "}
                          {formatTimestamp(newerTs)}
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Section C: Supporting Evidence */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-600">
                Supporting Evidence ({supportingEvidence.length})
              </h3>
              {detail.restricted_evidence_count > 0 && (
                <span className="inline-flex items-center gap-1 text-xs text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded">
                  <Lock className="w-3 h-3" />
                  {detail.restricted_evidence_count} restricted
                </span>
              )}
            </div>

            {supportingEvidence.length === 0 ? (
              <div className="p-4 rounded-lg border border-dashed border-slate-300 bg-slate-50 text-xs text-slate-600">
                No accessible supporting evidence. Use &ldquo;Request Context&rdquo; or &ldquo;Mark Unresolved&rdquo; until evidence is available.
              </div>
            ) : (
              <div className="space-y-3">
                {supportingEvidence.map((ev) => (
                  <EvidenceCard
                    key={ev.id}
                    ev={ev}
                    onInspect={() => setDrawerEvidence(ev)}
                  />
                ))}
              </div>
            )}
          </div>

          {/* Section D: Opposing Evidence / Conflicts */}
          {(opposingEvidence.length > 0 || detail.conflicts.length > 0) && (
            <div className="space-y-3">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-rose-700 flex items-center gap-1.5">
                <GitCompare className="w-3.5 h-3.5" />
                Opposing Evidence &amp; Conflicts
              </h3>

              {opposingEvidence.map((ev) => (
                <EvidenceCard
                  key={ev.id}
                  ev={ev}
                  variant="opposing"
                  onInspect={() => setDrawerEvidence(ev)}
                />
              ))}

              {detail.conflicts.map((conf) => (
                <div
                  key={conf.id}
                  className="rounded-lg border border-rose-200 bg-rose-50/30 p-4 space-y-3"
                >
                  <p className="text-xs font-medium text-rose-900">{conf.explanation}</p>
                  {conf.temporal_comparison && (
                    <p className="text-[11px] text-slate-600">{conf.temporal_comparison}</p>
                  )}
                  {conf.restricted_by_acl && (
                    <p className="text-xs text-slate-600 inline-flex items-center gap-1.5">
                      <Lock className="w-3.5 h-3.5" />
                      One or more opposing source records are restricted by delegated source ACL.
                    </p>
                  )}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {[
                      { label: "Source A", side: conf.side_a },
                      { label: "Source B", side: conf.side_b },
                    ].map(({ label, side }) => (
                      <div
                        key={label}
                        className="p-3 rounded-md bg-white border border-rose-200/80 space-y-1.5"
                      >
                        <div className="flex items-center justify-between text-[11px] text-slate-500">
                          <span className="font-semibold text-slate-700">
                            {label} · {side ? side.source_provider.toUpperCase() : "Restricted"}
                          </span>
                          {side?.timestamp && <span>{formatTimestamp(side.timestamp)}</span>}
                        </div>
                        {side ? (
                          <>
                            <p className="text-xs font-medium text-slate-900">{side.original_title}</p>
                            <p className="text-xs text-slate-700">{side.claim_text}</p>
                            {side.author && (
                              <p className="text-[11px] text-slate-500">Author: {side.author}</p>
                            )}
                          </>
                        ) : (
                          <p className="text-xs text-slate-500 italic">
                            Hidden by source access policy.
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Section E: Provenance & Analysis */}
          <div className="p-4 rounded-lg bg-slate-50 border border-slate-200 space-y-2 text-xs">
            <h3 className="font-semibold uppercase tracking-wider text-slate-600 text-[11px]">
              Provenance &amp; Analysis
            </h3>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div>
                <span className="text-slate-500">Evidence</span>
                <p className="font-semibold text-slate-900 mt-0.5">
                  {detail.evidence_references.length} accessible
                  {detail.restricted_evidence_count > 0 &&
                    ` + ${detail.restricted_evidence_count} restricted`}
                </p>
              </div>
              <div>
                <span className="text-slate-500">Completeness</span>
                <p className="font-semibold text-slate-900 mt-0.5 capitalize">
                  {detail.evidence_completeness ?? "—"}
                </p>
              </div>
              <div>
                <span className="text-slate-500">AI Confidence</span>
                <p className="font-semibold text-slate-900 mt-0.5">
                  {detail.model_confidence !== null
                    ? `${Math.round(detail.model_confidence * 100)}%`
                    : "Not scored"}
                </p>
              </div>
              <div>
                <span className="text-slate-500">Last Assessed</span>
                <p className="font-semibold text-slate-900 mt-0.5">
                  {formatTimestamp(detail.last_assessed_at).split(",")[0]}
                </p>
              </div>
            </div>
            {detail.uncertainty_note && (
              <p className="text-amber-800 pt-1 border-t border-slate-200">
                {detail.uncertainty_note}
              </p>
            )}
          </div>

          {/* Context Requests */}
          {detail.context_requests.length > 0 && (
            <div className="space-y-3">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-600 flex items-center gap-1.5">
                <MessageSquarePlus className="w-3.5 h-3.5" />
                Clarification &amp; Context Requests ({detail.context_requests.length})
              </h3>
              <div className="space-y-2.5">
                {detail.context_requests.map((req) => (
                  <div
                    key={req.id}
                    className="p-3.5 rounded-lg border border-slate-200 bg-slate-50/70 space-y-2"
                  >
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-medium text-slate-800">
                        To: {req.requested_from_name ?? "Project Member"}
                      </span>
                      <span
                        className={`px-2 py-0.5 rounded-full text-[11px] font-medium capitalize ${
                          req.status === "responded"
                            ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                            : "bg-blue-50 text-blue-700 border border-blue-200"
                        }`}
                      >
                        {req.status}
                      </span>
                    </div>
                    <p className="text-xs text-slate-800">{req.question}</p>
                    {req.response_text ? (
                      <div className="p-2.5 rounded bg-white border border-emerald-200 text-xs text-slate-700">
                        <span className="font-semibold text-emerald-800 block mb-0.5">
                          Response ({formatTimestamp(req.responded_at)}):
                        </span>
                        {req.response_text}
                      </div>
                    ) : (
                      <div className="flex gap-2 pt-1">
                        <input
                          type="text"
                          value={replyDrafts[req.id] ?? ""}
                          onChange={(e) =>
                            setReplyDrafts((prev) => ({ ...prev, [req.id]: e.target.value }))
                          }
                          placeholder="Provide clarification response..."
                          className="flex-1 text-xs px-2.5 py-1.5 rounded border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                        />
                        <button
                          type="button"
                          disabled={
                            submittingReqId === req.id || !(replyDrafts[req.id] ?? "").trim()
                          }
                          onClick={async () => {
                            const text = (replyDrafts[req.id] ?? "").trim();
                            if (!text) return;
                            setSubmittingReqId(req.id);
                            try {
                              await onRespondContextRequest(req.id, text);
                              setReplyDrafts((prev) => ({ ...prev, [req.id]: "" }));
                            } finally {
                              setSubmittingReqId(null);
                            }
                          }}
                          className="px-3 py-1.5 rounded bg-blue-600 text-white text-xs font-medium hover:bg-blue-700 disabled:opacity-50"
                        >
                          {submittingReqId === req.id ? "Sending..." : "Respond"}
                        </button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Persistent Reviewer Decision Bar */}
        <ReviewerDecisionBar
          detail={detail}
          members={members}
          busy={busy}
          onApprove={onApprove}
          onReject={onReject}
          onEditFinding={onEditFinding}
          onRequestContext={onRequestContext}
          onMarkUnresolved={onMarkUnresolved}
          onAssignReviewer={onAssignReviewer}
        />
      </section>

      {/* Evidence Source Drawer (slide-in) */}
      <EvidenceSourceDrawer
        evidence={drawerEvidence}
        caseDetail={detail}
        onClose={() => setDrawerEvidence(null)}
      />
    </>
  );
}

// ─────────────────────────────────────────────
//  Evidence Card (shared between supporting / opposing)
// ─────────────────────────────────────────────

interface EvidenceCardProps {
  ev: EvidenceReferenceDetail;
  variant?: "supporting" | "opposing";
  onInspect: () => void;
}

function EvidenceCard({ ev, variant = "supporting", onInspect }: EvidenceCardProps) {
  const borderClass =
    variant === "opposing"
      ? "border-rose-200 bg-rose-50/20"
      : "border-slate-200 bg-white hover:border-slate-300";

  return (
    <article
      className={`p-4 rounded-lg border transition-colors space-y-2.5 ${borderClass}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="space-y-0.5">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="px-2 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-200 text-[11px] font-semibold uppercase">
              {ev.source_name}
            </span>
            <span className="text-[11px] text-slate-500 capitalize">
              {ev.relationship_to_finding.replace(/_/g, " ")}
            </span>
          </div>
          <h4 className="text-sm font-semibold text-slate-900 pt-0.5">{ev.original_title}</h4>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {ev.original_source_url && (
            <a
              href={ev.original_source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-xs font-medium text-blue-600 hover:text-blue-800 hover:underline"
            >
              <ExternalLink className="w-3 h-3" />
              Open source
            </a>
          )}
          <button
            type="button"
            onClick={onInspect}
            className="inline-flex items-center gap-1 text-xs font-medium text-slate-600 hover:text-slate-900 px-2 py-1 rounded border border-slate-200 hover:border-slate-400 transition-colors"
          >
            <Maximize2 className="w-3 h-3" />
            Inspect
          </button>
        </div>
      </div>

      {ev.excerpt && (
        <blockquote className="text-xs text-slate-700 bg-slate-50 border-l-2 border-slate-300 pl-3 py-2 rounded-r whitespace-pre-wrap leading-relaxed">
          {ev.excerpt}
        </blockquote>
      )}

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-slate-500">
        <span className="inline-flex items-center gap-1">
          <UserIcon className="w-3 h-3" />
          {ev.author ?? "Unknown"}
        </span>
        <span className="inline-flex items-center gap-1">
          <Clock className="w-3 h-3" />
          {formatTimestamp(ev.timestamp)}
        </span>
        {ev.location_label && <span>Location: {ev.location_label}</span>}
        {ev.acl_scope !== "public" && (
          <span className="inline-flex items-center gap-1 text-amber-700">
            <Lock className="w-3 h-3" />
            {ev.acl_scope}
          </span>
        )}
      </div>
    </article>
  );
}
