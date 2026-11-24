"use client";

import React from "react";
import {
  ShieldCheck,
  Clock,
  ShieldAlert,
  Archive,
  Info,
  ArrowRight,
  ExternalLink,
  CheckCircle2,
  AlertTriangle,
  Sparkles,
} from "lucide-react";
import { Card, Badge, Button, Tooltip, cn } from "../figma-ui/index";
import { Ring } from "../figma-ui/charts";
import type { HandoverDomainEpistemicBreakdown } from "../../lib/types";

interface HandoverVerificationOverviewProps {
  epistemicSummary: HandoverDomainEpistemicBreakdown;
  totalCandidates: number;
  readinessScore?: number;
  isReadyForSignoff?: boolean;
  onOpenPendingQueue: (domain?: string) => void;
  onOpenConflicts: () => void;
  onOpenVerificationCenter: () => void;
  className?: string;
}

export function HandoverVerificationOverview({
  epistemicSummary,
  totalCandidates,
  readinessScore,
  isReadyForSignoff,
  onOpenPendingQueue,
  onOpenConflicts,
  onOpenVerificationCenter,
  className,
}: HandoverVerificationOverviewProps) {
  const verifiedCount = epistemicSummary.human_verified_included;
  const pendingCount = epistemicSummary.pending_verification;
  const conflictCount = epistemicSummary.unresolved_conflicts;
  const resolvedConflictCount = epistemicSummary.resolved_conflicts || 0;
  const excludedCount = epistemicSummary.rejected + epistemicSummary.outdated;

  // Exact denominator: human-verified + pending verification
  const effectiveTotal = Math.max(totalCandidates, verifiedCount + pendingCount);
  const verificationPct =
    effectiveTotal > 0 ? Math.round((verifiedCount / effectiveTotal) * 100) : 0;

  const isVerificationComplete = effectiveTotal > 0 && pendingCount === 0 && conflictCount === 0;

  return (
    <Card className={cn("p-5 overflow-hidden border-line/80 shadow-card bg-white", className)}>
      {/* Header */}
      <div className="flex items-start justify-between gap-3 pb-3 border-b border-line/60">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="flex size-7 items-center justify-center rounded-lg bg-teal-50 text-teal-700 border border-teal-200/80">
              <ShieldCheck className="size-4" />
            </span>
            <h3 className="text-[15px] font-semibold text-navy">
              Verification Overview & Epistemic Gate
            </h3>
          </div>
          <p className="mt-1 text-xs text-muted leading-relaxed">
            Only human-verified knowledge enters approved handover content. Extracted candidates,
            pending claims, and conflicting facts remain strictly separated.
          </p>
        </div>
        <Tooltip content="Opens the dedicated Verification Center for comprehensive cross-project audits.">
          <Button
            size="sm"
            variant="ghost"
            icon={ExternalLink}
            onClick={onOpenVerificationCenter}
            className="text-xs text-slate-500 hover:text-navy shrink-0"
          >
            Full Center
          </Button>
        </Tooltip>
      </div>

      {/* Progress & Independence Callout */}
      <div className="mt-4 rounded-xl bg-slate-50/80 p-3.5 border border-line/60">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <Ring value={verificationPct} size={50} />
            <div>
              <div className="flex items-center gap-1.5">
                <span className="text-sm font-bold text-navy">
                  {verificationPct}% Verification Gate
                </span>
                {isVerificationComplete ? (
                  <Badge tone="green" icon={CheckCircle2}>
                    Gate Passed
                  </Badge>
                ) : (
                  <Badge tone="amber" icon={Clock}>
                    Review Required
                  </Badge>
                )}
              </div>
              <p className="text-[11.5px] text-muted mt-0.5 font-mono">
                Formula: {verifiedCount} verified / ({verifiedCount} verified + {pendingCount} pending) = {verificationPct}%
              </p>
            </div>
          </div>

          {typeof readinessScore === "number" && (
            <div className="text-right sm:border-l sm:border-line sm:pl-3">
              <span className="block text-[11px] text-muted">Operational Readiness</span>
              <span className="font-semibold text-xs text-navy">
                {readinessScore}/100 Composite
              </span>
            </div>
          )}
        </div>

        {/* Independence Notice */}
        <div className="mt-2.5 flex items-start gap-1.5 text-[11px] text-slate-600 bg-white/70 rounded-lg p-2 border border-line/40">
          <Info className="size-3.5 text-blue-600 shrink-0 mt-0.5" />
          <p className="leading-snug">
            <strong className="text-navy">Epistemic Rule:</strong> The Verification Gate strictly measures confirmed knowledge:{" "}
            <code>verified / (verified + pending)</code>. Excluded findings ({excludedCount} rejected/outdated) and contradictions ({conflictCount} conflicts) are isolated and do not contribute to this completion metric. Operational readiness (8 weighted categories) is independent and cannot substitute for verified knowledge.
          </p>
        </div>
      </div>

      {/* Prioritized Four-Tier Status Matrix */}
      <div className="mt-4 space-y-2">
        {/* Tier 1: Pending Verification (High Priority) */}
        <div
          className={cn(
            "rounded-xl border p-3 transition-colors",
            pendingCount > 0
              ? "border-amber-200/80 bg-amber-50/40 hover:bg-amber-50/70"
              : "border-line/60 bg-slate-50/30"
          )}
        >
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <span
                className={cn(
                  "flex size-6 items-center justify-center rounded-md text-xs font-bold",
                  pendingCount > 0
                    ? "bg-amber-100 text-amber-800"
                    : "bg-slate-100 text-slate-500"
                )}
              >
                <Clock className="size-3.5" />
              </span>
              <div>
                <span className="text-xs font-semibold text-navy">Pending Human Verification</span>
                <p className="text-[11px] text-muted">
                  Extracted findings awaiting human reviewer inspection & source grounding check.
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <span className="font-bold text-xs text-amber-800 font-mono">
                {pendingCount}
              </span>
              {pendingCount > 0 && (
                <Button
                  size="sm"
                  variant="secondary"
                  icon={ArrowRight}
                  onClick={() => onOpenPendingQueue()}
                  className="h-7 text-xs px-2.5 border-amber-200 text-amber-900 bg-white hover:bg-amber-100/50"
                >
                  Review
                </Button>
              )}
            </div>
          </div>
        </div>

        {/* Tier 2: Human-Verified (Eligible Knowledge) */}
        <div className="rounded-xl border border-teal-200/70 bg-teal-50/30 p-3">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <span className="flex size-6 items-center justify-center rounded-md bg-teal-100 text-teal-800 text-xs font-bold">
                <CheckCircle2 className="size-3.5" />
              </span>
              <div>
                <span className="text-xs font-semibold text-navy">Human-Verified Knowledge</span>
                <p className="text-[11px] text-muted">
                  Attributable findings approved by project reviewers; included in package snapshot.
                </p>
              </div>
            </div>
            <span className="font-bold text-xs text-teal-800 font-mono shrink-0">
              {verifiedCount}
            </span>
          </div>
        </div>

        {/* Tier 3: Unresolved Conflicts */}
        <div
          className={cn(
            "rounded-xl border p-3 transition-colors",
            conflictCount > 0
              ? "border-red-200/80 bg-red-50/40 hover:bg-red-50/70"
              : "border-line/60 bg-slate-50/30"
          )}
        >
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <span
                className={cn(
                  "flex size-6 items-center justify-center rounded-md text-xs font-bold",
                  conflictCount > 0 ? "bg-red-100 text-red-700" : "bg-slate-100 text-slate-500"
                )}
              >
                <ShieldAlert className="size-3.5" />
              </span>
              <div>
                <span className="text-xs font-semibold text-navy">Unresolved Conflicts</span>
                <p className="text-[11px] text-muted">
                  Contradictory claims across connected sources requiring human adjudication.
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <span className="font-bold text-xs text-red-700 font-mono">
                {conflictCount}
              </span>
              {conflictCount > 0 && (
                <Button
                  size="sm"
                  variant="secondary"
                  icon={ArrowRight}
                  onClick={onOpenConflicts}
                  className="h-7 text-xs px-2.5 border-red-200 text-red-900 bg-white hover:bg-red-100/50"
                >
                  Resolve
                </Button>
              )}
            </div>
          </div>
        </div>

        {/* Tier 4: Excluded Knowledge (Rejected or Outdated) */}
        <div className="rounded-xl border border-line/60 bg-slate-50/40 p-2.5">
          <div className="flex items-center justify-between text-xs">
            <div className="flex items-center gap-2 text-slate-600">
              <Archive className="size-3.5 text-slate-400" />
              <span className="text-[11.5px]">Rejected or Outdated Findings:</span>
            </div>
            <div className="flex items-center gap-2 text-[11px]">
              <span className="text-slate-500 font-mono">
                {epistemicSummary.rejected} rejected · {epistemicSummary.outdated} outdated
              </span>
              <Tooltip content="Rejected and outdated findings are strictly excluded from package snapshots but permanently preserved in the immutable audit trail.">
                <Info className="size-3 text-slate-400" />
              </Tooltip>
            </div>
          </div>
        </div>
      </div>

      {/* Primary Actions Footer */}
      <div className="mt-4 pt-3 border-t border-line/70 flex flex-wrap items-center justify-between gap-2">
        <div className="text-[11px] text-muted font-medium">
          {resolvedConflictCount > 0 && (
            <span className="text-teal-700 mr-2">
              ✓ {resolvedConflictCount} conflicts resolved
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {pendingCount > 0 && (
            <Button
              size="sm"
              icon={ShieldCheck}
              onClick={() => onOpenPendingQueue()}
              className="text-xs"
            >
              Review Pending Queue ({pendingCount})
            </Button>
          )}
          {conflictCount > 0 && (
            <Button
              size="sm"
              variant="secondary"
              icon={ShieldAlert}
              onClick={onOpenConflicts}
              className="text-xs"
            >
              Investigate Conflicts ({conflictCount})
            </Button>
          )}
        </div>
      </div>
    </Card>
  );
}
