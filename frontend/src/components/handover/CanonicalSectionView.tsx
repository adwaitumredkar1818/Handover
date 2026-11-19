'use client'

import React, { useState } from 'react'
import { useRouter } from 'next/navigation'
import {
  AlertTriangle,
  ArrowRight,
  BookOpen,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock,
  Cpu,
  Database,
  ExternalLink,
  FileText,
  GitBranch,
  KeyRound,
  Layers,
  Lightbulb,
  Link2,
  ListTodo,
  Loader2,
  Lock,
  Network,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Terminal,
  UserRoundCog,
  Users,
} from 'lucide-react'

import {
  Avatar,
  Badge,
  Button,
  Callout,
  Card,
  CardHeader,
  EmptyState,
  Modal,
  Table,
  Td,
  Th,
  cn,
} from '../figma-ui/index'
import { CardSkeleton, TableSkeleton } from '../loading'
import type {
  CanonicalHandoverSectionType,
  HandoverDomainEpistemicBreakdown,
  HandoverEvidenceProvenance,
  HandoverSectionConflictItem,
  HandoverSectionDetail,
  HandoverSectionKnowledgeItem,
  HandoverSectionRelationship,
  HandoverVersionSectionsResponse,
} from '../../lib/types'

export interface CanonicalDomainMeta {
  sectionType: CanonicalHandoverSectionType
  tab: string
  shortLabel: string
  title: string
  description: string
  emptyHint: string
  icon: typeof Lightbulb
}

export const CANONICAL_DOMAINS: CanonicalDomainMeta[] = [
  {
    sectionType: 'project_overview_context',
    tab: 'overview',
    shortLabel: 'Overview',
    title: 'Project Overview & Strategic Context',
    description: 'Project objectives, background, strategic scope, and verified high-level findings.',
    emptyHint: 'No human-verified strategic findings have been compiled into this section yet.',
    icon: BookOpen,
  },
  {
    sectionType: 'decisions_rationale',
    tab: 'decisions',
    shortLabel: 'Decisions',
    title: 'Key Architecture & Technical Decisions',
    description: 'Human-verified architectural and technical decisions with rationale and supporting evidence.',
    emptyHint: 'No human-verified architectural or technical decisions are eligible for this package version.',
    icon: Lightbulb,
  },
  {
    sectionType: 'technical_architecture',
    tab: 'architecture',
    shortLabel: 'Architecture',
    title: 'System Architecture, Services & Schemas',
    description: 'Verified system components, services, database structures, APIs, and technology stack.',
    emptyHint: 'No human-verified architecture, service, or schema records are available yet. Architecture details are never invented without evidence.',
    icon: Cpu,
  },
  {
    sectionType: 'work_progress',
    tab: 'tasks',
    shortLabel: 'Tasks & Work',
    title: 'Active Work, Backlog & In-Flight Tasks',
    description: 'Verified active work, completed deliverables, pending backlog, and outstanding actions.',
    emptyHint: 'No human-verified work progress or task items are included in this package version.',
    icon: ListTodo,
  },
  {
    sectionType: 'responsibilities_ownership',
    tab: 'responsibilities',
    shortLabel: 'Ownership',
    title: 'Component Ownership & Team Roles',
    description: 'Verified component owners, project team roles, and documented responsibility transfers.',
    emptyHint: 'No human-verified ownership findings are compiled yet. Active project members and formal transfer records are shown above.',
    icon: UserRoundCog,
  },
  {
    sectionType: 'dependencies_relationships',
    tab: 'dependencies',
    shortLabel: 'Dependencies',
    title: 'Upstream/Downstream Dependencies',
    description: 'Verified upstream/downstream dependencies, integration links, and component relationships.',
    emptyHint: 'No human-verified dependency records or verified knowledge relationships are included in this version.',
    icon: Network,
  },
  {
    sectionType: 'bugs_blockers_risks',
    tab: 'risks',
    shortLabel: 'Risks & Issues',
    title: 'Known Issues, Blockers & Open Risks',
    description: 'Confirmed human-verified issues and risks, separated clearly from unresolved verification conflicts.',
    emptyHint: 'No human-verified issues, blockers, or risks are included in this version.',
    icon: AlertTriangle,
  },
  {
    sectionType: 'operational_historical',
    tab: 'operations',
    shortLabel: 'Operations',
    title: 'Operational Procedures & Runbooks',
    description: 'Verified setup, configuration guidance, deployment runbooks, maintenance, and troubleshooting (secrets redacted).',
    emptyHint: 'No human-verified operational procedures or runbooks are available yet. Procedures are never fabricated without evidence.',
    icon: Terminal,
  },
]

export const TAB_TO_SECTION_TYPE: Record<string, CanonicalHandoverSectionType> = Object.fromEntries(
  CANONICAL_DOMAINS.map((d) => [d.tab, d.sectionType])
) as Record<string, CanonicalHandoverSectionType>

export const SECTION_TYPE_TO_TAB: Record<string, string> = Object.fromEntries(
  CANONICAL_DOMAINS.map((d) => [d.sectionType, d.tab])
)

