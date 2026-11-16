"use client";

import React, { useState, useEffect, useCallback, useMemo } from "react";
import Link from "next/link";
import {
  ReactFlow,
  Controls,
  Background,
  MiniMap,
  useNodesState,
  useEdgesState,
  MarkerType,
  type Node,
  type Edge,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  Network,
  Search,
  Layers,
  GitBranch,
  ShieldAlert,
  Clock,
  Eye,
  RefreshCw,
  Users,
  Bot,
  UserCheck,
  HelpCircle,
  ExternalLink,
  Briefcase,
  Boxes,
  Table as TableIcon,
  X,
  CheckCircle2,
  UserX,
  RotateCcw,
} from "lucide-react";
import { api } from "../../lib/api";
import { useLiveApp } from "../../context/LiveAppContext";

export interface KnowledgeEntityNode {
  id: string;
  label?: string;
  type?: string;
  entity_type?: string;
  canonical_name?: string;
  confidence?: number;
  resolution_status?: string;
  status?: string;
  verification_status?: string;
  description?: string | null;
  source_provider?: string | null;
}

export interface KnowledgeEntityItem {
  id: string;
  canonical_name: string;
  entity_type: string;
  confidence_score: number;
  resolution_status: string;
  description?: string;
  created_at?: string;
}

export interface TraceabilityChainItem {
  id: string;
  decision_entity_id: string;
  decision_name?: string;
  completeness_status: string;
  work_item_count?: number;
  pr_count?: number;
  commit_count?: number;
  component_count?: number;
  work_item_ids?: string[];
  pull_request_ids?: string[];
  commit_ids?: string[];
  component_ids?: string[];
  missing_links: string[];
}

export interface DependencyGraphData {
  nodes: Array<{
    entity_id?: string;
    id?: string;
    name?: string;
    label?: string;
    entity_type: string;
    status?: string;
    is_root_blocker?: boolean;
    in_degree?: number;
    out_degree?: number;
  }>;
  edges: Array<{
    source?: string;
    source_id?: string;
    target?: string;
    target_id?: string;
    relationship_type?: string;
    dependency_type?: string;
  }>;
  cycles?: string[][];
  detected_cycles?: string[][];
  root_blockers?: Array<{ entity_id?: string; name?: string; entity_type?: string } | string>;
}

export interface TimelineEventItem {
  id: string;
  event_type: string;
  title: string;
  summary?: string;
  occurred_at: string;
  timestamp_precision: string;
  timestamp_origin: string;
}

export interface IdentityCandidateItem {
  id: string;
  left_entity_name?: string;
  left_entity_id?: string;
  right_entity_name?: string;
  right_entity_id?: string;
  left_entity?: { canonical_name?: string; id?: string };
  right_entity?: { canonical_name?: string; id?: string };
  match_score: number;
  policy_band?: string;
}

type RelationshipTab =
  | "people"
  | "clusters"
  | "traceability"
  | "responsibilities"
  | "dependencies"
  | "timeline"
  | "identity_review";

interface ContributorRecord {
  contributor_key: string;
  display_name: string;
  github_login?: string | null;
  github_numeric_id?: string | null;
  git_author_name?: string | null;
  git_author_email?: string | null;
  contributor_type: string;
  review_status: string;
  match_method?: string | null;
  match_confidence?: number | null;
  matched_project_membership_id?: string | null;
  matched_member_name?: string | null;
  suggested_project_membership_id?: string | null;
  suggested_member_name?: string | null;
  declared_responsibility?: string | null;
  contribution_count: number;
  commits_count: number;
  prs_count: number;
  issues_count: number;
  repositories: string[];
  work_areas: string[];
  evidence_ids: string[];
  review_history: Array<Record<string, unknown>>;
}

interface WorkClusterRecord {
  cluster_id: string;
  name: string;
  classification_method: string;
  contribution_count: number;
  contributor_count: number;
  contributors: Array<{ contributor_key: string; display_name: string; contributor_type: string; count: number }>;
  contributions: Array<{
    evidence_id: string;
    title: string;
    category: string;
    contributor_key: string;
    contributor_name: string;
    contributor_type: string;
    alignment?: string | null;
  }>;
  changed_paths: string[];
  evidence_ids: string[];
}

interface RelationshipWorkspaceProps {
  projectId: string;
}

function getContributorNodeStyle(ctype: string): { background: string; border: string; color: string } {
  switch (ctype) {
    case "confirmed_member":
      return { background: "#eef2ff", border: "2px solid #4f46e5", color: "#1e1b4b" };
    case "external_contributor":
      return { background: "#f1f5f9", border: "1.5px dashed #64748b", color: "#334155" };
    case "unidentified":
      return { background: "#f8fafc", border: "1.5px dashed #d97706", color: "#334155" };
    case "bot":
      return { background: "#f4f4f5", border: "1.5px solid #71717a", color: "#27272a" };
    case "work_cluster":
      return { background: "#ecfdf5", border: "2px solid #059669", color: "#064e3b" };
    default:
      return { background: "#ffffff", border: "1px solid #94a3b8", color: "#0f172a" };
  }
}

export function filterVisibleGraphEdges<T extends { source: string; target: string }>(
  allEdges: T[],
  visibleNodeIds: Set<string>
): T[] {
  return allEdges.filter((e) => visibleNodeIds.has(e.source) && visibleNodeIds.has(e.target));
}

