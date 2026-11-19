import fs from "node:fs";
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import {
  buildExpandableProjection,
  isLargeExpandableGraph,
  LARGE_GRAPH_THRESHOLD,
} from "../components/knowledge/ameliorate/expandableGraph";
import type { HandoverGraphEdge, HandoverGraphNode } from "../components/knowledge/ameliorate/ameliorateAdapter";

function makeSyntheticNodes(count: number): HandoverGraphNode[] {
  const nodes: HandoverGraphNode[] = [
    {
      id: "root-proj",
      entity_type: "project",
      label: "Handover",
      status: "IN_PROGRESS",
      verification_status: "approved",
      evidence_count: 5,
      evidence_ids: [],
      aliases: [],
      metadata: {},
    },
  ];
  const cats = ["frontend", "backend", "database", "infrastructure", "testing", "ai_ml"];
  for (let i = 1; i < count; i++) {
    const cat = cats[(i - 1) % cats.length]!;
    nodes.push({
      id: `n-${i}`,
      entity_type: "technology",
      category: cat,
      label: `Tech ${i}`,
      status: "declared_dependency",
      verification_status: "pending_review",
      evidence_count: 1,
      evidence_ids: [],
      aliases: [],
      metadata: { technology_category: cat },
    });
  }
  return nodes;
}

const mockGetGraph = vi.fn();
const mockGetGraphNodeDetail = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(""),
}));

vi.mock("@xyflow/react", () => ({
  ReactFlow: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
  Controls: () => <div />,
  Background: () => <div />,
  MiniMap: () => <div />,
  useNodesState: (init: unknown[]) => [init, vi.fn(), vi.fn()],
  useEdgesState: (init: unknown[]) => [init, vi.fn(), vi.fn()],
  MarkerType: { ArrowClosed: "arrowclosed" },
  Handle: () => null,
  Position: { Top: "top", Bottom: "bottom" },
  getBezierPath: () => ["M0,0 L10,10", 5, 5],
  EdgeLabelRenderer: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
}));

vi.mock("../components/knowledge/ameliorate/AmeliorateFlowchartCanvas", () => ({
  AmeliorateFlowchartCanvas: ({
    rawNodes,
    rawEdges,
    selectedNodeId,
    onSelectNode,
  }: {
    rawNodes: HandoverGraphNode[];
    rawEdges: HandoverGraphEdge[];
    selectedNodeId: string | null;
    onSelectNode: (node: any) => void;
  }) => (
    <div data-testid="ameliorate-canvas" data-node-count={rawNodes.length} data-edge-count={rawEdges.length} data-selected={selectedNodeId ?? ""}>
      {rawNodes.map((n) => (
        <button
          key={n.id}
          type="button"
          onClick={() => onSelectNode({ id: n.id, position: { x: 0, y: 0 }, data: { raw: n } })}
        >
          {n.label}
        </button>
      ))}
    </div>
  ),
}));

vi.mock("../context/LiveAppContext", () => ({
  useLiveApp: () => ({
    findings: [],
    refreshFindings: vi.fn(),
    refreshVerification: vi.fn(),
  }),
}));

vi.mock("../hooks/useProjectProcessingStatus", () => ({
  useProjectProcessingStatus: () => ({
    status: { is_processing: false, status: "idle" },
    retry: vi.fn(),
    retrying: false,
  }),
}));

vi.mock("../lib/api", () => ({
  api: {
    knowledgeIntelligence: {
      getGraph: (...args: unknown[]) => mockGetGraph(...args),
      getGraphNodeDetail: (...args: unknown[]) => mockGetGraphNodeDetail(...args),
      listFindings: vi.fn(async () => ({ items: [] })),
    },
  },
}));

import { KnowledgeIntelligenceWorkspace } from "../components/knowledge/KnowledgeIntelligenceWorkspace";
import { invalidateGraphCache } from "../lib/graphCache";

