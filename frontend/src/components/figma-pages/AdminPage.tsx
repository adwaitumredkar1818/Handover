'use client'

import React, { useState, useMemo, useContext, useEffect, Suspense, type ReactNode } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useLiveApp } from '../../context/LiveAppContext'
import { api } from '../../lib/api'
import {
  ScrollText as ScrollTextIcon,
  Bell,
  Building2,
  Camera,
  Check,
  CheckCheck,
  ClipboardCheck,
  Database,
  Download,
  Globe,
  Laptop,
  Lock,
  LogOut,
  Mail,
  MoreHorizontal,
  Pencil,
  Plug,
  Send,
  ShieldCheck,
  Smartphone,
  Sparkles,
  Trash2,
  UserPlus,
  Users,
  FolderKanban,
  AlertTriangle,
  Inbox,
  Filter,
  RefreshCw,
  Monitor,
} from 'lucide-react'
import {
  useFigmaStore,
  FigmaCtx,
  FigmaStoreProvider,
  auditLogs,
  ME,
  people,
  personById,
  SOURCE_META,
  type Notification,
  type Person,
  type SourceType,
} from '../../lib/figmaStore'
import {
  MetricBand,
  Avatar,
  Badge,
  Button,
  Callout,
  Card,
  CardHeader,
  ConfirmDialog,
  Dropdown,
  EmptyState,
  Field,
  Input,
  MenuItem,
  Modal,
  PageHeader,
  Pagination,
  PasswordInput,
  PersonCell,
  SearchInput,
  Select,
  StatusBadge,
  Switch,
  Table,
  Tabs,
  Td,
  Th,
  cn,
  Radio,
} from '../figma-ui'
import { SourceIcon } from '../figma-ui/brand'

/* 31. Workspace team */
interface TeamRow {
  id: string
  name: string
  email: string
  wsRole: 'Owner' | 'Admin' | 'Member'
  status: 'Active' | 'Invited'
  joinedAt?: string
  invitationId?: string
}

function mapOrgRoleToLabel(roleName?: string): 'Owner' | 'Admin' | 'Member' {
  if (roleName === 'org_owner') return 'Owner'
  if (roleName === 'org_admin') return 'Admin'
  return 'Member'
}

