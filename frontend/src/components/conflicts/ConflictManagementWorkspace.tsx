"use client";

import React, { useState, useEffect, useCallback } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { useLiveApp } from "../../context/LiveAppContext";
import {
  conflictsApi,
  ConflictDashboardMetrics,
  ConflictDetailResponse,
  ConflictQueueItem,
  ResolveConflictPayload,
} from "../../lib/conflictsApi";
import { api } from "../../lib/api";
import { ConflictDashboardBar } from "./ConflictDashboardBar";
import { ConflictQueuePanel } from "./ConflictQueuePanel";
import { ConflictInvestigationWorkspace } from "./ConflictInvestigationWorkspace";
import { GitCompare, AlertCircle, CheckCircle2 } from "lucide-react";
import { SectionLoader, CardSkeleton } from "../loading";

export function ConflictManagementWorkspace() {
  const { activeProject, members } = useLiveApp();
  const searchParams = useSearchParams();
  const router = useRouter();

  // State
  const [metrics, setMetrics] = useState<ConflictDashboardMetrics | null>(null);
  const [conflicts, setConflicts] = useState<ConflictQueueItem[]>([]);
  const [selectedConflictId, setSelectedConflictId] = useState<string | null>(null);
  const [selectedDetail, setSelectedDetail] = useState<ConflictDetailResponse | null>(null);
  const [teamMembers, setTeamMembers] = useState<Array<{ user_id: string; full_name: string; email: string }>>([]);

  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [toastMessage, setToastMessage] = useState<{ text: string; type: "success" | "error" } | null>(null);

  // Filters
  const [selectedCategory, setSelectedCategory] = useState<string>("all");
  const [selectedStatus, setSelectedStatus] = useState<string>("all");
  const [selectedPriority, setSelectedPriority] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState<string>("");

  const showToast = (text: string, type: "success" | "error" = "success") => {
    setToastMessage({ text, type });
    setTimeout(() => setToastMessage(null), 4000);
  };

  // 1. Map team members for assignments from LiveAppContext
  useEffect(() => {
    if (members && members.length > 0) {
      setTeamMembers(
        members.map((m) => ({
          user_id: m.user_id,
          full_name: m.user_full_name || m.user_email || m.user_id,
          email: m.user_email || "",
        }))
      );
    }
  }, [members]);

  // 2. Load metrics & conflicts list
  const loadConflicts = useCallback(
    async (projId: string, showSpinner = true) => {
      if (showSpinner) setLoading(true);
      try {
        const [dashMetrics, listRes] = await Promise.all([
          conflictsApi.getDashboard(projId).catch(() => null),
          conflictsApi.list(projId, {
            conflict_type: selectedCategory !== "all" ? selectedCategory : undefined,
            resolution_state: selectedStatus !== "all" ? selectedStatus : undefined,
            priority: selectedPriority !== "all" ? selectedPriority : undefined,
            search: searchQuery.trim() || undefined,
            limit: 100,
          }),
        ]);

        if (dashMetrics) setMetrics(dashMetrics);
        setConflicts(listRes.items);

        // Check if query param specifies conflict_id or case_id
        const paramConflictId = searchParams.get("conflict_id");
        const paramCaseId = searchParams.get("case_id");

        let targetId: string | null = null;
        if (paramConflictId && listRes.items.some((it) => it.id === paramConflictId)) {
          targetId = paramConflictId;
        } else if (paramCaseId) {
          const match = listRes.items.find(
            (it) => it.case_id === paramCaseId || it.related_finding_id === paramCaseId
          );
          if (match) targetId = match.id;
        }

        if (!targetId && selectedConflictId && listRes.items.some((it) => it.id === selectedConflictId)) {
          targetId = selectedConflictId;
        } else if (!targetId) {
          targetId = listRes.items[0]?.id || null;
        }

        setSelectedConflictId(targetId);
      } catch (err: any) {
        showToast(err.message || "Failed to load project conflicts", "error");
      } finally {
        if (showSpinner) setLoading(false);
      }
    },
    [selectedCategory, selectedStatus, selectedPriority, searchQuery, searchParams, selectedConflictId]
  );

  useEffect(() => {
    if (activeProject?.id) {
      loadConflicts(activeProject.id, true);
    }
  }, [activeProject?.id, selectedCategory, selectedStatus, selectedPriority, searchQuery]);

  // 3. Load detailed view when selectedConflictId changes
  useEffect(() => {
    if (!activeProject?.id || !selectedConflictId) {
      setSelectedDetail(null);
      return;
    }

    setDetailLoading(true);
    conflictsApi
      .getDetails(activeProject.id, selectedConflictId)
      .then((detail) => {
        setSelectedDetail(detail);
      })
      .catch((err: any) => {
        showToast(err.message || "Failed to fetch conflict details", "error");
      })
      .finally(() => {
        setDetailLoading(false);
      });
  }, [activeProject?.id, selectedConflictId]);

  // Actions
  const handleSync = async () => {
    if (!activeProject?.id) return;
    setSyncing(true);
    try {
      const res = await conflictsApi.sync(activeProject.id);
      showToast(
        `Synchronized successfully: ${res.assessment?.cases_assessed ?? 0} findings assessed, ${res.metrics?.total_conflicts ?? 0} total contradictions.`
      );
      await loadConflicts(activeProject.id, false);
    } catch (err: any) {
      showToast(err.message || "Failed to sync conflicts", "error");
    } finally {
      setSyncing(false);
    }
  };

  const handleAssignReviewer = async (reviewerId: string | null, notes?: string) => {
    if (!activeProject?.id || !selectedConflictId) return;
    try {
      const updated = await conflictsApi.assign(activeProject.id, selectedConflictId, reviewerId, notes);
      setSelectedDetail(updated);
      showToast(reviewerId ? "Reviewer assigned successfully." : "Reviewer unassigned.");
      loadConflicts(activeProject.id, false);
    } catch (err: any) {
      showToast(err.message || "Failed to assign reviewer", "error");
    }
  };

  const handleStartInvestigation = async (notes?: string) => {
    if (!activeProject?.id || !selectedConflictId) return;
    try {
      const updated = await conflictsApi.investigate(activeProject.id, selectedConflictId, notes);
      setSelectedDetail(updated);
      showToast("Investigation started.");
      loadConflicts(activeProject.id, false);
    } catch (err: any) {
      showToast(err.message || "Failed to start investigation", "error");
    }
  };

  const handleRequestContext = async (queries: string[], notes?: string) => {
    if (!activeProject?.id || !selectedConflictId) return;
    try {
      const updated = await conflictsApi.requestContext(activeProject.id, selectedConflictId, queries, notes);
      setSelectedDetail(updated);
      showToast("Context request recorded and status moved to Awaiting Context.");
      loadConflicts(activeProject.id, false);
    } catch (err: any) {
      showToast(err.message || "Failed to request context", "error");
    }
  };

  const handleAddNote = async (notes: string) => {
    if (!activeProject?.id || !selectedConflictId) return;
    try {
      const updated = await conflictsApi.addNotes(activeProject.id, selectedConflictId, notes);
      setSelectedDetail(updated);
      showToast("Investigator note added to audit trail.");
      loadConflicts(activeProject.id, false);
    } catch (err: any) {
      showToast(err.message || "Failed to add note", "error");
    }
  };

  const handleResolve = async (payload: ResolveConflictPayload) => {
    if (!activeProject?.id || !selectedConflictId) return;
    try {
      const updated = await conflictsApi.resolve(activeProject.id, selectedConflictId, payload);
      setSelectedDetail(updated);
      showToast("Contradiction formally resolved and recorded in audit log.");
      loadConflicts(activeProject.id, false);
    } catch (err: any) {
      showToast(err.message || "Failed to resolve conflict", "error");
    }
  };

  const handleReopen = async (reason: string) => {
    if (!activeProject?.id || !selectedConflictId) return;
    try {
      const updated = await conflictsApi.reopen(activeProject.id, selectedConflictId, reason);
      setSelectedDetail(updated);
      showToast("Contradiction reopened.");
      loadConflicts(activeProject.id, false);
    } catch (err: any) {
      showToast(err.message || "Failed to reopen conflict", "error");
    }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] bg-white overflow-hidden relative">
      {/* Toast Notification */}
      {toastMessage && (
        <div
          className={`fixed top-18 right-6 z-50 px-4 py-3 rounded-xl shadow-xl border flex items-center gap-2 text-xs font-semibold animate-in fade-in slide-in-from-top-4 ${
            toastMessage.type === "success"
              ? "bg-slate-900 text-white border-slate-800"
              : "bg-red-900 text-white border-red-800"
          }`}
        >
          {toastMessage.type === "success" ? (
            <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
          ) : (
            <AlertCircle className="w-4 h-4 text-red-400 shrink-0" />
          )}
          <span>{toastMessage.text}</span>
        </div>
      )}

      {/* Top Dashboard Metrics & Filters */}
      <ConflictDashboardBar
        metrics={metrics}
        selectedCategory={selectedCategory}
        onSelectCategory={setSelectedCategory}
        selectedStatus={selectedStatus}
        onSelectStatus={setSelectedStatus}
        selectedPriority={selectedPriority}
        onSelectPriority={setSelectedPriority}
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        onSync={handleSync}
        syncing={syncing}
      />

      {/* Main Workspace Split: Left Queue + Right Investigation Workspace */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left Queue Panel */}
        <ConflictQueuePanel
          conflicts={conflicts}
          selectedId={selectedConflictId}
          onSelect={setSelectedConflictId}
          loading={loading}
        />

        {/* Right Investigation Workspace */}
        {detailLoading ? (
          <div className="flex-1 p-6 bg-slate-50 flex flex-col justify-center" role="status" aria-live="polite">
            <SectionLoader
              label="Loading comparative investigation..."
              description="Retrieving contradictory statements, opposing source citations, and confidence metrics."
            />
          </div>
        ) : selectedDetail ? (
          <ConflictInvestigationWorkspace
            conflict={selectedDetail}
            onAssignReviewer={handleAssignReviewer}
            onStartInvestigation={handleStartInvestigation}
            onRequestContext={handleRequestContext}
            onAddNote={handleAddNote}
            onResolve={handleResolve}
            onReopen={handleReopen}
            teamMembers={teamMembers}
          />
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center p-8 bg-slate-50 text-center">
            <GitCompare className="w-12 h-12 text-slate-300 mb-3" />
            <h3 className="text-base font-bold text-slate-800">Select a Contradiction to Investigate</h3>
            <p className="text-xs text-slate-500 max-w-sm mt-1">
              Choose an item from the left queue to compare supporting vs opposing evidence side-by-side and execute reviewer determinations.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
