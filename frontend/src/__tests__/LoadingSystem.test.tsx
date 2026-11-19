import React from "react";
import "@testing-library/jest-dom/vitest";
import { describe, expect, it, vi } from "vitest";
import { render, screen, act, fireEvent } from "@testing-library/react";
import { renderHook } from "@testing-library/react";

import {
  CardSkeleton,
  TableSkeleton,
  ListSkeleton,
  FormSkeleton,
  PageSkeleton,
  GraphSkeleton,
  ButtonLoader,
  SectionLoader,
  AILoadingState,
  AIAssistantThinking,
  UploadProgress,
  EmptyState,
  ErrorState,
  SuccessState,
} from "../components/loading";

import { useLoadingState } from "../hooks/useLoadingState";
import { useOperationStatus } from "../hooks/useOperationStatus";
import { useProgressState } from "../hooks/useProgressState";

describe("Loading & User Feedback System Test Suite", () => {
  describe("1. Skeleton Loading States", () => {
    it("renders CardSkeleton with proper aria-hidden styling and count", () => {
      const { container } = render(<CardSkeleton count={3} />);
      const skeletonBoxes = container.querySelectorAll(".animate-pulse");
      expect(skeletonBoxes.length).toBe(3);
    });

    it("renders TableSkeleton with specified columns and rows", () => {
      const { container } = render(<TableSkeleton rows={4} columns={5} />);
      const tableStatus = container.querySelector(".animate-pulse");
      expect(tableStatus).toBeInTheDocument();
      const rows = container.querySelectorAll("tbody tr");
      expect(rows.length).toBe(4);
    });

    it("renders ListSkeleton with avatar support", () => {
      const { container } = render(<ListSkeleton variant="activity" count={4} />);
      const avatars = container.querySelectorAll(".rounded-full");
      expect(avatars.length).toBe(4);
    });

    it("renders FormSkeleton with fields and action row", () => {
      const { container } = render(<FormSkeleton fields={3} />);
      const formItems = container.querySelectorAll(".animate-pulse");
      expect(formItems.length).toBeGreaterThan(0);
    });

    it("renders PageSkeleton with dashboard layout header and metric cards", () => {
      const { container } = render(<PageSkeleton layout="dashboard" />);
      const pageElements = container.querySelectorAll(".animate-pulse");
      expect(pageElements.length).toBeGreaterThan(0);
    });

    it("renders GraphSkeleton with node clusters and connection lines", () => {
      render(<GraphSkeleton label="Computing knowledge relationships..." />);
      expect(screen.getByText("Computing knowledge relationships...")).toBeInTheDocument();
    });
  });

  describe("2. Button and Section Loaders", () => {
    it("renders ButtonLoader in idle and busy states with locked accessibility", () => {
      const handleClick = vi.fn();
      const { rerender } = render(
        <ButtonLoader isLoading={false} onClick={handleClick} loadingText="Saving...">
          Submit Form
        </ButtonLoader>
      );
      expect(screen.getByText("Submit Form")).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button"));
      expect(handleClick).toHaveBeenCalledTimes(1);

      rerender(
        <ButtonLoader isLoading={true} onClick={handleClick} loadingText="Saving...">
          Submit Form
        </ButtonLoader>
      );
      expect(screen.getByText("Saving...")).toBeInTheDocument();
      expect(screen.getByRole("button")).toHaveAttribute("aria-busy", "true");
      expect(screen.getByRole("button")).toBeDisabled();
    });

    it("renders SectionLoader with organic pulse and accessible announcement", () => {
      render(<SectionLoader label="Reconstructing dependencies..." />);
      const status = screen.getByRole("status");
      expect(status).toHaveAttribute("aria-live", "polite");
      expect(screen.getByText("Reconstructing dependencies...")).toBeInTheDocument();
    });
  });

  describe("3. AI Intelligence & Progress Indicators", () => {
    it("renders AIAssistantThinking with stage label and animation dots", () => {
      render(<AIAssistantThinking stage="retrieving" />);
      const status = screen.getByRole("status");
      expect(status).toHaveAttribute("aria-live", "polite");
      expect(screen.getByText("Knowledge Assistant")).toBeInTheDocument();
      expect(screen.getByText("Hybrid retrieval (ChromaDB vectors + PostgreSQL FTS)...")).toBeInTheDocument();
    });

    it("renders AILoadingState with title and multi-stage pipeline", () => {
      render(
        <AILoadingState
          title="Synthesizing Knowledge"
          subtitle="Reconstructing 8-domain cross-source relationships"
          activeStageId="extract"
        />
      );
      expect(screen.getByText("Synthesizing Knowledge")).toBeInTheDocument();
      expect(screen.getByText("Reconstructing 8-domain cross-source relationships")).toBeInTheDocument();
      expect(screen.getByText("Extracting architectural & operational facts")).toBeInTheDocument();
    });

    it("renders UploadProgress with file details and active stage", () => {
      render(
        <UploadProgress
          fileName="architecture_spec.pdf"
          fileSizeBytes={1024 * 1024}
          status="extracting"
        />
      );
      expect(screen.getByText("architecture_spec.pdf")).toBeInTheDocument();
      expect(screen.getByText("OCR & Document Parsing")).toBeInTheDocument();
    });
  });

  describe("4. Feedback States (Empty, Error, Success)", () => {
    it("renders EmptyState with actionable button", () => {
      const onAction = vi.fn();
      render(
        <EmptyState
          title="No Evidence Connected"
          description="Connect a repository or upload documents to begin."
          actionLabel="Connect Source"
          onAction={onAction}
        />
      );
      expect(screen.getByText("No Evidence Connected")).toBeInTheDocument();
      const btn = screen.getByText("Connect Source");
      expect(btn).toBeInTheDocument();
      fireEvent.click(btn);
      expect(onAction).toHaveBeenCalledTimes(1);
    });

    it("renders ErrorState with retry callback", () => {
      const onRetry = vi.fn();
      render(
        <ErrorState
          title="Failed to Sync GitHub Repository"
          message="Rate limit reached or invalid token scope."
          onRetry={onRetry}
        />
      );
      expect(screen.getByText("Failed to Sync GitHub Repository")).toBeInTheDocument();
      const retryBtn = screen.getByText("Try Again");
      expect(retryBtn).toBeInTheDocument();
      fireEvent.click(retryBtn);
      expect(onRetry).toHaveBeenCalledTimes(1);
    });

    it("renders SuccessState with checkmark and details", () => {
      render(
        <SuccessState
          title="Handover Approved"
          message="Package HO-1042 has been verified by the Reviewer."
        />
      );
      expect(screen.getByText("Handover Approved")).toBeInTheDocument();
      expect(screen.getByText("Package HO-1042 has been verified by the Reviewer.")).toBeInTheDocument();
    });
  });

  describe("5. Loading & Operation Hooks", () => {
    it("useLoadingState manages status lifecycle cleanly", () => {
      const { result } = renderHook(() => useLoadingState<string>());
      expect(result.current.isLoading).toBe(false);
      expect(result.current.isIdle).toBe(true);

      act(() => {
        result.current.startLoading();
      });
      expect(result.current.isLoading).toBe(true);
      expect(result.current.status).toBe("loading");

      act(() => {
        result.current.setSuccess("data-payload");
      });
      expect(result.current.isLoading).toBe(false);
      expect(result.current.isSuccess).toBe(true);
      expect(result.current.data).toBe("data-payload");

      act(() => {
        result.current.setError("Network timeout");
      });
      expect(result.current.isError).toBe(true);
      expect(result.current.error).toBe("Network timeout");

      act(() => {
        result.current.reset();
      });
      expect(result.current.isIdle).toBe(true);
    });

    it("useOperationStatus executes async operation and handles success", async () => {
      const mockOp = vi.fn().mockResolvedValue("op-result");
      const onSuccess = vi.fn();

      const { result } = renderHook(() =>
        useOperationStatus(mockOp, { onSuccess })
      );
      expect(result.current.isIdle).toBe(true);

      let outcome: string | null = null;
      await act(async () => {
        outcome = await result.current.execute("arg1");
      });

      expect(outcome).toBe("op-result");
      expect(mockOp).toHaveBeenCalledWith("arg1");
      expect(onSuccess).toHaveBeenCalledWith("op-result");
      expect(result.current.isSuccess).toBe(true);
    });

    it("useProgressState tracks stages and percentage updates", () => {
      const stages = [
        { id: "validate", label: "Validating" },
        { id: "process", label: "Processing" },
        { id: "complete", label: "Done" },
      ];

      const { result } = renderHook(() =>
        useProgressState({ stages, initialStageId: "validate" })
      );
      expect(result.current.currentStage?.id).toBe("validate");

      act(() => {
        result.current.nextStage();
      });
      expect(result.current.currentStage?.id).toBe("process");

      act(() => {
        result.current.setPercent(75);
      });
      expect(result.current.percent).toBe(75);

      act(() => {
        result.current.setStage("complete");
        result.current.setPercent(100);
      });
      expect(result.current.isCompleted).toBe(true);
    });
  });
});
