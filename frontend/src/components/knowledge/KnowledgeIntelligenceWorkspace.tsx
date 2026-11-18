"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import type { Node } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  Cpu,
  Layers,
  Workflow,
  BookOpen,
  Search,
  RefreshCw,
  ExternalLink,
  ShieldCheck,
  GitBranch,
  AlertCircle,
  Table as TableIcon,
  Network,
  FileText,
  X,
} from "lucide-react";
import { api } from "@/lib/api";
import { useLiveApp } from "@/context/LiveAppContext";
import { AmeliorateFlowchartCanvas } from "@/components/knowledge/ameliorate/AmeliorateFlowchartCanvas";
import { getCachedGraph, setCachedGraph, invalidateGraphCache } from "@/lib/graphCache";
import { useProjectProcessingStatus } from "@/hooks/useProjectProcessingStatus";
import { ProcessingEmptyStateCard } from "@/components/knowledge/LiveProcessingBanner";

type KnowledgeMode =
  | "technology-stack"
  | "system-architecture"
  | "features-workflows"
  | "domains";

interface KIGraphNode {
  id: string;
  entity_type: string;
  label: string;
  description?: string | null;
  category?: string | null;
  status: string;
  verification_status: string;
  evidence_count: number;
  evidence_ids: string[];
  aliases: string[];
  last_observed_at?: string | null;
  metadata: Record<string, unknown>;
}

interface KIGraphEdge {
  id: string;
  source: string;
  target: string;
  relationship_type: string;
  label: string;
  evidence_basis: string;
  verification_status: string;
  confidence_score: number;
  evidence_ids: string[];
}

const DOMAIN_DEFS: Array<{ id: string; label: string; desc: string }> = [
  { id: "PROJECT_OVERVIEW_CONTEXT", label: "Project Overview & Context", desc: "Mission, scope, goals, and product positioning" },
  { id: "DECISIONS_RATIONALE", label: "Decisions & Rationale", desc: "Architectural choices, trade-offs, and ADRs" },
  { id: "ARCHITECTURE_TECHNICAL", label: "Technical & Architecture", desc: "System layers, services, APIs, and databases" },
  { id: "WORK_PROGRESS", label: "Completed & Unfinished Work", desc: "Features, deliverables, and sprint progress" },
  { id: "RESPONSIBILITIES_OWNERSHIP", label: "Responsibilities & Ownership", desc: "Module owners, maintainers, and roles" },
  { id: "DEPENDENCIES_RELATIONSHIPS", label: "Dependencies", desc: "Internal and external technical dependencies" },
  { id: "RISKS_BLOCKERS_QUESTIONS", label: "Bugs, Blockers & Risks", desc: "Known operational risks, gaps, and blockers" },
  { id: "OPERATIONAL_HISTORICAL", label: "Operational & Historical", desc: "Runbooks, deployment notes, and past context" },
];

class CanvasErrorBoundary extends React.Component<
  { children: React.ReactNode; onReset: () => void },
  { hasError: boolean; error: Error | null }
