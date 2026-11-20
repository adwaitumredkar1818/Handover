'use client'

import React, { Suspense, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useRouter, useParams, useSearchParams } from 'next/navigation'
import {
  AlertTriangle, ArrowLeft, ArrowRight, BookOpen, Bot, Check, CheckCircle2, ChevronRight,
  CircleAlert, Copy, Download, ExternalLink, FileDown, FileQuestion, FileText, History,
  Layers, Lightbulb, Link2, ListTodo, Loader2, Lock, MessageSquare, MessageSquareText, Network,
  Pencil, Plus, Printer, RefreshCw, Rocket, Send, Share2, ShieldCheck, ShieldX, Sparkles,
  ThumbsDown, ThumbsUp, UserRound, Users, X, Compass, Cpu
} from 'lucide-react'

import { useStore } from '../../lib/figmaStore'
import {
  Avatar, Badge, Button, Callout, Card, CardHeader, EmptyState,
  Input, Modal, Select, Textarea, cn
} from '../figma-ui/index'
import { Logo } from '../figma-ui/brand'
import {
  HandoverLayout, HandoverNotFound, useHandover, HandoverWorkspace, Link,
  getMemberDisplayName, HANDOVER_TYPE_LABELS, isUUID
} from './HandoversPage'
import { useLiveApp } from '../../context/LiveAppContext'
import { api } from '../../lib/api'
import { SignoffApprovalPanel } from '../handover/SignoffApprovalPanel'
import { CANONICAL_DOMAINS, CanonicalSectionPanel } from '../handover/CanonicalSectionView'
import type {
  AssistantAnswerStatus,
  AssistantCitation,
  AssistantClaim,
  AssistantConversation,
  AssistantResponseMode,
  CanonicalHandoverSectionType,
  HandoverVersionSectionsResponse,
} from '../../lib/types'

/* ---------- 25. Sign-Off, Approval & Publication (Stage 6) ---------- */
export function Review({ id }: { id: string }) {
  const router = useRouter()
  const { activeProject, user, refreshHandovers } = useLiveApp()

  return (
    <HandoverLayout id={id} tab="review">
      {(h, _role, sectionsCtx) => {
        const resolvedPid = isUUID(h.projectId) ? h.projectId : activeProject?.id || h.projectId
        const navigateTab = (nextTab: string) => {
          const versionSuffix = sectionsCtx.selectedVersionId
            ? `&version=${sectionsCtx.selectedVersionId}`
            : ''
          if (nextTab === 'overview') {
            router.push(
              sectionsCtx.selectedVersionId
                ? `/handovers/${h.id}?version=${sectionsCtx.selectedVersionId}`
                : `/handovers/${h.id}`
            )
          } else if (nextTab === 'review') {
            router.push(`/handovers/${h.id}/review`)
          } else if (nextTab === 'recipient') {
            router.push(`/handovers/${h.id}/recipient`)
          } else {
            router.push(`/handovers/${h.id}?tab=${nextTab}${versionSuffix}`)
          }
        }

        return (
          <SignoffApprovalPanel
            caseId={h.id}
            projectId={resolvedPid}
            selectedVersionId={sectionsCtx.selectedVersionId}
            currentUserId={user?.id}
            onLifecycleChanged={() => {
              void refreshHandovers()
              sectionsCtx.retryLoadReadiness()
            }}
            onNavigateTab={navigateTab}
          />
        )
      }}
    </HandoverLayout>
  )
}

/* ---------- 26. Report ---------- */
const SECTIONS = [
  'Project Overview',
  'Role and Responsibilities',
  'Completed Work',
  'Ongoing Work',
  'Pending Tasks',
  'Technical Architecture',
  'Important Decisions',
  'Risks and Blockers',
  'Dependencies',
  'Important Contacts',
  'Recommended Next Actions',
  'Supporting Evidence'
]

