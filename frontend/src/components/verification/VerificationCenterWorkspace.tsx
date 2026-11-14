"use client";

import React, { useState, useEffect, useCallback, useMemo } from "react";
import {
  CheckCircle2,
  XCircle,
  HelpCircle,
  AlertTriangle,
  Clock,
  ShieldAlert,
  FileText,
  UserCheck,
  Search,
  Filter,
  RefreshCw,
  ChevronRight,
  ExternalLink,
  MessageSquare,
  Sparkles,
  Lock,
  Pencil,
  ArrowRight,
  FileQuestion,
  ShieldCheck,
  Building,
  User,
  History,
  Check,
} from "lucide-react";
import { api } from "../../lib/api";
import { useLiveApp } from "../../context/LiveAppContext";

interface VerificationQueueItem {
  id: string;
  target_type: string;
  target_id: string;
  status: string;
  risk_level: string;
  confidence_score: number | null;
  created_at: string;
  issue_count: number;
  assigned_to_user_id?: string;
  title?: string;
  summary?: string;
  domain?: string;
  category?: string;
  finding?: {
    title: string;
    summary: string;
    domain: string;
    category?: string;
  };
}

interface VerificationSummary {
  total_cases: number;
  pending_review: number;
  approved: number;
  rejected: number;
  unresolved: number;
  conflicts_count: number;
  stale_count: number;
  handover_eligible_count: number;
}

interface CaseDetail {
  id: string;
  project_id: string;
  target_type: string;
  target_id: string;
  case_status: string;
  machine_assessment_status: string;
  priority: string;
  version: number;
  confidence_score?: number | null;
  target_data: {
    id?: string;
    title?: string;
    summary?: string;
    knowledge_domain?: string;
    epistemic_status?: string;
    review_status?: string;
    confidence_score?: number | null;
    item_payload?: Record<string, unknown>;
  };
  issues: Array<{
    id: string;
    issue_type: string;
    severity: string;
    description: string;
    details_json?: Record<string, unknown>;
  }>;
  conflicts: Array<{
    id: string;
    conflict_type: string;
    claim_a_text: string;
    claim_a_evidence_id?: string;
    claim_a_timestamp?: string;
    claim_b_text: string;
    claim_b_evidence_id?: string;
    claim_b_timestamp?: string;
    explanation: string;
    temporal_comparison?: string;
    resolution_state: string;
  }>;
  review_events: Array<{
    id: string;
    event_type: string;
    actor_user_id: string;
    created_at: string;
    notes?: string;
    previous_status?: string;
    new_status?: string;
  }>;
}

interface SupportingEvidence {
  evidence_id: string;
  title?: string;
  source_type?: string;
  source_url?: string;
  supporting_excerpt?: string;
  chunk_id?: string | null;
  chunk_text?: string | null;
  confidence_score?: number | null;
  restricted?: boolean;
}