> {
  constructor(props: { children: React.ReactNode; onReset: () => void }) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  override componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error("Canvas render error caught by boundary:", error, info);
  }

  override render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center h-full p-8 text-center bg-slate-50">
          <AlertCircle className="w-10 h-10 text-amber-500 mb-3" />
          <p className="text-base font-medium text-slate-800">
            Graph visualization encountered an unexpected rendering error.
          </p>
          <p className="text-xs text-slate-500 mt-1 max-w-md">
            {this.state.error?.message || "An issue occurred while laying out nodes."}
          </p>
          <button
            type="button"
            onClick={() => {
              this.setState({ hasError: false, error: null });
              this.props.onReset();
            }}
            className="mt-4 px-4 py-2 rounded-lg bg-blue-600 text-xs font-medium text-white hover:bg-blue-700 inline-flex items-center gap-1.5"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Reload Graph View
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export function KnowledgeIntelligenceWorkspace({
  projectId,
  initialMode = "technology-stack",
}: {
  projectId: string;
  initialMode?: KnowledgeMode;
}) {
  const { findings: liveFindings, refreshFindings, refreshVerification } = useLiveApp();
  const [mode, setMode] = useState<KnowledgeMode>(initialMode);
  const [viewKind, setViewKind] = useState<"graph" | "list">("graph");
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [verificationFilter, setVerificationFilter] = useState("all");
  const [includeSuggested, setIncludeSuggested] = useState(true);

  const [rawNodes, setRawNodes] = useState<KIGraphNode[]>([]);
  const [rawEdges, setRawEdges] = useState<KIGraphEdge[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [selectedNodeDetail, setSelectedNodeDetail] = useState<{
    node: KIGraphNode;
    evidence_refs: Array<{
      evidence_id: string;
      title: string;
      source_type: string;
      source_url?: string | null;
      supporting_excerpt?: string | null;
    }>;
    adjacent_edges: Array<Record<string, unknown>>;
    related_nodes: Array<Record<string, unknown>>;
  } | null>(null);

  // Domain register state
  const [selectedDomain, setSelectedDomain] = useState<string>("all");
  const [domainFindings, setDomainFindings] = useState<Record<string, unknown>[]>([]);
  const [selectedFinding, setSelectedFinding] = useState<Record<string, unknown> | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [reloadCounter, setReloadCounter] = useState(0);

  const handleRefresh = useCallback(() => {
    invalidateGraphCache(`ki_graph:${projectId}`);
    invalidateGraphCache(`ki_domains:${projectId}`);
    setReloadCounter((c) => c + 1);
  }, [projectId]);

  const {
    status: processingStatus,
    retry: retryProcessing,
    retrying: retryingProcessing,
  } = useProjectProcessingStatus(projectId, {
    onProcessingComplete: handleRefresh,
  });

  // Project/mode switch cleanup & signature tracking to preserve selected drawer during live updates
  const activeProjectIdRef = useRef(projectId);
  const lastGraphSignatureRef = useRef<string>("");

  const computeGraphSignature = (nodes: KIGraphNode[], edges: KIGraphEdge[]) =>
    `${nodes.map((n) => `${n.id}:${n.status}:${n.verification_status}:${n.evidence_count}`).join("|")}||${edges.map((e) => `${e.id}:${e.relationship_type}:${e.verification_status}`).join("|")}`;

  useEffect(() => {
    activeProjectIdRef.current = projectId;
    lastGraphSignatureRef.current = "";
    setRawNodes([]);
    setRawEdges([]);
    setDomainFindings([]);
    setSelectedNodeDetail(null);
  }, [projectId]);

  useEffect(() => {
    lastGraphSignatureRef.current = "";
    setSelectedNodeDetail(null);
  }, [projectId, mode]);

  const loadDomains = useCallback(async () => {
    if (!projectId || mode !== "domains") return;
    const targetProjectId = projectId;
    const cacheKey = `ki_domains:${projectId}:${selectedDomain}`;
    const cached = getCachedGraph<Record<string, unknown>[]>(cacheKey);
    if (cached && cached.length > 0) {
      if (activeProjectIdRef.current === targetProjectId) {
        setDomainFindings(cached);
        setLoading(false);
        setError(null);
      }
      return;
    }
    if (rawNodes.length === 0) {
      setLoading(true);
    }
    setError(null);
    try {
      const res = await api.knowledgeIntelligence.listFindings(
        projectId,
        selectedDomain !== "all" ? selectedDomain : undefined,
        100,
        0
      );
      if (activeProjectIdRef.current !== targetProjectId) return;
      setDomainFindings(res.items || []);
      setCachedGraph(cacheKey, res.items || []);
    } catch (err) {
      if (activeProjectIdRef.current !== targetProjectId) return;
      setError(err instanceof Error ? err.message : "Failed to load reconstructed knowledge findings.");
    } finally {
      if (activeProjectIdRef.current === targetProjectId) {
        setLoading(false);
      }
    }
  }, [projectId, mode, selectedDomain, reloadCounter]);

  useEffect(() => {
    if (mode === "domains") {
      void loadDomains();
    }
  }, [mode, loadDomains]);

  useEffect(() => {
    if (mode === "domains" || !projectId) return;
    let isCurrent = true;
    const targetProjectId = projectId;

    const cacheKey = `ki_graph:${projectId}:${mode}:${statusFilter}:${verificationFilter}:${includeSuggested}:${searchQuery.trim()}`;
    const cached = getCachedGraph<{ nodes: KIGraphNode[]; edges: KIGraphEdge[] }>(cacheKey);
    if (cached && cached.nodes && cached.nodes.length > 0) {
      if (activeProjectIdRef.current === targetProjectId) {
        const nextNodes = cached.nodes;
        const nextEdges = cached.edges || [];
        const nextSig = computeGraphSignature(nextNodes, nextEdges);
        if (nextSig !== lastGraphSignatureRef.current) {
          lastGraphSignatureRef.current = nextSig;
          setRawNodes(nextNodes);
          setRawEdges(nextEdges);
        }
        setLoading(false);
        setError(null);
      }
      return;
    }

    if (rawNodes.length === 0) {
      setLoading(true);
    }
    setError(null);
    api.knowledgeIntelligence
      .getGraph(projectId, mode, {
        search: searchQuery.trim() || undefined,
        status: statusFilter !== "all" ? statusFilter : undefined,
        verification_state: verificationFilter !== "all" ? verificationFilter : undefined,
        include_suggested: includeSuggested,
      })
      .then((res) => {
        if (!isCurrent || activeProjectIdRef.current !== targetProjectId) return;
        const nextNodes = res.nodes || [];
        const nextEdges = res.edges || [];
        const nextSig = computeGraphSignature(nextNodes, nextEdges);
        if (nextSig !== lastGraphSignatureRef.current) {
          lastGraphSignatureRef.current = nextSig;
          setRawNodes(nextNodes);
          setRawEdges(nextEdges);
        }
        setCachedGraph(cacheKey, { nodes: nextNodes, edges: nextEdges });
      })
      .catch((err) => {
        if (!isCurrent || activeProjectIdRef.current !== targetProjectId) return;
        setError(err instanceof Error ? err.message : "Failed to load Knowledge Intelligence graph.");
      })
      .finally(() => {
        if (isCurrent && activeProjectIdRef.current === targetProjectId) {
          setLoading(false);
        }
      });
    return () => {
      isCurrent = false;
    };
  }, [projectId, mode, searchQuery, statusFilter, verificationFilter, includeSuggested, reloadCounter]);

  const handleSelectNode = async (_: unknown, node: Node) => {
    if (mode === "domains") return;
    const raw = (node.data as { raw?: KIGraphNode })?.raw;
    if (!raw) return;
    try {
      const detail = await api.knowledgeIntelligence.getGraphNodeDetail(projectId, mode, raw.id);
      setSelectedNodeDetail({
        node: detail.node as unknown as KIGraphNode,
        evidence_refs: detail.evidence_refs || [],
        adjacent_edges: detail.adjacent_edges || [],
        related_nodes: detail.related_nodes || [],
      });
    } catch {
      setSelectedNodeDetail({
        node: raw,
        evidence_refs: [],
        adjacent_edges: [],
        related_nodes: [],
      });
    }
  };

  const handleVerifyFinding = async (findingId: string, decision: "approve" | "flag" | "reject") => {
    setActionMessage(null);
    try {
      const kCase = await api.verification.assessTarget(projectId, "knowledge_item", findingId);
      const caseId = kCase?.id ? String(kCase.id) : null;
      if (!caseId) {
        setActionMessage("Could not retrieve verification case for this finding.");
        return;
      }
      if (decision === "approve") {
        await api.verification.approveCase(projectId, caseId, "Verified in Knowledge Intelligence");
      } else if (decision === "flag") {
        await api.verification.markUnresolved(projectId, caseId, "Flagged in Knowledge Intelligence");
      } else {
        await api.verification.rejectCase(projectId, caseId, "Rejected in Knowledge Intelligence");
      }
      setActionMessage("Verification decision recorded.");
      await Promise.all([loadDomains(), refreshFindings(), refreshVerification()]);
    } catch (err) {
      setActionMessage(err instanceof Error ? err.message : "Failed to submit verification.");
    }
  };

  const filteredDomainFindings = useMemo(() => {
    const items = domainFindings.length > 0 ? domainFindings : (liveFindings as unknown as Record<string, unknown>[]);
    return items.filter((item) => {
      if (item.is_stale) return false;
      const title = String(item.title || "").toLowerCase();
      const summary = String(item.structured_summary || item.summary || "").toLowerCase();
      if (searchQuery.trim() && !title.includes(searchQuery.toLowerCase()) && !summary.includes(searchQuery.toLowerCase())) {
        return false;
      }
      if (verificationFilter !== "all" && String(item.review_status || "").toLowerCase() !== verificationFilter.toLowerCase()) {
        return false;
      }
      if (selectedDomain !== "all") {
        const pDom = String(item.primary_domain || item.category || "").toUpperCase();
        if (pDom !== selectedDomain) return false;
      }
      return true;
    });
  }, [domainFindings, liveFindings, searchQuery, verificationFilter, selectedDomain]);

  if (!projectId) {
    return (
      <div className="p-8 text-center text-slate-500">
        <p className="font-medium text-slate-800">Select a project workspace to view Knowledge Intelligence.</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] bg-slate-50">
      {/* Header */}
      <div className="bg-white border-b border-slate-200 px-6 py-4">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold text-slate-900">Knowledge Intelligence</h1>
            <p className="text-sm text-slate-500">
              Understand your project&apos;s technology, architecture, features and reconstructed knowledge.
            </p>
          </div>
          <div className="flex items-center gap-2">
            {mode !== "domains" && (
              <button
                type="button"
                onClick={() => setViewKind(viewKind === "graph" ? "list" : "graph")}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 bg-white text-xs font-medium text-slate-700 hover:bg-slate-50"
              >
                {viewKind === "graph" ? <TableIcon className="w-3.5 h-3.5" /> : <Network className="w-3.5 h-3.5" />}
                {viewKind === "graph" ? "Table Fallback" : "Graph View"}
              </button>
            )}
            <button
              type="button"
              onClick={handleRefresh}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 bg-white text-xs font-medium text-slate-700 hover:bg-slate-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
              Refresh
            </button>
            <Link
              href={`/projects/${projectId}/evidence`}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 text-xs font-medium text-white hover:bg-blue-700"
            >
              <FileText className="w-3.5 h-3.5" />
              Evidence Center
            </Link>
          </div>
        </div>

        {/* Four Primary Modes */}
        <div className="flex flex-wrap items-center gap-2 mt-4" role="tablist" aria-label="Knowledge Intelligence views">
          {(
            [
              { id: "technology-stack", label: "Technology Stack", Icon: Cpu },
              { id: "system-architecture", label: "System Architecture", Icon: Layers },
              { id: "features-workflows", label: "Features & Workflows", Icon: Workflow },
              { id: "domains", label: "Knowledge Domains", Icon: BookOpen },
            ] as const
          ).map(({ id, label, Icon }) => (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={mode === id}
              onClick={() => setMode(id)}
              className={`inline-flex items-center gap-2 px-3.5 py-2 rounded-lg text-sm font-medium transition-colors ${
                mode === id
                  ? "bg-blue-600 text-white shadow-sm"
                  : "bg-slate-100 text-slate-700 hover:bg-slate-200"
              }`}
            >
              <Icon className="w-4 h-4" />
              {label}
            </button>
          ))}
        </div>

        {/* Toolbar Filters */}
        <div className="flex flex-wrap items-center gap-3 mt-3">
          <div className="relative flex-1 min-w-[220px] max-w-sm">
            <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search nodes, technologies, components, findings..."
              aria-label="Search knowledge graph"
              className="w-full pl-9 pr-3 py-1.5 text-sm bg-white border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          {mode !== "domains" ? (
            <>
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                aria-label="Filter by implementation basis"
                className="px-3 py-1.5 text-sm bg-white border border-slate-200 rounded-lg text-slate-700"
              >
                <option value="all">All statuses</option>
                <option value="declared_dependency">Declared Dependency</option>
                <option value="documented_only">Documented Only</option>
                <option value="implementation_evidenced">Implementation Evidenced</option>
                <option value="verified_implementation">Verified Implementation</option>
                <option value="proposed">Proposed</option>
                <option value="PLANNED">Planned</option>
                <option value="IN_PROGRESS">In Progress</option>
                <option value="HUMAN_VERIFIED">Human Verified</option>
              </select>
              <label className="inline-flex items-center gap-1.5 text-xs text-slate-600">
                <input
                  type="checkbox"
                  checked={includeSuggested}
                  onChange={(e) => setIncludeSuggested(e.target.checked)}
                />
                Show AI-suggested edges
              </label>
            </>
          ) : (
            <select
              value={selectedDomain}
              onChange={(e) => setSelectedDomain(e.target.value)}
              aria-label="Filter by knowledge domain"
              className="px-3 py-1.5 text-sm bg-white border border-slate-200 rounded-lg text-slate-700"
            >
              <option value="all">All 8 Domains</option>
              {DOMAIN_DEFS.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.label}
                </option>
              ))}
            </select>
          )}
          <select
            value={verificationFilter}
            onChange={(e) => setVerificationFilter(e.target.value)}
            aria-label="Filter by verification status"
            className="px-3 py-1.5 text-sm bg-white border border-slate-200 rounded-lg text-slate-700"
          >
            <option value="all">All verification states</option>
            <option value="approved">Human Verified</option>
            <option value="pending_review">Pending Review</option>
            <option value="rejected">Rejected</option>
          </select>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 relative overflow-hidden">
        {error && (
          <div className="m-4 p-3 rounded-lg bg-red-50 border border-red-200 flex items-center justify-between text-sm text-red-700">
            <span className="flex items-center gap-2">
              <AlertCircle className="w-4 h-4" />
              {error}
            </span>
            <button
              type="button"
              onClick={handleRefresh}
              className="underline font-medium"
            >
              Retry
            </button>
          </div>
        )}


        {mode !== "domains" ? (
          rawNodes.length === 0 && !loading ? (
            <ProcessingEmptyStateCard
              status={processingStatus}
              onRetry={retryProcessing}
              retrying={retryingProcessing}
              projectId={projectId}
            />
          ) : viewKind === "list" ? (
            <div className="p-6 h-full overflow-y-auto">
              <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
                <table className="w-full text-left text-sm">
                  <thead className="bg-slate-50 border-b border-slate-200 text-xs uppercase text-slate-500">
                    <tr>
                      <th className="px-4 py-3">Name</th>
                      <th className="px-4 py-3">Type</th>
                      <th className="px-4 py-3">Category</th>
                      <th className="px-4 py-3">Status</th>
                      <th className="px-4 py-3">Verification</th>
                      <th className="px-4 py-3">Evidence</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {rawNodes.map((n) => (
                      <tr
                        key={n.id}
                        className="hover:bg-slate-50 cursor-pointer"
                        onClick={() => handleSelectNode(null, { id: n.id, position: { x: 0, y: 0 }, data: { raw: n } } as Node)}
                      >
                        <td className="px-4 py-3 font-medium text-slate-900">{n.label}</td>
                        <td className="px-4 py-3 text-slate-600">{n.entity_type}</td>
                        <td className="px-4 py-3 text-slate-600">{n.category || "-"}</td>
                        <td className="px-4 py-3 text-slate-700">{n.status}</td>
                        <td className="px-4 py-3 text-slate-600">{n.verification_status}</td>
                        <td className="px-4 py-3 text-slate-600">{n.evidence_count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <CanvasErrorBoundary onReset={handleRefresh}>
              <AmeliorateFlowchartCanvas
                key={mode}
                rawNodes={rawNodes}
                rawEdges={rawEdges}
                selectedNodeId={selectedNodeDetail?.node.id ?? null}
                onSelectNode={(node) => handleSelectNode(null, node)}
              />
            </CanvasErrorBoundary>
          )
        ) : (
          /* 8-Domain Knowledge Register */
          <div className="p-6 h-full overflow-y-auto space-y-4">
            {actionMessage && (
              <div className="p-3 rounded-lg bg-blue-50 border border-blue-200 text-sm text-blue-800">
                {actionMessage}
              </div>
            )}
            {filteredDomainFindings.length === 0 && !loading ? (
              <div className="flex flex-col items-center justify-center py-20 text-center bg-white rounded-xl border border-slate-200">
                <BookOpen className="w-10 h-10 text-slate-300 mb-2" />
                <p className="text-base font-medium text-slate-800">
                  No project knowledge has been reconstructed yet.
                </p>
                <Link
                  href={`/projects/${projectId}/evidence`}
                  className="mt-3 inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-blue-600 text-xs font-medium text-white hover:bg-blue-700"
                >
                  Go to Evidence Center
                </Link>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {filteredDomainFindings.map((f) => {
                  const id = String(f.id);
                  const links = (f.evidence_links || f.citations || []) as Array<Record<string, unknown>>;
                  const firstEvId = links[0]?.evidence_id ? String(links[0].evidence_id) : null;
                  return (
                    <div
                      key={id}
                      className="bg-white border border-slate-200 rounded-xl p-4 flex flex-col justify-between gap-3"
                    >
                      <div>
                        <div className="flex items-center justify-between gap-2 text-xs mb-1.5">
                          <span className="px-2 py-0.5 rounded bg-slate-100 text-slate-700 font-medium">
                            {String(f.primary_domain || f.category || "GENERAL")}
                          </span>
                          <span className="px-2 py-0.5 rounded bg-blue-50 text-blue-700 font-medium">
                            {String(f.epistemic_status || "extracted")} · {String(f.review_status || "pending_review")}
                          </span>
                        </div>
                        <h3 className="font-semibold text-slate-900 text-sm">{String(f.title || "")}</h3>
                        <p className="text-xs text-slate-600 mt-1 line-clamp-3">
                          {String(f.structured_summary || f.summary || "")}
                        </p>
                      </div>
                      <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-slate-100 text-xs">
                        <div className="flex items-center gap-2">
                          {firstEvId && (
                            <Link
                              href={`/projects/${projectId}/evidence/${firstEvId}`}
                              className="inline-flex items-center gap-1 text-blue-600 hover:underline font-medium"
                            >
                              Open Evidence
                              <ExternalLink className="w-3 h-3" />
                            </Link>
                          )}
                          <button
                            type="button"
                            onClick={() => setSelectedFinding(f)}
                            className="text-slate-600 hover:text-slate-900 font-medium"
                          >
                            Details
                          </button>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <button
                            type="button"
                            onClick={() => handleVerifyFinding(id, "approve")}
                            className="px-2 py-1 rounded bg-emerald-50 text-emerald-700 hover:bg-emerald-100 font-medium"
                          >
                            Verify
                          </button>
                          <button
                            type="button"
                            onClick={() => handleVerifyFinding(id, "flag")}
                            className="px-2 py-1 rounded bg-amber-50 text-amber-700 hover:bg-amber-100 font-medium"
                          >
                            Flag
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* Right Details Drawer for Graph Nodes */}
        {selectedNodeDetail && mode !== "domains" && (
          <div className="absolute right-4 top-4 bottom-4 w-96 bg-white border border-slate-200 rounded-xl shadow-xl p-5 z-20 overflow-y-auto">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <span className="text-xs font-semibold px-2 py-0.5 rounded bg-blue-50 text-blue-700 uppercase">
                {selectedNodeDetail.node.entity_type}
              </span>
              <button
                type="button"
                aria-label="Close node details"
                onClick={() => setSelectedNodeDetail(null)}
                className="text-slate-400 hover:text-slate-700"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <h2 className="font-semibold text-slate-900 mt-3 text-base">{selectedNodeDetail.node.label}</h2>
            {selectedNodeDetail.node.description && (
              <p className="text-xs text-slate-600 mt-1.5 leading-relaxed">
                {selectedNodeDetail.node.description}
              </p>
            )}
            <div className="mt-4 space-y-2 text-xs border-t border-slate-100 pt-3">
              <div className="flex justify-between">
                <span className="text-slate-400">Status / Basis:</span>
                <span className="font-medium text-slate-800">{selectedNodeDetail.node.status}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Verification:</span>
                <span className="font-medium text-slate-800">{selectedNodeDetail.node.verification_status}</span>
              </div>
              {Boolean(selectedNodeDetail.node.metadata?.version) && (
                <div className="flex justify-between">
                  <span className="text-slate-400">Version:</span>
                  <span className="font-medium text-slate-800">{String(selectedNodeDetail.node.metadata.version)}</span>
                </div>
              )}
              {selectedNodeDetail.node.aliases.length > 0 && (
                <div>
                  <span className="text-slate-400 block mb-1">Aliases:</span>
                  <div className="flex flex-wrap gap-1">
                    {selectedNodeDetail.node.aliases.map((a) => (
                      <span key={a} className="px-2 py-0.5 rounded bg-slate-100 text-slate-700">
                        {a}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className="mt-4 pt-3 border-t border-slate-100">
              <h3 className="text-xs font-semibold uppercase text-slate-500 mb-2">
                Supporting Evidence ({selectedNodeDetail.evidence_refs.length})
              </h3>
              {selectedNodeDetail.evidence_refs.length === 0 ? (
                <p className="text-xs text-slate-400">No accessible evidence links returned.</p>
              ) : (
                <div className="space-y-2">
                  {selectedNodeDetail.evidence_refs.map((ev) => (
                    <div key={ev.evidence_id} className="p-2.5 rounded-lg bg-slate-50 border border-slate-200">
                      <Link
                        href={`/projects/${projectId}/evidence/${ev.evidence_id}`}
                        className="text-xs font-medium text-blue-600 hover:underline flex items-center justify-between gap-1"
                      >
                        <span className="truncate">{ev.title}</span>
                        <ExternalLink className="w-3 h-3 shrink-0" />
                      </Link>
                      {Boolean(ev.supporting_excerpt) && (
                        <p className="text-[11px] text-slate-500 mt-1 line-clamp-2">{ev.supporting_excerpt}</p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="mt-4 pt-3 border-t border-slate-100 flex flex-col gap-2">
              <Link
                href={`/projects/${projectId}/relationships?entityId=${selectedNodeDetail.node.id}`}
                className="inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg bg-blue-600 text-xs font-medium text-white hover:bg-blue-700"
              >
                <GitBranch className="w-3.5 h-3.5" />
                Explore Relationships
              </Link>
              <Link
                href={`/projects/${projectId}/verification`}
                className="inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg border border-slate-200 text-xs font-medium text-slate-700 hover:bg-slate-50"
              >
                <ShieldCheck className="w-3.5 h-3.5" />
                Open Verification Center
              </Link>
            </div>
          </div>
        )}

        {/* Selected Domain Finding Drawer */}
        {selectedFinding && mode === "domains" && (
          <div className="absolute right-4 top-4 bottom-4 w-96 bg-white border border-slate-200 rounded-xl shadow-xl p-5 z-20 overflow-y-auto">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <span className="text-xs font-semibold text-blue-700">
                {String(selectedFinding.primary_domain || selectedFinding.category || "")}
              </span>
              <button
                type="button"
                aria-label="Close finding details"
                onClick={() => setSelectedFinding(null)}
                className="text-slate-400 hover:text-slate-700"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <h2 className="font-semibold text-slate-900 mt-3 text-base">{String(selectedFinding.title || "")}</h2>
            <p className="text-xs text-slate-600 mt-2 leading-relaxed">
              {String(selectedFinding.structured_summary || selectedFinding.summary || "")}
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => handleVerifyFinding(String(selectedFinding.id), "approve")}
                className="flex-1 py-2 rounded-lg bg-emerald-600 text-xs font-medium text-white hover:bg-emerald-700"
              >
                Verify Finding
              </button>
              <button
                type="button"
                onClick={() => handleVerifyFinding(String(selectedFinding.id), "flag")}
                className="flex-1 py-2 rounded-lg border border-amber-300 bg-amber-50 text-xs font-medium text-amber-800 hover:bg-amber-100"
              >
                Flag Finding
              </button>
              <button
                type="button"
                onClick={() => handleVerifyFinding(String(selectedFinding.id), "reject")}
                className="py-2 px-3 rounded-lg border border-red-200 text-xs font-medium text-red-600 hover:bg-red-50"
              >
                Reject
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
