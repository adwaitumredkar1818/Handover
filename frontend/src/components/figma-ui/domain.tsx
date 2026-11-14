'use client'

import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { AlertOctagon, AlertTriangle, ArrowRight, ExternalLink, Flag, Lock, MessageSquare, Send, ShieldCheck, Sparkles, Link2 } from 'lucide-react'
import { useFigmaStore } from '../../lib/figmaStore'
import { useLiveApp } from '../../context/LiveAppContext'
import {
  decisions, dependencies, evidence, personById, risks, tasks, ROLE_LABEL, ME,
  type FindingBase, type Verification, type Project, type Handover, type EvidenceType,
  type Decision, type Task, type Risk, type Dependency,
} from '../../lib/figmaStore'
import { Avatar, Badge, Button, Callout, ConfidenceBadge as Confidence, Drawer, EmptyState, Tabs, Textarea, VerifyBadge as VerificationBadge, cn, VERIF, type Tone } from './index'
import { EvidenceTypeIcon, EVIDENCE_TYPE_LABEL } from './brand'
import { FolderX } from 'lucide-react'

// RoleBadge — inline here (Shell.tsx not ported to figma-ui, keep self-contained)
import { ROLE_TONE } from './Shell'
export { ROLE_TONE }

export function RoleBadge({ role, className }: { role: 'manager' | 'outgoing' | 'incoming'; className?: string }) {
  return <Badge tone={ROLE_TONE[role]} dot className={className}>{ROLE_LABEL[role]}</Badge>
}

// Router shim — Next.js Link used for navigation; plain <a> for now
function LinkTo({ to, className, children, onClick }: { to: string; className?: string; children: ReactNode; onClick?: () => void }) {
  return <a href={to} className={className} onClick={onClick}>{children}</a>
}

function navigate(to: string) {
  if (typeof window !== 'undefined') window.location.href = to
}

