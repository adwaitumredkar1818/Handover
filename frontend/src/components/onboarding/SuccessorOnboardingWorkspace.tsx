"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Bot,
  Check,
  CheckCircle2,
  ClipboardCheck,
  Copy,
  Database,
  ExternalLink,
  FileText,
  FolderKanban,
  GitBranch,
  Loader2,
  PackageCheck,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  Users,
} from "lucide-react";
import { Card, CardHeader, Button, Badge } from "../ui";
import { PageSkeleton } from "../loading";
import { useLiveApp } from "../../context/LiveAppContext";
import { api } from "../../lib/api";
import type {
  EvidenceSummary,
  HandoverCaseItem,
  Project,
  ProjectMember,
  ProjectOverview,
  ProjectSourceMapping,
} from "../../lib/types";

const ONBOARDING_STEPS = [
  { id: "welcome", title: "1. Project Welcome & Scope", icon: FolderKanban },
  { id: "role", title: "2. Role & Permissions", icon: ShieldCheck },
  { id: "knowledge", title: "3. Knowledge Overview", icon: BookOpen },
  { id: "evidence", title: "4. Evidence & Sources", icon: Database },
  { id: "handover", title: "5. Handover Packages", icon: PackageCheck },
  { id: "assistant", title: "6. AI Assistant Quick-Start", icon: Bot },
  { id: "complete", title: "7. Enter Project Workspace", icon: ClipboardCheck },
] as const;

const ROLE_CAPABILITIES: Record<
  string,
  { label: string; summary: string; capabilities: string[] }
> = {
  project_manager: {
    label: "Project Manager",
    summary:
      "You govern project configuration, membership, invitations, connected sources, and handover orchestration.",
    capabilities: [
      "View all project evidence you are authorised to access",
      "Invite members and manage project roles",
      "Connect or map authorised organisational sources",
      "Verify findings and orchestrate handover packages",
    ],
  },
  reviewer: {
    label: "Reviewer",
    summary:
      "You validate reconstructed knowledge against source evidence and formally approve handover packages.",
    capabilities: [
      "Inspect evidence and reconstructed knowledge findings",
      "Verify, edit, or reject candidate findings",
      "Resolve knowledge conflicts with supporting evidence",
      "Formally approve handover packages before sharing",
    ],
  },
  departing_owner: {
    label: "Outgoing Member",
    summary:
      "You contribute domain context, upload missing documents, and clarify ownership before transitioning.",
    capabilities: [
      "Upload documents and review reconstructed findings",
      "Annotate decisions, dependencies, and open risks",
      "Support verification with contextual clarifications",
    ],
  },
  incoming_assignee: {
    label: "Incoming Member / Successor",
    summary:
      "You review reconstructed project knowledge and evidence, and acknowledge receipt of approved handovers.",
    capabilities: [
      "Explore verified decisions, architecture, risks, and tasks",
      "Inspect supporting source evidence and citations",
      "Query the permission-filtered AI Knowledge Assistant",
      "Acknowledge receipt of reviewer-approved handover packages",
    ],
  },
  project_member: {
    label: "Project Member",
    summary:
      "You have standard collaborative read access to project evidence, knowledge, and handovers.",
    capabilities: [
      "View project overview, evidence library, and knowledge intelligence",
      "Query the permission-filtered AI Knowledge Assistant",
      "Collaborate with project reviewers and managers",
    ],
  },
};

function formatTransitionRole(role?: string | null): string | null {
  if (!role || role === "none") return null;
  if (role === "incoming_assignee") return "Incoming Successor";
  if (role === "departing_owner") return "Outgoing Owner";
  if (role === "reviewer") return "Designated Reviewer";
  return role.replace(/_/g, " ");
}

function getStatusTone(status: string): "green" | "amber" | "blue" | "gray" {
  const s = status.toLowerCase();
  if (["approved", "published", "completed", "verified"].includes(s)) return "green";
  if (["in_review", "pending_review", "needs_review", "pending"].includes(s)) return "amber";
  if (["active", "ready"].includes(s)) return "blue";
  return "gray";
}

