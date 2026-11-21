'use client'

import React, { useCallback, useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import {
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  BookOpen,
  CheckCircle2,
  Clock,
  ExternalLink,
  FileCheck2,
  GitBranch,
  HelpCircle,
  History,
  Loader2,
  Lock,
  MessageSquare,
  RefreshCw,
  RotateCcw,
  Send,
  ShieldAlert,
  ShieldCheck,
  ShieldX,
  UserCheck,
  UserCog,
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
import { CardSkeleton } from '../loading'
import { getCachedGraph, setCachedGraph } from '../../lib/graphCache'
import { api } from '../../lib/api'
import type {
  HandoverDeliveryRecord,
  HandoverSignoffWorkspaceResponse,
  SignoffPhaseDetail,
} from '../../lib/types'

export interface SignoffApprovalPanelProps {
  caseId: string
  projectId: string
  selectedVersionId?: string | null
  currentUserId?: string | null
  recipientFocused?: boolean
  onLifecycleChanged?: () => void
  onNavigateTab?: (tab: string) => void
}

const CANONICAL_SECTION_OPTIONS: Array<{ value: string; label: string }> = [
  { value: 'project_overview_context', label: '1. Project Overview & Context' },
  { value: 'decisions_rationale', label: '2. Decisions & Rationale' },
  { value: 'technical_architecture', label: '3. Technical Architecture' },
  { value: 'work_progress', label: '4. Work Progress & Tasks' },
  { value: 'responsibilities_ownership', label: '5. Responsibilities & Ownership' },
  { value: 'dependencies_relationships', label: '6. Dependencies & Relationships' },
  { value: 'bugs_blockers_risks', label: '7. Bugs, Blockers & Risks' },
  { value: 'operational_historical', label: '8. Operational & Historical' },
]

function formatLabel(raw?: string | null): string {
  if (!raw) return '—'
  return raw
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
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

function phaseBadge(status: string): {
  label: string
  tone: 'green' | 'blue' | 'amber' | 'red' | 'gray'
} {
  switch (status) {
    case 'completed':
      return { label: 'Completed', tone: 'green' }
    case 'in_progress':
      return { label: 'Action Required', tone: 'blue' }
    case 'rejected':
      return { label: 'Rejected', tone: 'red' }
    case 'returned_for_revision':
      return { label: 'Changes Requested', tone: 'amber' }
    case 'blocked':
      return { label: 'Blocked by Gates', tone: 'red' }
    case 'superseded':
      return { label: 'Superseded', tone: 'gray' }
    case 'pending':
    default:
      return { label: 'Pending', tone: 'gray' }
  }
}

export function SignoffApprovalPanel({
  caseId,
  projectId,
  selectedVersionId,
  currentUserId,
  recipientFocused = false,
  onLifecycleChanged,
  onNavigateTab,
}: SignoffApprovalPanelProps) {
  const router = useRouter()
  const [workspace, setWorkspace] = useState<HandoverSignoffWorkspaceResponse | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [actionSuccess, setActionSuccess] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  // Decision modal (Phase 1 or Phase 2 approve/reject/return)
  const [decisionModal, setDecisionModal] = useState<null | {
    signoffType: string
    decision: 'approved' | 'rejected' | 'returned_for_revision'
    title: string
    subtitle: string
  }>(null)
  const [decisionComments, setDecisionComments] = useState('')
  const [decisionConditions, setDecisionConditions] = useState('')
  const [affectedSections, setAffectedSections] = useState<string[]>([])

  // Assign reviewer modal
  const [assignModalOpen, setAssignModalOpen] = useState(false)
  const [selectedReviewerId, setSelectedReviewerId] = useState('')
  const [assignReason, setAssignReason] = useState('')

  // Reopen phase modal
  const [reopenModal, setReopenModal] = useState<null | { signoffType: string; phaseName: string }>(null)
  const [reopenReason, setReopenReason] = useState('')

  // Publish modal
  const [publishModalOpen, setPublishModalOpen] = useState(false)
  const [publishRecipientIds, setPublishRecipientIds] = useState<string[]>([])
  const [publishMessage, setPublishMessage] = useState('')
  const [publishExpiryDays, setPublishExpiryDays] = useState('')

  // Recipient acknowledgement modal
  const [ackDelivery, setAckDelivery] = useState<HandoverDeliveryRecord | null>(null)
  const [ackNotes, setAckNotes] = useState('')
  const [ackConfirmDomains, setAckConfirmDomains] = useState(true)
  const [ackConfirmResp, setAckConfirmResp] = useState(true)
  const [ackConfirmRisks, setAckConfirmRisks] = useState(true)

  // Clarification modal on published delivery
  const [clarifyTarget, setClarifyTarget] = useState<null | {
    delivery: HandoverDeliveryRecord
    mode: 'request' | 'response'
  }>(null)
  const [clarifyNotes, setClarifyNotes] = useState('')

  const loadWorkspace = useCallback(async () => {
    if (!projectId || !caseId) return
    const cacheKey = `handover_signoff_ws:${projectId}:${caseId}:${selectedVersionId || 'cur'}`
    const cached = getCachedGraph<HandoverSignoffWorkspaceResponse>(cacheKey)
    if (cached) {
      setWorkspace(cached)
      if (cached.assigned_reviewer_id) setSelectedReviewerId(cached.assigned_reviewer_id)
      if (cached.successor_id) setPublishRecipientIds([cached.successor_id])
      setIsLoading(false)
    } else {
      setIsLoading(true)
    }
    setError(null)
    try {
      const data = await api.handover.getSignoffWorkspace(projectId, caseId, selectedVersionId)
      setWorkspace(data)
      setCachedGraph(cacheKey, data)
      if (data.assigned_reviewer_id) {
        setSelectedReviewerId(data.assigned_reviewer_id)
      }
      if (data.successor_id) {
        setPublishRecipientIds([data.successor_id])
      }
    } catch (err: unknown) {
      if (!cached) {
        setError(err instanceof Error ? err.message : 'Failed to load signoff and publication workspace.')
      }
    } finally {
      setIsLoading(false)
    }
  }, [projectId, caseId, selectedVersionId])

  useEffect(() => {
    void loadWorkspace()
  }, [loadWorkspace])

  const navTab = (tab: string) => {
    if (onNavigateTab) {
      onNavigateTab(tab)
    } else {
      router.push(tab === 'overview' ? `/handovers/${caseId}` : `/handovers/${caseId}?tab=${tab}`)
    }
  }

  const handleSubmitDecision = async () => {
    if (!workspace || !workspace.selected_version_id || !decisionModal) return
    if (
      (decisionModal.decision === 'rejected' || decisionModal.decision === 'returned_for_revision') &&
      decisionComments.trim().length < 5
    ) {
      setActionError('A documented reason (at least 5 characters) is required.')
      return
    }
    setIsSubmitting(true)
    setActionError(null)
    setActionSuccess(null)
    try {
      await api.handover.submitSignoff(projectId, caseId, {
        version_id: workspace.selected_version_id,
        signoff_type: decisionModal.signoffType,
        decision: decisionModal.decision,
        comments: decisionComments.trim() || undefined,
        conditions: decisionConditions.trim() || undefined,
        affected_sections: affectedSections,
        expected_content_hash: workspace.selected_content_hash,
        expected_case_version: workspace.case_version,
      })
      setDecisionModal(null)
      setDecisionComments('')
      setDecisionConditions('')
      setAffectedSections([])
      await loadWorkspace()
      onLifecycleChanged?.()
      setActionSuccess(`Signoff decision (${formatLabel(decisionModal.decision)}) persisted with SHA-256 package binding.`)
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : 'Failed to persist signoff decision.')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleAssignReviewer = async () => {
    if (!workspace || !selectedReviewerId) return
    setIsSubmitting(true)
    setActionError(null)
    setActionSuccess(null)
    try {
      const updated = await api.handover.assignReviewer(projectId, caseId, {
        reviewer_user_id: selectedReviewerId,
        reason: assignReason.trim() || undefined,
        expected_case_version: workspace.case_version,
      })
      setWorkspace(updated)
      setAssignModalOpen(false)
      setAssignReason('')
      onLifecycleChanged?.()
      setActionSuccess('Independent reviewer assignment persisted and audited.')
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : 'Failed to assign reviewer.')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleReopenPhase = async () => {
    if (!workspace || !reopenModal || reopenReason.trim().length < 5) return
    setIsSubmitting(true)
    setActionError(null)
    setActionSuccess(null)
    try {
      const updated = await api.handover.reopenSignoffPhase(projectId, caseId, {
        signoff_type: reopenModal.signoffType,
        reason: reopenReason.trim(),
        expected_case_version: workspace.case_version,
      })
      setWorkspace(updated)
      setReopenModal(null)
      setReopenReason('')
      onLifecycleChanged?.()
      setActionSuccess('Signoff phase reopened. Previous decision preserved immutably as superseded.')
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : 'Failed to reopen signoff phase.')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handlePublish = async () => {
    if (!workspace || !workspace.selected_version_id || publishRecipientIds.length === 0) return
    setIsSubmitting(true)
    setActionError(null)
    setActionSuccess(null)
    try {
      await api.handover.deliverPackage(projectId, caseId, {
        version_id: workspace.selected_version_id,
        deliver_to_user_ids: publishRecipientIds,
        delivery_method: 'internal_download',
        message: publishMessage.trim() || undefined,
        expires_in_days: publishExpiryDays ? Number(publishExpiryDays) : undefined,
        expected_content_hash: workspace.selected_content_hash,
        expected_case_version: workspace.case_version,
      })
      setPublishModalOpen(false)
      setPublishMessage('')
      setPublishExpiryDays('')
      await loadWorkspace()
      onLifecycleChanged?.()
      setActionSuccess('Approved handover package published and delivered to designated recipients.')
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : 'Publication failed.')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleAcknowledgeDelivery = async () => {
    if (!ackDelivery) return
    setIsSubmitting(true)
    setActionError(null)
    setActionSuccess(null)
    try {
      await api.handover.acknowledgeDelivery(projectId, ackDelivery.id, {
        acknowledgement_notes: ackNotes.trim() || undefined,
        confirmations: {
          reviewed_canonical_domains: ackConfirmDomains,
          reviewed_responsibilities: ackConfirmResp,
          understood_open_risks: ackConfirmRisks,
        },
        expected_content_hash: ackDelivery.artifact_checksum,
      })
      setAckDelivery(null)
      setAckNotes('')
      await loadWorkspace()
      onLifecycleChanged?.()
      setActionSuccess('Complete-package recipient acknowledgement recorded with cryptographic hash.')
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : 'Acknowledgement failed.')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleClarifyDelivery = async () => {
    if (!clarifyTarget || clarifyNotes.trim().length < 3) return
    setIsSubmitting(true)
    setActionError(null)
    setActionSuccess(null)
    try {
      await api.handover.clarifyDelivery(projectId, clarifyTarget.delivery.id, {
        mode: clarifyTarget.mode,
        notes: clarifyNotes.trim(),
      })
      setClarifyTarget(null)
      setClarifyNotes('')
      await loadWorkspace()
      setActionSuccess(
        clarifyTarget.mode === 'request'
          ? 'Recipient clarification request persisted on the published delivery.'
          : 'Clarification response posted.',
      )
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : 'Clarification action failed.')
    } finally {
      setIsSubmitting(false)
    }
  }

  if (isLoading && !workspace) {
    return (
      <div className="p-4 space-y-4" role="status" aria-live="polite">
        <CardSkeleton count={3} />
      </div>
    )
  }

  if (error && !workspace) {
    return (
      <Card className="p-6">
        <Callout tone="red" icon={AlertCircle} title="Unable to load signoff workspace">
          <p className="mb-3">{error}</p>
          <Button variant="secondary" size="sm" icon={RefreshCw} onClick={loadWorkspace}>
            Retry
          </Button>
        </Callout>
      </Card>
    )
  }

  if (!workspace) return null

  const elig = workspace.approval_eligibility
  const pub = workspace.publication
  const lifecycle = workspace.lifecycle

  return (
    <div className="space-y-6" data-testid="signoff-approval-panel">
      {actionSuccess && (
        <Callout tone="green" icon={CheckCircle2} title="Governance action persisted">
          {actionSuccess}
        </Callout>
      )}
      {actionError && (
        <Callout tone="red" icon={AlertCircle} title="Governance action blocked or failed">
          {actionError}
        </Callout>
      )}
      {workspace.package_changed_since_approval && workspace.package_change_notice && (
        <Callout tone="amber" icon={AlertTriangle} title="Package Version Changed Since Prior Approval">
          {workspace.package_change_notice}
        </Callout>
      )}

      {/* A. Signoff Overview & Canonical Lifecycle Governance */}
      <Card className="p-5 sm:p-6">
        <div className="flex flex-col gap-4 border-b border-line pb-5 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <ShieldCheck className="size-5 text-brand" />
              <h2 className="text-lg font-semibold text-navy">
                {recipientFocused
                  ? 'Published Handover & Recipient Acknowledgement'
                  : 'Signoff, Managerial Approval & Controlled Publication'}
              </h2>
              <Badge tone={workspace.case_status === 'approved' || workspace.case_status === 'acknowledged' ? 'green' : workspace.case_status === 'rejected' ? 'red' : 'blue'}>
                {formatLabel(workspace.case_status)}
              </Badge>
              {workspace.selected_version_number != null && (
                <Badge tone="gray">Package v{workspace.selected_version_number}</Badge>
              )}
            </div>
            <p className="mt-1 text-[13px] text-muted">
              Authoritative three-phase governance bound to immutable package snapshots. All transitions, separation-of-duties checks, and 4-gate eligibility rules are enforced on the backend.
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-muted">
              <span>
                Previous state:{' '}
                <strong className="text-navy">{formatLabel(lifecycle.previous_status)}</strong>
              </span>
              <span>
                Responsible next:{' '}
                <strong className="text-navy">
                  {lifecycle.responsible_role_label}
                  {lifecycle.responsible_user_name ? ` (${lifecycle.responsible_user_name})` : ''}
                </strong>
              </span>
              {workspace.selected_content_hash && (
                <span
                  className="inline-flex items-center gap-1 font-mono text-[11px] text-slate-600"
                  title={`Immutable SHA-256: ${workspace.selected_content_hash}`}
                >
                  <Lock className="size-3 text-ok" />
                  SHA-256: {workspace.selected_content_hash.slice(0, 14)}…
                </span>
              )}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {workspace.readiness_score != null && (
              <Button variant="secondary" size="sm" onClick={() => navTab('readiness')}>
                Readiness {workspace.readiness_score}/100 ({formatLabel(workspace.readiness_level)})
              </Button>
            )}
            <Button variant="secondary" size="sm" icon={RefreshCw} onClick={loadWorkspace}>
              Refresh
            </Button>
          </div>
        </div>

        {/* Next Permitted Transitions & Blocked Transition Reasons */}
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <div className="rounded-xl border border-line bg-slate-50/60 p-4">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
              Authoritative Lifecycle & Participants
            </p>
            <div className="mt-2.5 grid gap-2 text-xs sm:grid-cols-3">
              <div className="rounded-lg border border-line bg-white p-2.5">
                <p className="text-[10.5px] text-muted">Outgoing Owner</p>
                <p className="mt-0.5 font-semibold text-navy">
                  {workspace.departing_member_name || 'Unassigned'}
                </p>
              </div>
              <div className="rounded-lg border border-line bg-white p-2.5">
                <div className="flex items-center justify-between gap-1">
                  <p className="text-[10.5px] text-muted">Independent Reviewer</p>
                  {!pub.is_published && (
                    <button
                      type="button"
                      onClick={() => setAssignModalOpen(true)}
                      className="text-[10.5px] font-medium text-brand hover:underline"
                    >
                      {workspace.assigned_reviewer_id ? 'Reassign' : 'Assign'}
                    </button>
                  )}
                </div>
                <p className="mt-0.5 font-semibold text-navy">
                  {workspace.assigned_reviewer_name || 'Not assigned yet'}
                </p>
              </div>
              <div className="rounded-lg border border-line bg-white p-2.5">
                <p className="text-[10.5px] text-muted">Designated Successor</p>
                <p className="mt-0.5 font-semibold text-navy">
                  {workspace.successor_name || 'Not assigned yet'}
                </p>
              </div>
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-1.5 text-[11px]">
              <span className="text-muted">Permitted next states:</span>
              {lifecycle.next_permitted_transitions.map((st) => (
                <Badge key={st} tone="gray">
                  {formatLabel(st)}
                </Badge>
              ))}
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-line/70 pt-3">
              {(() => {
                const p1 = workspace.phases.find((ph) => ph.phase_number === 1)
                const p2 = workspace.phases.find((ph) => ph.phase_number === 2)
                if (p1?.viewer_can_act && p1.status !== 'completed') {
                  return (
                    <Button
                      size="sm"
                      icon={Send}
                      onClick={() => {
                        setDecisionComments('')
                        setDecisionConditions('')
                        setAffectedSections([])
                        setDecisionModal({
                          signoffType: 'departing_signoff',
                          decision: 'approved',
                          title: 'Submit Phase 1 Departing Sign-Off',
                          subtitle: `Confirm package v${workspace.selected_version_number} is complete and ready for independent review.`,
                        })
                      }}
                    >
                      Next Step: Submit Phase 1 Sign-Off
                    </Button>
                  )
                }
                if (p2?.viewer_can_act && p2.status !== 'completed') {
                  return (
                    <Button
                      size="sm"
                      variant="success"
                      icon={ShieldCheck}
                      disabled={Boolean(elig && !elig.is_eligible_for_approval)}
                      onClick={() => {
                        setDecisionComments('')
                        setDecisionConditions('')
                        setAffectedSections([])
                        setDecisionModal({
                          signoffType: 'reviewer_approval',
                          decision: 'approved',
                          title: 'Approve Handover Package',
                          subtitle: `Grant Phase 2 approval for immutable package v${workspace.selected_version_number}.`,
                        })
                      }}
                    >
                      Next Step: Approve Handover Package
                    </Button>
                  )
                }
                if (p2 && p2.status !== 'completed' && !pub.is_published) {
                  return (
                    <Button
                      size="sm"
                      variant="secondary"
                      icon={UserCheck}
                      onClick={() => setAssignModalOpen(true)}
                    >
                      Next Step: Assign Independent Reviewer
                    </Button>
                  )
                }
                if (pub.is_eligible_to_publish && !pub.is_published) {
                  return (
                    <Button
                      size="sm"
                      icon={Send}
                      onClick={() => setPublishModalOpen(true)}
                    >
                      Next Step: Publish Approved Package
                    </Button>
                  )
                }
                if (pub.is_published) {
                  return (
                    <>
                      <Button
                        size="sm"
                        icon={BookOpen}
                        onClick={() => navTab('recipient')}
                      >
                        Next Step: Open Recipient View
                      </Button>
                      <Button
                        size="sm"
                        variant="secondary"
                        icon={FileCheck2}
                        onClick={() => navTab('report')}
                      >
                        Export Final Report
                      </Button>
                    </>
                  )
                }
                return null
              })()}
              {(() => {
                const p1 = workspace.phases.find((ph) => ph.phase_number === 1)
                const p2 = workspace.phases.find((ph) => ph.phase_number === 2)
                const reopenTarget =
                  !pub.is_published && p2?.latest_decision && !p2.latest_decision.is_superseded
                    ? p2
                    : !pub.is_published && p1?.latest_decision && !p1.latest_decision.is_superseded
                    ? p1
                    : null
                return (
                  <>
                    {reopenTarget && (
                      <Button
                        size="sm"
                        variant="secondary"
                        icon={RotateCcw}
                        onClick={() => {
                          setReopenReason('')
                          setReopenModal({
                            signoffType: reopenTarget.signoff_type,
                            phaseName: reopenTarget.phase_name,
                          })
                        }}
                      >
                        Go Back: Reopen Phase {reopenTarget.phase_number}
                      </Button>
                    )}
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => navTab('responsibilities')}
                    >
                      Back to Ownership
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => navTab('readiness')}
                    >
                      Back to Readiness
                    </Button>
                  </>
                )
              })()}
            </div>
          </div>

          <div className="rounded-xl border border-line bg-slate-50/60 p-4">
            <div className="flex items-center justify-between gap-2">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                Authoritative Approval Eligibility (4-Gate Engine)
              </p>
              {elig ? (
                <Badge tone={elig.is_eligible_for_approval ? 'green' : 'red'}>
                  {elig.is_eligible_for_approval ? 'Eligible for Approval' : 'Blocked'}
                </Badge>
              ) : (
                <Badge tone="amber">Not Assessed</Badge>
              )}
            </div>

            {elig ? (
              <>
                <div className="mt-2.5 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
                  {[
                    ['Score ≥ 70', elig.score_gate_passed],
                    ['Verification', elig.verification_gate_passed],
                    ['Conflicts', elig.conflict_gate_passed],
                    ['Checklists', elig.checklist_gate_passed],
                  ].map(([lbl, ok]) => (
                    <div
                      key={lbl as string}
                      className={cn(
                        'flex items-center justify-between rounded-lg border px-2.5 py-1.5',
                        ok ? 'border-emerald-200 bg-emerald-50/60' : 'border-red-200 bg-red-50/50',
                      )}
                    >
                      <span className="font-medium text-navy">{lbl as string}</span>
                      {ok ? (
                        <CheckCircle2 className="size-3.5 text-emerald-600" />
                      ) : (
                        <XCircle className="size-3.5 text-red-600" />
                      )}
                    </div>
                  ))}
                </div>
                {elig.blocking_requirements.length > 0 && (
                  <ul className="mt-2.5 space-y-1 text-xs text-red-800">
                    {elig.blocking_requirements.map((req, idx) => (
                      <li key={idx} className="flex items-start gap-1.5">
                        <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-red-600" />
                        <span>{req}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </>
            ) : (
              <p className="mt-2 text-xs text-amber-800">
                No readiness assessment exists for this package version yet. Run Readiness Assessment before Phase 2 approval.
              </p>
            )}

            <div className="mt-3 flex flex-wrap gap-2">
              <Button variant="ghost" size="sm" onClick={() => navTab('readiness')}>
                Readiness
              </Button>
              <Button variant="ghost" size="sm" onClick={() => navTab('checklists')}>
                Checklists
              </Button>
              <Button variant="ghost" size="sm" onClick={() => navTab('responsibilities')}>
                Ownership
              </Button>
              <Button variant="ghost" size="sm" onClick={() => router.push('/conflicts')}>
                Conflicts
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => router.push(`/verification?project=${projectId}`)}
              >
                Verification
              </Button>
            </div>
          </div>
        </div>
      </Card>

      {/* B & C. Three-Phase Signoff Workflow & Decision Interface */}
      {!recipientFocused && (
        <div className="grid gap-4 lg:grid-cols-3">
          {workspace.phases.map((phase: SignoffPhaseDetail) => {
            const pb = phaseBadge(phase.status)
            const dec = phase.latest_decision
            const canReopen =
              !pub.is_published &&
              phase.phase_number <= 2 &&
              Boolean(dec && !dec.is_superseded)

            return (
              <Card key={phase.signoff_type} className="flex flex-col justify-between p-5">
                <div>
                  <div className="flex items-start justify-between gap-2">
                    <span className="text-[11px] font-semibold uppercase tracking-wide text-brand">
                      Phase {phase.phase_number}
                    </span>
                    <Badge tone={pb.tone}>{pb.label}</Badge>
                  </div>
                  <h3 className="mt-1 text-[15px] font-semibold text-navy">{phase.phase_name}</h3>
                  <p className="mt-1 text-xs leading-relaxed text-muted">{phase.purpose}</p>

                  <dl className="mt-3.5 space-y-1.5 rounded-lg border border-line bg-slate-50/60 p-3 text-xs">
                    <div className="flex justify-between gap-2">
                      <dt className="text-muted">Assigned</dt>
                      <dd className="font-medium text-navy">
                        {phase.assigned_user_name || 'Unassigned'}
                      </dd>
                    </div>
                    <div className="flex justify-between gap-2">
                      <dt className="text-muted">Authority</dt>
                      <dd className="font-mono text-[11px] text-slate-600">
                        {phase.required_permission}
                      </dd>
                    </div>
                  </dl>

                  {phase.pending_requirements.length > 0 && (
                    <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50/60 p-3">
                      <p className="text-[11px] font-semibold uppercase tracking-wide text-amber-800">
                        Pending Requirements ({phase.pending_requirements.length})
                      </p>
                      <ul className="mt-1.5 space-y-1 text-xs text-amber-900">
                        {phase.pending_requirements.slice(0, 4).map((r, i) => (
                          <li key={i}>• {r}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {dec && (
                    <div className="mt-3 rounded-lg border border-line bg-white p-3 text-xs">
                      <div className="flex items-center justify-between gap-2">
                        <Badge
                          tone={
                            dec.decision === 'approved'
                              ? 'green'
                              : dec.decision === 'rejected'
                              ? 'red'
                              : 'amber'
                          }
                        >
                          {formatLabel(dec.decision)}
                        </Badge>
                        <span className="text-[11px] text-muted">{formatDateTime(dec.signed_at)}</span>
                      </div>
                      <p className="mt-1.5 font-medium text-navy">
                        Signed by {dec.signer_name || 'Participant'}
                      </p>
                      {dec.comments && <p className="mt-1 text-muted">“{dec.comments}”</p>}
                      {dec.affected_sections_json.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-1">
                          {dec.affected_sections_json.map((sec) => (
                            <Badge key={sec} tone="amber">
                              {formatLabel(sec)}
                            </Badge>
                          ))}
                        </div>
                      )}
                      {dec.signature_hash && (
                        <p className="mt-1.5 font-mono text-[10.5px] text-slate-500">
                          Sig: {dec.signature_hash.slice(0, 14)}…
                        </p>
                      )}
                    </div>
                  )}
                </div>

                {/* Phase Action Footer */}
                <div className="mt-4 border-t border-line pt-3.5">
                  {phase.viewer_ineligibility_reason && (
                    <p className="mb-2.5 flex items-start gap-1.5 text-[11.5px] text-amber-800">
                      <Lock className="mt-0.5 size-3.5 shrink-0 text-amber-600" />
                      <span>{phase.viewer_ineligibility_reason}</span>
                    </p>
                  )}

                  <div className="flex flex-wrap gap-2">
                    {phase.phase_number === 1 && phase.viewer_can_act && (
                      <Button
                        size="sm"
                        icon={Send}
                        onClick={() => {
                          setDecisionComments('')
                          setDecisionConditions('')
                          setAffectedSections([])
                          setDecisionModal({
                            signoffType: 'departing_signoff',
                            decision: 'approved',
                            title: 'Submit Phase 1 Departing Sign-Off',
                            subtitle: `Confirm package v${workspace.selected_version_number} is complete and ready for independent review.`,
                          })
                        }}
                      >
                        Submit Phase 1 Sign-Off
                      </Button>
                    )}

                    {phase.phase_number === 2 && phase.viewer_can_act && (
                      <>
                        <Button
                          size="sm"
                          variant="success"
                          icon={ShieldCheck}
                          disabled={Boolean(elig && !elig.is_eligible_for_approval)}
                          title={
                            elig && !elig.is_eligible_for_approval
                              ? 'Resolve all readiness blockers before approving'
                              : 'Grant independent managerial approval'
                          }
                          onClick={() => {
                            setDecisionComments('')
                            setDecisionConditions('')
                            setAffectedSections([])
                            setDecisionModal({
                              signoffType: 'reviewer_approval',
                              decision: 'approved',
                              title: 'Approve Handover Package',
                              subtitle: `Grant Phase 2 approval for immutable package v${workspace.selected_version_number}.`,
                            })
                          }}
                        >
                          Approve
                        </Button>
                        <Button
                          size="sm"
                          variant="secondary"
                          icon={RotateCcw}
                          onClick={() => {
                            setDecisionComments('')
                            setAffectedSections([])
                            setDecisionModal({
                              signoffType: 'reviewer_approval',
                              decision: 'returned_for_revision',
                              title: 'Request Changes',
                              subtitle: 'Return this package with specific corrections and affected sections.',
                            })
                          }}
                        >
                          Request Changes
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          icon={ShieldX}
                          onClick={() => {
                            setDecisionComments('')
                            setAffectedSections([])
                            setDecisionModal({
                              signoffType: 'reviewer_approval',
                              decision: 'rejected',
                              title: 'Reject Handover Package',
                              subtitle: 'Reject this handover with a mandatory audit rationale.',
                            })
                          }}
                        >
                          Reject
                        </Button>
                      </>
                    )}

                    {canReopen && (
                      <Button
                        size="sm"
                        variant="ghost"
                        icon={RotateCcw}
                        onClick={() => {
                          setReopenReason('')
                          setReopenModal({
                            signoffType: phase.signoff_type,
                            phaseName: phase.phase_name,
                          })
                        }}
                      >
                        Reopen Phase
                      </Button>
                    )}
                  </div>
                </div>
              </Card>
            )
          })}
        </div>
      )}

      {/* D. Controlled Publication Workspace */}
      <Card className="p-5 sm:p-6">
        <div className="flex flex-col gap-3 border-b border-line pb-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <FileCheck2 className="size-4 text-brand" />
              <h3 className="text-[15px] font-semibold text-navy">
                Controlled Publication & Delivery
              </h3>
              {pub.is_published ? (
                <Badge tone="green">Published (v{pub.published_version_number})</Badge>
              ) : pub.is_eligible_to_publish ? (
                <Badge tone="blue">Ready to Publish</Badge>
              ) : (
                <Badge tone="amber">Not Eligible to Publish</Badge>
              )}
            </div>
            <p className="mt-0.5 text-xs text-muted">
              Publication requires completed Phase 1 + Phase 2 approvals on the exact SHA-256 package version and active eligible project recipients.
            </p>
          </div>
          {!pub.is_published && (
            <Button
              size="sm"
              icon={Send}
              disabled={!pub.is_eligible_to_publish}
              onClick={() => setPublishModalOpen(true)}
            >
              Publish Approved Package
            </Button>
          )}
        </div>

        {pub.is_published ? (
          <div className="mt-4 grid gap-3 rounded-xl border border-emerald-200 bg-emerald-50/40 p-4 text-xs sm:grid-cols-4">
            <div>
              <p className="text-muted">Published Version</p>
              <p className="mt-0.5 font-semibold text-navy">v{pub.published_version_number}</p>
            </div>
            <div>
              <p className="text-muted">Published By</p>
              <p className="mt-0.5 font-semibold text-navy">{pub.published_by_name || 'Manager'}</p>
            </div>
            <div>
              <p className="text-muted">Published At</p>
              <p className="mt-0.5 font-semibold text-navy">{formatDateTime(pub.published_at)}</p>
            </div>
            <div>
              <p className="text-muted">Integrity SHA-256</p>
              <p className="mt-0.5 font-mono text-[11px] text-navy">
                {pub.published_content_hash ? `${pub.published_content_hash.slice(0, 16)}…` : '—'}
              </p>
            </div>
          </div>
        ) : (
          <div className="mt-4">
            {pub.blocking_reasons.length > 0 && (
              <ul className="space-y-1.5 text-xs text-amber-900">
                {pub.blocking_reasons.map((r, i) => (
                  <li key={i} className="flex items-start gap-1.5">
                    <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-amber-600" />
                    <span>{r}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </Card>

      {/* E. Recipient Acknowledgement & Clarification Workspace */}
      <Card className="p-5 sm:p-6">
        <div className="flex flex-col gap-2 border-b border-line pb-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <UserCheck className="size-4 text-brand" />
              <h3 className="text-[15px] font-semibold text-navy">
                Complete-Package Recipient Acknowledgement ({pub.deliveries.length})
              </h3>
            </div>
            <p className="mt-0.5 text-xs text-muted">
              Distinct from Stage 5 responsibility acknowledgement and managerial approval. Recipients review all eight canonical domains, raise clarifications if needed, and confirm receipt of the published handover package.
            </p>
          </div>
          <Button variant="secondary" size="sm" icon={BookOpen} onClick={() => navTab('overview')}>
            Inspect 8 Domains
          </Button>
        </div>

        {pub.deliveries.length === 0 ? (
          <div className="py-6 text-center text-xs text-muted">
            No published deliveries exist yet. Recipient acknowledgement becomes available once an approved package is published.
          </div>
        ) : (
          <div className="mt-4 space-y-4">
            {pub.deliveries.map((del) => {
              const isRecipient = currentUserId === del.delivered_to_user_id
              const canRespond =
                currentUserId === workspace.departing_member_id ||
                currentUserId === del.delivered_by_user_id

              return (
                <div key={del.id} className="rounded-xl border border-line bg-slate-50/50 p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-semibold text-navy">
                          Recipient: {del.delivered_to_name || 'Project Member'}
                        </span>
                        <Badge tone={del.acknowledged ? 'green' : 'amber'}>
                          {del.acknowledged ? 'Acknowledged' : 'Awaiting Acknowledgement'}
                        </Badge>
                      </div>
                      <p className="mt-1 text-xs text-muted">
                        Delivered {formatDateTime(del.delivered_at)} by {del.delivered_by_name || 'Manager'}
                        {del.artifact_checksum ? ` · SHA-256: ${del.artifact_checksum.slice(0, 12)}…` : ''}
                      </p>
                      {del.message && (
                        <p className="mt-1.5 text-xs text-slate-700">Publication note: “{del.message}”</p>
                      )}
                    </div>

                    <div className="flex flex-wrap gap-2">
                      {isRecipient && !del.acknowledged && (
                        <Button
                          size="sm"
                          variant="success"
                          icon={CheckCircle2}
                          onClick={() => {
                            setAckNotes('')
                            setAckDelivery(del)
                          }}
                        >
                          Acknowledge Receipt
                        </Button>
                      )}
                      {isRecipient && (
                        <Button
                          size="sm"
                          variant="secondary"
                          icon={HelpCircle}
                          onClick={() => {
                            setClarifyNotes('')
                            setClarifyTarget({ delivery: del, mode: 'request' })
                          }}
                        >
                          Request Clarification
                        </Button>
                      )}
                      {canRespond && del.clarifications.length > 0 && (
                        <Button
                          size="sm"
                          variant="secondary"
                          icon={MessageSquare}
                          onClick={() => {
                            setClarifyNotes('')
                            setClarifyTarget({ delivery: del, mode: 'response' })
                          }}
                        >
                          Respond to Clarification
                        </Button>
                      )}
                    </div>
                  </div>

                  {del.acknowledgement && (
                    <div className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50/60 p-3 text-xs text-emerald-900">
                      <p className="font-semibold">
                        Acknowledged by {del.acknowledgement.acknowledged_by_name} on{' '}
                        {formatDateTime(del.acknowledgement.acknowledged_at)}
                      </p>
                      {del.acknowledgement.acknowledgement_notes && (
                        <p className="mt-1">“{del.acknowledgement.acknowledgement_notes}”</p>
                      )}
                      {del.acknowledgement.acknowledgement_hash && (
                        <p className="mt-1 font-mono text-[10.5px] text-emerald-800">
                          Receipt Hash: {del.acknowledgement.acknowledgement_hash.slice(0, 18)}…
                        </p>
                      )}
                    </div>
                  )}

                  {del.clarifications.length > 0 && (
                    <div className="mt-3 space-y-2 border-t border-line pt-3">
                      <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                        Clarification Thread ({del.clarifications.length})
                      </p>
                      {del.clarifications.map((c) => (
                        <div
                          key={c.id}
                          className={cn(
                            'rounded-lg border p-2.5 text-xs',
                            c.mode === 'request'
                              ? 'border-amber-200 bg-amber-50/60 text-amber-950'
                              : 'border-blue-200 bg-blue-50/60 text-blue-950',
                          )}
                        >
                          <div className="flex justify-between gap-2 text-[11px]">
                            <strong>
                              {c.author_name || 'Participant'} (
                              {c.mode === 'request' ? 'Clarification Request' : 'Response'})
                            </strong>
                            <span>{formatDateTime(c.created_at)}</span>
                          </div>
                          <p className="mt-1">{c.notes}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </Card>

      {/* Signoff Decision History + Lifecycle Audit Trail */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="overflow-hidden">
          <CardHeader
            title={`Immutable Signoff Decision History (${workspace.signoff_history.length})`}
            subtitle="All historical approvals, rejections, change requests, and superseded decisions."
          />
          {workspace.signoff_history.length === 0 ? (
            <div className="p-5 text-center text-xs text-muted">
              No signoff decisions have been recorded yet.
            </div>
          ) : (
            <ul className="max-h-72 divide-y divide-line overflow-y-auto">
              {workspace.signoff_history.map((s) => (
                <li key={s.id} className="px-4 py-3 text-xs">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Badge
                        tone={
                          s.decision === 'approved'
                            ? 'green'
                            : s.decision === 'rejected'
                            ? 'red'
                            : 'amber'
                        }
                      >
                        {formatLabel(s.decision)}
                      </Badge>
                      <span className="font-semibold text-navy">{formatLabel(s.signoff_type)}</span>
                      {s.is_superseded && <Badge tone="gray">Superseded</Badge>}
                    </div>
                    <span className="text-[11px] text-muted">{formatDateTime(s.signed_at)}</span>
                  </div>
                  <p className="mt-1 text-muted">
                    By <strong className="text-navy">{s.signer_name || 'Participant'}</strong>
                    {s.package_content_hash ? ` · SHA-256 ${s.package_content_hash.slice(0, 10)}…` : ''}
                  </p>
                  {s.comments && <p className="mt-1 text-slate-700">“{s.comments}”</p>}
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card className="overflow-hidden">
          <CardHeader
            title={`Governance Audit & Lifecycle Activity (${workspace.activity_history.length})`}
            subtitle="Immutable PostgreSQL audit trail of assignments, signoffs, publications, and acknowledgements."
          />
          {workspace.activity_history.length === 0 ? (
            <div className="p-5 text-center text-xs text-muted">No governance audit events yet.</div>
          ) : (
            <ul className="max-h-72 divide-y divide-line overflow-y-auto">
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

      {/* Decision Confirmation Modal */}
      <Modal
        open={Boolean(decisionModal)}
        onClose={() => setDecisionModal(null)}
        title={decisionModal?.title || 'Confirm Signoff Decision'}
        subtitle={decisionModal?.subtitle}
        footer={
          <>
            <Button variant="secondary" onClick={() => setDecisionModal(null)}>
              Cancel
            </Button>
            <Button
              variant={decisionModal?.decision === 'approved' ? 'success' : 'primary'}
              disabled={isSubmitting}
              onClick={handleSubmitDecision}
            >
              {isSubmitting ? 'Persisting…' : 'Confirm & Record Decision'}
            </Button>
          </>
        }
      >
        <div className="space-y-3.5">
          {workspace.selected_content_hash && (
            <p className="rounded-lg border border-line bg-slate-50 px-3 py-2 font-mono text-[11px] text-slate-600">
              Package v{workspace.selected_version_number} · SHA-256:{' '}
              {workspace.selected_content_hash.slice(0, 24)}…
            </p>
          )}
          <Field
            label={
              decisionModal?.decision === 'approved'
                ? 'Review Comments (optional)'
                : 'Mandatory Reason / Required Corrections (min 5 chars)'
            }
          >
            <Textarea
              rows={3}
              value={decisionComments}
              onChange={(e) => setDecisionComments(e.target.value)}
              placeholder="Document review rationale, evidence checks, or required corrections…"
            />
          </Field>
          {decisionModal && decisionModal.decision !== 'approved' && (
            <div>
              <p className="mb-1.5 text-xs font-medium text-navy">Affected Package Sections</p>
              <div className="grid gap-1.5 sm:grid-cols-2">
                {CANONICAL_SECTION_OPTIONS.map((sec) => {
                  const checked = affectedSections.includes(sec.value)
                  return (
                    <label
                      key={sec.value}
                      className="flex cursor-pointer items-center gap-2 rounded-lg border border-line px-2.5 py-1.5 text-xs"
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() =>
                          setAffectedSections((prev) =>
                            checked ? prev.filter((x) => x !== sec.value) : [...prev, sec.value],
                          )
                        }
                        className="size-3.5 rounded border-slate-300 text-brand"
                      />
                      <span>{sec.label}</span>
                    </label>
                  )
                })}
              </div>
            </div>
          )}
        </div>
      </Modal>

      {/* Assign Independent Reviewer Modal */}
      <Modal
        open={assignModalOpen}
        onClose={() => setAssignModalOpen(false)}
        title="Assign Independent Reviewer"
        subtitle="Select an active project member other than the departing owner (separation of duties enforced)."
        footer={
          <>
            <Button variant="secondary" onClick={() => setAssignModalOpen(false)}>
              Cancel
            </Button>
            <Button
              disabled={isSubmitting || !selectedReviewerId}
              onClick={handleAssignReviewer}
            >
              {isSubmitting ? 'Assigning…' : 'Assign Reviewer'}
            </Button>
          </>
        }
      >
        <div className="space-y-3.5">
          {workspace.eligible_reviewers.length === 0 ? (
            <Callout tone="amber" icon={AlertTriangle} title="No eligible independent reviewer available">
              Add an additional active project member in Team Members so an independent reviewer (distinct from the departing member) can be assigned.
            </Callout>
          ) : (
            <>
              <Field label="Independent Reviewer">
                <Select
                  value={selectedReviewerId}
                  onChange={(e) => setSelectedReviewerId(e.target.value)}
                >
                  <option value="">Select eligible member…</option>
                  {workspace.eligible_reviewers.map((m) => (
                    <option key={m.user_id} value={m.user_id}>
                      {m.full_name} ({m.role_name.replace(/_/g, ' ')})
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Assignment Note (optional)">
                <Input
                  value={assignReason}
                  onChange={(e) => setAssignReason(e.target.value)}
                  placeholder="e.g. Technical architecture lead reviewer"
                />
              </Field>
            </>
          )}
        </div>
      </Modal>

      {/* Reopen Phase Modal */}
      <Modal
        open={Boolean(reopenModal)}
        onClose={() => setReopenModal(null)}
        title={`Reopen ${reopenModal?.phaseName || 'Signoff Phase'}`}
        subtitle="Supersedes the active approval immutably and requires fresh re-review before publication."
        footer={
          <>
            <Button variant="secondary" onClick={() => setReopenModal(null)}>
              Cancel
            </Button>
            <Button
              disabled={isSubmitting || reopenReason.trim().length < 5}
              onClick={handleReopenPhase}
            >
              {isSubmitting ? 'Reopening…' : 'Confirm Reopen'}
            </Button>
          </>
        }
      >
        <Field label="Mandatory Justification (min 5 chars)">
          <Textarea
            rows={3}
            value={reopenReason}
            onChange={(e) => setReopenReason(e.target.value)}
            placeholder="Explain why this signoff phase must be reopened…"
          />
        </Field>
      </Modal>

      {/* Controlled Publication Modal */}
      <Modal
        open={publishModalOpen}
        onClose={() => setPublishModalOpen(false)}
        title="Publish Approved Handover Package"
        subtitle={`Publish immutable v${workspace.selected_version_number} (SHA-256 ${workspace.selected_content_hash?.slice(0, 12)}…) to active project recipients.`}
        footer={
          <>
            <Button variant="secondary" onClick={() => setPublishModalOpen(false)}>
              Cancel
            </Button>
            <Button
              disabled={isSubmitting || publishRecipientIds.length === 0}
              onClick={handlePublish}
            >
              {isSubmitting ? 'Publishing…' : 'Confirm Publication'}
            </Button>
          </>
        }
      >
        <div className="space-y-3.5">
          <div>
            <p className="mb-1.5 text-xs font-medium text-navy">Eligible Active Recipients</p>
            <div className="space-y-1.5">
              {workspace.eligible_recipients.map((r) => {
                const checked = publishRecipientIds.includes(r.user_id)
                return (
                  <label
                    key={r.user_id}
                    className="flex cursor-pointer items-center justify-between rounded-lg border border-line px-3 py-2 text-xs"
                  >
                    <span className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() =>
                          setPublishRecipientIds((prev) =>
                            checked ? prev.filter((x) => x !== r.user_id) : [...prev, r.user_id],
                          )
                        }
                        className="size-4 rounded border-slate-300 text-brand"
                      />
                      <span className="font-medium text-navy">{r.full_name}</span>
                      <span className="text-muted">({r.role_name.replace(/_/g, ' ')})</span>
                    </span>
                    {r.is_case_successor && <Badge tone="blue">Designated Successor</Badge>}
                  </label>
                )
              })}
            </div>
          </div>
          <Field label="Publication Message (optional)">
            <Textarea
              rows={2}
              value={publishMessage}
              onChange={(e) => setPublishMessage(e.target.value)}
              placeholder="Include onboarding context or transition effective date…"
            />
          </Field>
          <Field label="Access Expiry (days, optional)">
            <Input
              type="number"
              min={1}
              max={365}
              value={publishExpiryDays}
              onChange={(e) => setPublishExpiryDays(e.target.value)}
              placeholder="Leave blank for persistent project access"
            />
          </Field>
        </div>
      </Modal>

      {/* Complete-Package Recipient Acknowledgement Modal */}
      <Modal
        open={Boolean(ackDelivery)}
        onClose={() => setAckDelivery(null)}
        title="Acknowledge Complete Published Handover"
        subtitle="Confirms receipt and review of the published handover package. Does not imply all operational risks or tasks are closed."
        footer={
          <>
            <Button variant="secondary" onClick={() => setAckDelivery(null)}>
              Cancel
            </Button>
            <Button variant="success" disabled={isSubmitting} onClick={handleAcknowledgeDelivery}>
              {isSubmitting ? 'Recording Receipt…' : 'Confirm Receipt Acknowledgement'}
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <label className="flex cursor-pointer items-center gap-2 text-xs text-navy">
            <input
              type="checkbox"
              checked={ackConfirmDomains}
              onChange={(e) => setAckConfirmDomains(e.target.checked)}
              className="size-4 rounded border-slate-300 text-brand"
            />
            I have reviewed the eight canonical handover domains and supporting evidence.
          </label>
          <label className="flex cursor-pointer items-center gap-2 text-xs text-navy">
            <input
              type="checkbox"
              checked={ackConfirmResp}
              onChange={(e) => setAckConfirmResp(e.target.checked)}
              className="size-4 rounded border-slate-300 text-brand"
            />
            I have reviewed the transferred responsibilities and operational context.
          </label>
          <label className="flex cursor-pointer items-center gap-2 text-xs text-navy">
            <input
              type="checkbox"
              checked={ackConfirmRisks}
              onChange={(e) => setAckConfirmRisks(e.target.checked)}
              className="size-4 rounded border-slate-300 text-brand"
            />
            I understand documented risks, caveats, and open work items.
          </label>
          <Field label="Recipient Acknowledgement Notes (optional)">
            <Textarea
              rows={3}
              value={ackNotes}
              onChange={(e) => setAckNotes(e.target.value)}
              placeholder="Note any follow-up onboarding steps or confirmation details…"
            />
          </Field>
        </div>
      </Modal>

      {/* Delivery Clarification Modal */}
      <Modal
        open={Boolean(clarifyTarget)}
        onClose={() => setClarifyTarget(null)}
        title={
          clarifyTarget?.mode === 'request'
            ? 'Request Clarification on Published Package'
            : 'Respond to Recipient Clarification'
        }
        subtitle="Preserves the immutable published package snapshot and records full audit provenance."
        footer={
          <>
            <Button variant="secondary" onClick={() => setClarifyTarget(null)}>
              Cancel
            </Button>
            <Button
              disabled={isSubmitting || clarifyNotes.trim().length < 3}
              onClick={handleClarifyDelivery}
            >
              {isSubmitting ? 'Posting…' : 'Submit'}
            </Button>
          </>
        }
      >
        <Field label="Clarification Details (required)">
          <Textarea
            rows={3}
            value={clarifyNotes}
            onChange={(e) => setClarifyNotes(e.target.value)}
            placeholder="Describe unclear sections, missing operational steps, or your clarifying answer…"
          />
        </Field>
      </Modal>
    </div>
  )
}
