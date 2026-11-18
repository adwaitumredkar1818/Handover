/**
 * Adapted from Ameliorate (https://github.com/amelioro/ameliorate)
 * Original MIT License:
 * Copyright (c) 2022 Joel Keyser
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 * The above copyright notice and this permission notice shall be included in all
 * copies or substantial portions of the Software.
 */

import { MarkerType, type Edge, type Node } from "@xyflow/react";

export type AmeliorateSpotlight = "primary" | "secondary" | "normal";

export interface HandoverGraphNode {
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

export interface HandoverGraphEdge {
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

export interface AmeliorateNodeTheme {
  borderColor: string;
  badgeBg: string;
  badgeText: string;
  typeLabel: string;
}

export interface AmeliorateNodeData extends Record<string, unknown> {
  raw: HandoverGraphNode;
  theme: AmeliorateNodeTheme;
  spotlight: AmeliorateSpotlight;
}

export interface AmeliorateEdgeData extends Record<string, unknown> {
  raw: HandoverGraphEdge;
  spotlight: AmeliorateSpotlight;
  labelX?: number;
  labelY?: number;
  hasCollision?: boolean;
}

export const AMELIORATE_PRIMARY_SPOTLIGHT = "#4f46e5";
export const AMELIORATE_SECONDARY_SPOTLIGHT = "#0284c7";
export const AMELIORATE_DEFAULT_EDGE_COLOR = "#94a3b8";

// Ameliorate palette accurately mapped to knowledge domains (vibrant solid badge headers matching Image 3)
const ENTITY_THEME_MAP: Record<string, AmeliorateNodeTheme> = {
  project: {
    borderColor: "#a855f7",
    badgeBg: "#9333ea",
    badgeText: "#ffffff",
    typeLabel: "Project",
  },
  feature: {
    borderColor: "#22c55e",
    badgeBg: "#16a34a",
    badgeText: "#ffffff",
    typeLabel: "Feature",
  },
  requirement: {
    borderColor: "#eab308",
    badgeBg: "#d97706",
    badgeText: "#ffffff",
    typeLabel: "Requirement",
  },
  operational_procedure: {
    borderColor: "#ec4899",
    badgeBg: "#db2777",
    badgeText: "#ffffff",
    typeLabel: "Workflow",
  },
  work_item: {
    borderColor: "#0ea5e9",
    badgeBg: "#0284c7",
    badgeText: "#ffffff",
    typeLabel: "Work Item",
  },
  technical_component: {
    borderColor: "#14b8a6",
    badgeBg: "#0f766e",
    badgeText: "#ffffff",
    typeLabel: "Component",
  },
  architecture_component: {
    borderColor: "#0d9488",
    badgeBg: "#115e59",
    badgeText: "#ffffff",
    typeLabel: "Architecture",
  },
  service: {
    borderColor: "#3b82f6",
    badgeBg: "#2563eb",
    badgeText: "#ffffff",
    typeLabel: "Service",
  },
  api: {
    borderColor: "#6366f1",
    badgeBg: "#4f46e5",
    badgeText: "#ffffff",
    typeLabel: "API",
  },
  technology: {
    borderColor: "#22c55e",
    badgeBg: "#16a34a",
    badgeText: "#ffffff",
    typeLabel: "Technology",
  },
  framework: {
    borderColor: "#06b6d4",
    badgeBg: "#0891b2",
    badgeText: "#ffffff",
    typeLabel: "Framework",
  },
  library: {
    borderColor: "#10b981",
    badgeBg: "#059669",
    badgeText: "#ffffff",
    typeLabel: "Library",
  },
  database: {
    borderColor: "#eab308",
    badgeBg: "#d97706",
    badgeText: "#ffffff",
    typeLabel: "Database",
  },
  backend: {
    borderColor: "#14b8a6",
    badgeBg: "#0f766e",
    badgeText: "#ffffff",
    typeLabel: "Backend",
  },
  frontend: {
    borderColor: "#06b6d4",
    badgeBg: "#0891b2",
    badgeText: "#ffffff",
    typeLabel: "Frontend",
  },
  ai_ml: {
    borderColor: "#a855f7",
    badgeBg: "#9333ea",
    badgeText: "#ffffff",
    typeLabel: "AI / ML",
  },
  storage: {
    borderColor: "#f97316",
    badgeBg: "#ea580c",
    badgeText: "#ffffff",
    typeLabel: "Storage",
  },
  external_integrations: {
    borderColor: "#6366f1",
    badgeBg: "#4f46e5",
    badgeText: "#ffffff",
    typeLabel: "Integration",
  },
  confirmed_member: {
    borderColor: "#4f46e5",
    badgeBg: "#4338ca",
    badgeText: "#ffffff",
    typeLabel: "Project Member",
  },
  project_member: {
    borderColor: "#4f46e5",
    badgeBg: "#4338ca",
    badgeText: "#ffffff",
    typeLabel: "Project Member",
  },
  work_cluster: {
    borderColor: "#059669",
    badgeBg: "#047857",
    badgeText: "#ffffff",
    typeLabel: "Work Cluster",
  },
  external_contributor: {
    borderColor: "#64748b",
    badgeBg: "#475569",
    badgeText: "#ffffff",
    typeLabel: "External",
  },
  bot: {
    borderColor: "#71717a",
    badgeBg: "#52525b",
    badgeText: "#ffffff",
    typeLabel: "Bot",
  },
  contributor: {
    borderColor: "#f59e0b",
    badgeBg: "#d97706",
    badgeText: "#ffffff",
    typeLabel: "Contributor",
  },
  person: {
    borderColor: "#4f46e5",
    badgeBg: "#4338ca",
    badgeText: "#ffffff",
    typeLabel: "Contributor",
  },
  decision: {
    borderColor: "#d97706",
    badgeBg: "#b45309",
    badgeText: "#ffffff",
    typeLabel: "Decision",
  },
  commit: {
    borderColor: "#6366f1",
    badgeBg: "#4f46e5",
    badgeText: "#ffffff",
    typeLabel: "Commit",
  },
  pull_request: {
    borderColor: "#8b5cf6",
    badgeBg: "#7c3aed",
    badgeText: "#ffffff",
    typeLabel: "Pull Request",
  },
  issue: {
    borderColor: "#0ea5e9",
    badgeBg: "#0284c7",
    badgeText: "#ffffff",
    typeLabel: "Issue",
  },
};

const FALLBACK_THEME: AmeliorateNodeTheme = {
  borderColor: "#22c55e",
  badgeBg: "#16a34a",
  badgeText: "#ffffff",
  typeLabel: "Node",
};

export function resolveAmeliorateNodeTheme(node: HandoverGraphNode): AmeliorateNodeTheme {
  const canon = (node.label || "").toLowerCase();
  const type = (node.entity_type || "").toLowerCase();
  const cat = (node.category || "").toLowerCase();

  if (node.metadata?.customTypeLabel && (ENTITY_THEME_MAP[type] || ENTITY_THEME_MAP[cat])) {
    const baseTheme = ENTITY_THEME_MAP[type] ?? ENTITY_THEME_MAP[cat] ?? FALLBACK_THEME;
    return {
      ...baseTheme,
      typeLabel: String(node.metadata.customTypeLabel),
    };
  }

  if (type === "confirmed_member" || cat === "confirmed_member" || type === "project_member") return ENTITY_THEME_MAP["confirmed_member"]!;
  if (type === "work_cluster" || cat === "work_cluster") return ENTITY_THEME_MAP["work_cluster"]!;
  if (type === "external_contributor" || cat === "external_contributor") return ENTITY_THEME_MAP["external_contributor"]!;
  if (type === "bot" || cat === "bot") return ENTITY_THEME_MAP["bot"]!;
  if (type === "contributor" || cat === "unidentified") return ENTITY_THEME_MAP["contributor"]!;
  if (type === "decision" || cat === "decision") return ENTITY_THEME_MAP["decision"]!;
  if (type === "commit" || cat === "commit") return ENTITY_THEME_MAP["commit"]!;
  if (type === "pull_request" || cat === "pull_request") return ENTITY_THEME_MAP["pull_request"]!;
  if (type === "issue" || cat === "issue") return ENTITY_THEME_MAP["issue"]!;

  if (type === "project" || canon === "skillspassport") return ENTITY_THEME_MAP["project"] ?? FALLBACK_THEME;
  if (canon.includes("next") || canon.includes("react") || cat === "frontend") return ENTITY_THEME_MAP["frontend"] ?? FALLBACK_THEME;
  if (canon.includes("fastapi") || cat === "backend") return ENTITY_THEME_MAP["backend"] ?? FALLBACK_THEME;
  if (canon.includes("postgres") || canon.includes("sqlalchemy") || cat === "database") return ENTITY_THEME_MAP["database"] ?? FALLBACK_THEME;
  if (canon.includes("supabase") || canon.includes("storage") || cat === "storage") return ENTITY_THEME_MAP["storage"] ?? FALLBACK_THEME;
  if (canon.includes("ollama") || canon.includes("qwen") || canon.includes("chroma") || cat === "ai_ml") return ENTITY_THEME_MAP["ai_ml"] ?? FALLBACK_THEME;
  if (canon.includes("github") || canon.includes("jira") || cat === "external_integrations") return ENTITY_THEME_MAP["external_integrations"] ?? FALLBACK_THEME;
  if (ENTITY_THEME_MAP[cat]) return ENTITY_THEME_MAP[cat]!;
  if (ENTITY_THEME_MAP[type]) return ENTITY_THEME_MAP[type]!;
  const readable = (node.entity_type || "Item").replace(/_/g, " ");
  return {
    ...FALLBACK_THEME,
    typeLabel: readable.charAt(0).toUpperCase() + readable.slice(1),
  };
}

export function resolveNodeTier(node: HandoverGraphNode): number {
  const canon = (node.label || "").toLowerCase();
  const type = (node.entity_type || "").toLowerCase();
  const cat = (node.category || "").toLowerCase();

  // Tier 0: Project root / System client entry / Confirmed Project Members
  if (type === "project" || canon === "skillspassport") return 0;
  if (canon === "browser" || canon.includes("web client")) return 0;
  if (type === "confirmed_member" || cat === "confirmed_member" || type === "project_member") return 0;

  // Tier 1: External / Unmapped Contributors / Decision
  if (type === "contributor" || type === "external_contributor" || type === "bot" || cat === "unidentified" || type === "person") return 1;

  // Tier 2: Work Clusters / Technical Components
  if (type === "work_cluster" || cat === "work_cluster") return 2;

  // Features & Workflows semantics: Product -> Features -> Workflow Steps -> Outcomes/Requirements
  if (type === "feature") return 1;
  if (type === "operational_procedure" || cat === "workflow_step") return 2;
  if (type === "requirement" || type === "work_item") return 3;

  // Tier 1: Frontend framework / UI library / API Gateway routes
  if (canon.includes("next") || canon.includes("react") || canon.includes("routes") || cat === "frontend") return 1;

  // Tier 2: Backend application server / Core service / Workers
  if (canon.includes("fastapi") || canon.includes("worker") || canon.includes("service") || canon.includes("competency") || cat === "backend" || cat === "core_services") return 2;

  // Tier 3: Database & Object Storage
  if (canon.includes("postgres") || canon.includes("sqlalchemy") || canon.includes("supabase") || canon.includes("storage") || cat === "database" || cat === "storage") return 3;

  // Tier 4: AI Inference Runtime & Vector Store
  if (canon.includes("ollama") || canon.includes("qwen") || canon.includes("chroma") || cat === "ai_ml") return 4;

  // Tier 5: External Data Sources & Integrations / Artefacts
  if (canon.includes("github") || canon.includes("jira") || canon.includes("slack") || cat === "external_integrations") return 5;
  if (type === "commit" || type === "pull_request" || type === "issue") return 3;

  return 2;
}

/**
 * Compute Ameliorate-style layered flowchart positions with balanced centered tiers
 * so nodes form a clean hierarchical flowchart exactly like Image 3 with zero node crossings.
 */
export function buildAmeliorateFlowchartElements(
  rawNodes: HandoverGraphNode[],
  rawEdges: HandoverGraphEdge[],
  selectedNodeId: string | null
): {
  nodes: Node<AmeliorateNodeData>[];
  edges: Edge<AmeliorateEdgeData>[];
} {
  if (rawNodes.length === 0) {
    return { nodes: [], edges: [] };
  }

  const visibleIds = new Set(rawNodes.map((n) => n.id));
  const validEdges = rawEdges.filter((e) => visibleIds.has(e.source) && visibleIds.has(e.target));

  const incoming = new Map<string, string[]>();
  const neighborSet = new Set<string>();

  for (const n of rawNodes) {
    incoming.set(n.id, []);
  }
  for (const e of validEdges) {
    incoming.get(e.target)?.push(e.source);
    if (selectedNodeId) {
      if (e.source === selectedNodeId) neighborSet.add(e.target);
      if (e.target === selectedNodeId) neighborSet.add(e.source);
    }
  }

  // Group nodes into balanced architectural tiers
  const byTier = new Map<number, HandoverGraphNode[]>();
  for (const n of rawNodes) {
    const tier = resolveNodeTier(n);
    const bucket = byTier.get(tier) || [];
    bucket.push(n);
    byTier.set(tier, bucket);
  }

  // Multi-row visual grid (wrap tiers with >3 items into centered sub-rows)
  const visualRows: HandoverGraphNode[][] = [];
  const sortedTiers = Array.from(byTier.keys()).sort((a, b) => a - b);

  for (const t of sortedTiers) {
    const items = [...(byTier.get(t) || [])];
    items.sort((a, b) => a.label.localeCompare(b.label));

    // Wrap tier into sub-rows of at most 3 items
    const MAX_ITEMS_PER_ROW = 3;
    for (let i = 0; i < items.length; i += MAX_ITEMS_PER_ROW) {
      visualRows.push(items.slice(i, i + MAX_ITEMS_PER_ROW));
    }
  }

  const NODE_COL_GAP = 330;
  const NODE_ROW_GAP = 280;

  // Standard max width: 3 nodes
  const maxRowItems = Math.min(Math.max(...visualRows.map((r) => r.length), 1), 3);
  const canvasWidth = (maxRowItems - 1) * NODE_COL_GAP;

  const nodePosMap = new Map<string, { x: number; y: number }>();
  const nodes: Node<AmeliorateNodeData>[] = [];

  visualRows.forEach((rowItems, rowIdx) => {
    // Sort items by their parent's average X position to minimize line crossings
    rowItems.sort((a, b) => {
      const aParents = incoming.get(a.id) || [];
      const bParents = incoming.get(b.id) || [];
      const aAvgX =
        aParents.length > 0
          ? aParents.reduce((acc, pid) => acc + (nodePosMap.get(pid)?.x ?? canvasWidth / 2), 0) / aParents.length
          : canvasWidth / 2;
      const bAvgX =
        bParents.length > 0
          ? bParents.reduce((acc, pid) => acc + (nodePosMap.get(pid)?.x ?? canvasWidth / 2), 0) / bParents.length
          : canvasWidth / 2;
      return aAvgX - bAvgX;
    });

    const rowWidth = (rowItems.length - 1) * NODE_COL_GAP;
    const startX = (canvasWidth - rowWidth) / 2 + 50;
    const y = rowIdx * NODE_ROW_GAP + 40;

    rowItems.forEach((item, colIdx) => {
      const x = startX + colIdx * NODE_COL_GAP;
      nodePosMap.set(item.id, { x, y });

      const spotlight: AmeliorateSpotlight =
        selectedNodeId === item.id
          ? "primary"
          : selectedNodeId && neighborSet.has(item.id)
            ? "secondary"
            : "normal";

      nodes.push({
        id: item.id,
        type: "ameliorateNode",
        position: { x, y },
        selected: selectedNodeId === item.id,
        data: {
          raw: item,
          theme: resolveAmeliorateNodeTheme(item),
          spotlight,
        },
      });
    });
  });

  // Node card bounding boxes for collision checking (card is 196w x ~96h, give 28px safety halo)
  const NODE_W = 196;
  const NODE_H = 96;
  const nodeBoxes: Array<{ xmin: number; xmax: number; ymin: number; ymax: number }> = [];
  nodePosMap.forEach(({ x, y }) => {
    nodeBoxes.push({
      xmin: x - 28,
      xmax: x + NODE_W + 28,
      ymin: y - 28,
      ymax: y + NODE_H + 28,
    });
  });

  // Consolidate parallel edges between the same node pair regardless of direction to avoid duplicate lines and overlapping labels
  const edgePairMap = new Map<string, HandoverGraphEdge[]>();
  for (const e of validEdges) {
    const key = [e.source, e.target].sort().join("<->");
    const list = edgePairMap.get(key) || [];
    list.push(e);
    edgePairMap.set(key, list);
  }

  const consolidatedEdges: HandoverGraphEdge[] = [];
  for (const [, pairList] of edgePairMap) {
    if (!pairList || pairList.length === 0) continue;
    const primary = pairList[0];
    if (!primary) continue;
    if (pairList.length === 1) {
      consolidatedEdges.push(primary);
    } else {
      // Merge multi-edges between the same pair into a single edge with distinct labels
      const distinctLabels = Array.from(new Set(pairList.map((e) => e.label).filter(Boolean)));
      const combinedLabel = distinctLabels.join(" · ");
      const combinedEvidenceIds = Array.from(new Set(pairList.flatMap((e) => e.evidence_ids || [])));
      consolidatedEdges.push({
        id: pairList.map((e) => e.id).join("__"),
        source: primary.source,
        target: primary.target,
        relationship_type: primary.relationship_type,
        label: combinedLabel,
        evidence_basis: primary.evidence_basis,
        verification_status: primary.verification_status,
        confidence_score: primary.confidence_score,
        evidence_ids: combinedEvidenceIds,
      });
    }
  }

  const placedLabels: Array<{ x: number; y: number; w: number; h: number }> = [];

  const edges: Edge<AmeliorateEdgeData>[] = consolidatedEdges.map((e) => {
    const spotlight: AmeliorateSpotlight =
      selectedNodeId && (e.source === selectedNodeId || e.target === selectedNodeId)
        ? "primary"
        : "normal";
    const strokeColor =
      spotlight === "primary"
        ? AMELIORATE_PRIMARY_SPOTLIGHT
        : AMELIORATE_DEFAULT_EDGE_COLOR;

    let customLabelX: number | undefined;
    let customLabelY: number | undefined;
    let hasCollision = false;

    const sPos = nodePosMap.get(e.source);
    const tPos = nodePosMap.get(e.target);

    if (e.label && sPos && tPos) {
      const sx = sPos.x + NODE_W / 2;
      const sy = sPos.y + NODE_H;
      const tx = tPos.x + NODE_W / 2;
      const ty = tPos.y;
      const dy = ty - sy;

      const p0: [number, number] = [sx, sy];
      const c = Math.max(35, Math.abs(dy) * 0.45);
      const p1: [number, number] = [sx, sy + c];
      const p2: [number, number] = [tx, ty - c];
      const p3: [number, number] = [tx, ty];

      const lblW = Math.max(54, e.label.length * 6.5 + 20);
      const lblH = 22;

      // Conservative candidate positions strictly along the bezier curve
      const candidateTs = [0.50, 0.40, 0.60];
      let chosenX: number | null = null;
      let chosenY: number | null = null;

      for (const t of candidateTs) {
        const mt = 1 - t;
        const bx = mt * mt * mt * p0[0] + 3 * mt * mt * t * p1[0] + 3 * mt * t * t * p2[0] + t * t * t * p3[0];
        const by = mt * mt * mt * p0[1] + 3 * mt * mt * t * p1[1] + 3 * mt * t * t * p2[1] + t * t * t * p3[1];
        const cx = bx;
        const cy = by;

        // Strict zero-node-collision guarantee: label must not overlap any node card or its safety halo
        const collidesWithNode = nodeBoxes.some(
          (b) =>
            cx + lblW / 2 > b.xmin &&
            cx - lblW / 2 < b.xmax &&
            cy + lblH / 2 > b.ymin &&
            cy - lblH / 2 < b.ymax
        );
        if (collidesWithNode) continue;

        // Strict zero-label-collision guarantee: label must not overlap any already-placed label
        const collidesWithLabel = placedLabels.some((pl) => {
          const xDist = Math.abs(cx - pl.x);
          const yDist = Math.abs(cy - pl.y);
          const minXDist = (lblW + pl.w) / 2 + 20;
          const minYDist = (lblH + pl.h) / 2 + 14;
          return xDist < minXDist && yDist < minYDist;
        });
        if (collidesWithLabel) continue;

        chosenX = cx;
        chosenY = cy;
        break;
      }

      if (chosenX !== null && chosenY !== null) {
        placedLabels.push({ x: chosenX, y: chosenY, w: lblW, h: lblH });
        customLabelX = Math.round(chosenX);
        customLabelY = Math.round(chosenY);
        hasCollision = false;
      } else {
        // In crowded channels where space is contested, mark hasCollision so the label stays clean & hidden until hover/select
        customLabelX = Math.round((sx + tx) / 2);
        customLabelY = Math.round((sy + ty) / 2);
        hasCollision = true;
      }
    }

    return {
      id: e.id,
      type: "ameliorateEdge",
      source: e.source,
      target: e.target,
      sourceHandle: "bottom",
      targetHandle: "top",
      label: e.label,
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: strokeColor,
        width: 14,
        height: 14,
      },
      data: {
        raw: e,
        spotlight,
        labelX: customLabelX,
        labelY: customLabelY,
        hasCollision,
      },
    };
  });

