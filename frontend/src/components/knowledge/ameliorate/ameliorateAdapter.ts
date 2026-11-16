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
  iconSymbol: string;
}

export interface AmeliorateNodeData extends Record<string, unknown> {
  raw: HandoverGraphNode;
  theme: AmeliorateNodeTheme;
  spotlight: AmeliorateSpotlight;
}

export interface AmeliorateEdgeData extends Record<string, unknown> {
  raw: HandoverGraphEdge;
  spotlight: AmeliorateSpotlight;
}

export const AMELIORATE_PRIMARY_SPOTLIGHT = "#4f46e5";
export const AMELIORATE_SECONDARY_SPOTLIGHT = "#0284c7";
export const AMELIORATE_DEFAULT_EDGE_COLOR = "#94a3b8";

// Ameliorate palette accurately mapped to knowledge domains
const ENTITY_THEME_MAP: Record<string, AmeliorateNodeTheme> = {
  project: {
    borderColor: "#a855f7",
    badgeBg: "#f3e8ff",
    badgeText: "#6b21a8",
    typeLabel: "Project",
    iconSymbol: "🧩",
  },
  feature: {
    borderColor: "#22c55e",
    badgeBg: "#dcfce7",
    badgeText: "#15803d",
    typeLabel: "Feature",
    iconSymbol: "🌿",
  },
  requirement: {
    borderColor: "#eab308",
    badgeBg: "#fef9c3",
    badgeText: "#854d0e",
    typeLabel: "Requirement",
    iconSymbol: "⚡",
  },
  operational_procedure: {
    borderColor: "#ec4899",
    badgeBg: "#fce7f3",
    badgeText: "#9d174d",
    typeLabel: "Workflow",
    iconSymbol: "🚨",
  },
  work_item: {
    borderColor: "#0ea5e9",
    badgeBg: "#e0f2fe",
    badgeText: "#0369a1",
    typeLabel: "Work Item",
    iconSymbol: "✓",
  },
  technical_component: {
    borderColor: "#14b8a6",
    badgeBg: "#ccfbf1",
    badgeText: "#0f766e",
    typeLabel: "Component",
    iconSymbol: "✓",
  },
  architecture_component: {
    borderColor: "#0d9488",
    badgeBg: "#ccfbf1",
    badgeText: "#115e59",
    typeLabel: "Architecture",
    iconSymbol: "✓",
  },
  service: {
    borderColor: "#3b82f6",
    badgeBg: "#dbeafe",
    badgeText: "#1d4ed8",
    typeLabel: "Service",
    iconSymbol: "✓",
  },
  api: {
    borderColor: "#6366f1",
    badgeBg: "#e0e7ff",
    badgeText: "#4338ca",
    typeLabel: "API",
    iconSymbol: "⚡",
  },
  technology: {
    borderColor: "#22c55e",
    badgeBg: "#dcfce7",
    badgeText: "#15803d",
    typeLabel: "Technology",
    iconSymbol: "🌿",
  },
  framework: {
    borderColor: "#06b6d4",
    badgeBg: "#cffafe",
    badgeText: "#0e7490",
    typeLabel: "Framework",
    iconSymbol: "⚡",
  },
  library: {
    borderColor: "#10b981",
    badgeBg: "#d1fae5",
    badgeText: "#047857",
    typeLabel: "Library",
    iconSymbol: "🌿",
  },
  database: {
    borderColor: "#eab308",
    badgeBg: "#fef9c3",
    badgeText: "#854d0e",
    typeLabel: "Database",
    iconSymbol: "⚡",
  },
};

const FALLBACK_THEME: AmeliorateNodeTheme = {
  borderColor: "#22c55e",
  badgeBg: "#dcfce7",
  badgeText: "#15803d",
  typeLabel: "Node",
  iconSymbol: "✓",
};

export function resolveAmeliorateNodeTheme(node: HandoverGraphNode): AmeliorateNodeTheme {
  const key = (node.entity_type || node.category || "").toLowerCase();
  if (ENTITY_THEME_MAP[key]) return ENTITY_THEME_MAP[key];
  const readable = (node.entity_type || "Item").replace(/_/g, " ");
  return {
    ...FALLBACK_THEME,
    typeLabel: readable.charAt(0).toUpperCase() + readable.slice(1),
  };
}

const ENTITY_LAYER_RANK: Record<string, number> = {
  project: 0,
  requirement: 0,
  feature: 1,
  architecture_component: 1,
  service: 1,
  api: 1,
  technical_component: 2,
  component: 2,
  operational_procedure: 2,
  work_item: 2,
  technology: 3,
  framework: 3,
  library: 3,
  database: 3,
};

