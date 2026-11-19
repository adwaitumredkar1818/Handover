"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { api, ApiError } from "../../lib/api";
import type {
  VerificationCaseDetail,
  SupportingEvidenceItem,
  ConcurrencyConflictState,
} from "./types";

export interface UseVerificationActionsProps {
  activeProjectId?: string;
  caseDetail: VerificationCaseDetail | null;
  loadWorkspaceData: () => Promise<void>;
  loadCaseDetail: (caseId: string) => Promise<void>;
  addToast: (toast: {
    type: "info" | "success" | "error" | "warning";
    title: string;
    message: string;
  }) => void;
}

export interface UseVerificationActionsReturn {
  reviewerNote: string;
  setReviewerNote: (note: string) => void;
  concurrencyConflict: ConcurrencyConflictState | null;
  setConcurrencyConflict: (conflict: ConcurrencyConflictState | null) => void;
  actionLoading: boolean;
  assessing: boolean;
  isEditModalOpen: boolean;
  setIsEditModalOpen: (open: boolean) => void;
  isRequestContextModalOpen: boolean;
  setIsRequestContextModalOpen: (open: boolean) => void;
  selectedChunkEvidence: SupportingEvidenceItem | null;
  setSelectedChunkEvidence: (evidence: SupportingEvidenceItem | null) => void;
  handleReloadLatestVersion: () => Promise<void>;
  handleApprove: () => Promise<void>;
  handleReject: () => Promise<void>;
  handleMarkUnresolved: () => Promise<void>;
  handleAssignReviewer: (assigneeUserId: string | null) => Promise<void>;
  handleSaveEdit: (payload: { title: string; summary: string; reason: string }) => Promise<void>;
  handleSendRequestContext: (payload: { targetUserId: string; question: string; informationType: string }) => Promise<void>;
  handleAssessAll: () => Promise<void>;
}

