"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { Activity, CheckSquare, Scale, ShieldCheck } from "lucide-react";
import { api } from "../../lib/api";
import { useLiveApp } from "../../context/LiveAppContext";
import { getCachedGraph, invalidateGraphCache, setCachedGraph } from "../../lib/graphCache";
import {
  DEFAULT_VERIFICATION_FILTERS,
  verificationApi,
  type QueueFilters,
  type VerificationCaseDetail,
  type VerificationQueueItem,
  type VerificationQueueResponse,
  type VerificationStatus,
  type VerificationSummary,
} from "../../lib/verificationApi";
import { VerificationOverviewBar } from "./VerificationOverviewBar";
import { FindingsQueuePanel } from "./FindingsQueuePanel";
import { FindingWorkspacePanel } from "./FindingWorkspacePanel";
import { ChangeImpactFeed } from "./ChangeImpactFeed";
import { KnowledgeQualityPanel } from "./KnowledgeQualityPanel";
import { formatDomainLabel } from "./verificationTheme";

const STATUS_TO_SUMMARY_KEY: Record<
  VerificationStatus,
  keyof Pick<
    VerificationSummary,
    | "candidate_count"
    | "pending_review_count"
    | "conflicted_count"
    | "unresolved_count"
    | "verified_count"
    | "rejected_count"
  >
> = {
  candidate: "candidate_count",
  pending_review: "pending_review_count",
  conflicted: "conflicted_count",
  unresolved: "unresolved_count",
  verified: "verified_count",
  rejected: "rejected_count",
};

interface OptimisticCasePatch {
  case_status?: VerificationStatus;
  current_claim?: string;
  domain?: string;
  assigned_reviewer_id?: string | null;
  assigned_reviewer_name?: string | null;
  handover_eligible?: boolean;
  handover_eligibility_reason?: string;
  pending_context_delta?: number;
}

function applySummaryDelta(
  prev: VerificationSummary,
  prevStatus: VerificationStatus,
  nextStatus: VerificationStatus,
  pendingContextDelta = 0
): VerificationSummary {
  if (prevStatus === nextStatus && pendingContextDelta === 0) return prev;
  const next = { ...prev };
  if (prevStatus !== nextStatus) {
    const prevKey = STATUS_TO_SUMMARY_KEY[prevStatus];
    const nextKey = STATUS_TO_SUMMARY_KEY[nextStatus];
    if (prevKey) next[prevKey] = Math.max(0, (next[prevKey] ?? 0) - 1);
    if (nextKey) next[nextKey] = (next[nextKey] ?? 0) + 1;
  }
  if (pendingContextDelta !== 0) {
    next.pending_context_requests_count = Math.max(
      0,
      (next.pending_context_requests_count ?? 0) + pendingContextDelta
    );
  }
  return next;
}

function patchQueueItemList(
  items: VerificationQueueItem[],
  caseId: string,
  detail: VerificationCaseDetail
): VerificationQueueItem[] {
  let changed = false;
  const next = items.map((item) => {
    if (item.id !== caseId) return item;
    changed = true;
    return {
      ...item,
      case_status: detail.case_status,
      current_claim: detail.current_claim,
      domain: detail.domain,
      assigned_reviewer_id: detail.assigned_reviewer_id,
      assigned_reviewer_name: detail.assigned_reviewer_name,
      version: detail.version,
      last_reviewed_at: detail.last_reviewed_at,
      updated_at: detail.updated_at,
    };
  });
  return changed ? next : items;
}

function hydrateQueueCaseDetails(
  projectId: string,
  details: Record<string, VerificationCaseDetail> | undefined,
  userId?: string | null
): void {
  if (!details) return;
  for (const [cid, detail] of Object.entries(details)) {
    setCachedGraph(`verif_case:${projectId}:${cid}`, detail, userId);
  }
}

