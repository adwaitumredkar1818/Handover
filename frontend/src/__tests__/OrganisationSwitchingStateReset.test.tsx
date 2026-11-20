import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

const mockPush = vi.fn();
let mockContextState: Record<string, any> = {};

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
  usePathname: () => "/dashboard",
  useParams: () => ({}),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("../context/LiveAppContext", () => ({
  useLiveApp: () => mockContextState,
}));

vi.mock("../lib/api", () => ({
  getApiBaseUrl: () => "http://127.0.0.1:8000",
  api: {
    knowledgeIntelligence: {
      getGraph: vi.fn(async () => ({ nodes: [], edges: [], metadata: {} })),
      getDomains: vi.fn(async () => []),
    },
    verification: {
      ensureTargetCase: vi.fn(async () => ({ id: "case-1" })),
    },
    assistant: {
      listConversations: vi.fn(async () => []),
      getConversation: vi.fn(async () => ({ messages: [] })),
    },
  },
}));

import { ProjectsList } from "../components/figma-pages/ProjectsPage";
import { KnowledgePage } from "../components/figma-pages/KnowledgePage";
import { HandoversPage } from "../components/figma-pages/HandoversPage";
import { AIAssistantThinking } from "../components/loading/AIAssistantThinking";
import { FigmaStoreProvider } from "../lib/figmaStore";

describe("Organisation Switching, State Reset & Loading States", () => {
  beforeEach(() => {
    mockPush.mockClear();
    mockContextState = {
      user: { id: "u1", full_name: "Test User", email: "test@example.com" },
      activeOrg: { id: "org-new", name: "Empty Org", slug: "empty-org" },
      organisations: [{ id: "org-new", name: "Empty Org", slug: "empty-org" }],
      projects: [],
      activeProject: null,
      overview: null,
      members: [],
      sourceMappings: [],
      evidenceList: [],
      findings: [],
      handoverCases: [],
      verificationSummary: null,
      isCreatingOrg: false,
      isCreatingProject: false,
      isLoadingOrganisations: false,
      isLoadingProjects: false,
      setIsCreateProjectModalOpen: vi.fn(),
      setActiveProject: vi.fn(),
    };
  });

  it("renders empty state in ProjectsList when organization has 0 projects and not creating", () => {
    render(
      <FigmaStoreProvider>
        <ProjectsList />
      </FigmaStoreProvider>
    );
    expect(screen.getByText("No projects yet")).toBeDefined();
    expect(screen.getByText(/Create a project to connect sources/i)).toBeDefined();
  });

  it("renders pulsating loading card in ProjectsList when isCreatingProject is true", () => {
    mockContextState.isCreatingProject = true;
    render(
      <FigmaStoreProvider>
        <ProjectsList />
      </FigmaStoreProvider>
    );
    expect(screen.getByText("Creating project workspace...")).toBeDefined();
    expect(screen.getByText(/Provisioning isolated repository & knowledge indexes/i)).toBeDefined();
  });

  it("renders empty state in KnowledgePage when no project is selected in the current organisation", () => {
    render(<KnowledgePage view="knowledge" />);
    expect(screen.getByText("No project workspace selected")).toBeDefined();
    expect(
      screen.getByText(/Select or create a project workspace in this organisation to view knowledge intelligence/i)
    ).toBeDefined();
  });

  it("renders empty state in HandoversPage workspace view when no project is selected", () => {
    render(<HandoversPage view="workspace" />);
    expect(screen.getByText("No project workspace selected")).toBeDefined();
    expect(
      screen.getByText(/Select or create a project workspace in this organisation to view or create handover packages/i)
    ).toBeDefined();
  });

  it("renders AIAssistantThinking with elapsed timer and progressive reasoning steps", () => {
    render(
      <AIAssistantThinking
        stage="retrieving"
        elapsedSeconds={7}
      />
    );
    expect(screen.getByText("Knowledge Assistant")).toBeDefined();
    expect(screen.getByText("7s")).toBeDefined();
    expect(screen.getByText("Hybrid retrieval (ChromaDB vectors + PostgreSQL FTS)...")).toBeDefined();
    expect(screen.getByText("Retrieve")).toBeDefined();
    expect(screen.getByText("Synthesize")).toBeDefined();
  });
});