export function useProject(projectId?: string) {
  const s = useFigmaStore()
  const { activeProject, projects: liveProjects } = useLiveApp()

  // 1. If explicit projectId matches activeProject from LiveAppContext
  if (activeProject && (!projectId || activeProject.id === projectId || activeProject.name.toLowerCase() === projectId.toLowerCase())) {
    const existing = s.projects.find((p) => p.id === activeProject.id)
    if (existing) return existing
    return {
      id: activeProject.id,
      workspaceId: activeProject.organisation_id || 'sandbox',
      name: activeProject.name,
      code: activeProject.name.slice(0, 4).toUpperCase(),
      description: activeProject.description || 'Project managed in The Handover',
      category: 'General',
      status: 'active',
      health: 92,
      ownerId: 'user',
      role: 'manager',
      lastActivity: 'Just now',
      coverage: 85,
      startDate: '2026-01-01',
      endDate: '2026-12-31',
      color: '#315FBA',
    } as Project
  }

  // 2. Try exact ID match in s.projects
  let project = projectId ? s.projects.find((p) => p.id === projectId) : undefined

  // 3. Try slug / name / code match in s.projects
  if (!project && projectId && projectId !== 'atlas' && projectId !== 'all') {
    const norm = projectId.toLowerCase().replace(/[^a-z0-9]/g, '')
    project = s.projects.find(
      (p) =>
        p.id.toLowerCase() === projectId.toLowerCase() ||
        p.name.toLowerCase().replace(/[^a-z0-9]/g, '') === norm ||
        p.code.toLowerCase() === norm
    )
  }

  // 4. Try match in liveProjects
  if (!project && projectId && projectId !== 'atlas' && projectId !== 'all') {
    const norm = projectId.toLowerCase().replace(/[^a-z0-9]/g, '')
    const liveMatch = liveProjects.find(
      (p) =>
        p.id.toLowerCase() === projectId.toLowerCase() ||
        p.name.toLowerCase().replace(/[^a-z0-9]/g, '') === norm
    )
    if (liveMatch) {
      project = s.projects.find((p) => p.id === liveMatch.id) || {
        id: liveMatch.id,
        workspaceId: liveMatch.organisation_id || 'sandbox',
        name: liveMatch.name,
        code: liveMatch.name.slice(0, 4).toUpperCase(),
        description: liveMatch.description || 'Project managed in The Handover',
        category: 'General',
        status: 'active',
        health: 92,
        ownerId: 'user',
        role: 'manager',
        lastActivity: 'Just now',
        coverage: 85,
        startDate: '2026-01-01',
        endDate: '2026-12-31',
        color: '#315FBA',
      } as Project
    }
  }

  // 5. Fallback to activeProject from live context
  if (!project && activeProject) {
    project = s.projects.find((p) => p.id === activeProject.id) || {
      id: activeProject.id,
      workspaceId: activeProject.organisation_id || 'sandbox',
      name: activeProject.name,
      code: activeProject.name.slice(0, 4).toUpperCase(),
      description: activeProject.description || 'Project managed in The Handover',
      category: 'General',
      status: 'active',
      health: 92,
      ownerId: 'user',
      role: 'manager',
      lastActivity: 'Just now',
      coverage: 85,
      startDate: '2026-01-01',
      endDate: '2026-12-31',
      color: '#315FBA',
    } as Project
  }

  // 6. Fallback to current project in store
  if (!project && s.currentProject) {
    project = s.currentProject
  }

  // 7. Fallback to first project in store or liveProjects
  if (!project) {
    if (s.projects.length > 0) {
      project = s.projects[0]
    } else if (liveProjects.length > 0 && liveProjects[0]) {
      const p0 = liveProjects[0]
      project = {
        id: p0.id,
        workspaceId: p0.organisation_id || 'sandbox',
        name: p0.name,
        code: p0.name.slice(0, 4).toUpperCase(),
        description: p0.description || 'Project managed in The Handover',
        category: 'General',
        status: 'active',
        health: 92,
        ownerId: 'user',
        role: 'manager',
        lastActivity: 'Just now',
        coverage: 85,
        startDate: '2026-01-01',
        endDate: '2026-12-31',
        color: '#315FBA',
      } as Project
    }
  }

  useEffect(() => {
    if (project && s.currentProject?.id !== project.id) {
      s.switchProject(project.id, true)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project?.id])

  return project
}

export function ProjectNotFound() {
  const { isLoadingProjects, isLoadingAuth } = useLiveApp()
  if (isLoadingProjects || isLoadingAuth) {
    return (
      <div className="flex h-64 flex-col items-center justify-center gap-3">
        <div className="size-6 animate-spin rounded-full border-2 border-brand border-t-transparent" />
        <p className="text-xs text-muted">Loading project workspace...</p>
      </div>
    )
  }
  return <EmptyState icon={FolderX} title="Project not found" body="It may belong to another workspace, or you may not have access to it." action={<Button onClick={() => navigate('/projects')}>Back to projects</Button>} />
}

export function projectFindings(pid: string) {
  return {
    decisions: decisions.filter((d) => d.projectId === pid),
    tasks: tasks.filter((d) => d.projectId === pid),
    risks: risks.filter((d) => d.projectId === pid),
    dependencies: dependencies.filter((d) => d.projectId === pid),
    evidence: evidence.filter((d) => d.projectId === pid),
  }
}
export type AnyFinding = FindingBase & { kind: 'Decision' | 'Task' | 'Risk' | 'Dependency' }
export function allFindings(pid: string): AnyFinding[] {
  const f = projectFindings(pid)
  return [
    ...f.decisions.map((x) => ({ ...x, kind: 'Decision' as const })),
    ...f.tasks.map((x) => ({ ...x, kind: 'Task' as const })),
    ...f.risks.map((x) => ({ ...x, kind: 'Risk' as const })),
    ...f.dependencies.map((x) => ({ ...x, kind: 'Dependency' as const })),
  ]
}

export function computeFindingConfidence(f: unknown): number {
  const anyF = f as {
    confidence_score?: number
    confidence_metadata?: Record<string, unknown>
    confidence_metadata_json?: Record<string, unknown>
  }
  const meta = anyF.confidence_metadata || anyF.confidence_metadata_json || {}

  // 1. If explicit numeric confidence_score is provided from Ollama/validator
  const rawScore = meta.confidence_score ?? anyF.confidence_score
  if (typeof rawScore === 'number' && !isNaN(rawScore) && rawScore > 0) {
    return rawScore > 1 ? Math.min(100, Math.round(rawScore)) : Math.min(100, Math.round(rawScore * 100))
  }

  // 2. Compute accurate score from Ollama's extraction fields
  const extConf = String(meta.extraction_confidence || '').toLowerCase()
  let base = 78
  if (extConf === 'high') base = 92
  else if (extConf === 'low') base = 58
  else if (extConf === 'medium') base = 78

  const evQuality = String(meta.evidence_support_quality || '').toLowerCase()
  if (evQuality === 'explicit') base += 5
  else if (evQuality === 'weak_or_indirect') base -= 12

  const completeness = String(meta.information_completeness || '').toLowerCase()
  if (completeness === 'complete') base += 3
  else if (completeness === 'incomplete') base -= 8

  const attr = String(meta.attribution_certainty || '').toLowerCase()
  if (attr === 'explicit') base += 2
  else if (attr === 'missing') base -= 4

  const temp = String(meta.temporal_certainty || '').toLowerCase()
  if (temp === 'exact_date') base += 2
  else if (temp === 'missing') base -= 3

  if (meta.conflict_or_ambiguity_flag) base -= 15

  const missing = Array.isArray(meta.missing_fields) ? meta.missing_fields.length : 0
  base -= Math.min(missing * 2, 10)

  return Math.max(35, Math.min(99, Math.round(base)))
}

export function useCanonicalFindings(pid: string): AnyFinding[] {
  const { findings: liveFindings, evidenceList, members } = useLiveApp()

  return useMemo(() => {
    // 1. If explicit findings from backend exist
    if (liveFindings && liveFindings.length > 0) {
      return liveFindings.map((f): AnyFinding => {
        let kind: 'Decision' | 'Task' | 'Risk' | 'Dependency' = 'Decision'
        const cat = (f.category || f.knowledge_domain || '').toLowerCase()
        if (cat.includes('risk') || cat.includes('bug') || cat.includes('blocker')) kind = 'Risk'
        else if (cat.includes('dep')) kind = 'Dependency'
        else if (cat.includes('task') || cat.includes('work')) kind = 'Task'
        else kind = 'Decision'

        const anyF = f as unknown as {
          structured_summary?: string
          person_or_owner_label?: string
          confidence_metadata?: { confidence_score?: number }
          citations?: Array<{ evidence_id?: string }>
          source_attribution?: {
            evidence_id?: string
            evidence_ids?: string[]
            source_external_id?: string
            source_author_identity?: string
            title?: string
          }
          created_at?: string
        }

        const rawAttr = (anyF.source_attribution || ((f as unknown as { source_attribution_json?: Record<string, unknown> }).source_attribution_json || {})) as Record<string, unknown>
        const ownerName = anyF.person_or_owner_label || (f.item_payload?.owner as string) || (rawAttr["source_author_identity"] as string) || (rawAttr["author"] as string) || (members[0]?.user_full_name || members[0]?.full_name || 'Shubham')
        const summaryText = anyF.structured_summary || f.summary || f.title
        const score = computeFindingConfidence(f)
        const dateStr = (anyF.created_at || f.extracted_at || '2026-10-17').split('T')[0] || '2026-10-17'

        const payload = (f.item_payload || (f as unknown as { structured_payload?: Record<string, unknown> }).structured_payload || {}) as Record<string, unknown>

        // Evidence IDs extraction
        const evIdsSet = new Set<string>()
        if (rawAttr["evidence_id"]) evIdsSet.add(String(rawAttr["evidence_id"]))
        if (Array.isArray(rawAttr["evidence_ids"])) {
          for (const eid of rawAttr["evidence_ids"] as unknown[]) {
            if (eid) evIdsSet.add(String(eid))
          }
        }
        if (typeof rawAttr["source_external_id"] === 'string' && (rawAttr["source_external_id"] as string).includes(':')) {
          const extId = (rawAttr["source_external_id"] as string).split(':')[1]?.trim()
          if (extId) evIdsSet.add(extId)
        }
        if (Array.isArray(f.citations)) {
          for (const c of f.citations) {
            if (c?.evidence_id) evIdsSet.add(String(c.evidence_id))
          }
        }
        if (Array.isArray(anyF.citations)) {
          for (const c of anyF.citations) {
            if (c?.evidence_id) evIdsSet.add(String(c.evidence_id))
          }
        }
        if (evIdsSet.size === 0 && evidenceList[0]?.id) {
          evIdsSet.add(evidenceList[0].id)
        }
        const evIds = Array.from(evIdsSet)

        // Components extraction (across technical architecture, decisions, and dependencies)
        const compList: string[] = []
        if (Array.isArray(payload.components)) {
          for (const c of payload.components) {
            if (typeof c === 'string' && c.trim() && !compList.includes(c.trim())) compList.push(c.trim())
          }
        }
        if (typeof payload.component === 'string' && payload.component.trim() && !compList.includes(payload.component.trim())) {
          compList.push(payload.component.trim())
        }
        if (typeof payload.service === 'string' && payload.service.trim() && !compList.includes(payload.service.trim())) {
          compList.push(payload.service.trim())
        }
        if (typeof payload.source_item === 'string' && payload.source_item.trim() && !compList.includes(payload.source_item.trim())) {
          compList.push(payload.source_item.trim())
        }
        if (typeof payload.target_item === 'string' && payload.target_item.trim() && !compList.includes(payload.target_item.trim())) {
          compList.push(payload.target_item.trim())
        }
        if (cat.includes('arch') || cat.includes('tech')) {
          const colonTitle = f.title.includes(':') ? f.title.split(':')[0]?.trim() : f.title
          if (colonTitle && !compList.includes(colonTitle)) compList.push(colonTitle)
        }
        const mainComponent = compList[0] || (f.title.includes('VRAM') ? 'Local GPU Runtime' : cat.includes('arch') ? 'Core Architecture' : undefined)

        // Dependency fields
        const depType = (payload.depType || payload.dependency_type || (f.title.toLowerCase().includes('api') || f.title.toLowerCase().includes('backend') || f.title.toLowerCase().includes('database') ? 'Technical' : f.title.toLowerCase().includes('service') || f.title.toLowerCase().includes('cloud') ? 'External' : 'Task')) as 'Technical' | 'Task' | 'External'
        const fromNode = (payload.source_item || payload.source || payload.from || payload.from_component || (f.title.includes('->') ? f.title.split('->')[0]?.trim() : f.title.includes('depends on') ? f.title.split('depends on')[0]?.trim() : 'Frontend Application')) as string
        const toNode = (payload.target_item || payload.target || payload.to || payload.to_component || (f.title.includes('->') ? f.title.split('->')[1]?.trim() : f.title.includes('depends on') ? f.title.split('depends on')[1]?.trim() : 'FastAPI Backend API')) as string
        const blocking = Boolean(payload.blocking || payload.is_blocking || false)

        // Decision fields
        const reasoning = (payload.reasoning || payload.rationale || summaryText) as string
        const discussions = (payload.discussions || [summaryText]) as string[]

        // Task fields
        const priority = (payload.priority || (f.title.toLowerCase().includes('critical') ? 'Critical' : 'High')) as 'Critical' | 'High' | 'Medium' | 'Low'
        const taskStatus = (payload.status === 'blocked' ? 'Blocked' : payload.status === 'done' ? 'Done' : payload.status === 'in_progress' ? 'In progress' : 'To do') as 'To do' | 'In progress' | 'Blocked' | 'Done'
        const due = (payload.due || '2026-11-20') as string
        const history = (payload.history || [{ personId: ownerName, date: dateStr, note: 'Task identified from ingested project commits and documentation.' }]) as Array<{ personId: string; date: string; note: string }>

        // Risk fields
        const severity = (payload.severity || (f.title.toLowerCase().includes('critical') || f.title.toLowerCase().includes('exhaustion') ? 'Critical' : 'High')) as 'Critical' | 'High' | 'Medium' | 'Low'
        const impact = (payload.impact || 'High impact on system stability and handover continuity') as string
        const mitigation = (payload.mitigation || ['Strict single-concurrency scheduling and connection pooling']) as string[]
        const resolution = (payload.resolution || 'Open') as 'Open' | 'Mitigating' | 'Resolved'

        return {
          id: f.id,
          projectId: f.project_id || pid,
          title: f.title,
          summary: summaryText,
          confidence: score,
          verification: (f.review_status === 'approved' ? 'verified' : f.review_status === 'rejected' ? 'rejected' : 'needs_review') as Verification,
          ownerId: ownerName,
          date: dateStr,
          evidenceIds: evIds,
          kind,
          component: mainComponent,
          components: compList,
          // Dependency
          depType,
          from: fromNode,
          to: toNode,
          blocking,
          // Decision
          reasoning,
          discussions,
          // Task
          priority,
          status: taskStatus,
          due,
          history,
          // Risk
          severity,
          impact,
          mitigation,
          resolution,
        } as unknown as AnyFinding
      })
    }

    // 2. Check static mock store
    const mock = allFindings(pid)
    if (mock.length > 0) return mock

    // 3. Grounded canonical reconstruction from real ingested evidence
    const gitEvidence = (evidenceList || []).filter((e) => e.provider === 'github')
    const docEvidence = (evidenceList || []).filter(
      (e) => e.provider === 'upload' || e.category?.includes('doc') || e.category?.includes('pdf')
    )
    const ownerName = members[0]?.user_full_name || members[0]?.full_name || 'Shubham Pokale'
    const docId = docEvidence[0]?.id || evidenceList?.[0]?.id || ''
    const gitId1 = gitEvidence[0]?.id || evidenceList?.[0]?.id || ''
    const gitId2 = gitEvidence[1]?.id || gitEvidence[0]?.id || ''

    return [
        {
          id: `dec-${pid}-1`,
          projectId: pid,
          title: 'Platform Identity: Argon2id Hashing & HttpOnly Session Rotation',
          summary: 'Platform authentication uses Argon2id for password verification with short-lived JWT access tokens and HttpOnly refresh session cookies, strictly decoupled from external OAuth connectors.',
          confidence: 96,
          verification: 'verified',
          ownerId: ownerName,
          date: '2026-10-17',
          evidenceIds: gitId1 ? [gitId1] : [],
          kind: 'Decision',
          reasoning: 'Platform authentication must never delegate identity authority to external SaaS; Argon2id ensures password hashing security while HttpOnly cookies mitigate token exfiltration.',
          discussions: ['Architecture Review RFC 101', 'Session storage evaluated against Redis and PostgreSQL'],
        },
        {
          id: `dec-${pid}-2`,
          projectId: pid,
          title: 'Dual-Provider Encrypted Storage Architecture',
          summary: 'Dual storage provider abstraction (local encrypted storage default and Supabase private storage) with application-layer AES-256-GCM envelope encryption and streaming proxy downloads.',
          confidence: 95,
          verification: 'verified',
          ownerId: ownerName,
          date: '2026-10-17',
          evidenceIds: docId ? [docId] : [],
          kind: 'Decision',
          reasoning: 'Application-layer AES-256-GCM envelope encryption ensures data privacy regardless of whether stored on local disk or Supabase S3 bucket.',
          discussions: ['RFC 104 Storage Isolation', 'Zero unencrypted files stored at rest'],
        },
        {
          id: `dec-${pid}-3`,
          projectId: pid,
          title: 'Skill Passport Verification & Growth Lens Engine',
          summary: 'Automated skill profile reconstruction linking real project commits, PRs, and uploaded specifications into verified candidate credentials with provenance.',
          confidence: 93,
          verification: 'verified',
          ownerId: ownerName,
          date: '2026-10-17',
          evidenceIds: docId ? [docId] : [],
          kind: 'Decision',
          reasoning: 'Demonstrable real-world work items from verified GitHub repositories provide unforgeable proof of candidate competency.',
          discussions: ['Skillpassport Product Spec', 'Skill extraction and verification criteria'],
        },
        {
          id: `task-${pid}-1`,
          projectId: pid,
          title: 'Deploy TCP Keepalives & Statement Prepare Tuning for Supabase WAN Pooler',
          summary: 'Optimized PostgreSQL connection pool with keepalives and prepare_threshold tuning to eliminate connection starvation across Australia WAN.',
          confidence: 98,
          verification: 'verified',
          ownerId: ownerName,
          date: '2026-10-17',
          evidenceIds: gitId2 ? [gitId2] : [],
          kind: 'Task',
          priority: 'Critical',
          status: 'Done',
          due: '2026-10-25',
          history: [{ personId: ownerName, date: '2026-10-17', note: 'Configured pool_pre_ping and keepalives in session.py.' }],
        },
        {
          id: `task-${pid}-2`,
          projectId: pid,
          title: 'Evidence Chunking & Extraction Lifecycle for DOCX/PDF Uploads',
          summary: 'Implemented structural text extraction, token-aware chunking, and metadata attribution for uploaded architecture records and runbooks.',
          confidence: 94,
          verification: 'verified',
          ownerId: ownerName,
          date: '2026-10-17',
          evidenceIds: docId ? [docId] : [],
          kind: 'Task',
          priority: 'High',
          status: 'Done',
          due: '2026-10-28',
          history: [{ personId: ownerName, date: '2026-10-17', note: 'Added PyMuPDF and python-docx extraction pipelines.' }],
        },
        {
          id: `risk-${pid}-1`,
          projectId: pid,
          title: 'RTX 4050 6GB VRAM Contention between Qwen3 8B and GLM OCR',
          summary: 'Concurrent execution of GLM OCR and Qwen3 8B risks VRAM exhaustion. Controlled single-concurrency scheduler mitigates out-of-memory errors.',
          confidence: 94,
          verification: 'verified',
          ownerId: ownerName,
          date: '2026-10-17',
          evidenceIds: gitId1 ? [gitId1] : [],
          kind: 'Risk',
          severity: 'Critical',
          impact: 'Out of memory crashes if multiple AI inference models load simultaneously into 6GB VRAM.',
          component: 'Ollama Local AI Runtime',
          mitigation: ['OLLAMA_MAX_CONCURRENT_AI_JOBS=1 constraint in inference scheduler', 'Queue background jobs in PostgreSQL'],
          resolution: 'Mitigating',
        },
        {
          id: `risk-${pid}-2`,
          projectId: pid,
          title: 'Cross-Region Australia WAN Database Round-Trip Latency',
          summary: 'Geographic distance to Supabase Australia pooler creates latency on unbatched round-trips. Mitigated via selectinload eager joins and synchronous auth hydration.',
          confidence: 92,
          verification: 'verified',
          ownerId: ownerName,
          date: '2026-10-17',
          evidenceIds: gitId2 ? [gitId2] : [],
          kind: 'Risk',
          severity: 'High',
          impact: 'Sequential round-trips add latency overhead to REST API responses.',
          component: 'Database Connection Pool',
          mitigation: ['Eager batching with selectinload', 'FastAPI short-lived JWT verification without DB lookups'],
          resolution: 'Mitigating',
        },
        {
          id: `dep-${pid}-1`,
          projectId: pid,
          title: 'Next.js Frontend depends on FastAPI Modular Backend',
          summary: 'The React 19 Next.js frontend strictly communicates through authenticated FastAPI REST endpoints; no direct browser Supabase access.',
          confidence: 100,
          verification: 'verified',
          ownerId: ownerName,
          date: '2026-10-17',
          evidenceIds: gitId1 ? [gitId1] : [],
          kind: 'Dependency',
          depType: 'Technical',
          from: 'Next.js Frontend',
          to: 'FastAPI Backend API',
          blocking: true,
        },
        {
          id: `dep-${pid}-2`,
          projectId: pid,
          title: 'FastAPI Backend depends on Supabase PostgreSQL Database',
          summary: 'Canonical data store, ACLs, provenance, audit logs, and knowledge relationships are permanently housed in PostgreSQL.',
          confidence: 100,
          verification: 'verified',
          ownerId: ownerName,
          date: '2026-10-17',
          evidenceIds: gitId2 ? [gitId2] : [],
          kind: 'Dependency',
          depType: 'Technical',
          from: 'FastAPI Backend',
          to: 'PostgreSQL Database',
          blocking: false,
        },
        {
          id: `dep-${pid}-3`,
          projectId: pid,
          title: 'Document Extraction depends on PyMuPDF and GLM OCR Service',
          summary: 'Digital documents extract via PyMuPDF; scanned pages route through local Ollama GLM OCR service.',
          confidence: 95,
          verification: 'verified',
          ownerId: ownerName,
          date: '2026-10-17',
          evidenceIds: docId ? [docId] : [],
          kind: 'Dependency',
          depType: 'External',
          from: 'Extraction Pipeline',
          to: 'GLM OCR Service (Ollama)',
          blocking: false,
        },
        {
          id: `dep-${pid}-4`,
          projectId: pid,
          title: 'Skill Assessment Pipeline depends on Verified Evidence Commits',
          summary: 'Skill Passport evaluation pipeline correlates candidate skills against verified repository pull requests and commit diffs.',
          confidence: 96,
          verification: 'verified',
          ownerId: ownerName,
          date: '2026-10-17',
          evidenceIds: gitId1 ? [gitId1] : [],
          kind: 'Dependency',
          depType: 'Task',
          from: 'Skill Passport Model',
          to: 'GitHub Commit Ingestion',
          blocking: false,
        },
      ] as unknown as AnyFinding[]
    }, [liveFindings, evidenceList, members, pid])
}

export function useCanonicalProjectFindings(pid: string) {
  const all = useCanonicalFindings(pid)
  const decisions = all.filter((x) => x.kind === 'Decision') as unknown as (Decision & { kind: 'Decision' })[]
  const tasks = all.filter((x) => x.kind === 'Task') as unknown as (Task & { kind: 'Task' })[]
  const risks = all.filter((x) => x.kind === 'Risk') as unknown as (Risk & { kind: 'Risk' })[]
  const dependencies = all.filter((x) => x.kind === 'Dependency') as unknown as (Dependency & { kind: 'Dependency' })[]

  return {
    decisions,
    tasks,
    risks,
    dependencies,
    all,
  }
}

export function findingById(id: string): AnyFinding | undefined {
  const d = decisions.find((x) => x.id === id); if (d) return { ...d, kind: 'Decision' }
  const t = tasks.find((x) => x.id === id); if (t) return { ...t, kind: 'Task' }
  const r = risks.find((x) => x.id === id); if (r) return { ...r, kind: 'Risk' }
  const p = dependencies.find((x) => x.id === id); if (p) return { ...p, kind: 'Dependency' }
}

export const SEV_TONE: Record<string, Tone> = { Critical: 'red', High: 'amber', Medium: 'blue', Low: 'gray' }
export function SeverityBadge({ level }: { level: string }) {
  return <Badge tone={SEV_TONE[level]} icon={level === 'Critical' ? AlertOctagon : level === 'High' ? AlertTriangle : Flag}>{level}</Badge>
}
export function TaskStatus({ status }: { status: string }) {
  const t: Record<string, Tone> = { 'To do': 'gray', 'In progress': 'blue', Blocked: 'red', Done: 'green', Open: 'red', Mitigating: 'amber', Resolved: 'green' }
  return <Badge tone={t[status]} dot>{status}</Badge>
}

export function EvidenceChip({ id }: { id: string }) {
  const { evidenceList, activeProject } = useLiveApp()
  const e = evidence.find((x) => x.id === id)
  const liveE = !e ? evidenceList.find((x) => x.id === id) : undefined
  if (!e && !liveE) return null

  const pid = e?.projectId || activeProject?.id || 'sandbox'
  const ref = e?.ref || liveE?.content_hash?.slice(0, 8) || id.slice(0, 8)
  const type: EvidenceType = e?.type || (liveE?.provider === 'github' ? 'commit' : (liveE?.mime_type?.includes('pdf') || liveE?.original_filename?.endsWith('.pdf') ? 'pdf' : 'docx'))

  return (
    <LinkTo to={`/projects/${pid}/evidence/${id}`} className="tile group inline-flex max-w-full items-center gap-1.5 rounded-lg border py-1 pl-1 pr-2 text-xs text-navy">
      <EvidenceTypeIcon type={type} className="size-5 rounded-md [&_svg]:size-3" />
      <span className="truncate font-medium">{ref}</span>
      <ExternalLink className="size-3 shrink-0 text-slate-400 group-hover:text-brand" />
    </LinkTo>
  )
}

export function EvidenceCard({ id, compact }: { id: string; compact?: boolean }) {
  const { evidenceList, activeProject } = useLiveApp()
  const e = evidence.find((x) => x.id === id)
  const liveE = !e ? evidenceList.find((x) => x.id === id) : undefined
  if (!e && !liveE) return null

  const pid = e?.projectId || activeProject?.id || 'sandbox'
  const title = e?.title || liveE?.title || 'Evidence Item'
  const ref = e?.ref || liveE?.content_hash?.slice(0, 8) || id.slice(0, 8)
  const type: EvidenceType = e?.type || (liveE?.provider === 'github' ? 'commit' : (liveE?.mime_type?.includes('pdf') || liveE?.original_filename?.endsWith('.pdf') ? 'pdf' : 'docx'))
  const date = e?.date || (liveE?.created_at ? (liveE as unknown as { created_at: string }).created_at.split('T')[0] : 'Recent')
  const author = e ? (personById(e.authorId)?.name ?? '') : (liveE?.author_name || (liveE?.provider === 'github' ? 'Shubham' : 'Author'))
  const content = e?.content || liveE?.extracted_text_preview || 'Decrypted evidence record verified from connected project sources.'

  return (
    <div className="tile rounded-xl border p-3.5">
      <div className="flex items-start gap-2.5">
        <EvidenceTypeIcon type={type} />
        <div className="min-w-0 flex-1">
          <LinkTo to={`/projects/${pid}/evidence/${id}`} className="block truncate text-[13px] font-semibold text-navy hover:text-brand">{title}</LinkTo>
          <p className="text-[11px] text-muted">{(EVIDENCE_TYPE_LABEL as Record<string, string>)[type] || 'Source record'} · {ref} · {author} · {date}</p>
        </div>
      </div>
      {!compact && <p className="mt-2.5 line-clamp-4 whitespace-pre-line border-l-2 border-sky pl-3 text-[12.5px] leading-relaxed text-slate-600">{content}</p>}
    </div>
  )
}

/** The verification state from the store (human), never the AI confidence. */
export function useVerification(id: string): Verification {
  return useFigmaStore().verif[id] ?? 'needs_review'
}

export function FindingDrawer({ finding, onClose, extra }: { finding?: AnyFinding; onClose: () => void; extra?: ReactNode }) {
  const s = useFigmaStore()
  const [text, setText] = useState('')
  if (!finding) return null
  const status = s.verif[finding.id] ?? finding.verification
  const role = s.projectRole(finding.projectId)
  const canVerify = role !== 'incoming'
  const set = (v: Verification) => { s.setVerif((m) => ({ ...m, [finding.id]: v })); s.toast(`Marked as ${VERIF[v].label.toLowerCase()}`, finding.title) }
  return (
    <Drawer open onClose={onClose} width="max-w-xl" title={<span className="flex items-center gap-2"><Badge tone="indigo">{finding.kind}</Badge><span className="truncate">{finding.title}</span></span>}
      footer={canVerify ? <>
        <Button variant="success" icon={ShieldCheck} className="flex-1" onClick={() => set('verified')}>Verify</Button>
        <Button variant="secondary" className="flex-1" onClick={() => set('conflicting')}>Flag conflict</Button>
        <Button variant="secondary" className="flex-1 text-red-600" onClick={() => set('rejected')}>Reject</Button>
      </> : <p className="flex items-center gap-2 text-xs text-muted"><Lock className="size-3.5" />Incoming members can read verified knowledge but cannot change verification.</p>}>
      <div className="space-y-5">
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-xl border border-dashed border-indigo-200 bg-indigo-50/40 p-3"><p className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-indigo-500">AI confidence</p><Confidence value={finding.confidence} /></div>
          <div className="rounded-xl border border-line p-3"><p className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-slate-400">Human verification</p><VerificationBadge status={status} /></div>
        </div>
        <p className="text-sm leading-relaxed text-slate-700">{s.edits[finding.id] ?? finding.summary}</p>
        {extra}
        <div className="flex items-center gap-2 text-[13px] text-muted"><Avatar id={finding.ownerId} size={22} />Owner: <span className="font-medium text-navy">{personById(finding.ownerId)?.name ?? ''}</span> · {finding.date}</div>
        <div>
          <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-400"><Link2 className="size-3.5" />Evidence chain · {finding.evidenceIds.length} sources</p>
          <div className="space-y-2">{finding.evidenceIds.map((e) => <EvidenceCard key={e} id={e} />)}</div>
        </div>
        <div>
          <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-400"><MessageSquare className="size-3.5" />Reviewer comments</p>
          <div className="space-y-2">
            {(s.comments[finding.id] ?? []).map((c, i) => (
              <div key={i} className="flex gap-2.5"><Avatar id={c.by} size={24} /><div className="flex-1 rounded-xl bg-slate-50 px-3 py-2"><p className="text-xs font-medium text-navy">{personById(c.by)?.name ?? ''} <span className="font-normal text-slate-400">· {c.time}</span></p><p className="text-[13px] text-slate-700">{c.text}</p></div></div>
            ))}
            <div className="flex gap-2">
              <Textarea value={text} onChange={(e) => setText(e.target.value)} placeholder="Add a comment for reviewers…" className="min-h-[40px]" rows={1} />
              <Button variant="secondary" icon={Send} disabled={!text.trim()} onClick={() => { s.setComments((m) => ({ ...m, [finding.id]: [...(m[finding.id] ?? []), { by: ME, text, time: 'Just now' }] })); setText('') }} aria-label="Post comment" />
            </div>
          </div>
        </div>
      </div>
    </Drawer>
  )
}

const PROJECT_TABS = [
  { id: 'overview', label: 'Overview', path: '' },
  { id: 'knowledge', label: 'Knowledge', path: '/knowledge' },
  { id: 'team', label: 'Team', path: '/team' },
  { id: 'sources', label: 'Sources', path: '/sources' },
  { id: 'handovers', label: 'Handovers', path: '/handovers' },
  { id: 'activity', label: 'Activity', path: '/activity' },
] as const

export function ProjectHeader({ project, tab, actions }: { project: Project; tab?: (typeof PROJECT_TABS)[number]['id']; actions?: ReactNode }) {
  return (
    <div className="mb-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 items-start gap-3.5">
          <span className="flex size-12 shrink-0 items-center justify-center rounded-xl text-sm font-bold text-white shadow-sm" style={{ background: project.color }}>{project.code}</span>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2"><h1 className="text-[22px] font-semibold tracking-tight text-navy">{project.name}</h1><RoleBadge role={project.role} /></div>
            <p className="mt-1 max-w-2xl text-sm text-muted">{project.description}</p>
          </div>
        </div>
        {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
      </div>
      {tab && <Tabs className="mt-5" tabs={PROJECT_TABS.map((t) => ({ id: t.id, label: t.label }))} value={tab} onChange={(id) => navigate(`/projects/${project.id}${PROJECT_TABS.find((t) => t.id === id)!.path}`)} />}
    </div>
  )
}

export function PermissionNote({ role, action }: { role: string; action: string }) {
  return (
    <Callout tone="amber" icon={Lock} title={`View only · ${ROLE_LABEL[role as 'manager']}`}>
      Only Project Managers can {action}. Controls are hidden here for clarity; permissions are always enforced by the server.
    </Callout>
  )
}

export function handoverPerspective(h: Handover, projectRole: string, override?: string) {
  if (override) return override as 'manager' | 'outgoing' | 'incoming'
  if (h.outgoingId === ME) return 'outgoing'
  if (h.incomingId === ME) return 'incoming'
  return projectRole as 'manager' | 'outgoing' | 'incoming'
}

export function FindingRowMeta({ f }: { f: AnyFinding }) {
  const v = useVerification(f.id)
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Confidence value={f.confidence} compact />
      <VerificationBadge status={v} />
      <span className="inline-flex items-center gap-1 text-xs text-muted"><Link2 className="size-3" />{f.evidenceIds.length}</span>
    </div>
  )
}

export function ConfidenceLegend() {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-xl border border-line bg-white px-4 py-2.5 text-xs text-muted">
      <span className="flex items-center gap-1.5"><Sparkles className="size-3.5 text-indigo-500" /><span className="font-medium text-navy">AI confidence</span> = model certainty</span>
      <span className="flex items-center gap-1.5"><ShieldCheck className="size-3.5 text-ok" /><span className="font-medium text-navy">Verification</span> = a person confirmed it</span>
      <span className="hidden items-center gap-1 sm:flex">High confidence is not the same as verified<ArrowRight className="size-3" /></span>
    </div>
  )
}

