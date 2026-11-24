import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { HandoverWorkspaceHeader } from '../components/handover/HandoverWorkspaceHeader'
import { HandoverLifecycleStepper } from '../components/handover/HandoverLifecycleStepper'
import { HandoverWorkspaceNav } from '../components/handover/HandoverWorkspaceNav'
import type { Handover, ProjectRole } from '../lib/figmaStore'
import type {
  HandoverPackageVersionSummary,
  HandoverReadinessIntelligenceResponse,
  HandoverVersionSectionsResponse,
  ProjectMember,
  User,
} from '../lib/types'

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

const mockHandover: Handover = {
  id: 'case-1',
  code: 'HO-001',
  projectId: 'proj-1',
  outgoingId: 'user-outgoing',
  incomingId: 'user-incoming',
  status: 'in_progress',
  scope: 'Full backend engineering handover',
  created: '10 Nov 2026',
  updated: '22 Nov 2026',
  due: '30 Nov 2026',
  progress: 60,
  handoverType: 'developer',
}

const mockCurrentUser: User = {
  id: 'user-outgoing',
  email: 'alex@example.com',
  full_name: 'Alex Rivera',
  roles: ['developer'],
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

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
  {
    id: 'm-2',
    user_id: 'user-incoming',
    project_id: 'proj-1',
    full_name: 'Morgan Chen',
    email: 'morgan@example.com',
    role_name: 'developer',
    transition_role: 'incoming_assignee',
    created_at: '2026-01-01T00:00:00Z',
  },
]

const mockVersions: HandoverPackageVersionSummary[] = [
  {
    id: 'ver-1',
    package_id: 'pkg-1',
    version_number: 1,
    is_current: true,
    content_hash: 'a1b2c3d4e5f67890123456789abcdef0',
    assembled_at: '2026-11-22T00:00:00Z',
    assembled_by_user_id: 'user-outgoing',
    created_at: '2026-11-22T00:00:00Z',
  },
]

const mockSectionsData: HandoverVersionSectionsResponse = {
  case_id: 'case-1',
  project_id: 'proj-1',
  version: {
    id: 'ver-1',
    package_id: 'pkg-1',
    version_number: 1,
    is_current: true,
    content_hash: 'a1b2c3d4e5f67890123456789abcdef0',
    assembled_at: '2026-11-22T00:00:00Z',
    assembled_by_user_id: 'user-outgoing',
    created_at: '2026-11-22T00:00:00Z',
  },
  handover_type: 'developer',
  handover_type_label: 'Developer Handover',
  role_focus_summary: 'Focus on technical architecture, decisions, and operations',
  mandatory_sections: [],
  missing_section_types: [],
  epistemic_summary: {
    human_verified_included: 20,
    pending_verification: 5,
    unresolved_conflicts: 1,
    resolved_conflicts: 0,
    rejected: 0,
    outdated: 0,
  },
  sections: [],
}

const mockReadinessData: HandoverReadinessIntelligenceResponse = {
  version_id: 'ver-1',
  case_id: 'case-1',
  project_id: 'proj-1',
  overall_score: 87,
  overall_level: 'ready_with_warnings',
  is_ready_for_signoff: false,
  categories: [],
  structured_blockers: [],
  blocker_count: 2,
  warning_count: 1,
  recommendations: [],
  assessment_history: [],
  checklist_summary: {
    total_groups: 1,
    total_items: 10,
    completed_items: 8,
    mandatory_total: 5,
    mandatory_completed: 4,
    mandatory_outstanding: 1,
    completion_pct: 80,
    groups: [],
  },
  assessed_at: '2026-11-22T00:00:00Z',
}

