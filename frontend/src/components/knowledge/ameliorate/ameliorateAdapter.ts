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
  const canon = (node.label || "").toLowerCase();
  const type = (node.entity_type || "").toLowerCase();
  const cat = (node.category || "").toLowerCase();

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

  // Tier 0: Project root / System client entry
  if (type === "project" || canon === "skillspassport") return 0;
  if (canon === "browser" || canon.includes("web client")) return 0;

  // Tier 1: Frontend framework / UI library / API Gateway routes
  if (canon.includes("next") || canon.includes("react") || canon.includes("routes") || cat === "frontend") return 1;

  // Tier 2: Backend application server / Core service / Workers
  if (canon.includes("fastapi") || canon.includes("worker") || canon.includes("service") || canon.includes("competency") || cat === "backend" || cat === "core_services") return 2;

  // Tier 3: Database & Object Storage
  if (canon.includes("postgres") || canon.includes("sqlalchemy") || canon.includes("supabase") || canon.includes("storage") || cat === "database" || cat === "storage") return 3;

  // Tier 4: AI Inference Runtime & Vector Store
  if (canon.includes("ollama") || canon.includes("qwen") || canon.includes("chroma") || cat === "ai_ml") return 4;

  // Tier 5: External Data Sources & Integrations
  if (canon.includes("github") || canon.includes("jira") || canon.includes("slack") || cat === "external_integrations") return 5;

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

  const NODE_COL_GAP = 220;
  const NODE_ROW_GAP = 135;

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
