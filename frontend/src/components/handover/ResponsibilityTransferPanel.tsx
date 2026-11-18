'use client'

import React, { useCallback, useEffect, useMemo, useState } from 'react'
import {
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  BookOpen,
  CheckCircle2,
  Clock,
  ExternalLink,
  HelpCircle,
  History,
  KeyRound,
  Layers,
  Loader2,
  Lock,
  MessageSquare,
  Plus,
  RefreshCw,
  RotateCcw,
  Send,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  UserCheck,
  UserRoundCog,
  Users,
  XCircle,
} from 'lucide-react'

import {
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
  Textarea,
  cn,
} from '../figma-ui/index'
import { api } from '../../lib/api'
import type {
  HandoverResponsibilityTransferDetail,
  HandoverResponsibilityWorkspaceResponse,
  ResponsibilityCandidateItem,
} from '../../lib/types'

export interface ResponsibilityTransferPanelProps {
  caseId: string
  projectId: string
  currentUserId?: string | null
  canManageProject?: boolean
  onDataChanged?: () => void
  onReassessReadiness?: () => Promise<void>
  isReassessingReadiness?: boolean
}

function transferStatusBadge(status: string): {
  label: string
  tone: 'green' | 'amber' | 'red' | 'blue' | 'gray' | 'indigo'
} {
  switch (status) {
    case 'acknowledged':
      return { label: 'Acknowledged', tone: 'green' }
    case 'completed':
      return { label: 'Completed', tone: 'green' }
    case 'awaiting_successor_acknowledgement':
      return { label: 'Awaiting Successor Ack', tone: 'blue' }
    case 'awaiting_outgoing_confirmation':
      return { label: 'Awaiting Outgoing Confirm', tone: 'indigo' }
    case 'prepared':
      return { label: 'Prepared for Transfer', tone: 'blue' }
    case 'clarification_requested':
      return { label: 'Clarification Requested', tone: 'amber' }
    case 'reopened':
      return { label: 'Reopened', tone: 'amber' }
    case 'blocked':
      return { label: 'Transfer Blocked', tone: 'red' }
    case 'pending':
    default:
      return { label: 'Not Started', tone: 'gray' }
  }
}

function priorityBadgeTone(priority: string): 'red' | 'amber' | 'blue' | 'gray' {
  switch ((priority || 'medium').toLowerCase()) {
    case 'critical':
    case 'high':
      return 'red'
    case 'medium':
      return 'amber'
    case 'low':
    default:
      return 'blue'
  }
}

