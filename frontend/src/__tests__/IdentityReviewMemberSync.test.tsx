import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

const mockReviewContributor = vi.fn((..._args: unknown[]) => Promise.resolve({ status: "ok" }));
const mockListMembers = vi.fn((..._args: unknown[]) => Promise.resolve([] as unknown[]));

const initialMembers = [
  {
    id: "pm-owner-1",
    user_id: "u-owner-1",
    full_name: "Vernit Garg",
    email: "vernit@example.com",
    role_name: "project_manager",
    status: "active",
  },
];

const addedMember = {
  id: "pm-priya-999",
  user_id: "u-priya-999",
  full_name: "Priya Sharma",
  email: "priya@company.com",
  role_name: "project_contributor",
  status: "active",
};

let currentLiveMembers = [...initialMembers];

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams("tab=identity_review"),
}));

vi.mock("@xyflow/react", () => ({
  ReactFlow: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
  Controls: () => <div />,
  Background: () => <div />,
  MiniMap: () => <div />,
  useNodesState: (init: unknown[]) => [init, vi.fn(), vi.fn()],
  useEdgesState: (init: unknown[]) => [init, vi.fn(), vi.fn()],
  MarkerType: { ArrowClosed: "arrowclosed" },
  Handle: () => null,
  Position: { Top: "top", Bottom: "bottom" },
  getBezierPath: () => ["M0,0 L10,10", 5, 5],
  EdgeLabelRenderer: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
}));

vi.mock("../context/LiveAppContext", () => ({
  useLiveApp: () => ({
    members: currentLiveMembers,
    activeProject: { id: "proj-1", name: "Test Project" },
  }),
}));

vi.mock("../hooks/useProjectProcessingStatus", () => ({
  useProjectProcessingStatus: () => ({
    status: { is_processing: false, status: "idle" },
    retry: vi.fn(),
    retrying: false,
  }),
}));

vi.mock("../lib/api", () => ({
  api: {
    members: {
      list: (...args: unknown[]) => mockListMembers(...args),
    },
    relationships: {
      getContributorsGraph: vi.fn(async () => ({ nodes: [], edges: [], summary: {} })),
      getGraph: vi.fn(async () => ({ nodes: [], edges: [] })),
      listWorkClusters: vi.fn(async () => []),
      listContributors: vi.fn(async () => [
        {
          contributor_key: "gh:ext-dev",
          display_name: "ext-dev",
          github_login: "ext-dev",
          contributor_type: "unidentified",
          review_status: "pending",
          match_method: "unmatched",
          contribution_count: 4,
          commits_count: 4,
          prs_count: 0,
          issues_count: 0,
          repositories: ["org/repo"],
          work_areas: ["Backend"],
          evidence_ids: [],
          review_history: [],
        },
        {
          contributor_key: "member:pm-priya-999",
          display_name: "Priya Sharma",
          github_login: null,
          contributor_type: "confirmed_member",
          review_status: "pending",
          match_method: "pending_identity",
          matched_project_membership_id: "pm-priya-999",
          matched_member_name: "Priya Sharma",
          contribution_count: 0,
          commits_count: 0,
          prs_count: 0,
          issues_count: 0,
          repositories: [],
          work_areas: ["Unassigned"],
          evidence_ids: [],
          review_history: [],
        },
      ]),
      listIdentityCandidates: vi.fn(async () => []),
      reviewContributor: (...args: unknown[]) => mockReviewContributor(...args),
    },
    roster: {
      listAttributions: vi.fn(async () => []),
    },
  },
}));

import { RelationshipWorkspace } from "../components/relationships/RelationshipWorkspace";

describe("Relationship Explorer Identity Review People Selector", () => {
  beforeEach(() => {
    currentLiveMembers = [...initialMembers];
    mockListMembers.mockReset();
    mockReviewContributor.mockClear();
  });

  it("displays newly added zero-commit team member in the Identity Review dropdown and persists match action", async () => {
    mockListMembers
      .mockResolvedValueOnce(initialMembers)
      .mockResolvedValueOnce([...initialMembers, addedMember]);

    const { rerender } = render(<RelationshipWorkspace projectId="proj-1" />);

    const identityTab = screen.getByRole("tab", { name: /Identity Review/i });
    fireEvent.click(identityTab);

    await waitFor(() => {
      expect(screen.getByLabelText(/Select project member for ext-dev/i)).toBeInTheDocument();
    });

    // Simulate adding Priya Sharma (0 commits, no GitHub identity) via Team Members
    currentLiveMembers = [...initialMembers, addedMember];
    rerender(<RelationshipWorkspace projectId="proj-1" />);

    await waitFor(() => {
      expect(
        screen.getAllByRole("option", { name: /Priya Sharma \(priya@company\.com\)/i }).length
      ).toBeGreaterThan(0);
    });

    // Verify unlinked pending state text is displayed for Priya
    expect(screen.getAllByText(/Not linked to a source identity/i).length).toBeGreaterThan(0);

    // Select Priya Sharma and submit Match Member
    const select = screen.getByLabelText(/Select project member for ext-dev/i);
    fireEvent.change(select, { target: { value: "pm-priya-999" } });

    const matchButtons = screen.getAllByRole("button", { name: /Match Member/i });
    fireEvent.click(matchButtons[0]!);

    await waitFor(() => {
      expect(mockReviewContributor).toHaveBeenCalledWith(
        "proj-1",
        "gh:ext-dev",
        expect.objectContaining({
          action: "match_member",
          project_membership_id: "pm-priya-999",
        })
      );
    });
  });
});
