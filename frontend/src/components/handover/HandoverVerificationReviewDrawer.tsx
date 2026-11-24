"use client";

import React, { useState, useEffect, useCallback, useMemo } from "react";
import {
  X,
  ShieldCheck,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Clock,
  Sparkles,
  FileText,
  Search,
  Filter,
  ArrowRight,
  HelpCircle,
  ExternalLink,
  Lock,
  Edit3,
  MessageSquare,
  Layers,
  ChevronRight,
  GitCompare,
  User as UserIcon,
  RotateCcw,
} from "lucide-react";
import {
  Badge,
  Button,
  Card,
  Modal,
  Tooltip,
  cn,
} from "../figma-ui/index";
import {
  verificationApi,
  type VerificationQueueItem,
  type VerificationCaseDetail,
  type EvidenceReferenceDetail,
  type VerificationStatus,
} from "../../lib/verificationApi";
import type { ProjectMember, User } from "../../lib/types";
import { FormattedMarkdown } from "../figma-ui/FormattedMarkdown";

interface HandoverVerificationReviewDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  projectId: string;
  initialDomain?: string;
  canReview: boolean;
  members: ProjectMember[];
  currentUser?: User | null;
  onDataChanged: () => void;
}

const DOMAIN_OPTIONS: { id: string; label: string }[] = [
  { id: "all", label: "All Domains" },
  { id: "decisions_rationale", label: "Decisions & Rationale" },
  { id: "technical_architecture", label: "Technical & Architecture" },
  { id: "work_progress", label: "Tasks & Work" },
  { id: "responsibilities_ownership", label: "Ownership & Roles" },
  { id: "dependencies_relationships", label: "Dependencies" },
  { id: "bugs_blockers_risks", label: "Bugs, Blockers & Risks" },
  { id: "operational_historical", label: "Operational Procedures" },
  { id: "project_overview_context", label: "Project Overview" },
];

const STATUS_OPTIONS: { id: string; label: string }[] = [
  { id: "all", label: "All Statuses" },
  { id: "pending_review", label: "Pending Review" },
  { id: "candidate", label: "Candidate" },
  { id: "conflicted", label: "Conflicted" },
  { id: "unresolved", label: "Unresolved" },
  { id: "verified", label: "Verified" },
  { id: "rejected", label: "Rejected" },
];

