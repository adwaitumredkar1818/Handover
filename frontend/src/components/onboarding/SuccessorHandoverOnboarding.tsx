"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Bot,
  Check,
  CheckCircle2,
  ClipboardCheck,
  Compass,
  Copy,
  Database,
  ExternalLink,
  FileText,
  FolderKanban,
  GitBranch,
  Layers,
  Loader2,
  MessageSquarePlus,
  PackageCheck,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  Users,
} from "lucide-react";
import { Badge, Button, Card, CardHeader } from "../ui";
import { FormattedMarkdown } from "../figma-ui/FormattedMarkdown";
import { useLiveApp } from "../../context/LiveAppContext";
import { api } from "../../lib/api";
import { getCachedGraph, setCachedGraph } from "../../lib/graphCache";
import type {
  HandoverCaseItem,
  HandoverDeliveryRecord,
  HandoverMandatorySection,
  HandoverPackageVersionSummary,
  HandoverResponsibilityTransferDetail,
  HandoverVersionSectionsResponse,
  Project,
  ProjectMember,
} from "../../lib/types";

const SUCCESSOR_STEPS = [
  { id: "welcome", title: "1. Welcome & Handover Scope", icon: FolderKanban },
  { id: "understand", title: "2. Understand the Project", icon: BookOpen },
  { id: "responsibilities", title: "3. Responsibilities & People", icon: Users },
  { id: "attention", title: "4. What Needs Your Attention", icon: AlertTriangle },
  { id: "decisions", title: "5. Decisions & Tech Guidance", icon: Layers },
  { id: "evidence", title: "6. Explore Evidence & Ask", icon: Database },
  { id: "acknowledge", title: "7. Ready & Acknowledgement", icon: ClipboardCheck },
] as const;

type StepId = (typeof SUCCESSOR_STEPS)[number]["id"];

function resolveMemberName(
  userId: string | null | undefined,
  members: ProjectMember[],
  fallback = "Not designated"
): string {
  if (!userId) return fallback;
  const m = members.find((mem) => mem.user_id === userId);
  if (!m) return userId;
  return m.full_name ? `${m.full_name}${m.email ? ` (${m.email})` : ""}` : m.email || userId;
}

function getSection(
  sections: HandoverMandatorySection[],
  ...keys: string[]
): HandoverMandatorySection | undefined {
  for (const key of keys) {
    const found = sections.find((s) => s.section_key === key);
    if (found) return found;
  }
  return undefined;
}

