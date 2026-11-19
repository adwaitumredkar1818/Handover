/**
 * Presentation-only expandable grouping layer for large Knowledge Intelligence graphs.
 *
 * Strictly activates ONLY when:
 * - Graph mode is NOT "features-workflows"
 * - Actual authorised canonical node count > LARGE_GRAPH_THRESHOLD (24)
 *
 * Graphs with <= 24 authorised nodes bypass this module completely and render
 * with the original Ameliorate layout and components untouched.
 */

import type { HandoverGraphEdge, HandoverGraphNode } from "./ameliorateAdapter";

export const LARGE_GRAPH_THRESHOLD = 24;
export const DEFAULT_GROUP_REVEAL_LIMIT = 14;
export const GROUP_REVEAL_STEP = 14;

export function isLargeExpandableGraph(nodeCount: number, mode?: string): boolean {
  if (mode === "features-workflows") return false;
  return nodeCount > LARGE_GRAPH_THRESHOLD;
}

export interface ExpandableGroupSummary {
  groupId: string;
  label: string;
  totalCount: number;
  revealedCount: number;
  expanded: boolean;
  childIds: string[];
}

export interface ExpandableProjectionResult {
  nodes: HandoverGraphNode[];
  edges: HandoverGraphEdge[];
  groups: ExpandableGroupSummary[];
  matchedGroupIds: string[];
  highlightedNodeId: string | null;
}

function slugifyGroup(label: string): string {
  return (
    label
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "") || "other"
  );
}

const TECH_CATEGORY_LABELS: Record<string, string> = {
  frontend: "Frontend",
  backend: "Backend",
  database: "Database",
  storage: "Storage",
  infrastructure: "Infrastructure",
  devops: "Infrastructure",
  testing: "Testing",
  ai_ml: "AI & ML",
  ai: "AI & ML",
  external_integrations: "External Integrations",
  integrations: "External Integrations",
  technical_component: "Technical Components",
  security: "Security & Auth",
};

function formatGroupLabel(rawKey: string, mode: string): string {
  const norm = rawKey.trim().toLowerCase().replace(/[\s-]+/g, "_");
  if (mode === "technology-stack" && TECH_CATEGORY_LABELS[norm]) {
    return TECH_CATEGORY_LABELS[norm];
  }
  return rawKey
    .trim()
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (ch) => ch.toUpperCase());
}

export function resolveCanonicalGroupLabel(node: HandoverGraphNode, mode: string): string {
  const meta = (node.metadata ?? {}) as Record<string, unknown>;
  if (mode === "technology-stack") {
    const rawCat =
      (typeof meta.technology_category === "string" && meta.technology_category) ||
      (typeof node.category === "string" && node.category) ||
      (typeof node.entity_type === "string" && node.entity_type) ||
      "Other";
    return formatGroupLabel(rawCat, mode);
  }
  const rawArch =
    (typeof meta.subsystem === "string" && meta.subsystem) ||
    (typeof meta.component_family === "string" && meta.component_family) ||
    (typeof node.category === "string" && node.category) ||
    (typeof node.entity_type === "string" && node.entity_type) ||
    "Components";
  return formatGroupLabel(rawArch, mode);
}

function isProjectRootNode(node: HandoverGraphNode): boolean {
  const meta = (node.metadata ?? {}) as Record<string, unknown>;
  return (
    node.entity_type?.toLowerCase() === "project" ||
    meta.is_root === true ||
    meta.node_role === "project_root"
  );
}