export function HandoverVerificationReviewDrawer({
  isOpen,
  onClose,
  projectId,
  initialDomain = "all",
  canReview,
  members,
  currentUser,
  onDataChanged,
}: HandoverVerificationReviewDrawerProps) {
  // Filter states
  const [selectedDomain, setSelectedDomain] = useState<string>(initialDomain);
  const [selectedStatus, setSelectedStatus] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState<string>("");

  // Data states
  const [queueItems, setQueueItems] = useState<VerificationQueueItem[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [isLoadingQueue, setIsLoadingQueue] = useState<boolean>(true);
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);
  const [caseDetail, setCaseDetail] = useState<VerificationCaseDetail | null>(null);
  const [isLoadingDetail, setIsLoadingDetail] = useState<boolean>(false);

  // Action states
  const [isSubmittingAction, setIsSubmittingAction] = useState<boolean>(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  // Modals
  const [showApproveModal, setShowApproveModal] = useState<boolean>(false);
  const [approveNote, setApproveNote] = useState<string>("");
  const [approveReason, setApproveReason] = useState<string>("Evidence fully verified by reviewer.");

  const [showRejectModal, setShowRejectModal] = useState<boolean>(false);
  const [rejectReason, setRejectReason] = useState<string>("");
  const [rejectNote, setRejectNote] = useState<string>("");

  const [showEditModal, setShowEditModal] = useState<boolean>(false);
  const [editClaimText, setEditClaimText] = useState<string>("");
  const [editReasonText, setEditReasonText] = useState<string>("");

  const [showContextModal, setShowContextModal] = useState<boolean>(false);
  const [contextRecipientId, setContextRecipientId] = useState<string>("");
  const [contextQuestion, setContextQuestion] = useState<string>("");

  // Sync initial domain prop
  useEffect(() => {
    if (initialDomain) {
      setSelectedDomain(initialDomain);
    }
  }, [initialDomain]);

  // Fetch queue items from real backend
  const fetchQueue = useCallback(async () => {
    if (!projectId || !isOpen) return;
    setIsLoadingQueue(true);
    setActionError(null);
    try {
      const filters = {
        domain: selectedDomain === "all" ? undefined : selectedDomain,
        status: selectedStatus === "all" ? undefined : selectedStatus,
        search: searchQuery.trim() || undefined,
      };
      const res = await verificationApi.getQueue(projectId, filters);
      setQueueItems(res.items || []);
      setTotalCount(res.total || 0);

      // Auto-select first item if none selected or previous no longer in list
      if (res.items?.length > 0) {
        if (!selectedCaseId || !res.items.some((i) => i.id === selectedCaseId)) {
          setSelectedCaseId(res.items[0]?.id ?? null);
        }
      } else {
        setSelectedCaseId(null);
        setCaseDetail(null);
      }
    } catch (err) {
      console.error("Failed to load verification queue:", err);
      setActionError(err instanceof Error ? err.message : "Unable to load verification queue.");
      setQueueItems([]);
    } finally {
      setIsLoadingQueue(false);
    }
  }, [projectId, isOpen, selectedDomain, selectedStatus, searchQuery, selectedCaseId]);

  useEffect(() => {
    if (isOpen) {
      fetchQueue();
    }
  }, [isOpen, selectedDomain, selectedStatus, searchQuery, fetchQueue]);

  // Fetch case detail when selectedCaseId changes
  useEffect(() => {
    if (!projectId || !selectedCaseId || !isOpen) {
      setCaseDetail(null);
      return;
    }
    let cancelled = false;
    setIsLoadingDetail(true);
    setActionError(null);
    setActionSuccess(null);

    verificationApi
      .getCaseDetail(projectId, selectedCaseId)
      .then((detail) => {
        if (!cancelled) {
          setCaseDetail(detail);
          setEditClaimText(detail.current_claim || "");
        }
      })
      .catch((err) => {
        if (!cancelled) {
          console.error("Failed to load case detail:", err);
          setActionError(err instanceof Error ? err.message : "Failed to load finding details.");
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoadingDetail(false);
      });

    return () => {
      cancelled = true;
    };
  }, [projectId, selectedCaseId, isOpen]);

  // Handle Approve action
  const handleApprove = async () => {
    if (!caseDetail || isSubmittingAction) return;
    setIsSubmittingAction(true);
    setActionError(null);
    try {
      const updated = await verificationApi.approveCase(projectId, caseDetail.id, {
        decision_reason: approveReason.trim() || "Approved by project reviewer.",
        reviewer_note: approveNote.trim() || undefined,
      });
      setCaseDetail(updated);
      setActionSuccess("Finding successfully approved and verified for handover.");
      setShowApproveModal(false);
      setApproveNote("");
      onDataChanged();
      await fetchQueue();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to approve finding.");
    } finally {
      setIsSubmittingAction(false);
    }
  };

  // Handle Reject action
  const handleReject = async () => {
    if (!caseDetail || isSubmittingAction) return;
    if (!rejectReason.trim()) {
      setActionError("Please provide a rejection reason for the audit record.");
      return;
    }
    setIsSubmittingAction(true);
    setActionError(null);
    try {
      const updated = await verificationApi.rejectCase(projectId, caseDetail.id, {
        decision_reason: rejectReason.trim(),
        reviewer_note: rejectNote.trim() || undefined,
      });
      setCaseDetail(updated);
      setActionSuccess("Finding rejected and excluded from handover snapshot.");
      setShowRejectModal(false);
      setRejectReason("");
      setRejectNote("");
      onDataChanged();
      await fetchQueue();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to reject finding.");
    } finally {
      setIsSubmittingAction(false);
    }
  };

  // Handle Edit Claim action
  const handleEditClaim = async () => {
    if (!caseDetail || isSubmittingAction) return;
    if (!editClaimText.trim() || !editReasonText.trim()) {
      setActionError("Please provide both the corrected statement and an edit reason.");
      return;
    }
    setIsSubmittingAction(true);
    setActionError(null);
    try {
      const updated = await verificationApi.editFinding(projectId, caseDetail.id, {
        current_claim: editClaimText.trim(),
        edit_reason: editReasonText.trim(),
      });
      setCaseDetail(updated);
      setActionSuccess("Finding statement corrected. An immutable revision was created.");
      setShowEditModal(false);
      setEditReasonText("");
      onDataChanged();
      await fetchQueue();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to edit finding statement.");
    } finally {
      setIsSubmittingAction(false);
    }
  };

  // Handle Request Clarification action
  const handleRequestContext = async () => {
    if (!caseDetail || isSubmittingAction) return;
    if (!contextRecipientId || !contextQuestion.trim()) {
      setActionError("Please select a team member and enter a clarification question.");
      return;
    }
    setIsSubmittingAction(true);
    setActionError(null);
    try {
      const updated = await verificationApi.requestContext(projectId, caseDetail.id, {
        requested_from_user_id: contextRecipientId,
        question: contextQuestion.trim(),
      });
      setCaseDetail(updated);
      setActionSuccess("Clarification request sent to team member.");
      setShowContextModal(false);
      setContextQuestion("");
      onDataChanged();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to send clarification request.");
    } finally {
      setIsSubmittingAction(false);
    }
  };

  // Handle Mark Unresolved action
  const handleMarkUnresolved = async () => {
    if (!caseDetail || isSubmittingAction) return;
    setIsSubmittingAction(true);
    setActionError(null);
    try {
      const updated = await verificationApi.markUnresolved(projectId, caseDetail.id, {
        decision_reason: "Marked unresolved pending further cross-source verification.",
      });
      setCaseDetail(updated);
      setActionSuccess("Case marked as unresolved.");
      onDataChanged();
      await fetchQueue();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to mark as unresolved.");
    } finally {
      setIsSubmittingAction(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-hidden bg-navy/40 backdrop-blur-xs flex justify-end animate-in fade-in duration-200">
      <div className="flex h-full w-full max-w-6xl flex-col bg-white shadow-2xl border-l border-line transition-transform duration-300">
        {/* Drawer Header */}
        <div className="flex items-center justify-between border-b border-line px-5 py-4 bg-slate-50/80">
          <div className="flex items-center gap-3">
            <span className="flex size-8 items-center justify-center rounded-lg bg-teal-50 text-teal-700 border border-teal-200">
              <ShieldCheck className="size-5" />
            </span>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold text-navy">
                  Knowledge Verification Queue & Review
                </h2>
                <Badge tone="indigo">
                  {totalCount} {totalCount === 1 ? "finding" : "findings"}
                </Badge>
              </div>
              <p className="text-xs text-muted">
                Inspect original citations, evaluate AI interpretations, and record human verification decisions.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close review drawer"
            className="rounded-lg p-2 text-slate-400 hover:bg-slate-200 hover:text-navy transition"
          >
            <X className="size-5" />
          </button>
        </div>

        {/* Filters Toolbar */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line/80 bg-white px-5 py-2.5 text-xs">
          <div className="flex flex-wrap items-center gap-2.5">
            {/* Domain Filter */}
            <label className="flex items-center gap-1.5 font-medium text-slate-600">
              <span>Domain:</span>
              <select
                aria-label="Filter by knowledge domain"
                value={selectedDomain}
                onChange={(e) => setSelectedDomain(e.target.value)}
                className="rounded-lg border border-line bg-white px-2.5 py-1 text-xs font-semibold text-navy focus:border-brand focus:outline-none"
              >
                {DOMAIN_OPTIONS.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.label}
                  </option>
                ))}
              </select>
            </label>

            {/* Status Filter */}
            <label className="flex items-center gap-1.5 font-medium text-slate-600">
              <span>Status:</span>
              <select
                aria-label="Filter by verification status"
                value={selectedStatus}
                onChange={(e) => setSelectedStatus(e.target.value)}
                className="rounded-lg border border-line bg-white px-2.5 py-1 text-xs font-semibold text-navy focus:border-brand focus:outline-none"
              >
                {STATUS_OPTIONS.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.label}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {/* Search Input */}
          <div className="relative w-full sm:w-64">
            <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              placeholder="Search findings, claims, keywords…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full rounded-lg border border-line bg-slate-50/60 pl-8 pr-3 py-1 text-xs text-navy focus:bg-white focus:border-brand focus:outline-none"
            />
          </div>
        </div>

        {/* Notifications & Alerts */}
        {actionError && (
          <div className="bg-red-50 border-b border-red-200 px-5 py-2 text-xs text-red-800 flex items-center justify-between">
            <span>{actionError}</span>
            <button onClick={() => setActionError(null)} className="font-bold ml-2">×</button>
          </div>
        )}
        {actionSuccess && (
          <div className="bg-teal-50 border-b border-teal-200 px-5 py-2 text-xs text-teal-800 flex items-center justify-between">
            <span className="flex items-center gap-1.5">
              <CheckCircle2 className="size-3.5 text-teal-600" />
              {actionSuccess}
            </span>
            <button onClick={() => setActionSuccess(null)} className="font-bold ml-2">×</button>
          </div>
        )}

        {/* Main 2-Column Split Workspace */}
        <div className="flex-1 min-h-0 grid grid-cols-1 md:grid-cols-12 divide-y md:divide-y-0 md:divide-x divide-line overflow-hidden">
          {/* Left Panel: Findings Queue (col-span-5) */}
          <div className="md:col-span-5 flex flex-col min-h-0 bg-slate-50/30 overflow-y-auto">
            {isLoadingQueue ? (
              <div className="p-4 space-y-3">
                {[1, 2, 3, 4, 5].map((i) => (
                  <div key={i} className="h-24 rounded-xl bg-slate-100 animate-pulse border border-line/60" />
                ))}
              </div>
            ) : queueItems.length === 0 ? (
              <div className="p-8 text-center text-muted">
                <ShieldCheck className="mx-auto size-8 text-slate-300 mb-2" />
                <p className="text-sm font-semibold text-navy">No findings match this filter</p>
                <p className="text-xs text-muted mt-1">
                  Adjust domain or status filters to view other candidate findings.
                </p>
              </div>
            ) : (
              <div className="divide-y divide-line/60">
                {queueItems.map((item) => {
                  const isSelected = item.id === selectedCaseId;
                  const isVerified = item.case_status === "verified";
                  const isPending =
                    item.case_status === "pending_review" || item.case_status === "candidate";
                  const isConflicted = item.case_status === "conflicted";

                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => setSelectedCaseId(item.id)}
                      className={cn(
                        "w-full text-left p-3.5 transition-colors relative flex flex-col gap-1.5",
                        isSelected
                          ? "bg-white border-l-4 border-l-brand shadow-xs"
                          : "hover:bg-slate-100/60"
                      )}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <span className="text-[13px] font-semibold text-navy line-clamp-1">
                          {item.title}
                        </span>
                        <span
                          className={cn(
                            "inline-flex items-center px-2 py-0.5 rounded-full text-[10.5px] font-semibold shrink-0",
                            isVerified
                              ? "bg-teal-50 text-teal-800 border border-teal-200"
                              : isPending
                              ? "bg-amber-50 text-amber-800 border border-amber-200"
                              : isConflicted
                              ? "bg-red-50 text-red-800 border border-red-200"
                              : "bg-slate-100 text-slate-600 border border-slate-200"
                          )}
                        >
                          {item.case_status.replace(/_/g, " ")}
                        </span>
                      </div>

                      <p className="text-xs text-slate-600 line-clamp-2 leading-relaxed">
                        {item.current_claim || item.original_ai_claim}
                      </p>

                      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 pt-1 text-[11px] text-muted">
                        <span className="capitalize">{item.domain.replace(/_/g, " ")}</span>
                        {item.source_provider && (
                          <span className="font-mono text-slate-500">
                            via {item.source_provider}
                          </span>
                        )}
                        <span>{item.evidence_count} sources</span>
                        {typeof item.model_confidence === "number" ? (
                          <span className="text-indigo-700 font-medium">
                            {Math.round(item.model_confidence * 100)}% conf
                          </span>
                        ) : (
                          <span className="text-slate-400 font-medium text-[10.5px]">
                            Conf unavailable
                          </span>
                        )}
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          {/* Right Panel: Focused Finding Review (col-span-7) */}
          <div className="md:col-span-7 flex flex-col min-h-0 bg-white overflow-y-auto p-5 sm:p-6 space-y-5">
            {isLoadingDetail ? (
              <div className="space-y-4">
                <div className="h-6 w-3/4 rounded bg-slate-100 animate-pulse" />
                <div className="h-20 rounded-xl bg-slate-100 animate-pulse" />
                <div className="h-32 rounded-xl bg-slate-100 animate-pulse" />
              </div>
            ) : !caseDetail ? (
              <div className="flex h-full flex-col items-center justify-center text-center p-8 text-muted">
                <FileText className="size-10 text-slate-300 mb-2" />
                <p className="text-sm font-semibold text-navy">Select a finding to inspect</p>
                <p className="text-xs text-muted max-w-sm mt-1">
                  Choose any knowledge candidate from the left queue to review its original source citations, AI synthesis, and verification decisions.
                </p>
              </div>
            ) : (
              <>
                {/* A. Finding Header & Metadata */}
                <div>
                  <div className="flex flex-wrap items-center justify-between gap-2 pb-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone="indigo">{(caseDetail.domain || "").replace(/_/g, " ")}</Badge>
                      <Badge
                        tone={
                          caseDetail.case_status === "verified"
                            ? "green"
                            : caseDetail.case_status === "conflicted"
                            ? "red"
                            : "amber"
                        }
                      >
                        {caseDetail.case_status.replace(/_/g, " ")}
                      </Badge>
                      <span className="text-xs text-muted">Priority: {caseDetail.priority}</span>
                    </div>
                    {caseDetail.handover_eligible ? (
                      <Badge tone="green" icon={ShieldCheck}>
                        Handover Eligible
                      </Badge>
                    ) : (
                      <Badge tone="gray">Pending Approval</Badge>
                    )}
                  </div>
                  <h3 className="text-lg font-bold text-navy">{caseDetail.title}</h3>
                  {caseDetail.person_name && (
                    <p className="text-xs text-muted mt-0.5">
                      Attributed owner: <strong className="text-navy">{caseDetail.person_name}</strong>
                    </p>
                  )}
                </div>

                {/* Extracted Claim Statement */}
                <div className="rounded-xl border border-line bg-slate-50/70 p-4">
                  <div className="flex items-center justify-between gap-2 mb-1.5">
                    <span className="text-xs font-semibold uppercase tracking-wider text-muted">
                      Knowledge Claim Statement
                    </span>
                    {canReview && (
                      <Button
                        size="sm"
                        variant="ghost"
                        icon={Edit3}
                        onClick={() => setShowEditModal(true)}
                        className="h-6 text-xs text-brand"
                      >
                        Edit Statement
                      </Button>
                    )}
                  </div>
                  <p className="text-sm leading-relaxed text-slate-800 font-medium">
                    {caseDetail.current_claim}
                  </p>
                </div>

                {/* B. Source Evidence Provenance */}
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <FileText className="size-4 text-brand" />
                      <h4 className="text-sm font-bold text-navy">
                        Cited Source Evidence ({caseDetail.evidence_references?.length || 0})
                      </h4>
                    </div>
                    {caseDetail.restricted_evidence_count > 0 && (
                      <Badge tone="amber" icon={Lock}>
                        {caseDetail.restricted_evidence_count} Restricted
                      </Badge>
                    )}
                  </div>

                  {(caseDetail.evidence_references || []).length === 0 ? (
                    <div className="rounded-xl border border-dashed border-line p-4 text-center text-xs text-muted">
                      No direct evidence records linked to this candidate finding.
                    </div>
                  ) : (
                    <div className="space-y-2.5">
                      {(caseDetail.evidence_references || []).map((ev, idx) => (
                        <div
                          key={ev.id || idx}
                          className="rounded-xl border border-line bg-white p-3.5 space-y-2 shadow-2xs"
                        >
                          <div className="flex items-start justify-between gap-2 text-xs">
                            <div className="flex items-center gap-2">
                              <span className="font-mono text-[11px] font-semibold text-slate-600 px-1.5 py-0.5 rounded bg-slate-100">
                                {ev.source_provider}
                              </span>
                              <span className="font-semibold text-navy">{ev.original_title || ev.source_name}</span>
                            </div>
                            <span className="text-[11px] text-muted">
                              {ev.timestamp ? new Date(ev.timestamp).toLocaleDateString() : "Undated"}
                            </span>
                          </div>

                          {ev.excerpt ? (
                            <blockquote className="rounded-lg bg-slate-50 p-2.5 text-xs text-slate-700 italic border-l-2 border-brand/60 leading-relaxed">
                              "{ev.excerpt}"
                            </blockquote>
                          ) : (
                            <div className="flex items-center gap-1.5 text-xs text-amber-700 bg-amber-50/60 p-2 rounded-lg">
                              <Lock className="size-3 shrink-0" />
                              <span>
                                Excerpt text restricted by access permissions ({ev.acl_scope}).
                              </span>
                            </div>
                          )}

                          <div className="flex items-center justify-between text-[11px] text-muted pt-1 border-t border-line/40">
                            <span>Author: {ev.author || "Unknown contributor"}</span>
                            {!ev.acl_restricted && ev.original_source_url ? (
                              <a
                                href={ev.original_source_url}
                                target="_blank"
                                rel="noreferrer"
                                className="inline-flex items-center gap-1 text-brand hover:underline font-medium"
                              >
                                View Source <ExternalLink className="size-2.5" />
                              </a>
                            ) : ev.acl_restricted ? (
                              <span className="inline-flex items-center gap-1 text-amber-700 font-medium text-[10.5px]">
                                <Lock className="size-2.5" /> Source Access Restricted
                              </span>
                            ) : null}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* C. AI Interpretation & Uncertainty Banner */}
                <div className="rounded-xl border border-indigo-200/70 bg-indigo-50/30 p-3.5 space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5 text-indigo-900 font-semibold text-xs">
                      <Sparkles className="size-4 text-indigo-600" />
                      <span>AI Extraction & Model Assessment</span>
                      {(caseDetail.machine_assessment?.ai_model || (caseDetail as any).ai_model) && (
                        <span className="font-mono text-[10.5px] px-1.5 py-0.5 rounded bg-indigo-100 text-indigo-800 font-semibold">
                          {String(caseDetail.machine_assessment?.ai_model || (caseDetail as any).ai_model)}
                        </span>
                      )}
                    </div>
                    {typeof caseDetail.model_confidence === "number" ? (
                      <span className="text-xs font-bold text-indigo-800">
                        {Math.round(caseDetail.model_confidence * 100)}% Confidence
                      </span>
                    ) : (
                      <span className="text-[11px] font-medium text-slate-500">
                        Confidence unavailable
                      </span>
                    )}
                  </div>
                  {caseDetail.uncertainty_note && (
                    <p className="text-xs text-indigo-950/80 leading-relaxed bg-white/60 p-2 rounded-lg border border-indigo-100">
                      <strong>Uncertainty Note:</strong> {caseDetail.uncertainty_note}
                    </p>
                  )}
                  {caseDetail.original_ai_claim !== caseDetail.current_claim && (
                    <div className="text-[11.5px] text-slate-600 bg-white/60 p-2 rounded-lg border border-indigo-100">
                      <span className="block text-[10.5px] font-semibold uppercase text-muted">
                        Original AI Extraction:
                      </span>
                      <p className="italic">{caseDetail.original_ai_claim}</p>
                    </div>
                  )}
                </div>

                {/* D. Conflicts Comparison (if present) */}
                {caseDetail.conflicts && caseDetail.conflicts.length > 0 && (
                  <div className="rounded-xl border border-red-200 bg-red-50/20 p-4 space-y-3">
                    <div className="flex items-center gap-2 text-red-900 font-bold text-xs uppercase tracking-wider">
                      <GitCompare className="size-4 text-red-600" />
                      <span>Cross-Source Contradictions Detected ({caseDetail.conflicts.length})</span>
                    </div>
                    {caseDetail.conflicts.map((conf, i) => (
                      <div key={conf.id || i} className="rounded-lg bg-white p-3 border border-red-100 space-y-2 text-xs">
                        <p className="font-semibold text-navy">{conf.explanation}</p>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1">
                          <div className="bg-slate-50 p-2 rounded border border-line/60">
                            <span className="block text-[10px] font-bold text-muted uppercase">Claim A</span>
                            <p className="text-slate-800 mt-0.5">{conf.side_a?.claim_text || "Source A statement"}</p>
                            <span className="text-[10px] text-slate-500 mt-1 block">
                              Source: {conf.side_a?.original_title} ({conf.side_a?.source_provider})
                            </span>
                          </div>
                          <div className="bg-slate-50 p-2 rounded border border-line/60">
                            <span className="block text-[10px] font-bold text-muted uppercase">Claim B</span>
                            <p className="text-slate-800 mt-0.5">{conf.side_b?.claim_text || "Source B statement"}</p>
                            <span className="text-[10px] text-slate-500 mt-1 block">
                              Source: {conf.side_b?.original_title} ({conf.side_b?.source_provider})
                            </span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {/* E. Review Actions Panel */}
                <div className="rounded-xl border border-line bg-slate-50 p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <h4 className="text-xs font-bold uppercase tracking-wider text-navy">
                      Reviewer Decision Panel
                    </h4>
                    <span className="text-[11px] text-muted">
                      {canReview ? "Authorized Reviewer" : "View-only Mode"}
                    </span>
                  </div>

                  {canReview ? (
                    <div className="flex flex-wrap items-center gap-2">
                      {caseDetail.case_status !== "verified" && (
                        <Button
                          icon={CheckCircle2}
                          disabled={isSubmittingAction}
                          onClick={() => setShowApproveModal(true)}
                          className="bg-ok hover:bg-ok/90 text-white"
                        >
                          Approve / Verify Finding
                        </Button>
                      )}
                      {caseDetail.case_status !== "rejected" && (
                        <Button
                          variant="secondary"
                          icon={XCircle}
                          disabled={isSubmittingAction}
                          onClick={() => setShowRejectModal(true)}
                          className="text-bad border-bad/30 hover:bg-red-50"
                        >
                          Reject Finding
                        </Button>
                      )}
                      <Button
                        variant="secondary"
                        icon={Edit3}
                        disabled={isSubmittingAction}
                        onClick={() => setShowEditModal(true)}
                      >
                        Edit Statement
                      </Button>
                      <Button
                        variant="secondary"
                        icon={MessageSquare}
                        disabled={isSubmittingAction}
                        onClick={() => setShowContextModal(true)}
                      >
                        Request Clarification
                      </Button>
                      <Button
                        variant="ghost"
                        icon={RotateCcw}
                        disabled={isSubmittingAction}
                        onClick={handleMarkUnresolved}
                      >
                        Mark Unresolved
                      </Button>
                    </div>
                  ) : (
                    <p className="text-xs text-muted italic">
                      You are viewing this finding in read-only mode. Only project managers or assigned reviewers can record verification actions.
                    </p>
                  )}
                </div>

                {/* F. Immutable Review Audit History */}
                {caseDetail.review_events && caseDetail.review_events.length > 0 && (
                  <div className="border-t border-line pt-4 space-y-2">
                    <h4 className="text-xs font-bold uppercase tracking-wider text-muted">
                      Verification Audit Trail ({caseDetail.review_events.length})
                    </h4>
                    <div className="space-y-1.5 text-xs">
                      {caseDetail.review_events.map((rev) => (
                        <div
                          key={rev.id}
                          className="flex items-center justify-between rounded-lg bg-slate-50/60 p-2 border border-line/40 text-[11.5px]"
                        >
                          <span className="font-semibold text-navy">
                            {rev.reviewer_name || "Reviewer"} ·{" "}
                            <span className="uppercase text-slate-600 font-mono text-[10.5px]">
                              {rev.action}
                            </span>
                            {rev.decision_reason && ` (${rev.decision_reason})`}
                          </span>
                          <span className="text-muted font-mono text-[10.5px]">
                            {new Date(rev.created_at).toLocaleDateString()}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </div>

        {/* ── Modal: Approve Finding ────────────────────────────────────── */}
        <Modal
          open={showApproveModal}
          onClose={() => setShowApproveModal(false)}
          title="Approve & Verify Finding"
          subtitle="Human approval certifies this finding as verified and eligible for inclusion in handover packages."
          footer={
            <div className="flex justify-end gap-2 w-full">
              <Button variant="secondary" onClick={() => setShowApproveModal(false)}>
                Cancel
              </Button>
              <Button
                icon={CheckCircle2}
                disabled={isSubmittingAction}
                onClick={handleApprove}
                className="bg-ok hover:bg-ok/90 text-white"
              >
                {isSubmittingAction ? "Verifying…" : "Confirm Approval"}
              </Button>
            </div>
          }
        >
          <div className="space-y-3 py-2 text-xs">
            <div>
              <label className="font-semibold text-navy block mb-1">Decision Reason:</label>
              <input
                type="text"
                value={approveReason}
                onChange={(e) => setApproveReason(e.target.value)}
                className="w-full rounded-lg border border-line p-2 text-xs text-navy focus:border-brand focus:outline-none"
              />
            </div>
            <div>
              <label className="font-semibold text-navy block mb-1">Optional Reviewer Notes:</label>
              <textarea
                rows={3}
                value={approveNote}
                onChange={(e) => setApproveNote(e.target.value)}
                placeholder="Add context or citations confirming verification…"
                className="w-full rounded-lg border border-line p-2 text-xs text-navy focus:border-brand focus:outline-none"
              />
            </div>
          </div>
        </Modal>

        {/* ── Modal: Reject Finding ─────────────────────────────────────── */}
        <Modal
          open={showRejectModal}
          onClose={() => setShowRejectModal(false)}
          title="Reject Finding"
          subtitle="Rejection removes this finding from handover snapshots and records the rationale in the immutable audit log."
          footer={
            <div className="flex justify-end gap-2 w-full">
              <Button variant="secondary" onClick={() => setShowRejectModal(false)}>
                Cancel
              </Button>
              <Button
                variant="secondary"
                disabled={isSubmittingAction || !rejectReason.trim()}
                onClick={handleReject}
                className="text-bad border-bad/30 hover:bg-red-50"
              >
                {isSubmittingAction ? "Rejecting…" : "Confirm Rejection"}
              </Button>
            </div>
          }
        >
          <div className="space-y-3 py-2 text-xs">
            <div>
              <label className="font-semibold text-navy block mb-1">
                Rejection Reason <span className="text-bad">*</span>:
              </label>
              <input
                type="text"
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                placeholder="e.g. Disproven by latest architecture decisions, inaccurate claim…"
                className="w-full rounded-lg border border-line p-2 text-xs text-navy focus:border-brand focus:outline-none"
              />
            </div>
            <div>
              <label className="font-semibold text-navy block mb-1">Additional Notes:</label>
              <textarea
                rows={3}
                value={rejectNote}
                onChange={(e) => setRejectNote(e.target.value)}
                placeholder="Explanation of why this candidate finding was rejected…"
                className="w-full rounded-lg border border-line p-2 text-xs text-navy focus:border-brand focus:outline-none"
              />
            </div>
          </div>
        </Modal>

        {/* ── Modal: Edit Finding Statement ─────────────────────────────── */}
        <Modal
          open={showEditModal}
          onClose={() => setShowEditModal(false)}
          title="Edit Finding Statement"
          subtitle="Modifying the claim creates an immutable human revision. The original AI extraction is permanently preserved."
          footer={
            <div className="flex justify-end gap-2 w-full">
              <Button variant="secondary" onClick={() => setShowEditModal(false)}>
                Cancel
              </Button>
              <Button
                disabled={isSubmittingAction || !editClaimText.trim() || !editReasonText.trim()}
                onClick={handleEditClaim}
              >
                {isSubmittingAction ? "Saving…" : "Save Revision"}
              </Button>
            </div>
          }
        >
          <div className="space-y-3 py-2 text-xs">
            <div>
              <label className="font-semibold text-navy block mb-1">
                Corrected Knowledge Statement <span className="text-bad">*</span>:
              </label>
              <textarea
                rows={4}
                value={editClaimText}
                onChange={(e) => setEditClaimText(e.target.value)}
                className="w-full rounded-lg border border-line p-2 text-xs text-navy focus:border-brand focus:outline-none leading-relaxed"
              />
            </div>
            <div>
              <label className="font-semibold text-navy block mb-1">
                Reason for Edit <span className="text-bad">*</span>:
              </label>
              <input
                type="text"
                value={editReasonText}
                onChange={(e) => setEditReasonText(e.target.value)}
                placeholder="e.g. Clarified scope, updated terminology, corrected parameter…"
                className="w-full rounded-lg border border-line p-2 text-xs text-navy focus:border-brand focus:outline-none"
              />
            </div>
          </div>
        </Modal>

        {/* ── Modal: Request Clarification Context ──────────────────────── */}
        <Modal
          open={showContextModal}
          onClose={() => setShowContextModal(false)}
          title="Request Clarification Context"
          subtitle="Send an attributable query to a team member to clarify missing evidence or resolve ambiguities."
          footer={
            <div className="flex justify-end gap-2 w-full">
              <Button variant="secondary" onClick={() => setShowContextModal(false)}>
                Cancel
              </Button>
              <Button
                disabled={isSubmittingAction || !contextRecipientId || !contextQuestion.trim()}
                onClick={handleRequestContext}
              >
                {isSubmittingAction ? "Sending…" : "Send Clarification Request"}
              </Button>
            </div>
          }
        >
          <div className="space-y-3 py-2 text-xs">
            <div>
              <label className="font-semibold text-navy block mb-1">
                Recipient Team Member <span className="text-bad">*</span>:
              </label>
              <select
                aria-label="Recipient Team Member"
                value={contextRecipientId}
                onChange={(e) => setContextRecipientId(e.target.value)}
                className="w-full rounded-lg border border-line p-2 text-xs text-navy focus:border-brand focus:outline-none"
              >
                <option value="">Select a team member…</option>
                {members.map((m) => (
                  <option key={m.user_id} value={m.user_id}>
                    {m.full_name || m.email} ({m.role_name})
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="font-semibold text-navy block mb-1">
                Clarification Question <span className="text-bad">*</span>:
              </label>
              <textarea
                rows={3}
                value={contextQuestion}
                onChange={(e) => setContextQuestion(e.target.value)}
                placeholder="e.g. Could you confirm if the redis cache fallback was deprecated in Sprint 12?"
                className="w-full rounded-lg border border-line p-2 text-xs text-navy focus:border-brand focus:outline-none"
              />
            </div>
          </div>
        </Modal>
      </div>
    </div>
  );
}
