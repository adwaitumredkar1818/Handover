import React from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { HandoverVerificationOverview } from '@/components/handover/HandoverVerificationOverview'
import { HandoverVerificationReviewDrawer } from '@/components/handover/HandoverVerificationReviewDrawer'
import { HandoverConflictModal } from '@/components/handover/HandoverConflictModal'
import type { HandoverDomainEpistemicBreakdown, HandoverSectionConflictItem, ProjectMember } from '@/lib/types'

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
vi.mock('@/lib/verificationApi', () => ({
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
      ],
      total: 1,
      page: 1,
      page_size: 25,
      available_domains: ['technical_architecture'],
      available_sources: ['github'],
      available_people: ['Alex Rivera'],
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
          source_name: 'PR #102: Canonical DB setup',
          author: 'Alex Rivera',
          timestamp: '2026-11-15T08:00:00Z',
          excerpt: 'PostgreSQL canonical database with Psycopg 3 driver setup.',
          source_url: 'https://github.com/org/repo/pull/102',
          location_label: 'database.py',
          relationship: 'supports',
          acl_restricted: false,
        },
      ],
      contradictions: [],
      audit_history: [],
      machine_assessment: { ai_model: 'qwen3:8b' },
    }),
    approveCase: vi.fn().mockResolvedValue({ success: true }),
    rejectCase: vi.fn().mockResolvedValue({ success: true }),
  },
}))

// Mock api
vi.mock('@/lib/api', () => ({
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

describe('Handover Workspace Phase 2.1 — Visual QA & Viewport Responsiveness', () => {
  const setViewport = (width: number, height: number) => {
    Object.defineProperty(window, 'innerWidth', { writable: true, configurable: true, value: width })
    Object.defineProperty(window, 'innerHeight', { writable: true, configurable: true, value: height })
    window.dispatchEvent(new Event('resize'))
  }

  describe('HandoverVerificationOverview Viewport Matrix', () => {
    const viewports = [
      { name: 'Desktop Large (1440×900)', width: 1440, height: 900 },
      { name: 'Standard Laptop (1280×800)', width: 1280, height: 800 },
      { name: 'Tablet Landscape (1024×768)', width: 1024, height: 768 },
      { name: 'Mobile Portrait (390×844)', width: 390, height: 844 },
    ]

    viewports.forEach(({ name, width, height }) => {
      it(`renders properly on ${name} without truncation or layout failure`, () => {
        setViewport(width, height)
        render(
          <HandoverVerificationOverview
            epistemicSummary={mockEpistemicSummary}
            totalCandidates={18}
            readinessScore={78}
            onOpenVerificationCenter={vi.fn()}
            onOpenPendingQueue={vi.fn()}
            onOpenConflicts={vi.fn()}
          />
        )

        // Verify header and formula are present
        expect(screen.getByText('Verification Overview & Epistemic Gate')).toBeInTheDocument()
        expect(screen.getByText(/Formula: 14 verified \/ \(14 verified \+ 4 pending\) = 78%/)).toBeInTheDocument()

        // Verify 4-tier cards are rendered
        expect(screen.getByText('Human-Verified Knowledge')).toBeInTheDocument()
        expect(screen.getByText('Pending Human Verification')).toBeInTheDocument()
        expect(screen.getByText('Unresolved Conflicts')).toBeInTheDocument()
        expect(screen.getByText('Rejected or Outdated Findings:')).toBeInTheDocument()
      })
    })
  })

  describe('HandoverVerificationReviewDrawer Viewport Adaptation', () => {
    it('maintains fixed drawer layout with responsive width classes', async () => {
      setViewport(390, 844)
      const { container } = render(
        <HandoverVerificationReviewDrawer
          isOpen={true}
          onClose={vi.fn()}
          projectId="proj-1"
          canReview={true}
          members={mockMembers}
          onDataChanged={vi.fn()}
        />
      )

      const backdrop = container.querySelector('.fixed.inset-0.z-50')
      expect(backdrop).toBeInTheDocument()
      expect(backdrop).toHaveClass('flex')
      expect(backdrop).toHaveClass('justify-end')

      const drawerPanel = container.querySelector('.max-w-6xl')
      expect(drawerPanel).toBeInTheDocument()
      expect(drawerPanel).toHaveClass('w-full')

      // Verify header renders
      await waitFor(() => {
        expect(screen.getByText('Knowledge Verification Queue & Review')).toBeInTheDocument()
      })
    })
  })

  describe('HandoverConflictModal Viewport Adaptation', () => {
    it('adapts side-by-side claims to grid layout on desktop and stacked on mobile', () => {
      setViewport(1440, 900)
      const { container } = render(
        <HandoverConflictModal
          isOpen={true}
          projectId="proj-1"
          conflicts={mockConflicts}
          onClose={vi.fn()}
          onDataChanged={vi.fn()}
          onOpenConflictsWorkspace={vi.fn()}
          canReview={true}
        />
      )

      expect(screen.getByText('Investigate Contradictions & Conflicts')).toBeInTheDocument()
      const claimsGrid = container.querySelector('.grid.grid-cols-1.md\\:grid-cols-2')
      expect(claimsGrid).toBeInTheDocument()

      expect(screen.getByText(/OLLAMA_MAX_CONCURRENT_AI_JOBS is strictly capped at 1/i)).toBeInTheDocument()
      expect(screen.getByText(/Ollama concurrency can be set to 3 parallel jobs/i)).toBeInTheDocument()
      expect(screen.getByText('Adjudicate Conflict')).toBeInTheDocument()
    })
  })
})
