import React from "react";
import "@testing-library/jest-dom/vitest";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

const mockOrganicScene = vi.fn(({ variant }: { variant?: string }) => (
  <div data-testid={`organic-scene-${variant}`} />
));

vi.mock("../components/brand/OrganicScene", () => ({
  OrganicScene: (props: { variant?: string }) => mockOrganicScene(props),
}));

vi.mock("next/image", () => ({
  default: (props: React.ImgHTMLAttributes<HTMLImageElement> & { priority?: boolean }) => {
    const { priority: _priority, ...rest } = props;
    // eslint-disable-next-line @next/next/no-img-element
    return <img {...rest} alt={props.alt ?? ""} />;
  },
}));

import { BrandIntro } from "../components/landing/BrandIntro";
import FigmaOrganicScene from "../components/figma-ui/OrganicScene";

describe("Brand Animation Restoration", () => {
  beforeEach(() => {
    sessionStorage.clear();
    window.history.replaceState({}, "", "/");
    vi.stubGlobal(
      "matchMedia",
      vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }))
    );
    mockOrganicScene.mockClear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders BrandIntro with all brand elements, locks scroll while active, and restores on skip", () => {
    render(<BrandIntro />);

    expect(screen.getByRole("region", { name: "Handover Brand Introduction" })).toBeInTheDocument();
    expect(screen.getByTestId("organic-scene-cinematic")).toBeInTheDocument();
    expect(screen.getByAltText("Handover Symbol")).toBeInTheDocument();
    expect(screen.getByAltText("Handover")).toBeInTheDocument();
    expect(screen.getByText("Knowledge Continues.")).toBeInTheDocument();
    expect(
      screen.getByText("Prevent Critical Knowledge From Leaving With People.")
    ).toBeInTheDocument();
    expect(document.body.style.overflow).toBe("hidden");

    fireEvent.click(screen.getByRole("button", { name: "Skip brand intro" }));
    expect(screen.queryByRole("region", { name: "Handover Brand Introduction" })).not.toBeInTheDocument();
    expect(document.body.style.overflow).toBe("");
    expect(sessionStorage.getItem("handover_intro_seen")).toBe("1");
  });

  it("skips BrandIntro on subsequent visits unless replay=1 is set", () => {
    sessionStorage.setItem("handover_intro_seen", "1");
    const { unmount } = render(<BrandIntro />);

    expect(screen.queryByRole("region", { name: "Handover Brand Introduction" })).not.toBeInTheDocument();
    unmount();

    window.history.replaceState({}, "", "/?replay=1");
    render(<BrandIntro />);
    expect(screen.getByRole("region", { name: "Handover Brand Introduction" })).toBeInTheDocument();
  });

  it("delegates figma-ui OrganicScene to the real brand OrganicScene and maps idle to hero", () => {
    render(<FigmaOrganicScene variant="idle" />);
    expect(screen.getByTestId("organic-scene-hero")).toBeInTheDocument();

    render(<FigmaOrganicScene variant="cinematic" dark />);
    expect(screen.getByTestId("organic-scene-cinematic")).toBeInTheDocument();
  });
});
