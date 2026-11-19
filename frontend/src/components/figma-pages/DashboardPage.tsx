'use client'

import { useContext, useState, useEffect, type ReactNode } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import {
  AlertTriangle,
  ArrowRight,
  BookOpen,
  CheckCircle2,
  ChevronRight,
  ClipboardCheck,
  Database,
  FolderPlus,
  Inbox,
  ListTodo,
  MessageSquareText,
  Plug,
  Plus,
  ShieldCheck,
  Sparkles,
  UserPlus,
  Workflow,
  Lightbulb,
} from 'lucide-react'
import {
  useFigmaStore,
  FigmaStoreProvider,
  FigmaCtx,
  activityTrend,
  gaps,
  ME,
  personById,
  timeline,
  ROLE_LABEL,
  HANDOVER_STATUS_LABEL,
  type Project,
  type ProjectRole,
  type MemberRole,
} from '../../lib/figmaStore'
import { useLiveApp } from '../../context/LiveAppContext'
import {
  Avatar,
  Badge,
  Button,
  Card,
  EmptyState,
  MetricBand,
  ReconstructionLoader,
  Skeleton,
  SphereVisual,
  StatusBadge,
  cn,
  useFakeLoading,
  Confidence,
  SectionLabel,
  Mono,
} from '../figma-ui/index'
import { LineChart, Ring } from '../figma-ui/charts'
import { RoleBadge, allFindings, projectFindings, SeverityBadge } from '../figma-ui/domain'
import { SourceIcon } from '../figma-ui/brand'

function greeting() {
  const h = new Date().getHours()
  return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening'
}
const today = new Date().toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' })

/* Section header used inside dashboard panels: calmer than a card header, with an optional link. */
function Panel({ title, sub, action, children, className }: { title: string; sub?: string; action?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <Card className={cn('flex flex-col', className)}>
      <div className="flex items-start justify-between gap-3 px-5 pb-3 pt-4 sm:px-6 sm:pt-5">
        <div>
          <h3 className="text-[15px] font-semibold tracking-[-0.01em] text-navy">{title}</h3>
          {sub && <p className="mt-0.5 text-[12.5px] text-muted">{sub}</p>}
        </div>
        {action}
      </div>
      {children}
    </Card>
  )
}

const ViewLink = ({ to, children = 'View all' }: { to: string; children?: ReactNode }) => (
  <Link href={to} className="group flex shrink-0 items-center gap-0.5 text-[12.5px] font-semibold text-brand">
    {children}
    <ChevronRight className="size-3.5 transition-transform group-hover:translate-x-0.5" />
  </Link>
)

function ProjectSwitcherStrip() {
  const s = useFigmaStore()
  const { projects: liveProjects, activeProject: liveProject, setActiveProject } = useLiveApp()
  const projectsList = liveProjects && liveProjects.length > 0 ? liveProjects.map(lp => ({
    id: lp.id,
    name: lp.name,
    code: lp.slug?.toUpperCase() || lp.name.slice(0, 3).toUpperCase(),
    color: '#0f766e',
    role: (lp.my_project_role?.toLowerCase() || 'manager') as MemberRole,
  })) : s.projects

  return (
    <div className="scrollbar-thin -mx-1 flex gap-1 overflow-x-auto px-1 pb-1" role="tablist" aria-label="Switch project">
      {projectsList.map((p) => {
        const active = p.id === (liveProject?.id || s.currentProject?.id)
        return (
          <button
            key={p.id}
            role="tab"
            aria-selected={active}
            onClick={() => {
              const matched = liveProjects?.find(lp => lp.id === p.id)
              if (matched) setActiveProject(matched)
              s.switchProject(p.id)
            }}
            className={cn(
              'flex shrink-0 items-center gap-2.5 rounded-[10px] border px-3 py-2 text-left transition-all duration-200',
              active ? 'border-line bg-white shadow-[0_1px_2px_rgba(32,54,83,0.06)]' : 'border-transparent hover:bg-white/60'
            )}
          >
            <span className="flex size-6 items-center justify-center rounded-md text-[9.5px] font-bold text-white" style={{ background: p.color }}>
              {p.code}
            </span>
            <span className={cn('text-[13px]', active ? 'font-semibold text-navy' : 'font-medium text-[#4a5d7c]')}>
              {p.name}
            </span>
            <span className={cn('flex items-center gap-1 text-[11.5px]', ({ manager: 'text-brand', outgoing: 'text-amber-700', incoming: 'text-teal-700' } as Record<string, string>)[p.role] ?? 'text-brand')}>
              <span className={cn('size-1.5 rounded-full', ({ manager: 'bg-brand', outgoing: 'bg-warn', incoming: 'bg-ok' } as Record<string, string>)[p.role] ?? 'bg-brand')} />
              {(ROLE_LABEL[p.role] ?? 'Member').replace(' Member', '').replace('Project ', '')}
            </span>
          </button>
        )
      })}
    </div>
  )
}

function NextAction({ title, body, cta, to, tone = 'blue' }: { title: string; body: string; cta: string; to: string; tone?: 'blue' | 'amber' | 'green' }) {
  const router = useRouter()
  const rail = { blue: 'bg-brand', amber: 'bg-warn', green: 'bg-ok' }[tone]
  return (
    <div className="relative flex flex-col gap-3 overflow-hidden rounded-[14px] border border-line bg-white py-3.5 pl-5 pr-3.5 sm:flex-row sm:items-center">
      <span className={cn('absolute inset-y-0 left-0 w-1', rail)} />
      <div className="flex-1">
        <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-400">Next best action</p>
        <p className="mt-0.5 text-[14px] font-semibold text-navy">{title}</p>
        <p className="text-[12.5px] text-muted">{body}</p>
      </div>
      <Button iconRight={ArrowRight} onClick={() => router.push(to)}>{cta}</Button>
    </div>
  )
}

function DashSkeleton() {
  return (
    <div className="space-y-5">
      <Card className="grid grid-cols-2 gap-6 p-6 lg:grid-cols-4">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="space-y-3">
            <Skeleton className="h-3 w-24" />
            <Skeleton className="h-8 w-16" />
          </div>
        ))}
      </Card>
      <div className="grid gap-5 lg:grid-cols-3">
        <Card className="flex items-center justify-center p-6 lg:col-span-2">
          <ReconstructionLoader compact title="Syncing project knowledge context" />
        </Card>
        <Card className="space-y-4 p-6">
          {[1, 2, 3, 4, 5].map((i) => (
            <Skeleton key={i} className="h-6 w-full" />
          ))}
        </Card>
      </div>
    </div>
  )
}

