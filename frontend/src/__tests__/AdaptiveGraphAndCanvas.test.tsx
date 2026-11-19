import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import {
  buildAmeliorateFlowchartElements,
  layoutWithElk,
  recomputeEdgeLabelPositions,
  resolveIncrementalNodePositions,
  type HandoverGraphEdge,
  type HandoverGraphNode,
} from "../components/knowledge/ameliorate/ameliorateAdapter";
import { AmeliorateFlowchartCanvas } from "../components/knowledge/ameliorate/AmeliorateFlowchartCanvas";

let lastMiniMapProps: Record<string, unknown> = {};
const mockFitView = vi.fn();
const mockGetViewport = vi.fn(() => ({ x: 10, y: 20, zoom: 0.85 }));
const mockSetViewport = vi.fn();

vi.mock("@xyflow/react", () => ({
  ReactFlow: ({
    nodes,
    children,
    onInit,
    onNodeClick,
  }: {
    nodes: Array<{ id: string }>;
    children?: React.ReactNode;
    onInit?: (inst: unknown) => void;
    onNodeClick?: (e: unknown, node: unknown) => void;
  }) => {
    React.useEffect(() => {
      onInit?.({
        fitView: mockFitView,
        getViewport: mockGetViewport,
        setViewport: mockSetViewport,
      });
    }, [onInit]);
    return (
      <div data-testid="react-flow-mock">
        {nodes.map((n) => (
          <button
            key={n.id}
            type="button"
            data-testid={`mock-node-${n.id}`}
            onClick={() => onNodeClick?.({}, n)}
          >
            {n.id}
          </button>
        ))}
        {children}
      </div>
    );
  },
  Controls: () => <div data-testid="rf-controls" />,
  Background: () => <div data-testid="rf-background" />,
  MiniMap: (props: Record<string, unknown>) => {
    lastMiniMapProps = props;
    return <div data-testid="rf-minimap" />;
  },
  useNodesState: (init: unknown[]) => {
    const [val, setVal] = React.useState(init);
    return [val, setVal, vi.fn()];
  },
  useEdgesState: (init: unknown[]) => {
    const [val, setVal] = React.useState(init);
    return [val, setVal, vi.fn()];
  },
  MarkerType: { ArrowClosed: "arrowclosed" },
  Handle: () => null,
  Position: { Top: "top", Bottom: "bottom" },
  getBezierPath: () => ["M0,0 L10,10", 5, 5],
  EdgeLabelRenderer: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
}));

function makeNode(id: string, type = "technical_component"): HandoverGraphNode {
  return {
    id,
    entity_type: type,
    label: `Node ${id}`,
    status: "SOURCE_EXTRACTED",
    verification_status: "unverified",
    evidence_count: 1,
    evidence_ids: [],
    aliases: [],
    metadata: {},
  };
}

function makeEdge(source: string, target: string, idx = 0): HandoverGraphEdge {
  return {
    id: `e-${source}-${target}-${idx}`,
    source,
    target,
    relationship_type: "depends_on",
    label: "depends on",
    evidence_basis: "explicit",
    verification_status: "unverified",
    confidence_score: 0.9,
    evidence_ids: [],
  };
}

function assertNoNodeOverlaps(nodes: Array<{ id: string; position: { x: number; y: number } }>) {
  const W = 204;
  const H = 104;
  for (let i = 0; i < nodes.length; i++) {
    for (let j = i + 1; j < nodes.length; j++) {
      const a = nodes[i]!;
      const b = nodes[j]!;
      const overlapX = Math.abs(a.position.x - b.position.x) < W;
      const overlapY = Math.abs(a.position.y - b.position.y) < H;
      expect(overlapX && overlapY, `Overlap between ${a.id} and ${b.id}`).toBe(false);
    }
  }
}

