"use client";

import React, { useState, useEffect, useRef } from "react";
import {
  X,
  ArrowRight,
  AlertCircle,
  Lock,
  UploadCloud,
  FileText,
  CheckCircle2,
  ExternalLink,
  Info,
  Search,
  CheckSquare,
  Square,
  Loader2,
  RefreshCw,
  Layers,
  Users,
  Calendar,
  Eye,
  EyeOff,
  ChevronDown,
  ChevronUp,
  Check,
  GitBranch,
  GitCommit,
  GitPullRequest,
  HelpCircle,
  Code2,
  ShieldCheck,
  Tag,
  CircleAlert,
  Plus,
} from "lucide-react";
import { useLiveApp } from "../../context/LiveAppContext";
import { SourceIcon } from "../brand/brand";
import { api } from "../../lib/api";
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
  { id: "docs", label: "PDF & DOCX", description: "Team rosters, meeting notes, specs, and runbooks" },
  { id: "confluence", label: "Confluence", badge: "Planned", description: "Documentation spaces (Planned Integration)" },
  { id: "gdrive", label: "Google Drive", badge: "Planned", description: "Authorised shared folders (Planned Integration)" },
];

export function ConnectSourceModal() {
  const {
    isAddSourceModalOpen,
    setIsAddSourceModalOpen,
    initialSourceProvider,
    activeOrg,
    organisations,
    setActiveOrg,
    projects,
    activeProject,
    setActiveProject,
    createProject,
    connectSource,
    addSourceMappings,
    triggerSync,
    refreshSources,
    refreshEvidence,
    orgConnections,
    addToast,
  } = useLiveApp();

  const [activeTab, setActiveTab] = useState<ConnectProviderTab>("github");

  // Multi-step flow state: "credentials" | "select_resources" | "configure_scope" | "confirm"
  type FlowStep = "credentials" | "select_resources" | "configure_scope" | "confirm";
  const [step, setStep] = useState<FlowStep>("credentials");
  const changeStep = (s: FlowStep) => {
    setStep(s);
    setError(null);
  };
  const [activeConnectionId, setActiveConnectionId] = useState<string | null>(null);

  // Resolved active connection (explicit or from existing organisation connections)
  const existingActiveConnection = orgConnections.find(
    (c) => c.provider === activeTab && c.status === "active"
  );
  const resolvedConnectionId = activeConnectionId || existingActiveConnection?.id || null;

  // Target project workspace state & inline creator
  const [selectedProjectId, setSelectedProjectId] = useState<string>("");
  const [isCreatingProject, setIsCreatingProject] = useState(false);
  const [newProjectName, setNewProjectName] = useState("");
  const [newProjectDescription, setNewProjectDescription] = useState("");
  const [showCreateProjectInline, setShowCreateProjectInline] = useState(false);

  // Determined target project: explicitly selected in modal -> workspace active -> first org project
  const targetProject =
    (selectedProjectId ? projects.find((p) => p.id === selectedProjectId) : null) ??
    activeProject ??
    (projects.length > 0 ? projects[0] : null);

  const effectiveProjectId = targetProject?.id ?? "";

  // GitHub state
  const [githubAccount, setGithubAccount] = useState("");
  const [githubToken, setGithubToken] = useState("");
  const [showGithubToken, setShowGithubToken] = useState(false);
  const [showPermGuide, setShowPermGuide] = useState(false);
  const [githubResolvedAccount, setGithubResolvedAccount] = useState("");
  const [githubFilterType, setGithubFilterType] = useState<"all" | "private" | "public" | "owned">("all");
  const [discoveredRepos, setDiscoveredRepos] = useState<
    Array<{
      external_resource_id: string;
      full_name: string;
      name: string;
      owner_login: string;
      description?: string;
      is_private: boolean;
      default_branch?: string;
      language?: string;
      topics?: string[];
      already_mapped?: boolean;
      is_fork?: boolean;
      is_archived?: boolean;
      open_issues_count?: number;
    }>
  >([]);
  const [selectedRepoKeys, setSelectedRepoKeys] = useState<Set<string>>(new Set());
  const [repoSearchFilter, setRepoSearchFilter] = useState("");

  // GitHub Sync Scope Configuration
  const [branchScope, setBranchScope] = useState<"default" | "all">("default");
  const [commitScope, setCommitScope] = useState<"all" | "since">("all");
  const [commitSinceDate, setCommitSinceDate] = useState("");
  const [prScope, setPrScope] = useState<"all" | "open">("all");
  const [issueScope, setIssueScope] = useState<"all" | "open">("all");
  const [includeDocs, setIncludeDocs] = useState(true);
  const [includeCommits, setIncludeCommits] = useState(true);
  const [includePRs, setIncludePRs] = useState(true);
  const [includeIssues, setIncludeIssues] = useState(true);
  const [includeReviews, setIncludeReviews] = useState(true);
  const [includeComments, setIncludeComments] = useState(true);
  const [includeCode, setIncludeCode] = useState(false);

  // Jira state
  const [jiraUrl, setJiraUrl] = useState("");
  const [jiraEmail, setJiraEmail] = useState("");
  const [jiraToken, setJiraToken] = useState("");
  const [discoveredProjects, setDiscoveredProjects] = useState<
    Array<{
      cloud_id: string;
      key: string;
      name: string;
      project_type_key?: string;
      is_private?: boolean;
    }>
  >([]);
  const [selectedProjectKeys, setSelectedProjectKeys] = useState<Set<string>>(new Set());
  const [projectSearchFilter, setProjectSearchFilter] = useState("");

  // Slack state
  const [slackDomain, setSlackDomain] = useState("");
  const [slackToken, setSlackToken] = useState("");
  const [discoveredChannels, setDiscoveredChannels] = useState<
    Array<{
      id: string;
      name: string;
      is_private: boolean;
      num_members: number;
      topic: string;
    }>
  >([]);
  const [selectedChannelIds, setSelectedChannelIds] = useState<Set<string>>(new Set());
  const [channelSearchFilter, setChannelSearchFilter] = useState("");

  // Document Upload state
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [docCustomTitle, setDocCustomTitle] = useState("");
  const [docCategory, setDocCategory] = useState<"team_roster" | "meeting_notes" | "project_document">("project_document");
  const [docSubtype, setDocSubtype] = useState("prd");
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Loading & error state
  const [isDiscovering, setIsDiscovering] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  useEffect(() => {
    if (typeof window !== "undefined") {
      (window as unknown as Record<string, unknown>).__setConnectModalStep = (
        s: FlowStep,
        opts?: {
          account?: string;
          connectionId?: string;
          repos?: Array<{
            external_resource_id: string;
            full_name: string;
            name: string;
            owner_login: string;
            description?: string;
            is_private: boolean;
            default_branch?: string;
            language?: string;
            topics?: string[];
            already_mapped?: boolean;
            is_fork?: boolean;
            is_archived?: boolean;
            open_issues_count?: number;
          }>;
          selectedKeys?: string[];
          branchScope?: "default" | "all";
          commitScope?: "all" | "since";
        }
      ) => {
        setStep(s);
        if (opts?.account) setGithubResolvedAccount(opts.account);
        if (opts?.connectionId) setActiveConnectionId(opts.connectionId);
        if (opts?.repos) setDiscoveredRepos(opts.repos);
        if (opts?.selectedKeys) setSelectedRepoKeys(new Set(opts.selectedKeys));
        if (opts?.branchScope) setBranchScope(opts.branchScope);
        if (opts?.commitScope) setCommitScope(opts.commitScope);
      };
      (window as unknown as Record<string, unknown>).__setShowPermGuide = (val: boolean) => setShowPermGuide(val);
    }
  }, []);

  const wasOpenRef = useRef(false);

  useEffect(() => {
    if (isAddSourceModalOpen && !wasOpenRef.current) {
      wasOpenRef.current = true;
      if (initialSourceProvider) {
        setActiveTab(initialSourceProvider as ConnectProviderTab);
      }
      setStep("credentials");
      setError(null);
      setSuccessMessage(null);
      setSelectedRepoKeys(new Set());
      setSelectedProjectKeys(new Set());
      setSelectedChannelIds(new Set());
      setShowGithubToken(false);
      setShowPermGuide(false);
      setShowCreateProjectInline(false);
      setNewProjectName("");
      setNewProjectDescription("");

      if (activeProject?.id) {
        setSelectedProjectId(activeProject.id);
      } else if (projects.length > 0 && projects[0]?.id) {
        setSelectedProjectId(projects[0].id);
        setActiveProject(projects[0]);
      } else {
        setSelectedProjectId("");
      }
    } else if (!isAddSourceModalOpen) {
      wasOpenRef.current = false;
    }
  }, [isAddSourceModalOpen, initialSourceProvider, activeProject?.id, projects, setActiveProject]);

  const handleQuickCreateProject = async () => {
    if (!newProjectName.trim()) return;
    setIsCreatingProject(true);
    setError(null);
    try {
      const proj = await createProject({
        name: newProjectName.trim(),
        description: newProjectDescription.trim() || undefined,
      });
      setSelectedProjectId(proj.id);
      setActiveProject(proj);
      setNewProjectName("");
      setNewProjectDescription("");
      setShowCreateProjectInline(false);
      addToast({
        type: "success",
        title: "Project Workspace Created",
        message: `Project ${proj.name} is now active and ready for source mapping.`,
      });
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to create project workspace.");
    } finally {
      setIsCreatingProject(false);
    }
  };

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

  // Step 1: Discover resources from provider
  const handleDiscover = async () => {
    if (!activeOrg?.id) {
      setError("Please select an organisation first.");
      return;
    }
    setError(null);
    setIsDiscovering(true);

    try {
      if (activeTab === "github") {
        if (!githubToken.trim()) {
          setError("Please provide your GitHub Personal Access Token.");
          setIsDiscovering(false);
          return;
        }
        // Connect source - username is auto-resolved by backend from GET /user if default or provided
        const accountHandle = githubAccount.trim() || "github-account";
        const conn = await connectSource("github", githubToken.trim(), accountHandle);
        setActiveConnectionId(conn.id);
        const resolvedName = conn.account_identifier || accountHandle;
        setGithubResolvedAccount(resolvedName);
        if (!githubAccount.trim()) {
          setGithubAccount(resolvedName);
        }
        // Discover accessible repositories with project_id so already_mapped is returned!
        const res = await api.sources.discoverGitHubRepositories(conn.id, 1, 100, effectiveProjectId || activeProject?.id);
        setDiscoveredRepos(res.items || []);
        if (!newProjectName && res.items?.[0]?.name) {
          setNewProjectName(res.items[0].name);
        }
        setStep("select_resources");
      } else if (activeTab === "jira") {
        if (!jiraEmail.trim() || !jiraToken.trim()) {
          setError("Please provide your Atlassian account email and API token.");
          setIsDiscovering(false);
          return;
        }
        const siteDomain = jiraUrl.trim() || "atlassian.net";
        const conn = await connectSource("jira", jiraToken.trim(), `${jiraEmail.trim()}@${siteDomain}`);
        setActiveConnectionId(conn.id);
        // Discover projects
        const res = await api.sources.discoverJiraProjects(conn.id);
        setDiscoveredProjects(res.projects || []);
        setStep("select_resources");
      } else if (activeTab === "slack") {
        if (!slackToken.trim()) {
          setError("Please provide your Slack Bot User OAuth Token (xoxb-...).");
          setIsDiscovering(false);
          return;
        }
        const domain = slackDomain.trim() || "slack-workspace";
        const conn = await connectSource("slack", slackToken.trim(), domain);
        setActiveConnectionId(conn.id);
        // Discover channels
        const res = await api.sources.discoverSlackChannels(conn.id);
        setDiscoveredChannels(res.items || []);
        setStep("select_resources");
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to verify credentials and discover resources.");
    } finally {
      setIsDiscovering(false);
    }
  };

  // Step 1b: Use existing active organisation connection
  const handleDiscoverExisting = async (connId: string) => {
    setError(null);
    setIsDiscovering(true);
    try {
      setActiveConnectionId(connId);
      const conn = orgConnections.find((c) => c.id === connId);
      if (conn?.account_identifier) {
        setGithubResolvedAccount(conn.account_identifier);
        setGithubAccount(conn.account_identifier);
      }
      if (activeTab === "github") {
        const res = await api.sources.discoverGitHubRepositories(connId, 1, 100, effectiveProjectId || activeProject?.id);
        setDiscoveredRepos(res.items || []);
        if (!newProjectName && res.items?.[0]?.name) {
          setNewProjectName(res.items[0].name);
        }
        setStep("select_resources");
      } else if (activeTab === "jira") {
        const res = await api.sources.discoverJiraProjects(connId);
        setDiscoveredProjects(res.projects || []);
        setStep("select_resources");
      } else if (activeTab === "slack") {
        const res = await api.sources.discoverSlackChannels(connId);
        setDiscoveredChannels(res.items || []);
        setStep("select_resources");
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to discover resources from existing connection.");
    } finally {
      setIsDiscovering(false);
    }
  };

  // Step 2: Batch map selected resources and trigger background sync
  const handleBatchIngest = async () => {
    const finalProjectId = effectiveProjectId;
    if (!finalProjectId) {
      setError("Please select or create a target project workspace first before starting synchronisation.");
      return;
    }
    const finalConnectionId = resolvedConnectionId;
    if (!finalConnectionId) {
      setError("Active source connection is missing. Please re-authenticate your credentials in Step 1.");
      return;
    }
    setError(null);
    setIsSubmitting(true);

    try {
      let createdMappingsCount = 0;

      if (activeTab === "github") {
        if (selectedRepoKeys.size === 0) {
          setError("Please select at least one repository to ingest.");
          setIsSubmitting(false);
          return;
        }
        const items = Array.from(selectedRepoKeys).map((fullName) => {
          const parts = fullName.split("/");
          return {
            owner: parts[0],
            repo: parts[1],
            full_name: fullName,
            branch_scope: branchScope,
            commit_scope: commitScope,
            commit_since: commitScope === "since" && commitSinceDate ? new Date(commitSinceDate).toISOString() : null,
            pr_scope: prScope,
            issue_scope: issueScope,
            include_docs: includeDocs,
            include_commits: includeCommits,
            include_pull_requests: includePRs,
            include_issues: includeIssues,
            include_reviews: includeReviews,
            include_comments: includeComments,
            include_code: includeCode,
          };
        });
        const res = await api.sources.batchCreateMappings(finalProjectId, {
          provider: "github",
          source_connection_id: finalConnectionId,
          items,
        });
        createdMappingsCount = res.created_mappings.length;
        if (res.created_mappings.length > 0) {
          addSourceMappings(res.created_mappings);
        }
      } else if (activeTab === "jira") {
        if (selectedProjectKeys.size === 0) {
          setError("Please select at least one Jira project to ingest.");
          setIsSubmitting(false);
          return;
        }
        const items = Array.from(selectedProjectKeys).map((key) => {
          const proj = discoveredProjects.find((p) => p.key === key);
          return { cloud_id: proj?.cloud_id || "jira", project_key: key };
        });
        const res = await api.sources.batchCreateMappings(finalProjectId, {
          provider: "jira",
          source_connection_id: finalConnectionId,
          items,
        });
        createdMappingsCount = res.created_mappings.length;
        if (res.created_mappings.length > 0) {
          addSourceMappings(res.created_mappings);
        }
      } else if (activeTab === "slack") {
        if (selectedChannelIds.size === 0) {
          setError("Please select at least one Slack channel to ingest.");
          setIsSubmitting(false);
          return;
        }
        const items = Array.from(selectedChannelIds).map((id) => {
          const ch = discoveredChannels.find((c) => c.id === id);
          return { channel_id: id, channel_name: ch?.name || id };
        });
        const res = await api.sources.batchCreateMappings(finalProjectId, {
          provider: "slack",
          source_connection_id: finalConnectionId,
          items,
        });
        createdMappingsCount = res.created_mappings.length;
        if (res.created_mappings.length > 0) {
          addSourceMappings(res.created_mappings);
        }
      }

      if (targetProject && activeProject?.id !== finalProjectId) {
        setActiveProject(targetProject);
      }
      setIsAddSourceModalOpen(false);
      void refreshSources();
      void refreshEvidence();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to map resources and queue sync.");
    } finally {
      setIsSubmitting(false);
    }
  };

  // Direct Document Upload Handler
  const handleDocSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) {
      setError("Please select a PDF or DOCX file to upload.");
      return;
    }
    const finalProjectId = effectiveProjectId;
    if (!finalProjectId) {
      setError("Please select or create an active project workspace first.");
      return;
    }
    setError(null);
    setIsSubmitting(true);

    try {
      await api.evidence.upload(finalProjectId, selectedFile, {
        title: docCustomTitle.trim() || undefined,
        document_category: docCategory,
        document_subtype: docCategory === "project_document" ? docSubtype : undefined,
      });
      if (targetProject && activeProject?.id !== finalProjectId) {
        setActiveProject(targetProject);
      }
      await refreshEvidence();
      setSelectedFile(null);
      setDocCustomTitle("");
      setIsAddSourceModalOpen(false);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Document upload failed.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const currentTabConfig: SourceTabConfig = TABS.find((t) => t.id === activeTab) ?? TABS[0]!;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-2xs p-4">
      <div className="w-full max-w-2xl bg-white rounded-xl shadow-2xl border border-[#DCE3EB] overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="px-6 py-4 bg-[#F4F6F9] border-b border-[#DCE3EB] flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <SourceIcon type={activeTab as SourceType} size={32} />
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-bold text-[#25334B]">
                  {activeTab === "docs" ? "Upload Project Document" : `Connect ${currentTabConfig.label}`}
                </h2>
                {currentTabConfig.badge && (
                  <span className="px-2 py-0.5 text-[10px] font-semibold bg-amber-100 text-amber-800 rounded-full border border-amber-200">
                    {currentTabConfig.badge}
                  </span>
                )}
              </div>
              <p className="text-[11px] text-[#69778D]">{currentTabConfig.description}</p>
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

        {/* Modal Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {/* Workspace Context & Target Project Info Bar */}
          <div className="flex flex-wrap items-center justify-between gap-2 p-2.5 rounded-lg bg-slate-50 border border-slate-200 text-xs text-slate-600">
            <div className="flex items-center gap-1.5">
              <span className="text-slate-400 font-medium">Organisation:</span>
              <span className="font-semibold text-slate-800">{activeOrg?.name || "Current Organisation"}</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="text-slate-400 font-medium">Target Project:</span>
              {targetProject ? (
                <span className="font-semibold text-[#203653] bg-white px-2 py-0.5 rounded border border-slate-200 shadow-2xs">
                  {targetProject.name}
                </span>
              ) : (
                <span className="font-semibold text-amber-700 bg-amber-50 px-2 py-0.5 rounded border border-amber-200">
                  None Selected
                </span>
              )}
            </div>
          </div>

          {error && (
            <div className="p-3 rounded-lg bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* ----------------- GITHUB TAB ----------------- */}
          {activeTab === "github" && (
            <div>
              {step === "credentials" && (
                <div className="space-y-4">
                  {existingActiveConnection && (
                    <div className="p-3 rounded-lg bg-emerald-50/70 border border-emerald-200 flex items-center justify-between gap-3 text-xs">
                      <div className="flex items-center gap-2">
                        <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                        <div>
                          <span className="font-semibold text-emerald-950">
                            Connected Account: @{existingActiveConnection.account_identifier}
                          </span>
                          <span className="text-[10px] text-emerald-700 ml-2 font-mono">
                            (Active in organisation)
                          </span>
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => handleDiscoverExisting(existingActiveConnection.id)}
                        disabled={isDiscovering}
                        className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded text-xs font-semibold flex items-center gap-1.5 shadow-2xs transition-colors shrink-0"
                      >
                        {isDiscovering ? (
                          <Loader2 className="w-3 h-3 animate-spin" />
                        ) : (
                          <ArrowRight className="w-3 h-3" />
                        )}
                        <span>Use This Account</span>
                      </button>
                    </div>
                  )}

                  <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 flex items-start gap-3">
                    <SourceIcon type="github" size={28} />
                    <div className="text-xs">
                      <span className="font-semibold text-slate-800">GitHub Personal Access Token (Fine-Grained or Classic)</span>
                      <p className="text-slate-500 text-[11px] mt-0.5 leading-relaxed">
                        Authenticate your GitHub account using a Personal Access Token. Repositories and account details will be discovered automatically.
                      </p>
                    </div>
                  </div>

                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label className="block text-xs font-semibold text-[#25334B]">
                        Personal Access Token (PAT) <span className="text-rose-500">*</span>
                      </label>
                      <a
                        href="https://github.com/settings/tokens?type=beta"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-[11px] text-[#4774A9] hover:underline flex items-center gap-1 font-medium"
                      >
                        <span>Generate token on GitHub</span>
                        <ExternalLink className="w-3 h-3" />
                      </a>
                    </div>
                    <div className="relative">
                      <input
                        type={showGithubToken ? "text" : "password"}
                        value={githubToken}
                        onChange={(e) => setGithubToken(e.target.value)}
                        placeholder="github_pat_... or ghp_..."
                        className="w-full pl-3 pr-10 py-2 rounded-lg border border-[#DCE3EB] text-xs font-mono focus:outline-none focus:ring-2 focus:ring-[#4774A9]"
                      />
                      <button
                        type="button"
                        onClick={() => setShowGithubToken(!showGithubToken)}
                        className="absolute right-2.5 top-2.5 text-slate-400 hover:text-slate-700"
                      >
                        {showGithubToken ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                      </button>
                    </div>
                    <p className="text-[10px] text-slate-400 mt-1 flex items-center gap-1">
                      <Lock className="w-3 h-3 text-emerald-600" /> Token is encrypted strictly at rest with AES-256-GCM envelope encryption.
                    </p>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-[#25334B] mb-1">
                      GitHub Username / Organisation (Optional)
                    </label>
                    <input
                      type="text"
                      value={githubAccount}
                      onChange={(e) => setGithubAccount(e.target.value)}
                      placeholder="Leave blank to auto-detect from token"
                      className="w-full px-3 py-2 rounded-lg border border-[#DCE3EB] text-xs focus:outline-none focus:ring-2 focus:ring-[#4774A9]"
                    />
                    <p className="text-[10px] text-slate-400 mt-1">
                      Auto-discovered from <code>GET /user</code> if left blank.
                    </p>
                  </div>

                  {/* Expandable Permissions Guide */}
                  <div className="border border-slate-200 rounded-lg overflow-hidden">
                    <button
                      type="button"
                      onClick={() => setShowPermGuide(!showPermGuide)}
                      className="w-full p-2.5 bg-slate-50 hover:bg-slate-100 flex items-center justify-between text-xs font-medium text-slate-700 transition-colors"
                    >
                      <span className="flex items-center gap-1.5">
                        <HelpCircle className="w-3.5 h-3.5 text-[#4774A9]" />
                        <span>Required GitHub Permissions Guide</span>
                      </span>
                      {showPermGuide ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
                    </button>
                    {showPermGuide && (
                      <div className="p-3 bg-white text-[11px] text-slate-600 space-y-2 border-t border-slate-200">
                        <p className="font-medium text-slate-800">For Fine-Grained Personal Access Tokens, set the following read-only scopes:</p>
                        <ul className="space-y-1.5 pl-1">
                          <li className="flex items-start gap-2">
                            <span className="font-mono bg-slate-100 px-1 py-0.5 rounded text-[10px] text-slate-800 shrink-0">Contents: Read</span>
                            <span>Required for extracting README.md, repository documentation, commits, and file changes.</span>
                          </li>
                          <li className="flex items-start gap-2">
                            <span className="font-mono bg-slate-100 px-1 py-0.5 rounded text-[10px] text-slate-800 shrink-0">Pull requests: Read</span>
                            <span>Required for extracting PR titles, descriptions, code reviews, and reviewer comments.</span>
                          </li>
                          <li className="flex items-start gap-2">
                            <span className="font-mono bg-slate-100 px-1 py-0.5 rounded text-[10px] text-slate-800 shrink-0">Issues: Read</span>
                            <span>Required for extracting bug reports, task discussions, issue comments, and labels.</span>
                          </li>
                          <li className="flex items-start gap-2">
                            <span className="font-mono bg-slate-100 px-1 py-0.5 rounded text-[10px] text-slate-800 shrink-0">Metadata: Read</span>
                            <span>Automatically included by GitHub for repository discovery and branch listing.</span>
                          </li>
                        </ul>
                      </div>
                    )}
                  </div>

                  <div className="pt-2 flex justify-end">
                    <button
                      type="button"
                      onClick={handleDiscover}
                      disabled={isDiscovering || !githubToken.trim()}
                      className="px-4 py-2 bg-[#4774A9] hover:bg-[#386295] disabled:opacity-50 text-white rounded-lg text-xs font-semibold flex items-center gap-2 transition-colors"
                    >
                      {isDiscovering ? (
                        <>
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          <span>Validating Token & Discovering Repositories...</span>
                        </>
                      ) : (
                        <>
                          <span>Validate & Discover Repositories</span>
                          <ArrowRight className="w-3.5 h-3.5" />
                        </>
                      )}
                    </button>
                  </div>
                </div>
              )}

              {step === "select_resources" && (
                <div className="space-y-4">
                  {/* Authenticated account banner */}
                  <div className="flex items-center justify-between p-2.5 bg-blue-50/60 border border-blue-200/80 rounded-lg">
                    <div className="flex items-center gap-2 text-xs">
                      <ShieldCheck className="w-4 h-4 text-emerald-600 shrink-0" />
                      <span className="text-slate-600">Authenticated as:</span>
                      <span className="font-semibold text-slate-900 font-mono">@{githubResolvedAccount || githubAccount}</span>
                    </div>
                    <span className="text-[11px] text-blue-700 font-medium">
                      {discoveredRepos.length} repositories discovered
                    </span>
                  </div>

                  {/* Target Project Workspace Selector / Creator */}
                  <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg space-y-2">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="text-xs font-semibold text-slate-700">Target Project Workspace:</span>
                      {projects.length > 0 ? (
                        <div className="flex items-center gap-2">
                          <select
                            value={targetProject?.id || ""}
                            onChange={(e) => {
                              const found = projects.find((p) => p.id === e.target.value);
                              if (found) {
                                setSelectedProjectId(found.id);
                                setActiveProject(found);
                              }
                            }}
                            className="text-xs font-semibold text-[#203653] bg-white border border-slate-200 rounded px-2.5 py-1 focus:ring-1 focus:ring-[#315FBA] outline-none"
                          >
                            {projects.map((p) => (
                              <option key={p.id} value={p.id}>
                                {p.name}
                              </option>
                            ))}
                          </select>
                          <button
                            type="button"
                            onClick={() => setShowCreateProjectInline(!showCreateProjectInline)}
                            className="text-[11px] text-[#315FBA] hover:underline font-medium"
                          >
                            + New Project
                          </button>
                        </div>
                      ) : (
                        <span className="text-xs font-semibold text-rose-600">No project workspace found</span>
                      )}
                    </div>

                    {(projects.length === 0 || showCreateProjectInline) && (
                      <div className="pt-2 border-t border-slate-200 space-y-2">
                        <p className="text-[11px] text-slate-600">
                          {projects.length === 0
                            ? `No projects exist in ${activeOrg?.name || "this organisation"} yet. Create a project workspace to map repositories into:`
                            : "Create a new project workspace:"}
                        </p>
                        <div className="flex gap-2">
                          <input
                            type="text"
                            value={newProjectName}
                            onChange={(e) => setNewProjectName(e.target.value)}
                            placeholder="e.g. HackMatrix-5.0-MISC02"
                            className="flex-1 text-xs border border-slate-200 rounded px-2.5 py-1.5 bg-white text-slate-800"
                          />
                          <button
                            type="button"
                            disabled={!newProjectName.trim() || isCreatingProject}
                            onClick={handleQuickCreateProject}
                            className="px-3 py-1.5 bg-[#315FBA] hover:bg-[#264C98] disabled:opacity-50 text-white rounded text-xs font-semibold flex items-center gap-1 shrink-0"
                          >
                            {isCreatingProject ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
                            Create Project
                          </button>
                        </div>
                      </div>
                    )}
                  </div>

                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="text-xs font-bold text-slate-800">
                        Select Repositories for &ldquo;{targetProject?.name || "Workspace"}&rdquo;
                      </h3>
                      <p className="text-[11px] text-slate-500">
                        Select one or more repositories to map into this project workspace.
                      </p>
                    </div>
                    <div className="flex gap-2 text-xs items-center">
                      <button
                        type="button"
                        onClick={() => {
                          const visibleKeys = discoveredRepos
                            .filter((r) => {
                              const matchesSearch =
                                !repoSearchFilter.trim() ||
                                r.full_name.toLowerCase().includes(repoSearchFilter.toLowerCase()) ||
                                (r.description && r.description.toLowerCase().includes(repoSearchFilter.toLowerCase())) ||
                                (r.language && r.language.toLowerCase().includes(repoSearchFilter.toLowerCase()));
                              const matchesFilter =
                                githubFilterType === "all" ||
                                (githubFilterType === "private" && r.is_private) ||
                                (githubFilterType === "public" && !r.is_private) ||
                                (githubFilterType === "owned" &&
                                  r.owner_login.toLowerCase() === (githubResolvedAccount || githubAccount).toLowerCase());
                              return matchesSearch && matchesFilter;
                            })
                            .map((r) => r.full_name);
                          setSelectedRepoKeys(new Set([...selectedRepoKeys, ...visibleKeys]));
                        }}
                        className="text-[#4774A9] hover:underline font-medium text-[11px]"
                      >
                        Select All Filtered
                      </button>
                      <span className="text-slate-300">|</span>
                      <button
                        type="button"
                        onClick={() => setSelectedRepoKeys(new Set())}
                        className="text-slate-500 hover:underline font-medium text-[11px]"
                      >
                        Clear Selection
                      </button>
                    </div>
                  </div>

                  {/* Search filter and filter tabs */}
                  <div className="flex gap-2 items-center">
                    <div className="relative flex-1">
                      <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-slate-400" />
                      <input
                        type="text"
                        value={repoSearchFilter}
                        onChange={(e) => setRepoSearchFilter(e.target.value)}
                        placeholder="Filter by name, language, or description..."
                        className="w-full pl-8 pr-3 py-1.5 rounded-lg border border-[#DCE3EB] text-xs focus:outline-none focus:ring-1 focus:ring-[#4774A9]"
                      />
                    </div>
                    <div className="flex bg-slate-100 rounded-lg p-0.5 text-[11px] font-medium text-slate-600 shrink-0">
                      {(["all", "private", "public", "owned"] as const).map((filter) => (
                        <button
                          key={filter}
                          type="button"
                          onClick={() => setGithubFilterType(filter)}
                          className={`px-2 py-1 rounded-md capitalize transition-colors ${
                            githubFilterType === filter ? "bg-white text-slate-900 shadow-2xs font-semibold" : "hover:text-slate-900"
                          }`}
                        >
                          {filter}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Selection Counter */}
                  <div className="text-[11px] text-slate-500 flex items-center justify-between">
                    <span>Showing repositories</span>
                    <span className="font-semibold text-slate-800">
                      {selectedRepoKeys.size} repository{selectedRepoKeys.size === 1 ? "" : "ies"} selected
                    </span>
                  </div>

                  {/* Repos list */}
                  <div className="max-h-64 overflow-y-auto border border-[#DCE3EB] rounded-lg divide-y divide-[#EBF0F5]">
                    {discoveredRepos
                      .filter((r) => {
                        const matchesSearch =
                          !repoSearchFilter.trim() ||
                          r.full_name.toLowerCase().includes(repoSearchFilter.toLowerCase()) ||
                          (r.description && r.description.toLowerCase().includes(repoSearchFilter.toLowerCase())) ||
                          (r.language && r.language.toLowerCase().includes(repoSearchFilter.toLowerCase()));
                        const matchesFilter =
                          githubFilterType === "all" ||
                          (githubFilterType === "private" && r.is_private) ||
                          (githubFilterType === "public" && !r.is_private) ||
                          (githubFilterType === "owned" &&
                            r.owner_login.toLowerCase() === (githubResolvedAccount || githubAccount).toLowerCase());
                        return matchesSearch && matchesFilter;
                      })
                      .map((repo) => {
                        const isChecked = selectedRepoKeys.has(repo.full_name);
                        return (
                          <div
                            key={repo.external_resource_id}
                            onClick={() => {
                              const next = new Set(selectedRepoKeys);
                              if (isChecked) next.delete(repo.full_name);
                              else next.add(repo.full_name);
                              setSelectedRepoKeys(next);
                            }}
                            className={`p-2.5 flex items-start gap-2.5 cursor-pointer hover:bg-slate-50 transition-colors ${
                              isChecked ? "bg-blue-50/50" : ""
                            }`}
                          >
                            <input
                              type="checkbox"
                              checked={isChecked}
                              onChange={() => {}} // Handled by parent div
                              className="mt-1 rounded text-[#4774A9] focus:ring-0"
                            />
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-1.5 flex-wrap">
                                <span className="text-xs font-semibold text-slate-900">
                                  {repo.full_name}
                                </span>
                                <span className="px-1.5 py-0.2 text-[9px] font-medium bg-slate-100 text-slate-600 rounded">
                                  {repo.is_private ? "Private" : "Public"}
                                </span>
                                {repo.default_branch && (
                                  <span className="px-1.5 py-0.2 text-[9px] font-medium bg-slate-50 text-slate-500 rounded border border-slate-200">
                                    {repo.default_branch}
                                  </span>
                                )}
                                {repo.language && (
                                  <span className="px-1.5 py-0.2 text-[9px] font-medium bg-blue-50 text-blue-700 rounded border border-blue-200">
                                    {repo.language}
                                  </span>
                                )}
                                {repo.already_mapped && (
                                  <span className="px-1.5 py-0.2 text-[9px] font-semibold bg-emerald-50 text-emerald-700 rounded border border-emerald-200">
                                    Already Ingested
                                  </span>
                                )}
                              </div>
                              {repo.description && (
                                <p className="text-[11px] text-slate-500 truncate mt-0.5">{repo.description}</p>
                              )}
                            </div>
                          </div>
                        );
                      })}
                  </div>

                  <div className="pt-2 flex items-center justify-between">
                    <button
                      type="button"
                      onClick={() => changeStep("credentials")}
                      className="text-xs text-slate-500 hover:text-slate-800"
                    >
                      &larr; Change Token
                    </button>
                    <button
                      type="button"
                      onClick={() => changeStep("configure_scope")}
                      disabled={selectedRepoKeys.size === 0}
                      className="px-4 py-2 bg-[#4774A9] hover:bg-[#386295] disabled:opacity-50 text-white rounded-lg text-xs font-semibold flex items-center gap-2"
                    >
                      <span>Configure Sync Scope ({selectedRepoKeys.size})</span>
                      <ArrowRight className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              )}

              {step === "configure_scope" && (
                <div className="space-y-4">
                  <div>
                    <h3 className="text-xs font-bold text-slate-800">
                      Configure Synchronisation Scope ({selectedRepoKeys.size} repositories selected)
                    </h3>
                    <p className="text-[11px] text-slate-500">
                      Customise what information is imported and indexed into project &ldquo;{targetProject?.name || "Workspace"}&rdquo;.
                    </p>
                  </div>

                  <div className="space-y-3 max-h-72 overflow-y-auto pr-1">
                    {/* Option 1: Documentation */}
                    <div className="p-3 border border-slate-200 rounded-lg bg-slate-50/50 space-y-1">
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={includeDocs}
                          onChange={(e) => setIncludeDocs(e.target.checked)}
                          className="rounded text-[#4774A9]"
                        />
                        <span className="text-xs font-semibold text-slate-800">Ingest Documentation & README Files</span>
                      </label>
                      <p className="text-[11px] text-slate-500 pl-6">
                        Extracts README.md, docs/, architecture decisions, specifications, and project markdown.
                      </p>
                    </div>

                    {/* Option 2: Branch Scope */}
                    <div className="p-3 border border-slate-200 rounded-lg bg-slate-50/50 space-y-2">
                      <span className="text-xs font-semibold text-slate-800 block">Branch Ingestion Scope</span>
                      <div className="grid grid-cols-2 gap-2 text-xs">
                        <label className={`p-2 rounded-lg border cursor-pointer flex items-center gap-2 ${
                          branchScope === "default" ? "bg-blue-50/60 border-[#4774A9] text-[#25334B]" : "bg-white border-slate-200 text-slate-600"
                        }`}>
                          <input
                            type="radio"
                            name="branchScope"
                            checked={branchScope === "default"}
                            onChange={() => setBranchScope("default")}
                            className="text-[#4774A9]"
                          />
                          <div>
                            <span className="font-semibold block text-[11px]">Default branch only</span>
                            <span className="text-[10px] text-slate-500">Recommended, faster sync</span>
                          </div>
                        </label>
                        <label className={`p-2 rounded-lg border cursor-pointer flex items-center gap-2 ${
                          branchScope === "all" ? "bg-blue-50/60 border-[#4774A9] text-[#25334B]" : "bg-white border-slate-200 text-slate-600"
                        }`}>
                          <input
                            type="radio"
                            name="branchScope"
                            checked={branchScope === "all"}
                            onChange={() => setBranchScope("all")}
                            className="text-[#4774A9]"
                          />
                          <div>
                            <span className="font-semibold block text-[11px]">All accessible branches</span>
                            <span className="text-[10px] text-slate-500">Multi-branch commit sync</span>
                          </div>
                        </label>
                      </div>
                    </div>

                    {/* Option 3: Commit History Scope */}
                    <div className="p-3 border border-slate-200 rounded-lg bg-slate-50/50 space-y-2">
                      <span className="text-xs font-semibold text-slate-800 block">Commit History Scope</span>
                      <div className="grid grid-cols-2 gap-2 text-xs">
                        <label className={`p-2 rounded-lg border cursor-pointer flex items-center gap-2 ${
                          commitScope === "all" ? "bg-blue-50/60 border-[#4774A9] text-[#25334B]" : "bg-white border-slate-200 text-slate-600"
                        }`}>
                          <input
                            type="radio"
                            name="commitScope"
                            checked={commitScope === "all"}
                            onChange={() => setCommitScope("all")}
                            className="text-[#4774A9]"
                          />
                          <div>
                            <span className="font-semibold block text-[11px]">All available history</span>
                            <span className="text-[10px] text-slate-500">Full repository commit log</span>
                          </div>
                        </label>
                        <label className={`p-2 rounded-lg border cursor-pointer flex items-center gap-2 ${
                          commitScope === "since" ? "bg-blue-50/60 border-[#4774A9] text-[#25334B]" : "bg-white border-slate-200 text-slate-600"
                        }`}>
                          <input
                            type="radio"
                            name="commitScope"
                            checked={commitScope === "since"}
                            onChange={() => setCommitScope("since")}
                            className="text-[#4774A9]"
                          />
                          <div>
                            <span className="font-semibold block text-[11px]">Since specific date</span>
                            <span className="text-[10px] text-slate-500">Targeted date range</span>
                          </div>
                        </label>
                      </div>
                      {commitScope === "since" && (
                        <div className="pt-1">
                          <input
                            type="date"
                            value={commitSinceDate}
                            onChange={(e) => setCommitSinceDate(e.target.value)}
                            className="px-2.5 py-1.5 border border-slate-300 rounded text-xs"
                          />
                        </div>
                      )}
                    </div>

                    {/* Option 4: Pull Requests & Reviews */}
                    <div className="p-3 border border-slate-200 rounded-lg bg-slate-50/50 space-y-2">
                      <span className="text-xs font-semibold text-slate-800 block">Pull Requests & Code Reviews</span>
                      <div className="flex gap-4 text-xs">
                        <label className="flex items-center gap-1.5 cursor-pointer">
                          <input
                            type="radio"
                            name="prScope"
                            checked={prScope === "all"}
                            onChange={() => setPrScope("all")}
                            className="text-[#4774A9]"
                          />
                          <span className="text-slate-700 text-[11px]">All PRs (Open, Closed, Merged)</span>
                        </label>
                        <label className="flex items-center gap-1.5 cursor-pointer">
                          <input
                            type="radio"
                            name="prScope"
                            checked={prScope === "open"}
                            onChange={() => setPrScope("open")}
                            className="text-[#4774A9]"
                          />
                          <span className="text-slate-700 text-[11px]">Open PRs only</span>
                        </label>
                      </div>
                      <label className="flex items-center gap-2 cursor-pointer pt-1 border-t border-slate-200/60">
                        <input
                          type="checkbox"
                          checked={includeReviews}
                          onChange={(e) => setIncludeReviews(e.target.checked)}
                          className="rounded text-[#4774A9]"
                        />
                        <span className="text-[11px] text-slate-700">Include PR Reviews & Review Comments</span>
                      </label>
                    </div>

                    {/* Option 5: Issues & Discussions */}
                    <div className="p-3 border border-slate-200 rounded-lg bg-slate-50/50 space-y-2">
                      <span className="text-xs font-semibold text-slate-800 block">Issues & Task Discussions</span>
                      <div className="flex gap-4 text-xs">
                        <label className="flex items-center gap-1.5 cursor-pointer">
                          <input
                            type="radio"
                            name="issueScope"
                            checked={issueScope === "all"}
                            onChange={() => setIssueScope("all")}
                            className="text-[#4774A9]"
                          />
                          <span className="text-slate-700 text-[11px]">All Issues (Open and Closed)</span>
                        </label>
                        <label className="flex items-center gap-1.5 cursor-pointer">
                          <input
                            type="radio"
                            name="issueScope"
                            checked={issueScope === "open"}
                            onChange={() => setIssueScope("open")}
                            className="text-[#4774A9]"
                          />
                          <span className="text-slate-700 text-[11px]">Open Issues only</span>
                        </label>
                      </div>
                      <label className="flex items-center gap-2 cursor-pointer pt-1 border-t border-slate-200/60">
                        <input
                          type="checkbox"
                          checked={includeComments}
                          onChange={(e) => setIncludeComments(e.target.checked)}
                          className="rounded text-[#4774A9]"
                        />
                        <span className="text-[11px] text-slate-700">Include Issue Comments</span>
                      </label>
                    </div>

                    {/* Option 6: Source Code Indexing */}
                    <div className="p-3 border border-slate-200 rounded-lg bg-slate-50/50 space-y-1">
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={includeCode}
                          onChange={(e) => setIncludeCode(e.target.checked)}
                          className="rounded text-[#4774A9]"
                        />
                        <span className="text-xs font-semibold text-slate-800">Index Key Source Code Files (Experimental)</span>
                      </label>
                      <p className="text-[11px] text-slate-500 pl-6">
                        Extracts code definitions from key files. Commits, diffs, and docs are always captured regardless of this setting.
                      </p>
                    </div>
                  </div>

                  <div className="pt-2 flex items-center justify-between">
                    <button
                      type="button"
                      onClick={() => changeStep("select_resources")}
                      className="text-xs text-slate-500 hover:text-slate-800"
                    >
                      &larr; Adjust Repositories
                    </button>
                    <button
                      type="button"
                      onClick={() => changeStep("confirm")}
                      className="px-4 py-2 bg-[#4774A9] hover:bg-[#386295] text-white rounded-lg text-xs font-semibold flex items-center gap-2"
                    >
                      <span>Review & Confirm</span>
                      <ArrowRight className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              )}

              {step === "confirm" && (
                <div className="space-y-4">
                  <div className="p-3 rounded-lg bg-emerald-50 border border-emerald-200 flex items-start gap-3">
                    <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />
                    <div className="text-xs">
                      <span className="font-semibold text-emerald-900">Ready to Ingest & Synchronise</span>
                      <p className="text-emerald-700 text-[11px] mt-0.5">
                        Review your configuration below. Background worker jobs will be queued to synchronise and index knowledge into ChromaDB and PostgreSQL.
                      </p>
                    </div>
                  </div>

                  <div className="border border-slate-200 rounded-lg p-4 space-y-3 text-xs bg-slate-50/30">
                    <div className="flex flex-wrap items-center justify-between py-1.5 border-b border-slate-200 gap-2">
                      <span className="text-slate-500">Target Project</span>
                      {targetProject ? (
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-slate-800">{targetProject.name}</span>
                          {projects.length > 1 && (
                            <select
                              value={targetProject.id}
                              onChange={(e) => {
                                const found = projects.find((p) => p.id === e.target.value);
                                if (found) {
                                  setSelectedProjectId(found.id);
                                  setActiveProject(found);
                                }
                              }}
                              className="text-[11px] text-[#203653] bg-white border border-slate-200 rounded px-2 py-0.5 focus:ring-1 focus:ring-[#315FBA] outline-none"
                            >
                              {projects.map((p) => (
                                <option key={p.id} value={p.id}>
                                  {p.name}
                                </option>
                              ))}
                            </select>
                          )}
                        </div>
                      ) : (
                        <div className="text-right">
                          <span className="font-semibold text-rose-600 block">No project selected</span>
                          {projects.length > 0 ? (
                            <select
                              value=""
                              onChange={(e) => {
                                const found = projects.find((p) => p.id === e.target.value);
                                if (found) {
                                  setSelectedProjectId(found.id);
                                  setActiveProject(found);
                                }
                              }}
                              className="mt-1 text-[11px] text-[#203653] bg-white border border-rose-300 rounded px-2 py-0.5 outline-none"
                            >
                              <option value="">-- Choose Target Project --</option>
                              {projects.map((p) => (
                                <option key={p.id} value={p.id}>
                                  {p.name}
                                </option>
                              ))}
                            </select>
                          ) : (
                            <button
                              type="button"
                              onClick={() => setShowCreateProjectInline(true)}
                              className="mt-1 text-xs text-[#315FBA] font-semibold hover:underline block"
                            >
                              + Create Project Workspace
                            </button>
                          )}
                        </div>
                      )}
                    </div>
                    {/* Inline project creator if no project selected and requested */}
                    {!targetProject && (
                      <div className="p-3 border border-amber-200 rounded-lg bg-amber-50/70 space-y-2">
                        <p className="text-[11px] text-amber-900 font-medium">
                          A project workspace is required to map your selected repositories into:
                        </p>
                        <div className="flex gap-2">
                          <input
                            type="text"
                            value={newProjectName}
                            onChange={(e) => setNewProjectName(e.target.value)}
                            placeholder="e.g. HackMatrix-5.0-MISC02"
                            className="flex-1 text-xs border border-amber-300 rounded px-2.5 py-1.5 bg-white text-slate-800"
                          />
                          <button
                            type="button"
                            disabled={!newProjectName.trim() || isCreatingProject}
                            onClick={handleQuickCreateProject}
                            className="px-3 py-1.5 bg-[#315FBA] hover:bg-[#264C98] disabled:opacity-50 text-white rounded text-xs font-semibold flex items-center gap-1 shrink-0"
                          >
                            {isCreatingProject ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
                            Create Project
                          </button>
                        </div>
                      </div>
                    )}
                    <div className="flex justify-between py-1 border-b border-slate-200">
                      <span className="text-slate-500">GitHub Identity</span>
                      <span className="font-mono font-medium text-slate-800">@{githubResolvedAccount || githubAccount}</span>
                    </div>
                    <div className="py-1 border-b border-slate-200">
                      <span className="text-slate-500 block mb-1">Selected Repositories ({selectedRepoKeys.size})</span>
                      <div className="flex flex-wrap gap-1.5 max-h-24 overflow-y-auto">
                        {Array.from(selectedRepoKeys).map((key) => (
                          <span key={key} className="px-2 py-0.5 bg-white border border-slate-200 text-slate-700 rounded text-[11px] font-mono">
                            {key}
                          </span>
                        ))}
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-2 pt-1 text-[11px]">
                      <div>
                        <span className="text-slate-500">Documentation:</span>{" "}
                        <span className="font-medium text-slate-800">{includeDocs ? "Included" : "Excluded"}</span>
                      </div>
                      <div>
                        <span className="text-slate-500">Branches:</span>{" "}
                        <span className="font-medium text-slate-800">{branchScope === "all" ? "All branches" : "Default only"}</span>
                      </div>
                      <div>
                        <span className="text-slate-500">Commit History:</span>{" "}
                        <span className="font-medium text-slate-800">{commitScope === "since" ? `Since ${commitSinceDate}` : "All available"}</span>
                      </div>
                      <div>
                        <span className="text-slate-500">Pull Requests:</span>{" "}
                        <span className="font-medium text-slate-800">{prScope === "open" ? "Open only" : "All PRs"}</span>
                      </div>
                      <div>
                        <span className="text-slate-500">Issues:</span>{" "}
                        <span className="font-medium text-slate-800">{issueScope === "open" ? "Open only" : "All issues"}</span>
                      </div>
                      <div>
                        <span className="text-slate-500">Source Code:</span>{" "}
                        <span className="font-medium text-slate-800">{includeCode ? "Enabled" : "Disabled"}</span>
                      </div>
                    </div>
                  </div>

                  <p className="text-[11px] text-slate-500 flex items-center gap-1.5">
                    <Info className="w-3.5 h-3.5 text-[#4774A9] shrink-0" />
                    <span>Sync runs in the background. You can navigate away and will receive an in-app notification when done.</span>
                  </p>

                  <div className="pt-2 flex items-center justify-between">
                    <button
                      type="button"
                      onClick={() => changeStep("configure_scope")}
                      className="text-xs text-slate-500 hover:text-slate-800"
                    >
                      &larr; Edit Scope
                    </button>
                    <button
                      type="button"
                      onClick={handleBatchIngest}
                      disabled={isSubmitting || !effectiveProjectId}
                      className="px-4 py-2 bg-[#4774A9] hover:bg-[#386295] disabled:opacity-50 text-white rounded-lg text-xs font-semibold flex items-center gap-2"
                    >
                      {isSubmitting ? (
                        <>
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          <span>Queueing Background Sync...</span>
                        </>
                      ) : (
                        <>
                          <Check className="w-3.5 h-3.5" />
                          <span>Confirm & Start Background Sync</span>
                        </>
                      )}
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ----------------- JIRA TAB ----------------- */}
          {activeTab === "jira" && (
            <div>
              {step === "credentials" ? (
                <div className="space-y-4">
                  <div className="p-3 rounded-lg bg-blue-50/50 border border-blue-200 flex items-start gap-3">
                    <SourceIcon type="jira" size={24} />
                    <div className="text-xs">
                      <span className="font-semibold text-slate-800">Atlassian Jira Cloud Connector</span>
                      <p className="text-slate-500 text-[11px] mt-0.5">
                        Connect with your Atlassian API Token. Accessible Jira projects will be discovered dynamically without typing project keys manually.
                      </p>
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-[#25334B] mb-1">
                      Atlassian Site Domain / URL
                    </label>
                    <input
                      type="text"
                      value={jiraUrl}
                      onChange={(e) => setJiraUrl(e.target.value)}
                      placeholder="e.g. company.atlassian.net"
                      className="w-full px-3 py-2 rounded-lg border border-[#DCE3EB] text-xs focus:outline-none focus:ring-2 focus:ring-[#4774A9]"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-[#25334B] mb-1">
                      Atlassian Account Email <span className="text-rose-500">*</span>
                    </label>
                    <input
                      type="email"
                      value={jiraEmail}
                      onChange={(e) => setJiraEmail(e.target.value)}
                      placeholder="e.g. user@company.com"
                      className="w-full px-3 py-2 rounded-lg border border-[#DCE3EB] text-xs focus:outline-none focus:ring-2 focus:ring-[#4774A9]"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-[#25334B] mb-1">
                      Atlassian API Token <span className="text-rose-500">*</span>
                    </label>
                    <input
                      type="password"
                      value={jiraToken}
                      onChange={(e) => setJiraToken(e.target.value)}
                      placeholder="ATATT3xFfGF0..."
                      className="w-full px-3 py-2 rounded-lg border border-[#DCE3EB] text-xs font-mono focus:outline-none focus:ring-2 focus:ring-[#4774A9]"
                    />
                  </div>

                  <div className="pt-2 flex justify-end">
                    <button
                      type="button"
                      onClick={handleDiscover}
                      disabled={isDiscovering || !jiraEmail || !jiraToken}
                      className="px-4 py-2 bg-[#4774A9] hover:bg-[#386295] disabled:opacity-50 text-white rounded-lg text-xs font-semibold flex items-center gap-2"
                    >
                      {isDiscovering ? (
                        <>
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          <span>Discovering Jira Projects...</span>
                        </>
                      ) : (
                        <>
                          <span>Verify & Discover Projects</span>
                          <ArrowRight className="w-3.5 h-3.5" />
                        </>
                      )}
                    </button>
                  </div>
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="text-xs font-bold text-slate-800">
                        Select Jira Projects ({discoveredProjects.length} discovered)
                      </h3>
                      <p className="text-[11px] text-slate-500">
                        Select projects to ingest issues, epics, changelogs, and task history.
                      </p>
                    </div>
                    <div className="flex gap-2 text-xs">
                      <button
                        type="button"
                        onClick={() => setSelectedProjectKeys(new Set(discoveredProjects.map((p) => p.key)))}
                        className="text-[#4774A9] hover:underline font-medium text-[11px]"
                      >
                        Select All
                      </button>
                      <span className="text-slate-300">|</span>
                      <button
                        type="button"
                        onClick={() => setSelectedProjectKeys(new Set())}
                        className="text-slate-500 hover:underline font-medium text-[11px]"
                      >
                        Clear
                      </button>
                    </div>
                  </div>

                  {/* Search filter */}
                  <div className="relative">
                    <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-slate-400" />
                    <input
                      type="text"
                      value={projectSearchFilter}
                      onChange={(e) => setProjectSearchFilter(e.target.value)}
                      placeholder="Filter projects..."
                      className="w-full pl-8 pr-3 py-1.5 rounded-lg border border-[#DCE3EB] text-xs focus:outline-none focus:ring-1 focus:ring-[#4774A9]"
                    />
                  </div>

                  <div className="max-h-60 overflow-y-auto border border-[#DCE3EB] rounded-lg divide-y divide-[#EBF0F5]">
                    {discoveredProjects
                      .filter((p) => p.name.toLowerCase().includes(projectSearchFilter.toLowerCase()) || p.key.toLowerCase().includes(projectSearchFilter.toLowerCase()))
                      .map((proj) => {
                        const isChecked = selectedProjectKeys.has(proj.key);
                        return (
                          <div
                            key={proj.key}
                            onClick={() => {
                              const next = new Set(selectedProjectKeys);
                              if (isChecked) next.delete(proj.key);
                              else next.add(proj.key);
                              setSelectedProjectKeys(next);
                            }}
                            className={`p-2.5 flex items-start gap-2.5 cursor-pointer hover:bg-slate-50 transition-colors ${
                              isChecked ? "bg-blue-50/50" : ""
                            }`}
                          >
                            <input
                              type="checkbox"
                              checked={isChecked}
                              onChange={() => {}}
                              className="mt-0.5 rounded text-[#4774A9] focus:ring-0"
                            />
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2">
                                <span className="text-xs font-semibold text-slate-900">{proj.name}</span>
                                <span className="px-1.5 py-0.2 text-[9px] font-mono bg-blue-100 text-blue-800 rounded font-bold">
                                  {proj.key}
                                </span>
                              </div>
                              <p className="text-[11px] text-slate-500 mt-0.5">
                                Type: {proj.project_type_key || "Software"}
                              </p>
                            </div>
                          </div>
                        );
                      })}
                  </div>

                  <div className="pt-2 flex items-center justify-between">
                    <button
                      type="button"
                      onClick={() => changeStep("credentials")}
                      className="text-xs text-slate-500 hover:text-slate-800"
                    >
                      &larr; Back to credentials
                    </button>
                    <button
                      type="button"
                      onClick={handleBatchIngest}
                      disabled={isSubmitting || selectedProjectKeys.size === 0 || !effectiveProjectId}
                      className="px-4 py-2 bg-[#4774A9] hover:bg-[#386295] disabled:opacity-50 text-white rounded-lg text-xs font-semibold flex items-center gap-2"
                    >
                      {isSubmitting ? (
                        <>
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          <span>Mapping & Starting Sync...</span>
                        </>
                      ) : (
                        <span>Ingest Selected ({selectedProjectKeys.size})</span>
                      )}
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ----------------- SLACK TAB ----------------- */}
          {activeTab === "slack" && (
            <div>
              {step === "credentials" ? (
                <div className="space-y-4">
                  <div className="p-3 rounded-lg bg-emerald-50/50 border border-emerald-200 flex items-start gap-3">
                    <SourceIcon type="slack" size={24} />
                    <div className="text-xs">
                      <span className="font-semibold text-slate-800">Slack Workspace Connector</span>
                      <p className="text-slate-500 text-[11px] mt-0.5">
                        Connect using your Slack Bot User OAuth Token (<code>xoxb-...</code>). Accessible public and private discussion channels will be discovered automatically.
                      </p>
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-[#25334B] mb-1">
                      Workspace Name / Identifier
                    </label>
                    <input
                      type="text"
                      value={slackDomain}
                      onChange={(e) => setSlackDomain(e.target.value)}
                      placeholder="e.g. engineering-workspace"
                      className="w-full px-3 py-2 rounded-lg border border-[#DCE3EB] text-xs focus:outline-none focus:ring-2 focus:ring-[#4774A9]"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-[#25334B] mb-1">
                      Bot User OAuth Token <span className="text-rose-500">*</span>
                    </label>
                    <input
                      type="password"
                      value={slackToken}
                      onChange={(e) => setSlackToken(e.target.value)}
                      placeholder="xoxb-..."
                      className="w-full px-3 py-2 rounded-lg border border-[#DCE3EB] text-xs font-mono focus:outline-none focus:ring-2 focus:ring-[#4774A9]"
                    />
                  </div>

                  <div className="pt-2 flex justify-end">
                    <button
                      type="button"
                      onClick={handleDiscover}
                      disabled={isDiscovering || !slackToken}
                      className="px-4 py-2 bg-[#4774A9] hover:bg-[#386295] disabled:opacity-50 text-white rounded-lg text-xs font-semibold flex items-center gap-2"
                    >
                      {isDiscovering ? (
                        <>
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          <span>Discovering Slack Channels...</span>
                        </>
                      ) : (
                        <>
                          <span>Verify & Discover Channels</span>
                          <ArrowRight className="w-3.5 h-3.5" />
                        </>
                      )}
                    </button>
                  </div>
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="text-xs font-bold text-slate-800">
                        Select Slack Channels ({discoveredChannels.length} discovered)
                      </h3>
                      <p className="text-[11px] text-slate-500">
                        Select channels to ingest discussions, decisions, and threads.
                      </p>
                    </div>
                    <div className="flex gap-2 text-xs">
                      <button
                        type="button"
                        onClick={() => setSelectedChannelIds(new Set(discoveredChannels.map((c) => c.id)))}
                        className="text-[#4774A9] hover:underline font-medium text-[11px]"
                      >
                        Select All
                      </button>
                      <span className="text-slate-300">|</span>
                      <button
                        type="button"
                        onClick={() => setSelectedChannelIds(new Set())}
                        className="text-slate-500 hover:underline font-medium text-[11px]"
                      >
                        Clear
                      </button>
                    </div>
                  </div>

                  <div className="relative">
                    <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-slate-400" />
                    <input
                      type="text"
                      value={channelSearchFilter}
                      onChange={(e) => setChannelSearchFilter(e.target.value)}
                      placeholder="Filter channels..."
                      className="w-full pl-8 pr-3 py-1.5 rounded-lg border border-[#DCE3EB] text-xs focus:outline-none focus:ring-1 focus:ring-[#4774A9]"
                    />
                  </div>

                  <div className="max-h-60 overflow-y-auto border border-[#DCE3EB] rounded-lg divide-y divide-[#EBF0F5]">
                    {discoveredChannels
                      .filter((c) => c.name.toLowerCase().includes(channelSearchFilter.toLowerCase()))
                      .map((ch) => {
                        const isChecked = selectedChannelIds.has(ch.id);
                        return (
                          <div
                            key={ch.id}
                            onClick={() => {
                              const next = new Set(selectedChannelIds);
                              if (isChecked) next.delete(ch.id);
                              else next.add(ch.id);
                              setSelectedChannelIds(next);
                            }}
                            className={`p-2.5 flex items-start gap-2.5 cursor-pointer hover:bg-slate-50 transition-colors ${
                              isChecked ? "bg-emerald-50/50" : ""
                            }`}
                          >
                            <input
                              type="checkbox"
                              checked={isChecked}
                              onChange={() => {}}
                              className="mt-0.5 rounded text-emerald-600 focus:ring-0"
                            />
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2">
                                <span className="text-xs font-semibold text-slate-900">#{ch.name}</span>
                                <span className="px-1.5 py-0.2 text-[9px] font-medium bg-slate-100 text-slate-600 rounded">
                                  {ch.is_private ? "Private" : "Public"} • {ch.num_members} members
                                </span>
                              </div>
                              {ch.topic && (
                                <p className="text-[11px] text-slate-500 truncate mt-0.5">{ch.topic}</p>
                              )}
                            </div>
                          </div>
                        );
                      })}
                  </div>

                  <div className="pt-2 flex items-center justify-between">
                    <button
                      type="button"
                      onClick={() => changeStep("credentials")}
                      className="text-xs text-slate-500 hover:text-slate-800"
                    >
                      &larr; Back to credentials
                    </button>
                    <button
                      type="button"
                      onClick={handleBatchIngest}
                      disabled={isSubmitting || selectedChannelIds.size === 0 || !effectiveProjectId}
                      className="px-4 py-2 bg-[#4774A9] hover:bg-[#386295] disabled:opacity-50 text-white rounded-lg text-xs font-semibold flex items-center gap-2"
                    >
                      {isSubmitting ? (
                        <>
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          <span>Mapping & Starting Sync...</span>
                        </>
                      ) : (
                        <span>Ingest Selected ({selectedChannelIds.size})</span>
                      )}
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ----------------- PDF & DOCX UPLOAD TAB ----------------- */}
          {activeTab === "docs" && (
            <form onSubmit={handleDocSubmit} className="space-y-4">
              {/* Category Selector */}
              <div>
                <label className="block text-xs font-semibold text-[#25334B] mb-1.5">
                  Document Intelligence Profile <span className="text-rose-500">*</span>
                </label>
                <div className="grid grid-cols-3 gap-2">
                  <button
                    type="button"
                    onClick={() => setDocCategory("team_roster")}
                    className={`p-2.5 rounded-lg border text-left transition-colors flex flex-col gap-1 ${
                      docCategory === "team_roster"
                        ? "border-[#4774A9] bg-blue-50/50 text-[#25334B] font-bold"
                        : "border-[#DCE3EB] bg-white text-slate-600 hover:bg-slate-50"
                    }`}
                  >
                    <div className="flex items-center gap-1.5">
                      <Users className="w-3.5 h-3.5 text-[#4774A9]" />
                      <span className="text-xs font-semibold">Team Roster</span>
                    </div>
                    <span className="text-[10px] text-slate-500 font-normal">
                      Members, roles, responsibilities & handles
                    </span>
                  </button>

                  <button
                    type="button"
                    onClick={() => setDocCategory("meeting_notes")}
                    className={`p-2.5 rounded-lg border text-left transition-colors flex flex-col gap-1 ${
                      docCategory === "meeting_notes"
                        ? "border-[#4774A9] bg-blue-50/50 text-[#25334B] font-bold"
                        : "border-[#DCE3EB] bg-white text-slate-600 hover:bg-slate-50"
                    }`}
                  >
                    <div className="flex items-center gap-1.5">
                      <Calendar className="w-3.5 h-3.5 text-[#4774A9]" />
                      <span className="text-xs font-semibold">Meeting Notes</span>
                    </div>
                    <span className="text-[10px] text-slate-500 font-normal">
                      Discussions, decisions & action items
                    </span>
                  </button>

                  <button
                    type="button"
                    onClick={() => setDocCategory("project_document")}
                    className={`p-2.5 rounded-lg border text-left transition-colors flex flex-col gap-1 ${
                      docCategory === "project_document"
                        ? "border-[#4774A9] bg-blue-50/50 text-[#25334B] font-bold"
                        : "border-[#DCE3EB] bg-white text-slate-600 hover:bg-slate-50"
                    }`}
                  >
                    <div className="flex items-center gap-1.5">
                      <Layers className="w-3.5 h-3.5 text-[#4774A9]" />
                      <span className="text-xs font-semibold">Project Spec</span>
                    </div>
                    <span className="text-[10px] text-slate-500 font-normal">
                      PRD, architecture, runbooks, design
                    </span>
                  </button>
                </div>
              </div>

              {/* Subtype Dropdown (if project_document) */}
              {docCategory === "project_document" && (
                <div>
                  <label className="block text-xs font-semibold text-[#25334B] mb-1">
                    Specification Subtype
                  </label>
                  <select
                    value={docSubtype}
                    onChange={(e) => setDocSubtype(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg border border-[#DCE3EB] text-xs focus:outline-none focus:ring-2 focus:ring-[#4774A9]"
                  >
                    <option value="prd">Product Requirements Document (PRD)</option>
                    <option value="srs">Software Requirements Specification (SRS)</option>
                    <option value="trd">Technical Requirements Document (TRD)</option>
                    <option value="dd">Detailed Design Document (DD)</option>
                    <option value="add">Architectural Decision Document (ADD / ADR)</option>
                    <option value="api_spec">API Specification</option>
                    <option value="database_design">Database Design / Schema Spec</option>
                    <option value="ui_ux_spec">UI / UX Design Specification</option>
                    <option value="test_plan">Test Plan & Verification Matrix</option>
                    <option value="deployment_guide">Deployment Guide</option>
                    <option value="runbook">Operational Runbook</option>
                    <option value="technical_doc">Technical Documentation</option>
                    <option value="contracts">Contracts & Legal Documentation</option>
                    <option value="other">Other Technical Document</option>
                  </select>
                </div>
              )}

              {/* Drag and Drop Zone */}
              <div>
                <label className="block text-xs font-semibold text-[#25334B] mb-1">
                  Upload PDF or DOCX File <span className="text-rose-500">*</span>
                </label>
                <div
                  onDragOver={(e) => {
                    e.preventDefault();
                    setIsDragOver(true);
                  }}
                  onDragLeave={() => setIsDragOver(false)}
                  onDrop={handleDrop}
                  onClick={() => fileInputRef.current?.click()}
                  className={`border-2 border-dashed rounded-xl p-6 flex flex-col items-center justify-center cursor-pointer transition-colors ${
                    isDragOver
                      ? "border-[#4774A9] bg-blue-50/50"
                      : selectedFile
                      ? "border-emerald-400 bg-emerald-50/30"
                      : "border-[#DCE3EB] hover:border-[#4774A9]/50 hover:bg-slate-50/50"
                  }`}
                >
                  <input
                    type="file"
                    ref={fileInputRef}
                    onChange={handleFileChange}
                    accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    className="hidden"
                  />
                  {selectedFile ? (
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-lg bg-emerald-100 text-emerald-700 flex items-center justify-center font-bold text-xs uppercase">
                        {selectedFile.name.split(".").pop()}
                      </div>
                      <div className="text-left">
                        <p className="text-xs font-bold text-slate-800">{selectedFile.name}</p>
                        <p className="text-[11px] text-slate-500">
                          {(selectedFile.size / (1024 * 1024)).toFixed(2)} MB • Ready for processing
                        </p>
                      </div>
                    </div>
                  ) : (
                    <>
                      <UploadCloud className="w-8 h-8 text-[#4774A9] mb-2" />
                      <p className="text-xs font-semibold text-slate-700">Click to upload or drag & drop</p>
                      <p className="text-[11px] text-slate-400 mt-0.5">PDF or DOCX (digital text + OCR for scanned pages)</p>
                    </>
                  )}
                </div>
              </div>

              {/* Custom Title */}
              <div>
                <label className="block text-xs font-semibold text-[#25334B] mb-1">
                  Display Title (Optional)
                </label>
                <input
                  type="text"
                  value={docCustomTitle}
                  onChange={(e) => setDocCustomTitle(e.target.value)}
                  placeholder="e.g. Q4 Sprint Team Roster & Ownership"
                  className="w-full px-3 py-2 rounded-lg border border-[#DCE3EB] text-xs focus:outline-none focus:ring-2 focus:ring-[#4774A9]"
                />
              </div>

              <div className="pt-2 flex justify-end">
                <button
                  type="submit"
                  disabled={isSubmitting || !selectedFile || !effectiveProjectId}
                  className="px-4 py-2 bg-[#4774A9] hover:bg-[#386295] disabled:opacity-50 text-white rounded-lg text-xs font-semibold flex items-center gap-2"
                >
                  {isSubmitting ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      <span>Ingesting & Processing...</span>
                    </>
                  ) : (
                    <span>Upload & Extract Intelligence</span>
                  )}
                </button>
              </div>
            </form>
          )}

          {/* ----------------- CONFLUENCE & GDRIVE (PLANNED) ----------------- */}
          {(activeTab === "confluence" || activeTab === "gdrive") && (
            <div className="py-8 text-center space-y-4">
              <div className="w-14 h-14 mx-auto rounded-full bg-amber-50 border border-amber-200 flex items-center justify-center">
                <SourceIcon type={activeTab as SourceType} size={32} />
              </div>
              <div className="max-w-md mx-auto space-y-1.5">
                <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 text-xs font-semibold bg-amber-100 text-amber-800 rounded-full border border-amber-200">
                  <span>Planned Connector</span>
                </div>
                <h3 className="text-sm font-bold text-slate-800">
                  {activeTab === "confluence" ? "Atlassian Confluence" : "Google Drive"} Integration
                </h3>
                <p className="text-xs text-slate-500 leading-relaxed">
                  Direct connection for {activeTab === "confluence" ? "Confluence spaces" : "Google Drive shared folders"} is scheduled for an upcoming platform release.
                  In the meantime, you can export your spaces or docs as PDF/DOCX files and upload them under the <strong>PDF & DOCX</strong> tab for full extraction.
                </p>
              </div>
              <div className="pt-2">
                <button
                  type="button"
                  disabled
                  className="px-4 py-2 bg-slate-200 text-slate-400 rounded-lg text-xs font-semibold cursor-not-allowed"
                >
                  Connector Available in Next Phase
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
