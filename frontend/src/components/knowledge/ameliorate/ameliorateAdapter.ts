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
};

const FALLBACK_THEME: AmeliorateNodeTheme = {
  borderColor: "#22c55e",
  badgeBg: "#16a34a",
  badgeText: "#ffffff",
  typeLabel: "Node",
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

const FUNCTIONAL_LAYER_ORDER: Record<string, number> = {
  project: 0,
  requirement: 0,
  client: 1,
  ui: 1,
  frontend: 1,
  backend: 1,
  api_backend: 1,
  core_services: 1,
  service: 1,
  api: 1,
  feature: 1,
  operational_procedure: 2,
  work_item: 2,
  database: 2,
  storage: 2,
  data_storage: 2,
  ai_ml: 2,
  ai_processing: 2,
  technical_component: 2,
  architecture_component: 2,
  framework: 2,
  library: 2,
  external_integrations: 3,
};

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

  const byLayer = new Map<number, HandoverGraphNode[]>();
  for (const n of rawNodes) {
    const topRank = layerMap.get(n.id);
    const catKey = (n.category || n.entity_type || "").toLowerCase();
    const funcRank = n.entity_type.toLowerCase() === "project" ? 0 : (FUNCTIONAL_LAYER_ORDER[catKey] ?? 1);
    const finalRank = topRank !== undefined && topRank > 0 ? topRank : funcRank;
    const bucket = byLayer.get(finalRank) || [];
    bucket.push(n);
    byLayer.set(finalRank, bucket);
  }

  const sortedLayers = Array.from(byLayer.keys()).sort((a, b) => a - b);
  const NODE_COL_GAP = 230;
  const NODE_ROW_GAP = 140;

  // Maximum items in any layer defines canvas width
  const maxRowItems = Math.max(...Array.from(byLayer.values()).map((items) => items.length), 1);
  const canvasWidth = (maxRowItems - 1) * NODE_COL_GAP;

  const nodes: Node<AmeliorateNodeData>[] = [];
  sortedLayers.forEach((layerIdx, rowIdx) => {
    const rawItems = [...(byLayer.get(layerIdx) || [])];
    rawItems.sort((a, b) => {
      const aParents = incoming.get(a.id) || [];
      const bParents = incoming.get(b.id) || [];
      if (aParents.length !== bParents.length) return bParents.length - aParents.length;
      return a.label.localeCompare(b.label);
    });

    const rowWidth = (rawItems.length - 1) * NODE_COL_GAP;
    const startX = (canvasWidth - rowWidth) / 2 + 60;
    const y = rowIdx * NODE_ROW_GAP + 40;

    rawItems.forEach((item, colIdx) => {
      const x = startX + colIdx * NODE_COL_GAP;
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
