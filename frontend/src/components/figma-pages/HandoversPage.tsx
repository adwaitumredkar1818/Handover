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
import type {
  HandoverPackageVersionSummary,
  HandoverReadinessIntelligenceResponse,
  HandoverVersionSectionsResponse,
} from '../../lib/types'
import {
  CanonicalEvidenceTable,
  CanonicalSectionPanel,
  TAB_TO_SECTION_TYPE,
} from '../handover/CanonicalSectionView'
import { ReadinessIntelligencePanel } from '../handover/ReadinessIntelligencePanel'
import { TransitionChecklistsPanel } from '../handover/TransitionChecklistsPanel'
import { ResponsibilityTransferPanel } from '../handover/ResponsibilityTransferPanel'
import { SignoffApprovalPanel } from '../handover/SignoffApprovalPanel'

export const isUUID = (val?: string | null): boolean =>
  Boolean(val && /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(val))

export function getMemberDisplayName(
  id?: string | null,
  members?: Array<any>,
  currentUser?: { id?: string; full_name?: string | null; email?: string } | null
): string {
  if (!id) return 'Unassigned'
  if (currentUser && currentUser.id === id) {
    return currentUser.full_name || currentUser.email?.split('@')[0] || 'Current User'
  }
  if (members && members.length > 0) {
    const m = members.find((x) => x.user_id === id || x.id === id)
    if (m) {
      return m.full_name || (m.email ? m.email.split('@')[0] : 'Project Member')
    }
  }
  const p = personById(id)
  if (p && p.id === id && p.name !== 'Maya Chen' && p.name !== 'Project Member') {
    return p.name
  }
  if (isUUID(id)) {
    return 'Project Member'
  }
  return p?.name || 'Project Member'
}