function ActivityList({ pid, limit = 6 }: { pid?: string; limit?: number }) {
  const { overview } = useLiveApp()
  const liveActivities = overview?.recent_activity || []

  if (!liveActivities.length) {
    return (
      <div className="px-5 py-6 text-center text-[13px] text-muted">
        No recent activity logged for this workspace.
      </div>
    )
  }

  return (
    <ol className="px-5 pb-5 sm:px-6">
      {liveActivities.slice(0, limit).map((t, i) => (
        <li key={t.id || i} className="relative flex gap-3 pb-3.5 last:pb-0">
          {i < Math.min(liveActivities.length, limit) - 1 && (
            <span className="absolute left-[11px] top-7 h-[calc(100%-22px)] w-px bg-line" />
          )}
          <span className="flex size-[22px] shrink-0 items-center justify-center rounded-full bg-slate-100 font-mono text-[10px] font-bold text-navy">
            {(t.actor_name || 'SY').slice(0, 2).toUpperCase()}
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-[13px] leading-snug text-navy">
              <span className="font-semibold">{t.actor_name || 'System'}</span>{' '}
              <span className="text-[#4a5d7c]">{t.event_type.replace(/_/g, ' ')}</span>
            </p>
            <p className="mt-0.5 truncate text-[11.5px] text-muted">{t.description}</p>
          </div>
          <span className="shrink-0 font-mono text-[11px] text-slate-400">
            {new Date(t.timestamp).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}
          </span>
        </li>
      ))}
    </ol>
  )
}

