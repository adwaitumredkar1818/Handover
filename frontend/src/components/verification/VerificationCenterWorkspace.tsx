"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { ShieldCheck } from "lucide-react";
import { useLiveApp } from "../../context/LiveAppContext";
import {
  verificationApi,
  type QueueFilters,
  type VerificationCaseDetail,
  type VerificationQueueItem,
  type VerificationSummary,
} from "../../lib/verificationApi";
import { VerificationOverviewBar } from "./VerificationOverviewBar";
import { FindingsQueuePanel } from "./FindingsQueuePanel";
import { FindingWorkspacePanel } from "./FindingWorkspacePanel";

export function VerificationCenterWorkspace() {
  const { activeProject, members } = useLiveApp();
  const projectId = activeProject?.id ?? null;

  // ── State ────────────────────────────────────────────────────────────────
  const [summary, setSummary] = useState<VerificationSummary | null>(null);
  const [queueItems, setQueueItems] = useState<VerificationQueueItem[]>([]);
  const [queueTotal, setQueueTotal] = useState(0);
  const [availableDomains, setAvailableDomains] = useState<string[]>([]);
  const [availableSources, setAvailableSources] = useState<string[]>([]);
  const [availablePeople, setAvailablePeople] = useState<string[]>([]);

  const [filters, setFilters] = useState<QueueFilters>({
    status: "all",
    domain: "all",
    person: "all",
    source: "all",
    reviewer_id: "all",
    category: "all",
    search: "",
    sort_by: "updated_at",
    sort_dir: "desc",
  });

  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);
  const [caseDetail, setCaseDetail] = useState<VerificationCaseDetail | null>(null);

  const [queueLoading, setQueueLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [statusNotice, setStatusNotice] = useState<string | null>(null);

  // Debounce search input to avoid a request on every keystroke
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [debouncedFilters, setDebouncedFilters] = useState<QueueFilters>(filters);

  const handleFiltersChange = (next: QueueFilters) => {
    setFilters(next);
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    if (next.search !== debouncedFilters.search) {
      searchTimerRef.current = setTimeout(() => setDebouncedFilters(next), 350);
    } else {
      setDebouncedFilters(next);
    }
  };

  // ── Load summary + queue ─────────────────────────────────────────────────
  const loadSummaryAndQueue = useCallback(
    async (filtersOverride?: QueueFilters) => {
      if (!projectId) return;
      setQueueLoading(true);
      setErrorMsg(null);
      try {
        const [sumRes, qRes] = await Promise.all([
          verificationApi.getSummary(projectId),
          verificationApi.getQueue(projectId, filtersOverride ?? debouncedFilters),
        ]);
        setSummary(sumRes);
        setQueueItems(qRes.items);
        setQueueTotal(qRes.total);
        setAvailableDomains(qRes.available_domains);
        setAvailableSources(qRes.available_sources);
        setAvailablePeople(qRes.available_people);

        // Auto-select first item if none selected or selection no longer in list
        setSelectedCaseId((prev) => {
          const stillExists = qRes.items.some((i) => i.id === prev);
          if (!prev || !stillExists) return qRes.items[0]?.id ?? null;
          return prev;
        });
      } catch (err) {
        setErrorMsg(err instanceof Error ? err.message : "Failed to load verification queue.");
      } finally {
        setQueueLoading(false);
      }
    },
    [projectId, debouncedFilters]
  );

  // ── Load case detail ─────────────────────────────────────────────────────
  const loadCaseDetail = useCallback(async () => {
    if (!projectId || !selectedCaseId) {
      setCaseDetail(null);
      return;
    }
    setDetailLoading(true);
    try {
      const detail = await verificationApi.getCaseDetail(projectId, selectedCaseId);
      setCaseDetail(detail);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to load finding details.");
    } finally {
      setDetailLoading(false);
    }
  }, [projectId, selectedCaseId]);

  useEffect(() => {
    void loadSummaryAndQueue();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, debouncedFilters]);

  useEffect(() => {
    void loadCaseDetail();
  }, [loadCaseDetail]);

  // ── Keyboard navigation ──────────────────────────────────────────────────
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        if (queueItems.length === 0) return;
        const idx = queueItems.findIndex((i) => i.id === selectedCaseId);
        if (e.key === "ArrowDown" && idx < queueItems.length - 1) {
          e.preventDefault();
          const next = queueItems[idx + 1];
          if (next) setSelectedCaseId(next.id);
        } else if (e.key === "ArrowUp" && idx > 0) {
          e.preventDefault();
          const prev = queueItems[idx - 1];
          if (prev) setSelectedCaseId(prev.id);
        }
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [queueItems, selectedCaseId]);

  // ── Action helpers ───────────────────────────────────────────────────────
  const handleSync = async () => {
    if (!projectId) return;
    setActionBusy(true);
    setErrorMsg(null);
    setStatusNotice(null);
    try {
      const res = await verificationApi.syncAndAssess(projectId);
      setStatusNotice(
        `Synced ${res.cases_created} new, assessed ${res.cases_assessed} case(s), detected ${res.issues_detected} issue(s).`
      );
      await loadSummaryAndQueue();
      if (selectedCaseId) await loadCaseDetail();
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Sync failed.");
    } finally {
      setActionBusy(false);
    }
  };

  const runAction = async (
    fn: () => Promise<VerificationCaseDetail>,
    notice: string
  ) => {
    setActionBusy(true);
    setErrorMsg(null);
    setStatusNotice(null);
    try {
      const updated = await fn();
      setCaseDetail(updated);
      setStatusNotice(notice);
      await loadSummaryAndQueue();
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Action failed.");
    } finally {
      setActionBusy(false);
    }
  };

  // ── No project guard ─────────────────────────────────────────────────────
  if (!projectId) {
    return (
      <div className="p-8 max-w-4xl mx-auto text-center">
        <ShieldCheck className="w-10 h-10 text-slate-300 mx-auto mb-3" />
        <h1 className="text-lg font-semibold text-slate-900">Verification Center</h1>
        <p className="text-sm text-slate-500 mt-1">
          Select or create a project workspace to review extracted findings and supporting evidence.
        </p>
      </div>
    );
  }

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col gap-4 md:flex-1 md:min-h-0 md:overflow-hidden">
      {/* A: Overview Bar */}
      <VerificationOverviewBar
        projectName={activeProject?.name}
        summary={summary}
        filters={filters}
        onFiltersChange={handleFiltersChange}
        availableDomains={availableDomains}
        availableSources={availableSources}
        availablePeople={availablePeople}
        members={members}
        actionBusy={actionBusy}
        onSync={handleSync}
        statusNotice={statusNotice}
        errorMsg={errorMsg}
      />

      {/* B: Two-Panel Master–Detail (independent adaptive scrolling on md+, single-column flow on mobile) */}
      <div className="flex flex-col gap-4 md:flex-1 md:min-h-0 md:grid md:grid-cols-[minmax(240px,280px)_minmax(0,1fr)] lg:grid-cols-[minmax(280px,340px)_minmax(0,1fr)] md:grid-rows-[minmax(0,1fr)] md:items-start">
        {/* Left — Findings Queue */}
        <FindingsQueuePanel
          items={queueItems}
          total={queueTotal}
          selectedCaseId={selectedCaseId}
          onSelectCase={setSelectedCaseId}
          loading={queueLoading}
        />

        {/* Right — Main Review Workspace */}
        <FindingWorkspacePanel
          detail={caseDetail}
          loading={detailLoading}
          members={members}
          busy={actionBusy}
          onApprove={async (note, reason) => {
            if (!projectId || !caseDetail) return;
            await runAction(
              () =>
                verificationApi.approveCase(projectId, caseDetail.id, {
                  reviewer_note: note || undefined,
                  decision_reason: reason || undefined,
                }),
              "Finding approved and marked Verified."
            );
          }}
          onReject={async (reason, note) => {
            if (!projectId || !caseDetail) return;
            await runAction(
              () =>
                verificationApi.rejectCase(projectId, caseDetail.id, {
                  decision_reason: reason,
                  reviewer_note: note || undefined,
                }),
              "Finding rejected and retained in audit history."
            );
          }}
          onEditFinding={async (claim, domain, editReason, note) => {
            if (!projectId || !caseDetail) return;
            await runAction(
              () =>
                verificationApi.editFinding(projectId, caseDetail.id, {
                  current_claim: claim,
                  domain,
                  edit_reason: editReason,
                  reviewer_note: note || undefined,
                }),
              "Finding updated; original AI statement preserved."
            );
          }}
          onRequestContext={async (recipientId, question, note) => {
            if (!projectId || !caseDetail) return;
            await runAction(
              () =>
                verificationApi.requestContext(projectId, caseDetail.id, {
                  requested_from_user_id: recipientId,
                  question,
                  reviewer_note: note || undefined,
                }),
              "Clarification request dispatched."
            );
          }}
          onMarkUnresolved={async (reason, note) => {
            if (!projectId || !caseDetail) return;
            await runAction(
              () =>
                verificationApi.markUnresolved(projectId, caseDetail.id, {
                  decision_reason: reason,
                  reviewer_note: note || undefined,
                }),
              "Finding marked Unresolved and blocked from handover."
            );
          }}
          onAssignReviewer={async (reviewerId) => {
            if (!projectId || !caseDetail) return;
            await runAction(
              () => verificationApi.assignReviewer(projectId, caseDetail.id, reviewerId),
              "Reviewer assignment updated."
            );
          }}
          onRespondContextRequest={async (reqId, responseText) => {
            if (!projectId) return;
            setActionBusy(true);
            try {
              await verificationApi.respondContextRequest(projectId, reqId, {
                response_text: responseText,
              });
              setStatusNotice("Context response attached and finding returned to review.");
              await loadCaseDetail();
              await loadSummaryAndQueue();
            } catch (err) {
              setErrorMsg(
                err instanceof Error ? err.message : "Failed to submit context response."
              );
            } finally {
              setActionBusy(false);
            }
          }}
        />
      </div>
    </div>
  );
}
