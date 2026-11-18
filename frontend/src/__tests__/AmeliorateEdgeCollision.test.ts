import { describe, it, expect } from "vitest";
import {
  buildAmeliorateFlowchartElements,
  type HandoverGraphNode,
  type HandoverGraphEdge,
} from "../components/knowledge/ameliorate/ameliorateAdapter";

describe("Ameliorate Flowchart Layout and Edge Collision Elimination", () => {
  it("strictly prevents edge labels from colliding with node cards or each other", () => {
    // Replicate the dense scenario from the user screenshot:
    // 2 Project Members (Tier 0)
    // 2 Contributors (Tier 1)
    // 5 Work Clusters (Tier 2)
    const rawNodes: HandoverGraphNode[] = [
      {
        id: "member:test",
        label: "Test Engineer",
        entity_type: "confirmed_member",
        status: "HUMAN_VERIFIED",
        verification_status: "verified",
        evidence_count: 5,
        evidence_ids: [],
        aliases: [],
        metadata: {},
      },
      {
        id: "member:vernit",
        label: "Vernit Garg",
        entity_type: "confirmed_member",
        status: "HUMAN_VERIFIED",
        verification_status: "verified",
        evidence_count: 7,
        evidence_ids: [],
        aliases: [],
        metadata: {},
      },
      {
        id: "person:adwait",
        label: "Adwait Umredkar",
        entity_type: "contributor",
        status: "pending",
        verification_status: "pending",
        evidence_count: 29,
        evidence_ids: [],
        aliases: [],
        metadata: {},
      },
      {
        id: "person:adw",
        label: "adwait1818",
        entity_type: "contributor",
        status: "pending",
        verification_status: "pending",
        evidence_count: 14,
        evidence_ids: [],
        aliases: [],
        metadata: {},
      },
      {
        id: "cluster:auth",
        label: "Authentication",
        entity_type: "work_cluster",
        status: "derived",
        verification_status: "derived",
        evidence_count: 14,
        evidence_ids: [],
        aliases: [],
        metadata: {},
      },
      {
        id: "cluster:app",
        label: "Application Core",
        entity_type: "work_cluster",
        status: "derived",
        verification_status: "derived",
        evidence_count: 7,
        evidence_ids: [],
        aliases: [],
        metadata: {},
      },
      {
        id: "cluster:aiml",
        label: "AI/ML Inference",
        entity_type: "work_cluster",
        status: "derived",
        verification_status: "derived",
        evidence_count: 6,
        evidence_ids: [],
        aliases: [],
        metadata: {},
      },
      {
        id: "cluster:bugfix",
        label: "Bug Fixing",
        entity_type: "work_cluster",
        status: "derived",
        verification_status: "derived",
        evidence_count: 6,
        evidence_ids: [],
        aliases: [],
        metadata: {},
      },
      {
        id: "cluster:backend",
        label: "Backend Services",
        entity_type: "work_cluster",
        status: "derived",
        verification_status: "derived",
        evidence_count: 12,
        evidence_ids: [],
        aliases: [],
        metadata: {},
      },
    ];

    // Many dense edges crossing tiers
    const rawEdges: HandoverGraphEdge[] = [
      {
        id: "e1",
        source: "member:vernit",
        target: "person:adwait",
        relationship_type: "assigned_role",
        label: "assigned role",
        evidence_basis: "explicit",
        verification_status: "verified",
        confidence_score: 1.0,
        evidence_ids: [],
      },
      {
        id: "e2",
        source: "member:vernit",
        target: "person:adw",
        relationship_type: "assigned_role",
        label: "assigned role",
        evidence_basis: "explicit",
        verification_status: "verified",
        confidence_score: 1.0,
        evidence_ids: [],
      },
      {
        id: "e3",
        source: "member:test",
        target: "person:adwait",
        relationship_type: "assigned_role",
        label: "assigned role",
        evidence_basis: "explicit",
        verification_status: "verified",
        confidence_score: 1.0,
        evidence_ids: [],
      },
      // Edges to work clusters
      {
        id: "e4",
        source: "person:adwait",
        target: "cluster:auth",
        relationship_type: "contributed_to",
        label: "14 contrib(s)",
        evidence_basis: "explicit",
        verification_status: "verified",
        confidence_score: 1.0,
        evidence_ids: [],
      },
      {
        id: "e5",
        source: "person:adwait",
        target: "cluster:app",
        relationship_type: "contributed_to",
        label: "7 contrib(s)",
        evidence_basis: "explicit",
        verification_status: "verified",
        confidence_score: 1.0,
        evidence_ids: [],
      },
      {
        id: "e6",
        source: "person:adwait",
        target: "cluster:aiml",
        relationship_type: "contributed_to",
        label: "6 contrib(s)",
        evidence_basis: "explicit",
        verification_status: "verified",
        confidence_score: 1.0,
        evidence_ids: [],
      },
      {
        id: "e7",
        source: "person:adw",
        target: "cluster:auth",
        relationship_type: "contributed_to",
        label: "4 contrib(s)",
        evidence_basis: "explicit",
        verification_status: "verified",
        confidence_score: 1.0,
        evidence_ids: [],
      },
      {
        id: "e8",
        source: "person:adw",
        target: "cluster:app",
        relationship_type: "contributed_to",
        label: "2 contrib(s)",
        evidence_basis: "explicit",
        verification_status: "verified",
        confidence_score: 1.0,
        evidence_ids: [],
      },
      {
        id: "e9",
        source: "person:adw",
        target: "cluster:aiml",
        relationship_type: "contributed_to",
        label: "1 contrib(s)",
        evidence_basis: "explicit",
        verification_status: "verified",
        confidence_score: 1.0,
        evidence_ids: [],
      },
      {
        id: "e10",
        source: "person:adw",
        target: "cluster:bugfix",
        relationship_type: "contributed_to",
        label: "6 contrib(s)",
        evidence_basis: "explicit",
        verification_status: "verified",
        confidence_score: 1.0,
        evidence_ids: [],
      },
      {
        id: "e11",
        source: "person:adw",
        target: "cluster:backend",
        relationship_type: "contributed_to",
        label: "1 contrib(s)",
        evidence_basis: "explicit",
        verification_status: "verified",
        confidence_score: 1.0,
        evidence_ids: [],
      },
    ];

    const { nodes, edges } = buildAmeliorateFlowchartElements(rawNodes, rawEdges, null);

    expect(nodes.length).toBe(9);
    expect(edges.length).toBe(11);

    // 1. Verify that no visible label overlaps any node bounding box
    const nodeBoxes = nodes.map((n) => ({
      id: n.id,
      xmin: n.position.x,
      xmax: n.position.x + 196,
      ymin: n.position.y,
      ymax: n.position.y + 96,
    }));

    const visibleLabels: Array<{ id: string; x: number; y: number; w: number; h: number }> = [];

    for (const e of edges) {
      if (e.data?.hasCollision === false && e.data?.labelX !== undefined && e.data?.labelY !== undefined) {
        const lx = e.data.labelX;
        const ly = e.data.labelY;
        const labelText = typeof e.label === "string" ? e.label : "";
        const lw = Math.max(54, (labelText.length || 5) * 6.5 + 20);
        const lh = 22;

        visibleLabels.push({ id: e.id, x: lx, y: ly, w: lw, h: lh });

        // Must not intersect any node
        for (const b of nodeBoxes) {
          const xOverlap = lx + lw / 2 > b.xmin && lx - lw / 2 < b.xmax;
          const yOverlap = ly + lh / 2 > b.ymin && ly - lh / 2 < b.ymax;
          expect(xOverlap && yOverlap).toBe(false);
        }
      }
    }

    // 2. Verify that no two visible labels overlap each other
    for (let i = 0; i < visibleLabels.length; i++) {
      for (let j = i + 1; j < visibleLabels.length; j++) {
        const a = visibleLabels[i];
        const b = visibleLabels[j];
        if (!a || !b) continue;
        const xOverlap = Math.abs(a.x - b.x) < (a.w + b.w) / 2;
        const yOverlap = Math.abs(a.y - b.y) < (a.h + b.h) / 2;
        expect(xOverlap && yOverlap).toBe(false);
      }
    }

    // 3. In crowded channels, edges that cannot fit safely are flagged with hasCollision: true
    const crowdedEdges = edges.filter((e) => e.data?.hasCollision === true);
    expect(crowdedEdges.length).toBeGreaterThan(0);
  });
});
