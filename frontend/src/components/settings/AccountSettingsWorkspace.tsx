'use client'

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import {
  AlertTriangle,
  Bell,
  Building2,
  Camera,
  Check,
  CheckCircle2,
  Download,
  FolderKanban,
  Globe,
  KeyRound,
  Laptop,
  Lock,
  LogOut,
  Mail,
  Monitor,
  Palette,
  Plug,
  RefreshCw,
  ScrollText,
  Shield,
  ShieldCheck,
  Smartphone,
  Sparkles,
  Trash2,
  User as UserIcon,
  Users,
} from 'lucide-react'
import { useLiveApp } from '../../context/LiveAppContext'
import { api } from '../../lib/api'
import { applyUserPreferences, DEFAULT_USER_PREFERENCES } from '../../lib/userPreferences'
import type {
  AccountDeletionRequestResponse,
  NotificationPreferences,
  SourceConnection,
  UserPreferences,
  UserSession,
} from '../../lib/types'
import {
  Avatar,
  Badge,
  Button,
  Callout,
  Card,
  CardHeader,
  ConfirmDialog,
  Field,
  Input,
  Modal,
  PageHeader,
  PasswordInput,
  Select,
  Switch,
  Table,
  Td,
  Textarea,
  Th,
  cn,
} from '../figma-ui'
import { SourceIcon } from '../figma-ui/brand'
import type { SourceType } from '../../lib/figmaStore'

export type SettingsSectionId =
  | 'profile'
  | 'security'
  | 'appearance'
  | 'notifications'
  | 'connections'
  | 'privacy'
  | 'organisation'
  | 'project'

const COMMON_TIMEZONES = [
  'UTC',
  'Europe/London',
  'Europe/Berlin',
  'Europe/Paris',
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'Asia/Kolkata',
  'Asia/Singapore',
  'Asia/Tokyo',
  'Australia/Sydney',
]