function normalizeInlineBullets(text: string): string {
  return (text || "").replace(/\s+-\s+(?=\*\*|`|\[)/g, "\n- ");
}

function formatDate(iso?: string | null): string {
  if (!iso) return "Not set";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? String(iso) : d.toLocaleDateString();
}

export interface SuccessorHandoverOnboardingProps {
  projectId: string;
  project: Project;
  members: ProjectMember[];
  publishedCases: HandoverCaseItem[];
  initialCaseId?: string | null;
  initialVersionId?: string | null;
  onSwitchToOrientation: () => void;
}

export function SuccessorHandoverOnboarding({
  projectId,
  project,
  members,
  publishedCases,
  initialCaseId,
  initialVersionId,
  onSwitchToOrientation,
}: SuccessorHandoverOnboardingProps) {
  const router = useRouter();
  const { user } = useLiveApp();

  const [selectedCaseId, setSelectedCaseId] = useState<string>(() => {
    if (initialCaseId && publishedCases.some((c) => c.id === initialCaseId)) {
      return initialCaseId;
    }
    return publishedCases[0]?.id ?? "";
  });
  const [selectedVersionId, setSelectedVersionId] = useState<string>(initialVersionId || "");
  const [versions, setVersions] = useState<HandoverPackageVersionSummary[]>([]);
  const [caseDetail, setCaseDetail] = useState<{
    case: Record<string, unknown>;
    responsibility_transfers: HandoverResponsibilityTransferDetail[];
  } | null>(null);
  const [sectionsData, setSectionsData] = useState<HandoverVersionSectionsResponse | null>(null);
  const [transfers, setTransfers] = useState<HandoverResponsibilityTransferDetail[]>([]);
  const [deliveries, setDeliveries] = useState<HandoverDeliveryRecord[]>([]);

  const [stepIndex, setStepIndex] = useState(0);
  const [isLoadingPackage, setIsLoadingPackage] = useState(true);
  const [packageError, setPackageError] = useState<string | null>(null);

  const [completedSteps, setCompletedSteps] = useState<Record<string, boolean>>({});
  const [stepTimestamps, setStepTimestamps] = useState<Record<string, string | null>>({});
  const [isSavingStep, setIsSavingStep] = useState(false);
  const [saveFeedback, setSaveFeedback] = useState<string | null>(null);

  // Interactive actions
  const [copiedPrompt, setCopiedPrompt] = useState<string | null>(null);
  const [clarifyingTransferId, setClarifyingTransferId] = useState<string | null>(null);
  const [clarifyNote, setClarifyNote] = useState("");
  const [isSubmittingClarify, setIsSubmittingClarify] = useState(false);
  const [deliveryClarifyOpen, setDeliveryClarifyOpen] = useState(false);
  const [deliveryClarifyNote, setDeliveryClarifyNote] = useState("");
  const [ackNotes, setAckNotes] = useState("");
  const [isAcknowledging, setIsAcknowledging] = useState(false);
  const [actionBanner, setActionBanner] = useState<{ tone: "green" | "red"; text: string } | null>(
    null
  );

  const activeCase = useMemo(
    () => publishedCases.find((c) => c.id === selectedCaseId) ?? publishedCases[0] ?? null,
    [publishedCases, selectedCaseId]
  );

  // Sync if publishedCases changes
  useEffect(() => {
    if (!selectedCaseId && publishedCases[0]) {
      setSelectedCaseId(publishedCases[0].id);
    }
  }, [publishedCases, selectedCaseId]);

  const loadHandoverPackage = useCallback(async () => {
    if (!activeCase) return;
    const knownVersionId = selectedVersionId || activeCase.current_version_id || "";
    const pkgCacheKey = `succ_handover_pkg:${projectId}:${activeCase.id}:${knownVersionId || "cur"}`;
    type CachedPkg = {
      caseDetail: {
        case: Record<string, unknown>;
        responsibility_transfers: HandoverResponsibilityTransferDetail[];
      };
      versions: HandoverPackageVersionSummary[];
      resolvedVersionId: string;
      transfers: HandoverResponsibilityTransferDetail[];
      sectionsData: HandoverVersionSectionsResponse | null;
      deliveries: HandoverDeliveryRecord[];
      completedSteps: Record<string, boolean>;
      stepTimestamps: Record<string, string | null>;
    };
    const cachedPkg = getCachedGraph<CachedPkg>(pkgCacheKey, undefined, user?.id);
    if (cachedPkg) {
      setCaseDetail(cachedPkg.caseDetail);
      setVersions(cachedPkg.versions);
      if (cachedPkg.resolvedVersionId && cachedPkg.resolvedVersionId !== selectedVersionId) {
        setSelectedVersionId(cachedPkg.resolvedVersionId);
      }
      setTransfers(cachedPkg.transfers);
      setSectionsData(cachedPkg.sectionsData);
      setDeliveries(cachedPkg.deliveries);
      setCompletedSteps(cachedPkg.completedSteps);
      setStepTimestamps(cachedPkg.stepTimestamps);
      setIsLoadingPackage(false);
    } else {
      setIsLoadingPackage(true);
    }
    setPackageError(null);
    setSaveFeedback(null);
    setActionBanner(null);
    try {
      // Single-wave parallel fetch when knownVersionId is already available from activeCase
      const [detailRes, versionsRes, respWorkspace, prefetchedSec, prefetchedSignoff, prefetchedProg] =
        await Promise.all([
          api.handover.getCase(projectId, activeCase.id),
          api.handover.getVersions(projectId, activeCase.id).catch(() => []),
          api.handover.getResponsibilityWorkspace(projectId, activeCase.id).catch(() => null),
          knownVersionId
            ? api.handover.getVersionSections(projectId, activeCase.id, knownVersionId)
            : Promise.resolve(null),
          knownVersionId
            ? api.handover.getSignoffWorkspace(projectId, activeCase.id, knownVersionId).catch(() => null)
            : Promise.resolve(null),
          knownVersionId
            ? api.onboarding
                .getProgress(projectId, undefined, {
                  caseId: activeCase.id,
                  versionId: knownVersionId,
                })
                .catch(() => null)
            : Promise.resolve(null),
        ]);

      const nextCaseDetail = {
        case: detailRes.case as Record<string, unknown>,
        responsibility_transfers: (detailRes.responsibility_transfers ||
          []) as HandoverResponsibilityTransferDetail[],
      };
      setCaseDetail(nextCaseDetail);

      const publishedVersions = (versionsRes || []).filter(
        (v) => v.is_current || v.assembly_status === "published" || v.assembly_status === "assembled"
      );
      const effectiveVersions =
        publishedVersions.length > 0 ? publishedVersions : versionsRes || [];
      setVersions(effectiveVersions);

      const chosenVersion =
        effectiveVersions.find((v) => v.id === selectedVersionId) ||
        effectiveVersions.find((v) => v.assembly_status === "published") ||
        effectiveVersions.find((v) => v.id === activeCase.current_version_id) ||
        effectiveVersions[0] ||
        null;

      const resolvedVersionId = chosenVersion?.id || "";
      if (resolvedVersionId !== selectedVersionId) {
        setSelectedVersionId(resolvedVersionId);
      }

      const nextTransfers = respWorkspace?.transfers
        ? respWorkspace.transfers
        : ((detailRes.responsibility_transfers || []) as HandoverResponsibilityTransferDetail[]);
      setTransfers(nextTransfers);

      if (resolvedVersionId) {
        const usePrefetched = resolvedVersionId === knownVersionId && prefetchedSec !== null;
        const [secRes, signoffRes, progressRes] = usePrefetched
          ? [prefetchedSec, prefetchedSignoff, prefetchedProg]
          : await Promise.all([
              api.handover.getVersionSections(projectId, activeCase.id, resolvedVersionId),
              api.handover
                .getSignoffWorkspace(projectId, activeCase.id, resolvedVersionId)
                .catch(() => null),
              api.onboarding
                .getProgress(projectId, undefined, {
                  caseId: activeCase.id,
                  versionId: resolvedVersionId,
                })
                .catch(() => null),
            ]);
        setSectionsData(secRes);
        const pubDeliveries =
          (signoffRes?.publication as { deliveries?: HandoverDeliveryRecord[] } | undefined)
            ?.deliveries || [];
        setDeliveries(pubDeliveries);

        const map: Record<string, boolean> = { ...(progressRes?.completed_steps || {}) };
        const tsMap: Record<string, string | null> = {};
        for (const item of progressRes?.items || []) {
          tsMap[item.step_id] = item.completed_at ?? null;
        }
        setCompletedSteps(map);
        setStepTimestamps(tsMap);

        setCachedGraph(
          pkgCacheKey,
          {
            caseDetail: nextCaseDetail,
            versions: effectiveVersions,
            resolvedVersionId,
            transfers: nextTransfers,
            sectionsData: secRes,
            deliveries: pubDeliveries,
            completedSteps: map,
            stepTimestamps: tsMap,
          },
          user?.id
        );
      } else {
        setSectionsData(null);
        setDeliveries([]);
        setCompletedSteps({});
        setStepTimestamps({});
      }
    } catch (err: unknown) {
      if (!cachedPkg) {
        setPackageError(
          err instanceof Error ? err.message : "Unable to load published handover package."
        );
      }
    } finally {
      setIsLoadingPackage(false);
    }
  }, [activeCase, projectId, selectedVersionId, user?.id]);

  useEffect(() => {
    void loadHandoverPackage();
  }, [loadHandoverPackage]);

  const activeVersion = useMemo(
    () => versions.find((v) => v.id === selectedVersionId) || versions[0] || null,
    [selectedVersionId, versions]
  );

  const myDelivery = useMemo(() => {
    if (!deliveries.length) return null;
    if (user?.id) {
      const mine = deliveries.find((d) => d.delivered_to_user_id === user.id);
      if (mine) return mine;
    }
    return deliveries[0] || null;
  }, [deliveries, user?.id]);

  const isAlreadyAcknowledged = Boolean(
    myDelivery?.acknowledged ||
      myDelivery?.acknowledgement ||
      activeCase?.status.toLowerCase() === "completed"
  );

  const toggleStepReviewed = useCallback(
    async (stepId: StepId, nextVal: boolean) => {
      if (!activeCase || !activeVersion) return;
      setIsSavingStep(true);
      setSaveFeedback(null);
      setCompletedSteps((prev) => ({ ...prev, [stepId]: nextVal }));
      try {
        const res = await api.onboarding.updateStep(projectId, stepId, nextVal, {
          caseId: activeCase.id,
          versionId: activeVersion.id,
        });
        setStepTimestamps((prev) => ({ ...prev, [stepId]: res.completed_at ?? null }));
      } catch (err: unknown) {
        setCompletedSteps((prev) => ({ ...prev, [stepId]: !nextVal }));
        setSaveFeedback(
          err instanceof Error ? `Failed to save progress: ${err.message}` : "Failed to save progress."
        );
      } finally {
        setIsSavingStep(false);
      }
    },
    [activeCase, activeVersion, projectId]
  );

  const handleResetChecklist = useCallback(async () => {
    if (!activeCase || !activeVersion) return;
    setIsSavingStep(true);
    setSaveFeedback(null);
    const doneIds = Object.entries(completedSteps)
      .filter(([, done]) => done)
      .map(([id]) => id);
    try {
      await Promise.all(
        doneIds.map((id) =>
          api.onboarding
            .deleteStep(projectId, id, { caseId: activeCase.id, versionId: activeVersion.id })
            .catch(() => {})
        )
      );
      setCompletedSteps({});
      setStepTimestamps({});
    } catch (err: unknown) {
      setSaveFeedback(err instanceof Error ? err.message : "Unable to reset checklist.");
    } finally {
      setIsSavingStep(false);
    }
  }, [activeCase, activeVersion, completedSteps, projectId]);

  const handleAcceptResponsibility = async (transferId: string) => {
    setActionBanner(null);
    try {
      const updated = await api.handover.acknowledgeResponsibilitySuccessor(projectId, transferId, {
        acknowledgement_notes: "Reviewed and accepted during Successor Onboarding.",
      });
      setTransfers((prev) => prev.map((t) => (t.id === transferId ? updated : t)));
      setActionBanner({ tone: "green", text: "Responsibility acceptance recorded." });
    } catch (err: unknown) {
      setActionBanner({
        tone: "red",
        text: err instanceof Error ? err.message : "Unable to record responsibility acceptance.",
      });
    }
  };

  const handleRequestTransferClarification = async (transferId: string) => {
    if (!clarifyNote.trim()) return;
    setIsSubmittingClarify(true);
    setActionBanner(null);
    try {
      const updated = await api.handover.clarifyResponsibility(projectId, transferId, {
        notes: clarifyNote.trim(),
        mode: "request",
      });
      setTransfers((prev) => prev.map((t) => (t.id === transferId ? updated : t)));
      setClarifyingTransferId(null);
      setClarifyNote("");
      setActionBanner({ tone: "green", text: "Clarification request sent to reviewer/owner." });
    } catch (err: unknown) {
      setActionBanner({
        tone: "red",
        text: err instanceof Error ? err.message : "Unable to send clarification request.",
      });
    } finally {
      setIsSubmittingClarify(false);
    }
  };

  const handleRequestDeliveryClarification = async () => {
    if (!myDelivery || !deliveryClarifyNote.trim()) return;
    setIsSubmittingClarify(true);
    setActionBanner(null);
    try {
      const updated = await api.handover.clarifyDelivery(projectId, myDelivery.id, {
        notes: deliveryClarifyNote.trim(),
        mode: "request",
      });
      setDeliveries((prev) => prev.map((d) => (d.id === updated.id ? updated : d)));
      setDeliveryClarifyOpen(false);
      setDeliveryClarifyNote("");
      setActionBanner({
        tone: "green",
        text: "Package clarification request recorded without altering the published snapshot.",
      });
    } catch (err: unknown) {
      setActionBanner({
        tone: "red",
        text: err instanceof Error ? err.message : "Unable to submit clarification request.",
      });
    } finally {
      setIsSubmittingClarify(false);
    }
  };

  const handleAcknowledgePackage = async () => {
    if (!myDelivery || isAlreadyAcknowledged) return;
    setIsAcknowledging(true);
    setActionBanner(null);
    try {
      await api.handover.acknowledgeDelivery(projectId, myDelivery.id, {
        acknowledgement_notes:
          ackNotes.trim() || "I acknowledge receiving this published Handover package.",
        expected_content_hash: activeVersion?.content_hash ?? undefined,
      });
      setDeliveries((prev) =>
        prev.map((d) =>
          d.id === myDelivery.id
            ? {
                ...d,
                acknowledged: true,
                acknowledgement: {
                  id: "ack-recorded",
                  delivery_id: myDelivery.id,
                  acknowledged_by_user_id: user?.id || "",
                  acknowledged_at: new Date().toISOString(),
                } as HandoverDeliveryRecord["acknowledgement"],
              }
            : d
        )
      );
      setActionBanner({
        tone: "green",
        text: "Formal receipt acknowledgement recorded.",
      });
    } catch (err: unknown) {
      setActionBanner({
        tone: "red",
        text: err instanceof Error ? err.message : "Unable to acknowledge handover package.",
      });
    } finally {
      setIsAcknowledging(false);
    }
  };

  const handleCopyPrompt = async (prompt: string) => {
    try {
      await navigator.clipboard.writeText(prompt);
      setCopiedPrompt(prompt);
      setTimeout(() => setCopiedPrompt(null), 1800);
    } catch {
      // ignore
    }
  };

  const currentStep = SUCCESSOR_STEPS[stepIndex] ?? SUCCESSOR_STEPS[0];
  const completedCount = useMemo(
    () => SUCCESSOR_STEPS.filter((s) => Boolean(completedSteps[s.id])).length,
    [completedSteps]
  );
  const completionPct = Math.round((completedCount / SUCCESSOR_STEPS.length) * 100);

  const mandatorySections = sectionsData?.mandatory_sections || [];
  const secOverview = getSection(mandatorySections, "project_overview", "executive_overview");
  const secArch = getSection(mandatorySections, "architecture_technical_context", "architecture_technical");
  const secCompleted = getSection(mandatorySections, "completed_work");
  const secPending = getSection(mandatorySections, "pending_work");
  const secDecisions = getSection(mandatorySections, "important_decisions_rationale", "decisions_rationale");
  const secDeps = getSection(mandatorySections, "dependencies");
  const secRisks = getSection(mandatorySections, "risks_and_blockers", "risks_blockers");
  const secResp = getSection(mandatorySections, "responsibilities", "responsibilities_ownership");
  const secContacts = getSection(mandatorySections, "evidence_references", "contacts_escalation");
  const secNext = getSection(mandatorySections, "recommended_next_steps");

  const departingUserId =
    (caseDetail?.case?.departing_member_id as string | undefined) || activeCase?.departing_member_id;
  const successorUserId =
    (caseDetail?.case?.successor_id as string | undefined) || activeCase?.successor_id;
  const departingName = resolveMemberName(departingUserId, members, "Not designated on this case");
  const successorName = resolveMemberName(successorUserId, members, "Not designated on this case");

  // Project purpose: real project description, or approved overview item if description is empty
  const approvedOverviewItems = secOverview?.knowledge_items || [];
  const projectPurpose =
    project.description?.trim() ||
    (approvedOverviewItems[0]?.content ? String(approvedOverviewItems[0].content) : null);

  // Deduplicated evidence references grouped by section relevance
  const relevantEvidenceGroups = useMemo(() => {
    const groups: Array<{ label: string; refs: HandoverMandatorySection["evidence_references"] }> =
      [];
    const candidates: Array<{ label: string; sec?: HandoverMandatorySection }> = [
      { label: "Project & Architecture Documentation", sec: secArch },
      { label: "Project Overview & Context", sec: secOverview },
      { label: "Decisions & Rationale", sec: secDecisions },
      { label: "Pending Work & Open Tasks", sec: secPending },
      { label: "Risks, Blockers & Dependencies", sec: secRisks },
    ];
    for (const c of candidates) {
      const refs = c.sec?.evidence_references || [];
      if (refs.length > 0) {
        groups.push({ label: c.label, refs: refs.slice(0, 6) });
      }
    }
    return groups;
  }, [secArch, secDecisions, secOverview, secPending, secRisks]);

  const firstIncompleteIdx = SUCCESSOR_STEPS.findIndex((s) => !completedSteps[s.id]);
  const hasClarificationPending = Boolean(
    (myDelivery?.clarifications?.length || 0) > 0 ||
      transfers.some((t) => t.transfer_status === "clarification_requested")
  );

  return (
    <div className="space-y-6">
      {/* Header (Preserved Design System 2.0 layout) */}
      <div className="flex flex-col justify-between gap-4 rounded-2xl border border-line bg-white p-5 shadow-2xs sm:flex-row sm:items-center">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2 text-xs font-semibold uppercase tracking-wider text-brand">
            <Sparkles className="size-3.5" />
            <span>Successor Handover Onboarding</span>
            {activeVersion && (
              <Badge tone="blue">Published v{activeVersion.version_number}</Badge>
            )}
            {isSavingStep && (
              <span className="inline-flex items-center gap-1 text-[11px] font-medium normal-case text-muted">
                <Loader2 className="size-3 animate-spin" /> Saving…
              </span>
            )}
          </div>
          <h1 className="mt-1 text-xl font-bold tracking-tight text-navy">
            {project.name}
            {activeCase ? ` — ${activeCase.title}` : ""}
          </h1>
          <div className="mt-2 flex flex-wrap items-center gap-3">
            <p className="text-xs text-muted">
              Step {stepIndex + 1} of {SUCCESSOR_STEPS.length}: {currentStep.title}
            </p>
            <span className="text-xs font-semibold text-navy">
              {completedCount}/{SUCCESSOR_STEPS.length} reviewed ({completionPct}%)
            </span>
          </div>
          <div className="mt-2 h-1.5 w-full max-w-md overflow-hidden rounded-full bg-slate-100">
            <div
              className="h-full rounded-full bg-brand transition-all duration-300"
              style={{ width: `${completionPct}%` }}
            />
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {publishedCases.length > 1 && (
            <select
              aria-label="Select published handover case"
              value={activeCase?.id || ""}
              onChange={(e) => {
                setSelectedCaseId(e.target.value);
                setSelectedVersionId("");
                setStepIndex(0);
              }}
              className="h-8 rounded-lg border border-line bg-white px-2.5 text-xs text-navy focus:border-brand focus:outline-none"
            >
              {publishedCases.map((hc) => (
                <option key={hc.id} value={hc.id}>
                  {hc.title}
                </option>
              ))}
            </select>
          )}
          {versions.length > 1 && (
            <select
              aria-label="Select published package version"
              value={activeVersion?.id || ""}
              onChange={(e) => {
                setSelectedVersionId(e.target.value);
                setStepIndex(0);
              }}
              className="h-8 rounded-lg border border-line bg-white px-2.5 text-xs text-navy focus:border-brand focus:outline-none"
            >
              {versions.map((v) => (
                <option key={v.id} value={v.id}>
                  Version v{v.version_number}
                </option>
              ))}
            </select>
          )}
          <Button variant="ghost" size="sm" icon={Compass} onClick={onSwitchToOrientation}>
            General Orientation
          </Button>
          {completedCount > 0 && (
            <Button
              variant="ghost"
              size="sm"
              icon={RotateCcw}
              disabled={isSavingStep}
              onClick={() => void handleResetChecklist()}
            >
              Reset
            </Button>
          )}
          <Link href={`/projects/${projectId}`}>
            <Button variant="secondary" size="sm" icon={ArrowLeft}>
              Project Workspace
            </Button>
          </Link>
        </div>
      </div>

      {saveFeedback && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-2.5 text-xs text-red-700">
          {saveFeedback}
        </div>
      )}

      {actionBanner && (
        <div
          className={`rounded-xl border px-4 py-2.5 text-xs ${
            actionBanner.tone === "green"
              ? "border-emerald-200 bg-emerald-50 text-emerald-800"
              : "border-red-200 bg-red-50 text-red-700"
          }`}
        >
          {actionBanner.text}
        </div>
      )}

      {isLoadingPackage ? (
        <Card className="p-8 text-center text-xs text-muted">
          <Loader2 className="mx-auto mb-2 size-5 animate-spin text-brand" />
          Loading published Handover package…
        </Card>
      ) : packageError ? (
        <Card className="p-6">
          <div className="flex items-start gap-3 text-sm text-red-700">
            <AlertCircle className="mt-0.5 size-5 shrink-0" />
            <div>
              <p className="font-semibold">Unable to load published handover</p>
              <p className="mt-1 text-xs">{packageError}</p>
            </div>
          </div>
        </Card>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
          {/* Left 7-Step Sidebar */}
          <Card className="h-fit p-3">
            <ul className="space-y-1">
              {SUCCESSOR_STEPS.map((s, idx) => {
                const Icon = s.icon;
                const active = idx === stepIndex;
                const done = !!completedSteps[s.id];
                return (
                  <li key={s.id}>
                    <button
                      type="button"
                      onClick={() => setStepIndex(idx)}
                      className={`flex w-full items-center gap-2.5 rounded-xl px-3 py-2.5 text-left text-xs font-medium transition ${
                        active
                          ? "bg-brand/10 font-semibold text-brand"
                          : "text-navy hover:bg-slate-50"
                      }`}
                    >
                      <span
                        className={`flex size-6 shrink-0 items-center justify-center rounded-full border ${
                          done
                            ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                            : active
                              ? "border-brand bg-brand text-white"
                              : "border-line bg-white text-muted"
                        }`}
                      >
                        {done ? <Check className="size-3.5" /> : <Icon className="size-3.5" />}
                      </span>
                      <span className="truncate">{s.title}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </Card>

          {/* Main Step Content */}
          <Card className="p-6">
            {/* STEP 1 — WELCOME & HANDOVER SCOPE */}
            {currentStep.id === "welcome" && (
              <div className="space-y-4">
                <CardHeader
                  title="Welcome & Handover Scope"
                  subtitle="Published handover package details and transition participants"
                  icon={FolderKanban}
                />

                <div className="space-y-2 rounded-xl border border-line bg-slate-50/70 p-4 text-xs text-navy">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone="green">
                      {activeCase?.status.toLowerCase() === "completed"
                        ? "Published · Acknowledged"
                        : "Published Handover"}
                    </Badge>
                    <Badge tone="blue">
                      {sectionsData?.handover_type_label ||
                        (activeCase?.handover_type || "developer").replace(/_/g, " ")}
                    </Badge>
                    {activeVersion && (
                      <span className="text-muted">
                        Version <strong>v{activeVersion.version_number}</strong> · Published{" "}
                        {formatDate(activeVersion.assembled_at || activeVersion.created_at)}
                      </span>
                    )}
                    {activeCase?.target_handover_date && (
                      <span className="text-muted">
                        · Due <strong>{formatDate(activeCase.target_handover_date)}</strong>
                      </span>
                    )}
                  </div>
                  <p className="leading-relaxed text-slate-700">
                    {projectPurpose ||
                      "No approved project purpose or description has been recorded yet."}
                  </p>
                  {sectionsData?.role_focus_summary && (
                    <p className="text-muted">{sectionsData.role_focus_summary}</p>
                  )}
                </div>

                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="rounded-xl border border-line p-4 text-xs">
                    <p className="font-semibold text-navy">Departing Member</p>
                    <p className="mt-1 text-muted">{departingName}</p>
                  </div>
                  <div className="rounded-xl border border-line p-4 text-xs">
                    <p className="font-semibold text-navy">Incoming Successor</p>
                    <p className="mt-1 text-muted">{successorName}</p>
                  </div>
                </div>

                <div className="rounded-xl border border-line p-4 text-xs">
                  <p className="font-semibold text-navy">What you&apos;re taking over</p>
                  {transfers.length > 0 ? (
                    <ul className="mt-2 space-y-1.5">
                      {transfers.slice(0, 5).map((t) => (
                        <li key={t.id} className="flex items-start gap-2 text-slate-700">
                          <CheckCircle2 className="mt-0.5 size-3.5 shrink-0 text-brand" />
                          <span>
                            <strong>{t.title || t.component_name || "Responsibility"}:</strong>{" "}
                            {t.responsibility_description}
                          </span>
                        </li>
                      ))}
                    </ul>
                  ) : approvedOverviewItems.length > 0 ? (
                    <ul className="mt-2 space-y-1.5">
                      {approvedOverviewItems.slice(0, 3).map((ki, i) => (
                        <li key={i} className="flex items-start gap-2 text-slate-700">
                          <CheckCircle2 className="mt-0.5 size-3.5 shrink-0 text-brand" />
                          <span>{String(ki.title || ki.content)}</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="mt-1 text-muted">
                      No explicit responsibility transfer records are attached to this case yet.
                    </p>
                  )}
                </div>
              </div>
            )}

            {/* STEP 2 — UNDERSTAND THE PROJECT */}
            {currentStep.id === "understand" && (
              <div className="space-y-4">
                <CardHeader
                  title="Understand the Project"
                  subtitle="Composed from the approved, published Handover package (no raw knowledge dump)"
                  icon={BookOpen}
                />

                <div className="space-y-3">
                  <div className="rounded-xl border border-line p-4 text-xs">
                    <p className="font-semibold text-navy">What does this project do?</p>
                    {approvedOverviewItems.length > 0 ? (
                      <ul className="mt-2 space-y-1.5 text-slate-700">
                        {approvedOverviewItems.slice(0, 4).map((ki, idx) => (
                          <li key={idx} className="rounded-lg bg-slate-50/70 p-2.5">
                            <p className="font-medium text-navy">{String(ki.title || "Overview")}</p>
                            <FormattedMarkdown
                              content={normalizeInlineBullets(String(ki.content || ""))}
                              className="mt-1 text-xs text-slate-700"
                            />
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="mt-1 text-muted">
                        {secOverview?.insufficient_info_message ||
                          projectPurpose ||
                          "Insufficient approved project overview findings in this package."}
                      </p>
                    )}
                  </div>

                  <div className="rounded-xl border border-line p-4 text-xs">
                    <p className="font-semibold text-navy">
                      How is it structured &amp; what technologies matter?
                    </p>
                    {(secArch?.knowledge_items?.length || 0) > 0 ? (
                      <ul className="mt-2 space-y-2 text-slate-700">
                        {(secArch?.knowledge_items || []).slice(0, 5).map((ki, idx) => (
                          <li key={idx} className="rounded-lg bg-slate-50/70 p-2.5">
                            <p className="font-medium text-navy">{String(ki.title || "Component")}</p>
                            <FormattedMarkdown
                              content={normalizeInlineBullets(String(ki.content || ""))}
                              className="mt-1 text-xs text-slate-700"
                            />
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="mt-1 text-muted">
                        {secArch?.insufficient_info_message ||
                          "No approved architecture items recorded in this package."}
                      </p>
                    )}
                  </div>

                  <div className="rounded-xl border border-line p-4 text-xs">
                    <p className="font-semibold text-navy">
                      What has been built &amp; current state?
                    </p>
                    {(secCompleted?.knowledge_items?.length || 0) > 0 ? (
                      <ul className="mt-2 space-y-1.5 text-slate-700">
                        {(secCompleted?.knowledge_items || []).slice(0, 4).map((ki, idx) => (
                          <li key={idx} className="rounded-lg bg-slate-50/70 p-2.5">
                            <p className="font-medium text-navy">{String(ki.title || "Deliverable")}</p>
                            <FormattedMarkdown
                              content={normalizeInlineBullets(String(ki.content || ""))}
                              className="mt-1 text-xs text-slate-700"
                            />
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="mt-1 text-muted">
                        {secCompleted?.insufficient_info_message ||
                          "No approved completed-work deliverables recorded in this package."}
                      </p>
                    )}
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-4 text-xs font-semibold">
                  <Link href={`/projects/${projectId}/overview`} className="text-brand hover:underline">
                    Project Overview →
                  </Link>
                  <Link
                    href={`/projects/${projectId}/intelligence`}
                    className="text-brand hover:underline"
                  >
                    Knowledge Intelligence &amp; Architecture →
                  </Link>
                  {activeCase && (
                    <Link
                      href={`/handovers/${activeCase.id}/report`}
                      className="text-navy hover:underline"
                    >
                      Full Handover Report →
                    </Link>
                  )}
                </div>
              </div>
            )}

            {/* STEP 3 — RESPONSIBILITIES & PEOPLE */}
            {currentStep.id === "responsibilities" && (
              <div className="space-y-4">
                <CardHeader
                  title="Responsibilities & People"
                  subtitle="Reviewed responsibility transfers, contacts, and unclear ownership"
                  icon={Users}
                />

                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="rounded-xl border border-line bg-slate-50/60 p-3.5 text-xs">
                    <p className="font-semibold text-navy">Departing Owner</p>
                    <p className="mt-1 text-muted">{departingName}</p>
                  </div>
                  <div className="rounded-xl border border-line bg-slate-50/60 p-3.5 text-xs">
                    <p className="font-semibold text-navy">Incoming Successor</p>
                    <p className="mt-1 text-muted">{successorName}</p>
                  </div>
                </div>

                {transfers.length > 0 ? (
                  <ul className="space-y-3">
                    {transfers.map((t) => (
                      <li key={t.id} className="rounded-xl border border-line p-4 text-xs">
                        <div className="flex flex-wrap items-start justify-between gap-2">
                          <div>
                            <p className="font-semibold text-navy">
                              {t.title || t.component_name || "Transferred Responsibility"}
                            </p>
                            <p className="mt-1 text-slate-700">{t.responsibility_description}</p>
                          </div>
                          <div className="flex flex-wrap gap-1.5">
                            <Badge tone={t.successor_acknowledged_at ? "green" : "amber"}>
                              {t.successor_acknowledged_at
                                ? "Accepted by successor"
                                : t.transfer_status.replace(/_/g, " ")}
                            </Badge>
                            {t.ownership_certainty && (
                              <Badge tone="gray">{t.ownership_certainty.replace(/_/g, " ")}</Badge>
                            )}
                          </div>
                        </div>

                        {(t.required_access || t.operational_context) && (
                          <div className="mt-2 space-y-1 text-muted">
                            {t.required_access && (
                              <p>
                                <strong>Access prerequisite:</strong> {t.required_access}
                              </p>
                            )}
                            {t.operational_context && (
                              <p>
                                <strong>Context:</strong> {t.operational_context}
                              </p>
                            )}
                          </div>
                        )}

                        <div className="mt-3 flex flex-wrap items-center gap-2">
                          {!t.successor_acknowledged_at && (
                            <Button
                              size="sm"
                              variant="primary"
                              onClick={() => void handleAcceptResponsibility(t.id)}
                            >
                              Accept Responsibility
                            </Button>
                          )}
                          <Button
                            size="sm"
                            variant="secondary"
                            icon={MessageSquarePlus}
                            onClick={() =>
                              setClarifyingTransferId(
                                clarifyingTransferId === t.id ? null : t.id
                              )
                            }
                          >
                            Request Clarification
                          </Button>
                        </div>

                        {clarifyingTransferId === t.id && (
                          <div className="mt-3 space-y-2 rounded-lg border border-line bg-slate-50 p-3">
                            <textarea
                              rows={2}
                              value={clarifyNote}
                              onChange={(e) => setClarifyNote(e.target.value)}
                              placeholder="Ask for missing access, ownership clarity, or context…"
                              className="w-full rounded-lg border border-line bg-white p-2 text-xs text-navy focus:border-brand focus:outline-none"
                            />
                            <div className="flex justify-end gap-2">
                              <Button
                                size="sm"
                                variant="ghost"
                                onClick={() => setClarifyingTransferId(null)}
                              >
                                Cancel
                              </Button>
                              <Button
                                size="sm"
                                disabled={isSubmittingClarify || !clarifyNote.trim()}
                                onClick={() => void handleRequestTransferClarification(t.id)}
                              >
                                Send Request
                              </Button>
                            </div>
                          </div>
                        )}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <div className="rounded-xl border border-dashed border-line p-4 text-xs text-muted">
                    {(secResp?.responsibilities_summary?.length || 0) > 0
                      ? "Responsibility summaries are listed in the Handover package, though no interactive transfer records are attached yet."
                      : secResp?.insufficient_info_message ||
                        "No reviewed responsibility transfer records are documented in this package yet."}
                  </div>
                )}

                {(secContacts?.knowledge_items?.length || 0) > 0 && (
                  <div className="rounded-xl border border-line p-4 text-xs">
                    <p className="font-semibold text-navy">Key Contacts &amp; Escalation</p>
                    <ul className="mt-2 space-y-3 text-slate-700">
                      {(secContacts?.knowledge_items || []).slice(0, 4).map((ki, i) => (
                        <li key={i} className="space-y-1">
                          <p className="font-semibold text-navy">
                            {String(ki.title || "Contact")}
                          </p>
                          <FormattedMarkdown
                            content={normalizeInlineBullets(String(ki.content || ""))}
                            className="space-y-1 text-slate-700"
                          />
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}

            {/* STEP 4 — WHAT NEEDS YOUR ATTENTION */}
            {currentStep.id === "attention" && (
              <div className="space-y-4">
                <CardHeader
                  title="What Needs Your Attention"
                  subtitle="Open work, blockers, dependencies, and recommended next actions from the published package"
                  icon={AlertTriangle}
                />

                {[
                  {
                    heading: "Open & Pending Work",
                    items: secPending?.knowledge_items || [],
                    emptyMsg:
                      secPending?.insufficient_info_message ||
                      "No approved pending work items are recorded in this package.",
                    tone: "blue" as const,
                  },
                  {
                    heading: "Risks & Blockers",
                    items: secRisks?.knowledge_items || [],
                    emptyMsg:
                      secRisks?.insufficient_info_message ||
                      "No approved risks or blockers are recorded in this package.",
                    tone: "amber" as const,
                  },
                  {
                    heading: "Dependencies",
                    items: secDeps?.knowledge_items || [],
                    emptyMsg:
                      secDeps?.insufficient_info_message ||
                      "No evidence-supported dependencies are recorded in this package.",
                    tone: "gray" as const,
                  },
                ].map((group) => (
                  <div key={group.heading} className="space-y-2">
                    <div className="flex items-center gap-2">
                      <h3 className="text-xs font-semibold uppercase tracking-wide text-navy">
                        {group.heading}
                      </h3>
                      <Badge tone={group.tone}>{group.items.length}</Badge>
                    </div>
                    {group.items.length === 0 ? (
                      <div className="rounded-xl border border-dashed border-line p-3.5 text-xs text-muted">
                        {group.emptyMsg}
                      </div>
                    ) : (
                      <ul className="space-y-2">
                        {group.items.slice(0, 6).map((ki, idx) => (
                          <li key={idx} className="rounded-xl border border-line p-3.5 text-xs">
                            <p className="font-semibold text-navy">
                              {String(ki.title || "Item")}
                            </p>
                            <FormattedMarkdown
                              content={normalizeInlineBullets(String(ki.content || ""))}
                              className="mt-1.5 text-xs leading-relaxed text-slate-700"
                            />
                            {Array.isArray(ki.provenance) && ki.provenance.length > 0 && (
                              <p className="mt-1.5 text-[11px] text-muted">
                                Evidence:{" "}
                                {ki.provenance
                                  .map((p) => p.source_name || p.source_type || "Source")
                                  .join(", ")}
                              </p>
                            )}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                ))}

                {(secNext?.recommended_steps?.length || 0) > 0 && (
                  <div className="space-y-2">
                    <h3 className="text-xs font-semibold uppercase tracking-wide text-navy">
                      Follow-up Actions
                    </h3>
                    <ul className="space-y-1.5">
                      {(secNext?.recommended_steps || []).map((st, idx) => (
                        <li
                          key={idx}
                          className="flex items-center justify-between gap-2 rounded-xl border border-line px-3.5 py-2.5 text-xs"
                        >
                          <span className="font-medium text-navy">
                            {String(st.title || "Next action")}
                          </span>
                          <Badge tone="blue">{String(st.status || "pending")}</Badge>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}

            {/* STEP 5 — IMPORTANT DECISIONS & TECHNICAL GUIDANCE */}
            {currentStep.id === "decisions" && (
              <div className="space-y-4">
                <CardHeader
                  title="Important Decisions & Technical Guidance"
                  subtitle="Approved architectural decisions, rationale, trade-offs, and operational context"
                  icon={Layers}
                />

                {(secDecisions?.knowledge_items?.length || 0) > 0 ? (
                  <ul className="space-y-3">
                    {(secDecisions?.knowledge_items || []).slice(0, 8).map((ki, idx) => (
                      <li key={idx} className="rounded-xl border border-line p-4 text-xs">
                        <div className="flex items-center justify-between gap-2">
                          <p className="font-semibold text-navy">
                            {String(ki.title || "Technical Decision")}
                          </p>
                          <Badge tone="green">Approved</Badge>
                        </div>
                        <FormattedMarkdown
                          content={normalizeInlineBullets(String(ki.content || ""))}
                          className="mt-1.5 text-xs leading-relaxed text-slate-700"
                        />
                        {Array.isArray(ki.provenance) && ki.provenance.length > 0 && (
                          <p className="mt-2 text-[11px] text-muted">
                            Source:{" "}
                            {ki.provenance
                              .map((p) => p.source_name || p.source_type || "Evidence")
                              .join(", ")}
                          </p>
                        )}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <div className="rounded-xl border border-dashed border-line p-5 text-xs text-muted">
                    {secDecisions?.insufficient_info_message ||
                      "No human-verified technical decisions with rationale are recorded in this version."}
                  </div>
                )}

                {(secArch?.knowledge_items?.length || 0) > 0 && (
                  <div className="space-y-2.5">
                    <p className="text-xs font-semibold uppercase tracking-wider text-muted">
                      Technical &amp; Architectural Guidance ({secArch?.knowledge_items?.length || 0})
                    </p>
                    <ul className="space-y-2.5">
                      {(secArch?.knowledge_items || []).slice(0, 6).map((ki, idx) => (
                        <li key={idx} className="rounded-xl border border-line p-4 text-xs">
                          <div className="flex items-center justify-between gap-2">
                            <p className="font-semibold text-navy">
                              {String(ki.title || "Architecture & Technical Context")}
                            </p>
                            <Badge tone="blue">Architecture</Badge>
                          </div>
                          <FormattedMarkdown
                            content={normalizeInlineBullets(String(ki.content || ""))}
                            className="mt-1.5 text-xs leading-relaxed text-slate-700"
                          />
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {(secArch?.evidence_references?.length || 0) > 0 && (
                  <div className="rounded-xl border border-line bg-slate-50/70 p-4 text-xs">
                    <p className="font-semibold text-navy">
                      Technical &amp; Operational Reference Documents
                    </p>
                    <ul className="mt-2 space-y-1 text-slate-700">
                      {(secArch?.evidence_references || []).slice(0, 5).map((ev, i) => (
                        <li key={i} className="flex items-center gap-2">
                          <FileText className="size-3.5 text-brand" />
                          <span>
                            {ev.source_name || "Document"} (
                            {ev.source_provider || ev.source_type || "source"})
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}

            {/* STEP 6 — EXPLORE EVIDENCE & ASK QUESTIONS */}
            {currentStep.id === "evidence" && (
              <div className="space-y-4">
                <CardHeader
                  title="Explore Evidence & Ask Questions"
                  subtitle="Evidence references organised by Handover relevance, plus optional AI Assistant"
                  icon={Database}
                />

                {relevantEvidenceGroups.length > 0 ? (
                  <div className="space-y-3">
                    {relevantEvidenceGroups.map((grp) => (
                      <div key={grp.label} className="rounded-xl border border-line p-3.5 text-xs">
                        <p className="font-semibold text-navy">{grp.label}</p>
                        <ul className="mt-2 space-y-1.5">
                          {grp.refs.map((ev, idx) => (
                            <li
                              key={idx}
                              className="flex items-center justify-between gap-2 text-slate-700"
                            >
                              <span className="truncate">
                                {ev.source_name || "Evidence item"}
                              </span>
                              <Badge tone="gray">
                                {ev.source_provider || ev.source_type || "source"}
                              </Badge>
                            </li>
                          ))}
                        </ul>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="rounded-xl border border-dashed border-line p-4 text-xs text-muted">
                    No linked evidence references are attached to this package version yet.
                  </div>
                )}

                <div className="flex flex-wrap items-center gap-4 text-xs font-semibold">
                  <Link
                    href={`/projects/${projectId}/evidence`}
                    className="inline-flex items-center gap-1 text-brand hover:underline"
                  >
                    Open Evidence Center <ExternalLink className="size-3" />
                  </Link>
                  <Link
                    href={`/projects/${projectId}/relationships`}
                    className="inline-flex items-center gap-1 text-navy hover:underline"
                  >
                    <GitBranch className="size-3" /> Open Relationship Explorer
                  </Link>
                </div>

                <div className="space-y-2 border-t border-line pt-4">
                  <p className="text-xs font-semibold text-navy">
                    Ask the Handover Knowledge Assistant (Optional — Ollama runs only when you ask)
                  </p>
                  {[
                    "What are the most important pending tasks in this Handover?",
                    "Which technical decisions affect the work I'm taking over?",
                    "Which known blockers should I investigate first?",
                    "What are my confirmed responsibilities?",
                  ].map((prompt) => {
                    const isCopied = copiedPrompt === prompt;
                    return (
                      <button
                        key={prompt}
                        type="button"
                        onClick={() => void handleCopyPrompt(prompt)}
                        className="flex w-full items-center justify-between gap-3 rounded-xl border border-line bg-slate-50/70 p-3 text-left text-xs text-navy transition hover:border-brand/40"
                      >
                        <span>&ldquo;{prompt}&rdquo;</span>
                        <span className="inline-flex shrink-0 items-center gap-1 text-[11px] font-medium text-brand">
                          {isCopied ? (
                            <>
                              <Check className="size-3" /> Copied
                            </>
                          ) : (
                            <>
                              <Copy className="size-3" /> Copy
                            </>
                          )}
                        </span>
                      </button>
                    );
                  })}
                  <div className="flex flex-wrap items-center gap-2 pt-1">
                    {activeCase && (
                      <Link href={`/handovers/${activeCase.id}/assistant`}>
                        <Button variant="primary" size="sm" icon={Bot}>
                          Open Handover Assistant
                        </Button>
                      </Link>
                    )}
                    <Link href="/assistant">
                      <Button variant="secondary" size="sm" icon={Bot}>
                        Open Project Assistant
                      </Button>
                    </Link>
                  </div>
                </div>
              </div>
            )}

            {/* STEP 7 — READY TO CONTINUE & ACKNOWLEDGEMENT */}
            {currentStep.id === "acknowledge" && (
              <div className="space-y-4">
                <CardHeader
                  title="Ready to Continue & Acknowledgement"
                  subtitle="Review your completed activities and formally acknowledge receipt when ready"
                  icon={ClipboardCheck}
                />

                {hasClarificationPending && (
                  <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
                    There is an open clarification request on this Handover. You can still review
                    and enter the workspace, or wait for a response before acknowledging receipt.
                  </div>
                )}

                <ul className="space-y-2">
                  {SUCCESSOR_STEPS.slice(0, -1).map((step, idx) => {
                    const isDone = Boolean(completedSteps[step.id]);
                    const ts = stepTimestamps[step.id];
                    return (
                      <li
                        key={step.id}
                        className="flex items-center justify-between gap-3 rounded-xl border border-line px-3.5 py-2.5 text-xs"
                      >
                        <button
                          type="button"
                          onClick={() => setStepIndex(idx)}
                          className="flex items-center gap-2.5 text-left hover:underline"
                        >
                          <span
                            className={`flex size-5 items-center justify-center rounded-full ${
                              isDone
                                ? "bg-emerald-100 text-emerald-700"
                                : "bg-slate-100 text-muted"
                            }`}
                          >
                            {isDone ? (
                              <Check className="size-3" />
                            ) : (
                              <span className="size-1.5 rounded-full bg-slate-400" />
                            )}
                          </span>
                          <span className="font-medium text-navy">{step.title}</span>
                        </button>
                        <div className="flex items-center gap-2">
                          {ts && (
                            <span className="hidden text-[11px] text-muted sm:inline">
                              {formatDate(ts)}
                            </span>
                          )}
                          <button
                            type="button"
                            onClick={() => void toggleStepReviewed(step.id, !isDone)}
                            className="text-[11px] font-semibold text-brand hover:underline"
                          >
                            {isDone ? "Mark pending" : "Mark reviewed"}
                          </button>
                        </div>
                      </li>
                    );
                  })}
                </ul>

                <div className="rounded-xl border border-line bg-slate-50/70 p-4 text-xs space-y-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="font-semibold text-navy">Formal Package Acknowledgement</p>
                    {isAlreadyAcknowledged && (
                      <Badge tone="green">
                        Receipt Acknowledged{" "}
                        {myDelivery?.acknowledgement?.acknowledged_at
                          ? `· ${formatDate(myDelivery.acknowledgement.acknowledged_at)}`
                          : ""}
                      </Badge>
                    )}
                  </div>
                  <p className="text-muted">
                    Acknowledgement is separate from checklist completion and does not imply you
                    have mastered every detail—it confirms receipt of this published package.
                  </p>
                  {!isAlreadyAcknowledged && myDelivery && (
                    <>
                      <textarea
                        rows={2}
                        value={ackNotes}
                        onChange={(e) => setAckNotes(e.target.value)}
                        placeholder="Optional acknowledgement notes…"
                        className="w-full rounded-lg border border-line bg-white p-2 text-xs text-navy focus:border-brand focus:outline-none"
                      />
                      <Button
                        variant="primary"
                        size="sm"
                        icon={ShieldCheck}
                        disabled={isAcknowledging}
                        onClick={() => void handleAcknowledgePackage()}
                      >
                        {isAcknowledging
                          ? "Recording Acknowledgement…"
                          : "I acknowledge receiving this published Handover package."}
                      </Button>
                    </>
                  )}
                  {!myDelivery && !isAlreadyAcknowledged && (
                    <p className="text-muted">
                      No direct delivery record is attached to your account for this version; open
                      the Recipient View if you need to inspect delivery status.
                    </p>
                  )}
                </div>

                {deliveryClarifyOpen && myDelivery && (
                  <div className="space-y-2 rounded-xl border border-line bg-slate-50 p-3.5 text-xs">
                    <p className="font-semibold text-navy">Request Package Clarification</p>
                    <textarea
                      rows={2}
                      value={deliveryClarifyNote}
                      onChange={(e) => setDeliveryClarifyNote(e.target.value)}
                      placeholder="Describe what needs clarification in this published handover…"
                      className="w-full rounded-lg border border-line bg-white p-2 text-xs text-navy focus:border-brand focus:outline-none"
                    />
                    <div className="flex justify-end gap-2">
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setDeliveryClarifyOpen(false)}
                      >
                        Cancel
                      </Button>
                      <Button
                        size="sm"
                        disabled={isSubmittingClarify || !deliveryClarifyNote.trim()}
                        onClick={() => void handleRequestDeliveryClarification()}
                      >
                        Submit Clarification
                      </Button>
                    </div>
                  </div>
                )}

                <div className="flex flex-wrap items-center gap-2 pt-1">
                  {firstIncompleteIdx >= 0 && firstIncompleteIdx < SUCCESSOR_STEPS.length - 1 && (
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => setStepIndex(firstIncompleteIdx)}
                    >
                      Review Incomplete Steps
                    </Button>
                  )}
                  {myDelivery && (
                    <Button
                      variant="secondary"
                      size="sm"
                      icon={MessageSquarePlus}
                      onClick={() => setDeliveryClarifyOpen((v) => !v)}
                    >
                      Request Clarification
                    </Button>
                  )}
                  {activeCase && (
                    <Link href={`/handovers/${activeCase.id}/report`}>
                      <Button variant="secondary" size="sm" icon={FileText}>
                        Open Published Handover
                      </Button>
                    </Link>
                  )}
                  <Button
                    variant="primary"
                    size="sm"
                    icon={ArrowRight}
                    onClick={() => router.push(`/projects/${projectId}`)}
                  >
                    Enter Project Workspace
                  </Button>
                </div>
              </div>
            )}

            {/* Footer Navigation (Never auto-completes on navigation) */}
            <div className="mt-6 flex flex-wrap items-center justify-between gap-2 border-t border-line pt-4">
              <Button
                variant="secondary"
                size="sm"
                icon={ArrowLeft}
                disabled={stepIndex === 0}
                onClick={() => setStepIndex((i) => Math.max(0, i - 1))}
              >
                Previous
              </Button>
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  variant={completedSteps[currentStep.id] ? "secondary" : "primary"}
                  size="sm"
                  icon={completedSteps[currentStep.id] ? CheckCircle2 : Check}
                  disabled={isSavingStep}
                  onClick={() =>
                    void toggleStepReviewed(currentStep.id, !completedSteps[currentStep.id])
                  }
                >
                  {completedSteps[currentStep.id] ? "Reviewed ✓ (Undo)" : "Mark Step Reviewed"}
                </Button>
                {stepIndex < SUCCESSOR_STEPS.length - 1 && (
                  <Button
                    variant="secondary"
                    size="sm"
                    iconRight={ArrowRight}
                    onClick={() => setStepIndex((i) => i + 1)}
                  >
                    Next Step
                  </Button>
                )}
              </div>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
