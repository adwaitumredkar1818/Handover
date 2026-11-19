'use client'

import React, { Suspense, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useRouter, useParams, useSearchParams } from 'next/navigation'
import {
  AlertTriangle, ArrowLeft, ArrowRight, BookOpen, Bot, Check, CheckCircle2, ChevronRight,
  CircleAlert, Copy, Download, ExternalLink, FileDown, FileQuestion, FileText, History,
  Layers, Lightbulb, Link2, ListTodo, Lock, MessageSquare, MessageSquareText, Network,
  Pencil, Plus, Printer, Rocket, Send, Share2, ShieldCheck, ShieldX, Sparkles,
  ThumbsDown, ThumbsUp, UserRound, Users, X, Compass, Cpu
} from 'lucide-react'

import { useStore, architecture, evidence, gaps, ME, personById, type Verification } from '../../lib/figmaStore'
import {
  Avatar, Badge, Button, Callout, Card, CardHeader, Checkbox, Confidence, EmptyState,
  Field, Input, Modal, Progress, Textarea, VerificationBadge, cn, VERIF, Tooltip
} from '../figma-ui/index'
import { Logo, EvidenceTypeIcon } from '../figma-ui/brand'
import { StackedBar, Ring } from '../figma-ui/charts'
import {
  EvidenceCard, EvidenceChip, SeverityBadge, TaskStatus, allFindings, projectFindings,
  type AnyFinding
} from '../figma-ui/domain'
import {
  HandoverLayout, HandoverNotFound, handoverStats, useHandover, HandoverWorkspace, Link,
  getMemberDisplayName, getMemberDisplayRole, isUUID
} from './HandoversPage'
import { useLiveApp } from '../../context/LiveAppContext'
import { api } from '../../lib/api'
import { SignoffApprovalPanel } from '../handover/SignoffApprovalPanel'
import { CANONICAL_DOMAINS, CanonicalSectionPanel } from '../handover/CanonicalSectionView'
import type { CanonicalHandoverSectionType } from '../../lib/types'

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

  return (
    <HandoverLayout id={id} tab="report">
      {(h, _role, sectionsCtx) => {
        const p = projects.find((x) => x.id === h.projectId) || (activeProject?.id === h.projectId ? activeProject : null) || s.allProjects.find((x) => x.id === h.projectId)
        const pId = p?.id || h.projectId
        const pName = p?.name || activeProject?.name || 'Project'
        const outName = getMemberDisplayName(h.outgoingId, members, user)
        const incName = getMemberDisplayName(h.incomingId, members, user)
        const sectionsData = sectionsCtx.sectionsData
        const canonicalSections = sectionsData?.sections || []
        const verifiedTotal = sectionsData?.epistemic_summary.human_verified_included ?? 0
        const pendingTotal = sectionsData?.epistemic_summary.pending_verification ?? 0
        const pubStatus =
          h.status === 'published'
            ? 'Published'
            : h.status === 'completed'
            ? 'Published · acknowledged'
            : h.status === 'approved'
            ? 'Approved · not yet published'
            : 'Draft · not published'

        const downloadMarkdown = async () => {
          try {
            s.toast('Exporting Markdown', 'Generating markdown handover package...', 'info')
            const md = await api.handover.exportMarkdown(pId, h.id)
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
            const jsonData = await api.handover.exportJson(pId, h.id)
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

        return (
          <div className="grid gap-6 xl:grid-cols-[220px_1fr]">
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
                        : 'gray'
                    }
                    dot
                    className="mt-2"
                  >
                    {pubStatus}
                  </Badge>
                  {sectionsData?.version.content_hash && (
                    <p className="mt-3 break-all font-mono text-[10px] text-slate-400">
                      v{sectionsData.version.version_number} · SHA-256: {sectionsData.version.content_hash.slice(0, 16)}…
                    </p>
                  )}
                </Card>
                <nav className="space-y-0.5">
                  {canonicalSections.map((sec) => (
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
                <Button
                  icon={FileDown}
                  onClick={() => {
                    s.toast('Preparing PDF', 'Use “Save as PDF” in the print dialog.', 'info')
                    setTimeout(() => window.print(), 300)
                  }}
                >
                  Export PDF
                </Button>
                <Button variant="secondary" icon={FileText} onClick={downloadMarkdown}>
                  Export Markdown
                </Button>
                <Button variant="secondary" icon={Download} onClick={downloadJson}>
                  Export JSON
                </Button>
                <Button variant="secondary" icon={Share2} onClick={() => setShare(true)}>
                  Share
                </Button>
                <Button variant="secondary" icon={Printer} onClick={() => window.print()}>
                  Print
                </Button>
                <span className="ml-auto xl:hidden">
                  <Badge tone="gray" dot>{pubStatus}</Badge>
                </span>
              </div>
              <article className="mx-auto max-w-[860px] rounded-2xl border border-line bg-white px-6 py-8 shadow-card sm:px-12 sm:py-12">
                <header className="mb-8 border-b-2 border-navy pb-6">
                  <div className="flex items-center justify-between">
                    <Logo size={24} />
                    <span className="text-xs font-medium text-muted">
                      {h.code} · {sectionsData ? `Version v${sectionsData.version.version_number}` : 'Draft'}
                    </span>
                  </div>
                  <p className="mt-8 text-xs font-semibold uppercase tracking-[0.2em] text-brand">Handover Report</p>
                  <h1 className="mt-2 text-3xl font-semibold tracking-tight text-navy">{pName}</h1>
                  <dl className="mt-6 grid grid-cols-2 gap-4 text-[13px] sm:grid-cols-4">
                    {[
                      ['Outgoing', outName],
                      ['Incoming', incName],
                      ['Prepared', h.created],
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
                    Only human-verified knowledge compiled into this immutable package version appears as confirmed handover content. Unresolved conflicts are explicitly separated.
                  </p>
                </header>
                {sectionsCtx.isLoadingSections || sectionsCtx.isLoadingVersions ? (
                  <div className="py-10 text-center text-sm text-muted">Loading canonical report sections…</div>
                ) : sectionsCtx.sectionsError ? (
                  <Callout tone="red" icon={AlertTriangle} title="Unable to load report sections">
                    {sectionsCtx.sectionsError}
                  </Callout>
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
                              No human-verified items included in this domain for Version v{sectionsData?.version.version_number}.
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
                          {sec.relationships.length > 0 && (
                            <ul className="list-disc space-y-1 pl-5 text-[13px]">
                              {sec.relationships.map((rel) => (
                                <li key={rel.id}>
                                  <span className="font-medium text-navy">{rel.source_entity_name}</span>{' '}
                                  <span className="text-brand">[{rel.relationship_type}]</span>{' '}
                                  <span className="font-medium text-navy">{rel.target_entity_name}</span>
                                </li>
                              ))}
                            </ul>
                          )}
                          {sec.unresolved_conflicts.length > 0 && (
                            <div className="rounded-lg border border-red-200 bg-red-50/40 p-3">
                              <p className="text-xs font-semibold text-bad">
                                Unresolved Verification Conflicts ({sec.unresolved_conflicts.length} — Not Verified Facts)
                              </p>
                              <ul className="mt-1.5 list-disc space-y-1 pl-4 text-xs text-slate-700">
                                {sec.unresolved_conflicts.map((cf) => (
                                  <li key={cf.id}>{cf.explanation}</li>
                                ))}
                              </ul>
                            </div>
                          )}
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

        return (
          <div className="space-y-6" data-testid="recipient-workspace">
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
                    Canonical 8-Domain Handover Package Reader
                  </h2>
                  <p className="mt-0.5 text-xs text-muted">
                    Review all eight persisted knowledge domains, provenance links, and responsibility records for this handover package version.
                  </p>
                </div>
                <Button
                  size="sm"
                  variant="secondary"
                  icon={ArrowLeft}
                  onClick={() => router.push(`/handovers/${h.id}/review`)}
                >
                  Open Sign-Off &amp; Approval
                </Button>
              </div>
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
                    onRetry={sectionsCtx.retryLoadSections}
                    onNavigateTab={navigateTab}
                  />
                </div>
              </div>
            </Card>
          </div>
        )
      }}
    </HandoverLayout>
  )
}

/* ---------- 30. AI assistant ---------- */
interface Msg {
  role: 'user' | 'ai'
  text: string
  cites?: string[]
  findings?: AnyFinding[]
  grounded?: 'verified' | 'partial' | 'none'
}
const SUGGESTED = [
  'Why was this architecture selected?',
  'Which tasks remain incomplete?',
  'What issues were left unresolved?',
  'Who is responsible for deployment?',
  'What should I work on first?'
]

function answer(q: string, pid: string, verif: Record<string, Verification>): Msg {
  const f = projectFindings(pid)
  const all = allFindings(pid)
  const ql = q.toLowerCase()
  const isV = (x: AnyFinding) => (verif[x.id] ?? x.verification) === 'verified'

  if (ql.includes('architecture') || ql.includes('why')) {
    const d = f.decisions[0]
    if (d) {
      return {
        role: 'ai',
        text: `The current architecture is shaped mainly by the decision to **${d.title.toLowerCase()}**. ${d.reasoning}${
          f.decisions[1] ? ` A related decision, “${f.decisions[1].title}”, followed: ${f.decisions[1].reasoning}` : ''
        }`,
        cites: [...d.evidenceIds, ...(f.decisions[1]?.evidenceIds ?? [])].slice(0, 4),
        findings: [{ ...d, kind: 'Decision' }, ...(f.decisions[1] ? [{ ...f.decisions[1], kind: 'Decision' as const }] : [])],
        grounded: isV({ ...d, kind: 'Decision' }) ? 'verified' : 'partial'
      }
    }
  }
  if (ql.includes('task') || ql.includes('incomplete')) {
    const open = f.tasks.filter((t) => t.status !== 'Done')
    return {
      role: 'ai',
      text: `${open.length} tasks remain incomplete:\n${open
        .map((t) => `• **${t.title}** (${t.status.toLowerCase()}, ${t.priority} priority, due ${t.due}, owner ${personById(t.ownerId).name})`)
        .join('\n')}`,
      cites: open.flatMap((t) => t.evidenceIds).slice(0, 5),
      findings: open.slice(0, 3).map((t) => ({ ...t, kind: 'Task' as const })),
      grounded: open.every((t) => isV({ ...t, kind: 'Task' })) ? 'verified' : 'partial'
    }
  }
  if (ql.includes('unresolved') || ql.includes('issue') || ql.includes('risk')) {
    const r = f.risks.filter((x) => x.resolution !== 'Resolved')
    return {
      role: 'ai',
      text: `These issues are still open:\n${r
        .map((x) => `• **[${x.severity}] ${x.title}**: ${x.impact}.`)
        .join('\n')}${
        all.some((x) => (verif[x.id] ?? x.verification) === 'conflicting')
          ? '\n\nNote: some related findings have conflicting evidence and haven’t been resolved by a reviewer.'
          : ''
      }`,
      cites: r.flatMap((x) => x.evidenceIds).slice(0, 5),
      findings: r.slice(0, 3).map((x) => ({ ...x, kind: 'Risk' as const })),
      grounded: 'partial'
    }
  }
  if (ql.includes('deploy') || ql.includes('responsible')) {
    const ev = evidence.find((e) => e.projectId === pid && /deploy|release|rollout/i.test(e.content))
    if (ev) {
      return {
        role: 'ai',
        text: `According to **${ev.title}**: ${
          ev.extracted.find((x) => /deploy|release|rollout/i.test(x)) ?? ev.extracted[0] ?? ''
        }. No single named owner is recorded, so confirm who covers this with your manager.`,
        cites: [ev.id],
        grounded: ev.verification === 'verified' ? 'verified' : 'partial'
      }
    }
    return {
      role: 'ai',
      text: 'I couldn’t find verified evidence naming a deployment owner for this project. I won’t guess. This has been logged as a knowledge gap; ask the outgoing member directly.',
      grounded: 'none'
    }
  }
  if (ql.includes('first') || ql.includes('start') || ql.includes('priority')) {
    const order = ['Critical', 'High', 'Medium', 'Low']
    const t = [...f.tasks].filter((x) => x.status !== 'Done').sort((a, b) => order.indexOf(a.priority) - order.indexOf(b.priority))[0]
    const r = f.risks.find((x) => x.severity === 'Critical' || x.severity === 'High')
    return {
      role: 'ai',
      text: `I'd start with **${t?.title ?? 'reviewing open tasks'}**. It's ${t?.priority.toLowerCase()} priority and due ${t?.due}.${
        r ? ` In parallel, get familiar with the risk “${r.title}”, since ${r.impact.toLowerCase()}.` : ''
      }`,
      cites: [...(t?.evidenceIds ?? []), ...(r?.evidenceIds ?? [])].slice(0, 4),
      findings: [t && { ...t, kind: 'Task' as const }, r && { ...r, kind: 'Risk' as const }].filter(Boolean) as AnyFinding[],
      grounded: 'partial'
    }
  }
  const words = ql.split(/\W+/).filter((w) => w.length > 3)
  const hits = all
    .map((x) => ({
      x,
      score: words.filter((w) => (x.title + ' ' + x.summary).toLowerCase().includes(w)).length
    }))
    .filter((h) => h.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, 2)
  if (hits.length) {
    return {
      role: 'ai',
      text: hits.map(({ x }) => `**${x.title}**: ${x.summary}`).join('\n\n'),
      cites: hits.flatMap(({ x }) => x.evidenceIds).slice(0, 4),
      findings: hits.map(({ x }) => x),
      grounded: hits.every(({ x }) => isV(x)) ? 'verified' : 'partial'
    }
  }
  return {
    role: 'ai',
    text: 'I couldn’t find evidence in this handover that answers that. I only answer from the project’s authorised, linked evidence. Try rephrasing, or send the question to the outgoing member.',
    grounded: 'none'
  }
}

function RichText({ text }: { text: string }) {
  return (
    <>
      {text.split('\n').map((line, i) => (
        <p key={i} className={line.startsWith('•') ? 'pl-1' : i ? 'mt-2' : ''}>
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
  const { members, user } = useLiveApp()
  const { h, project } = useHandover(id)
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [input, setInput] = useState('')
  const [typing, setTyping] = useState(false)
  const [conv, setConv] = useState('current')
  const end = useRef<HTMLDivElement>(null)

  useEffect(() => {
    end.current?.scrollIntoView({ behavior: 'smooth' })
  }, [msgs, typing])

  if (!h || !project) return <HandoverNotFound />

  const ask = (q: string) => {
    if (!q.trim() || typing) return
    setMsgs((m) => [...m, { role: 'user', text: q }])
    setInput('')
    setTyping(true)
    setTimeout(() => {
      setMsgs((m) => [...m, answer(q, h.projectId, s.verif)])
      setTyping(false)
    }, 950)
  }

  const last = [...msgs].reverse().find((m) => m.role === 'ai')
  const history = [
    { id: 'current', title: msgs[0]?.text ?? 'New conversation', when: 'Now' },
    { id: 'c2', title: 'How does the slot reservation alert work?', when: 'Yesterday' },
    { id: 'c3', title: 'Who owns dbt incremental models?', when: 'Jun 16' }
  ]

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
          <h1 className="flex items-center gap-2.5 text-[22px] font-semibold tracking-tight text-navy">
            Handover Assistant <Badge tone="indigo" icon={ShieldCheck}>Evidence-grounded</Badge>
          </h1>
          <p className="mt-1 text-sm text-muted">
            Answers come only from this handover's linked evidence, with citations. It never invents facts.
          </p>
        </div>
      </div>
      <div className="grid h-[calc(100dvh-260px)] min-h-[520px] gap-5 lg:grid-cols-[240px_1fr] xl:grid-cols-[240px_1fr_320px]">
        <Card className="hidden flex-col overflow-hidden lg:flex">
          <div className="border-b border-line p-3">
            <Button
              variant="secondary"
              className="w-full"
              icon={Plus}
              onClick={() => {
                setMsgs([])
                setConv('current')
              }}
            >
              New conversation
            </Button>
          </div>
          <p className="px-4 pb-1 pt-3 text-[11px] font-semibold uppercase tracking-wide text-slate-400">History</p>
          <ul className="flex-1 space-y-0.5 overflow-y-auto px-2">
            {history.map((c) => (
              <li key={c.id}>
                <button
                  onClick={() => setConv(c.id)}
                  className={cn(
                    'w-full rounded-lg px-2.5 py-2 text-left',
                    conv === c.id ? 'bg-tint' : 'hover:bg-slate-50'
                  )}
                >
                  <span className="line-clamp-1 text-[13px] font-medium text-navy">{c.title}</span>
                  <span className="text-[11px] text-muted">{c.when}</span>
                </button>
              </li>
            ))}
          </ul>
        </Card>
        <Card className="flex min-h-0 flex-col overflow-hidden">
          <div className="scrollbar-thin flex-1 space-y-5 overflow-y-auto p-4 sm:p-6">
            {conv !== 'current' ? (
              <EmptyState
                icon={History}
                title="Past conversation"
                body="Archived conversations are read-only in this prototype. Start a new one to ask questions."
                action={<Button variant="secondary" onClick={() => setConv('current')}>Back to current</Button>}
              />
            ) : !msgs.length ? (
              <div className="flex h-full flex-col items-center justify-center text-center">
                <span className="flex size-12 items-center justify-center rounded-2xl bg-tint text-brand">
                  <Sparkles className="size-5" />
                </span>
                <p className="mt-4 text-base font-semibold text-navy">Ask about {project.name}</p>
                <p className="mt-1 max-w-sm text-[13px] text-muted">
                  Every answer links to the commits, issues, threads and documents it's based on.
                </p>
                <div className="mt-6 flex max-w-lg flex-wrap justify-center gap-2">
                  {SUGGESTED.map((q) => (
                    <button
                      key={q}
                      onClick={() => ask(q)}
                      className="rounded-full border border-line bg-white px-3 py-1.5 text-[13px] text-navy hover:border-brand/40 hover:bg-tint/40"
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              msgs.map((m, i) =>
                m.role === 'user' ? (
                  <div key={i} className="flex justify-end">
                    <div className="max-w-[80%] rounded-2xl rounded-br-md bg-brand px-4 py-2.5 text-[13.5px] text-white">
                      {m.text}
                    </div>
                  </div>
                ) : (
                  <div key={i} className="flex gap-3">
                    <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-tint text-brand">
                      <Bot className="size-4" />
                    </span>
                    <div className="min-w-0 max-w-[88%] flex-1">
                      <div className="rounded-2xl rounded-tl-md border border-line bg-white px-4 py-3 text-[13.5px] leading-relaxed text-slate-700">
                        <RichText text={m.text} />
                        {m.cites && !!m.cites.length && (
                          <div className="mt-3 flex flex-wrap gap-1.5 border-t border-line pt-3">
                            {m.cites.map((c, ci) => (
                              <span key={c} className="flex items-center gap-1">
                                <span className="text-[11px] font-semibold text-brand">[{ci + 1}]</span>
                                <EvidenceChip id={c} />
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                      <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[11px]">
                        {m.grounded === 'verified' && <Badge tone="green" icon={ShieldCheck}>Based on verified findings</Badge>}
                        {m.grounded === 'partial' && <Badge tone="amber" icon={CircleAlert}>Includes unverified findings</Badge>}
                        {m.grounded === 'none' && <Badge tone="gray" icon={FileQuestion}>No supporting evidence</Badge>}
                        {m.grounded === 'none' && (
                          <button
                            className="font-medium text-brand"
                            onClick={() => s.toast(`Question sent to ${getMemberDisplayName(h.outgoingId, members, user)}`, undefined, 'info')}
                          >
                            Ask {getMemberDisplayName(h.outgoingId, members, user).split(' ')[0] ?? getMemberDisplayName(h.outgoingId, members, user)} →
                          </button>
                        )}
                        <span className="ml-auto flex gap-1">
                          <button
                            className="rounded p-1 text-slate-400 hover:text-navy"
                            aria-label="Helpful"
                            onClick={() => s.toast('Thanks for the feedback')}
                          >
                            <ThumbsUp className="size-3.5" />
                          </button>
                          <button
                            className="rounded p-1 text-slate-400 hover:text-navy"
                            aria-label="Not helpful"
                            onClick={() => s.toast('Feedback recorded', 'A reviewer will look at this answer.', 'info')}
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
            {typing && (
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
                  <span className="ml-2 text-xs text-muted">Searching evidence…</span>
                </div>
              </div>
            )}
            <div ref={end} />
          </div>
          {conv === 'current' && (
            <div className="border-t border-line p-3">
              {!!msgs.length && (
                <div className="scrollbar-thin mb-2 flex gap-1.5 overflow-x-auto">
                  {SUGGESTED.filter((q) => !msgs.some((m) => m.text === q)).map((q) => (
                    <button
                      key={q}
                      onClick={() => ask(q)}
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
                  ask(input)
                }}
                className="flex items-end gap-2"
              >
                <Textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault()
                      ask(input)
                    }
                  }}
                  rows={1}
                  placeholder="Ask a question about this handover…"
                  className="min-h-[42px] resize-none"
                />
                <Button type="submit" icon={Send} disabled={!input.trim() || typing} className="h-[42px]" aria-label="Send" />
              </form>
              <p className="mt-1.5 text-[11px] text-slate-400">Answers may include unverified findings; these are always labelled.</p>
            </div>
          )}
        </Card>
        <Card className="hidden overflow-y-auto xl:block">
          <CardHeader title="Sources in this answer" icon={Link2} />
          <div className="space-y-2 px-5 pb-4">
            {last?.cites?.length ? (
              last.cites.map((c) => <EvidenceCard key={c} id={c} compact />)
            ) : (
              <p className="text-[13px] text-muted">Citations for the latest answer appear here.</p>
            )}
          </div>
          <CardHeader title="Related findings" icon={Sparkles} className="border-t border-line" />
          <ul className="space-y-2 px-5 pb-5">
            {last?.findings?.length ? (
              last.findings.map((x) => (
                <li key={x.id} className="rounded-xl border border-line p-3">
                  <p className="text-[13px] font-medium text-navy">{x.title}</p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    <Badge tone="indigo">{x.kind}</Badge>
                    <VerificationBadge status={s.verif[x.id] ?? x.verification} />
                  </div>
                </li>
              ))
            ) : (
              <li className="text-[13px] text-muted">None yet.</li>
            )}
          </ul>
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
