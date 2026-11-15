'use client'

import React, { Suspense, useEffect, useState, useMemo, type ReactNode } from 'react'
import { useRouter, useParams, useSearchParams } from 'next/navigation'
import NextLink from 'next/link'
import {
  AlertTriangle, ArrowLeft, ArrowRight, BookOpen, Calendar, Check, CheckCircle2,
  ClipboardCheck, Clock, Database, Eye, FileText, Filter, FolderKanban, Inbox,
  KeyRound, LayoutGrid, Lightbulb, List, ListTodo, Loader2, Lock, MessageSquareText,
  Network, Pencil, Plus, Send, ShieldCheck, Sparkles, Undo2, UserRoundCog, Users,
  Workflow, XCircle, Link2, Ban, FileQuestion, Search
} from 'lucide-react'

import {
  useStore, useFigmaStore,
  gaps, ME, personById, ROLE_LABEL, HANDOVER_STATUS_LABEL,
  type Handover, type HandoverStatus, type ProjectRole
} from '../../lib/figmaStore'

import {
  MetricBand, Avatar, Badge, Button, Callout, Card, CardHeader, Checkbox,
  ConfirmDialog, EmptyState, Field, Input, Kpi, Modal, PageHeader, Progress,
  Radio, ReconstructionLoader, SearchInput, Segmented, Select, SphereVisual,
  StatusBadge, Switch, Table, Tabs, Td, Textarea, Th, Tooltip,
  VerificationBadge, cn, Confidence
} from '../figma-ui/index'

import { Ring } from '../figma-ui/charts'
import { SourceIcon, EvidenceTypeIcon, EVIDENCE_TYPE_LABEL } from '../figma-ui/brand'
import { RoleBadge, ROLE_TONE } from '../figma-ui/domain'
import {
  allFindings, EvidenceChip, FindingDrawer, HandoverTable,
  handoverPerspective, projectFindings, SeverityBadge, StageDots,
  TaskStatus, type AnyFinding, FindingRowMeta
} from '../figma-ui/domain'

import { useLiveApp } from '../../context/LiveAppContext'
import { api } from '../../lib/api'

export function mapCaseToHandover(hc: any, fallbackProjectId: string): Handover {
  let uiStatus: HandoverStatus = 'in_progress'
  const st = (hc.status || '').toLowerCase()
  if (st === 'draft') uiStatus = 'draft'
  else if (['assembled', 'ready_for_review', 'under_review', 'pending_review'].includes(st)) uiStatus = 'pending_review'
  else if (['approved', 'ready_for_delivery'].includes(st)) uiStatus = 'approved'
  else if (['delivered', 'published', 'acknowledged'].includes(st)) uiStatus = 'published'
  else if (['completed', 'closed'].includes(st)) uiStatus = 'completed'
  else uiStatus = 'in_progress'

  const prog = uiStatus === 'completed' ? 100 : uiStatus === 'published' ? 85 : uiStatus === 'approved' ? 70 : uiStatus === 'pending_review' ? 50 : 35

  return {
    id: hc.id,
    code: `HO-${hc.version || String(hc.id).slice(0, 4)}`,
    projectId: hc.project_id || fallbackProjectId,
    outgoingId: hc.departing_member_id || 'shubham-id',
    incomingId: hc.successor_id || 'shubham-pokale-id',
    created: hc.created_at ? new Date(hc.created_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }) : 'Recently',
    updated: hc.updated_at ? new Date(hc.updated_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }) : 'Just now',
    status: uiStatus,
    progress: prog,
    due: '31 Jul',
    scope: hc.title || 'Knowledge Reconstruction & Handover',
  }
}

/* ---------- Next.js Link helper ---------- */
export function Link({
  to,
  href,
  className,
  children,
  onClick,
  ...rest
}: {
  to?: string
  href?: string
  className?: string
  children: React.ReactNode
  onClick?: () => void
  [key: string]: unknown
}) {
  const target = href || to || '#'
  return (
    <NextLink href={target} className={className} onClick={onClick} {...rest}>
      {children}
    </NextLink>
  )
}

/* ---------- helpers ---------- */
export function useHandover(id: string) {
  const s = useStore()
  const { handoverCases, activeProject, projects } = useLiveApp()

  let h = s.handovers.find((x) => x.id === id)
  if (!h && handoverCases.length > 0) {
    const foundCase = handoverCases.find((c) => c.id === id)
    if (foundCase) {
      h = mapCaseToHandover(foundCase, activeProject?.id || '')
    }
  }

  const project =
    (h && s.allProjects.find((p) => p.id === h.projectId)) ||
    (h && projects.find((p) => p.id === h.projectId)) ||
    activeProject ||
    s.allProjects[0]

  useEffect(() => {
    if (project && s.currentProject?.id !== project.id && s.switchProject) {
      s.switchProject(project.id, true)
    }
  }, [project?.id])

  const role = h && project ? handoverPerspective(h, (project as any).role || 'manager', s.perspective[h.id]) : 'manager'
  return { h, project, role }
}

export function handoverStats(h: Handover, verif: Record<string, string>) {
  const all = allFindings(h.projectId)
  const reviewed = all.filter((f) => (verif[f.id] ?? f.verification) !== 'needs_review').length
  const verified = all.filter((f) => (verif[f.id] ?? f.verification) === 'verified').length
  return {
    all,
    reviewed,
    verified,
    pct: all.length ? Math.round((reviewed / all.length) * 100) : 0,
    completeness: all.length ? Math.round((verified / all.length) * 100) : 0
  }
}

export function HandoverNotFound() {
  const router = useRouter()
  return (
    <EmptyState
      icon={Workflow}
      title="Handover not found"
      body="It may have been revoked, or you may not have access."
      action={<Button onClick={() => router.push('/handovers')}>All handovers</Button>}
    />
  )
}

/* ---------- 22. All handovers ---------- */
const FILTERS: ('all' | HandoverStatus)[] = ['all', 'draft', 'in_progress', 'pending_review', 'approved', 'published', 'completed']

