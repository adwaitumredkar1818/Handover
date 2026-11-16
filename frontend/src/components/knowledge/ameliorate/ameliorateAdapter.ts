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
  typeLabel: string;
  iconKey:
    | "project"
    | "feature"
    | "requirement"
    | "workflow"
    | "component"
    | "technology"
    | "database"
    | "document"
    | "work_item"
    | "pull_request"
    | "commit"
    | "default";
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

export const AMELIORATE_PRIMARY_SPOTLIGHT = "#315fba";
export const AMELIORATE_SECONDARY_SPOTLIGHT = "#0284c7";
export const AMELIORATE_DEFAULT_EDGE_COLOR = "#b1b1b7";

const ENTITY_THEME_MAP: Record<string, AmeliorateNodeTheme> = {
  project: {
    borderColor: "#315fba",
    badgeBg: "#bfdbfe",
    typeLabel: "Project",
    iconKey: "project",
  },
  feature: {
    borderColor: "#2563eb",
    badgeBg: "#bfdbfe",
    typeLabel: "Feature",
    iconKey: "feature",
  },
  requirement: {
    borderColor: "#eab308",
    badgeBg: "#fef08a",
    typeLabel: "Requirement",
    iconKey: "requirement",
  },
  operational_procedure: {
    borderColor: "#22c55e",
    badgeBg: "#bbf7d0",
    typeLabel: "Workflow",
    iconKey: "workflow",
  },
  work_item: {
    borderColor: "#0ea5e9",
    badgeBg: "#bae6fd",
    typeLabel: "Work Item",
    iconKey: "work_item",
  },
  technical_component: {
    borderColor: "#14b8a6",
    badgeBg: "#99f6e4",
    typeLabel: "Component",
    iconKey: "component",
  },
  architecture_component: {
    borderColor: "#0d9488",
    badgeBg: "#99f6e4",
    typeLabel: "Architecture",
    iconKey: "component",
  },
  service: {
    borderColor: "#0284c7",
    badgeBg: "#bae6fd",
    typeLabel: "Service",
    iconKey: "component",
  },
  api: {
    borderColor: "#06b6d4",
    badgeBg: "#a5f3fc",
    typeLabel: "API",
    iconKey: "component",
  },
  technology: {
    borderColor: "#16a34a",
    badgeBg: "#bbf7d0",
    typeLabel: "Technology",
    iconKey: "technology",
  },
  framework: {
    borderColor: "#0891b2",
    badgeBg: "#a5f3fc",
    typeLabel: "Framework",
    iconKey: "technology",
  },
  library: {
    borderColor: "#22c55e",
    badgeBg: "#bbf7d0",
    typeLabel: "Library",
    iconKey: "technology",
  },
  database: {
    borderColor: "#f59e0b",
    badgeBg: "#fde68a",
    typeLabel: "Database",
    iconKey: "database",
  },
  document: {
    borderColor: "#64748b",
    badgeBg: "#e2e8f0",
    typeLabel: "Document",
    iconKey: "document",
  },
  pull_request: {
    borderColor: "#3b82f6",
    badgeBg: "#bfdbfe",
    typeLabel: "Pull Request",
    iconKey: "pull_request",
  },
  commit: {
    borderColor: "#64748b",
    badgeBg: "#e2e8f0",
    typeLabel: "Commit",
    iconKey: "commit",
  },
};

const FALLBACK_THEME: AmeliorateNodeTheme = {
  borderColor: "#315fba",
  badgeBg: "#bfdbfe",
  typeLabel: "Node",
  iconKey: "default",
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
  pull_request: 3,
  document: 4,
  commit: 4,
};

/**
 * Compute Ameliorate-style layered flowchart positions and spotlight states
 * from The Handover's existing Knowledge Intelligence graph payload.
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

  const layerMap = new Map<string, number>();
  for (const n of rawNodes) {
    layerMap.set(n.id, ENTITY_LAYER_RANK[n.entity_type.toLowerCase()] ?? 2);
  }

  // Relax ranks along edges up to 4 passes so connected targets sit below sources
  for (let pass = 0; pass < 4; pass++) {
    let changed = false;
    for (const e of validEdges) {
      const srcRank = layerMap.get(e.source) ?? 0;
      const dstRank = layerMap.get(e.target) ?? 0;
      if (dstRank <= srcRank && srcRank < 6) {
        layerMap.set(e.target, srcRank + 1);
        changed = true;
      }
    }
    if (!changed) break;
  }

  const byLayer = new Map<number, HandoverGraphNode[]>();
  for (const n of rawNodes) {
    const rank = layerMap.get(n.id) ?? 0;
    const bucket = byLayer.get(rank) || [];
    bucket.push(n);
    byLayer.set(rank, bucket);
  }

  const sortedLayers = Array.from(byLayer.keys()).sort((a, b) => a - b);
  const NODE_COL_GAP = 228;
  const NODE_ROW_GAP = 148;
  const xPosById = new Map<string, number>();
  const maxCols = Math.max(...sortedLayers.map((l) => (byLayer.get(l) || []).length), 1);
  const canvasCenterWidth = (maxCols - 1) * NODE_COL_GAP;

  const nodes: Node<AmeliorateNodeData>[] = [];
  sortedLayers.forEach((layerIdx, rowIdx) => {
    const items = [...(byLayer.get(layerIdx) || [])];
    items.sort((a, b) => {
      const aParents = incoming.get(a.id) || [];
      const bParents = incoming.get(b.id) || [];
      const aAvg =
        aParents.length > 0
          ? aParents.reduce((sum, p) => sum + (xPosById.get(p) ?? 0), 0) / aParents.length
          : 0;
      const bAvg =
        bParents.length > 0
          ? bParents.reduce((sum, p) => sum + (xPosById.get(p) ?? 0), 0) / bParents.length
          : 0;
      if (aAvg !== bAvg) return aAvg - bAvg;
      return a.label.localeCompare(b.label);
    });

    const rowWidth = (items.length - 1) * NODE_COL_GAP;
    const startX = (canvasCenterWidth - rowWidth) / 2 + 40;
    items.forEach((item, colIdx) => {
      const x = startX + colIdx * NODE_COL_GAP;
      const y = rowIdx * NODE_ROW_GAP + 40;
      xPosById.set(item.id, x);

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
      label: e.label,
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: strokeColor,
        width: 15,
        height: 15,
      },
      data: {
        raw: e,
        spotlight,
      },
    };
  });

  return { nodes, edges };
}
