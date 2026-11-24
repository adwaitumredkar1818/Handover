import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { HandoverVerificationOverview } from '../components/handover/HandoverVerificationOverview'
import { HandoverVerificationReviewDrawer } from '../components/handover/HandoverVerificationReviewDrawer'
import { HandoverConflictModal } from '../components/handover/HandoverConflictModal'
import type { HandoverDomainEpistemicBreakdown, HandoverSectionConflictItem, ProjectMember, User } from '../lib/types'

// Mock next/navigation
vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    prefetch: vi.fn(),
  }),
  useParams: () => ({ id: 'case-1' }),
  useSearchParams: () => new URLSearchParams(),
}))

// Mock verificationApi
vi.mock('../lib/verificationApi', () => ({
  verificationApi: {
    getQueue: vi.fn().mockResolvedValue({
      items: [
        {
          id: 'case-item-1',
          finding_id: 'find-1',
          title: 'PostgreSQL is canonical database with Psycopg 3',
          claim: 'PostgreSQL stores all canonical knowledge items and relationships',
          domain: 'technical_architecture',
          case_status: 'pending_review',
          priority: 'high',
          confidence_score: 0.94,
          model_confidence: 0.94,
          source_provider: 'github',
          source_type: 'pull_request',
          source_id: 'PR-102',
          author: 'Alex Rivera',
          supporting_evidence_count: 2,
          contradiction_count: 0,
          updated_at: '2026-11-20T10:00:00Z',
        },
        {
          id: 'case-item-2',
          finding_id: 'find-2',
          title: 'RTX 4050 6GB VRAM Contention Safeguard',
          claim: 'Ollama concurrency is capped at 1 job to prevent out-of-memory errors',
          domain: 'technical_architecture',
          case_status: 'conflicted',
          priority: 'high',
          confidence_score: 0.88,
          model_confidence: 0.88,
          source_provider: 'jira',
          source_type: 'issue',
          source_id: 'ENG-405',
          author: 'Morgan Chen',
          supporting_evidence_count: 1,
          contradiction_count: 1,
          updated_at: '2026-11-21T12:00:00Z',
        },
        {
          id: 'case-item-3',
          finding_id: 'find-3',
          title: 'Legacy Redis cache configuration note',
          claim: 'Redis caching was considered for worker queuing',
          domain: 'technical_architecture',
          case_status: 'pending_review',
          priority: 'low',
          model_confidence: null,
          source_provider: 'docs',
          author: 'Alex Rivera',
          supporting_evidence_count: 1,
          contradiction_count: 0,
          updated_at: '2026-11-21T14:00:00Z',
        },
      ],
      total: 3,
      page: 1,
      page_size: 25,
      available_domains: ['technical_architecture', 'decisions_rationale'],
      available_sources: ['github', 'jira', 'docs'],
      available_people: ['Alex Rivera', 'Morgan Chen'],
    }),
    getCaseDetail: vi.fn().mockResolvedValue({
      id: 'case-item-1',
      finding_id: 'find-1',
      title: 'PostgreSQL is canonical database with Psycopg 3',
      current_claim: 'PostgreSQL stores all canonical knowledge items and relationships',
      original_claim: 'PostgreSQL stores all canonical knowledge items and relationships',
      domain: 'technical_architecture',
      case_status: 'pending_review',
      priority: 'high',
      confidence_score: 0.94,
      ai_model: 'qwen3:8b',
      reasoning: 'Reconstructed from PR-102 architectural commits and migrations',
      evidence_references: [
        {
          id: 'ev-1',
          evidence_id: 'ev-1',
          source_provider: 'github',
          source_type: 'pull_request',
          source_name: 'PR #102: Migrate to Psycopg 3 & PostgreSQL canonical schemas',
          original_title: 'PR #102: Migrate to Psycopg 3 & PostgreSQL canonical schemas',
          source_reference: 'https://github.com/org/repo/pull/102',
          original_source_url: 'https://github.com/org/repo/pull/102',
          author: 'Alex Rivera',
          timestamp: '2026-11-15T08:00:00Z',
          excerpt: 'PostgreSQL is the sole canonical source of truth for all structured application data.',
          acl_restricted: false,
        },
        {
          id: 'ev-2',
          evidence_id: 'ev-2',
          source_provider: 'jira',
          source_type: 'issue',
          source_name: 'SEC-402: Confidential Security Audit Discussion',
          original_title: 'SEC-402: Confidential Security Audit Discussion',
          source_reference: 'https://jira.org/SEC-402',
          original_source_url: 'https://jira.org/SEC-402',
          author: 'Security Lead',
          timestamp: '2026-11-16T12:00:00Z',
          excerpt: '',
          acl_restricted: true,
          acl_scope: 'private_project_board',
        },
      ],
      contradictions: [],
      audit_history: [
        {
          id: 'audit-1',
          action: 'created_candidate',
          actor_name: 'Qwen3 8B Reconstruction Worker',
          created_at: '2026-11-15T08:05:00Z',
          notes: 'Auto-extracted from verified PR #102.',
        },
      ],
      machine_assessment: {
        ai_model: 'qwen3:8b',
      },
    }),
    approveCase: vi.fn().mockImplementation(async (_pid, id) => ({
      id,
      finding_id: 'find-1',
      title: 'PostgreSQL is canonical database with Psycopg 3',
      current_claim: 'PostgreSQL stores all canonical knowledge items and relationships',
      original_claim: 'PostgreSQL stores all canonical knowledge items and relationships',
      domain: 'technical_architecture',
      case_status: 'verified',
      priority: 'high',
      confidence_score: 0.94,
      ai_model: 'qwen3:8b',
      evidence_references: [],
      contradictions: [],
      audit_history: [],
      machine_assessment: { ai_model: 'qwen3:8b' },
    })),
    rejectCase: vi.fn().mockImplementation(async (_pid, id) => ({
      id,
      finding_id: 'find-1',
      title: 'PostgreSQL is canonical database with Psycopg 3',
      current_claim: 'PostgreSQL stores all canonical knowledge items and relationships',
      original_claim: 'PostgreSQL stores all canonical knowledge items and relationships',
      domain: 'technical_architecture',
      case_status: 'rejected',
      priority: 'high',
      confidence_score: 0.94,
      ai_model: 'qwen3:8b',
      evidence_references: [],
      contradictions: [],
      audit_history: [],
      machine_assessment: { ai_model: 'qwen3:8b' },
    })),
    requestClarification: vi.fn().mockResolvedValue({ success: true }),
    editStatement: vi.fn().mockResolvedValue({ success: true }),
    markUnresolved: vi.fn().mockResolvedValue({ success: true }),
  },
}))

