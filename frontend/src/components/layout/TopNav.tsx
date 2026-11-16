"use client";

import React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Menu,
  ChevronsLeft,
  ChevronsRight,
  Search,
  Bell,
  CircleHelp,
  ChevronDown,
  User,
  Settings,
  ShieldCheck,
  LogOut,
  Workflow,
  ArrowRight,
  Keyboard,
  LifeBuoy,
  BookOpen,
  CheckCircle2,
  AlertTriangle,
  Sparkles,
  Palette,
  HelpCircle,
  RefreshCw,
  Info,
} from "lucide-react";
import { Logo } from "../figma-ui/brand";
import {
  Avatar,
  Dropdown,
  IconButton,
  MenuItem,
  Tooltip,
  cn,
} from "../figma-ui/index";
import { Breadcrumbs } from "./Breadcrumbs";
import { useLiveApp } from "../../context/LiveAppContext";
import { ROLE_LABEL, type ProjectRole } from "../../lib/figmaStore";

function ContextChip() {
  const [mounted, setMounted] = React.useState(false);
  React.useEffect(() => {
    setMounted(true);
  }, []);

  const { activeProject, user, members } = useLiveApp();
  if (!mounted || !activeProject) return null;

  const currentMember = members.find(
    (m) => m.user_id === user?.id || m.user_email === user?.email
  );
  const currentRole = (
    currentMember?.transition_role === "departing_owner"
      ? "outgoing"
      : currentMember?.transition_role === "incoming_assignee"
      ? "incoming"
      : currentMember?.role_name?.toLowerCase() || "manager"
  ) as ProjectRole;

  const roleLabel =
    ROLE_LABEL[currentRole as keyof typeof ROLE_LABEL] || "Project Member";

  const projectCode =
    (activeProject as unknown as { settings?: { code?: string } })?.settings?.code ||
    activeProject.name
      ?.replace(/[^A-Za-z]/g, "")
      .slice(0, 3)
      .toUpperCase() ||
    "PRJ";

  const projectColor =
    (activeProject as unknown as { settings?: { color?: string } })?.settings?.color ||
    "#315FBA";

  const isOutgoing = currentRole === "outgoing";
  const isIncoming = currentRole === "incoming";

  const roleTextTone = isOutgoing
    ? "text-amber-700"
    : isIncoming
    ? "text-teal-700"
    : "text-brand";

  const roleBgTone = isOutgoing
    ? "bg-warn"
    : isIncoming
    ? "bg-ok"
    : "bg-brand";

  return (
    <Tooltip
      content={`Your active role in ${activeProject.name}: ${roleLabel}. It changes navigation, widgets and actions.`}
      side="bottom"
    >
      <span className="hidden items-center gap-2 rounded-full border border-line bg-white py-1 pl-1 pr-2.5 text-[12px] font-medium text-navy 2xl:flex shadow-2xs">
        <span
          className="flex size-5 items-center justify-center rounded-full text-[8.5px] font-bold text-white shadow-2xs"
          style={{ background: projectColor }}
        >
          {projectCode.slice(0, 2)}
        </span>
        <span className="truncate max-w-[120px] font-semibold text-navy">
          {activeProject.name.split(" ")[0]}
        </span>
        <span className="text-slate-300">·</span>
        <span className={cn("flex items-center gap-1 font-semibold", roleTextTone)}>
          <span className={cn("size-1.5 rounded-full shrink-0", roleBgTone)} />
          {roleLabel}
        </span>
      </span>
    </Tooltip>
  );
}