export function Report({ id }: { id: string }) {
  const s = useStore()
  const { projects, activeProject, members, user } = useLiveApp()
  const [share, setShare] = useState(false)
  const [roleView, setRoleView] = useState<string>('')
  const [roleSectionsData, setRoleSectionsData] = useState<HandoverVersionSectionsResponse | null>(null)
  const [isLoadingRoleView, setIsLoadingRoleView] = useState(false)
  const [isExportingPdf, setIsExportingPdf] = useState(false)

  useEffect(() => {
    setRoleView('')
    setRoleSectionsData(null)
  }, [id])

  return (
    <HandoverLayout id={id} tab="report">
      {(h, _role, sectionsCtx) => {
        const p = projects.find((x) => x.id === h.projectId) || (activeProject?.id === h.projectId ? activeProject : null) || s.projects.find((x) => x.id === h.projectId)
        const pId = p?.id || h.projectId
        const pName = p?.name || activeProject?.name || 'Project'
        const outName = getMemberDisplayName(h.outgoingId, members, user)
        const incName = h.incomingId ? getMemberDisplayName(h.incomingId, members, user) : 'Unassigned'
        const baseData = sectionsCtx.sectionsData
        const effectiveData =
          roleView && roleSectionsData && roleSectionsData.handover_type === roleView
            ? roleSectionsData
            : baseData
        const mandatorySections = effectiveData?.mandatory_sections || []
        const canonicalSections = effectiveData?.sections || []
        const verifiedTotal = effectiveData?.epistemic_summary.human_verified_included ?? 0
        const pendingTotal = effectiveData?.epistemic_summary.pending_verification ?? 0
        const isApprovedRelease = ['approved', 'published', 'completed'].includes(h.status)
        const watermarkBanner = isApprovedRelease ? 'APPROVED RELEASE' : 'DRAFT — NOT APPROVED'
        const pubStatus =
          h.status === 'published'
            ? 'Published'
            : h.status === 'completed'
            ? 'Published · acknowledged'
            : h.status === 'approved'
            ? 'Approved · not yet published'
            : 'Draft · not published'

        const handleRoleViewChange = async (nextRole: string) => {
          setRoleView(nextRole)
          if (!nextRole || !sectionsCtx.selectedVersionId || !isUUID(pId)) {
            setRoleSectionsData(null)
            return
          }
          setIsLoadingRoleView(true)
          try {
            const resp = await api.handover.getVersionSections(
              pId,
              h.id,
              sectionsCtx.selectedVersionId,
              nextRole
            )
            setRoleSectionsData(resp)
          } catch (err: unknown) {
            s.toast(
              'Role switch failed',
              err instanceof Error ? err.message : 'Unable to load role presentation.',
              'error'
            )
          } finally {
            setIsLoadingRoleView(false)
          }
        }

        const downloadPdf = async () => {
          setIsExportingPdf(true)
          try {
            s.toast('Exporting PDF', 'Generating PDF handover package with server watermark…', 'info')
            const blob = await api.handover.exportPdf(pId, h.id, {
              versionId: sectionsCtx.selectedVersionId || undefined,
              role: roleView || undefined,
            })
            const url = URL.createObjectURL(blob)
            const a = document.createElement('a')
            a.href = url
            a.download = `${h.code}-handover.pdf`
            a.click()
            URL.revokeObjectURL(url)
            s.toast('PDF downloaded', `${h.code}-handover.pdf`, 'success')
          } catch (err: unknown) {
            console.error('PDF export error:', err)
            s.toast('PDF export failed', err instanceof Error ? err.message : 'Failed to export PDF', 'error')
          } finally {
            setIsExportingPdf(false)
          }
        }

        const downloadMarkdown = async () => {
          try {
            s.toast('Exporting Markdown', 'Generating markdown handover package...', 'info')
            const md = await api.handover.exportMarkdown(pId, h.id, {
              versionId: sectionsCtx.selectedVersionId || undefined,
              role: roleView || undefined,
            })
            const blob = new Blob([md], { type: 'text/markdown' })
            const url = URL.createObjectURL(blob)
            const a = document.createElement('a')
            a.href = url
            a.download = `${h.code}-handover.md`
            a.click()
            URL.revokeObjectURL(url)
            s.toast('Report downloaded', `${h.code}-handover.md`, 'success')
          } catch (err: unknown) {
            console.error('Markdown export error:', err)
            s.toast('Export failed', err instanceof Error ? err.message : 'Failed to export Markdown', 'error')
          }
        }

        const downloadJson = async () => {
          try {
            s.toast('Exporting JSON', 'Generating JSON handover package...', 'info')
            const jsonData = await api.handover.exportJson(pId, h.id, {
              versionId: sectionsCtx.selectedVersionId || undefined,
              role: roleView || undefined,
            })
            const blob = new Blob([JSON.stringify(jsonData, null, 2)], { type: 'application/json' })
            const url = URL.createObjectURL(blob)
            const a = document.createElement('a')
            a.href = url
            a.download = `${h.code}-handover.json`
            a.click()
            URL.revokeObjectURL(url)
            s.toast('Report downloaded', `${h.code}-handover.json`, 'success')
          } catch (err: unknown) {
            console.error('JSON export error:', err)
            s.toast('Export failed', err instanceof Error ? err.message : 'Failed to export JSON', 'error')
          }
        }

        const shareUrl = typeof window !== 'undefined' ? window.location.href : `/handovers/${h.id}/report`
        const activeRoleType = effectiveData?.handover_type || h.handoverType || 'developer'
        const activeRoleLabel =
          effectiveData?.handover_type_label ||
          HANDOVER_TYPE_LABELS[activeRoleType] ||
          'Developer Handover'

        return (
          <div className="grid gap-6 xl:grid-cols-[240px_1fr]">
            <div className="no-print hidden xl:block">
              <div className="sticky top-0 space-y-4">
                <Card className="p-4">
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">Publication status</p>
                  <Badge
                    tone={
                      h.status === 'published' || h.status === 'completed'
                        ? 'green'
                        : h.status === 'approved'
                        ? 'indigo'
                        : 'amber'
                    }
                    dot
                    className="mt-2"
                  >
                    {pubStatus}
                  </Badge>
                  <p className="mt-2 text-[11px] font-semibold text-navy">{activeRoleLabel}</p>
                  {effectiveData?.version.content_hash && (
                    <p className="mt-2 break-all font-mono text-[10px] text-slate-400">
                      v{effectiveData.version.version_number} · SHA-256: {effectiveData.version.content_hash.slice(0, 16)}…
                    </p>
                  )}
                </Card>
                <nav className="space-y-0.5">
                  {mandatorySections.length > 0
                    ? mandatorySections.map((ms) => (
                        <a
                          key={ms.section_key}
                          href={`#sec-${ms.section_number}`}
                          onClick={(e) => {
                            e.preventDefault()
                            document.getElementById(`sec-${ms.section_number}`)?.scrollIntoView({ behavior: 'smooth' })
                          }}
                          className="flex items-center justify-between gap-2 rounded-lg px-3 py-1.5 text-[12.5px] text-muted hover:bg-white hover:text-navy"
                        >
                          <span className="truncate">
                            {ms.section_number}. {ms.section_title}
                          </span>
                          {ms.is_role_priority && (
                            <span className="size-1.5 shrink-0 rounded-full bg-brand" title="Role priority" />
                          )}
                        </a>
                      ))
                    : canonicalSections.map((sec) => (
                        <a
                          key={sec.id}
                          href={`#sec-${sec.section_order}`}
                          onClick={(e) => {
                            e.preventDefault()
                            document.getElementById(`sec-${sec.section_order}`)?.scrollIntoView({ behavior: 'smooth' })
                          }}
                          className="block rounded-lg px-3 py-1.5 text-[13px] text-muted hover:bg-white hover:text-navy"
                        >
                          {sec.section_order}. {sec.section_title}
                        </a>
                      ))}
                </nav>
              </div>
            </div>
            <div>
              <div className="no-print mb-4 flex flex-wrap items-center gap-2">
                <Button icon={FileDown} disabled={isExportingPdf} onClick={() => void downloadPdf()}>
                  {isExportingPdf ? 'Generating PDF…' : 'Export PDF'}
                </Button>
                <Button variant="secondary" icon={FileText} onClick={() => void downloadMarkdown()}>
                  Export Markdown
                </Button>
                <Button variant="secondary" icon={Download} onClick={() => void downloadJson()}>
                  Export JSON
                </Button>
                <Button variant="secondary" icon={Share2} onClick={() => setShare(true)}>
                  Share
                </Button>
                <Button variant="secondary" icon={Printer} onClick={() => window.print()}>
                  Print
                </Button>
                <div className="ml-auto flex items-center gap-2">
                  <span className="text-xs font-medium text-muted">Role view:</span>
                  <Select
                    aria-label="Handover role view"
                    className="h-9 w-52 text-xs"
                    value={roleView || activeRoleType}
                    onChange={(e) => void handleRoleViewChange(e.target.value)}
                  >
                    <option value="developer">Developer Handover</option>
                    <option value="project_manager">Project Manager Handover</option>
                    <option value="technical_lead">Technical Lead Handover</option>
                  </Select>
                </div>
              </div>
              <article className="mx-auto max-w-[860px] rounded-2xl border border-line bg-white px-6 py-8 shadow-card sm:px-12 sm:py-12">
                <header className="mb-8 border-b-2 border-navy pb-6">
                  <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
                    <Logo size={24} />
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone={isApprovedRelease ? 'green' : 'amber'} icon={isApprovedRelease ? ShieldCheck : Lock}>
                        {watermarkBanner}
                      </Badge>
                      <Badge tone="indigo">{activeRoleLabel}</Badge>
                      <span className="text-xs font-medium text-muted">
                        {h.code} · {effectiveData ? `Version v${effectiveData.version.version_number}` : 'Draft'}
                      </span>
                    </div>
                  </div>
                  <p className="mt-6 text-xs font-semibold uppercase tracking-[0.2em] text-brand">Handover Report</p>
                  <h1 className="mt-2 text-3xl font-semibold tracking-tight text-navy">{pName}</h1>
                  <p className="mt-1 text-sm text-muted">{h.scope}</p>
                  {effectiveData?.role_focus_summary && (
                    <p className="mt-2 text-xs text-slate-600">{effectiveData.role_focus_summary}</p>
                  )}
                  <dl className="mt-6 grid grid-cols-2 gap-4 text-[13px] sm:grid-cols-4">
                    {[
                      ['Outgoing', outName],
                      ['Incoming', incName],
                      ['Target Date', h.due],
                      ['Verified', `${verifiedTotal} verified (${pendingTotal} pending)`]
                    ].map(([k, val]) => (
                      <div key={k}>
                        <dt className="text-[11px] uppercase tracking-wide text-slate-400">{k}</dt>
                        <dd className="mt-0.5 font-medium text-navy">{val}</dd>
                      </div>
                    ))}
                  </dl>
                  <p className="mt-5 rounded-lg bg-slate-50 px-3 py-2 text-xs text-muted">
                    <ShieldCheck className="mr-1 inline size-3.5 text-ok" />
                    Only human-verified knowledge compiled into this immutable package version appears as confirmed handover content. Unresolved conflicts and unverified items are explicitly separated.
                  </p>
                </header>
                {sectionsCtx.isLoadingSections || sectionsCtx.isLoadingVersions || isLoadingRoleView ? (
                  <div className="py-10 text-center text-sm text-muted">Loading canonical report sections…</div>
                ) : sectionsCtx.sectionsError ? (
                  <Callout tone="red" icon={AlertTriangle} title="Unable to load report sections">
                    {sectionsCtx.sectionsError}
                  </Callout>
                ) : mandatorySections.length > 0 ? (
                  <div className="space-y-8">
                    {mandatorySections.map((ms) => (
                      <section key={ms.section_key} id={`sec-${ms.section_number}`} className="scroll-mt-6 border-t border-line pt-6 first:border-0 first:pt-0">
                        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="font-mono text-xs font-semibold text-brand">
                              {String(ms.section_number).padStart(2, '0')}
                            </span>
                            <h2 className="text-[16px] font-semibold text-navy">{ms.section_title}</h2>
                            {ms.is_role_priority && (
                              <Badge tone="blue" icon={Sparkles}>Priority</Badge>
                            )}
                          </div>
                          <div className="flex items-center gap-2">
                            <Badge
                              tone={
                                ms.readiness_status === 'ready'
                                  ? 'green'
                                  : ms.readiness_status === 'has_conflicts'
                                  ? 'red'
                                  : 'amber'
                              }
                            >
                              {ms.readiness_status.replace(/_/g, ' ')}
                            </Badge>
                            <span className="text-xs text-muted">
                              {ms.knowledge_items.length} verified · {ms.evidence_references.length} sources
                            </span>
                          </div>
                        </div>
                        {ms.role_emphasis_note && (
                          <p className="mb-3 text-xs text-muted">{ms.role_emphasis_note}</p>
                        )}
                        {ms.insufficient_info_message && (
                          <div className="mb-3 rounded-lg border border-amber-200 bg-amber-50/70 p-3 text-xs text-amber-900">
                            <AlertTriangle className="mr-1.5 inline size-3.5 text-warn" />
                            {ms.insufficient_info_message}
                          </div>
                        )}
                        <div className="space-y-3 text-[13.5px] leading-relaxed text-slate-700">
                          {ms.knowledge_items.map((ki) => (
                            <div key={ki.id} className="rounded-lg border border-line bg-slate-50/40 p-3.5">
                              <p className="font-semibold text-navy">
                                {ki.title}
                                <ShieldCheck className="ml-1.5 inline size-3.5 text-ok" />
                              </p>
                              <p className="mt-1 whitespace-pre-wrap text-[13px] text-slate-700">{ki.content}</p>
                              <p className="mt-1.5 text-[11px] text-muted">
                                {ki.provenance_available
                                  ? `Sources: ${ki.provenance.map((ev) => ev.source_name || 'Restricted').join(', ')}`
                                  : 'Provenance: No linked source recorded'}
                              </p>
                            </div>
                          ))}
                          {ms.relationships.length > 0 && (
                            <ul className="list-disc space-y-1 pl-5 text-[13px]">
                              {ms.relationships.map((rel) => (
                                <li key={rel.id}>
                                  <span className="font-medium text-navy">{rel.source_entity_name}</span>{' '}
                                  <span className="text-brand">[{rel.relationship_type}]</span>{' '}
                                  <span className="font-medium text-navy">{rel.target_entity_name}</span>
                                </li>
                              ))}
                            </ul>
                          )}
                          {ms.responsibilities_summary.length > 0 && (
                            <ul className="list-disc space-y-1 pl-5 text-[13px]">
                              {ms.responsibilities_summary.map((r, rIdx) => (
                                <li key={rIdx}>
                                  <span className="font-medium text-navy">{String(r.responsibility_title || r.title || 'Responsibility')}</span>{' '}
                                  — Status: {String(r.transfer_status || 'pending')}
                                </li>
                              ))}
                            </ul>
                          )}
                          {ms.recommended_steps.length > 0 && (
                            <ul className="list-disc space-y-1 pl-5 text-[13px]">
                              {ms.recommended_steps.map((st, sIdx) => (
                                <li key={sIdx}>
                                  [{String(st.status || 'pending')}] <span className="font-medium text-navy">{String(st.title || '')}</span>
                                </li>
                              ))}
                            </ul>
                          )}
                          {ms.unresolved_conflicts.length > 0 && (
                            <div className="rounded-lg border border-red-200 bg-red-50/40 p-3">
                              <p className="text-xs font-semibold text-bad">
                                Unresolved Verification Conflicts ({ms.unresolved_conflicts.length} — Excluded from Verified Facts)
                              </p>
                              <ul className="mt-1.5 list-disc space-y-1 pl-4 text-xs text-slate-700">
                                {ms.unresolved_conflicts.map((cf) => (
                                  <li key={cf.id}>{cf.explanation}</li>
                                ))}
                              </ul>
                            </div>
                          )}
                        </div>
                      </section>
                    ))}
                  </div>
                ) : (
                  <div className="space-y-8">
                    {canonicalSections.map((sec) => (
                      <section key={sec.id} id={`sec-${sec.section_order}`} className="scroll-mt-6 border-t border-line pt-6 first:border-0 first:pt-0">
                        <div className="mb-3 flex items-center justify-between">
                          <h2 className="flex items-baseline gap-3 text-[16px] font-semibold text-navy">
                            <span className="font-mono text-xs font-medium text-brand">{String(sec.section_order).padStart(2, '0')}</span>
                            {sec.section_title}
                          </h2>
                          <span className="text-xs text-muted">
                            {sec.knowledge_items.length} verified · {sec.relationships.length} relationships
                          </span>
                        </div>
                        <div className="space-y-3 text-[13.5px] leading-relaxed text-slate-700">
                          {sec.knowledge_items.length === 0 && sec.relationships.length === 0 && sec.unresolved_conflicts.length === 0 && (
                            <p className="text-xs italic text-muted">
                              No human-verified items included in this domain for Version v{effectiveData?.version.version_number}.
                              {sec.epistemic_breakdown.pending_verification > 0
                                ? ` (${sec.epistemic_breakdown.pending_verification} extracted items are awaiting human verification.)`
                                : ''}
                            </p>
                          )}
                          {sec.knowledge_items.map((ki) => (
                            <div key={ki.id} className="rounded-lg border border-line bg-slate-50/40 p-3.5">
                              <p className="font-semibold text-navy">
                                {ki.title}
                                <ShieldCheck className="ml-1.5 inline size-3.5 text-ok" />
                              </p>
                              <p className="mt-1 whitespace-pre-wrap text-[13px] text-slate-700">{ki.content}</p>
                              <p className="mt-1.5 text-[11px] text-muted">
                                {ki.provenance_available
                                  ? `Sources: ${ki.provenance.map((ev) => ev.source_name).join(', ')}`
                                  : 'Provenance: No linked source recorded'}
                              </p>
                            </div>
                          ))}
                        </div>
                      </section>
                    ))}
                  </div>
                )}
                <footer className="mt-10 border-t border-line pt-4 text-[11px] text-slate-400">
                  Generated by The Handover from persisted canonical package sections. Only human-verified knowledge is presented as confirmed handover content.
                </footer>
              </article>
              <Modal
                open={share}
                onClose={() => setShare(false)}
                title="Share report"
                subtitle="Only people with project access can open this link"
                footer={<Button onClick={() => setShare(false)}>Done</Button>}
              >
                <div className="flex gap-2">
                  <Input readOnly value={shareUrl} />
                  <Button
                    variant="secondary"
                    icon={Copy}
                    onClick={() => {
                      navigator.clipboard?.writeText(shareUrl)
                      s.toast('Link copied')
                    }}
                  >
                    Copy
                  </Button>
                </div>
                <p className="mb-2 mt-5 text-[13px] font-medium text-navy">Project members with access</p>
                <ul className="space-y-2">
                  {(members.length > 0
                    ? members.map((m) => ({
                        id: m.user_id || m.id,
                        name: m.full_name || m.email || 'Project Member',
                        role: m.role_name || 'Member',
                      }))
                    : [h.outgoingId, h.incomingId]
                        .filter(Boolean)
                        .map((pid) => ({
                          id: pid,
                          name: getMemberDisplayName(pid, members, user),
                          role: pid === h.incomingId ? 'Incoming' : 'Outgoing',
                        }))
                  ).map((person) => (
                    <li key={person.id} className="flex items-center gap-2.5">
                      <Avatar id={person.id} name={person.name} size={28} />
                      <span className="flex-1 text-[13px] text-navy">{person.name}</span>
                      <span className="text-xs text-muted">{person.role}</span>
                    </li>
                  ))}
                </ul>
              </Modal>
            </div>
          </div>
        )
      }}
    </HandoverLayout>
  )
}

