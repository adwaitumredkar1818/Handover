'use client'

import React, { useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import {
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ClipboardCheck,
  Clock,
  Database,
  ExternalLink,
  FileWarning,
  GitCompareArrows,
  History,
  Layers,
  ListChecks,
  Loader2,
  Lock,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  ShieldX,
  Sparkles,
  UserCheck,
  XCircle,
} from 'lucide-react'

import {
  Badge,
  Button,
  Callout,
  Card,
  CardHeader,
  EmptyState,
  Progress,
  Table,
  Td,
  Th,
  cn,
} from '../figma-ui/index'
import { Ring } from '../figma-ui/charts'
import type {
  HandoverPackageVersionSummary,
  HandoverReadinessCategoryItem,
  HandoverReadinessIntelligenceResponse,
  ReadinessConflictItem,
  ReadinessStructuredBlocker,
} from '../../lib/types'

export interface ReadinessIntelligencePanelProps {
  caseId: string
  projectId: string
  selectedVersion: HandoverPackageVersionSummary | null
  readiness: HandoverReadinessIntelligenceResponse | null
  isLoading: boolean
  isReassessing: boolean
  error: string | null
  notAssessedYet: boolean
  onRetry: () => void
  onReassess: (notes?: string) => Promise<void>
  onNavigateTab: (tab: string) => void
  onToggleChecklistItem: (projectId: string, itemId: string, currentStatus: string) => Promise<void>
  onGenerateChecklists: (projectId: string) => Promise<void>
  updatingChecklistItemId: string | null
  isGeneratingChecklists: boolean
}

function levelBadge(level: string): { label: string; tone: 'green' | 'amber' | 'red' | 'blue' | 'gray' } {
  switch (level) {
    case 'ready':
      return { label: 'Ready', tone: 'green' }
    case 'ready_with_warnings':
      return { label: 'Ready with Warnings', tone: 'blue' }
    case 'partially_ready':
      return { label: 'Partially Ready', tone: 'amber' }
    case 'not_ready':
    default:
      return { label: 'Not Ready', tone: 'red' }
  }
}

function severityTone(sev: string): 'red' | 'amber' | 'blue' | 'gray' {
  switch (sev.toLowerCase()) {
    case 'critical':
    case 'high':
      return 'red'
    case 'medium':
      return 'amber'
    case 'low':
      return 'blue'
    default:
      return 'gray'
  }
}

function conflictStateBadge(state: string): { label: string; tone: 'red' | 'amber' | 'green' | 'blue' | 'gray' } {
  switch (state) {
    case 'resolved':
    case 'reconciled':
      return { label: state.replace(/_/g, ' '), tone: 'green' }
    case 'superseded':
    case 'dismissed':
      return { label: state.replace(/_/g, ' '), tone: 'gray' }
    case 'under_investigation':
      return { label: 'Under Investigation', tone: 'amber' }
    case 'awaiting_context':
      return { label: 'Awaiting Context', tone: 'blue' }
    case 'reopened':
      return { label: 'Reopened', tone: 'red' }
    case 'open':
    case 'unresolved':
    default:
      return { label: 'Unresolved', tone: 'red' }
  }
}

function formatDateTime(iso?: string | null): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('en-GB', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}

function formatLifecycleLabel(state?: string | null): string {
  if (!state) return 'Terminal'
  return state
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

function formatConflictType(ctype: string): string {
  return ctype
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

export function ReadinessIntelligencePanel({
  caseId,
  projectId,
  selectedVersion,
  readiness,
  isLoading,
  isReassessing,
  error,
  notAssessedYet,
  onRetry,
  onReassess,
  onNavigateTab,
  onToggleChecklistItem,
  onGenerateChecklists,
  updatingChecklistItemId,
  isGeneratingChecklists,
}: ReadinessIntelligencePanelProps) {
  const router = useRouter()
  const [conflictFilter, setConflictFilter] = useState<'all' | 'blocking' | 'resolved'>('blocking')
  const [checklistDirty, setChecklistDirty] = useState(false)
  const [reassessBanner, setReassessBanner] = useState<string | null>(null)

  const handleReassessClick = async () => {
    setReassessBanner(null)
    await onReassess('Live readiness reassessment from Handover Workspace')
    setChecklistDirty(false)
    setReassessBanner('Readiness assessment updated and persisted to canonical history.')
  }

  const handleToggleChecklist = async (itemId: string, currentStatus: string) => {
    await onToggleChecklistItem(projectId, itemId, currentStatus)
    setChecklistDirty(true)
  }

  const handleBlockerNavigation = (blocker: ReadinessStructuredBlocker) => {
    if (blocker.target_url) {
      if (blocker.target_url.includes('#checklists')) {
        const el = document.getElementById('readiness-checklists-section')
        if (el) {
          el.scrollIntoView({ behavior: 'smooth', block: 'start' })
          return
        }
      }
      if (blocker.target_url.startsWith(`/handovers/${caseId}?tab=`)) {
        const match = blocker.target_url.match(/[?&]tab=([^&#]+)/)
        if (match?.[1] && match[1] !== 'readiness') {
          onNavigateTab(match[1])
          return
        }
      }
      router.push(blocker.target_url)
      return
    }
    if (blocker.related_section_tab) {
      onNavigateTab(blocker.related_section_tab)
    }
  }

  const filteredConflicts: ReadinessConflictItem[] = useMemo(() => {
    const items = readiness?.conflict_summary?.items || []
    if (conflictFilter === 'blocking') return items.filter((c) => c.is_blocking)
    if (conflictFilter === 'resolved') return items.filter((c) => !c.is_blocking)
    return items
  }, [readiness?.conflict_summary?.items, conflictFilter])

  // Loading state
  if (isLoading && !readiness) {
    return (
      <Card className="p-10">
        <div className="flex flex-col items-center justify-center gap-3 text-center">
          <Loader2 className="size-7 animate-spin text-brand" />
          <p className="text-sm font-semibold text-navy">Loading live readiness intelligence…</p>
          <p className="max-w-md text-xs text-muted">
            Retrieving canonical 9-category readiness scores, verification coverage, conflict status, evidence completeness, and checklist gates.
          </p>
        </div>
      </Card>
    )
  }

  // No assembled version yet
  if (!selectedVersion) {
    return (
      <Card>
        <EmptyState
          icon={ShieldAlert}
          title="No assembled package version yet"
          body="Assemble a handover package version first before running a canonical 9-category readiness assessment."
          action={
            <Button variant="secondary" onClick={() => onNavigateTab('overview')}>
              Return to Overview
            </Button>
          }
        />
      </Card>
    )
  }

  // Not yet assessed state (clean empty state with direct trigger)
  if (notAssessedYet && !readiness) {
    return (
      <Card>
        <EmptyState
          icon={ShieldCheck}
          title="Readiness has not been assessed for this package version"
          body={`Package v${selectedVersion.version_number} has not been evaluated by the Handover Readiness Engine yet. Run an assessment to compute weighted category scores, verification gates, and conflict blockers.`}
          action={
            <Button
              icon={isReassessing ? Loader2 : RefreshCw}
              disabled={isReassessing}
              onClick={handleReassessClick}
            >
              {isReassessing ? 'Assessing Readiness…' : 'Run Initial Readiness Assessment'}
            </Button>
          }
        />
      </Card>
    )
  }

  // Explicit error state (zero mock fallback)
  if (error && !readiness) {
    return (
      <Card className="p-6">
        <Callout tone="red" icon={AlertCircle} title="Failed to load readiness intelligence">
          <p className="mb-3">{error}</p>
          <Button variant="secondary" size="sm" icon={RefreshCw} onClick={onRetry}>
            Retry
          </Button>
        </Callout>
      </Card>
    )
  }

  if (!readiness) return null

  const overallBadge = levelBadge(readiness.overall_level)
  const eligibility = readiness.approval_eligibility
  const verification = readiness.verification_summary
  const conflicts = readiness.conflict_summary
  const evidence = readiness.evidence_quality
  const checklists = readiness.checklist_summary
  const categories = readiness.categories || []
  const history = readiness.assessment_history || []

  const categoryCards = categories.filter((c) => c.category !== 'overall_quality')
  const overallCategory = categories.find((c) => c.category === 'overall_quality')

  return (
    <div className="space-y-6" data-testid="readiness-intelligence-panel">
      {/* Feedback banner after reassessment or error */}
      {reassessBanner && (
        <Callout tone="green" icon={CheckCircle2} title="Reassessment persisted">
          {reassessBanner}
        </Callout>
      )}
      {error && (
        <Callout tone="red" icon={AlertCircle} title="Readiness refresh error">
          {error}
        </Callout>
      )}
      {checklistDirty && (
        <Callout tone="amber" icon={RefreshCw} title="Checklist state changed">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span>
              Transition checklist progress was updated. Reassess readiness to record a fresh persisted snapshot reflecting the updated checklist gate.
            </span>
            <Button size="sm" icon={RefreshCw} disabled={isReassessing} onClick={handleReassessClick}>
              {isReassessing ? 'Reassessing…' : 'Reassess Now'}
            </Button>
          </div>
        </Callout>
      )}

      {/* 1. Overall Readiness Summary Header Card */}
      <Card className="p-5 sm:p-6">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-col gap-5 sm:flex-row sm:items-center">
            <div className="relative flex shrink-0 items-center justify-center">
              <Ring value={readiness.overall_score} size={88} />
            </div>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-lg font-semibold text-navy">Handover Readiness Intelligence</h2>
                <Badge tone={overallBadge.tone}>{overallBadge.label}</Badge>
                {readiness.version_number != null && (
                  <Badge tone="gray">Package v{readiness.version_number}</Badge>
                )}
              </div>
              <p className="mt-1 text-[13px] text-muted">
                Weighted evaluation across all 9 canonical readiness categories, live Verification Center records, Conflict Management contradictions, and mandatory transition checklists.
              </p>
              <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-muted">
                <span className="inline-flex items-center gap-1.5">
                  <Clock className="size-3.5 text-slate-400" />
                  Last assessed: <strong className="font-medium text-navy">{formatDateTime(readiness.assessed_at)}</strong>
                </span>
                {readiness.content_hash && (
                  <span
                    className="inline-flex items-center gap-1 font-mono text-[11px] text-slate-600"
                    title={`Package Version SHA-256: ${readiness.content_hash}`}
                  >
                    <ShieldCheck className="size-3.5 text-ok" />
                    SHA-256: {readiness.content_hash.slice(0, 12)}…
                  </span>
                )}
                <span className="inline-flex items-center gap-1.5">
                  <History className="size-3.5 text-slate-400" />
                  {history.length} persisted run{history.length === 1 ? '' : 's'}
                </span>
              </div>
            </div>
          </div>

          <div className="flex flex-col items-start gap-3 lg:items-end">
            <div className="flex flex-wrap items-center gap-2">
              <div className="rounded-lg border border-red-200 bg-red-50/70 px-3 py-1.5 text-center">
                <p className="text-[11px] font-medium text-red-700">Active Blockers</p>
                <p className="text-base font-bold text-red-800">{readiness.blocker_count}</p>
              </div>
              <div className="rounded-lg border border-amber-200 bg-amber-50/70 px-3 py-1.5 text-center">
                <p className="text-[11px] font-medium text-amber-700">Warnings</p>
                <p className="text-base font-bold text-amber-800">{readiness.warning_count}</p>
              </div>
              <div className="rounded-lg border border-line bg-slate-50 px-3 py-1.5 text-center">
                <p className="text-[11px] font-medium text-muted">Threshold</p>
                <p className="text-base font-bold text-navy">≥ 70</p>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                icon={isReassessing ? Loader2 : RefreshCw}
                disabled={isReassessing}
                onClick={handleReassessClick}
                data-testid="reassess-readiness-btn"
              >
                {isReassessing ? 'Reassessing…' : 'Reassess Readiness'}
              </Button>
              <Button
                variant="secondary"
                icon={ExternalLink}
                onClick={() => router.push(`/verification?project=${projectId}`)}
              >
                Verification Center
              </Button>
              <Button
                variant="secondary"
                icon={GitCompareArrows}
                onClick={() => router.push('/conflicts')}
              >
                Conflicts
              </Button>
            </div>
          </div>
        </div>
      </Card>

      {/* 2. Authoritative Approval Eligibility & Lifecycle Governance */}
      {eligibility && (
        <Card className="p-5 sm:p-6">
          <div className="flex flex-col gap-4 border-b border-line pb-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                {eligibility.is_eligible_for_approval ? (
                  <ShieldCheck className="size-5 text-ok" />
                ) : (
                  <ShieldX className="size-5 text-bad" />
                )}
                <h3 className="text-[15px] font-semibold text-navy">Approval Eligibility & Sign-Off Gates</h3>
                <Badge tone={eligibility.is_eligible_for_approval ? 'green' : 'red'}>
                  {eligibility.is_eligible_for_approval ? 'Eligible for Approval' : 'Not Eligible for Approval'}
                </Badge>
              </div>
              <p className="mt-1 text-xs text-muted">
                Lifecycle status:{' '}
                <strong className="font-medium text-navy">{formatLifecycleLabel(eligibility.current_case_status)}</strong>
                {eligibility.next_lifecycle_state && (
                  <>
                    {' '}
                    <ArrowRight className="inline size-3 text-slate-400" /> Next:{' '}
                    <strong className="font-medium text-navy">{formatLifecycleLabel(eligibility.next_lifecycle_state)}</strong>
                  </>
                )}
              </p>
            </div>
            <span className="text-[11px] font-medium text-muted">
              Authoritative backend gate · Reviewers cannot bypass blocking gates
            </span>
          </div>

          {/* 4 Gate Pills */}
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {[
              {
                label: 'Score Threshold (≥ 70)',
                passed: eligibility.score_gate_passed,
                detail: `${readiness.overall_score}/100 weighted`,
              },
              {
                label: 'Verification Gate',
                passed: eligibility.verification_gate_passed,
                detail: verification
                  ? `${verification.verification_coverage_pct}% verified (${verification.eligible_human_verified}/${verification.total_knowledge_items})`
                  : 'Evaluated by readiness engine',
              },
              {
                label: 'Conflict Gate',
                passed: eligibility.conflict_gate_passed,
                detail: conflicts
                  ? `${conflicts.blocking_approval_count} blocking conflict(s)`
                  : 'Evaluated by readiness engine',
              },
              {
                label: 'Mandatory Checklists',
                passed: eligibility.checklist_gate_passed,
                detail: checklists
                  ? `${checklists.mandatory_completed}/${checklists.mandatory_total} mandatory done`
                  : 'Evaluated by readiness engine',
              },
            ].map((gate) => (
              <div
                key={gate.label}
                className={cn(
                  'rounded-xl border p-3.5',
                  gate.passed
                    ? 'border-emerald-200 bg-emerald-50/50'
                    : 'border-red-200 bg-red-50/40'
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-semibold text-navy">{gate.label}</span>
                  {gate.passed ? (
                    <CheckCircle2 className="size-4 shrink-0 text-emerald-600" />
                  ) : (
                    <XCircle className="size-4 shrink-0 text-red-600" />
                  )}
                </div>
                <p className="mt-1 text-xs text-muted">{gate.detail}</p>
              </div>
            ))}
          </div>

          {/* Blocking Requirements & Signoff Phases */}
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <div className="rounded-xl border border-line bg-slate-50/60 p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">
                Blocking Approval Requirements ({eligibility.blocking_requirements.length})
              </p>
              {eligibility.blocking_requirements.length > 0 ? (
                <ul className="mt-2.5 space-y-2">
                  {eligibility.blocking_requirements.map((req, idx) => (
                    <li key={idx} className="flex items-start gap-2 text-[13px] text-red-800">
                      <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-red-600" />
                      <span>{req}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-2 flex items-center gap-1.5 text-[13px] text-emerald-700">
                  <CheckCircle2 className="size-4" />
                  All approval readiness gates are satisfied.
                </p>
              )}
              {eligibility.warnings.length > 0 && (
                <div className="mt-3 border-t border-line pt-3">
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-amber-700">
                    Advisory Warnings ({eligibility.warnings.length})
                  </p>
                  <ul className="mt-1.5 space-y-1">
                    {eligibility.warnings.map((w, idx) => (
                      <li key={idx} className="text-xs text-amber-800">
                        • {w}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            <div className="rounded-xl border border-line bg-slate-50/60 p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">
                Three-Phase Sign-Off Governance
              </p>
              <div className="mt-2.5 space-y-2">
                {eligibility.required_signoffs.map((phase) => {
                  const statusTone =
                    phase.status === 'approved'
                      ? 'green'
                      : phase.status === 'blocked'
                      ? 'red'
                      : phase.status === 'rejected'
                      ? 'red'
                      : 'gray'
                  return (
                    <div
                      key={phase.signoff_type}
                      className="flex items-center justify-between gap-2 rounded-lg border border-line bg-white px-3 py-2"
                    >
                      <div>
                        <p className="text-[13px] font-medium text-navy">{phase.phase}</p>
                        {phase.signed_at && (
                          <p className="text-[11px] text-muted">Signed {formatDateTime(phase.signed_at)}</p>
                        )}
                      </div>
                      <Badge tone={statusTone}>{formatLifecycleLabel(phase.status)}</Badge>
                    </div>
                  )
                })}
              </div>
            </div>
          </div>
        </Card>
      )}

      {/* 3. Grouped Actionable Blocker & Corrective Action Queue */}
      <Card className="overflow-hidden">
        <CardHeader
          title={`Actionable Blockers & Corrective Queue (${readiness.structured_blockers.length})`}
          subtitle="Direct remediation actions linking directly to Verification Center, Conflict Management, Checklists, and Handover sections."
        />
        {readiness.structured_blockers.length === 0 ? (
          <div className="p-6 text-center">
            <CheckCircle2 className="mx-auto size-7 text-emerald-600" />
            <p className="mt-2 text-sm font-semibold text-navy">No active readiness blockers</p>
            <p className="mt-1 text-xs text-muted">
              All evaluated subsystems passed without blocking issues for this package version.
            </p>
          </div>
        ) : (
          <div className="divide-y divide-line">
            {readiness.structured_blockers.map((blocker) => (
              <div
                key={blocker.id}
                className="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={severityTone(blocker.severity)}>{blocker.severity.toUpperCase()}</Badge>
                    <Badge tone="gray">{blocker.originating_subsystem}</Badge>
                  </div>
                  <p className="mt-1.5 text-[13.5px] font-semibold text-navy">{blocker.description}</p>
                  <p className="mt-0.5 text-xs text-muted">{blocker.recommended_action}</p>
                </div>
                <div className="shrink-0">
                  <Button
                    variant="secondary"
                    size="sm"
                    iconRight={ArrowRight}
                    onClick={() => handleBlockerNavigation(blocker)}
                  >
                    {blocker.originating_subsystem === 'Verification Center'
                      ? 'Open Verification'
                      : blocker.originating_subsystem === 'Conflict Management'
                      ? 'Investigate Conflicts'
                      : blocker.originating_subsystem === 'Transition Checklists'
                      ? 'Open Checklists'
                      : 'Inspect Section'}
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* 4. Nine-Category Readiness Matrix */}
      <Card className="p-5 sm:p-6">
        <div className="flex flex-col gap-2 border-b border-line pb-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h3 className="text-[15px] font-semibold text-navy">
              Nine-Category Readiness Breakdown ({categories.length}/9 Canonical Dimensions)
            </h3>
            <p className="mt-0.5 text-xs text-muted">
              Deterministic weighted scoring across Evidence, Verification, Conflicts, Freshness, Relationships, Responsibilities, Risks, Dependencies, and Overall Quality.
            </p>
          </div>
          {overallCategory && (
            <Badge tone={levelBadge(overallCategory.level).tone}>
              Overall Aggregate: {overallCategory.score}/100
            </Badge>
          )}
        </div>

        <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {categoryCards.map((cat: HandoverReadinessCategoryItem) => {
            const b = levelBadge(cat.level)
            const weightPct = cat.weight != null ? Math.round(cat.weight * 100) : null
            const progressTone =
              cat.score >= 85 ? 'green' : cat.score >= 60 ? 'amber' : 'red'
            return (
              <div
                key={cat.category}
                className="flex flex-col justify-between rounded-xl border border-line bg-white p-4 transition hover:border-slate-300"
              >
                <div>
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <p className="text-[13.5px] font-semibold text-navy">{cat.label}</p>
                      {weightPct != null && (
                        <p className="text-[11px] text-muted">Weight: {weightPct}%</p>
                      )}
                    </div>
                    <Badge tone={b.tone}>{b.label}</Badge>
                  </div>

                  <div className="mt-3 flex items-center justify-between text-xs">
                    <span className="font-semibold text-navy">
                      {cat.score} / {cat.max_score}
                    </span>
                    <span className="text-muted">
                      {cat.blockers_json.length} blocker{cat.blockers_json.length === 1 ? '' : 's'} ·{' '}
                      {cat.warnings_json.length} warning{cat.warnings_json.length === 1 ? '' : 's'}
                    </span>
                  </div>
                  <Progress value={cat.score} tone={progressTone} className="mt-1.5" />

                  {cat.blockers_json.length > 0 && (
                    <ul className="mt-3 space-y-1">
                      {cat.blockers_json.map((blk, i) => (
                        <li key={i} className="flex items-start gap-1.5 text-xs text-red-700">
                          <AlertTriangle className="mt-0.5 size-3 shrink-0" />
                          <span>{blk}</span>
                        </li>
                      ))}
                    </ul>
                  )}

                  {cat.warnings_json.length > 0 && (
                    <ul className="mt-2 space-y-1">
                      {cat.warnings_json.map((w, i) => (
                        <li key={i} className="flex items-start gap-1.5 text-xs text-amber-700">
                          <FileWarning className="mt-0.5 size-3 shrink-0" />
                          <span>{w}</span>
                        </li>
                      ))}
                    </ul>
                  )}

                  {cat.missing_requirements.length > 0 && cat.blockers_json.length === 0 && (
                    <ul className="mt-2 space-y-1">
                      {cat.missing_requirements.map((m, i) => (
                        <li key={i} className="text-xs text-slate-600">
                          • {m}
                        </li>
                      ))}
                    </ul>
                  )}

                  {cat.recommendations.length > 0 && (
                    <p className="mt-2.5 rounded-lg bg-slate-50 px-2.5 py-2 text-[11.5px] text-slate-600">
                      <strong className="font-medium text-navy">Action:</strong> {cat.recommendations[0]}
                    </p>
                  )}
                </div>

                <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-line pt-3">
                  {cat.category === 'verification_completeness' ? (
                    <Button
                      variant="ghost"
                      size="sm"
                      iconRight={ExternalLink}
                      onClick={() => router.push(`/verification?project=${projectId}`)}
                    >
                      Open Verification Center
                    </Button>
                  ) : cat.category === 'conflict_resolution' ? (
                    <Button
                      variant="ghost"
                      size="sm"
                      iconRight={ExternalLink}
                      onClick={() => router.push('/conflicts')}
                    >
                      Open Conflict Management
                    </Button>
                  ) : cat.related_section_tab ? (
                    <Button
                      variant="ghost"
                      size="sm"
                      iconRight={ArrowRight}
                      onClick={() => onNavigateTab(cat.related_section_tab!)}
                    >
                      Inspect {formatLifecycleLabel(cat.related_section_tab)}
                    </Button>
                  ) : null}
                </div>
              </div>
            )
          })}
        </div>

        {/* 9th Category: Overall Quality Aggregate Row */}
        {overallCategory && (
          <div className="mt-4 rounded-xl border border-brand/25 bg-tint/25 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <Sparkles className="size-4 text-brand" />
                  <span className="text-[13.5px] font-semibold text-navy">
                    9. {overallCategory.label} (Weighted Aggregate)
                  </span>
                  <Badge tone={levelBadge(overallCategory.level).tone}>
                    {levelBadge(overallCategory.level).label}
                  </Badge>
                </div>
                <p className="mt-1 text-xs text-muted">
                  Composite score combining all 8 weighted dimensions above (15% Evidence + 20% Verification + 15% Conflicts + 10% Freshness + 10% Relationships + 15% Responsibilities + 5% Risks + 10% Dependencies).
                </p>
              </div>
              <div className="text-right">
                <span className="text-xl font-bold text-navy">{overallCategory.score}</span>
                <span className="text-xs text-muted"> / 100</span>
              </div>
            </div>
          </div>
        )}
      </Card>

      {/* 5. Verification Intelligence + 6. Evidence Completeness (2-Column Grid) */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Verification Intelligence */}
        {verification && (
          <Card className="p-5 sm:p-6">
            <div className="flex items-start justify-between gap-3 border-b border-line pb-4">
              <div>
                <div className="flex items-center gap-2">
                  <UserCheck className="size-4 text-brand" />
                  <h3 className="text-[15px] font-semibold text-navy">Verification Intelligence</h3>
                </div>
                <p className="mt-0.5 text-xs text-muted">
                  Live Verification Center coverage across project knowledge items and verification cases.
                </p>
              </div>
              <Button
                variant="secondary"
                size="sm"
                iconRight={ExternalLink}
                onClick={() => router.push(`/verification?project=${projectId}`)}
              >
                Open Queue
              </Button>
            </div>

            <div className="mt-4">
              <div className="flex items-center justify-between text-xs">
                <span className="font-medium text-navy">Reviewer Verification Coverage</span>
                <span className="font-semibold text-navy">
                  {verification.verification_coverage_pct}% ({verification.eligible_human_verified} /{' '}
                  {verification.total_knowledge_items})
                </span>
              </div>
              <Progress
                value={verification.verification_coverage_pct}
                tone={
                  verification.verification_coverage_pct >= 80
                    ? 'green'
                    : verification.verification_coverage_pct >= 50
                    ? 'amber'
                    : 'red'
                }
                className="mt-1.5"
              />
            </div>

            <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <div className="rounded-lg border border-line bg-slate-50/70 p-2.5">
                <p className="text-[11px] text-muted">Total Items</p>
                <p className="text-base font-bold text-navy">{verification.total_knowledge_items}</p>
              </div>
              <div className="rounded-lg border border-emerald-200 bg-emerald-50/50 p-2.5">
                <p className="text-[11px] text-emerald-700">Verified</p>
                <p className="text-base font-bold text-emerald-800">{verification.eligible_human_verified}</p>
              </div>
              <div className="rounded-lg border border-amber-200 bg-amber-50/50 p-2.5">
                <p className="text-[11px] text-amber-700">Pending</p>
                <p className="text-base font-bold text-amber-800">{verification.pending_verification}</p>
              </div>
              <div className="rounded-lg border border-line bg-slate-50/70 p-2.5">
                <p className="text-[11px] text-muted">Rejected</p>
                <p className="text-base font-bold text-slate-700">{verification.rejected_items}</p>
              </div>
            </div>

            {/* 6-Status Verification Case Breakdown */}
            <div className="mt-4">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                Verification Cases by Status
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                {Object.entries(verification.case_counts).map(([statusKey, count]) => (
                  <span
                    key={statusKey}
                    className="inline-flex items-center gap-1.5 rounded-full border border-line bg-white px-2.5 py-1 text-xs"
                  >
                    <span className="capitalize text-muted">{statusKey.replace(/_/g, ' ')}</span>
                    <strong className="font-semibold text-navy">{count}</strong>
                  </span>
                ))}
              </div>
            </div>

            {/* Recent Reviewer Activity */}
            <div className="mt-4 border-t border-line pt-4">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                Recent Reviewer Decisions
              </p>
              {verification.recent_reviews.length > 0 ? (
                <ul className="mt-2 space-y-2">
                  {verification.recent_reviews.slice(0, 4).map((ev) => (
                    <li
                      key={ev.id}
                      className="flex items-start justify-between gap-2 rounded-lg bg-slate-50/70 px-3 py-2 text-xs"
                    >
                      <div className="min-w-0">
                        <p className="truncate font-medium text-navy">
                          {ev.case_title || 'Verification finding'}
                        </p>
                        <p className="text-[11px] text-muted">
                          {ev.reviewer_name || 'Reviewer'} · {formatLifecycleLabel(ev.action)} →{' '}
                          {formatLifecycleLabel(ev.new_status)}
                        </p>
                      </div>
                      <span className="shrink-0 text-[11px] text-muted">
                        {formatDateTime(ev.created_at)}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-2 text-xs text-muted">
                  No reviewer verification decisions have been recorded for this project yet.
                </p>
              )}
            </div>
          </Card>
        )}

        {/* Evidence Completeness & Quality */}
        {evidence && (
          <Card className="p-5 sm:p-6">
            <div className="flex items-start justify-between gap-3 border-b border-line pb-4">
              <div>
                <div className="flex items-center gap-2">
                  <Database className="size-4 text-brand" />
                  <h3 className="text-[15px] font-semibold text-navy">Evidence Completeness & Quality</h3>
                </div>
                <p className="mt-0.5 text-xs text-muted">
                  Evidence backing, corroboration, staleness, and read-time source ACL visibility.
                </p>
              </div>
              <Button
                variant="secondary"
                size="sm"
                iconRight={ArrowRight}
                onClick={() => onNavigateTab('evidence')}
              >
                Evidence Tab
              </Button>
            </div>

            <div className="mt-4">
              <div className="flex items-center justify-between text-xs">
                <span className="font-medium text-navy">Knowledge Grounded in Source Evidence</span>
                <span className="font-semibold text-navy">
                  {evidence.evidence_coverage_pct}% ({evidence.items_with_evidence} /{' '}
                  {evidence.total_knowledge_items})
                </span>
              </div>
              <Progress
                value={evidence.evidence_coverage_pct}
                tone={evidence.evidence_coverage_pct >= 85 ? 'green' : 'amber'}
                className="mt-1.5"
              />
            </div>

            <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
              <div className="rounded-lg border border-line bg-slate-50/70 p-2.5">
                <p className="text-[11px] text-muted">Missing Evidence</p>
                <p className={cn('text-base font-bold', evidence.items_missing_evidence > 0 ? 'text-red-700' : 'text-navy')}>
                  {evidence.items_missing_evidence}
                </p>
              </div>
              <div className="rounded-lg border border-line bg-slate-50/70 p-2.5">
                <p className="text-[11px] text-muted">Corroborated</p>
                <p className="text-base font-bold text-emerald-700">{evidence.corroborated_items}</p>
              </div>
              <div className="rounded-lg border border-line bg-slate-50/70 p-2.5">
                <p className="text-[11px] text-muted">Uncertain Claims</p>
                <p className={cn('text-base font-bold', evidence.uncertain_items > 0 ? 'text-amber-700' : 'text-navy')}>
                  {evidence.uncertain_items}
                </p>
              </div>
              <div className="rounded-lg border border-line bg-slate-50/70 p-2.5">
                <p className="text-[11px] text-muted">Stale Knowledge</p>
                <p className={cn('text-base font-bold', evidence.stale_items > 0 ? 'text-amber-700' : 'text-navy')}>
                  {evidence.stale_items}
                </p>
              </div>
              <div className="rounded-lg border border-line bg-slate-50/70 p-2.5">
                <p className="text-[11px] text-muted">Superseded</p>
                <p className="text-base font-bold text-navy">{evidence.superseded_items}</p>
              </div>
              <div className="rounded-lg border border-line bg-slate-50/70 p-2.5">
                <p className="text-[11px] text-muted">Source Records</p>
                <p className="text-base font-bold text-navy">{evidence.total_evidence_sources}</p>
              </div>
            </div>

            {/* Source ACL Transparency Strip */}
            <div className="mt-4 rounded-xl border border-line bg-slate-50/80 p-3.5">
              <div className="flex items-center gap-2 text-xs font-semibold text-navy">
                <Lock className="size-3.5 text-brand" />
                Source Access Control (Fail-Closed Read-Time Enforcement)
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-4 text-xs text-muted">
                <span>
                  Authorised Accessible:{' '}
                  <strong className="font-semibold text-emerald-700">
                    {evidence.accessible_evidence_count}
                  </strong>
                </span>
                <span>
                  ACL-Restricted:{' '}
                  <strong
                    className={cn(
                      'font-semibold',
                      evidence.restricted_evidence_count > 0 ? 'text-amber-700' : 'text-navy'
                    )}
                  >
                    {evidence.restricted_evidence_count}
                  </strong>
                </span>
              </div>
              {evidence.restricted_evidence_count > 0 && (
                <p className="mt-1.5 text-[11.5px] text-amber-800">
                  Restricted external sources are redacted in accordance with delegated source ACL policies.
                </p>
              )}
            </div>
          </Card>
        )}
      </div>

      {/* 6. Conflict Management Integration Section */}
      {conflicts && (
        <Card className="overflow-hidden">
          <div className="flex flex-col gap-3 border-b border-line p-5 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <GitCompareArrows className="size-4 text-bad" />
                <h3 className="text-[15px] font-semibold text-navy">
                  Conflict Management Integration ({conflicts.total_conflicts})
                </h3>
                {conflicts.blocking_approval_count > 0 ? (
                  <Badge tone="red">{conflicts.blocking_approval_count} Blocking Approval</Badge>
                ) : (
                  <Badge tone="green">0 Blocking</Badge>
                )}
                {conflicts.critical_and_high_count > 0 && (
                  <Badge tone="red">{conflicts.critical_and_high_count} Critical/High</Badge>
                )}
              </div>
              <p className="mt-0.5 text-xs text-muted">
                Live canonical contradictions from Conflict Management. Conflicts cannot be auto-resolved from Handover; open Conflict Management to compare evidence and record a resolution.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <div className="inline-flex rounded-lg border border-line bg-slate-50 p-0.5 text-xs">
                {(['blocking', 'resolved', 'all'] as const).map((mode) => (
                  <button
                    key={mode}
                    type="button"
                    onClick={() => setConflictFilter(mode)}
                    className={cn(
                      'rounded-md px-2.5 py-1 font-medium capitalize transition',
                      conflictFilter === mode
                        ? 'bg-white text-navy shadow-sm'
                        : 'text-muted hover:text-navy'
                    )}
                  >
                    {mode} (
                    {mode === 'blocking'
                      ? conflicts.blocking_approval_count
                      : mode === 'resolved'
                      ? conflicts.resolved_conflicts
                      : conflicts.total_conflicts}
                    )
                  </button>
                ))}
              </div>
              <Button
                variant="secondary"
                size="sm"
                iconRight={ExternalLink}
                onClick={() => router.push('/conflicts')}
              >
                Open Workspace
              </Button>
            </div>
          </div>

          {/* Conflict Counters Bar */}
          <div className="grid grid-cols-2 gap-px border-b border-line bg-line sm:grid-cols-5">
            {[
              { label: 'Open / Unresolved', val: conflicts.open_conflicts, tone: 'text-red-700' },
              { label: 'Investigating', val: conflicts.under_investigation, tone: 'text-amber-700' },
              { label: 'Awaiting Context', val: conflicts.awaiting_context, tone: 'text-blue-700' },
              { label: 'Resolved', val: conflicts.resolved_conflicts, tone: 'text-emerald-700' },
              { label: 'Critical & High', val: conflicts.critical_and_high_count, tone: 'text-red-800' },
            ].map((item) => (
              <div key={item.label} className="bg-slate-50/70 px-4 py-3">
                <p className="text-[11px] text-muted">{item.label}</p>
                <p className={cn('text-base font-bold', item.tone)}>{item.val}</p>
              </div>
            ))}
          </div>

          {/* Conflict List */}
          {filteredConflicts.length === 0 ? (
            <div className="p-6 text-center text-xs text-muted">
              No {conflictFilter === 'all' ? '' : conflictFilter} conflicts found for this project.
            </div>
          ) : (
            <div className="max-h-[420px] divide-y divide-line overflow-y-auto">
              {filteredConflicts.map((cf) => {
                const st = conflictStateBadge(cf.resolution_state)
                return (
                  <div
                    key={cf.id}
                    className="flex flex-col gap-3 px-5 py-3.5 hover:bg-slate-50/70 sm:flex-row sm:items-start sm:justify-between"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge tone={severityTone(cf.priority)}>{cf.priority.toUpperCase()}</Badge>
                        <Badge tone={st.tone}>{st.label}</Badge>
                        <Badge tone="gray">{formatConflictType(cf.conflict_type)}</Badge>
                        {cf.acl_restricted && (
                          <Badge tone="amber">
                            <Lock className="mr-1 inline size-3" />
                            ACL Restricted Source
                          </Badge>
                        )}
                      </div>
                      <p className="mt-1.5 text-[13px] font-medium text-navy">{cf.explanation}</p>
                      {(cf.side_a_source_title || cf.side_b_source_title) && (
                        <div className="mt-2 grid gap-2 text-[11.5px] text-muted sm:grid-cols-2">
                          {cf.side_a_source_title && (
                            <div className="truncate rounded-md border border-line bg-slate-50 px-2.5 py-1">
                              <strong className="text-navy">Source A:</strong> {cf.side_a_source_title}
                            </div>
                          )}
                          {cf.side_b_source_title && (
                            <div className="truncate rounded-md border border-line bg-slate-50 px-2.5 py-1">
                              <strong className="text-navy">Source B:</strong> {cf.side_b_source_title}
                            </div>
                          )}
                        </div>
                      )}
                      {cf.resolution_notes && (
                        <p className="mt-1.5 text-xs text-emerald-700">
                          Resolution: {cf.resolution_notes}
                        </p>
                      )}
                    </div>
                    <div className="shrink-0">
                      <Button
                        variant="secondary"
                        size="sm"
                        iconRight={ExternalLink}
                        onClick={() => router.push(cf.conflict_url)}
                      >
                        Investigate
                      </Button>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </Card>
      )}

      {/* 7. Transition Checklists Integration (#readiness-checklists-section) */}
      <Card id="readiness-checklists-section" className="overflow-hidden">
        <div className="flex flex-col gap-3 border-b border-line p-5 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <ListChecks className="size-4 text-brand" />
              <h3 className="text-[15px] font-semibold text-navy">Transition Checklists & Mandatory Gates</h3>
              {checklists && (
                <Badge tone={checklists.mandatory_outstanding === 0 ? 'green' : 'amber'}>
                  {checklists.mandatory_completed}/{checklists.mandatory_total} Mandatory Done
                </Badge>
              )}
            </div>
            <p className="mt-0.5 text-xs text-muted">
              Persisted operational, knowledge transfer, and access revocation checklists. Mandatory blocking items must be completed before final approval.
            </p>
          </div>
          {checklists && checklists.total_groups > 0 ? (
            <div className="flex flex-wrap items-center gap-3">
              <div className="text-right">
                <p className="text-sm font-semibold text-navy">
                  {checklists.completed_items} / {checklists.total_items} completed ({checklists.completion_pct}%)
                </p>
                <Progress
                  value={checklists.completion_pct}
                  tone={checklists.mandatory_outstanding === 0 ? 'green' : 'blue'}
                  className="mt-1 w-44"
                />
              </div>
              <Button
                variant="secondary"
                size="sm"
                iconRight={ArrowRight}
                onClick={() => onNavigateTab('checklists')}
              >
                Manage Checklists
              </Button>
            </div>
          ) : (
            <Button
              size="sm"
              icon={isGeneratingChecklists ? Loader2 : ClipboardCheck}
              disabled={isGeneratingChecklists}
              onClick={() => onGenerateChecklists(projectId)}
            >
              {isGeneratingChecklists ? 'Generating…' : 'Generate Standard Checklists'}
            </Button>
          )}
        </div>

        {!checklists || checklists.groups.length === 0 ? (
          <div className="p-6 text-center text-xs text-muted">
            No transition checklists have been generated for this handover case yet.
          </div>
        ) : (
          <div className="grid gap-4 p-5 lg:grid-cols-3">
            {checklists.groups.map((grp) => (
              <div key={grp.id} className="rounded-xl border border-line bg-slate-50/40 p-4">
                <div className="flex items-start justify-between gap-2 border-b border-line pb-3">
                  <div>
                    <p className="text-[13.5px] font-semibold text-navy">{grp.title}</p>
                    <p className="text-[11px] text-muted">
                      {grp.completed_items}/{grp.total_items} done · {grp.mandatory_outstanding} mandatory left
                    </p>
                  </div>
                  <Badge tone={grp.mandatory_outstanding === 0 ? 'green' : 'amber'}>
                    {grp.mandatory_outstanding === 0 ? 'Gate Clear' : 'Blocking'}
                  </Badge>
                </div>
                <ul className="mt-3 space-y-2.5">
                  {grp.items.map((item) => {
                    const isDone = item.status === 'completed'
                    const isBusy = updatingChecklistItemId === item.id
                    return (
                      <li key={item.id} className="flex items-start gap-2.5">
                        <input
                          type="checkbox"
                          checked={isDone}
                          disabled={isBusy}
                          onChange={() => handleToggleChecklist(item.id, item.status)}
                          aria-label={item.item_text}
                          className="mt-0.5 size-4 cursor-pointer rounded border-slate-300 text-brand focus:ring-brand disabled:opacity-50"
                        />
                        <div className="min-w-0 flex-1">
                          <p
                            className={cn(
                              'text-xs leading-relaxed',
                              isDone ? 'text-muted line-through' : 'text-navy'
                            )}
                          >
                            {item.item_text}
                          </p>
                          <div className="mt-1 flex flex-wrap items-center gap-1.5">
                            {item.blocking ? (
                              <span className="rounded bg-red-100 px-1.5 py-0.5 text-[10px] font-semibold text-red-700">
                                Mandatory
                              </span>
                            ) : (
                              <span className="rounded bg-slate-200/70 px-1.5 py-0.5 text-[10px] font-medium text-slate-600">
                                Optional
                              </span>
                            )}
                            {item.category && (
                              <span className="text-[10px] capitalize text-muted">
                                {item.category.replace(/_/g, ' ')}
                              </span>
                            )}
                          </div>
                        </div>
                      </li>
                    )
                  })}
                </ul>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* 8. Persisted Readiness Assessment History */}
      <Card className="overflow-hidden">
        <CardHeader
          title={`Persisted Readiness Assessment History (${history.length})`}
          subtitle="Immutable chronological audit trail of readiness evaluations for this package version."
        />
        {history.length === 0 ? (
          <div className="p-6 text-center text-xs text-muted">No historical assessments recorded yet.</div>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Assessed At</Th>
                <Th>Score</Th>
                <Th>Status</Th>
                <Th>Blockers</Th>
                <Th>Warnings</Th>
                <Th>Assessed By</Th>
                <Th>Notes</Th>
              </tr>
            </thead>
            <tbody>
              {history.map((run, idx) => {
                const rb = levelBadge(run.overall_level)
                return (
                  <tr key={run.id} className={idx === 0 ? 'bg-tint/20' : undefined}>
                    <Td className="whitespace-nowrap text-xs font-medium text-navy">
                      {formatDateTime(run.assessed_at)}
                      {idx === 0 && (
                        <Badge tone="blue" className="ml-2">
                          Latest
                        </Badge>
                      )}
                    </Td>
                    <Td className="font-semibold text-navy">{run.overall_score}/100</Td>
                    <Td>
                      <Badge tone={rb.tone}>{rb.label}</Badge>
                    </Td>
                    <Td className={run.blocker_count > 0 ? 'font-semibold text-red-700' : 'text-muted'}>
                      {run.blocker_count}
                    </Td>
                    <Td className={run.warning_count > 0 ? 'font-semibold text-amber-700' : 'text-muted'}>
                      {run.warning_count}
                    </Td>
                    <Td className="text-xs text-navy">{run.assessed_by_name || 'System'}</Td>
                    <Td className="max-w-xs truncate text-xs text-muted">{run.notes || '—'}</Td>
                  </tr>
                )
              })}
            </tbody>
          </Table>
        )}
      </Card>
    </div>
  )
}