export function useVerificationActions({
  activeProjectId,
  caseDetail,
  loadWorkspaceData,
  loadCaseDetail,
  addToast,
}: UseVerificationActionsProps): UseVerificationActionsReturn {
  // Reviewer Interactions & OCC Concurrency
  const [reviewerNote, setReviewerNote] = useState<string>("");
  const [concurrencyConflict, setConcurrencyConflict] = useState<ConcurrencyConflictState | null>(null);
  const [actionLoading, setActionLoading] = useState<boolean>(false);
  const [assessing, setAssessing] = useState<boolean>(false);

  // Modals & Drawers
  const [isEditModalOpen, setIsEditModalOpen] = useState<boolean>(false);
  const [isRequestContextModalOpen, setIsRequestContextModalOpen] = useState<boolean>(false);
  const [selectedChunkEvidence, setSelectedChunkEvidence] = useState<SupportingEvidenceItem | null>(null);

  // Auto-clear concurrency conflict when switching to a different candidate case
  const prevCaseIdRef = useRef<string | null>(null);
  useEffect(() => {
    if (caseDetail?.id !== prevCaseIdRef.current) {
      prevCaseIdRef.current = caseDetail?.id ?? null;
      setConcurrencyConflict(null);
    }
  }, [caseDetail?.id]);

  // 1. Concurrency 409 Conflict Recovery (Preserves Reviewer Notes)
  const handleReloadLatestVersion = useCallback(async () => {
    if (!activeProjectId || !caseDetail?.id) return;
    try {
      setActionLoading(true);
      await loadCaseDetail(caseDetail.id);
      setConcurrencyConflict(null);
      addToast({
        type: "info",
        title: "Latest Snapshot Loaded",
        message: "Refetched latest case version from server. Your unsaved notes remain preserved.",
      });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to reload latest version";
      addToast({ type: "error", title: "Reload Failed", message: msg });
    } finally {
      setActionLoading(false);
    }
  }, [activeProjectId, caseDetail?.id, loadCaseDetail, addToast]);

  // 2. Action Handlers with OCC Versioning
  const handleApprove = useCallback(async () => {
    if (!activeProjectId || !caseDetail) return;
    try {
      setActionLoading(true);
      await api.verification.approveCase(activeProjectId, caseDetail.id, {
        expected_version: caseDetail.version,
        review_notes: reviewerNote.trim() || undefined,
      });
      addToast({ type: "success", title: "Case Approved", message: "Promoted to Human-Verified status." });
      setReviewerNote("");
      await Promise.all([loadWorkspaceData(), loadCaseDetail(caseDetail.id)]);
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 409) {
        setConcurrencyConflict({
          isConflict: true,
          message: "Another reviewer modified this finding. Click 'Reload Latest' to view changes before re-submitting.",
        });
      } else {
        const msg = err instanceof ApiError ? err.message : (err instanceof Error ? err.message : "Approval failed");
        addToast({ type: "error", title: "Approval Failed", message: msg });
      }
    } finally {
      setActionLoading(false);
    }
  }, [activeProjectId, caseDetail, reviewerNote, loadWorkspaceData, loadCaseDetail, addToast]);

  const handleReject = useCallback(async () => {
    if (!activeProjectId || !caseDetail) return;
    try {
      setActionLoading(true);
      await api.verification.rejectCase(activeProjectId, caseDetail.id, {
        expected_version: caseDetail.version,
        reason: reviewerNote.trim() || "Rejected by reviewer",
        review_notes: reviewerNote.trim() || undefined,
      });
      addToast({ type: "success", title: "Case Rejected", message: "Excluded from downstream handover." });
      setReviewerNote("");
      await Promise.all([loadWorkspaceData(), loadCaseDetail(caseDetail.id)]);
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 409) {
        setConcurrencyConflict({
          isConflict: true,
          message: "Another reviewer modified this finding concurrently. Reload latest snapshot to proceed.",
        });
      } else {
        const msg = err instanceof ApiError ? err.message : (err instanceof Error ? err.message : "Rejection failed");
        addToast({ type: "error", title: "Rejection Failed", message: msg });
      }
    } finally {
      setActionLoading(false);
    }
  }, [activeProjectId, caseDetail, reviewerNote, loadWorkspaceData, loadCaseDetail, addToast]);

  const handleMarkUnresolved = useCallback(async () => {
    if (!activeProjectId || !caseDetail) return;
    try {
      setActionLoading(true);
      await api.verification.markUnresolved(activeProjectId, caseDetail.id, {
        expected_version: caseDetail.version,
        explanation: reviewerNote.trim() || "Unresolved - consensus not established",
      });
      addToast({ type: "success", title: "Marked Unresolved", message: "Flagged for expert adjudication." });
      setReviewerNote("");
      await Promise.all([loadWorkspaceData(), loadCaseDetail(caseDetail.id)]);
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 409) {
        setConcurrencyConflict({ isConflict: true, message: "Concurrent modification detected. Reload latest version." });
      } else {
        const msg = err instanceof ApiError ? err.message : (err instanceof Error ? err.message : "Action failed");
        addToast({ type: "error", title: "Action Failed", message: msg });
      }
    } finally {
      setActionLoading(false);
    }
  }, [activeProjectId, caseDetail, reviewerNote, loadWorkspaceData, loadCaseDetail, addToast]);

  const handleAssignReviewer = useCallback(async (assigneeUserId: string | null) => {
    if (!activeProjectId || !caseDetail) return;
    try {
      setActionLoading(true);
      await api.verification.assignReviewer(activeProjectId, caseDetail.id, {
        expected_version: caseDetail.version,
        assignee_user_id: assigneeUserId,
      });
      addToast({
        type: "success",
        title: "Reviewer Updated",
        message: assigneeUserId ? "Assigned reviewer" : "Unassigned case",
      });
      await Promise.all([loadWorkspaceData(), loadCaseDetail(caseDetail.id)]);
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 409) {
        setConcurrencyConflict({ isConflict: true, message: "Concurrent modification detected during assignment." });
      } else {
        const msg = err instanceof ApiError ? err.message : (err instanceof Error ? err.message : "Assignment failed");
        addToast({ type: "error", title: "Assignment Failed", message: msg });
      }
    } finally {
      setActionLoading(false);
    }
  }, [activeProjectId, caseDetail, loadWorkspaceData, loadCaseDetail, addToast]);

  const handleSaveEdit = useCallback(async (payload: { title: string; summary: string; reason: string }) => {
    if (!activeProjectId || !caseDetail) return;
    try {
      setActionLoading(true);
      await api.verification.editFinding(activeProjectId, caseDetail.id, {
        expected_version: caseDetail.version,
        title: payload.title,
        summary: payload.summary,
        reason: payload.reason,
      });
      addToast({ type: "success", title: "Finding Corrected", message: "Audited revision recorded." });
      setIsEditModalOpen(false);
      await Promise.all([loadWorkspaceData(), loadCaseDetail(caseDetail.id)]);
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 409) {
        setConcurrencyConflict({ isConflict: true, message: "Case updated concurrently. Reload latest before editing." });
      } else {
        const msg = err instanceof ApiError ? err.message : (err instanceof Error ? err.message : "Edit failed");
        addToast({ type: "error", title: "Edit Failed", message: msg });
      }
    } finally {
      setActionLoading(false);
    }
  }, [activeProjectId, caseDetail, loadWorkspaceData, loadCaseDetail, addToast]);

  const handleSendRequestContext = useCallback(async (payload: { targetUserId: string; question: string; informationType: string }) => {
    if (!activeProjectId || !caseDetail) return;
    try {
      setActionLoading(true);
      await api.verification.requestContext(activeProjectId, caseDetail.id, {
        requested_from_user_id: payload.targetUserId,
        question: payload.question,
        requested_information_type: payload.informationType,
        expected_version: caseDetail.version,
      });
      addToast({ type: "success", title: "Inquiry Sent", message: "Clarification request dispatched to team member." });
      setIsRequestContextModalOpen(false);
      await loadCaseDetail(caseDetail.id);
    } catch (err: unknown) {
      const msg = err instanceof ApiError ? err.message : (err instanceof Error ? err.message : "Inquiry failed");
      addToast({ type: "error", title: "Request Failed", message: msg });
    } finally {
      setActionLoading(false);
    }
  }, [activeProjectId, caseDetail, loadCaseDetail, addToast]);

  const handleAssessAll = useCallback(async () => {
    if (!activeProjectId) return;
    try {
      setAssessing(true);
      await api.verification.assessAll(activeProjectId);
      addToast({ type: "success", title: "Assessment Complete", message: "Ran automated verification across findings." });
      await loadWorkspaceData();
    } catch (err: unknown) {
      const msg = err instanceof ApiError ? err.message : (err instanceof Error ? err.message : "Assessment failed");
      addToast({ type: "error", title: "Assessment Failed", message: msg });
    } finally {
      setAssessing(false);
    }
  }, [activeProjectId, loadWorkspaceData, addToast]);

  return {
    reviewerNote,
    setReviewerNote,
    concurrencyConflict,
    setConcurrencyConflict,
    actionLoading,
    assessing,
    isEditModalOpen,
    setIsEditModalOpen,
    isRequestContextModalOpen,
    setIsRequestContextModalOpen,
    selectedChunkEvidence,
    setSelectedChunkEvidence,
    handleReloadLatestVersion,
    handleApprove,
    handleReject,
    handleMarkUnresolved,
    handleAssignReviewer,
    handleSaveEdit,
    handleSendRequestContext,
    handleAssessAll,
  };
}