export function SettingsTeam() {
  const router = useRouter()
  const s = useFigmaStore()
  const { activeOrg, refreshNotifications, syncMemberNameUpdate, addToast } = useLiveApp()
  const [rows, setRows] = useState<TeamRow[]>([])
  const [loadingTeam, setLoadingTeam] = useState(false)
  const [q, setQ] = useState('')
  const [roleF, setRoleF] = useState('all')
  const [invite, setInvite] = useState(false)
  const [inv, setInv] = useState<{ email: string; role: 'Member' | 'Admin' }>({
    email: '',
    role: 'Member',
  })
  const [inviting, setInviting] = useState(false)
  const [inviteError, setInviteError] = useState<string | null>(null)
  const [remove, setRemove] = useState<TeamRow | null>(null)
  const [editMember, setEditMember] = useState<TeamRow | null>(null)
  const [editedMemberName, setEditedMemberName] = useState('')
  const [savingName, setSavingName] = useState(false)
  const [editNameError, setEditNameError] = useState<string | null>(null)

  const handleSaveMemberName = async () => {
    if (!activeOrg?.id || !editMember) return
    const trimmed = editedMemberName.trim()
    if (!trimmed) return
    setSavingName(true)
    setEditNameError(null)
    try {
      const updated = await api.organisations.updateMemberName(
        activeOrg.id,
        editMember.id,
        trimmed
      )
      const nextName = updated.full_name || trimmed
      setRows((prev) =>
        prev.map((row) =>
          row.id === editMember.id ? { ...row, name: nextName } : row
        )
      )
      syncMemberNameUpdate(editMember.id, nextName)
      addToast({
        type: 'success',
        title: 'Name updated',
        message: `Updated member name to "${nextName}".`,
      })
      setEditMember(null)
    } catch (err) {
      setEditNameError(
        err instanceof Error ? err.message : 'Failed to update member name.'
      )
    } finally {
      setSavingName(false)
    }
  }

  const loadTeam = React.useCallback(async () => {
    if (!activeOrg?.id) {
      setRows([])
      return
    }
    setLoadingTeam(true)
    try {
      const [membersRes, invitationsRes] = await Promise.allSettled([
        api.organisations.listMembers(activeOrg.id),
        api.organisations.listInvitations(activeOrg.id, { status: 'pending' }),
      ])
      const nextRows: TeamRow[] = []
      if (membersRes.status === 'fulfilled') {
        for (const m of membersRes.value) {
          nextRows.push({
            id: m.user_id || m.id,
            name: m.full_name || m.email.split('@')[0] || 'Member',
            email: m.email,
            wsRole: mapOrgRoleToLabel(m.role_name),
            status: 'Active',
            joinedAt: m.joined_at,
          })
        }
      }
      if (invitationsRes.status === 'fulfilled') {
        for (const item of invitationsRes.value.items) {
          nextRows.push({
            id: `inv-${item.id}`,
            invitationId: item.id,
            name:
              item.email
                .split('@')[0]
                ?.replace('.', ' ')
                .replace(/\b\w/g, (c) => c.toUpperCase()) || item.email,
            email: item.email,
            wsRole: mapOrgRoleToLabel(item.role_name),
            status: 'Invited',
            joinedAt: item.created_at,
          })
        }
      }
      setRows(nextRows)
    } finally {
      setLoadingTeam(false)
    }
  }, [activeOrg?.id])

  useEffect(() => {
    void loadTeam()
  }, [loadTeam])

  const shown = rows.filter(
    (p) =>
      (p.name + p.email).toLowerCase().includes(q.toLowerCase()) &&
      (roleF === 'all' || p.wsRole === roleF),
  )

  const handleSendInvite = async () => {
    if (!activeOrg?.id) {
      setInviteError('Please select or create an organisation workspace first.')
      return
    }
    setInviting(true)
    setInviteError(null)
    try {
      const res = await api.organisations.createInvitation(activeOrg.id, {
        email: inv.email.trim(),
        role_name: inv.role === 'Admin' ? 'org_admin' : 'org_member',
      })
      s.toast('Invitation sent', `Invited ${inv.email.trim()} to ${activeOrg.name}.`)
      if (res.development_invitation_token) {
        s.toast('Dev invite token ready', `/invitations/${res.development_invitation_token}`, 'info')
      }
      setInvite(false)
      setInv({ email: '', role: 'Member' })
      await loadTeam()
      void refreshNotifications()
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to send invitation'
      setInviteError(msg)
    } finally {
      setInviting(false)
    }
  }

  const handleRevokeOrRemove = async () => {
    if (!remove || !activeOrg?.id) return
    if (remove.status === 'Invited' && remove.invitationId) {
      try {
        await api.organisations.revokeInvitation(activeOrg.id, remove.invitationId)
        s.toast('Invitation revoked', remove.email, 'info')
        await loadTeam()
      } catch (err: unknown) {
        s.toast('Failed to revoke invitation', err instanceof Error ? err.message : undefined, 'error')
      }
    }
    setRemove(null)
  }

  const isJustYou = !loadingTeam && rows.length <= 1

  return (
    <>
      {isJustYou ? (
        <>
          <PageHeader title="Team Management" />
          <Card>
            <EmptyState
              icon={Users}
              title="Just you so far"
              body="Invite teammates to collaborate on projects and handovers."
              action={
                <Button
                  icon={UserPlus}
                  onClick={() => {
                    setInviteError(null)
                    setInvite(true)
                  }}
                >
                  Invite members
                </Button>
              }
            />
          </Card>
        </>
      ) : (
        <>
          <PageHeader
            title="Team Management"
            subtitle="Workspace members and roles. Project roles are managed inside each project."
            actions={
              <Button
                icon={UserPlus}
                onClick={() => {
                  setInviteError(null)
                  setInvite(true)
                }}
              >
                Invite members
              </Button>
            }
          />
          <MetricBand
            className="mb-5"
            items={[
              { label: 'Members', value: rows.filter((p) => p.status === 'Active').length },
              {
                label: 'Pending invitations',
                value: rows.filter((p) => p.status === 'Invited').length,
                tone: 'amber',
              },
              {
                label: 'Admins & owners',
                value: rows.filter((p) => p.wsRole !== 'Member').length,
                tone: 'indigo',
              },
              {
                label: 'Workspace',
                value: activeOrg?.name || 'Active',
                tone: 'gray',
              },
            ]}
          />
          <Card className="overflow-hidden">
            <div className="flex flex-col gap-2 border-b border-line p-3 sm:flex-row">
              <SearchInput
                placeholder="Search members"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                className="sm:w-72"
              />
              <Select
                value={roleF}
                onChange={(e) => setRoleF(e.target.value)}
                className="sm:w-40"
              >
                <option value="all">All roles</option>
                <option>Owner</option>
                <option>Admin</option>
                <option>Member</option>
              </Select>
            </div>
            <Table>
              <thead>
                <tr>
                  <Th>Member</Th>
                  <Th>Workspace role</Th>
                  <Th>Status</Th>
                  <Th>Joined / Invited</Th>
                  <Th className="w-10" />
                </tr>
              </thead>
              <tbody>
                {shown.map((p) => (
                  <tr key={p.id} className="hover:bg-slate-50/50">
                    <Td>
                      <div className="min-w-0">
                        <p className="text-[13px] font-medium text-navy truncate">{p.name}</p>
                        <p className="text-[11.5px] text-muted truncate">{p.email}</p>
                      </div>
                    </Td>
                    <Td>
                      <Badge tone={p.wsRole === 'Owner' ? 'navy' : p.wsRole === 'Admin' ? 'blue' : 'gray'}>
                        {p.wsRole}
                      </Badge>
                    </Td>
                    <Td>
                      <StatusBadge status={p.status} />
                    </Td>
                    <Td className="text-xs text-muted">
                      {p.joinedAt ? new Date(p.joinedAt).toLocaleDateString() : '—'}
                    </Td>
                    <Td>
                      {(p.status === 'Active' || p.wsRole !== 'Owner') && (
                        <Dropdown
                          trigger={() => (
                            <button
                              type="button"
                              aria-label={`Actions for ${p.name}`}
                              className="flex size-7 items-center justify-center rounded-lg text-muted hover:bg-slate-100"
                            >
                              <MoreHorizontal className="size-4" />
                            </button>
                          )}
                        >
                          {(close) => (
                            <>
                              {p.status === 'Active' && (
                                <MenuItem
                                  icon={Pencil}
                                  onClick={() => {
                                    close()
                                    setEditMember(p)
                                    setEditedMemberName(p.name)
                                    setEditNameError(null)
                                  }}
                                >
                                  Edit name
                                </MenuItem>
                              )}
                              <MenuItem
                                icon={FolderKanban}
                                onClick={() => {
                                  close()
                                  router.push('/projects')
                                }}
                              >
                                View projects
                              </MenuItem>
                              {p.status === 'Invited' && p.wsRole !== 'Owner' && (
                                <MenuItem
                                  icon={Trash2}
                                  danger
                                  onClick={() => {
                                    close()
                                    setRemove(p)
                                  }}
                                >
                                  Revoke invitation
                                </MenuItem>
                              )}
                            </>
                          )}
                        </Dropdown>
                      )}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </Card>
        </>
      )}
      <Modal
        open={invite}
        onClose={() => {
          setInvite(false)
          setInviteError(null)
        }}
        title="Invite to workspace"
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => {
                setInvite(false)
                setInviteError(null)
              }}
            >
              Cancel
            </Button>
            <Button
              icon={Send}
              disabled={inviting || !/^\S+@\S+\.\S+$/.test(inv.email)}
              onClick={() => void handleSendInvite()}
            >
              {inviting ? 'Sending...' : 'Send invitation'}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          {inviteError && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-bad">
              {inviteError}
            </div>
          )}
          <Field label="Email address">
            <Input
              value={inv.email}
              onChange={(e) => setInv({ ...inv, email: e.target.value })}
              placeholder="name@company.com"
            />
          </Field>
          <div>
            <p className="mb-2 text-[13px] font-medium text-navy">Workspace role</p>
            <div className="space-y-3">
              <Radio
                checked={inv.role === 'Member'}
                onChange={() => setInv({ ...inv, role: 'Member' })}
                label="Member"
                description="Access projects they're added to."
              />
              <Radio
                checked={inv.role === 'Admin'}
                onChange={() => setInv({ ...inv, role: 'Admin' })}
                label="Admin"
                description="Manage members, integrations and workspace settings."
              />
            </div>
          </div>
        </div>
      </Modal>
      <Modal
        open={Boolean(editMember)}
        onClose={() => {
          setEditMember(null)
          setEditNameError(null)
        }}
        title="Edit member name"
        subtitle={editMember?.email}
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => {
                setEditMember(null)
                setEditNameError(null)
              }}
              disabled={savingName}
            >
              Cancel
            </Button>
            <Button
              disabled={savingName || !editedMemberName.trim()}
              onClick={() => void handleSaveMemberName()}
            >
              {savingName ? 'Saving...' : 'Save name'}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          {editNameError && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-bad">
              {editNameError}
            </div>
          )}
          <Field label="Full name" required>
            <Input
              value={editedMemberName}
              onChange={(e) => setEditedMemberName(e.target.value)}
              placeholder="Enter member full name"
              autoFocus
            />
          </Field>
        </div>
      </Modal>
      <ConfirmDialog
        open={!!remove}
        onClose={() => setRemove(null)}
        tone="danger"
        title="Revoke invitation?"
        confirmLabel="Revoke"
        body={
          remove && (
            <>
              The pending invitation for <strong>{remove.email}</strong> will be revoked and the
              invite link will no longer work.
            </>
          )
        }
        onConfirm={() => void handleRevokeOrRemove()}
      />
    </>
  )
}