export function buildExpandableProjection({
  rawNodes,
  rawEdges,
  mode,
  expandedGroupIds,
  revealedCountsByGroup,
  searchQuery,
}: {
  rawNodes: HandoverGraphNode[];
  rawEdges: HandoverGraphEdge[];
  mode: string;
  expandedGroupIds: Set<string>;
  revealedCountsByGroup: Map<string, number>;
  searchQuery?: string;
}): ExpandableProjectionResult {
  const rootNodes = rawNodes.filter(isProjectRootNode);
  const rootNode = rootNodes[0] ?? null;
  const nonRootNodes = rootNode ? rawNodes.filter((n) => n.id !== rootNode.id) : rawNodes;

  // Degree map so progressive disclosure prioritizes well-connected & well-evidenced nodes
  const degreeMap = new Map<string, number>();
  for (const e of rawEdges) {
    degreeMap.set(e.source, (degreeMap.get(e.source) ?? 0) + 1);
    degreeMap.set(e.target, (degreeMap.get(e.target) ?? 0) + 1);
  }

  const grouped = new Map<string, { label: string; children: HandoverGraphNode[] }>();
  for (const node of nonRootNodes) {
    const label = resolveCanonicalGroupLabel(node, mode);
    const groupId = `group::${mode}::${slugifyGroup(label)}`;
    const bucket = grouped.get(groupId) ?? { label, children: [] };
    bucket.children.push(node);
    grouped.set(groupId, bucket);
  }

  const trimmedSearch = (searchQuery ?? "").trim().toLowerCase();
  const matchedGroupIds: string[] = [];
  let highlightedNodeId: string | null = null;

  if (trimmedSearch.length > 0) {
    for (const [groupId, bucket] of grouped.entries()) {
      const match = bucket.children.find(
        (n) =>
          n.label.toLowerCase().includes(trimmedSearch) ||
          (n.description ?? "").toLowerCase().includes(trimmedSearch) ||
          (n.category ?? "").toLowerCase().includes(trimmedSearch)
      );
      if (match) {
        matchedGroupIds.push(groupId);
        if (!highlightedNodeId) highlightedNodeId = match.id;
      }
    }
  }

  const effectiveExpanded = new Set(expandedGroupIds);
  for (const gid of matchedGroupIds) {
    effectiveExpanded.add(gid);
  }

  const projectedNodes: HandoverGraphNode[] = [];
  const projectedEdges: HandoverGraphEdge[] = [];
  const visibleNodeIds = new Set<string>();
  const groups: ExpandableGroupSummary[] = [];

  if (rootNode) {
    projectedNodes.push(rootNode);
    visibleNodeIds.add(rootNode.id);
  }

  const sortedGroups = Array.from(grouped.entries()).sort(
    (a, b) => b[1].children.length - a[1].children.length || a[1].label.localeCompare(b[1].label)
  );

  for (const [groupId, bucket] of sortedGroups) {
    const sortedChildren = [...bucket.children].sort((a, b) => {
      if (trimmedSearch.length > 0) {
        const aMatch = a.label.toLowerCase().includes(trimmedSearch) ? 1 : 0;
        const bMatch = b.label.toLowerCase().includes(trimmedSearch) ? 1 : 0;
        if (aMatch !== bMatch) return bMatch - aMatch;
      }
      const degDiff = (degreeMap.get(b.id) ?? 0) - (degreeMap.get(a.id) ?? 0);
      if (degDiff !== 0) return degDiff;
      const evDiff = (b.evidence_count ?? 0) - (a.evidence_count ?? 0);
      if (evDiff !== 0) return evDiff;
      return a.label.localeCompare(b.label);
    });

    const isExpanded = effectiveExpanded.has(groupId);
    const desiredLimit = revealedCountsByGroup.get(groupId) ?? sortedChildren.length;
    const revealedChildren = isExpanded ? sortedChildren.slice(0, desiredLimit) : [];

    groups.push({
      groupId,
      label: bucket.label,
      totalCount: sortedChildren.length,
      revealedCount: revealedChildren.length,
      expanded: isExpanded,
      childIds: sortedChildren.map((c) => c.id),
    });

    const groupNode: HandoverGraphNode = {
      id: groupId,
      entity_type: mode === "technology-stack" ? "technical_component" : "layer",
      label: `${bucket.label} (${sortedChildren.length})`,
      description: isExpanded
        ? revealedChildren.length < sortedChildren.length
          ? `Showing ${revealedChildren.length} of ${sortedChildren.length} · Click to collapse`
          : `${sortedChildren.length} items · Click to collapse`
        : `${sortedChildren.length} items · Click to expand`,
      category: bucket.label,
      status: isExpanded ? "IN_PROGRESS" : "declared_dependency",
      verification_status: "pending_review",
      evidence_count: sortedChildren.reduce((sum, c) => sum + (c.evidence_count ?? 0), 0),
      evidence_ids: [],
      aliases: [],
      metadata: {
        is_presentation_group: true,
        group_id: groupId,
        group_label: bucket.label,
        child_count: sortedChildren.length,
        revealed_count: revealedChildren.length,
        expanded: isExpanded,
      },
    };

    projectedNodes.push(groupNode);
    visibleNodeIds.add(groupId);

    if (rootNode) {
      projectedEdges.push({
        id: `pres-edge::${rootNode.id}::${groupId}`,
        source: rootNode.id,
        target: groupId,
        relationship_type: "contains_group",
        label: `${sortedChildren.length} items`,
        evidence_basis: "presentation_group",
        verification_status: "pending_review",
        confidence_score: 1,
        evidence_ids: [],
      });
    }

    if (isExpanded) {
      for (const child of revealedChildren) {
        projectedNodes.push(child);
        visibleNodeIds.add(child.id);
        projectedEdges.push({
          id: `pres-edge::${groupId}::${child.id}`,
          source: groupId,
          target: child.id,
          relationship_type: "group_member",
          label: "includes",
          evidence_basis: "presentation_group",
          verification_status: child.verification_status ?? "pending_review",
          confidence_score: 1,
          evidence_ids: [],
        });
      }
    }
  }

  // Preserve real canonical edges between all currently visible canonical nodes
  // (skipping direct root->child edges when the child is already connected via its expanded group hub
  // unless there is no group hub, to avoid redundant 77-edge fan-out clutter; all non-root real edges
  // between revealed nodes are always preserved).
  const rootId = rootNode?.id ?? null;
  for (const edge of rawEdges) {
    if (!visibleNodeIds.has(edge.source) || !visibleNodeIds.has(edge.target)) continue;
    if (rootId && edge.source === rootId) continue;
    projectedEdges.push(edge);
  }

  return {
    nodes: projectedNodes,
    edges: projectedEdges,
    groups,
    matchedGroupIds,
    highlightedNodeId,
  };
}
