"use client";

import React, { useState } from "react";
import {
  ShieldCheck,
  Bot,
  Pencil,
  RefreshCw,
  FileText,
  ArrowRight,
  ArrowLeft,
  BookOpen,
  Info,
  MoreVertical,
  CheckCircle2,
  Clock,
  ExternalLink,
} from "lucide-react";
import {
  Avatar,
  Badge,
  Button,
  Card,
  StatusBadge,
  Tooltip,
  cn,
} from "../figma-ui/index";
import { RoleBadge } from "../figma-ui/domain";
import { Ring } from "../figma-ui/charts";
import type {
  HandoverPackageVersionSummary,
  HandoverReadinessIntelligenceResponse,
  HandoverVersionSectionsResponse,
  ProjectMember,
  User,
} from "../../lib/types";
import type { Handover, ProjectRole } from "../../lib/figmaStore";
import { HandoverLifecycleStepper } from "./HandoverLifecycleStepper";

interface HandoverWorkspaceHeaderProps {
  handover: Handover;
  projectName: string;
  role: ProjectRole;
  members: ProjectMember[];
  currentUser: User | null;
  sectionsData: HandoverVersionSectionsResponse | null;
  versions: HandoverPackageVersionSummary[];
  selectedVersionId: string | null;
  onSelectVersionId: (versionId: string) => void;
  isLoadingVersions: boolean;
  isLoadingSections: boolean;
  readinessData: HandoverReadinessIntelligenceResponse | null;
  isRefreshingDraft: boolean;
  onRefreshDraft: () => Promise<void>;
  onOpenEditModal: () => void;
  onAskAssistant: () => void;
  onSignOff: () => void;
  onOpenReport: () => void;
  onOpenRecipientView?: () => void;
  onNavigatePrevious?: () => void;
  prevStageLabel?: string | null;
  currentTab: string;
}