function isUnfilteredQueueQuery(f: QueueFilters): boolean {
  return (
    (!f.status || f.status === "all") &&
    (!f.domain || f.domain === "all") &&
    (!f.person || f.person === "all") &&
    (!f.source || f.source === "all") &&
    (!f.reviewer_id || f.reviewer_id === "all") &&
    (!f.category || f.category === "all") &&
    !(f.search ?? "").trim()
  );
}

function filterQueueItemsClientSide(
  items: VerificationQueueItem[],
  f: QueueFilters
): VerificationQueueItem[] {
  const searchQ = (f.search ?? "").trim().toLowerCase();
  const domainTarget = f.domain && f.domain !== "all" ? f.domain.toLowerCase() : null;
  const domainTargetLabel = domainTarget ? formatDomainLabel(domainTarget).toLowerCase() : null;
  const personQ = f.person && f.person !== "all" ? f.person.toLowerCase() : null;

  const filtered = items.filter((item) => {
    if (f.status && f.status !== "all" && item.case_status !== f.status) return false;
    if (domainTarget) {
      const itemDom = (item.domain || "").toLowerCase();
      const itemDomLabel = formatDomainLabel(item.domain || "").toLowerCase();
      if (itemDom !== domainTarget && itemDomLabel !== domainTargetLabel) return false;
    }
    if (f.source && f.source !== "all" && item.source_provider !== f.source) return false;
    if (f.reviewer_id && f.reviewer_id !== "all" && item.assigned_reviewer_id !== f.reviewer_id) {
      return false;
    }
    if (personQ && !(item.person_name || "").toLowerCase().includes(personQ)) return false;
    if (
      f.category &&
      f.category !== "all" &&
      !item.verification_categories.includes(f.category as VerificationQueueItem["verification_categories"][number])
    ) {
      return false;
    }
    if (searchQ) {
      const haystack = [
        item.title || "",
        item.current_claim || "",
        item.original_ai_claim || "",
        item.domain || "",
      ]
        .join(" ")
        .toLowerCase();
      if (!haystack.includes(searchQ)) return false;
    }
    return true;
  });

  const sortBy = f.sort_by || "updated_at";
  const asc = (f.sort_dir || "desc").toLowerCase() === "asc";
  const mult = asc ? 1 : -1;
  return [...filtered].sort((a, b) => {
    let cmp = 0;
    if (sortBy === "priority") cmp = (a.priority || "").localeCompare(b.priority || "");
    else if (sortBy === "status") cmp = (a.case_status || "").localeCompare(b.case_status || "");
    else if (sortBy === "domain") cmp = (a.domain || "").localeCompare(b.domain || "");
    else cmp = (a.updated_at || "").localeCompare(b.updated_at || "");
    return cmp !== 0 ? cmp * mult : a.id.localeCompare(b.id);
  });
}

