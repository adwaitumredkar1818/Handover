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
    user: { id: 'user-succ', email: 'succ@example.com', full_name: 'Priya Nair', roles: ['project_manager'] },
    setActiveProject: setActiveProjectMock,
  }),
}))

describe('SuccessorOnboardingWorkspace', () => {
  const projectId = '11111111-1111-4111-8111-111111111111'

  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    vi.spyOn(api.projects, 'get').mockResolvedValue({
      id: projectId,
      organisation_id: 'org-1',
      name: 'Travello AI',
      slug: 'travello-ai',
      description: 'Travel planning intelligence platform',
      status: 'active',
      created_at: '2026-11-01T00:00:00Z',
      updated_at: '2026-11-20T00:00:00Z',
    } as never)
    vi.spyOn(api.projects, 'getOverview').mockResolvedValue({
      departing_member: { id: 'user-out', full_name: 'Vernit Garg', email: 'vernit@example.com' },
      successor: { id: 'user-succ', full_name: 'Priya Nair', email: 'succ@example.com' },
      readiness: { overall_readiness_pct: 84 },
    } as never)
    vi.spyOn(api.members, 'list').mockResolvedValue([
      {
        id: 'm1',
        user_id: 'user-succ',
        full_name: 'Priya Nair',
        email: 'succ@example.com',
        role_name: 'project_manager',
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
      items: [
        {
          id: 'f1',
          title: 'PostgreSQL is canonical store',
          structured_summary: 'All structured records live in PostgreSQL.',
          category: 'architecture',
          verification_status: 'verified',
        },
      ],
      total: 1,
    } as never)
    vi.spyOn(api.evidence, 'list').mockResolvedValue([
      { id: 'ev-1', title: 'architecture.pdf', provider: 'document' },
    ] as never)
    vi.spyOn(api.sources, 'listProjectMappings').mockResolvedValue([
      { id: 'src-1', provider: 'github', external_resource_name: 'org/travello' },
    ] as never)
    vi.spyOn(api.handover, 'listCases').mockResolvedValue({
      items: [
        {
          id: 'hc-1',
          project_id: projectId,
          title: 'Travello Transfer v1',
          status: 'approved',
          version: 1,
          latest_readiness_score: 84,
          created_at: '2026-11-18T00:00:00Z',
          updated_at: '2026-11-20T00:00:00Z',
        },
      ],
      total: 1,
    } as never)
    vi.spyOn(api.onboarding, 'getProgress').mockResolvedValue({
      project_id: projectId,
      user_id: 'user-succ',
      completed_steps: { welcome: true },
      steps: [{ step_id: 'welcome', is_completed: true, completed_at: '2026-11-20T10:00:00Z' }],
    } as never)
    vi.spyOn(api.onboarding, 'updateStep').mockResolvedValue({
      step_id: 'welcome',
      is_completed: true,
      completed_at: '2026-11-21T00:00:00Z',
    })
  })

  it('loads persisted progress, displays handover recipient links, and saves step completion', async () => {
    render(<SuccessorOnboardingWorkspace projectId={projectId} />)

    await waitFor(() => {
      expect(screen.getByText('Travello AI')).toBeInTheDocument()
    })

    expect(screen.getByText('1/7 completed (14%)')).toBeInTheDocument()
    expect(screen.getByText('Vernit Garg (vernit@example.com)')).toBeInTheDocument()

    // Navigate to Handover Packages step and verify Recipient View link
    fireEvent.click(screen.getByRole('button', { name: /5\. Handover Packages/i }))
    expect(screen.getByText('Travello Transfer v1')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Recipient View/i })).toHaveAttribute(
      'href',
      '/handovers/hc-1/recipient'
    )

    // Save & Continue persists step via API
    fireEvent.click(screen.getByRole('button', { name: /Save & Continue/i }))
    await waitFor(() => {
      expect(api.onboarding.updateStep).toHaveBeenCalledWith(projectId, 'handover', true)
    })
  })
})