export function HandoverWorkspaceHeader({
  handover,
  projectName,
  role,
  members,
  currentUser,
  sectionsData,
  versions,
  selectedVersionId,
  onSelectVersionId,
  isLoadingVersions,
  isLoadingSections,
  readinessData,
  isRefreshingDraft,
  onRefreshDraft,
  onOpenEditModal,
  onAskAssistant,
  onSignOff,
  onOpenReport,
  onOpenRecipientView,
  onNavigatePrevious,
  prevStageLabel,
  currentTab,
}: HandoverWorkspaceHeaderProps) {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  // Participant names helper
  const getMemberDisplayName = (userId: string | undefined): string => {
    if (!userId) return "Unassigned";
    if (currentUser && currentUser.id === userId) {
      return `${currentUser.full_name || currentUser.email} (You)`;
    }
    const match = members.find((m) => m.user_id === userId || m.id === userId);
    return match?.full_name || match?.email || "Team Member";
  };

  const isLockedLifecycle = ["approved", "published", "completed"].includes(
    handover.status
  );

  const selectedVersion =
    versions.find((v) => v.id === selectedVersionId) ||
    sectionsData?.version ||
    null;

  // Real Epistemic Counts (Zero Fabrication)
  const verifiedCount =
    sectionsData?.epistemic_summary.human_verified_included ?? 0;
  const pendingCount =
    sectionsData?.epistemic_summary.pending_verification ?? 0;
  const totalCandidates = verifiedCount + pendingCount;
  const verificationPct =
    totalCandidates > 0
      ? Math.round((verifiedCount / totalCandidates) * 100)
      : 0;

  // Handover Type Label
  const handoverTypeLabel =
    sectionsData?.handover_type_label ||
    (handover.handoverType === "project_manager"
      ? "Project Manager Handover"
      : handover.handoverType === "technical_lead"
      ? "Technical Lead Handover"
      : "Developer Handover");

  return (
    <Card className="mb-5 overflow-hidden border-line/80 shadow-card bg-white">
      {/* ── Main Header Body ────────────────────────────────────────────── */}
      <div className="p-5 sm:p-6 space-y-5">
        {/* Top: Metadata Pill Row & Epistemic Badges */}
        <div className="flex flex-wrap items-center justify-between gap-2.5 pb-1">
          <div className="flex flex-wrap items-center gap-2">
            {/* Handover ID Code */}
            <span className="font-mono text-xs font-semibold px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 border border-slate-200">
              {handover.code}
            </span>

            {/* Lifecycle Status Badge */}
            <StatusBadge status={handover.status} />

            {/* Handover Role Type */}
            <Badge tone="indigo">{handoverTypeLabel}</Badge>

            {/* Perspective Role Badge */}
            <Tooltip content="Your perspective on this handover, based on your role in the project.">
              <span>
                <RoleBadge role={role} />
              </span>
            </Tooltip>

            {/* Package Version Badge */}
            {selectedVersion && (
              <Badge tone={selectedVersion.is_current ? "blue" : "amber"}>
                Package v{selectedVersion.version_number}
                {selectedVersion.is_current ? " (Current)" : " (Historical)"}
              </Badge>
            )}

            {/* Interactive Readiness Score with Mandatory Educational Tooltip */}
            {readinessData && (
              <Tooltip
                content={
                  <div className="max-w-xs space-y-1.5 text-left p-0.5">
                    <p className="font-semibold text-white text-xs flex items-center gap-1.5">
                      <span className="size-2 rounded-full bg-blue-400" />
                      Readiness vs. Verification Gate
                    </p>
                    <p className="text-[11.5px] leading-relaxed text-slate-200">
                      Readiness is an 8-dimensional operational composite
                      (evidence citations, conflicts, checklists, ownership, etc.).
                    </p>
                    <p className="text-[11.5px] leading-relaxed text-amber-300">
                      <strong>Independent Gate:</strong> High readiness does not permit sign-off until eligible findings are human-verified in the Verification Center.
                    </p>
                  </div>
                }
              >
                <div className="inline-flex items-center gap-1.5 rounded-full border border-line bg-slate-50 px-2.5 py-0.5 text-[11px] font-semibold text-navy cursor-default">
                  <span>Readiness {readinessData.overall_score}/100</span>
                  <span
                    className={cn(
                      "size-2 rounded-full",
                      readinessData.overall_level === "ready"
                        ? "bg-emerald-500"
                        : readinessData.overall_level === "ready_with_warnings"
                        ? "bg-blue-500"
                        : readinessData.overall_level === "partially_ready"
                        ? "bg-amber-500"
                        : "bg-red-500"
                    )}
                  />
                  <Info className="size-3 text-slate-400 ml-0.5" />
                </div>
              </Tooltip>
            )}
          </div>
        </div>

        {/* Middle: Dominant Title, Scope & Primary Actions Corridor */}
        <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          {/* Left Column: Project Title & Subtitle */}
          <div className="min-w-0 max-w-2xl">
            <h1 className="text-2xl sm:text-[26px] font-semibold tracking-[-0.025em] text-navy leading-tight">
              {projectName}
            </h1>
            <p className="mt-1 text-[13.5px] text-muted leading-relaxed">
              {handover.scope ||
                "Comprehensive project knowledge reconstruction, transition checklists, and handover dossier."}
            </p>

            {/* Transfer Corridor: Outgoing -> Incoming, Timestamps */}
            <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-3 text-[13px] pt-1 border-t border-slate-100">
              {/* Outgoing */}
              <div className="flex items-center gap-2">
                <Avatar
                  id={handover.outgoingId}
                  name={getMemberDisplayName(handover.outgoingId)}
                  size={28}
                />
                <div>
                  <span className="block text-[10.5px] font-medium uppercase tracking-wider text-muted">
                    Outgoing Lead
                  </span>
                  <span className="font-medium text-navy text-xs">
                    {getMemberDisplayName(handover.outgoingId)}
                  </span>
                </div>
              </div>

              <ArrowRight className="size-4 text-brand shrink-0" aria-hidden="true" />

              {/* Incoming */}
              <div className="flex items-center gap-2">
                <Avatar
                  id={handover.incomingId}
                  name={getMemberDisplayName(handover.incomingId)}
                  size={28}
                />
                <div>
                  <span className="block text-[10.5px] font-medium uppercase tracking-wider text-muted">
                    Designated Successor
                  </span>
                  <span className="font-medium text-navy text-xs">
                    {getMemberDisplayName(handover.incomingId)}
                  </span>
                </div>
              </div>

              <span className="hidden h-6 w-px bg-slate-200 sm:block" aria-hidden="true" />

              {/* Timestamps */}
              <div className="text-xs">
                <span className="block text-[10.5px] font-medium uppercase tracking-wider text-muted">
                  Last Updated
                </span>
                <span className="font-medium text-navy">{handover.updated}</span>
              </div>

              <div className="text-xs">
                <span className="block text-[10.5px] font-medium uppercase tracking-wider text-muted">
                  Target Due Date
                </span>
                <span className="font-medium text-navy">{handover.due || "—"}</span>
              </div>
            </div>
          </div>

          {/* Right Column: Verified Knowledge Ring & Action Hierarchy */}
          <div className="flex shrink-0 flex-col items-start gap-4 lg:items-end">
            {/* Verified Knowledge Radial & Breakdown */}
            <div className="flex items-center gap-3.5 bg-slate-50/70 border border-slate-200/80 rounded-xl p-2.5 sm:px-3.5">
              <Ring
                value={verificationPct}
                size={52}
                color={verificationPct >= 50 ? "#299B80" : "#315FBA"}
              />
              <div className="text-left">
                <div className="flex items-center gap-1.5">
                  <ShieldCheck className="size-3.5 text-teal-600" />
                  <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                    Verified Knowledge
                  </p>
                </div>
                <div className="flex items-center gap-2 mt-0.5">
                  <span className="inline-flex items-center gap-1 text-xs font-semibold text-teal-700">
                    <span className="size-1.5 rounded-full bg-teal-500" />
                    {verifiedCount} verified
                  </span>
                  <span className="text-slate-300">·</span>
                  <span className="inline-flex items-center gap-1 text-xs font-medium text-amber-700">
                    <span className="size-1.5 rounded-full bg-amber-500" />
                    {pendingCount} pending
                  </span>
                </div>
                <p className="text-[10.5px] text-slate-400 mt-0.5">
                  {totalCandidates > 0
                    ? `${verificationPct}% verified of ${totalCandidates} eligible findings`
                    : "No candidate findings recorded yet"}
                </p>
              </div>
            </div>

            {/* Action Hierarchy */}
            <div className="flex flex-wrap items-center gap-2">
              {/* Previous Stage (Navigation helper) */}
              {prevStageLabel && onNavigatePrevious && (
                <Button
                  variant="secondary"
                  size="sm"
                  icon={ArrowLeft}
                  onClick={onNavigatePrevious}
                  className="hidden md:inline-flex"
                >
                  {prevStageLabel}
                </Button>
              )}

              {/* Secondary: Edit Details */}
              {!isLockedLifecycle && (
                <Button
                  variant="secondary"
                  size="sm"
                  icon={Pencil}
                  onClick={onOpenEditModal}
                >
                  Edit Details
                </Button>
              )}

              {/* Secondary: Ask Assistant */}
              <Button
                variant="secondary"
                size="sm"
                icon={Bot}
                onClick={onAskAssistant}
              >
                Ask Assistant
              </Button>

              {/* Tertiary: Refresh Draft */}
              {!isLockedLifecycle && (
                <Button
                  variant="secondary"
                  size="sm"
                  icon={RefreshCw}
                  disabled={isRefreshingDraft}
                  onClick={() => void onRefreshDraft()}
                  className="hidden sm:inline-flex"
                >
                  {isRefreshingDraft ? "Refreshing…" : "Refresh Draft"}
                </Button>
              )}

              {/* Tertiary: Report */}
              <Button
                variant="secondary"
                size="sm"
                icon={FileText}
                onClick={onOpenReport}
                className="hidden sm:inline-flex"
              >
                Report
              </Button>

              {/* Recipient View (when applicable) */}
              {(handover.status === "published" ||
                handover.status === "completed") &&
                onOpenRecipientView && (
                  <Button
                    variant="secondary"
                    size="sm"
                    icon={BookOpen}
                    onClick={onOpenRecipientView}
                  >
                    Recipient View
                  </Button>
                )}

              {/* Primary Milestone Action: Sign-Off & Approval */}
              {currentTab !== "review" && (
                <Button
                  variant="primary"
                  size="sm"
                  icon={ShieldCheck}
                  onClick={onSignOff}
                  className="bg-blue-600 hover:bg-blue-700 text-white shadow-xs font-semibold px-3.5"
                >
                  Sign-Off &amp; Approval
                </Button>
              )}

              {/* Mobile Overflow Menu */}
              <div className="relative sm:hidden">
                <Button
                  variant="secondary"
                  size="sm"
                  icon={MoreVertical}
                  onClick={() => setMobileMenuOpen((o) => !o)}
                  aria-label="More actions"
                />
                {mobileMenuOpen && (
                  <div className="absolute right-0 top-full mt-1.5 w-44 rounded-xl border border-slate-200 bg-white p-1.5 shadow-lg z-30 space-y-1">
                    {!isLockedLifecycle && (
                      <button
                        type="button"
                        onClick={() => {
                          setMobileMenuOpen(false);
                          void onRefreshDraft();
                        }}
                        disabled={isRefreshingDraft}
                        className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-xs text-slate-700 hover:bg-slate-50 text-left"
                      >
                        <RefreshCw className="size-3.5 text-slate-400" />
                        <span>Refresh Draft</span>
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => {
                        setMobileMenuOpen(false);
                        onOpenReport();
                      }}
                      className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-xs text-slate-700 hover:bg-slate-50 text-left"
                    >
                      <FileText className="size-3.5 text-slate-400" />
                      <span>Formal Report</span>
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* ── Lifecycle Stepper Progress Tracker ──────────────────────────── */}
        <div className="pt-2 border-t border-slate-100">
          <HandoverLifecycleStepper
            currentStatus={handover.status}
            createdDate={handover.created}
            assembledDate={selectedVersion?.assembled_at ? new Date(selectedVersion.assembled_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }) : undefined}
            publishedDate={handover.publishedOn}
            acknowledgedDate={handover.acknowledgedOn}
          />
        </div>
      </div>

      {/* ── Package Version & SHA-256 Hash Footer Bar ──────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line/80 bg-slate-50/70 px-5 py-2.5 text-xs text-muted">
        <div className="flex flex-wrap items-center gap-3">
          {versions.length > 0 ? (
            <label className="flex items-center gap-2">
              <span className="font-semibold text-navy text-xs">Package Snapshot:</span>
              <select
                aria-label="Package Version"
                value={selectedVersionId || ""}
                onChange={(e) => onSelectVersionId(e.target.value)}
                className="rounded-lg border border-line bg-white px-2.5 py-1 text-xs font-medium text-navy focus:border-brand focus:outline-none"
              >
                {versions.map((v) => (
                  <option key={v.id} value={v.id}>
                    v{v.version_number}
                    {v.is_current ? " (Current)" : " (Historical)"}
                    {v.assembled_at
                      ? ` · ${new Date(v.assembled_at).toLocaleDateString("en-GB", {
                          day: "numeric",
                          month: "short",
                        })}`
                      : ""}
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <span className="text-xs">
              {isLoadingVersions
                ? "Loading package versions…"
                : "No package snapshot assembled yet"}
            </span>
          )}

          {selectedVersion?.content_hash && (
            <span
              className="inline-flex items-center gap-1.5 rounded-md border border-line bg-white px-2.5 py-0.5 font-mono text-[11px] text-slate-700 shadow-2xs"
              title={`Immutable Package SHA-256: ${selectedVersion.content_hash}`}
            >
              <ShieldCheck className="size-3 text-teal-600" />
              <span>SHA-256: {selectedVersion.content_hash.slice(0, 12)}…</span>
            </span>
          )}
        </div>

        <div className="text-[11px] text-slate-400 font-medium">
          Evidence integrity guaranteed · Citations fail-closed
        </div>
      </div>
    </Card>
  );
}