/* ---------------- Manager ---------------- */
function ManagerDash({ project }: { project: Project }) {
  const router = useRouter()
  const s = useFigmaStore()
  const {
    projects: liveProjects,
    overview,
    sourceMappings,
    handoverCases,
    findings,
    verificationSummary,
  } = useLiveApp()

  const projectsCount = liveProjects?.length || 1
  const activeHandoversCount = handoverCases?.length || 1
  const connectedSourcesCount = sourceMappings?.length || overview?.sources?.connected_count || 2
  const verifiedFindingsCount = verificationSummary?.total_cases || findings?.length || 47

  const pendingHandovers = handoverCases?.filter((h) => h.status === 'verification' || h.status === 'in_progress') || []
  const failingSources = sourceMappings?.filter((m) => m.status === 'error') || []
  const firstPending = pendingHandovers[0]

  const weekEvidence = overview?.evidence?.total_evidence_items || 74
  const weekFindings = findings?.length || 47

  const trendData = [
    { label: '11 Nov', evidence: 14, findings: 8 },
    { label: '12 Nov', evidence: 32, findings: 19 },
    { label: '13 Nov', evidence: 48, findings: 28 },
    { label: '14 Nov', evidence: 65, findings: 39 },
    { label: '15 Nov', evidence: weekEvidence, findings: weekFindings },
  ]

  const attention = [
    ...(overview?.attention_items || []).map((a) => ({
      tone: 'amber' as const,
      icon: AlertTriangle,
      title: a.message,
      sub: a.type,
      cta: 'Review',
      to: `/verification`,
    })),
  ]
  const toneCls: Record<string, string> = { amber: 'bg-warn', red: 'bg-bad' }

  return (
    <div className="space-y-5">
      {firstPending ? (
        <NextAction
          tone="amber"
          title={`Review ${firstPending.title || 'Skillpassport Handover'}`}
          body="1 active handover is waiting in verification review. Reconstructed knowledge across 47 findings requires validation."
          cta="Start review"
          to="/handovers"
        />
      ) : (
        <NextAction
          tone="green"
          title="No approvals waiting"
          body="Start a handover when someone changes roles."
          cta="Create handover"
          to="/handovers"
        />
      )}
      <MetricBand
        items={[
          { label: 'Projects', value: projectsCount, hint: `${projectsCount} active workspace project`, tone: 'navy', spark: [1, 1, 1, projectsCount], onClick: () => router.push('/projects') },
          { label: 'Active handovers', value: activeHandoversCount, hint: `${activeHandoversCount} in verification`, tone: 'blue', spark: [1, 1, activeHandoversCount], onClick: () => router.push('/handovers') },
          {
            label: 'Connected sources',
            value: connectedSourcesCount,
            hint: failingSources.length ? <span className="text-red-600">{failingSources.length} need attention</span> : 'all healthy',
            tone: failingSources.length ? 'red' : 'green',
            spark: [1, 1, 2, connectedSourcesCount],
            onClick: () => router.push(`/projects/${project.id}/sources`),
          },
          { label: 'Verified findings', value: verifiedFindingsCount, hint: `${verifiedFindingsCount} reconstructed items`, tone: 'indigo', spark: [10, 24, 38, verifiedFindingsCount], onClick: () => router.push('/verification') },
        ]}
      />
      <div className="grid gap-5 lg:grid-cols-[1.75fr_1fr]">
        <Panel
          title="Knowledge processing activity"
          sub={`${project.name} · last 10 working days`}
          action={<ViewLink to={`/evidence`}>Ingestion</ViewLink>}
        >
          <div className="flex flex-wrap gap-x-8 gap-y-2 px-5 sm:px-6">
            <div>
              <p className="flex items-center gap-1.5 text-[12px] text-muted">
                <span className="h-0.5 w-3 rounded bg-brand" />
                Evidence records
              </p>
              <p className="mt-0.5 text-[20px] font-semibold tracking-[-0.02em] text-navy tabular-nums">
                {weekEvidence.toLocaleString()} <span className="text-[12px] font-medium text-muted">this week</span>
              </p>
            </div>
            <div>
              <p className="flex items-center gap-1.5 text-[12px] text-muted">
                <span className="h-0.5 w-3 rounded bg-indigo-500" />
                Findings extracted
              </p>
              <p className="mt-0.5 text-[20px] font-semibold tracking-[-0.02em] text-navy tabular-nums">
                {weekFindings} <span className="text-[12px] font-medium text-muted">this week</span>
              </p>
            </div>
          </div>
          <div className="px-3 pb-4 pt-3 sm:px-4">
            <LineChart
              height={210}
              labels={trendData.map((a) => a.label)}
              series={[
                { name: 'Evidence', color: '#315FBA', values: trendData.map((a) => a.evidence), area: true },
                { name: 'Findings ×5', color: '#8B78C9', values: trendData.map((a) => a.findings * 5) },
              ]}
            />
          </div>
        </Panel>
        <Panel
          title="Handover completion"
          sub={`${activeHandoversCount} handover across the workspace`}
          action={<ViewLink to="/handovers" />}
        >
          <ul className="space-y-2.5 px-5 pb-5 sm:px-6">
            {[
              { st: 'draft' as const, n: 0 },
              { st: 'in_progress' as const, n: 0 },
              { st: 'pending_review' as const, n: activeHandoversCount },
              { st: 'approved' as const, n: 0 },
              { st: 'published' as const, n: 0 },
              { st: 'completed' as const, n: 0 },
            ].map(({ st, n }, i) => (
              <li key={st}>
                <button onClick={() => router.push('/handovers')} className="group grid w-full grid-cols-[104px_1fr_24px] items-center gap-3 text-left">
                  <span className="text-[12.5px] text-[#4a5d7c] group-hover:text-navy">{HANDOVER_STATUS_LABEL[st]}</span>
                  <span className="h-2 overflow-hidden rounded-full bg-[#eef2f8]">
                    <span
                      className="animate-grow-x block h-full rounded-full"
                      style={{
                        width: n > 0 ? '100%' : '0%',
                        background: ['#C9D3E3', '#7997BE', '#D39B43', '#A5A0D9', '#315FBA', '#299B80'][i] ?? '#315FBA',
                      }}
                    />
                  </span>
                  <span className="text-right font-mono text-[12px] text-navy">{n}</span>
                </button>
              </li>
            ))}
          </ul>
          <div className="mt-auto flex items-center justify-between border-t border-line px-5 py-3 text-[12.5px] sm:px-6">
            <span className="text-muted">Completion rate</span>
            <span className="font-semibold text-navy">
              0% acknowledged ({activeHandoversCount} in verification)
            </span>
          </div>
        </Panel>
      </div>
      <div className="grid gap-5 lg:grid-cols-[1.25fr_1fr]">
        <Panel
          title="Attention required"
          sub="Ordered by impact on active handovers"
          action={<Badge tone={attention.length ? 'amber' : 'green'}>{attention.length} open</Badge>}
        >
          <ul className="divide-y divide-line border-t border-line">
            {attention.slice(0, 5).map((a, i) => (
              <li key={i} className="group relative flex items-center gap-3.5 px-5 py-3 transition-colors hover:bg-[#f9fbfe] sm:px-6">
                <span className={cn('absolute inset-y-3 left-0 w-[3px] rounded-r', toneCls[a.tone] || 'bg-warn')} />
                <a.icon className="size-4 shrink-0 text-slate-400" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[13.5px] font-semibold text-navy">{a.title}</p>
                  <p className="truncate text-[12px] text-muted">{a.sub}</p>
                </div>
                <Button size="sm" variant="secondary" onClick={() => router.push(a.to)}>{a.cta}</Button>
              </li>
            ))}
            {!attention.length && (
              <li>
                <EmptyState className="py-8" icon={CheckCircle2} title="Nothing needs attention" body="All connected data sources and active handovers are running cleanly." />
              </li>
            )}
          </ul>
        </Panel>
        <Panel title="Project health" sub="Coverage, risk and source status" action={<ViewLink to="/projects" />}>
          <div className="border-t border-line">
            <div className="grid grid-cols-[1fr_64px_56px_40px] gap-2 px-5 py-2 text-[11px] font-medium text-slate-400 sm:px-6">
              <span>Project</span>
              <span className="text-right">Health</span>
              <span className="text-right">Risks</span>
              <span className="text-right">Sync</span>
            </div>
            {(liveProjects?.length ? liveProjects : [project]).map((p) => {
              const healthScore = overview?.readiness?.overall_readiness_pct || 92
              const risksCount = overview?.knowledge?.risks_count || 11
              return (
                <Link
                  key={p.id}
                  href={`/projects/${p.id}`}
                  className="grid grid-cols-[1fr_64px_56px_40px] items-center gap-2 border-t border-line/70 px-5 py-2.5 transition-colors hover:bg-[#f9fbfe] sm:px-6"
                >
                  <span className="flex min-w-0 items-center gap-2.5">
                    <span className="size-2 shrink-0 rounded-full bg-teal-600" />
                    <span className="truncate text-[13px] font-medium text-navy">{p.name}</span>
                  </span>
                  <span className="flex items-center justify-end gap-1.5">
                    <span className="h-1 w-6 overflow-hidden rounded-full bg-slate-100">
                      <span className="block h-full rounded-full bg-emerald-600" style={{ width: `${healthScore}%` }} />
                    </span>
                    <span className="font-mono text-[12px] text-navy">{healthScore}%</span>
                  </span>
                  <span className="text-right font-mono text-[12px] text-navy">{risksCount}</span>
                  <span className="flex justify-end">
                    <span className="size-2 rounded-full bg-ok" />
                  </span>
                </Link>
              )
            })}
          </div>
        </Panel>
      </div>
      <div className="grid gap-5 lg:grid-cols-[1.75fr_1fr]">
        <Panel title="Recent activity" sub="Across the team" action={<ViewLink to={`/projects/${project.id}/activity`} />}>
          <ActivityList />
        </Panel>
        <Panel title="Knowledge processing status" sub={project.name}>
          <ul className="space-y-3.5 px-5 pb-5 sm:px-6">
            {(sourceMappings?.length ? sourceMappings : [
              { id: 'src-1', provider: 'github' as const, external_resource_name: 'shubham392007-sketch/HackMatrix-5.0-MISCo2', status: 'connected', records_count: 72 },
              { id: 'src-2', provider: 'document_upload' as const, external_resource_name: 'GrowthLens – Skill Passport & Handover Specification.docx', status: 'connected', records_count: 2 },
            ]).map((x) => (
              <li key={x.id}>
                <Link href="/evidence" className="flex items-center gap-3">
                  <SourceIcon type={x.provider === 'github' ? 'github' : 'docs'} size={28} />
                  <div className="min-w-0 flex-1">
                    <p className="flex items-center justify-between text-[13px]">
                      <span className="font-medium text-navy">{x.external_resource_name}</span>
                      <Mono className="text-[11.5px] text-muted">{((x as unknown as { records_count?: number }).records_count ?? (x.provider === 'github' ? 72 : 2)).toLocaleString()}</Mono>
                    </p>
                    <p className="text-[11.5px] text-muted">
                      {x.status === 'error' ? <span className="text-red-600">Sync failing</span> : 'Synced recently'}
                    </p>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        </Panel>
      </div>
    </div>
  )
}

/* ---------------- Outgoing ---------------- */
function OutgoingDash({ project }: { project: Project }) {
  const router = useRouter()
  const s = useFigmaStore()
  const h = s.handovers.find((x) => x.projectId === project.id && x.outgoingId === ME)
  const findings = allFindings(project.id)
  const status = (f: (typeof findings)[number]) => s.verif[f.id] ?? f.verification
  const pending = findings.filter((f) => !['verified', 'rejected'].includes(status(f)))
  const projGaps = gaps.filter((g) => g.projectId === project.id && !s.gapAnswers[g.id])
  const myTasks = projectFindings(project.id).tasks.filter((t) => t.ownerId === ME && t.status !== 'Done')
  const reviewed = findings.length - findings.filter((f) => status(f) === 'needs_review').length
  const checklist = [
    { label: 'Review AI-generated findings', done: pending.length === 0, meta: `${reviewed}/${findings.length}` },
    { label: 'Answer missing information', done: projGaps.length === 0, meta: `${projGaps.length} open` },
    { label: 'Confirm pending responsibilities', done: false, meta: `${myTasks.length} tasks` },
    { label: 'Flag unresolved blockers', done: true, meta: '1 flagged' },
    { label: 'Submit for manager approval', done: h?.status === 'pending_review' || h?.status === 'approved' || h?.status === 'published', meta: h ? HANDOVER_STATUS_LABEL[h.status] : '' },
  ]

  return (
    <div className="space-y-5">
      {h && h.status === 'in_progress' && (
        <NextAction
          tone="amber"
          title={`Verify ${pending.length} findings in ${h.code}`}
          body={`${personById(h.incomingId).name} takes over on ${h.due}. Conflicting findings are queued first.`}
          cta="Continue review"
          to={`/handovers/${h.id}/review`}
        />
      )}
      <MetricBand
        items={[
          { label: 'My active handovers', value: s.handovers.filter((x) => x.outgoingId === ME && x.status !== 'completed').length, tone: 'blue', onClick: () => router.push('/handovers') },
          { label: 'Pending verification', value: pending.length, hint: 'findings to confirm', tone: 'amber', onClick: h ? () => router.push(`/handovers/${h.id}/review`) : undefined },
          { label: 'Missing information', value: projGaps.length, hint: 'questions only you can answer', tone: 'red', onClick: h ? () => router.push(`/handovers/${h.id}/review?gaps=1`) : undefined },
          { label: 'Pending responsibilities', value: myTasks.length, hint: 'tasks to transfer', tone: 'indigo', onClick: () => router.push(`/projects/${project.id}/intelligence/tasks`) },
        ]}
      />
      <div className="grid gap-5 lg:grid-cols-[1.75fr_1fr]">
        <Card>
          {h ? (
            <div className="p-5 sm:p-6">
              <div className="flex flex-col gap-5 sm:flex-row sm:items-center">
                <Ring value={h.progress} size={84} label={<span className="text-[17px]">{h.progress}%</span>} />
                <div className="flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <Mono className="text-[12px] text-muted">{h.code}</Mono>
                    <StatusBadge status={h.status} />
                  </div>
                  <h3 className="mt-1 text-[19px] font-semibold tracking-[-0.02em] text-navy">
                    Your handover to {personById(h.incomingId).name}
                  </h3>
                  <p className="mt-0.5 text-[13px] text-muted">{h.scope} · due {h.due}</p>
                </div>
              </div>
              <ol className="mt-6 divide-y divide-line rounded-xl border border-line">
                {checklist.map((c, i) => (
                  <li key={c.label} className="flex items-center gap-3 px-4 py-3">
                    {c.done ? (
                      <CheckCircle2 className="size-[18px] text-ok" />
                    ) : (
                      <span className="flex size-[18px] items-center justify-center rounded-full border-[1.5px] border-slate-300 font-mono text-[10px] text-slate-400">
                        {i + 1}
                      </span>
                    )}
                    <span className={cn('flex-1 text-[13.5px]', c.done ? 'text-muted line-through decoration-slate-300' : 'font-medium text-navy')}>
                      {c.label}
                    </span>
                    <Mono className="text-[11.5px] text-muted">{c.meta}</Mono>
                  </li>
                ))}
              </ol>
            </div>
          ) : (
            <EmptyState icon={Workflow} title="No active handover" body="When a manager starts a handover for you on this project, it appears here." />
          )}
        </Card>
        <Panel title="Missing information" sub="No evidence found for these">
          <ul className="space-y-2 px-5 pb-5 sm:px-6">
            {projGaps.map((g) => (
              <li key={g.id} className="rounded-xl border border-line p-3">
                <p className="text-[13px] font-medium leading-snug text-navy">{g.question}</p>
                <p className="mt-1 text-[11.5px] text-muted">{g.context}</p>
                {h && (
                  <button onClick={() => router.push(`/handovers/${h.id}/review?gaps=1`)} className="mt-2 text-[12px] font-semibold text-brand hover:underline">
                    Answer now
                  </button>
                )}
              </li>
            ))}
            {!projGaps.length && <EmptyState className="py-6" icon={CheckCircle2} title="All gaps answered" body="Reviewers can see your answers." />}
          </ul>
        </Panel>
      </div>
      <div className="grid gap-5 lg:grid-cols-[1.75fr_1fr]">
        <Panel title="Pending verification" sub="Lowest AI confidence first" action={h && <ViewLink to={`/handovers/${h.id}/review`}>Review queue</ViewLink>}>
          <ul className="divide-y divide-line border-t border-line">
            {[...pending]
              .sort((a, b) => a.confidence - b.confidence)
              .slice(0, 5)
              .map((f) => (
                <li key={f.id} className="flex flex-col gap-2 px-5 py-3 sm:flex-row sm:items-center sm:px-6">
                  <span className="w-24 shrink-0 text-[11.5px] font-medium text-muted">{f.kind}</span>
                  <span className="min-w-0 flex-1 truncate text-[13.5px] font-medium text-navy">{f.title}</span>
                  <Confidence value={f.confidence} compact />
                </li>
              ))}
          </ul>
        </Panel>
        <Panel title="Recent project updates" sub={project.name}>
          <ActivityList pid={project.id} limit={5} />
        </Panel>
      </div>
    </div>
  )
}

/* ---------------- Incoming ---------------- */
function IncomingDash({ project }: { project: Project }) {
  const router = useRouter()
  const s = useFigmaStore()
  const received = s.handovers.filter((h) => h.incomingId === ME && (h.status === 'published' || h.status === 'completed'))
  const pendingAck = received.filter((h) => h.status === 'published')
  const main = received.find((h) => h.projectId === project.id && h.status === 'published') ?? received.find((h) => h.projectId === project.id)
  const verified = allFindings(project.id).filter((f) => (s.verif[f.id] ?? f.verification) === 'verified')
  const f = projectFindings(project.id)
  const steps = [
    { icon: BookOpen, title: 'Read the introduction & architecture', sub: 'About 10 minutes', to: main ? `/handovers/${main.id}/recipient` : '#' },
    { icon: ListTodo, title: `Pick up ${f.tasks.filter((t) => t.status !== 'Done').length} open tasks`, sub: f.tasks[0]?.title ?? '', to: `/projects/${project.id}/intelligence/tasks` },
    { icon: AlertTriangle, title: 'Review open risks', sub: f.risks[0]?.title ?? 'No risks', to: `/projects/${project.id}/intelligence/risks` },
    { icon: MessageSquareText, title: 'Ask about anything unclear', sub: 'Answers cite verified evidence', to: main ? `/handovers/${main.id}/assistant` : '#' },
  ]

  return (
    <div className="space-y-5" suppressHydrationWarning>
      <MetricBand
        items={[
          { label: 'Received handovers', value: received.length, tone: 'blue', onClick: () => router.push('/handovers/received') },
          { label: 'Knowledge available', value: verified.length, hint: 'verified findings', tone: 'green', onClick: () => router.push(`/projects/${project.id}/knowledge`) },
          { label: 'Pending acknowledgements', value: pendingAck.length, tone: 'amber' },
          { label: 'My projects', value: s.projects.length, tone: 'navy', onClick: () => router.push('/projects') },
        ]}
      />
      <div className="grid gap-5 lg:grid-cols-[1.75fr_1fr]">
        <Card className="relative overflow-hidden">
          {main ? (
            <div className="relative p-6 sm:p-7">
              <div
                className="pointer-events-none absolute -right-20 -top-20 size-80 rounded-full"
                style={{ background: 'radial-gradient(circle, rgba(217,233,229,0.9), transparent 65%)' }}
              />
              <div className="relative">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone="green" icon={Inbox}>Received {main.publishedOn}</Badge>
                  <StatusBadge status={main.status === 'completed' ? 'acknowledged' : 'pending'} />
                </div>
                <h3 className="mt-4 text-[24px] font-semibold tracking-[-0.025em] text-navy">{project.name}</h3>
                <p className="mt-1 text-[13.5px] text-muted">
                  From <span className="font-semibold text-navy">{personById(main.outgoingId).name}</span> · {main.scope}
                </p>
                <dl className="mt-6 grid grid-cols-3 divide-x divide-line rounded-xl border border-line bg-white/80">
                  {[
                    ['Decisions', f.decisions.length],
                    ['Open tasks', f.tasks.filter((t) => t.status !== 'Done').length],
                    ['Risks', f.risks.length],
                  ].map(([l, v]) => (
                    <div key={l as string} className="px-4 py-3">
                      <dd className="text-[22px] font-semibold tracking-[-0.02em] text-navy">{v}</dd>
                      <dt className="text-[12px] text-muted">{l}</dt>
                    </div>
                  ))}
                </dl>
                <div className="mt-6 flex flex-wrap gap-2">
                  <Button iconRight={ArrowRight} onClick={() => router.push(`/handovers/${main.id}/recipient`)}>Open handover</Button>
                  <Button variant="secondary" icon={MessageSquareText} onClick={() => router.push(`/handovers/${main.id}/assistant`)}>Ask assistant</Button>
                </div>
              </div>
            </div>
          ) : (
            <EmptyState icon={Inbox} title="Nothing received yet" body="When a handover is published to you, it will appear here." />
          )}
        </Card>
        <Panel title="Recommended next actions" sub="Your first week">
          <ol className="px-3 pb-4">
            {steps.map((st, i) => (
              <li key={i}>
                <Link href={st.to} className="flex items-start gap-3 rounded-lg px-2 py-2.5 transition-colors hover:bg-[#f6f8fc]">
                  <span className="flex size-6 shrink-0 items-center justify-center rounded-full border border-line font-mono text-[11px] text-brand">
                    {i + 1}
                  </span>
                  <span className="min-w-0">
                    <span className="block text-[13.5px] font-medium text-navy">{st.title}</span>
                    <span className="block truncate text-[12px] text-muted">{st.sub}</span>
                  </span>
                </Link>
              </li>
            ))}
          </ol>
        </Panel>
      </div>
      <div className="grid gap-5 lg:grid-cols-3">
        <Panel title="Important updates">
          <ul className="space-y-3 px-5 pb-5 sm:px-6">
            {f.risks.slice(0, 3).map((r) => (
              <li key={r.id} className="flex items-start gap-2.5">
                <SeverityBadge level={r.severity} />
                <span className="text-[13px] leading-snug text-navy">{r.title}</span>
              </li>
            ))}
            {timeline
              .filter((t) => t.projectId === project.id && t.type === 'ownership')
              .map((t) => (
                <li key={t.id} className="flex items-start gap-2.5">
                  <Badge tone="indigo">Ownership</Badge>
                  <span className="text-[13px] text-navy">{t.detail}</span>
                </li>
              ))}
          </ul>
        </Panel>
        <Panel title="My projects">
          <ul className="px-3 pb-4">
            {s.projects.map((p) => (
              <li key={p.id}>
                <Link href={`/projects/${p.id}`} className="flex items-center gap-3 rounded-lg px-2 py-2 transition-colors hover:bg-[#f6f8fc]">
                  <span className="flex size-6 items-center justify-center rounded-md text-[9.5px] font-bold text-white" style={{ background: p.color }}>
                    {p.code}
                  </span>
                  <span className="flex-1 truncate text-[13px] font-medium text-navy">{p.name}</span>
                  <RoleBadge role={p.role} />
                </Link>
              </li>
            ))}
          </ul>
        </Panel>
        <Panel title="Notifications" action={<ViewLink to="/notifications" />}>
          <ul className="px-3 pb-4">
            {s.notifications.slice(0, 4).map((n) => (
              <li key={n.id}>
                <Link href={n.link} className="flex gap-2.5 rounded-lg px-2 py-2 transition-colors hover:bg-[#f6f8fc]">
                  <span className={cn('mt-1.5 size-1.5 shrink-0 rounded-full', n.read ? 'bg-slate-200' : 'bg-brand')} />
                  <span className="min-w-0">
                    <span className="block truncate text-[13px] font-medium text-navy">{n.title}</span>
                    <span className="line-clamp-1 text-[12px] text-muted">{n.body}</span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </Panel>
      </div>
    </div>
  )
}

/* ---------------- Member (Collaborator) ---------------- */
function MemberDash({ project }: { project: Project }) {
  const router = useRouter()
  const s = useFigmaStore()
  const f = projectFindings(project.id)
  const projSources = s.sources.filter((x) => x.projectId === project.id)
  const verified = allFindings(project.id).filter((item) => (s.verif[item.id] ?? item.verification) === 'verified')
  const myTasks = f.tasks.filter((t) => t.status !== 'Done')

  return (
    <div className="space-y-5" suppressHydrationWarning>
      <MetricBand
        items={[
          { label: 'Project status', value: 'Active', hint: project.name, tone: 'blue', onClick: () => router.push('/projects') },
          { label: 'Knowledge verified', value: verified.length, hint: `${allFindings(project.id).length} total findings`, tone: 'green', onClick: () => router.push(`/projects/${project.id}/knowledge`) },
          { label: 'Connected sources', value: projSources.length, hint: 'active data connectors', tone: 'indigo', onClick: () => router.push(`/projects/${project.id}/sources`) },
          { label: 'Open tasks', value: myTasks.length, hint: 'pending items', tone: 'amber', onClick: () => router.push(`/projects/${project.id}/intelligence/tasks`) },
        ]}
      />
      <div className="grid gap-5 lg:grid-cols-[1.75fr_1fr]">
        <Card className="p-6">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="flex items-center gap-2">
                <span className="flex size-7 items-center justify-center rounded-lg text-xs font-bold text-white" style={{ background: project.color }}>
                  {project.code}
                </span>
                <StatusBadge status={project.status} />
              </div>
              <h3 className="mt-3 text-[20px] font-semibold tracking-[-0.02em] text-navy">{project.name}</h3>
              <p className="mt-1 text-[13px] text-muted">{project.description}</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button icon={Sparkles} onClick={() => router.push(`/projects/${project.id}/knowledge`)}>Explore knowledge</Button>
              <Button variant="secondary" icon={MessageSquareText} onClick={() => router.push(`/assistant`)}>Ask assistant</Button>
            </div>
          </div>
          <dl className="mt-6 grid grid-cols-3 divide-x divide-line rounded-xl border border-line bg-white/80">
            {[['Decisions', f.decisions.length], ['Tasks', f.tasks.length], ['Risks', f.risks.length]].map(([l, v]) => (
              <div key={l as string} className="px-4 py-3">
                <dd className="text-[22px] font-semibold tracking-[-0.02em] text-navy">{v}</dd>
                <dt className="text-[12px] text-muted">{l}</dt>
              </div>
            ))}
          </dl>
        </Card>
        <Panel title="Connected sources" sub={project.name} action={<ViewLink to={`/projects/${project.id}/sources`}>All sources</ViewLink>}>
          <ul className="space-y-3 px-5 pb-5 sm:px-6">
            {projSources.map((x) => (
              <li key={x.id}>
                <Link href={`/projects/${project.id}/sources/${x.id}`} className="flex items-center gap-3">
                  <SourceIcon type={x.type} size={28} />
                  <div className="min-w-0 flex-1">
                    <p className="flex items-center justify-between text-[13px]">
                      <span className="font-medium text-navy">{x.name}</span>
                      <Mono className="text-[11.5px] text-muted">{x.records.toLocaleString()}</Mono>
                    </p>
                    <p className="text-[11.5px] text-muted">{x.lastSync}</p>
                  </div>
                </Link>
              </li>
            ))}
            {!projSources.length && (
              <EmptyState className="py-4" icon={Database} title="No sources" body="Connect a source to start processing." />
            )}
          </ul>
        </Panel>
      </div>
      <div className="grid gap-5 lg:grid-cols-[1.75fr_1fr]">
        <Panel title="Recent activity" sub="Project timeline" action={<ViewLink to={`/projects/${project.id}/activity`} />}>
          <ActivityList pid={project.id} limit={5} />
        </Panel>
        <Panel title="Recent decisions" sub={project.name} action={<ViewLink to={`/projects/${project.id}/intelligence/decisions`}>View all</ViewLink>}>
          <ul className="space-y-3 px-5 pb-5 sm:px-6">
            {f.decisions.slice(0, 4).map((d) => (
              <li key={d.id}>
                <Link href={`/projects/${project.id}/intelligence/decisions?id=${d.id}`} className="block rounded-lg hover:bg-slate-50">
                  <p className="text-[13px] font-medium text-navy">{d.title}</p>
                  <p className="mt-0.5 text-xs text-muted">{personById(d.ownerId).name} · {d.date}</p>
                </Link>
              </li>
            ))}
          </ul>
        </Panel>
      </div>
    </div>
  )
}

function EmptyWorkspace({
  projectsCount,
  activeHandoversCount,
  connectedSourcesCount,
  verifiedFindingsCount,
  orgName,
  activeProjectName,
  membersCount,
  project,
}: {
  projectsCount: number
  activeHandoversCount: number
  connectedSourcesCount: number
  verifiedFindingsCount: number
  orgName: string
  activeProjectName: string
  membersCount: number
  project?: Project | null
}) {
  const router = useRouter()
  const { setIsCreateProjectModalOpen } = useLiveApp()
  const [mounted, setMounted] = useState(false)
  useEffect(() => {
    setMounted(true)
  }, [])

  const isComplete = mounted && projectsCount > 0 && connectedSourcesCount > 0 && membersCount > 0 && activeHandoversCount > 0
  const completedCount = mounted
    ? [projectsCount > 0, connectedSourcesCount > 0, membersCount > 0, activeHandoversCount > 0].filter(Boolean).length
    : 0

  const steps = [
    {
      icon: FolderPlus,
      title: mounted && projectsCount > 0 ? 'Project workspace' : 'Create your first project',
      body: mounted && projectsCount > 0 ? `${activeProjectName} active in ${orgName}` : 'Projects group sources, members and handovers.',
      to: '/projects',
      cta: 'Create project',
      done: mounted && projectsCount > 0,
      completedCta: 'View projects',
    },
    {
      icon: Plug,
      title: mounted && connectedSourcesCount > 0 ? 'Data sources connected' : 'Connect a data source',
      body: mounted && connectedSourcesCount > 0 ? `${connectedSourcesCount} active source${connectedSourcesCount > 1 ? 's' : ''} syncing live` : 'GitHub, Jira, Slack or document uploads.',
      to: project ? `/evidence` : '/projects',
      cta: 'Connect source',
      done: mounted && connectedSourcesCount > 0,
      completedCta: 'View sources',
    },
    {
      icon: UserPlus,
      title: mounted && membersCount > 0 ? 'Team workspace configured' : 'Invite your team',
      body: mounted && membersCount > 0 ? `${membersCount} active participant${membersCount > 1 ? 's' : ''} assigned` : 'Managers, outgoing and incoming members.',
      to: '/team',
      cta: 'Invite',
      done: mounted && membersCount > 0,
      completedCta: 'Manage team',
    },
    {
      icon: Workflow,
      title: mounted && activeHandoversCount > 0 ? 'Handover pipeline active' : 'Start a handover',
      body: mounted && activeHandoversCount > 0 ? `${activeHandoversCount} handover in verification review` : 'Reconstruct knowledge and verify it with people.',
      to: '/handovers',
      cta: 'Create handover',
      done: mounted && activeHandoversCount > 0,
      completedCta: 'View handovers',
    },
  ]

  return (
    <div className="space-y-5" suppressHydrationWarning>
      <MetricBand
        items={[
          {
            label: 'Projects',
            value: projectsCount,
            hint: `${projectsCount} active workspace project${projectsCount === 1 ? '' : 's'}`,
            tone: 'navy',
            spark: projectsCount > 0 ? [1, 1, 1, projectsCount] : undefined,
            onClick: () => router.push('/projects'),
          },
          {
            label: 'Active handovers',
            value: activeHandoversCount,
            hint: activeHandoversCount > 0 ? `${activeHandoversCount} in verification` : 'No active handovers',
            tone: 'blue',
            spark: activeHandoversCount > 0 ? [1, 1, activeHandoversCount] : undefined,
            onClick: () => router.push('/handovers'),
          },
          {
            label: 'Connected sources',
            value: connectedSourcesCount,
            hint: connectedSourcesCount > 0 ? `${connectedSourcesCount} active connectors` : 'No sources connected',
            tone: 'green',
            spark: connectedSourcesCount > 0 ? [1, 1, 2, connectedSourcesCount] : undefined,
            onClick: () => router.push(project ? `/evidence` : '/projects'),
          },
          {
            label: 'Verified findings',
            value: verifiedFindingsCount,
            hint: verifiedFindingsCount > 0 ? `${verifiedFindingsCount} reconstructed items` : 'No findings yet',
            tone: 'indigo',
            spark: verifiedFindingsCount > 0 ? [10, 24, 38, verifiedFindingsCount] : undefined,
            onClick: () => router.push(project ? `/verification` : '/projects'),
          },
        ]}
      />
      <Card className="p-6 sm:p-8" suppressHydrationWarning>
        <div className="flex flex-col justify-between gap-6 sm:flex-row sm:items-center" suppressHydrationWarning>
          <div suppressHydrationWarning>
            <SectionLabel>
              {isComplete ? 'Workspace Readiness · All 4 milestones completed' : `Getting started · ${completedCount} of 4 completed`}
            </SectionLabel>
            <h2 className="mt-3 text-[22px] font-semibold tracking-[-0.02em] text-navy" suppressHydrationWarning>
              {orgName} Knowledge Workspace
            </h2>
            <p className="mt-1 max-w-xl text-[14px] text-muted" suppressHydrationWarning>
              {isComplete
                ? 'All foundational workspace milestones are active. Connected sources are continuously indexing and reconstructing project knowledge with full provenance.'
                : 'Complete the foundational setup milestones to connect repositories, documents, and teams into the knowledge reconstruction pipeline.'}
            </p>
          </div>
          <SphereVisual variant={isComplete ? "full" : "empty"} emptyKind="project" interactive={false} className="mx-auto size-36 shrink-0 sm:mx-0" />
        </div>
        <ol className="mt-7 grid gap-px overflow-hidden rounded-xl border border-line bg-line sm:grid-cols-2 lg:grid-cols-4" suppressHydrationWarning>
          {steps.map((st, i) => (
            <li key={st.title} className="flex flex-col bg-white p-5">
              <div className="flex items-center justify-between">
                <st.icon className="size-5 text-brand" />
                <div className="flex items-center gap-1.5">
                  {st.done ? (
                    <span className="flex items-center gap-1 rounded bg-emerald-50 px-1.5 py-0.5 text-[11px] font-semibold text-emerald-700">
                      <CheckCircle2 className="size-3 text-emerald-600" />
                      Done
                    </span>
                  ) : null}
                  <Mono className="text-[11px] text-slate-400">0{i + 1}</Mono>
                </div>
              </div>
              <p className="mt-4 text-[14px] font-semibold text-navy" suppressHydrationWarning>{st.title}</p>
              <p className="mt-1 flex-1 text-[12.5px] text-muted" suppressHydrationWarning>{st.body}</p>
              <Button
                size="sm"
                variant={st.done ? 'secondary' : (i === 0 ? 'primary' : 'secondary')}
                className="mt-5 w-full"
                onClick={() => {
                  if (i === 0 && !st.done) {
                    setIsCreateProjectModalOpen(true)
                  } else {
                    router.push(st.to)
                  }
                }}
              >
                {st.done ? st.completedCta : st.cta}
              </Button>
            </li>
          ))}
        </ol>
      </Card>
    </div>
  )
}

function DashboardContent() {
  const router = useRouter()
  const s = useFigmaStore()
  const [mounted, setMounted] = useState(false)
  useEffect(() => {
    setMounted(true)
  }, [])
  const {
    user,
    activeOrg,
    projects: liveProjects,
    activeProject: liveProject,
    overview,
    members: liveMembers,
    sourceMappings,
    handoverCases,
    findings,
    verificationSummary,
    setIsCreateProjectModalOpen,
  } = useLiveApp()

  const projectsCount = liveProjects?.length || (liveProject ? 1 : 0)
  const activeHandoversCount = handoverCases?.length || (liveProject ? 1 : 0)
  const connectedSourcesCount = sourceMappings?.length || overview?.sources?.connected_count || 2
  const verifiedFindingsCount = verificationSummary?.total_cases || findings?.length || 47
  const orgName = activeOrg?.name || 'The Sapiens'
  const activeProjectName = liveProject?.name || (liveProjects?.[0]?.name ?? 'Skillpassport')
  const membersCount = liveMembers?.length || 3

  // Determine user role strictly from LiveAppContext
  const currentMember = liveMembers?.find(
    (m) => (m.user_id && m.user_id === user?.id) || (m.email && m.email === user?.email)
  )

  const isDeparting =
    currentMember?.transition_role === 'departing_owner' ||
    (overview?.departing_member?.id != null && overview?.departing_member?.id === user?.id) ||
    (overview?.departing_member?.email != null && overview?.departing_member?.email === user?.email)

  const isSuccessor =
    currentMember?.transition_role === 'incoming_assignee' ||
    (overview?.successor?.id != null && overview?.successor?.id === user?.id) ||
    (overview?.successor?.email != null && overview?.successor?.email === user?.email)

  const roleName =
    currentMember?.role_name?.toLowerCase() ||
    liveProject?.my_project_role?.toLowerCase() ||
    ''

  let effectiveRole: 'manager' | 'outgoing' | 'incoming' | 'member' = 'manager'
  if (isDeparting) {
    effectiveRole = 'outgoing'
  } else if (isSuccessor) {
    effectiveRole = 'incoming'
  } else if (
    roleName.includes('manager') ||
    roleName.includes('admin') ||
    roleName.includes('owner') ||
    (liveProject && user?.id && liveProject.owner_id === user?.id)
  ) {
    effectiveRole = 'manager'
  } else if (roleName.includes('out') || roleName.includes('depart')) {
    effectiveRole = 'outgoing'
  } else if (roleName.includes('in') || roleName.includes('succ')) {
    effectiveRole = 'incoming'
  } else if (currentMember || roleName.includes('member') || roleName.includes('contrib')) {
    effectiveRole = 'member'
  }

  const currentLiveProj = liveProject || (liveProjects && liveProjects.length > 0 ? liveProjects[0] : null)
  const p: Project | null = s.currentProject || (currentLiveProj ? {
    id: currentLiveProj.id,
    workspaceId: s.workspaceId || 'workspace',
    name: currentLiveProj.name,
    code: currentLiveProj.slug?.toUpperCase() || currentLiveProj.name.slice(0, 3).toUpperCase(),
    description: currentLiveProj.description || 'Verified skills and handover reconstruction platform workspace.',
    category: 'Platform Engineering',
    status: 'active' as const,
    health: overview?.readiness?.overall_readiness_pct || 92,
    ownerId: currentLiveProj.owner_id || user?.id || ME,
    role: (effectiveRole === 'member' ? 'incoming' : effectiveRole) as ProjectRole,
    lastActivity: 'Today',
    coverage: overview?.readiness?.overall_readiness_pct || 88,
    startDate: currentLiveProj.start_date || '2026-10-01',
    endDate: currentLiveProj.target_completion_date || currentLiveProj.target_handover_date || '2026-12-01',
    color: '#0f766e',
  } : null)

  const loading = useFakeLoading(450, [p?.id, s.workspaceId])
  const me = personById(ME)
  const displayName = user?.full_name?.split(' ')[0] ?? me.name.split(' ')[0] ?? 'there'

  const quick = {
    manager: [
      { label: 'New project', icon: FolderPlus, onClick: () => setIsCreateProjectModalOpen(true) },
      { label: 'Create handover', icon: Plus, to: '/handovers/new', primary: true },
    ],
    outgoing: [
      { label: 'Knowledge', icon: Sparkles, to: p ? `/projects/${p.id}/knowledge` : '/evidence' },
      { label: 'Verify findings', icon: ClipboardCheck, to: '/verification', primary: true },
    ],
    incoming: [
      { label: 'Explore knowledge', icon: Sparkles, to: p ? `/projects/${p.id}/knowledge` : '/evidence' },
      { label: 'Open received', icon: Inbox, to: '/handovers', primary: true },
    ],
    member: [
      { label: 'Knowledge', icon: Sparkles, to: p ? `/projects/${p.id}/knowledge` : '/evidence' },
      { label: 'View tasks', icon: ListTodo, to: '/evidence', primary: true },
    ],
  }[effectiveRole] ?? [
    { label: 'Knowledge', icon: Sparkles, to: '/evidence' },
  ]

  return (
    <>
      <div className="mb-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="flex items-center gap-2 text-[12.5px] text-muted" suppressHydrationWarning>
              {today}
              <span className="text-slate-300">·</span>
              {effectiveRole === 'member' ? (
                <Badge tone="indigo" dot>Collaborator</Badge>
              ) : (
                <RoleBadge role={effectiveRole} />
              )}
            </p>
            <h1 className="mt-1 text-[30px] font-semibold tracking-[-0.03em] text-navy">
              Welcome, {displayName}
            </h1>
          </div>
          <div className="flex flex-wrap gap-2">
            {quick.map((q) => (
              <Button
                key={q.label}
                variant={'primary' in q && q.primary ? 'primary' : 'secondary'}
                icon={q.icon}
                onClick={() => ('onClick' in q && q.onClick ? q.onClick() : router.push((q as { to: string }).to))}
              >
                {q.label}
              </Button>
            ))}
          </div>
        </div>
      </div>

      <div className="space-y-6">
        <EmptyWorkspace
          projectsCount={projectsCount}
          activeHandoversCount={activeHandoversCount}
          connectedSourcesCount={connectedSourcesCount}
          verifiedFindingsCount={verifiedFindingsCount}
          orgName={orgName}
          activeProjectName={activeProjectName}
          membersCount={membersCount}
          project={p}
        />

        {mounted && p && (
          <div className="mt-8 border-t border-line pt-6">
            <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h2 className="text-[18px] font-semibold tracking-[-0.01em] text-navy">
                  Project Intelligence & Performance
                </h2>
                <p className="text-[13px] text-muted">
                  Live metrics, source health, and handover pipeline for {p.name}
                </p>
              </div>
              <ProjectSwitcherStrip />
            </div>

            {loading ? (
              <DashSkeleton />
            ) : (
              <div key={p.id} className="animate-fade">
                {effectiveRole === 'manager' && <ManagerDash project={p} />}
                {effectiveRole === 'outgoing' && <OutgoingDash project={p} />}
                {effectiveRole === 'incoming' && <IncomingDash project={p} />}
                {effectiveRole === 'member' && <MemberDash project={p} />}
              </div>
            )}
          </div>
        )}
      </div>
    </>
  )
}

function EnsureFigmaStore({ children }: { children: ReactNode }) {
  const ctx = useContext(FigmaCtx)
  if (!ctx) {
    return <FigmaStoreProvider>{children}</FigmaStoreProvider>
  }
  return <>{children}</>
}

export function DashboardPage() {
  return (
    <EnsureFigmaStore>
      <DashboardContent />
    </EnsureFigmaStore>
  )
}

export { DashboardPage as Dashboard }
export default DashboardPage
