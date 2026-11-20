"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Mail,
  UserPlus,
  RefreshCw,
  Search,
  Ban,
  CheckCircle2,
  AlertCircle,
  Clock,
  Copy,
  Check,
  Loader2,
} from "lucide-react";
import {
  Card,
  CardHeader,
  Button,
  Badge,
  Modal,
  Field,
  Input,
  Select,
  ConfirmDialog,
} from "../ui";
import { api, ApiError } from "../../lib/api";
import { ListSkeleton } from "../loading";
import type { InvitationSummary } from "../../lib/types";

export const PROJECT_ROLE_OPTIONS: Array<{
  value: string;
  label: string;
  description: string;
}> = [
  {
    value: "project_manager",
    label: "Project Manager",
    description:
      "Full project governance, team & invitation management, source configuration, and handover orchestration.",
  },
  {
    value: "reviewer",
    label: "Reviewer",
    description:
      "Inspects evidence, verifies or rejects candidate findings, and formally approves handover packages.",
  },
  {
    value: "departing_owner",
    label: "Outgoing Member",
    description:
      "Contributes context, uploads evidence, and documents architectural ownership prior to transition.",
  },
  {
    value: "incoming_assignee",
    label: "Incoming Member",
    description:
      "Reviews reconstructed knowledge and evidence, and acknowledges receipt of approved handovers.",
  },
  {
    value: "project_member",
    label: "Project Member",
    description:
      "Standard project participant with access to project evidence, knowledge intelligence, and collaboration.",
  },
];

const ROLE_LABEL_MAP: Record<string, string> = Object.fromEntries(
  PROJECT_ROLE_OPTIONS.map((r) => [r.value, r.label])
);

function statusTone(status: string): "blue" | "green" | "amber" | "red" | "gray" {
  switch (status) {
    case "pending":
      return "blue";
    case "accepted":
      return "green";
    case "expired":
      return "amber";
    case "revoked":
      return "red";
    default:
      return "gray";
  }
}

export interface ProjectInvitationsPanelProps {
  organisationId: string;
  projectId: string;
  projectName: string;
  canManage: boolean;
}