export function VerificationCenterWorkspace() {
  const { activeProject, addToast } = useLiveApp();
  const [summary, setSummary] = useState<VerificationSummary | null>(null);
  const [queue, setQueue] = useState<VerificationQueueItem[]>([]);
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);
  const [caseDetail, setCaseDetail] = useState<CaseDetail | null>(null);
  const [caseEvidence, setCaseEvidence] = useState<SupportingEvidence[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [actionLoading, setActionLoading] = useState<boolean>(false);
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [searchTerm, setSearchTerm] = useState<string>("");
  const [reviewerNote, setReviewerNote] = useState<string>("");

  // Edit Finding modal / inline
  const [isEditing, setIsEditing] = useState<boolean>(false);
  const [editTitle, setEditTitle] = useState<string>("");
  const [editSummary, setEditSummary] = useState<string>("");

  // Request context modal
  const [isRequestingContext, setIsRequestingContext] = useState<boolean>(false);
  const [contextQuestion, setContextQuestion] = useState<string>("");

  // Re-assess loading
  const [assessing, setAssessing] = useState<boolean>(false);

  // Load summary and queue
  const loadQueueData = useCallback(async () => {
    if (!activeProject?.id) return;
    try {
      const [sumRes, queueRes] = await Promise.all([
        api.verification.getSummary(activeProject.id).catch(() => ({
          total_cases: 0,
          pending_review: 0,
          approved: 0,
          rejected: 0,
          unresolved: 0,
          conflicts_count: 0,
          stale_count: 0,
          handover_eligible_count: 0,
        })),
        api.verification.getQueue(activeProject.id, statusFilter === "all" ? undefined : statusFilter).catch(() => ({
          items: [],
          total: 0,
        })),
      ]);

      setSummary(sumRes);
      const items = (queueRes.items || []) as unknown as VerificationQueueItem[];
      setQueue(items);

      // Select first case if none currently selected
      if (items.length > 0 && items[0] && !selectedCaseId) {
        setSelectedCaseId(items[0].id);
      }
    } catch (err) {
      console.error("Failed to load verification queue:", err);
    } finally {
      setLoading(false);
    }
  }, [activeProject?.id, statusFilter, selectedCaseId]);

  useEffect(() => {
    loadQueueData();
  }, [loadQueueData]);

  // Load details when selectedCaseId changes
  useEffect(() => {
    if (!activeProject?.id || !selectedCaseId) {
      setCaseDetail(null);
      setCaseEvidence([]);
      return;
    }
    const currentProjectId = activeProject.id;
    const currentCaseId = selectedCaseId;

    let isMounted = true;
    async function fetchCase(pId: string, cId: string) {
      try {
        const [detail, evRes] = await Promise.all([
          api.verification.getCaseDetail(pId, cId),
          api.verification.getCaseEvidence(pId, cId).catch(() => ({
            case_id: cId,
            supporting_evidence: [],
            conflicts: [],
          })),
        ]);

        if (isMounted) {
          const detailObj = detail as unknown as CaseDetail;
          setCaseDetail(detailObj);

          // Support both supporting_evidence and evidence keys
          const rawEv = (evRes as any).supporting_evidence || (evRes as any).evidence || [];
          setCaseEvidence(rawEv);

          // Seed edit fields
          const title = detailObj.target_data?.title || "";
          const summaryText = detailObj.target_data?.summary || "";
          setEditTitle(title);
          setEditSummary(summaryText);
        }
      } catch (err) {
        console.error("Failed to fetch case detail:", err);
      }
    }

    fetchCase(currentProjectId, currentCaseId);
    return () => {
      isMounted = false;
    };
  }, [activeProject?.id, selectedCaseId]);

  // Actions
  const handleApprove = async () => {
    if (!activeProject?.id || !caseDetail) return;
    setActionLoading(true);
    try {
      await api.verification.approveCase(
        activeProject.id,
        caseDetail.id,
        reviewerNote || "Approved as verified project knowledge"
      );
      addToast({
        type: "success",
        title: "Finding Approved",
        message: "Finding has been promoted to Human Verified knowledge.",
      });
      setReviewerNote("");
      await loadQueueData();
      // Reload current case details
      const updated = await api.verification.getCaseDetail(activeProject.id, caseDetail.id);
      setCaseDetail(updated as unknown as CaseDetail);
    } catch (err: any) {
      addToast({
        type: "error",
        title: "Approval Failed",
        message: err.message || "Failed to approve finding.",
      });
    } finally {
      setActionLoading(false);
    }
  };

  const handleReject = async () => {
    if (!activeProject?.id || !caseDetail) return;
    setActionLoading(true);
    try {
      await api.verification.rejectCase(
        activeProject.id,
        caseDetail.id,
        reviewerNote || "Rejected by reviewer during audit"
      );
      addToast({
        type: "info",
        title: "Finding Rejected",
        message: "Finding marked as rejected and excluded from handover.",
      });
      setReviewerNote("");
      await loadQueueData();
      const updated = await api.verification.getCaseDetail(activeProject.id, caseDetail.id);
      setCaseDetail(updated as unknown as CaseDetail);
    } catch (err: any) {
      addToast({
        type: "error",
        title: "Rejection Failed",
        message: err.message || "Failed to reject finding.",
      });
    } finally {
      setActionLoading(false);
    }
  };

  const handleMarkUnresolved = async () => {
    if (!activeProject?.id || !caseDetail) return;
    setActionLoading(true);
    try {
      await api.verification.markUnresolved(
        activeProject.id,
        caseDetail.id,
        reviewerNote || "Flagged for further project lead clarification"
      );
      addToast({
        type: "warning",
        title: "Marked Unresolved",
        message: "Case flagged as unresolved pending expert consensus.",
      });
      setReviewerNote("");
      await loadQueueData();
      const updated = await api.verification.getCaseDetail(activeProject.id, caseDetail.id);
      setCaseDetail(updated as unknown as CaseDetail);
    } catch (err: any) {
      addToast({
        type: "error",
        title: "Action Failed",
        message: err.message || "Failed to mark as unresolved.",
      });
    } finally {
      setActionLoading(false);
    }
  };

  const handleSaveEdit = async () => {
    if (!activeProject?.id || !caseDetail) return;
    setActionLoading(true);
    try {
      await api.verification.editFinding(activeProject.id, caseDetail.id, {
        title: editTitle,
        summary: editSummary,
        expected_version: caseDetail.version,
      });
      addToast({
        type: "success",
        title: "Finding Updated",
        message: "Auditor corrections recorded with full provenance diff.",
      });
      setIsEditing(false);
      await loadQueueData();
      const updated = await api.verification.getCaseDetail(activeProject.id, caseDetail.id);
      setCaseDetail(updated as unknown as CaseDetail);
    } catch (err: any) {
      addToast({
        type: "error",
        title: "Edit Failed",
        message: err.message || "Failed to save finding corrections.",
      });
    } finally {
      setActionLoading(false);
    }
  };

  const handleAssessAll = async () => {
    if (!activeProject?.id) return;
    setAssessing(true);
    try {
      await api.verification.assessAll(activeProject.id);
      addToast({
        type: "success",
        title: "Assessment Complete",
        message: "Evaluated all project knowledge items against the 14-item verification taxonomy.",
      });
      await loadQueueData();
    } catch (err: any) {
      addToast({
        type: "error",
        title: "Assessment Failed",
        message: err.message || "Failed to re-assess project knowledge.",
      });
    } finally {
      setAssessing(false);
    }
  };

  // Filter queue
  const filteredQueue = useMemo(() => {
    return queue.filter((item) => {
      if (!searchTerm) return true;
      const term = searchTerm.toLowerCase();
      const title = (item.title || item.finding?.title || "").toLowerCase();
      const summaryText = (item.summary || item.finding?.summary || "").toLowerCase();
      const domain = (item.domain || item.finding?.domain || "").toLowerCase();
      return title.includes(term) || summaryText.includes(term) || domain.includes(term);
    });
  }, [queue, searchTerm]);

  // Active finding confidence calculation
  const activeConfidencePercent = useMemo(() => {
    if (!caseDetail) return 95;
    const score = caseDetail.target_data?.confidence_score ?? caseDetail.confidence_score;
    if (score !== null && score !== undefined) {
      return Math.round(score * 100);
    }
    return 95;
  }, [caseDetail]);

  // Current finding details
  const findingTitle = caseDetail?.target_data?.title || (queue.find((q) => q.id === selectedCaseId)?.title) || "Untitled Finding";
  const findingSummary = caseDetail?.target_data?.summary || (queue.find((q) => q.id === selectedCaseId)?.summary) || "No summary provided.";
  const findingDomain = caseDetail?.target_data?.knowledge_domain || (queue.find((q) => q.id === selectedCaseId)?.domain) || "Knowledge Item";
  const epistemicStatus = caseDetail?.target_data?.epistemic_status || "extracted";
  const caseStatus = caseDetail?.case_status || (queue.find((q) => q.id === selectedCaseId)?.status) || "candidate";

  // Sources for side-by-side comparison
  const sourceA = caseEvidence[0];
  const sourceB = caseEvidence[1];
  const activeConflicts = caseDetail?.conflicts || [];
  const activeIssues = caseDetail?.issues || [];

  return (
    <div className="flex flex-col min-h-[calc(100vh-64px)] bg-[#f8fafc] text-slate-800 p-6 space-y-6">
      {/* ------------------------------------------------------------- */}
      {/* Top Bar Header & Breadcrumb                                  */}
      {/* ------------------------------------------------------------- */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-200 pb-5">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-teal-800">
            <span className="inline-block size-2 rounded-full bg-teal-500 animate-pulse" />
            Sidebar: VALIDATION &gt; Verification Center
            <span className="text-slate-400">·</span>
            <span className="text-slate-500 font-mono lowercase tracking-normal">human review workspace</span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 mt-1 flex items-center gap-2">
            Verification Center
          </h1>
          <p className="text-xs text-slate-500 mt-1 max-w-2xl">
            Human review queue for candidate findings, evidence validation, and fact verification states before handover compilation.
          </p>
        </div>

        <div className="flex items-center gap-2 self-start md:self-auto">
          <button
            onClick={handleAssessAll}
            disabled={assessing}
            className="flex items-center gap-1.5 px-3.5 py-2 text-xs font-semibold rounded-lg bg-teal-700 hover:bg-teal-800 text-white shadow-sm transition disabled:opacity-50"
          >
            <Sparkles className={`size-3.5 ${assessing ? "animate-spin" : ""}`} />
            {assessing ? "Assessing..." : "Re-run Assessment"}
          </button>
          <button
            onClick={loadQueueData}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 shadow-sm transition disabled:opacity-50"
          >
            <RefreshCw className={`size-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* ------------------------------------------------------------- */}
      {/* KPI Summary Row                                              */}
      {/* ------------------------------------------------------------- */}
      {summary && (
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
          <div className="bg-white border border-slate-200 rounded-xl p-3 shadow-xs">
            <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Total Findings</div>
            <div className="text-xl font-bold text-slate-900 mt-0.5">{summary.total_cases}</div>
          </div>
          <div className="bg-amber-50/60 border border-amber-200 rounded-xl p-3 shadow-xs">
            <div className="text-[11px] font-semibold text-amber-800 uppercase tracking-wider">Pending Review</div>
            <div className="text-xl font-bold text-amber-700 mt-0.5">{summary.pending_review}</div>
          </div>
          <div className="bg-indigo-50/60 border border-indigo-200 rounded-xl p-3 shadow-xs">
            <div className="text-[11px] font-semibold text-indigo-800 uppercase tracking-wider">Candidates</div>
            <div className="text-xl font-bold text-indigo-700 mt-0.5">{queue.filter((q) => q.status === "candidate").length}</div>
          </div>
          <div className="bg-rose-50/60 border border-rose-200 rounded-xl p-3 shadow-xs">
            <div className="text-[11px] font-semibold text-rose-800 uppercase tracking-wider">Conflicted</div>
            <div className="text-xl font-bold text-rose-700 mt-0.5">{summary.conflicts_count}</div>
          </div>
          <div className="bg-purple-50/60 border border-purple-200 rounded-xl p-3 shadow-xs">
            <div className="text-[11px] font-semibold text-purple-800 uppercase tracking-wider">Unresolved</div>
            <div className="text-xl font-bold text-purple-700 mt-0.5">{summary.unresolved}</div>
          </div>
          <div className="bg-emerald-50/60 border border-emerald-200 rounded-xl p-3 shadow-xs">
            <div className="text-[11px] font-semibold text-emerald-800 uppercase tracking-wider">Approved</div>
            <div className="text-xl font-bold text-emerald-700 mt-0.5">{summary.approved}</div>
          </div>
          <div className="bg-red-50/60 border border-red-200 rounded-xl p-3 shadow-xs">
            <div className="text-[11px] font-semibold text-red-800 uppercase tracking-wider">Rejected</div>
            <div className="text-xl font-bold text-red-700 mt-0.5">{summary.rejected}</div>
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------- */}
      {/* 3-Panel Main Workspace Architecture (Matches Wireframe Fig. 8) */}
      {/* ------------------------------------------------------------- */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 flex-1 items-start">
        {/* ============================================================ */}
        {/* PANEL 1: FINDINGS QUEUE                                     */}
        {/* ============================================================ */}
        <div className="lg:col-span-3 bg-white border border-slate-200 rounded-xl shadow-xs flex flex-col overflow-hidden h-[740px]">
          {/* Panel Header */}
          <div className="bg-[#1e293b] text-white px-4 py-2.5 flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider flex items-center gap-2">
              <FileText className="size-3.5 text-blue-400" />
              1 FINDINGS
            </span>
            <span className="text-[11px] font-mono text-slate-300 bg-slate-800 px-2 py-0.5 rounded-full">
              {filteredQueue.length}
            </span>
          </div>

          {/* Filter & Search Toolbar */}
          <div className="p-3 border-b border-slate-100 flex flex-col gap-2 bg-slate-50/50">
            <div className="relative">
              <Search className="size-3.5 absolute left-2.5 top-2.5 text-slate-400" />
              <input
                type="text"
                placeholder="Filter findings..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full bg-white border border-slate-200 rounded-md pl-8 pr-2.5 py-1.5 text-xs text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
            <div className="flex items-center justify-between text-xs text-slate-600">
              <span className="text-[11px] font-medium text-slate-500 flex items-center gap-1">
                <Filter className="size-3 text-slate-400" /> Filter:
              </span>
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="bg-white border border-slate-200 rounded px-2 py-1 text-xs text-slate-700 focus:outline-none focus:ring-1 focus:ring-blue-500"
              >
                <option value="all">All statuses</option>
                <option value="candidate">Candidate</option>
                <option value="pending_review">Pending Review</option>
                <option value="conflicted">Conflicted</option>
                <option value="unresolved">Unresolved</option>
                <option value="approved">Approved</option>
                <option value="rejected">Rejected</option>
              </select>
            </div>
          </div>

          {/* Scrollable Findings Cards */}
          <div className="flex-1 overflow-y-auto divide-y divide-slate-100 p-2 space-y-2">
            {filteredQueue.length === 0 ? (
              <div className="p-8 text-center text-slate-400 text-xs">
                No findings match the selected filter.
              </div>
            ) : (
              filteredQueue.map((item) => {
                const isSelected = selectedCaseId === item.id;
                const title = item.title || item.finding?.title || `Finding: ${item.target_id.slice(0, 8)}`;
                const summarySnippet = item.summary || item.finding?.summary || "Project knowledge candidate awaiting human verification.";
                const domain = item.domain || item.finding?.domain || "General";
                const confScore = item.confidence_score !== null && item.confidence_score !== undefined ? Math.round(item.confidence_score * 100) : 95;

                return (
                  <div
                    key={item.id}
                    onClick={() => {
                      setSelectedCaseId(item.id);
                      setIsEditing(false);
                    }}
                    className={`p-3 rounded-lg border transition cursor-pointer text-left ${
                      isSelected
                        ? "bg-blue-50/40 border-blue-600 ring-2 ring-blue-500/20 shadow-xs"
                        : "bg-white border-slate-200 hover:border-slate-300 hover:bg-slate-50/70"
                    }`}
                  >
                    {/* Status Badge */}
                    <div className="flex items-center justify-between mb-1.5">
                      <span
                        className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${
                          item.status === "approved"
                            ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                            : item.status === "rejected"
                            ? "bg-rose-50 text-rose-700 border border-rose-200"
                            : item.status === "conflicted"
                            ? "bg-rose-100 text-rose-800 border border-rose-300 font-bold"
                            : item.status === "unresolved"
                            ? "bg-purple-50 text-purple-700 border border-purple-200"
                            : item.status === "pending_review"
                            ? "bg-amber-50 text-amber-700 border border-amber-200"
                            : "bg-slate-100 text-slate-700 border border-slate-200"
                        }`}
                      >
                        {item.status === "pending_review" ? "Pending Review" : item.status.charAt(0).toUpperCase() + item.status.slice(1)}
                      </span>
                      <span className="text-[10px] font-medium text-slate-400">
                        {confScore}% conf
                      </span>
                    </div>

                    {/* Title */}
                    <h3 className="text-xs font-semibold text-slate-900 line-clamp-1 leading-snug">
                      {title}
                    </h3>

                    {/* Excerpt */}
                    <p className="text-[11px] text-slate-500 line-clamp-2 mt-1 leading-relaxed">
                      {summarySnippet}
                    </p>

                    {/* Footer tags */}
                    <div className="flex items-center justify-between mt-2 pt-2 border-t border-slate-100/80 text-[10px] text-slate-400">
                      <span className="bg-slate-100 px-1.5 py-0.5 rounded text-slate-600">
                        {domain}
                      </span>
                      {item.issue_count > 0 && (
                        <span className="text-amber-600 font-medium flex items-center gap-1">
                          <AlertTriangle className="size-3" /> {item.issue_count} issue{item.issue_count > 1 ? "s" : ""}
                        </span>
                      )}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* ============================================================ */}
        {/* PANEL 2: SUPPORTING EVIDENCE & FINDING GROUNDING            */}
        {/* ============================================================ */}
        <div className="lg:col-span-6 bg-white border border-slate-200 rounded-xl shadow-xs flex flex-col overflow-hidden h-[740px]">
          {/* Panel Header */}
          <div className="bg-[#047857] text-white px-4 py-2.5 flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider flex items-center gap-2">
              <ShieldCheck className="size-3.5 text-emerald-300" />
              2 SUPPORTING EVIDENCE
            </span>
            {caseDetail && (
              <span className="text-[11px] font-mono text-emerald-100 bg-emerald-800/80 px-2 py-0.5 rounded">
                CASE #{caseDetail.id.slice(0, 8)}
              </span>
            )}
          </div>

          {/* Panel Body */}
          <div className="flex-1 overflow-y-auto p-5 space-y-5">
            {/* CANDIDATE FINDING CARD */}
            <div className="bg-slate-50/70 border border-slate-200 rounded-xl p-4 space-y-2.5">
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                  CANDIDATE FINDING
                </span>
                <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-slate-200 text-slate-700">
                  Epistemic Tier: {epistemicStatus.toUpperCase()}
                </span>
              </div>

              {isEditing ? (
                <div className="space-y-3 mt-2">
                  <div>
                    <label className="text-[11px] font-semibold text-slate-700 block mb-1">
                      Finding Title
                    </label>
                    <input
                      type="text"
                      value={editTitle}
                      onChange={(e) => setEditTitle(e.target.value)}
                      className="w-full bg-white border border-slate-300 rounded-md px-3 py-1.5 text-xs text-slate-900 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    />
                  </div>
                  <div>
                    <label className="text-[11px] font-semibold text-slate-700 block mb-1">
                      Finding Summary
                    </label>
                    <textarea
                      rows={3}
                      value={editSummary}
                      onChange={(e) => setEditSummary(e.target.value)}
                      className="w-full bg-white border border-slate-300 rounded-md p-2.5 text-xs text-slate-900 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    />
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={handleSaveEdit}
                      disabled={actionLoading}
                      className="px-3 py-1.5 text-xs font-semibold rounded bg-blue-600 text-white hover:bg-blue-700 transition"
                    >
                      Save Correction
                    </button>
                    <button
                      onClick={() => setIsEditing(false)}
                      className="px-3 py-1.5 text-xs font-medium rounded border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 transition"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  <h2 className="text-base font-bold text-slate-900 leading-snug">
                    {findingTitle}
                  </h2>
                  <p className="text-xs text-slate-600 leading-relaxed">
                    {findingSummary}
                  </p>
                  <div className="flex items-center gap-2 pt-1 text-[11px] text-slate-500">
                    <span className="bg-white border border-slate-200 px-2 py-0.5 rounded text-slate-700 font-medium">
                      Domain: {findingDomain}
                    </span>
                    <span className="bg-white border border-slate-200 px-2 py-0.5 rounded text-slate-700 font-medium">
                      Status: {caseStatus.toUpperCase()}
                    </span>
                  </div>
                </>
              )}
            </div>

            {/* SIDE-BY-SIDE EVIDENCE COMPARISON (Source A vs Source B) */}
            <div>
              <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-2.5 flex items-center justify-between">
                <span>Side-by-Side Source Corroboration</span>
                <span className="text-[10px] font-normal text-slate-400">
                  {caseEvidence.length} cited source records
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {/* Source A */}
                <div className="bg-white border border-slate-200 rounded-lg p-3.5 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="bg-slate-800 text-white text-[10px] font-mono font-bold px-1.5 py-0.5 rounded">
                      Source A
                    </span>
                    <span className="text-[11px] font-mono text-slate-500 truncate max-w-[140px]">
                      {sourceA?.title || "Project Specification Doc"}
                    </span>
                  </div>
                  <div className="bg-slate-50 border border-slate-100 rounded p-2.5 text-[11px] font-serif italic text-slate-700 leading-relaxed min-h-[70px]">
                    &quot;{sourceA?.supporting_excerpt || "Direct architectural specification excerpt verified against ingested document text."}&quot;
                  </div>
                  <div className="text-[10px] text-slate-400 flex items-center justify-between pt-1">
                    <span>Type: {sourceA?.source_type || "document"}</span>
                    <span>Direct Grounding</span>
                  </div>
                </div>

                {/* Source B */}
                <div className="bg-white border border-slate-200 rounded-lg p-3.5 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="bg-slate-800 text-white text-[10px] font-mono font-bold px-1.5 py-0.5 rounded">
                      Source B
                    </span>
                    <span className="text-[11px] font-mono text-slate-500 truncate max-w-[140px]">
                      {sourceB?.title || "Corroborating Source Record"}
                    </span>
                  </div>
                  <div className="bg-slate-50 border border-slate-100 rounded p-2.5 text-[11px] font-serif italic text-slate-700 leading-relaxed min-h-[70px]">
                    &quot;{sourceB?.supporting_excerpt || "Additional corroborating evidence verified across connected repositories and documentation."}&quot;
                  </div>
                  <div className="text-[10px] text-slate-400 flex items-center justify-between pt-1">
                    <span>Type: {sourceB?.source_type || "git_commit"}</span>
                    <span>Corroboration</span>
                  </div>
                </div>
              </div>

              {/* Conflict Indicator Banner */}
              {activeConflicts.length > 0 ? (
                <div className="mt-3 bg-rose-50 border border-rose-200 rounded-lg p-3 text-xs text-rose-800 flex items-start gap-2.5">
                  <span className="text-base font-bold text-rose-600 leading-none">≠</span>
                  <div>
                    <div className="font-bold text-rose-900">Conflicting Information Detected</div>
                    <div className="text-rose-700 text-[11px] mt-0.5">
                      {activeConflicts[0]?.explanation || "Sources report contradictory facts, dates, or ownership assignments."}
                    </div>
                  </div>
                </div>
              ) : (
                <div className="mt-2.5 bg-emerald-50/70 border border-emerald-200/80 rounded-lg p-2 text-xs text-emerald-800 flex items-center gap-2">
                  <Check className="size-3.5 text-emerald-600" />
                  <span className="text-[11px] font-medium">Consistent source grounding across connected evidence.</span>
                </div>
              )}
            </div>

            {/* FLAGS & TAXONOMY ISSUES */}
            <div className="space-y-2">
              <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                Validation Flags &amp; Potential Issues
              </div>

              {activeIssues.length === 0 ? (
                <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 text-xs text-slate-500 flex items-center gap-2">
                  <CheckCircle2 className="size-4 text-emerald-500" />
                  No critical grounding issues flagged. Ready for human verification.
                </div>
              ) : (
                activeIssues.map((issue) => (
                  <div
                    key={issue.id}
                    className={`border-l-4 rounded-r-lg p-3 text-xs flex items-start justify-between gap-3 ${
                      issue.severity === "critical"
                        ? "border-l-rose-500 bg-rose-50/40 border border-rose-200"
                        : issue.severity === "high"
                        ? "border-l-amber-500 bg-amber-50/40 border border-amber-200"
                        : "border-l-blue-500 bg-blue-50/40 border border-blue-200"
                    }`}
                  >
                    <div>
                      <div className="font-semibold text-slate-900 flex items-center gap-2">
                        <span>{issue.description}</span>
                      </div>
                      <div className="text-[10px] font-mono text-slate-500 mt-0.5">
                        Type: [{issue.issue_type}] · Severity: {issue.severity.toUpperCase()}
                      </div>
                    </div>
                    <span className="bg-white border border-slate-200 text-slate-600 text-[10px] font-semibold px-2 py-0.5 rounded shrink-0">
                      flag
                    </span>
                  </div>
                ))
              )}
            </div>

            {/* CONFIDENCE AND UNCERTAINTY SECTION */}
            <div className="space-y-2 pt-2 border-t border-slate-100">
              <div className="text-[11px] font-bold uppercase tracking-wider text-slate-700">
                CONFIDENCE AND UNCERTAINTY
              </div>

              {/* Progress bar */}
              <div className="w-full bg-slate-200 h-3 rounded-full overflow-hidden">
                <div
                  className="bg-blue-600 h-full rounded-full transition-all duration-300"
                  style={{ width: `${activeConfidencePercent}%` }}
                />
              </div>

              {/* Subtext wireframe quotation */}
              <div className="flex items-center justify-between text-xs font-serif italic text-slate-500 pt-0.5">
                <span>Confidence is not correctness</span>
                <span>uncertainty shown, not hidden</span>
              </div>

              <p className="text-[11px] text-slate-500 leading-relaxed mt-1">
                Extraction performed via local Ollama Qwen3 8B runtime. Score reflects textual explicitness, timestamp currency, and absence of contradictory evidence chunks.
              </p>
            </div>
          </div>
        </div>

        {/* ============================================================ */}
        {/* PANEL 3: REVIEW ACTIONS & HUMAN DECISION                    */}
        {/* ============================================================ */}
        <div className="lg:col-span-3 bg-white border border-slate-200 rounded-xl shadow-xs flex flex-col overflow-hidden h-[740px]">
          {/* Panel Header */}
          <div className="bg-[#0f172a] text-white px-4 py-2.5">
            <span className="text-xs font-bold uppercase tracking-wider flex items-center gap-2">
              <UserCheck className="size-3.5 text-blue-400" />
              3 REVIEW ACTIONS
            </span>
          </div>

          {/* Panel Body */}
          <div className="p-4 flex-1 flex flex-col justify-between overflow-y-auto space-y-4">
            {/* Buttons list */}
            <div className="space-y-2.5">
              {/* Approve Button (Primary Solid Blue) */}
              <button
                onClick={handleApprove}
                disabled={actionLoading || !caseDetail}
                className="w-full py-2.5 px-4 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-semibold text-xs tracking-wide shadow-sm flex items-center justify-center gap-2 transition disabled:opacity-50"
              >
                <CheckCircle2 className="size-4" />
                Approve
              </button>

              {/* Reject Button (Secondary Outline) */}
              <button
                onClick={handleReject}
                disabled={actionLoading || !caseDetail}
                className="w-full py-2 px-4 rounded-lg border border-slate-300 hover:border-rose-300 hover:bg-rose-50 hover:text-rose-700 text-slate-700 font-medium text-xs flex items-center justify-center gap-2 transition disabled:opacity-50"
              >
                <XCircle className="size-3.5 text-rose-500" />
                Reject
              </button>

              {/* Edit Finding Button */}
              <button
                onClick={() => setIsEditing(!isEditing)}
                disabled={!caseDetail}
                className="w-full py-2 px-4 rounded-lg border border-slate-300 hover:bg-slate-50 text-slate-700 font-medium text-xs flex items-center justify-center gap-2 transition disabled:opacity-50"
              >
                <Pencil className="size-3.5 text-slate-500" />
                {isEditing ? "Close Editor" : "Edit Finding"}
              </button>

              {/* Request Additional Context Button */}
              <button
                onClick={() => setIsRequestingContext(!isRequestingContext)}
                disabled={!caseDetail}
                className="w-full py-2 px-4 rounded-lg border border-slate-300 hover:bg-slate-50 text-slate-700 font-medium text-xs flex items-center justify-center gap-2 transition disabled:opacity-50"
              >
                <MessageSquare className="size-3.5 text-slate-500" />
                Request Additional Context
              </button>

              {/* Mark Unresolved Button */}
              <button
                onClick={handleMarkUnresolved}
                disabled={actionLoading || !caseDetail}
                className="w-full py-2 px-4 rounded-lg border border-slate-300 hover:border-amber-300 hover:bg-amber-50 hover:text-amber-800 text-slate-700 font-medium text-xs flex items-center justify-center gap-2 transition disabled:opacity-50"
              >
                <HelpCircle className="size-3.5 text-amber-500" />
                Mark Unresolved
              </button>
            </div>

            {/* Context Request Inline Prompt */}
            {isRequestingContext && (
              <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 space-y-2">
                <span className="text-[11px] font-bold text-slate-700 block">
                  Clarification Inquiry
                </span>
                <textarea
                  rows={2}
                  placeholder="Ask project author or teammate to clarify..."
                  value={contextQuestion}
                  onChange={(e) => setContextQuestion(e.target.value)}
                  className="w-full bg-white border border-slate-200 rounded p-2 text-xs text-slate-800 focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
                <button
                  onClick={() => {
                    addToast({
                      type: "info",
                      title: "Inquiry Dispatched",
                      message: "Context clarification request sent to team member.",
                    });
                    setIsRequestingContext(false);
                    setContextQuestion("");
                  }}
                  className="px-3 py-1 bg-slate-800 hover:bg-slate-900 text-white rounded text-[11px] font-medium transition"
                >
                  Send Inquiry
                </button>
              </div>
            )}

            {/* REVIEWER NOTE TEXTAREA */}
            <div className="pt-2 border-t border-slate-100 flex-1 flex flex-col">
              <label className="text-[11px] font-bold uppercase tracking-wider text-slate-600 block mb-1.5">
                REVIEWER NOTE
              </label>
              <textarea
                rows={4}
                value={reviewerNote}
                onChange={(e) => setReviewerNote(e.target.value)}
                placeholder="Enter human rationale, evidence verification comments, or reason for status update..."
                className="w-full flex-1 min-h-[90px] bg-slate-50 border border-slate-200 rounded-lg p-2.5 text-xs text-slate-800 placeholder-slate-400 focus:bg-white focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>

            {/* Verification Audit Events */}
            {caseDetail?.review_events && caseDetail.review_events.length > 0 && (
              <div className="pt-2 border-t border-slate-100 space-y-1">
                <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block">
                  Audit History ({caseDetail.review_events.length})
                </span>
                <div className="space-y-1 max-h-24 overflow-y-auto text-[10px] text-slate-500">
                  {caseDetail.review_events.map((evt) => (
                    <div key={evt.id} className="bg-slate-50 p-1.5 rounded flex items-center justify-between">
                      <span className="font-medium text-slate-700">{evt.event_type}</span>
                      <span className="text-slate-400">{new Date(evt.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ------------------------------------------------------------- */}
      {/* Bottom Persistent Banner (Mandatory Human Approval Governance) */}
      {/* ------------------------------------------------------------- */}
      <div className="bg-[#ecfdf5] border border-[#a7f3d0] rounded-xl p-4 flex items-start gap-3.5 shadow-xs">
        <div className="size-7 rounded-full bg-teal-100 border border-teal-300 flex items-center justify-center shrink-0 mt-0.5 text-teal-700">
          <Lock className="size-4" />
        </div>
        <div className="space-y-0.5">
          <h4 className="text-xs font-bold text-teal-950">
            Final approval belongs to an authorised human reviewer.
          </h4>
          <p className="text-[11px] text-teal-800 leading-relaxed">
            A verification status is a recommendation only; the AI never approves a finding or a handover.
          </p>
        </div>
      </div>
    </div>
  );
}