/* ---------- 29. Incoming Recipient Acknowledgement & Complete Package View (Stage 6) ---------- */
export function RecipientWorkspace({ id }: { id: string }) {
  const router = useRouter()
  const { activeProject, user, refreshHandovers } = useLiveApp()
  const [selectedDomain, setSelectedDomain] = useState<CanonicalHandoverSectionType>('project_overview_context')
  const [readerMode, setReaderMode] = useState<'mandatory' | 'canonical'>('mandatory')
  const [selectedMandatoryKey, setSelectedMandatoryKey] = useState<string>('executive_overview')

  return (
    <HandoverLayout id={id} tab="overview">
      {(h, _role, sectionsCtx) => {
        const resolvedPid = isUUID(h.projectId) ? h.projectId : activeProject?.id || h.projectId
        const navigateTab = (nextTab: string) => {
          const versionSuffix = sectionsCtx.selectedVersionId
            ? `&version=${sectionsCtx.selectedVersionId}`
            : ''
          if (nextTab === 'overview') {
            router.push(
              sectionsCtx.selectedVersionId
                ? `/handovers/${h.id}?version=${sectionsCtx.selectedVersionId}`
                : `/handovers/${h.id}`
            )
          } else if (nextTab === 'review') {
            router.push(`/handovers/${h.id}/review`)
          } else if (nextTab === 'recipient') {
            router.push(`/handovers/${h.id}/recipient`)
          } else {
            router.push(`/handovers/${h.id}?tab=${nextTab}${versionSuffix}`)
          }
        }

        const sectionCounts = new Map(
          (sectionsCtx.sectionsData?.sections || []).map((sec) => [
            sec.section_type,
            sec.knowledge_items.length + sec.relationships.length + sec.unresolved_conflicts.length,
          ])
        )
        const mandatoryList = sectionsCtx.sectionsData?.mandatory_sections || []
        const activeMandatory =
          mandatoryList.find((m) => m.section_key === selectedMandatoryKey) || mandatoryList[0] || null
        const effectiveMode = mandatoryList.length > 0 ? readerMode : 'canonical'

        const recommendedActions = mandatoryList.flatMap((m) => m.recommended_steps || []).slice(0, 4)
        const unresolvedTotal = sectionsCtx.sectionsData?.epistemic_summary?.unresolved_conflicts ?? 0
        const handoverTypeLabel =
          sectionsCtx.sectionsData?.handover_type_label ||
          HANDOVER_TYPE_LABELS[h.handoverType || 'developer'] ||
          'Developer Handover'

        return (
          <div className="space-y-6" data-testid="recipient-workspace">
            {/* Guided Successor Onboarding Summary */}
            <Card className="border-brand/20 bg-tint/20 p-5">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                <div className="space-y-1.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <Compass className="size-4 text-brand" />
                    <span className="text-sm font-semibold text-navy">Guided Successor Onboarding</span>
                    <Badge tone="indigo">{handoverTypeLabel}</Badge>
                    <Badge tone={h.status === 'completed' ? 'green' : 'amber'}>
                      {h.status === 'completed' ? 'Receipt Acknowledged' : `Target Date: ${h.due}`}
                    </Badge>
                    {unresolvedTotal > 0 && (
                      <Badge tone="red">{unresolvedTotal} unresolved conflict(s)</Badge>
                    )}
                  </div>
                  <p className="text-xs text-slate-600">
                    {sectionsCtx.sectionsData?.role_focus_summary ||
                      'Inspect verified decisions, architecture, open risks, and recommended first steps below, then record your acknowledgement.'}
                  </p>
                  {recommendedActions.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-2">
                      {recommendedActions.map((st, idx) => (
                        <span
                          key={idx}
                          className="inline-flex items-center gap-1 rounded-lg border border-line bg-white px-2.5 py-1 text-[11px] font-medium text-navy"
                        >
                          <ListTodo className="size-3 text-brand" />
                          {String(st.title || 'Next step')}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                <div className="flex shrink-0 flex-wrap gap-2">
                  <Button
                    size="sm"
                    variant="secondary"
                    icon={Bot}
                    onClick={() => router.push(`/handovers/${h.id}/assistant`)}
                  >
                    Ask Handover Assistant
                  </Button>
                  <Button
                    size="sm"
                    variant="secondary"
                    icon={FileText}
                    onClick={() => router.push(`/handovers/${h.id}/report`)}
                  >
                    Export Package Report
                  </Button>
                </div>
              </div>
            </Card>

            <SignoffApprovalPanel
              caseId={h.id}
              projectId={resolvedPid}
              selectedVersionId={sectionsCtx.selectedVersionId}
              currentUserId={user?.id}
              recipientFocused={true}
              onLifecycleChanged={() => {
                void refreshHandovers()
                sectionsCtx.retryLoadReadiness()
              }}
              onNavigateTab={navigateTab}
            />

            <Card className="p-5">
              <div className="mb-4 flex flex-wrap items-center justify-between gap-2 border-b border-line pb-3">
                <div>
                  <h2 className="text-[15px] font-semibold text-navy">
                    {effectiveMode === 'mandatory'
                      ? 'Role-Prioritized 10-Section Handover Package Reader'
                      : 'Canonical 8-Domain Handover Package Reader'}
                  </h2>
                  <p className="mt-0.5 text-xs text-muted">
                    Review verified knowledge, provenance evidence, missing-information notices, and responsibility records.
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {mandatoryList.length > 0 && (
                    <div className="inline-flex rounded-lg border border-line bg-slate-50 p-0.5 text-xs">
                      <button
                        type="button"
                        onClick={() => setReaderMode('mandatory')}
                        className={cn(
                          'rounded-md px-2.5 py-1 font-medium transition',
                          effectiveMode === 'mandatory' ? 'bg-white text-navy shadow-xs' : 'text-muted'
                        )}
                      >
                        10 Role Sections
                      </button>
                      <button
                        type="button"
                        onClick={() => setReaderMode('canonical')}
                        className={cn(
                          'rounded-md px-2.5 py-1 font-medium transition',
                          effectiveMode === 'canonical' ? 'bg-white text-navy shadow-xs' : 'text-muted'
                        )}
                      >
                        8 Domains
                      </button>
                    </div>
                  )}
                  <Button
                    size="sm"
                    variant="secondary"
                    icon={ArrowLeft}
                    onClick={() => router.push(`/handovers/${h.id}/review`)}
                  >
                    Open Sign-Off &amp; Approval
                  </Button>
                </div>
              </div>
              {effectiveMode === 'mandatory' && activeMandatory ? (
                <div className="grid gap-5 lg:grid-cols-[260px_1fr]">
                  <nav className="space-y-1">
                    {mandatoryList.map((ms) => {
                      const isActive = activeMandatory.section_key === ms.section_key
                      return (
                        <button
                          key={ms.section_key}
                          type="button"
                          onClick={() => setSelectedMandatoryKey(ms.section_key)}
                          className={cn(
                            'flex w-full items-center justify-between gap-2 rounded-xl border px-3 py-2 text-left text-xs font-medium transition',
                            isActive
                              ? 'border-brand/40 bg-tint text-brand'
                              : 'border-transparent bg-white text-slate-700 hover:border-line hover:bg-slate-50'
                          )}
                        >
                          <span className="truncate">
                            {ms.section_number}. {ms.section_title}
                          </span>
                          <span className="flex shrink-0 items-center gap-1">
                            {ms.is_role_priority && (
                              <span className="size-1.5 rounded-full bg-brand" title="Role priority" />
                            )}
                            <span className="rounded-full bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-600">
                              {ms.knowledge_items.length + ms.relationships.length + ms.recommended_steps.length}
                            </span>
                          </span>
                        </button>
                      )
                    })}
                  </nav>
                  <div className="min-w-0 space-y-4">
                    <div className="flex flex-wrap items-start justify-between gap-2 rounded-xl border border-line bg-slate-50/50 p-4">
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-mono text-xs font-semibold text-brand">
                            {String(activeMandatory.section_number).padStart(2, '0')}
                          </span>
                          <h3 className="text-[15px] font-semibold text-navy">{activeMandatory.section_title}</h3>
                          {activeMandatory.is_role_priority && (
                            <Badge tone="blue" icon={Sparkles}>Priority</Badge>
                          )}
                        </div>
                        {activeMandatory.role_emphasis_note && (
                          <p className="mt-1 text-xs text-muted">{activeMandatory.role_emphasis_note}</p>
                        )}
                      </div>
                      <Badge
                        tone={
                          activeMandatory.readiness_status === 'ready'
                            ? 'green'
                            : activeMandatory.readiness_status === 'has_conflicts'
                            ? 'red'
                            : 'amber'
                        }
                      >
                        {activeMandatory.readiness_status.replace(/_/g, ' ')}
                      </Badge>
                    </div>

                    {activeMandatory.insufficient_info_message && (
                      <Callout tone="amber" icon={AlertTriangle} title="Insufficient Verified Information">
                        {activeMandatory.insufficient_info_message}
                      </Callout>
                    )}

                    {activeMandatory.knowledge_items.map((ki) => (
                      <div key={ki.id} className="rounded-xl border border-line bg-white p-4">
                        <div className="flex items-center justify-between gap-2">
                          <p className="text-[13.5px] font-semibold text-navy">{ki.title}</p>
                          <Badge tone="green" icon={ShieldCheck}>Human Verified</Badge>
                        </div>
                        <p className="mt-1.5 whitespace-pre-wrap text-[13px] text-slate-700">{ki.content}</p>
                        {ki.provenance.length > 0 && (
                          <div className="mt-2.5 flex flex-wrap gap-1.5">
                            {ki.provenance.map((ev, eIdx) =>
                              ev.acl_restricted ? (
                                <Badge key={eIdx} tone="gray" icon={Lock}>
                                  Restricted Source
                                </Badge>
                              ) : (
                                <button
                                  key={ev.evidence_id + eIdx}
                                  type="button"
                                  onClick={() => router.push(`/projects/${resolvedPid}/evidence/${ev.evidence_id}`)}
                                  className="inline-flex items-center gap-1 rounded-full border border-line bg-slate-50 px-2.5 py-0.5 text-[11px] font-medium text-brand hover:border-brand/40"
                                >
                                  <Link2 className="size-3" />
                                  {ev.source_name || ev.source_provider || 'Evidence'}
                                </button>
                              )
                            )}
                          </div>
                        )}
                      </div>
                    ))}

                    {activeMandatory.recommended_steps.length > 0 && (
                      <div className="rounded-xl border border-line bg-slate-50/40 p-4">
                        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                          Recommended Next Actions
                        </p>
                        <ul className="mt-2 space-y-1.5 text-[13px]">
                          {activeMandatory.recommended_steps.map((st, sIdx) => (
                            <li key={sIdx} className="flex items-center gap-2 text-navy">
                              <CheckCircle2 className="size-3.5 text-brand" />
                              <span>{String(st.title || '')}</span>
                              <Badge tone="gray">{String(st.status || 'pending')}</Badge>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {activeMandatory.responsibilities_summary.length > 0 && (
                      <div className="rounded-xl border border-line bg-slate-50/40 p-4">
                        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                          Ownership &amp; Accountability
                        </p>
                        <ul className="mt-2 space-y-1.5 text-[13px]">
                          {activeMandatory.responsibilities_summary.map((r, rIdx) => (
                            <li key={rIdx} className="flex items-center justify-between gap-2">
                              <span className="font-medium text-navy">
                                {String(r.responsibility_title || r.title || 'Responsibility')}
                              </span>
                              <Badge tone={r.successor_acknowledged ? 'green' : 'amber'}>
                                {String(r.transfer_status || 'pending')}
                              </Badge>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <div className="grid gap-5 lg:grid-cols-[240px_1fr]">
                  <nav className="space-y-1">
                    {CANONICAL_DOMAINS.map((dom) => {
                      const Icon = dom.icon
                      const isActive = selectedDomain === dom.sectionType
                      const count = sectionCounts.get(dom.sectionType) ?? 0
                      return (
                        <button
                          key={dom.sectionType}
                          type="button"
                          onClick={() => setSelectedDomain(dom.sectionType)}
                          className={cn(
                            'flex w-full items-center justify-between gap-2 rounded-xl border px-3 py-2 text-left text-xs font-medium transition',
                            isActive
                              ? 'border-brand/40 bg-tint text-brand'
                              : 'border-transparent bg-white text-slate-700 hover:border-line hover:bg-slate-50'
                          )}
                        >
                          <span className="flex items-center gap-2 truncate">
                            <Icon className="size-3.5 shrink-0" />
                            <span className="truncate">{dom.shortLabel}</span>
                          </span>
                          <span className="rounded-full bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-600">
                            {count}
                          </span>
                        </button>
                      )
                    })}
                  </nav>
                  <div className="min-w-0">
                    <CanonicalSectionPanel
                      sectionType={selectedDomain}
                      data={sectionsCtx.sectionsData}
                      isLoading={sectionsCtx.isLoadingVersions || sectionsCtx.isLoadingSections}
                      error={sectionsCtx.sectionsError}
                      projectId={resolvedPid}
                      handoverId={h.id}
                      caseStatus={h.rawStatus || h.status}
                      onRetry={sectionsCtx.retryLoadSections}
                      onNavigateTab={navigateTab}
                    />
                  </div>
                </div>
              )}
            </Card>
          </div>
        )
      }}
    </HandoverLayout>
  )
}

/* ---------- 30. AI assistant (Real Handover-Scoped Grounded RAG) ---------- */
interface LiveAssistantTurn {
  id: string
  role: 'user' | 'assistant'
  text: string
  answerStatus?: AssistantAnswerStatus | null
  citations?: AssistantCitation[]
  claims?: AssistantClaim[]
  uncertainty?: string | null
  conflicts?: string[]
  missingInformation?: string[]
  suggestedFollowups?: string[]
  feedbackSent?: 'helpful' | 'unhelpful' | null
}

const SUGGESTED = [
  'Why was this architecture selected?',
  'Which tasks remain incomplete?',
  'What risks or blockers remain unresolved?',
  'Who owns critical operational responsibilities?',
  'What should I work on first as successor?'
]

function RichText({ text }: { text: string }) {
  return (
    <>
      {text.split('\n').map((line, i) => (
        <p key={i} className={line.startsWith('•') || line.startsWith('-') ? 'pl-1' : i ? 'mt-2' : ''}>
          {line.split(/(\*\*[^*]+\*\*)/).map((part, j) =>
            part.startsWith('**') ? (
              <strong key={j} className="font-semibold text-navy">
                {part.slice(2, -2)}
              </strong>
            ) : (
              part
            )
          )}
        </p>
      ))}
    </>
  )
}

export function Assistant({ id }: { id: string }) {
  const s = useStore()
  const router = useRouter()
  const { activeProject, members, user } = useLiveApp()
  const { h, project } = useHandover(id)
  const resolvedPid = h
    ? isUUID(h.projectId)
      ? h.projectId
      : activeProject?.id || h.projectId
    : ''

  const [conversations, setConversations] = useState<AssistantConversation[]>([])
  const [activeConvId, setActiveConvId] = useState<string | null>(null)
  const [turns, setTurns] = useState<LiveAssistantTurn[]>([])
  const [currentVersionId, setCurrentVersionId] = useState<string | null>(null)
  const [responseMode, setResponseMode] = useState<AssistantResponseMode>('standard')
  const [input, setInput] = useState('')
  const [loadingConv, setLoadingConv] = useState(false)
  const [sending, setSending] = useState(false)
  const [assistantError, setAssistantError] = useState<string | null>(null)
  const end = useRef<HTMLDivElement>(null)

  useEffect(() => {
    end.current?.scrollIntoView({ behavior: 'smooth' })
  }, [turns, sending])

  useEffect(() => {
    let active = true
    if (!h || !resolvedPid || !isUUID(resolvedPid)) return

    setLoadingConv(true)
    setAssistantError(null)
    Promise.all([
      api.assistant.listConversations(resolvedPid).catch(() => []),
      api.handover.getVersions(resolvedPid, h.id).catch(() => []),
    ])
      .then(async ([convs, vers]) => {
        if (!active) return
        const list = Array.isArray(vers) ? vers : []
        const curVer = list.find((v) => v.is_current) || list[0]
        setCurrentVersionId(curVer ? curVer.id : null)

        const allConvs = Array.isArray(convs) ? convs : []
        const handoverConvs = allConvs.filter(
          (c) =>
            c.metadata_json &&
            String((c.metadata_json as Record<string, unknown>).handover_case_id || '') === h.id
        )
        const displayConvs = handoverConvs.length > 0 ? handoverConvs : allConvs
        setConversations(displayConvs)

        if (handoverConvs.length > 0) {
          const latest = handoverConvs[0]!
          setActiveConvId(latest.id)
          try {
            const detail = await api.assistant.getConversation(resolvedPid, latest.id)
            if (!active) return
            setTurns(
              (detail.messages || []).map((m) => ({
                id: m.id,
                role: m.sender_type === 'user' ? 'user' : 'assistant',
                text: m.content,
                answerStatus: m.answer_status,
                citations: m.citations || [],
                claims: m.structured_payload_json?.claims || [],
                uncertainty: m.structured_payload_json?.uncertainty || null,
                conflicts: m.structured_payload_json?.conflicts || [],
                missingInformation: m.structured_payload_json?.missing_information || [],
                suggestedFollowups: m.structured_payload_json?.suggested_followup_questions || [],
              }))
            )
          } catch {
            setTurns([])
          }
        } else {
          setActiveConvId(null)
          setTurns([])
        }
      })
      .finally(() => {
        if (active) setLoadingConv(false)
      })

    return () => {
      active = false
    }
  }, [h?.id, resolvedPid])

  if (!h || !project) return <HandoverNotFound />

  const selectConversation = async (convId: string) => {
    setActiveConvId(convId)
    setAssistantError(null)
    if (!resolvedPid || !isUUID(resolvedPid)) return
    setLoadingConv(true)
    try {
      const detail = await api.assistant.getConversation(resolvedPid, convId)
      setTurns(
        (detail.messages || []).map((m) => ({
          id: m.id,
          role: m.sender_type === 'user' ? 'user' : 'assistant',
          text: m.content,
          answerStatus: m.answer_status,
          citations: m.citations || [],
          claims: m.structured_payload_json?.claims || [],
          uncertainty: m.structured_payload_json?.uncertainty || null,
          conflicts: m.structured_payload_json?.conflicts || [],
          missingInformation: m.structured_payload_json?.missing_information || [],
          suggestedFollowups: m.structured_payload_json?.suggested_followup_questions || [],
        }))
      )
    } catch (err: unknown) {
      setAssistantError(err instanceof Error ? err.message : 'Unable to load conversation.')
    } finally {
      setLoadingConv(false)
    }
  }

  const startNewConversation = () => {
    setActiveConvId(null)
    setTurns([])
    setAssistantError(null)
  }

  const ask = async (q: string) => {
    const cleanQ = q.trim()
    if (!cleanQ || sending) return
    if (!resolvedPid || !isUUID(resolvedPid)) {
      setAssistantError('Select a valid project before asking the assistant.')
      return
    }

    const tempUserId = `user-${Date.now()}`
    setTurns((prev) => [...prev, { id: tempUserId, role: 'user', text: cleanQ }])
    setInput('')
    setSending(true)
    setAssistantError(null)

    try {
      let targetConvId = activeConvId
      if (!targetConvId) {
        const created = await api.assistant.createConversation(
          resolvedPid,
          `${h.code}: ${cleanQ.slice(0, 48)}`,
          { handover_case_id: h.id }
        )
        targetConvId = created.id
        setActiveConvId(created.id)
        setConversations((prev) => [created, ...prev])
      }

      const resp = await api.assistant.askQuestion(resolvedPid, targetConvId, {
        question: cleanQ,
        mode: 'hybrid',
        response_mode: responseMode,
        handover_case_id: h.id,
        package_version_id: currentVersionId || undefined,
      })

      setTurns((prev) => [
        ...prev,
        {
          id: resp.message_id,
          role: 'assistant',
          text: resp.answer,
          answerStatus: resp.answer_status,
          citations: resp.citations || [],
          claims: resp.claims || [],
          uncertainty: resp.uncertainty,
          conflicts: resp.conflicts || [],
          missingInformation: resp.missing_information || [],
          suggestedFollowups: resp.suggested_followup_questions || [],
        },
      ])
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Assistant request failed.'
      setAssistantError(msg)
      setTurns((prev) => prev.filter((t) => t.id !== tempUserId))
    } finally {
      setSending(false)
    }
  }

  const handleFeedback = async (turnId: string, feedbackType: 'helpful' | 'unhelpful') => {
    if (!resolvedPid || !isUUID(resolvedPid) || !isUUID(turnId)) return
    try {
      await api.assistant.submitFeedback(resolvedPid, turnId, { feedback_type: feedbackType })
      setTurns((prev) =>
        prev.map((t) => (t.id === turnId ? { ...t, feedbackSent: feedbackType } : t))
      )
      s.toast(
        feedbackType === 'helpful' ? 'Feedback recorded' : 'Issue flagged',
        feedbackType === 'helpful'
          ? 'Marked answer helpful.'
          : 'A reviewer can inspect this response.',
        feedbackType === 'helpful' ? 'success' : 'info'
      )
    } catch (err: unknown) {
      s.toast('Feedback failed', err instanceof Error ? err.message : 'Unable to save feedback.', 'error')
    }
  }

  const lastAssistant = [...turns].reverse().find((m) => m.role === 'assistant')

  return (
    <>
      <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <Link
            to={
              h.status === 'published' || h.status === 'completed'
                ? `/handovers/${h.id}/recipient`
                : `/handovers/${h.id}`
            }
            className="mb-2 inline-flex items-center gap-1.5 text-[13px] font-medium text-muted hover:text-navy"
          >
            <ArrowLeft className="size-4" />{h.code} · {project.name}
          </Link>
          <h1 className="flex flex-wrap items-center gap-2.5 text-[22px] font-semibold tracking-tight text-navy">
            Handover Assistant
            <Badge tone="indigo" icon={ShieldCheck}>Evidence-grounded</Badge>
            <Badge tone="blue">{HANDOVER_TYPE_LABELS[h.handoverType || 'developer'] || 'Handover Scope'}</Badge>
          </h1>
          <p className="mt-1 text-sm text-muted">
            Answers come only from ACL-permitted evidence linked to this project and handover package. Uncertainty and conflicts are disclosed explicitly.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted">Mode:</span>
          <Select
            aria-label="Assistant reasoning mode"
            className="h-9 w-44 text-xs"
            value={responseMode}
            onChange={(e) => setResponseMode(e.target.value as AssistantResponseMode)}
          >
            <option value="standard">Standard Grounded Q&amp;A</option>
            <option value="deep_research">Deep Research</option>
            <option value="deep_think">Deep Think (Causal)</option>
            <option value="deep_extract">Deep Extract</option>
          </Select>
        </div>
      </div>

      {assistantError && (
        <div className="mb-4">
          <Callout tone="red" icon={Lock} title="Assistant notice">
            {assistantError}
          </Callout>
        </div>
      )}

      <div className="grid h-[calc(100dvh-260px)] min-h-[520px] gap-5 lg:grid-cols-[240px_1fr] xl:grid-cols-[240px_1fr_340px]">
        <Card className="hidden flex-col overflow-hidden lg:flex">
          <div className="border-b border-line p-3">
            <Button
              variant="secondary"
              className="w-full"
              icon={Plus}
              onClick={startNewConversation}
            >
              New conversation
            </Button>
          </div>
          <p className="px-4 pb-1 pt-3 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
            Handover Conversations
          </p>
          <ul className="flex-1 space-y-0.5 overflow-y-auto px-2 pb-3">
            {conversations.length === 0 ? (
              <li className="px-2.5 py-2 text-xs text-muted">No saved threads yet.</li>
            ) : (
              conversations.map((c) => (
                <li key={c.id}>
                  <button
                    type="button"
                    onClick={() => void selectConversation(c.id)}
                    className={cn(
                      'w-full rounded-lg px-2.5 py-2 text-left',
                      activeConvId === c.id ? 'bg-tint' : 'hover:bg-slate-50'
                    )}
                  >
                    <span className="line-clamp-1 text-[13px] font-medium text-navy">{c.title}</span>
                    <span className="text-[11px] text-muted">
                      {new Date(c.last_message_at || c.created_at).toLocaleDateString('en-GB', {
                        day: 'numeric',
                        month: 'short',
                      })}
                    </span>
                  </button>
                </li>
              ))
            )}
          </ul>
        </Card>

        <Card className="flex min-h-0 flex-col overflow-hidden">
          <div className="scrollbar-thin flex-1 space-y-5 overflow-y-auto p-4 sm:p-6">
            {loadingConv ? (
              <div className="flex h-full items-center justify-center text-sm text-muted">
                <Loader2 className="mr-2 size-4 animate-spin text-brand" />
                Loading grounded conversation…
              </div>
            ) : !turns.length ? (
              <div className="flex h-full flex-col items-center justify-center text-center">
                <span className="flex size-12 items-center justify-center rounded-2xl bg-tint text-brand">
                  <Sparkles className="size-5" />
                </span>
                <p className="mt-4 text-base font-semibold text-navy">Ask about {project.name}</p>
                <p className="mt-1 max-w-sm text-[13px] text-muted">
                  Every answer uses live backend hybrid retrieval and your handover package evidence, citing sources [S1], [S2].
                </p>
                <div className="mt-6 flex max-w-lg flex-wrap justify-center gap-2">
                  {SUGGESTED.map((q) => (
                    <button
                      key={q}
                      type="button"
                      onClick={() => void ask(q)}
                      className="rounded-full border border-line bg-white px-3 py-1.5 text-[13px] text-navy hover:border-brand/40 hover:bg-tint/40"
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              turns.map((m) =>
                m.role === 'user' ? (
                  <div key={m.id} className="flex justify-end">
                    <div className="max-w-[80%] rounded-2xl rounded-br-md bg-brand px-4 py-2.5 text-[13.5px] text-white">
                      {m.text}
                    </div>
                  </div>
                ) : (
                  <div key={m.id} className="flex gap-3">
                    <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-tint text-brand">
                      <Bot className="size-4" />
                    </span>
                    <div className="min-w-0 max-w-[88%] flex-1">
                      <div className="rounded-2xl rounded-tl-md border border-line bg-white px-4 py-3 text-[13.5px] leading-relaxed text-slate-700">
                        <RichText text={m.text} />

                        {m.uncertainty && (
                          <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50/70 px-3 py-2 text-xs text-amber-900">
                            <strong>Uncertainty:</strong> {m.uncertainty}
                          </div>
                        )}

                        {m.conflicts && m.conflicts.length > 0 && (
                          <div className="mt-2 rounded-lg border border-red-200 bg-red-50/50 px-3 py-2 text-xs text-red-900">
                            <strong>Conflicting evidence:</strong> {m.conflicts.join(' · ')}
                          </div>
                        )}

                        {m.citations && m.citations.length > 0 && (
                          <div className="mt-3 flex flex-wrap gap-1.5 border-t border-line pt-3">
                            {m.citations.map((c) => (
                              <button
                                key={`${c.citation_label}-${c.evidence_id}`}
                                type="button"
                                onClick={() =>
                                  router.push(`/projects/${resolvedPid}/evidence/${c.evidence_id}`)
                                }
                                className="inline-flex items-center gap-1 rounded-full border border-line bg-slate-50 px-2.5 py-0.5 text-[11px] font-medium text-navy hover:border-brand/40 hover:text-brand"
                              >
                                <span className="font-semibold text-brand">[{c.citation_label}]</span>
                                <span className="max-w-[180px] truncate">{c.source_title}</span>
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                      <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[11px]">
                        {m.answerStatus === 'answered' && (
                          <Badge tone="green" icon={ShieldCheck}>Evidence grounded</Badge>
                        )}
                        {m.answerStatus === 'partially_answered' && (
                          <Badge tone="amber" icon={CircleAlert}>Partially answered · uncertainty noted</Badge>
                        )}
                        {m.answerStatus === 'conflicted_evidence' && (
                          <Badge tone="red" icon={AlertTriangle}>Conflicting evidence</Badge>
                        )}
                        {m.answerStatus === 'insufficient_evidence' && (
                          <Badge tone="gray" icon={FileQuestion}>Insufficient evidence</Badge>
                        )}
                        {m.answerStatus === 'access_restricted' && (
                          <Badge tone="red" icon={Lock}>Source ACL restricted</Badge>
                        )}
                        {m.answerStatus === 'insufficient_evidence' && h.outgoingId && (
                          <button
                            type="button"
                            className="font-medium text-brand"
                            onClick={() =>
                              s.toast(
                                `Follow-up noted for ${getMemberDisplayName(h.outgoingId, members, user)}`,
                                'Ask them to contribute missing context directly in the Handover Workspace.',
                                'info'
                              )
                            }
                          >
                            Request context from {getMemberDisplayName(h.outgoingId, members, user).split(' ')[0]} →
                          </button>
                        )}
                        <span className="ml-auto flex gap-1">
                          <button
                            type="button"
                            className={cn(
                              'rounded p-1 hover:text-navy',
                              m.feedbackSent === 'helpful' ? 'text-ok' : 'text-slate-400'
                            )}
                            aria-label="Helpful"
                            onClick={() => void handleFeedback(m.id, 'helpful')}
                          >
                            <ThumbsUp className="size-3.5" />
                          </button>
                          <button
                            type="button"
                            className={cn(
                              'rounded p-1 hover:text-navy',
                              m.feedbackSent === 'unhelpful' ? 'text-bad' : 'text-slate-400'
                            )}
                            aria-label="Not helpful"
                            onClick={() => void handleFeedback(m.id, 'unhelpful')}
                          >
                            <ThumbsDown className="size-3.5" />
                          </button>
                        </span>
                      </div>
                    </div>
                  </div>
                )
              )
            )}
            {sending && (
              <div className="flex gap-3">
                <span className="flex size-8 items-center justify-center rounded-full bg-tint text-brand">
                  <Bot className="size-4" />
                </span>
                <div className="flex items-center gap-1 rounded-2xl border border-line bg-white px-4 py-3">
                  {[0, 1, 2].map((d) => (
                    <span
                      key={d}
                      className="size-1.5 animate-bounce rounded-full bg-slate-400"
                      style={{ animationDelay: `${d * 0.15}s` }}
                    />
                  ))}
                  <span className="ml-2 text-xs text-muted">Retrieving ACL-filtered project &amp; handover evidence…</span>
                </div>
              </div>
            )}
            <div ref={end} />
          </div>
          <div className="border-t border-line p-3">
            {!!turns.length && (
              <div className="scrollbar-thin mb-2 flex gap-1.5 overflow-x-auto">
                {(lastAssistant?.suggestedFollowups?.length
                  ? lastAssistant.suggestedFollowups
                  : SUGGESTED.filter((q) => !turns.some((m) => m.text === q))
                )
                  .slice(0, 4)
                  .map((q) => (
                    <button
                      key={q}
                      type="button"
                      onClick={() => void ask(q)}
                      className="shrink-0 rounded-full border border-line px-2.5 py-1 text-xs text-muted hover:text-navy"
                    >
                      {q}
                    </button>
                  ))}
              </div>
            )}
            <form
              onSubmit={(e) => {
                e.preventDefault()
                void ask(input)
              }}
              className="flex items-end gap-2"
            >
              <Textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    void ask(input)
                  }
                }}
                rows={1}
                placeholder="Ask a question about this handover…"
                className="min-h-[42px] resize-none"
              />
              <Button
                type="submit"
                icon={Send}
                disabled={!input.trim() || sending}
                className="h-[42px]"
                aria-label="Send"
              />
            </form>
            <p className="mt-1.5 text-[11px] text-slate-400">
              Answers strictly cite ACL-permitted evidence; unverified items or missing knowledge are flagged openly.
            </p>
          </div>
        </Card>

        <Card className="hidden overflow-y-auto xl:block">
          <CardHeader title="Citations in Latest Answer" icon={Link2} />
          <div className="space-y-2.5 px-5 pb-4">
            {lastAssistant?.citations?.length ? (
              lastAssistant.citations.map((c) => (
                <div key={`${c.citation_label}-${c.evidence_id}`} className="rounded-xl border border-line p-3 text-xs">
                  <div className="flex items-center justify-between gap-2">
                    <Badge tone="indigo">[{c.citation_label}]</Badge>
                    <Badge tone={c.is_verified ? 'green' : 'amber'}>
                      {c.is_verified ? 'Verified' : 'Source record'}
                    </Badge>
                  </div>
                  <p className="mt-1.5 font-semibold text-navy">{c.source_title}</p>
                  <p className="mt-0.5 text-[11px] text-muted">
                    {c.source_provider}{c.author ? ` · ${c.author}` : ''}
                  </p>
                  {c.excerpt && (
                    <p className="mt-1.5 line-clamp-3 text-[11.5px] leading-relaxed text-slate-600">{c.excerpt}</p>
                  )}
                  <button
                    type="button"
                    onClick={() => router.push(`/projects/${resolvedPid}/evidence/${c.evidence_id}`)}
                    className="mt-2 inline-flex items-center gap-1 text-[11px] font-medium text-brand hover:underline"
                  >
                    Open evidence <ExternalLink className="size-3" />
                  </button>
                </div>
              ))
            ) : (
              <p className="text-[13px] text-muted">Evidence citations for the latest answer appear here.</p>
            )}
          </div>
          {lastAssistant?.missingInformation && lastAssistant.missingInformation.length > 0 && (
            <>
              <CardHeader title="Missing Information" icon={FileQuestion} className="border-t border-line" />
              <ul className="list-disc space-y-1 px-8 pb-5 text-xs text-amber-800">
                {lastAssistant.missingInformation.map((mi, idx) => (
                  <li key={idx}>{mi}</li>
                ))}
              </ul>
            </>
          )}
        </Card>
      </div>
    </>
  )
}

/* ---------- Top-level HandoverDetailPage component ---------- */
export interface HandoverDetailPageProps {
  id?: string
  tab?: 'overview' | 'review' | 'report' | 'recipient' | 'assistant'
}

function HandoverDetailPageInner({ id, tab = 'overview' }: HandoverDetailPageProps) {
  const params = useParams()
  const handoverId = id || (params?.id as string) || ''

  switch (tab) {
    case 'review':
      return <Review id={handoverId} />
    case 'report':
      return <Report id={handoverId} />
    case 'recipient':
      return <RecipientWorkspace id={handoverId} />
    case 'assistant':
      return <Assistant id={handoverId} />
    case 'overview':
    default:
      return <HandoverWorkspace id={handoverId} initialTab="overview" />
  }
}

export function HandoverDetailPage(props: HandoverDetailPageProps) {
  return (
    <Suspense fallback={<div className="p-8 text-center text-sm text-muted">Loading handover details…</div>}>
      <HandoverDetailPageInner {...props} />
    </Suspense>
  )
}

export default HandoverDetailPage