export function getMemberDisplayRole(
  id?: string | null,
  members?: Array<any>,
  currentUser?: { id?: string; role?: string; roles?: string[] } | null
): string {
  if (!id) return 'None'
  if (currentUser && currentUser.id === id) {
    return currentUser.role || currentUser.roles?.[0] || 'Project Member'
  }
  if (members && members.length > 0) {
    const m = members.find((x) => x.user_id === id || x.id === id)
    if (m) {
      return m.role_name || m.transition_role || 'Project Member'
    }
  }
  const p = personById(id)
  return p?.title || 'Project Member'
}

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
    outgoingId: hc.departing_member_id || '',
    incomingId: hc.successor_id || '',
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
  const [fetchedCase, setFetchedCase] = useState<any>(null)

  useEffect(() => {
    let active = true
    if (isUUID(id) && activeProject?.id && !handoverCases.some((c) => c.id === id)) {
      api.handover.getCase(activeProject.id, id)
        .then((data) => {
          if (active) setFetchedCase(data)
        })
        .catch((err) => console.warn('Could not fetch handover case:', err))
    }
    return () => { active = false }
  }, [id, activeProject?.id, handoverCases])

  let h: Handover | undefined = undefined
  if (handoverCases.length > 0) {
    const foundCase = handoverCases.find((c) => c.id === id)
    if (foundCase) {
      h = mapCaseToHandover(foundCase, activeProject?.id || '')
    }
  }
  if (!h && fetchedCase) {
    h = mapCaseToHandover(fetchedCase, activeProject?.id || '')
  }
  if (!h && !isUUID(id)) {
    h = s.handovers.find((x) => x.id === id)
  }

  const project =
    (h && projects.find((p) => p.id === h.projectId)) ||
    (activeProject?.id === h?.projectId ? activeProject : null) ||
    activeProject ||
    (h && s.allProjects.find((p) => p.id === h.projectId)) ||
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
  const { activeProject, projects, user, members, handoverCases, refreshHandovers, isLoadingHandovers } = useLiveApp()
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
    const liveItems = (handoverCases || []).map((hc) => mapCaseToHandover(hc, activeProject?.id || ''))
    s.setHandovers(liveItems)
  }, [handoverCases, activeProject?.id])

  const allHandoversList = useMemo(() => {
    return (handoverCases || []).map((hc) => mapCaseToHandover(hc, activeProject?.id || ''))
  }, [handoverCases, activeProject?.id])

  const list = allHandoversList.filter((h) => {
    const outName = getMemberDisplayName(h.outgoingId, members, user)
    const incName = getMemberDisplayName(h.incomingId, members, user)
    return (
      (f === 'all' || h.status === f) &&
      (proj === 'all' || h.projectId === proj) &&
      `${h.code} ${outName} ${incName} ${h.scope}`.toLowerCase().includes(q.toLowerCase())
    )
  })
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
            {(projects.length ? projects : (activeProject ? [activeProject] : [])).map((p) => (
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
        {isLoadingHandovers && allHandoversList.length === 0 ? (
          <div className="flex items-center justify-center gap-2 py-12 text-sm text-muted">
            <Loader2 className="size-4 animate-spin text-brand" />
            <span>Loading handovers…</span>
          </div>
        ) : view === 'table' ? (
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
  const { projects, activeProject, members, user } = useLiveApp()
  const p = projects.find((x) => x.id === h.projectId) || (activeProject?.id === h.projectId ? activeProject : s.allProjects.find((x) => x.id === h.projectId))
  const outName = getMemberDisplayName(h.outgoingId, members, user)
  const incName = getMemberDisplayName(h.incomingId, members, user)
  return (
    <Card interactive className="flex flex-col p-5">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-muted">{h.code}</span>
        <StatusBadge status={h.status} />
      </div>
      <Link to={`/handovers/${h.id}`} className="mt-2 text-[15px] font-semibold text-navy hover:text-brand">
        {p?.name || activeProject?.name || 'Project'}
      </Link>
      <p className="mt-0.5 line-clamp-1 text-[13px] text-muted">{h.scope}</p>
      <div className="mt-4 flex items-center gap-2">
        <Avatar id={h.outgoingId} name={outName} size={28} />
        <div className="h-px flex-1 border-t border-dashed border-slate-300" />
        <ArrowRight className="size-3.5 text-brand" />
        <div className="h-px flex-1 border-t border-dashed border-slate-300" />
        <Avatar id={h.incomingId} name={incName} size={28} />
      </div>
      <div className="mt-1 flex justify-between text-xs text-muted">
        <span>{outName}</span>
        <span>{incName}</span>
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

  const availableProjects = projects.length > 0 ? projects : (activeProject ? [activeProject] : [])
  const [step, setStep] = useState(0)
  const [maxStep, setMaxStep] = useState(0)
  const [pid, setPid] = useState(
    projectParam && availableProjects.some((p) => p.id === projectParam)
      ? projectParam
      : activeProject?.id || availableProjects[0]?.id || ''
  )

  useEffect(() => {
    if (activeProject?.id && (!pid || !isUUID(pid) || pid === 'northwind')) {
      setPid(activeProject.id)
    }
  }, [activeProject?.id, pid])

  const projectMembers = useMemo(() => {
    if (liveMembers && liveMembers.length > 0) {
      return liveMembers.map((m) => ({
        personId: m.user_id || m.id,
        name: m.full_name || (m.email ? m.email.split('@')[0] : 'Member'),
        role: m.role_name || 'member',
        email: m.email || '',
      }))
    }
    if (user) {
      return [{
        personId: user.id,
        name: user.full_name || (user.email ? user.email.split('@')[0] : 'Member'),
        role: user.roles?.[0] || 'project_manager',
        email: user.email || '',
      }]
    }
    return []
  }, [liveMembers, user])

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
    return []
  }, [sourceMappings])

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
      const userMember = projectMembers.find((m) => m.personId === user?.id)
      const departing = userMember || projectMembers[0]
      if (departing && !out) {
        setOut(departing.personId)
      }
      if (!inc && projectMembers.length > 1) {
        const other = projectMembers.find((m) => m.personId !== departing?.personId)
        if (other) setInc(other.personId)
      }
    }
    setSrcSel(projectSources.filter((x) => x.status !== 'error').map((x) => x.id))
  }, [pid, projectMembers, projectSources, user?.id, out])

  const startReconstruction = async () => {
    setIsGenerating(true)
    setGenPct(15)
    try {
      const targetPid = isUUID(pid) ? pid : activeProject?.id
      if (!targetPid || !isUUID(targetPid)) {
        throw new Error('Please select a valid project workspace.')
      }
      const targetOut = isUUID(out) ? out : user?.id
      if (!targetOut || !isUUID(targetOut)) {
        throw new Error('Please select a valid departing team member.')
      }
      const targetInc = isUUID(inc) ? inc : (inc === out ? targetOut : undefined)

      // 1. Create Case in PostgreSQL
      const caseRes = await api.handover.createCase(targetPid, {
        title: `Handover: ${project?.name || activeProject?.name || 'Skill Passport'} Transfer`,
        description: scope.notes || 'Knowledge reconstruction for departing team member',
        departing_member_id: targetOut,
        successor_id: targetInc,
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

      const asmRes = await api.handover.assemblePackage(targetPid, newCaseId, {
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
        const rdRes = await api.handover.assessReadiness(targetPid, newCaseId, newVerId, 'Readiness gate assessment')
        setReadinessData(rdRes)
      } catch (err) {
        console.warn('Readiness assessment warning:', err)
      }
      setGenPct(85)

      // 4. Generate checklists
      try {
        await api.handover.generateChecklists(targetPid, newCaseId, newVerId)
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
    !!pid && isUUID(pid),
    Boolean(out && isUUID(out) && (!inc || isUUID(inc))),
    projectSources.length === 0 || srcSel.length > 0,
    scope.areas.length > 0 && scope.from < scope.to,
    true,
    genPct >= 100,
    true,
    true
  ][step])

  const submit = async () => {
    const targetPid = isUUID(pid) ? pid : activeProject?.id
    if (!targetPid || !isUUID(targetPid)) {
      addToast({ type: 'error', title: 'Error', message: 'No valid project selected' })
      return
    }
    const finalId = createdCaseId
    if (createdCaseId && isUUID(createdCaseId)) {
      try {
        if (submitMode === 'verify') {
          await api.handover.submitSignoff(targetPid, createdCaseId, {
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
      message: `Handover case is now ready in Handover Workspace.`,
    })
    router.push(finalId ? `/handovers/${finalId}` : '/handovers')
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
              <p className="mt-1 text-sm text-muted">The outgoing member verifies findings; the incoming member receives the published handover (optional at creation).</p>
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
                <Field label="Incoming member (optional)">
                  <Select value={inc} onChange={(e) => setInc(e.target.value)}>
                    <option value="">(Optional) Leave unassigned for now</option>
                    {projectMembers.filter((m) => m.personId !== out).map((m) => (
                      <option key={m.personId} value={m.personId}>
                        {m.name} · {m.role} ({m.email})
                      </option>
                    ))}
                  </Select>
                </Field>
              </div>
              {out && inc && out === inc && (
                <div className="mt-3 flex items-center gap-2 rounded-xl border border-amber-200 bg-amber-50/80 px-3.5 py-2.5 text-[13px] text-amber-800">
                  <ShieldCheck className="size-4 shrink-0 text-amber-600" />
                  <span>Single-participant / self-handover mode: Same member designated as outgoing and incoming participant.</span>
                </div>
              )}
              {out && (
                <div className="mt-6 flex items-center gap-4 rounded-xl bg-slate-50 p-4">
                  <div className="flex-1 text-center">
                    <Avatar
                      id={out}
                      name={projectMembers.find((m) => m.personId === out)?.name || getMemberDisplayName(out, liveMembers, user)}
                      size={44}
                      className="mx-auto"
                    />
                    <p className="mt-2 text-sm font-semibold text-navy">
                      {projectMembers.find((m) => m.personId === out)?.name || getMemberDisplayName(out, liveMembers, user)}
                    </p>
                    <p className="text-xs text-muted">
                      {projectMembers.find((m) => m.personId === out)?.role || getMemberDisplayRole(out, liveMembers, user)}
                    </p>
                  </div>
                  <div className="flex flex-col items-center text-brand">
                    <Workflow className="size-5" />
                    <span className="mt-1 text-[11px] font-medium">{out === inc ? 'self-transition' : 'hands over to'}</span>
                  </div>
                  <div className="flex-1 text-center">
                    {inc ? (
                      <>
                        <Avatar
                          id={inc}
                          name={projectMembers.find((m) => m.personId === inc)?.name || getMemberDisplayName(inc, liveMembers, user)}
                          size={44}
                          className="mx-auto"
                        />
                        <p className="mt-2 text-sm font-semibold text-navy">
                          {projectMembers.find((m) => m.personId === inc)?.name || getMemberDisplayName(inc, liveMembers, user)}
                        </p>
                        <p className="text-xs text-muted">
                          {projectMembers.find((m) => m.personId === inc)?.role || getMemberDisplayRole(inc, liveMembers, user)}
                        </p>
                      </>
                    ) : (
                      <div className="py-1">
                        <div className="mx-auto flex size-11 items-center justify-center rounded-full border-2 border-dashed border-slate-300 text-xs font-medium text-slate-400">
                          ?
                        </div>
                        <p className="mt-2 text-sm font-medium text-slate-500">To be assigned</p>
                        <p className="text-xs text-muted">Successor can be assigned later</p>
                      </div>
                    )}
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
                  <div className="rounded-xl border border-line bg-slate-50/70 p-5">
                    <div className="flex items-start gap-3">
                      <Database className="mt-0.5 size-5 shrink-0 text-brand" />
                      <div>
                        <p className="text-sm font-semibold text-navy">Project Documents & Canonical Evidence</p>
                        <p className="mt-1 text-[13px] leading-relaxed text-muted">
                          No external source integrations (GitHub, Jira, Slack) are active for this project. Handover reconstruction will automatically assemble knowledge from all uploaded project documents and verified evidence records.
                        </p>
                        <p className="mt-2 flex items-center gap-1.5 text-xs font-medium text-ok">
                          <Check className="size-3.5" /> Ready to assemble with project evidence
                        </p>
                      </div>
                    </div>
                  </div>
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
                    Only evidence authored by or involving {getMemberDisplayName(out, liveMembers, user)}
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
                  ['Members', `${getMemberDisplayName(out, liveMembers, user)} → ${inc ? getMemberDisplayName(inc, liveMembers, user) : 'Unassigned'}`, 1],
                  ['Sources', projectSources.length ? projectSources.filter((x) => srcSel.includes(x.id)).map((x) => x.name).join(', ') : 'Project Documents & Evidence', 2],
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
                    {projectSources.length
                      ? `Ready to reconstruct ${projectSources.filter((x) => srcSel.includes(x.id)).reduce((a, b) => a + b.records, 0).toLocaleString()} records`
                      : 'Ready to reconstruct project knowledge'}
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
              <p className="mt-1 text-sm text-muted">This is an AI draft. Verified knowledge is compiled with cryptographic integrity; {getMemberDisplayName(out, liveMembers, user)} will confirm each finding.</p>
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
                    label={<span className="font-medium">Send to {getMemberDisplayName(out, liveMembers, user)} for verification <Badge tone="blue" className="ml-1">Recommended</Badge></span>}
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
                <Lock className="size-3" />{getMemberDisplayName(out, liveMembers, user)} and approvers will be notified. Nothing is visible to {inc ? getMemberDisplayName(inc, liveMembers, user) : 'unassigned incoming member'} until you publish.
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
export const H_TABS = [
  'overview',
  'readiness',
  'checklists',
  'decisions',
  'architecture',
  'tasks',
  'responsibilities',
  'dependencies',
  'risks',
  'operations',
  'evidence',
  'review',
  'report'
] as const
export type HTab = (typeof H_TABS)[number] | 'knowledge'
const TAB_LABELS: Record<string, string> = {
  overview: 'Overview',
  readiness: 'Readiness',
  checklists: 'Checklists',
  decisions: 'Decisions',
  architecture: 'Architecture',
  tasks: 'Tasks & Work',
  responsibilities: 'Ownership',
  dependencies: 'Dependencies',
  risks: 'Risks & Issues',
  operations: 'Operations',
  evidence: 'Evidence',
  review: 'Sign-Off & Approval',
  report: 'Report',
}
const STAGE_LABELS = [['draft', 'Draft'], ['in_progress', 'Verification'], ['pending_review', 'Manager review'], ['approved', 'Approved'], ['published', 'Published'], ['completed', 'Acknowledged']] as const

export interface HandoverSectionsContext {
  versions: HandoverPackageVersionSummary[]
  selectedVersionId: string | null
  setSelectedVersionId: (versionId: string) => void
  sectionsData: HandoverVersionSectionsResponse | null
  isLoadingVersions: boolean
  isLoadingSections: boolean
  sectionsError: string | null
  retryLoadSections: () => void
  readinessData: HandoverReadinessIntelligenceResponse | null
  isLoadingReadiness: boolean
  isReassessingReadiness: boolean
  readinessError: string | null
  readinessNotAssessed: boolean
  retryLoadReadiness: () => void
  reassessReadiness: (notes?: string) => Promise<void>
}

export function HandoverLayout({
  id,
  tab,
  children
}: {
  id: string
  tab: HTab
  children: (h: Handover, role: ProjectRole, sectionsCtx: HandoverSectionsContext) => ReactNode
}) {
  const s = useStore()
  const router = useRouter()
  const searchParams = useSearchParams()
  const versionParam = searchParams?.get('version')
  const { activeProject, members, user, refreshHandovers } = useLiveApp()
  const { h, project, role } = useHandover(id)

  // Canonical package version & eight-domain sections state
  const [versions, setVersions] = useState<HandoverPackageVersionSummary[]>([])
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null)
  const [sectionsData, setSectionsData] = useState<HandoverVersionSectionsResponse | null>(null)
  const [isLoadingVersions, setIsLoadingVersions] = useState(false)
  const [isLoadingSections, setIsLoadingSections] = useState(false)
  const [sectionsError, setSectionsError] = useState<string | null>(null)
  const [retryNonce, setRetryNonce] = useState(0)

  // Stage 4: Live Readiness Intelligence state
  const [readinessData, setReadinessData] = useState<HandoverReadinessIntelligenceResponse | null>(null)
  const [isLoadingReadiness, setIsLoadingReadiness] = useState(false)
  const [isReassessingReadiness, setIsReassessingReadiness] = useState(false)
  const [readinessError, setReadinessError] = useState<string | null>(null)
  const [readinessNotAssessed, setReadinessNotAssessed] = useState(false)
  const [readinessNonce, setReadinessNonce] = useState(0)

  const resolvedProjectId = (h?.projectId && isUUID(h.projectId) ? h.projectId : activeProject?.id) || ''

  // Reset and load versions whenever handover case or project changes (prevents cross-case leakage)
  useEffect(() => {
    let active = true
    setVersions([])
    setSelectedVersionId(null)
    setSectionsData(null)
    setSectionsError(null)
    setReadinessData(null)
    setReadinessError(null)
    setReadinessNotAssessed(false)

    if (!id || !isUUID(id) || !resolvedProjectId || !isUUID(resolvedProjectId)) {
      return
    }

    setIsLoadingVersions(true)
    api.handover
      .getVersions(resolvedProjectId, id)
      .then((res) => {
        if (!active) return
        const list = Array.isArray(res) ? res : []
        setVersions(list)
        if (list.length > 0) {
          const fromParam = versionParam && list.find((v) => v.id === versionParam)
          const current = list.find((v) => v.is_current)
          setSelectedVersionId((fromParam || current || list[0])!.id)
        }
      })
      .catch((err: unknown) => {
        if (!active) return
        const msg = err instanceof Error ? err.message : 'Failed to load package versions.'
        setSectionsError(msg)
      })
      .finally(() => {
        if (active) setIsLoadingVersions(false)
      })

    return () => {
      active = false
    }
  }, [id, resolvedProjectId, versionParam])

  // Load canonical eight-domain sections for the selected version
  useEffect(() => {
    let active = true
    if (!id || !isUUID(id) || !resolvedProjectId || !isUUID(resolvedProjectId) || !selectedVersionId) {
      setSectionsData(null)
      return
    }

    setIsLoadingSections(true)
    setSectionsError(null)
    api.handover
      .getVersionSections(resolvedProjectId, id, selectedVersionId)
      .then((res) => {
        if (!active) return
        // Guard against stale cross-case / cross-version responses
        if (res.case_id === id && res.version?.id === selectedVersionId) {
          setSectionsData(res)
        }
      })
      .catch((err: unknown) => {
        if (!active) return
        const msg = err instanceof Error ? err.message : 'Failed to retrieve canonical handover sections.'
        setSectionsError(msg)
        setSectionsData(null)
      })
      .finally(() => {
        if (active) setIsLoadingSections(false)
      })

    return () => {
      active = false
    }
  }, [id, resolvedProjectId, selectedVersionId, retryNonce])

  const retryLoadSections = () => setRetryNonce((n) => n + 1)
  const retryLoadReadiness = () => setReadinessNonce((n) => n + 1)

  // Stage 4: Load persisted live Readiness Intelligence for selected package version
  useEffect(() => {
    let active = true
    if (!id || !isUUID(id) || !resolvedProjectId || !isUUID(resolvedProjectId) || !selectedVersionId) {
      setReadinessData(null)
      setReadinessNotAssessed(false)
      return
    }

    setIsLoadingReadiness(true)
    setReadinessError(null)
    setReadinessNotAssessed(false)
    api.handover
      .getReadiness(resolvedProjectId, id, selectedVersionId)
      .then((res) => {
        if (!active) return
        if (res.version_id === selectedVersionId && (!res.case_id || res.case_id === id)) {
          setReadinessData(res)
          setReadinessNotAssessed(false)
        }
      })
      .catch((err: unknown) => {
        if (!active) return
        const status = (err as { status?: number })?.status
        const msg = err instanceof Error ? err.message : 'Failed to load readiness intelligence.'
        if (status === 404 || /no readiness assessment found/i.test(msg)) {
          setReadinessData(null)
          setReadinessNotAssessed(true)
          setReadinessError(null)
        } else {
          setReadinessError(msg)
        }
      })
      .finally(() => {
        if (active) setIsLoadingReadiness(false)
      })

    return () => {
      active = false
    }
  }, [id, resolvedProjectId, selectedVersionId, readinessNonce])

  const reassessReadiness = async (notes?: string) => {
    if (
      isReassessingReadiness ||
      !id ||
      !isUUID(id) ||
      !resolvedProjectId ||
      !isUUID(resolvedProjectId) ||
      !selectedVersionId
    ) {
      return
    }
    setIsReassessingReadiness(true)
    setReadinessError(null)
    try {
      const updated = await api.handover.assessReadiness(
        resolvedProjectId,
        id,
        selectedVersionId,
        notes || 'Live readiness reassessment'
      )
      setReadinessData(updated)
      setReadinessNotAssessed(false)
      s.toast(
        'Readiness reassessed',
        `Score ${updated.overall_score}/100 · ${updated.blocker_count} active blocker(s)`,
        updated.blocker_count === 0 ? 'success' : 'info'
      )
      await refreshHandovers()
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to reassess handover readiness.'
      setReadinessError(msg)
      s.toast('Reassessment failed', msg, 'error')
    } finally {
      setIsReassessingReadiness(false)
    }
  }

  if (!h || !project) return <HandoverNotFound />

  const sectionsCtx: HandoverSectionsContext = {
    versions,
    selectedVersionId,
    setSelectedVersionId,
    sectionsData,
    isLoadingVersions,
    isLoadingSections,
    sectionsError,
    retryLoadSections,
    readinessData,
    isLoadingReadiness,
    isReassessingReadiness,
    readinessError,
    readinessNotAssessed,
    retryLoadReadiness,
    reassessReadiness,
  }

  const verifiedCount = sectionsData?.epistemic_summary.human_verified_included ?? 0
  const pendingCount = sectionsData?.epistemic_summary.pending_verification ?? 0
  const totalCandidates = verifiedCount + pendingCount
  const idx = STAGE_LABELS.findIndex(([k]) => k === h.status)

  const actions: ReactNode[] = []
  if (tab !== 'review') {
    actions.push(
      <Button
        key="signoff"
        icon={ShieldCheck}
        onClick={() => router.push(`/handovers/${h.id}/review`)}
      >
        Sign-Off &amp; Approval
      </Button>
    )
  }
  if (h.status === 'published' || h.status === 'completed') {
    actions.push(
      <Button
        key="recipient"
        variant="secondary"
        icon={BookOpen}
        onClick={() => router.push(`/handovers/${h.id}/recipient`)}
      >
        Recipient View
      </Button>
    )
  }

  // Real tab badge counts derived strictly from canonical backend sections (never mock stores)
  const sectionByType = new Map((sectionsData?.sections || []).map((sec) => [sec.section_type, sec]))
  const uniqueEvidenceIds = new Set<string>()
  for (const sec of sectionsData?.sections || []) {
    for (const ki of sec.knowledge_items) {
      for (const ev of ki.provenance) uniqueEvidenceIds.add(ev.evidence_id)
    }
    for (const rel of sec.relationships) {
      for (const ev of rel.provenance) uniqueEvidenceIds.add(ev.evidence_id)
    }
  }

  const tabs = [...H_TABS]
  const counts: Partial<Record<string, number>> = {
    readiness: readinessData?.blocker_count,
    checklists: readinessData?.checklist_summary?.mandatory_outstanding,
    decisions: sectionByType.get('decisions_rationale')?.knowledge_items.length ?? 0,
    architecture: sectionByType.get('technical_architecture')?.knowledge_items.length ?? 0,
    tasks: sectionByType.get('work_progress')?.knowledge_items.length ?? 0,
    responsibilities: sectionByType.get('responsibilities_ownership')?.knowledge_items.length ?? 0,
    dependencies:
      (sectionByType.get('dependencies_relationships')?.knowledge_items.length ?? 0) +
      (sectionByType.get('dependencies_relationships')?.relationships.length ?? 0),
    risks:
      (sectionByType.get('bugs_blockers_risks')?.knowledge_items.length ?? 0) +
      (sectionByType.get('bugs_blockers_risks')?.unresolved_conflicts.length ?? 0),
    operations: sectionByType.get('operational_historical')?.knowledge_items.length ?? 0,
    evidence: uniqueEvidenceIds.size,
  }

  const selectedVersion = versions.find((v) => v.id === selectedVersionId) || sectionsData?.version || null
  const activeTabValue = tab === 'knowledge' ? 'overview' : tab

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
                  {selectedVersion && (
                    <Badge tone={selectedVersion.is_current ? 'blue' : 'amber'}>
                      Package v{selectedVersion.version_number}
                      {selectedVersion.is_current ? ' (Current)' : ' (Historical)'}
                    </Badge>
                  )}
                  {readinessData && (
                    <button
                      type="button"
                      onClick={() =>
                        router.push(
                          selectedVersionId
                            ? `/handovers/${h.id}?tab=readiness&version=${selectedVersionId}`
                            : `/handovers/${h.id}?tab=readiness`
                        )
                      }
                      className="inline-flex items-center gap-1.5 rounded-full border border-line bg-slate-50 px-2.5 py-0.5 text-[11px] font-semibold text-navy transition hover:border-brand/40 hover:bg-tint/40"
                    >
                      <span>Readiness {readinessData.overall_score}/100</span>
                      <span
                        className={cn(
                          'size-1.5 rounded-full',
                          readinessData.overall_level === 'ready'
                            ? 'bg-emerald-500'
                            : readinessData.overall_level === 'ready_with_warnings'
                            ? 'bg-blue-500'
                            : readinessData.overall_level === 'partially_ready'
                            ? 'bg-amber-500'
                            : 'bg-red-500'
                        )}
                      />
                    </button>
                  )}
                </div>
                <h1 className="mt-2 text-[22px] font-semibold tracking-tight text-navy">{project.name}</h1>
                <p className="mt-0.5 text-[13px] text-muted">{h.scope}</p>
                <div className="mt-4 flex flex-wrap items-center gap-x-6 gap-y-3 text-[13px]">
                  <span className="flex items-center gap-2">
                    <Avatar id={h.outgoingId} name={getMemberDisplayName(h.outgoingId, members, user)} size={28} />
                    <span>
                      <span className="block text-[11px] text-muted">Outgoing</span>
                      <span className="font-medium text-navy">{getMemberDisplayName(h.outgoingId, members, user)}</span>
                    </span>
                  </span>
                  <ArrowRight className="size-4 text-brand" />
                  <span className="flex items-center gap-2">
                    <Avatar id={h.incomingId} name={getMemberDisplayName(h.incomingId, members, user)} size={28} />
                    <span>
                      <span className="block text-[11px] text-muted">Incoming</span>
                      <span className="font-medium text-navy">{getMemberDisplayName(h.incomingId, members, user)}</span>
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
                  <Ring value={totalCandidates > 0 ? Math.round((verifiedCount / totalCandidates) * 100) : 0} size={56} />
                  <div>
                    <p className="text-[11px] text-muted">Verified Knowledge</p>
                    <p className="text-[13px] font-medium text-navy">
                      {isLoadingSections ? 'Loading…' : `${verifiedCount} verified · ${pendingCount} pending`}
                    </p>
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
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line bg-slate-50/60 px-5 py-2.5 text-xs text-muted">
            <div className="flex flex-wrap items-center gap-3">
              {versions.length > 0 ? (
                <label className="flex items-center gap-2">
                  <span className="font-medium text-navy">Package Version:</span>
                  <select
                    aria-label="Package Version"
                    value={selectedVersionId || ''}
                    onChange={(e) => setSelectedVersionId(e.target.value)}
                    className="rounded-lg border border-line bg-white px-2.5 py-1 text-xs font-medium text-navy focus:border-brand focus:outline-none"
                  >
                    {versions.map((v) => (
                      <option key={v.id} value={v.id}>
                        v{v.version_number}
                        {v.is_current ? ' (Current)' : ' (Historical)'}
                        {v.assembled_at ? ` · ${new Date(v.assembled_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}` : ''}
                      </option>
                    ))}
                  </select>
                </label>
              ) : (
                <span>{isLoadingVersions ? 'Loading package versions…' : 'No package versions assembled yet'}</span>
              )}
              {selectedVersion?.content_hash && (
                <span
                  className="inline-flex items-center gap-1 rounded-md border border-line bg-white px-2 py-0.5 font-mono text-[11px] text-slate-600"
                  title={`Immutable Package SHA-256: ${selectedVersion.content_hash}`}
                >
                  <ShieldCheck className="size-3 text-ok" />
                  SHA-256: {selectedVersion.content_hash.slice(0, 12)}…
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              <span className="hidden items-center gap-1.5 sm:flex"><Eye className="size-3.5" />View as</span>
              <Segmented
                value={role}
                onChange={(v) => s.setPerspective((m) => ({ ...m, [h.id]: v }))}
                options={(['manager', 'outgoing', 'incoming'] as const).map((r) => ({
                  id: r,
                  label: ROLE_LABEL[r].replace(' Member', '').replace('Project ', '')
                }))}
              />
            </div>
          </div>
        </Card>
        <Tabs
          className="mb-5"
          tabs={tabs.map((t) => ({ id: t, label: TAB_LABELS[t] || t, count: counts[t] }))}
          value={activeTabValue}
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
      {children(h, role, sectionsCtx)}
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
  const { activeProject, members, user, refreshHandovers } = useLiveApp()
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
      if (!id || !isUUID(id)) return
      setIsLoadingChecklists(true)
      try {
        const targetCase = s.handovers.find((x) => x.id === id)
        const pId = targetCase?.projectId && isUUID(targetCase.projectId) ? targetCase.projectId : activeProject?.id
        if (!pId || !isUUID(pId)) return
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
      {(h, _role, sectionsCtx) => {
        const resolvedPid = isUUID(h.projectId) ? h.projectId : activeProject?.id || h.projectId
        const normalizedTab = tab === 'knowledge' ? 'overview' : tab
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

        const checklistsCard = (
          <Card>
            <div className="flex flex-col gap-3 border-b border-line p-5 sm:flex-row sm:items-center sm:justify-between">
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
                  onClick={() => handleGenerateChecklists(resolvedPid)}
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
                    <Button icon={Sparkles} onClick={() => handleGenerateChecklists(resolvedPid)}>
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
                        <div className="flex items-center justify-between border-b border-line pb-3">
                          <span className="text-[13px] font-semibold text-navy">{typeLabel}</span>
                          <span className="text-xs font-medium text-muted">{completedCount}/{items.length}</span>
                        </div>
                        <ul className="mt-3 flex-1 space-y-2.5">
                          {items.map((item: any) => {
                            const isDone = item.status === 'completed'
                            const isUpdating = updatingItemId === item.id
                            return (
                              <li key={item.id} className="flex items-start gap-2.5 text-xs">
                                <input
                                  type="checkbox"
                                  checked={isDone}
                                  disabled={isUpdating}
                                  onChange={() => toggleItem(resolvedPid, item.id, item.status)}
                                  className="mt-0.5 size-4 cursor-pointer rounded border-slate-300 text-brand focus:ring-brand"
                                />
                                <div className="min-w-0 flex-1">
                                  <span className={cn('leading-relaxed', isDone ? 'text-slate-400 line-through' : 'font-medium text-slate-800')}>
                                    {item.item_text || item.title}
                                  </span>
                                  {item.blocking && (
                                    <span className="ml-1.5 inline-block rounded border border-red-200 bg-red-50 px-1 text-[10px] font-medium text-red-600">
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
        )

        if (normalizedTab === 'readiness') {
          const selectedVersionObj =
            sectionsCtx.versions.find((v) => v.id === sectionsCtx.selectedVersionId) ||
            sectionsCtx.sectionsData?.version ||
            null
          return (
            <ReadinessIntelligencePanel
              caseId={h.id}
              projectId={resolvedPid}
              selectedVersion={selectedVersionObj}
              readiness={sectionsCtx.readinessData}
              isLoading={sectionsCtx.isLoadingVersions || sectionsCtx.isLoadingReadiness}
              isReassessing={sectionsCtx.isReassessingReadiness}
              error={sectionsCtx.readinessError}
              notAssessedYet={sectionsCtx.readinessNotAssessed}
              onRetry={sectionsCtx.retryLoadReadiness}
              onReassess={sectionsCtx.reassessReadiness}
              onNavigateTab={navigateTab}
              onToggleChecklistItem={async (pId, itemId, curStatus) => {
                await toggleItem(pId, itemId, curStatus)
                sectionsCtx.retryLoadReadiness()
              }}
              onGenerateChecklists={async (pId) => {
                await handleGenerateChecklists(pId)
                sectionsCtx.retryLoadReadiness()
              }}
              updatingChecklistItemId={updatingItemId}
              isGeneratingChecklists={isLoadingChecklists}
            />
          )
        }

        if (normalizedTab === 'checklists') {
          return (
            <TransitionChecklistsPanel
              caseId={h.id}
              projectId={resolvedPid}
              currentUserId={user?.id}
              members={members || []}
              onDataChanged={() => {
                sectionsCtx.retryLoadReadiness()
                if (resolvedPid && isUUID(resolvedPid) && isUUID(id)) {
                  api.handover.getChecklists(resolvedPid, id).then((r) => setChecklists(r || [])).catch(() => {})
                }
              }}
              onReassessReadiness={() =>
                sectionsCtx.reassessReadiness('Post-checklist reassessment')
              }
              isReassessingReadiness={sectionsCtx.isReassessingReadiness}
            />
          )
        }

        if (normalizedTab === 'responsibilities') {
          const canManage = _role === 'manager'
          return (
            <div className="space-y-6">
              <ResponsibilityTransferPanel
                caseId={h.id}
                projectId={resolvedPid}
                currentUserId={user?.id}
                canManageProject={canManage}
                onDataChanged={() => {
                  sectionsCtx.retryLoadReadiness()
                }}
                onReassessReadiness={() =>
                  sectionsCtx.reassessReadiness('Post-responsibility-transfer reassessment')
                }
                isReassessingReadiness={sectionsCtx.isReassessingReadiness}
              />
              <CanonicalSectionPanel
                sectionType="responsibilities_ownership"
                data={sectionsCtx.sectionsData}
                isLoading={sectionsCtx.isLoadingVersions || sectionsCtx.isLoadingSections}
                error={sectionsCtx.sectionsError}
                projectId={resolvedPid}
                handoverId={h.id}
                onRetry={sectionsCtx.retryLoadSections}
                onNavigateTab={navigateTab}
              />
            </div>
          )
        }

        if (normalizedTab === 'review') {
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
        }

        if (normalizedTab === 'evidence') {
          return (
            <CanonicalEvidenceTable
              data={sectionsCtx.sectionsData}
              isLoading={sectionsCtx.isLoadingVersions || sectionsCtx.isLoadingSections}
              error={sectionsCtx.sectionsError}
              projectId={resolvedPid}
              onRetry={sectionsCtx.retryLoadSections}
            />
          )
        }

        const targetSectionType = TAB_TO_SECTION_TYPE[normalizedTab] || 'project_overview_context'

        return (
          <CanonicalSectionPanel
            sectionType={targetSectionType}
            data={sectionsCtx.sectionsData}
            isLoading={sectionsCtx.isLoadingVersions || sectionsCtx.isLoadingSections}
            error={sectionsCtx.sectionsError}
            projectId={resolvedPid}
            handoverId={h.id}
            onRetry={sectionsCtx.retryLoadSections}
            onNavigateTab={navigateTab}
            overviewExtras={normalizedTab === 'overview' ? checklistsCard : undefined}
          />
        )
      }}
    </HandoverLayout>
  )
}

/* ---------- 27. Published ---------- */
export function PublishedHandovers() {
  const router = useRouter()
  const { handoverCases, projects, members, user } = useLiveApp()

  const liveHandovers = useMemo(() => {
    return (handoverCases || []).map((c) => {
      const pName = projects.find((p) => p.id === c.project_id)?.name || 'Project'
      return mapCaseToHandover(c, pName)
    })
  }, [handoverCases, projects])

  const list = liveHandovers.filter((h) => ['published', 'completed', 'delivered', 'acknowledged'].includes(h.status))

  return (
    <>
      <div className="flex flex-col gap-3 pb-5 sm:flex-row sm:items-center sm:justify-between">
        <PageHeader
          title="Published Handovers"
          subtitle="Track published handover packages and formal recipient acknowledgements."
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
                <Th>Updated</Th>
                <Th>Status</Th>
                <Th className="text-right">Actions</Th>
              </tr>
            </thead>
            <tbody>
              {list.map((h) => {
                const p = projects.find((x) => x.id === h.projectId)
                const outName = getMemberDisplayName(h.outgoingId, members, user)
                const incName = getMemberDisplayName(h.incomingId, members, user)
                const isAck = h.status === 'completed' || (h.status as string) === 'acknowledged'
                return (
                  <tr key={h.id} className="hover:bg-slate-50/50">
                    <Td>
                      <Link to={`/handovers/${h.id}/review`} className="font-medium text-navy hover:text-brand">
                        {h.code}
                      </Link>
                      <p className="text-xs text-muted">from {outName}</p>
                    </Td>
                    <Td className="text-[13px]">{p?.name || 'Project'}</Td>
                    <Td>
                      <span className="flex items-center gap-2 whitespace-nowrap text-[13px]">
                        <Avatar id={h.incomingId} name={incName} size={24} />
                        {incName}
                      </span>
                    </Td>
                    <Td className="whitespace-nowrap text-[13px] text-muted">{h.updated}</Td>
                    <Td>
                      {isAck ? (
                        <Badge tone="green" icon={CheckCircle2}>Acknowledged</Badge>
                      ) : (
                        <Badge tone="amber" icon={Clock}>Pending acknowledgement</Badge>
                      )}
                    </Td>
                    <Td className="text-right">
                      <div className="flex justify-end gap-1.5">
                        <Button
                          size="sm"
                          variant="secondary"
                          icon={ShieldCheck}
                          onClick={() => router.push(`/handovers/${h.id}/review`)}
                        >
                          Publication &amp; Audit
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          icon={BookOpen}
                          onClick={() => router.push(`/handovers/${h.id}/recipient`)}
                        >
                          Recipient View
                        </Button>
                      </div>
                    </Td>
                  </tr>
                )
              })}
            </tbody>
          </Table>
        )}
      </Card>
    </>
  )
}

/* ---------- 28. Received ---------- */
export function ReceivedHandovers() {
  const router = useRouter()
  const { handoverCases, projects, members, user } = useLiveApp()

  const liveHandovers = useMemo(() => {
    return (handoverCases || []).map((c) => {
      const pName = projects.find((p) => p.id === c.project_id)?.name || 'Project'
      return mapCaseToHandover(c, pName)
    })
  }, [handoverCases, projects])

  const currentUserId = user?.id || ''
  const list = liveHandovers.filter(
    (h) => h.incomingId === currentUserId &&
           ['published', 'completed', 'delivered', 'acknowledged'].includes(h.status as string)
  )
  const pending = list.filter((h) => (h.status as string) === 'published' || (h.status as string) === 'delivered')

  return (
    <>
      <PageHeader
        title="Received Handovers"
        subtitle="Published handover packages assigned to you. Review all eight domains and record formal acknowledgement."
      />
      {!list.length ? (
        <Card>
          <EmptyState
            icon={Inbox}
            title="Your inbox is empty"
            body="When an approved handover package is published to you, it appears here with its verified knowledge domains and acknowledgement controls."
          />
        </Card>
      ) : (
        <>
          {!!pending.length && (
            <div className="mb-5">
              <Callout tone="blue" icon={Inbox} title={`${pending.length} handover${pending.length > 1 ? 's' : ''} awaiting your acknowledgement`}>
                Review the published package domains, raise any clarifications, then record your formal acknowledgement.
              </Callout>
            </div>
          )}
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {list.map((h) => {
              const p = projects.find((x) => x.id === h.projectId)
              const outName = getMemberDisplayName(h.outgoingId, members, user)
              const isAck = h.status === 'completed' || (h.status as string) === 'acknowledged'
              return (
                <Card key={h.id} interactive className={cn('flex flex-col overflow-hidden', !isAck && 'ring-2 ring-brand/20')}>
                  <div className="h-1.5 bg-brand" />
                  <div className="flex flex-1 flex-col p-5">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-medium text-muted">{h.code}</span>
                      {!isAck ? (
                        <Badge tone="amber" icon={Clock}>Pending acknowledgement</Badge>
                      ) : (
                        <Badge tone="green" icon={CheckCircle2}>Acknowledged</Badge>
                      )}
                    </div>
                    <h3 className="mt-3 text-base font-semibold text-navy">{p?.name || 'Project'}</h3>
                    <p className="mt-0.5 text-[13px] text-muted">{h.scope}</p>
                    <div className="mt-4 flex items-center gap-2.5 text-[13px]">
                      <Avatar id={h.outgoingId} name={outName} size={28} />
                      <div>
                        <p className="font-medium text-navy">{outName}</p>
                        <p className="text-xs text-muted">Updated {h.updated}</p>
                      </div>
                    </div>
                    <div className="mt-5 flex gap-2">
                      <Button className="flex-1" iconRight={ArrowRight} onClick={() => router.push(`/handovers/${h.id}/recipient`)}>
                        Open package
                      </Button>
                      <Button
                        variant="secondary"
                        icon={ShieldCheck}
                        onClick={() => router.push(`/handovers/${h.id}/review`)}
                        aria-label="Sign-off and audit history"
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
  const { handoverCases, activeProject } = useLiveApp()
  const pId = projectId || (params?.id as string) || activeProject?.id

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
      const targetId = handoverCases.find((h) => !pId || h.project_id === pId)?.id ?? handoverCases[0]?.id ?? ''
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