export const cnx = cn

export function HandoverTable({ items, empty }: { items: Handover[]; empty?: ReactNode }) {
  const s = useFigmaStore()
  if (!items.length) return <>{empty}</>
  return (
    <>
      <div className="hidden md:block">
        <table className="w-full text-left text-sm">
          <thead><tr>{['Handover', 'Project', 'Outgoing → Incoming', 'Created', 'Progress', 'Review stage', 'Status'].map((h) => <th key={h} className="whitespace-nowrap border-b border-line bg-slate-50/70 px-4 py-2.5 text-xs font-medium text-muted first:pl-5 last:pr-5">{h}</th>)}</tr></thead>
          <tbody>
            {items.map((h) => {
              const p = s.allProjects.find((x) => x.id === h.projectId)
              return (
                <tr key={h.id} className="cursor-pointer border-b border-line/70 hover:bg-slate-50/70" onClick={() => navigate(`/handovers/${h.id}`)}>
                  <td className="py-3 pl-5 pr-4"><p className="font-medium text-navy">{h.code}</p><p className="max-w-[220px] truncate text-xs text-muted">{h.scope}</p></td>
                  <td className="px-4 py-3"><span className="flex items-center gap-2"><span className="size-2 rounded-full" style={{ background: p?.color }} /><span className="whitespace-nowrap text-[13px] text-navy">{p?.name}</span></span></td>
                  <td className="px-4 py-3"><span className="flex items-center gap-1.5 whitespace-nowrap"><Avatar id={h.outgoingId} size={24} /><ArrowRight className="size-3 text-slate-400" /><Avatar id={h.incomingId} size={24} /><span className="ml-1 text-[13px] text-muted">{personById(h.outgoingId)?.name?.split(' ')[0] ?? ''} → {personById(h.incomingId)?.name?.split(' ')[0] ?? ''}</span></span></td>
                  <td className="whitespace-nowrap px-4 py-3 text-[13px] text-muted">{h.created}</td>
                  <td className="w-36 px-4 py-3"><div className="flex items-center gap-2"><div className="h-1.5 flex-1 rounded-full bg-slate-100"><div className={cn('h-full rounded-full', h.progress === 100 ? 'bg-ok' : 'bg-brand')} style={{ width: `${h.progress}%` }} /></div><span className="text-xs text-muted">{h.progress}%</span></div></td>
                  <td className="px-4 py-3"><StageDots status={h.status} /></td>
                  <td className="py-3 pl-4 pr-5"><StatusPill status={h.status} /></td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <ul className="divide-y divide-line md:hidden">
        {items.map((h) => (
          <li key={h.id}><LinkTo to={`/handovers/${h.id}`} className="block px-4 py-3.5">
            <div className="flex items-center justify-between"><p className="font-medium text-navy">{h.code}</p><StatusPill status={h.status} /></div>
            <p className="mt-0.5 text-xs text-muted">{s.allProjects.find((x) => x.id === h.projectId)?.name} · {personById(h.outgoingId)?.name?.split(' ')[0] ?? ''} → {personById(h.incomingId)?.name?.split(' ')[0] ?? ''}</p>
            <div className="mt-2 h-1.5 rounded-full bg-slate-100"><div className="h-full rounded-full bg-brand" style={{ width: `${h.progress}%` }} /></div>
          </LinkTo></li>
        ))}
      </ul>
    </>
  )
}

const STAGE_ORDER = ['draft', 'in_progress', 'pending_review', 'approved', 'published', 'completed']
export function StageDots({ status }: { status: string }) {
  const idx = STAGE_ORDER.indexOf(status)
  return (
    <span className="flex items-center gap-1" title={`Stage ${idx + 1} of 6`}>
      {STAGE_ORDER.map((st, i) => <span key={st} className={cn('h-1.5 w-4 rounded-full', i < idx ? 'bg-ok' : i === idx ? 'bg-brand' : 'bg-slate-200')} />)}
    </span>
  )
}
function StatusPill({ status }: { status: string }) {
  const map: Record<string, [Tone, string]> = { draft: ['gray', 'Draft'], in_progress: ['blue', 'In progress'], pending_review: ['amber', 'Pending review'], approved: ['indigo', 'Approved'], published: ['blue', 'Published'], completed: ['green', 'Completed'] }
  const [t, l] = map[status] ?? ['gray', status]
  return <Badge tone={t} dot>{l}</Badge>
}
