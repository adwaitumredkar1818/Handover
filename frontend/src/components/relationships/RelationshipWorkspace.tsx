"use client";

import React, { useState, useEffect, useCallback } from "react";
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
  Filter,
  Layers,
  GitBranch,
  ShieldAlert,
  Clock,
  Eye,
  RefreshCw,
} from "lucide-react";
import { api } from "../../lib/api";

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
  nodes: Array<{ entity_id?: string; id?: string; name?: string; label?: string; entity_type: string; status?: string; is_root_blocker?: boolean; in_degree?: number; out_degree?: number }>;
  edges: Array<{ source?: string; source_id?: string; target?: string; target_id?: string; relationship_type?: string; dependency_type?: string }>;
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

interface RelationshipWorkspaceProps {
  projectId: string;
}

export function RelationshipWorkspace({ projectId }: RelationshipWorkspaceProps) {
  const [activeTab, setActiveTab] = useState<
    "graph" | "entities" | "traceability" | "dependencies" | "timeline" | "candidates"
  >("graph");
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Graph state
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [selectedNode, setSelectedNode] = useState<KnowledgeEntityNode | null>(null);

  // Entities state
  const [entities, setEntities] = useState<KnowledgeEntityItem[]>([]);
  const [entityFilter, setEntityFilter] = useState<string>("");

  // Traceability state
  const [traceChains, setTraceChains] = useState<TraceabilityChainItem[]>([]);

  // Dependencies state
  const [depGraph, setDepGraph] = useState<DependencyGraphData | null>(null);

  // Timeline state
  const [timelineEvents, setTimelineEvents] = useState<TimelineEventItem[]>([]);

  // Candidates state
  const [candidates, setCandidates] = useState<IdentityCandidateItem[]>([]);

  // Layout mode state
  const [layoutMode, setLayoutMode] = useState<"cluster" | "grid" | "circle">("cluster");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [selectedTypeFilter, setSelectedTypeFilter] = useState<string>("all");
  const [rawGraphData, setRawGraphData] = useState<{ nodes: KnowledgeEntityNode[]; edges: any[] }>({ nodes: [], edges: [] });

  const computeLayout = useCallback((nodesList: KnowledgeEntityNode[], edgesList: any[], mode: "cluster" | "grid" | "circle") => {
    const total = nodesList.length;
    if (total === 0) return [];

    if (mode === "grid") {
      const cols = Math.max(4, Math.ceil(Math.sqrt(total * 1.5)));
      const xSpacing = 280;
      const ySpacing = 160;
      return nodesList.map((n, idx) => {
        const row = Math.floor(idx / cols);
        const col = idx % cols;
        return {
          id: String(n.id),
          data: {
            label: `${n.canonical_name || n.label || "Unnamed Entity"}\n[${n.entity_type || n.type || "entity"}]`,
            raw: n,
          },
          position: { x: col * xSpacing + 50, y: row * ySpacing + 50 },
        };
      });
    }

    if (mode === "cluster") {
      // Group nodes by entity_type into semantic domain clusters
      const typeGroups: Record<string, KnowledgeEntityNode[]> = {};
      nodesList.forEach((n) => {
        const t = (n.entity_type || n.type || "general").toLowerCase();
        if (!typeGroups[t]) typeGroups[t] = [];
        typeGroups[t].push(n);
      });

      const types = Object.keys(typeGroups);
      const clusterAngleStep = (2 * Math.PI) / Math.max(1, types.length);
      const clusterRadius = Math.max(450, types.length * 140);
      const centerX = 800;
      const centerY = 700;

      const flowNodesList: Array<{ id: string; data: { label: string; raw: any }; position: { x: number; y: number } }> = [];

      types.forEach((type, tIdx) => {
        const items = typeGroups[type]!;
        const clusterCenterX = centerX + clusterRadius * Math.cos(tIdx * clusterAngleStep);
        const clusterCenterY = centerY + clusterRadius * Math.sin(tIdx * clusterAngleStep);

        const itemsPerRow = Math.max(2, Math.ceil(Math.sqrt(items.length * 1.2)));
        const itemSpacingX = 260;
        const itemSpacingY = 140;

        items.forEach((item, itemIdx) => {
          const r = Math.floor(itemIdx / itemsPerRow);
          const c = itemIdx % itemsPerRow;
          const x = clusterCenterX - (itemsPerRow * itemSpacingX) / 2 + c * itemSpacingX;
          const y = clusterCenterY - (Math.ceil(items.length / itemsPerRow) * itemSpacingY) / 2 + r * itemSpacingY;

          flowNodesList.push({
            id: String(item.id),
            data: {
              label: `${item.canonical_name || item.label || "Unnamed Entity"}\n[${item.entity_type || item.type || "entity"}]`,
              raw: item,
            },
            position: { x, y },
          });
        });
      });

      return flowNodesList;
    }

    // Fallback mode: "circle"
    const baseRadius = Math.max(550, total * 22);
    return nodesList.map((n, idx) => {
      const angle = (idx / total) * 2 * Math.PI;
      return {
        id: String(n.id),
        data: {
          label: `${n.canonical_name || n.label || "Unnamed Entity"}\n[${n.entity_type || n.type || "entity"}]`,
          raw: n,
        },
        position: {
          x: 900 + baseRadius * Math.cos(angle),
          y: 800 + baseRadius * Math.sin(angle),
        },
      };
    });
  }, []);

  const loadGraphData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const graphData = await api.relationships.getGraph(projectId);
      setRawGraphData(graphData as any);

      const computed = computeLayout(graphData.nodes as any, graphData.edges as any, layoutMode);

      const flowNodes: Node[] = computed.map((c) => {
        const n = c.data.raw;
        const entityType = n.entity_type || n.type || "entity";
        const canonicalName = n.canonical_name || n.label || "Unnamed Entity";
        const confidence = typeof n.confidence === "number" ? n.confidence : 1.0;
        const resolutionStatus = n.resolution_status || n.status || n.verification_status || "candidate";

        return {
          id: c.id,
          data: {
            label: `${canonicalName}\n[${entityType}]`,
            raw: {
              ...n,
              id: c.id,
              canonical_name: canonicalName,
              type: entityType,
              confidence,
              resolution_status: resolutionStatus,
            },
          },
          position: c.position,
          style: {
            background: entityType === "decision" ? "#fef3c7" : entityType === "person" ? "#e0e7ff" : entityType === "component" ? "#dcfce7" : "#f1f5f9",
            color: "#0f172a",
            border: entityType === "decision" ? "1.5px solid #d97706" : entityType === "person" ? "1.5px solid #4f46e5" : "1px solid #94a3b8",
            borderRadius: "10px",
            fontSize: "12px",
            padding: "10px 14px",
            textAlign: "center" as const,
            whiteSpace: "pre-wrap" as const,
            boxShadow: "0 2px 6px -1px rgba(0, 0, 0, 0.08)",
            minWidth: "160px",
            maxWidth: "240px",
          },
        };
      });

      const flowEdges: Edge[] = graphData.edges.map((e) => {
        const edgeType = e.relationship_type || e.type || e.label || "related_to";
        return {
          id: String(e.id),
          source: String(e.source),
          target: String(e.target),
          label: String(e.label || edgeType).toLowerCase().replace(/_/g, " "),
          markerEnd: { type: MarkerType.ArrowClosed },
          style: { stroke: "#64748b" },
        };
      });

      setNodes(flowNodes);
      setEdges(flowEdges);
    } catch (err: unknown) {
      setError((err as Error)?.message || "Failed to load relationship graph");
    } finally {
      setLoading(false);
    }
  }, [projectId, layoutMode, computeLayout, setNodes, setEdges]);

  // Re-run layout when user switches mode or filter
  useEffect(() => {
    if (rawGraphData.nodes.length > 0) {
      let filtered = rawGraphData.nodes;
      if (selectedTypeFilter !== "all") {
        filtered = filtered.filter((n) => (n.entity_type || n.type || "").toLowerCase() === selectedTypeFilter.toLowerCase());
      }
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        filtered = filtered.filter((n) => (n.canonical_name || n.label || "").toLowerCase().includes(q));
      }

      const computed = computeLayout(filtered, rawGraphData.edges, layoutMode);
      const flowNodes: Node[] = computed.map((c) => {
        const n = c.data.raw;
        const entityType = n.entity_type || n.type || "entity";
        const canonicalName = n.canonical_name || n.label || "Unnamed Entity";
        return {
          id: c.id,
          data: {
            label: `${canonicalName}\n[${entityType}]`,
            raw: n,
          },
          position: c.position,
          style: {
            background: entityType === "decision" ? "#fef3c7" : entityType === "person" ? "#e0e7ff" : entityType === "component" ? "#dcfce7" : "#f1f5f9",
            color: "#0f172a",
            border: entityType === "decision" ? "1.5px solid #d97706" : entityType === "person" ? "1.5px solid #4f46e5" : "1px solid #94a3b8",
            borderRadius: "10px",
            fontSize: "12px",
            padding: "10px 14px",
            textAlign: "center" as const,
            whiteSpace: "pre-wrap" as const,
            boxShadow: "0 2px 6px -1px rgba(0, 0, 0, 0.08)",
            minWidth: "160px",
            maxWidth: "240px",
          },
        };
      });
      setNodes(flowNodes);
    }
  }, [layoutMode, selectedTypeFilter, searchQuery, rawGraphData, computeLayout, setNodes]);

  useEffect(() => {
    loadGraphData();
  }, [loadGraphData]);

  async function loadTabDetails(tab: typeof activeTab) {
    setActiveTab(tab);
    setError(null);
    try {
      if (tab === "entities" && entities.length === 0) {
        const res = await api.relationships.listEntities(projectId);
        setEntities(res.items || []);
      } else if (tab === "traceability" && traceChains.length === 0) {
        const res = await api.relationships.getTraceability(projectId);
        const chainsList = (res.chains || res.items || []).map((tc: any) => ({
          ...tc,
          decision_name: tc.decision_name || "Untitled Decision",
          work_item_count: tc.work_item_count ?? tc.work_item_ids?.length ?? 0,
          pr_count: tc.pr_count ?? tc.pull_request_ids?.length ?? 0,
          commit_count: tc.commit_count ?? tc.commit_ids?.length ?? 0,
          component_count: tc.component_count ?? tc.component_ids?.length ?? 0,
          missing_links: tc.missing_links || [],
        }));
        setTraceChains(chainsList);
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
      } else if (tab === "candidates" && candidates.length === 0) {
        const res = await api.relationships.listIdentityCandidates(projectId);
        setCandidates((res || []) as unknown as IdentityCandidateItem[]);
      }
    } catch (err: unknown) {
      setError((err as Error)?.message || `Failed to load ${tab} data`);
    }
  }

  return (
    <div className="flex flex-col h-[calc(100vh-180px)] min-h-[500px] bg-slate-50 border border-slate-200 rounded-xl overflow-hidden shadow-sm">
      {/* Tab Navigation */}
      <div className="flex items-center justify-between px-6 py-3 bg-white border-b border-slate-200">
        <div className="flex items-center gap-2">
          <Network className="w-5 h-5 text-indigo-600" />
          <h2 className="font-semibold text-slate-800 text-base">Interactive Knowledge Graph & Explorer</h2>
        </div>
        <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-lg text-xs font-medium">
          <button
            onClick={() => loadTabDetails("graph")}
            className={`px-3 py-1.5 rounded-md transition-all ${
              activeTab === "graph" ? "bg-white text-indigo-600 shadow-sm font-semibold" : "text-slate-600 hover:text-slate-900"
            }`}
          >
            Graph Explorer
          </button>
          <button
            onClick={() => loadTabDetails("entities")}
            className={`px-3 py-1.5 rounded-md transition-all ${
              activeTab === "entities" ? "bg-white text-indigo-600 shadow-sm font-semibold" : "text-slate-600 hover:text-slate-900"
            }`}
          >
            Entities
          </button>
          <button
            onClick={() => loadTabDetails("traceability")}
            className={`px-3 py-1.5 rounded-md transition-all ${
              activeTab === "traceability" ? "bg-white text-indigo-600 shadow-sm font-semibold" : "text-slate-600 hover:text-slate-900"
            }`}
          >
            Traceability
          </button>
          <button
            onClick={() => loadTabDetails("dependencies")}
            className={`px-3 py-1.5 rounded-md transition-all ${
              activeTab === "dependencies" ? "bg-white text-indigo-600 shadow-sm font-semibold" : "text-slate-600 hover:text-slate-900"
            }`}
          >
            Dependencies
          </button>
          <button
            onClick={() => loadTabDetails("timeline")}
            className={`px-3 py-1.5 rounded-md transition-all ${
              activeTab === "timeline" ? "bg-white text-indigo-600 shadow-sm font-semibold" : "text-slate-600 hover:text-slate-900"
            }`}
          >
            Timeline
          </button>
          <button
            onClick={() => loadTabDetails("candidates")}
            className={`px-3 py-1.5 rounded-md transition-all ${
              activeTab === "candidates" ? "bg-white text-indigo-600 shadow-sm font-semibold" : "text-slate-600 hover:text-slate-900"
            }`}
          >
            Entity Resolution
          </button>
        </div>
      </div>

      {/* Main Tab Panels */}
      <div className="flex-1 relative overflow-hidden">
        {error && (
          <div className="absolute top-4 left-4 right-4 z-50 bg-red-50 text-red-700 border border-red-200 px-4 py-3 rounded-lg text-sm flex items-center justify-between">
            <span>{error}</span>
            <button onClick={() => setError(null)} className="text-red-500 hover:text-red-800 font-bold">×</button>
          </div>
        )}

        {/* 1. GRAPH EXPLORER */}
        {activeTab === "graph" && (
          <div className="w-full h-full relative flex flex-col">
            {/* Graph Controls Toolbar */}
            <div className="z-10 bg-white/95 backdrop-blur-xs border-b border-slate-200 px-4 py-2.5 flex flex-wrap items-center justify-between gap-3 shadow-2xs">
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Layout:</span>
                <div className="flex bg-slate-100 p-0.5 rounded-lg text-xs">
                  <button
                    onClick={() => setLayoutMode("cluster")}
                    className={`px-2.5 py-1 rounded-md transition ${layoutMode === "cluster" ? "bg-white text-indigo-600 font-semibold shadow-xs" : "text-slate-600 hover:text-slate-900"}`}
                  >
                    Domain Clusters
                  </button>
                  <button
                    onClick={() => setLayoutMode("grid")}
                    className={`px-2.5 py-1 rounded-md transition ${layoutMode === "grid" ? "bg-white text-indigo-600 font-semibold shadow-xs" : "text-slate-600 hover:text-slate-900"}`}
                  >
                    Organized Grid
                  </button>
                  <button
                    onClick={() => setLayoutMode("circle")}
                    className={`px-2.5 py-1 rounded-md transition ${layoutMode === "circle" ? "bg-white text-indigo-600 font-semibold shadow-xs" : "text-slate-600 hover:text-slate-900"}`}
                  >
                    Radial
                  </button>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <select
                  value={selectedTypeFilter}
                  onChange={(e) => setSelectedTypeFilter(e.target.value)}
                  className="bg-slate-100 border border-slate-200 text-xs rounded-lg px-2.5 py-1.5 text-slate-700 outline-none"
                >
                  <option value="all">All Entity Types</option>
                  <option value="decision">Decisions</option>
                  <option value="person">People & Ownership</option>
                  <option value="work_item">Work Items & Tasks</option>
                  <option value="component">Technical Components</option>
                </select>

                <div className="relative">
                  <input
                    type="text"
                    placeholder="Search entities..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="bg-slate-100 border border-slate-200 text-xs rounded-lg pl-7 pr-3 py-1.5 text-slate-700 outline-none w-44 focus:w-56 transition-all"
                  />
                  <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2 top-2" />
                </div>

                <button
                  onClick={loadGraphData}
                  className="flex items-center gap-1 text-xs text-slate-600 hover:text-indigo-600 bg-slate-100 hover:bg-slate-200 px-2.5 py-1.5 rounded-lg transition"
                  title="Reload graph data"
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                  <span>Reset</span>
                </button>
              </div>
            </div>

            <div className="flex-1 relative">
            {loading ? (
              <div className="flex items-center justify-center h-full text-slate-500">
                <RefreshCw className="w-6 h-6 animate-spin mr-2" /> Loading Knowledge Graph...
              </div>
            ) : nodes.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-slate-500 p-8 text-center">
                <Network className="w-12 h-12 text-slate-300 mb-2" />
                <p className="font-medium text-slate-700">No Graph Relationships Reconstructed Yet</p>
                <p className="text-sm text-slate-400 mt-1 max-w-md">Trigger relationship discovery or AI knowledge reconstruction in the Evidence Center or Knowledge Intelligence to populate graph entities.</p>
              </div>
            ) : (
              <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onNodeClick={(_, node) => setSelectedNode((node.data as { raw?: KnowledgeEntityNode })?.raw || null)}
                fitView
              >
                <Background />
                <Controls />
                <MiniMap />
              </ReactFlow>
            )}

            {/* Selected Node Details Drawer */}
            {selectedNode && (
              <div className="absolute right-4 top-4 bottom-4 w-80 bg-white border border-slate-200 rounded-xl shadow-lg p-5 z-20 overflow-y-auto">
                <div className="flex items-center justify-between pb-3 border-b border-slate-100">
                  <span className="text-xs font-semibold px-2 py-0.5 rounded bg-indigo-50 text-indigo-700 uppercase">
                    {selectedNode.type || selectedNode.entity_type || "entity"}
                  </span>
                  <button onClick={() => setSelectedNode(null)} className="text-slate-400 hover:text-slate-700 text-lg">×</button>
                </div>
                <h3 className="font-semibold text-slate-900 mt-3 text-base">{selectedNode.canonical_name || selectedNode.label || "Unnamed Entity"}</h3>
                <p className="text-xs text-slate-500 mt-1">ID: {selectedNode.id}</p>
                <div className="mt-4 space-y-2 text-sm text-slate-600">
                  <div className="flex justify-between">
                    <span className="text-slate-400">Confidence:</span>
                    <span className="font-medium text-slate-800">{((selectedNode.confidence ?? 1.0) * 100).toFixed(1)}%</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Resolution:</span>
                    <span className="font-medium text-slate-800 capitalize">{selectedNode.resolution_status || selectedNode.status || "candidate"}</span>
                  </div>
                </div>
              </div>
            )}
            </div>
          </div>
        )}

        {/* 2. ENTITY EXPLORER */}
        {activeTab === "entities" && (
          <div className="p-6 h-full overflow-y-auto">
            <div className="flex items-center gap-3 mb-6">
              <div className="relative flex-1">
                <Search className="w-4 h-4 absolute left-3 top-3 text-slate-400" />
                <input
                  type="text"
                  placeholder="Filter entities by name or type..."
                  value={entityFilter}
                  onChange={(e) => setEntityFilter(e.target.value)}
                  className="w-full pl-9 pr-4 py-2 bg-white border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {entities
                .filter((e) =>
                  e.canonical_name.toLowerCase().includes(entityFilter.toLowerCase()) ||
                  e.entity_type.toLowerCase().includes(entityFilter.toLowerCase())
                )
                .map((ent) => (
                  <div key={ent.id} className="bg-white p-4 border border-slate-200 rounded-xl shadow-xs hover:border-indigo-300 transition-all">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-semibold px-2 py-0.5 rounded bg-slate-100 text-slate-700 uppercase">
                        {ent.entity_type}
                      </span>
                      <span className="text-xs text-slate-400">{(ent.confidence_score * 100).toFixed(0)}% conf</span>
                    </div>
                    <h4 className="font-medium text-slate-900 text-sm">{ent.canonical_name}</h4>
                    {ent.description && <p className="text-xs text-slate-500 mt-2 line-clamp-2">{ent.description}</p>}
                  </div>
                ))}
            </div>
          </div>
        )}

        {/* 3. DECISION TRACEABILITY */}
        {activeTab === "traceability" && (
          <div className="p-6 h-full overflow-y-auto">
            <h3 className="text-base font-semibold text-slate-900 mb-4">Decision-to-Implementation Traceability Chains</h3>
            <div className="space-y-4">
              {traceChains.map((tc) => (
                <div key={tc.id} className="bg-white p-5 border border-slate-200 rounded-xl shadow-xs">
                  <div className="flex items-center justify-between mb-3">
                    <span className="font-semibold text-slate-800 text-sm">{tc.decision_name}</span>
                    <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${
                      tc.completeness_status === "complete" ? "bg-emerald-50 text-emerald-700 border border-emerald-200" :
                      tc.completeness_status === "partially_traced" ? "bg-amber-50 text-amber-700 border border-amber-200" :
                      "bg-slate-100 text-slate-600"
                    }`}>
                      {tc.completeness_status.replace(/_/g, " ")}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 text-xs text-slate-500 mt-2">
                    <span>Work items: {tc.work_item_count}</span>
                    <span>•</span>
                    <span>Pull requests: {tc.pr_count}</span>
                    <span>•</span>
                    <span>Commits: {tc.commit_count}</span>
                    <span>•</span>
                    <span>Components: {tc.component_count}</span>
                  </div>
                  {tc.missing_links && tc.missing_links.length > 0 && (
                    <div className="mt-3 p-2.5 bg-amber-50 rounded-lg text-xs text-amber-800">
                      <strong>Missing Links:</strong> {tc.missing_links.join(", ")}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 4. DEPENDENCIES & BLOCKERS */}
        {activeTab === "dependencies" && (
          <div className="p-6 h-full overflow-y-auto">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="bg-white p-5 border border-slate-200 rounded-xl">
                <h4 className="font-semibold text-slate-800 text-sm mb-3 flex items-center gap-2">
                  <ShieldAlert className="w-4 h-4 text-red-500" /> Root Blockers
                </h4>
                {(!depGraph?.root_blockers || depGraph.root_blockers.length === 0) ? (
                  <p className="text-xs text-slate-500">No active root blockers identified.</p>
                ) : (
                  <ul className="space-y-2">
                    {depGraph.root_blockers.map((b, i: number) => {
                      const blockerName = typeof b === "string" ? b : (b?.name || b?.entity_id || "Unknown Blocker");
                      const blockerType = typeof b === "object" && b?.entity_type ? ` [${b.entity_type}]` : "";
                      return (
                        <li key={i} className="text-xs bg-red-50 text-red-700 p-2 rounded-md border border-red-100">
                          {blockerName}{blockerType}
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>

              <div className="bg-white p-5 border border-slate-200 rounded-xl">
                <h4 className="font-semibold text-slate-800 text-sm mb-3 flex items-center gap-2">
                  <GitBranch className="w-4 h-4 text-amber-500" /> Cycle Detection
                </h4>
                {(!depGraph?.cycles || depGraph.cycles.length === 0) ? (
                  <p className="text-xs text-emerald-600 font-medium">✓ Valid Directed Acyclic Graph (DAG): Zero circular dependencies detected.</p>
                ) : (
                  <ul className="space-y-2">
                    {depGraph.cycles.map((cyc: string[], idx: number) => (
                      <li key={idx} className="text-xs bg-amber-50 text-amber-800 p-2 rounded-md border border-amber-200">
                        Cycle #{idx + 1}: {cyc.join(" ➔ ")}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          </div>
        )}

        {/* 5. TIMELINE */}
        {activeTab === "timeline" && (
          <div className="p-6 h-full overflow-y-auto">
            <h3 className="text-base font-semibold text-slate-900 mb-4 flex items-center gap-2">
              <Clock className="w-5 h-5 text-indigo-600" /> Reconstructed Project Timeline
            </h3>
            <div className="relative pl-6 border-l-2 border-slate-200 space-y-6">
              {timelineEvents.map((evt) => (
                <div key={evt.id} className="relative">
                  <div className="absolute -left-[31px] top-1 w-3.5 h-3.5 rounded-full bg-indigo-500 border-2 border-white shadow-xs" />
                  <div className="bg-white p-4 border border-slate-200 rounded-xl shadow-xs">
                    <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
                      <span>{new Date(evt.occurred_at).toLocaleString()}</span>
                      <span className="uppercase font-semibold">{evt.event_type}</span>
                    </div>
                    <h5 className="font-semibold text-slate-900 text-sm">{evt.title}</h5>
                    {evt.summary && <p className="text-xs text-slate-600 mt-1">{evt.summary}</p>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 6. ENTITY RESOLUTION */}
        {activeTab === "candidates" && (
          <div className="p-6 h-full overflow-y-auto">
            <h3 className="text-base font-semibold text-slate-900 mb-4">Identity Merge Candidates (Review Queue)</h3>
            <div className="space-y-4">
              {candidates.length === 0 ? (
                <p className="text-sm text-slate-500">Zero pending identity candidates requiring manual review.</p>
              ) : (
                candidates.map((cand) => {
                  const leftName = cand.left_entity?.canonical_name || cand.left_entity_name || cand.left_entity_id;
                  const rightName = cand.right_entity?.canonical_name || cand.right_entity_name || cand.right_entity_id;
                  return (
                    <div key={cand.id} className="bg-white p-5 border border-slate-200 rounded-xl shadow-xs flex items-center justify-between">
                      <div>
                        <div className="flex items-center gap-2 text-sm font-semibold text-slate-800">
                          <span>{leftName}</span>
                          <span className="text-slate-400">⇄</span>
                          <span>{rightName}</span>
                        </div>
                        <p className="text-xs text-slate-500 mt-1">
                          Match Score: {(cand.match_score * 100).toFixed(1)}% • Band: {cand.policy_band}
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={async () => {
                            await api.relationships.reviewCandidate(projectId, cand.id, "accept");
                            setCandidates((prev) => prev.filter((c) => c.id !== cand.id));
                          }}
                          className="px-3 py-1.5 bg-indigo-600 text-white rounded-lg text-xs font-semibold hover:bg-indigo-700"
                        >
                          Accept Merge
                        </button>
                        <button
                          onClick={async () => {
                            await api.relationships.reviewCandidate(projectId, cand.id, "reject");
                            setCandidates((prev) => prev.filter((c) => c.id !== cand.id));
                          }}
                          className="px-3 py-1.5 bg-slate-100 text-slate-700 rounded-lg text-xs font-semibold hover:bg-slate-200"
                        >
                          Reject
                        </button>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