export function SuccessorOnboardingWorkspace({
  projectId,
}: {
  projectId: string;
}) {
  const router = useRouter();
  const { user, setActiveProject } = useLiveApp();

  const [stepIndex, setStepIndex] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [saveFeedback, setSaveFeedback] = useState<string | null>(null);
  const [isSavingStep, setIsSavingStep] = useState(false);
  const [copiedPrompt, setCopiedPrompt] = useState<string | null>(null);

  const [project, setProject] = useState<Project | null>(null);
  const [overview, setOverview] = useState<ProjectOverview | null>(null);
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [findings, setFindings] = useState<Record<string, unknown>[]>([]);
  const [findingsTotal, setFindingsTotal] = useState(0);
  const [evidence, setEvidence] = useState<EvidenceSummary[]>([]);
  const [sources, setSources] = useState<ProjectSourceMapping[]>([]);
  const [handoverCases, setHandoverCases] = useState<HandoverCaseItem[]>([]);

  const [completedSteps, setCompletedSteps] = useState<Record<string, boolean>>({});
  const [stepTimestamps, setStepTimestamps] = useState<Record<string, string | null>>({});
  const [inspectedMemberId, setInspectedMemberId] = useState<string>("");

  const storageKey = `handover_onboarding_completed_${projectId}`;

  const isInspectingOther = Boolean(
    inspectedMemberId && user?.id && inspectedMemberId !== user.id
  );

  const applyOnboardingPayload = useCallback(
    (
      onboardingRes: {
        completed_steps?: Record<string, boolean>;
        steps?: Array<{
          step_id: string;
          is_completed: boolean;
          completed_at?: string | null;
        }>;
      } | null,
      allowLocalMerge: boolean
    ) => {
      const mergedCompleted: Record<string, boolean> = {
        ...(onboardingRes?.completed_steps || {}),
      };
      const timestamps: Record<string, string | null> = {};
      for (const s of onboardingRes?.steps || []) {
        timestamps[s.step_id] = s.completed_at ?? null;
      }

      if (allowLocalMerge && typeof window !== "undefined") {
        try {
          const raw = localStorage.getItem(storageKey);
          if (raw) {
            const localSteps = JSON.parse(raw) as Record<string, boolean>;
            for (const [stepId, isDone] of Object.entries(localSteps)) {
              if (isDone && !mergedCompleted[stepId]) {
                mergedCompleted[stepId] = true;
                void api.onboarding.updateStep(projectId, stepId, true).catch(() => {});
              }
            }
          }
        } catch {
          // ignore
        }
      }

      setCompletedSteps(mergedCompleted);
      setStepTimestamps(timestamps);
    },
    [projectId, storageKey]
  );

  const setStepCompletion = useCallback(
    async (id: string, nextVal: boolean) => {
      if (isInspectingOther) return;
      setSaveFeedback(null);
      setIsSavingStep(true);
      setCompletedSteps((prev) => {
        const next = { ...prev, [id]: nextVal };
        if (typeof window !== "undefined") {
          try {
            localStorage.setItem(storageKey, JSON.stringify(next));
          } catch {
            // ignore
          }
        }
        return next;
      });
      try {
        const updated = await api.onboarding.updateStep(projectId, id, nextVal);
        setStepTimestamps((prev) => ({
          ...prev,
          [id]: updated.completed_at ?? null,
        }));
      } catch (err: unknown) {
        setSaveFeedback(
          err instanceof Error
            ? `Could not sync step to server: ${err.message}`
            : "Could not sync onboarding progress to server."
        );
      } finally {
        setIsSavingStep(false);
      }
    },
    [isInspectingOther, projectId, storageKey]
  );

  const handleResetProgress = useCallback(async () => {
    if (isInspectingOther) return;
    setIsSavingStep(true);
    setSaveFeedback(null);
    const activeIds = Object.entries(completedSteps)
      .filter(([, done]) => done)
      .map(([id]) => id);
    try {
      await Promise.all(
        activeIds.map((id) => api.onboarding.deleteStep(projectId, id).catch(() => {}))
      );
      setCompletedSteps({});
      setStepTimestamps({});
      setStepIndex(0);
      if (typeof window !== "undefined") {
        try {
          localStorage.removeItem(storageKey);
        } catch {
          // ignore
        }
      }
    } catch (err: unknown) {
      setSaveFeedback(
        err instanceof Error ? err.message : "Unable to reset onboarding progress."
      );
    } finally {
      setIsSavingStep(false);
    }
  }, [completedSteps, isInspectingOther, projectId, storageKey]);

  const loadWorkspaceData = useCallback(async () => {
    if (!projectId) return;
    setIsLoading(true);
    if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(projectId)) {
      setErrorMessage("Invalid project identifier.");
      setIsLoading(false);
      return;
    }
    setErrorMessage(null);
    try {
      const [
        projRes,
        overviewRes,
        membersRes,
        findingsRes,
        evidenceRes,
        sourcesRes,
        casesRes,
        onboardingRes,
      ] = await Promise.all([
        api.projects.get(projectId),
        api.projects.getOverview(projectId).catch(() => null),
        api.members.list(projectId).catch(() => []),
        api.knowledgeIntelligence
          .listFindings(projectId, undefined, 25, 0)
          .catch(() => ({ items: [], total: 0 })),
        api.evidence.list(projectId, { limit: 10 }).catch(() => []),
        api.sources.listProjectMappings(projectId).catch(() => []),
        api.handover
          .listCases(projectId)
          .catch(() => ({ items: [], total: 0 })),
        api.onboarding
          .getProgress(projectId)
          .catch(() => null),
      ]);

      setProject(projRes);
      setActiveProject(projRes);
      setOverview(overviewRes);
      setMembers(membersRes);
      setFindings(findingsRes.items || []);
      setFindingsTotal(findingsRes.total || 0);
      setEvidence(evidenceRes || []);
      setSources(sourcesRes || []);
      setHandoverCases(casesRes.items || []);
      applyOnboardingPayload(onboardingRes, true);
    } catch (err: unknown) {
      setErrorMessage(
        err instanceof Error
          ? err.message
          : "Unable to load project onboarding details."
      );
    } finally {
      setIsLoading(false);
    }
  }, [applyOnboardingPayload, projectId, setActiveProject]);

  useEffect(() => {
    void loadWorkspaceData();
  }, [loadWorkspaceData]);

  const handleInspectMemberChange = async (targetId: string) => {
    setInspectedMemberId(targetId);
    setSaveFeedback(null);
    try {
      const target = targetId && targetId !== user?.id ? targetId : undefined;
      const res = await api.onboarding.getProgress(projectId, target);
      applyOnboardingPayload(res, !target);
    } catch (err: unknown) {
      setSaveFeedback(
        err instanceof Error ? err.message : "Unable to load member onboarding progress."
      );
    }
  };

  const myMemberRecord = useMemo(
    () => members.find((m) => m.user_id === user?.id) || null,
    [members, user?.id]
  );

  const canManageProject =
    myMemberRecord?.role_name === "project_manager" ||
    user?.roles?.some((r) => ["admin", "project_manager"].includes(r.toLowerCase()));

  const myRoleKey = myMemberRecord?.role_name || "project_member";
  const roleInfo =
    ROLE_CAPABILITIES[myRoleKey] ?? ROLE_CAPABILITIES.project_member!;
  const myTransitionLabel = formatTransitionRole(myMemberRecord?.transition_role);

  const isExplicitSuccessor = useMemo(() => {
    if (!user?.id) return false;
    return (
      overview?.successor?.id === user.id ||
      myMemberRecord?.transition_role === "incoming_assignee" ||
      myRoleKey === "incoming_assignee"
    );
  }, [user?.id, overview?.successor?.id, myMemberRecord?.transition_role, myRoleKey]);

  const currentStep = ONBOARDING_STEPS[stepIndex] ?? ONBOARDING_STEPS[0];
  const completedCount = useMemo(
    () => ONBOARDING_STEPS.filter((s) => Boolean(completedSteps[s.id])).length,
    [completedSteps]
  );
  const completionPct = Math.round((completedCount / ONBOARDING_STEPS.length) * 100);

  const handleNext = () => {
    if (!isInspectingOther) {
      void setStepCompletion(currentStep.id, true);
    }
    if (stepIndex < ONBOARDING_STEPS.length - 1) {
      setStepIndex((i) => i + 1);
    }
  };

  const handleCompleteOnboarding = async () => {
    if (!isInspectingOther) {
      await setStepCompletion("complete", true);
    }
    router.push(`/projects/${projectId}`);
  };

  const handleCopyPrompt = async (prompt: string) => {
    try {
      await navigator.clipboard.writeText(prompt);
      setCopiedPrompt(prompt);
      setTimeout(() => setCopiedPrompt(null), 1800);
    } catch {
      // ignore clipboard restrictions
    }
  };

  const inspectedMember = useMemo(
    () => members.find((m) => m.user_id === inspectedMemberId) || null,
    [inspectedMemberId, members]
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col justify-between gap-4 rounded-2xl border border-line bg-white p-5 shadow-2xs sm:flex-row sm:items-center">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2 text-xs font-semibold uppercase tracking-wider text-brand">
            <Sparkles className="size-3.5" />
            <span>
              {isExplicitSuccessor
                ? "Successor Onboarding & Continuation"
                : "Project Onboarding & Orientation"}
            </span>
            {isSavingStep && (
              <span className="inline-flex items-center gap-1 text-[11px] font-medium normal-case text-muted">
                <Loader2 className="size-3 animate-spin" /> Saving…
              </span>
            )}
          </div>
          <h1 className="mt-1 text-xl font-bold tracking-tight text-navy">
            {project ? project.name : "Project Onboarding"}
          </h1>
          <div className="mt-2 flex flex-wrap items-center gap-3">
            <p className="text-xs text-muted">
              Step {stepIndex + 1} of {ONBOARDING_STEPS.length}: {currentStep.title}
            </p>
            <span className="text-xs font-semibold text-navy">
              {completedCount}/{ONBOARDING_STEPS.length} completed ({completionPct}%)
            </span>
          </div>
          <div className="mt-2 h-1.5 w-full max-w-md overflow-hidden rounded-full bg-slate-100">
            <div
              className="h-full rounded-full bg-brand transition-all duration-300"
              style={{ width: `${completionPct}%` }}
            />
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {canManageProject && members.length > 1 && (
            <select
              aria-label="Inspect member onboarding progress"
              value={inspectedMemberId}
              onChange={(e) => void handleInspectMemberChange(e.target.value)}
              className="h-8 rounded-lg border border-line bg-white px-2.5 text-xs text-navy focus:border-brand focus:outline-none"
            >
              <option value="">My Onboarding Progress</option>
              {members
                .filter((m) => m.user_id !== user?.id)
                .map((m) => (
                  <option key={m.user_id} value={m.user_id}>
                    {m.full_name || m.email}
                    {m.transition_role === "incoming_assignee" ? " (Successor)" : ""}
                  </option>
                ))}
            </select>
          )}
          {!isInspectingOther && completedCount > 0 && (
            <Button
              variant="ghost"
              size="sm"
              icon={RotateCcw}
              disabled={isSavingStep}
              onClick={() => void handleResetProgress()}
            >
              Reset
            </Button>
          )}
          <Link href={`/projects/${projectId}`}>
            <Button variant="secondary" size="sm" icon={ArrowLeft}>
              Skip to Project
            </Button>
          </Link>
        </div>
      </div>

      {isInspectingOther && inspectedMember && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-2.5 text-xs text-amber-900">
          Viewing read-only onboarding checklist for{" "}
          <strong>{inspectedMember.full_name || inspectedMember.email}</strong>. Switch back to
          &ldquo;My Onboarding Progress&rdquo; to update your own steps.
        </div>
      )}

      {saveFeedback && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-2.5 text-xs text-red-700">
          {saveFeedback}
        </div>
      )}

      {isLoading ? (
        <div role="status" aria-live="polite">
          <PageSkeleton layout="dashboard" />
        </div>
      ) : errorMessage || !project ? (
        <Card className="p-6">
          <div className="flex items-start gap-3 text-sm text-red-700">
            <AlertCircle className="mt-0.5 size-5 shrink-0" />
            <div>
              <p className="font-semibold">Unable to load project onboarding</p>
              <p className="mt-1 text-xs">{errorMessage || "Project not found."}</p>
              <div className="mt-4">
                <Link href="/overview">
                  <Button variant="secondary" size="sm">
                    Return to Overview
                  </Button>
                </Link>
              </div>
            </div>
          </div>
        </Card>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
          {/* Left Stepper */}
          <Card className="h-fit p-3">
            <ul className="space-y-1">
              {ONBOARDING_STEPS.map((s, idx) => {
                const Icon = s.icon;
                const active = idx === stepIndex;
                const done = !!completedSteps[s.id];
                return (
                  <li key={s.id}>
                    <button
                      type="button"
                      onClick={() => setStepIndex(idx)}
                      className={`flex w-full items-center gap-2.5 rounded-xl px-3 py-2.5 text-left text-xs font-medium transition ${
                        active
                          ? "bg-brand/10 font-semibold text-brand"
                          : "text-navy hover:bg-slate-50"
                      }`}
                    >
                      <span
                        className={`flex size-6 shrink-0 items-center justify-center rounded-full border ${
                          done
                            ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                            : active
                              ? "border-brand bg-brand text-white"
                              : "border-line bg-white text-muted"
                        }`}
                      >
                        {done ? (
                          <Check className="size-3.5" />
                        ) : (
                          <Icon className="size-3.5" />
                        )}
                      </span>
                      <span className="truncate">{s.title}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </Card>

          {/* Step Content */}
          <Card className="p-6">
            {currentStep.id === "welcome" && (
              <div className="space-y-4">
                <CardHeader
                  title="Project Welcome & Scope"
                  subtitle="Canonical project state and transition participants"
                  icon={FolderKanban}
                />
                <div className="space-y-2 rounded-xl border border-line bg-slate-50/70 p-4 text-xs text-navy">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={getStatusTone(project.status)}>{project.status}</Badge>
                    {project.target_handover_date && (
                      <span className="text-muted">
                        Target handover:{" "}
                        <strong>
                          {new Date(project.target_handover_date).toLocaleDateString()}
                        </strong>
                      </span>
                    )}
                  </div>
                  <p className="leading-relaxed text-muted">
                    {project.description || "No project description has been recorded yet."}
                  </p>
                </div>

                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="rounded-xl border border-line p-4 text-xs">
                    <p className="font-semibold text-navy">Departing Owner</p>
                    <p className="mt-1 text-muted">
                      {overview?.departing_member
                        ? `${overview.departing_member.full_name} (${overview.departing_member.email})`
                        : "Not currently designated"}
                    </p>
                  </div>
                  <div className="rounded-xl border border-line p-4 text-xs">
                    <p className="font-semibold text-navy">Designated Successor</p>
                    <p className="mt-1 text-muted">
                      {overview?.successor
                        ? `${overview.successor.full_name} (${overview.successor.email})`
                        : "Not currently designated"}
                    </p>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  <div className="rounded-xl border border-line bg-white p-3 text-xs">
                    <p className="text-[11px] text-muted">Team Members</p>
                    <p className="mt-0.5 text-base font-bold text-navy">{members.length}</p>
                  </div>
                  <div className="rounded-xl border border-line bg-white p-3 text-xs">
                    <p className="text-[11px] text-muted">Connected Sources</p>
                    <p className="mt-0.5 text-base font-bold text-navy">{sources.length}</p>
                  </div>
                  <div className="rounded-xl border border-line bg-white p-3 text-xs">
                    <p className="text-[11px] text-muted">Findings</p>
                    <p className="mt-0.5 text-base font-bold text-navy">{findingsTotal}</p>
                  </div>
                  <div className="rounded-xl border border-line bg-white p-3 text-xs">
                    <p className="text-[11px] text-muted">Handover Cases</p>
                    <p className="mt-0.5 text-base font-bold text-navy">{handoverCases.length}</p>
                  </div>
                </div>
              </div>
            )}

            {currentStep.id === "role" && (
              <div className="space-y-4">
                <CardHeader
                  title="Your Role & Permissions"
                  subtitle={`Assigned role: ${roleInfo.label}${myTransitionLabel ? ` · ${myTransitionLabel}` : ""}`}
                  icon={ShieldCheck}
                />
                <p className="text-xs leading-relaxed text-muted">{roleInfo.summary}</p>
                <ul className="space-y-2">
                  {roleInfo.capabilities.map((cap) => (
                    <li
                      key={cap}
                      className="flex items-start gap-2 rounded-xl border border-line bg-slate-50/50 p-3 text-xs text-navy"
                    >
                      <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-600" />
                      <span>{cap}</span>
                    </li>
                  ))}
                </ul>
                <div className="rounded-xl border border-sky-200 bg-sky-50 p-3.5 text-xs text-sky-900">
                  <strong>Source Access Boundary:</strong> Project membership does not
                  automatically grant access to private external repositories or restricted
                  channels connected by another user. Evidence visibility is strictly
                  ACL-enforced.
                </div>
              </div>
            )}

            {currentStep.id === "knowledge" && (
              <div className="space-y-4">
                <CardHeader
                  title="Reconstructed Knowledge Overview"
                  subtitle={`${findingsTotal} reconstructed finding(s) available`}
                  icon={BookOpen}
                />
                {findings.length === 0 ? (
                  <div className="rounded-xl border border-dashed border-line p-6 text-center text-xs text-muted">
                    No reconstructed knowledge findings exist for this project yet. Upload
                    documents or sync sources to begin reconstruction.
                  </div>
                ) : (
                  <ul className="space-y-2.5">
                    {findings.slice(0, 6).map((item, idx) => {
                      const title = String(item.title || item.summary || "Finding");
                      const body =
                        typeof item.structured_summary === "string"
                          ? item.structured_summary
                          : typeof item.summary === "string"
                            ? item.summary
                            : typeof item.description === "string"
                              ? item.description
                              : null;
                      const domain =
                        typeof item.category === "string"
                          ? item.category
                          : typeof item.domain === "string"
                            ? item.domain
                            : null;
                      const verif =
                        typeof item.verification_status === "string"
                          ? item.verification_status
                          : typeof item.epistemic_status === "string"
                            ? item.epistemic_status
                            : null;

                      return (
                        <li
                          key={String(item.id || idx)}
                          className="rounded-xl border border-line p-3.5 text-xs"
                        >
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <span className="font-semibold text-navy">{title}</span>
                            <div className="flex flex-wrap items-center gap-1.5">
                              {domain && <Badge tone="blue">{domain}</Badge>}
                              {verif && (
                                <Badge tone={getStatusTone(verif)}>
                                  {verif.replace(/_/g, " ")}
                                </Badge>
                              )}
                            </div>
                          </div>
                          {body && (
                            <p className="mt-1 line-clamp-2 text-muted">{body}</p>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                )}
                <div className="flex flex-wrap items-center gap-4">
                  <Link
                    href={`/projects/${projectId}/knowledge`}
                    className="inline-flex items-center gap-1 text-xs font-semibold text-brand hover:underline"
                  >
                    Open full Knowledge Intelligence <ArrowRight className="size-3" />
                  </Link>
                  <Link
                    href={`/projects/${projectId}/relationships`}
                    className="inline-flex items-center gap-1 text-xs font-semibold text-navy hover:underline"
                  >
                    <GitBranch className="size-3" /> Explore Relationships
                  </Link>
                </div>
              </div>
            )}

            {currentStep.id === "evidence" && (
              <div className="space-y-4">
                <CardHeader
                  title="Evidence & Connected Sources"
                  subtitle={`${sources.length} source mapping(s) · ${evidence.length} recent evidence item(s)`}
                  icon={Database}
                />
                {sources.length === 0 && evidence.length === 0 ? (
                  <div className="rounded-xl border border-dashed border-line p-6 text-center text-xs text-muted">
                    No connected sources or uploaded evidence items are available yet in your
                    authorised scope.
                  </div>
                ) : (
                  <div className="space-y-3">
                    {sources.length > 0 && (
                      <div className="space-y-1.5">
                        <p className="text-xs font-semibold text-navy">Mapped Sources</p>
                        <div className="flex flex-wrap gap-2">
                          {sources.map((src) => (
                            <Badge key={src.id} tone="gray">
                              {src.provider}: {src.external_resource_name}
                            </Badge>
                          ))}
                        </div>
                      </div>
                    )}
                    {evidence.length > 0 && (
                      <ul className="space-y-2">
                        {evidence.slice(0, 5).map((ev) => (
                          <li key={ev.id}>
                            <Link
                              href={`/projects/${projectId}/evidence/${ev.id}`}
                              className="flex items-center justify-between gap-2 rounded-xl border border-line p-3 text-xs transition hover:border-brand/40 hover:bg-slate-50/70"
                            >
                              <div className="flex min-w-0 items-center gap-2">
                                <FileText className="size-4 shrink-0 text-brand" />
                                <span className="truncate font-medium text-navy">
                                  {ev.title}
                                </span>
                              </div>
                              <div className="flex shrink-0 items-center gap-2">
                                <Badge tone="gray">{ev.provider}</Badge>
                                <ExternalLink className="size-3 text-muted" />
                              </div>
                            </Link>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
                <Link
                  href={`/projects/${projectId}/evidence`}
                  className="inline-flex items-center gap-1 text-xs font-semibold text-brand hover:underline"
                >
                  Open Evidence Center <ArrowRight className="size-3" />
                </Link>
              </div>
            )}

            {currentStep.id === "handover" && (
              <div className="space-y-4">
                <CardHeader
                  title="Handover Packages & Readiness"
                  subtitle={
                    overview?.readiness
                      ? `Current readiness score: ${overview.readiness.overall_readiness_pct}%`
                      : "Real handover case records"
                  }
                  icon={PackageCheck}
                />
                {handoverCases.length === 0 ? (
                  <div className="rounded-xl border border-dashed border-line p-6 text-center text-xs text-muted">
                    No handover packages have been generated for this project yet. Handover
                    packages require human verification and designated reviewer approval before
                    sharing.
                  </div>
                ) : (
                  <ul className="space-y-2.5">
                    {handoverCases.map((hc) => {
                      const score = hc.latest_readiness_score ?? hc.readiness_score;
                      return (
                        <li
                          key={hc.id}
                          className="flex flex-col justify-between gap-3 rounded-xl border border-line p-3.5 text-xs sm:flex-row sm:items-center"
                        >
                          <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-2">
                              <p className="font-semibold text-navy">{hc.title}</p>
                              <Badge tone={getStatusTone(hc.status)}>
                                {hc.status.replace(/_/g, " ")}
                              </Badge>
                            </div>
                            <p className="mt-1 text-muted">
                              Version {hc.version ?? 1}
                              {typeof score === "number" ? ` · Readiness ${score}%` : ""} · Updated{" "}
                              {new Date(hc.updated_at).toLocaleDateString()}
                            </p>
                          </div>
                          <div className="flex shrink-0 flex-wrap items-center gap-2">
                            <Link href={`/handovers/${hc.id}/report`}>
                              <Button variant="secondary" size="sm" icon={FileText}>
                                Report
                              </Button>
                            </Link>
                            <Link href={`/handovers/${hc.id}/recipient`}>
                              <Button variant="primary" size="sm" icon={ClipboardCheck}>
                                Recipient View
                              </Button>
                            </Link>
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                )}
                <Link
                  href={`/projects/${projectId}/handovers`}
                  className="inline-flex items-center gap-1 text-xs font-semibold text-brand hover:underline"
                >
                  Open Handover Workspace <ArrowRight className="size-3" />
                </Link>
              </div>
            )}

            {currentStep.id === "assistant" && (
              <div className="space-y-4">
                <CardHeader
                  title="AI Knowledge Assistant Quick-Start"
                  subtitle="Evidence-grounded answers with strict permission filtering"
                  icon={Bot}
                />
                <p className="text-xs leading-relaxed text-muted">
                  Ask questions about this project&apos;s architecture, decisions, risks, or
                  open work. Every answer is grounded strictly in evidence you are authorised to
                  read and includes explicit citations and uncertainty disclosures.
                </p>
                <div className="space-y-2">
                  {[
                    "What are the most critical architectural decisions and their rationale?",
                    "Which open bugs, blockers, or operational risks need immediate attention?",
                    "What responsibilities and dependencies am I taking over?",
                  ].map((prompt) => {
                    const isCopied = copiedPrompt === prompt;
                    return (
                      <button
                        key={prompt}
                        type="button"
                        onClick={() => void handleCopyPrompt(prompt)}
                        className="flex w-full items-center justify-between gap-3 rounded-xl border border-line bg-slate-50/70 p-3 text-left text-xs text-navy transition hover:border-brand/40 hover:bg-slate-100/70"
                      >
                        <span>&ldquo;{prompt}&rdquo;</span>
                        <span className="inline-flex shrink-0 items-center gap-1 text-[11px] font-medium text-brand">
                          {isCopied ? (
                            <>
                              <Check className="size-3" /> Copied
                            </>
                          ) : (
                            <>
                              <Copy className="size-3" /> Copy
                            </>
                          )}
                        </span>
                      </button>
                    );
                  })}
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Link href="/assistant">
                    <Button variant="primary" size="sm" icon={Bot}>
                      Open Knowledge Assistant
                    </Button>
                  </Link>
                  {handoverCases[0] && (
                    <Link href={`/handovers/${handoverCases[0].id}/assistant`}>
                      <Button variant="secondary" size="sm" icon={Sparkles}>
                        Open Handover Assistant
                      </Button>
                    </Link>
                  )}
                </div>
              </div>
            )}

            {currentStep.id === "complete" && (
              <div className="space-y-4">
                <CardHeader
                  title="Ready to Continue Project Work"
                  subtitle="Confirm your orientation checklist and enter the workspace"
                  icon={ClipboardCheck}
                />
                <p className="text-xs leading-relaxed text-muted">
                  Review your onboarding checklist below. You can toggle individual steps or
                  revisit this guide anytime from the project workspace.
                </p>
                <ul className="space-y-2">
                  {ONBOARDING_STEPS.slice(0, -1).map((step) => {
                    const isDone = Boolean(completedSteps[step.id]);
                    const ts = stepTimestamps[step.id];
                    return (
                      <li
                        key={step.id}
                        className="flex items-center justify-between gap-3 rounded-xl border border-line px-3.5 py-2.5 text-xs"
                      >
                        <div className="flex items-center gap-2.5">
                          <span
                            className={`flex size-5 items-center justify-center rounded-full ${
                              isDone
                                ? "bg-emerald-100 text-emerald-700"
                                : "bg-slate-100 text-muted"
                            }`}
                          >
                            {isDone ? <Check className="size-3" /> : <span className="size-1.5 rounded-full bg-slate-400" />}
                          </span>
                          <span className="font-medium text-navy">{step.title}</span>
                        </div>
                        <div className="flex items-center gap-2">
                          {ts && (
                            <span className="hidden text-[11px] text-muted sm:inline">
                              {new Date(ts).toLocaleDateString()}
                            </span>
                          )}
                          {!isInspectingOther && (
                            <button
                              type="button"
                              onClick={() => void setStepCompletion(step.id, !isDone)}
                              className="text-[11px] font-semibold text-brand hover:underline"
                            >
                              {isDone ? "Mark pending" : "Mark done"}
                            </button>
                          )}
                        </div>
                      </li>
                    );
                  })}
                </ul>
                <div className="flex flex-wrap items-center gap-3 pt-2">
                  <Button
                    variant="primary"
                    icon={ArrowRight}
                    disabled={isSavingStep}
                    onClick={() => void handleCompleteOnboarding()}
                  >
                    Enter {project.name} Workspace
                  </Button>
                  <Link href={`/projects/${projectId}/team`}>
                    <Button variant="secondary" icon={Users}>
                      View Project Team
                    </Button>
                  </Link>
                </div>
              </div>
            )}

            {/* Footer Navigation */}
            <div className="mt-6 flex items-center justify-between border-t border-line pt-4">
              <Button
                variant="secondary"
                size="sm"
                icon={ArrowLeft}
                disabled={stepIndex === 0}
                onClick={() => setStepIndex((i) => Math.max(0, i - 1))}
              >
                Previous
              </Button>
              {stepIndex < ONBOARDING_STEPS.length - 1 ? (
                <Button
                  variant="primary"
                  size="sm"
                  icon={ArrowRight}
                  disabled={isSavingStep}
                  onClick={handleNext}
                >
                  Save &amp; Continue
                </Button>
              ) : (
                <Button
                  variant="primary"
                  size="sm"
                  icon={CheckCircle2}
                  disabled={isSavingStep}
                  onClick={() => void handleCompleteOnboarding()}
                >
                  Finish Onboarding
                </Button>
              )}
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