function ActiveJobsIndicator() {
  const { activeJobs } = useLiveApp();
  const [mounted, setMounted] = React.useState(false);
  React.useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted || !activeJobs || activeJobs.length === 0) return null;

  return (
    <Dropdown
      width="w-80"
      trigger={() => (
        <button
          type="button"
          className="flex items-center gap-1.5 rounded-full border border-sky-300 bg-sky-50 px-2.5 py-1 text-xs font-semibold text-sky-800 shadow-2xs hover:bg-sky-100 transition animate-pulse cursor-pointer mr-1"
        >
          <RefreshCw className="size-3.5 animate-spin text-sky-600" />
          <span>Syncing ({activeJobs.length})</span>
        </button>
      )}
    >
      {() => (
        <div className="p-3">
          <div className="flex items-center justify-between border-b border-line pb-2 mb-2">
            <span className="text-xs font-bold text-navy">Background Sync Tasks</span>
            <span className="text-[10.5px] font-medium text-sky-600">
              {activeJobs.length} in progress
            </span>
          </div>
          <div className="space-y-2.5 max-h-64 overflow-y-auto scrollbar-thin">
            {activeJobs.map((job) => (
              <div
                key={job.id}
                className="rounded-lg border border-line bg-slate-50/70 p-2.5 text-xs space-y-1.5"
              >
                <div className="flex items-center justify-between font-semibold text-navy">
                  <span className="capitalize text-[12px]">
                    {job.job_type.replace(/_/g, " ")}
                  </span>
                  <span className="text-[11px] font-mono font-bold text-sky-600">
                    {job.progress_percent}%
                  </span>
                </div>
                <div className="h-1.5 w-full rounded-full bg-slate-200 overflow-hidden">
                  <div
                    className="h-full bg-sky-500 rounded-full transition-all duration-300"
                    style={{ width: `${Math.max(8, job.progress_percent)}%` }}
                  />
                </div>
                {job.message && (
                  <p className="text-[11px] text-[#475569] leading-snug break-words">
                    {job.message}
                  </p>
                )}
                <div className="flex items-center justify-between text-[10px] text-muted pt-0.5">
                  <span className="capitalize">{job.status}</span>
                  {job.stage && <span className="font-mono">{job.stage}</span>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </Dropdown>
  );
}

function NotificationsMenu() {
  const router = useRouter();
  const {
    overview,
    notifications,
    unreadNotificationsCount,
    markNotificationRead,
    markAllNotificationsRead,
  } = useLiveApp();
  const [mounted, setMounted] = React.useState(false);
  React.useEffect(() => {
    setMounted(true);
  }, []);

  const attentionItems = overview?.attention_items || [];
  const totalCount = unreadNotificationsCount + attentionItems.length;

  return (
    <Dropdown
      width="w-[380px] max-w-[calc(100vw-24px)]"
      trigger={() => (
        <IconButton
          icon={Bell}
          label="Notifications"
          badge={totalCount > 0 ? totalCount : undefined}
        />
      )}
    >
      {(close) => (
        <div>
          <div className="flex items-center justify-between px-3.5 py-2.5 border-b border-line bg-slate-50/40">
            <div className="flex items-center gap-2">
              <p className="text-sm font-semibold text-navy">Notifications</p>
              {unreadNotificationsCount > 0 && (
                <span className="rounded-full bg-sky-100 px-2 py-0.5 text-[10.5px] font-bold text-sky-700">
                  {unreadNotificationsCount} unread
                </span>
              )}
            </div>
            {unreadNotificationsCount > 0 && (
              <button
                type="button"
                onClick={() => markAllNotificationsRead()}
                className="text-[11px] font-medium text-brand hover:underline cursor-pointer"
              >
                Mark all read
              </button>
            )}
          </div>
          <div className="max-h-80 overflow-y-auto divide-y divide-line/60 scrollbar-thin">
            {notifications.length === 0 && attentionItems.length === 0 ? (
              <div className="p-6 text-center text-xs text-muted">
                <CheckCircle2 className="size-6 text-ok mx-auto mb-1.5" />
                <p className="font-semibold text-navy">All caught up</p>
                <p className="mt-0.5 text-[11px]">
                  No active sync alerts or unread notifications.
                </p>
              </div>
            ) : (
              <>
                {notifications.map((n) => {
                  const isUnread = !n.is_read;
                  return (
                    <div
                      key={n.id}
                      onClick={() => {
                        if (isUnread) markNotificationRead(n.id);
                        if (n.notification_type?.includes("sync") || n.notification_type?.includes("evidence")) {
                          close();
                          router.push("/evidence");
                        }
                      }}
                      className={cn(
                        "flex gap-3 px-3.5 py-3 text-left transition-colors cursor-pointer hover:bg-slate-50/80",
                        isUnread ? "bg-sky-50/30" : "bg-white"
                      )}
                    >
                      <div className="mt-0.5 shrink-0">
                        {n.severity === "success" ? (
                          <CheckCircle2 className="size-4 text-emerald-600" />
                        ) : n.severity === "error" ? (
                          <AlertTriangle className="size-4 text-rose-600" />
                        ) : n.severity === "warning" ? (
                          <AlertTriangle className="size-4 text-amber-500" />
                        ) : (
                          <Info className="size-4 text-sky-600" />
                        )}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between gap-2">
                          <p className={cn("text-[12.5px] font-semibold text-navy leading-snug", isUnread && "font-bold")}>
                            {n.title}
                          </p>
                          {isUnread && (
                            <span className="size-2 rounded-full bg-sky-500 shrink-0" />
                          )}
                        </div>
                        <p className="text-[11px] text-[#4B5563] mt-0.5 leading-relaxed line-clamp-2">
                          {n.body}
                        </p>
                        <p className="text-[10px] text-muted mt-1">
                          {new Date(n.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                        </p>
                      </div>
                    </div>
                  );
                })}

                {attentionItems.map((item) => (
                  <button
                    key={item.id}
                    onClick={() => {
                      close();
                      router.push("/dashboard");
                    }}
                    className="flex w-full gap-2.5 px-3 py-2 text-left hover:bg-tint transition-colors cursor-pointer"
                  >
                    <AlertTriangle className="size-4 text-amber-500 shrink-0 mt-0.5" />
                    <div className="min-w-0 flex-1">
                      <p className="text-[13px] font-medium text-navy leading-snug">
                        {item.message}
                      </p>
                      <p className="text-[10.5px] text-muted mt-0.5">
                        Type: {item.type}
                      </p>
                    </div>
                  </button>
                ))}
              </>
            )}
          </div>
          <button
            onClick={() => {
              close();
              router.push("/evidence");
            }}
            className="flex w-full items-center justify-center gap-1 border-t border-line py-2 text-[12px] font-medium text-brand hover:underline cursor-pointer bg-slate-50/50"
          >
            Open Evidence Center <ArrowRight className="size-3.5" />
          </button>
        </div>
      )}
    </Dropdown>
  );
}

export function TopNav({
  collapsed,
  onToggleCollapse,
  onOpenSearch,
}: {
  collapsed: boolean;
  onToggleCollapse: () => void;
  onOpenSearch: () => void;
}) {
  const router = useRouter();
  const { user, logout, addToast, setIsMobileSidebarOpen } = useLiveApp();

  const [mounted, setMounted] = React.useState(false);
  React.useEffect(() => {
    setMounted(true);
  }, []);

  const userName =
    (mounted && (user?.full_name || user?.email?.split("@")[0])) || "User";
  const userEmail = (mounted && user?.email) || "";

  return (
    <header className="no-print flex h-[60px] shrink-0 items-center gap-2 border-b border-line/80 bg-white/85 px-3 backdrop-blur-xl sm:px-5 font-sans select-none z-30">
      {/* Mobile Menu Trigger */}
      <IconButton
        icon={Menu}
        label="Open menu"
        className="lg:hidden"
        onClick={() => setIsMobileSidebarOpen(true)}
      />

      {/* Desktop Sidebar Collapse Toggle */}
      <IconButton
        icon={collapsed ? ChevronsRight : ChevronsLeft}
        label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        className="hidden lg:inline-flex"
        onClick={onToggleCollapse}
      />

      {/* Mobile Logo */}
      <Link href="/dashboard" className="lg:hidden md:hidden">
        <Logo size={24} />
      </Link>

      {/* Dynamic Breadcrumbs */}
      <Breadcrumbs />

      {/* Right Controls */}
      <div className="ml-auto flex items-center gap-1">
        {/* Global Search Button (⌘K) */}
        <button
          type="button"
          onClick={onOpenSearch}
          className="mr-1 hidden h-9 w-60 items-center gap-2 rounded-[9px] border border-line bg-slate-50/80 px-3 text-[13px] text-slate-400 hover:border-slate-300 xl:flex cursor-pointer transition"
          title="Search (⌘K)"
        >
          <Search className="size-4 shrink-0 text-slate-400" />
          <span>Search everything</span>
          <kbd className="ml-auto rounded border border-line bg-white px-1.5 text-[10px] font-mono text-slate-500 shadow-2xs">
            ⌘K
          </kbd>
        </button>

        {/* Small Screen Search Icon */}
        <IconButton
          icon={Search}
          label="Search"
          className="xl:hidden"
          onClick={onOpenSearch}
        />

        {/* Project Role Context Chip */}
        <ContextChip />

        {/* Live / Prototype Data Badge */}
        <Tooltip
          content="Production environment connected with live evidence ingestion and PostgreSQL canonical storage."
          side="bottom"
        >
          <span className="mr-1 hidden rounded-full border border-dashed border-slate-300 px-2 py-0.5 text-[11px] font-medium text-slate-500 sm:inline">
            Production mode
          </span>
        </Tooltip>

        {/* Background Active Jobs Indicator */}
        <ActiveJobsIndicator />

        {/* Notifications Menu */}
        <NotificationsMenu />

        {/* Help & Support Menu */}
        <Dropdown
          trigger={() => (
            <IconButton
              icon={CircleHelp}
              label="Help & guides"
              className="hidden sm:inline-flex"
            />
          )}
        >
          {(close) => (
            <div>
              <MenuItem
                icon={BookOpen}
                onClick={() => {
                  close();
                  router.push("/flows");
                }}
              >
                Prototype flows
              </MenuItem>
              <MenuItem
                icon={Sparkles}
                onClick={() => {
                  close();
                  router.push("/brand");
                }}
              >
                3D Brand & Launch Studio
              </MenuItem>
              <MenuItem
                icon={Palette}
                onClick={() => {
                  close();
                  router.push("/design-system");
                }}
              >
                Design system
              </MenuItem>
              <MenuItem
                icon={Keyboard}
                onClick={() => {
                  close();
                  onOpenSearch();
                }}
                hint={<kbd className="text-[11px] font-mono text-slate-400">⌘K</kbd>}
              >
                Keyboard shortcuts
              </MenuItem>
              <div className="my-1 border-t border-line" />
              <MenuItem
                icon={LifeBuoy}
                onClick={() => {
                  close();
                  addToast({
                    type: "info",
                    title: "Support request logged",
                    message: "Engineering support has received your diagnostic request.",
                  });
                }}
              >
                Contact support
              </MenuItem>
            </div>
          )}
        </Dropdown>

        {/* User Account Dropdown */}
        <Dropdown
          width="w-60"
          trigger={() => (
            <button
              className="ml-1 flex items-center gap-1.5 rounded-full p-0.5 pr-1.5 hover:bg-tint transition cursor-pointer"
              aria-label="Account menu"
            >
              <Avatar name={userName} size={30} />
              <ChevronDown className="hidden size-3.5 text-slate-400 sm:block" />
            </button>
          )}
        >
          {(close) => (
            <div>
              <div className="flex items-center gap-2.5 px-3 py-2.5">
                <Avatar name={userName} size={34} />
                <div className="min-w-0">
                  <p
                    className="truncate text-sm font-semibold text-navy"
                    suppressHydrationWarning
                  >
                    {userName}
                  </p>
                  <p
                    className="truncate text-xs text-muted"
                    suppressHydrationWarning
                  >
                    {userEmail}
                  </p>
                </div>
              </div>
              <div className="my-1 border-t border-line" />
              <MenuItem
                icon={User}
                onClick={() => {
                  close();
                  router.push("/settings/profile");
                }}
              >
                Profile & account
              </MenuItem>
              <MenuItem
                icon={Settings}
                onClick={() => {
                  close();
                  router.push("/settings");
                }}
              >
                Settings
              </MenuItem>
              <MenuItem
                icon={ShieldCheck}
                onClick={() => {
                  close();
                  router.push("/settings/audit-logs");
                }}
              >
                Audit logs
              </MenuItem>
              <MenuItem
                icon={HelpCircle}
                onClick={() => {
                  close();
                  router.push("/flows");
                }}
              >
                Prototype flows
              </MenuItem>
              <div className="my-1 border-t border-line" />
              <MenuItem
                icon={LogOut}
                danger
                onClick={() => {
                  close();
                  logout();
                }}
              >
                Sign out
              </MenuItem>
            </div>
          )}
        </Dropdown>
      </div>
    </header>
  );
}