export function ProjectInvitationsPanel({
  organisationId,
  projectId,
  projectName,
  canManage,
}: ProjectInvitationsPanelProps) {
  const [invitations, setInvitations] = useState<InvitationSummary[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [permissionDenied, setPermissionDenied] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");

  // Invite modal state
  const [isInviteModalOpen, setIsInviteModalOpen] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("project_member");
  const [expiresInHours, setExpiresInHours] = useState(72);
  const [isSending, setIsSending] = useState(false);
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [inviteBanner, setInviteBanner] = useState<{
    tone: "success" | "warning" | "info";
    message: string;
    devLink?: string;
  } | null>(null);
  const [copiedDevLink, setCopiedDevLink] = useState(false);

  // Revoke confirmation state
  const [invitationToRevoke, setInvitationToRevoke] =
    useState<InvitationSummary | null>(null);
  const [isRevoking, setIsRevoking] = useState(false);

  const loadInvitations = useCallback(async () => {
    if (!organisationId || !projectId) return;
    setIsLoading(true);
    setErrorMessage(null);
    setPermissionDenied(false);
    try {
      const res = await api.projects.listInvitations(organisationId, projectId, {
        limit: 100,
      });
      setInvitations(res.items || []);
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 403) {
        setPermissionDenied(true);
        setInvitations([]);
      } else {
        setErrorMessage(
          err instanceof Error
            ? err.message
            : "Unable to load project invitations."
        );
      }
    } finally {
      setIsLoading(false);
    }
  }, [organisationId, projectId]);

  useEffect(() => {
    void loadInvitations();
  }, [loadInvitations]);

  const filteredInvitations = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return invitations.filter((inv) => {
      if (statusFilter !== "all" && inv.status !== statusFilter) return false;
      if (q && !inv.email.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [invitations, searchQuery, statusFilter]);

  const selectedRoleMeta = useMemo(
    () =>
      PROJECT_ROLE_OPTIONS.find((r) => r.value === inviteRole) ||
      PROJECT_ROLE_OPTIONS[PROJECT_ROLE_OPTIONS.length - 1],
    [inviteRole]
  );

  const handleSendInvite = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleaned = inviteEmail.trim().toLowerCase();
    if (!cleaned || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(cleaned)) {
      setInviteError("Please enter a valid email address.");
      return;
    }

    setIsSending(true);
    setInviteError(null);
    try {
      const res = await api.projects.createInvitation(organisationId, projectId, {
        email: cleaned,
        role_name: inviteRole,
        expires_in_hours: expiresInHours,
      });

      const devLink = res.development_invitation_token
        ? `${window.location.origin}/invitations/${res.development_invitation_token}`
        : undefined;

      setInviteBanner({
        tone:
          res.invitation_delivery === "submitted"
            ? "success"
            : res.invitation_delivery === "failed"
              ? "warning"
              : "info",
        message: res.message,
        devLink,
      });
      setInviteEmail("");
      setIsInviteModalOpen(false);
      await loadInvitations();
    } catch (err: unknown) {
      setInviteError(
        err instanceof Error ? err.message : "Failed to create project invitation."
      );
    } finally {
      setIsSending(false);
    }
  };

  const handleConfirmRevoke = async () => {
    if (!invitationToRevoke) return;
    setIsRevoking(true);
    setErrorMessage(null);
    try {
      await api.projects.revokeInvitation(
        organisationId,
        projectId,
        invitationToRevoke.id
      );
      setInvitationToRevoke(null);
      await loadInvitations();
    } catch (err: unknown) {
      setErrorMessage(
        err instanceof Error ? err.message : "Failed to revoke invitation."
      );
    } finally {
      setIsRevoking(false);
    }
  };

  const handleCopyDevLink = async (link: string) => {
    try {
      await navigator.clipboard.writeText(link);
      setCopiedDevLink(true);
      setTimeout(() => setCopiedDevLink(false), 2000);
    } catch {
      // ignore clipboard errors
    }
  };

  if (permissionDenied) {
    return null;
  }

  const pendingCount = invitations.filter((i) => i.status === "pending").length;

  return (
    <Card className="overflow-hidden">
      <CardHeader
        title="Project Invitations"
        subtitle={`${pendingCount} pending · ${invitations.length} total`}
        icon={Mail}
        action={
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              icon={RefreshCw}
              onClick={() => void loadInvitations()}
              disabled={isLoading}
            >
              Refresh
            </Button>
            {canManage && (
              <Button
                variant="primary"
                size="sm"
                icon={UserPlus}
                onClick={() => {
                  setInviteError(null);
                  setIsInviteModalOpen(true);
                }}
              >
                Invite to Project
              </Button>
            )}
          </div>
        }
      />

      <div className="space-y-4 px-5 pb-5">
        {inviteBanner && (
          <div
            className={`rounded-xl border p-3.5 text-xs ${
              inviteBanner.tone === "success"
                ? "border-emerald-200 bg-emerald-50 text-emerald-900"
                : inviteBanner.tone === "warning"
                  ? "border-amber-200 bg-amber-50 text-amber-900"
                  : "border-sky-200 bg-sky-50 text-sky-900"
            }`}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-start gap-2">
                {inviteBanner.tone === "success" ? (
                  <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-600" />
                ) : (
                  <AlertCircle className="mt-0.5 size-4 shrink-0" />
                )}
                <div>
                  <p className="font-medium">{inviteBanner.message}</p>
                  {inviteBanner.devLink && (
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      <code className="rounded bg-white/80 px-2 py-1 text-[11px] text-navy border border-line">
                        {inviteBanner.devLink}
                      </code>
                      <button
                        type="button"
                        onClick={() => void handleCopyDevLink(inviteBanner.devLink!)}
                        className="inline-flex items-center gap-1 rounded border border-line bg-white px-2 py-1 text-[11px] font-medium text-navy hover:bg-slate-50"
                      >
                        {copiedDevLink ? (
                          <>
                            <Check className="size-3 text-emerald-600" />
                            Copied
                          </>
                        ) : (
                          <>
                            <Copy className="size-3" />
                            Copy link
                          </>
                        )}
                      </button>
                    </div>
                  )}
                </div>
              </div>
              <button
                type="button"
                onClick={() => setInviteBanner(null)}
                className="text-[11px] underline opacity-75 hover:opacity-100"
              >
                Dismiss
              </button>
            </div>
          </div>
        )}

        {errorMessage && (
          <div className="flex items-center gap-2 rounded-xl border border-red-200 bg-red-50 p-3 text-xs text-red-700">
            <AlertCircle className="size-4 shrink-0" />
            <span>{errorMessage}</span>
          </div>
        )}

        {/* Filters */}
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-2.5 size-3.5 text-muted" />
            <Input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search invitations by email..."
              className="pl-8 text-xs"
            />
          </div>
          <Select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="sm:w-40 text-xs"
          >
            <option value="all">All statuses</option>
            <option value="pending">Pending</option>
            <option value="accepted">Accepted</option>
            <option value="expired">Expired</option>
            <option value="revoked">Revoked</option>
          </Select>
        </div>

        {/* List */}
        {isLoading ? (
          <div className="py-2" role="status" aria-live="polite">
            <ListSkeleton variant="thread" count={4} />
          </div>
        ) : filteredInvitations.length === 0 ? (
          <div className="rounded-xl border border-dashed border-line p-6 text-center text-xs text-muted">
            {invitations.length === 0
              ? "No project invitations have been sent yet."
              : "No invitations match the current filter."}
          </div>
        ) : (
          <ul className="space-y-2.5">
            {filteredInvitations.map((inv) => {
              const roleKey = inv.project_role_name || inv.role_name;
              const roleLabel = ROLE_LABEL_MAP[roleKey] || roleKey;
              return (
                <li
                  key={inv.id}
                  className="flex flex-col justify-between gap-3 rounded-xl border border-line bg-white p-3.5 sm:flex-row sm:items-center"
                >
                  <div className="min-w-0 space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="truncate text-[13px] font-semibold text-navy">
                        {inv.email}
                      </span>
                      <Badge tone={statusTone(inv.status)}>
                        {inv.status}
                      </Badge>
                    </div>
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted">
                      <span>
                        Project role:{" "}
                        <strong className="font-medium text-navy">
                          {roleLabel}
                        </strong>
                      </span>
                      <span className="inline-flex items-center gap-1">
                        <Clock className="size-3" />
                        Expires {new Date(inv.expires_at).toLocaleDateString()}
                      </span>
                    </div>
                  </div>

                  {canManage && inv.status === "pending" && (
                    <Button
                      variant="secondary"
                      size="sm"
                      icon={Ban}
                      onClick={() => setInvitationToRevoke(inv)}
                    >
                      Revoke
                    </Button>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {/* Invite Modal */}
      <Modal
        open={isInviteModalOpen}
        onClose={() => setIsInviteModalOpen(false)}
        title="Invite to Project"
        subtitle={`Send a single-use invitation to join ${projectName}`}
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => setIsInviteModalOpen(false)}
              disabled={isSending}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={handleSendInvite}
              disabled={isSending}
            >
              {isSending ? "Sending..." : "Send Invitation"}
            </Button>
          </>
        }
      >
        <form onSubmit={handleSendInvite} className="space-y-4">
          {inviteError && (
            <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700">
              <AlertCircle className="mt-0.5 size-4 shrink-0" />
              <span>{inviteError}</span>
            </div>
          )}

          <Field
            label="Invitee Email Address"
            required
            hint="If they are new to the organisation, accepting establishes both organisation membership and project access atomically."
          >
            <Input
              type="email"
              value={inviteEmail}
              onChange={(e) => setInviteEmail(e.target.value)}
              placeholder="colleague@company.com"
              required
            />
          </Field>

          <Field label="Assigned Project Role" required>
            <Select
              value={inviteRole}
              onChange={(e) => setInviteRole(e.target.value)}
            >
              {PROJECT_ROLE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </Select>
            <p className="mt-1.5 rounded-lg bg-slate-50 p-2.5 text-[11.5px] leading-relaxed text-muted border border-line">
              {selectedRoleMeta?.description}
            </p>
          </Field>

          <Field label="Invitation Expiry">
            <Select
              value={String(expiresInHours)}
              onChange={(e) => setExpiresInHours(Number(e.target.value))}
            >
              <option value="24">24 hours</option>
              <option value="72">3 days (72 hours)</option>
              <option value="168">7 days</option>
              <option value="336">14 days</option>
            </Select>
          </Field>
        </form>
      </Modal>

      {/* Revoke Confirm Dialog */}
      <ConfirmDialog
        open={!!invitationToRevoke}
        onClose={() => setInvitationToRevoke(null)}
        onConfirm={() => void handleConfirmRevoke()}
        title="Revoke Project Invitation?"
        tone="danger"
        confirmLabel="Revoke Invitation"
        isLoading={isRevoking}
        body={
          invitationToRevoke && (
            <p>
              Revoke the pending invitation for{" "}
              <strong className="text-navy">{invitationToRevoke.email}</strong>?
              Its invitation link will immediately become unusable.
            </p>
          )
        }
      />
    </Card>
  );
}