describe("Adaptive Graph Layouts, MiniMap & Fullscreen", () => {
  beforeEach(() => {
    lastMiniMapProps = {};
    mockFitView.mockClear();
    mockGetViewport.mockClear();
    mockSetViewport.mockClear();
  });

  const topologies: Array<{
    name: string;
    build: () => { nodes: HandoverGraphNode[]; edges: HandoverGraphEdge[] };
  }> = [
    {
      name: "2 nodes / 1 edge",
      build: () => ({
        nodes: [makeNode("a"), makeNode("b")],
        edges: [makeEdge("a", "b")],
      }),
    },
    {
      name: "5 nodes hub-and-spoke",
      build: () => ({
        nodes: ["hub", "s1", "s2", "s3", "s4"].map((id) => makeNode(id)),
        edges: ["s1", "s2", "s3", "s4"].map((s, i) => makeEdge("hub", s, i)),
      }),
    },
    {
      name: "12 nodes branching hierarchy",
      build: () => {
        const nodes = Array.from({ length: 12 }, (_, i) => makeNode(`h${i}`));
        const edges: HandoverGraphEdge[] = [];
        for (let i = 1; i < 12; i++) {
          edges.push(makeEdge(`h${Math.floor((i - 1) / 2)}`, `h${i}`, i));
        }
        return { nodes, edges };
      },
    },
    {
      name: "20 nodes multiple connected components",
      build: () => {
        const nodes = Array.from({ length: 20 }, (_, i) => makeNode(`m${i}`));
        const edges: HandoverGraphEdge[] = [];
        for (let g = 0; g < 4; g++) {
          const base = g * 5;
          for (let k = 1; k < 5; k++) {
            edges.push(makeEdge(`m${base}`, `m${base + k}`, base + k));
          }
        }
        return { nodes, edges };
      },
    },
    {
      name: "45 nodes dense cross-connected graph",
      build: () => {
        const nodes = Array.from({ length: 45 }, (_, i) => makeNode(`d${i}`));
        const edges: HandoverGraphEdge[] = [];
        let eid = 0;
        for (let i = 0; i < 45; i++) {
          edges.push(makeEdge(`d${i}`, `d${(i + 1) % 45}`, eid++));
          edges.push(makeEdge(`d${i}`, `d${(i + 7) % 45}`, eid++));
        }
        return { nodes, edges };
      },
    },
    {
      name: "70 nodes large graph",
      build: () => {
        const nodes = Array.from({ length: 70 }, (_, i) => makeNode(`lg${i}`));
        const edges = Array.from({ length: 69 }, (_, i) => makeEdge(`lg${Math.floor(i / 3)}`, `lg${i + 1}`, i));
        return { nodes, edges };
      },
    },
  ];

  const viewports = [
    { label: "wide", viewportWidth: 1600, viewportHeight: 700 },
    { label: "tall", viewportWidth: 600, viewportHeight: 1000 },
    { label: "laptop", viewportWidth: 1024, viewportHeight: 600 },
    { label: "fullscreen", viewportWidth: 1920, viewportHeight: 1080 },
  ];

  for (const topo of topologies) {
    for (const vp of viewports) {
      it(`lays out ${topo.name} cleanly in ${vp.label} viewport with zero overlaps and deterministic coordinates`, () => {
        const { nodes: rawNodes, edges: rawEdges } = topo.build();
        const first = buildAmeliorateFlowchartElements(rawNodes, rawEdges, null, vp);
        const second = buildAmeliorateFlowchartElements(rawNodes, rawEdges, null, vp);

        expect(first.nodes).toHaveLength(rawNodes.length);
        assertNoNodeOverlaps(first.nodes);
        expect(first.nodes.map((n) => n.position)).toEqual(second.nodes.map((n) => n.position));
      });
    }
  }

  it("preserves existing node positions during incremental background updates", () => {
    const initialNodes = [makeNode("n1"), makeNode("n2")];
    const initialEdges = [makeEdge("n1", "n2")];
    const layout1 = buildAmeliorateFlowchartElements(initialNodes, initialEdges, null);

    const existingPos = new Map<string, { x: number; y: number }>();
    existingPos.set("n1", { x: 420, y: 20 });
    existingPos.set("n2", { x: 760, y: 20 });

    const nextNodes = [makeNode("n1"), makeNode("n2"), makeNode("n3")];
    const nextEdges = [makeEdge("n1", "n2"), makeEdge("n2", "n3", 1)];
    const layout2 = buildAmeliorateFlowchartElements(nextNodes, nextEdges, null);
    const resolved = resolveIncrementalNodePositions(layout2.nodes, layout2.edges, existingPos);

    const p1 = resolved.find((n) => n.id === "n1")!.position;
    const p2 = resolved.find((n) => n.id === "n2")!.position;
    expect(p1).toEqual({ x: 420, y: 20 });
    expect(p2).toEqual({ x: 760, y: 20 });
    expect(layout1.nodes.length).toBe(2);
    assertNoNodeOverlaps(resolved);
  });

  it("renders interactive MiniMap (pannable, zoomable, bottom-right) and supports Fullscreen + Escape", () => {
    const rawNodes = [makeNode("a"), makeNode("b"), makeNode("c")];
    const rawEdges = [makeEdge("a", "b"), makeEdge("b", "c", 1)];
    const onSelectNode = vi.fn();

    render(
      <AmeliorateFlowchartCanvas
        rawNodes={rawNodes}
        rawEdges={rawEdges}
        selectedNodeId="a"
        onSelectNode={onSelectNode}
      />
    );

    expect(screen.getByTestId("rf-minimap")).toBeInTheDocument();
    expect(lastMiniMapProps.pannable).toBe(true);
    expect(lastMiniMapProps.zoomable).toBe(true);
    expect(lastMiniMapProps.position).toBe("bottom-right");

    const fsBtn = screen.getByRole("button", { name: /Expand to fullscreen/i });
    fireEvent.click(fsBtn);

    const container = screen.getByTestId("ameliorate-graph-container");
    expect(container.className).toContain("fixed inset-0");

    fireEvent.keyDown(window, { key: "Escape" });
    expect(container.className).not.toContain("fixed inset-0");

    fireEvent.click(screen.getByTestId("mock-node-b"));
    expect(onSelectNode).toHaveBeenCalledTimes(1);
  });

  it("prevents vertical-column collapse and keeps edge labels aligned after incremental node shifts (100+ nodes & chain-like graphs)", () => {
    // 1. Long chain-like Knowledge Intelligence graph (24 nodes) should use horizontal space rather than 1-column strip
    const chainNodes = Array.from({ length: 24 }, (_, i) =>
      makeNode(`k${i}`, i === 0 ? "project" : i % 3 === 0 ? "database" : "service")
    );
    const chainEdges = Array.from({ length: 23 }, (_, i) => makeEdge(`k${i}`, `k${i + 1}`, i));
    const chainLayout = buildAmeliorateFlowchartElements(chainNodes, chainEdges, null, {
      viewportWidth: 1280,
      viewportHeight: 720,
    });

    assertNoNodeOverlaps(chainLayout.nodes);
    const xs = chainLayout.nodes.map((n) => n.position.x);
    const ys = chainLayout.nodes.map((n) => n.position.y);
    const width = Math.max(...xs) - Math.min(...xs) + 204;
    const height = Math.max(...ys) - Math.min(...ys) + 116;
    expect(width).toBeGreaterThan(600);
    expect(height / width).toBeLessThan(2.5);

    // 2. Edge labels must stay aligned with their edges even after resolveIncrementalNodePositions moves nodes
    const existing = new Map<string, { x: number; y: number }>();
    existing.set("k0", { x: 900, y: 120 });
    const shiftedNodes = resolveIncrementalNodePositions(chainLayout.nodes, chainLayout.edges, existing);
    const realignedEdges = recomputeEdgeLabelPositions(shiftedNodes, chainLayout.edges);
    const posMap = new Map(shiftedNodes.map((n) => [n.id, n.position]));
    for (const edge of realignedEdges) {
      const sp = posMap.get(edge.source)!;
      const tp = posMap.get(edge.target)!;
      const midX = (sp.x + 102 + tp.x + 102) / 2;
      const midY = (sp.y + 116 + tp.y) / 2;
      const lx = edge.data?.labelX ?? midX;
      const ly = edge.data?.labelY ?? midY;
      expect(Math.hypot(lx - midX, ly - midY)).toBeLessThan(Math.hypot(tp.x - sp.x, tp.y - sp.y) + 120);
    }

    // 3. 108-node large graph with mixed dimensions has zero overlaps
    const largeNodes = Array.from({ length: 108 }, (_, i) => makeNode(`big${i}`));
    const largeEdges = Array.from({ length: 107 }, (_, i) => makeEdge(`big${Math.floor(i / 4)}`, `big${i + 1}`, i));
    const largeLayout = buildAmeliorateFlowchartElements(largeNodes, largeEdges, null, {
      viewportWidth: 1440,
      viewportHeight: 900,
    });
    expect(largeLayout.nodes).toHaveLength(108);
    assertNoNodeOverlaps(largeLayout.nodes);
  });

  it("preserves 2-person-to-1-cluster small layout and runs ELK Layered cleanly on 25-node and 55-node graphs", async () => {
    // 1. Small 2-contributor-to-1-cluster reference layout
    const smallNodes = [
      makeNode("p1", "confirmed_member"),
      makeNode("p2", "confirmed_member"),
      makeNode("c1", "work_cluster"),
    ];
    const smallEdges = [makeEdge("p1", "c1", 0), makeEdge("p2", "c1", 1)];
    const smallBase = buildAmeliorateFlowchartElements(smallNodes, smallEdges, null);
    const smallElk = await layoutWithElk(smallBase.nodes, smallBase.edges);
    const np1 = smallElk.nodes.find((n) => n.id === "p1")!;
    const np2 = smallElk.nodes.find((n) => n.id === "p2")!;
    const nc1 = smallElk.nodes.find((n) => n.id === "c1")!;
    expect(np1.position.y).toBe(np2.position.y);
    expect(nc1.position.y).toBeGreaterThan(np1.position.y);
    assertNoNodeOverlaps(smallElk.nodes);

    // 2. 25-node and 55-node graphs via ELK Layered
    for (const count of [25, 55]) {
      const nodes = Array.from({ length: count }, (_, i) =>
        makeNode(`elk${i}`, i === 0 ? "project" : i % 4 === 0 ? "service" : "technology")
      );
      const edges = Array.from({ length: count - 1 }, (_, i) =>
        makeEdge(`elk${Math.floor(i / 3)}`, `elk${i + 1}`, i)
      );
      const base = buildAmeliorateFlowchartElements(nodes, edges, null, {
        viewportWidth: 1366,
        viewportHeight: 768,
      });
      const elkRes = await layoutWithElk(base.nodes, base.edges, {
        viewportWidth: 1366,
        viewportHeight: 768,
      });
      expect(elkRes.nodes).toHaveLength(count);
      assertNoNodeOverlaps(elkRes.nodes);
      const xs = elkRes.nodes.map((n) => n.position.x);
      expect(Math.max(...xs) - Math.min(...xs)).toBeGreaterThan(400);
    }
  });
});
