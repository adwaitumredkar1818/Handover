"use client";

import React, { useState, useEffect, useRef } from "react";
import {
  X,
  PlugZap,
  ShieldAlert,
  ArrowRight,
  AlertCircle,
  Lock,
  UploadCloud,
  FileText,
  CheckCircle2,
  ExternalLink,
  Info,
} from "lucide-react";
import { useLiveApp } from "../../context/LiveAppContext";
import { SourceIcon } from "../brand/brand";
import type { SourceType } from "../../lib/figmaStore";

type ConnectProviderTab = "github" | "jira" | "slack" | "docs" | "confluence" | "gdrive";

interface SourceTabConfig {
  id: ConnectProviderTab;
  label: string;
  badge?: string;
  description: string;
}

const TABS: SourceTabConfig[] = [
  { id: "github", label: "GitHub", description: "Repositories, commits, PRs, and code ownership" },
  { id: "jira", label: "Jira", description: "Issues, epics, sprints, and task history" },
  { id: "slack", label: "Slack", description: "Discussions, decisions, and incident channels" },
  { id: "docs", label: "PDF & DOCX", description: "Architecture records, runbooks, and specs" },
  { id: "confluence", label: "Confluence", description: "Documentation spaces and team knowledge" },
  { id: "gdrive", label: "Google Drive", description: "Authorised shared folders and docs" },
];

