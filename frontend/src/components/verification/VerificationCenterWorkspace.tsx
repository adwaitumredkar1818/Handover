"use client";

import React, { useState, useEffect, useCallback, useMemo } from "react";
import {
  CheckCircle2,
  XCircle,
  HelpCircle,
  AlertTriangle,
  FileText,
  UserCheck,
  Search,
  Filter,
  RefreshCw,
  ExternalLink,
  MessageSquare,
  Sparkles,
  Lock,
  Pencil,
  FileQuestion,
  Check,
  Quote,
  Send,
  Calendar,
  User as UserIcon,
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
    action?: string;
    event_type?: string;
    reviewer_user_id?: string;
    actor_user_id?: string;
    created_at: string;
    notes?: string;
    review_notes?: string;
    previous_status?: string;
    new_status?: string;
  }>;
}

interface SupportingEvidence {
  evidence_id: string;
  title?: string;
  source_type?: string;
  source_url?: string | null;
  author?: string | null;
  support_type?: string;
  supporting_excerpt?: string | null;
  excerpt_verified?: boolean;
  source_location?: Record<string, unknown>;
  chunk_id?: string | null;
  chunk_text?: string | null;
  confidence_score?: number | null;
  restricted?: boolean;
}

export function VerificationCenterWorkspace() {
  const { activeProject, addToast, user } = useLiveApp();
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

  // Expandable chunk viewer state
  const [expandedChunks, setExpandedChunks] = useState<Record<string, boolean>>({});

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

          // Real supporting evidence links from backend
          const rawEv = (evRes as any).supporting_evidence || (evRes as any).evidence || [];
          setCaseEvidence(rawEv);

          // Seed edit fields with real finding data
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
      const noteToSave = reviewerNote.trim() || "Approved as verified project knowledge";
      await api.verification.approveCase(
        activeProject.id,
        caseDetail.id,
        noteToSave
      );
      addToast({
        type: "success",
        title: "Finding Approved",
        message: "Finding promoted to Human Verified knowledge and recorded in audit log.",
      });
      setReviewerNote("");
      await loadQueueData();
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
      const noteToSave = reviewerNote.trim() || "Rejected by reviewer during audit";
      await api.verification.rejectCase(
        activeProject.id,
        caseDetail.id,
        noteToSave
      );
      addToast({
        type: "info",
        title: "Finding Rejected",
        message: "Finding marked as rejected and excluded from handover compilation.",
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
      const noteToSave = reviewerNote.trim() || "Flagged for further project lead clarification";
      await api.verification.markUnresolved(
        activeProject.id,
        caseDetail.id,
        noteToSave
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
        reason: reviewerNote.trim() || "Auditor correction to title/summary",
      });
      addToast({
        type: "success",
        title: "Finding Updated",
        message: "Auditor corrections recorded with full version provenance.",
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

  const handleSendContextRequest = async () => {
    if (!activeProject?.id || !caseDetail || !contextQuestion.trim()) return;
    setActionLoading(true);
    try {
      const recipientId = activeProject.owner_id || user?.id;
      if (!recipientId) throw new Error("No recipient available for clarification request.");
      await api.verification.requestContext(activeProject.id, caseDetail.id, {
        requested_from_user_id: recipientId,
        question: contextQuestion.trim(),
        requested_information_type: "clarification",
        expected_version: caseDetail.version,
      });
      addToast({
        type: "success",
        title: "Clarification Dispatched",
        message: "Context clarification request sent to team member and logged in audit trail.",
      });
      setIsRequestingContext(false);
      setContextQuestion("");
      const updated = await api.verification.getCaseDetail(activeProject.id, caseDetail.id);
      setCaseDetail(updated as unknown as CaseDetail);
    } catch (err: any) {
      addToast({
        type: "error",
        title: "Dispatch Failed",
        message: err.message || "Failed to dispatch clarification inquiry.",
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
        message: "Deterministic verification rules and confidence checks evaluated.",
      });
      await loadQueueData();
      if (selectedCaseId) {
        const updated = await api.verification.getCaseDetail(activeProject.id, selectedCaseId);
        setCaseDetail(updated as unknown as CaseDetail);
      }
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

  // Active finding confidence calculation - strictly Ollama/backend score, NO 95% default!
  const activeConfidencePercent = useMemo(() => {
    if (!caseDetail) return null;
    const score = caseDetail.target_data?.confidence_score ?? caseDetail.confidence_score;
    if (score !== null && score !== undefined) {
      return Math.round(score * 100);
    }
    return null;
  }, [caseDetail]);

  // Current finding details
  const findingTitle = caseDetail?.target_data?.title || (queue.find((q) => q.id === selectedCaseId)?.title) || "Untitled Finding";
  const findingSummary = caseDetail?.target_data?.summary || (queue.find((q) => q.id === selectedCaseId)?.summary) || "No summary provided.";
  const findingDomain = caseDetail?.target_data?.knowledge_domain || (queue.find((q) => q.id === selectedCaseId)?.domain) || "Knowledge Item";
  const epistemicStatus = caseDetail?.target_data?.epistemic_status || "extracted";
  const caseStatus = caseDetail?.case_status || (queue.find((q) => q.id === selectedCaseId)?.status) || "candidate";

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
                const confScore = item.confidence_score !== null && item.confidence_score !== undefined
                  ? Math.round(item.confidence_score * 100)
                  : null;

                return (
                  <div
                    key={item.id}
                    onClick={() => {
                      setSelectedCaseId(item.id);
                      setIsEditing(false);
                      setIsRequestingContext(false);
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
                        {confScore !== null ? `${confScore}% conf` : "Unscored"}
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
        {/* PANEL 2: SUPPORTING EVIDENCE & PROVENANCE                   */}
        {/* ============================================================ */}
        <div className="lg:col-span-6 bg-white border border-slate-200 rounded-xl shadow-xs flex flex-col overflow-hidden h-[740px]">
          {/* Panel Header */}
          <div className="bg-[#0f766e] text-white px-4 py-2.5 flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider flex items-center gap-2">
              <FileText className="size-3.5 text-teal-200" />
              2 SUPPORTING EVIDENCE
            </span>
            <span className="text-[11px] font-mono text-teal-100 bg-teal-800/80 px-2 py-0.5 rounded-full">
              {caseEvidence.length} {caseEvidence.length === 1 ? "Citation" : "Citations"}
            </span>
          </div>

          {/* Panel Body */}
          <div className="p-4 flex-1 overflow-y-auto space-y-4">
            {/* Candidate Finding Card */}
            <div className="bg-slate-50/70 border border-slate-200 rounded-lg p-3.5 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                  CANDIDATE FINDING
                </span>
                <span className="text-[10px] font-mono uppercase bg-slate-200/80 text-slate-700 px-2 py-0.5 rounded font-medium">
                  Epistemic Tier: {epistemicStatus.toUpperCase()}
                </span>
              </div>

              {isEditing ? (
                <div className="space-y-3 pt-1">
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

            {/* REAL CITED SUPPORTING EVIDENCE */}
            <div>
              <div className="text-[11px] font-bold uppercase tracking-wider text-slate-600 mb-2.5 flex items-center justify-between">
                <span className="flex items-center gap-1.5">
                  <FileText className="size-3.5 text-teal-600" />
                  CITED SUPPORTING EVIDENCE & PROVENANCE
                </span>
                <span className="text-[11px] font-semibold text-slate-500 bg-slate-100 px-2 py-0.5 rounded-full">
                  {caseEvidence.length} {caseEvidence.length === 1 ? "Cited Source Record" : "Cited Source Records"}
                </span>
              </div>

              {caseEvidence.length === 0 ? (
                <div className="bg-amber-50/60 border border-amber-200 rounded-lg p-5 text-center space-y-2">
                  <FileQuestion className="size-7 text-amber-500 mx-auto" />
                  <div className="font-semibold text-xs text-amber-900">
                    No Direct Supporting Evidence Records Cited
                  </div>
                  <p className="text-[11px] text-amber-700 max-w-md mx-auto leading-relaxed">
                    This candidate finding currently has no direct cited source records in the knowledge base. Human reviewers should verify its claims or request additional context from the project team before approving.
                  </p>
                </div>
              ) : (
                <div className="space-y-3">
                  {caseEvidence.map((ev, idx) => {
                    const isChunkExpanded = Boolean(expandedChunks[ev.evidence_id || String(idx)]);
                    const pageNum = (ev.source_location as any)?.page_number;
                    const chunkIdx = (ev.source_location as any)?.chunk_index;

                    return (
                      <div
                        key={ev.evidence_id || idx}
                        className="bg-white border border-slate-200 rounded-lg p-3.5 space-y-2.5 shadow-xs transition hover:border-slate-300"
                      >
                        {/* Evidence Citation Header */}
                        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-2">
                          <div className="flex items-center gap-2">
                            <span className="bg-slate-800 text-white text-[10px] font-mono font-bold px-1.5 py-0.5 rounded">
                              Citation #{idx + 1}
                            </span>
                            <span className="font-semibold text-xs text-slate-900 truncate max-w-sm" title={ev.title}>
                              {ev.title || "Untitled Document"}
                            </span>
                          </div>
                          <div className="flex items-center gap-1.5 text-[10px]">
                            <span className="bg-teal-50 text-teal-700 border border-teal-200 font-medium px-2 py-0.5 rounded capitalize">
                              {ev.source_type ? ev.source_type.replace(/_/g, " ") : "Document"}
                            </span>
                            {ev.support_type && (
                              <span className="bg-blue-50 text-blue-700 border border-blue-200 font-medium px-2 py-0.5 rounded capitalize">
                                {ev.support_type.replace(/_/g, " ")}
                              </span>
                            )}
                            {ev.restricted && (
                              <span className="bg-rose-50 text-rose-700 border border-rose-200 font-medium px-2 py-0.5 rounded flex items-center gap-1">
                                <Lock className="size-2.5" /> Restricted ACL
                              </span>
                            )}
                          </div>
                        </div>

                        {/* Verbatim Supporting Excerpt */}
                        <div className="space-y-1">
                          <div className="flex items-center justify-between text-[10px] text-slate-500 font-medium">
                            <span className="flex items-center gap-1">
                              <Quote className="size-3 text-teal-600" />
                              Verbatim Grounding Excerpt:
                            </span>
                            {ev.excerpt_verified && (
                              <span className="text-emerald-700 font-medium flex items-center gap-1">
                                <CheckCircle2 className="size-3" /> Grounding Verified
                              </span>
                            )}
                          </div>
                          <div className="bg-slate-50/80 border border-slate-200/80 rounded-md p-3 text-[11px] font-serif italic text-slate-800 leading-relaxed">
                            &quot;{ev.supporting_excerpt || "No explicit textual excerpt recorded for this citation."}&quot;
                          </div>
                        </div>

                        {/* Optional Expandable Chunk Context */}
                        {ev.chunk_text && ev.chunk_text !== ev.supporting_excerpt && (
                          <div className="pt-1">
                            <button
                              type="button"
                              onClick={() =>
                                setExpandedChunks((prev) => ({
                                  ...prev,
                                  [ev.evidence_id || String(idx)]: !isChunkExpanded,
                                }))
                              }
                              className="text-[10px] text-blue-600 hover:text-blue-800 font-medium flex items-center gap-1"
                            >
                              {isChunkExpanded ? "Hide full chunk context ▲" : "View full chunk context ▼"}
                            </button>
                            {isChunkExpanded && (
                              <div className="mt-2 bg-slate-900 text-slate-100 p-3 rounded text-[11px] font-mono leading-relaxed max-h-48 overflow-y-auto whitespace-pre-wrap">
                                {ev.chunk_text}
                              </div>
                            )}
                          </div>
                        )}

                        {/* Metadata Footer */}
                        <div className="flex flex-wrap items-center justify-between gap-2 pt-1 text-[10px] text-slate-400 border-t border-slate-100">
                          <div className="flex items-center gap-3">
                            {pageNum !== undefined && <span>Page: {pageNum}</span>}
                            {chunkIdx !== undefined && <span>Chunk: #{chunkIdx}</span>}
                            {ev.author && <span>Author: {ev.author}</span>}
                            <span className="font-mono">ID: {ev.evidence_id ? ev.evidence_id.slice(0, 8) : "N/A"}</span>
                          </div>
                          {ev.source_url && (
                            <a
                              href={ev.source_url}
                              target="_blank"
                              rel="noreferrer"
                              className="text-blue-600 hover:underline flex items-center gap-1"
                            >
                              <ExternalLink className="size-3" /> View Source
                            </a>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

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
              <div className="text-[11px] font-bold uppercase tracking-wider text-slate-700 flex items-center justify-between">
                <span>CONFIDENCE AND UNCERTAINTY</span>
                {activeConfidencePercent !== null ? (
                  <span className="text-xs font-mono font-semibold text-blue-700">
                    {activeConfidencePercent}%
                  </span>
                ) : (
                  <span className="text-xs font-mono font-medium text-slate-400">
                    Unscored
                  </span>
                )}
              </div>

              {/* Progress bar */}
              <div className="w-full bg-slate-200 h-2.5 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all duration-300 ${
                    activeConfidencePercent !== null
                      ? activeConfidencePercent >= 80
                        ? "bg-emerald-600"
                        : activeConfidencePercent >= 50
                        ? "bg-blue-600"
                        : "bg-amber-500"
                      : "bg-slate-300"
                  }`}
                  style={{ width: `${activeConfidencePercent ?? 0}%` }}
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
            {/* Current Human Review Status Banner */}
            <div className="space-y-2">
              {caseStatus === "approved" ? (
                <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-3 text-xs text-emerald-800 space-y-1">
                  <div className="font-bold flex items-center gap-1.5 text-emerald-900">
                    <CheckCircle2 className="size-4 text-emerald-600" />
                    HUMAN VERIFIED (APPROVED)
                  </div>
                  <p className="text-[11px] text-emerald-700 leading-relaxed">
                    This finding is human-verified and eligible for compilation into handover packages.
                  </p>
                </div>
              ) : caseStatus === "rejected" ? (
                <div className="bg-rose-50 border border-rose-200 rounded-lg p-3 text-xs text-rose-800 space-y-1">
                  <div className="font-bold flex items-center gap-1.5 text-rose-900">
                    <XCircle className="size-4 text-rose-600" />
                    REJECTED FINDING
                  </div>
                  <p className="text-[11px] text-rose-700 leading-relaxed">
                    This finding was rejected during review and is excluded from handover packages.
                  </p>
                </div>
              ) : caseStatus === "unresolved" ? (
                <div className="bg-purple-50 border border-purple-200 rounded-lg p-3 text-xs text-purple-800 space-y-1">
                  <div className="font-bold flex items-center gap-1.5 text-purple-900">
                    <HelpCircle className="size-4 text-purple-600" />
                    MARKED UNRESOLVED
                  </div>
                  <p className="text-[11px] text-purple-700 leading-relaxed">
                    Flagged as unresolved pending further consensus or clarification.
                  </p>
                </div>
              ) : (
                <div className="bg-amber-50/70 border border-amber-200 rounded-lg p-3 text-xs text-amber-800 space-y-1">
                  <div className="font-bold flex items-center gap-1.5 text-amber-900">
                    <AlertTriangle className="size-4 text-amber-600" />
                    AWAITING HUMAN REVIEW
                  </div>
                  <p className="text-[11px] text-amber-700 leading-relaxed">
                    Candidate fact extracted by AI. Verification requires explicit human reviewer decision.
                  </p>
                </div>
              )}

              {/* Action Buttons */}
              <div className="space-y-2 pt-1">
                {/* Approve Button */}
                <button
                  onClick={handleApprove}
                  disabled={actionLoading || !caseDetail}
                  className="w-full py-2.5 px-4 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white font-semibold text-xs tracking-wide shadow-sm flex items-center justify-center gap-2 transition disabled:opacity-50"
                >
                  <CheckCircle2 className="size-4" />
                  {caseStatus === "approved" ? "Re-Approve Finding" : "Approve Finding"}
                </button>

                {/* Reject Button */}
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
                  {isRequestingContext ? "Close Inquiry Form" : "Request Additional Context"}
                </button>

                {/* Mark Unresolved Button */}
                <button
                  onClick={handleMarkUnresolved}
                  disabled={actionLoading || !caseDetail}
                  className="w-full py-2 px-4 rounded-lg border border-slate-300 hover:border-purple-300 hover:bg-purple-50 hover:text-purple-800 text-slate-700 font-medium text-xs flex items-center justify-center gap-2 transition disabled:opacity-50"
                >
                  <HelpCircle className="size-3.5 text-purple-500" />
                  Mark Unresolved
                </button>
              </div>
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
                  onClick={handleSendContextRequest}
                  disabled={actionLoading || !contextQuestion.trim()}
                  className="px-3 py-1 bg-slate-800 hover:bg-slate-900 text-white rounded text-[11px] font-medium transition flex items-center gap-1.5 disabled:opacity-50"
                >
                  <Send className="size-3" /> Send Inquiry
                </button>
              </div>
            )}

            {/* REVIEWER NOTE TEXTAREA */}
            <div className="pt-2 border-t border-slate-100 flex-1 flex flex-col">
              <label className="text-[11px] font-bold uppercase tracking-wider text-slate-600 block mb-1.5">
                REVIEWER NOTE &amp; RATIONALE
              </label>
              <textarea
                rows={4}
                value={reviewerNote}
                onChange={(e) => setReviewerNote(e.target.value)}
                placeholder="Enter human rationale, evidence verification comments, or reason for status update..."
                className="w-full flex-1 min-h-[85px] bg-slate-50 border border-slate-200 rounded-lg p-2.5 text-xs text-slate-800 placeholder-slate-400 focus:bg-white focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>

            {/* Verification Audit Events */}
            <div className="pt-2 border-t border-slate-100">
              <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500 block mb-1.5">
                Audit Review Log ({caseDetail?.review_events?.length || 0})
              </span>
              {caseDetail?.review_events && caseDetail.review_events.length > 0 ? (
                <div className="space-y-1.5 max-h-36 overflow-y-auto text-[11px]">
                  {caseDetail.review_events.map((evt) => {
                    const actionLabel = (evt.action || evt.event_type || "ACTION").toUpperCase();
                    const isApprove = actionLabel.includes("APPROV");
                    const isReject = actionLabel.includes("REJECT");
                    const isUnresolved = actionLabel.includes("UNRESOLV");

                    return (
                      <div
                        key={evt.id}
                        className="bg-slate-50 border border-slate-200/80 p-2 rounded text-slate-700 space-y-1"
                      >
                        <div className="flex items-center justify-between text-[10px]">
                          <span
                            className={`font-bold px-1.5 py-0.5 rounded ${
                              isApprove
                                ? "bg-emerald-100 text-emerald-800"
                                : isReject
                                ? "bg-rose-100 text-rose-800"
                                : isUnresolved
                                ? "bg-purple-100 text-purple-800"
                                : "bg-blue-100 text-blue-800"
                            }`}
                          >
                            {actionLabel}
                          </span>
                          <span className="text-slate-400 font-mono">
                            {new Date(evt.created_at).toLocaleString([], {
                              month: "short",
                              day: "numeric",
                              hour: "2-digit",
                              minute: "2-digit",
                            })}
                          </span>
                        </div>
                        {(evt.review_notes || evt.notes) && (
                          <div className="text-[11px] text-slate-600 italic bg-white p-1.5 rounded border border-slate-100">
                            &quot;{evt.review_notes || evt.notes}&quot;
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="text-[11px] text-slate-400 italic bg-slate-50 border border-dashed border-slate-200 p-2.5 rounded text-center">
                  No previous human review actions recorded. Ready for initial evaluation.
                </div>
              )}
            </div>
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