export function VerificationCenterWorkspace() {
  const { activeProject, members, user } = useLiveApp();
  const projectId = activeProject?.id ?? null;

  const canReview = React.useMemo(() => {
    if (!activeProject) return false;
    if (activeProject.effective_permissions?.includes("project.knowledge.review")) {
      return true;
    }
    const projectRole = (activeProject.my_project_role ?? "").toLowerCase();
    if (projectRole === "project_manager" || projectRole === "reviewer") {
      return true;
    }
    if (user?.id) {
      const me = members.find((m) => m.user_id === user.id);
      const memberRole = (me?.role_name ?? "").toLowerCase();
      if (memberRole === "project_manager" || memberRole === "reviewer") {
        return true;
      }
    }
    const userRoles = (user?.roles ?? []).map((r) => r.toLowerCase());
    if (userRoles.includes("org_owner") || userRoles.includes("org_admin")) {
      return true;
    }
    return false;
  }, [activeProject, members, user]);

  // ── State ────────────────────────────────────────────────────────────────
  const [summary, setSummary] = useState<VerificationSummary | null>(null);
  const [queueItems, setQueueItems] = useState<VerificationQueueItem[]>([]);
  const [queueTotal, setQueueTotal] = useState(0);
  const [availableDomains, setAvailableDomains] = useState<string[]>([]);
  const [availableSources, setAvailableSources] = useState<string[]>([]);
  const [availablePeople, setAvailablePeople] = useState<string[]>([]);

  const [filters, setFilters] = useState<QueueFilters>(DEFAULT_VERIFICATION_FILTERS);

  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);
  const selectedCaseIdRef = useRef<string | null>(null);
  selectedCaseIdRef.current = selectedCaseId;
  const [caseDetail, setCaseDetail] = useState<VerificationCaseDetail | null>(null);

  const [queueLoading, setQueueLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);
  const [verifyingAll, setVerifyingAll] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [statusNotice, setStatusNotice] = useState<string | null>(null);
  const [activeWorkspaceTab, setActiveWorkspaceTab] = useState<"queue" | "change_impact" | "quality">("queue");

  // Debounce search input to avoid a request on every keystroke
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [debouncedFilters, setDebouncedFilters] = useState<QueueFilters>(filters);
  const loadedProjectRef = useRef<string | null>(null);
  const hasQueueDataRef = useRef(false);
  const mutationEpochRef = useRef(0);
  const unfilteredQueueRef = useRef<VerificationQueueItem[]>([]);
  const prefetchedTabsProjectRef = useRef<string | null>(null);

  const handleFiltersChange = (next: QueueFilters) => {
    setFilters(next);
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    if (next.search !== debouncedFilters.search) {
      searchTimerRef.current = setTimeout(() => setDebouncedFilters(next), 350);
    } else {
      setDebouncedFilters(next);
    }
  };

  // ── Load summary + queue (with stale-while-revalidate cache) ───────────────
  const loadSummaryAndQueue = useCallback(
    async (filtersOverride?: QueueFilters, forceRefresh = false) => {
      if (!projectId) {
        loadedProjectRef.current = null;
        hasQueueDataRef.current = false;
        unfilteredQueueRef.current = [];
        return;
      }
      if (loadedProjectRef.current !== projectId) {
        loadedProjectRef.current = projectId;
        hasQueueDataRef.current = false;
        unfilteredQueueRef.current = [];
      }
      const activeFilters = filtersOverride ?? debouncedFilters;
      const cacheKey = `verif_q:${projectId}:${JSON.stringify(activeFilters)}`;
      const cached = !forceRefresh
        ? getCachedGraph<{
            summary: VerificationSummary;
            queue: Awaited<ReturnType<typeof verificationApi.getQueue>>;
          }>(cacheKey, undefined, user?.id)
        : null;

      if (cached) {
        hasQueueDataRef.current = cached.queue.items.length > 0;
        if (isUnfilteredQueueQuery(activeFilters)) {
          unfilteredQueueRef.current = cached.queue.items;
        }
        hydrateQueueCaseDetails(projectId, cached.queue.case_details, user?.id);
        setSummary(cached.summary);
        setQueueItems(cached.queue.items);
        setQueueTotal(cached.queue.total);
        setAvailableDomains(cached.queue.available_domains);
        setAvailableSources(cached.queue.available_sources);
        setAvailablePeople(cached.queue.available_people);
        const curSel = selectedCaseIdRef.current;
        const nextSel =
          !curSel || !cached.queue.items.some((i) => i.id === curSel)
            ? cached.queue.items[0]?.id ?? null
            : curSel;
        setSelectedCaseId(nextSel);
        if (nextSel) {
          const preloadedDetail =
            cached.queue.case_details?.[nextSel] ??
            getCachedGraph<VerificationCaseDetail>(
              `verif_case:${projectId}:${nextSel}`,
              undefined,
              user?.id
            );
          if (preloadedDetail) {
            setCaseDetail(preloadedDetail);
            setDetailLoading(false);
          }
        }
        setQueueLoading(false);
      } else if (!forceRefresh && unfilteredQueueRef.current.length > 0) {
        // Apply immediate client-side filter preview while server returns exact matches
        const previewItems = filterQueueItemsClientSide(unfilteredQueueRef.current, activeFilters);
        setQueueItems(previewItems);
        setQueueTotal(previewItems.length);
        setQueueLoading(false);
      } else if (!hasQueueDataRef.current) {
        setQueueLoading(true);
      }

      const epochAtStart = mutationEpochRef.current;
      setErrorMsg(null);
      try {
        const [sumRes, qRes] = await Promise.all([
          verificationApi.getSummary(projectId),
          verificationApi.getQueue(projectId, activeFilters),
        ]);
        if (epochAtStart !== mutationEpochRef.current) {
          return;
        }
        hasQueueDataRef.current = true;
        if (isUnfilteredQueueQuery(activeFilters)) {
          unfilteredQueueRef.current = qRes.items;
        }
        hydrateQueueCaseDetails(projectId, qRes.case_details, user?.id);
        setCachedGraph(cacheKey, { summary: sumRes, queue: qRes }, user?.id);
        setSummary(sumRes);
        setQueueItems(qRes.items);
        setQueueTotal(qRes.total);
        setAvailableDomains(qRes.available_domains);
        setAvailableSources(qRes.available_sources);
        setAvailablePeople(qRes.available_people);

        // Background-warm secondary tabs (Change Impact & Knowledge Quality) once per project
        if (prefetchedTabsProjectRef.current !== projectId) {
          prefetchedTabsProjectRef.current = projectId;
          const ciKey = `verif_change_impact:${projectId}`;
          if (!getCachedGraph(ciKey)) {
            void api.verification
              .getChangeImpact(projectId, 100, 0)
              .then((res) => {
                setCachedGraph(ciKey, { items: res.items || [], total: res.total || 0 });
              })
              .catch(() => {});
          }
          const qKey = `verif_quality:${projectId}`;
          if (!getCachedGraph(qKey)) {
            void api.knowledgeIntelligence
              .getQuality(projectId, false)
              .then((res) => {
                const overall =
                  typeof res.overall_quality_score === "number"
                    ? res.overall_quality_score
                    : typeof res.overall_score === "number"
                    ? res.overall_score
                    : 0;
                const gaps = Array.isArray(res.identified_gaps)
                  ? res.identified_gaps
                  : Array.isArray(res.gaps)
                  ? res.gaps
                  : [];
                setCachedGraph(qKey, {
                  dimension_scores: res.dimension_scores || {},
                  overall_score: overall,
                  gaps,
                  total_items: res.total_items ?? 0,
                });
              })
              .catch(() => {});
          }
        }

        // Auto-select first item if none selected or selection no longer in list
        const curSel = selectedCaseIdRef.current;
        const nextSel =
          !curSel || !qRes.items.some((i) => i.id === curSel)
            ? qRes.items[0]?.id ?? null
            : curSel;
        setSelectedCaseId(nextSel);
        if (nextSel) {
          const freshDetail = qRes.case_details?.[nextSel];
          if (freshDetail) {
            setCaseDetail(freshDetail);
            setDetailLoading(false);
          }
        }

        // Backfill any queue items missing from inline case_details
        const missingIds = qRes.items
          .map((i) => i.id)
          .filter(
            (id) =>
              !qRes.case_details?.[id] &&
              !getCachedGraph<VerificationCaseDetail>(`verif_case:${projectId}:${id}`, undefined, user?.id)
          );
        if (missingIds.length > 0) {
          void (async () => {
            let idx = 0;
            const workers = Array.from({ length: Math.min(2, missingIds.length) }, async () => {
              while (idx < missingIds.length) {
                const cid = missingIds[idx++];
                if (!cid) continue;
                try {
                  const detail = await verificationApi.getCaseDetail(projectId, cid);
                  setCachedGraph(`verif_case:${projectId}:${cid}`, detail, user?.id);
                } catch {
                  // Best-effort background warmup
                }
              }
            });
            await Promise.allSettled(workers);
          })();
        }
      } catch (err) {
        if (!cached && !hasQueueDataRef.current) {
          setErrorMsg(err instanceof Error ? err.message : "Failed to load verification queue.");
        }
      } finally {
        setQueueLoading(false);
      }
    },
    [projectId, debouncedFilters, user?.id]
  );

  // ── Load case detail (serve immediately from hydrated cache unless forced) ──
  const loadCaseDetail = useCallback(async (forceRefresh = false) => {
    if (!projectId || !selectedCaseId) {
      setCaseDetail(null);
      return;
    }
    const detailCacheKey = `verif_case:${projectId}:${selectedCaseId}`;
    const cachedDetail = !forceRefresh
      ? getCachedGraph<VerificationCaseDetail>(detailCacheKey, undefined, user?.id)
      : null;

    if (cachedDetail) {
      setCaseDetail(cachedDetail);
      setDetailLoading(false);
      return;
    }

    setDetailLoading(true);
    try {
      const detail = await verificationApi.getCaseDetail(projectId, selectedCaseId);
      setCachedGraph(detailCacheKey, detail, user?.id);
      setCaseDetail(detail);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to load finding details.");
    } finally {
      setDetailLoading(false);
    }
  }, [projectId, selectedCaseId, user?.id]);

  useEffect(() => {
    void loadSummaryAndQueue();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, debouncedFilters]);

  useEffect(() => {
    void loadCaseDetail();
  }, [loadCaseDetail]);

  // ── Prefetch next queue item detail ──────────────────────────────────────
  useEffect(() => {
    if (!projectId || !selectedCaseId || queueItems.length < 2) return;
    const idx = queueItems.findIndex((i) => i.id === selectedCaseId);
    if (idx < 0 || idx >= queueItems.length - 1) return;
    const nextItem = queueItems[idx + 1];
    if (!nextItem) return;

    const nextCacheKey = `verif_case:${projectId}:${nextItem.id}`;
    if (getCachedGraph<VerificationCaseDetail>(nextCacheKey, undefined, user?.id)) {
      return;
    }

    let cancelled = false;
    const timer = setTimeout(() => {
      verificationApi
        .getCaseDetail(projectId, nextItem.id)
        .then((detail) => {
          if (!cancelled) {
            setCachedGraph(nextCacheKey, detail, user?.id);
          }
        })
        .catch(() => {
          // Best-effort background prefetch
        });
    }, 150);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [projectId, selectedCaseId, queueItems, user?.id]);

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

  const handleVerifyAll = async () => {
    if (!projectId) return;
    const prevSummary = summary;
    const prevQueue = queueItems;
    const prevDetail = caseDetail;
    const unverifiedCount = prevSummary
      ? prevSummary.candidate_count +
        prevSummary.pending_review_count +
        prevSummary.conflicted_count +
        prevSummary.unresolved_count
      : 0;
    if (unverifiedCount === 0) return;

    mutationEpochRef.current += 1;
    setVerifyingAll(true);
    setActionBusy(true);
    setErrorMsg(null);

    const nowIso = new Date().toISOString();
    if (prevSummary) {
      setSummary({
        ...prevSummary,
        candidate_count: 0,
        pending_review_count: 0,
        conflicted_count: 0,
        unresolved_count: 0,
        verified_count: prevSummary.verified_count + unverifiedCount,
      });
    }
    const optimisticQueue = prevQueue.map((item) =>
      item.case_status !== "rejected"
        ? { ...item, case_status: "verified" as VerificationStatus, last_reviewed_at: nowIso, updated_at: nowIso }
        : item
    );
    setQueueItems(optimisticQueue);
    unfilteredQueueRef.current = unfilteredQueueRef.current.map((item) =>
      item.case_status !== "rejected"
        ? { ...item, case_status: "verified" as VerificationStatus, last_reviewed_at: nowIso, updated_at: nowIso }
        : item
    );
    if (prevDetail && prevDetail.case_status !== "rejected") {
      setCaseDetail({
        ...prevDetail,
        case_status: "verified",
        handover_eligible: prevDetail.restricted_evidence_count === 0,
        handover_eligibility_reason:
          prevDetail.restricted_evidence_count > 0
            ? prevDetail.handover_eligibility_reason
            : "Human-verified and eligible for Handover Workspace.",
        last_reviewed_at: nowIso,
        updated_at: nowIso,
      });
    }
    setStatusNotice(`Verifying ${unverifiedCount} eligible finding(s)...`);

    try {
      const res = await verificationApi.verifyAll(projectId, {
        reviewer_note: "Bulk verified via Verify All in Verification Center",
      });
      mutationEpochRef.current += 1;
      setSummary(res.summary);
      setStatusNotice(
        `Verified ${res.verified_count} finding(s) (${res.knowledge_items_verified} knowledge item(s), ${res.relationships_verified} relationship(s)).`
      );
      invalidateGraphCache(`verif_q:${projectId}`);
      invalidateGraphCache(`verif_case:${projectId}`);
      invalidateGraphCache(`verif_quality:${projectId}`);
      setVerifyingAll(false);
      setActionBusy(false);
      void loadSummaryAndQueue(undefined, true);
      if (selectedCaseIdRef.current) {
        void loadCaseDetail(true);
      }
    } catch (err) {
      mutationEpochRef.current += 1;
      setSummary(prevSummary);
      setQueueItems(prevQueue);
      setCaseDetail(prevDetail);
      setStatusNotice(null);
      setErrorMsg(err instanceof Error ? err.message : "Bulk verification failed.");
      setVerifyingAll(false);
      setActionBusy(false);
    }
  };

  // ── Action helpers ───────────────────────────────────────────────────────
  const handleSync = async () => {
    if (!projectId) return;
    setActionBusy(true);
    setErrorMsg(null);
    setStatusNotice(null);
    try {
      const res = await verificationApi.syncAndAssess(projectId);
      invalidateGraphCache(`verif_q:${projectId}`);
      invalidateGraphCache(`verif_case:${projectId}`);
      setStatusNotice(
        `Synced ${res.cases_created} new, assessed ${res.cases_assessed} case(s), detected ${res.issues_detected} issue(s).`
      );
      await loadSummaryAndQueue(undefined, true);
      if (selectedCaseId) await loadCaseDetail(true);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Sync failed.");
    } finally {
      setActionBusy(false);
    }
  };

  const runAction = async (
    fn: () => Promise<VerificationCaseDetail>,
    notice: string,
    optimisticPatch?: OptimisticCasePatch
  ) => {
    const prevDetail = caseDetail;
    const prevQueue = queueItems;
    const prevSummary = summary;
    const prevStatus = prevDetail?.case_status;

    mutationEpochRef.current += 1;
    setActionBusy(true);
    setErrorMsg(null);

    if (optimisticPatch && prevDetail) {
      const nowIso = new Date().toISOString();
      const targetStatus = optimisticPatch.case_status ?? prevDetail.case_status;
      const optimisticDetail: VerificationCaseDetail = {
        ...prevDetail,
        case_status: targetStatus,
        current_claim: optimisticPatch.current_claim ?? prevDetail.current_claim,
        domain: optimisticPatch.domain ?? prevDetail.domain,
        assigned_reviewer_id:
          optimisticPatch.assigned_reviewer_id !== undefined
            ? optimisticPatch.assigned_reviewer_id
            : prevDetail.assigned_reviewer_id,
        assigned_reviewer_name:
          optimisticPatch.assigned_reviewer_name !== undefined
            ? optimisticPatch.assigned_reviewer_name
            : prevDetail.assigned_reviewer_name,
        handover_eligible:
          optimisticPatch.handover_eligible ??
          (prevDetail.restricted_evidence_count === 0 && targetStatus === "verified"),
        handover_eligibility_reason:
          optimisticPatch.handover_eligibility_reason ?? prevDetail.handover_eligibility_reason,
        last_reviewed_at: nowIso,
        updated_at: nowIso,
      };
      setCaseDetail(optimisticDetail);
      setQueueItems((curr) => patchQueueItemList(curr, prevDetail.id, optimisticDetail));
      if (
        prevSummary &&
        ((prevStatus && targetStatus !== prevStatus) || optimisticPatch.pending_context_delta)
      ) {
        setSummary(
          applySummaryDelta(
            prevSummary,
            prevStatus ?? targetStatus,
            targetStatus,
            optimisticPatch.pending_context_delta ?? 0
          )
        );
      }
      setStatusNotice(notice);
    } else {
      setStatusNotice(null);
    }

    try {
      const updated = await fn();
      mutationEpochRef.current += 1;
      const nextQueue = patchQueueItemList(prevQueue, updated.id, updated);
      const nextSummary = prevSummary
        ? applySummaryDelta(
            prevSummary,
            prevStatus ?? updated.case_status,
            updated.case_status,
            optimisticPatch?.pending_context_delta ?? 0
          )
        : prevSummary;

      setCaseDetail(updated);
      setQueueItems(nextQueue);
      if (nextSummary) setSummary(nextSummary);
      setStatusNotice(notice);

      if (projectId) {
        const activeQCacheKey = `verif_q:${projectId}:${JSON.stringify(debouncedFilters)}`;
        const prevCachedQ = getCachedGraph<{
          summary: VerificationSummary;
          queue: VerificationQueueResponse;
        }>(activeQCacheKey, undefined, user?.id);
        setCachedGraph(`verif_case:${projectId}:${updated.id}`, updated, user?.id);
        invalidateGraphCache(`verif_q:${projectId}`);
        if (nextSummary) {
          setCachedGraph(
            activeQCacheKey,
            {
              summary: nextSummary,
              queue: {
                items: nextQueue,
                total: queueTotal,
                limit: debouncedFilters.limit ?? 50,
                offset: debouncedFilters.offset ?? 0,
                available_domains: availableDomains,
                available_sources: availableSources,
                available_people: availablePeople,
                case_details: {
                  ...(prevCachedQ?.queue?.case_details ?? {}),
                  [updated.id]: updated,
                },
              },
            },
            user?.id
          );
        }
      }

      setActionBusy(false);
      void loadSummaryAndQueue(undefined, true);
    } catch (err) {
      mutationEpochRef.current += 1;
      setCaseDetail(prevDetail);
      setQueueItems(prevQueue);
      setSummary(prevSummary);
      setStatusNotice(null);
      setErrorMsg(err instanceof Error ? err.message : "Action failed.");
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
        canReview={canReview}
        onSync={handleSync}
        onVerifyAll={handleVerifyAll}
        verifyingAll={verifyingAll}
        statusNotice={statusNotice}
        errorMsg={errorMsg}
      />

      {/* Sub-navigation workspace tabs */}
      <div className="flex items-center gap-2 border-b border-slate-200 pb-2">
        <button
          onClick={() => setActiveWorkspaceTab("queue")}
          className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-md transition cursor-pointer ${
            activeWorkspaceTab === "queue"
              ? "bg-indigo-600 text-white shadow-xs"
              : "text-slate-600 hover:bg-slate-100"
          }`}
        >
          <CheckSquare className="w-3.5 h-3.5" />
          Findings Review Queue
        </button>
        <button
          onClick={() => setActiveWorkspaceTab("change_impact")}
          className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-md transition cursor-pointer ${
            activeWorkspaceTab === "change_impact"
              ? "bg-indigo-600 text-white shadow-xs"
              : "text-slate-600 hover:bg-slate-100"
          }`}
        >
          <Activity className="w-3.5 h-3.5" />
          Change Impact Feed
        </button>
        <button
          onClick={() => setActiveWorkspaceTab("quality")}
          className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-md transition cursor-pointer ${
            activeWorkspaceTab === "quality"
              ? "bg-indigo-600 text-white shadow-xs"
              : "text-slate-600 hover:bg-slate-100"
          }`}
        >
          <Scale className="w-3.5 h-3.5" />
          Knowledge Quality
        </button>
      </div>

      {activeWorkspaceTab === "change_impact" && (
        <div className="flex-1 min-h-0">
          <ChangeImpactFeed
            projectId={projectId}
            onSelectFinding={(caseId) => {
              setSelectedCaseId(caseId);
              setActiveWorkspaceTab("queue");
            }}
          />
        </div>
      )}

      {activeWorkspaceTab === "quality" && (
        <div className="flex-1 min-h-0">
          <KnowledgeQualityPanel projectId={projectId} />
        </div>
      )}

      {/* B: Two-Panel Master–Detail (independent adaptive scrolling on md+, single-column flow on mobile) */}
      {activeWorkspaceTab === "queue" && (
      <div className="flex flex-col gap-4 md:flex-1 md:min-h-0 md:grid md:grid-cols-[minmax(240px,280px)_minmax(0,1fr)] lg:grid-cols-[minmax(280px,340px)_minmax(0,1fr)] md:grid-rows-[minmax(0,1fr)] md:items-start">
        {/* Left — Findings Queue */}
        <FindingsQueuePanel
          items={queueItems}
          total={queueTotal}
          selectedCaseId={selectedCaseId}
          onSelectCase={setSelectedCaseId}
          loading={queueLoading}
          canReview={canReview}
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
              "Finding approved and marked Verified.",
              {
                case_status: "verified",
                handover_eligible: caseDetail.restricted_evidence_count === 0,
                handover_eligibility_reason:
                  caseDetail.restricted_evidence_count > 0
                    ? caseDetail.handover_eligibility_reason
                    : "Human-verified and eligible for Handover Workspace.",
              }
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
              "Finding rejected and retained in audit history.",
              {
                case_status: "rejected",
                handover_eligible: false,
                handover_eligibility_reason: "Rejected by human reviewer; excluded from handover.",
              }
            );
          }}
          onEditFinding={async (claim, domain, editReason, note) => {
            if (!projectId || !caseDetail) return;
            const nextStatus: VerificationStatus =
              caseDetail.case_status === "conflicted" ? "conflicted" : "pending_review";
            await runAction(
              () =>
                verificationApi.editFinding(projectId, caseDetail.id, {
                  current_claim: claim,
                  domain,
                  edit_reason: editReason,
                  reviewer_note: note || undefined,
                }),
              "Finding updated; original AI statement preserved.",
              {
                case_status: nextStatus,
                current_claim: claim,
                domain: domain.trim() || caseDetail.domain,
                handover_eligible: false,
              }
            );
          }}
          onRequestContext={async (recipientId, question, note) => {
            if (!projectId || !caseDetail) return;
            const nextStatus: VerificationStatus =
              caseDetail.case_status === "candidate" ? "pending_review" : caseDetail.case_status;
            await runAction(
              () =>
                verificationApi.requestContext(projectId, caseDetail.id, {
                  requested_from_user_id: recipientId,
                  question,
                  reviewer_note: note || undefined,
                }),
              "Clarification request dispatched.",
              {
                case_status: nextStatus,
                pending_context_delta: 1,
              }
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
              "Finding marked Unresolved and blocked from handover.",
              {
                case_status: "unresolved",
                handover_eligible: false,
                handover_eligibility_reason: "Blocked: insufficient evidence; cannot enter approved handover.",
              }
            );
          }}
          onAssignReviewer={async (reviewerId) => {
            if (!projectId || !caseDetail) return;
            const member = reviewerId ? members.find((m) => m.user_id === reviewerId) : undefined;
            const nextStatus: VerificationStatus =
              reviewerId && caseDetail.case_status === "candidate"
                ? "pending_review"
                : caseDetail.case_status;
            await runAction(
              () => verificationApi.assignReviewer(projectId, caseDetail.id, reviewerId),
              "Reviewer assignment updated.",
              {
                case_status: nextStatus,
                assigned_reviewer_id: reviewerId,
                assigned_reviewer_name: member ? member.full_name || member.email : null,
              }
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
      )}
    </div>
  );
}
