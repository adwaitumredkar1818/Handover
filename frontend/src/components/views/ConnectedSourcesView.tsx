"use client";

import React, { useState, useMemo } from "react";
import { useRouter } from "next/navigation";
import {
  PlugZap,
  Plus,
  ShieldCheck,
  CheckCircle2,
  RefreshCw,
  KeyRound,
  AlertCircle,
  Upload,
  Plug,
  ExternalLink,
  Layers,
  FileText,
  Clock,
  Sparkles,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { useLiveApp } from "../../context/LiveAppContext";
import { SourceIcon, type BrandSourceType } from "../brand/brand";
import { Card, Button, StatusBadge, Badge } from "../ui";

interface SourceCardMeta {
  type: BrandSourceType;
  label: string;
  description: string;
  frequency: string;
}

const SOURCE_CATALOG: SourceCardMeta[] = [
  {
    type: "github",
    label: "GitHub",
    description: "Synchronises commits, pull requests, issues, discussions, and code manifests with full commit provenance.",
    frequency: "Continuous / Webhook",
  },
  {
    type: "jira",
    label: "Jira",
    description: "Ingests sprint backlogs, epics, user stories, issue comments, issue transitions, and blocker histories.",
    frequency: "Hourly poll",
  },
  {
    type: "slack",
    label: "Slack",
    description: "Captures channels, conversation threads, design decisions, and ad-hoc knowledge shared across discussions.",
    frequency: "Real-time stream",
  },
  {
    type: "docs",
    label: "PDF & DOCX Uploads",
    description: "Digitally extracts text and runs OCR on project specs, architecture records, handbooks, and team documentation.",
    frequency: "On-demand upload",
  },
  {
    type: "confluence",
    label: "Confluence",
    description: "Scheduled in platform roadmap. Automated discovery and sync currently in active development.",
    frequency: "Roadmap Q2",
  },
  {
    type: "gdrive",
    label: "Google Drive",
    description: "Scheduled in platform roadmap. Automated discovery and sync currently in active development.",
    frequency: "Roadmap Q2",
  },
];

export function ConnectedSourcesView() {
  const router = useRouter();
  const {
    activeOrg,
    activeProject,
    orgConnections,
    sourceMappings,
    evidenceList,
    evidenceMetrics,
    isLoadingSources,
    setIsAddSourceModalOpen,
    setIsUploadModalOpen,
    openConnectSourceModal,
    triggerSync,
    refreshSources,
    refreshEvidence,
  } = useLiveApp();

  const [syncingProvider, setSyncingProvider] = useState<string | null>(null);
  const [showOrgCredentials, setShowOrgCredentials] = useState(true);

  // Filter mappings & evidence per provider
  const allGithubMappings = useMemo(
    () => sourceMappings.filter((m) => m.provider === "github"),
    [sourceMappings]
  );
  const githubMapping = allGithubMappings[0];
  const jiraMapping = useMemo(
    () => sourceMappings.find((m) => m.provider === "jira"),
    [sourceMappings]
  );
  const slackMapping = useMemo(
    () => sourceMappings.find((m) => m.provider === "slack"),
    [sourceMappings]
  );

  const githubEvidence = useMemo(
    () =>
      evidenceList.filter((e) => {
        const prov = (e.provider || e.source_provider || e.source_type || "").toLowerCase();
        const cat = (e.category || "").toLowerCase();
        return (
          prov === "github" ||
          cat === "commit" ||
          cat === "pull_request" ||
          cat === "pr" ||
          cat === "source_code" ||
          (e.title || "").toLowerCase().startsWith("github")
        );
      }),
    [evidenceList]
  );

  const docEvidence = useMemo(
    () =>
      evidenceList.filter((e) => {
        const prov = (e.provider || e.source_provider || e.source_type || "").toLowerCase();
        const cat = (e.category || "").toLowerCase();
        return (
          prov === "upload" ||
          prov === "local_upload" ||
          prov === "project" ||
          prov === "pdf" ||
          prov === "docx" ||
          cat.includes("document") ||
          cat.includes("pdf") ||
          cat.includes("docx") ||
          cat === "team_roster" ||
          cat === "meeting_notes" ||
          cat === "project_document"
        );
      }),
    [evidenceList]
  );

  const jiraEvidence = useMemo(
    () =>
      evidenceList.filter(
        (e) => (e.provider || e.source_provider || e.source_type || "").toLowerCase() === "jira"
      ),
    [evidenceList]
  );

  const slackEvidence = useMemo(
    () =>
      evidenceList.filter(
        (e) => (e.provider || e.source_provider || e.source_type || "").toLowerCase() === "slack"
      ),
    [evidenceList]
  );

  // Check any connection error or reauth needed
  const attentionConnections = useMemo(
    () =>
      orgConnections.filter(
        (conn) =>
          conn.status === "reauth_required" ||
          conn.status === "error" ||
          Boolean(conn.last_error_code)
      ),
    [orgConnections]
  );

  const handleSyncProvider = async (provider: string, mappingId?: string) => {
    if (!mappingId) {
      if (activeProject) {
        router.push(`/projects/${activeProject.id}/evidence?provider=${provider}`);
      } else {
        router.push(`/evidence?provider=${provider}`);
      }
      return;
    }
    setSyncingProvider(provider);
    try {
      await triggerSync(mappingId);
    } finally {
      setSyncingProvider(null);
    }
  };

  return (
    <div className="space-y-6">
      {/* 1. Header with Breadcrumb and Actions */}
      <div className="bg-white rounded-xl border border-[#DCE3EB] p-5 shadow-2xs flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold text-[#4774A9] uppercase tracking-wider">
            <span>Administration</span>
            <span className="w-1.5 h-1.5 rounded-full bg-[#249E91]" />
            <span className="text-[#69778D] font-normal">{activeOrg?.name || "Organisation"}</span>
          </div>
          <h1 className="text-xl font-bold text-[#25334B] mt-1 tracking-tight">
            Connected Sources &amp; Authorisations
          </h1>
          <p className="text-xs text-[#69778D] mt-0.5">
            Manage organization-wide OAuth connections, delegated personal access tokens, and external tool credentials.
          </p>
        </div>

        <div className="flex items-center gap-2.5 shrink-0">
          <button
            type="button"
            onClick={() => {
              void refreshSources();
              void refreshEvidence();
            }}
            disabled={isLoadingSources}
            className="px-3 py-2 rounded-lg border border-[#DCE3EB] bg-white hover:bg-slate-50 text-[#25334B] text-xs font-semibold flex items-center gap-1.5 transition-colors shadow-2xs"
            title="Refresh connection status"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoadingSources ? "animate-spin text-[#4774A9]" : "text-[#69778D]"}`} />
            <span className="hidden sm:inline">Refresh</span>
          </button>
          <button
            type="button"
            onClick={() => setIsAddSourceModalOpen(true)}
            className="px-4 py-2 rounded-lg bg-[#4774A9] hover:bg-[#365F92] text-white text-xs font-semibold flex items-center gap-2 transition-colors shadow-xs"
          >
            <Plus className="w-4 h-4" />
            <span>Connect New Source</span>
          </button>
        </div>
      </div>

      {/* 2. Security Guidance Banner */}
      <div className="p-4 rounded-xl bg-emerald-50/70 border border-emerald-200 flex items-start gap-3 text-xs text-emerald-950">
        <ShieldCheck className="w-5 h-5 text-[#249E91] shrink-0 mt-0.5" />
        <div className="leading-relaxed">
          <span className="font-semibold">Zero Credential Leakage:</span> All external tokens (GitHub PATs, Jira API keys, OAuth tokens) are encrypted symmetrically at rest in PostgreSQL using AES-256-GCM via <code>TOKEN_ENCRYPTION_KEY</code> and are never returned to client-side code.
        </div>
      </div>

      {/* 3. Attention / Re-auth Banner (if any connection has errors) */}
      {attentionConnections.length > 0 && (
        <div className="space-y-3">
          {attentionConnections.map((conn) => (
            <div
              key={conn.id}
              className="p-4 rounded-xl bg-amber-50/80 border border-amber-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs text-amber-950"
            >
              <div className="flex items-start gap-3">
                <AlertCircle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
                <div>
                  <div className="font-bold text-amber-900">
                    A source connection requires attention: {conn.display_name}
                  </div>
                  <p className="text-amber-800 text-[11px] mt-0.5">
                    {conn.last_error_summary ||
                      (conn.last_error_code === "GITHUB_REPO_ACCESS_REVOKED"
                        ? "GitHub personal access token has been revoked or has lost permission to the mapped repository."
                        : "Authorisation credentials have expired or require re-confirmation.")}
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setIsAddSourceModalOpen(true)}
                className="px-3 py-1.5 rounded-lg bg-amber-600 hover:bg-amber-700 text-white text-xs font-semibold inline-flex items-center gap-1.5 self-start sm:self-center transition-colors shadow-2xs shrink-0"
              >
                <KeyRound className="w-3.5 h-3.5" />
                <span>Reconnect {conn.provider === "github" ? "GitHub" : conn.provider}</span>
              </button>
            </div>
          ))}
        </div>
      )}

      {/* 4. Beautiful Source Grid Cards (6 Catalog Items + 1 Request Integration) */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {SOURCE_CATALOG.map((meta) => {
          const isPlanned = meta.type === "confluence" || meta.type === "gdrive";
          let isConnected = false;
          let recordCount = 0;
          let scopeItems: string[] = [];
          let lastSync = "—";
          let mappingId: string | undefined = undefined;

          if (meta.type === "github") {
            isConnected = allGithubMappings.length > 0 || githubEvidence.length > 0;
            const gitMetricsCount = evidenceMetrics?.by_provider?.["github"];
            recordCount = Math.max(gitMetricsCount ?? 0, githubEvidence.length);
            scopeItems = allGithubMappings
              .map((m) => m.external_resource_key || m.external_resource_name)
              .filter(Boolean) as string[];
            lastSync = isConnected ? "Recent" : "—";
            mappingId = githubMapping?.id;
          } else if (meta.type === "jira") {
            isConnected = Boolean(jiraMapping) || jiraEvidence.length > 0;
            recordCount = jiraEvidence.length;
            scopeItems = jiraMapping?.external_resource_name
              ? [jiraMapping.external_resource_name]
              : [];
            lastSync = isConnected ? "Recent" : "—";
            mappingId = jiraMapping?.id;
          } else if (meta.type === "slack") {
            isConnected = Boolean(slackMapping) || slackEvidence.length > 0;
            recordCount = slackEvidence.length;
            scopeItems = slackMapping?.external_resource_name
              ? [slackMapping.external_resource_name]
              : [];
            lastSync = isConnected ? "Recent" : "—";
            mappingId = slackMapping?.id;
          } else if (meta.type === "docs") {
            const docMetricsCount =
              (evidenceMetrics?.by_provider?.["local_upload"] ?? 0) +
              (evidenceMetrics?.by_provider?.["upload"] ?? 0) +
              (evidenceMetrics?.by_provider?.["project"] ?? 0) +
              (evidenceMetrics?.by_provider?.["pdf"] ?? 0) +
              (evidenceMetrics?.by_provider?.["docx"] ?? 0);
            recordCount = Math.max(docMetricsCount, docEvidence.length);
            isConnected = recordCount > 0 || docEvidence.length > 0;
            scopeItems = docEvidence.length
              ? docEvidence.map((d) => d.title).slice(0, 2)
              : [];
            lastSync = isConnected ? "Recent" : "—";
          }

          const isCurrentlySyncing = syncingProvider === meta.type;

          return (
            <Card key={meta.type} interactive={!isPlanned} className="flex flex-col p-5 h-full">
              {/* Top row: Source icon + Status badge */}
              <div className="flex items-start justify-between">
                <SourceIcon type={meta.type} size={44} />
                {isPlanned ? (
                  <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold bg-amber-50 text-amber-800 border border-amber-200">
                    Planned Integration
                  </span>
                ) : (
                  <StatusBadge status={isConnected ? "connected" : "disconnected"} />
                )}
              </div>

              {/* Title & Description */}
              <h3 className="mt-4 text-[15px] font-semibold text-navy">{meta.label}</h3>
              <p className="mt-1 flex-1 text-xs text-muted leading-relaxed">
                {meta.description}
              </p>

              {/* Stats Block or Placeholder */}
              {isPlanned ? (
                <p className="mt-4 rounded-xl border border-dashed border-amber-200 bg-amber-50/40 p-3 text-xs text-amber-800/80">
                  Scheduled in platform roadmap. Automated discovery and sync currently in development.
                </p>
              ) : isConnected ? (
                <dl className="mt-4 grid grid-cols-2 gap-2 rounded-xl bg-slate-50 p-3 text-xs">
                  <div>
                    <dt className="text-muted">Last sync</dt>
                    <dd className="mt-0.5 font-medium text-navy">{lastSync}</dd>
                  </div>
                  <div>
                    <dt className="text-muted">Records</dt>
                    <dd className="mt-0.5 font-medium text-navy">
                      {recordCount.toLocaleString()}{" "}
                      <span className="text-[10px] text-muted font-normal">
                        {meta.type === "github" ? "commits/PRs" : meta.type === "docs" ? "files" : "items"}
                      </span>
                    </dd>
                  </div>
                  <div className="col-span-2">
                    <dt className="text-muted">Scope</dt>
                    <dd className="mt-0.5 truncate font-medium text-navy" title={scopeItems.join(", ") || "—"}>
                      {scopeItems.join(", ") || (meta.type === "docs" ? "Project documents" : "Mapped resources")}
                    </dd>
                  </div>
                </dl>
              ) : (
                <p className="mt-4 rounded-xl border border-dashed border-line p-3 text-xs text-muted">
                  Not connected to active project workspace
                </p>
              )}

              {/* Action Buttons */}
              <div className="mt-4 flex items-center gap-2 pt-1 border-t border-slate-100">
                {isPlanned ? (
                  <Button
                    className="flex-1 opacity-60 cursor-not-allowed"
                    icon={Plug}
                    disabled={true}
                    size="sm"
                  >
                    Planned Integration
                  </Button>
                ) : isConnected ? (
                  <>
                    <Button
                      variant="secondary"
                      size="sm"
                      className="flex-1"
                      disabled={isCurrentlySyncing}
                      onClick={() => {
                        if (meta.type === "docs") {
                          if (activeProject) {
                            router.push(`/projects/${activeProject.id}/evidence?provider=upload`);
                          } else {
                            router.push(`/evidence?provider=upload`);
                          }
                        } else {
                          void handleSyncProvider(meta.type, mappingId);
                        }
                      }}
                    >
                      {isCurrentlySyncing ? (
                        <>
                          <RefreshCw className="w-3.5 h-3.5 animate-spin mr-1.5" />
                          <span>Syncing...</span>
                        </>
                      ) : meta.type === "docs" ? (
                        "View Evidence"
                      ) : (
                        "Sync Now"
                      )}
                    </Button>

                    {meta.type === "docs" && (
                      <Button
                        variant="subtle"
                        size="sm"
                        icon={Upload}
                        onClick={() => setIsUploadModalOpen(true)}
                      >
                        Upload
                      </Button>
                    )}

                    {meta.type === "github" && (
                      <Button
                        variant="subtle"
                        size="sm"
                        icon={Plus}
                        onClick={() => openConnectSourceModal("github")}
                      >
                        Add repo
                      </Button>
                    )}
                  </>
                ) : (
                  <Button
                    className="flex-1"
                    size="sm"
                    icon={meta.type === "docs" ? Upload : Plug}
                    onClick={() => {
                      if (meta.type === "docs") {
                        setIsUploadModalOpen(true);
                      } else {
                        openConnectSourceModal(meta.type);
                      }
                    }}
                  >
                    {meta.type === "docs" ? "Upload files" : "Connect"}
                  </Button>
                )}
              </div>
            </Card>
          );
        })}

        {/* 7th Card: Other Authorised Sources */}
        <Card className="flex flex-col items-center justify-center border-dashed p-5 text-center min-h-[260px]">
          <span className="flex size-11 items-center justify-center rounded-xl bg-slate-100 text-slate-500 mb-2">
            <Plus className="size-5" />
          </span>
          <h3 className="text-sm font-semibold text-navy">Other Authorised Sources</h3>
          <p className="mt-1 text-xs text-muted max-w-xs leading-relaxed">
            Request Linear, GitLab, Notion, or custom API connectors for your workspace.
          </p>
          <Button
            variant="ghost"
            size="sm"
            className="mt-4 text-[#4774A9]"
            onClick={() => setIsAddSourceModalOpen(true)}
          >
            Request integration
          </Button>
        </Card>
      </div>

      {/* 5. Organization Credentials & Encryption Management */}
      <div className="bg-white rounded-xl border border-[#DCE3EB] shadow-2xs overflow-hidden">
        <button
          type="button"
          onClick={() => setShowOrgCredentials(!showOrgCredentials)}
          className="w-full px-5 py-3.5 bg-[#F8FAFC] border-b border-[#DCE3EB] flex items-center justify-between text-xs font-semibold text-[#69778D] hover:bg-slate-100/70 transition-colors"
        >
          <div className="flex items-center gap-2">
            <span>Authorised Organisation Credentials</span>
            <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-200 text-slate-700">
              {orgConnections.length}
            </span>
          </div>
          <div className="flex items-center gap-1.5 text-[11px] text-[#4774A9]">
            <span>{showOrgCredentials ? "Hide Details" : "Show Details"}</span>
            {showOrgCredentials ? (
              <ChevronUp className="w-3.5 h-3.5" />
            ) : (
              <ChevronDown className="w-3.5 h-3.5" />
            )}
          </div>
        </button>

        {showOrgCredentials && (
          <div>
            {orgConnections.length === 0 ? (
              <div className="p-8 text-center">
                <PlugZap className="w-8 h-8 text-[#69778D] opacity-40 mx-auto mb-2" />
                <div className="text-xs font-semibold text-[#25334B]">No Stored Credentials</div>
                <p className="text-[11px] text-[#69778D] mt-1">
                  Connect GitHub or Jira to store encrypted authentication credentials in your organisation.
                </p>
              </div>
            ) : (
              <div className="divide-y divide-[#DCE3EB]">
                {orgConnections.map((conn) => (
                  <div
                    key={conn.id}
                    className="p-4 flex items-center justify-between hover:bg-[#F4F6F9]/50 transition-colors"
                  >
                    <div className="flex items-center gap-3">
                      <div className="w-9 h-9 rounded-lg bg-[#253650] text-white flex items-center justify-center font-bold text-xs shrink-0">
                        {conn.provider === "github" ? "GH" : conn.provider === "jira" ? "JR" : "SL"}
                      </div>
                      <div>
                        <div className="font-semibold text-xs text-[#25334B]">
                          {conn.display_name}
                        </div>
                        <div className="text-[10px] text-[#69778D]">
                          Provider: {conn.provider.toUpperCase()} · ID: {conn.id.slice(0, 8)}...
                          {conn.account_identifier && ` · @${conn.account_identifier}`}
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-3">
                      {conn.status === "reauth_required" || conn.status === "error" || conn.last_error_code ? (
                        <div className="flex items-center gap-2">
                          <span
                            title={conn.last_error_summary || conn.last_error_code || "Re-authorisation required"}
                            className="text-[10px] uppercase font-bold px-2 py-0.5 rounded-full bg-amber-50 text-amber-800 border border-amber-200 inline-flex items-center gap-1"
                          >
                            <AlertCircle className="w-3 h-3 text-amber-600" />
                            {conn.last_error_code === "GITHUB_REPO_ACCESS_REVOKED"
                              ? "Access Revoked"
                              : conn.status === "reauth_required"
                              ? "Re-auth Required"
                              : conn.status}
                          </span>
                          <button
                            type="button"
                            onClick={() => setIsAddSourceModalOpen(true)}
                            className="px-2.5 py-1 rounded-md bg-blue-600 hover:bg-blue-700 text-white text-[11px] font-semibold inline-flex items-center gap-1"
                          >
                            <KeyRound className="w-3 h-3" />
                            Reconnect {conn.provider === "github" ? "GitHub" : conn.provider}
                          </button>
                        </div>
                      ) : (
                        <>
                          <span className="text-[10px] uppercase font-bold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
                            {conn.status}
                          </span>
                          <span className="text-[11px] text-[#69778D] font-mono">
                            AES-256 Protected
                          </span>
                        </>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
