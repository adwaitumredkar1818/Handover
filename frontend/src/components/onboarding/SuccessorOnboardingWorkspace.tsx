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
  Database,
  FileText,
  FolderKanban,
  Loader2,
  PackageCheck,
  ShieldCheck,
  Sparkles,
  Users,
} from "lucide-react";
import { AppLayout } from "../layout/AppLayout";
import { Card, CardHeader, Button, Badge } from "../ui";
import { useLiveApp } from "../../context/LiveAppContext";
import { api } from "../../lib/api";
import type {
  EvidenceSummary,
  Project,
  ProjectMember,
  ProjectOverview,
  ProjectSourceMapping,
} from "../../lib/types";

interface HandoverCaseSummary {
  id: string;
  project_id: string;
  title: string;
  status: string;
  version: number;
  created_at: string;
  updated_at: string;
  departing_member_id?: string;
  successor_id?: string;
}

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

  const [project, setProject] = useState<Project | null>(null);
  const [overview, setOverview] = useState<ProjectOverview | null>(null);
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [findings, setFindings] = useState<Record<string, unknown>[]>([]);
  const [findingsTotal, setFindingsTotal] = useState(0);
  const [evidence, setEvidence] = useState<EvidenceSummary[]>([]);
  const [sources, setSources] = useState<ProjectSourceMapping[]>([]);
  const [handoverCases, setHandoverCases] = useState<HandoverCaseSummary[]>([]);

  const [completedSteps, setCompletedSteps] = useState<Record<string, boolean>>(
    {}
  );

  const storageKey = `handover_onboarding_completed_${projectId}`;

  const markStepDone = (id: string) => {
    setCompletedSteps((prev) => {
      const next = { ...prev, [id]: true };
      if (typeof window !== "undefined") {
        try {
          localStorage.setItem(storageKey, JSON.stringify(next));
        } catch {
          // ignore
        }
      }
      return next;
    });
    // Canonical backend database persistence
    void api.onboarding.updateStep(projectId, id, true).catch(() => {});
  };

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

      // Merge server-persisted onboarding progress with any local storage cache
      const mergedCompleted: Record<string, boolean> = {
        ...(onboardingRes?.completed_steps || {}),
      };
      if (typeof window !== "undefined") {
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
    } catch (err: unknown) {
      setErrorMessage(
        err instanceof Error
          ? err.message
          : "Unable to load project onboarding details."
      );
    } finally {
      setIsLoading(false);
    }
  }, [projectId, setActiveProject]);

  useEffect(() => {
    void loadWorkspaceData();
  }, [loadWorkspaceData]);

  const myMemberRecord = useMemo(
    () => members.find((m) => m.user_id === user?.id) || null,
    [members, user?.id]
  );

  const myRoleKey = myMemberRecord?.role_name || "project_member";
  const roleInfo =
    ROLE_CAPABILITIES[myRoleKey] ?? ROLE_CAPABILITIES.project_member!;

  const isExplicitSuccessor = useMemo(() => {
    if (!user?.id) return false;
    return (
      overview?.successor?.id === user.id ||
      myMemberRecord?.transition_role === "incoming_assignee" ||
      myRoleKey === "incoming_assignee"
    );
  }, [user?.id, overview?.successor?.id, myMemberRecord?.transition_role, myRoleKey]);

  const currentStep = ONBOARDING_STEPS[stepIndex] ?? ONBOARDING_STEPS[0];

  const handleNext = () => {
    markStepDone(currentStep.id);
    if (stepIndex < ONBOARDING_STEPS.length - 1) {
      setStepIndex((i) => i + 1);
    }
  };

  const handleCompleteOnboarding = () => {
    markStepDone("complete");
    router.push(`/projects/${projectId}`);
  };

  return (
    <AppLayout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex flex-col justify-between gap-4 rounded-2xl border border-line bg-white p-5 shadow-2xs sm:flex-row sm:items-center">
          <div>
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-brand">
              <Sparkles className="size-3.5" />
              <span>
                {isExplicitSuccessor
                  ? "Successor Onboarding & Continuation"
                  : "Project Onboarding & Orientation"}
              </span>
            </div>
            <h1 className="mt-1 text-xl font-bold tracking-tight text-navy">
              {project ? project.name : "Project Onboarding"}
            </h1>
            <p className="mt-0.5 text-xs text-muted">
              Step {stepIndex + 1} of {ONBOARDING_STEPS.length}:{" "}
              {currentStep.title}
            </p>
          </div>

          <div className="flex items-center gap-2">
            <Link href={`/projects/${projectId}`}>
              <Button variant="secondary" size="sm" icon={ArrowLeft}>
                Skip to Project
              </Button>
            </Link>
          </div>
        </div>

        {isLoading ? (
          <Card className="flex items-center justify-center p-12 text-sm text-muted">
            <Loader2 className="mr-2 size-5 animate-spin text-brand" />
            Loading real project context...
          </Card>
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
                            ? "bg-brand/10 text-brand font-semibold"
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
                  <div className="rounded-xl border border-line bg-slate-50/70 p-4 text-xs text-navy space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone="blue">{project.status}</Badge>
                      {project.target_handover_date && (
                        <span className="text-muted">
                          Target handover:{" "}
                          <strong>
                            {new Date(
                              project.target_handover_date
                            ).toLocaleDateString()}
                          </strong>
                        </span>
                      )}
                    </div>
                    <p className="leading-relaxed text-muted">
                      {project.description ||
                        "No project description has been recorded yet."}
                    </p>
                  </div>

                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="rounded-xl border border-line p-4 text-xs">
                      <p className="font-semibold text-navy">
                        Departing Owner
                      </p>
                      <p className="mt-1 text-muted">
                        {overview?.departing_member
                          ? `${overview.departing_member.full_name} (${overview.departing_member.email})`
                          : "Not currently designated"}
                      </p>
                    </div>
                    <div className="rounded-xl border border-line p-4 text-xs">
                      <p className="font-semibold text-navy">
                        Designated Successor
                      </p>
                      <p className="mt-1 text-muted">
                        {overview?.successor
                          ? `${overview.successor.full_name} (${overview.successor.email})`
                          : "Not currently designated"}
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {currentStep.id === "role" && (
                <div className="space-y-4">
                  <CardHeader
                    title="Your Role & Permissions"
                    subtitle={`Assigned role: ${roleInfo.label}`}
                    icon={ShieldCheck}
                  />
                  <p className="text-xs leading-relaxed text-muted">
                    {roleInfo.summary}
                  </p>
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
                    <strong>Source Access Boundary:</strong> Project membership
                    does not automatically grant access to private external
                    repositories or restricted channels connected by another
                    user. Evidence visibility is strictly ACL-enforced.
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
                      No reconstructed knowledge findings exist for this project
                      yet. Upload documents or sync sources to begin
                      reconstruction.
                    </div>
                  ) : (
                    <ul className="space-y-2.5">
                      {findings.slice(0, 6).map((item, idx) => (
                        <li
                          key={String(item.id || idx)}
                          className="rounded-xl border border-line p-3.5 text-xs"
                        >
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <span className="font-semibold text-navy">
                              {String(item.title || item.summary || "Finding")}
                            </span>
                            {typeof item.domain === "string" && (
                              <Badge tone="blue">{item.domain}</Badge>
                            )}
                          </div>
                          {typeof item.description === "string" && (
                            <p className="mt-1 line-clamp-2 text-muted">
                              {item.description}
                            </p>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                  <Link
                    href={`/projects/${projectId}/knowledge`}
                    className="inline-block text-xs font-semibold text-brand hover:underline"
                  >
                    Open full Knowledge Intelligence →
                  </Link>
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
                      No connected sources or uploaded evidence items are
                      available yet in your authorised scope.
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {sources.length > 0 && (
                        <div className="space-y-1.5">
                          <p className="text-xs font-semibold text-navy">
                            Mapped Sources
                          </p>
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
                            <li
                              key={ev.id}
                              className="flex items-center justify-between gap-2 rounded-xl border border-line p-3 text-xs"
                            >
                              <div className="flex items-center gap-2 min-w-0">
                                <FileText className="size-4 shrink-0 text-brand" />
                                <span className="truncate font-medium text-navy">
                                  {ev.title}
                                </span>
                              </div>
                              <Badge tone="gray">{ev.provider}</Badge>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )}
                  <Link
                    href={`/projects/${projectId}/evidence`}
                    className="inline-block text-xs font-semibold text-brand hover:underline"
                  >
                    Open Evidence Center →
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
                      No handover packages have been generated for this project
                      yet. Handover packages require human verification and
                      designated reviewer approval before sharing.
                    </div>
                  ) : (
                    <ul className="space-y-2.5">
                      {handoverCases.map((hc) => (
                        <li
                          key={hc.id}
                          className="flex items-center justify-between gap-3 rounded-xl border border-line p-3.5 text-xs"
                        >
                          <div>
                            <p className="font-semibold text-navy">
                              {hc.title}
                            </p>
                            <p className="text-muted">
                              Version {hc.version} · Updated{" "}
                              {new Date(hc.updated_at).toLocaleDateString()}
                            </p>
                          </div>
                          <Badge tone="blue">{hc.status}</Badge>
                        </li>
                      ))}
                    </ul>
                  )}
                  <Link
                    href={`/projects/${projectId}/handovers`}
                    className="inline-block text-xs font-semibold text-brand hover:underline"
                  >
                    Open Handover Workspace →
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
                    Ask questions about this project&apos;s architecture,
                    decisions, risks, or open work. Every answer is grounded
                    strictly in evidence you are authorised to read and includes
                    explicit citations and uncertainty disclosures.
                  </p>
                  <div className="space-y-2">
                    {[
                      "What are the most critical architectural decisions and their rationale?",
                      "Which open bugs, blockers, or operational risks need immediate attention?",
                      "What responsibilities and dependencies am I taking over?",
                    ].map((prompt) => (
                      <div
                        key={prompt}
                        className="rounded-xl border border-line bg-slate-50/70 p-3 text-xs text-navy"
                      >
                        &ldquo;{prompt}&rdquo;
                      </div>
                    ))}
                  </div>
                  <Link href="/assistant">
                    <Button variant="primary" size="sm" icon={Bot}>
                      Open Knowledge Assistant
                    </Button>
                  </Link>
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
                    You have reviewed your project scope, RBAC permissions,
                    available knowledge, evidence boundaries, and handover
                    status. You can revisit this onboarding guide anytime from
                    the project workspace.
                  </p>
                  <div className="flex flex-wrap items-center gap-3 pt-2">
                    <Button
                      variant="primary"
                      icon={ArrowRight}
                      onClick={handleCompleteOnboarding}
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
                    onClick={handleNext}
                  >
                    Save &amp; Continue
                  </Button>
                ) : (
                  <Button
                    variant="primary"
                    size="sm"
                    icon={CheckCircle2}
                    onClick={handleCompleteOnboarding}
                  >
                    Finish Onboarding
                  </Button>
                )}
              </div>
            </Card>
          </div>
        )}
      </div>
    </AppLayout>
  );
}