function certaintyBadge(certainty: string): { label: string; tone: 'green' | 'blue' | 'amber' } {
  switch ((certainty || 'proposed').toLowerCase()) {
    case 'confirmed':
      return { label: 'Ownership Confirmed', tone: 'green' }
    case 'uncertain':
      return { label: 'Uncertain Ownership', tone: 'amber' }
    case 'proposed':
    default:
      return { label: 'Proposed Owner', tone: 'blue' }
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

const DOMAIN_OPTIONS: Array<{ value: string; label: string }> = [
  { value: 'responsibilities_ownership', label: 'Responsibilities & Ownership' },
  { value: 'technical_architecture', label: 'Technical Architecture' },
  { value: 'decisions_rationale', label: 'Decisions & Rationale' },
  { value: 'work_items', label: 'Work Progress & Tasks' },
  { value: 'dependencies', label: 'Dependencies & Relationships' },
  { value: 'bugs_blockers_risks', label: 'Bugs, Blockers & Risks' },
  { value: 'operational_historical', label: 'Operational & Historical' },
  { value: 'project_overview_context', label: 'Project Overview & Context' },
]

export function ResponsibilityTransferPanel({
  caseId,
  projectId,
  currentUserId,
  canManageProject = false,
  onDataChanged,
  onReassessReadiness,
  isReassessingReadiness,
}: ResponsibilityTransferPanelProps) {
  const [workspace, setWorkspace] = useState<HandoverResponsibilityWorkspaceResponse | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [actionSuccess, setActionSuccess] = useState<string | null>(null)
  const [readinessDirty, setReadinessDirty] = useState(false)

  const [selectedTransferId, setSelectedTransferId] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState<
    'all' | 'unassigned' | 'awaiting_successor' | 'clarification' | 'acknowledged' | 'blocked'
  >('all')

  // Create / Map Responsibility Modal
  const [createOpen, setCreateOpen] = useState(false)
  const [isCreating, setIsCreating] = useState(false)
  const [newTitle, setNewTitle] = useState('')
  const [newDesc, setNewDesc] = useState('')
  const [newComponent, setNewComponent] = useState('')
  const [newDomain, setNewDomain] = useState('responsibilities_ownership')
  const [newPriority, setNewPriority] = useState('medium')
  const [newCertainty, setNewCertainty] = useState('proposed')
  const [newSuccessorId, setNewSuccessorId] = useState('')
  const [newOpsCtx, setNewOpsCtx] = useState('')
  const [newAccess, setNewAccess] = useState('')
  const [newEffectiveDate, setNewEffectiveDate] = useState('')
  const [newNotes, setNewNotes] = useState('')
  const [newKnowledgeItemId, setNewKnowledgeItemId] = useState<string | null>(null)

  // Quick edit / Reassign state on selected transfer
  const [reassignSuccessorId, setReassignSuccessorId] = useState('')
  const [editOpsCtx, setEditOpsCtx] = useState('')
  const [editAccess, setEditAccess] = useState('')
  const [editNotes, setEditNotes] = useState('')
  const [isSaving, setIsSaving] = useState(false)

  // Governance Modals
  const [confirmOutgoingOpen, setConfirmOutgoingOpen] = useState(false)
  const [outgoingNotes, setOutgoingNotes] = useState('')
  const [ackModalOpen, setAckModalOpen] = useState(false)
  const [ackNotes, setAckNotes] = useState('')
  const [clarifyModalOpen, setClarifyModalOpen] = useState(false)
  const [clarifyMode, setClarifyMode] = useState<'request' | 'response'>('request')
  const [clarifyNotes, setClarifyNotes] = useState('')
  const [reopenModalOpen, setReopenModalOpen] = useState(false)
  const [reopenReason, setReopenReason] = useState('')
  const [blockModalOpen, setBlockModalOpen] = useState(false)
  const [blockReason, setBlockReason] = useState('')
  const [isSubmittingGovernance, setIsSubmittingGovernance] = useState(false)

  const loadWorkspace = useCallback(async () => {
    if (!projectId || !caseId) return
    setIsLoading(true)
    setError(null)
    try {
      const data = await api.handover.getResponsibilityWorkspace(projectId, caseId)
      setWorkspace(data)
      setSelectedTransferId((prev) => {
        if (prev && data.transfers.some((t) => t.id === prev)) return prev
        return data.transfers[0]?.id ?? null
      })
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : 'Failed to load responsibility transfer workspace.',
      )
    } finally {
      setIsLoading(false)
    }
  }, [projectId, caseId])

  useEffect(() => {
    void loadWorkspace()
  }, [loadWorkspace])

  const selectedTransfer: HandoverResponsibilityTransferDetail | null = useMemo(
    () => (workspace?.transfers || []).find((t) => t.id === selectedTransferId) ?? null,
    [workspace, selectedTransferId],
  )

  useEffect(() => {
    if (!selectedTransfer) return
    setReassignSuccessorId(selectedTransfer.proposed_successor_id || '')
    setEditOpsCtx(selectedTransfer.operational_context || '')
    setEditAccess(selectedTransfer.required_access || '')
    setEditNotes(selectedTransfer.transfer_notes || '')
    setActionError(null)
  }, [selectedTransfer])

  const eligibleSuccessorsForOwner = (ownerId?: string | null) =>
    (workspace?.eligible_participants || []).filter(
      (p) => p.is_active && p.user_id !== ownerId,
    )

  const filteredTransfers = useMemo(() => {
    const list = workspace?.transfers || []
    switch (statusFilter) {
      case 'unassigned':
        return list.filter((t) => !t.proposed_successor_id)
      case 'awaiting_successor':
        return list.filter((t) => t.transfer_status === 'awaiting_successor_acknowledgement')
      case 'clarification':
        return list.filter(
          (t) =>
            t.transfer_status === 'clarification_requested' ||
            t.transfer_status === 'reopened',
        )
      case 'acknowledged':
        return list.filter(
          (t) => t.transfer_status === 'acknowledged' || t.transfer_status === 'completed',
        )
      case 'blocked':
        return list.filter((t) => t.transfer_status === 'blocked')
      case 'all':
      default:
        return list
    }
  }, [workspace, statusFilter])

  const openCreateFromCandidate = (candidate?: ResponsibilityCandidateItem) => {
    setActionError(null)
    if (candidate) {
      setNewTitle(candidate.title.slice(0, 200))
      setNewDesc(candidate.summary || candidate.title)
      setNewDomain('responsibilities_ownership')
      setNewCertainty(candidate.is_verified ? 'confirmed' : 'uncertain')
      setNewKnowledgeItemId(candidate.knowledge_item_id)
      setNewNotes(
        candidate.is_verified
          ? 'Grounded in verified canonical ownership record.'
          : 'Mapped from pending project knowledge item — requires explicit owner confirmation.',
      )
    } else {
      setNewTitle('')
      setNewDesc('')
      setNewDomain('responsibilities_ownership')
      setNewCertainty('proposed')
      setNewKnowledgeItemId(null)
      setNewNotes('')
    }
    setNewComponent('')
    setNewPriority('medium')
    setNewSuccessorId(workspace?.case_successor_id || '')
    setNewOpsCtx('')
    setNewAccess('')
    setNewEffectiveDate('')
    setCreateOpen(true)
  }

  const handleCreateTransfer = async () => {
    if (newDesc.trim().length < 5) return
    setIsCreating(true)
    setActionError(null)
    setActionSuccess(null)
    try {
      const created = await api.handover.createResponsibilities(projectId, caseId, [
        {
          title: newTitle.trim() || undefined,
          responsibility_description: newDesc.trim(),
          knowledge_domain: newDomain,
          component_name: newComponent.trim() || undefined,
          priority: newPriority,
          ownership_certainty: newCertainty,
          operational_context: newOpsCtx.trim() || undefined,
          required_access: newAccess.trim() || undefined,
          effective_transfer_date: newEffectiveDate || null,
          proposed_successor_id: newSuccessorId || null,
          transfer_notes: newNotes.trim() || undefined,
          related_knowledge_item_id: newKnowledgeItemId,
        },
      ])
      setCreateOpen(false)
      await loadWorkspace()
      if (created[0]?.id) setSelectedTransferId(created[0].id)
      onDataChanged?.()
      setActionSuccess('Responsibility transfer mapped and persisted.')
      setReadinessDirty(true)
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : 'Failed to create responsibility transfer.')
    } finally {
      setIsCreating(false)
    }
  }

  const handleSaveDetails = async () => {
    if (!selectedTransfer) return
    setIsSaving(true)
    setActionError(null)
    setActionSuccess(null)
    try {
      await api.handover.updateResponsibility(projectId, selectedTransfer.id, {
        proposed_successor_id: reassignSuccessorId || null,
        clear_successor: !reassignSuccessorId && Boolean(selectedTransfer.proposed_successor_id),
        operational_context: editOpsCtx,
        required_access: editAccess,
        transfer_notes: editNotes,
        expected_version: selectedTransfer.version,
      })
      await loadWorkspace()
      onDataChanged?.()
      setActionSuccess('Responsibility details and successor assignment saved.')
      setReadinessDirty(true)
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : 'Failed to save responsibility changes.')
    } finally {
      setIsSaving(false)
    }
  }

  const handleConfirmOutgoing = async () => {
    if (!selectedTransfer) return
    setIsSubmittingGovernance(true)
    setActionError(null)
    setActionSuccess(null)
    try {
      await api.handover.confirmResponsibilityOutgoing(projectId, selectedTransfer.id, {
        confirmation_notes: outgoingNotes.trim() || undefined,
        expected_version: selectedTransfer.version,
      })
      setConfirmOutgoingOpen(false)
      setOutgoingNotes('')
      await loadWorkspace()
      onDataChanged?.()
      setActionSuccess('Outgoing-owner confirmation recorded. Now awaiting successor acknowledgement.')
      setReadinessDirty(true)
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : 'Outgoing confirmation failed.')
    } finally {
      setIsSubmittingGovernance(false)
    }
  }

  const handleSuccessorAck = async () => {
    if (!selectedTransfer) return
    setIsSubmittingGovernance(true)
    setActionError(null)
    setActionSuccess(null)
    try {
      await api.handover.acknowledgeResponsibilitySuccessor(projectId, selectedTransfer.id, {
        acknowledgement_notes: ackNotes.trim() || undefined,
        expected_version: selectedTransfer.version,
      })
      setAckModalOpen(false)
      setAckNotes('')
      await loadWorkspace()
      onDataChanged?.()
      setActionSuccess(
        'Successor acknowledgement recorded. Note: final managerial approval remains a separate governance step.',
      )
      setReadinessDirty(true)
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : 'Successor acknowledgement failed.')
    } finally {
      setIsSubmittingGovernance(false)
    }
  }

  const handleClarificationSubmit = async () => {
    if (!selectedTransfer || clarifyNotes.trim().length < 3) return
    setIsSubmittingGovernance(true)
    setActionError(null)
    setActionSuccess(null)
    try {
      await api.handover.clarifyResponsibility(projectId, selectedTransfer.id, {
        mode: clarifyMode,
        notes: clarifyNotes.trim(),
        expected_version: selectedTransfer.version,
      })
      setClarifyModalOpen(false)
      setClarifyNotes('')
      await loadWorkspace()
      onDataChanged?.()
      setActionSuccess(
        clarifyMode === 'request'
          ? 'Clarification request recorded and transfer marked for follow-up.'
          : 'Clarification response posted.',
      )
      setReadinessDirty(true)
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : 'Clarification action failed.')
    } finally {
      setIsSubmittingGovernance(false)
    }
  }

  const handleReopen = async () => {
    if (!selectedTransfer || reopenReason.trim().length < 5) return
    setIsSubmittingGovernance(true)
    setActionError(null)
    setActionSuccess(null)
    try {
      await api.handover.reopenResponsibility(projectId, selectedTransfer.id, {
        reason: reopenReason.trim(),
        expected_version: selectedTransfer.version,
      })
      setReopenModalOpen(false)
      setReopenReason('')
      await loadWorkspace()
      onDataChanged?.()
      setActionSuccess('Responsibility transfer reopened with audit trail.')
      setReadinessDirty(true)
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : 'Failed to reopen responsibility transfer.')
    } finally {
      setIsSubmittingGovernance(false)
    }
  }

  const handleMarkBlocked = async () => {
    if (!selectedTransfer || blockReason.trim().length < 3) return
    setIsSubmittingGovernance(true)
    setActionError(null)
    setActionSuccess(null)
    try {
      await api.handover.updateResponsibility(projectId, selectedTransfer.id, {
        transfer_status: 'blocked',
        blocker_reason: blockReason.trim(),
        expected_version: selectedTransfer.version,
      })
      setBlockModalOpen(false)
      setBlockReason('')
      await loadWorkspace()
      onDataChanged?.()
      setActionSuccess('Responsibility transfer marked as blocked.')
      setReadinessDirty(true)
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : 'Failed to mark transfer blocked.')
    } finally {
      setIsSubmittingGovernance(false)
    }
  }

  if (isLoading && !workspace) {
    return (
      <Card className="p-10">
        <div className="flex flex-col items-center justify-center gap-3 text-center">
          <Loader2 className="size-7 animate-spin text-brand" />
          <p className="text-sm font-semibold text-navy">Loading responsibility transfer workspace…</p>
          <p className="text-xs text-muted">
            Validating real project participants, mapped ownership transfers, 8-domain knowledge links, and ACL-checked evidence.
          </p>
        </div>
      </Card>
    )
  }

  if (error && !workspace) {
    return (
      <Card className="p-6">
        <Callout tone="red" icon={AlertCircle} title="Unable to load responsibility workspace">
          <p className="mb-3">{error}</p>
          <Button variant="secondary" size="sm" icon={RefreshCw} onClick={loadWorkspace}>
            Retry
          </Button>
        </Callout>
      </Card>
    )
  }

  if (!workspace) return null

  const isSelectedOutgoingOwner =
    Boolean(selectedTransfer) &&
    (currentUserId === selectedTransfer?.current_owner_id || canManageProject)
  const isSelectedSuccessor =
    Boolean(selectedTransfer?.proposed_successor_id) &&
    currentUserId === selectedTransfer?.proposed_successor_id

  return (
    <div className="space-y-6" data-testid="responsibility-transfer-panel">
      {actionSuccess && (
        <Callout tone="green" icon={CheckCircle2} title="Ownership transfer updated">
          {actionSuccess}
        </Callout>
      )}
      {actionError && (
        <Callout tone="red" icon={AlertCircle} title="Ownership action blocked or failed">
          {actionError}
        </Callout>
      )}
      {readinessDirty && onReassessReadiness && (
        <Callout tone="amber" icon={RefreshCw} title="Readiness reassessment recommended">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span>
              Responsibility transfer state changed. Reassess readiness to refresh persisted ownership coverage scores and approval gates.
            </span>
            <Button
              size="sm"
              icon={isReassessingReadiness ? Loader2 : RefreshCw}
              disabled={isReassessingReadiness}
              onClick={async () => {
                await onReassessReadiness()
                setReadinessDirty(false)
              }}
            >
              {isReassessingReadiness ? 'Reassessing…' : 'Reassess Readiness'}
            </Button>
          </div>
        </Callout>
      )}

      {/* Header & Summary KPIs */}
      <Card className="p-5 sm:p-6">
        <div className="flex flex-col gap-4 border-b border-line pb-5 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <UserRoundCog className="size-5 text-brand" />
              <h2 className="text-lg font-semibold text-navy">
                Responsibility Transfer & Ownership Management
              </h2>
              <Badge tone={workspace.unassigned_count === 0 && workspace.total_transfers > 0 ? 'green' : 'amber'}>
                {workspace.acknowledged_count}/{workspace.total_transfers} Acknowledged
              </Badge>
            </div>
            <p className="mt-1 text-[13px] text-muted">
              Map real departing responsibilities to eligible project members, preserve outgoing confirmation vs successor acknowledgement separation, and ground every transfer in canonical evidence.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" icon={Plus} onClick={() => openCreateFromCandidate(undefined)}>
              Map Responsibility
            </Button>
            <Button variant="secondary" size="sm" icon={RefreshCw} onClick={loadWorkspace}>
              Refresh
            </Button>
          </div>
        </div>

        {/* Summary Counters */}
        <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <div className="rounded-xl border border-line bg-slate-50/70 p-3">
            <p className="text-[11px] text-muted">Mapped Transfers</p>
            <p className="text-lg font-bold text-navy">{workspace.total_transfers}</p>
          </div>
          <div
            className={cn(
              'rounded-xl border p-3',
              workspace.unassigned_count > 0
                ? 'border-amber-200 bg-amber-50/60'
                : 'border-line bg-slate-50/70',
            )}
          >
            <p className={cn('text-[11px]', workspace.unassigned_count > 0 ? 'text-amber-700' : 'text-muted')}>
              Unassigned
            </p>
            <p className={cn('text-lg font-bold', workspace.unassigned_count > 0 ? 'text-amber-800' : 'text-navy')}>
              {workspace.unassigned_count}
            </p>
          </div>
          <div className="rounded-xl border border-line bg-slate-50/70 p-3">
            <p className="text-[11px] text-muted">Awaiting Outgoing</p>
            <p className="text-lg font-bold text-navy">{workspace.awaiting_outgoing_count}</p>
          </div>
          <div className="rounded-xl border border-blue-200 bg-blue-50/50 p-3">
            <p className="text-[11px] text-blue-700">Awaiting Successor</p>
            <p className="text-lg font-bold text-blue-800">{workspace.awaiting_successor_count}</p>
          </div>
          <div className="rounded-xl border border-emerald-200 bg-emerald-50/50 p-3">
            <p className="text-[11px] text-emerald-700">Acknowledged</p>
            <p className="text-lg font-bold text-emerald-800">{workspace.acknowledged_count}</p>
          </div>
          <div
            className={cn(
              'rounded-xl border p-3',
              workspace.blocked_count + workspace.clarification_count > 0
                ? 'border-red-200 bg-red-50/50'
                : 'border-line bg-slate-50/70',
            )}
          >
            <p className="text-[11px] text-muted">Blocked / Clarify</p>
            <p className="text-lg font-bold text-navy">
              {workspace.blocked_count + workspace.clarification_count}
            </p>
          </div>
        </div>

        {/* Real Project Participants Strip */}
        <div className="mt-4 rounded-xl border border-line bg-slate-50/60 p-3.5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-navy">
              <Users className="size-3.5 text-brand" />
              Live Project Participants ({workspace.eligible_participants.length})
            </span>
            {workspace.eligible_participants.filter((p) => p.is_active && !p.is_departing_owner).length === 0 && (
              <span className="text-[11.5px] font-medium text-amber-700">
                No second active project member available yet — add a team member in Team Members to assign a successor.
              </span>
            )}
          </div>
          <div className="mt-2.5 flex flex-wrap gap-2">
            {workspace.eligible_participants.map((p) => (
              <div
                key={p.user_id}
                className={cn(
                  'inline-flex items-center gap-2 rounded-lg border px-2.5 py-1.5 text-xs',
                  p.is_active ? 'border-line bg-white' : 'border-red-200 bg-red-50/60',
                )}
              >
                <span className="font-medium text-navy">{p.full_name}</span>
                <span className="text-[11px] text-muted">({p.role_name.replace(/_/g, ' ')})</span>
                {p.is_departing_owner && <Badge tone="amber">Outgoing</Badge>}
                {p.is_case_successor && <Badge tone="blue">Successor</Badge>}
                {!p.is_active && <Badge tone="red">Inactive</Badge>}
              </div>
            ))}
          </div>
        </div>
      </Card>

      {/* Ownership Validation Warnings */}
      {workspace.validation_issues.length > 0 && (
        <Card className="border-amber-200 bg-amber-50/30 p-5">
          <div className="flex items-center gap-2">
            <ShieldAlert className="size-4 text-amber-700" />
            <h3 className="text-sm font-semibold text-navy">
              Ownership & Participant Validation Alerts ({workspace.validation_issues.length})
            </h3>
          </div>
          <ul className="mt-3 space-y-2">
            {workspace.validation_issues.map((issue, idx) => (
              <li key={`${issue.code}-${idx}`} className="flex items-start gap-2 text-xs text-navy">
                <Badge tone={priorityBadgeTone(issue.severity)}>{issue.severity.toUpperCase()}</Badge>
                <span>{issue.message}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {/* Main Master-Detail Responsibility Transfer Workspace */}
      <div className="grid gap-6 lg:grid-cols-[0.95fr_1.05fr]">
        {/* Left: Responsibility Queue + Discovered Real Candidates */}
        <div className="space-y-4">
          <Card className="overflow-hidden">
            <div className="border-b border-line p-4">
              <div className="flex items-center justify-between gap-2">
                <h3 className="text-sm font-semibold text-navy">
                  Mapped Responsibility Queue ({filteredTransfers.length})
                </h3>
              </div>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {(
                  [
                    ['all', 'All'],
                    ['unassigned', 'Unassigned'],
                    ['awaiting_successor', 'Awaiting Ack'],
                    ['clarification', 'Clarification'],
                    ['acknowledged', 'Acknowledged'],
                    ['blocked', 'Blocked'],
                  ] as const
                ).map(([k, lbl]) => (
                  <button
                    key={k}
                    type="button"
                    onClick={() => setStatusFilter(k)}
                    className={cn(
                      'rounded-full border px-2.5 py-0.5 text-[11px] font-medium transition',
                      statusFilter === k
                        ? 'border-brand bg-tint/50 text-brand'
                        : 'border-line bg-white text-muted hover:text-navy',
                    )}
                  >
                    {lbl}
                  </button>
                ))}
              </div>
            </div>

            {filteredTransfers.length === 0 ? (
              <div className="p-6 text-center">
                <UserRoundCog className="mx-auto size-7 text-slate-300" />
                <p className="mt-2 text-sm font-semibold text-navy">
                  {workspace.total_transfers === 0
                    ? 'No responsibility transfers mapped yet'
                    : 'No transfers match this filter'}
                </p>
                <p className="mt-1 text-xs text-muted">
                  Map an explicit responsibility below or promote a discovered project ownership record with human confirmation.
                </p>
                <Button
                  size="sm"
                  className="mt-4"
                  icon={Plus}
                  onClick={() => openCreateFromCandidate(undefined)}
                >
                  Map First Responsibility
                </Button>
              </div>
            ) : (
              <div className="divide-y divide-line">
                {filteredTransfers.map((t) => {
                  const sb = transferStatusBadge(t.transfer_status)
                  const cb = certaintyBadge(t.ownership_certainty)
                  const isSel = selectedTransfer?.id === t.id
                  return (
                    <button
                      key={t.id}
                      type="button"
                      onClick={() => setSelectedTransferId(t.id)}
                      className={cn(
                        'block w-full px-4 py-3.5 text-left transition',
                        isSel ? 'bg-tint/40 ring-1 ring-inset ring-brand/25' : 'hover:bg-slate-50',
                      )}
                    >
                      <div className="flex flex-wrap items-center gap-1.5">
                        <Badge tone={priorityBadgeTone(t.priority)}>{t.priority.toUpperCase()}</Badge>
                        <Badge tone={sb.tone}>{sb.label}</Badge>
                        {t.ownership_certainty === 'uncertain' && <Badge tone={cb.tone}>Uncertain</Badge>}
                      </div>
                      <p className="mt-1.5 text-[13.5px] font-semibold text-navy">
                        {t.title || t.responsibility_description.slice(0, 70)}
                      </p>
                      <p className="mt-0.5 line-clamp-2 text-xs text-muted">
                        {t.responsibility_description}
                      </p>
                      <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-muted">
                        <span>{t.current_owner_name || 'Owner'}</span>
                        <ArrowRight className="size-3 text-brand" />
                        <span
                          className={cn(
                            'font-medium',
                            t.proposed_successor_name ? 'text-navy' : 'text-amber-700',
                          )}
                        >
                          {t.proposed_successor_name || 'Unassigned successor'}
                        </span>
                        {t.component_name && (
                          <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10.5px]">
                            {t.component_name}
                          </span>
                        )}
                      </div>
                    </button>
                  )
                })}
              </div>
            )}
          </Card>

          {/* Discovered Project Ownership Candidates (from Real KnowledgeItems, Never Auto-Promoted) */}
          <Card className="overflow-hidden">
            <CardHeader
              title={`Discovered Project Ownership Records (${workspace.discovered_candidates.length})`}
              subtitle="Grounded in canonical Knowledge Intelligence. Unverified items remain marked pending/uncertain until explicitly confirmed."
            />
            {workspace.discovered_candidates.length === 0 ? (
              <div className="p-5 text-center text-xs text-muted">
                All discovered responsibility knowledge items have been mapped or none exist yet.
              </div>
            ) : (
              <div className="max-h-96 divide-y divide-line overflow-y-auto">
                {workspace.discovered_candidates.map((cand) => (
                  <div key={cand.knowledge_item_id} className="p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <Badge tone={cand.is_verified ? 'green' : 'amber'}>
                            {cand.is_verified ? 'Reviewer-Verified' : 'Uncertain / Pending Review'}
                          </Badge>
                          <Badge tone="gray">{cand.epistemic_status.replace(/_/g, ' ')}</Badge>
                        </div>
                        <p className="mt-1.5 text-[13px] font-semibold text-navy">{cand.title}</p>
                        <p className="mt-0.5 line-clamp-2 text-xs text-muted">{cand.summary}</p>
                        {cand.source_context && (
                          <p className="mt-1 text-[11px] text-amber-800">{cand.source_context}</p>
                        )}
                        {cand.evidence_refs.length > 0 && (
                          <div className="mt-1.5 flex flex-wrap gap-1.5">
                            {cand.evidence_refs.slice(0, 2).map((ref) => (
                              <span
                                key={ref.evidence_id}
                                className="inline-flex items-center gap-1 rounded border border-line bg-slate-50 px-2 py-0.5 text-[10.5px] text-slate-600"
                              >
                                {ref.acl_restricted && <Lock className="size-2.5 text-amber-600" />}
                                {ref.title.slice(0, 48)}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                      <Button
                        variant="secondary"
                        size="sm"
                        icon={Plus}
                        onClick={() => openCreateFromCandidate(cand)}
                      >
                        Map
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>

        {/* Right: Detailed Responsibility Transfer, Successor Review & 8-Domain Context */}
        <div className="space-y-4">
          {selectedTransfer ? (
            <Card className="p-5">
              {/* Transfer Header */}
              <div className="border-b border-line pb-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Badge tone={priorityBadgeTone(selectedTransfer.priority)}>
                      {selectedTransfer.priority.toUpperCase()}
                    </Badge>
                    <Badge tone={transferStatusBadge(selectedTransfer.transfer_status).tone}>
                      {transferStatusBadge(selectedTransfer.transfer_status).label}
                    </Badge>
                    <Badge tone={certaintyBadge(selectedTransfer.ownership_certainty).tone}>
                      {certaintyBadge(selectedTransfer.ownership_certainty).label}
                    </Badge>
                    {selectedTransfer.component_name && (
                      <Badge tone="gray">{selectedTransfer.component_name}</Badge>
                    )}
                  </div>
                  <span className="font-mono text-[11px] text-muted">v{selectedTransfer.version}</span>
                </div>
                <h3 className="mt-2 text-base font-semibold text-navy">
                  {selectedTransfer.title || 'Mapped Project Responsibility'}
                </h3>
                <p className="mt-1 text-[13px] leading-relaxed text-slate-700">
                  {selectedTransfer.responsibility_description}
                </p>

                {/* Validation Warnings on this Transfer */}
                {selectedTransfer.validation_warnings.length > 0 && (
                  <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50/70 p-2.5 text-xs text-amber-900">
                    {selectedTransfer.validation_warnings.map((w, i) => (
                      <p key={i} className="flex items-start gap-1.5">
                        <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-amber-700" />
                        <span>{w}</span>
                      </p>
                    ))}
                  </div>
                )}

                {selectedTransfer.blocker_reason && (
                  <div className="mt-3 rounded-lg border border-red-200 bg-red-50/70 p-2.5 text-xs text-red-900">
                    <strong>Blocker:</strong> {selectedTransfer.blocker_reason}
                  </div>
                )}
              </div>

              {/* Owner -> Successor Assignment */}
              <div className="mt-4 grid gap-3 rounded-xl border border-line bg-slate-50/60 p-3.5 sm:grid-cols-2">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                    Current Outgoing Owner
                  </p>
                  <p className="mt-1 text-sm font-semibold text-navy">
                    {selectedTransfer.current_owner_name || 'Unknown'}
                  </p>
                  <p className="text-[11px] text-muted">
                    {selectedTransfer.current_owner_role?.replace(/_/g, ' ') || 'member'} ·{' '}
                    {selectedTransfer.current_owner_active ? 'Active' : 'Inactive'}
                  </p>
                </div>
                <div>
                  <Field label="Designated Incoming Successor">
                    <Select
                      value={reassignSuccessorId}
                      onChange={(e) => setReassignSuccessorId(e.target.value)}
                    >
                      <option value="">Unassigned (select active member)</option>
                      {eligibleSuccessorsForOwner(selectedTransfer.current_owner_id).map((p) => (
                        <option key={p.user_id} value={p.user_id}>
                          {p.full_name} ({p.role_name.replace(/_/g, ' ')})
                        </option>
                      ))}
                    </Select>
                  </Field>
                </div>
              </div>

              {/* Operational Context, Required Access & Transfer Notes */}
              <div className="mt-4 space-y-3">
                <Field label="Operational Context & Runbook Notes">
                  <Textarea
                    rows={2}
                    value={editOpsCtx}
                    onChange={(e) => setEditOpsCtx(e.target.value)}
                    placeholder="Key operational workflows, monitoring dashboards, SLAs, or recurring tasks…"
                  />
                </Field>
                <Field label="Required Access & Permissions">
                  <Input
                    value={editAccess}
                    onChange={(e) => setEditAccess(e.target.value)}
                    placeholder="e.g. GitHub maintainer, staging DB read-only, PagerDuty escalation"
                  />
                </Field>
                <Field label="Transfer Notes">
                  <Textarea
                    rows={2}
                    value={editNotes}
                    onChange={(e) => setEditNotes(e.target.value)}
                    placeholder="Additional transfer notes or handoff schedule details…"
                  />
                </Field>
                <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted">
                  <span>
                    Effective transfer date:{' '}
                    <strong className="text-navy">
                      {selectedTransfer.effective_transfer_date || 'Not scheduled'}
                    </strong>
                  </span>
                  <Button
                    size="sm"
                    variant="secondary"
                    icon={isSaving ? Loader2 : CheckCircle2}
                    disabled={isSaving}
                    onClick={handleSaveDetails}
                  >
                    {isSaving ? 'Saving…' : 'Save Details & Assignment'}
                  </Button>
                </div>
              </div>

              {/* Distinct Three-Step Governance Controls */}
              <div className="mt-5 rounded-xl border border-line bg-slate-50/70 p-4">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">
                  Transfer Governance & Successor Review
                </p>
                <p className="mt-0.5 text-[11.5px] text-muted">
                  Outgoing confirmation, successor acknowledgement, and final managerial approval (Stage 6) are strictly separated events.
                </p>

                {/* Confirmation & Acknowledgement Status Summary */}
                <div className="mt-3 grid gap-2 text-xs sm:grid-cols-2">
                  <div className="rounded-lg border border-line bg-white p-2.5">
                    <p className="text-[11px] font-semibold text-slate-500">1. Outgoing Confirmation</p>
                    {selectedTransfer.outgoing_confirmed_at ? (
                      <p className="mt-1 font-medium text-emerald-700">
                        Confirmed by {selectedTransfer.outgoing_confirmed_by_name} ·{' '}
                        {formatDateTime(selectedTransfer.outgoing_confirmed_at)}
                      </p>
                    ) : (
                      <p className="mt-1 text-amber-700">Awaiting outgoing owner confirmation</p>
                    )}
                    {selectedTransfer.outgoing_confirmation_notes && (
                      <p className="mt-1 text-[11px] text-muted">
                        “{selectedTransfer.outgoing_confirmation_notes}”
                      </p>
                    )}
                  </div>
                  <div className="rounded-lg border border-line bg-white p-2.5">
                    <p className="text-[11px] font-semibold text-slate-500">2. Successor Acknowledgement</p>
                    {selectedTransfer.successor_acknowledged_at ? (
                      <p className="mt-1 font-medium text-emerald-700">
                        Acknowledged by {selectedTransfer.successor_acknowledged_by_name} ·{' '}
                        {formatDateTime(selectedTransfer.successor_acknowledged_at)}
                      </p>
                    ) : (
                      <p className="mt-1 text-muted">Not yet acknowledged by incoming successor</p>
                    )}
                    {selectedTransfer.successor_acknowledgement_notes && (
                      <p className="mt-1 text-[11px] text-muted">
                        “{selectedTransfer.successor_acknowledgement_notes}”
                      </p>
                    )}
                  </div>
                </div>

                {/* Clarification Thread */}
                {(selectedTransfer.clarification_request_notes ||
                  selectedTransfer.clarification_response_notes) && (
                  <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50/70 p-3 text-xs">
                    {selectedTransfer.clarification_request_notes && (
                      <p className="text-amber-900">
                        <strong>
                          Clarification requested ({selectedTransfer.clarification_requested_by_name || 'Successor'}):
                        </strong>{' '}
                        {selectedTransfer.clarification_request_notes}
                      </p>
                    )}
                    {selectedTransfer.clarification_response_notes && (
                      <p className="mt-1.5 text-emerald-900">
                        <strong>Outgoing owner response:</strong>{' '}
                        {selectedTransfer.clarification_response_notes}
                      </p>
                    )}
                  </div>
                )}

                {/* Action Buttons */}
                <div className="mt-3.5 flex flex-wrap gap-2">
                  {isSelectedOutgoingOwner &&
                    selectedTransfer.transfer_status !== 'acknowledged' &&
                    selectedTransfer.transfer_status !== 'completed' && (
                      <Button
                        size="sm"
                        icon={Send}
                        disabled={!selectedTransfer.proposed_successor_id}
                        title={
                          selectedTransfer.proposed_successor_id
                            ? 'Confirm responsibility is prepared for successor review'
                            : 'Assign an eligible successor first'
                        }
                        onClick={() => {
                          setOutgoingNotes('')
                          setConfirmOutgoingOpen(true)
                        }}
                      >
                        Confirm Outgoing Preparation
                      </Button>
                    )}

                  {isSelectedSuccessor &&
                    Boolean(selectedTransfer.outgoing_confirmed_at) &&
                    selectedTransfer.transfer_status !== 'acknowledged' && (
                      <Button
                        size="sm"
                        variant="success"
                        icon={UserCheck}
                        onClick={() => {
                          setAckNotes('')
                          setAckModalOpen(true)
                        }}
                      >
                        Acknowledge Receipt
                      </Button>
                    )}

                  {(isSelectedSuccessor || canManageProject) &&
                    selectedTransfer.transfer_status !== 'acknowledged' && (
                      <Button
                        size="sm"
                        variant="secondary"
                        icon={HelpCircle}
                        onClick={() => {
                          setClarifyMode('request')
                          setClarifyNotes('')
                          setClarifyModalOpen(true)
                        }}
                      >
                        Request Clarification
                      </Button>
                    )}

                  {isSelectedOutgoingOwner &&
                    selectedTransfer.transfer_status === 'clarification_requested' && (
                      <Button
                        size="sm"
                        variant="secondary"
                        icon={MessageSquare}
                        onClick={() => {
                          setClarifyMode('response')
                          setClarifyNotes('')
                          setClarifyModalOpen(true)
                        }}
                      >
                        Respond to Clarification
                      </Button>
                    )}

                  {selectedTransfer.transfer_status === 'acknowledged' && (
                    <Button
                      size="sm"
                      variant="secondary"
                      icon={RotateCcw}
                      onClick={() => {
                        setReopenReason('')
                        setReopenModalOpen(true)
                      }}
                    >
                      Reopen Transfer
                    </Button>
                  )}

                  {selectedTransfer.transfer_status !== 'blocked' &&
                    selectedTransfer.transfer_status !== 'acknowledged' && (
                      <Button
                        size="sm"
                        variant="ghost"
                        icon={XCircle}
                        onClick={() => {
                          setBlockReason('')
                          setBlockModalOpen(true)
                        }}
                      >
                        Mark Blocked
                      </Button>
                    )}
                </div>
              </div>

              {/* 8-Domain Related Knowledge & Supporting Evidence (ACL-Safe) */}
              <div className="mt-5 space-y-4 border-t border-line pt-4">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">
                    Linked Canonical Knowledge ({selectedTransfer.related_knowledge.length})
                  </p>
                  {selectedTransfer.related_knowledge.length === 0 ? (
                    <p className="mt-1.5 text-xs text-muted">
                      No canonical knowledge items linked to this responsibility yet.
                    </p>
                  ) : (
                    <ul className="mt-2 space-y-2">
                      {selectedTransfer.related_knowledge.map((ki) => (
                        <li
                          key={ki.id}
                          className="rounded-lg border border-line bg-slate-50/60 p-3 text-xs"
                        >
                          <div className="flex flex-wrap items-center gap-1.5">
                            <Badge tone={ki.is_verified ? 'green' : 'amber'}>
                              {ki.is_verified ? 'Reviewer-Verified' : ki.review_status.replace(/_/g, ' ')}
                            </Badge>
                            <Badge tone="gray">{ki.category.replace(/_/g, ' ')}</Badge>
                          </div>
                          <p className="mt-1 font-semibold text-navy">{ki.title}</p>
                          <p className="mt-0.5 text-muted">{ki.summary}</p>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">
                    Supporting Evidence & Provenance ({selectedTransfer.supporting_evidence.length})
                  </p>
                  {selectedTransfer.supporting_evidence.length === 0 ? (
                    <p className="mt-1.5 text-xs text-muted">
                      No direct source evidence references attached to this responsibility yet.
                    </p>
                  ) : (
                    <ul className="mt-2 space-y-2">
                      {selectedTransfer.supporting_evidence.map((ev) => (
                        <li
                          key={ev.evidence_id}
                          className="rounded-lg border border-line bg-white p-3 text-xs"
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className="flex items-center gap-1.5 font-semibold text-navy">
                              {ev.acl_restricted && <Lock className="size-3.5 text-amber-600" />}
                              {ev.title}
                            </span>
                            {ev.source_url && !ev.acl_restricted && (
                              <a
                                href={ev.source_url}
                                target="_blank"
                                rel="noreferrer"
                                className="inline-flex items-center gap-1 text-brand hover:underline"
                              >
                                Source <ExternalLink className="size-3" />
                              </a>
                            )}
                          </div>
                          {ev.acl_restricted ? (
                            <p className="mt-1 text-[11px] text-amber-800">
                              Source metadata and excerpt redacted under fail-closed external source ACL policy.
                            </p>
                          ) : (
                            <>
                              {ev.excerpt && (
                                <p className="mt-1 italic text-slate-600">“{ev.excerpt}”</p>
                              )}
                              <p className="mt-1 text-[11px] text-muted">
                                {ev.source_type || 'evidence'}
                                {ev.source_author ? ` · ${ev.source_author}` : ''}
                                {ev.source_timestamp ? ` · ${formatDateTime(ev.source_timestamp)}` : ''}
                              </p>
                            </>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            </Card>
          ) : (
            <Card className="p-6 text-center text-xs text-muted">
              Select a responsibility transfer from the queue, or map one from the discovered project ownership records.
            </Card>
          )}

          {/* E. Responsibility Activity History */}
          <Card className="overflow-hidden">
            <CardHeader
              title={`Ownership Activity History (${workspace.activity_history.length})`}
              subtitle="Immutable audit log of mappings, reassignments, confirmations, clarifications, and acknowledgements."
            />
            {workspace.activity_history.length === 0 ? (
              <div className="p-5 text-center text-xs text-muted">
                No responsibility transfer activity recorded yet.
              </div>
            ) : (
              <ul className="max-h-60 divide-y divide-line overflow-y-auto">
                {workspace.activity_history.map((ev) => (
                  <li key={ev.id} className="px-4 py-3 text-xs">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium text-navy">{ev.summary}</span>
                      <span className="shrink-0 text-[11px] text-muted">
                        {formatDateTime(ev.created_at)}
                      </span>
                    </div>
                    <p className="mt-0.5 text-[11px] text-muted">
                      {ev.actor_name || 'System'} · {ev.event_type}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>

      {/* Create / Map Responsibility Modal */}
      <Modal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title="Map Responsibility Transfer"
        subtitle="Create a persisted ownership transfer record grounded in actual project context and active team members."
        footer={
          <>
            <Button variant="secondary" onClick={() => setCreateOpen(false)}>
              Cancel
            </Button>
            <Button
              disabled={isCreating || newDesc.trim().length < 5}
              onClick={handleCreateTransfer}
            >
              {isCreating ? 'Mapping…' : 'Create Transfer Record'}
            </Button>
          </>
        }
      >
        <div className="space-y-3.5">
          <Field label="Responsibility Title">
            <Input
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              placeholder="e.g. Core Billing API & Webhook Worker Ownership"
            />
          </Field>
          <Field label="Description (required)">
            <Textarea
              rows={3}
              value={newDesc}
              onChange={(e) => setNewDesc(e.target.value)}
              placeholder="Describe the scope of ownership, recurring duties, and system boundaries…"
            />
          </Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Component / Service / Workstream">
              <Input
                value={newComponent}
                onChange={(e) => setNewComponent(e.target.value)}
                placeholder="e.g. billing-worker"
              />
            </Field>
            <Field label="Knowledge Domain">
              <Select value={newDomain} onChange={(e) => setNewDomain(e.target.value)}>
                {DOMAIN_OPTIONS.map((d) => (
                  <option key={d.value} value={d.value}>
                    {d.label}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Priority">
              <Select value={newPriority} onChange={(e) => setNewPriority(e.target.value)}>
                <option value="critical">Critical</option>
                <option value="high">High</option>
                <option value="medium">Medium</option>
                <option value="low">Low</option>
              </Select>
            </Field>
            <Field label="Ownership Certainty">
              <Select value={newCertainty} onChange={(e) => setNewCertainty(e.target.value)}>
                <option value="confirmed">Confirmed</option>
                <option value="proposed">Proposed</option>
                <option value="uncertain">Uncertain</option>
              </Select>
            </Field>
            <Field label="Effective Date">
              <Input
                type="date"
                value={newEffectiveDate}
                onChange={(e) => setNewEffectiveDate(e.target.value)}
              />
            </Field>
          </div>
          <Field label="Proposed Incoming Successor (active project members)">
            <Select value={newSuccessorId} onChange={(e) => setNewSuccessorId(e.target.value)}>
              <option value="">Leave unassigned for now</option>
              {eligibleSuccessorsForOwner(workspace.departing_member_id).map((p) => (
                <option key={p.user_id} value={p.user_id}>
                  {p.full_name} ({p.role_name.replace(/_/g, ' ')})
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Operational Context">
            <Textarea
              rows={2}
              value={newOpsCtx}
              onChange={(e) => setNewOpsCtx(e.target.value)}
              placeholder="Deployment cadence, alerts, escalation paths, or key runbooks…"
            />
          </Field>
          <Field label="Required Access / Permissions">
            <Input
              value={newAccess}
              onChange={(e) => setNewAccess(e.target.value)}
              placeholder="e.g. GitHub repo write, cloud read role"
            />
          </Field>
          <Field label="Transfer Notes">
            <Textarea
              rows={2}
              value={newNotes}
              onChange={(e) => setNewNotes(e.target.value)}
            />
          </Field>
        </div>
      </Modal>

      {/* Outgoing Owner Confirmation Modal */}
      <Modal
        open={confirmOutgoingOpen}
        onClose={() => setConfirmOutgoingOpen(false)}
        title="Confirm Outgoing Responsibility Preparation"
        subtitle="Marks this responsibility prepared and advances it to Awaiting Successor Acknowledgement."
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirmOutgoingOpen(false)}>
              Cancel
            </Button>
            <Button disabled={isSubmittingGovernance} onClick={handleConfirmOutgoing}>
              {isSubmittingGovernance ? 'Confirming…' : 'Confirm Outgoing Transfer'}
            </Button>
          </>
        }
      >
        <Field label="Confirmation Notes (optional)">
          <Textarea
            rows={3}
            value={outgoingNotes}
            onChange={(e) => setOutgoingNotes(e.target.value)}
            placeholder="Summarize walkthroughs, open items, and operational context handed over…"
          />
        </Field>
      </Modal>

      {/* Successor Acknowledgement Modal */}
      <Modal
        open={ackModalOpen}
        onClose={() => setAckModalOpen(false)}
        title="Acknowledge Responsibility Transfer"
        subtitle="Confirms that you have reviewed the operational context and supporting evidence. This does not substitute for final managerial approval."
        footer={
          <>
            <Button variant="secondary" onClick={() => setAckModalOpen(false)}>
              Cancel
            </Button>
            <Button variant="success" disabled={isSubmittingGovernance} onClick={handleSuccessorAck}>
              {isSubmittingGovernance ? 'Acknowledging…' : 'Confirm Acknowledgement'}
            </Button>
          </>
        }
      >
        <Field label="Acknowledgement Notes (optional)">
          <Textarea
            rows={3}
            value={ackNotes}
            onChange={(e) => setAckNotes(e.target.value)}
            placeholder="Confirm readiness to assume ownership or note follow-up onboarding items…"
          />
        </Field>
      </Modal>

      {/* Clarification Request / Response Modal */}
      <Modal
        open={clarifyModalOpen}
        onClose={() => setClarifyModalOpen(false)}
        title={
          clarifyMode === 'request'
            ? 'Request Clarification on Responsibility'
            : 'Respond to Clarification Request'
        }
        subtitle={
          clarifyMode === 'request'
            ? 'Flags this transfer as requiring additional information from the outgoing owner.'
            : 'Provides requested operational context and returns transfer for successor review.'
        }
        footer={
          <>
            <Button variant="secondary" onClick={() => setClarifyModalOpen(false)}>
              Cancel
            </Button>
            <Button
              disabled={isSubmittingGovernance || clarifyNotes.trim().length < 3}
              onClick={handleClarificationSubmit}
            >
              {isSubmittingGovernance ? 'Submitting…' : 'Submit'}
            </Button>
          </>
        }
      >
        <Field label={clarifyMode === 'request' ? 'What requires clarification? (required)' : 'Clarification Response (required)'}>
          <Textarea
            rows={3}
            value={clarifyNotes}
            onChange={(e) => setClarifyNotes(e.target.value)}
            placeholder="Provide specific questions or clarifying operational details…"
          />
        </Field>
      </Modal>

      {/* Reopen Transfer Modal */}
      <Modal
        open={reopenModalOpen}
        onClose={() => setReopenModalOpen(false)}
        title="Reopen Responsibility Transfer"
        subtitle="Clears prior successor acknowledgement and updates readiness assessment."
        footer={
          <>
            <Button variant="secondary" onClick={() => setReopenModalOpen(false)}>
              Cancel
            </Button>
            <Button
              disabled={isSubmittingGovernance || reopenReason.trim().length < 5}
              onClick={handleReopen}
            >
              {isSubmittingGovernance ? 'Reopening…' : 'Confirm Reopen'}
            </Button>
          </>
        }
      >
        <Field label="Reason for Reopening (required, min 5 chars)">
          <Textarea
            rows={3}
            value={reopenReason}
            onChange={(e) => setReopenReason(e.target.value)}
            placeholder="Explain why this responsibility transfer needs further work or verification…"
          />
        </Field>
      </Modal>

      {/* Mark Blocked Modal */}
      <Modal
        open={blockModalOpen}
        onClose={() => setBlockModalOpen(false)}
        title="Mark Responsibility Transfer Blocked"
        subtitle="Blocked transfers surface as active readiness blockers until resolved."
        footer={
          <>
            <Button variant="secondary" onClick={() => setBlockModalOpen(false)}>
              Cancel
            </Button>
            <Button
              disabled={isSubmittingGovernance || blockReason.trim().length < 3}
              onClick={handleMarkBlocked}
            >
              {isSubmittingGovernance ? 'Saving…' : 'Mark Blocked'}
            </Button>
          </>
        }
      >
        <Field label="Blocker Reason (required)">
          <Textarea
            rows={3}
            value={blockReason}
            onChange={(e) => setBlockReason(e.target.value)}
            placeholder="e.g. Waiting for AWS production IAM role provisioning or team member onboarding…"
          />
        </Field>
      </Modal>
    </div>
  )
}