/* 32. Notifications */
const N_META: Record<
  Notification['type'],
  { icon: typeof Bell; label: string; tone: string }
> = {
  invitation: { icon: Inbox, label: 'Handover invitations', tone: 'bg-blue-50 text-brand' },
  review: { icon: ClipboardCheck, label: 'Review requests', tone: 'bg-amber-50 text-warn' },
  approval: { icon: ShieldCheck, label: 'Approvals', tone: 'bg-teal-50 text-ok' },
  ingestion: { icon: Database, label: 'Ingestion', tone: 'bg-indigo-50 text-indigo-500' },
  integration: { icon: Plug, label: 'Integration failures', tone: 'bg-red-50 text-bad' },
  project: { icon: FolderKanban, label: 'Project updates', tone: 'bg-slate-100 text-slate-600' },
}

function groupForDate(isoDate: string): 'Today' | 'Yesterday' | 'Earlier' {
  const d = new Date(isoDate)
  if (Number.isNaN(d.getTime())) return 'Earlier'
  const now = new Date()
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  const startOfYesterday = startOfToday - 86_400_000
  const ts = d.getTime()
  if (ts >= startOfToday) return 'Today'
  if (ts >= startOfYesterday) return 'Yesterday'
  return 'Earlier'
}

function formatNotifTime(isoDate: string): string {
  const d = new Date(isoDate)
  if (Number.isNaN(d.getTime())) return isoDate
  return d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function Notifications() {
  const router = useRouter()
  const {
    notifications,
    unreadNotificationCount,
    markNotificationRead,
    markAllNotificationsRead,
  } = useLiveApp()
  const [type, setType] = useState<'all' | Notification['type']>('all')
  const [unreadOnly, setUnreadOnly] = useState(false)

  const list = notifications.filter(
    (n) => (type === 'all' || n.type === type) && (!unreadOnly || !n.is_read),
  )
  const groups = (['Today', 'Yesterday', 'Earlier'] as const)
    .map((g) => ({ g, items: list.filter((n) => groupForDate(n.created_at) === g) }))
    .filter((x) => x.items.length)
  const unread = unreadNotificationCount

  return (
    <>
      <PageHeader
        title="Notifications"
        subtitle={`${unread} unread`}
        actions={
          <>
            <Button
              variant="secondary"
              icon={CheckCheck}
              disabled={!unread}
              onClick={() => void markAllNotificationsRead()}
            >
              Mark all as read
            </Button>
            <Button
              variant="ghost"
              onClick={() => router.push('/settings/profile?tab=preferences')}
            >
              Preferences
            </Button>
          </>
        }
      />
      <div className="grid gap-5 lg:grid-cols-[240px_1fr]">
        <div className="space-y-3">
          <nav className="scrollbar-thin flex gap-1 overflow-x-auto lg:flex-col">
            {(['all', ...Object.keys(N_META)] as ('all' | Notification['type'])[]).map(
              (t) => {
                const n =
                  t === 'all'
                    ? notifications.filter((x) => !x.is_read).length
                    : notifications.filter((x) => x.type === t && !x.is_read).length
                const M = t === 'all' ? null : N_META[t]
                return (
                  <button
                    key={t}
                    onClick={() => setType(t)}
                    className={cn(
                      'flex shrink-0 items-center gap-2.5 rounded-lg px-3 py-2 text-left text-[13px] font-medium transition',
                      type === t
                        ? 'bg-white text-navy shadow-card'
                        : 'text-muted hover:bg-white/60',
                    )}
                  >
                    {M ? <M.icon className="size-4" /> : <Bell className="size-4" />}
                    <span className="flex-1">{M ? M.label : 'All notifications'}</span>
                    {!!n && (
                      <span className="rounded-full bg-brand px-1.5 text-[11px] font-semibold text-white">
                        {n}
                      </span>
                    )}
                  </button>
                )
              },
            )}
          </nav>
          <label className="flex items-center justify-between rounded-lg bg-white px-3 py-2.5 text-[13px] text-navy shadow-card">
            Unread only
            <Switch checked={unreadOnly} onChange={setUnreadOnly} />
          </label>
        </div>
        <Card className="overflow-hidden">
          {!groups.length ? (
            <EmptyState
              icon={Bell}
              title="You're all caught up"
              body="New review requests, approvals and sync issues will appear here."
            />
          ) : (
            groups.map(({ g, items }) => (
              <div key={g}>
                <p className="border-b border-line bg-slate-50/70 px-5 py-2 text-xs font-semibold text-muted">
                  {g}
                </p>
                <ul className="divide-y divide-line">
                  {items.map((n) => {
                    const nType = (n.type || (n as any).notification_type || 'project') as keyof typeof N_META
                    const M = N_META[nType] || N_META.project
                    return (
                      <li
                        key={n.id}
                        className={cn(
                          'group flex gap-3.5 px-5 py-4 transition hover:bg-slate-50',
                          !n.is_read && 'bg-tint/30',
                        )}
                      >
                        <span
                          className={cn(
                            'flex size-9 shrink-0 items-center justify-center rounded-xl',
                            M.tone,
                          )}
                        >
                          <M.icon className="size-4" />
                        </span>
                        <button
                          className="min-w-0 flex-1 text-left"
                          onClick={() => {
                            if (!n.is_read) {
                              void markNotificationRead(n.id, true)
                            }
                            if (n.link) router.push(n.link)
                          }}
                        >
                          <p className="flex items-center gap-2 text-[13.5px] font-medium text-navy">
                            {n.title}
                            {!n.is_read && <span className="size-2 rounded-full bg-brand" />}
                          </p>
                          <p className="mt-0.5 text-[13px] text-muted">{n.body}</p>
                          <p className="mt-1 text-[11px] text-slate-400">
                            {formatNotifTime(n.created_at)} · {M.label}
                          </p>
                        </button>
                        <div className="flex shrink-0 flex-col items-end gap-2">
                          {n.type === 'integration' && (
                            <Button
                              size="sm"
                              variant="danger"
                              onClick={() => n.link && router.push(n.link)}
                            >
                              Reconnect
                            </Button>
                          )}
                          {n.type === 'review' && (
                            <Button
                              size="sm"
                              onClick={() => n.link && router.push(n.link)}
                            >
                              Review
                            </Button>
                          )}
                          {n.type === 'invitation' && (
                            <Button
                              size="sm"
                              onClick={() => n.link && router.push(n.link)}
                            >
                              Open
                            </Button>
                          )}
                          <button
                            onClick={() => void markNotificationRead(n.id, !n.is_read)}
                            className="text-[11px] font-medium text-muted opacity-0 transition group-hover:opacity-100 hover:text-brand"
                          >
                            {n.is_read ? 'Mark unread' : 'Mark read'}
                          </button>
                        </div>
                      </li>
                    )
                  })}
                </ul>
              </div>
            ))
          )}
        </Card>
      </div>
    </>
  )
}

/* 33. Audit logs */
export function AuditLogs() {
  const s = useFigmaStore()
  const [q, setQ] = useState('')
  const [type, setType] = useState('all')
  const [user, setUser] = useState('all')
  const [proj, setProj] = useState('all')
  const [page, setPage] = useState(1)

  const list = auditLogs.filter(
    (a) =>
      (a.action + a.resource).toLowerCase().includes(q.toLowerCase()) &&
      (type === 'all' || a.type === type) &&
      (user === 'all' || a.userId === user) &&
      (proj === 'all' || a.project === proj),
  )
  const per = 10
  const typeTone: Record<string, 'blue' | 'green' | 'amber' | 'red' | 'gray' | 'indigo'> = {
    Access: 'gray',
    Handover: 'blue',
    Integration: 'amber',
    Verification: 'green',
    Membership: 'indigo',
    Settings: 'gray',
  }

  return (
    <>
      <PageHeader
        title="Audit Logs"
        subtitle="Immutable record of access, verification, publication and configuration changes. Retained for 24 months."
        actions={
          <Button
            variant="secondary"
            icon={Download}
            onClick={() =>
              s.toast(
                'Export started',
                'CSV will be emailed to you within a few minutes.',
                'info',
              )
            }
          >
            Export CSV
          </Button>
        }
      />
      <Card className="overflow-hidden">
        <div className="flex flex-col gap-2 border-b border-line p-3 lg:flex-row">
          <SearchInput
            placeholder="Search action or resource"
            value={q}
            onChange={(e) => {
              setQ(e.target.value)
              setPage(1)
            }}
            className="lg:w-72"
          />
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:flex">
            <Select
              value={type}
              onChange={(e) => setType(e.target.value)}
              className="lg:w-40"
            >
              <option value="all">All activity</option>
              {['Access', 'Handover', 'Integration', 'Verification', 'Membership', 'Settings'].map(
                (t) => (
                  <option key={t}>{t}</option>
                ),
              )}
            </Select>
            <Select
              value={user}
              onChange={(e) => setUser(e.target.value)}
              className="lg:w-40"
            >
              <option value="all">All users</option>
              <option value="system">System</option>
              {people.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </Select>
            <Select
              value={proj}
              onChange={(e) => setProj(e.target.value)}
              className="lg:w-44"
            >
              <option value="all">All projects</option>
              {Array.from(new Set(auditLogs.map((a) => a.project))).map((p) => (
                <option key={p}>{p}</option>
              ))}
            </Select>
            <Select className="lg:w-36">
              <option>Last 30 days</option>
              <option>Last 7 days</option>
              <option>Last 90 days</option>
            </Select>
          </div>
        </div>
        {!list.length ? (
          <EmptyState
            icon={Filter}
            title="No matching events"
            body="Try another filter or search term."
          />
        ) : (
          <>
            <Table>
              <thead>
                <tr>
                  <Th>Timestamp</Th>
                  <Th>User</Th>
                  <Th>Action</Th>
                  <Th>Resource</Th>
                  <Th>Project</Th>
                  <Th>Type</Th>
                </tr>
              </thead>
              <tbody>
                {list.slice((page - 1) * per, page * per).map((a) => (
                  <tr key={a.id} className="hover:bg-slate-50/50">
                    <Td className="whitespace-nowrap font-mono text-xs text-muted">
                      {a.time}
                    </Td>
                    <Td>
                      {a.userId === 'system' ? (
                        <span className="flex items-center gap-2 text-[13px]">
                          <span className="flex size-6 items-center justify-center rounded-full bg-slate-100 text-[9px] font-bold text-slate-500">
                            SYS
                          </span>
                          System
                        </span>
                      ) : (
                        <span className="flex items-center gap-2 whitespace-nowrap text-[13px]">
                          <Avatar id={a.userId} size={24} />
                          {personById(a.userId)?.name ?? 'User'}
                        </span>
                      )}
                    </Td>
                    <Td className="text-[13px] font-medium text-navy">{a.action}</Td>
                    <Td className="text-[13px] text-muted">{a.resource}</Td>
                    <Td className="whitespace-nowrap text-[13px]">{a.project}</Td>
                    <Td>
                      <Badge tone={typeTone[a.type]}>{a.type}</Badge>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
            <Pagination
              page={page}
              pages={Math.max(1, Math.ceil(list.length / per))}
              onChange={setPage}
              total={list.length}
            />
          </>
        )}
      </Card>
    </>
  )
}

/* 34. Settings */
const S_TABS = [
  { id: 'general', label: 'General' },
  { id: 'workspace', label: 'Workspace' },
  { id: 'ai', label: 'AI configuration' },
  { id: 'retention', label: 'Data retention' },
  { id: 'privacy', label: 'Privacy' },
  { id: 'permissions', label: 'Permissions' },
  { id: 'integrations', label: 'Integrations' },
] as const

type STab = (typeof S_TABS)[number]['id']

function Row({
  title,
  desc,
  children,
}: {
  title: string
  desc?: string
  children: React.ReactNode
}) {
  return (
    <div className="flex flex-col gap-3 border-b border-line py-4 last:border-0 sm:flex-row sm:items-center sm:justify-between">
      <div className="max-w-md">
        <p className="text-[13.5px] font-medium text-navy">{title}</p>
        {desc && <p className="mt-0.5 text-xs text-muted">{desc}</p>}
      </div>
      <div className="sm:min-w-[220px] sm:text-right">{children}</div>
    </div>
  )
}

export function Settings() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const s = useFigmaStore()
  const activeTabParam = searchParams ? searchParams.get('tab') : null
  const [tab, setTab] = useState<STab>(
    (activeTabParam as STab) || 'general',
  )

  const [cfg, setCfg] = useState({
    lang: 'English (UK)',
    tz: 'Europe/London',
    date: 'DD MMM YYYY',
    wsName: 'Northwind Labs',
    domain: 'northwind.io',
    autoJoin: true,
    threshold: 70,
    requireVerify: true,
    aiModel: 'Handover Reasoning (default)',
    autoGaps: true,
    conflictDetect: true,
    retention: '24',
    evidenceRetention: '12',
    deleteOnDisconnect: false,
    piiRedact: true,
    excludeDMs: true,
    training: false,
    sso: true,
    mfa: true,
    guestAccess: false,
    exportAllowed: true,
  })

  const [dirty, setDirty] = useState(false)
  const upd = <K extends keyof typeof cfg>(k: K, v: (typeof cfg)[K]) => {
    setCfg((prev) => ({ ...prev, [k]: v }))
    setDirty(true)
  }

  const save = () => {
    setDirty(false)
    s.toast('Settings saved', 'Changes are recorded in the audit log.')
  }

  const allSources: SourceType[] = ['github', 'jira', 'slack', 'docs', 'confluence', 'gdrive']

  const handleTabChange = (t: string) => {
    setTab(t as STab)
    router.push(`/settings?tab=${t}`)
  }

  return (
    <>
      <PageHeader
        title="Settings"
        subtitle="Workspace-wide configuration. Requires Owner or Admin role."
        actions={
          dirty ? (
            <>
              <Button variant="ghost" onClick={() => setDirty(false)}>
                Discard
              </Button>
              <Button icon={Check} onClick={save}>
                Save changes
              </Button>
            </>
          ) : (
            <>
              <Button
                variant="secondary"
                icon={Users}
                onClick={() => router.push('/settings/team')}
              >
                Team management
              </Button>
              <Button
                variant="secondary"
                icon={ScrollTextIcon}
                onClick={() => router.push('/settings/audit-logs')}
              >
                Audit logs
              </Button>
            </>
          )
        }
      />
      <Tabs
        className="mb-5"
        tabs={S_TABS.map((t) => ({ id: t.id, label: t.label }))}
        value={tab}
        onChange={handleTabChange}
      />
      {tab === 'general' && (
        <Card className="px-5 py-1">
          <Row title="Language">
            <Select value={cfg.lang} onChange={(e) => upd('lang', e.target.value)}>
              <option>English (UK)</option>
              <option>English (US)</option>
              <option>Deutsch</option>
            </Select>
          </Row>
          <Row title="Time zone" desc="Used for timelines and reports">
            <Select value={cfg.tz} onChange={(e) => upd('tz', e.target.value)}>
              <option>Europe/London</option>
              <option>Europe/Berlin</option>
              <option>America/New_York</option>
            </Select>
          </Row>
          <Row title="Date format">
            <Select value={cfg.date} onChange={(e) => upd('date', e.target.value)}>
              <option>DD MMM YYYY</option>
              <option>MM/DD/YYYY</option>
              <option>YYYY-MM-DD</option>
            </Select>
          </Row>
        </Card>
      )}
      {tab === 'workspace' && (
        <Card className="px-5 py-1">
          <Row title="Workspace name">
            <Input
              value={cfg.wsName}
              onChange={(e) => upd('wsName', e.target.value)}
            />
          </Row>
          <Row title="Workspace logo">
            <Button
              variant="secondary"
              size="sm"
              icon={Camera}
              onClick={() => s.toast('Logo uploaded')}
            >
              Upload
            </Button>
          </Row>
          <Row
            title="Verified domain"
            desc="People with this email domain can request to join"
          >
            <Input
              value={cfg.domain}
              onChange={(e) => upd('domain', e.target.value)}
            />
          </Row>
          <Row
            title="Auto-approve domain members"
            desc="Skip admin approval for verified-domain sign-ups"
          >
            <Switch
              checked={cfg.autoJoin}
              onChange={(v) => upd('autoJoin', v)}
            />
          </Row>
          <Row
            title="Delete workspace"
            desc="Permanently delete all projects, evidence and handovers"
          >
            <Button
              variant="danger"
              size="sm"
              icon={Trash2}
              onClick={() =>
                s.toast(
                  'Deletion requires Owner confirmation by email',
                  undefined,
                  'error',
                )
              }
            >
              Delete workspace
            </Button>
          </Row>
        </Card>
      )}
      {tab === 'ai' && (
        <div className="space-y-5">
          <Callout icon={Sparkles} title="AI never replaces human verification">
            These settings control how findings are generated and surfaced. Publication
            always requires a person to approve.
          </Callout>
          <Card className="px-5 py-1">
            <Row title="Reconstruction model">
              <Select
                value={cfg.aiModel}
                onChange={(e) => upd('aiModel', e.target.value)}
              >
                <option>Handover Reasoning (default)</option>
                <option>Handover Reasoning · EU data residency</option>
              </Select>
            </Row>
            <Row
              title="Minimum confidence to show findings"
              desc={`Findings below ${cfg.threshold}% are hidden from reports and only shown in the review queue`}
            >
              <div className="flex items-center gap-3">
                <input
                  type="range"
                  min={40}
                  max={95}
                  step={5}
                  value={cfg.threshold}
                  onChange={(e) => upd('threshold', +e.target.value)}
                  className="flex-1 accent-[#315FBA]"
                />
                <span className="w-10 text-sm font-semibold text-navy">
                  {cfg.threshold}%
                </span>
              </div>
            </Row>
            <Row
              title="Require verification before publishing"
              desc="Unverified findings block publication unless explicitly accepted"
            >
              <Switch
                checked={cfg.requireVerify}
                onChange={(v) => upd('requireVerify', v)}
              />
            </Row>
            <Row title="Automatic knowledge-gap detection">
              <Switch
                checked={cfg.autoGaps}
                onChange={(v) => upd('autoGaps', v)}
              />
            </Row>
            <Row title="Conflicting evidence detection">
              <Switch
                checked={cfg.conflictDetect}
                onChange={(v) => upd('conflictDetect', v)}
              />
            </Row>
          </Card>
        </div>
      )}
      {tab === 'retention' && (
        <Card className="px-5 py-1">
          <Row
            title="Handover reports"
            desc="Published reports and verification history"
          >
            <Select
              value={cfg.retention}
              onChange={(e) => upd('retention', e.target.value)}
            >
              <option value="12">12 months</option>
              <option value="24">24 months</option>
              <option value="60">5 years</option>
              <option value="0">Forever</option>
            </Select>
          </Row>
          <Row
            title="Raw evidence"
            desc="Ingested source content (commits, messages, files)"
          >
            <Select
              value={cfg.evidenceRetention}
              onChange={(e) => upd('evidenceRetention', e.target.value)}
            >
              <option value="6">6 months</option>
              <option value="12">12 months</option>
              <option value="24">24 months</option>
            </Select>
          </Row>
          <Row title="Delete evidence when a source is disconnected">
            <Switch
              checked={cfg.deleteOnDisconnect}
              onChange={(v) => upd('deleteOnDisconnect', v)}
            />
          </Row>
          <Row title="Export all workspace data">
            <Button
              variant="secondary"
              size="sm"
              icon={Download}
              onClick={() =>
                s.toast(
                  'Export requested',
                  'You will receive a download link by email.',
                  'info',
                )
              }
            >
              Request export
            </Button>
          </Row>
        </Card>
      )}
      {tab === 'privacy' && (
        <Card className="px-5 py-1">
          <Row
            title="Redact personal data"
            desc="Mask emails, phone numbers and credentials found in evidence"
          >
            <Switch
              checked={cfg.piiRedact}
              onChange={(v) => upd('piiRedact', v)}
            />
          </Row>
          <Row
            title="Exclude private and direct messages"
            desc="Only public channels selected by managers are ingested"
          >
            <Switch
              checked={cfg.excludeDMs}
              onChange={(v) => upd('excludeDMs', v)}
            />
          </Row>
          <Row
            title="Allow use of data to improve models"
            desc="Off by default. Your data is never used for training unless enabled."
          >
            <Switch
              checked={cfg.training}
              onChange={(v) => upd('training', v)}
            />
          </Row>
          <Row title="Data processing agreement">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => s.toast('DPA downloaded')}
            >
              Download DPA
            </Button>
          </Row>
        </Card>
      )}
      {tab === 'permissions' && (
        <div className="space-y-5">
          <Card className="px-5 py-1">
            <Row
              title="Enforce SSO"
              desc="Members must sign in with Google Workspace"
            >
              <Switch checked={cfg.sso} onChange={(v) => upd('sso', v)} />
            </Row>
            <Row title="Require two-factor authentication">
              <Switch checked={cfg.mfa} onChange={(v) => upd('mfa', v)} />
            </Row>
            <Row
              title="Allow guest recipients"
              desc="Publish handovers to people outside the workspace"
            >
              <Switch
                checked={cfg.guestAccess}
                onChange={(v) => upd('guestAccess', v)}
              />
            </Row>
            <Row title="Allow report export & download">
              <Switch
                checked={cfg.exportAllowed}
                onChange={(v) => upd('exportAllowed', v)}
              />
            </Row>
          </Card>
          <Card className="overflow-hidden">
            <CardHeader
              title="Workspace roles"
              subtitle="Project roles (Manager / Outgoing / Incoming) are set per project"
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
                  ['Manage billing & delete workspace', 1, 0, 0],
                  ['Manage members & workspace roles', 1, 1, 0],
                  ['Configure AI, retention & privacy', 1, 1, 0],
                  ['View audit logs', 1, 1, 0],
                  ['Create projects', 1, 1, 1],
                  ['Access projects they belong to', 1, 1, 1],
                ].map(([l, ...v]) => (
                  <tr key={l as string}>
                    <Td className="text-[13px]">{l}</Td>
                    {v.map((x, i) => (
                      <Td key={i}>
                        {x ? (
                          <Check className="size-4 text-ok" />
                        ) : (
                          <span className="text-slate-300">—</span>
                        )}
                      </Td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </Table>
            <p className="flex items-center gap-1.5 px-5 py-3 text-xs text-muted">
              <Lock className="size-3" />
              Permissions are enforced by the backend on every request.
            </p>
          </Card>
        </div>
      )}
      {tab === 'integrations' && (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {allSources.map((t) => {
            const n = s.sources.filter(
              (x) => x.type === t && x.status !== 'disconnected',
            )
            const err = s.sources.some(
              (x) => x.type === t && x.status === 'error',
            )
            return (
              <Card key={t} interactive className="p-5">
                <div className="flex items-start justify-between">
                  <SourceIcon type={t} size={40} />
                  {err ? (
                    <StatusBadge status="error" />
                  ) : n.length ? (
                    <Badge tone="green" dot>
                      Enabled
                    </Badge>
                  ) : (
                    <Badge tone="gray" dot>
                      Available
                    </Badge>
                  )}
                </div>
                <p className="mt-3 text-[15px] font-semibold text-navy">
                  {SOURCE_META[t].label}
                </p>
                <p className="mt-1 text-[13px] text-muted">
                  {SOURCE_META[t].description}
                </p>
                <p className="mt-3 text-xs text-muted">
                  {n.length
                    ? `Used by ${n.length} project${n.length > 1 ? 's' : ''}`
                    : 'Not used by any project'}
                </p>
                <div className="mt-4 flex items-center justify-between border-t border-line pt-3">
                  <span className="text-[13px] text-navy">Allow in workspace</span>
                  <Switch
                    checked={t !== 'gdrive'}
                    onChange={() => s.toast('Integration policy updated')}
                  />
                </div>
              </Card>
            )
          })}
        </div>
      )}
    </>
  )
}

/* 35. Profile */
export function Profile() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const s = useFigmaStore()
  const me = personById(ME) ?? people[0]
  const initialTab =
    (searchParams?.get('tab') as
      | 'profile'
      | 'security'
      | 'accounts'
      | 'preferences') || 'profile'
  const [tab, setTab] = useState<'profile' | 'security' | 'accounts' | 'preferences'>(
    initialTab,
  )
  const [f, setF] = useState({
    name: me?.name ?? '',
    title: me?.title ?? '',
    email: me?.email ?? '',
    phone: '+44 20 7946 0321',
  })
  const [pw, setPw] = useState({ cur: '', next: '', confirm: '' })
  const [sessions, setSessions] = useState([
    {
      id: 1,
      device: 'MacBook Pro · Chrome',
      loc: 'London, UK',
      when: 'Current session',
      icon: Laptop,
    },
    {
      id: 2,
      device: 'iPhone 15 · Safari',
      loc: 'London, UK',
      when: '2 hours ago',
      icon: Smartphone,
    },
    {
      id: 3,
      device: 'Windows · Edge',
      loc: 'Manchester, UK',
      when: 'Jun 12',
      icon: Monitor,
    },
  ])
  const [prefs, setPrefs] = useState({
    emailReview: true,
    emailPublished: true,
    emailIngestion: true,
    digest: 'daily',
    density: 'comfortable',
  })
  const [savingPrefs, setSavingPrefs] = useState(false)

  useEffect(() => {
    let active = true
    api.notifications
      .getPreferences()
      .then((res) => {
        if (!active) return
        setPrefs((prev) => ({
          ...prev,
          emailReview: res.review_requests,
          emailPublished: res.approvals,
          emailIngestion: res.ingestion_updates,
          digest: res.email_digest_enabled ? 'daily' : 'off',
        }))
      })
      .catch(() => {
        // Ignore if unauthenticated
      })
    return () => {
      active = false
    }
  }, [])

  const pwErr =
    pw.next && pw.next.length < 8
      ? 'At least 8 characters'
      : pw.confirm && pw.confirm !== pw.next
      ? 'Passwords do not match'
      : ''

  return (
    <>
      <PageHeader
        title="Profile & Account"
        subtitle="Your personal information, security and preferences."
      />
      <Tabs
        className="mb-5"
        tabs={[
          { id: 'profile', label: 'Profile' },
          { id: 'security', label: 'Password & sessions' },
          { id: 'accounts', label: 'Connected accounts' },
          { id: 'preferences', label: 'Preferences' },
        ]}
        value={tab}
        onChange={(t) => setTab(t as typeof tab)}
      />
      {tab === 'profile' && (
        <Card className="p-5 sm:p-6">
          <div className="flex flex-col gap-5 border-b border-line pb-6 sm:flex-row sm:items-center">
            <div className="relative w-fit">
              <Avatar id={ME} size={80} />
              <button
                onClick={() => s.toast('Profile picture updated')}
                className="absolute -bottom-1 -right-1 flex size-8 items-center justify-center rounded-full border-2 border-white bg-brand text-white"
                aria-label="Change picture"
              >
                <Camera className="size-3.5" />
              </button>
            </div>
            <div>
              <p className="text-lg font-semibold text-navy">{f.name}</p>
              <p className="text-sm text-muted">
                {f.title} · Workspace {me?.wsRole ?? 'Member'}
              </p>
              <div className="mt-2 flex gap-2">
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => s.toast('Profile picture updated')}
                >
                  Upload new picture
                </Button>
                <Button size="sm" variant="ghost">
                  Remove
                </Button>
              </div>
            </div>
          </div>
          <div className="mt-6 grid gap-4 sm:grid-cols-2">
            <Field label="Full name">
              <Input
                value={f.name}
                onChange={(e) => setF({ ...f, name: e.target.value })}
              />
            </Field>
            <Field label="Job title">
              <Input
                value={f.title}
                onChange={(e) => setF({ ...f, title: e.target.value })}
              />
            </Field>
            <Field label="Email" hint="Changing email requires re-verification">
              <Input
                type="email"
                value={f.email}
                onChange={(e) => setF({ ...f, email: e.target.value })}
              />
            </Field>
            <Field label="Phone (optional)">
              <Input
                value={f.phone}
                onChange={(e) => setF({ ...f, phone: e.target.value })}
              />
            </Field>
          </div>
          <div className="mt-6 flex justify-end">
            <Button icon={Check} onClick={() => s.toast('Profile updated')}>
              Save profile
            </Button>
          </div>
        </Card>
      )}
      {tab === 'security' && (
        <div className="grid gap-5 lg:grid-cols-2">
          <Card className="p-5 sm:p-6">
            <p className="text-[15px] font-semibold text-navy">Change password</p>
            <div className="mt-4 space-y-4">
              <Field label="Current password">
                <PasswordInput
                  value={pw.cur}
                  onChange={(e) => setPw({ ...pw, cur: e.target.value })}
                />
              </Field>
              <Field
                label="New password"
                error={pw.next && pw.next.length < 8 ? pwErr : undefined}
              >
                <PasswordInput
                  value={pw.next}
                  onChange={(e) => setPw({ ...pw, next: e.target.value })}
                />
              </Field>
              <Field
                label="Confirm new password"
                error={
                  pw.confirm && pw.confirm !== pw.next
                    ? 'Passwords do not match'
                    : undefined
                }
              >
                <PasswordInput
                  value={pw.confirm}
                  onChange={(e) => setPw({ ...pw, confirm: e.target.value })}
                />
              </Field>
              <Button
                disabled={
                  !pw.cur || !pw.next || !!pwErr || pw.next !== pw.confirm
                }
                onClick={() => {
                  setPw({ cur: '', next: '', confirm: '' })
                  s.toast(
                    'Password updated',
                    'Other sessions will be asked to sign in again.',
                  )
                }}
              >
                Update password
              </Button>
            </div>
          </Card>
          <Card>
            <CardHeader
              title="Active sessions"
              subtitle="Devices signed in to your account"
              action={
                <Button
                  size="sm"
                  variant="ghost"
                  className="text-red-600"
                  onClick={() => {
                    setSessions(sessions.slice(0, 1))
                    s.toast('Signed out of other sessions', undefined, 'info')
                  }}
                >
                  Sign out others
                </Button>
              }
            />
            <ul className="space-y-2 px-5 pb-5">
              {sessions.map((x) => (
                <li
                  key={x.id}
                  className="flex items-center gap-3 rounded-xl border border-line p-3"
                >
                  <x.icon className="size-5 text-muted" />
                  <div className="flex-1">
                    <p className="text-[13px] font-medium text-navy">{x.device}</p>
                    <p className="text-xs text-muted">
                      {x.loc} · {x.when}
                    </p>
                  </div>
                  {x.id === 1 ? (
                    <Badge tone="green">This device</Badge>
                  ) : (
                    <Button
                      size="sm"
                      variant="ghost"
                      icon={LogOut}
                      onClick={() =>
                        setSessions(sessions.filter((y) => y.id !== x.id))
                      }
                    >
                      Revoke
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          </Card>
        </div>
      )}
      {tab === 'accounts' && (
        <Card className="divide-y divide-line">
          {[
            { t: 'github' as SourceType, acc: '@mayachen', on: true },
            { t: 'jira' as SourceType, acc: 'maya.chen@northwind.io', on: true },
            { t: 'slack' as SourceType, acc: '', on: false },
          ].map((a) => (
            <div key={a.t} className="flex items-center gap-4 p-5">
              <SourceIcon type={a.t} size={40} />
              <div className="flex-1">
                <p className="text-[14px] font-medium text-navy">
                  {SOURCE_META[a.t].label}
                </p>
                <p className="text-xs text-muted">
                  {a.on
                    ? `Connected as ${a.acc} · used to attribute your evidence`
                    : 'Link your account so your messages are attributed to you'}
                </p>
              </div>
              {a.on ? (
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() =>
                    s.toast(
                      `${SOURCE_META[a.t].label} disconnected`,
                      undefined,
                      'info',
                    )
                  }
                >
                  Disconnect
                </Button>
              ) : (
                <Button
                  size="sm"
                  onClick={() => s.toast(`${SOURCE_META[a.t].label} connected`)}
                >
                  Connect
                </Button>
              )}
            </div>
          ))}
          <div className="flex items-center gap-4 p-5">
            <span className="flex size-10 items-center justify-center rounded-[10px] border border-line">
              <Globe className="size-5 text-muted" />
            </span>
            <div className="flex-1">
              <p className="text-[14px] font-medium text-navy">Google</p>
              <p className="text-xs text-muted">
                Sign in with Google · {me?.email ?? ''}
              </p>
            </div>
            <Badge tone="green" icon={Check}>
              Connected
            </Badge>
          </div>
        </Card>
      )}
      {tab === 'preferences' && (
        <Card className="px-5 py-1">
          <Row title="Email me when I'm asked to review">
            <Switch
              checked={prefs.emailReview}
              onChange={(v) => setPrefs({ ...prefs, emailReview: v })}
            />
          </Row>
          <Row title="Email me when a handover is published to me">
            <Switch
              checked={prefs.emailPublished}
              onChange={(v) => setPrefs({ ...prefs, emailPublished: v })}
            />
          </Row>
          <Row title="Email me about ingestion results">
            <Switch
              checked={prefs.emailIngestion}
              onChange={(v) => setPrefs({ ...prefs, emailIngestion: v })}
            />
          </Row>
          <Row title="Activity digest">
            <Select
              value={prefs.digest}
              onChange={(e) => setPrefs({ ...prefs, digest: e.target.value })}
            >
              <option value="off">Off</option>
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
            </Select>
          </Row>
          <Row title="Default landing page">
            <Select defaultValue="dashboard">
              <option value="dashboard">Dashboard</option>
              <option>My Projects</option>
              <option>Received Handovers</option>
            </Select>
          </Row>
          <div className="flex justify-end py-4">
            <Button
              icon={Check}
              disabled={savingPrefs}
              onClick={async () => {
                setSavingPrefs(true)
                try {
                  await api.notifications.updatePreferences({
                    review_requests: prefs.emailReview,
                    approvals: prefs.emailPublished,
                    ingestion_updates: prefs.emailIngestion,
                    email_digest_enabled: prefs.digest !== 'off',
                  })
                  s.toast('Preferences saved')
                } catch {
                  s.toast('Failed to save preferences', undefined, 'error')
                } finally {
                  setSavingPrefs(false)
                }
              }}
            >
              {savingPrefs ? 'Saving...' : 'Save preferences'}
            </Button>
          </div>
        </Card>
      )}
    </>
  )
}

/* Master AdminPage component */
export type AdminPageView = 'team' | 'audit' | 'settings' | 'profile' | 'notifications'

export interface AdminPageProps {
  view?: AdminPageView
}

function AdminPageContent({ view = 'settings' }: AdminPageProps) {
  switch (view) {
    case 'team':
      return <SettingsTeam />
    case 'audit':
      return <AuditLogs />
    case 'notifications':
      return <Notifications />
    case 'profile':
      return <Profile />
    case 'settings':
    default:
      return <Settings />
  }
}

function EnsureFigmaStore({ children }: { children: ReactNode }) {
  const existing = useContext(FigmaCtx)
  if (existing) return <>{children}</>
  return <FigmaStoreProvider>{children}</FigmaStoreProvider>
}

export function AdminPage({ view = 'settings' }: AdminPageProps) {
  return (
    <EnsureFigmaStore>
      <Suspense
        fallback={
          <div className="flex h-64 items-center justify-center text-sm text-muted">
            Loading...
          </div>
        }
      >
        <AdminPageContent view={view} />
      </Suspense>
    </EnsureFigmaStore>
  )
}

export default AdminPage