// Mock api
vi.mock('../lib/api', () => ({
  api: {
    conflicts: {
      resolve: vi.fn().mockResolvedValue({ id: 'conf-1', resolution_state: 'resolved' }),
    },
  },
}))

const mockEpistemicSummary: HandoverDomainEpistemicBreakdown = {
  human_verified_included: 14,
  pending_verification: 4,
  unresolved_conflicts: 1,
  resolved_conflicts: 2,
  rejected: 2,
  outdated: 1,
}

const mockConflicts: HandoverSectionConflictItem[] = [
  {
    id: 'conf-1',
    verification_case_id: 'case-item-2',
    conflict_type: 'direct_contradiction',
    priority: 'high',
    resolution_state: 'unresolved',
    explanation: 'Conflicting concurrency limits detected between pull request documentation and Jira spike ticket.',
    claim_a_text: 'OLLAMA_MAX_CONCURRENT_AI_JOBS is strictly capped at 1 for 6GB RTX 4050.',
    claim_b_text: 'Ollama concurrency can be set to 3 parallel jobs for faster batch indexing.',
    side_a_source_title: 'PR #89: Configure single-job inference scheduler',
    side_b_source_title: 'ENG-390: Spike multi-threaded indexing',
    updated_at: '2026-11-20T00:00:00Z',
  },
]

const mockMembers: ProjectMember[] = [
  {
    id: 'm-1',
    user_id: 'user-outgoing',
    project_id: 'proj-1',
    full_name: 'Alex Rivera',
    email: 'alex@example.com',
    role_name: 'developer',
    transition_role: 'departing_owner',
    created_at: '2026-01-01T00:00:00Z',
  },
]