export function RelationshipWorkspace({ projectId }: RelationshipWorkspaceProps) {
  const { members: liveMembers } = useLiveApp();
  const [fetchedMembers, setFetchedMembers] = useState<any[]>([]);

  useEffect(() => {
    if (!projectId) return;
    api.members.list(projectId).then((m) => {
      if (Array.isArray(m) && m.length > 0) {
        setFetchedMembers(m);
      }
    }).catch(() => {});
  }, [projectId]);

  const projectMembers = fetchedMembers.length > 0 ? fetchedMembers : liveMembers;

  const [activeTab, setActiveTab] = useState<RelationshipTab>("people");
  const [graphSubmode, setGraphSubmode] = useState<"contributors" | "entities">("contributors");
  const [peopleViewKind, setPeopleViewKind] = useState<"graph" | "list">("graph");
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [actionFeedback, setActionFeedback] = useState<string | null>(null);

  // Graph state
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [rawEntityGraph, setRawEntityGraph] = useState<{ nodes: KnowledgeEntityNode[]; edges: any[] }>({
    nodes: [],
    edges: [],
  });
  const [rawContributorGraph, setRawContributorGraph] = useState<{
    nodes: Array<{
      id: string;
      node_kind: string;
      label: string;
      contributor_key?: string | null;
      contributor_type: string;
      review_status: string;
      verification_status: string;
      contribution_count: number;
      metadata: Record<string, unknown>;
    }>;
    edges: Array<{
      id: string;
      source: string;
      target: string;
      relationship_type: string;
      label: string;
      evidence_basis: string;
    }>;
    summary: Record<string, number>;
  }>({ nodes: [], edges: [], summary: {} });

  // Filters & expansion
  const [layoutMode, setLayoutMode] = useState<"cluster" | "grid" | "circle">("cluster");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [selectedTypeFilter, setSelectedTypeFilter] = useState<string>("all");
  const [contributorTypeFilter, setContributorTypeFilter] = useState<string>("all");
  const [workClusterFilter, setWorkClusterFilter] = useState<string>("all");
  const [includeExternal, setIncludeExternal] = useState<boolean>(true);
  const [includeBots, setIncludeBots] = useState<boolean>(true);
  const [expandContributorKey, setExpandContributorKey] = useState<string | undefined>(undefined);
  const [expandClusterName, setExpandClusterName] = useState<string | undefined>(undefined);

  // Drawers
  const [selectedEntityDetail, setSelectedEntityDetail] = useState<{
    entity: KnowledgeEntityNode;
    adjacent_edges?: Array<Record<string, unknown>>;
    related_nodes?: Array<Record<string, unknown>>;
    evidence_links?: Array<Record<string, unknown>>;
  } | null>(null);
  const [selectedContributorDetail, setSelectedContributorDetail] = useState<ContributorRecord | null>(null);

  // Tab data states
  const [contributors, setContributors] = useState<ContributorRecord[]>([]);
  const [clusters, setClusters] = useState<WorkClusterRecord[]>([]);
  const [attributions, setAttributions] = useState<Array<Record<string, unknown>>>([]);
  const [traceChains, setTraceChains] = useState<TraceabilityChainItem[]>([]);
  const [depGraph, setDepGraph] = useState<DependencyGraphData | null>(null);
  const [timelineEvents, setTimelineEvents] = useState<TimelineEventItem[]>([]);
  const [candidates, setCandidates] = useState<IdentityCandidateItem[]>([]);
  const [selectedMatchMemberByKey, setSelectedMatchMemberByKey] = useState<Record<string, string>>({});

  // Respect URL query params (?entityId=... or ?tab=...)
  useEffect(() => {
    if (typeof window === "undefined") return;
    const sp = new URLSearchParams(window.location.search);
    const tabParam = sp.get("tab") as RelationshipTab | null;
    const entityParam = sp.get("entityId");
    if (tabParam && ["people", "clusters", "traceability", "responsibilities", "dependencies", "timeline", "identity_review"].includes(tabParam)) {
      setActiveTab(tabParam);
    }
    if (entityParam) {
      setGraphSubmode("entities");
      api.relationships
        .getGraph(projectId, 250, { center_node_id: entityParam, depth: 2 })
        .then((res) => setRawEntityGraph(res as any))
        .catch(() => {});
    }
  }, [projectId]);

  const computeEntityLayout = useCallback(
    (nodesList: KnowledgeEntityNode[], mode: "cluster" | "grid" | "circle") => {
      const total = nodesList.length;
      if (total === 0) return [];
      if (mode === "grid") {
        const cols = Math.max(4, Math.ceil(Math.sqrt(total * 1.5)));
        return nodesList.map((n, idx) => ({
          id: String(n.id),
          raw: n,
          position: { x: (idx % cols) * 260 + 40, y: Math.floor(idx / cols) * 150 + 40 },
        }));
      }
      if (mode === "cluster") {
        const typeGroups: Record<string, KnowledgeEntityNode[]> = {};
        nodesList.forEach((n) => {
          const t = (n.entity_type || n.type || "general").toLowerCase();
          (typeGroups[t] ||= []).push(n);
        });
        const types = Object.keys(typeGroups);
        const angleStep = (2 * Math.PI) / Math.max(1, types.length);
        const radius = Math.max(420, types.length * 130);
        const out: Array<{ id: string; raw: KnowledgeEntityNode; position: { x: number; y: number } }> = [];
        types.forEach((type, tIdx) => {
          const items = typeGroups[type]!;
          const cx = 750 + radius * Math.cos(tIdx * angleStep);
          const cy = 650 + radius * Math.sin(tIdx * angleStep);
          const cols = Math.max(2, Math.ceil(Math.sqrt(items.length)));
          items.forEach((item, idx) => {
            out.push({
              id: String(item.id),
              raw: item,
              position: {
                x: cx - (cols * 240) / 2 + (idx % cols) * 240,
                y: cy - (Math.ceil(items.length / cols) * 130) / 2 + Math.floor(idx / cols) * 130,
              },
            });
          });
        });
        return out;
      }
      const r = Math.max(480, total * 20);
      return nodesList.map((n, idx) => {
        const angle = (idx / total) * 2 * Math.PI;
        return {
          id: String(n.id),
          raw: n,
          position: { x: 800 + r * Math.cos(angle), y: 700 + r * Math.sin(angle) },
        };
      });
    },
    []
  );

  const loadPeopleAndEntityGraphs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      if (graphSubmode === "contributors") {
        const [graphRes, contribList, clusterList] = await Promise.all([
          api.relationships.getContributorsGraph(projectId, {
            contributor_type: contributorTypeFilter !== "all" ? contributorTypeFilter : undefined,
            work_cluster: workClusterFilter !== "all" ? workClusterFilter : undefined,
            search: searchQuery.trim() || undefined,
            include_external: includeExternal,
            include_bots: includeBots,
            expand_contributor_key: expandContributorKey,
            expand_cluster_name: expandClusterName,
          }),
          api.relationships.listContributors(projectId),
          api.relationships.listWorkClusters(projectId),
        ]);
        setRawContributorGraph(graphRes);
        setContributors(contribList);
        setClusters(clusterList);
      } else {
        const graphData = await api.relationships.getGraph(projectId);
        setRawEntityGraph(graphData as any);
      }
    } catch (err: unknown) {
      setError((err as Error)?.message || "Failed to load Relationship Explorer graph.");
    } finally {
      setLoading(false);
    }
  }, [
    projectId,
    graphSubmode,
    contributorTypeFilter,
    workClusterFilter,
    searchQuery,
    includeExternal,
    includeBots,
    expandContributorKey,
    expandClusterName,
  ]);

  useEffect(() => {
    loadPeopleAndEntityGraphs();
  }, [loadPeopleAndEntityGraphs]);

  // Project filtered nodes AND strictly filter dangling edges!
  useEffect(() => {
    if (graphSubmode === "contributors") {
      const contribs = rawContributorGraph.nodes.filter((n) => n.node_kind === "contributor");
      const workClusters = rawContributorGraph.nodes.filter((n) => n.node_kind === "work_cluster");
      const artefacts = rawContributorGraph.nodes.filter(
        (n) => n.node_kind !== "contributor" && n.node_kind !== "work_cluster"
      );

      const flowNodes: Node[] = [];
      contribs.forEach((c, idx) => {
        const st = getContributorNodeStyle(c.contributor_type);
        const badge =
          c.contributor_type === "unidentified"
            ? "Unresolved Identity"
            : c.contributor_type.replace(/_/g, " ");
        flowNodes.push({
          id: c.id,
          position: { x: 60, y: idx * 130 + 40 },
          data: { label: `${c.label}\n[${badge} · ${c.contribution_count}]`, raw: c },
          style: {
            ...st,
            borderRadius: "10px",
            padding: "10px 14px",
            fontSize: "12px",
            minWidth: "200px",
            maxWidth: "250px",
            textAlign: "center",
            whiteSpace: "pre-wrap",
          },
        });
      });

      workClusters.forEach((wc, idx) => {
        const st = getContributorNodeStyle("work_cluster");
        flowNodes.push({
          id: wc.id,
          position: { x: 420, y: idx * 130 + 40 },
          data: { label: `${wc.label}\n[Work Cluster · ${wc.contribution_count}]`, raw: wc },
          style: {
            ...st,
            borderRadius: "10px",
            padding: "10px 14px",
            fontSize: "12px",
            minWidth: "200px",
            maxWidth: "250px",
            textAlign: "center",
            whiteSpace: "pre-wrap",
          },
        });
      });

      artefacts.forEach((art, idx) => {
        flowNodes.push({
          id: art.id,
          position: { x: 780, y: idx * 110 + 40 },
          data: { label: `${art.label}\n[${art.node_kind}]`, raw: art },
          style: {
            background: "#ffffff",
            border: "1px solid #cbd5e1",
            color: "#1e293b",
            borderRadius: "8px",
            padding: "8px 12px",
            fontSize: "11px",
            minWidth: "180px",
            maxWidth: "240px",
            textAlign: "center",
            whiteSpace: "pre-wrap",
          },
        });
      });

      const visibleIds = new Set(flowNodes.map((n) => n.id));
      const flowEdges: Edge[] = filterVisibleGraphEdges(rawContributorGraph.edges, visibleIds).map(
        (e) => ({
          id: e.id,
          source: e.source,
          target: e.target,
          label: e.label,
          markerEnd: { type: MarkerType.ArrowClosed },
          style: { stroke: "#64748b" },
        })
      );

      setNodes(flowNodes);
      setEdges(flowEdges);
      return;
    }

    // Generic Entity Graph filtering (fixing dangling-edge bug)
    let filtered = rawEntityGraph.nodes;
    if (selectedTypeFilter !== "all") {
      filtered = filtered.filter(
        (n) => (n.entity_type || n.type || "").toLowerCase() === selectedTypeFilter.toLowerCase()
      );
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      filtered = filtered.filter((n) => (n.canonical_name || n.label || "").toLowerCase().includes(q));
    }

    const computed = computeEntityLayout(filtered, layoutMode);
    const flowNodes: Node[] = computed.map((c) => {
      const n = c.raw;
      const entityType = n.entity_type || n.type || "entity";
      const canonicalName = n.canonical_name || n.label || "Unnamed Entity";
      return {
        id: c.id,
        data: { label: `${canonicalName}\n[${entityType}]`, raw: n },
        position: c.position,
        style: {
          background:
            entityType === "decision"
              ? "#fef3c7"
              : entityType === "person"
                ? "#e0e7ff"
                : entityType === "work_cluster"
                  ? "#ecfdf5"
                  : "#f8fafc",
          color: "#0f172a",
          border:
            entityType === "decision"
              ? "1.5px solid #d97706"
              : entityType === "person"
                ? "1.5px solid #4f46e5"
                : "1px solid #94a3b8",
          borderRadius: "10px",
          fontSize: "12px",
          padding: "10px 14px",
          textAlign: "center",
          whiteSpace: "pre-wrap",
          minWidth: "160px",
          maxWidth: "230px",
        },
      };
    });

    const visibleIds = new Set(flowNodes.map((n) => n.id));
    const flowEdges: Edge[] = filterVisibleGraphEdges(
      rawEntityGraph.edges.map((e) => ({
        id: String(e.id),
        source: String(e.source),
        target: String(e.target),
        label: String(e.label || e.relationship_type || "related").toLowerCase().replace(/_/g, " "),
        markerEnd: { type: MarkerType.ArrowClosed },
        style: { stroke: "#64748b" },
      })),
      visibleIds
    );
    setNodes(flowNodes);
    setEdges(flowEdges);
  }, [
    graphSubmode,
    rawContributorGraph,
    rawEntityGraph,
    selectedTypeFilter,
    searchQuery,
    layoutMode,
    computeEntityLayout,
    setNodes,
    setEdges,
  ]);

  const loadTabDetails = async (tab: RelationshipTab) => {
    setActiveTab(tab);
    setError(null);
    try {
      if (tab === "clusters" && clusters.length === 0) {
        setClusters(await api.relationships.listWorkClusters(projectId));
      } else if ((tab === "identity_review" || tab === "responsibilities") && contributors.length === 0) {
        const [contribs, attrs] = await Promise.all([
          api.relationships.listContributors(projectId),
          api.roster.listAttributions(projectId),
        ]);
        setContributors(contribs);
        setAttributions(attrs as unknown as Array<Record<string, unknown>>);
      } else if (tab === "responsibilities" && attributions.length === 0) {
        setAttributions((await api.roster.listAttributions(projectId)) as unknown as Array<Record<string, unknown>>);
      } else if (tab === "traceability" && traceChains.length === 0) {
        const res = await api.relationships.getTraceability(projectId);
        setTraceChains(
          (res.chains || res.items || []).map((tc: any) => ({
            ...tc,
            decision_name: tc.decision_name || "Untitled Decision",
            work_item_count: tc.work_item_count ?? tc.work_item_ids?.length ?? 0,
            pr_count: tc.pr_count ?? tc.pull_request_ids?.length ?? 0,
            commit_count: tc.commit_count ?? tc.commit_ids?.length ?? 0,
            component_count: tc.component_count ?? tc.component_ids?.length ?? 0,
            missing_links: tc.missing_links || [],
          }))
        );
      } else if (tab === "dependencies" && !depGraph) {
        const res = await api.relationships.getDependencies(projectId);
        setDepGraph({
          nodes: res.nodes || [],
          edges: res.edges || [],
          cycles: res.cycles || res.detected_cycles || [],
          root_blockers: res.root_blockers || [],
        });
      } else if (tab === "timeline" && timelineEvents.length === 0) {
        const res = await api.relationships.getTimeline(projectId);
        setTimelineEvents(res.items || []);
      }
      if (tab === "identity_review" && candidates.length === 0) {
        try {
          setCandidates((await api.relationships.listIdentityCandidates(projectId)) as unknown as IdentityCandidateItem[]);
        } catch {
          // Non-fatal if no entity merge candidates exist
        }
      }
    } catch (err: unknown) {
      setError((err as Error)?.message || "Failed to load view data.");
    }
  };

  const handleNodeClick = async (_: unknown, node: Node) => {
    const raw = (node.data as { raw?: any })?.raw;
    if (!raw) return;

    if (graphSubmode === "contributors") {
      if (raw.node_kind === "contributor" && raw.contributor_key) {
        setSelectedEntityDetail(null);
        try {
          const detail = await api.relationships.getContributorDetail(projectId, raw.contributor_key);
          setSelectedContributorDetail(detail as unknown as ContributorRecord);
          setExpandContributorKey(raw.contributor_key);
        } catch {
          const fallback = contributors.find((c) => c.contributor_key === raw.contributor_key) || null;
          setSelectedContributorDetail(fallback);
        }
      } else if (raw.node_kind === "work_cluster") {
        setExpandClusterName(raw.label);
      }
      return;
    }

    setSelectedContributorDetail(null);
    try {
      const detail = await api.relationships.getEntityDetails(projectId, raw.id);
      setSelectedEntityDetail({
        entity: (detail.entity as KnowledgeEntityNode) || raw,
        adjacent_edges: (detail.adjacent_edges as Array<Record<string, unknown>>) || [],
        related_nodes: (detail.related_nodes as Array<Record<string, unknown>>) || [],
        evidence_links: (detail.evidence_links as Array<Record<string, unknown>>) || [],
      });
    } catch {
      setSelectedEntityDetail({ entity: raw });
    }
  };

  const handleExpandNeighbourhood = async (entityId: string) => {
    try {
      const graphData = await api.relationships.getGraph(projectId, 250, {
        center_node_id: entityId,
        depth: 2,
      });
      setRawEntityGraph(graphData as any);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to expand entity neighborhood.");
    }
  };

  const handleContributorReviewAction = async (
    contributorKey: string,
    action: "match_member" | "mark_external" | "mark_bot" | "leave_unidentified" | "reject_match" | "revert"
  ) => {
    setError(null);
    setActionFeedback(null);
    try {
      const selectedMembershipId = selectedMatchMemberByKey[contributorKey];
      if (action === "match_member" && !selectedMembershipId) {
        setError("Select a project member before confirming identity match.");
        return;
      }
      await api.relationships.reviewContributor(projectId, contributorKey, {
        action,
        project_membership_id: action === "match_member" ? selectedMembershipId : undefined,
        notes: `Reviewed in Relationship Explorer (${action})`,
      });
      setActionFeedback(`Updated contributor identity (${action.replace(/_/g, " ")}).`);
      await loadPeopleAndEntityGraphs();
      setAttributions((await api.roster.listAttributions(projectId)) as unknown as Array<Record<string, unknown>>);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to submit contributor review.");
    }
  };

  const pendingReviewsCount = useMemo(
    () => contributors.filter((c) => c.contributor_type === "unidentified" && c.review_status === "pending").length,
    [contributors]
  );

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] bg-slate-50">
      {/* Header */}
      <div className="bg-white border-b border-slate-200 px-6 py-4">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold text-slate-900">Relationship Explorer</h1>
            <p className="text-sm text-slate-500">
              Explore the people, contributions, responsibilities and work areas behind your project.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => loadPeopleAndEntityGraphs()}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 bg-white text-xs font-medium text-slate-700 hover:bg-slate-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
              Refresh
            </button>
            <button
              type="button"
              onClick={async () => {
                setLoading(true);
                try {
                  await api.relationships.rebuildWorkClusters(projectId);
                  await loadPeopleAndEntityGraphs();
                  setActionFeedback("Work clusters rebuilt from persisted evidence.");
                } catch (e) {
                  setError((e as Error).message);
                } finally {
                  setLoading(false);
                }
              }}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 text-xs font-medium text-white hover:bg-blue-700"
            >
              <Boxes className="w-3.5 h-3.5" />
              Rebuild Work Clusters
            </button>
          </div>
        </div>

        {/* Notification Banner for Unmatched Contributors */}
        {pendingReviewsCount > 0 && activeTab !== "identity_review" && (
          <div className="mt-3 px-4 py-2.5 rounded-lg bg-amber-50 border border-amber-200 flex items-center justify-between text-xs text-amber-900">
            <span className="font-medium">
              Contributor identities require review. ({pendingReviewsCount} unresolved GitHub identity/identities)
            </span>
            <button
              type="button"
              onClick={() => loadTabDetails("identity_review")}
              className="px-3 py-1 rounded bg-amber-600 text-white font-medium hover:bg-amber-700"
            >
              Review Identities
            </button>
          </div>
        )}

        {/* 7 Primary Views */}
        <div className="flex flex-wrap items-center gap-1.5 mt-4" role="tablist" aria-label="Relationship Explorer tabs">
          {(
            [
              { id: "people", label: "People & Contributions", Icon: Users },
              { id: "clusters", label: "Work Clusters", Icon: Boxes },
              { id: "identity_review", label: `Identity Review${pendingReviewsCount > 0 ? ` (${pendingReviewsCount})` : ""}`, Icon: UserCheck },
              { id: "responsibilities", label: "Responsibilities", Icon: Briefcase },
              { id: "traceability", label: "Traceability", Icon: GitBranch },
              { id: "dependencies", label: "Dependencies", Icon: ShieldAlert },
              { id: "timeline", label: "Timeline", Icon: Clock },
            ] as const
          ).map(({ id, label, Icon }) => (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={activeTab === id}
              onClick={() => loadTabDetails(id)}
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                activeTab === id
                  ? "bg-blue-600 text-white"
                  : "bg-slate-100 text-slate-700 hover:bg-slate-200"
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              {label}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="mx-6 mt-3 p-3 rounded-lg bg-red-50 border border-red-200 text-xs text-red-700 flex items-center justify-between">
          <span>{error}</span>
          <button type="button" onClick={() => setError(null)} className="underline">Dismiss</button>
        </div>
      )}
      {actionFeedback && (
        <div className="mx-6 mt-3 p-3 rounded-lg bg-emerald-50 border border-emerald-200 text-xs text-emerald-800 flex items-center justify-between">
          <span>{actionFeedback}</span>
          <button type="button" onClick={() => setActionFeedback(null)} className="underline">Dismiss</button>
        </div>
      )}

      {/* Tab Content */}
      <div className="flex-1 relative overflow-hidden">
        {/* 1. PEOPLE & CONTRIBUTIONS GRAPH */}
        {activeTab === "people" && (
          <div className="flex flex-col h-full">
            <div className="bg-white border-b border-slate-200 px-6 py-2.5 flex flex-wrap items-center gap-3 text-xs">
              <div className="inline-flex rounded-lg border border-slate-200 overflow-hidden">
                <button
                  type="button"
                  onClick={() => setGraphSubmode("contributors")}
                  className={`px-3 py-1 font-medium ${graphSubmode === "contributors" ? "bg-blue-50 text-blue-700" : "bg-white text-slate-600"}`}
                >
                  Contributor Graph
                </button>
                <button
                  type="button"
                  onClick={() => setGraphSubmode("entities")}
                  className={`px-3 py-1 font-medium ${graphSubmode === "entities" ? "bg-blue-50 text-blue-700" : "bg-white text-slate-600"}`}
                >
                  All Entities
                </button>
              </div>

              <div className="relative min-w-[200px] flex-1 max-w-xs">
                <Search className="w-3.5 h-3.5 absolute left-2.5 top-2 text-slate-400" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search people, clusters, entities..."
                  aria-label="Search relationship graph"
                  className="w-full pl-8 pr-3 py-1.5 bg-white border border-slate-200 rounded-lg text-xs"
                />
              </div>

              {graphSubmode === "contributors" ? (
                <>
                  <select
                    value={contributorTypeFilter}
                    onChange={(e) => setContributorTypeFilter(e.target.value)}
                    aria-label="Filter by contributor type"
                    className="px-2.5 py-1.5 border border-slate-200 rounded-lg bg-white text-slate-700"
                  >
                    <option value="all">All Contributors</option>
                    <option value="confirmed_member">Confirmed Team Members</option>
                    <option value="external_contributor">External Contributors</option>
                    <option value="unidentified">Unidentified Contributors</option>
                    <option value="bot">Bots</option>
                  </select>
                  <select
                    value={workClusterFilter}
                    onChange={(e) => setWorkClusterFilter(e.target.value)}
                    aria-label="Filter by work cluster"
                    className="px-2.5 py-1.5 border border-slate-200 rounded-lg bg-white text-slate-700"
                  >
                    <option value="all">All Work Clusters</option>
                    {clusters.map((c) => (
                      <option key={c.cluster_id} value={c.name}>
                        {c.name} ({c.contribution_count})
                      </option>
                    ))}
                  </select>
                  <label className="inline-flex items-center gap-1 text-slate-600">
                    <input type="checkbox" checked={includeExternal} onChange={(e) => setIncludeExternal(e.target.checked)} />
                    External
                  </label>
                  <label className="inline-flex items-center gap-1 text-slate-600">
                    <input type="checkbox" checked={includeBots} onChange={(e) => setIncludeBots(e.target.checked)} />
                    Bots
                  </label>
                  {(expandContributorKey || expandClusterName) && (
                    <button
                      type="button"
                      onClick={() => {
                        setExpandContributorKey(undefined);
                        setExpandClusterName(undefined);
                      }}
                      className="px-2 py-1 rounded bg-slate-100 text-slate-700 hover:bg-slate-200"
                    >
                      Collapse Drill-Down
                    </button>
                  )}
                </>
              ) : (
                <>
                  <select
                    value={selectedTypeFilter}
                    onChange={(e) => setSelectedTypeFilter(e.target.value)}
                    aria-label="Filter by entity type"
                    className="px-2.5 py-1.5 border border-slate-200 rounded-lg bg-white text-slate-700"
                  >
                    <option value="all">All Entity Types</option>
                    <option value="person">Person</option>
                    <option value="work_cluster">Work Cluster</option>
                    <option value="technology">Technology</option>
                    <option value="technical_component">Technical Component</option>
                    <option value="feature">Feature</option>
                    <option value="decision">Decision</option>
                    <option value="pull_request">Pull Request</option>
                    <option value="commit">Commit</option>
                    <option value="work_item">Jira / Work Item</option>
                  </select>
                  <select
                    value={layoutMode}
                    onChange={(e) => setLayoutMode(e.target.value as "cluster" | "grid" | "circle")}
                    aria-label="Graph layout"
                    className="px-2.5 py-1.5 border border-slate-200 rounded-lg bg-white text-slate-700"
                  >
                    <option value="cluster">Cluster Layout</option>
                    <option value="grid">Grid Layout</option>
                    <option value="circle">Radial Layout</option>
                  </select>
                </>
              )}

              <button
                type="button"
                onClick={() => setPeopleViewKind(peopleViewKind === "graph" ? "list" : "graph")}
                className="ml-auto inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-slate-200 bg-white text-slate-700"
              >
                {peopleViewKind === "graph" ? <TableIcon className="w-3.5 h-3.5" /> : <Network className="w-3.5 h-3.5" />}
                {peopleViewKind === "graph" ? "Table View" : "Graph View"}
              </button>
            </div>

            <div className="flex-1 relative">
              {nodes.length === 0 && !loading ? (
                <div className="flex flex-col items-center justify-center h-full text-center p-8 text-slate-500">
                  <Users className="w-12 h-12 text-slate-300 mb-3" />
                  <p className="font-medium text-slate-800">No contributor or entity relationships reconstructed yet.</p>
                  <p className="text-xs text-slate-500 mt-1 max-w-md">
                    Connect and sync a GitHub repository in Evidence Center, then rebuild work clusters or relationship discovery.
                  </p>
                </div>
              ) : peopleViewKind === "list" ? (
                <div className="p-6 h-full overflow-y-auto">
                  <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
                    <table className="w-full text-left text-xs">
                      <thead className="bg-slate-50 border-b border-slate-200 uppercase text-slate-500">
                        <tr>
                          <th className="px-4 py-3">Contributor</th>
                          <th className="px-4 py-3">Category</th>
                          <th className="px-4 py-3">Review Status</th>
                          <th className="px-4 py-3">Contributions</th>
                          <th className="px-4 py-3">Work Areas</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {contributors.map((c) => (
                          <tr
                            key={c.contributor_key}
                            className="hover:bg-slate-50 cursor-pointer"
                            onClick={() => setSelectedContributorDetail(c)}
                          >
                            <td className="px-4 py-3 font-medium text-slate-900">
                              {c.display_name} {c.github_login ? `(@${c.github_login})` : ""}
                            </td>
                            <td className="px-4 py-3 text-slate-600">{c.contributor_type.replace(/_/g, " ")}</td>
                            <td className="px-4 py-3 text-slate-600">{c.review_status}</td>
                            <td className="px-4 py-3 text-slate-700">{c.contribution_count}</td>
                            <td className="px-4 py-3 text-slate-600">{c.work_areas.join(", ") || "-"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : (
                <ReactFlow
                  nodes={nodes}
                  edges={edges}
                  onNodesChange={onNodesChange}
                  onEdgesChange={onEdgesChange}
                  onNodeClick={handleNodeClick}
                  fitView
                >
                  <Background />
                  <Controls />
                  <MiniMap />
                </ReactFlow>
              )}

              {/* Contributor Detail Panel */}
              {selectedContributorDetail && (
                <div className="absolute right-4 top-4 bottom-4 w-96 bg-white border border-slate-200 rounded-xl shadow-xl p-5 z-20 overflow-y-auto">
                  <div className="flex items-center justify-between pb-3 border-b border-slate-100">
                    <span className="text-xs font-semibold px-2 py-0.5 rounded bg-blue-50 text-blue-700">
                      {selectedContributorDetail.contributor_type.replace(/_/g, " ")}
                    </span>
                    <button
                      type="button"
                      aria-label="Close contributor details"
                      onClick={() => setSelectedContributorDetail(null)}
                      className="text-slate-400 hover:text-slate-700"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                  <h3 className="font-semibold text-slate-900 mt-3 text-base">{selectedContributorDetail.display_name}</h3>
                  {selectedContributorDetail.github_login && (
                    <p className="text-xs text-slate-500">GitHub: @{selectedContributorDetail.github_login}</p>
                  )}
                  <div className="mt-4 space-y-2 text-xs border-t border-slate-100 pt-3">
                    <div className="flex justify-between">
                      <span className="text-slate-400">Identity Status:</span>
                      <span className="font-medium text-slate-800">{selectedContributorDetail.review_status}</span>
                    </div>
                    {selectedContributorDetail.contributor_type === "confirmed_member" && (
                      <>
                        <div className="flex justify-between">
                          <span className="text-slate-400">Team Member:</span>
                          <span className="font-medium text-slate-800">{selectedContributorDetail.matched_member_name || "Confirmed"}</span>
                        </div>
                        {selectedContributorDetail.declared_responsibility && (
                          <div>
                            <span className="text-slate-400 block">Declared Responsibility:</span>
                            <p className="text-slate-700 mt-0.5">{selectedContributorDetail.declared_responsibility}</p>
                          </div>
                        )}
                      </>
                    )}
                    <div className="flex justify-between">
                      <span className="text-slate-400">Observed Contributions:</span>
                      <span className="font-medium text-slate-800">
                        {selectedContributorDetail.commits_count} commits · {selectedContributorDetail.prs_count} PRs · {selectedContributorDetail.issues_count} issues
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-400 block mb-1">Work Clusters:</span>
                      <div className="flex flex-wrap gap-1">
                        {selectedContributorDetail.work_areas.map((wa) => (
                          <span key={wa} className="px-2 py-0.5 rounded bg-emerald-50 text-emerald-700">
                            {wa}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                  <div className="mt-4 pt-3 border-t border-slate-100">
                    <h4 className="text-xs font-semibold uppercase text-slate-500 mb-2">
                      Supporting Evidence ({selectedContributorDetail.evidence_ids.length})
                    </h4>
                    <div className="space-y-1.5">
                      {selectedContributorDetail.evidence_ids.slice(0, 8).map((evId) => (
                        <Link
                          key={evId}
                          href={`/projects/${projectId}/evidence/${evId}`}
                          className="flex items-center justify-between p-2 rounded-lg bg-slate-50 border border-slate-200 text-xs text-blue-600 hover:underline"
                        >
                          <span className="truncate">Evidence {evId.slice(0, 8)}</span>
                          <ExternalLink className="w-3 h-3" />
                        </Link>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {/* Generic Entity Node Detail Drawer */}
              {selectedEntityDetail && (
                <div className="absolute right-4 top-4 bottom-4 w-96 bg-white border border-slate-200 rounded-xl shadow-xl p-5 z-20 overflow-y-auto">
                  <div className="flex items-center justify-between pb-3 border-b border-slate-100">
                    <span className="text-xs font-semibold px-2 py-0.5 rounded bg-blue-50 text-blue-700 uppercase">
                      {selectedEntityDetail.entity.type || selectedEntityDetail.entity.entity_type || "entity"}
                    </span>
                    <button
                      type="button"
                      aria-label="Close entity details"
                      onClick={() => setSelectedEntityDetail(null)}
                      className="text-slate-400 hover:text-slate-700"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                  <h3 className="font-semibold text-slate-900 mt-3 text-base">
                    {selectedEntityDetail.entity.canonical_name || selectedEntityDetail.entity.label || "Unnamed Entity"}
                  </h3>
                  {selectedEntityDetail.entity.description && (
                    <p className="text-xs text-slate-600 mt-1.5">{selectedEntityDetail.entity.description}</p>
                  )}
                  <div className="mt-3 space-y-1.5 text-xs">
                    <div className="flex justify-between">
                      <span className="text-slate-400">Resolution:</span>
                      <span className="font-medium text-slate-800">{selectedEntityDetail.entity.resolution_status || "canonical"}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">Adjacent Edges:</span>
                      <span className="font-medium text-slate-800">{selectedEntityDetail.adjacent_edges?.length || 0}</span>
                    </div>
                  </div>
                  <div className="mt-4 flex flex-col gap-2">
                    <button
                      type="button"
                      onClick={() => handleExpandNeighbourhood(selectedEntityDetail.entity.id)}
                      className="py-2 px-3 rounded-lg bg-blue-600 text-xs font-medium text-white hover:bg-blue-700"
                    >
                      Expand Neighbourhood (Depth 2)
                    </button>
                    <Link
                      href={`/projects/${projectId}/knowledge`}
                      className="py-2 px-3 rounded-lg border border-slate-200 text-center text-xs font-medium text-slate-700 hover:bg-slate-50"
                    >
                      View in Knowledge Intelligence
                    </Link>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* 2. WORK CLUSTERS TAB */}
        {activeTab === "clusters" && (
          <div className="p-6 h-full overflow-y-auto space-y-4">
            {clusters.length === 0 ? (
              <div className="bg-white border border-slate-200 rounded-xl p-10 text-center text-sm text-slate-500">
                No work clusters built yet. Click &quot;Rebuild Work Clusters&quot; after syncing GitHub or Jira records.
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {clusters.map((cl) => (
                  <div key={cl.cluster_id} className="bg-white border border-slate-200 rounded-xl p-5 space-y-3">
                    <div className="flex items-center justify-between">
                      <h3 className="font-semibold text-slate-900">{cl.name}</h3>
                      <span className="px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 text-xs font-medium">
                        {cl.contribution_count} contribution(s) · {cl.contributor_count} contributor(s)
                      </span>
                    </div>
                    <p className="text-xs text-slate-500">Classification basis: {cl.classification_method}</p>
                    <div className="flex flex-wrap gap-1.5">
                      {cl.contributors.map((cc) => (
                        <span key={cc.contributor_key} className="px-2 py-0.5 rounded bg-blue-50 text-blue-700 text-xs">
                          {cc.display_name} ({cc.count})
                        </span>
                      ))}
                    </div>
                    {cl.contributions.slice(0, 4).map((item) => (
                      <div key={item.evidence_id} className="flex items-center justify-between text-xs border-t border-slate-100 pt-2">
                        <span className="truncate text-slate-700">{item.title}</span>
                        <Link
                          href={`/projects/${projectId}/evidence/${item.evidence_id}`}
                          className="text-blue-600 hover:underline shrink-0 ml-2 inline-flex items-center gap-1"
                        >
                          Open Evidence <ExternalLink className="w-3 h-3" />
                        </Link>
                      </div>
                    ))}
                    <div className="pt-2 border-t border-slate-100 flex justify-end">
                      <Link
                        href={`/projects/${projectId}/knowledge`}
                        className="text-xs font-medium text-blue-600 hover:underline"
                      >
                        View Related Knowledge Findings →
                      </Link>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* 3. CONTRIBUTOR IDENTITY REVIEW */}
        {activeTab === "identity_review" && (
          <div className="p-6 h-full overflow-y-auto space-y-6">
            <div>
              <h2 className="text-base font-semibold text-slate-900">Contributor Identity Review</h2>
              <p className="text-xs text-slate-500">
                Match imported GitHub identities to existing project members, or explicitly mark external contributors and bots.
                To invite a new teammate, use Project Workspace Team Members.
              </p>
            </div>
            {contributors.length === 0 ? (
              <div className="bg-white border border-slate-200 rounded-xl p-8 text-center text-sm text-slate-500">
                No GitHub or Jira contributor records imported yet.
              </div>
            ) : (
              <div className="space-y-3">
                {contributors.map((c) => (
                  <div key={c.contributor_key} className="bg-white border border-slate-200 rounded-xl p-4 flex flex-wrap items-center justify-between gap-4">
                    <div className="space-y-1 min-w-[260px]">
                      <div className="flex items-center gap-2">
                        {c.contributor_type === "bot" ? (
                          <Bot className="w-4 h-4 text-zinc-600" />
                        ) : c.contributor_type === "confirmed_member" ? (
                          <CheckCircle2 className="w-4 h-4 text-blue-600" />
                        ) : (
                          <HelpCircle className="w-4 h-4 text-amber-600" />
                        )}
                        <span className="font-semibold text-slate-900 text-sm">{c.display_name}</span>
                        <span className="px-2 py-0.5 rounded bg-slate-100 text-slate-700 text-[11px]">
                          {c.contributor_type.replace(/_/g, " ")} · {c.review_status}
                        </span>
                      </div>
                      <p className="text-xs text-slate-500">
                        {c.github_login ? `Login: @${c.github_login}` : ""}
                        {c.github_numeric_id ? ` · ID: ${c.github_numeric_id}` : ""}
                        {c.git_author_email ? ` · Email: ${c.git_author_email}` : ""}
                      </p>
                      <p className="text-xs text-slate-500">
                        Contributions: {c.contribution_count} · Repos: {c.repositories.join(", ") || "N/A"} · Basis: {c.match_method || "unmatched"}
                      </p>
                      {c.suggested_member_name && !c.matched_member_name && (
                        <p className="text-xs text-amber-700">Suggested member candidate: {c.suggested_member_name}</p>
                      )}
                      {c.matched_member_name && (
                        <p className="text-xs text-blue-700 font-medium">Matched Team Member: {c.matched_member_name}</p>
                      )}
                    </div>

                    <div className="flex flex-wrap items-center gap-2 text-xs">
                      <select
                        value={selectedMatchMemberByKey[c.contributor_key] || c.suggested_project_membership_id || ""}
                        onChange={(e) =>
                          setSelectedMatchMemberByKey((prev) => ({
                            ...prev,
                            [c.contributor_key]: e.target.value,
                          }))
                        }
                        aria-label={`Select project member for ${c.display_name}`}
                        className="px-2.5 py-1.5 border border-slate-200 rounded-lg bg-white text-slate-700"
                      >
                        <option value="">Select Project Member...</option>
                        {projectMembers.map((m) => (
                          <option key={m.id} value={m.id}>
                            {m.user_full_name || m.full_name || m.user_email || m.id}
                          </option>
                        ))}
                      </select>
                      <button
                        type="button"
                        onClick={() => handleContributorReviewAction(c.contributor_key, "match_member")}
                        className="px-3 py-1.5 rounded-lg bg-blue-600 text-white font-medium hover:bg-blue-700"
                      >
                        Match Member
                      </button>
                      <button
                        type="button"
                        onClick={() => handleContributorReviewAction(c.contributor_key, "mark_external")}
                        className="px-2.5 py-1.5 rounded-lg border border-slate-200 text-slate-700 hover:bg-slate-50 inline-flex items-center gap-1"
                      >
                        <UserX className="w-3.5 h-3.5" /> External
                      </button>
                      <button
                        type="button"
                        onClick={() => handleContributorReviewAction(c.contributor_key, "mark_bot")}
                        className="px-2.5 py-1.5 rounded-lg border border-slate-200 text-slate-700 hover:bg-slate-50 inline-flex items-center gap-1"
                      >
                        <Bot className="w-3.5 h-3.5" /> Bot
                      </button>
                      <button
                        type="button"
                        onClick={() => handleContributorReviewAction(c.contributor_key, "revert")}
                        className="px-2.5 py-1.5 rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 inline-flex items-center gap-1"
                      >
                        <RotateCcw className="w-3.5 h-3.5" /> Revert
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* 4. RESPONSIBILITIES VS OBSERVED CONTRIBUTIONS */}
        {activeTab === "responsibilities" && (
          <div className="p-6 h-full overflow-y-auto space-y-4">
            <h2 className="text-base font-semibold text-slate-900">Declared Responsibilities vs Observed Contributions</h2>
            <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50 border-b border-slate-200 uppercase text-slate-500">
                  <tr>
                    <th className="px-4 py-3">Contributor</th>
                    <th className="px-4 py-3">Observed Work Area</th>
                    <th className="px-4 py-3">Alignment State</th>
                    <th className="px-4 py-3">Explanation</th>
                    <th className="px-4 py-3">Evidence</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {attributions.map((a) => (
                    <tr key={String(a.id)}>
                      <td className="px-4 py-3 font-medium text-slate-900">{String(a.contributor_identifier)}</td>
                      <td className="px-4 py-3 text-slate-700">{String(a.contribution_category || "Other")}</td>
                      <td className="px-4 py-3">
                        <span className="px-2 py-0.5 rounded bg-slate-100 text-slate-700 font-medium">
                          {String(a.responsibility_alignment || "UNCERTAIN")}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-slate-600">{String(a.alignment_explanation || "")}</td>
                      <td className="px-4 py-3">
                        <Link
                          href={`/projects/${projectId}/evidence/${String(a.evidence_item_id)}`}
                          className="text-blue-600 hover:underline inline-flex items-center gap-1"
                        >
                          Open <ExternalLink className="w-3 h-3" />
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* 5. TRACEABILITY */}
        {activeTab === "traceability" && (
          <div className="p-6 h-full overflow-y-auto space-y-4">
            <h2 className="text-base font-semibold text-slate-900">Decision-to-Implementation Traceability</h2>
            {traceChains.length === 0 ? (
              <div className="p-8 text-center bg-white border border-slate-200 rounded-xl text-sm text-slate-500">
                No decision traceability chains reconstructed yet.
              </div>
            ) : (
              <div className="space-y-3">
                {traceChains.map((tc) => (
                  <div key={tc.id} className="bg-white border border-slate-200 rounded-xl p-4">
                    <div className="flex items-center justify-between mb-2">
                      <h3 className="font-semibold text-slate-900 text-sm">{tc.decision_name}</h3>
                      <span className="px-2 py-0.5 rounded bg-blue-50 text-blue-700 text-xs">{tc.completeness_status}</span>
                    </div>
                    <p className="text-xs text-slate-600">
                      Work Items: {tc.work_item_count} · PRs: {tc.pr_count} · Commits: {tc.commit_count} · Components: {tc.component_count}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* 6. DEPENDENCIES */}
        {activeTab === "dependencies" && (
          <div className="p-6 h-full overflow-y-auto space-y-4">
            <h2 className="text-base font-semibold text-slate-900">Dependency & Cycle Analysis</h2>
            {!depGraph || depGraph.nodes.length === 0 ? (
              <div className="p-8 text-center bg-white border border-slate-200 rounded-xl text-sm text-slate-500">
                No dependency edges discovered yet.
              </div>
            ) : (
              <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-3 text-xs">
                <p>Nodes: {depGraph.nodes.length} · Edges: {depGraph.edges.length}</p>
                <p>Cycles Detected: {(depGraph.cycles || depGraph.detected_cycles || []).length}</p>
              </div>
            )}
          </div>
        )}

        {/* 7. TIMELINE */}
        {activeTab === "timeline" && (
          <div className="p-6 h-full overflow-y-auto space-y-3">
            <h2 className="text-base font-semibold text-slate-900">Chronological Project Timeline</h2>
            {timelineEvents.length === 0 ? (
              <div className="p-8 text-center bg-white border border-slate-200 rounded-xl text-sm text-slate-500">
                No timeline events recorded yet.
              </div>
            ) : (
              timelineEvents.map((ev) => (
                <div key={ev.id} className="bg-white border border-slate-200 rounded-xl p-4 text-xs">
                  <div className="flex justify-between text-slate-400 mb-1">
                    <span className="uppercase font-semibold">{ev.event_type}</span>
                    <span>{ev.occurred_at}</span>
                  </div>
                  <p className="font-semibold text-slate-900 text-sm">{ev.title}</p>
                  {ev.summary && <p className="text-slate-600 mt-1">{ev.summary}</p>}
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  );
}