describe('Handover Workspace Phase 1 Refinements', () => {
  describe('HandoverLifecycleStepper', () => {
    it('renders all 6 canonical lifecycle stages', () => {
      render(
        <HandoverLifecycleStepper
          currentStatus="in_progress"
          createdDate="10 Nov 2026"
          assembledDate="22 Nov 2026"
        />
      )

      // Desktop and mobile stage labels
      expect(screen.getAllByText('Draft').length).toBeGreaterThanOrEqual(1)
      expect(screen.getAllByText('Verification').length).toBeGreaterThanOrEqual(1)
      expect(screen.getAllByText('Manager Review').length).toBeGreaterThanOrEqual(1)
      expect(screen.getAllByText('Approved').length).toBeGreaterThanOrEqual(1)
      expect(screen.getAllByText('Published').length).toBeGreaterThanOrEqual(1)
      expect(screen.getAllByText('Acknowledged').length).toBeGreaterThanOrEqual(1)
    })
  })

  describe('HandoverWorkspaceHeader', () => {
    it('renders project identity, transfer corridor, epistemic counter, and action hierarchy', () => {
      const handleSignOff = vi.fn()
      const handleAskAssistant = vi.fn()
      const handleOpenEditModal = vi.fn()
      const handleRefreshDraft = vi.fn().mockResolvedValue(undefined)
      const handleOpenReport = vi.fn()
      const handleSelectVersion = vi.fn()

      render(
        <HandoverWorkspaceHeader
          handover={mockHandover}
          projectName="Project Aurora"
          role="outgoing"
          members={mockMembers}
          currentUser={mockCurrentUser}
          sectionsData={mockSectionsData}
          versions={mockVersions}
          selectedVersionId="ver-1"
          onSelectVersionId={handleSelectVersion}
          isLoadingVersions={false}
          isLoadingSections={false}
          readinessData={mockReadinessData}
          isRefreshingDraft={false}
          onRefreshDraft={handleRefreshDraft}
          onOpenEditModal={handleOpenEditModal}
          onAskAssistant={handleAskAssistant}
          onSignOff={handleSignOff}
          onOpenReport={handleOpenReport}
          currentTab="overview"
        />
      )

      // Project title & Handover code
      expect(screen.getByText('Project Aurora')).toBeInTheDocument()
      expect(screen.getByText('HO-001')).toBeInTheDocument()

      // Transfer corridor (outgoing -> incoming)
      expect(screen.getByText(/Alex Rivera/)).toBeInTheDocument()
      expect(screen.getByText('Morgan Chen')).toBeInTheDocument()

      // Epistemic count (20 verified / 5 pending -> 80% verified)
      expect(screen.getByText(/80% verified/)).toBeInTheDocument()
      expect(screen.getByText(/20 Verified/i)).toBeInTheDocument()
      expect(screen.getByText(/5 Pending/i)).toBeInTheDocument()

      // Primary Action: Sign-Off & Approval
      const signOffBtn = screen.getByRole('button', { name: /Sign-Off & Approval/i })
      expect(signOffBtn).toBeInTheDocument()
      fireEvent.click(signOffBtn)
      expect(handleSignOff).toHaveBeenCalledTimes(1)

      // Secondary Action: Ask Assistant
      const assistantBtn = screen.getByRole('button', { name: /Ask Assistant/i })
      expect(assistantBtn).toBeInTheDocument()
      fireEvent.click(assistantBtn)
      expect(handleAskAssistant).toHaveBeenCalledTimes(1)

      // Secondary Action: Edit Details
      const editBtn = screen.getByRole('button', { name: /Edit Details/i })
      expect(editBtn).toBeInTheDocument()
      fireEvent.click(editBtn)
      expect(handleOpenEditModal).toHaveBeenCalledTimes(1)

      // Package version selection & SHA-256
      expect(screen.getByLabelText('Package Version')).toBeInTheDocument()
      expect(screen.getByText(/SHA-256: a1b2c3d4e5f6…/)).toBeInTheDocument()
    })
  })

  describe('HandoverWorkspaceNav', () => {
    it('renders grouped navigation sections and navigates on click', () => {
      const handleSelectTab = vi.fn()
      const counts = {
        readiness: 2,
        checklists: 1,
        decisions: 5,
        architecture: 3,
        evidence: 12,
      }

      render(
        <HandoverWorkspaceNav
          activeTab="overview"
          counts={counts}
          readinessData={mockReadinessData}
          onSelectTab={handleSelectTab}
        />
      )

      // Nav group labels
      expect(screen.getAllByText('Overview').length).toBeGreaterThanOrEqual(1)
      expect(screen.getByText('Knowledge')).toBeInTheDocument()
      expect(screen.getByText('Transfer')).toBeInTheDocument()
      expect(screen.getByText('Output')).toBeInTheDocument()

      // Specific tabs
      expect(screen.getByRole('tab', { name: /Readiness/i })).toBeInTheDocument()
      expect(screen.getByRole('tab', { name: /Decisions/i })).toBeInTheDocument()
      expect(screen.getByRole('tab', { name: /Checklists/i })).toBeInTheDocument()

      // Click on Decisions tab
      const decisionsTab = screen.getByRole('tab', { name: /Decisions/i })
      fireEvent.click(decisionsTab)
      expect(handleSelectTab).toHaveBeenCalledWith('decisions')
    })
  })
})