/**
 * Compute Ameliorate-style layered flowchart positions with balanced wrapping
 * so nodes do not stretch infinitely across the screen and cause tiny zoom.
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

  // Dynamic topological leveling so children sit directly below their parents
  const inDegree = new Map<string, number>();
  const childrenMap = new Map<string, string[]>();
  for (const n of rawNodes) {
    inDegree.set(n.id, 0);
    childrenMap.set(n.id, []);
  }
  for (const e of validEdges) {
    inDegree.set(e.target, (inDegree.get(e.target) || 0) + 1);
    childrenMap.get(e.source)?.push(e.target);
  }

  const layerMap = new Map<string, number>();
  const queue: { id: string; depth: number }[] = [];

  // Project entity always occupies root level 0 if present
  const projectNode = rawNodes.find((n) => n.entity_type.toLowerCase() === "project");
  if (projectNode) {
    layerMap.set(projectNode.id, 0);
    queue.push({ id: projectNode.id, depth: 0 });
  }

  // Other in-degree 0 nodes take root level 0
  for (const n of rawNodes) {
    if (n.id === projectNode?.id) continue;
    if ((inDegree.get(n.id) || 0) === 0) {
      layerMap.set(n.id, 0);
      queue.push({ id: n.id, depth: 0 });
    }
  }

  // BFS propagation: child depth = parent depth + 1
  while (queue.length > 0) {
    const { id, depth } = queue.shift()!;
    const children = childrenMap.get(id) || [];
    for (const childId of children) {
      const curDepth = layerMap.get(childId);
      const nextDepth = depth + 1;
      if (curDepth === undefined || curDepth < nextDepth) {
        layerMap.set(childId, nextDepth);
        queue.push({ id: childId, depth: nextDepth });
      }
    }
  }

  // Any remaining disconnected nodes sit on level 1
  for (const n of rawNodes) {
    if (!layerMap.has(n.id)) {
      layerMap.set(n.id, 1);
    }
  }

  const byLayer = new Map<number, HandoverGraphNode[]>();
  for (const n of rawNodes) {
    const rank = layerMap.get(n.id) ?? 0;
    const bucket = byLayer.get(rank) || [];
    bucket.push(n);
    byLayer.set(rank, bucket);
  }

  const sortedLayers = Array.from(byLayer.keys()).sort((a, b) => a - b);
  const NODE_COL_GAP = 240;
  const NODE_ROW_GAP = 140;
  const MAX_COLS_PER_ROW = 4;

  // Flatten layers with row wrapping so wide tiers form balanced sub-rows
  interface LayoutRow {
    items: HandoverGraphNode[];
    y: number;
  }

  const layoutRows: LayoutRow[] = [];
  let currentY = 40;

  sortedLayers.forEach((layerIdx) => {
    const rawItems = [...(byLayer.get(layerIdx) || [])];
    rawItems.sort((a, b) => {
      const aParents = incoming.get(a.id) || [];
      const bParents = incoming.get(b.id) || [];
      if (aParents.length !== bParents.length) return bParents.length - aParents.length;
      return a.label.localeCompare(b.label);
    });

    // Chunk into sub-rows of at most MAX_COLS_PER_ROW
    for (let i = 0; i < rawItems.length; i += MAX_COLS_PER_ROW) {
      const chunk = rawItems.slice(i, i + MAX_COLS_PER_ROW);
      layoutRows.push({ items: chunk, y: currentY });
      currentY += NODE_ROW_GAP;
    }
  });

  const maxRowItems = Math.max(...layoutRows.map((r) => r.items.length), 1);
  const canvasWidth = (maxRowItems - 1) * NODE_COL_GAP;

  const nodes: Node<AmeliorateNodeData>[] = [];
  layoutRows.forEach((row) => {
    const rowWidth = (row.items.length - 1) * NODE_COL_GAP;
    const startX = (canvasWidth - rowWidth) / 2 + 60;

    row.items.forEach((item, colIdx) => {
      const x = startX + colIdx * NODE_COL_GAP;
      const y = row.y;

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

  const edges: Edge<AmeliorateEdgeData>[] = validEdges.map((e) => {
    const spotlight: AmeliorateSpotlight =
      selectedNodeId && (e.source === selectedNodeId || e.target === selectedNodeId)
        ? "primary"
        : "normal";
    const strokeColor =
      spotlight === "primary"
        ? AMELIORATE_PRIMARY_SPOTLIGHT
        : AMELIORATE_DEFAULT_EDGE_COLOR;

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
      },
    };
  });

  return { nodes, edges };
}
