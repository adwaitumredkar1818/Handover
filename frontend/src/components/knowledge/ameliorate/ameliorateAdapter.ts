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
import ELK from "elkjs/lib/elk.bundled.js";

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

  if (type === "project") return ENTITY_THEME_MAP["project"] ?? FALLBACK_THEME;
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
  if (type === "project") return 0;
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

export interface AdaptiveLayoutOptions {
  viewportWidth?: number;
  viewportHeight?: number;
  nodeDimensions?: Map<string, { width: number; height: number }>;
}

interface NodeBox {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

const DEFAULT_NODE_W = 204;
const DEFAULT_NODE_H = 116;
const MIN_NODE_GAP_X = 64;
const MIN_NODE_GAP_Y = 64;

function getNodeSize(
  id: string,
  dims?: Map<string, { width: number; height: number }>
): { w: number; h: number } {
  const m = dims?.get(id);
  return {
    w: m && m.width > 40 ? m.width : DEFAULT_NODE_W,
    h: m && m.height > 40 ? m.height : DEFAULT_NODE_H,
  };
}

/**
 * Deterministic AABB overlap resolution pass. Ensures no two node cards ever overlap
 * while preserving relative layout order and balanced spacing.
 */
function resolveOverlaps(
  positions: Map<string, { x: number; y: number }>,
  ids: string[],
  dims?: Map<string, { width: number; height: number }>,
  padding = 40
): void {
  const sortedIds = [...ids].sort();
  const boxes: NodeBox[] = sortedIds.map((id) => {
    const pos = positions.get(id) ?? { x: 0, y: 0 };
    const { w, h } = getNodeSize(id, dims);
    return { id, x: pos.x, y: pos.y, w, h };
  });

  for (let iter = 0; iter < 80; iter++) {
    let moved = false;
    for (let i = 0; i < boxes.length; i++) {
      const a = boxes[i]!;
      for (let j = i + 1; j < boxes.length; j++) {
        const b = boxes[j]!;
        const axCenter = a.x + a.w / 2;
        const ayCenter = a.y + a.h / 2;
        const bxCenter = b.x + b.w / 2;
        const byCenter = b.y + b.h / 2;

        const reqDx = (a.w + b.w) / 2 + padding;
        const reqDy = (a.h + b.h) / 2 + padding;
        const dx = bxCenter - axCenter;
        const dy = byCenter - ayCenter;

        if (Math.abs(dx) < reqDx && Math.abs(dy) < reqDy) {
          moved = true;
          const overlapX = reqDx - Math.abs(dx);
          const overlapY = reqDy - Math.abs(dy);

          // Push apart along the axis with smaller penetration (deterministic tie-break)
          if (overlapX <= overlapY) {
            const sign = dx === 0 ? (i % 2 === 0 ? -1 : 1) : Math.sign(dx);
            const shift = overlapX / 2 + 2;
            a.x -= sign * shift;
            b.x += sign * shift;
          } else {
            const sign = dy === 0 ? (i % 2 === 0 ? -1 : 1) : Math.sign(dy);
            const shift = overlapY / 2 + 2;
            a.y -= sign * shift;
            b.y += sign * shift;
          }
        }
      }
    }
    if (!moved) break;
  }

  for (const box of boxes) {
    positions.set(box.id, { x: Math.round(box.x), y: Math.round(box.y) });
  }
}

/**
 * Partition graph into connected components (sorted largest-first, deterministic by ID).
 */
function findConnectedComponents(
  nodes: HandoverGraphNode[],
  edges: HandoverGraphEdge[]
): HandoverGraphNode[][] {
  const nodeMap = new Map(nodes.map((n) => [n.id, n]));
  const adj = new Map<string, Set<string>>();
  for (const n of nodes) adj.set(n.id, new Set());
  for (const e of edges) {
    if (nodeMap.has(e.source) && nodeMap.has(e.target)) {
      adj.get(e.source)!.add(e.target);
      adj.get(e.target)!.add(e.source);
    }
  }

  const visited = new Set<string>();
  const components: HandoverGraphNode[][] = [];
  const sortedNodes = [...nodes].sort((a, b) => a.id.localeCompare(b.id));

  for (const start of sortedNodes) {
    if (visited.has(start.id)) continue;
    const comp: HandoverGraphNode[] = [];
    const queue = [start.id];
    visited.add(start.id);
    while (queue.length > 0) {
      const curr = queue.shift()!;
      const node = nodeMap.get(curr);
      if (node) comp.push(node);
      const neighbors = Array.from(adj.get(curr) || []).sort();
      for (const nxt of neighbors) {
        if (!visited.has(nxt)) {
          visited.add(nxt);
          queue.push(nxt);
        }
      }
    }
    components.push(comp);
  }

  components.sort((a, b) => b.length - a.length || a[0]!.id.localeCompare(b[0]!.id));
  return components;
}

/**
 * Lay out a single connected component using clean top-to-bottom layered arrangement.
 */
function layoutComponent(
  compNodes: HandoverGraphNode[],
  compEdges: HandoverGraphEdge[],
  aspectRatio: number,
  dims?: Map<string, { width: number; height: number }>
): Map<string, { x: number; y: number }> {
  const pos = new Map<string, { x: number; y: number }>();
  const n = compNodes.length;
  if (n === 0) return pos;

  const colStep = DEFAULT_NODE_W + MIN_NODE_GAP_X + 22; // ~290px
  const rowStep = DEFAULT_NODE_H + MIN_NODE_GAP_Y + 25; // ~205px

  // Build adjacency & degrees
  const inDeg = new Map<string, number>();
  const outDeg = new Map<string, number>();
  const incoming = new Map<string, string[]>();
  const outgoing = new Map<string, string[]>();
  for (const node of compNodes) {
    inDeg.set(node.id, 0);
    outDeg.set(node.id, 0);
    incoming.set(node.id, []);
    outgoing.set(node.id, []);
  }
  for (const e of compEdges) {
    if (e.source === e.target) continue;
    outgoing.get(e.source)?.push(e.target);
    incoming.get(e.target)?.push(e.source);
    outDeg.set(e.source, (outDeg.get(e.source) || 0) + 1);
    inDeg.set(e.target, (inDeg.get(e.target) || 0) + 1);
  }

  const totalDeg = (id: string) => (inDeg.get(id) || 0) + (outDeg.get(id) || 0);
  const sortedByDeg = [...compNodes].sort(
    (a, b) => totalDeg(b.id) - totalDeg(a.id) || a.label.localeCompare(b.label)
  );
  const maxDeg = totalDeg(sortedByDeg[0]!.id);
  const edgeDensity = compEdges.length / Math.max(1, n);

  // 1. SMALL GRAPHS (n <= 4): Compact centered layout
  if (n <= 4) {
    if (n === 1) {
      pos.set(compNodes[0]!.id, { x: 0, y: 0 });
      return pos;
    }
    if (n === 2) {
      const ordered = [...compNodes].sort((a, b) => resolveNodeTier(a) - resolveNodeTier(b) || a.label.localeCompare(b.label));
      if (aspectRatio >= 1.25 && resolveNodeTier(ordered[0]!) === resolveNodeTier(ordered[1]!)) {
        pos.set(ordered[0]!.id, { x: 0, y: 0 });
        pos.set(ordered[1]!.id, { x: colStep, y: 0 });
      } else {
        pos.set(ordered[0]!.id, { x: 0, y: 0 });
        pos.set(ordered[1]!.id, { x: 0, y: rowStep * 0.9 });
      }
      return pos;
    }
    // 3 or 4 nodes: respect directed top-to-bottom flow (sources / lower tier on top, targets below)
    const sources = compNodes.filter((x) => (inDeg.get(x.id) || 0) === 0);
    if (sources.length >= 2 && sources.length < compNodes.length) {
      const topRow = [...sources].sort((a, b) => a.label.localeCompare(b.label));
      const bottomRow = compNodes
        .filter((x) => (inDeg.get(x.id) || 0) > 0)
        .sort((a, b) => a.label.localeCompare(b.label));
      const maxRow = Math.max(topRow.length, bottomRow.length);
      const totalW = (maxRow - 1) * colStep;
      const topStart = (totalW - (topRow.length - 1) * colStep) / 2;
      const botStart = (totalW - (bottomRow.length - 1) * colStep) / 2;
      topRow.forEach((item, idx) => pos.set(item.id, { x: topStart + idx * colStep, y: 0 }));
      bottomRow.forEach((item, idx) => pos.set(item.id, { x: botStart + idx * colStep, y: rowStep }));
    } else {
      const root = sources[0] ?? sortedByDeg[0]!;
      const rest = compNodes.filter((x) => x.id !== root.id).sort((a, b) => a.label.localeCompare(b.label));
      const topWidth = (rest.length - 1) * colStep;
      pos.set(root.id, { x: topWidth / 2, y: 0 });
      rest.forEach((item, idx) => {
        pos.set(item.id, { x: idx * colStep, y: rowStep });
      });
    }
    resolveOverlaps(pos, compNodes.map((x) => x.id), dims);
    return pos;
  }

  // 2. HUB-AND-SPOKE GRAPHS (one dominant central node connected to >= 4 leaves, low cross-links)
  const isHubAndSpoke =
    maxDeg >= Math.max(4, Math.floor(n * 0.55)) &&
    edgeDensity <= 1.45 &&
    n <= 32;

  if (isHubAndSpoke) {
    const hub = sortedByDeg[0]!;
    const spokes = compNodes
      .filter((x) => x.id !== hub.id)
      .sort((a, b) => totalDeg(b.id) - totalDeg(a.id) || a.label.localeCompare(b.label));

    const maxCols = Math.max(2, Math.min(5, Math.ceil(Math.sqrt(spokes.length * Math.max(0.8, aspectRatio)))));
    const rows: HandoverGraphNode[][] = [];
    for (let i = 0; i < spokes.length; i += maxCols) {
      rows.push(spokes.slice(i, i + maxCols));
    }

    const maxRowWidth = (Math.min(spokes.length, maxCols) - 1) * colStep;
    pos.set(hub.id, { x: maxRowWidth / 2, y: 0 });

    rows.forEach((rowItems, rIdx) => {
      const rw = (rowItems.length - 1) * colStep;
      const startX = (maxRowWidth - rw) / 2;
      rowItems.forEach((item, cIdx) => {
        pos.set(item.id, { x: startX + cIdx * colStep, y: (rIdx + 1) * rowStep });
      });
    });

    resolveOverlaps(pos, compNodes.map((x) => x.id), dims);
    return pos;
  }

  // 3. LAYERED HIERARCHICAL LAYOUT (Topological + Architectural Tier + Barycenter Crossing Minimization)
  // Compute topological depth via Kahn's algorithm (gracefully handles cycles)
  const remainingIn = new Map(inDeg);
  const topoDepth = new Map<string, number>();
  const queue: string[] = [];
  for (const node of compNodes) {
    if ((remainingIn.get(node.id) || 0) === 0) {
      queue.push(node.id);
      topoDepth.set(node.id, 0);
    }
  }
  queue.sort();

  const processed = new Set<string>();
  while (queue.length > 0) {
    const curr = queue.shift()!;
    processed.add(curr);
    const d = topoDepth.get(curr) || 0;
    for (const nxt of outgoing.get(curr) || []) {
      topoDepth.set(nxt, Math.max(topoDepth.get(nxt) || 0, d + 1));
      const nextIn = (remainingIn.get(nxt) || 0) - 1;
      remainingIn.set(nxt, nextIn);
      if (nextIn === 0) {
        queue.push(nxt);
      }
    }
  }

  // Assign any cyclic/remaining nodes using architectural tier or neighbor depth
  for (const node of compNodes) {
    if (!topoDepth.has(node.id)) {
      const parentDepths = (incoming.get(node.id) || [])
        .map((p) => topoDepth.get(p))
        .filter((d): d is number => d !== undefined);
      const fallback = parentDepths.length > 0 ? Math.max(...parentDepths) + 1 : resolveNodeTier(node);
      topoDepth.set(node.id, fallback);
    }
  }

  // Blend with semantic architectural tier when topological depth is either flat (< 2)
  // OR creates an overly tall sparse chain (e.g. > 6 layers with < 1.8 nodes/layer avg)
  const maxTopo = Math.max(...Array.from(topoDepth.values()), 0);
  const useTopoLayers = maxTopo >= 2 && (maxTopo <= 6 || n / (maxTopo + 1) >= 1.8);
  const byLayer = new Map<number, HandoverGraphNode[]>();
  for (const node of compNodes) {
    const layer = useTopoLayers ? (topoDepth.get(node.id) ?? 0) : resolveNodeTier(node);
    const bucket = byLayer.get(layer) || [];
    bucket.push(node);
    byLayer.set(layer, bucket);
  }

  // Determine ideal max items per row based on viewport aspect ratio and graph size
  const targetCols = Math.max(
    3,
    Math.min(6, Math.round(Math.sqrt(n * Math.max(1.0, aspectRatio)) * 1.15))
  );

  // Build wrapped visual rows
  const sortedLayers = Array.from(byLayer.keys()).sort((a, b) => a - b);
  const visualRows: HandoverGraphNode[][] = [];
  for (const layerKey of sortedLayers) {
    const items = [...(byLayer.get(layerKey) || [])].sort(
      (a, b) => totalDeg(b.id) - totalDeg(a.id) || a.label.localeCompare(b.label)
    );
    for (let i = 0; i < items.length; i += targetCols) {
      visualRows.push(items.slice(i, i + targetCols));
    }
  }

  const maxRowItems = Math.max(...visualRows.map((r) => r.length), 1);
  const totalWidth = (maxRowItems - 1) * colStep;

  // Initial row placement
  const assignRows = () => {
    visualRows.forEach((rowItems, rIdx) => {
      const rw = (rowItems.length - 1) * colStep;
      const startX = (totalWidth - rw) / 2;
      rowItems.forEach((item, cIdx) => {
        pos.set(item.id, { x: startX + cIdx * colStep, y: rIdx * rowStep });
      });
    });
  };
  assignRows();

  // 2 forward/backward barycenter sweeps to minimize edge crossings
  for (let sweep = 0; sweep < 2; sweep++) {
    for (let rIdx = 1; rIdx < visualRows.length; rIdx++) {
      visualRows[rIdx]!.sort((a, b) => {
        const aNbrs = [...(incoming.get(a.id) || []), ...(outgoing.get(a.id) || [])];
        const bNbrs = [...(incoming.get(b.id) || []), ...(outgoing.get(b.id) || [])];
        const aAvg =
          aNbrs.length > 0
            ? aNbrs.reduce((s, id) => s + (pos.get(id)?.x ?? totalWidth / 2), 0) / aNbrs.length
            : totalWidth / 2;
        const bAvg =
          bNbrs.length > 0
            ? bNbrs.reduce((s, id) => s + (pos.get(id)?.x ?? totalWidth / 2), 0) / bNbrs.length
            : totalWidth / 2;
        return aAvg - bAvg || a.label.localeCompare(b.label);
      });
    }
    assignRows();
  }

  resolveOverlaps(pos, compNodes.map((x) => x.id), dims);
  return pos;
}

const elkInstance = new ELK();

/**
 * Compute Clean Layered Flow layout using ELK Layered (`elkjs`) for graphs with >= 7 nodes.
 * Preserves small graphs (1-6 nodes) with the synchronous compact layered layout,
 * balances wide flat leaf layers so hub-and-spoke graphs stay readable, and recomputes edge labels.
 */
export async function layoutWithElk(
  nodes: Node<AmeliorateNodeData>[],
  edges: Edge<AmeliorateEdgeData>[],
  options?: AdaptiveLayoutOptions
): Promise<{
  nodes: Node<AmeliorateNodeData>[];
  edges: Edge<AmeliorateEdgeData>[];
}> {
  if (nodes.length <= 6) {
    return {
      nodes,
      edges: recomputeEdgeLabelPositions(nodes, edges, options?.nodeDimensions),
    };
  }

  const dims = options?.nodeDimensions;
  const vpW = options?.viewportWidth && options.viewportWidth > 200 ? options.viewportWidth : 1200;
  const vpH = options?.viewportHeight && options.viewportHeight > 200 ? options.viewportHeight : 720;
  const aspectRatio = Math.max(1.1, Math.min(2.2, vpW / vpH));

  const visibleIds = new Set(nodes.map((n) => n.id));
  const validEdges = edges.filter((e) => visibleIds.has(e.source) && visibleIds.has(e.target) && e.source !== e.target);

  const sortedNodesForElk = [...nodes].sort(
    (a, b) =>
      resolveNodeTier(a.data.raw) - resolveNodeTier(b.data.raw) ||
      (a.data.raw.entity_type || "").localeCompare(b.data.raw.entity_type || "") ||
      a.data.raw.label.localeCompare(b.data.raw.label)
  );

  const elkGraph = {
    id: "root",
    layoutOptions: {
      "elk.algorithm": "layered",
      "elk.direction": "DOWN",
      "elk.edgeRouting": "SPLINES",
      "elk.spacing.nodeNode": "36",
      "elk.layered.spacing.nodeNodeBetweenLayers": "80",
      "elk.spacing.edgeNode": "22",
      "elk.separateConnectedComponents": "true",
      "elk.spacing.componentComponent": "64",
      "elk.aspectRatio": String(Number(aspectRatio.toFixed(2))),
      "elk.layered.crossingMinimization.strategy": "LAYER_SWEEP",
      "elk.layered.nodePlacement.strategy": "NETWORK_SIMPLEX",
      "elk.layered.considerModelOrder.strategy": "PREFER_NODES",
    },
    children: sortedNodesForElk.map((n) => {
      const sz = getNodeSize(n.id, dims);
      return { id: n.id, width: sz.w, height: sz.h };
    }),
    edges: validEdges.map((e) => ({
      id: e.id,
      sources: [e.source],
      targets: [e.target],
    })),
  };

  try {
    const laidOut = await elkInstance.layout(elkGraph);
    const posMap = new Map<string, { x: number; y: number }>();
    for (const child of laidOut.children || []) {
      posMap.set(child.id, {
        x: Math.round(child.x ?? 0),
        y: Math.round(child.y ?? 0),
      });
    }

    // Balance any excessively wide single layer (> maxCols nodes at identical Y) into compact sub-rows
    const maxCols = Math.max(4, Math.min(8, Math.ceil(Math.sqrt(nodes.length * aspectRatio))));
    const byLayerY = new Map<number, Node<AmeliorateNodeData>[]>();
    for (const n of sortedNodesForElk) {
      const y = posMap.get(n.id)?.y ?? n.position.y;
      const bucketKey = Math.round(y / 20) * 20;
      const list = byLayerY.get(bucketKey) || [];
      list.push(n);
      byLayerY.set(bucketKey, list);
    }

    const sortedYKeys = Array.from(byLayerY.keys()).sort((a, b) => a - b);
    let yShift = 0;
    const colStep = DEFAULT_NODE_W + 32; // 236px compact horizontal pitch
    const rowStep = DEFAULT_NODE_H + 48; // 164px compact vertical pitch

    for (const yKey of sortedYKeys) {
      const layerNodes = byLayerY.get(yKey)!;
      if (layerNodes.length > maxCols) {
        layerNodes.sort((a, b) => (posMap.get(a.id)?.x ?? 0) - (posMap.get(b.id)?.x ?? 0));
        const subRows = Math.ceil(layerNodes.length / maxCols);
        const centerRefX =
          layerNodes.reduce((acc, n) => acc + (posMap.get(n.id)?.x ?? 0), 0) / layerNodes.length;
        const maxRowW = (maxCols - 1) * colStep;
        const baseX = Math.round(centerRefX - maxRowW / 2);

        layerNodes.forEach((n, idx) => {
          const r = Math.floor(idx / maxCols);
          const c = idx % maxCols;
          const itemsInThisRow = r === subRows - 1 ? layerNodes.length - r * maxCols : maxCols;
          const rw = (itemsInThisRow - 1) * colStep;
          const startX = baseX + (maxRowW - rw) / 2;
          posMap.set(n.id, {
            x: Math.round(startX + c * colStep),
            y: Math.round(yKey + yShift + r * rowStep),
          });
        });
        yShift += (subRows - 1) * rowStep;
      } else if (yShift > 0) {
        for (const n of layerNodes) {
          const p = posMap.get(n.id)!;
          posMap.set(n.id, { x: p.x, y: p.y + yShift });
        }
      }
    }

    resolveOverlaps(
      posMap,
      nodes.map((n) => n.id),
      dims,
      28
    );

    // Ameliorate convention: center the laid-out graph around origin (0, 0)
    let minX = Infinity;
    let maxX = -Infinity;
    let minY = Infinity;
    let maxY = -Infinity;
    for (const n of nodes) {
      const p = posMap.get(n.id) ?? n.position;
      const sz = getNodeSize(n.id, dims);
      minX = Math.min(minX, p.x);
      maxX = Math.max(maxX, p.x + sz.w);
      minY = Math.min(minY, p.y);
      maxY = Math.max(maxY, p.y + sz.h);
    }
    const offsetX = Number.isFinite(minX) ? -Math.round((minX + maxX) / 2) : 0;
    const offsetY = Number.isFinite(minY) ? -Math.round((minY + maxY) / 2) : 0;

    const updatedNodes = nodes.map((n) => {
      const p = posMap.get(n.id) ?? n.position;
      return {
        ...n,
        position: { x: p.x + offsetX, y: p.y + offsetY },
      };
    });
    const updatedEdges = recomputeEdgeLabelPositions(updatedNodes, edges, dims);
    return { nodes: updatedNodes, edges: updatedEdges };
  } catch {
    return {
      nodes,
      edges: recomputeEdgeLabelPositions(nodes, edges, dims),
    };
  }
}

/**
 * Resolve positions for incremental background knowledge updates:
 * - Preserves all existing node coordinates.
 * - Places newly arrived nodes near their connected neighbors (or fallback pos) and resolves local overlaps.
 */
export function resolveIncrementalNodePositions(
  newLayoutNodes: Node<AmeliorateNodeData>[],
  edges: Edge<AmeliorateEdgeData>[],
  existingPositions: Map<string, { x: number; y: number }>,
  dims?: Map<string, { width: number; height: number }>
): Node<AmeliorateNodeData>[] {
  const resultPositions = new Map<string, { x: number; y: number }>();
  const addedIds: string[] = [];

  for (const n of newLayoutNodes) {
    const prev = existingPositions.get(n.id);
    if (prev) {
      resultPositions.set(n.id, prev);
    } else {
      addedIds.push(n.id);
    }
  }

  // Use clean baseLayout position for newly arrived nodes (never collapse onto hub center)
  for (const id of addedIds) {
    const layoutFallback = newLayoutNodes.find((x) => x.id === id)?.position ?? { x: 80, y: 80 };
    resultPositions.set(id, layoutFallback);
  }

  // Always guarantee zero overlap across final positions (even if dimensions changed or stale cache existed)
  resolveOverlaps(
    resultPositions,
    newLayoutNodes.map((n) => n.id),
    dims
  );

  return newLayoutNodes.map((n) => {
    const pos = resultPositions.get(n.id) ?? n.position;
    existingPositions.set(n.id, pos);
    return { ...n, position: pos };
  });
}

/**
 * Recompute edge label coordinates (labelX, labelY, hasCollision) directly from the
 * actual final node positions so edge labels can never float away from their edges.
 */
export function recomputeEdgeLabelPositions(
  finalNodes: Node<AmeliorateNodeData>[],
  edges: Edge<AmeliorateEdgeData>[],
  dims?: Map<string, { width: number; height: number }>
): Edge<AmeliorateEdgeData>[] {
  const posMap = new Map(finalNodes.map((n) => [n.id, n.position]));
  const nodeBoxes = finalNodes.map((n) => {
    const { w, h } = getNodeSize(n.id, dims);
    return {
      xmin: n.position.x - 24,
      xmax: n.position.x + w + 24,
      ymin: n.position.y - 24,
      ymax: n.position.y + h + 24,
    };
  });
  const placedLabels: Array<{ x: number; y: number; w: number; h: number }> = [];

  return edges.map((e) => {
    const sPos = posMap.get(e.source);
    const tPos = posMap.get(e.target);
    const labelText = e.label ? String(e.label) : "";
    if (!labelText || !sPos || !tPos || !e.data) {
      return e;
    }

    const sSz = getNodeSize(e.source, dims);
    const tSz = getNodeSize(e.target, dims);
    const sx = sPos.x + sSz.w / 2;
    const sy = sPos.y + sSz.h;
    const tx = tPos.x + tSz.w / 2;
    const ty = tPos.y;
    const dy = ty - sy;

    const p0: [number, number] = [sx, sy];
    const c = Math.max(35, Math.abs(dy) * 0.45);
    const p1: [number, number] = [sx, sy + c];
    const p2: [number, number] = [tx, ty - c];
    const p3: [number, number] = [tx, ty];

    const lblW = Math.max(54, labelText.length * 6.5 + 20);
    const lblH = 22;
    const candidateTs = [0.5, 0.4, 0.6];
    let chosenX: number | null = null;
    let chosenY: number | null = null;

    for (const t of candidateTs) {
      const mt = 1 - t;
      const cx = mt * mt * mt * p0[0] + 3 * mt * mt * t * p1[0] + 3 * mt * t * t * p2[0] + t * t * t * p3[0];
      const cy = mt * mt * mt * p0[1] + 3 * mt * mt * t * p1[1] + 3 * mt * t * t * p2[1] + t * t * t * p3[1];

      const collidesWithNode = nodeBoxes.some(
        (b) => cx + lblW / 2 > b.xmin && cx - lblW / 2 < b.xmax && cy + lblH / 2 > b.ymin && cy - lblH / 2 < b.ymax
      );
      if (collidesWithNode) continue;

      const collidesWithLabel = placedLabels.some((pl) => {
        return Math.abs(cx - pl.x) < (lblW + pl.w) / 2 + 18 && Math.abs(cy - pl.y) < (lblH + pl.h) / 2 + 12;
      });
      if (collidesWithLabel) continue;

      chosenX = cx;
      chosenY = cy;
      break;
    }

    if (chosenX !== null && chosenY !== null) {
      placedLabels.push({ x: chosenX, y: chosenY, w: lblW, h: lblH });
      return {
        ...e,
        data: {
          ...e.data,
          labelX: Math.round(chosenX),
          labelY: Math.round(chosenY),
          hasCollision: false,
        },
      };
    }

    return {
      ...e,
      data: {
        ...e.data,
        labelX: Math.round((sx + tx) / 2),
        labelY: Math.round((sy + ty) / 2),
        hasCollision: true,
      },
    };
  });
}

/**
 * Compute adaptive, deterministic Ameliorate-style flowchart positions based on
 * graph topology, connected components, viewport aspect ratio, and measured node dimensions.
 */
export function buildAmeliorateFlowchartElements(
  rawNodes: HandoverGraphNode[],
  rawEdges: HandoverGraphEdge[],
  selectedNodeId: string | null,
  options?: AdaptiveLayoutOptions
): {
  nodes: Node<AmeliorateNodeData>[];
  edges: Edge<AmeliorateEdgeData>[];
} {
  if (rawNodes.length === 0) {
    return { nodes: [], edges: [] };
  }

  const visibleIds = new Set(rawNodes.map((n) => n.id));
  const validEdges = rawEdges.filter((e) => visibleIds.has(e.source) && visibleIds.has(e.target));

  const neighborSet = new Set<string>();
  for (const e of validEdges) {
    if (selectedNodeId) {
      if (e.source === selectedNodeId) neighborSet.add(e.target);
      if (e.target === selectedNodeId) neighborSet.add(e.source);
    }
  }

  const vpW = options?.viewportWidth && options.viewportWidth > 200 ? options.viewportWidth : 1100;
  const vpH = options?.viewportHeight && options.viewportHeight > 200 ? options.viewportHeight : 680;
  const aspectRatio = vpW / vpH;
  const dims = options?.nodeDimensions;

  const components = findConnectedComponents(rawNodes, validEdges);
  const nodePosMap = new Map<string, { x: number; y: number }>();

  // Pack connected components in a balanced 2D grid matching viewport aspect ratio
  const COMP_GAP_X = 120;
  const COMP_GAP_Y = 100;

  const compLayouts = components.map((comp) => {
    const compIds = new Set(comp.map((n) => n.id));
    const compEdges = validEdges.filter((e) => compIds.has(e.source) && compIds.has(e.target));
    const localPos = layoutComponent(comp, compEdges, aspectRatio, dims);

    let minX = Infinity;
    let maxX = -Infinity;
    let minY = Infinity;
    let maxY = -Infinity;
    for (const node of comp) {
      const p = localPos.get(node.id) ?? { x: 0, y: 0 };
      const sz = getNodeSize(node.id, dims);
      minX = Math.min(minX, p.x);
      maxX = Math.max(maxX, p.x + sz.w);
      minY = Math.min(minY, p.y);
      maxY = Math.max(maxY, p.y + sz.h);
    }
    return {
      comp,
      localPos,
      minX,
      minY,
      compW: Math.max(DEFAULT_NODE_W, maxX - minX),
      compH: Math.max(DEFAULT_NODE_H, maxY - minY),
    };
  });

  const totalArea = compLayouts.reduce((acc, c) => acc + (c.compW + COMP_GAP_X) * (c.compH + COMP_GAP_Y), 0);
  const targetRowWidth = Math.max(vpW * 1.35, 1100, Math.round(Math.sqrt(totalArea * Math.max(1.1, aspectRatio))));

  let cursorX = 50;
  let cursorY = 40;
  let rowMaxH = 0;

  for (const cl of compLayouts) {
    if (cursorX > 50 && cursorX + cl.compW > targetRowWidth) {
      cursorX = 50;
      cursorY += rowMaxH + COMP_GAP_Y;
      rowMaxH = 0;
    }

    for (const node of cl.comp) {
      const p = cl.localPos.get(node.id) ?? { x: 0, y: 0 };
      nodePosMap.set(node.id, {
        x: Math.round(cursorX + (p.x - cl.minX)),
        y: Math.round(cursorY + (p.y - cl.minY)),
      });
    }

    cursorX += cl.compW + COMP_GAP_X;
    rowMaxH = Math.max(rowMaxH, cl.compH);
  }

  // Final global overlap safeguard across all components
  resolveOverlaps(
    nodePosMap,
    rawNodes.map((n) => n.id),
    dims
  );

  const nodes: Node<AmeliorateNodeData>[] = rawNodes.map((item) => {
    const pos = nodePosMap.get(item.id) ?? { x: 50, y: 40 };
    const spotlight: AmeliorateSpotlight =
      selectedNodeId === item.id
        ? "primary"
        : selectedNodeId && neighborSet.has(item.id)
          ? "secondary"
          : "normal";

    return {
      id: item.id,
      type: "ameliorateNode",
      position: pos,
      selected: selectedNodeId === item.id,
      data: {
        raw: item,
        theme: resolveAmeliorateNodeTheme(item),
        spotlight,
      },
    };
  });

  // Node card bounding boxes for edge-label collision checking
  const nodeBoxes: Array<{ xmin: number; xmax: number; ymin: number; ymax: number }> = [];
  nodePosMap.forEach(({ x, y }, id) => {
    const { w, h } = getNodeSize(id, dims);
    nodeBoxes.push({
      xmin: x - 28,
      xmax: x + w + 28,
      ymin: y - 28,
      ymax: y + h + 28,
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
      const sSz = getNodeSize(e.source, dims);
      const tSz = getNodeSize(e.target, dims);
      const sx = sPos.x + sSz.w / 2;
      const sy = sPos.y + sSz.h;
      const tx = tPos.x + tSz.w / 2;
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
