"use client";

import React, { useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  HelpCircle,
  RefreshCw,
  User,
  ShieldCheck,
  ShieldAlert,
  FileText,
  ExternalLink,
  ChevronRight,
  GitCompare,
  Lock,
  MessageSquare,
  Sparkles,
  ArrowRight,
  Calendar,
  X,
  History,
  Check,
  Users,
  Send,
} from "lucide-react";
import {
  ConflictDetailResponse,
  ResolveConflictPayload,
} from "../../lib/conflictsApi";

interface ConflictInvestigationWorkspaceProps {
  conflict: ConflictDetailResponse;
  onAssignReviewer: (reviewerId: string | null, notes?: string) => Promise<void>;
  onStartInvestigation: (notes?: string) => Promise<void>;
  onRequestContext: (queries: string[], notes?: string) => Promise<void>;
  onAddNote: (notes: string) => Promise<void>;
  onResolve: (payload: ResolveConflictPayload) => Promise<void>;
  onReopen: (reason: string) => Promise<void>;
  teamMembers?: Array<{ user_id: string; full_name: string; email: string }>;
}

export function ConflictInvestigationWorkspace({
  conflict,
  onAssignReviewer,
  onStartInvestigation,
  onRequestContext,
  onAddNote,
  onResolve,
  onReopen,
  teamMembers = [],
}: ConflictInvestigationWorkspaceProps) {
  // Modal states
  const [showResolveModal, setShowResolveModal] = useState(false);
  const [showReopenModal, setShowReopenModal] = useState(false);
  const [showContextModal, setShowContextModal] = useState(false);
  const [showNoteModal, setShowNoteModal] = useState(false);
  const [showAssignModal, setShowAssignModal] = useState(false);

  // Form states
  const [actionLoading, setActionLoading] = useState(false);
  const [resolveStrategy, setResolveStrategy] = useState<string>("side_a_authoritative");
  const [resolveNotes, setResolveNotes] = useState("");
  const [authoritativeClaim, setAuthoritativeClaim] = useState("");
  const [syncFinding, setSyncFinding] = useState(true);

  const [reopenReason, setReopenReason] = useState("");
  const [contextQueryInput, setContextQueryInput] = useState("");
  const [contextQueries, setContextQueries] = useState<string[]>([]);
  const [contextNotes, setContextNotes] = useState("");
  const [newNote, setNewNote] = useState("");
  const [selectedReviewerId, setSelectedReviewerId] = useState<string>("");

  const isResolved = ["resolved", "reconciled", "superseded", "dismissed"].includes(
    conflict.resolution_state.toLowerCase()
  );

  // Temporal analysis helper
  const getTemporalAnalysis = () => {
    switch (conflict.temporal_comparison) {
      case "b_supersedes_a":
        return {
          title: "Side B is newer than Side A (Potential superseding update)",
          desc: "Source timestamps indicate Side B occurred after Side A. Side B may represent the current operational truth.",
          badge: "bg-blue-100 text-blue-800 border-blue-200",
        };
      case "a_supersedes_b":
        return {
          title: "Side A is newer than Side B (Side A supersedes Side B)",
          desc: "Source timestamps indicate Side A occurred after Side B. Side A represents the more recent record.",
          badge: "bg-blue-100 text-blue-800 border-blue-200",
        };
      default:
        return {
          title: "Concurrent / Ambiguous Timeline",
          desc: "Both sources were recorded in overlapping timeframe or lack definitive timestamps. Semantic investigation required.",
          badge: "bg-slate-100 text-slate-700 border-slate-200",
        };
    }
  };

  const temporal = getTemporalAnalysis();

  // Handlers
  const handleOpenResolve = () => {
    setResolveStrategy("side_a_authoritative");
    setAuthoritativeClaim(conflict.side_a.claim_text);
    setResolveNotes("");
    setSyncFinding(true);
    setShowResolveModal(true);
  };

  const handleSubmitResolve = async () => {
    if (!resolveNotes.trim()) return;
    setActionLoading(true);
    try {
      await onResolve({
        resolution_strategy: resolveStrategy,
        resolution_notes: resolveNotes.trim(),
        authoritative_claim_text: authoritativeClaim.trim() || undefined,
        sync_finding: syncFinding,
      });
      setShowResolveModal(false);
    } finally {
      setActionLoading(false);
    }
  };

  const handleSubmitReopen = async () => {
    if (!reopenReason.trim()) return;
    setActionLoading(true);
    try {
      await onReopen(reopenReason.trim());
      setShowReopenModal(false);
      setReopenReason("");
    } finally {
      setActionLoading(false);
    }
  };

  const handleAddContextQuery = () => {
    if (contextQueryInput.trim()) {
      setContextQueries([...contextQueries, contextQueryInput.trim()]);
      setContextQueryInput("");
    }
  };

  const handleSubmitContext = async () => {
    if (contextQueries.length === 0 && !contextQueryInput.trim()) return;
    setActionLoading(true);
    const finalQueries = contextQueryInput.trim()
      ? [...contextQueries, contextQueryInput.trim()]
      : contextQueries;
    try {
      await onRequestContext(finalQueries, contextNotes.trim() || undefined);
      setShowContextModal(false);
      setContextQueries([]);
      setContextNotes("");
    } finally {
      setActionLoading(false);
    }
  };

  const handleSubmitNote = async () => {
    if (!newNote.trim()) return;
    setActionLoading(true);
    try {
      await onAddNote(newNote.trim());
      setShowNoteModal(false);
      setNewNote("");
    } finally {
      setActionLoading(false);
    }
  };

  const handleAssignReviewerSubmit = async () => {
    setActionLoading(true);
    try {
      await onAssignReviewer(selectedReviewerId || null);
      setShowAssignModal(false);
    } finally {
      setActionLoading(false);
    }
  };

  return (
    <div className="flex-1 overflow-y-auto bg-slate-50 flex flex-col justify-between">
      <div className="p-6 md:p-8 space-y-6 max-w-6xl mx-auto w-full">
        {/* Header Ribbon */}
        <div className="bg-white rounded-2xl border border-slate-200/90 p-6 shadow-xs">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 mb-2">
                <span className="px-2.5 py-0.5 rounded-full text-xs font-bold uppercase tracking-wider bg-rose-100 text-rose-800 border border-rose-200">
                  {conflict.conflict_type.replace("_", " ")}
                </span>
                <span className="px-2 py-0.5 rounded text-xs font-bold uppercase tracking-wider bg-slate-100 text-slate-700">
                  Priority: {conflict.priority}
                </span>
                <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-indigo-50 text-indigo-700 border border-indigo-200">
                  Status: {conflict.resolution_state.replace("_", " ").toUpperCase()}
                </span>
              </div>
              <h2 className="text-xl font-bold text-slate-900 tracking-tight">
                {conflict.side_a.title} <span className="text-slate-400 font-normal">vs</span>{" "}
                {conflict.side_b.title}
              </h2>
            </div>

            {/* Assigned Investigator Card */}
            <div className="flex items-center gap-3 bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5">
              <div className="w-8 h-8 rounded-full bg-slate-200 flex items-center justify-center text-slate-700 font-bold text-xs">
                {conflict.assigned_reviewer_name ? conflict.assigned_reviewer_name.charAt(0) : "?"}
              </div>
              <div>
                <span className="block text-[10px] font-bold uppercase tracking-wider text-slate-400">
                  Investigator
                </span>
                <span className="text-xs font-bold text-slate-800">
                  {conflict.assigned_reviewer_name || "Unassigned"}
                </span>
              </div>
              <button
                onClick={() => {
                  setSelectedReviewerId(conflict.assigned_reviewer_id || "");
                  setShowAssignModal(true);
                }}
                className="text-[11px] font-semibold text-blue-600 hover:text-blue-800 ml-2"
              >
                Change
              </button>
            </div>
          </div>
        </div>

        {/* Side-by-Side Comparative Evidence Section */}
        <div>
          <div className="flex items-center justify-between mb-3 px-1">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-600 flex items-center gap-2">
              <GitCompare className="w-4 h-4 text-slate-500" />
              Side-by-Side Evidence Comparison
            </h3>
            <span className={`px-2.5 py-1 rounded-full text-[11px] font-semibold border ${temporal.badge}`}>
              {temporal.title}
            </span>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* SIDE A CARD */}
            <div className="bg-white rounded-2xl border-2 border-blue-200 p-5 shadow-xs flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between pb-3 border-b border-slate-100 mb-3">
                  <div className="flex items-center gap-2">
                    <span className="w-6 h-6 rounded-full bg-blue-600 text-white flex items-center justify-center text-xs font-bold">
                      A
                    </span>
                    <div>
                      <span className="text-xs font-bold text-slate-900 line-clamp-1">
                        {conflict.side_a.title}
                      </span>
                      <span className="text-[10px] text-slate-500 uppercase tracking-wider">
                        Source: {conflict.side_a.provider || "Evidence Item"}
                      </span>
                    </div>
                  </div>

                  {conflict.side_a.source_url && (
                    <a
                      href={conflict.side_a.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-slate-400 hover:text-blue-600 inline-flex items-center gap-1 text-xs"
                    >
                      <ExternalLink className="w-3.5 h-3.5" />
                    </a>
                  )}
                </div>

                {/* Metadata Pill Row */}
                <div className="flex flex-wrap items-center gap-2 mb-3 text-[11px] text-slate-600">
                  {conflict.side_a.author && (
                    <span className="inline-flex items-center gap-1 bg-slate-100 px-2 py-0.5 rounded text-slate-700">
                      <User className="w-3 h-3 text-slate-500" />
                      {conflict.side_a.author}
                    </span>
                  )}
                  {conflict.side_a.source_timestamp && (
                    <span className="inline-flex items-center gap-1 bg-slate-100 px-2 py-0.5 rounded text-slate-700">
                      <Calendar className="w-3 h-3 text-slate-500" />
                      {new Date(conflict.side_a.source_timestamp).toLocaleDateString()}
                    </span>
                  )}
                  <span
                    className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold ${
                      conflict.side_a.is_accessible
                        ? "bg-emerald-50 text-emerald-700"
                        : "bg-red-50 text-red-700"
                    }`}
                  >
                    {conflict.side_a.is_accessible ? (
                      <>
                        <ShieldCheck className="w-3 h-3" /> ACL Verified
                      </>
                    ) : (
                      <>
                        <Lock className="w-3 h-3" /> Access Restricted
                      </>
                    )}
                  </span>
                </div>

                {/* Claim Box */}
                <div className="bg-blue-50/40 border border-blue-200/70 rounded-xl p-4 text-xs text-slate-900 leading-relaxed font-mono whitespace-pre-wrap">
                  {conflict.side_a.claim_text}
                </div>
              </div>

              {conflict.side_a.redaction_reason && (
                <div className="mt-3 p-2 bg-rose-50 border border-rose-200 rounded text-[11px] text-rose-800 flex items-center gap-1.5">
                  <ShieldAlert className="w-3.5 h-3.5 text-rose-600 shrink-0" />
                  <span>{conflict.side_a.redaction_reason}</span>
                </div>
              )}
            </div>

            {/* SIDE B CARD */}
            <div className="bg-white rounded-2xl border-2 border-rose-200 p-5 shadow-xs flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between pb-3 border-b border-slate-100 mb-3">
                  <div className="flex items-center gap-2">
                    <span className="w-6 h-6 rounded-full bg-rose-600 text-white flex items-center justify-center text-xs font-bold">
                      B
                    </span>
                    <div>
                      <span className="text-xs font-bold text-slate-900 line-clamp-1">
                        {conflict.side_b.title}
                      </span>
                      <span className="text-[10px] text-slate-500 uppercase tracking-wider">
                        Source: {conflict.side_b.provider || "Opposing Claim"}
                      </span>
                    </div>
                  </div>

                  {conflict.side_b.source_url && (
                    <a
                      href={conflict.side_b.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-slate-400 hover:text-rose-600 inline-flex items-center gap-1 text-xs"
                    >
                      <ExternalLink className="w-3.5 h-3.5" />
                    </a>
                  )}
                </div>

                {/* Metadata Pill Row */}
                <div className="flex flex-wrap items-center gap-2 mb-3 text-[11px] text-slate-600">
                  {conflict.side_b.author && (
                    <span className="inline-flex items-center gap-1 bg-slate-100 px-2 py-0.5 rounded text-slate-700">
                      <User className="w-3 h-3 text-slate-500" />
                      {conflict.side_b.author}
                    </span>
                  )}
                  {conflict.side_b.source_timestamp && (
                    <span className="inline-flex items-center gap-1 bg-slate-100 px-2 py-0.5 rounded text-slate-700">
                      <Calendar className="w-3 h-3 text-slate-500" />
                      {new Date(conflict.side_b.source_timestamp).toLocaleDateString()}
                    </span>
                  )}
                  <span
                    className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold ${
                      conflict.side_b.is_accessible
                        ? "bg-emerald-50 text-emerald-700"
                        : "bg-red-50 text-red-700"
                    }`}
                  >
                    {conflict.side_b.is_accessible ? (
                      <>
                        <ShieldCheck className="w-3 h-3" /> ACL Verified
                      </>
                    ) : (
                      <>
                        <Lock className="w-3 h-3" /> Access Restricted
                      </>
                    )}
                  </span>
                </div>

                {/* Claim Box */}
                <div className="bg-rose-50/40 border border-rose-200/70 rounded-xl p-4 text-xs text-slate-900 leading-relaxed font-mono whitespace-pre-wrap">
                  {conflict.side_b.claim_text}
                </div>
              </div>

              {conflict.side_b.redaction_reason && (
                <div className="mt-3 p-2 bg-rose-50 border border-rose-200 rounded text-[11px] text-rose-800 flex items-center gap-1.5">
                  <ShieldAlert className="w-3.5 h-3.5 text-rose-600 shrink-0" />
                  <span>{conflict.side_b.redaction_reason}</span>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Explainable Detection Intelligence Card */}
        <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-xs">
          <div className="flex items-center gap-2 mb-2 text-xs font-bold uppercase tracking-wider text-slate-700">
            <Sparkles className="w-4 h-4 text-amber-500" />
            Why the System Detected This Contradiction
          </div>
          <p className="text-xs text-slate-700 leading-relaxed bg-amber-50/50 border border-amber-200/60 rounded-xl p-3.5">
            {conflict.explanation}
          </p>
        </div>

        {/* Related Knowledge & Verification Center Finding */}
        <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-xs flex flex-wrap items-center justify-between gap-4">
          <div>
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block mb-1">
              Associated Verification Case
            </span>
            <div className="flex items-center gap-2">
              <FileText className="w-4 h-4 text-blue-600" />
              <span className="text-sm font-bold text-slate-900">
                {conflict.related_finding_title || conflict.side_a.title}
              </span>
              {conflict.finding_domain && (
                <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-100 text-slate-600 uppercase">
                  {conflict.finding_domain.replace("_", " ")}
                </span>
              )}
            </div>
          </div>

          <Link
            href={`/verification?case_id=${conflict.case_id}`}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-800 transition-colors"
          >
            <span>Inspect in Verification Center</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>

        {/* Investigation Notes & Audit History Section */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Notes Log */}
          <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-xs flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between mb-3 pb-2 border-b border-slate-100">
                <span className="text-xs font-bold uppercase tracking-wider text-slate-700 flex items-center gap-1.5">
                  <MessageSquare className="w-3.5 h-3.5 text-slate-500" />
                  Investigator Notes & Queries
                </span>
                <button
                  onClick={() => setShowNoteModal(true)}
                  className="text-[11px] font-semibold text-blue-600 hover:text-blue-800"
                >
                  + Add Note
                </button>
              </div>

              {conflict.investigation_notes ? (
                <div className="text-xs text-slate-700 whitespace-pre-wrap font-sans leading-relaxed bg-slate-50 p-3.5 rounded-xl border border-slate-200/70 max-h-56 overflow-y-auto">
                  {conflict.investigation_notes}
                </div>
              ) : (
                <div className="text-xs text-slate-400 italic py-6 text-center">
                  Zero internal investigator notes recorded yet.
                </div>
              )}
            </div>
          </div>

          {/* Audit Timeline */}
          <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-xs">
            <div className="flex items-center justify-between mb-3 pb-2 border-b border-slate-100">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-700 flex items-center gap-1.5">
                <History className="w-3.5 h-3.5 text-slate-500" />
                Immutable Audit Trail
              </span>
              <span className="text-[10px] text-slate-400">PostgreSQL Immutable Log</span>
            </div>

            {conflict.audit_history.length > 0 ? (
              <div className="space-y-3 max-h-56 overflow-y-auto pr-1">
                {conflict.audit_history.map((event) => (
                  <div key={event.id} className="text-xs flex items-start gap-2.5">
                    <div className="w-2 h-2 rounded-full bg-blue-500 mt-1.5 shrink-0" />
                    <div>
                      <div className="font-semibold text-slate-800">
                        {event.action} <span className="text-slate-400 font-normal">by</span>{" "}
                        <span className="text-slate-700">{event.actor_name || "System"}</span>
                      </div>
                      {event.notes && <div className="text-slate-500 text-[11px] mt-0.5">{event.notes}</div>}
                      <span className="text-[10px] text-slate-400 block mt-0.5">
                        {new Date(event.created_at).toLocaleString()}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-xs text-slate-400 italic py-6 text-center">
                Initial detection recorded at {new Date(conflict.created_at).toLocaleString()}.
              </div>
            )}
          </div>
        </div>

        {/* Resolved Banner (if already resolved) */}
        {isResolved && (
          <div className="bg-emerald-50 border border-emerald-300 rounded-2xl p-5 shadow-xs flex items-start gap-3.5">
            <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />
            <div className="space-y-1">
              <h4 className="text-sm font-bold text-emerald-950">
                Conflict Formally Resolved: {conflict.resolution_strategy?.replace("_", " ").toUpperCase()}
              </h4>
              <p className="text-xs text-emerald-800">
                <strong>Reviewer Rationale:</strong> {conflict.resolution_notes}
              </p>
              {conflict.authoritative_claim_text && (
                <div className="bg-white/80 border border-emerald-200 rounded-lg p-2.5 text-xs font-mono text-emerald-950 mt-2">
                  <span className="font-bold block text-[10px] uppercase text-emerald-700 mb-1">
                    Canonical Authoritative Statement
                  </span>
                  {conflict.authoritative_claim_text}
                </div>
              )}
              <span className="text-[10px] text-emerald-600 block pt-1">
                Resolved by {conflict.resolved_by_user_name || "Authorised Reviewer"} on{" "}
                {conflict.resolved_at ? new Date(conflict.resolved_at).toLocaleString() : "Date N/A"}
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Persistent Bottom Reviewer Actions Bar */}
      <div className="bg-white border-t border-slate-200 px-6 py-4 sticky bottom-0 z-10 shadow-lg">
        <div className="max-w-6xl mx-auto flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold text-slate-600 uppercase tracking-wider">
              Investigation Actions:
            </span>
            <button
              onClick={() => onStartInvestigation("Reviewer initiated investigation")}
              disabled={isResolved || conflict.resolution_state === "under_investigation"}
              className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-100 hover:bg-slate-200 text-slate-800 transition-colors disabled:opacity-40"
            >
              Start Investigation
            </button>
            <button
              onClick={() => setShowContextModal(true)}
              disabled={isResolved}
              className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-100 hover:bg-slate-200 text-slate-800 transition-colors disabled:opacity-40"
            >
              Request Context
            </button>
            <button
              onClick={() => setShowNoteModal(true)}
              className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-100 hover:bg-slate-200 text-slate-800 transition-colors"
            >
              Add Note
            </button>
          </div>

          <div className="flex items-center gap-2">
            {isResolved ? (
              <button
                onClick={() => setShowReopenModal(true)}
                className="px-4 py-2 rounded-xl text-xs font-bold bg-amber-600 hover:bg-amber-700 text-white transition-colors shadow-xs"
              >
                Reopen Conflict
              </button>
            ) : (
              <button
                onClick={handleOpenResolve}
                className="inline-flex items-center gap-1.5 px-5 py-2.5 rounded-xl text-xs font-extrabold bg-slate-900 hover:bg-slate-800 text-white transition-all shadow-md hover:shadow-lg"
              >
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                Resolve Conflict
              </button>
            )}
          </div>
        </div>
      </div>

      {/* ==================================================================== */}
      {/* MODALS */}
      {/* ==================================================================== */}

      {/* 1. Resolve Conflict Modal */}
      {showResolveModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-xs p-4">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl w-full max-w-2xl overflow-hidden animate-in fade-in zoom-in-95">
            <div className="p-5 border-b border-slate-200 flex items-center justify-between bg-slate-50">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-5 h-5 text-emerald-600" />
                <h3 className="text-base font-bold text-slate-900">Formally Resolve Contradiction</h3>
              </div>
              <button onClick={() => setShowResolveModal(false)} className="text-slate-400 hover:text-slate-600">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-6 space-y-4 max-h-[75vh] overflow-y-auto">
              <div>
                <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-2">
                  Select Resolution Strategy
                </label>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
                  <div
                    onClick={() => {
                      setResolveStrategy("side_a_authoritative");
                      setAuthoritativeClaim(conflict.side_a.claim_text);
                    }}
                    className={`p-3 rounded-xl border cursor-pointer text-xs transition-all ${
                      resolveStrategy === "side_a_authoritative"
                        ? "border-blue-600 bg-blue-50/70 ring-1 ring-blue-600"
                        : "border-slate-200 hover:bg-slate-50"
                    }`}
                  >
                    <span className="font-bold text-blue-900 block mb-1">Side A is Authoritative</span>
                    <span className="text-[11px] text-slate-600">
                      Accept Claim A ({conflict.side_a.provider}) as canonical truth; supersede Claim B.
                    </span>
                  </div>

                  <div
                    onClick={() => {
                      setResolveStrategy("side_b_authoritative");
                      setAuthoritativeClaim(conflict.side_b.claim_text);
                    }}
                    className={`p-3 rounded-xl border cursor-pointer text-xs transition-all ${
                      resolveStrategy === "side_b_authoritative"
                        ? "border-rose-600 bg-rose-50/70 ring-1 ring-rose-600"
                        : "border-slate-200 hover:bg-slate-50"
                    }`}
                  >
                    <span className="font-bold text-rose-900 block mb-1">Side B is Authoritative</span>
                    <span className="text-[11px] text-slate-600">
                      Accept Claim B ({conflict.side_b.provider}) as canonical truth; supersede Claim A.
                    </span>
                  </div>

                  <div
                    onClick={() => {
                      setResolveStrategy("reconciled");
                      setAuthoritativeClaim(`${conflict.side_a.claim_text}\n\nCoexists with:\n${conflict.side_b.claim_text}`);
                    }}
                    className={`p-3 rounded-xl border cursor-pointer text-xs transition-all ${
                      resolveStrategy === "reconciled"
                        ? "border-purple-600 bg-purple-50/70 ring-1 ring-purple-600"
                        : "border-slate-200 hover:bg-slate-50"
                    }`}
                  >
                    <span className="font-bold text-purple-900 block mb-1">Reconcile / Coexist</span>
                    <span className="text-[11px] text-slate-600">
                      Synthesize both statements into a combined harmonious canonical record.
                    </span>
                  </div>

                  <div
                    onClick={() => {
                      setResolveStrategy("dismissed_false_positive");
                      setAuthoritativeClaim(conflict.side_a.claim_text);
                    }}
                    className={`p-3 rounded-xl border cursor-pointer text-xs transition-all ${
                      resolveStrategy === "dismissed_false_positive"
                        ? "border-slate-700 bg-slate-100 ring-1 ring-slate-700"
                        : "border-slate-200 hover:bg-slate-50"
                    }`}
                  >
                    <span className="font-bold text-slate-900 block mb-1">Dismiss as False Positive</span>
                    <span className="text-[11px] text-slate-600">
                      Determine that claims are compatible or not mutually exclusive.
                    </span>
                  </div>
                </div>
              </div>

              <div>
                <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
                  Canonical Authoritative Statement
                </label>
                <textarea
                  rows={3}
                  value={authoritativeClaim}
                  onChange={(e) => setAuthoritativeClaim(e.target.value)}
                  className="w-full text-xs font-mono p-3 bg-slate-50 border border-slate-200 rounded-xl focus:bg-white focus:outline-none focus:ring-1 focus:ring-blue-500"
                  placeholder="Authoritative text that will become the accepted ground truth..."
                />
              </div>

              <div>
                <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
                  Reviewer Rationale & Audit Justification <span className="text-red-500">*</span>
                </label>
                <textarea
                  rows={3}
                  value={resolveNotes}
                  onChange={(e) => setResolveNotes(e.target.value)}
                  className="w-full text-xs p-3 bg-slate-50 border border-slate-200 rounded-xl focus:bg-white focus:outline-none focus:ring-1 focus:ring-blue-500"
                  placeholder="Provide explicit reasons for this decision for the immutable audit trail..."
                />
              </div>

              <div className="flex items-center gap-2 pt-1">
                <input
                  type="checkbox"
                  id="syncFinding"
                  checked={syncFinding}
                  onChange={(e) => setSyncFinding(e.target.checked)}
                  className="rounded text-blue-600"
                />
                <label htmlFor="syncFinding" className="text-xs font-medium text-slate-700">
                  Update associated Verification Center finding with this authoritative statement and clear conflicted state.
                </label>
              </div>
            </div>

            <div className="p-4 bg-slate-50 border-t border-slate-200 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setShowResolveModal(false)}
                className="px-4 py-2 text-xs font-semibold text-slate-600 hover:text-slate-800"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSubmitResolve}
                disabled={actionLoading || !resolveNotes.trim()}
                className="px-5 py-2 text-xs font-bold rounded-xl bg-slate-900 hover:bg-slate-800 text-white disabled:opacity-50 transition-colors shadow-xs"
              >
                {actionLoading ? "Submitting..." : "Confirm & Resolve"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 2. Reopen Modal */}
      {showReopenModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-xs p-4">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl w-full max-w-md overflow-hidden animate-in fade-in">
            <div className="p-5 border-b border-slate-200 flex items-center justify-between bg-amber-50">
              <div className="flex items-center gap-2">
                <RefreshCw className="w-5 h-5 text-amber-600" />
                <h3 className="text-base font-bold text-slate-900">Reopen Contradiction</h3>
              </div>
              <button onClick={() => setShowReopenModal(false)} className="text-slate-400 hover:text-slate-600">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-6 space-y-3">
              <p className="text-xs text-slate-600">
                Reopening this contradiction will flag the associated project finding as conflicted and return it to the active investigation queue.
              </p>
              <div>
                <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
                  Reason for Reopening <span className="text-red-500">*</span>
                </label>
                <textarea
                  rows={3}
                  value={reopenReason}
                  onChange={(e) => setReopenReason(e.target.value)}
                  placeholder="Explain why this previously resolved conflict is being reopened..."
                  className="w-full text-xs p-3 bg-slate-50 border border-slate-200 rounded-xl focus:bg-white focus:outline-none focus:ring-1 focus:ring-amber-500"
                />
              </div>
            </div>

            <div className="p-4 bg-slate-50 border-t border-slate-200 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setShowReopenModal(false)}
                className="px-4 py-2 text-xs font-semibold text-slate-600"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSubmitReopen}
                disabled={actionLoading || !reopenReason.trim()}
                className="px-5 py-2 text-xs font-bold rounded-xl bg-amber-600 hover:bg-amber-700 text-white disabled:opacity-50 transition-colors shadow-xs"
              >
                {actionLoading ? "Reopening..." : "Confirm Reopen"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 3. Request Context Modal */}
      {showContextModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-xs p-4">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl w-full max-w-lg overflow-hidden animate-in fade-in">
            <div className="p-5 border-b border-slate-200 flex items-center justify-between bg-slate-50">
              <div className="flex items-center gap-2">
                <HelpCircle className="w-5 h-5 text-amber-600" />
                <h3 className="text-base font-bold text-slate-900">Request Context or Clarification</h3>
              </div>
              <button onClick={() => setShowContextModal(false)} className="text-slate-400 hover:text-slate-600">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-6 space-y-4">
              <div>
                <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
                  Information Queries (Questions for Project Members)
                </label>
                <div className="flex gap-2 mb-2">
                  <input
                    type="text"
                    value={contextQueryInput}
                    onChange={(e) => setContextQueryInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        handleAddContextQuery();
                      }
                    }}
                    placeholder="e.g. Which API version is active in production?"
                    className="flex-1 text-xs p-2.5 bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-blue-500"
                  />
                  <button
                    type="button"
                    onClick={handleAddContextQuery}
                    className="px-3 py-2 text-xs font-semibold bg-slate-100 hover:bg-slate-200 rounded-lg text-slate-700"
                  >
                    Add
                  </button>
                </div>

                {contextQueries.length > 0 && (
                  <ul className="space-y-1 bg-slate-50 p-2.5 rounded-lg border border-slate-200/80">
                    {contextQueries.map((q, idx) => (
                      <li key={idx} className="text-xs text-slate-700 flex items-center justify-between">
                        <span>• {q}</span>
                        <button
                          type="button"
                          onClick={() => setContextQueries(contextQueries.filter((_, i) => i !== idx))}
                          className="text-slate-400 hover:text-red-600"
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <div>
                <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
                  Investigator Instructions
                </label>
                <textarea
                  rows={2}
                  value={contextNotes}
                  onChange={(e) => setContextNotes(e.target.value)}
                  placeholder="Optional guidance on who should answer or what documentation to check..."
                  className="w-full text-xs p-3 bg-slate-50 border border-slate-200 rounded-xl focus:bg-white focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
              </div>
            </div>

            <div className="p-4 bg-slate-50 border-t border-slate-200 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setShowContextModal(false)}
                className="px-4 py-2 text-xs font-semibold text-slate-600"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSubmitContext}
                disabled={actionLoading || (contextQueries.length === 0 && !contextQueryInput.trim())}
                className="px-5 py-2 text-xs font-bold rounded-xl bg-slate-900 hover:bg-slate-800 text-white disabled:opacity-50 transition-colors shadow-xs"
              >
                {actionLoading ? "Requesting..." : "Submit Request"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 4. Add Note Modal */}
      {showNoteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-xs p-4">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl w-full max-w-md overflow-hidden animate-in fade-in">
            <div className="p-5 border-b border-slate-200 flex items-center justify-between bg-slate-50">
              <div className="flex items-center gap-2">
                <MessageSquare className="w-5 h-5 text-blue-600" />
                <h3 className="text-base font-bold text-slate-900">Add Investigator Note</h3>
              </div>
              <button onClick={() => setShowNoteModal(false)} className="text-slate-400 hover:text-slate-600">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-6">
              <textarea
                rows={4}
                value={newNote}
                onChange={(e) => setNewNote(e.target.value)}
                placeholder="Record discovery findings, team interview notes, or source verification details..."
                className="w-full text-xs p-3 bg-slate-50 border border-slate-200 rounded-xl focus:bg-white focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>

            <div className="p-4 bg-slate-50 border-t border-slate-200 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setShowNoteModal(false)}
                className="px-4 py-2 text-xs font-semibold text-slate-600"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSubmitNote}
                disabled={actionLoading || !newNote.trim()}
                className="px-5 py-2 text-xs font-bold rounded-xl bg-slate-900 hover:bg-slate-800 text-white disabled:opacity-50 transition-colors shadow-xs"
              >
                {actionLoading ? "Saving..." : "Save Note"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 5. Assign Reviewer Modal */}
      {showAssignModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-xs p-4">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl w-full max-w-sm overflow-hidden animate-in fade-in">
            <div className="p-5 border-b border-slate-200 flex items-center justify-between bg-slate-50">
              <div className="flex items-center gap-2">
                <Users className="w-5 h-5 text-blue-600" />
                <h3 className="text-base font-bold text-slate-900">Assign Investigator</h3>
              </div>
              <button onClick={() => setShowAssignModal(false)} className="text-slate-400 hover:text-slate-600">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-6 space-y-3">
              <label className="block text-xs font-bold uppercase tracking-wider text-slate-700">
                Select Project Member
              </label>
              <select
                value={selectedReviewerId}
                onChange={(e) => setSelectedReviewerId(e.target.value)}
                className="w-full text-xs p-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-1 focus:ring-blue-500"
              >
                <option value="">Unassigned</option>
                {teamMembers.map((m) => (
                  <option key={m.user_id} value={m.user_id}>
                    {m.full_name} ({m.email})
                  </option>
                ))}
              </select>
            </div>

            <div className="p-4 bg-slate-50 border-t border-slate-200 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setShowAssignModal(false)}
                className="px-4 py-2 text-xs font-semibold text-slate-600"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleAssignReviewerSubmit}
                disabled={actionLoading}
                className="px-5 py-2 text-xs font-bold rounded-xl bg-slate-900 hover:bg-slate-800 text-white transition-colors shadow-xs"
              >
                {actionLoading ? "Updating..." : "Save Assignment"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
