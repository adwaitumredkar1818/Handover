import React from "react";
import "@testing-library/jest-dom/vitest";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { KnowledgeIntelligenceWorkspace } from "../components/knowledge/KnowledgeIntelligenceWorkspace";
import {
  RelationshipWorkspace,
  filterVisibleGraphEdges,
} from "../components/relationships/RelationshipWorkspace";
import { api } from "../lib/api";

vi.mock("../context/LiveAppContext", () => ({
  useLiveApp: () => ({
    findings: [],
    members: [
      { id: "pm-1", user_full_name: "Alice Engineer", user_email: "alice@example.com" },
    ],
    refreshFindings: vi.fn(),
    refreshVerification: vi.fn(),
  }),
}));

vi.mock("@xyflow/react", () => ({
  ReactFlow: ({ nodes, edges, children }: { nodes: unknown[]; edges: unknown[]; children?: React.ReactNode }) => (
    <div data-testid="react-flow-mock" data-nodes={nodes.length} data-edges={edges.length}>
      {children}
    </div>
  ),
  Background: () => <div />,
  Controls: () => <div />,
  MiniMap: () => <div />,
  useNodesState: (init: unknown[]) => {
    const [val, setVal] = React.useState(init);
    return [val, setVal, vi.fn()];
  },
  useEdgesState: (init: unknown[]) => {
    const [val, setVal] = React.useState(init);
    return [val, setVal, vi.fn()];
  },
  MarkerType: { ArrowClosed: "arrowclosed" },
}));

describe("Knowledge Intelligence & Relationship Explorer UI", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("shows strict empty state when no project knowledge exists (no synthetic data)", async () => {
    vi.spyOn(api.knowledgeIntelligence, "getGraph").mockResolvedValue({
      graph_type: "technology-stack",
      project_id: "proj-1",
      nodes: [],
      edges: [],
      summary: { node_count: 0, edge_count: 0, categories: {} },
    });

    render(<KnowledgeIntelligenceWorkspace projectId="proj-1" />);

    await waitFor(() => {
      expect(
        screen.getByText("No knowledge has been reconstructed from this project's evidence yet.")
      ).toBeInTheDocument();
    });
    expect(screen.queryByText(/Argon2id/i)).not.toBeInTheDocument();
  });

  it("switches across all four Knowledge Intelligence views cleanly", async () => {
    const getGraphSpy = vi.spyOn(api.knowledgeIntelligence, "getGraph").mockResolvedValue({
      graph_type: "technology-stack",
      project_id: "proj-1",
      nodes: [
        {
          id: "n-1",
          entity_type: "technology",
          label: "PostgreSQL",
          status: "declared_dependency",
          verification_status: "pending",
          evidence_count: 1,
          evidence_ids: ["ev-1"],
          aliases: ["Postgres"],
          metadata: {},
        },
      ],
      edges: [],
      summary: { node_count: 1, edge_count: 0, categories: { database: 1 } },
    });
    const listFindingsSpy = vi.spyOn(api.knowledgeIntelligence, "listFindings").mockResolvedValue({
      items: [],
      total: 0,
      limit: 100,
      offset: 0,
    });

    render(<KnowledgeIntelligenceWorkspace projectId="proj-1" />);
    await waitFor(() => expect(getGraphSpy).toHaveBeenCalledWith("proj-1", "technology-stack", expect.any(Object)));

    fireEvent.click(screen.getByRole("tab", { name: /System Architecture/i }));
    await waitFor(() => expect(getGraphSpy).toHaveBeenCalledWith("proj-1", "system-architecture", expect.any(Object)));

    fireEvent.click(screen.getByRole("tab", { name: /Features & Workflows/i }));
    await waitFor(() => expect(getGraphSpy).toHaveBeenCalledWith("proj-1", "features-workflows", expect.any(Object)));

    fireEvent.click(screen.getByRole("tab", { name: /Knowledge Domains/i }));
    await waitFor(() => expect(listFindingsSpy).toHaveBeenCalled());
  });

  it("filters out dangling edges when graph nodes are filtered", () => {
    const edges = [
      { id: "e1", source: "n1", target: "n2" },
      { id: "e2", source: "n1", target: "n3" },
    ];
    const filtered = filterVisibleGraphEdges(edges, new Set(["n1", "n2"]));
    expect(filtered).toHaveLength(1);
    expect(filtered[0]?.id).toBe("e1");
  });

  it("renders Contributor Identity Review and allows marking external contributor", async () => {
    vi.spyOn(api.relationships, "getContributorsGraph").mockResolvedValue({
      project_id: "proj-1",
      nodes: [],
      edges: [],
      summary: {},
    });
    vi.spyOn(api.relationships, "listContributors").mockResolvedValue([
      {
        contributor_key: "ghid:99",
        display_name: "External Dev",
        github_login: "ext-dev",
        contributor_type: "unidentified",
        review_status: "pending",
        contribution_count: 3,
        commits_count: 2,
        prs_count: 1,
        issues_count: 0,
        repositories: ["org/repo"],
        work_areas: ["Frontend"],
        evidence_ids: ["ev-9"],
        review_history: [],
      },
    ]);
    vi.spyOn(api.relationships, "listWorkClusters").mockResolvedValue([]);
    vi.spyOn(api.roster, "listAttributions").mockResolvedValue([]);
    const reviewSpy = vi.spyOn(api.relationships, "reviewContributor").mockResolvedValue({
      contributor_key: "ghid:99",
      contributor_type: "external_contributor",
      review_status: "marked_external",
      updated_records: 3,
    });

    render(<RelationshipWorkspace projectId="proj-1" />);

    await waitFor(() => {
      expect(screen.getByText(/Contributor identities require review/i)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /Review Identities/i }));
    await waitFor(() => expect(screen.getByText("External Dev")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /External/i }));
    await waitFor(() =>
      expect(reviewSpy).toHaveBeenCalledWith("proj-1", "ghid:99", expect.objectContaining({ action: "mark_external" }))
    );
  });
});