function formatDate(iso?: string | null): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleDateString('en-GB', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    })
  } catch {
    return iso
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

function humanizeStatus(val?: string | null): string {
  if (!val) return 'Unknown'
  return val
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

/* ---------- Epistemic Breakdown Strip ---------- */
export function EpistemicBreakdownBar({
  breakdown,
  sectionSha,
  onOpenVerification,
  onOpenConflicts,
}: {
  breakdown: HandoverDomainEpistemicBreakdown
  sectionSha?: string | null
  onOpenVerification: () => void
  onOpenConflicts: () => void
}) {
  return (
    <div className="mb-4 flex flex-wrap items-center gap-2 rounded-xl border border-line bg-slate-50/70 px-4 py-2.5 text-xs">
      <Badge tone="green" icon={ShieldCheck}>
        {breakdown.human_verified_included} human-verified
      </Badge>
      {breakdown.pending_verification > 0 && (
        <button
          type="button"
          onClick={onOpenVerification}
          className="inline-flex items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-2.5 py-0.5 font-medium text-amber-800 hover:bg-amber-100"
        >
          <Clock className="size-3" />
          {breakdown.pending_verification} pending verification
        </button>
      )}
      {breakdown.unresolved_conflicts > 0 && (
        <button
          type="button"
          onClick={onOpenConflicts}
          className="inline-flex items-center gap-1 rounded-full border border-red-200 bg-red-50 px-2.5 py-0.5 font-medium text-red-700 hover:bg-red-100"
        >
          <ShieldAlert className="size-3" />
          {breakdown.unresolved_conflicts} unresolved conflicts
        </button>
      )}
      {breakdown.resolved_conflicts > 0 && (
        <Badge tone="indigo">{breakdown.resolved_conflicts} resolved conflicts</Badge>
      )}
      {breakdown.rejected > 0 && (
        <Badge tone="gray">{breakdown.rejected} rejected</Badge>
      )}
      {breakdown.outdated > 0 && (
        <Badge tone="amber">{breakdown.outdated} outdated</Badge>
      )}
      {sectionSha && (
        <span
          className="ml-auto font-mono text-[11px] text-slate-400"
          title={`Section SHA-256: ${sectionSha}`}
        >
          SHA-256: {sectionSha.slice(0, 12)}…
        </span>
      )}
    </div>
  )
}

/* ---------- Provenance Detail Modal ---------- */
export function ProvenanceDetailModal({
  item,
  projectId,
  onClose,
}: {
  item: HandoverSectionKnowledgeItem | null
  projectId: string
  onClose: () => void
}) {
  const router = useRouter()
  if (!item) return null

  return (
    <Modal
      open={Boolean(item)}
      onClose={onClose}
      title={item.title}
      subtitle={`Evidence Provenance & Verification Attribution · ${humanizeStatus(item.category)}`}
      footer={
        <div className="flex flex-wrap items-center justify-between gap-2 w-full">
          {item.verification.verification_case_id ? (
            <Button
              variant="secondary"
              size="sm"
              icon={ShieldCheck}
              onClick={() => router.push(`/verification?project=${projectId}`)}
            >
              Open in Verification Center
            </Button>
          ) : (
            <span />
          )}
          <Button size="sm" onClick={onClose}>
            Close
          </Button>
        </div>
      }
    >
      <div className="space-y-4 text-[13px]">
        <div className="flex flex-wrap gap-2">
          <Badge tone="green" icon={ShieldCheck}>
            {humanizeStatus(item.epistemic_status)}
          </Badge>
          <Badge tone="blue">{humanizeStatus(item.review_status)}</Badge>
          <Badge tone="indigo">{humanizeStatus(item.support_classification)}</Badge>
          {item.is_stale && <Badge tone="amber">Marked stale</Badge>}
        </div>

        <div className="rounded-xl border border-line bg-slate-50/70 p-3.5">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Verified Content</p>
          <p className="mt-1.5 whitespace-pre-wrap leading-relaxed text-navy">{item.content}</p>
        </div>

        <div className="rounded-xl border border-line p-3.5">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">
            Human Verification Decision
          </p>
          {item.verification.verification_case_id ? (
            <dl className="mt-2 grid gap-2 sm:grid-cols-2 text-xs">
              <div>
                <dt className="text-muted">Verification Case</dt>
                <dd className="font-mono text-navy">{item.verification.verification_case_id.slice(0, 12)}…</dd>
              </div>
              <div>
                <dt className="text-muted">Case Status</dt>
                <dd className="font-medium text-navy">{humanizeStatus(item.verification.case_status)}</dd>
              </div>
              <div>
                <dt className="text-muted">Reviewer Decision</dt>
                <dd className="font-medium text-navy">{humanizeStatus(item.verification.reviewer_decision || 'approved')}</dd>
              </div>
              <div>
                <dt className="text-muted">Reviewed By / At</dt>
                <dd className="font-medium text-navy">
                  {item.verification.reviewed_by_name || 'Verified Reviewer'} · {formatDateTime(item.verification.reviewed_at)}
                </dd>
              </div>
              {item.verification.review_notes && (
                <div className="sm:col-span-2">
                  <dt className="text-muted">Reviewer Notes</dt>
                  <dd className="mt-0.5 text-navy">{item.verification.review_notes}</dd>
                </div>
              )}
            </dl>
          ) : (
            <p className="mt-1.5 text-xs text-muted">
              Verification case metadata unavailable; item passed canonical human-verified eligibility checks.
            </p>
          )}
        </div>

        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
            Supporting Evidence Provenance ({item.provenance.length})
          </p>
          {!item.provenance_available ? (
            <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-3 text-xs text-muted">
              No supporting evidence provenance links were recorded for this finding.
            </div>
          ) : (
            <div className="space-y-2.5 max-h-72 overflow-y-auto pr-1">
              {item.provenance.map((ev, idx) => (
                <div key={`${ev.evidence_id}-${idx}`} className="rounded-xl border border-line bg-white p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      {ev.acl_restricted ? (
                        <Lock className="size-4 shrink-0 text-amber-600" />
                      ) : (
                        <FileText className="size-4 shrink-0 text-brand" />
                      )}
                      <span className="truncate font-semibold text-navy">{ev.source_name}</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <Badge tone={ev.acl_restricted ? 'amber' : 'gray'}>
                        {humanizeStatus(ev.source_type)}
                      </Badge>
                      <Badge tone="indigo">{humanizeStatus(ev.support_type)}</Badge>
                    </div>
                  </div>
                  {ev.acl_restricted ? (
                    <p className="mt-2 text-xs text-amber-800">
                      Source excerpt and external reference are restricted by delegated source permissions.
                    </p>
                  ) : (
                    <>
                      <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted">
                        {ev.source_reference && <span>Ref: {ev.source_reference}</span>}
                        {ev.author && <span>Author: {ev.author}</span>}
                        {ev.source_timestamp && <span>Source date: {formatDate(ev.source_timestamp)}</span>}
                        {ev.extracted_at && <span>Extracted: {formatDate(ev.extracted_at)}</span>}
                      </div>
                      {ev.supporting_excerpt && (
                        <blockquote className="mt-2 rounded-lg border-l-2 border-brand/50 bg-slate-50 px-3 py-2 text-xs italic text-slate-700 whitespace-pre-wrap">
                          “{ev.supporting_excerpt}”
                        </blockquote>
                      )}
                      <div className="mt-2 flex flex-wrap items-center gap-3 text-xs">
                        <button
                          type="button"
                          onClick={() => router.push(`/projects/${projectId}/evidence/${ev.evidence_id}`)}
                          className="inline-flex items-center gap-1 font-medium text-brand hover:underline"
                        >
                          <Link2 className="size-3" /> View Evidence Record
                        </button>
                        {ev.source_url && (
                          <a
                            href={ev.source_url}
                            target="_blank"
                            rel="noreferrer"
                            className="inline-flex items-center gap-1 font-medium text-slate-600 hover:text-navy hover:underline"
                          >
                            <ExternalLink className="size-3" /> Original Source
                          </a>
                        )}
                      </div>
                    </>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </Modal>
  )
}

/* ---------- Verified Knowledge Item Card ---------- */
function VerifiedKnowledgeCard({
  item,
  projectId,
  onInspectProvenance,
}: {
  item: HandoverSectionKnowledgeItem
  projectId: string
  onInspectProvenance: (it: HandoverSectionKnowledgeItem) => void
}) {
  const [expanded, setExpanded] = useState(false)
  const isLong = (item.content || '').length > 280
  const displayedContent = isLong && !expanded ? `${item.content.slice(0, 280)}…` : item.content

  // Extract displayable structured payload highlights (only persisted keys, never fabricated)
  const payloadHighlights = Object.entries(item.structured_payload || {})
    .filter(([k, v]) => {
      if (!v) return false
      if (['title', 'summary', 'description', 'structured_summary'].includes(k.toLowerCase())) return false
      if (typeof v === 'string') return v.trim().length > 0 && v.trim().length < 240
      if (Array.isArray(v)) return v.length > 0 && v.every((x) => typeof x === 'string')
      return false
    })
    .slice(0, 4)

  return (
    <div className="rounded-xl border border-line bg-white p-4 transition hover:border-slate-300">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h4 className="text-[14px] font-semibold text-navy">{item.title}</h4>
            <Badge tone="green" icon={ShieldCheck}>
              Human verified
            </Badge>
            {item.normalised_status && (
              <Badge tone="blue">{humanizeStatus(item.normalised_status)}</Badge>
            )}
            {item.is_stale && <Badge tone="amber">Outdated</Badge>}
          </div>
          <p className="mt-2 whitespace-pre-wrap text-[13px] leading-relaxed text-slate-700">
            {displayedContent}
          </p>
          {isLong && (
            <button
              type="button"
              onClick={() => setExpanded((e) => !e)}
              className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-brand hover:underline"
            >
              {expanded ? (
                <>
                  Show less <ChevronUp className="size-3" />
                </>
              ) : (
                <>
                  Read full content <ChevronDown className="size-3" />
                </>
              )}
            </button>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            icon={Link2}
            onClick={() => onInspectProvenance(item)}
          >
            Provenance ({item.provenance.length})
          </Button>
        </div>
      </div>

      {payloadHighlights.length > 0 && (
        <dl className="mt-3 grid gap-2 rounded-lg bg-slate-50/70 p-3 text-xs sm:grid-cols-2">
          {payloadHighlights.map(([k, v]) => (
            <div key={k}>
              <dt className="font-medium text-muted">{humanizeStatus(k)}</dt>
              <dd className="mt-0.5 text-navy">
                {Array.isArray(v) ? (v as string[]).join(', ') : String(v)}
              </dd>
            </div>
          ))}
        </dl>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 border-t border-line pt-2.5 text-[11.5px] text-muted">
        {item.owner_label && (
          <span>
            Owner: <strong className="font-medium text-navy">{item.owner_label}</strong>
          </span>
        )}
        <span>
          Support: <strong className="font-medium text-navy">{humanizeStatus(item.support_classification)}</strong>
        </span>
        {item.verification.reviewed_by_name && (
          <span>
            Verified by <strong className="font-medium text-navy">{item.verification.reviewed_by_name}</strong>
            {item.verification.reviewed_at ? ` · ${formatDate(item.verification.reviewed_at)}` : ''}
          </span>
        )}
        {!item.provenance_available ? (
          <span className="text-amber-700">Provenance: No linked evidence recorded</span>
        ) : (
          <span className="flex flex-wrap items-center gap-1.5">
            <span>Sources:</span>
            {item.provenance.slice(0, 2).map((ev, idx) => (
              <button
                key={`${ev.evidence_id}-${idx}`}
                type="button"
                onClick={() => onInspectProvenance(item)}
                className="inline-flex items-center gap-1 rounded bg-slate-100 px-1.5 py-0.5 font-medium text-navy hover:bg-tint"
              >
                {ev.acl_restricted ? <Lock className="size-2.5 text-amber-600" /> : <FileText className="size-2.5 text-brand" />}
                <span className="max-w-[160px] truncate">{ev.source_name}</span>
              </button>
            ))}
            {item.provenance.length > 2 && <span>+{item.provenance.length - 2} more</span>}
          </span>
        )}
      </div>
    </div>
  )
}

/* ---------- Verified Relationship Card (Domain 6 & Architecture) ---------- */
function VerifiedRelationshipRow({
  rel,
  projectId,
}: {
  rel: HandoverSectionRelationship
  projectId: string
}) {
  const router = useRouter()
  return (
    <div className="rounded-xl border border-line bg-white p-3.5">
      <div className="flex flex-wrap items-center gap-2 text-[13px]">
        <Badge tone="indigo">{humanizeStatus(rel.source_entity_type)}</Badge>
        <span className="font-semibold text-navy">{rel.source_entity_name}</span>
        <span className="inline-flex items-center gap-1 rounded-full bg-tint px-2 py-0.5 text-[11px] font-semibold text-brand">
          <ArrowRight className="size-3" />
          {humanizeStatus(rel.relationship_type)}
        </span>
        <Badge tone="indigo">{humanizeStatus(rel.target_entity_type)}</Badge>
        <span className="font-semibold text-navy">{rel.target_entity_name}</span>
        <span className="ml-auto flex items-center gap-1.5">
          <Badge tone="green" icon={ShieldCheck}>
            {humanizeStatus(rel.verification_status)}
          </Badge>
          {rel.is_stale && <Badge tone="amber">Stale</Badge>}
        </span>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-muted">
        <span>Confidence: {Math.round(rel.confidence_score * 100)}%</span>
        {rel.reviewed_at && <span>Verified {formatDate(rel.reviewed_at)}</span>}
        {rel.provenance_available ? (
          rel.provenance.slice(0, 2).map((ev, idx) => (
            <button
              key={`${ev.evidence_id}-${idx}`}
              type="button"
              disabled={ev.acl_restricted}
              onClick={() => !ev.acl_restricted && router.push(`/projects/${projectId}/evidence/${ev.evidence_id}`)}
              className="inline-flex items-center gap-1 rounded bg-slate-100 px-1.5 py-0.5 font-medium text-navy hover:bg-tint disabled:opacity-60"
            >
              {ev.acl_restricted ? <Lock className="size-2.5 text-amber-600" /> : <FileText className="size-2.5 text-brand" />}
              <span className="max-w-[160px] truncate">{ev.source_name}</span>
            </button>
          ))
        ) : (
          <span>Provenance unavailable</span>
        )}
      </div>
    </div>
  )
}

/* ---------- Conflict Card (Domain 7 — Strictly Separated From Verified Facts) ---------- */
function ConflictSeparationCard({
  conflict,
  projectId,
}: {
  conflict: HandoverSectionConflictItem
  projectId: string
}) {
  const router = useRouter()
  const isResolved = conflict.resolution_state === 'resolved' || conflict.resolution_state === 'dismissed'
  return (
    <div
      className={cn(
        'rounded-xl border p-4',
        isResolved ? 'border-line bg-slate-50/50' : 'border-red-200 bg-red-50/30'
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={isResolved ? 'green' : 'red'} icon={isResolved ? CheckCircle2 : ShieldAlert}>
            {isResolved ? 'Resolved conflict' : 'Unresolved conflict (Not a verified fact)'}
          </Badge>
          <Badge tone={conflict.priority === 'critical' || conflict.priority === 'high' ? 'red' : 'amber'}>
            {humanizeStatus(conflict.priority)} priority
          </Badge>
          <Badge tone="gray">{humanizeStatus(conflict.conflict_type)}</Badge>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => router.push(`/conflicts?project=${projectId}&conflict=${conflict.id}`)}
          >
            Inspect in Conflict Management
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => router.push(`/verification?project=${projectId}`)}
          >
            Verification Center
          </Button>
        </div>
      </div>

      <p className="mt-2.5 text-[13px] font-medium text-navy">{conflict.explanation}</p>

      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <div className="rounded-lg border border-line bg-white p-3">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
            Claim A {conflict.side_a_source_title ? `· ${conflict.side_a_source_title}` : ''}
          </p>
          <p className="mt-1 text-xs leading-relaxed text-slate-700">{conflict.claim_a_text}</p>
        </div>
        <div className="rounded-lg border border-line bg-white p-3">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
            Claim B {conflict.side_b_source_title ? `· ${conflict.side_b_source_title}` : ''}
          </p>
          <p className="mt-1 text-xs leading-relaxed text-slate-700">{conflict.claim_b_text}</p>
        </div>
      </div>

      {isResolved && (conflict.authoritative_claim_text || conflict.resolution_notes) && (
        <div className="mt-3 rounded-lg border border-teal-200 bg-teal-50/40 p-3 text-xs text-navy">
          <p className="font-semibold text-ok">Resolution Record {conflict.resolved_at ? `· ${formatDate(conflict.resolved_at)}` : ''}</p>
          {conflict.authoritative_claim_text && <p className="mt-1">{conflict.authoritative_claim_text}</p>}
          {conflict.resolution_notes && <p className="mt-1 text-muted">{conflict.resolution_notes}</p>}
        </div>
      )}
    </div>
  )
}

/* ---------- Main Eight-Domain Canonical Section Renderer ---------- */
export function CanonicalSectionPanel({
  sectionType,
  data,
  isLoading,
  error,
  projectId,
  handoverId,
  onRetry,
  onNavigateTab,
  overviewExtras,
}: {
  sectionType: CanonicalHandoverSectionType
  data: HandoverVersionSectionsResponse | null
  isLoading: boolean
  error: string | null
  projectId: string
  handoverId: string
  onRetry: () => void
  onNavigateTab: (tab: string) => void
  overviewExtras?: React.ReactNode
}) {
  const router = useRouter()
  const [inspectItem, setInspectItem] = useState<HandoverSectionKnowledgeItem | null>(null)

  const domainMeta = CANONICAL_DOMAINS.find((d) => d.sectionType === sectionType) || CANONICAL_DOMAINS[0]!
  const DomainIcon = domainMeta.icon

  if (isLoading) {
    return (
      <div className="space-y-4" role="status" aria-live="polite">
        <CardSkeleton variant="domain" count={3} />
      </div>
    )
  }

  if (error) {
    return (
      <Card className="p-6">
        <Callout tone="red" icon={AlertTriangle} title="Unable to load canonical handover sections">
          <p>{error}</p>
          <p className="mt-1 text-xs">
            Mock fallback data is strictly disabled. Retry to load persisted section records from the backend.
          </p>
          <div className="mt-3">
            <Button size="sm" variant="secondary" icon={RefreshCw} onClick={onRetry}>
              Retry loading sections
            </Button>
          </div>
        </Callout>
      </Card>
    )
  }

  if (!data) {
    return (
      <Card className="p-6">
        <EmptyState
          icon={Layers}
          title="No package version assembled yet"
          body="Assemble a handover package version to compile eligible human-verified knowledge across all eight canonical domains."
          action={
            <Button variant="secondary" onClick={() => router.push(`/verification?project=${projectId}`)}>
              Open Verification Center
            </Button>
          }
        />
      </Card>
    )
  }

  const section: HandoverSectionDetail | undefined = data.sections.find(
    (s) => s.section_type === sectionType
  )
  const isMissing = !section || data.missing_section_types.includes(sectionType)

  if (isMissing || !section) {
    return (
      <Card className="p-6">
        <EmptyState
          icon={DomainIcon}
          title={`${domainMeta.title} not included in Version v${data.version.version_number}`}
          body="This canonical domain section was not compiled into the selected package version snapshot. Select another version or re-assemble with all eight domains enabled."
        />
      </Card>
    )
  }

  const sectionSha =
    typeof section.metadata_json?.sha256 === 'string' ? section.metadata_json.sha256 : null
  const bd = section.epistemic_breakdown

  const openVerification = () => router.push(`/verification?project=${projectId}`)
  const openConflicts = () => router.push(`/conflicts?project=${projectId}`)

  const renderEmptyVerifiedState = () => {
    const pendingMsg =
      bd.pending_verification > 0
        ? `${bd.pending_verification} extracted knowledge item${bd.pending_verification === 1 ? '' : 's'} in this domain are awaiting human verification in Verification Center. Only human-verified, approved findings are eligible for handover packages.`
        : domainMeta.emptyHint

    return (
      <EmptyState
        icon={DomainIcon}
        title={`No verified items in ${domainMeta.shortLabel} yet`}
        body={pendingMsg}
        action={
          bd.pending_verification > 0 ? (
            <Button icon={ShieldCheck} onClick={openVerification}>
              Review {bd.pending_verification} pending in Verification Center
            </Button>
          ) : undefined
        }
      />
    )
  }

  /* ---- Domain 1: Project Overview & Strategic Context ---- */
  if (sectionType === 'project_overview_context') {
    const ctx = section.domain_context || {}
    const scopeAreas = Array.isArray((ctx.case_metadata as any)?.scope_areas)
      ? ((ctx.case_metadata as any).scope_areas as string[])
      : []

    return (
      <div className="space-y-5">
        <EpistemicBreakdownBar
          breakdown={data.epistemic_summary}
          sectionSha={sectionSha}
          onOpenVerification={openVerification}
          onOpenConflicts={openConflicts}
        />

        <div className="grid gap-5 lg:grid-cols-3">
          <Card className="p-5 lg:col-span-2">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-[15px] font-semibold text-navy">
                  {String(ctx.project_name || 'Project Overview & Strategic Context')}
                </p>
                <p className="mt-1 text-[13.5px] leading-relaxed text-slate-700">
                  {String(
                    ctx.project_description ||
                      ctx.case_description ||
                      'No project background description recorded yet.'
                  )}
                </p>
              </div>
              {Boolean(ctx.project_status) && (
                <Badge tone="blue">{humanizeStatus(String(ctx.project_status))}</Badge>
              )}
            </div>

            <dl className="mt-4 grid gap-3 rounded-xl bg-slate-50/70 p-3.5 text-xs sm:grid-cols-3">
              <div>
                <dt className="text-muted">Handover Scope</dt>
                <dd className="mt-0.5 font-medium text-navy">{String(ctx.case_title || '—')}</dd>
              </div>
              <div>
                <dt className="text-muted">Start / Target Date</dt>
                <dd className="mt-0.5 font-medium text-navy">
                  {formatDate(ctx.start_date as string | null)} → {formatDate(ctx.target_completion_date as string | null)}
                </dd>
              </div>
              <div>
                <dt className="text-muted">Package Snapshot</dt>
                <dd className="mt-0.5 font-mono text-navy">
                  v{data.version.version_number}
                  {data.version.content_hash ? ` · ${data.version.content_hash.slice(0, 10)}…` : ''}
                </dd>
              </div>
            </dl>

            {scopeAreas.length > 0 && (
              <div className="mt-3 flex flex-wrap items-center gap-1.5 text-xs">
                <span className="text-muted">Configured focus areas:</span>
                {scopeAreas.map((area) => (
                  <Badge key={area} tone="gray">
                    {area}
                  </Badge>
                ))}
              </div>
            )}
          </Card>

          <Card className="p-5">
            <p className="text-[15px] font-semibold text-navy">Epistemic Integrity Gate</p>
            <p className="mt-1 text-xs text-muted">
              Only human-verified knowledge enters handover content. Pending and conflicting items remain strictly separated.
            </p>
            <dl className="mt-4 space-y-2 text-[13px]">
              <div className="flex justify-between">
                <dt className="text-muted">Human-verified (included)</dt>
                <dd className="font-semibold text-ok">{data.epistemic_summary.human_verified_included}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-muted">Pending human verification</dt>
                <dd className="font-semibold text-amber-700">{data.epistemic_summary.pending_verification}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-muted">Unresolved conflicts</dt>
                <dd className="font-semibold text-bad">{data.epistemic_summary.unresolved_conflicts}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-muted">Rejected / outdated</dt>
                <dd className="font-semibold text-slate-500">
                  {data.epistemic_summary.rejected + data.epistemic_summary.outdated}
                </dd>
              </div>
            </dl>
            <div className="mt-4 flex flex-wrap gap-2">
              {data.epistemic_summary.pending_verification > 0 && (
                <Button size="sm" variant="secondary" icon={ShieldCheck} onClick={openVerification}>
                  Verify Findings
                </Button>
              )}
              {data.epistemic_summary.unresolved_conflicts > 0 && (
                <Button size="sm" variant="secondary" icon={ShieldAlert} onClick={openConflicts}>
                  Resolve Conflicts
                </Button>
              )}
            </div>
          </Card>
        </div>

        {/* Eight-Domain Canonical Coverage Matrix */}
        <Card className="p-5">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <h3 className="text-[15px] font-semibold text-navy">Canonical Eight-Domain Handover Coverage</h3>
              <p className="text-xs text-muted">
                Click any domain to inspect persisted verified findings, relationships, and provenance for Version v{data.version.version_number}.
              </p>
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {CANONICAL_DOMAINS.map((dom, index) => {
              const sec = data.sections.find((s) => s.section_type === dom.sectionType)
              const Ic = dom.icon
              const verifiedCount = (sec?.knowledge_items.length || 0) + (sec?.relationships.length || 0)
              const pendingCount = sec?.epistemic_breakdown.pending_verification || 0
              const conflictCount = sec?.unresolved_conflicts.length || 0
              return (
                <button
                  key={dom.sectionType}
                  type="button"
                  onClick={() => onNavigateTab(dom.tab)}
                  className="flex flex-col rounded-xl border border-line bg-slate-50/40 p-3.5 text-left transition hover:border-brand/40 hover:bg-tint/20"
                >
                  <div className="flex items-center justify-between">
                    <span className="flex items-center gap-1.5 text-xs font-semibold text-brand">
                      <Ic className="size-4" /> Domain {index + 1}
                    </span>
                    <Badge tone={verifiedCount > 0 ? 'green' : 'gray'}>
                      {verifiedCount} verified
                    </Badge>
                  </div>
                  <p className="mt-2 text-[13px] font-semibold text-navy">{dom.shortLabel}</p>
                  <p className="mt-1 line-clamp-2 text-[11.5px] text-muted">{dom.title}</p>
                  <div className="mt-auto flex flex-wrap gap-2 pt-2.5 text-[11px] text-muted">
                    {pendingCount > 0 && <span className="text-amber-700">{pendingCount} pending</span>}
                    {conflictCount > 0 && <span className="text-bad">{conflictCount} conflicts</span>}
                    {pendingCount === 0 && conflictCount === 0 && verifiedCount === 0 && (
                      <span>No records yet</span>
                    )}
                  </div>
                </button>
              )
            })}
          </div>
        </Card>

        {/* Verified Strategic Findings in Domain 1 */}
        <Card className="p-5">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <h3 className="text-[15px] font-semibold text-navy">Verified Strategic Context Findings</h3>
              <p className="text-xs text-muted">{domainMeta.description}</p>
            </div>
            <Badge tone="green">{section.knowledge_items.length} verified</Badge>
          </div>
          {section.knowledge_items.length > 0 ? (
            <div className="space-y-3">
              {section.knowledge_items.map((ki) => (
                <VerifiedKnowledgeCard
                  key={ki.id}
                  item={ki}
                  projectId={projectId}
                  onInspectProvenance={setInspectItem}
                />
              ))}
            </div>
          ) : (
            renderEmptyVerifiedState()
          )}
        </Card>

        {overviewExtras}

        <ProvenanceDetailModal
          item={inspectItem}
          projectId={projectId}
          onClose={() => setInspectItem(null)}
        />
      </div>
    )
  }

  /* ---- Domain 5: Component Ownership & Team Roles ---- */
  if (sectionType === 'responsibilities_ownership') {
    const teamMembers = Array.isArray(section.domain_context?.team_members)
      ? (section.domain_context.team_members as Array<{
          user_id: string
          full_name?: string | null
          email?: string | null
          role_name: string
          responsibility_description?: string | null
          is_departing_member?: boolean
          is_successor?: boolean
        }>)
      : []
    const transfers = Array.isArray(section.domain_context?.responsibility_transfers)
      ? (section.domain_context.responsibility_transfers as Array<{
          id: string
          responsibility_description: string
          knowledge_domain: string
          transfer_status: string
          transfer_notes?: string | null
          current_owner_name?: string | null
          proposed_successor_name?: string | null
        }>)
      : []

    return (
      <div className="space-y-5">
        <EpistemicBreakdownBar
          breakdown={bd}
          sectionSha={sectionSha}
          onOpenVerification={openVerification}
          onOpenConflicts={openConflicts}
        />

        <div className="grid gap-5 lg:grid-cols-2">
          <Card>
            <CardHeader
              title="Active Project Members & Roles"
              subtitle="Real project membership from PostgreSQL RBAC"
              icon={Users}
            />
            <div className="px-5 pb-5">
              {teamMembers.length === 0 ? (
                <p className="text-xs text-muted">No active project members found.</p>
              ) : (
                <ul className="space-y-2.5">
                  {teamMembers.map((m) => {
                    const displayName = m.full_name || m.email || 'Project Member'
                    return (
                      <li
                        key={m.user_id}
                        className="flex items-start gap-3 rounded-xl border border-line bg-slate-50/40 p-3"
                      >
                        <Avatar id={m.user_id} name={displayName} size={32} />
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-1.5">
                            <span className="text-[13px] font-semibold text-navy">{displayName}</span>
                            <Badge tone="blue">{humanizeStatus(m.role_name)}</Badge>
                            {m.is_departing_member && <Badge tone="amber">Outgoing</Badge>}
                            {m.is_successor && <Badge tone="green">Incoming</Badge>}
                          </div>
                          {m.email && <p className="text-xs text-muted">{m.email}</p>}
                          {m.responsibility_description && (
                            <p className="mt-1 text-xs text-slate-700">{m.responsibility_description}</p>
                          )}
                        </div>
                      </li>
                    )
                  })}
                </ul>
              )}
            </div>
          </Card>

          <Card>
            <CardHeader
              title="Documented Responsibility Transfers"
              subtitle="Persisted handover transfer records for this case"
              icon={UserRoundCog}
            />
            <div className="px-5 pb-5">
              {transfers.length === 0 ? (
                <EmptyState
                  icon={UserRoundCog}
                  title="No explicit responsibility transfers mapped"
                  body="Ownership is never fabricated. Add explicit responsibility transfers or verify extracted ownership items in Verification Center."
                />
              ) : (
                <ul className="space-y-2.5">
                  {transfers.map((t) => (
                    <li key={t.id} className="rounded-xl border border-line p-3 text-xs">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-semibold text-navy">{t.responsibility_description}</span>
                        <Badge tone={t.transfer_status === 'completed' ? 'green' : 'amber'}>
                          {humanizeStatus(t.transfer_status)}
                        </Badge>
                      </div>
                      <p className="mt-1 text-muted">
                        {t.current_owner_name || 'Current Owner'} → {t.proposed_successor_name || 'Unassigned'}
                      </p>
                      {t.transfer_notes && <p className="mt-1 text-slate-600">{t.transfer_notes}</p>}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </Card>
        </div>

        <Card className="p-5">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <h3 className="text-[15px] font-semibold text-navy">Verified Ownership & Responsibility Findings</h3>
              <p className="text-xs text-muted">{domainMeta.description}</p>
            </div>
            <Badge tone="green">{section.knowledge_items.length} verified</Badge>
          </div>
          {section.knowledge_items.length > 0 ? (
            <div className="space-y-3">
              {section.knowledge_items.map((ki) => (
                <VerifiedKnowledgeCard
                  key={ki.id}
                  item={ki}
                  projectId={projectId}
                  onInspectProvenance={setInspectItem}
                />
              ))}
            </div>
          ) : (
            renderEmptyVerifiedState()
          )}
        </Card>

        <ProvenanceDetailModal
          item={inspectItem}
          projectId={projectId}
          onClose={() => setInspectItem(null)}
        />
      </div>
    )
  }

  /* ---- Domain 6: Upstream/Downstream Dependencies ---- */
  if (sectionType === 'dependencies_relationships') {
    return (
      <div className="space-y-5">
        <EpistemicBreakdownBar
          breakdown={bd}
          sectionSha={sectionSha}
          onOpenVerification={openVerification}
          onOpenConflicts={openConflicts}
        />

        <Card className="p-5">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div>
              <h3 className="text-[15px] font-semibold text-navy">
                Verified Knowledge Relationships ({section.relationships.length})
              </h3>
              <p className="text-xs text-muted">
                Persisted upstream/downstream component and entity dependency links compiled into Version v{data.version.version_number}.
              </p>
            </div>
            <Button
              size="sm"
              variant="secondary"
              icon={GitBranch}
              onClick={() => router.push(`/projects/${projectId}/knowledge`)}
            >
              Open Relationship Explorer
            </Button>
          </div>

          {section.relationships.length > 0 ? (
            <div className="space-y-2.5">
              {section.relationships.map((rel) => (
                <VerifiedRelationshipRow key={rel.id} rel={rel} projectId={projectId} />
              ))}
            </div>
          ) : (
            <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50/60 p-4 text-xs text-muted">
              No human-verified relationship edges have been compiled into this package version yet.
            </div>
          )}
        </Card>

        <Card className="p-5">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <h3 className="text-[15px] font-semibold text-navy">
                Verified Dependency Findings ({section.knowledge_items.length})
              </h3>
              <p className="text-xs text-muted">{domainMeta.description}</p>
            </div>
          </div>
          {section.knowledge_items.length > 0 ? (
            <div className="space-y-3">
              {section.knowledge_items.map((ki) => (
                <VerifiedKnowledgeCard
                  key={ki.id}
                  item={ki}
                  projectId={projectId}
                  onInspectProvenance={setInspectItem}
                />
              ))}
            </div>
          ) : (
            renderEmptyVerifiedState()
          )}
        </Card>

        <ProvenanceDetailModal
          item={inspectItem}
          projectId={projectId}
          onClose={() => setInspectItem(null)}
        />
      </div>
    )
  }

  /* ---- Domain 7: Known Issues, Blockers & Open Risks ---- */
  if (sectionType === 'bugs_blockers_risks') {
    return (
      <div className="space-y-5">
        <EpistemicBreakdownBar
          breakdown={bd}
          sectionSha={sectionSha}
          onOpenVerification={openVerification}
          onOpenConflicts={openConflicts}
        />

        {/* Confirmed Issues & Risks */}
        <Card className="p-5">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <h3 className="text-[15px] font-semibold text-navy">
                Confirmed Issues, Blockers & Risks ({section.knowledge_items.length})
              </h3>
              <p className="text-xs text-muted">
                Human-verified issues, known limitations, and operational risks compiled into this version.
              </p>
            </div>
            <Badge tone="green" icon={ShieldCheck}>
              Human verified
            </Badge>
          </div>
          {section.knowledge_items.length > 0 ? (
            <div className="space-y-3">
              {section.knowledge_items.map((ki) => (
                <VerifiedKnowledgeCard
                  key={ki.id}
                  item={ki}
                  projectId={projectId}
                  onInspectProvenance={setInspectItem}
                />
              ))}
            </div>
          ) : (
            renderEmptyVerifiedState()
          )}
        </Card>

        {/* Unresolved Verification Conflicts — STRICTLY SEPARATED */}
        <Card className="p-5">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div>
              <h3 className="text-[15px] font-semibold text-navy">
                Unresolved Verification Conflicts ({section.unresolved_conflicts.length})
              </h3>
              <p className="text-xs text-muted">
                Contradictory claims detected across sources. Never presented as verified facts.
              </p>
            </div>
            <Button size="sm" variant="secondary" icon={ShieldAlert} onClick={openConflicts}>
              Open Conflict Management
            </Button>
          </div>

          {section.unresolved_conflicts.length > 0 ? (
            <div className="space-y-3">
              <Callout tone="amber" icon={AlertTriangle} title="Epistemic separation notice">
                These {section.unresolved_conflicts.length} contradiction{section.unresolved_conflicts.length === 1 ? '' : 's'} remain unresolved. They are excluded from confirmed handover facts and must be investigated by a human reviewer.
              </Callout>
              {section.unresolved_conflicts.map((cf) => (
                <ConflictSeparationCard key={cf.id} conflict={cf} projectId={projectId} />
              ))}
            </div>
          ) : (
            <div className="rounded-xl border border-line bg-slate-50/50 p-4 text-xs text-muted">
              No unresolved verification conflicts exist for this project.
            </div>
          )}
        </Card>

        {/* Resolved Conflicts */}
        {section.resolved_conflicts.length > 0 && (
          <Card className="p-5">
            <div className="mb-3">
              <h3 className="text-[15px] font-semibold text-navy">
                Resolved Conflicts ({section.resolved_conflicts.length})
              </h3>
              <p className="text-xs text-muted">
                Previously detected contradictions resolved with human review decisions.
              </p>
            </div>
            <div className="space-y-3">
              {section.resolved_conflicts.map((cf) => (
                <ConflictSeparationCard key={cf.id} conflict={cf} projectId={projectId} />
              ))}
            </div>
          </Card>
        )}

        <ProvenanceDetailModal
          item={inspectItem}
          projectId={projectId}
          onClose={() => setInspectItem(null)}
        />
      </div>
    )
  }

  /* ---- Domains 2, 3, 4, 8 (Decisions, Architecture, Work Progress, Operational Procedures) ---- */
  return (
    <div className="space-y-5">
      <EpistemicBreakdownBar
        breakdown={bd}
        sectionSha={sectionSha}
        onOpenVerification={openVerification}
        onOpenConflicts={openConflicts}
      />

      {sectionType === 'operational_historical' && (
        <Callout tone="blue" icon={KeyRound} title="Secret & credential safeguard">
          Operational runbooks and setup procedures are strictly sourced from human-verified evidence. Secrets, API keys, tokens, and sensitive credentials are automatically redacted and never displayed.
        </Callout>
      )}

      <Card className="p-5">
        <div className="mb-4 flex flex-wrap items-start justify-between gap-2">
          <div>
            <div className="flex items-center gap-2">
              <DomainIcon className="size-5 text-brand" />
              <h3 className="text-[15px] font-semibold text-navy">{section.section_title}</h3>
            </div>
            <p className="mt-0.5 text-xs text-muted">{domainMeta.description}</p>
          </div>
          <Badge tone={section.knowledge_items.length > 0 ? 'green' : 'gray'}>
            {section.knowledge_items.length} verified item{section.knowledge_items.length === 1 ? '' : 's'}
          </Badge>
        </div>

        {section.knowledge_items.length > 0 ? (
          <div className="space-y-3">
            {section.knowledge_items.map((ki) => (
              <VerifiedKnowledgeCard
                key={ki.id}
                item={ki}
                projectId={projectId}
                onInspectProvenance={setInspectItem}
              />
            ))}
          </div>
        ) : (
          renderEmptyVerifiedState()
        )}
      </Card>

      <ProvenanceDetailModal
        item={inspectItem}
        projectId={projectId}
        onClose={() => setInspectItem(null)}
      />
    </div>
  )
}

/* ---------- Evidence Provenance Table (For the Evidence Tab of HandoverWorkspace) ---------- */
export function CanonicalEvidenceTable({
  data,
  isLoading,
  error,
  projectId,
  onRetry,
}: {
  data: HandoverVersionSectionsResponse | null
  isLoading: boolean
  error: string | null
  projectId: string
  onRetry: () => void
}) {
  const router = useRouter()

  if (isLoading) {
    return (
      <div className="p-4" role="status" aria-live="polite">
        <TableSkeleton rows={5} columns={4} />
      </div>
    )
  }

  if (error) {
    return (
      <Card className="p-6">
        <Callout tone="red" icon={AlertTriangle} title="Unable to load evidence provenance">
          <p>{error}</p>
          <Button className="mt-3" size="sm" variant="secondary" icon={RefreshCw} onClick={onRetry}>
            Retry
          </Button>
        </Callout>
      </Card>
    )
  }

  // Deduplicate ACL-checked evidence referenced across all canonical sections in this version
  const evidenceMap = new Map<
    string,
    { ev: HandoverEvidenceProvenance; usedBySections: Set<string>; linkCount: number }
  >()

  if (data) {
    for (const sec of data.sections) {
      for (const ki of sec.knowledge_items) {
        for (const ev of ki.provenance) {
          const existing = evidenceMap.get(ev.evidence_id)
          if (existing) {
            existing.usedBySections.add(sec.section_title)
            existing.linkCount += 1
          } else {
            evidenceMap.set(ev.evidence_id, {
              ev,
              usedBySections: new Set([sec.section_title]),
              linkCount: 1,
            })
          }
        }
      }
      for (const rel of sec.relationships) {
        for (const ev of rel.provenance) {
          const existing = evidenceMap.get(ev.evidence_id)
          if (existing) {
            existing.usedBySections.add(sec.section_title)
            existing.linkCount += 1
          } else {
            evidenceMap.set(ev.evidence_id, {
              ev,
              usedBySections: new Set([sec.section_title]),
              linkCount: 1,
            })
          }
        }
      }
    }
  }

  const rows = Array.from(evidenceMap.values())

  if (rows.length === 0) {
    return (
      <Card className="p-6">
        <EmptyState
          icon={Database}
          title="No linked evidence in this package version yet"
          body="Only source evidence supporting human-verified findings compiled into this package version appears here."
          action={
            <Button variant="secondary" onClick={() => router.push(`/verification?project=${projectId}`)}>
              Open Verification Center
            </Button>
          }
        />
      </Card>
    )
  }

  return (
    <Card className="overflow-hidden">
      <Table>
        <thead>
          <tr>
            <Th>Evidence Source</Th>
            <Th>Type</Th>
            <Th>Author</Th>
            <Th>Source Date</Th>
            <Th>Cited By</Th>
            <Th>Access</Th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ ev, usedBySections, linkCount }) => (
            <tr
              key={ev.evidence_id}
              className={cn(ev.acl_restricted ? 'bg-amber-50/20' : 'cursor-pointer hover:bg-slate-50/70')}
              onClick={() => !ev.acl_restricted && router.push(`/projects/${projectId}/evidence/${ev.evidence_id}`)}
            >
              <Td>
                <div className="flex items-center gap-2.5">
                  {ev.acl_restricted ? (
                    <Lock className="size-4 shrink-0 text-amber-600" />
                  ) : (
                    <FileText className="size-4 shrink-0 text-brand" />
                  )}
                  <div className="min-w-0">
                    <p className="truncate font-medium text-navy">{ev.source_name}</p>
                    {ev.source_reference && !ev.acl_restricted && (
                      <p className="truncate text-xs text-muted">{ev.source_reference}</p>
                    )}
                  </div>
                </div>
              </Td>
              <Td className="text-xs">{humanizeStatus(ev.source_type)}</Td>
              <Td className="text-xs text-muted">{ev.acl_restricted ? 'Restricted' : ev.author || '—'}</Td>
              <Td className="text-xs text-muted">{ev.acl_restricted ? '—' : formatDate(ev.source_timestamp)}</Td>
              <Td className="text-xs text-navy">
                {linkCount} finding{linkCount === 1 ? '' : 's'} ({usedBySections.size} domain{usedBySections.size === 1 ? '' : 's'})
              </Td>
              <Td>
                {ev.acl_restricted ? (
                  <Badge tone="amber" icon={Lock}>
                    Restricted
                  </Badge>
                ) : (
                  <Badge tone="green" icon={ShieldCheck}>
                    Authorised
                  </Badge>
                )}
              </Td>
            </tr>
          ))}
        </tbody>
      </Table>
    </Card>
  )
}
