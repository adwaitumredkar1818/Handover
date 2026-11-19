import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

const mockPush = vi.fn();
const mockSetIsCreateProjectModalOpen = vi.fn();
const mockCreateProject = vi.fn(async (data: { name: string }) => ({
  id: "proj-new-123",
  name: data.name,
  slug: "new-proj",
  status: "active",
  organisation_id: "org-1",
}));
const mockSetActiveProject = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
  usePathname: () => "/dashboard",
  useParams: () => ({}),
}));

vi.mock("../context/LiveAppContext", () => ({
  useLiveApp: () => ({
    user: { id: "u1", full_name: "Vernit Garg", email: "vernit@example.com" },
    activeOrg: { id: "org-1", name: "The Sapiens", slug: "the-sapiens" },
    organisations: [{ id: "org-1", name: "The Sapiens", slug: "the-sapiens" }],
    projects: [],
    activeProject: null,
    overview: null,
    members: [],
    sourceMappings: [],
    handoverCases: [],
    findings: [],
    verificationSummary: null,
    isCreateProjectModalOpen: false,
    setIsCreateProjectModalOpen: mockSetIsCreateProjectModalOpen,
    createProject: mockCreateProject,
    setActiveProject: mockSetActiveProject,
  }),
}));

vi.mock("../lib/api", () => ({
  api: {
    organisations: {
      listMembers: vi.fn(async () => [
        { user_id: "u1", full_name: "Vernit Garg", email: "vernit@example.com" },
      ]),
    },
    members: {
      add: vi.fn(async () => ({})),
    },
  },
}));

import { DashboardPage } from "../components/figma-pages/DashboardPage";
import { ProjectCreationWizard } from "../components/project-workspace/ProjectCreationWizard";

describe("Dashboard & Shared Project Creation Flow", () => {
  beforeEach(() => {
    mockPush.mockClear();
    mockSetIsCreateProjectModalOpen.mockClear();
    mockCreateProject.mockClear();
    mockSetActiveProject.mockClear();
  });

  it("Dashboard 'New project' and 'Create project' buttons open the shared CreateProjectModal instead of a fake store route", () => {
    render(<DashboardPage />);
    const newProjBtn = screen.getByRole("button", { name: /New project/i });
    fireEvent.click(newProjBtn);
    expect(mockSetIsCreateProjectModalOpen).toHaveBeenCalledWith(true);
    expect(mockPush).not.toHaveBeenCalledWith("/projects/new");
  });

  it("ProjectCreationWizard submits real project data through createProject and navigates on success", async () => {
    const onSuccess = vi.fn();
    render(<ProjectCreationWizard isModal={true} onSuccess={onSuccess} />);

    const nameInput = screen.getByPlaceholderText(/e\.g\. Billing Infrastructure Modernisation/i);
    fireEvent.change(nameInput, { target: { value: "Conark Handover" } });

    // Step 0 -> Step 1 -> Step 2 -> Create
    fireEvent.click(screen.getByRole("button", { name: /Continue|Next/i }));
    fireEvent.click(screen.getByRole("button", { name: /Continue|Next/i }));
    fireEvent.click(screen.getByRole("button", { name: /Create Project Workspace/i }));

    await waitFor(() => {
      expect(mockCreateProject).toHaveBeenCalledTimes(1);
    });
    expect(mockCreateProject).toHaveBeenCalledWith(
      expect.objectContaining({ name: "Conark Handover" }),
      expect.objectContaining({ orgId: "org-1" })
    );
    await waitFor(() => {
      expect(onSuccess).toHaveBeenCalledWith(expect.objectContaining({ id: "proj-new-123" }));
    });
  });
});