const mockCurrentUser: User = {
  id: 'user-outgoing',
  email: 'alex@example.com',
  full_name: 'Alex Rivera',
  roles: ['manager'],
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

describe('Handover Workspace — Phase 2: Verification & Epistemic Integrity', () => {
  describe('HandoverVerificationOverview Metric Integrity & Edge Cases', () => {
    it('renders the 4-tier prioritized matrix with correct counts and explicit formula', () => {
      const onOpenPendingQueue = vi.fn()
      const onOpenConflicts = vi.fn()
      const onOpenVerificationCenter = vi.fn()

      render(
        <HandoverVerificationOverview
          epistemicSummary={mockEpistemicSummary}
          totalCandidates={18}
          readinessScore={78}
          onOpenPendingQueue={onOpenPendingQueue}
          onOpenConflicts={onOpenConflicts}
          onOpenVerificationCenter={onOpenVerificationCenter}
        />
      )

      // Verified findings count (Tier 2)
      expect(screen.getByText('14')).toBeDefined()
      expect(screen.getByText('Human-Verified Knowledge')).toBeDefined()

      // Pending verification count (Tier 1)
      expect(screen.getByText('4')).toBeDefined()
      expect(screen.getByText('Pending Human Verification')).toBeDefined()

      // Unresolved conflicts (Tier 3)
      expect(screen.getByText('1')).toBeDefined()
      expect(screen.getByText('Unresolved Conflicts')).toBeDefined()

      // Excluded knowledge (Tier 4: rejected 2 + outdated 1)
      expect(screen.getByText(/2 rejected · 1 outdated/i)).toBeDefined()
      expect(screen.getByText('Rejected or Outdated Findings:')).toBeDefined()

      // Exact mathematical formula: 14 / (14 + 4) = 14 / 18 = 78%
      expect(screen.getByText('78% Verification Gate')).toBeDefined()
      expect(
        screen.getByText(/Formula: 14 verified \/ \(14 verified \+ 4 pending\) = 78%/i)
      ).toBeDefined()

      // Epistemic separation disclosure
      expect(screen.getByText(/Epistemic Rule:/i)).toBeDefined()
    })

    it('handles zero total findings safely without division by zero', () => {
      const zeroSummary: HandoverDomainEpistemicBreakdown = {
        human_verified_included: 0,
        pending_verification: 0,
        unresolved_conflicts: 0,
        resolved_conflicts: 0,
        rejected: 0,
        outdated: 0,
      }

      render(
        <HandoverVerificationOverview
          epistemicSummary={zeroSummary}
          totalCandidates={0}
          onOpenPendingQueue={vi.fn()}
          onOpenConflicts={vi.fn()}
          onOpenVerificationCenter={vi.fn()}
        />
      )

      expect(screen.getByText('0% Verification Gate')).toBeDefined()
      expect(screen.getByText(/Formula: 0 verified \/ \(0 verified \+ 0 pending\) = 0%/i)).toBeDefined()
    })

    it('handles all findings pending (0% completion)', () => {
      const allPendingSummary: HandoverDomainEpistemicBreakdown = {
        human_verified_included: 0,
        pending_verification: 8,
        unresolved_conflicts: 0,
        resolved_conflicts: 0,
        rejected: 0,
        outdated: 0,
      }

      render(
        <HandoverVerificationOverview
          epistemicSummary={allPendingSummary}
          totalCandidates={8}
          onOpenPendingQueue={vi.fn()}
          onOpenConflicts={vi.fn()}
          onOpenVerificationCenter={vi.fn()}
        />
      )

      expect(screen.getByText('0% Verification Gate')).toBeDefined()
      expect(screen.getByText('Review Required')).toBeDefined()
      expect(screen.getByText(/Formula: 0 verified \/ \(0 verified \+ 8 pending\) = 0%/i)).toBeDefined()
    })

    it('handles all findings verified (100% completion, Gate Passed)', () => {
      const allVerifiedSummary: HandoverDomainEpistemicBreakdown = {
        human_verified_included: 10,
        pending_verification: 0,
        unresolved_conflicts: 0,
        resolved_conflicts: 1,
        rejected: 0,
        outdated: 0,
      }

      render(
        <HandoverVerificationOverview
          epistemicSummary={allVerifiedSummary}
          totalCandidates={10}
          onOpenPendingQueue={vi.fn()}
          onOpenConflicts={vi.fn()}
          onOpenVerificationCenter={vi.fn()}
        />
      )

      expect(screen.getByText('100% Verification Gate')).toBeDefined()
      expect(screen.getByText('Gate Passed')).toBeDefined()
    })

    it('blocks gate pass if conflicts remain unresolved despite 100% verification', () => {
      const conflictedSummary: HandoverDomainEpistemicBreakdown = {
        human_verified_included: 10,
        pending_verification: 0,
        unresolved_conflicts: 2,
        resolved_conflicts: 0,
        rejected: 0,
        outdated: 0,
      }

      render(
        <HandoverVerificationOverview
          epistemicSummary={conflictedSummary}
          totalCandidates={10}
          onOpenPendingQueue={vi.fn()}
          onOpenConflicts={vi.fn()}
          onOpenVerificationCenter={vi.fn()}
        />
      )

      expect(screen.getByText('100% Verification Gate')).toBeDefined()
      // Even with 100%, unresolved conflicts block "Gate Passed"
      expect(screen.getByText('Review Required')).toBeDefined()
    })

    it('triggers the review pending queue callback when the action button is clicked', () => {
      const onOpenPendingQueue = vi.fn()
      render(
        <HandoverVerificationOverview
          epistemicSummary={mockEpistemicSummary}
          totalCandidates={18}
          onOpenPendingQueue={onOpenPendingQueue}
          onOpenConflicts={vi.fn()}
          onOpenVerificationCenter={vi.fn()}
        />
      )

      const reviewBtn = screen.getByRole('button', { name: /^Review$/i })
      fireEvent.click(reviewBtn)
      expect(onOpenPendingQueue).toHaveBeenCalled()
    })

    it('triggers the conflict resolution callback when resolve button is clicked', () => {
      const onOpenConflicts = vi.fn()
      render(
        <HandoverVerificationOverview
          epistemicSummary={mockEpistemicSummary}
          totalCandidates={18}
          onOpenPendingQueue={vi.fn()}
          onOpenConflicts={onOpenConflicts}
          onOpenVerificationCenter={vi.fn()}
        />
      )

      const resolveBtn = screen.getByRole('button', { name: /^Resolve$/i })
      fireEvent.click(resolveBtn)
      expect(onOpenConflicts).toHaveBeenCalled()
    })
  })

  describe('HandoverVerificationReviewDrawer & AI Transparency', () => {
    it('renders the queue items, displays model attribution, and handles approval', async () => {
      const onClose = vi.fn()
      const onDataChanged = vi.fn()

      render(
        <HandoverVerificationReviewDrawer
          isOpen={true}
          onClose={onClose}
          projectId="proj-1"
          initialDomain="all"
          canReview={true}
          members={mockMembers}
          currentUser={mockCurrentUser}
          onDataChanged={onDataChanged}
        />
      )

      expect(screen.getByText('Knowledge Verification Queue & Review')).toBeDefined()

      // Queue items loaded
      await waitFor(() => {
        expect(screen.getAllByText('PostgreSQL is canonical database with Psycopg 3').length).toBeGreaterThanOrEqual(1)
      })

      // Select item and check details
      const itemBtns = screen.getAllByText('PostgreSQL is canonical database with Psycopg 3')
      fireEvent.click(itemBtns[0]!)

      // Inspector displays claim, evidence, and actions
      await waitFor(() => {
        expect(
          screen.getByText('PostgreSQL stores all canonical knowledge items and relationships')
        ).toBeDefined()
      })

      // Cited source evidence is displayed with provider badge
      expect(screen.getByText(/PR #102: Migrate to Psycopg 3/i)).toBeDefined()
      expect(screen.getByText(/Alex Rivera/i)).toBeDefined()

      // AI Model attribution tag is displayed
      expect(screen.getByText('qwen3:8b')).toBeDefined()

      // ACL-restricted evidence masks excerpt and hides direct link
      expect(screen.getByText(/Excerpt text restricted by access permissions/i)).toBeDefined()
      expect(screen.getByText(/Source Access Restricted/i)).toBeDefined()

      // Reviewer action: Click "Approve / Verify Finding" to open confirmation modal
      const openApproveBtn = screen.getByRole('button', { name: /Approve \/ Verify Finding/i })
      expect(openApproveBtn).toBeDefined()
      fireEvent.click(openApproveBtn)

      // Confirm approval inside modal
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /Confirm Approval/i })).toBeDefined()
      })
      const confirmApproveBtn = screen.getByRole('button', { name: /Confirm Approval/i })
      fireEvent.click(confirmApproveBtn)

      await waitFor(() => {
        expect(onDataChanged).toHaveBeenCalled()
      })
    })

    it('displays missing confidence as unavailable, never 0% or invented', async () => {
      render(
        <HandoverVerificationReviewDrawer
          isOpen={true}
          onClose={vi.fn()}
          projectId="proj-1"
          initialDomain="all"
          canReview={true}
          members={mockMembers}
          currentUser={mockCurrentUser}
          onDataChanged={vi.fn()}
        />
      )

      await waitFor(() => {
        expect(screen.getByText('Legacy Redis cache configuration note')).toBeDefined()
      })

      // In the queue, missing confidence shows "Conf unavailable"
      expect(screen.getByText('Conf unavailable')).toBeDefined()
    })

    it('disables review actions when canReview is false', async () => {
      render(
        <HandoverVerificationReviewDrawer
          isOpen={true}
          onClose={vi.fn()}
          projectId="proj-1"
          initialDomain="all"
          canReview={false}
          members={mockMembers}
          currentUser={mockCurrentUser}
          onDataChanged={vi.fn()}
        />
      )

      await waitFor(() => {
        expect(screen.getAllByText('PostgreSQL is canonical database with Psycopg 3').length).toBeGreaterThanOrEqual(1)
      })

      const itemBtns = screen.getAllByText('PostgreSQL is canonical database with Psycopg 3')
      fireEvent.click(itemBtns[0]!)

      await waitFor(() => {
        expect(
          screen.getByText('PostgreSQL stores all canonical knowledge items and relationships')
        ).toBeDefined()
      })

      // View-only notification is shown
      expect(screen.getByText(/View-only Mode/i)).toBeDefined()
      expect(
        screen.getByText(/You are viewing this finding in read-only mode/i)
      ).toBeDefined()
    })
  })

  describe('HandoverConflictModal', () => {
    it('renders side-by-side claims from both sources and enforces adjudication notes', async () => {
      const onClose = vi.fn()
      const onDataChanged = vi.fn()
      const onOpenConflictsWorkspace = vi.fn()

      render(
        <HandoverConflictModal
          isOpen={true}
          onClose={onClose}
          projectId="proj-1"
          conflicts={mockConflicts}
          onOpenConflictsWorkspace={onOpenConflictsWorkspace}
          onDataChanged={onDataChanged}
          canReview={true}
        />
      )

      expect(screen.getByText('Investigate Contradictions & Conflicts')).toBeDefined()
      expect(screen.getByText(/OLLAMA_MAX_CONCURRENT_AI_JOBS is strictly capped at 1/i)).toBeDefined()
      expect(screen.getByText(/Ollama concurrency can be set to 3 parallel jobs/i)).toBeDefined()

      // Sources displayed
      expect(screen.getByText(/PR #89: Configure single-job/i)).toBeDefined()
      expect(screen.getByText(/ENG-390: Spike multi-threaded/i)).toBeDefined()

      // The adjudication section is rendered
      expect(screen.getByText('Adjudicate Conflict')).toBeDefined()

      // Enter adjudication notes
      const notesInput = screen.getByPlaceholderText(/Source B represents the latest approved architecture/i)
      fireEvent.change(notesInput, {
        target: { value: 'Confirmed single-worker cap on RTX 4050 6GB per AGENTS.md rule 3.' },
      })

      // Resolve button is now enabled
      const resolveBtn = screen.getByRole('button', { name: /^Resolve Conflict$/i })
      expect(resolveBtn.hasAttribute('disabled')).toBe(false)
      fireEvent.click(resolveBtn)

      await waitFor(() => {
        expect(onDataChanged).toHaveBeenCalled()
      })
    })
  })
})
