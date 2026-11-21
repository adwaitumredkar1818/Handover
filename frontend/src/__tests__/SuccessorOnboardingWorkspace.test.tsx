import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { SuccessorOnboardingWorkspace } from '@/components/onboarding/SuccessorOnboardingWorkspace'
import { api } from '@/lib/api'

const pushMock = vi.fn()
const setActiveProjectMock = vi.fn()

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
}))

vi.mock('@/context/LiveAppContext', () => ({
  useLiveApp: () => ({
    user: {
      id: 'user-succ',
      email: 'succ@example.com',
      full_name: 'Priya Nair',
      roles: ['project_member'],
    },
    setActiveProject: setActiveProjectMock,
  }),
}))

describe('SuccessorOnboardingWorkspace', () => {
  const projectId = '11111111-1111-4111-8111-111111111111'
  const caseId1 = '22222222-2222-4222-8222-222222222222'
  const verId1 = '33333333-3333-4333-8333-333333333333'

  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    vi.spyOn(api.projects, 'get').mockResolvedValue({
      id: projectId,
      organisation_id: 'org-1',
      name: 'Travello AI',
      slug: 'travello-ai',
      description: '',
      status: 'active',
      created_at: '2026-11-01T00:00:00Z',
      updated_at: '2026-11-20T00:00:00Z',
    } as never)
    vi.spyOn(api.projects, 'getOverview').mockResolvedValue({
      departing_member: { id: 'user-out', full_name: 'Vernit Garg', email: 'vernit@example.com' },
      successor: { id: 'user-succ', full_name: 'Priya Nair', email: 'succ@example.com' },
      readiness: { overall_readiness_pct: 90 },
    } as never)
    vi.spyOn(api.members, 'list').mockResolvedValue([
      {
        id: 'm1',
        user_id: 'user-succ',
        full_name: 'Priya Nair',
        email: 'succ@example.com',
        role_name: 'project_member',
        transition_role: 'incoming_assignee',
      },
      {
        id: 'm2',
        user_id: 'user-out',
        full_name: 'Vernit Garg',
        email: 'vernit@example.com',
        role_name: 'project_member',
        transition_role: 'departing_owner',
      },
    ] as never)
    vi.spyOn(api.knowledgeIntelligence, 'listFindings').mockResolvedValue({
      items: [],
      total: 0,
    } as never)
    vi.spyOn(api.evidence, 'list').mockResolvedValue([] as never)
    vi.spyOn(api.sources, 'listProjectMappings').mockResolvedValue([] as never)
    vi.spyOn(api.onboarding, 'getProgress').mockResolvedValue({
      project_id: projectId,
      user_id: 'user-succ',
      completed_steps: {},
      items: [],
    } as never)
    vi.spyOn(api.onboarding, 'updateStep').mockResolvedValue({
      step_id: 'welcome',
      is_completed: true,
      completed_at: '2026-11-21T00:00:00Z',
    })
  })

  it('launches Successor Handover Onboarding for an assigned published case, does not auto-complete on navigation, and supports explicit review & acknowledgement', async () => {
    vi.spyOn(api.handover, 'listCases').mockResolvedValue({
      items: [
        {
          id: caseId1,
          project_id: projectId,
          title: 'Travello Backend Transfer',
          status: 'published',
          version: 1,
          departing_member_id: 'user-out',
          successor_id: 'user-succ',
          current_version_id: verId1,
          handover_type: 'developer',
          created_at: '2026-11-18T00:00:00Z',
          updated_at: '2026-11-20T00:00:00Z',
        },
      ],
      total: 1,
    } as never)
    vi.spyOn(api.handover, 'getCase').mockResolvedValue({
      case: {
        id: caseId1,
        project_id: projectId,
        title: 'Travello Backend Transfer',
        status: 'published',
        version: 1,
        departing_member_id: 'user-out',
        successor_id: 'user-succ',
      },
      packages: [],
      signoffs: [],
      status_history: [],
      responsibility_transfers: [],
    } as never)
    vi.spyOn(api.handover, 'getVersions').mockResolvedValue([
      {
        id: verId1,
        package_id: 'pkg-1',
        version_number: 1,
        is_current: true,
        assembly_status: 'published',
        assembled_at: '2026-11-20T00:00:00Z',
        content_hash: 'hash-v1',
        created_at: '2026-11-20T00:00:00Z',
      },
    ] as never)
    vi.spyOn(api.handover, 'getResponsibilityWorkspace').mockResolvedValue({
      transfers: [
        {
          id: 'tr-1',
          title: 'Payment Worker Ownership',
          responsibility_description: 'Own ingestion & payment job retries.',
          transfer_status: 'pending_successor_ack',
          successor_acknowledged_at: null,
          ownership_certainty: 'confirmed',
        },
      ],
    } as never)
    vi.spyOn(api.handover, 'getVersionSections').mockResolvedValue({
      handover_type: 'developer',
      handover_type_label: 'Developer Handover',
      role_focus_summary: 'Focus on backend workers and PostgreSQL schema.',
      mandatory_sections: [
        {
          section_key: 'executive_overview',
          section_number: 1,
          section_title: 'Project Overview',
          knowledge_items: [
            { title: 'Core Purpose', content: 'AI travel itinerary engine.' },
          ],
          evidence_references: [],
        },
        {
          section_key: 'pending_work',
          section_number: 4,
          section_title: 'Pending Work',
          knowledge_items: [
            { title: 'Finish staging rollout', content: 'Verify Alembic migration.', provenance: [] },
          ],
          evidence_references: [],
        },
      ],
    } as never)
    vi.spyOn(api.handover, 'getSignoffWorkspace').mockResolvedValue({
      publication: {
        deliveries: [
          {
            id: 'del-1',
            delivered_to_user_id: 'user-succ',
            acknowledged: false,
            acknowledgement: null,
            clarifications: [],
          },
        ],
      },
    } as never)
    vi.spyOn(api.handover, 'acknowledgeDelivery').mockResolvedValue({
      id: 'ack-1',
    } as never)

    render(<SuccessorOnboardingWorkspace projectId={projectId} />)

    await waitFor(() => {
      expect(screen.getByText('Successor Handover Onboarding')).toBeInTheDocument()
    })

    // Falls back to approved overview when project.description is empty
    await waitFor(() => {
      expect(screen.getByText('AI travel itinerary engine.')).toBeInTheDocument()
    })
    // Starts at 0/7 (0%), never auto-completed
    expect(screen.getByText('0/7 reviewed (0%)')).toBeInTheDocument()
    // Shows "What you're taking over" from real responsibility transfers
    expect(screen.getByText(/Payment Worker Ownership/)).toBeInTheDocument()

    // Navigating via Next Step must NOT mark Step 1 complete
    fireEvent.click(screen.getByRole('button', { name: /Next Step/i }))
    expect(api.onboarding.updateStep).not.toHaveBeenCalled()
    expect(screen.getByText('0/7 reviewed (0%)')).toBeInTheDocument()

    // Explicit Mark Step Reviewed persists scoped by caseId & versionId
    fireEvent.click(screen.getByRole('button', { name: /Mark Step Reviewed/i }))
    await waitFor(() => {
      expect(api.onboarding.updateStep).toHaveBeenCalledWith(projectId, 'understand', true, {
        caseId: caseId1,
        versionId: verId1,
      })
    })
    expect(screen.getByText('1/7 reviewed (14%)')).toBeInTheDocument()

    // Step 7: Formal acknowledgement is explicit and independent
    fireEvent.click(screen.getByRole('button', { name: /7\. Ready & Acknowledgement/i }))
    fireEvent.click(
      screen.getByRole('button', {
        name: /I acknowledge receiving this published Handover package\./i,
      })
    )
    await waitFor(() => {
      expect(api.handover.acknowledgeDelivery).toHaveBeenCalledWith(projectId, 'del-1', {
        acknowledgement_notes: 'I acknowledge receiving this published Handover package.',
        expected_content_hash: 'hash-v1',
      })
    })
  })

  it('shows honest empty state when successor only has unpublished draft cases', async () => {
    vi.spyOn(api.handover, 'listCases').mockResolvedValue({
      items: [
        {
          id: caseId1,
          project_id: projectId,
          title: 'Unpublished Draft Case',
          status: 'draft',
          version: 1,
          successor_id: 'user-succ',
          created_at: '2026-11-18T00:00:00Z',
          updated_at: '2026-11-20T00:00:00Z',
        },
      ],
      total: 1,
    } as never)

    render(<SuccessorOnboardingWorkspace projectId={projectId} />)

    await waitFor(() => {
      expect(
        screen.getByText('No published Handover has been assigned to you yet.')
      ).toBeInTheDocument()
    })
    expect(screen.queryByText('Unpublished Draft Case')).not.toBeInTheDocument()
  })
})