export function ConnectSourceModal() {
  const {
    isAddSourceModalOpen,
    setIsAddSourceModalOpen,
    initialSourceProvider,
    connectSource,
    createMapping,
    triggerSync,
    uploadDocument,
  } = useLiveApp();

  const [activeTab, setActiveTab] = useState<ConnectProviderTab>("github");

  // GitHub state
  const [githubAccount, setGithubAccount] = useState("");
  const [githubToken, setGithubToken] = useState("");
  const [githubRepo, setGithubRepo] = useState("");
  const [githubLabel, setGithubLabel] = useState("");

  // Jira state
  const [jiraEmail, setJiraEmail] = useState("");
  const [jiraToken, setJiraToken] = useState("");
  const [jiraProjectKey, setJiraProjectKey] = useState("");
  const [jiraLabel, setJiraLabel] = useState("");

  // Slack state
  const [slackDomain, setSlackDomain] = useState("");
  const [slackToken, setSlackToken] = useState("");
  const [slackChannel, setSlackChannel] = useState("");
  const [slackLabel, setSlackLabel] = useState("");

  // Confluence state
  const [confluenceDomain, setConfluenceDomain] = useState("");
  const [confluenceToken, setConfluenceToken] = useState("");
  const [confluenceSpaceKey, setConfluenceSpaceKey] = useState("");
  const [confluenceLabel, setConfluenceLabel] = useState("");

  // Google Drive state
  const [gdriveAccount, setGdriveAccount] = useState("");
  const [gdriveFolderId, setGdriveFolderId] = useState("");
  const [gdriveLabel, setGdriveLabel] = useState("");

  // Document Upload state
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [docCustomTitle, setDocCustomTitle] = useState("");
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Status & error state
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  useEffect(() => {
    if (isAddSourceModalOpen) {
      if (initialSourceProvider) {
        setActiveTab(initialSourceProvider as ConnectProviderTab);
      }
      setError(null);
      setSuccessMessage(null);
    }
  }, [isAddSourceModalOpen, initialSourceProvider]);

  if (!isAddSourceModalOpen) return null;

  // File drop handlers for docs tab
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      const ext = file.name.split(".").pop()?.toLowerCase();
      if (ext !== "pdf" && ext !== "docx") {
        setError("Only PDF and DOCX files are supported");
        return;
      }
      setSelectedFile(file);
      if (!docCustomTitle) {
        setDocCustomTitle(file.name.replace(/\.[^/.]+$/, ""));
      }
      setError(null);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const file = e.dataTransfer.files[0];
      const ext = file.name.split(".").pop()?.toLowerCase();
      if (ext !== "pdf" && ext !== "docx") {
        setError("Only PDF and DOCX files are supported");
        return;
      }
      setSelectedFile(file);
      if (!docCustomTitle) {
        setDocCustomTitle(file.name.replace(/\.[^/.]+$/, ""));
      }
      setError(null);
    }
  };

  // Submit Handler
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccessMessage(null);
    setIsSubmitting(true);

    try {
      if (activeTab === "docs") {
        if (!selectedFile) {
          setError("Please select a PDF or DOCX file to ingest");
          setIsSubmitting(false);
          return;
        }
        await uploadDocument(selectedFile, docCustomTitle.trim() || undefined);
        setSelectedFile(null);
        setDocCustomTitle("");
        setIsAddSourceModalOpen(false);
        return;
      }

      if (activeTab === "github") {
        if (!githubAccount.trim() || !githubToken.trim() || !githubRepo.trim()) {
          setError("Please fill in GitHub account handle, personal access token, and target repository");
          setIsSubmitting(false);
          return;
        }
        const cleanRepo = githubRepo.includes("/")
          ? githubRepo
              .split("/")
              .map((s) => s.trim())
              .filter(Boolean)
              .join("/")
          : githubRepo.trim();

        const conn = await connectSource("github", githubToken.trim(), githubAccount.trim());
        const mapping = await createMapping({
          source_connection_id: conn.id,
          external_resource_key: cleanRepo,
          external_resource_name: githubLabel.trim() || cleanRepo,
          external_resource_url: `https://github.com/${cleanRepo}`,
        });

        if (mapping?.id) {
          try {
            await triggerSync(mapping.id);
          } catch {
            // Background sync queued
          }
        }
        setIsAddSourceModalOpen(false);
        return;
      }

      if (activeTab === "jira") {
        if (!jiraEmail.trim() || !jiraToken.trim() || !jiraProjectKey.trim()) {
          setError("Please fill in Atlassian email, API token, and target Jira project key");
          setIsSubmitting(false);
          return;
        }
        const cleanKey = jiraProjectKey.trim().toUpperCase();
        const conn = await connectSource("jira", jiraToken.trim(), jiraEmail.trim());
        const mapping = await createMapping({
          source_connection_id: conn.id,
          external_resource_key: cleanKey,
          external_resource_name: jiraLabel.trim() || `Jira: ${cleanKey}`,
          external_resource_url: undefined,
        });

        if (mapping?.id) {
          try {
            await triggerSync(mapping.id);
          } catch {
            // Background sync queued
          }
        }
        setIsAddSourceModalOpen(false);
        return;
      }

      if (activeTab === "slack") {
        if (!slackDomain.trim() || !slackToken.trim() || !slackChannel.trim()) {
          setError("Please fill in Slack workspace domain, bot token, and target channel name/ID");
          setIsSubmitting(false);
          return;
        }
        const cleanChannel = slackChannel.trim().replace(/^#/, "");
        const conn = await connectSource("slack", slackToken.trim(), slackDomain.trim());
        const mapping = await createMapping({
          source_connection_id: conn.id,
          external_resource_key: cleanChannel,
          external_resource_name: slackLabel.trim() || `#${cleanChannel}`,
          external_resource_url: `https://${slackDomain.replace(/^https?:\/\//, "")}/archives/${cleanChannel}`,
        });

        if (mapping?.id) {
          try {
            await triggerSync(mapping.id);
          } catch {
            // Background sync queued
          }
        }
        setIsAddSourceModalOpen(false);
        return;
      }

      if (activeTab === "confluence") {
        // Confluence maps through Atlassian source connection
        if (!confluenceDomain.trim() || !confluenceToken.trim() || !confluenceSpaceKey.trim()) {
          setError("Please fill in Atlassian site domain, API token, and target Space Key");
          setIsSubmitting(false);
          return;
        }
        const cleanSpace = confluenceSpaceKey.trim().toUpperCase();
        const conn = await connectSource("jira", confluenceToken.trim(), confluenceDomain.trim());
        const mapping = await createMapping({
          source_connection_id: conn.id,
          external_resource_key: cleanSpace,
          external_resource_name: confluenceLabel.trim() || `Space: ${cleanSpace}`,
        });
        if (mapping?.id) {
          try {
            await triggerSync(mapping.id);
          } catch {
            // Background sync queued
          }
        }
        setIsAddSourceModalOpen(false);
        return;
      }

      if (activeTab === "gdrive") {
        setError("Google Drive OAuth connection requires administrator credentials setup.");
        setIsSubmitting(false);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to connect source or map resource");
    } finally {
      setIsSubmitting(false);
    }
  };

  const currentTabConfig: SourceTabConfig = TABS.find((t) => t.id === activeTab) ?? TABS[0]!;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-2xs p-4">
      <div className="w-full max-w-xl bg-white rounded-xl shadow-2xl border border-[#DCE3EB] overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="px-6 py-4 bg-[#F4F6F9] border-b border-[#DCE3EB] flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <SourceIcon type={activeTab as SourceType} size={32} />
            <div>
              <h2 className="text-sm font-bold text-[#25334B]">
                {activeTab === "docs" ? "Upload & Ingest Document Evidence" : `Connect ${currentTabConfig?.label || "Source"}`}
              </h2>
              <p className="text-[11px] text-[#69778D]">{currentTabConfig?.description || ""}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setIsAddSourceModalOpen(false)}
            className="p-1 rounded text-[#69778D] hover:text-[#25334B] hover:bg-slate-200/60 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Modal Body Form */}
        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-6 space-y-4">
          {error && (
            <div className="p-3 rounded-lg bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* 1. GITHUB TAB */}
          {activeTab === "github" && (
            <div className="space-y-4">
              <div className="p-3 rounded-lg bg-slate-50 border border-slate-200 flex items-start gap-3">
                <SourceIcon type="github" size={28} />
                <div className="text-xs">
                  <span className="font-semibold text-slate-800">GitHub Connector</span>
                  <p className="text-slate-500 text-[11px] mt-0.5">
                    Connect an authorised GitHub repository to ingest READMEs, architecture decisions, pull requests, issues, and commit histories.
                  </p>
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-[#25334B] mb-1">
                  GitHub Username / Organization Handle <span className="text-rose-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  value={githubAccount}
                  onChange={(e) => setGithubAccount(e.target.value)}
                  placeholder="e.g. shubham392007-sketch"
                  className="w-full px-3 py-2 rounded-lg border border-[#DCE3EB] text-xs focus:outline-none focus:ring-2 focus:ring-[#4774A9] text-[#25334B]"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-[#25334B] mb-1">
                  Personal Access Token (PAT) <span className="text-rose-500">*</span>
                </label>
                <input
                  type="password"
                  required
                  value={githubToken}
                  onChange={(e) => setGithubToken(e.target.value)}
                  placeholder="ghp_•••••••••••• or github_pat_••••••••••••"
                  className="w-full px-3 py-2 rounded-lg border border-[#DCE3EB] text-xs focus:outline-none focus:ring-2 focus:ring-[#4774A9] text-[#25334B]"
                />
                <div className="text-[11px] text-[#69778D] mt-1 flex items-center gap-1.5">
                  <Info className="w-3.5 h-3.5 text-[#4774A9] shrink-0" />
                  <span>Read-only scopes required: <code>repo</code>, <code>read:org</code>. Tokens are encrypted using AES-256-GCM.</span>
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-[#25334B] mb-1">
                  Target Repository (owner/repo) <span className="text-rose-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  value={githubRepo}
                  onChange={(e) => {
                    setGithubRepo(e.target.value);
                    if (!githubLabel) setGithubLabel(e.target.value);
                  }}
                  placeholder="e.g. shubham392007-sketch/HackMatrix-5.0-MISC02"
                  className="w-full px-3 py-2 rounded-lg border border-[#DCE3EB] text-xs focus:outline-none focus:ring-2 focus:ring-[#4774A9] text-[#25334B]"
                />
                <div className="text-[11px] text-[#69778D] mt-1">
                  Format must be <span className="font-mono text-[#25334B]">owner/repo</span>.
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-[#25334B] mb-1">
                  Display Label (Optional)
                </label>
                <input
                  type="text"
                  value={githubLabel}
                  onChange={(e) => setGithubLabel(e.target.value)}
                  placeholder="e.g. Core Service Repository"
                  className="w-full px-3 py-2 rounded-lg border border-[#DCE3EB] text-xs focus:outline-none focus:ring-2 focus:ring-[#4774A9] text-[#25334B]"
                />
              </div>
            </div>
          )}

          {/* 2. JIRA TAB */}
          {activeTab === "jira" && (
            <div className="space-y-4">
              <div className="p-3 rounded-lg bg-blue-50/60 border border-blue-200 flex items-start gap-3">
                <SourceIcon type="jira" size={28} />
                <div className="text-xs">
                  <span className="font-semibold text-slate-800">Jira Software Connector</span>
                  <p className="text-slate-500 text-[11px] mt-0.5">
                    Sync issues, tasks, blocker states, epics, and assignee histories with full provenance.
                  </p>
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-[#25334B] mb-1">
                  Atlassian Account Email <span className="text-rose-500">*</span>
                </label>
                <input
                  type="email"
                  required
                  value={jiraEmail}
                  onChange={(e) => setJiraEmail(e.target.value)}
                  placeholder="e.g. developer@company.com"
                  className="w-full px-3 py-2 rounded-lg border border-[#DCE3EB] text-xs focus:outline-none focus:ring-2 focus:ring-[#4774A9] text-[#25334B]"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-[#25334B] mb-1">
                  Atlassian API Token <span className="text-rose-500">*</span>
                </label>
                <input
                  type="password"
                  required
                  value={jiraToken}
                  onChange={(e) => setJiraToken(e.target.value)}
                  placeholder="API token generated from id.atlassian.com/manage-profile/security/api-tokens"
                  className="w-full px-3 py-2 rounded-lg border border-[#DCE3EB] text-xs focus:outline-none focus:ring-2 focus:ring-[#4774A9] text-[#25334B]"
                />
                <div className="text-[11px] text-[#69778D] mt-1 flex items-center gap-1.5">
                  <Info className="w-3.5 h-3.5 text-[#4774A9] shrink-0" />
                  <span>Requires read access to issues and projects (<code>read:jira-work</code>).</span>
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-[#25334B] mb-1">
                  Target Jira Project Key <span className="text-rose-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  value={jiraProjectKey}
                  onChange={(e) => {
                    setJiraProjectKey(e.target.value);
                    if (!jiraLabel) setJiraLabel(`Jira: ${e.target.value.toUpperCase()}`);
                  }}
                  placeholder="e.g. PAY or PROJ"
                  className="w-full px-3 py-2 rounded-lg border border-[#DCE3EB] text-xs focus:outline-none focus:ring-2 focus:ring-[#4774A9] text-[#25334B] uppercase"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-[#25334B] mb-1">
                  Display Label (Optional)
                </label>
                <input
                  type="text"
                  value={jiraLabel}
                  onChange={(e) => setJiraLabel(e.target.value)}
                  placeholder="e.g. Payments Product Backlog"
                  className="w-full px-3 py-2 rounded-lg border border-[#DCE3EB] text-xs focus:outline-none focus:ring-2 focus:ring-[#4774A9] text-[#25334B]"
                />
              </div>
            </div>
          )}

          {/* 3. SLACK TAB */}
          {activeTab === "slack" && (
            <div className="space-y-4">
              <div className="p-3 rounded-lg bg-pink-50/60 border border-pink-200 flex items-start gap-3">
                <SourceIcon type="slack" size={28} />
                <div className="text-xs">
                  <span className="font-semibold text-slate-800">Slack Communication Connector</span>
                  <p className="text-slate-500 text-[11px] mt-0.5">
                    Capture historical discussions, architectural decisions, and key technical context from designated channels.
                  </p>
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-[#25334B] mb-1">
                  Workspace Domain / Team URL <span className="text-rose-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  value={slackDomain}
                  onChange={(e) => setSlackDomain(e.target.value)}
                  placeholder="e.g. northwind-hq.slack.com"
                  className="w-full px-3 py-2 rounded-lg border border-[#DCE3EB] text-xs focus:outline-none focus:ring-2 focus:ring-[#4774A9] text-[#25334B]"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-[#25334B] mb-1">
                  Slack Bot User OAuth Token <span className="text-rose-500">*</span>
                </label>
                <input
                  type="password"
                  required
                  value={slackToken}
                  onChange={(e) => setSlackToken(e.target.value)}
                  placeholder="xoxb-••••••••••••-••••••••••••"
                  className="w-full px-3 py-2 rounded-lg border border-[#DCE3EB] text-xs focus:outline-none focus:ring-2 focus:ring-[#4774A9] text-[#25334B]"
                />
                <div className="text-[11px] text-[#69778D] mt-1 flex items-center gap-1.5">
                  <Info className="w-3.5 h-3.5 text-[#4774A9] shrink-0" />
                  <span>Read-only scopes required: <code>channels:read</code>, <code>channels:history</code>.</span>
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-[#25334B] mb-1">
                  Target Channel (Name or ID) <span className="text-rose-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  value={slackChannel}
                  onChange={(e) => {
                    setSlackChannel(e.target.value);
                    if (!slackLabel) setSlackLabel(e.target.value.startsWith("#") ? e.target.value : `#${e.target.value}`);
                  }}
                  placeholder="e.g. #architecture, #payments-oncall, or C01234567"
                  className="w-full px-3 py-2 rounded-lg border border-[#DCE3EB] text-xs focus:outline-none focus:ring-2 focus:ring-[#4774A9] text-[#25334B]"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-[#25334B] mb-1">
                  Display Label (Optional)
                </label>
                <input
                  type="text"
                  value={slackLabel}
                  onChange={(e) => setSlackLabel(e.target.value)}
                  placeholder="e.g. #architecture Discussions"
                  className="w-full px-3 py-2 rounded-lg border border-[#DCE3EB] text-xs focus:outline-none focus:ring-2 focus:ring-[#4774A9] text-[#25334B]"
                />
              </div>
            </div>
          )}

          {/* 4. PDF & DOCX DOCUMENTS TAB */}
          {activeTab === "docs" && (
            <div className="space-y-4">
              <div className="p-3 rounded-lg bg-sky-50/60 border border-sky-200 flex items-start gap-3">
                <SourceIcon type="docs" size={28} />
                <div className="text-xs">
                  <span className="font-semibold text-slate-800">Document Evidence Ingestion</span>
                  <p className="text-slate-500 text-[11px] mt-0.5">
                    Upload architecture diagrams, handover documents, runbooks, and design specs. Automated digital extraction and OCR are applied.
                  </p>
                </div>
              </div>

              {/* Drag and Drop Zone */}
              <div
                onDragOver={(e) => {
                  e.preventDefault();
                  setIsDragOver(true);
                }}
                onDragLeave={() => setIsDragOver(false)}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-all ${
                  isDragOver
                    ? "border-[#249E91] bg-teal-50/40"
                    : selectedFile
                    ? "border-[#249E91] bg-emerald-50/30"
                    : "border-[#DCE3EB] hover:border-[#4774A9] hover:bg-[#F4F6F9]"
                }`}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                  onChange={handleFileChange}
                  className="hidden"
                />

                {selectedFile ? (
                  <div className="flex flex-col items-center">
                    <CheckCircle2 className="w-8 h-8 text-[#249E91] mb-2" />
                    <div className="text-xs font-semibold text-[#25334B]">{selectedFile.name}</div>
                    <div className="text-[11px] text-[#69778D] mt-0.5">
                      {(selectedFile.size / 1024).toFixed(1)} KB · Ready to ingest
                    </div>
                  </div>
                ) : (
                  <div className="flex flex-col items-center">
                    <UploadCloud className="w-8 h-8 text-[#4774A9] mb-2" />
                    <div className="text-xs font-semibold text-[#25334B]">
                      Click to choose file or drag and drop
                    </div>
                    <p className="text-[11px] text-[#69778D] mt-1">
                      Supports PDF and DOCX files up to 50MB
                    </p>
                  </div>
                )}
              </div>

              <div>
                <label className="block text-xs font-semibold text-[#25334B] mb-1">
                  Document Title (Optional)
                </label>
                <input
                  type="text"
                  value={docCustomTitle}
                  onChange={(e) => setDocCustomTitle(e.target.value)}
                  placeholder="e.g. Architecture Blueprint & Handover Spec"
                  className="w-full px-3 py-2 rounded-lg border border-[#DCE3EB] text-xs focus:outline-none focus:ring-2 focus:ring-[#4774A9] text-[#25334B]"
                />
              </div>
            </div>
          )}

          {/* 5. CONFLUENCE TAB */}
          {activeTab === "confluence" && (
            <div className="space-y-4">
              <div className="p-3 rounded-lg bg-indigo-50/60 border border-indigo-200 flex items-start gap-3">
                <SourceIcon type="confluence" size={28} />
                <div className="text-xs">
                  <span className="font-semibold text-slate-800">Confluence Documentation Connector</span>
                  <p className="text-slate-500 text-[11px] mt-0.5">
                    Connect an Atlassian Confluence space to ingest wiki pages, meeting notes, runbooks, and design proposals.
                  </p>
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-[#25334B] mb-1">
                  Atlassian Site Domain <span className="text-rose-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  value={confluenceDomain}
                  onChange={(e) => setConfluenceDomain(e.target.value)}
                  placeholder="e.g. your-company.atlassian.net"
                  className="w-full px-3 py-2 rounded-lg border border-[#DCE3EB] text-xs focus:outline-none focus:ring-2 focus:ring-[#4774A9] text-[#25334B]"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-[#25334B] mb-1">
                  Atlassian API Token <span className="text-rose-500">*</span>
                </label>
                <input
                  type="password"
                  required
                  value={confluenceToken}
                  onChange={(e) => setConfluenceToken(e.target.value)}
                  placeholder="Atlassian API token from id.atlassian.com"
                  className="w-full px-3 py-2 rounded-lg border border-[#DCE3EB] text-xs focus:outline-none focus:ring-2 focus:ring-[#4774A9] text-[#25334B]"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-[#25334B] mb-1">
                  Target Confluence Space Key <span className="text-rose-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  value={confluenceSpaceKey}
                  onChange={(e) => {
                    setConfluenceSpaceKey(e.target.value);
                    if (!confluenceLabel) setConfluenceLabel(`Space: ${e.target.value.toUpperCase()}`);
                  }}
                  placeholder="e.g. ENG or ARCH"
                  className="w-full px-3 py-2 rounded-lg border border-[#DCE3EB] text-xs focus:outline-none focus:ring-2 focus:ring-[#4774A9] text-[#25334B] uppercase"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-[#25334B] mb-1">
                  Display Label (Optional)
                </label>
                <input
                  type="text"
                  value={confluenceLabel}
                  onChange={(e) => setConfluenceLabel(e.target.value)}
                  placeholder="e.g. Engineering Wiki Space"
                  className="w-full px-3 py-2 rounded-lg border border-[#DCE3EB] text-xs focus:outline-none focus:ring-2 focus:ring-[#4774A9] text-[#25334B]"
                />
              </div>
            </div>
          )}

          {/* 6. GOOGLE DRIVE TAB */}
          {activeTab === "gdrive" && (
            <div className="space-y-4">
              <div className="p-3 rounded-lg bg-amber-50/60 border border-amber-200 flex items-start gap-3">
                <SourceIcon type="gdrive" size={28} />
                <div className="text-xs">
                  <span className="font-semibold text-slate-800">Google Drive Shared Folder Connector</span>
                  <p className="text-slate-500 text-[11px] mt-0.5">
                    Connect an authorised Google Drive workspace or shared folder containing project assets and specifications.
                  </p>
                </div>
              </div>

              <div className="p-4 rounded-xl border border-dashed border-[#DCE3EB] text-center space-y-2">
                <div className="inline-flex p-2.5 rounded-full bg-amber-100 text-amber-700">
                  <ExternalLink className="w-5 h-5" />
                </div>
                <h4 className="text-xs font-semibold text-slate-800">Google Workspace Enterprise Connector</h4>
                <p className="text-[11px] text-slate-500 max-w-sm mx-auto">
                  Google Drive synchronization requires setting up Google Cloud OAuth credentials with read-only Drive scopes (<code>drive.readonly</code>).
                </p>
              </div>

              <div>
                <label className="block text-xs font-semibold text-[#25334B] mb-1">
                  Google Workspace Account Email
                </label>
                <input
                  type="email"
                  value={gdriveAccount}
                  onChange={(e) => setGdriveAccount(e.target.value)}
                  placeholder="e.g. team-leads@company.com"
                  className="w-full px-3 py-2 rounded-lg border border-[#DCE3EB] text-xs focus:outline-none focus:ring-2 focus:ring-[#4774A9] text-[#25334B]"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-[#25334B] mb-1">
                  Shared Folder ID
                </label>
                <input
                  type="text"
                  value={gdriveFolderId}
                  onChange={(e) => setGdriveFolderId(e.target.value)}
                  placeholder="e.g. 1a2B3c4D5e6F7g8H9i0J"
                  className="w-full px-3 py-2 rounded-lg border border-[#DCE3EB] text-xs focus:outline-none focus:ring-2 focus:ring-[#4774A9] text-[#25334B]"
                />
              </div>
            </div>
          )}

          {/* ACL Boundary & Encryption Notice */}
          <div className="p-3 rounded-lg bg-amber-50/70 border border-amber-200 flex items-start gap-2.5 text-amber-950 text-[11px] leading-relaxed">
            <ShieldAlert className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
            <div>
              <span className="font-semibold">Project Membership != Source Access:</span> The backend strictly verifies delegated source access before indexing or answering queries. Users without access to this source cannot read its raw evidence.
            </div>
          </div>

          {/* Footer Controls */}
          <div className="pt-3 flex items-center justify-between border-t border-[#DCE3EB]">
            <div className="flex items-center gap-1.5 text-[11px] text-[#249E91] font-semibold">
              <Lock className="w-3.5 h-3.5" />
              <span>AES-256 Envelope Encrypted</span>
            </div>
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => setIsAddSourceModalOpen(false)}
                className="px-4 py-2 rounded-lg border border-[#DCE3EB] text-xs font-semibold text-[#69778D] hover:bg-[#F4F6F9]"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isSubmitting}
                className="px-4 py-2 rounded-lg bg-[#4774A9] hover:bg-[#365F92] text-white text-xs font-semibold flex items-center gap-1.5 transition-colors disabled:opacity-50"
              >
                <span>
                  {isSubmitting
                    ? "Connecting & Verifying..."
                    : activeTab === "docs"
                    ? "Upload & Ingest Evidence"
                    : "Connect & Map Resource"}
                </span>
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