  return { nodes, edges };
}

export function updateAmeliorateSpotlight(
  nodes: Node<AmeliorateNodeData>[],
  edges: Edge<AmeliorateEdgeData>[],
  selectedNodeId: string | null
): { nodes: Node<AmeliorateNodeData>[]; edges: Edge<AmeliorateEdgeData>[] } {
  const neighborSet = new Set<string>();
  if (selectedNodeId) {
    for (const e of edges) {
      if (e.source === selectedNodeId) neighborSet.add(e.target);
      if (e.target === selectedNodeId) neighborSet.add(e.source);
    }
  }

  const updatedNodes = nodes.map((n) => {
    const isSelected = selectedNodeId === n.id;
    const spotlight: AmeliorateSpotlight =
      isSelected
        ? "primary"
        : selectedNodeId && neighborSet.has(n.id)
        ? "secondary"
        : "normal";
    if (n.selected === isSelected && n.data.spotlight === spotlight) {
      return n;
    }
    return {
      ...n,
      selected: isSelected,
      data: {
        ...n.data,
        spotlight,
      },
    };
  });

  const updatedEdges: Edge<AmeliorateEdgeData>[] = edges.map((e) => {
    const spotlight: AmeliorateSpotlight =
      selectedNodeId && (e.source === selectedNodeId || e.target === selectedNodeId)
        ? "primary"
        : "normal";
    const strokeColor =
      spotlight === "primary"
        ? AMELIORATE_PRIMARY_SPOTLIGHT
        : AMELIORATE_DEFAULT_EDGE_COLOR;
    const markerEndObj = typeof e.markerEnd === "object" && e.markerEnd !== null ? e.markerEnd : null;
    const currentColor = markerEndObj && "color" in markerEndObj ? (markerEndObj as { color?: string }).color : undefined;
    if (e.data?.spotlight === spotlight && currentColor === strokeColor) {
      return e;
    }
    const edgeData = e.data;
    if (!edgeData) {
      return e;
    }
    const updatedEdge: Edge<AmeliorateEdgeData> = {
      ...e,
      markerEnd: {
        ...(markerEndObj || {}),
        type: MarkerType.ArrowClosed,
        color: strokeColor,
        width: 14,
        height: 14,
      },
      data: {
        raw: edgeData.raw,
        spotlight,
        labelX: edgeData.labelX,
        labelY: edgeData.labelY,
        hasCollision: edgeData.hasCollision,
      },
    };
    return updatedEdge;
  });

  return { nodes: updatedNodes, edges: updatedEdges };
}
