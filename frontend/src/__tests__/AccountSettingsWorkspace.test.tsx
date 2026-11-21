import React from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { AccountSettingsWorkspace } from '../components/settings/AccountSettingsWorkspace'

const mockReplace = vi.fn()
const mockPush = vi.fn()
const mockSetUser = vi.fn()
const mockRefreshUser = vi.fn()
const mockLogout = vi.fn()
const mockAddToast = vi.fn()

let currentSectionParam = ''
let mockUserObj = {
  id: 'user-1',
  email: 'alice@example.com',
  full_name: 'Alice Vance',
  status: 'active',
  is_email_verified: true,
  job_title: 'Principal Engineer',
  bio: 'Handover owner',
  timezone: 'UTC',
  has_avatar: false,
  avatar_url: null,
  auth_method: 'password' as const,
  preferences: {
    theme: 'light' as const,
    date_format: 'DD MMM YYYY' as const,
    density: 'comfortable' as const,
    reduced_motion: false,
    default_landing_page: '/dashboard' as const,
  },
  created_at: '2026-11-01T00:00:00Z',
}

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: mockReplace, push: mockPush }),
  useSearchParams: () => new URLSearchParams(currentSectionParam ? `section=${currentSectionParam}` : ''),
}))

vi.mock('../context/LiveAppContext', () => ({
  useLiveApp: () => ({
    user: mockUserObj,
    setUser: mockSetUser,
    refreshUser: mockRefreshUser,
    logout: mockLogout,
    organisations: [{ id: 'org-1', name: 'Acme Org', slug: 'acme-org', created_at: '2026-11-01T00:00:00Z' }],
    activeOrg: { id: 'org-1', name: 'Acme Org', slug: 'acme-org', created_at: '2026-11-01T00:00:00Z' },
    setActiveOrg: vi.fn(),
    projects: [{ id: 'proj-1', name: 'Core Platform', status: 'active', my_project_role: 'project_manager' }],
    activeProject: { id: 'proj-1', name: 'Core Platform', status: 'active', visibility: 'private', my_project_role: 'project_manager' },
    addToast: mockAddToast,
  }),
}))

const mockUpdateMe = vi.fn()
const mockListMembers = vi.fn()
const mockListSessions = vi.fn()
const mockGetNotifPrefs = vi.fn()
const mockUpdateNotifPrefs = vi.fn()

vi.mock('../lib/api', () => ({
  api: {
    users: {
      updateMe: (...args: unknown[]) => mockUpdateMe(...args),
      uploadAvatar: vi.fn(),
      deleteAvatar: vi.fn(),
      fetchAvatarObjectUrl: vi.fn(),
    },
    organisations: {
      listMembers: (...args: unknown[]) => mockListMembers(...args),
      update: vi.fn(),
      archive: vi.fn(),
    },
    auth: {
      listSessions: (...args: unknown[]) => mockListSessions(...args),
      revokeSession: vi.fn(),
      revokeOtherSessions: vi.fn(),
      revokeAllSessions: vi.fn(),
      changePassword: vi.fn(),
      changeEmail: vi.fn(),
      exportMyData: vi.fn(),
      requestDeletion: vi.fn(),
    },
    notifications: {
      getPreferences: (...args: unknown[]) => mockGetNotifPrefs(...args),
      updatePreferences: (...args: unknown[]) => mockUpdateNotifPrefs(...args),
    },
    sources: {
      listOrgConnections: vi.fn().mockResolvedValue([]),
      startOAuth: vi.fn(),
      disconnectConnection: vi.fn(),
    },
  },
}))

describe('AccountSettingsWorkspace', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    currentSectionParam = ''
    mockListMembers.mockResolvedValue([{ user_id: 'user-1', role_name: 'org_owner' }])
    mockListSessions.mockResolvedValue({ items: [] })
    mockGetNotifPrefs.mockResolvedValue({
      user_id: 'user-1',
      review_requests: true,
      approvals: true,
      ingestion_updates: true,
      project_invitations: true,
      membership_changes: true,
      handover_assigned: true,
      changes_requested: true,
      handover_published: true,
      successor_acknowledged: true,
      verification_assigned: true,
      source_sync_failed: true,
      security_events: true,
      email_digest_enabled: false,
      email_delivery_available: false,
    })
  })

  it('loads profile data and persists profile updates through api.users.updateMe', async () => {
    mockUpdateMe.mockResolvedValue({
      ...mockUserObj,
      full_name: 'Alice Vance-Updated',
    })

    render(<AccountSettingsWorkspace mode="profile" />)
    const nameInput = screen.getByDisplayValue('Alice Vance')
    fireEvent.change(nameInput, { target: { value: 'Alice Vance-Updated' } })

    const saveBtn = screen.getByRole('button', { name: /save profile/i })
    expect(saveBtn).not.toBeDisabled()
    fireEvent.click(saveBtn)

    await waitFor(() => {
      expect(mockUpdateMe).toHaveBeenCalledWith(
        expect.objectContaining({
          full_name: 'Alice Vance-Updated',
        }),
      )
      expect(mockSetUser).toHaveBeenCalled()
    })
  })

  it('navigates to notifications section and persists notification preferences', async () => {
    mockUpdateNotifPrefs.mockResolvedValue({
      user_id: 'user-1',
      review_requests: false,
      approvals: true,
      ingestion_updates: true,
      email_digest_enabled: false,
      email_delivery_available: false,
    })

    render(<AccountSettingsWorkspace mode="settings" />)
    const notifNav = screen.getByRole('button', { name: /notifications/i })
    fireEvent.click(notifNav)

    await waitFor(() => {
      expect(mockGetNotifPrefs).toHaveBeenCalled()
      expect(screen.getByText(/Security & account events \(mandatory\)/i)).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /save notification preferences/i }))
    await waitFor(() => {
      expect(mockUpdateNotifPrefs).toHaveBeenCalled()
    })
  })
})
