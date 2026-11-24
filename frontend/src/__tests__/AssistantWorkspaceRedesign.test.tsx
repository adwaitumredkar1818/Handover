import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { AssistantWorkspaceView } from "../components/assistant/AssistantWorkspaceView";
import { AssistantThinking3D } from "../components/assistant/AssistantThinking3D";

// Mock LiveAppContext
const mockAddToast = vi.fn();
vi.mock("../context/LiveAppContext", () => ({
  useLiveApp: () => ({
    activeProject: {
      id: "proj-123",
      name: "Project Workspace",
      slug: "project-workspace",
    },
    user: {
      id: "usr-456",
      email: "standard_user@example.com",
      full_name: "Standard User",
      roles: ["project_manager"],
    },
    addToast: mockAddToast,
  }),
}));

// Mock Next.js Link
vi.mock("next/link", () => ({
  __esModule: true,
  default: ({ children, href, className }: { children: React.ReactNode; href: string; className?: string }) => (
    <a href={href} className={className}>
      {children}
    </a>
  ),
}));

// Mock API
vi.mock("../lib/api", () => ({
  api: {
    assistant: {
      listConversations: vi.fn().mockResolvedValue([
        {
          id: "conv-1",
          project_id: "proj-123",
          title: "Investigation #1",
          created_at: new Date().toISOString(),
          last_message_at: new Date().toISOString(),
          message_count: 2,
        },
      ]),
      getConversation: vi.fn().mockResolvedValue({
        id: "conv-1",
        project_id: "proj-123",
        title: "Investigation #1",
        created_at: new Date().toISOString(),
        messages: [],
      }),
      createConversation: vi.fn().mockResolvedValue({
        id: "conv-2",
        project_id: "proj-123",
        title: "New Investigation",
        created_at: new Date().toISOString(),
        last_message_at: new Date().toISOString(),
        message_count: 0,
      }),
      deleteConversation: vi.fn().mockResolvedValue({ success: true }),
      startInvestigation: vi.fn().mockRejectedValue(new Error("No live SSE in test")),
      askQuestion: vi.fn().mockResolvedValue({
        message_id: "msg-ans-1",
        conversation_id: "conv-1",
        answer: "This is a verified answer grounded in project documents [S1].",
        answer_status: "answered",
        response_mode: "standard",
        citations: [
          {
            citation_label: "S1",
            source_title: "Architecture Specification",
            source_provider: "Document Upload",
            excerpt: "The platform uses FastAPI and PostgreSQL.",
            is_verified: true,
          },
        ],
        claims: [
          {
            claim_text: "FastAPI is the sole identity authority.",
            confidence: 0.98,
            citation_labels: ["S1"],
          },
        ],
      }),
      submitFeedback: vi.fn().mockResolvedValue({ success: true }),
    },
  },
}));