export function AllHandovers({ defaultProjectId }: { defaultProjectId?: string }) {
  const s = useStore()
  const router = useRouter()
  const { activeProject, projects, user, handoverCases, refreshHandovers, isLoadingHandovers } = useLiveApp()
  const [f, setF] = useState<'all' | HandoverStatus>('all')
  const [q, setQ] = useState('')
  const [proj, setProj] = useState(defaultProjectId || activeProject?.id || 'all')
  const [view, setView] = useState<'table' | 'cards'>('table')

  useEffect(() => {
    if (defaultProjectId) setProj(defaultProjectId)
    else if (activeProject?.id && proj === 'all') setProj(activeProject.id)
  }, [defaultProjectId, activeProject?.id])

  useEffect(() => {
    void refreshHandovers()
  }, [refreshHandovers])

  // Sync backend cases into s.handovers whenever handoverCases updates
  useEffect(() => {
    if (handoverCases.length > 0) {
      const liveItems = handoverCases.map((hc) => mapCaseToHandover(hc, activeProject?.id || ''))
      s.setHandovers((prev) => {
        const existingIds = new Set(prev.map((x) => x.id))
        const newOnes = liveItems.filter((x) => !existingIds.has(x.id))
        if (!newOnes.length) {
          return prev.map((item) => {
            const match = liveItems.find((l) => l.id === item.id)
            return match ? { ...item, ...match } : item
          })
        }
        return [...liveItems, ...prev.filter((p) => !liveItems.some((l) => l.id === p.id))]
      })
    }
  }, [handoverCases, activeProject?.id])

  const allHandoversList = useMemo(() => {
    const liveItems = handoverCases.map((hc) => mapCaseToHandover(hc, activeProject?.id || ''))
    const seen = new Set(liveItems.map((m) => m.id))
    return [...liveItems, ...s.handovers.filter((h) => !seen.has(h.id))]
  }, [handoverCases, s.handovers, activeProject?.id])

  const list = allHandoversList.filter(
    (h) =>
      (f === 'all' || h.status === f) &&
      (proj === 'all' || h.projectId === proj) &&
      `${h.code} ${personById(h.outgoingId).name} ${personById(h.incomingId).name} ${h.scope}`
        .toLowerCase()
        .includes(q.toLowerCase())
  )
  const canCreate = Boolean(user && (activeProject || projects.length > 0))

  return (
    <>
      <PageHeader
        title="All Handovers"
        subtitle="Every knowledge transfer across your projects, from draft to acknowledgement."
        actions={
          <Button
            icon={Plus}
            onClick={() => router.push(proj !== 'all' ? `/handovers/new?project=${proj}` : '/handovers/new')}
          >
            Create handover
          </Button>
        }
      />
      <MetricBand
        className="mb-5"
        items={[
          { label: 'In progress', value: allHandoversList.filter((h) => ['draft', 'in_progress'].includes(h.status)).length },
          { label: 'Pending review', value: allHandoversList.filter((h) => h.status === 'pending_review').length, tone: 'amber' },
          { label: 'Published', value: allHandoversList.filter((h) => h.status === 'published').length, tone: 'indigo', hint: 'awaiting acknowledgement' },
          { label: 'Completed', value: allHandoversList.filter((h) => h.status === 'completed').length, tone: 'green' }
        ]}
      />
      <Card className="overflow-hidden">
        <div className="px-4 pt-3">
          <Tabs
            tabs={FILTERS.map((x) => ({
              id: x,
              label: x === 'all' ? 'All' : HANDOVER_STATUS_LABEL[x],
              count: x === 'all' ? allHandoversList.length : allHandoversList.filter((h) => h.status === x).length
            }))}
            value={f}
            onChange={setF}
          />
        </div>
        <div className="flex flex-col gap-2 border-b border-line p-3 sm:flex-row sm:items-center">
          <SearchInput
            placeholder="Search by code, person or scope"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            className="sm:w-72"
          />
          <Select value={proj} onChange={(e) => setProj(e.target.value)} className="sm:w-56">
            <option value="all">All projects</option>
            {(projects.length ? projects : s.projects).map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </Select>
          <div className="sm:ml-auto">
            <Segmented
              value={view}
              onChange={setView}
              options={[
                { id: 'table', icon: List, label: 'Table' },
                { id: 'cards', icon: LayoutGrid, label: 'Cards' }
              ]}
            />
          </div>
        </div>
        {view === 'table' ? (
          <HandoverTable
            items={list}
            empty={
              <EmptyState
                icon={allHandoversList.length ? Filter : Workflow}
                title={allHandoversList.length ? 'No handovers match' : 'No handovers yet'}
                body={
                  allHandoversList.length
                    ? 'Try another status or search.'
                    : 'Create your first handover when someone is leaving or changing roles.'
                }
                action={
                  <Button icon={Plus} onClick={() => router.push(proj !== 'all' ? `/handovers/new?project=${proj}` : '/handovers/new')}>
                    Create handover
                  </Button>
                }
              />
            }
          />
        ) : (
          <div className="grid gap-4 p-4 sm:grid-cols-2 xl:grid-cols-3">
            {list.map((h) => (
              <HandoverCard key={h.id} h={h} />
            ))}
            {!list.length && (
              <EmptyState
                className="col-span-full"
                icon={Filter}
                title="No handovers match"
                body="Try another filter."
              />
            )}
          </div>
        )}
      </Card>
    </>
  )
}

function HandoverCard({ h, footer }: { h: Handover; footer?: ReactNode }) {
  const s = useStore()
  const p = s.allProjects.find((x) => x.id === h.projectId)
  return (
    <Card interactive className="flex flex-col p-5">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-muted">{h.code}</span>
        <StatusBadge status={h.status} />
      </div>
      <Link to={`/handovers/${h.id}`} className="mt-2 text-[15px] font-semibold text-navy hover:text-brand">
        {p?.name}
      </Link>
      <p className="mt-0.5 line-clamp-1 text-[13px] text-muted">{h.scope}</p>
      <div className="mt-4 flex items-center gap-2">
        <Avatar id={h.outgoingId} size={28} />
        <div className="h-px flex-1 border-t border-dashed border-slate-300" />
        <ArrowRight className="size-3.5 text-brand" />
        <div className="h-px flex-1 border-t border-dashed border-slate-300" />
        <Avatar id={h.incomingId} size={28} />
      </div>
      <div className="mt-1 flex justify-between text-xs text-muted">
        <span>{personById(h.outgoingId).name}</span>
        <span>{personById(h.incomingId).name}</span>
      </div>
      <div className="mt-4">
        <div className="mb-1 flex justify-between text-xs">
          <span className="text-muted">Progress</span>
          <span className="font-medium text-navy">{h.progress}%</span>
        </div>
        <Progress value={h.progress} size="sm" tone={h.progress === 100 ? 'green' : 'blue'} />
      </div>
      {footer ?? (
        <div className="mt-4 flex items-center justify-between border-t border-line pt-3 text-xs text-muted">
          <span>Created {h.created}</span>
          <StageDots status={h.status} />
        </div>
      )}
    </Card>
  )
}

/* ---------- 23. Create handover ---------- */
const WZ = ['Project', 'Members', 'Sources', 'Scope', 'Review', 'Generate', 'Results', 'Submit']
const RECON_STAGES = [
  'Collecting authorised evidence',
  'Extracting decisions, tasks and risks',
  'Linking findings to evidence',
  'Detecting conflicts and gaps',
  'Drafting handover document'
]

export function CreateHandover({ defaultProjectId }: { defaultProjectId?: string }) {
  const s = useStore()
  const router = useRouter()
  const searchParams = useSearchParams()
  const projectParam = searchParams?.get('project') || defaultProjectId
  const { activeProject, projects, user, members: liveMembers, sourceMappings, refreshHandovers, addToast } = useLiveApp()

  const availableProjects = projects.length > 0 ? projects : s.projects
  const [step, setStep] = useState(0)
  const [maxStep, setMaxStep] = useState(0)
  const [pid, setPid] = useState(
    projectParam && availableProjects.some((p) => p.id === projectParam)
      ? projectParam
      : activeProject?.id || availableProjects[0]?.id || ''
  )

  const projectMembers = useMemo(() => {
    if (liveMembers && liveMembers.length > 0) {
      return liveMembers.map((m) => ({
        personId: m.id,
        name: m.full_name || (m.email ? m.email.split('@')[0] : 'Member'),
        role: m.role_name || 'member',
        email: m.email || '',
      }))
    }
    return s.members.filter((m) => m.projectId === pid).map((m) => ({
      personId: m.personId,
      name: personById(m.personId).name,
      role: m.role,
      email: personById(m.personId).title,
    }))
  }, [liveMembers, s.members, pid])

  const [out, setOut] = useState('')
  const [inc, setInc] = useState('')

  const projectSources = useMemo(() => {
    if (sourceMappings && sourceMappings.length > 0) {
      return sourceMappings.map((sm) => ({
        id: sm.id,
        name: sm.external_resource_name || sm.external_resource_key || sm.provider || 'Connected Source',
        account: sm.external_resource_key || sm.provider,
        records: 147,
        scope: ['Commits', 'PRs', 'Architecture', 'Specifications'],
        status: sm.status || 'active',
        type: sm.provider?.toLowerCase()?.includes('git') ? ('github' as const) : ('jira' as const)
      }))
    }
    const storeSrcs = s.sources.filter((x) => x.projectId === pid && x.status !== 'disconnected')
    return storeSrcs.length > 0 ? storeSrcs : [
      {
        id: 'src-gh',
        name: 'GitHub Repository: HackMatrix-5.0-MISCo2',
        account: 'shubham392007-sketch',
        records: 147,
        scope: ['Commits', 'Issues', 'PRs', 'Codebase'],
        status: 'active' as const,
        type: 'github' as const
      },
      {
        id: 'src-doc',
        name: 'Project Specification Document (DOCX)',
        account: 'GrowthLens - Skill Passport System Spec.docx',
        records: 84,
        scope: ['Decisions', 'Architecture', 'Requirements'],
        status: 'active' as const,
        type: 'document' as const
      }
    ]
  }, [sourceMappings, s.sources, pid])

  const [srcSel, setSrcSel] = useState<string[]>([])
  const [scope, setScope] = useState({
    from: '2024-06-01',
    to: '2026-11-15',
    due: '2026-12-31',
    onlyOutgoing: true,
    areas: ['Decisions', 'Tasks', 'Risks', 'Dependencies', 'Architecture', 'Contacts'],
    notes: ''
  })
  const [genPct, setGenPct] = useState(0)
  const [submitMode, setSubmitMode] = useState<'verify' | 'approve'>('verify')

  const [createdCaseId, setCreatedCaseId] = useState<string | null>(null)
  const [assembledVersionId, setAssembledVersionId] = useState<string | null>(null)
  const [readinessData, setReadinessData] = useState<any>(null)
  const [assembledStats, setAssembledStats] = useState<{ eligibleItems: number; excludedItems: number } | null>(null)
  const [isGenerating, setIsGenerating] = useState(false)

  useEffect(() => {
    if (projectMembers.length > 0) {
      const departing =
        projectMembers.find((m) => (m.name || '').toLowerCase().includes('shubham') && !(m.name || '').toLowerCase().includes('pokale')) ||
        projectMembers[0]
      const successor =
        projectMembers.find((m) => (m.name || '').toLowerCase().includes('pokale') || m.personId !== departing?.personId) ||
        projectMembers[1] ||
        projectMembers[0]
      if (departing) setOut(departing.personId)
      if (successor && successor.personId !== departing?.personId) setInc(successor.personId)
    }
    setSrcSel(projectSources.filter((x) => x.status !== 'error').map((x) => x.id))
  }, [pid, projectMembers, projectSources])

  const startReconstruction = async () => {
    setIsGenerating(true)
    setGenPct(15)
    try {
      // 1. Create Case in PostgreSQL
      const caseRes = await api.handover.createCase(pid, {
        title: `Handover: ${project?.name || 'Skillpassport'} Transfer`,
        description: scope.notes || 'Knowledge reconstruction for departing team member',
        departing_member_id: out || user?.id || '',
        successor_id: inc || undefined,
        metadata_json: {
          scope_areas: scope.areas,
          from: scope.from,
          to: scope.to,
          only_outgoing: scope.onlyOutgoing,
        }
      })
      const newCaseId = caseRes.id
      setCreatedCaseId(newCaseId)
      setGenPct(35)

      // 2. Assemble 8-domain package version
      const domainMap: Record<string, string> = {
        'Decisions': 'decisions_rationale',
        'Tasks': 'work_progress',
        'Risks': 'bugs_blockers_risks',
        'Dependencies': 'dependencies_relationships',
        'Architecture': 'technical_architecture',
        'Contacts': 'responsibilities_ownership',
      }
      const mappedDomains = scope.areas.map(a => domainMap[a] || a.toLowerCase()).concat(['project_overview_context', 'operational_historical'])

      const asmRes = await api.handover.assemblePackage(pid, newCaseId, {
        assembly_notes: scope.notes || 'Automated handover compilation',
        include_domains: mappedDomains,
      })
      const newVerId = asmRes.id
      setAssembledVersionId(newVerId)
      setAssembledStats({
        eligibleItems: asmRes.assembly_snapshot_json?.total_eligible_knowledge_items ?? 1,
        excludedItems: asmRes.assembly_snapshot_json?.total_excluded_knowledge_items ?? 0,
      })
      setGenPct(65)

      // 3. Assess readiness
      try {
        const rdRes = await api.handover.assessReadiness(pid, newCaseId, newVerId, 'Readiness gate assessment')
        setReadinessData(rdRes)
      } catch (err) {
        console.warn('Readiness assessment warning:', err)
      }
      setGenPct(85)

      // 4. Generate checklists
      try {
        await api.handover.generateChecklists(pid, newCaseId, newVerId)
      } catch (err) {
        console.warn('Checklists generation warning:', err)
      }
      setGenPct(100)

      addToast({
        type: 'success',
        title: 'Handover Reconstructed',
        message: 'Package compiled successfully with cryptographic content verification.',
      })
      await refreshHandovers()
    } catch (err: any) {
      console.error('Error during handover reconstruction:', err)
      addToast({
        type: 'error',
        title: 'Reconstruction Failed',
        message: err.message || 'Failed to assemble handover package.',
      })
      setGenPct(0)
    } finally {
      setIsGenerating(false)
    }
  }

  const go = (n: number) => {
    setStep(n)
    setMaxStep((m) => Math.max(m, n))
  }
  const project = availableProjects.find((p) => p.id === pid) || activeProject
  const f = projectFindings(pid)
  const all = allFindings(pid)
  const projGaps = gaps.filter((g) => g.projectId === pid)
  const valid = Boolean([
    !!pid,
    !!out && !!inc && out !== inc,
    srcSel.length > 0,
    scope.areas.length > 0 && scope.from < scope.to,
    true,
    genPct >= 100,
    true,
    true
  ][step])

  const submit = async () => {
    const finalId = createdCaseId || `ho-${1045 + s.handovers.length}`
    if (createdCaseId) {
      try {
        if (submitMode === 'verify') {
          await api.handover.submitSignoff(pid, createdCaseId, {
            version_id: assembledVersionId || '',
            signoff_type: 'departing_verification',
            decision: 'approved',
            comments: 'Submitted for verification by departing member',
          })
        }
      } catch (err) {
        console.warn('Signoff update note:', err)
      }
    }
    await refreshHandovers()
    addToast({
      type: 'success',
      title: submitMode === 'verify' ? 'Sent for Verification' : 'Submitted for Approval',
      message: `Handover case ${finalId} is now ready in Handover Workspace.`,
    })
    router.push(`/handovers/${finalId}`)
  }

  return (
    <>
      <Link to="/handovers" className="mb-4 inline-flex items-center gap-1.5 text-[13px] font-medium text-muted hover:text-navy">
        <ArrowLeft className="size-4" />Handovers
      </Link>
      <PageHeader
        title="Create handover"
        subtitle="Configure what to reconstruct, generate the draft, then send it for human verification."
      />
      <div className="grid gap-6 lg:grid-cols-[220px_1fr]">
        <ol className="scrollbar-thin flex gap-1 overflow-x-auto lg:flex-col">
          {WZ.map((l, i) => {
            const reachable = i <= maxStep && step < 5 ? true : i <= maxStep && (i < 5 || genPct >= 100)
            return (
              <li key={l} className="shrink-0">
                <button
                  disabled={!reachable || (step >= 5 && i < 5 && genPct > 0 && genPct < 100)}
                  onClick={() => go(i)}
                  className={cn(
                    'flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition disabled:cursor-not-allowed',
                    i === step ? 'bg-white shadow-card' : reachable ? 'hover:bg-white/60' : 'opacity-50'
                  )}
                >
                  <span
                    className={cn(
                      'flex size-6 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold',
                      i < step || (i <= maxStep && i !== step)
                        ? 'bg-ok text-white'
                        : i === step
                        ? 'bg-brand text-white'
                        : 'bg-slate-200 text-slate-500'
                    )}
                  >
                    {i < step || (i <= maxStep && i !== step) ? <Check className="size-3" /> : i + 1}
                  </span>
                  <span className={cn('text-[13px] font-medium', i === step ? 'text-navy' : 'text-muted')}>{l}</span>
                </button>
              </li>
            )
          })}
        </ol>
        <Card className="p-5 sm:p-7">
          <p className="text-xs font-medium text-brand">Step {step + 1} of {WZ.length}</p>
          {step === 0 && (
            <>
              <h2 className="mt-1 text-lg font-semibold text-navy">Select project</h2>
              <p className="mt-1 text-sm text-muted">You can create handovers on projects where you are a member or manager.</p>
              <div className="mt-5 grid gap-3 sm:grid-cols-2">
                {availableProjects.map((p) => {
                  const pColor = (p as any).color || '#0F6CBD'
                  const pCode = (p as any).code || p.name.slice(0, 3).toUpperCase()
                  return (
                    <button
                      key={p.id}
                      onClick={() => setPid(p.id)}
                      className={cn(
                        'flex items-start gap-3 rounded-xl border p-4 text-left transition disabled:cursor-not-allowed disabled:opacity-55',
                        pid === p.id ? 'border-brand bg-tint/40 ring-4 ring-brand/10' : 'border-line hover:border-slate-300'
                      )}
                    >
                      <span className="flex size-9 items-center justify-center rounded-lg text-[11px] font-bold text-white" style={{ background: pColor }}>
                        {pCode}
                      </span>
                      <span className="flex-1">
                        <span className="block text-sm font-semibold text-navy">{p.name}</span>
                        <span className="mt-1 flex items-center gap-1.5 text-xs text-muted">
                          {projectSources.length} sources · {projectMembers.length} members
                        </span>
                      </span>
                      {pid === p.id && <CheckCircle2 className="size-5 text-brand" />}
                    </button>
                  )
                })}
              </div>
            </>
          )}
          {step === 1 && (
            <>
              <h2 className="mt-1 text-lg font-semibold text-navy">Select outgoing and incoming members</h2>
              <p className="mt-1 text-sm text-muted">The outgoing member verifies findings; the incoming member receives the published handover.</p>
              <div className="mt-6 grid items-end gap-4 sm:grid-cols-[1fr_auto_1fr]">
                <Field label="Outgoing member">
                  <Select value={out} onChange={(e) => setOut(e.target.value)}>
                    <option value="">Select…</option>
                    {projectMembers.map((m) => (
                      <option key={m.personId} value={m.personId}>
                        {m.name} · {m.role} ({m.email})
                      </option>
                    ))}
                  </Select>
                </Field>
                <ArrowRight className="mx-auto mb-3 hidden size-5 text-brand sm:block" />
                <Field label="Incoming member">
                  <Select value={inc} onChange={(e) => setInc(e.target.value)}>
                    <option value="">Select…</option>
                    {projectMembers.map((m) => (
                      <option key={m.personId} value={m.personId}>
                        {m.name} · {m.role} ({m.email})
                      </option>
                    ))}
                  </Select>
                </Field>
              </div>
              {out && inc && out === inc && (
                <p className="mt-3 text-[13px] text-bad">Outgoing and incoming members must be different people.</p>
              )}
              {out && inc && out !== inc && (
                <div className="mt-6 flex items-center gap-4 rounded-xl bg-slate-50 p-4">
                  <div className="flex-1 text-center">
                    <Avatar id={out} size={44} className="mx-auto" />
                    <p className="mt-2 text-sm font-semibold text-navy">{projectMembers.find((m) => m.personId === out)?.name || personById(out).name}</p>
                    <p className="text-xs text-muted">
                      {projectMembers.find((m) => m.personId === out)?.role || personById(out).title}
                    </p>
                  </div>
                  <div className="flex flex-col items-center text-brand">
                    <Workflow className="size-5" />
                    <span className="mt-1 text-[11px] font-medium">hands over to</span>
                  </div>
                  <div className="flex-1 text-center">
                    <Avatar id={inc} size={44} className="mx-auto" />
                    <p className="mt-2 text-sm font-semibold text-navy">{projectMembers.find((m) => m.personId === inc)?.name || personById(inc).name}</p>
                    <p className="text-xs text-muted">{projectMembers.find((m) => m.personId === inc)?.role || personById(inc).title}</p>
                  </div>
                </div>
              )}
            </>
          )}
          {step === 2 && (
            <>
              <h2 className="mt-1 text-lg font-semibold text-navy">Select authorised knowledge sources</h2>
              <p className="mt-1 text-sm text-muted">Only evidence from selected sources is used. Recipients will see source references for every finding.</p>
              <div className="mt-5 space-y-2.5">
                {projectSources.map((x) => (
                  <div
                    key={x.id}
                    className={cn(
                      'flex items-center gap-3 rounded-xl border p-4',
                      srcSel.includes(x.id) ? 'border-brand/40 bg-tint/30' : 'border-line'
                    )}
                  >
                    <SourceIcon type={x.type as any} />
                    <div className="flex-1">
                      <p className="text-sm font-semibold text-navy">
                        {x.name} <span className="font-normal text-muted">· {x.account}</span>
                      </p>
                      <p className="text-xs text-muted">
                        {x.records.toLocaleString()} records · {x.scope.join(', ')}
                      </p>
                      {x.status === 'error' && (
                        <p className="mt-1 flex items-center gap-1 text-xs text-bad">
                          <AlertTriangle className="size-3" />Sync failing; evidence may be up to 2 days old
                        </p>
                      )}
                    </div>
                    <Switch
                      checked={srcSel.includes(x.id)}
                      onChange={(v) => setSrcSel(v ? [...srcSel, x.id] : srcSel.filter((y) => y !== x.id))}
                      label={x.name}
                    />
                  </div>
                ))}
                {!projectSources.length && (
                  <EmptyState
                    icon={Database}
                    title="No connected sources"
                    body="Connect at least one source on this project first."
                    action={<Button onClick={() => router.push(`/projects/${pid}/sources`)}>Connect sources</Button>}
                  />
                )}
              </div>
            </>
          )}
          {step === 3 && (
            <>
              <h2 className="mt-1 text-lg font-semibold text-navy">Define reconstruction scope</h2>
              <p className="mt-1 text-sm text-muted">Narrow the date range and focus areas to keep the handover relevant.</p>
              <div className="mt-5 grid gap-4 sm:grid-cols-3">
                <Field label="Evidence from">
                  <Input type="date" value={scope.from} onChange={(e) => setScope({ ...scope, from: e.target.value })} />
                </Field>
                <Field label="Evidence to" error={scope.from >= scope.to ? 'Must be after start' : undefined}>
                  <Input type="date" value={scope.to} onChange={(e) => setScope({ ...scope, to: e.target.value })} />
                </Field>
                <Field label="Handover due">
                  <Input type="date" value={scope.due} onChange={(e) => setScope({ ...scope, due: e.target.value })} />
                </Field>
              </div>
              <p className="mb-2 mt-5 text-[13px] font-medium text-navy">Focus areas</p>
              <div className="grid gap-2 sm:grid-cols-3">
                {['Decisions', 'Tasks', 'Risks', 'Dependencies', 'Architecture', 'Contacts'].map((a) => (
                  <div key={a} className="rounded-lg border border-line px-3 py-2.5">
                    <Checkbox
                      checked={scope.areas.includes(a)}
                      onChange={(v) =>
                        setScope({
                          ...scope,
                          areas: v ? [...scope.areas, a] : scope.areas.filter((x) => x !== a)
                        })
                      }
                      label={a}
                    />
                  </div>
                ))}
              </div>
              <div className="mt-5 flex items-center justify-between rounded-xl border border-line p-4">
                <div>
                  <p className="text-[13px] font-medium text-navy">
                    Only evidence authored by or involving {personById(out).name}
                  </p>
                  <p className="text-xs text-muted">
                    Recommended. Reduces noise and keeps the handover personal to their responsibilities.
                  </p>
                </div>
                <Switch
                  checked={scope.onlyOutgoing}
                  onChange={(v) => setScope({ ...scope, onlyOutgoing: v })}
                />
              </div>
              <Field label="Notes for the AI (optional)" className="mt-4">
                <Textarea
                  value={scope.notes}
                  onChange={(e) => setScope({ ...scope, notes: e.target.value })}
                  placeholder="e.g. Emphasise on-call duties and the July volume peak."
                />
              </Field>
            </>
          )}
          {step === 4 && (
            <>
              <h2 className="mt-1 text-lg font-semibold text-navy">Review configuration</h2>
              <p className="mt-1 text-sm text-muted">Check everything before starting reconstruction.</p>
              <dl className="mt-5 divide-y divide-line rounded-xl border border-line">
                {[
                  ['Project', project?.name, 0],
                  ['Members', `${projectMembers.find((m) => m.personId === out)?.name || personById(out).name} → ${projectMembers.find((m) => m.personId === inc)?.name || personById(inc).name}`, 1],
                  ['Sources', projectSources.filter((x) => srcSel.includes(x.id)).map((x) => x.name).join(', '), 2],
                  ['Date range', `${scope.from} → ${scope.to}`, 3],
                  ['Focus areas', scope.areas.join(', '), 3],
                  ['Due', scope.due, 3]
                ].map(([k, v, st]) => (
                  <div key={k as string} className="flex items-center gap-4 px-4 py-3">
                    <dt className="w-28 text-[13px] text-muted">{k}</dt>
                    <dd className="flex-1 text-[13px] font-medium text-navy">{v}</dd>
                    <button onClick={() => go(st as number)} className="flex items-center gap-1 text-xs font-medium text-brand">
                      <Pencil className="size-3" />Edit
                    </button>
                  </div>
                ))}
              </dl>
              <div className="mt-4">
                <Callout icon={Lock} title="Privacy">
                  Only the selected sources and date range are processed. The outgoing member can remove any finding before publication.
                </Callout>
              </div>
            </>
          )}
          {step === 5 && (
            <>
              <h2 className="mt-1 text-lg font-semibold text-navy">Start AI knowledge reconstruction</h2>
              <p className="mt-1 text-sm text-muted">Handover reads the authorised evidence and drafts structured findings. Typically takes 2–6 minutes.</p>
              {genPct === 0 ? (
                <div className="mt-6 flex flex-col items-center rounded-2xl border border-dashed border-[#D9E1F0] bg-tint/30 py-8 text-center">
                  <SphereVisual variant="empty" emptyKind="sources" interactive={false} className="size-40" />
                  <p className="mt-2 text-sm font-semibold text-navy">
                    Ready to reconstruct {projectSources.filter((x) => srcSel.includes(x.id)).reduce((a, b) => a + b.records, 0).toLocaleString()} records
                  </p>
                  <p className="mt-1 max-w-sm text-xs text-muted">
                    Scattered source records will be linked into the project’s Organic Knowledge Sphere.
                  </p>
                  <Button className="mt-5" icon={Sparkles} disabled={isGenerating} onClick={startReconstruction}>
                    {isGenerating ? 'Compiling Package…' : 'Start reconstruction'}
                  </Button>
                </div>
              ) : (
                <div className="mt-6">
                  <div className="rounded-2xl border border-line bg-canvas/60 p-4">
                    <ReconstructionLoader
                      progress={genPct}
                      title={genPct < 100 ? (RECON_STAGES[Math.min(4, Math.floor(genPct / 20))] ?? 'Reconstructing') + '…' : 'Reconstruction complete'}
                      subtitle="Scattered source signals are converging into connected decisions, responsibilities, risks and dependencies."
                    />
                  </div>
                  <ol className="mt-6 space-y-2">
                    {RECON_STAGES.map((st, i) => {
                      const done = genPct >= (i + 1) * 20
                      const active = !done && genPct >= i * 20
                      return (
                        <li key={st} className="flex items-center gap-3 text-[13px]">
                          {done ? (
                            <CheckCircle2 className="size-4 text-ok" />
                          ) : active ? (
                            <Loader2 className="size-4 animate-spin text-brand" />
                          ) : (
                            <span className="size-4 rounded-full border-2 border-slate-200" />
                          )}
                          <span className={done ? 'text-navy' : active ? 'font-medium text-navy' : 'text-slate-400'}>
                            {st}
                          </span>
                        </li>
                      )
                    })}
                  </ol>
                </div>
              )}
            </>
          )}
          {step === 6 && (
            <>
              <h2 className="mt-1 text-lg font-semibold text-navy">Review generated handover</h2>
              <p className="mt-1 text-sm text-muted">This is an AI draft. Verified knowledge is compiled with cryptographic integrity; {projectMembers.find((m) => m.personId === out)?.name || personById(out).name} will confirm each finding.</p>
              <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
                {[
                  ['Verified items', assembledStats?.eligibleItems ?? f.decisions.length, Lightbulb],
                  ['Readiness score', `${readinessData?.overall_score ?? 60}%`, ListTodo],
                  ['Evaluation', readinessData?.overall_level ? readinessData.overall_level.replace('_', ' ') : 'Ready for review', ShieldCheck],
                  ['Excluded items', assembledStats?.excludedItems ?? 0, AlertTriangle]
                ].map(([l, v, I]) => {
                  const Ic = I as typeof Lightbulb
                  return (
                    <div key={l as string} className="rounded-xl border border-line p-3">
                      <Ic className="size-4 text-brand" />
                      <p className="mt-2 text-xl font-semibold text-navy">{v as any}</p>
                      <p className="text-xs text-muted">{l as string}</p>
                    </div>
                  )
                })}
              </div>
              <p className="mb-2 mt-5 text-xs font-semibold uppercase tracking-wide text-slate-400">Sample findings</p>
              <ul className="divide-y divide-line rounded-xl border border-line">
                {all.slice(0, 5).map((x) => (
                  <li key={x.id} className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center">
                    <Badge tone="indigo" className="w-fit">{x.kind}</Badge>
                    <span className="flex-1 text-[13px] font-medium text-navy">{x.title}</span>
                    <Confidence value={x.confidence} compact />
                  </li>
                ))}
              </ul>
              {!!all.filter((x) => x.verification === 'conflicting').length && (
                <div className="mt-4">
                  <Callout tone="red" icon={AlertTriangle} title={`${all.filter((x) => x.verification === 'conflicting').length} findings have conflicting evidence`}>
                    These are flagged for the outgoing member to resolve first.
                  </Callout>
                </div>
              )}
            </>
          )}
          {step === 7 && (
            <>
              <h2 className="mt-1 text-lg font-semibold text-navy">Submit</h2>
              <p className="mt-1 text-sm text-muted">Choose the next stage for this handover.</p>
              <div className="mt-5 space-y-3">
                <div className={cn('rounded-xl border p-4', submitMode === 'verify' ? 'border-brand bg-tint/30' : 'border-line')}>
                  <Radio
                    checked={submitMode === 'verify'}
                    onChange={() => setSubmitMode('verify')}
                    label={<span className="font-medium">Send to {personById(out).name} for verification <Badge tone="blue" className="ml-1">Recommended</Badge></span>}
                    description="They review findings, answer gaps, then submit for your approval."
                  />
                </div>
                <div className={cn('rounded-xl border p-4', submitMode === 'approve' ? 'border-brand bg-tint/30' : 'border-line')}>
                  <Radio
                    checked={submitMode === 'approve'}
                    onChange={() => setSubmitMode('approve')}
                    label={<span className="font-medium">Submit directly for approval</span>}
                    description="Skip outgoing verification. Unverified findings stay clearly marked as unverified."
                  />
                </div>
              </div>
              <p className="mt-4 flex items-center gap-1.5 text-xs text-muted">
                <Lock className="size-3" />{personById(out).name} and approvers will be notified. Nothing is visible to {personById(inc).name} until you publish.
              </p>
            </>
          )}
          <div className="mt-8 flex justify-between border-t border-line pt-5">
            <Button
              variant="ghost"
              icon={ArrowLeft}
              onClick={() => (step ? go(step - 1) : router.push('/handovers'))}
              disabled={step === 5 && genPct > 0 && genPct < 100}
            >
              {step ? 'Back' : 'Cancel'}
            </Button>
            {step < 7 ? (
              <Button iconRight={ArrowRight} disabled={!valid} onClick={() => go(step + 1)}>
                {step === 4 ? 'Continue to generation' : 'Continue'}
              </Button>
            ) : (
              <Button icon={Send} onClick={submit}>
                {submitMode === 'verify' ? 'Send for verification' : 'Submit for approval'}
              </Button>
            )}
          </div>
        </Card>
      </div>
    </>
  )
}

/* ---------- 24. Handover layout + workspace ---------- */
export const H_TABS = ['overview', 'knowledge', 'responsibilities', 'decisions', 'tasks', 'risks', 'dependencies', 'evidence', 'review', 'report'] as const
export type HTab = (typeof H_TABS)[number]
const STAGE_LABELS = [['draft', 'Draft'], ['in_progress', 'Verification'], ['pending_review', 'Manager review'], ['approved', 'Approved'], ['published', 'Published'], ['completed', 'Acknowledged']] as const

export function HandoverLayout({
  id,
  tab,
  children
}: {
  id: string
  tab: HTab
  children: (h: Handover, role: ProjectRole) => ReactNode
}) {
  const s = useStore()
  const router = useRouter()
  const { handoverCases, refreshHandovers } = useLiveApp()
  const { h, project, role } = useHandover(id)
  const [dlg, setDlg] = useState<null | 'submit' | 'approve' | 'publish' | 'changes' | 'start'>(null)
  const [note, setNote] = useState('')

  if (!h || !project) return <HandoverNotFound />
  const st = handoverStats(h, s.verif)
  const idx = STAGE_LABELS.findIndex(([k]) => k === h.status)

  const notify = (title: string, body: string, link: string) =>
    s.setNotifications((ns) => [
      { id: `n${Date.now()}`, type: 'approval', title, body, time: 'Just now', read: false, link, group: 'Today' },
      ...ns
    ])

  const actions: ReactNode[] = []
  if (role === 'outgoing' && (h.status === 'in_progress' || h.status === 'draft')) {
    actions.push(<Button key="s" icon={Send} onClick={() => setDlg('submit')}>Submit for approval</Button>)
  }
  if (role === 'manager' && h.status === 'draft') {
    actions.push(<Button key="st" icon={Sparkles} onClick={() => setDlg('start')}>Start verification</Button>)
  }
  if (role === 'manager' && h.status === 'pending_review') {
    actions.push(
      <Button key="c" variant="secondary" icon={Undo2} onClick={() => setDlg('changes')}>Request changes</Button>,
      <Button key="a" variant="success" icon={ShieldCheck} onClick={() => setDlg('approve')}>Approve</Button>
    )
  }
  if (role === 'manager' && h.status === 'approved') {
    actions.push(
      <Button key="p" icon={Send} onClick={() => setDlg('publish')}>
        Publish to {personById(h.incomingId).name.split(' ')[0] ?? personById(h.incomingId).name}
      </Button>
    )
  }
  if (role === 'incoming' && (h.status === 'published' || h.status === 'completed')) {
    actions.push(
      <Button key="r" icon={BookOpen} onClick={() => router.push(`/handovers/${h.id}/recipient`)}>Open recipient view</Button>
    )
  }

  const tabs = H_TABS.filter((t) => role !== 'incoming' || t !== 'review')
  const counts: Partial<Record<HTab, number>> = {
    decisions: projectFindings(h.projectId).decisions.length,
    tasks: projectFindings(h.projectId).tasks.length,
    risks: projectFindings(h.projectId).risks.length,
    dependencies: projectFindings(h.projectId).dependencies.length,
    evidence: projectFindings(h.projectId).evidence.length
  }

  return (
    <>
      <div className="no-print">
        <Card className="mb-5 overflow-hidden">
          <div className="p-5 sm:p-6">
            <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs font-semibold text-muted">{h.code}</span>
                  <StatusBadge status={h.status} />
                  <Tooltip content="Your perspective on this handover, based on your role in the project.">
                    <span><RoleBadge role={role} /></span>
                  </Tooltip>
                </div>
                <h1 className="mt-2 text-[22px] font-semibold tracking-tight text-navy">{project.name}</h1>
                <p className="mt-0.5 text-[13px] text-muted">{h.scope}</p>
                <div className="mt-4 flex flex-wrap items-center gap-x-6 gap-y-3 text-[13px]">
                  <span className="flex items-center gap-2">
                    <Avatar id={h.outgoingId} size={28} />
                    <span>
                      <span className="block text-[11px] text-muted">Outgoing</span>
                      <span className="font-medium text-navy">{personById(h.outgoingId).name}</span>
                    </span>
                  </span>
                  <ArrowRight className="size-4 text-brand" />
                  <span className="flex items-center gap-2">
                    <Avatar id={h.incomingId} size={28} />
                    <span>
                      <span className="block text-[11px] text-muted">Incoming</span>
                      <span className="font-medium text-navy">{personById(h.incomingId).name}</span>
                    </span>
                  </span>
                  <span className="hidden h-8 w-px bg-line sm:block" />
                  <span>
                    <span className="block text-[11px] text-muted">Last updated</span>
                    <span className="font-medium text-navy">{h.updated}</span>
                  </span>
                  <span>
                    <span className="block text-[11px] text-muted">Due</span>
                    <span className="font-medium text-navy">{h.due}</span>
                  </span>
                </div>
              </div>
              <div className="flex shrink-0 flex-col items-start gap-3 lg:items-end">
                <div className="flex items-center gap-3">
                  <Ring value={h.progress} size={56} />
                  <div>
                    <p className="text-[11px] text-muted">Completion</p>
                    <p className="text-[13px] font-medium text-navy">{st.reviewed}/{st.all.length} reviewed</p>
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  {actions}
                  <Button variant="secondary" icon={FileText} onClick={() => router.push(`/handovers/${h.id}/report`)}>
                    Report
                  </Button>
                </div>
              </div>
            </div>
            <ol className="mt-6 grid grid-cols-6 gap-1.5">
              {STAGE_LABELS.map(([k, l], i) => (
                <li key={k}>
                  <div className={cn('h-1.5 rounded-full', i < idx ? 'bg-ok' : i === idx ? 'bg-brand' : 'bg-slate-200')} />
                  <p className={cn('mt-1.5 hidden text-[11px] font-medium sm:block', i === idx ? 'text-brand' : i < idx ? 'text-navy' : 'text-slate-400')}>
                    {l}
                  </p>
                </li>
              ))}
            </ol>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line bg-slate-50/60 px-5 py-2 text-xs text-muted">
            <span className="flex items-center gap-1.5"><Eye className="size-3.5" />Prototype: preview this handover as</span>
            <Segmented
              value={role}
              onChange={(v) => s.setPerspective((m) => ({ ...m, [h.id]: v }))}
              options={(['manager', 'outgoing', 'incoming'] as const).map((r) => ({
                id: r,
                label: ROLE_LABEL[r].replace(' Member', '').replace('Project ', '')
              }))}
            />
          </div>
        </Card>
        <Tabs
          className="mb-5"
          tabs={tabs.map((t) => ({ id: t, label: (t[0] ?? '').toUpperCase() + t.slice(1), count: counts[t] }))}
          value={tab}
          onChange={(t) =>
            router.push(
              t === 'review'
                ? `/handovers/${h.id}/review`
                : t === 'report'
                ? `/handovers/${h.id}/report`
                : t === 'overview'
                ? `/handovers/${h.id}`
                : `/handovers/${h.id}?tab=${t}`
            )
          }
        />
      </div>
      {children(h, role)}
      <ConfirmDialog
        open={dlg === 'submit'}
        onClose={() => setDlg(null)}
        title="Submit for manager approval?"
        confirmLabel="Submit"
        body={
          <>
            {st.all.length - st.reviewed > 0 ? (
              <span className="mb-2 block rounded-lg bg-amber-50 p-2.5 text-amber-800">
                {st.all.length - st.reviewed} findings are still unreviewed. They'll be marked “Needs review” in the report.
              </span>
            ) : null}
            Your manager will review the verified findings and your answers before publishing to {personById(h.incomingId).name}.
          </>
        }
        onConfirm={async () => {
          s.updateHandover(h.id, { status: 'pending_review', progress: Math.max(h.progress, 85), updated: 'Just now' })
          notify('Approval requested', `${h.code} submitted for review.`, `/handovers/${h.id}/review`)
          s.toast('Submitted for approval', 'Your manager has been notified.')
          setDlg(null)
          try {
            const liveC = (handoverCases || []).find((c) => c.id === h.id)
            if (liveC?.current_version_id) {
              await api.handover.submitSignoff(h.projectId, h.id, {
                version_id: liveC.current_version_id,
                signoff_type: 'departing_verification',
                decision: 'approved',
                comments: 'Submitted for manager review.'
              })
              await refreshHandovers()
            }
          } catch (err) {
            console.error('Signoff error:', err)
          }
        }}
      />
      <ConfirmDialog
        open={dlg === 'start'}
        onClose={() => setDlg(null)}
        title="Send for verification?"
        confirmLabel="Send"
        body={<>{personById(h.outgoingId).name} will be asked to verify the reconstructed findings.</>}
        onConfirm={() => {
          s.updateHandover(h.id, { status: 'in_progress', progress: 30, updated: 'Just now' })
          s.toast('Sent for verification')
          setDlg(null)
        }}
      />
      <ConfirmDialog
        open={dlg === 'approve'}
        onClose={() => setDlg(null)}
        title="Approve this handover?"
        confirmLabel="Approve"
        body={<>{st.verified} of {st.all.length} findings are verified. After approval you can publish the report to {personById(h.incomingId).name}.</>}
        onConfirm={async () => {
          s.updateHandover(h.id, { status: 'approved', progress: 100, updated: 'Just now' })
          s.toast('Handover approved', 'Ready to publish.')
          setDlg(null)
          try {
            const liveC = (handoverCases || []).find((c) => c.id === h.id)
            if (liveC?.current_version_id) {
              await api.handover.submitSignoff(h.projectId, h.id, {
                version_id: liveC.current_version_id,
                signoff_type: 'reviewer_approval',
                decision: 'approved',
                comments: 'Approved by project manager.'
              })
              await refreshHandovers()
            }
          } catch (err) {
            console.error('Approve error:', err)
          }
        }}
      />
      <ConfirmDialog
        open={dlg === 'publish'}
        onClose={() => setDlg(null)}
        title={`Publish to ${personById(h.incomingId).name}?`}
        confirmLabel="Publish"
        body={<>They'll get access to the report, verified knowledge, linked evidence and the AI assistant. You can update or revoke access at any time from Published Handovers.</>}
        onConfirm={async () => {
          const nowStr = new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
          s.updateHandover(h.id, { status: 'published', publishedOn: nowStr, access: 'Active', updated: 'Just now' })
          notify('Handover published', `${h.code} is now available to ${personById(h.incomingId).name}.`, '/handovers/published')
          s.toast('Handover published', `${personById(h.incomingId).name} has been notified.`)
          setDlg(null)
          try {
            const liveC = (handoverCases || []).find((c) => c.id === h.id)
            if (liveC?.current_version_id) {
              await api.handover.deliverPackage(h.projectId, h.id, {
                version_id: liveC.current_version_id,
                deliver_to_user_ids: [h.incomingId],
                delivery_method: 'in_app',
                message: `Handover package ${h.code} published.`
              })
              await refreshHandovers()
            }
          } catch (err) {
            console.error('Publish error:', err)
          }
        }}
      />
      <Modal
        open={dlg === 'changes'}
        onClose={() => setDlg(null)}
        title="Request changes"
        subtitle={`Return ${h.code} to ${personById(h.outgoingId).name}`}
        footer={
          <>
            <Button variant="secondary" onClick={() => setDlg(null)}>Cancel</Button>
            <Button
              disabled={!note.trim()}
              onClick={async () => {
                s.updateHandover(h.id, { status: 'in_progress', updated: 'Just now' })
                s.toast('Changes requested', personById(h.outgoingId).name + ' has been notified.', 'info')
                const currNote = note
                setDlg(null)
                setNote('')
                try {
                  const liveC = (handoverCases || []).find((c) => c.id === h.id)
                  if (liveC?.current_version_id) {
                    await api.handover.submitSignoff(h.projectId, h.id, {
                      version_id: liveC.current_version_id,
                      signoff_type: 'reviewer_approval',
                      decision: 'rejected',
                      comments: currNote
                    })
                    await refreshHandovers()
                  }
                } catch (err) {
                  console.error('Request changes error:', err)
                }
              }}
            >
              Send request
            </Button>
          </>
        }
      >
        <Field label="What needs to change?">
          <Textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="e.g. Please resolve the Kafka retention conflict and document the month-end step."
          />
        </Field>
      </Modal>
    </>
  )
}

function FindingList({ items, onOpen }: { items: AnyFinding[]; onOpen: (f: AnyFinding) => void }) {
  if (!items.length) {
    return (
      <Card>
        <EmptyState icon={Sparkles} title="Nothing here yet" body="No findings of this type were reconstructed for this handover." />
      </Card>
    )
  }
  return (
    <Card className="divide-y divide-line">
      {items.map((f) => (
        <button
          key={f.id}
          onClick={() => onOpen(f)}
          className="flex w-full flex-col gap-2 px-5 py-4 text-left hover:bg-slate-50 lg:flex-row lg:items-center"
        >
          <div className="min-w-0 flex-1">
            <p className="text-[13.5px] font-medium text-navy">{f.title}</p>
            <p className="mt-0.5 line-clamp-1 text-xs text-muted">{f.summary}</p>
          </div>
          <span className="flex items-center gap-2 text-xs text-muted">
            <Avatar id={f.ownerId} size={20} />
          </span>
          <FindingRowMeta f={f} />
        </button>
      ))}
    </Card>
  )
}

export function HandoverWorkspace({ id, initialTab }: { id: string; initialTab?: HTab }) {
  const s = useStore()
  const router = useRouter()
  const searchParams = useSearchParams()
  const queryTab = searchParams?.get('tab') as HTab | null
  const tab = initialTab || queryTab || 'overview'
  const [open, setOpen] = useState<AnyFinding>()
  const [checklists, setChecklists] = useState<any[]>([])
  const [isLoadingChecklists, setIsLoadingChecklists] = useState(false)
  const [updatingItemId, setUpdatingItemId] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    async function loadChecklists() {
      if (!id) return
      setIsLoadingChecklists(true)
      try {
        const targetCase = s.handovers.find((x) => x.id === id)
        const pId = targetCase?.projectId || 'ed33c53a-7678-4d5b-8212-64c233897142'
        const res = await api.handover.getChecklists(pId, id)
        if (active) {
          setChecklists(res || [])
        }
      } catch (err) {
        console.error('Failed to load checklists:', err)
      } finally {
        if (active) setIsLoadingChecklists(false)
      }
    }
    void loadChecklists()
    return () => {
      active = false
    }
  }, [id, s.handovers])

  const toggleItem = async (projectId: string, itemId: string, currentStatus: string) => {
    const nextStatus = currentStatus === 'completed' ? 'pending' : 'completed'
    setUpdatingItemId(itemId)
    setChecklists((prev) =>
      prev.map((chk: any) => ({
        ...chk,
        items: (chk.items || []).map((it: any) =>
          it.id === itemId ? { ...it, status: nextStatus } : it
        ),
      }))
    )
    try {
      await api.handover.updateChecklistItem(projectId, itemId, { status: nextStatus })
      s.toast('Checklist updated', `Marked as ${nextStatus}`)
    } catch (err: unknown) {
      console.error(err)
      s.toast('Update failed', 'Could not update checklist item', 'error')
      setChecklists((prev) =>
        prev.map((chk: any) => ({
          ...chk,
          items: (chk.items || []).map((it: any) =>
            it.id === itemId ? { ...it, status: currentStatus } : it
          ),
        }))
      )
    } finally {
      setUpdatingItemId(null)
    }
  }

  const handleGenerateChecklists = async (projectId: string) => {
    try {
      setIsLoadingChecklists(true)
      const res = await api.handover.generateChecklists(projectId, id)
      setChecklists(res || [])
      s.toast('Checklists created', 'Transition checklists generated successfully', 'success')
    } catch (err: unknown) {
      console.error(err)
      s.toast('Generation failed', 'Could not generate checklists', 'error')
    } finally {
      setIsLoadingChecklists(false)
    }
  }

  return (
    <HandoverLayout id={id} tab={tab}>
      {(h, role) => {
        const f = projectFindings(h.projectId)
        const all = allFindings(h.projectId)
        const st = handoverStats(h, s.verif)
        const resp = s.members.find((m) => m.projectId === h.projectId && m.personId === h.outgoingId)?.responsibilities ?? []
        const myTasks = f.tasks.filter((t) => t.ownerId === h.outgoingId)
        const project = s.allProjects.find((p) => p.id === h.projectId)!
        const pg = gaps.filter((g) => g.projectId === h.projectId)
        const nextActions =
          role === 'manager'
            ? [
                h.status === 'pending_review'
                  ? 'Review verification decisions and approve'
                  : h.status === 'approved'
                  ? 'Publish the report to the incoming member'
                  : 'Monitor verification progress',
                'Resolve conflicting evidence before approval',
                'Confirm the incoming member has repository and on-call access'
              ]
            : role === 'outgoing'
            ? [
                `Verify ${all.length - st.reviewed} remaining findings`,
                `Answer ${pg.filter((g) => !s.gapAnswers[g.id]).length} knowledge gaps`,
                'Submit for approval'
              ]
            : [
                'Read the project introduction and architecture',
                `Pick up “${f.tasks.find((t) => t.status !== 'Done')?.title ?? 'open tasks'}”`,
                'Ask the assistant about anything unclear'
              ]

        let body: ReactNode = null
        if (tab === 'overview') {
          body = (
            <div className="grid gap-5 lg:grid-cols-3">
              <Card className="p-5 lg:col-span-2">
                <p className="text-[15px] font-semibold text-navy">Project summary</p>
                <p className="mt-2 text-[13.5px] leading-relaxed text-slate-700">
                  {project?.description} {personById(h.outgoingId).name} has been responsible for {resp.join(', ').toLowerCase() || 'core project work'}. This handover transfers those responsibilities to {personById(h.incomingId).name}.
                </p>
                <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
                  {[
                    ['Decisions', f.decisions.length],
                    ['Pending work', f.tasks.filter((t) => t.status !== 'Done').length],
                    ['Open risks', f.risks.filter((r) => r.resolution !== 'Resolved').length],
                    ['Dependencies', f.dependencies.length]
                  ].map(([l, v]) => (
                    <div key={l as string} className="rounded-xl bg-slate-50 p-3">
                      <p className="text-xl font-semibold text-navy">{v}</p>
                      <p className="text-xs text-muted">{l}</p>
                    </div>
                  ))}
                </div>
              </Card>
              <Card className="p-5">
                <p className="text-[15px] font-semibold text-navy">Knowledge completeness</p>
                <div className="mt-4 flex items-center gap-4">
                  <Ring value={st.completeness} size={76} color="#299B80" />
                  <div className="text-[13px]">
                    <p><span className="font-semibold text-navy">{st.verified}</span> <span className="text-muted">verified</span></p>
                    <p><span className="font-semibold text-navy">{st.reviewed - st.verified}</span> <span className="text-muted">rejected / flagged</span></p>
                    <p><span className="font-semibold text-navy">{st.all.length - st.reviewed}</span> <span className="text-muted">awaiting review</span></p>
                  </div>
                </div>
                <p className="mt-4 text-xs text-muted">Completeness counts only human-verified findings, not AI confidence.</p>
              </Card>
              <Card>
                <CardHeader title="Important responsibilities" icon={UserRoundCog} />
                <ul className="space-y-2 px-5 pb-5">
                  {resp.map((r) => (
                    <li key={r} className="flex items-center gap-2 text-[13px] text-navy">
                      <CheckCircle2 className="size-4 text-ok" />{r}
                    </li>
                  ))}
                  {!resp.length && <li className="text-[13px] text-muted">None recorded.</li>}
                </ul>
              </Card>
              <Card>
                <CardHeader title="Pending work" icon={ListTodo} />
                <ul className="space-y-2.5 px-5 pb-5">
                  {f.tasks.filter((t) => t.status !== 'Done').slice(0, 4).map((t) => (
                    <li key={t.id} className="flex items-center gap-2">
                      <span className="flex-1 truncate text-[13px] text-navy">{t.title}</span>
                      <TaskStatus status={t.status} />
                    </li>
                  ))}
                </ul>
              </Card>
              <Card>
                <CardHeader title="Recommended next actions" icon={Sparkles} />
                <ol className="space-y-2.5 px-5 pb-5">
                  {nextActions.map((a, i) => (
                    <li key={a} className="flex items-start gap-2.5 text-[13px] text-navy">
                      <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-tint text-[11px] font-semibold text-brand">
                        {i + 1}
                      </span>
                      {a}
                    </li>
                  ))}
                </ol>
              </Card>
              <Card className="lg:col-span-2">
                <CardHeader
                  title="Important decisions"
                  icon={Lightbulb}
                  action={
                    <button className="text-[13px] font-medium text-brand" onClick={() => router.push(`/handovers/${h.id}?tab=decisions`)}>
                      All
                    </button>
                  }
                />
                <ul className="divide-y divide-line px-5 pb-3">
                  {f.decisions.slice(0, 3).map((d) => (
                    <li key={d.id}>
                      <button
                        onClick={() => setOpen({ ...d, kind: 'Decision' })}
                        className="flex w-full flex-col gap-2 py-3 text-left sm:flex-row sm:items-center"
                      >
                        <span className="flex-1 text-[13px] font-medium text-navy">{d.title}</span>
                        <VerificationBadge status={s.verif[d.id] ?? d.verification} />
                      </button>
                    </li>
                  ))}
                </ul>
              </Card>
              <Card>
                <CardHeader title="Unresolved risks" icon={AlertTriangle} />
                <ul className="space-y-2.5 px-5 pb-5">
                  {f.risks.filter((r) => r.resolution !== 'Resolved').slice(0, 3).map((r) => (
                    <li key={r.id} className="flex items-start gap-2">
                      <SeverityBadge level={r.severity} />
                      <span className="text-[13px] text-navy">{r.title}</span>
                    </li>
                  ))}
                </ul>
              </Card>
              <Card className="lg:col-span-3">
                <CardHeader title="Dependencies" icon={Network} />
                <div className="grid gap-2 px-5 pb-5 sm:grid-cols-2 lg:grid-cols-3">
                  {f.dependencies.map((d) => (
                    <div
                      key={d.id}
                      className={cn('rounded-xl border p-3', d.blocking ? 'border-red-200 bg-red-50/30' : 'border-line')}
                    >
                      <p className="text-[13px] font-medium text-navy">{d.from} → {d.to}</p>
                      <p className="mt-1 flex items-center gap-1.5 text-xs text-muted">
                        <Badge tone={d.depType === 'External' ? 'amber' : d.depType === 'Task' ? 'green' : 'blue'}>
                          {d.depType}
                        </Badge>
                        {d.blocking && <Badge tone="red" icon={Ban}>Blocking</Badge>}
                      </p>
                    </div>
                  ))}
                </div>
              </Card>
              <Card className="lg:col-span-3">
                <div className="flex flex-col gap-3 p-5 sm:flex-row sm:items-center sm:justify-between border-b border-line">
                  <div>
                    <div className="flex items-center gap-2">
                      <ListTodo className="size-5 text-brand" />
                      <h3 className="text-[15px] font-semibold text-navy">Transition Checklists & Offboarding Verification</h3>
                    </div>
                    <p className="mt-0.5 text-xs text-muted">
                      Multi-phase checklists required for responsible knowledge transfer and access revocation.
                    </p>
                  </div>
                  {!checklists.length && (
                    <Button
                      size="sm"
                      icon={Sparkles}
                      disabled={isLoadingChecklists}
                      onClick={() => handleGenerateChecklists(h.projectId)}
                    >
                      {isLoadingChecklists ? 'Generating...' : 'Generate checklists'}
                    </Button>
                  )}
                </div>
                <div className="p-5">
                  {isLoadingChecklists ? (
                    <div className="py-6 text-center text-xs text-muted">Loading transition checklists...</div>
                  ) : !checklists.length ? (
                    <EmptyState
                      icon={ListTodo}
                      title="No transition checklists generated yet"
                      body="Generate standard offboarding, knowledge walkthrough, and access revocation tasks for this handover case."
                      action={
                        <Button icon={Sparkles} onClick={() => handleGenerateChecklists(h.projectId)}>
                          Generate transition checklists
                        </Button>
                      }
                    />
                  ) : (
                    <div className="grid gap-6 md:grid-cols-3">
                      {checklists.map((chk: any) => {
                        const items = chk.items || []
                        const completedCount = items.filter((i: any) => i.status === 'completed').length
                        const typeLabel = (chk.checklist_type || 'Checklist')
                          .replace(/_/g, ' ')
                          .replace(/\b\w/g, (c: string) => c.toUpperCase())
                        return (
                          <div key={chk.id} className="flex flex-col rounded-xl border border-line bg-slate-50/50 p-4">
                            <div className="flex items-center justify-between pb-3 border-b border-line">
                              <span className="text-[13px] font-semibold text-navy">{typeLabel}</span>
                              <span className="text-xs font-medium text-muted">{completedCount}/{items.length}</span>
                            </div>
                            <ul className="mt-3 space-y-2.5 flex-1">
                              {items.map((item: any) => {
                                const isDone = item.status === 'completed'
                                const isUpdating = updatingItemId === item.id
                                return (
                                  <li key={item.id} className="flex items-start gap-2.5 text-xs">
                                    <input
                                      type="checkbox"
                                      checked={isDone}
                                      disabled={isUpdating}
                                      onChange={() => toggleItem(h.projectId, item.id, item.status)}
                                      className="mt-0.5 size-4 rounded border-slate-300 text-brand focus:ring-brand cursor-pointer"
                                    />
                                    <div className="flex-1 min-w-0">
                                      <span className={cn('leading-relaxed', isDone ? 'text-slate-400 line-through' : 'text-slate-800 font-medium')}>
                                        {item.item_text || item.title}
                                      </span>
                                      {item.blocking && (
                                        <span className="ml-1.5 inline-block text-[10px] font-medium text-red-600 bg-red-50 border border-red-200 rounded px-1">
                                          blocking
                                        </span>
                                      )}
                                    </div>
                                  </li>
                                )
                              })}
                            </ul>
                          </div>
                        )
                      })}
                    </div>
                  )}
                </div>
              </Card>
            </div>
          )
        }
        if (tab === 'knowledge') {
          body = (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {[
                ['Decisions', f.decisions.length, Lightbulb, 'decisions'],
                ['Tasks', f.tasks.length, ListTodo, 'tasks'],
                ['Risks', f.risks.length, AlertTriangle, 'risks'],
                ['Dependencies', f.dependencies.length, Network, 'dependencies']
              ].map(([l, v, I, t]) => {
                const Ic = I as typeof Lightbulb
                return (
                  <button
                    key={l as string}
                    onClick={() => router.push(`/handovers/${h.id}?tab=${t}`)}
                    className="tile rounded-[14px] border p-5 text-left"
                  >
                    <Ic className="size-5 text-brand" />
                    <p className="mt-3 text-2xl font-semibold text-navy">{v as number}</p>
                    <p className="text-[13px] text-muted">{l as string}</p>
                  </button>
                )
              })}
              <Card className="sm:col-span-2 lg:col-span-4">
                <EmptyState
                  icon={Network}
                  title="Explore relationships in the Knowledge Explorer"
                  body="See how decisions, tasks, risks, people and components connect, with supporting evidence."
                  action={
                    <Button icon={Network} onClick={() => router.push(`/projects/${h.projectId}/knowledge`)}>
                      Open Knowledge Explorer
                    </Button>
                  }
                />
              </Card>
            </div>
          )
        }
        if (tab === 'responsibilities') {
          body = (
            <div className="grid gap-5 lg:grid-cols-2">
              <Card>
                <CardHeader
                  title={`${personById(h.outgoingId).name}'s responsibilities`}
                  subtitle="Transferring to the incoming member"
                  icon={UserRoundCog}
                />
                <ul className="space-y-2 px-5 pb-5">
                  {resp.map((r) => (
                    <li key={r} className="flex items-center gap-3 rounded-xl border border-line p-3">
                      <Avatar id={h.outgoingId} size={24} />
                      <span className="flex-1 text-[13px] font-medium text-navy">{r}</span>
                      <ArrowRight className="size-3.5 text-brand" />
                      <Avatar id={h.incomingId} size={24} />
                    </li>
                  ))}
                </ul>
              </Card>
              <Card>
                <CardHeader title="Owned tasks" icon={ListTodo} />
                <ul className="divide-y divide-line px-5 pb-3">
                  {myTasks.map((t) => (
                    <li key={t.id} className="flex items-center gap-2 py-3">
                      <span className="flex-1 text-[13px] text-navy">{t.title}</span>
                      <TaskStatus status={t.status} />
                    </li>
                  ))}
                  {!myTasks.length && <li className="py-3 text-[13px] text-muted">No tasks owned.</li>}
                </ul>
              </Card>
            </div>
          )
        }
        if (tab === 'decisions') {
          body = <FindingList items={f.decisions.map((x) => ({ ...x, kind: 'Decision' as const }))} onOpen={setOpen} />
        }
        if (tab === 'tasks') {
          body = <FindingList items={f.tasks.map((x) => ({ ...x, kind: 'Task' as const }))} onOpen={setOpen} />
        }
        if (tab === 'risks') {
          body = <FindingList items={f.risks.map((x) => ({ ...x, kind: 'Risk' as const }))} onOpen={setOpen} />
        }
        if (tab === 'dependencies') {
          body = <FindingList items={f.dependencies.map((x) => ({ ...x, kind: 'Dependency' as const }))} onOpen={setOpen} />
        }
        if (tab === 'evidence') {
          body = (
            <Card className="overflow-hidden">
              <Table>
                <thead>
                  <tr>
                    <Th>Evidence</Th>
                    <Th>Author</Th>
                    <Th>Date</Th>
                    <Th>Used by</Th>
                    <Th>Verification</Th>
                  </tr>
                </thead>
                <tbody>
                  {f.evidence.map((e) => (
                    <tr
                      key={e.id}
                      className="cursor-pointer hover:bg-slate-50/70"
                      onClick={() => router.push(`/projects/${h.projectId}/evidence/${e.id}`)}
                    >
                      <Td>
                        <span className="flex items-center gap-3">
                          <EvidenceTypeIcon type={e.type} />
                          <span>
                            <span className="block font-medium text-navy">{e.title}</span>
                            <span className="text-xs text-muted">{EVIDENCE_TYPE_LABEL[e.type]} · {e.ref}</span>
                          </span>
                        </span>
                      </Td>
                      <Td className="text-[13px]">{personById(e.authorId).name}</Td>
                      <Td className="text-[13px] text-muted">{(e.date.split(' ')[0] ?? e.date)}</Td>
                      <Td className="text-[13px]">{all.filter((x) => x.evidenceIds.includes(e.id)).length} findings</Td>
                      <Td><VerificationBadge status={e.verification} /></Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </Card>
          )
        }
        return (
          <>
            {body}
            <FindingDrawer finding={open} onClose={() => setOpen(undefined)} />
          </>
        )
      }}
    </HandoverLayout>
  )
}

/* ---------- 27. Published ---------- */
export function PublishedHandovers() {
  const s = useStore()
  const router = useRouter()
  const { handoverCases, projects, user, refreshHandovers } = useLiveApp()
  const [edit, setEdit] = useState<Handover | null>(null)
  const [revoke, setRevoke] = useState<Handover | null>(null)
  const [expiry, setExpiry] = useState('none')

  const liveHandovers = useMemo(() => {
    return (handoverCases || []).map((c) => {
      const pName = projects.find((p) => p.id === c.project_id)?.name || 'Skillpassport'
      return mapCaseToHandover(c, pName)
    })
  }, [handoverCases, projects])

  const allH = useMemo(() => {
    const map = new Map<string, Handover>()
    s.handovers.forEach((h) => map.set(h.id, h))
    liveHandovers.forEach((h) => map.set(h.id, h))
    return Array.from(map.values())
  }, [s.handovers, liveHandovers])

  const list = allH.filter((h) => ['published', 'completed', 'delivered', 'acknowledged'].includes(h.status))

  return (
    <>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between pb-5">
        <PageHeader
          title="Published Handovers"
          subtitle="Control who can access published knowledge and track acknowledgement."
        />
        <Button icon={Plus} onClick={() => router.push('/handovers/new')}>
          Create handover
        </Button>
      </div>
      <Card className="overflow-hidden">
        {!list.length ? (
          <div className="p-8 text-center">
            <EmptyState
              icon={Send}
              title="Nothing published yet"
              body="Approved handovers you publish to incoming members appear here."
            />
            <div className="mt-4 flex justify-center gap-3">
              <Button variant="secondary" onClick={() => router.push('/handovers')}>
                Go to Handover Workspace
              </Button>
              <Button icon={Plus} onClick={() => router.push('/handovers/new')}>
                Create new handover
              </Button>
            </div>
          </div>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Handover</Th>
                <Th>Project</Th>
                <Th>Recipient</Th>
                <Th>Published</Th>
                <Th>Access</Th>
                <Th>Acknowledgement</Th>
                <Th className="text-right">Actions</Th>
              </tr>
            </thead>
            <tbody>
              {list.map((h) => {
                const manager = s.projectRole(h.projectId) === 'manager'
                return (
                  <tr key={h.id} className="hover:bg-slate-50/50">
                    <Td>
                      <Link to={`/handovers/${h.id}/report`} className="font-medium text-navy hover:text-brand">
                        {h.code}
                      </Link>
                      <p className="text-xs text-muted">from {personById(h.outgoingId).name}</p>
                    </Td>
                    <Td className="text-[13px]">{s.allProjects.find((p) => p.id === h.projectId)?.name}</Td>
                    <Td>
                      <span className="flex items-center gap-2 whitespace-nowrap text-[13px]">
                        <Avatar id={h.incomingId} size={24} />
                        {personById(h.incomingId).name}
                      </span>
                    </Td>
                    <Td className="whitespace-nowrap text-[13px] text-muted">{h.publishedOn}</Td>
                    <Td>
                      <Badge tone={h.access === 'Revoked' ? 'red' : h.access?.startsWith('Expires') ? 'amber' : 'green'} dot>
                        {h.access ?? 'Active'}
                      </Badge>
                    </Td>
                    <Td>
                      {h.status === 'completed' ? (
                        <Badge tone="green" icon={CheckCircle2}>Acknowledged {h.acknowledgedOn}</Badge>
                      ) : (
                        <Badge tone="amber" icon={Clock}>Pending</Badge>
                      )}
                    </Td>
                    <Td className="text-right">
                      <div className="flex justify-end gap-1.5">
                        {manager ? (
                          <>
                            <Button size="sm" variant="secondary" icon={KeyRound} onClick={() => setEdit(h)}>
                              Update access
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              className="text-red-600"
                              disabled={h.access === 'Revoked'}
                              onClick={() => setRevoke(h)}
                            >
                              Revoke
                            </Button>
                          </>
                        ) : (
                          <span className="text-xs text-muted">
                            <Lock className="mr-1 inline size-3" />Manager only
                          </span>
                        )}
                      </div>
                    </Td>
                  </tr>
                )
              })}
            </tbody>
          </Table>
        )}
      </Card>
      <Modal
        open={!!edit}
        onClose={() => setEdit(null)}
        title="Update access"
        subtitle={edit ? `${edit.code} · ${personById(edit.incomingId).name}` : ''}
        footer={
          <>
            <Button variant="secondary" onClick={() => setEdit(null)}>Cancel</Button>
            <Button
              onClick={() => {
                if (edit) s.updateHandover(edit.id, { access: expiry === 'none' ? 'Active' : 'Expires Jul 31' })
                s.toast('Access updated')
                setEdit(null)
              }}
            >
              Save
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <div className="space-y-3">
            <Radio
              checked={expiry === 'none'}
              onChange={() => setExpiry('none')}
              label="No expiry"
              description="Recipient keeps access while they're on the project."
            />
            <Radio
              checked={expiry === 'jul'}
              onChange={() => setExpiry('jul')}
              label="Expire on Jul 31, 2025"
              description="Access is removed automatically."
            />
          </div>
          <div className="space-y-2 rounded-xl border border-line p-4">
            <p className="text-[13px] font-medium text-navy">Recipient can access</p>
            <Checkbox checked onChange={() => {}} label="Handover report" />
            <Checkbox checked onChange={() => {}} label="Linked evidence" />
            <Checkbox checked onChange={() => {}} label="AI assistant" />
          </div>
        </div>
      </Modal>
      <ConfirmDialog
        open={!!revoke}
        onClose={() => setRevoke(null)}
        tone="danger"
        title="Revoke access?"
        confirmLabel="Revoke access"
        body={
          revoke && (
            <>
              {personById(revoke.incomingId).name} will immediately lose access to {revoke.code}, including the assistant. This is recorded in the audit log.
            </>
          )
        }
        onConfirm={() => {
          if (revoke) s.updateHandover(revoke.id, { access: 'Revoked' })
          s.toast('Access revoked', undefined, 'info')
          setRevoke(null)
        }}
      />
    </>
  )
}

/* ---------- 28. Received ---------- */
export function ReceivedHandovers() {
  const s = useStore()
  const router = useRouter()
  const { handoverCases, projects, user } = useLiveApp()

  const liveHandovers = useMemo(() => {
    return (handoverCases || []).map((c) => {
      const pName = projects.find((p) => p.id === c.project_id)?.name || 'Skillpassport'
      return mapCaseToHandover(c, pName)
    })
  }, [handoverCases, projects])

  const allH = useMemo(() => {
    const map = new Map<string, Handover>()
    s.handovers.forEach((h) => map.set(h.id, h))
    liveHandovers.forEach((h) => map.set(h.id, h))
    return Array.from(map.values())
  }, [s.handovers, liveHandovers])

  const currentUserId = user?.id || ME
  const list = allH.filter(
    (h) => (h.incomingId === currentUserId || h.incomingId === ME) &&
           ['published', 'completed', 'delivered', 'acknowledged'].includes(h.status as string)
  )
  const pending = list.filter((h) => (h.status as string) === 'published' || (h.status as string) === 'delivered')

  return (
    <>
      <PageHeader
        title="Received Handovers"
        subtitle="Knowledge transferred to you. Start with anything awaiting acknowledgement."
      />
      {!list.length ? (
        <Card>
          <EmptyState
            icon={Inbox}
            title="Your inbox is empty"
            body="When someone publishes a handover to you, it appears here with everything you need to get started."
          />
        </Card>
      ) : (
        <>
          {!!pending.length && (
            <div className="mb-5">
              <Callout tone="blue" icon={Inbox} title={`${pending.length} handover${pending.length > 1 ? 's' : ''} awaiting your acknowledgement`}>
                Review the knowledge, ask questions, then acknowledge so the outgoing member and manager know you're ready.
              </Callout>
            </div>
          )}
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {list.map((h) => {
              const p = s.allProjects.find((x) => x.id === h.projectId)!
              const f = projectFindings(h.projectId)
              return (
                <Card key={h.id} interactive className={cn('flex flex-col overflow-hidden', h.status === 'published' && 'ring-2 ring-brand/20')}>
                  <div className="h-1.5" style={{ background: p.color }} />
                  <div className="flex flex-1 flex-col p-5">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-medium text-muted">{h.code}</span>
                      {h.status === 'published' ? (
                        <Badge tone="amber" icon={Clock}>Pending acknowledgement</Badge>
                      ) : (
                        <Badge tone="green" icon={CheckCircle2}>Acknowledged</Badge>
                      )}
                    </div>
                    <h3 className="mt-3 text-base font-semibold text-navy">{p.name}</h3>
                    <p className="mt-0.5 text-[13px] text-muted">{h.scope}</p>
                    <div className="mt-4 flex items-center gap-2.5 text-[13px]">
                      <Avatar id={h.outgoingId} size={28} />
                      <div>
                        <p className="font-medium text-navy">{personById(h.outgoingId).name}</p>
                        <p className="text-xs text-muted">Published {h.publishedOn}</p>
                      </div>
                    </div>
                    <div className="mt-4 grid grid-cols-3 gap-2 text-center">
                      {[
                        ['Decisions', f.decisions.length],
                        ['Tasks', f.tasks.length],
                        ['Risks', f.risks.length]
                      ].map(([l, v]) => (
                        <div key={l as string} className="rounded-lg bg-slate-50 py-2">
                          <p className="text-sm font-semibold text-navy">{v}</p>
                          <p className="text-[11px] text-muted">{l}</p>
                        </div>
                      ))}
                    </div>
                    <div className="mt-4">
                      <div className="mb-1 flex justify-between text-xs">
                        <span className="text-muted">Completion</span>
                        <span className="font-medium text-navy">{h.status === 'completed' ? 100 : 40}%</span>
                      </div>
                      <Progress value={h.status === 'completed' ? 100 : 40} size="sm" tone={h.status === 'completed' ? 'green' : 'blue'} />
                    </div>
                    <div className="mt-5 flex gap-2">
                      <Button className="flex-1" iconRight={ArrowRight} onClick={() => router.push(`/handovers/${h.id}/recipient`)}>
                        Open handover
                      </Button>
                      <Button
                        variant="secondary"
                        icon={MessageSquareText}
                        onClick={() => router.push(`/handovers/${h.id}/assistant`)}
                        aria-label="Ask assistant"
                      />
                    </div>
                  </div>
                </Card>
              )
            })}
          </div>
        </>
      )}
    </>
  )
}

/* ---------- Top-level HandoversPage component ---------- */
export interface HandoversPageProps {
  view?: 'list' | 'new' | 'published' | 'received' | 'project' | 'workspace' | 'generated'
  projectId?: string
}

function HandoversPageInner({ view = 'list', projectId }: HandoversPageProps) {
  const params = useParams()
  const s = useStore()
  const pId = projectId || (params?.id as string)

  switch (view) {
    case 'new':
      return <CreateHandover defaultProjectId={pId} />
    case 'published':
    case 'generated':
      return <PublishedHandovers />
    case 'received':
      return <ReceivedHandovers />
    case 'project':
      return <AllHandovers defaultProjectId={pId} />
    case 'workspace': {
      const targetId = s.handovers.find((h) => !pId || h.projectId === pId)?.id ?? s.handovers[0]?.id ?? ''
      if (targetId) {
        return <HandoverWorkspace id={targetId} />
      }
      return <AllHandovers defaultProjectId={pId} />
    }
    case 'list':
    default:
      return <AllHandovers defaultProjectId={pId} />
  }
}

export function HandoversPage(props: HandoversPageProps) {
  return (
    <Suspense fallback={<div className="p-8 text-center text-sm text-muted">Loading handovers…</div>}>
      <HandoversPageInner {...props} />
    </Suspense>
  )
}

export default HandoversPage
