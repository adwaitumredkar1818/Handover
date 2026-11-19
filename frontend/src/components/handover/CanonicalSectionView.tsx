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
  Pencil,
  Plus,
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
  Field,
  Input,
  Modal,
  Select,
  Table,
  Td,
  Textarea,
  Th,
  cn,
} from '../figma-ui/index'
import { api } from '../../lib/api'
import type {
  CanonicalHandoverSectionType,
  HandoverContextContributionResponse,
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
  caseStatus,
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
  caseStatus?: string
  onRetry: () => void
  onNavigateTab: (tab: string) => void
  overviewExtras?: React.ReactNode
}) {
  const router = useRouter()
  const [inspectItem, setInspectItem] = useState<HandoverSectionKnowledgeItem | null>(null)

  // Contribute Missing Context state
  const [showContextModal, setShowContextModal] = useState(false)
  const [ctxCategory, setCtxCategory] = useState<string>(sectionType)
  const [ctxTitle, setCtxTitle] = useState('')
  const [ctxContent, setCtxContent] = useState('')
  const [ctxRationale, setCtxRationale] = useState('')
  const [ctxSubmitting, setCtxSubmitting] = useState(false)
  const [ctxError, setCtxError] = useState<string | null>(null)
  const [ctxResult, setCtxResult] = useState<HandoverContextContributionResponse | null>(null)

  // Section Narrative Drafting / Editing state
  const [showNarrativeModal, setShowNarrativeModal] = useState(false)
  const [narrativeDraft, setNarrativeDraft] = useState('')
  const [narrativeSummary, setNarrativeSummary] = useState('')
  const [narrativeExtraCtx, setNarrativeExtraCtx] = useState('')
  const [narrativeGenerating, setNarrativeGenerating] = useState(false)
  const [narrativeSaving, setNarrativeSaving] = useState(false)
  const [narrativeWarning, setNarrativeWarning] = useState<string | null>(null)
  const [narrativeError, setNarrativeError] = useState<string | null>(null)

  const domainMeta = CANONICAL_DOMAINS.find((d) => d.sectionType === sectionType) || CANONICAL_DOMAINS[0]!
  const DomainIcon = domainMeta.icon

  if (isLoading) {
    return (
      <Card className="p-10">
        <div className="flex flex-col items-center justify-center gap-3 text-center">
          <Loader2 className="size-6 animate-spin text-brand" />
          <p className="text-sm font-medium text-navy">Loading canonical section data…</p>
          <p className="text-xs text-muted">
            Retrieving persisted records, content links, and source-ACL-checked provenance.
          </p>
        </div>
      </Card>
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
  const normalizedStatus = (caseStatus || '').toLowerCase()
  const isLockedVersion =
    Boolean((data.version as unknown as { is_locked?: boolean })?.is_locked) ||
    ['approved', 'ready_for_delivery', 'delivered', 'published', 'acknowledged', 'transferred', 'completed'].includes(
      normalizedStatus
    )

  const handleOpenContextModal = () => {
    setCtxCategory(sectionType)
    setCtxTitle('')
    setCtxContent('')
    setCtxRationale('')
    setCtxError(null)
    setCtxResult(null)
    setShowContextModal(true)
  }

  const handleSubmitContext = async () => {
    if (!ctxTitle.trim() || !ctxContent.trim()) {
      setCtxError('Please enter both a clear title and the missing context details.')
      return
    }
    setCtxSubmitting(true)
    setCtxError(null)
    try {
      const res = await api.handover.contributeContext(projectId, handoverId, {
        category: ctxCategory,
        title: ctxTitle.trim(),
        content: ctxContent.trim(),
        rationale: ctxRationale.trim() || undefined,
      })
      setCtxResult(res)
      onRetry()
    } catch (err: unknown) {
      setCtxError(err instanceof Error ? err.message : 'Failed to contribute missing context.')
    } finally {
      setCtxSubmitting(false)
    }
  }

  const handleOpenNarrativeModal = () => {
    setNarrativeDraft(section.section_content || '')
    setNarrativeSummary(section.content_summary || '')
    setNarrativeExtraCtx('')
    setNarrativeWarning(null)
    setNarrativeError(null)
    setShowNarrativeModal(true)
  }

  const handleGenerateNarrativeDraft = async () => {
    setNarrativeGenerating(true)
    setNarrativeError(null)
    setNarrativeWarning(null)
    try {
      const res = await api.handover.draftSectionNarrative(projectId, handoverId, {
        version_id: section.version_id,
        section_type: section.section_type,
        additional_context: narrativeExtraCtx.trim() || undefined,
      })
      setNarrativeDraft(res.draft_content || '')
      if (res.content_summary && !narrativeSummary.trim()) {
        setNarrativeSummary(res.content_summary)
      }
      setNarrativeWarning(
        `AI-generated draft synthesized ${res.findings_count} verified finding(s) — review and edit before saving.`
      )
    } catch (err: unknown) {
      setNarrativeError(err instanceof Error ? err.message : 'Failed to generate AI narrative draft.')
    } finally {
      setNarrativeGenerating(false)
    }
  }

  const handleSaveNarrative = async () => {
    setNarrativeSaving(true)
    setNarrativeError(null)
    try {
      await api.handover.editSectionContent(projectId, section.id, {
        section_content: narrativeDraft,
        content_summary: narrativeSummary.trim() || undefined,
      })
      setShowNarrativeModal(false)
      onRetry()
    } catch (err: unknown) {
      setNarrativeError(err instanceof Error ? err.message : 'Failed to save section narrative.')
    } finally {
      setNarrativeSaving(false)
    }
  }

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

  const renderDomainBody = (): React.ReactNode => {
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

  const mandatoryMatch = (data.mandatory_sections || []).find((ms) =>
    ms.source_domains.includes(sectionType)
  )

  return (
    <div className="space-y-5">
      {/* Contribution, Drafting & Epistemic Notice Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line bg-white px-4 py-3 shadow-xs">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[13px] font-semibold text-navy">{section.section_title}</span>
            {data.handover_type_label && (
              <Badge tone="indigo">{data.handover_type_label}</Badge>
            )}
            {mandatoryMatch?.is_role_priority && (
              <Badge tone="blue" icon={Sparkles}>
                Priority for {data.handover_type_label || 'Role'}
              </Badge>
            )}
          </div>
          <p className="mt-0.5 text-xs text-muted">
            {mandatoryMatch?.role_emphasis_note ||
              data.role_focus_summary ||
              'All verified items remain linked to source evidence and human verification decisions.'}
          </p>
        </div>
        {!isLockedVersion && (
          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              variant="secondary"
              icon={Plus}
              onClick={handleOpenContextModal}
            >
              Contribute Missing Context
            </Button>
            <Button
              size="sm"
              variant="secondary"
              icon={Pencil}
              onClick={handleOpenNarrativeModal}
            >
              Draft / Edit Section Narrative
            </Button>
          </div>
        )}
      </div>

      {/* Persisted Human-Edited Section Narrative Summary (if authored) */}
      {(section.section_content || section.content_summary) && (
        <Card className="p-5">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <FileText className="size-4 text-brand" />
              <h3 className="text-sm font-semibold text-navy">Section Narrative Summary</h3>
              <Badge tone="blue">Handover Narrative</Badge>
            </div>
            {!isLockedVersion && (
              <Button size="sm" variant="ghost" icon={Pencil} onClick={handleOpenNarrativeModal}>
                Edit narrative
              </Button>
            )}
          </div>
          {section.content_summary && (
            <p className="mb-2 text-xs font-medium text-muted">{section.content_summary}</p>
          )}
          {section.section_content && (
            <p className="whitespace-pre-wrap text-[13.5px] leading-relaxed text-slate-700">
              {section.section_content}
            </p>
          )}
        </Card>
      )}

      {renderDomainBody()}

      {/* Contribute Missing Context Modal */}
      <Modal
        open={showContextModal}
        onClose={() => setShowContextModal(false)}
        title="Contribute Missing Handover Context"
        subtitle="Additions are recorded as attributable candidate evidence and queued in Verification Center — never auto-verified."
        footer={
          ctxResult ? (
            <div className="flex w-full items-center justify-between gap-2">
              <Button
                size="sm"
                variant="secondary"
                icon={ShieldCheck}
                onClick={() => {
                  setShowContextModal(false)
                  router.push(`/verification?project=${projectId}`)
                }}
              >
                Open in Verification Center
              </Button>
              <Button size="sm" onClick={() => setShowContextModal(false)}>
                Done
              </Button>
            </div>
          ) : (
            <div className="flex w-full justify-end gap-2">
              <Button variant="secondary" onClick={() => setShowContextModal(false)}>
                Cancel
              </Button>
              <Button
                icon={Plus}
                disabled={ctxSubmitting}
                onClick={() => void handleSubmitContext()}
              >
                {ctxSubmitting ? 'Submitting…' : 'Submit Candidate Context'}
              </Button>
            </div>
          )
        }
      >
        {ctxResult ? (
          <div className="space-y-3">
            <Callout tone="amber" icon={Clock} title="Recorded as candidate context (pending review)">
              <p className="text-xs">
                <strong>{ctxResult.title}</strong> has been stored with epistemic status{' '}
                <code>{ctxResult.epistemic_status}</code> and review status{' '}
                <code>{ctxResult.review_status}</code>. A human reviewer must approve it in Verification Center before it enters approved handover facts.
              </p>
              <p className="mt-1.5 font-mono text-[11px] text-amber-800">
                Verification Case: {ctxResult.verification_case_id}
              </p>
            </Callout>
          </div>
        ) : (
          <div className="space-y-4">
            <Callout tone="blue" icon={ShieldAlert} title="Strict Epistemic Rule">
              Contributed context is attributable to your account and remains unverified (
              <code>extracted</code> / <code>pending_review</code>) until confirmed in Verification Center.
            </Callout>
            {ctxError && (
              <Callout tone="red" icon={AlertTriangle} title="Submission error">
                {ctxError}
              </Callout>
            )}
            <Field label="Knowledge Domain Category">
              <Select value={ctxCategory} onChange={(e) => setCtxCategory(e.target.value)}>
                <option value="project_overview_context">Project Overview & Context</option>
                <option value="decisions_rationale">Decisions & Rationale</option>
                <option value="technical_architecture">Architecture & Technical Systems</option>
                <option value="work_progress">Completed & Unfinished Work</option>
                <option value="responsibilities_ownership">Responsibilities & Ownership</option>
                <option value="dependencies_relationships">Dependencies & Relationships</option>
                <option value="bugs_blockers_risks">Risks, Bugs & Blockers</option>
                <option value="operational_historical">Operations, Setup & Next Steps</option>
              </Select>
            </Field>
            <Field label="Short Title">
              <Input
                value={ctxTitle}
                onChange={(e) => setCtxTitle(e.target.value)}
                placeholder="e.g. Why Redis caching was deferred in Worker Lane B"
              />
            </Field>
            <Field label="Context Details (decisions, caveats, pending tasks, risks)">
              <Textarea
                rows={4}
                value={ctxContent}
                onChange={(e) => setCtxContent(e.target.value)}
                placeholder="Document concrete technical facts, constraints, owners, or open risks for your successor…"
              />
            </Field>
            <Field label="Rationale / Background (optional)">
              <Input
                value={ctxRationale}
                onChange={(e) => setCtxRationale(e.target.value)}
                placeholder="Why was this decision made or what blocks resolution?"
              />
            </Field>
          </div>
        )}
      </Modal>

      {/* Draft / Edit Section Narrative Modal */}
      <Modal
        open={showNarrativeModal}
        onClose={() => setShowNarrativeModal(false)}
        size="lg"
        title={`Edit Narrative — ${section.section_title}`}
        subtitle="Draft prose grounded in this section's human-verified findings, then edit and save."
        footer={
          <div className="flex w-full flex-wrap items-center justify-between gap-2">
            <Button
              size="sm"
              variant="secondary"
              icon={Sparkles}
              disabled={narrativeGenerating}
              onClick={() => void handleGenerateNarrativeDraft()}
            >
              {narrativeGenerating ? 'Generating Grounded Draft…' : 'Generate Grounded AI Draft'}
            </Button>
            <div className="flex items-center gap-2">
              <Button variant="secondary" onClick={() => setShowNarrativeModal(false)}>
                Cancel
              </Button>
              <Button
                icon={CheckCircle2}
                disabled={narrativeSaving}
                onClick={() => void handleSaveNarrative()}
              >
                {narrativeSaving ? 'Saving…' : 'Save Section Narrative'}
              </Button>
            </div>
          </div>
        }
      >
        <div className="space-y-4">
          {narrativeWarning && (
            <Callout tone="amber" icon={Sparkles} title="AI Assistance Notice">
              {narrativeWarning}
            </Callout>
          )}
          {narrativeError && (
            <Callout tone="red" icon={AlertTriangle} title="Narrative error">
              {narrativeError}
            </Callout>
          )}
          <Field label="Executive Summary Line (optional)">
            <Input
              value={narrativeSummary}
              onChange={(e) => setNarrativeSummary(e.target.value)}
              placeholder="Concise one-line takeaway for the successor…"
            />
          </Field>
          <Field label="Guidance for AI Draft (optional)">
            <Input
              value={narrativeExtraCtx}
              onChange={(e) => setNarrativeExtraCtx(e.target.value)}
              placeholder="e.g. Emphasise immediate day-1 risks and operational runbooks…"
            />
          </Field>
          <Field label="Section Narrative Markdown / Text">
            <Textarea
              rows={8}
              value={narrativeDraft}
              onChange={(e) => setNarrativeDraft(e.target.value)}
              placeholder="Write or generate the transition narrative grounded in approved findings…"
            />
          </Field>
        </div>
      </Modal>
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
      <Card className="p-10 text-center text-sm text-muted">
        <Loader2 className="mx-auto mb-2 size-5 animate-spin text-brand" />
        Loading linked provenance evidence…
      </Card>
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