describe("Project Knowledge Assistant UI Redesign Test Suite", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("1. 3D Thinking Animation Component", () => {
    it("renders AssistantThinking3D in idle, compact, and thinking modes with custom labels", () => {
      const { rerender } = render(
        <AssistantThinking3D size="lg" label="Understanding your question..." />
      );
      expect(screen.getByText("Understanding your question...")).toBeInTheDocument();
      expect(screen.getByText(/Searching authorized project sources with zero fabrication/i)).toBeInTheDocument();

      rerender(<AssistantThinking3D size="sm" isThinking={true} label="Reviewing relevant evidence..." />);
      expect(screen.getByText("Reviewing relevant evidence...")).toBeInTheDocument();

      rerender(<AssistantThinking3D size="xs" isThinking={false} />);
      expect(screen.queryByText("Reviewing relevant evidence...")).not.toBeInTheDocument();
    });
  });

  describe("2. Main Workspace, Breadcrumbs & Welcome State", () => {
    it("renders the redesigned header, title, and 2x2 quick action cards", async () => {
      render(<AssistantWorkspaceView />);

      // Top Breadcrumb & Actions
      expect(screen.getByText("AI Assistant")).toBeInTheDocument();
      expect(screen.getAllByText("Project Knowledge Assistant").length).toBeGreaterThanOrEqual(2);
      expect(screen.getByText("New Thread")).toBeInTheDocument();
      expect(screen.getByText("Evidence Center")).toBeInTheDocument();

      // Welcome State Content
      expect(
        screen.getByText(/Ask any question regarding architecture, technical decisions/i)
      ).toBeInTheDocument();

      // Quick Action Cards in 2x2 Grid and Left Panel
      expect(screen.getAllByText("Project Overview & Goals").length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText("Architecture & Tech Stack").length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText("Key Decisions & Rationale").length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText("Ownership & Responsibilities").length).toBeGreaterThanOrEqual(1);
    });
  });

  describe("3. Floating Panels Independent Collapsibility (4 States)", () => {
    it("supports all 4 panel states: both open, left open, right open, both closed", async () => {
      render(<AssistantWorkspaceView />);

      const mainCanvas = screen.getByRole("main");

      // State 1: Both panels open initially
      expect(screen.getByText("Context & History")).toBeInTheDocument();
      expect(screen.getByText("Retrieved Evidence")).toBeInTheDocument();
      expect(mainCanvas).toHaveClass("max-w-2xl xl:max-w-3xl");

      // State 2: Collapse Left Panel (Close button)
      const leftCloseButtons = screen.getAllByTitle("Close panel");
      expect(leftCloseButtons[0]).toBeDefined();
      fireEvent.click(leftCloseButtons[0]!); // Click left close button

      // Left panel collapsed, right remains open
      expect(screen.queryByText("Context & History")).not.toBeInTheDocument();
      expect(screen.getByText("Retrieved Evidence")).toBeInTheDocument();
      expect(mainCanvas).toHaveClass("max-w-3xl xl:max-w-4xl");

      // Edge reopen control for left panel is present
      const leftReopenBtn = screen.getByTitle("Open Context & History");
      expect(leftReopenBtn).toBeInTheDocument();

      // State 3: Collapse Right Panel (Both closed)
      const rightCloseBtn = screen.getByTitle("Close panel");
      fireEvent.click(rightCloseBtn);

      // Both panels closed -> Chat canvas expands to wide centered format
      expect(screen.queryByText("Context & History")).not.toBeInTheDocument();
      expect(screen.queryByText("Retrieved Evidence")).not.toBeInTheDocument();
      expect(mainCanvas).toHaveClass("max-w-4xl xl:max-w-5xl");

      // Both edge reopen controls present
      expect(screen.getByTitle("Open Context & History")).toBeInTheDocument();
      expect(screen.getByTitle("Open Retrieved Evidence")).toBeInTheDocument();

      // State 4: Reopen Right Panel only (Left closed, Right open)
      fireEvent.click(screen.getByTitle("Open Retrieved Evidence"));
      expect(screen.queryByText("Context & History")).not.toBeInTheDocument();
      expect(screen.getByText("Retrieved Evidence")).toBeInTheDocument();
      expect(mainCanvas).toHaveClass("max-w-3xl xl:max-w-4xl");

      // Reopen Left Panel too (Both open again)
      fireEvent.click(screen.getByTitle("Open Context & History"));
      expect(screen.getByText("Context & History")).toBeInTheDocument();
      expect(screen.getByText("Retrieved Evidence")).toBeInTheDocument();
      expect(mainCanvas).toHaveClass("max-w-2xl xl:max-w-3xl");
    });
  });

  describe("4. Minimal Bottom Composer & Settings Popover", () => {
    it("renders minimal composer and toggles '+' popover with modes and search method", async () => {
      render(<AssistantWorkspaceView />);

      const input = screen.getByPlaceholderText(
        "Ask a question about the project (e.g. architecture, ownership, decisions)..."
      );
      expect(input).toBeInTheDocument();

      // Mode pill bar should NOT be cluttering above input
      const plusButton = screen.getByTitle("Assistant Modes & Search Settings");
      expect(plusButton).toBeInTheDocument();

      // Popover should initially be closed
      expect(screen.queryByText("Assistant Settings")).not.toBeInTheDocument();

      // Click '+' button to open settings popover
      fireEvent.click(plusButton);
      expect(screen.getByText("Assistant Settings")).toBeInTheDocument();

      // Verify modes inside popover
      expect(screen.getByText("Deep Research")).toBeInTheDocument();
      expect(screen.getByText("Deep Think")).toBeInTheDocument();
      expect(screen.getByText("Deep Extract")).toBeInTheDocument();
      expect(screen.getByText("Knowledge Domain")).toBeInTheDocument();
      expect(screen.getByText("Search Method")).toBeInTheDocument();

      // Select 'Deep Research' mode
      fireEvent.click(screen.getByText("Deep Research"));

      // Indicator badge should appear next to '+' button
      expect(screen.getByText("Research")).toBeInTheDocument();
    });
  });

  describe("5. Content Simplification & Jargon Reduction", () => {
    it("uses clear, natural wording and eliminates unnecessary technical jargon", () => {
      render(<AssistantWorkspaceView />);

      // Simplified project context explanation
      expect(
        screen.getByText(/Only information you are allowed to access is used. Citations fail-closed./i)
      ).toBeInTheDocument();

      // Empty evidence explanation
      expect(screen.getByText("No Retrieved Evidence")).toBeInTheDocument();
      expect(
        screen.getByText(/Ask a question in the center panel. Authorized supporting records will appear here/i)
      ).toBeInTheDocument();
    });
  });

  describe("6. Active Conversation & Left-Aligned 3D Thinking Response Turn", () => {
    it("submits a question and renders the compact 3D thinking animation on the left answering the user", async () => {
      render(<AssistantWorkspaceView />);

      // Wait for initial conversation and message loading to settle
      await waitFor(() => {
        expect(
          screen.getByPlaceholderText(
            "Ask a question about the project (e.g. architecture, ownership, decisions)..."
          )
        ).toBeInTheDocument();
      });

      const input = screen.getByPlaceholderText(
        "Ask a question about the project (e.g. architecture, ownership, decisions)..."
      );

      // Submit user question
      fireEvent.change(input, { target: { value: "What is the platform identity authority?" } });
      const askBtn = await screen.findByTitle("Ask Question");
      fireEvent.click(askBtn);

      // User question should appear
      await waitFor(() => {
        expect(screen.getByText("What is the platform identity authority?")).toBeInTheDocument();
      });

      // Once the mock resolves, the assistant answer should appear with compact 3D avatar on the left
      await waitFor(() => {
        expect(
          screen.getByText(/This is a verified answer grounded in project documents/i)
        ).toBeInTheDocument();
        expect(screen.getByTitle("Project Knowledge Assistant")).toBeInTheDocument();
        expect(screen.getAllByText("[S1]").length).toBeGreaterThanOrEqual(1);
      });
    });
  });
});