describe("Threshold-based Expandable Large Graphs (LARGE_GRAPH_THRESHOLD = 24)", () => {
  beforeEach(() => {
    mockGetGraph.mockReset();
    mockGetGraphNodeDetail.mockReset();
    invalidateGraphCache("ki_");
  });

  it("enforces exact 24-node threshold boundary across 3, 6, 12, 20, 24, 25, 40, 90 nodes and excludes features-workflows", () => {
    expect(LARGE_GRAPH_THRESHOLD).toBe(24);
    for (const count of [3, 6, 12, 20, 24]) {
      expect(isLargeExpandableGraph(count, "technology-stack")).toBe(false);
      expect(isLargeExpandableGraph(count, "system-architecture")).toBe(false);
      expect(isLargeExpandableGraph(count, "features-workflows")).toBe(false);
    }
    for (const count of [25, 40, 90]) {
      expect(isLargeExpandableGraph(count, "technology-stack")).toBe(true);
      expect(isLargeExpandableGraph(count, "system-architecture")).toBe(true);
      expect(isLargeExpandableGraph(count, "features-workflows")).toBe(false);
    }
  });

  it("opens real 90-node handover Technology Stack graph as clean overview with accurate counts, expand/collapse, and search", () => {
    const nodes = makeSyntheticNodes(90);
    const backendNode = nodes.find((n) => n.category === "backend");
    if (backendNode) {
      backendNode.label = "FastAPI";
    }
    const edges: HandoverGraphEdge[] = nodes.slice(1).map((n) => ({
      id: `e-root-${n.id}`,
      source: "root-proj",
      target: n.id,
      relationship_type: "USES",
      label: "uses",
      evidence_basis: "Architecture spec",
      verification_status: "approved",
      confidence_score: 0.95,
      evidence_ids: [],
    }));
    expect(nodes.length).toBe(90);

    // 1. Initial collapsed overview
    const overview = buildExpandableProjection({
      rawNodes: nodes,
      rawEdges: edges,
      mode: "technology-stack",
      expandedGroupIds: new Set(),
      revealedCountsByGroup: new Map(),
    });
    const sumCounts = overview.groups.reduce((acc, g) => acc + g.totalCount, 0);
    expect(sumCounts).toBe(89); // 89 non-root + 1 root = 90
    expect(overview.nodes.length).toBe(overview.groups.length + 1);

    // 2. Expand Backend group -> reveals children while keeping unrelated groups collapsed
    const backendGroup = overview.groups.find((g) => g.label.toLowerCase().includes("backend"))!;
    expect(backendGroup).toBeDefined();
    const expanded = buildExpandableProjection({
      rawNodes: nodes,
      rawEdges: edges,
      mode: "technology-stack",
      expandedGroupIds: new Set([backendGroup.groupId]),
      revealedCountsByGroup: new Map(),
    });
    expect(expanded.nodes.length).toBeGreaterThan(overview.nodes.length);
    expect(expanded.groups.filter((g) => g.expanded).length).toBe(1);

    // 2b. Expanding ALL groups manually reveals 100% of all canonical nodes (no 14-node cap)
    const allExpanded = buildExpandableProjection({
      rawNodes: nodes,
      rawEdges: edges,
      mode: "technology-stack",
      expandedGroupIds: new Set(overview.groups.map((g) => g.groupId)),
      revealedCountsByGroup: new Map(),
    });
    const visibleIds = new Set(allExpanded.nodes.map((n) => n.id));
    for (const n of nodes) {
      expect(visibleIds.has(n.id)).toBe(true);
    }

    // 3. Search finds FastAPI inside collapsed group and auto-expands it
    const searched = buildExpandableProjection({
      rawNodes: nodes,
      rawEdges: edges,
      mode: "technology-stack",
      expandedGroupIds: new Set(),
      revealedCountsByGroup: new Map(),
      searchQuery: "FastAPI",
    });
    expect(searched.highlightedNodeId).toBeTruthy();
    expect(searched.nodes.some((n) => n.label.toLowerCase().includes("fastapi"))).toBe(true);
  });

  it("renders <= 24 nodes untouched, activates overview at 25+, supports Show Full Graph, and never jumps during live 24->25 growth", async () => {
    const nodes24 = makeSyntheticNodes(24);
    const nodes25 = makeSyntheticNodes(25);
    mockGetGraph.mockResolvedValueOnce({ nodes: nodes24, edges: [] });

    render(<KnowledgeIntelligenceWorkspace projectId="proj-threshold" initialMode="technology-stack" />);

    await waitFor(() => {
      const canvas = screen.getByTestId("ameliorate-canvas");
      expect(canvas.getAttribute("data-node-count")).toBe("24");
    });
    expect(screen.queryByText(/Grouped Overview/i)).not.toBeInTheDocument();

    // Simulate live update crossing 24 -> 25 nodes
    mockGetGraph.mockResolvedValueOnce({ nodes: nodes25, edges: [] });
    fireEvent.click(screen.getByRole("button", { name: /Refresh/i }));

    await waitFor(() => {
      expect(screen.getByText(/Graph grew to 25 nodes/i)).toBeInTheDocument();
    });
    // View stayed in Full Graph instead of jumping to overview
    expect(screen.getByTestId("ameliorate-canvas").getAttribute("data-node-count")).toBe("25");

    // User can opt-in to Grouped Overview, expand a group, and inspect a real node
    fireEvent.click(screen.getByRole("button", { name: /Switch to Grouped Overview/i }));
    await waitFor(() => {
      expect(screen.getByText(/Grouped Overview \(25 nodes\)/i)).toBeInTheDocument();
    });

    const backendBtn = screen.getByRole("button", { name: /Backend \(4\)/i });
    fireEvent.click(backendBtn);
    expect(mockGetGraphNodeDetail).not.toHaveBeenCalled();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Back to Overview/i })).toBeInTheDocument();
    });

    // Clicking a real canonical node opens the existing detail drawer via getGraphNodeDetail
    mockGetGraphNodeDetail.mockResolvedValueOnce({
      node: nodes25[2],
      evidence_refs: [],
      adjacent_edges: [],
      related_nodes: [],
    });
    fireEvent.click(screen.getByRole("button", { name: "Tech 2" }));
    await waitFor(() => {
      expect(mockGetGraphNodeDetail).toHaveBeenCalledWith("proj-threshold", "technology-stack", "n-2");
    });
  });
});