function parseUserAgentLabel(meta?: Record<string, string> | null): {
  label: string
  isMobile: boolean
} {
  const ua = meta?.user_agent || meta?.userAgent || ''
  if (!ua) return { label: 'Authenticated Web Session', isMobile: false }
  const isMobile = /mobile|iphone|android|ipad/i.test(ua)
  let browser = 'Browser'
  if (/edg\//i.test(ua)) browser = 'Microsoft Edge'
  else if (/chrome|crios/i.test(ua)) browser = 'Chrome'
  else if (/firefox|fxios/i.test(ua)) browser = 'Firefox'
  else if (/safari/i.test(ua)) browser = 'Safari'
  let os = ''
  if (/windows/i.test(ua)) os = 'Windows'
  else if (/mac os|macintosh/i.test(ua)) os = 'macOS'
  else if (/iphone|ipad/i.test(ua)) os = 'iOS'
  else if (/android/i.test(ua)) os = 'Android'
  else if (/linux/i.test(ua)) os = 'Linux'
  return {
    label: os ? `${os} · ${browser}` : browser,
    isMobile,
  }
}

function formatDateWithPrefs(
  iso: string | null | undefined,
  format: UserPreferences['date_format'] = 'DD MMM YYYY',
  tz = 'UTC',
): string {
  if (!iso) return 'Not available'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return String(iso)
  try {
    if (format === 'YYYY-MM-DD') {
      return new Intl.DateTimeFormat('en-CA', {
        timeZone: tz,
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
      }).format(d)
    }
    if (format === 'MM/DD/YYYY') {
      return new Intl.DateTimeFormat('en-US', {
        timeZone: tz,
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
      }).format(d)
    }
    return new Intl.DateTimeFormat('en-GB', {
      timeZone: tz,
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    }).format(d)
  } catch {
    return d.toLocaleDateString()
  }
}

export interface AccountSettingsWorkspaceProps {
  mode: 'profile' | 'settings'
}

export function AccountSettingsWorkspace({ mode }: AccountSettingsWorkspaceProps) {
  const router = useRouter()
  const searchParams = useSearchParams()
  const {
    user,
    setUser,
    refreshUser,
    logout,
    organisations,
    activeOrg,
    setActiveOrg,
    projects,
    activeProject,
    addToast,
  } = useLiveApp()

  const rawSectionParam = searchParams?.get('section') || searchParams?.get('tab') || ''
  const resolveInitialSection = (): SettingsSectionId => {
    const map: Record<string, SettingsSectionId> = {
      profile: 'profile',
      security: 'security',
      appearance: 'appearance',
      preferences: 'appearance',
      notifications: 'notifications',
      accounts: 'connections',
      connections: 'connections',
      integrations: 'connections',
      privacy: 'privacy',
      retention: 'privacy',
      organisation: 'organisation',
      workspace: 'organisation',
      general: mode === 'profile' ? 'profile' : 'organisation',
      permissions: 'organisation',
      project: 'project',
    }
    if (rawSectionParam && map[rawSectionParam]) return map[rawSectionParam]
    return mode === 'profile' ? 'profile' : 'organisation'
  }

  const [section, setSection] = useState<SettingsSectionId>(resolveInitialSection)
  useEffect(() => {
    setSection(resolveInitialSection())
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, rawSectionParam])

  const selectSection = (next: SettingsSectionId) => {
    setSection(next)
    const base = mode === 'profile' ? '/settings/profile' : '/settings'
    router.replace(`${base}?section=${next}`, { scroll: false })
  }

  const prefs = user?.preferences ?? DEFAULT_USER_PREFERENCES
  const userTz = user?.timezone || 'UTC'

  // Org membership role lookup for current user
  const [orgRoleName, setOrgRoleName] = useState<string | null>(null)
  useEffect(() => {
    if (!activeOrg?.id || !user?.id) {
      setOrgRoleName(null)
      return
    }
    let active = true
    api.organisations
      .listMembers(activeOrg.id)
      .then((list) => {
        if (!active) return
        const mine = list.find((m) => m.user_id === user.id)
        setOrgRoleName(mine?.role_name || null)
      })
      .catch(() => {
        if (active) setOrgRoleName(null)
      })
    return () => {
      active = false
    }
  }, [activeOrg?.id, user?.id])

  const isOrgOwner = orgRoleName === 'org_owner'
  const isOrgAdmin = isOrgOwner || orgRoleName === 'org_admin'

  // Section 1: Profile state
  const [fullName, setFullName] = useState(user?.full_name || '')
  const [jobTitle, setJobTitle] = useState(user?.job_title || '')
  const [bio, setBio] = useState(user?.bio || '')
  const [timezone, setTimezone] = useState(user?.timezone || 'UTC')
  const [savingProfile, setSavingProfile] = useState(false)
  const [profileError, setProfileError] = useState<string | null>(null)
  const [uploadingAvatar, setUploadingAvatar] = useState(false)
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  useEffect(() => {
    if (!user) return
    setFullName(user.full_name || '')
    setJobTitle(user.job_title || '')
    setBio(user.bio || '')
    setTimezone(user.timezone || 'UTC')
  }, [user?.id, user?.full_name, user?.job_title, user?.bio, user?.timezone])

  const profileDirty =
    Boolean(user) &&
    (fullName.trim() !== (user?.full_name || '') ||
      jobTitle.trim() !== (user?.job_title || '') ||
      bio.trim() !== (user?.bio || '') ||
      timezone !== (user?.timezone || 'UTC'))

  const handleSaveProfile = async (e: React.FormEvent) => {
    e.preventDefault()
    if (fullName.trim().length < 2) {
      setProfileError('Full name must be at least 2 characters.')
      return
    }
    setSavingProfile(true)
    setProfileError(null)
    try {
      const updated = await api.users.updateMe({
        full_name: fullName.trim(),
        job_title: jobTitle.trim() || null,
        bio: bio.trim() || null,
        timezone,
      })
      setUser(updated)
      addToast({ type: 'success', title: 'Profile saved', message: 'Your profile details have been updated.' })
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to update profile.'
      setProfileError(msg)
      addToast({ type: 'error', title: 'Profile update failed', message: msg })
    } finally {
      setSavingProfile(false)
    }
  }

  const handleAvatarFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    if (file.size > 2 * 1024 * 1024) {
      addToast({ type: 'error', title: 'Image too large', message: 'Avatar must be 2 MB or smaller.' })
      return
    }
    setUploadingAvatar(true)
    try {
      const updated = await api.users.uploadAvatar(file)
      setUser(updated)
      addToast({ type: 'success', title: 'Avatar updated', message: 'Your profile picture has been saved.' })
    } catch (err) {
      addToast({
        type: 'error',
        title: 'Avatar upload failed',
        message: err instanceof Error ? err.message : 'Could not upload avatar.',
      })
    } finally {
      setUploadingAvatar(false)
    }
  }

  const handleRemoveAvatar = async () => {
    setUploadingAvatar(true)
    try {
      const updated = await api.users.deleteAvatar()
      setUser(updated)
      addToast({ type: 'info', title: 'Avatar removed', message: 'Reverted to your initials avatar.' })
    } catch (err) {
      addToast({
        type: 'error',
        title: 'Remove failed',
        message: err instanceof Error ? err.message : 'Could not remove avatar.',
      })
    } finally {
      setUploadingAvatar(false)
    }
  }

  // Section 2: Security & Sessions
  const [curPw, setCurPw] = useState('')
  const [newPw, setNewPw] = useState('')
  const [confirmPw, setConfirmPw] = useState('')
  const [savingPw, setSavingPw] = useState(false)
  const [pwError, setPwError] = useState<string | null>(null)

  const [newEmail, setNewEmail] = useState('')
  const [emailPw, setEmailPw] = useState('')
  const [savingEmail, setSavingEmail] = useState(false)
  const [emailError, setEmailError] = useState<string | null>(null)

  const [sessions, setSessions] = useState<UserSession[]>([])
  const [loadingSessions, setLoadingSessions] = useState(false)
  const [revokingId, setRevokingId] = useState<string | null>(null)
  const [confirmLogoutAll, setConfirmLogoutAll] = useState(false)

  const loadSessions = useCallback(async () => {
    setLoadingSessions(true)
    try {
      const res = await api.auth.listSessions()
      setSessions((res.items || []).filter((s) => !s.revoked_at))
    } catch {
      setSessions([])
    } finally {
      setLoadingSessions(false)
    }
  }, [])

  useEffect(() => {
    if (section === 'security') {
      void loadSessions()
    }
  }, [section, loadSessions])

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault()
    setPwError(null)
    if (newPw.length < 8) {
      setPwError('New password must be at least 8 characters.')
      return
    }
    if (newPw !== confirmPw) {
      setPwError('New passwords do not match.')
      return
    }
    setSavingPw(true)
    try {
      const res = await api.auth.changePassword({
        current_password: curPw,
        new_password: newPw,
      })
      setCurPw('')
      setNewPw('')
      setConfirmPw('')
      addToast({ type: 'success', title: 'Password updated', message: res.message })
      void loadSessions()
    } catch (err) {
      setPwError(err instanceof Error ? err.message : 'Failed to update password.')
    } finally {
      setSavingPw(false)
    }
  }

  const handleChangeEmail = async (e: React.FormEvent) => {
    e.preventDefault()
    setEmailError(null)
    if (!newEmail.includes('@')) {
      setEmailError('Enter a valid email address.')
      return
    }
    setSavingEmail(true)
    try {
      const res = await api.auth.changeEmail({
        new_email: newEmail.trim(),
        current_password: emailPw,
      })
      setNewEmail('')
      setEmailPw('')
      await refreshUser()
      addToast({ type: 'success', title: 'Email updated', message: res.message })
    } catch (err) {
      setEmailError(err instanceof Error ? err.message : 'Failed to update email.')
    } finally {
      setSavingEmail(false)
    }
  }

  // Section 3: Appearance & Preferences
  const [prefForm, setPrefForm] = useState<UserPreferences>(prefs)
  const [savingAppearance, setSavingAppearance] = useState(false)
  useEffect(() => {
    if (user?.preferences) setPrefForm(user.preferences)
  }, [user?.preferences])

  const handleSaveAppearance = async () => {
    setSavingAppearance(true)
    try {
      const updated = await api.users.updateMe({ preferences: prefForm })
      setUser(updated)
      applyUserPreferences(updated.preferences)
      addToast({ type: 'success', title: 'Appearance saved', message: 'Your preferences are persisted across sessions.' })
    } catch (err) {
      addToast({
        type: 'error',
        title: 'Save failed',
        message: err instanceof Error ? err.message : 'Could not save appearance preferences.',
      })
    } finally {
      setSavingAppearance(false)
    }
  }

  // Section 4: Notification Preferences
  const [notifPrefs, setNotifPrefs] = useState<NotificationPreferences | null>(null)
  const [loadingNotifs, setLoadingNotifs] = useState(false)
  const [savingNotifs, setSavingNotifs] = useState(false)

  useEffect(() => {
    if (section !== 'notifications') return
    let active = true
    setLoadingNotifs(true)
    api.notifications
      .getPreferences()
      .then((res) => {
        if (active) setNotifPrefs(res)
      })
      .catch(() => {
        if (active) setNotifPrefs(null)
      })
      .finally(() => {
        if (active) setLoadingNotifs(false)
      })
    return () => {
      active = false
    }
  }, [section])

  const handleSaveNotifPrefs = async () => {
    if (!notifPrefs) return
    setSavingNotifs(true)
    try {
      const updated = await api.notifications.updatePreferences({
        project_invitations: notifPrefs.project_invitations,
        membership_changes: notifPrefs.membership_changes,
        handover_assigned: notifPrefs.handover_assigned,
        review_requests: notifPrefs.review_requests,
        changes_requested: notifPrefs.changes_requested,
        approvals: notifPrefs.approvals,
        handover_published: notifPrefs.handover_published,
        successor_acknowledged: notifPrefs.successor_acknowledged,
        verification_assigned: notifPrefs.verification_assigned,
        ingestion_updates: notifPrefs.ingestion_updates,
        source_sync_failed: notifPrefs.source_sync_failed,
        email_digest_enabled: notifPrefs.email_digest_enabled,
      })
      setNotifPrefs(updated)
      addToast({ type: 'success', title: 'Notification preferences saved', message: 'Your delivery preferences are active.' })
    } catch (err) {
      addToast({
        type: 'error',
        title: 'Failed to save',
        message: err instanceof Error ? err.message : 'Could not persist notification preferences.',
      })
    } finally {
      setSavingNotifs(false)
    }
  }

  // Section 5: Connected Accounts
  const [connections, setConnections] = useState<SourceConnection[]>([])
  const [loadingConnections, setLoadingConnections] = useState(false)
  const [disconnectTarget, setDisconnectTarget] = useState<SourceConnection | null>(null)
  const [disconnecting, setDisconnecting] = useState(false)

  const loadConnections = useCallback(async () => {
    if (!activeOrg?.id) {
      setConnections([])
      return
    }
    setLoadingConnections(true)
    try {
      const list = await api.sources.listOrgConnections(activeOrg.id)
      setConnections(list)
    } catch {
      setConnections([])
    } finally {
      setLoadingConnections(false)
    }
  }, [activeOrg?.id])

  useEffect(() => {
    if (section === 'connections') {
      void loadConnections()
    }
  }, [section, loadConnections])

  const handleConnectProvider = async (provider: 'github' | 'jira' | 'slack') => {
    if (!activeOrg?.id) return
    try {
      const res = await api.sources.startOAuth(activeOrg.id, provider)
      if (res.authorization_url) {
        window.location.href = res.authorization_url
      } else {
        router.push('/sources')
      }
    } catch (err) {
      addToast({
        type: 'info',
        title: `Connect ${provider} in Sources`,
        message: err instanceof Error ? err.message : 'Redirecting to Connected Sources.',
      })
      router.push('/sources')
    }
  }

  const handleConfirmDisconnect = async () => {
    if (!disconnectTarget) return
    setDisconnecting(true)
    try {
      await api.sources.disconnectConnection(disconnectTarget.id)
      addToast({
        type: 'info',
        title: 'Account disconnected',
        message: 'Existing canonical evidence and approved knowledge were preserved.',
      })
      setDisconnectTarget(null)
      await loadConnections()
    } catch (err) {
      addToast({
        type: 'error',
        title: 'Disconnect failed',
        message: err instanceof Error ? err.message : 'Could not disconnect account.',
      })
    } finally {
      setDisconnecting(false)
    }
  }

  // Section 6: Privacy & Data
  const [exporting, setExporting] = useState(false)
  const [delModalOpen, setDelModalOpen] = useState(false)
  const [delConfirmText, setDelConfirmText] = useState('')
  const [delPassword, setDelPassword] = useState('')
  const [delReason, setDelReason] = useState('')
  const [submittingDel, setSubmittingDel] = useState(false)
  const [delResult, setDelResult] = useState<AccountDeletionRequestResponse | null>(null)

  const handleExportData = async () => {
    setExporting(true)
    try {
      const payload = await api.auth.exportMyData()
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `the-handover-account-export-${new Date().toISOString().slice(0, 10)}.json`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
      addToast({ type: 'success', title: 'Data exported', message: 'Downloaded your personal account export (JSON).' })
    } catch (err) {
      addToast({
        type: 'error',
        title: 'Export failed',
        message: err instanceof Error ? err.message : 'Could not export account data.',
      })
    } finally {
      setExporting(false)
    }
  }

  const handleSubmitDeletion = async () => {
    setSubmittingDel(true)
    setDelResult(null)
    try {
      const res = await api.auth.requestDeletion({
        confirmation_text: delConfirmText,
        current_password: user?.auth_method === 'oauth' ? undefined : delPassword,
        reason: delReason.trim() || undefined,
      })
      setDelResult(res)
      if (res.status === 'pending_review') {
        addToast({ type: 'info', title: 'Deletion request recorded', message: res.message })
        setDelConfirmText('')
        setDelPassword('')
      }
    } catch (err) {
      addToast({
        type: 'error',
        title: 'Request rejected',
        message: err instanceof Error ? err.message : 'Could not submit deletion request.',
      })
    } finally {
      setSubmittingDel(false)
    }
  }

  // Section 7: Organisation Settings
  const [orgName, setOrgName] = useState(activeOrg?.name || '')
  const [orgDesc, setOrgDesc] = useState((activeOrg as unknown as { description?: string })?.description || '')
  const [savingOrg, setSavingOrg] = useState(false)
  const [archiveOrgOpen, setArchiveOrgOpen] = useState(false)
  const [archivingOrg, setArchivingOrg] = useState(false)

  useEffect(() => {
    setOrgName(activeOrg?.name || '')
    setOrgDesc((activeOrg as unknown as { description?: string })?.description || '')
  }, [activeOrg])

  const handleSaveOrg = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!activeOrg?.id || !isOrgAdmin) return
    setSavingOrg(true)
    try {
      const updated = await api.organisations.update(activeOrg.id, {
        name: orgName.trim(),
        description: orgDesc.trim() || null,
      })
      setActiveOrg(updated)
      addToast({ type: 'success', title: 'Organisation updated', message: `Saved settings for ${updated.name}.` })
    } catch (err) {
      addToast({
        type: 'error',
        title: 'Update failed',
        message: err instanceof Error ? err.message : 'Could not update organisation.',
      })
    } finally {
      setSavingOrg(false)
    }
  }

  const handleArchiveOrg = async () => {
    if (!activeOrg?.id || !isOrgOwner) return
    setArchivingOrg(true)
    try {
      await api.organisations.archive(activeOrg.id)
      addToast({ type: 'info', title: 'Organisation archived', message: `${activeOrg.name} has been archived.` })
      setArchiveOrgOpen(false)
    } catch (err) {
      addToast({
        type: 'error',
        title: 'Archive failed',
        message: err instanceof Error ? err.message : 'Could not archive organisation.',
      })
    } finally {
      setArchivingOrg(false)
    }
  }

  const navItems: Array<{
    id: SettingsSectionId
    label: string
    group: 'Personal' | 'Workspace'
    icon: React.ComponentType<{ className?: string }>
  }> = [
    { id: 'profile', label: 'My Profile', group: 'Personal', icon: UserIcon },
    { id: 'security', label: 'Account & Security', group: 'Personal', icon: ShieldCheck },
    { id: 'appearance', label: 'Appearance & Preferences', group: 'Personal', icon: Palette },
    { id: 'notifications', label: 'Notifications', group: 'Personal', icon: Bell },
    { id: 'connections', label: 'Connected Accounts', group: 'Personal', icon: Plug },
    { id: 'privacy', label: 'Privacy & Data', group: 'Personal', icon: Lock },
    { id: 'organisation', label: 'Organisation Settings', group: 'Workspace', icon: Building2 },
    ...(activeProject
      ? [{ id: 'project' as const, label: 'Active Project', group: 'Workspace' as const, icon: FolderKanban }]
      : []),
  ]

  const tzOptions = useMemo(() => {
    const set = new Set(COMMON_TIMEZONES)
    if (timezone) set.add(timezone)
    return Array.from(set)
  }, [timezone])

  return (
    <div className="space-y-6">
      <PageHeader
        title={mode === 'profile' ? 'Profile & Account' : 'Settings'}
        subtitle="Manage your personal identity, security, appearance, notifications, connected accounts, and workspace controls."
        actions={
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" icon={Users} onClick={() => router.push('/settings/team')}>
              Team management
            </Button>
            <Button variant="secondary" icon={ScrollText} onClick={() => router.push('/settings/audit-logs')}>
              Audit logs
            </Button>
          </div>
        }
      />

      {/* Mobile section selector */}
      <div className="lg:hidden">
        <Field label="Settings Section">
          <Select value={section} onChange={(e) => selectSection(e.target.value as SettingsSectionId)}>
            {navItems.map((item) => (
              <option key={item.id} value={item.id}>
                {item.group}: {item.label}
              </option>
            ))}
          </Select>
        </Field>
      </div>

      <div className="grid gap-6 lg:grid-cols-[240px_1fr]">
        {/* Left Navigation */}
        <aside className="hidden lg:block">
          <Card className="sticky top-6 p-2">
            {(['Personal', 'Workspace'] as const).map((group) => (
              <div key={group} className="mb-3 last:mb-0">
                <p className="px-3 pb-1.5 pt-2 text-[11px] font-semibold uppercase tracking-wider text-muted">
                  {group}
                </p>
                <nav className="space-y-0.5" aria-label={`${group} settings`}>
                  {navItems
                    .filter((i) => i.group === group)
                    .map((item) => {
                      const Icon = item.icon
                      const active = section === item.id
                      return (
                        <button
                          key={item.id}
                          type="button"
                          onClick={() => selectSection(item.id)}
                          className={cn(
                            'flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-[13px] font-medium transition cursor-pointer',
                            active
                              ? 'bg-tint text-brand font-semibold'
                              : 'text-navy hover:bg-slate-50',
                          )}
                        >
                          <Icon className={cn('size-4 shrink-0', active ? 'text-brand' : 'text-muted')} />
                          <span className="truncate">{item.label}</span>
                        </button>
                      )
                    })}
                </nav>
              </div>
            ))}
          </Card>
        </aside>

        {/* Right Content */}
        <div className="min-w-0 space-y-5">
          {/* 1. MY PROFILE */}
          {section === 'profile' && (
            <div className="space-y-5">
              <Card className="p-5 sm:p-6">
                <div className="flex flex-col gap-5 border-b border-line pb-6 sm:flex-row sm:items-center">
                  <div className="relative w-fit">
                    <Avatar name={user?.full_name || fullName || 'User'} src={user?.avatar_url} size={80} />
                    <button
                      type="button"
                      disabled={uploadingAvatar}
                      onClick={() => fileInputRef.current?.click()}
                      className="absolute -bottom-1 -right-1 flex size-8 items-center justify-center rounded-full border-2 border-white bg-brand text-white shadow-sm hover:bg-brand-dark cursor-pointer disabled:opacity-50"
                      aria-label="Upload profile picture"
                    >
                      <Camera className="size-3.5" />
                    </button>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept="image/png,image/jpeg,image/webp"
                      className="hidden"
                      onChange={handleAvatarFile}
                    />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <h2 className="text-lg font-semibold text-navy truncate">
                        {user?.full_name || 'Authenticated User'}
                      </h2>
                      {user?.is_email_verified ? (
                        <Badge tone="green">Email Verified</Badge>
                      ) : (
                        <Badge tone="amber">Email Unverified</Badge>
                      )}
                    </div>
                    <p className="text-sm text-muted truncate">{user?.email}</p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <Button
                        size="sm"
                        variant="secondary"
                        disabled={uploadingAvatar}
                        onClick={() => fileInputRef.current?.click()}
                      >
                        {uploadingAvatar ? 'Uploading…' : 'Upload picture'}
                      </Button>
                      {user?.has_avatar && (
                        <Button
                          size="sm"
                          variant="ghost"
                          disabled={uploadingAvatar}
                          onClick={handleRemoveAvatar}
                        >
                          Remove
                        </Button>
                      )}
                      <span className="self-center text-[11.5px] text-muted">
                        PNG, JPEG, or WebP · max 2 MB · encrypted in private storage
                      </span>
                    </div>
                  </div>
                </div>

                <form onSubmit={handleSaveProfile} className="mt-6 space-y-4">
                  {profileError && (
                    <Callout tone="red" icon={AlertTriangle} title="Validation error">
                      {profileError}
                    </Callout>
                  )}
                  <div className="grid gap-4 sm:grid-cols-2">
                    <Field label="Display name">
                      <Input
                        value={fullName}
                        onChange={(e) => setFullName(e.target.value)}
                        required
                        minLength={2}
                        maxLength={120}
                      />
                    </Field>
                    <Field label="Job title (optional)">
                      <Input
                        value={jobTitle}
                        onChange={(e) => setJobTitle(e.target.value)}
                        placeholder="e.g. Staff Backend Engineer"
                        maxLength={120}
                      />
                    </Field>
                    <Field label="Email address" hint="Change email in Account & Security">
                      <Input value={user?.email || ''} disabled />
                    </Field>
                    <Field label="Timezone">
                      <Select value={timezone} onChange={(e) => setTimezone(e.target.value)}>
                        {tzOptions.map((tz) => (
                          <option key={tz} value={tz}>
                            {tz}
                          </option>
                        ))}
                      </Select>
                    </Field>
                  </div>
                  <Field label="Personal bio (optional)" hint="Max 500 characters">
                    <Textarea
                      rows={3}
                      value={bio}
                      onChange={(e) => setBio(e.target.value)}
                      maxLength={500}
                      placeholder="Briefly describe your domain ownership or responsibilities…"
                    />
                  </Field>
                  <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-4">
                    <span className="text-xs text-muted">
                      Member since {formatDateWithPrefs(user?.created_at, prefs.date_format, userTz)}
                    </span>
                    <div className="flex gap-2">
                      {profileDirty && (
                        <Button
                          type="button"
                          variant="ghost"
                          onClick={() => {
                            setFullName(user?.full_name || '')
                            setJobTitle(user?.job_title || '')
                            setBio(user?.bio || '')
                            setTimezone(user?.timezone || 'UTC')
                            setProfileError(null)
                          }}
                        >
                          Reset
                        </Button>
                      )}
                      <Button type="submit" icon={Check} disabled={!profileDirty || savingProfile}>
                        {savingProfile ? 'Saving…' : 'Save profile'}
                      </Button>
                    </div>
                  </div>
                </form>
              </Card>

              <Card className="p-5">
                <CardHeader
                  title="Workspace & Project Memberships"
                  subtitle="Organisations and projects associated with your account"
                />
                <div className="mt-3 grid gap-4 sm:grid-cols-2">
                  <div className="rounded-xl border border-line p-3.5">
                    <p className="text-xs font-semibold uppercase tracking-wide text-muted">
                      Organisations ({organisations.length})
                    </p>
                    <ul className="mt-2 space-y-1.5 text-[13px]">
                      {organisations.length === 0 ? (
                        <li className="text-muted">No active organisations</li>
                      ) : (
                        organisations.map((o) => (
                          <li key={o.id} className="flex items-center justify-between gap-2">
                            <span className="font-medium text-navy truncate">{o.name}</span>
                            {o.id === activeOrg?.id && <Badge tone="blue">Active</Badge>}
                          </li>
                        ))
                      )}
                    </ul>
                  </div>
                  <div className="rounded-xl border border-line p-3.5">
                    <p className="text-xs font-semibold uppercase tracking-wide text-muted">
                      Projects ({projects.length})
                    </p>
                    <ul className="mt-2 space-y-1.5 text-[13px] max-h-40 overflow-y-auto">
                      {projects.length === 0 ? (
                        <li className="text-muted">No active projects</li>
                      ) : (
                        projects.map((p) => (
                          <li key={p.id} className="flex items-center justify-between gap-2">
                            <span className="font-medium text-navy truncate">{p.name}</span>
                            <Badge tone="gray">{p.my_project_role || p.status}</Badge>
                          </li>
                        ))
                      )}
                    </ul>
                  </div>
                </div>
              </Card>
            </div>
          )}

          {/* 2. ACCOUNT & SECURITY */}
          {section === 'security' && (
            <div className="space-y-5">
              <Card className="p-5 sm:p-6">
                <CardHeader
                  title="Account Identity"
                  subtitle="Authentication method, account status, and email verification"
                />
                <div className="mt-4 grid gap-3 sm:grid-cols-3 text-[13px]">
                  <div className="rounded-xl border border-line p-3">
                    <p className="text-xs text-muted">Authentication method</p>
                    <p className="mt-1 font-semibold text-navy capitalize">
                      {user?.auth_method === 'oauth'
                        ? 'External OAuth'
                        : user?.auth_method === 'hybrid'
                        ? 'Password + OAuth'
                        : 'Email & Password'}
                    </p>
                  </div>
                  <div className="rounded-xl border border-line p-3">
                    <p className="text-xs text-muted">Account status</p>
                    <div className="mt-1">
                      <Badge tone={user?.status === 'active' ? 'green' : 'amber'}>
                        {user?.status || 'active'}
                      </Badge>
                    </div>
                  </div>
                  <div className="rounded-xl border border-line p-3">
                    <p className="text-xs text-muted">Last sign-in</p>
                    <p className="mt-1 font-medium text-navy">
                      {formatDateWithPrefs(user?.last_login_at, prefs.date_format, userTz)}
                    </p>
                  </div>
                </div>

                {user?.auth_method === 'oauth' ? (
                  <div className="mt-4">
                    <Callout tone="blue" icon={Globe} title="Managed by external provider">
                      Your email and password are managed by your external OAuth sign-in provider.
                    </Callout>
                  </div>
                ) : (
                  <form onSubmit={handleChangeEmail} className="mt-5 border-t border-line pt-5 space-y-3">
                    <p className="text-sm font-semibold text-navy">Change Account Email</p>
                    {emailError && (
                      <Callout tone="red" icon={AlertTriangle} title="Email update failed">
                        {emailError}
                      </Callout>
                    )}
                    <div className="grid gap-3 sm:grid-cols-2">
                      <Field label="New email address">
                        <Input
                          type="email"
                          value={newEmail}
                          onChange={(e) => setNewEmail(e.target.value)}
                          placeholder="new.email@company.com"
                          required
                        />
                      </Field>
                      <Field label="Current password">
                        <PasswordInput
                          value={emailPw}
                          onChange={(e) => setEmailPw(e.target.value)}
                          required
                        />
                      </Field>
                    </div>
                    <Button type="submit" variant="secondary" icon={Mail} disabled={savingEmail || !newEmail || !emailPw}>
                      {savingEmail ? 'Updating…' : 'Update email'}
                    </Button>
                  </form>
                )}
              </Card>

              <div className="grid gap-5 lg:grid-cols-2">
                <Card className="p-5 sm:p-6">
                  <CardHeader title="Password & Security" subtitle="Update your local platform password" />
                  {user?.auth_method === 'oauth' ? (
                    <div className="mt-4">
                      <Callout tone="blue" icon={KeyRound} title="OAuth-only account">
                        Password changes are managed through your connected Google/OAuth provider.
                      </Callout>
                    </div>
                  ) : (
                    <form onSubmit={handleChangePassword} className="mt-4 space-y-3.5">
                      {pwError && (
                        <Callout tone="red" icon={AlertTriangle} title="Password error">
                          {pwError}
                        </Callout>
                      )}
                      <Field label="Current password">
                        <PasswordInput value={curPw} onChange={(e) => setCurPw(e.target.value)} required />
                      </Field>
                      <Field label="New password" hint="At least 8 characters with strong entropy">
                        <PasswordInput value={newPw} onChange={(e) => setNewPw(e.target.value)} required minLength={8} />
                      </Field>
                      <Field label="Confirm new password">
                        <PasswordInput value={confirmPw} onChange={(e) => setConfirmPw(e.target.value)} required />
                      </Field>
                      <Button type="submit" disabled={savingPw || !curPw || !newPw || !confirmPw}>
                        {savingPw ? 'Updating…' : 'Update password'}
                      </Button>
                    </form>
                  )}

                  <div className="mt-5 border-t border-line pt-4">
                    <div className="flex items-center justify-between gap-2">
                      <div>
                        <p className="text-[13px] font-semibold text-navy">Multi-Factor Authentication (MFA)</p>
                        <p className="text-xs text-muted">
                          TOTP / hardware-key MFA is not supported by the current FastAPI session provider.
                        </p>
                      </div>
                      <Badge tone="gray">Not Supported</Badge>
                    </div>
                  </div>
                </Card>

                <Card className="p-5 sm:p-6">
                  <CardHeader
                    title="Active Sessions"
                    subtitle="Refresh-session families currently valid for your account"
                    action={
                      <Button
                        size="sm"
                        variant="ghost"
                        className="text-red-600"
                        onClick={async () => {
                          try {
                            const res = await api.auth.revokeOtherSessions()
                            addToast({ type: 'info', title: 'Other sessions revoked', message: res.message })
                            await loadSessions()
                          } catch (err) {
                            addToast({
                              type: 'error',
                              title: 'Revoke failed',
                              message: err instanceof Error ? err.message : 'Could not revoke sessions.',
                            })
                          }
                        }}
                      >
                        Sign out others
                      </Button>
                    }
                  />
                  {loadingSessions ? (
                    <p className="mt-4 text-xs text-muted">Loading active sessions…</p>
                  ) : sessions.length === 0 ? (
                    <p className="mt-4 text-xs text-muted">No active refresh sessions recorded.</p>
                  ) : (
                    <ul className="mt-4 space-y-2.5">
                      {sessions.map((sess) => {
                        const ua = parseUserAgentLabel(sess.session_metadata)
                        const Icon = ua.isMobile ? Smartphone : Laptop
                        return (
                          <li key={sess.id} className="flex items-center gap-3 rounded-xl border border-line p-3">
                            <Icon className="size-5 shrink-0 text-muted" />
                            <div className="min-w-0 flex-1">
                              <p className="truncate text-[13px] font-medium text-navy">{ua.label}</p>
                              <p className="text-xs text-muted">
                                Created {formatDateWithPrefs(sess.created_at, prefs.date_format, userTz)}
                                {sess.last_used_at
                                  ? ` · Last used ${formatDateWithPrefs(sess.last_used_at, prefs.date_format, userTz)}`
                                  : ''}
                              </p>
                            </div>
                            {sess.is_current_family ? (
                              <Badge tone="green">Current</Badge>
                            ) : (
                              <Button
                                size="sm"
                                variant="ghost"
                                icon={LogOut}
                                disabled={revokingId === sess.id}
                                onClick={async () => {
                                  setRevokingId(sess.id)
                                  try {
                                    await api.auth.revokeSession(sess.id)
                                    addToast({ type: 'info', title: 'Session revoked', message: 'Device signed out.' })
                                    await loadSessions()
                                  } catch (err) {
                                    addToast({
                                      type: 'error',
                                      title: 'Failed',
                                      message: err instanceof Error ? err.message : 'Could not revoke session.',
                                    })
                                  } finally {
                                    setRevokingId(null)
                                  }
                                }}
                              >
                                Revoke
                              </Button>
                            )}
                          </li>
                        )
                      })}
                    </ul>
                  )}
                  <div className="mt-4 border-t border-line pt-4">
                    <Button
                      variant="danger"
                      size="sm"
                      icon={LogOut}
                      onClick={() => setConfirmLogoutAll(true)}
                    >
                      Logout from all devices
                    </Button>
                  </div>
                </Card>
              </div>
            </div>
          )}

          {/* 3. APPEARANCE & PREFERENCES */}
          {section === 'appearance' && (
            <Card className="p-5 sm:p-6 space-y-5">
              <CardHeader
                title="Appearance & Preferences"
                subtitle="Persisted across sessions and devices without affecting Handover PDF reports or Relationship graphs"
              />
              <div className="grid gap-3 sm:grid-cols-3">
                {(
                  [
                    { id: 'light', label: 'Light', desc: 'Crisp white surfaces', icon: Monitor },
                    { id: 'dark', label: 'Dark', desc: 'Low-glare slate palette', icon: Palette },
                    { id: 'system', label: 'System', desc: 'Follow OS preference', icon: Sparkles },
                  ] as const
                ).map((opt) => {
                  const active = prefForm.theme === opt.id
                  return (
                    <button
                      key={opt.id}
                      type="button"
                      onClick={() => {
                        const next = { ...prefForm, theme: opt.id }
                        setPrefForm(next)
                        applyUserPreferences(next)
                      }}
                      className={cn(
                        'rounded-xl border p-4 text-left transition cursor-pointer',
                        active ? 'border-brand bg-tint/50 ring-1 ring-brand/30' : 'border-line hover:border-slate-300',
                      )}
                    >
                      <p className="text-sm font-semibold text-navy">{opt.label}</p>
                      <p className="mt-0.5 text-xs text-muted">{opt.desc}</p>
                    </button>
                  )
                })}
              </div>

              <div className="grid gap-4 sm:grid-cols-3">
                <Field label="Date format">
                  <Select
                    value={prefForm.date_format}
                    onChange={(e) =>
                      setPrefForm({
                        ...prefForm,
                        date_format: e.target.value as UserPreferences['date_format'],
                      })
                    }
                  >
                    <option value="DD MMM YYYY">DD MMM YYYY (21 Nov 2026)</option>
                    <option value="MM/DD/YYYY">MM/DD/YYYY (11/21/2026)</option>
                    <option value="YYYY-MM-DD">YYYY-MM-DD (2026-11-21)</option>
                  </Select>
                </Field>
                <Field label="Interface density">
                  <Select
                    value={prefForm.density}
                    onChange={(e) => {
                      const next = {
                        ...prefForm,
                        density: e.target.value as UserPreferences['density'],
                      }
                      setPrefForm(next)
                      applyUserPreferences(next)
                    }}
                  >
                    <option value="comfortable">Comfortable</option>
                    <option value="compact">Compact</option>
                  </Select>
                </Field>
                <Field label="Default landing page">
                  <Select
                    value={prefForm.default_landing_page}
                    onChange={(e) =>
                      setPrefForm({
                        ...prefForm,
                        default_landing_page: e.target.value as UserPreferences['default_landing_page'],
                      })
                    }
                  >
                    <option value="/dashboard">Dashboard</option>
                    <option value="/projects">My Projects</option>
                    <option value="/handovers/received">Received Handovers</option>
                  </Select>
                </Field>
              </div>

              <div className="flex items-center justify-between rounded-xl border border-line p-4">
                <div>
                  <p className="text-sm font-medium text-navy">Reduce motion</p>
                  <p className="text-xs text-muted">Minimise UI transitions and animations across the workspace.</p>
                </div>
                <Switch
                  checked={prefForm.reduced_motion}
                  onChange={(v) => {
                    const next = { ...prefForm, reduced_motion: v }
                    setPrefForm(next)
                    applyUserPreferences(next)
                  }}
                />
              </div>

              <div className="flex justify-end border-t border-line pt-4">
                <Button icon={Check} disabled={savingAppearance} onClick={handleSaveAppearance}>
                  {savingAppearance ? 'Saving…' : 'Save preferences'}
                </Button>
              </div>
            </Card>
          )}

          {/* 4. NOTIFICATIONS */}
          {section === 'notifications' && (
            <Card className="p-5 sm:p-6 space-y-4">
              <CardHeader
                title="Notification Preferences"
                subtitle="Configure persistent in-app alerts and supported email digest delivery"
              />
              {loadingNotifs || !notifPrefs ? (
                <p className="text-xs text-muted">Loading notification preferences…</p>
              ) : (
                <>
                  <div className="divide-y divide-line">
                    {(
                      [
                        ['project_invitations', 'Project & workspace invitations', 'Alerts when you are invited to join a project or organisation'],
                        ['membership_changes', 'Team membership changes', 'Role changes and team transitions on your projects'],
                        ['handover_assigned', 'Handover assigned to you', 'When you are designated as departing owner or incoming successor'],
                        ['review_requests', 'Handover approval & review requests', 'When a handover enters Phase 2 managerial review'],
                        ['changes_requested', 'Changes requested', 'When a reviewer returns a handover package for revision'],
                        ['approvals', 'Handover approvals', 'When managerial sign-off is granted'],
                        ['handover_published', 'Handover publication', 'When an approved handover package is published to you'],
                        ['successor_acknowledged', 'Successor acknowledgement', 'When a recipient formally acknowledges receipt'],
                        ['verification_assigned', 'Verification tasks assigned', 'Candidate findings or checklist items awaiting your review'],
                        ['ingestion_updates', 'Background processing completion', 'Document extraction, indexing, and knowledge reconstruction completion'],
                        ['source_sync_failed', 'Failed source synchronisation', 'Alerts when a connected GitHub, Jira, or Slack sync fails'],
                      ] as const
                    ).map(([key, title, desc]) => (
                      <div key={key} className="flex items-center justify-between gap-4 py-3.5">
                        <div>
                          <p className="text-[13.5px] font-medium text-navy">{title}</p>
                          <p className="text-xs text-muted">{desc}</p>
                        </div>
                        <Switch
                          checked={Boolean(notifPrefs[key])}
                          onChange={(v) => setNotifPrefs({ ...notifPrefs, [key]: v })}
                        />
                      </div>
                    ))}
                    <div className="flex items-center justify-between gap-4 py-3.5">
                      <div>
                        <p className="text-[13.5px] font-medium text-navy">Security & account events (mandatory)</p>
                        <p className="text-xs text-muted">Password changes, email updates, and session revocations cannot be muted.</p>
                      </div>
                      <Switch checked={true} disabled onChange={() => {}} />
                    </div>
                    <div className="flex items-center justify-between gap-4 py-3.5">
                      <div>
                        <p className="text-[13.5px] font-medium text-navy">Email activity digest</p>
                        <p className="text-xs text-muted">
                          {notifPrefs.email_delivery_available
                            ? 'Send periodic email summaries for unread notifications.'
                            : 'Outbound email delivery is not configured on this server.'}
                        </p>
                      </div>
                      <Switch
                        checked={Boolean(notifPrefs.email_digest_enabled)}
                        disabled={!notifPrefs.email_delivery_available}
                        onChange={(v) => setNotifPrefs({ ...notifPrefs, email_digest_enabled: v })}
                      />
                    </div>
                  </div>
                  <div className="flex justify-end border-t border-line pt-4">
                    <Button icon={Check} disabled={savingNotifs} onClick={handleSaveNotifPrefs}>
                      {savingNotifs ? 'Saving…' : 'Save notification preferences'}
                    </Button>
                  </div>
                </>
              )}
            </Card>
          )}

          {/* 5. CONNECTED ACCOUNTS */}
          {section === 'connections' && (
            <Card className="p-5 sm:p-6 space-y-4">
              <CardHeader
                title="Connected Accounts"
                subtitle={
                  activeOrg
                    ? `Personal OAuth source connections in ${activeOrg.name}`
                    : 'Select an organisation to manage connected accounts'
                }
                action={
                  <Button variant="secondary" size="sm" icon={RefreshCw} onClick={loadConnections}>
                    Refresh
                  </Button>
                }
              />
              <Callout tone="blue" icon={Shield} title="Connections vs. Project Evidence">
                Disconnecting a personal OAuth account pauses future personal syncs using that credential, but never deletes canonical project evidence or approved handover knowledge.
              </Callout>
              {loadingConnections ? (
                <p className="text-xs text-muted">Loading connected accounts…</p>
              ) : (
                <div className="divide-y divide-line">
                  {(['github', 'jira', 'slack'] as const).map((provider) => {
                    const conn = connections.find(
                      (c) => c.provider === provider && c.status !== 'disconnected',
                    )
                    return (
                      <div key={provider} className="flex flex-wrap items-center gap-4 py-4">
                        <SourceIcon type={provider as SourceType} size={40} />
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <p className="text-[14px] font-semibold text-navy capitalize">{provider}</p>
                            {conn ? (
                              <Badge tone={conn.status === 'active' ? 'green' : 'amber'}>
                                {conn.status}
                              </Badge>
                            ) : (
                              <Badge tone="gray">Not connected</Badge>
                            )}
                          </div>
                          {conn ? (
                            <p className="mt-0.5 text-xs text-muted">
                              Account: {conn.display_name || conn.account_identifier || 'Authenticated'}
                              {conn.last_synced_at
                                ? ` · Last synced ${formatDateWithPrefs(conn.last_synced_at, prefs.date_format, userTz)}`
                                : ''}
                            </p>
                          ) : (
                            <p className="mt-0.5 text-xs text-muted">
                              Connect your {provider} account to authorise delegated source discovery.
                            </p>
                          )}
                        </div>
                        <div className="flex gap-2">
                          {conn ? (
                            <>
                              <Button size="sm" variant="secondary" onClick={() => handleConnectProvider(provider)}>
                                Reconnect
                              </Button>
                              <Button
                                size="sm"
                                variant="ghost"
                                className="text-red-600"
                                onClick={() => setDisconnectTarget(conn)}
                              >
                                Disconnect
                              </Button>
                            </>
                          ) : (
                            <Button size="sm" onClick={() => handleConnectProvider(provider)}>
                              Connect
                            </Button>
                          )}
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </Card>
          )}

          {/* 6. PRIVACY & DATA */}
          {section === 'privacy' && (
            <div className="space-y-5">
              <Card className="p-5 sm:p-6 space-y-4">
                <CardHeader
                  title="Privacy & Personal Data"
                  subtitle="Inspect and export data scoped strictly to your account"
                />
                <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-line p-4">
                  <div>
                    <p className="text-sm font-semibold text-navy">Export personal account data</p>
                    <p className="text-xs text-muted">
                      Download a JSON archive containing your profile, memberships, session metadata, notification preferences, and personal audit events.
                    </p>
                  </div>
                  <Button variant="secondary" icon={Download} disabled={exporting} onClick={handleExportData}>
                    {exporting ? 'Preparing…' : 'Export my data (JSON)'}
                  </Button>
                </div>
              </Card>

              <Card className="border-red-200 p-5 sm:p-6 space-y-3">
                <CardHeader
                  title="Account Deletion Request"
                  subtitle="High-risk operation with organisational retention & ownership checks"
                />
                <p className="text-xs leading-relaxed text-muted">
                  To protect institutional memory, shared project evidence, approved handover snapshots, and immutable audit logs are preserved under organisational retention policy. If you are the sole Owner of an active organisation, ownership must be transferred first.
                </p>
                <Button
                  variant="danger"
                  size="sm"
                  icon={Trash2}
                  onClick={() => {
                    setDelResult(null)
                    setDelModalOpen(true)
                  }}
                >
                  Request account deletion…
                </Button>
              </Card>
            </div>
          )}

          {/* 7. ORGANISATION SETTINGS */}
          {section === 'organisation' && (
            <div className="space-y-5">
              <Card className="p-5 sm:p-6 space-y-4">
                <CardHeader
                  title="Organisation Settings"
                  subtitle={
                    activeOrg
                      ? `Configuration for ${activeOrg.name} (${isOrgAdmin ? 'Admin access' : 'Read-only member view'})`
                      : 'No active organisation selected'
                  }
                />
                {activeOrg ? (
                  <form onSubmit={handleSaveOrg} className="space-y-4">
                    <div className="grid gap-4 sm:grid-cols-2">
                      <Field label="Organisation name">
                        <Input
                          value={orgName}
                          onChange={(e) => setOrgName(e.target.value)}
                          disabled={!isOrgAdmin}
                          required
                          minLength={2}
                        />
                      </Field>
                      <Field label="Workspace slug" hint="Canonical URL identifier">
                        <Input value={activeOrg.slug} disabled />
                      </Field>
                    </div>
                    <Field label="Description (optional)">
                      <Textarea
                        rows={2}
                        value={orgDesc}
                        onChange={(e) => setOrgDesc(e.target.value)}
                        disabled={!isOrgAdmin}
                      />
                    </Field>
                    {isOrgAdmin ? (
                      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-4">
                        {isOrgOwner ? (
                          <Button
                            type="button"
                            variant="danger"
                            size="sm"
                            icon={Trash2}
                            onClick={() => setArchiveOrgOpen(true)}
                          >
                            Archive organisation…
                          </Button>
                        ) : (
                          <span className="text-xs text-muted">Only an Organisation Owner can archive this workspace.</span>
                        )}
                        <Button type="submit" icon={Check} disabled={savingOrg}>
                          {savingOrg ? 'Saving…' : 'Save organisation'}
                        </Button>
                      </div>
                    ) : (
                      <Callout tone="amber" icon={Lock} title="Read-only access">
                        Organisation Owner or Admin role is required to modify organisation settings.
                      </Callout>
                    )}
                  </form>
                ) : (
                  <p className="text-xs text-muted">Select or create an organisation from the sidebar switcher.</p>
                )}
              </Card>

              <Card className="overflow-hidden">
                <CardHeader
                  title="Workspace Role Permissions"
                  subtitle="Enforced server-side by FastAPI RBAC on every request"
                />
                <Table>
                  <thead>
                    <tr>
                      <Th>Capability</Th>
                      <Th>Owner</Th>
                      <Th>Admin</Th>
                      <Th>Member</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {[
                      ['Archive organisation', 1, 0, 0],
                      ['Manage members, roles & invitations', 1, 1, 0],
                      ['Edit organisation details', 1, 1, 0],
                      ['View audit logs', 1, 1, 0],
                      ['Create & access authorised projects', 1, 1, 1],
                    ].map(([label, ...vals]) => (
                      <tr key={label as string}>
                        <Td className="text-[13px]">{label}</Td>
                        {vals.map((v, idx) => (
                          <Td key={idx}>
                            {v ? (
                              <CheckCircle2 className="size-4 text-ok" />
                            ) : (
                              <span className="text-slate-300">—</span>
                            )}
                          </Td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </Table>
              </Card>
            </div>
          )}

          {/* 8. PROJECT SETTINGS */}
          {section === 'project' && activeProject && (
            <Card className="p-5 sm:p-6 space-y-4">
              <CardHeader
                title={`Active Project: ${activeProject.name}`}
                subtitle="Project-level configuration, transition participants, and archival live inside the Project Workspace"
              />
              <div className="grid gap-3 sm:grid-cols-3 text-[13px]">
                <div className="rounded-xl border border-line p-3">
                  <p className="text-xs text-muted">Status</p>
                  <p className="mt-1 font-semibold text-navy capitalize">{activeProject.status}</p>
                </div>
                <div className="rounded-xl border border-line p-3">
                  <p className="text-xs text-muted">Visibility</p>
                  <p className="mt-1 font-semibold text-navy capitalize">{activeProject.visibility || 'private'}</p>
                </div>
                <div className="rounded-xl border border-line p-3">
                  <p className="text-xs text-muted">Your project role</p>
                  <p className="mt-1 font-semibold text-navy">{activeProject.my_project_role || 'Member'}</p>
                </div>
              </div>
              <div className="flex flex-wrap gap-2 pt-2">
                <Button onClick={() => router.push(`/projects/${activeProject.id}?tab=settings`)}>
                  Open Project Settings
                </Button>
                <Button variant="secondary" onClick={() => router.push(`/projects/${activeProject.id}/team`)}>
                  Project Team
                </Button>
              </div>
            </Card>
          )}
        </div>
      </div>

      {/* Confirm Logout All Devices */}
      <ConfirmDialog
        open={confirmLogoutAll}
        onClose={() => setConfirmLogoutAll(false)}
        title="Logout from all devices?"
        body="This immediately revokes every active refresh session across all browsers and devices, including your current session."
        confirmLabel="Logout everywhere"
        tone="danger"
        onConfirm={async () => {
          try {
            await api.auth.revokeAllSessions()
            setConfirmLogoutAll(false)
            await logout()
            router.push('/login')
          } catch (err) {
            addToast({
              type: 'error',
              title: 'Failed',
              message: err instanceof Error ? err.message : 'Could not revoke all sessions.',
            })
          }
        }}
      />

      {/* Confirm Disconnect Account */}
      <ConfirmDialog
        open={Boolean(disconnectTarget)}
        onClose={() => setDisconnectTarget(null)}
        title={`Disconnect ${disconnectTarget?.provider || 'account'}?`}
        body="Disconnecting stops personal OAuth access for future syncs. Existing project evidence, extracted knowledge, and approved handovers remain intact."
        confirmLabel={disconnecting ? 'Disconnecting…' : 'Disconnect account'}
        tone="danger"
        onConfirm={handleConfirmDisconnect}
      />

      {/* Confirm Archive Organisation */}
      <ConfirmDialog
        open={archiveOrgOpen}
        onClose={() => setArchiveOrgOpen(false)}
        title={`Archive ${activeOrg?.name}?`}
        body="Archiving marks this organisation as inactive. Immutable audit logs and historical handover records are retained."
        confirmLabel={archivingOrg ? 'Archiving…' : 'Archive organisation'}
        tone="danger"
        onConfirm={handleArchiveOrg}
      />

      {/* Account Deletion Request Modal */}
      <Modal
        open={delModalOpen}
        onClose={() => setDelModalOpen(false)}
        title="Request Account Deletion"
        subtitle="Requires explicit confirmation and ownership-transfer verification."
        footer={
          <>
            <Button variant="secondary" onClick={() => setDelModalOpen(false)}>
              Close
            </Button>
            <Button
              variant="danger"
              disabled={
                submittingDel ||
                delConfirmText.trim() !== 'DELETE' ||
                (user?.auth_method !== 'oauth' && !delPassword)
              }
              onClick={handleSubmitDeletion}
            >
              {submittingDel ? 'Checking…' : 'Submit deletion request'}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          {delResult && (
            <Callout
              tone={delResult.status === 'blocked' ? 'red' : 'amber'}
              icon={AlertTriangle}
              title={delResult.status === 'blocked' ? 'Action blocked by governance' : 'Deletion request recorded'}
            >
              <p>{delResult.message}</p>
              <p className="mt-1 text-xs">
                Organisations: {delResult.impact.active_organisations} · Sole owner:{' '}
                {delResult.impact.sole_owner_organisations} · Projects: {delResult.impact.active_projects} ·
                Handovers: {delResult.impact.active_handover_participations}
              </p>
            </Callout>
          )}
          <Field label='Type "DELETE" to confirm'>
            <Input
              value={delConfirmText}
              onChange={(e) => setDelConfirmText(e.target.value)}
              placeholder="DELETE"
            />
          </Field>
          {user?.auth_method !== 'oauth' && (
            <Field label="Current password">
              <PasswordInput value={delPassword} onChange={(e) => setDelPassword(e.target.value)} />
            </Field>
          )}
          <Field label="Reason (optional)">
            <Textarea
              rows={2}
              value={delReason}
              onChange={(e) => setDelReason(e.target.value)}
              placeholder="Optional reason for offboarding/account closure…"
            />
          </Field>
        </div>
      </Modal>
    </div>
  )
}
