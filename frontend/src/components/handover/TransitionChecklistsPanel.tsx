'use client'

import React, { useCallback, useEffect, useMemo, useState } from 'react'
import {
  AlertCircle,
  AlertTriangle,
  Calendar,
  CheckCircle2,
  ClipboardCheck,
  Clock,
  ExternalLink,
  History,
  ListChecks,
  Loader2,
  Lock,
  Plus,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
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
  Field,
  Input,
  Modal,
  Progress,
  Select,
  Textarea,
  cn,
} from '../figma-ui/index'
import { ListSkeleton } from '../loading'
import { api } from '../../lib/api'
import type {
  HandoverChecklistGroupDetail,
  HandoverChecklistItemDetail,
  HandoverChecklistWorkspaceResponse,
  ProjectMember,
} from '../../lib/types'

export interface TransitionChecklistsPanelProps {
  caseId: string
  projectId: string
  currentUserId?: string | null
  members: ProjectMember[]
  onDataChanged?: () => void
  onReassessReadiness?: () => Promise<void>
  isReassessingReadiness?: boolean
}

function statusBadge(
  status: string,
  isOverdue: boolean,
): { label: string; tone: 'green' | 'amber' | 'red' | 'blue' | 'gray' } {
  if (isOverdue && status !== 'completed' && status !== 'skipped') {
    return { label: 'Overdue', tone: 'red' }
  }
  switch (status) {
    case 'completed':
      return { label: 'Completed', tone: 'green' }
    case 'in_progress':
      return { label: 'In Progress', tone: 'blue' }
    case 'blocked':
      return { label: 'Blocked', tone: 'red' }
    case 'skipped':
      return { label: 'Skipped', tone: 'gray' }
    case 'pending':
    default:
      return { label: 'Pending', tone: 'amber' }
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

function toDateInputValue(iso?: string | null): string {
  if (!iso) return ''
  try {
    return new Date(iso).toISOString().slice(0, 10)
  } catch {
    return ''
  }
}

export function TransitionChecklistsPanel({
  caseId,
  projectId,
  currentUserId,
  members,
  onDataChanged,
  onReassessReadiness,
  isReassessingReadiness,
}: TransitionChecklistsPanelProps) {
  const [workspace, setWorkspace] = useState<HandoverChecklistWorkspaceResponse | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [actionSuccess, setActionSuccess] = useState<string | null>(null)
  const [readinessDirty, setReadinessDirty] = useState(false)

  const [filterMode, setFilterMode] = useState<
    'all' | 'mandatory' | 'outstanding' | 'blocked' | 'overdue' | 'completed'
  >('all')
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null)
  const [isGenerating, setIsGenerating] = useState(false)
  const [isSavingItem, setIsSavingItem] = useState(false)
  const [isReviewing, setIsReviewing] = useState(false)

  // Detail editor fields for selected item
  const [editStatus, setEditStatus] = useState('pending')
  const [editAssignee, setEditAssignee] = useState('')
  const [editDueDate, setEditDueDate] = useState('')
  const [editNotes, setEditNotes] = useState('')
  const [editCriteria, setEditCriteria] = useState('')

  // Reopen modal
  const [reopenModalOpen, setReopenModalOpen] = useState(false)
  const [reopenTargetStatus, setReopenTargetStatus] = useState<'pending' | 'in_progress' | 'blocked'>('in_progress')
  const [reopenReason, setReopenReason] = useState('')

  // Review modal
  const [reviewModalOpen, setReviewModalOpen] = useState(false)
  const [reviewApproved, setReviewApproved] = useState(true)
  const [reviewNotes, setReviewNotes] = useState('')

  // Add custom item modal
  const [addModalOpen, setAddModalOpen] = useState(false)
  const [newChecklistId, setNewChecklistId] = useState('')
  const [newItemText, setNewItemText] = useState('')
  const [newDescription, setNewDescription] = useState('')
  const [newCriteria, setNewCriteria] = useState('')
  const [newCategory, setNewCategory] = useState('operations')
  const [newBlocking, setNewBlocking] = useState(false)
  const [newAssignee, setNewAssignee] = useState('')
  const [newDueDate, setNewDueDate] = useState('')
  const [isCreating, setIsCreating] = useState(false)

  const activeMembers = useMemo(
    () => (members || []).filter((m) => (m.status || 'active') === 'active'),
    [members],
  )

  const loadWorkspace = useCallback(async () => {
    if (!projectId || !caseId) return
    setIsLoading(true)
    setError(null)
    try {
      const data = await api.handover.getChecklistWorkspace(projectId, caseId)
      setWorkspace(data)
      if (data.checklists[0]?.id && !newChecklistId) {
        setNewChecklistId(data.checklists[0].id)
      }
      const allItems = data.checklists.flatMap((c) => c.items)
      setSelectedItemId((prev) => {
        if (prev && allItems.some((i) => i.id === prev)) return prev
        return allItems[0]?.id ?? null
      })
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load transition checklists.')
    } finally {
      setIsLoading(false)
    }
  }, [projectId, caseId, newChecklistId])

  useEffect(() => {
    void loadWorkspace()
  }, [loadWorkspace])

  const allItems = useMemo(
    () => (workspace?.checklists || []).flatMap((c) => c.items),
    [workspace],
  )

  const selectedItem: HandoverChecklistItemDetail | null = useMemo(
    () => allItems.find((i) => i.id === selectedItemId) ?? null,
    [allItems, selectedItemId],
  )

  useEffect(() => {
    if (!selectedItem) return
    setEditStatus(selectedItem.status)
    setEditAssignee(selectedItem.assigned_to_user_id || '')
    setEditDueDate(toDateInputValue(selectedItem.due_date))
    setEditNotes(selectedItem.notes || '')
    setEditCriteria(selectedItem.completion_criteria || '')
    setActionError(null)
  }, [selectedItem])

  const handleGenerate = async () => {
    setIsGenerating(true)
    setActionError(null)
    setActionSuccess(null)
    try {
      await api.handover.generateChecklists(projectId, caseId)
      await loadWorkspace()
      onDataChanged?.()
      setActionSuccess('Standard transition checklists generated and persisted.')
      setReadinessDirty(true)
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : 'Failed to generate checklists.')
    } finally {
      setIsGenerating(false)
    }
  }

  const handleSaveItem = async () => {
    if (!selectedItem) return
    // If transitioning from completed to non-completed, require explicit Reopen modal!
    if (selectedItem.status === 'completed' && editStatus !== 'completed') {
      setReopenTargetStatus(
        editStatus === 'blocked' ? 'blocked' : editStatus === 'pending' ? 'pending' : 'in_progress',
      )
      setReopenReason('')
      setReopenModalOpen(true)
      return
    }

    setIsSavingItem(true)
    setActionError(null)
    setActionSuccess(null)
    try {
      await api.handover.updateChecklistItem(projectId, selectedItem.id, {
        status: editStatus,
        notes: editNotes,
        completion_criteria: editCriteria || undefined,
        assigned_to_user_id: editAssignee || null,
        clear_assignee: !editAssignee && Boolean(selectedItem.assigned_to_user_id),
        due_date: editDueDate ? new Date(`${editDueDate}T17:00:00Z`).toISOString() : null,
        clear_due_date: !editDueDate && Boolean(selectedItem.due_date),
        expected_version: selectedItem.version,
      })
      await loadWorkspace()
      onDataChanged?.()
      setActionSuccess('Checklist item changes saved and audited.')
      setReadinessDirty(true)
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : 'Could not update checklist item.')
    } finally {
      setIsSavingItem(false)
    }
  }

  const handleConfirmReopen = async () => {
    if (!selectedItem || reopenReason.trim().length < 3) return
    setIsSavingItem(true)
    setActionError(null)
    setActionSuccess(null)
    try {
      await api.handover.updateChecklistItem(projectId, selectedItem.id, {
        status: reopenTargetStatus,
        reopen_reason: reopenReason.trim(),
        notes: editNotes || undefined,
        expected_version: selectedItem.version,
      })
      setReopenModalOpen(false)
      setReopenReason('')
      await loadWorkspace()
      onDataChanged?.()
      setActionSuccess('Checklist item reopened with audit rationale.')
      setReadinessDirty(true)
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : 'Failed to reopen checklist item.')
    } finally {
      setIsSavingItem(false)
    }
  }

  const handleSubmitReview = async () => {
    if (!selectedItem) return
    if (!reviewApproved && reviewNotes.trim().length < 3) {
      setActionError('Reopening during reviewer verification requires review notes.')
      return
    }
    setIsReviewing(true)
    setActionError(null)
    setActionSuccess(null)
    try {
      await api.handover.reviewChecklistItem(projectId, selectedItem.id, {
        approved: reviewApproved,
        review_notes: reviewNotes.trim() || undefined,
        expected_version: selectedItem.version,
      })
      setReviewModalOpen(false)
      setReviewNotes('')
      await loadWorkspace()
      onDataChanged?.()
      setActionSuccess(
        reviewApproved
          ? 'Independent reviewer verification recorded.'
          : 'Checklist item returned for rework during review.',
      )
      setReadinessDirty(true)
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : 'Reviewer verification failed.')
    } finally {
      setIsReviewing(false)
    }
  }

  const handleCreateCustomItem = async () => {
    if (!newChecklistId || newItemText.trim().length < 3) return
    setIsCreating(true)
    setActionError(null)
    setActionSuccess(null)
    try {
      const created = await api.handover.createChecklistItem(projectId, caseId, newChecklistId, {
        item_text: newItemText.trim(),
        description: newDescription.trim() || undefined,
        completion_criteria: newCriteria.trim() || undefined,
        category: newCategory,
        blocking: newBlocking,
        assigned_to_user_id: newAssignee || null,
        due_date: newDueDate ? new Date(`${newDueDate}T17:00:00Z`).toISOString() : null,
      })
      setAddModalOpen(false)
      setNewItemText('')
      setNewDescription('')
      setNewCriteria('')
      setNewBlocking(false)
      setNewAssignee('')
      setNewDueDate('')
      await loadWorkspace()
      setSelectedItemId(created.id)
      onDataChanged?.()
      setActionSuccess('Custom checklist item added and persisted.')
      setReadinessDirty(true)
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : 'Failed to create checklist item.')
    } finally {
      setIsCreating(false)
    }
  }

  const filterItem = (item: HandoverChecklistItemDetail): boolean => {
    switch (filterMode) {
      case 'mandatory':
        return item.blocking
      case 'outstanding':
        return item.status !== 'completed' && item.status !== 'skipped'
      case 'blocked':
        return item.status === 'blocked'
      case 'overdue':
        return item.is_overdue
      case 'completed':
        return item.status === 'completed'
      case 'all':
      default:
        return true
    }
  }

  if (isLoading && !workspace) {
    return (
      <div className="p-4 space-y-4" role="status" aria-live="polite">
        <ListSkeleton count={5} />
      </div>
    )
  }

  if (error && !workspace) {
    return (
      <Card className="p-6">
        <Callout tone="red" icon={AlertCircle} title="Unable to load transition checklists">
          <p className="mb-3">{error}</p>
          <Button variant="secondary" size="sm" icon={RefreshCw} onClick={loadWorkspace}>
            Retry
          </Button>
        </Callout>
      </Card>
    )
  }

  if (!workspace || workspace.checklists.length === 0) {
    return (
      <Card>
        <EmptyState
          icon={ListChecks}
          title="No transition checklists generated yet"
          body="Generate the canonical Pre-Handover, Knowledge Transfer, and Access Revocation checklists to track mandatory operational offboarding tasks."
          action={
            <Button
              icon={isGenerating ? Loader2 : ClipboardCheck}
              disabled={isGenerating}
              onClick={handleGenerate}
            >
              {isGenerating ? 'Generating…' : 'Generate Standard Checklists'}
            </Button>
          }
        />
      </Card>
    )
  }

  const canIndependentlyReview =
    selectedItem?.status === 'completed' &&
    selectedItem.completed_by_user_id !== currentUserId

  return (
    <div className="space-y-6" data-testid="transition-checklists-panel">
      {actionSuccess && (
        <Callout tone="green" icon={CheckCircle2} title="Checklist persisted">
          {actionSuccess}
        </Callout>
      )}
      {actionError && (
        <Callout tone="red" icon={AlertCircle} title="Checklist action failed">
          {actionError}
        </Callout>
      )}
      {readinessDirty && onReassessReadiness && (
        <Callout tone="amber" icon={RefreshCw} title="Readiness reassessment recommended">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span>
              Checklist progress changed. Run readiness reassessment to persist an updated gate snapshot.
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

      {/* A. Transition Checklist Overview */}
      <Card className="p-5 sm:p-6">
        <div className="flex flex-col gap-4 border-b border-line pb-5 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <ListChecks className="size-5 text-brand" />
              <h2 className="text-lg font-semibold text-navy">Transition Checklists</h2>
              <Badge tone={workspace.mandatory_outstanding === 0 ? 'green' : 'amber'}>
                {workspace.mandatory_completed}/{workspace.mandatory_total} Mandatory Done
              </Badge>
            </div>
            <p className="mt-1 text-[13px] text-muted">
              Persistent offboarding, knowledge transfer, and access revocation checklists. Item completion, independent reviewer verification, and final managerial sign-off are tracked separately.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              icon={Plus}
              onClick={() => {
                if (!newChecklistId && workspace.checklists[0]) {
                  setNewChecklistId(workspace.checklists[0].id)
                }
                setAddModalOpen(true)
              }}
            >
              Add Item
            </Button>
            <Button variant="secondary" size="sm" icon={RefreshCw} onClick={loadWorkspace}>
              Refresh
            </Button>
          </div>
        </div>

        {/* KPI Metrics Strip */}
        <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <div className="rounded-xl border border-line bg-slate-50/70 p-3">
            <p className="text-[11px] text-muted">Overall Progress</p>
            <p className="text-lg font-bold text-navy">{workspace.completion_pct}%</p>
            <p className="text-[11px] text-muted">
              {workspace.completed_items}/{workspace.total_items} items
            </p>
          </div>
          <div className="rounded-xl border border-amber-200 bg-amber-50/50 p-3">
            <p className="text-[11px] text-amber-700">Mandatory Blocking</p>
            <p className="text-lg font-bold text-amber-800">{workspace.mandatory_outstanding}</p>
            <p className="text-[11px] text-amber-700">of {workspace.mandatory_total} open</p>
          </div>
          <div className="rounded-xl border border-line bg-slate-50/70 p-3">
            <p className="text-[11px] text-muted">Optional Items</p>
            <p className="text-lg font-bold text-navy">
              {workspace.optional_completed}/{workspace.optional_total}
            </p>
            <p className="text-[11px] text-muted">completed</p>
          </div>
          <div className="rounded-xl border border-line bg-slate-50/70 p-3">
            <p className="text-[11px] text-muted">Outstanding</p>
            <p className="text-lg font-bold text-navy">{workspace.outstanding_items}</p>
            <p className="text-[11px] text-muted">remaining</p>
          </div>
          <div
            className={cn(
              'rounded-xl border p-3',
              workspace.blocked_items > 0
                ? 'border-red-200 bg-red-50/50'
                : 'border-line bg-slate-50/70',
            )}
          >
            <p className={cn('text-[11px]', workspace.blocked_items > 0 ? 'text-red-700' : 'text-muted')}>
              Blocked
            </p>
            <p className={cn('text-lg font-bold', workspace.blocked_items > 0 ? 'text-red-800' : 'text-navy')}>
              {workspace.blocked_items}
            </p>
            <p className="text-[11px] text-muted">escalations</p>
          </div>
          <div
            className={cn(
              'rounded-xl border p-3',
              workspace.overdue_items > 0
                ? 'border-red-200 bg-red-50/50'
                : 'border-line bg-slate-50/70',
            )}
          >
            <p className={cn('text-[11px]', workspace.overdue_items > 0 ? 'text-red-700' : 'text-muted')}>
              Overdue
            </p>
            <p className={cn('text-lg font-bold', workspace.overdue_items > 0 ? 'text-red-800' : 'text-navy')}>
              {workspace.overdue_items}
            </p>
            <p className="text-[11px] text-muted">past due date</p>
          </div>
        </div>

        <div className="mt-4">
          <Progress
            value={workspace.completion_pct}
            tone={workspace.mandatory_outstanding === 0 ? 'green' : 'blue'}
          />
        </div>

        {/* Filter Bar */}
        <div className="mt-4 flex flex-wrap items-center gap-2">
          {(
            [
              ['all', `All (${workspace.total_items})`],
              ['mandatory', `Mandatory (${workspace.mandatory_total})`],
              ['outstanding', `Outstanding (${workspace.outstanding_items})`],
              ['blocked', `Blocked (${workspace.blocked_items})`],
              ['overdue', `Overdue (${workspace.overdue_items})`],
              ['completed', `Completed (${workspace.completed_items})`],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => setFilterMode(key)}
              className={cn(
                'rounded-full border px-3 py-1 text-xs font-medium transition',
                filterMode === key
                  ? 'border-brand bg-tint/50 text-brand'
                  : 'border-line bg-white text-muted hover:border-slate-300 hover:text-navy',
              )}
            >
              {label}
            </button>
          ))}
        </div>
      </Card>

      {/* B. Master–Detail Checklists & Item Inspector */}
      <div className="grid gap-6 lg:grid-cols-[1.15fr_0.85fr]">
        {/* Left: Categorised Checklists */}
        <div className="space-y-4">
          {workspace.checklists.map((grp: HandoverChecklistGroupDetail) => {
            const visibleItems = grp.items.filter(filterItem)
            const grpPct = grp.total_items > 0 ? Math.round((grp.completed_items / grp.total_items) * 100) : 0
            return (
              <Card key={grp.id} className="overflow-hidden">
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line bg-slate-50/60 px-5 py-3.5">
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="text-sm font-semibold text-navy">
                        {grp.title || grp.checklist_type.replace(/_/g, ' ')}
                      </h3>
                      <Badge tone={grp.mandatory_outstanding === 0 ? 'green' : 'amber'}>
                        {grp.mandatory_outstanding === 0
                          ? 'Mandatory Clear'
                          : `${grp.mandatory_outstanding} Mandatory Left`}
                      </Badge>
                    </div>
                    <p className="mt-0.5 text-[11.5px] text-muted">
                      {grp.completed_items}/{grp.total_items} completed ({grpPct}%)
                      {grp.blocked_items > 0 ? ` · ${grp.blocked_items} blocked` : ''}
                      {grp.overdue_items > 0 ? ` · ${grp.overdue_items} overdue` : ''}
                    </p>
                  </div>
                  <div className="w-28">
                    <Progress value={grpPct} tone={grp.mandatory_outstanding === 0 ? 'green' : 'blue'} />
                  </div>
                </div>

                {visibleItems.length === 0 ? (
                  <div className="px-5 py-4 text-xs text-muted">
                    No items match the current filter in this category.
                  </div>
                ) : (
                  <div className="divide-y divide-line">
                    {visibleItems.map((item) => {
                      const sb = statusBadge(item.status, item.is_overdue)
                      const isSelected = selectedItem?.id === item.id
                      return (
                        <button
                          key={item.id}
                          type="button"
                          onClick={() => setSelectedItemId(item.id)}
                          className={cn(
                            'flex w-full items-start gap-3 px-5 py-3.5 text-left transition',
                            isSelected ? 'bg-tint/40 ring-1 ring-inset ring-brand/25' : 'hover:bg-slate-50',
                          )}
                        >
                          <span className="mt-0.5 shrink-0">
                            {item.status === 'completed' ? (
                              <CheckCircle2 className="size-4 text-emerald-600" />
                            ) : item.status === 'blocked' ? (
                              <XCircle className="size-4 text-red-600" />
                            ) : (
                              <span className="block size-4 rounded-full border-2 border-slate-300" />
                            )}
                          </span>
                          <div className="min-w-0 flex-1">
                            <p
                              className={cn(
                                'text-[13px] font-medium',
                                item.status === 'completed' ? 'text-muted line-through' : 'text-navy',
                              )}
                            >
                              {item.item_text}
                            </p>
                            <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[11px]">
                              <Badge tone={sb.tone}>{sb.label}</Badge>
                              {item.blocking ? (
                                <Badge tone="red">Mandatory</Badge>
                              ) : (
                                <Badge tone="gray">Optional</Badge>
                              )}
                              {item.reviewed_at && (
                                <Badge tone="green">
                                  <ShieldCheck className="mr-1 inline size-3" />
                                  Reviewed
                                </Badge>
                              )}
                              {item.reopened_count > 0 && (
                                <Badge tone="amber">Reopened ×{item.reopened_count}</Badge>
                              )}
                              {item.assigned_to_name && (
                                <span className="text-muted">Assigned: {item.assigned_to_name}</span>
                              )}
                              {item.due_date && (
                                <span className={cn(item.is_overdue ? 'font-medium text-red-700' : 'text-muted')}>
                                  Due {new Date(item.due_date).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}
                                </span>
                              )}
                            </div>
                          </div>
                        </button>
                      )
                    })}
                  </div>
                )}
              </Card>
            )
          })}
        </div>

        {/* Right: Checklist Item Detail Inspector */}
        <div className="space-y-4">
          {selectedItem ? (
            <Card className="p-5">
              <div className="flex flex-wrap items-start justify-between gap-2 border-b border-line pb-4">
                <div>
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Badge tone={statusBadge(selectedItem.status, selectedItem.is_overdue).tone}>
                      {statusBadge(selectedItem.status, selectedItem.is_overdue).label}
                    </Badge>
                    <Badge tone={selectedItem.blocking ? 'red' : 'gray'}>
                      {selectedItem.blocking ? 'Mandatory Gate' : 'Optional'}
                    </Badge>
                    {selectedItem.category && (
                      <Badge tone="blue">{selectedItem.category.replace(/_/g, ' ')}</Badge>
                    )}
                  </div>
                  <h3 className="mt-2 text-[15px] font-semibold text-navy">{selectedItem.item_text}</h3>
                  {selectedItem.description && (
                    <p className="mt-1 text-xs leading-relaxed text-muted">{selectedItem.description}</p>
                  )}
                </div>
                <span className="text-[11px] font-mono text-muted">v{selectedItem.version}</span>
              </div>

              {/* Completion Criteria */}
              <div className="mt-4 space-y-3.5">
                <Field label="Completion Criteria">
                  <Textarea
                    rows={2}
                    value={editCriteria}
                    onChange={(e) => setEditCriteria(e.target.value)}
                    placeholder="Define objective evidence or verification criteria required to complete this item."
                  />
                </Field>

                <div className="grid gap-3 sm:grid-cols-2">
                  <Field label="Status">
                    <Select value={editStatus} onChange={(e) => setEditStatus(e.target.value)}>
                      <option value="pending">Pending</option>
                      <option value="in_progress">In Progress</option>
                      <option value="completed">Completed</option>
                      <option value="blocked">Blocked</option>
                      <option value="skipped">Skipped</option>
                    </Select>
                  </Field>
                  <Field label="Assigned Participant">
                    <Select value={editAssignee} onChange={(e) => setEditAssignee(e.target.value)}>
                      <option value="">Unassigned</option>
                      {activeMembers.map((m) => (
                        <option key={m.user_id} value={m.user_id}>
                          {m.full_name || m.email} ({m.role_name})
                        </option>
                      ))}
                    </Select>
                  </Field>
                </div>

                <Field label="Due Date">
                  <Input
                    type="date"
                    value={editDueDate}
                    onChange={(e) => setEditDueDate(e.target.value)}
                  />
                </Field>

                <Field label="Completion / Progress Notes">
                  <Textarea
                    rows={3}
                    value={editNotes}
                    onChange={(e) => setEditNotes(e.target.value)}
                    placeholder="Document completion details, blocker context, or handoff verification notes…"
                  />
                </Field>

                {/* Attached Supporting Evidence (ACL-safe) */}
                {selectedItem.evidence_summary && (
                  <div className="rounded-xl border border-line bg-slate-50/70 p-3">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                      Supporting Evidence
                    </p>
                    <div className="mt-1.5 flex items-center justify-between gap-2 text-xs">
                      <span className="flex items-center gap-1.5 font-medium text-navy">
                        {selectedItem.evidence_summary.acl_restricted && (
                          <Lock className="size-3.5 text-amber-600" />
                        )}
                        {selectedItem.evidence_summary.title}
                      </span>
                      {selectedItem.evidence_summary.source_url &&
                        !selectedItem.evidence_summary.acl_restricted && (
                          <a
                            href={selectedItem.evidence_summary.source_url}
                            target="_blank"
                            rel="noreferrer"
                            className="inline-flex items-center gap-1 text-brand hover:underline"
                          >
                            Source <ExternalLink className="size-3" />
                          </a>
                        )}
                    </div>
                  </div>
                )}

                {/* Action Buttons */}
                <div className="flex flex-wrap items-center gap-2 pt-1">
                  <Button
                    icon={isSavingItem ? Loader2 : CheckCircle2}
                    disabled={isSavingItem}
                    onClick={handleSaveItem}
                  >
                    {isSavingItem
                      ? 'Saving…'
                      : selectedItem.status === 'completed' && editStatus !== 'completed'
                      ? 'Reopen Item…'
                      : 'Save Changes'}
                  </Button>

                  {selectedItem.status === 'completed' && (
                    <Button
                      variant="secondary"
                      icon={RotateCcw}
                      onClick={() => {
                        setReopenTargetStatus('in_progress')
                        setReopenReason('')
                        setReopenModalOpen(true)
                      }}
                    >
                      Reopen
                    </Button>
                  )}

                  {selectedItem.status === 'completed' && !selectedItem.reviewed_at && (
                    <Button
                      variant="secondary"
                      icon={UserCheck}
                      disabled={!canIndependentlyReview}
                      title={
                        canIndependentlyReview
                          ? 'Record independent reviewer verification'
                          : 'Separation of duties: completer cannot independently verify their own item'
                      }
                      onClick={() => {
                        setReviewApproved(true)
                        setReviewNotes('')
                        setReviewModalOpen(true)
                      }}
                    >
                      Verify as Reviewer
                    </Button>
                  )}
                </div>
              </div>

              {/* Completion, Review & Reopen Audit Provenance */}
              <div className="mt-5 space-y-2.5 border-t border-line pt-4 text-xs">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                  Completion & Review Provenance
                </p>
                <div className="flex items-center justify-between text-muted">
                  <span>Completed by</span>
                  <span className="font-medium text-navy">
                    {selectedItem.completed_by_name
                      ? `${selectedItem.completed_by_name} · ${formatDateTime(selectedItem.completed_at)}`
                      : 'Not yet completed'}
                  </span>
                </div>
                <div className="flex items-center justify-between text-muted">
                  <span>Reviewer verification</span>
                  <span className="font-medium text-navy">
                    {selectedItem.reviewed_by_name
                      ? `${selectedItem.reviewed_by_name} · ${formatDateTime(selectedItem.reviewed_at)}`
                      : 'Pending independent review'}
                  </span>
                </div>
                {selectedItem.review_notes && (
                  <p className="rounded-lg bg-emerald-50/70 px-3 py-2 text-emerald-800">
                    Reviewer note: {selectedItem.review_notes}
                  </p>
                )}
                {selectedItem.reopened_count > 0 && (
                  <div className="rounded-lg border border-amber-200 bg-amber-50/60 p-3 text-amber-900">
                    <p className="font-semibold">
                      Reopened {selectedItem.reopened_count} time{selectedItem.reopened_count === 1 ? '' : 's'}
                      {selectedItem.reopened_by_name ? ` by ${selectedItem.reopened_by_name}` : ''}
                    </p>
                    {selectedItem.reopened_reason && (
                      <p className="mt-1 text-xs">Reason: {selectedItem.reopened_reason}</p>
                    )}
                  </div>
                )}
              </div>
            </Card>
          ) : (
            <Card className="p-6 text-center text-xs text-muted">
              Select a checklist item to inspect criteria, update status, or record reviewer verification.
            </Card>
          )}

          {/* E. Checklist Activity History */}
          <Card className="overflow-hidden">
            <CardHeader
              title={`Checklist Activity History (${workspace.activity_history.length})`}
              subtitle="Immutable audit log of checklist completions, reopenings, and independent reviews."
            />
            {workspace.activity_history.length === 0 ? (
              <div className="p-5 text-center text-xs text-muted">No checklist activity recorded yet.</div>
            ) : (
              <ul className="max-h-64 divide-y divide-line overflow-y-auto">
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

      {/* Reopen Modal */}
      <Modal
        open={reopenModalOpen}
        onClose={() => setReopenModalOpen(false)}
        title="Reopen Completed Checklist Item"
        subtitle="Reopening clears completion and independent verification and writes an immutable audit event."
        footer={
          <>
            <Button variant="secondary" onClick={() => setReopenModalOpen(false)}>
              Cancel
            </Button>
            <Button
              disabled={isSavingItem || reopenReason.trim().length < 3}
              onClick={handleConfirmReopen}
            >
              {isSavingItem ? 'Reopening…' : 'Confirm Reopen'}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Field label="Target Status">
            <Select
              value={reopenTargetStatus}
              onChange={(e) => setReopenTargetStatus(e.target.value as 'pending' | 'in_progress' | 'blocked')}
            >
              <option value="in_progress">In Progress</option>
              <option value="pending">Pending</option>
              <option value="blocked">Blocked</option>
            </Select>
          </Field>
          <Field label="Reason for Reopening (required)">
            <Textarea
              rows={3}
              value={reopenReason}
              onChange={(e) => setReopenReason(e.target.value)}
              placeholder="Explain what is incomplete or incorrect so the audit trail captures why this item was reopened."
            />
          </Field>
        </div>
      </Modal>

      {/* Independent Reviewer Verification Modal */}
      <Modal
        open={reviewModalOpen}
        onClose={() => setReviewModalOpen(false)}
        title="Independent Reviewer Verification"
        subtitle="Verify that objective completion criteria were satisfied, or return the item for rework."
        footer={
          <>
            <Button variant="secondary" onClick={() => setReviewModalOpen(false)}>
              Cancel
            </Button>
            <Button
              disabled={isReviewing || (!reviewApproved && reviewNotes.trim().length < 3)}
              onClick={handleSubmitReview}
            >
              {isReviewing ? 'Submitting…' : reviewApproved ? 'Verify Completion' : 'Return & Reopen'}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Field label="Review Decision">
            <Select
              value={reviewApproved ? 'approve' : 'reopen'}
              onChange={(e) => setReviewApproved(e.target.value === 'approve')}
            >
              <option value="approve">Verify completion criteria satisfied</option>
              <option value="reopen">Return for rework (reopen item)</option>
            </Select>
          </Field>
          <Field label={reviewApproved ? 'Review Notes (optional)' : 'Reopen Reason (required)'}>
            <Textarea
              rows={3}
              value={reviewNotes}
              onChange={(e) => setReviewNotes(e.target.value)}
              placeholder="Document verification checks performed or missing work required…"
            />
          </Field>
        </div>
      </Modal>

      {/* Add Custom Checklist Item Modal */}
      <Modal
        open={addModalOpen}
        onClose={() => setAddModalOpen(false)}
        title="Add Transition Checklist Item"
        subtitle="Add a project-specific operational, security, or knowledge-transfer item."
        footer={
          <>
            <Button variant="secondary" onClick={() => setAddModalOpen(false)}>
              Cancel
            </Button>
            <Button
              disabled={isCreating || newItemText.trim().length < 3 || !newChecklistId}
              onClick={handleCreateCustomItem}
            >
              {isCreating ? 'Adding…' : 'Add Checklist Item'}
            </Button>
          </>
        }
      >
        <div className="space-y-3.5">
          <Field label="Checklist Group">
            <Select value={newChecklistId} onChange={(e) => setNewChecklistId(e.target.value)}>
              {workspace.checklists.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.title || c.checklist_type.replace(/_/g, ' ')}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Item Title (required)">
            <Input
              value={newItemText}
              onChange={(e) => setNewItemText(e.target.value)}
              placeholder="e.g. Transfer primary PagerDuty on-call schedule"
            />
          </Field>
          <Field label="Description">
            <Textarea
              rows={2}
              value={newDescription}
              onChange={(e) => setNewDescription(e.target.value)}
              placeholder="Operational context for this transition task…"
            />
          </Field>
          <Field label="Completion Criteria">
            <Textarea
              rows={2}
              value={newCriteria}
              onChange={(e) => setNewCriteria(e.target.value)}
              placeholder="What proves this task is genuinely complete?"
            />
          </Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Category">
              <Select value={newCategory} onChange={(e) => setNewCategory(e.target.value)}>
                <option value="operations">Operations</option>
                <option value="architecture">Architecture</option>
                <option value="ownership">Ownership</option>
                <option value="security">Security</option>
                <option value="knowledge_transfer">Knowledge Transfer</option>
                <option value="governance">Governance</option>
                <option value="general">General</option>
              </Select>
            </Field>
            <Field label="Assigned Participant">
              <Select value={newAssignee} onChange={(e) => setNewAssignee(e.target.value)}>
                <option value="">Unassigned</option>
                {activeMembers.map((m) => (
                  <option key={m.user_id} value={m.user_id}>
                    {m.full_name || m.email}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Due Date">
              <Input type="date" value={newDueDate} onChange={(e) => setNewDueDate(e.target.value)} />
            </Field>
            <div className="flex items-end pb-2">
              <label className="flex cursor-pointer items-center gap-2 text-xs font-medium text-navy">
                <input
                  type="checkbox"
                  checked={newBlocking}
                  onChange={(e) => setNewBlocking(e.target.checked)}
                  className="size-4 rounded border-slate-300 text-brand"
                />
                Mandatory blocking approval gate
              </label>
            </div>
          </div>
        </div>
      </Modal>
    </div>
  )
}
