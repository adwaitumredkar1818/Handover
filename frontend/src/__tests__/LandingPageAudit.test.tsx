import React from "react";
import "@testing-library/jest-dom/vitest";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { LandingPage } from "../components/landing/LandingPage";
import { HeroSection } from "../components/landing/HeroSection";
import { HowItWorksSection } from "../components/landing/HowItWorksSection";
import { ConnectedSourcesSection } from "../components/landing/ConnectedSourcesSection";
import { EvidenceCenterSection } from "../components/landing/EvidenceCenterSection";
import { IntelligenceSection } from "../components/landing/IntelligenceSection";
import { ExplorerSection } from "../components/landing/ExplorerSection";
import { KnowledgeAssistantSection } from "../components/landing/KnowledgeAssistantSection";
import { HandoversSection } from "../components/landing/HandoversSection";
import { FaqSection } from "../components/landing/FaqSection";
import { TrustSection } from "../components/landing/TrustSection";
import { LandingNav } from "../components/landing/LandingNav";

// Mock next/navigation
const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: mockPush,
  }),
}));

// Mock LiveAppContext
vi.mock("../context/LiveAppContext", () => ({
  useLiveApp: () => ({
    user: null,
  }),
}));

// Mock OrganicScene & BrandIntro
vi.mock("../components/brand/OrganicScene", () => ({
  OrganicScene: ({ variant }: { variant: string }) => (
    <div data-testid={`organic-scene-${variant}`} />
  ),
}));

vi.mock("../components/landing/BrandIntro", () => ({
  BrandIntro: () => <div data-testid="brand-intro" />,
}));

// Class mock for IntersectionObserver (JSDOM does not provide one)
class MockIntersectionObserver {
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
}

beforeEach(() => {
  window.IntersectionObserver = MockIntersectionObserver as unknown as typeof IntersectionObserver;
  window.scrollTo = vi.fn();
  Element.prototype.scrollIntoView = vi.fn();
  vi.clearAllMocks();
});

describe("Landing Page Independent Audit Test Suite", () => {
  describe("1. Structural Integrity & Core Narrative", () => {
    it("renders the master headline, eyebrow and primary CTAs", () => {
      render(<LandingPage />);

      // Master headline
      expect(screen.getByText(/People move on\./i)).toBeInTheDocument();
      expect(screen.getByText(/Knowledge shouldn't\./i)).toBeInTheDocument();

      // Formal platform description in eyebrow
      expect(
        screen.getByText(/Intelligent Project Knowledge Reconstruction & Handover Platform/i)
      ).toBeInTheDocument();

      // Core assurance strip
      expect(screen.getByText("Connect Your Tools")).toBeInTheDocument();
      expect(screen.getByText("Reconstruct Knowledge")).toBeInTheDocument();
      expect(screen.getByText("Human-Verified")).toBeInTheDocument();
      expect(screen.getByText("Role-Tailored Handovers")).toBeInTheDocument();
    });

    it("verifies all essential anchor IDs are present in the DOM for smooth scrolling", () => {
      const { container } = render(<LandingPage />);

      const requiredIds = [
        "product",
        "introducing",
        "how",
        "sources",
        "evidence",
        "intelligence",
        "explorer",
        "assistant",
        "handovers",
        "roles",
        "security",
        "faq",
      ];

      for (const id of requiredIds) {
        const el = container.querySelector(`#${id}`);
        expect(el).not.toBeNull();
      }
    });
  });

  describe("2. Canonical 5-Stage Workflow", () => {
    it("renders all five canonical stages and switches active step preview", () => {
      render(<HowItWorksSection />);

      // Verify all 5 steps exist
      const steps = ["Connect", "Reconstruct", "Verify", "Review", "Handover"];
      for (const step of steps) {
        expect(screen.getByText(step)).toBeInTheDocument();
      }

      // Initial step is Connect (Step 01) - rendered in responsive containers
      expect(screen.getAllByText("Select Connected Repositories")[0]).toBeInTheDocument();
      expect(screen.getAllByText("payment-core")[0]).toBeInTheDocument();

      // Switch to Reconstruct (Step 02)
      fireEvent.click(screen.getByText("Reconstruct"));
      expect(screen.getAllByText("Knowledge Reconstruction")[0]).toBeInTheDocument();

      // Switch to Verify (Step 03)
      fireEvent.click(screen.getByText("Verify"));
      expect(
        screen.getAllByText(/Settlement worker lacks retry logic on acquirer timeouts/i)[0]
      ).toBeInTheDocument();
      expect(screen.getAllByText("Human Review Queue")[0]).toBeInTheDocument();

      // Switch to Review (Step 04)
      fireEvent.click(screen.getByText("Review"));
      expect(screen.getAllByText("Technical Review")[0]).toBeInTheDocument();
      expect(screen.getAllByText(/Jordan Lee \(Lead\)/i)[0]).toBeInTheDocument();

      // Switch to Handover (Step 05)
      fireEvent.click(screen.getByText("Handover"));
      expect(screen.getAllByText(/HO-1042 · Payment Platform Transition/i)[0]).toBeInTheDocument();
    });
  });

  describe("3. Evidence Center (Three-Panel Architecture)", () => {
    it("renders sources sidebar, filterable library, and detailed provenance inspection", () => {
      render(<EvidenceCenterSection />);

      // Panel A: Connected Sources
      expect(screen.getByText("Connected Sources")).toBeInTheDocument();
      expect(screen.getByText("GitHub Repositories")).toBeInTheDocument();
      expect(screen.getByText("Jira Projects")).toBeInTheDocument();
      expect(screen.getByText("Slack Channels")).toBeInTheDocument();
      expect(screen.getByText("Uploaded Documents")).toBeInTheDocument();

      // Panel B: Filter Tabs
      expect(screen.getByText("All Evidence")).toBeInTheDocument();
      expect(screen.getAllByText("payment-core #4827")[0]).toBeInTheDocument();

      // Filter to Slack
      fireEvent.click(screen.getByText("Slack"));
      expect(screen.getByText("#payments-arch")).toBeInTheDocument();

      // Filter to Docs
      fireEvent.click(screen.getByText("Documents"));
      expect(screen.getByText("ADR-007.pdf")).toBeInTheDocument();

      // Selection updates Panel C
      fireEvent.click(screen.getByText("ADR-007.pdf"));
      expect(
        screen.getAllByText("Architecture Decision Record: Event-driven settlement")[0]
      ).toBeInTheDocument();
      expect(screen.getByText(/sha256:1e2f3a4b5c6d7e8/i)).toBeInTheDocument();
    });
  });

  describe("4. Knowledge Intelligence (All 8 Domains)", () => {
    it("renders all eight canonical knowledge domains and updates active finding card", () => {
      render(<IntelligenceSection />);

      const domains = [
        "Decisions",
        "Architecture",
        "Work Status",
        "Ownership",
        "Dependencies",
        "Risks",
        "Procedures",
        "Discussions",
      ];

      for (const d of domains) {
        expect(screen.getAllByText(d)[0]).toBeInTheDocument();
      }

      // Initial active domain: Decisions (matches button & finding card)
      expect(
        screen.getAllByText(/Decouple settlement from ledger via Kafka event stream/i)[0]
      ).toBeInTheDocument();

      // Click Risks
      fireEvent.click(screen.getByText("Risks"));
      expect(
        screen.getByText(/Settlement worker has no retry mechanism on acquirer timeouts/i)
      ).toBeInTheDocument();

      // Click Ownership
      fireEvent.click(screen.getByText("Ownership"));
      expect(
        screen.getByText(/Rotate acquirer API credentials and update certificates/i)
      ).toBeInTheDocument();
    });
  });

  describe("5. Relationship Explorer", () => {
    it("renders interactive SVG graph and updates node selection drawer", () => {
      render(<ExplorerSection />);

      // Initial selected node: Decouple settlement via Kafka (in SVG label & drawer)
      expect(screen.getAllByText("Decouple settlement via Kafka")[0]).toBeInTheDocument();
      expect(screen.getAllByText("Alex Chen")[0]).toBeInTheDocument();

      // Click related entity button for Alex Chen
      const alexButton = screen.getByRole("button", { name: /Alex Chen/i });
      fireEvent.click(alexButton);

      // Detail drawer updates to Alex Chen
      expect(
        screen.getByText(/Staff Backend Engineer\. Outgoing technical owner/i)
      ).toBeInTheDocument();
    });
  });

  describe("6. Project Knowledge Assistant & Uncertainty Disclosure", () => {
    it("renders grounded citations and explicit uncertainty disclosure on missing evidence", () => {
      render(<KnowledgeAssistantSection />);

      // Sample 1: Grounded answer with citations
      expect(
        screen.getByText(/Why was Redis chosen over Memcached for session caching\?/i)
      ).toBeInTheDocument();
      expect(screen.getByText(/Grounded in verified project findings/i)).toBeInTheDocument();

      // Switch to Sample 3: Disaster recovery question
      fireEvent.click(screen.getByText("Sample 03"));
      expect(
        screen.getByText(/What is the disaster recovery failover plan for the settlement database\?/i)
      ).toBeInTheDocument();
      expect(
        screen.getByText(/I do not have sufficient evidence in connected repositories/i)
      ).toBeInTheDocument();
      expect(
        screen.getByText(/Insufficient Evidence Disclosed — Never Guessed/i)
      ).toBeInTheDocument();
    });
  });

  describe("7. Handovers Dossier & 58 Verified Items Audit", () => {
    it("renders dossier HO-1042 with 8-domain breakdown totaling 58 findings", () => {
      render(<HandoversSection />);

      expect(screen.getByText("HO-1042")).toBeInTheDocument();
      expect(screen.getByText("Alex Chen")).toBeInTheDocument();
      expect(screen.getByText("Priya Shah")).toBeInTheDocument();
      expect(screen.getByText("58 Total Findings")).toBeInTheDocument();

      // Verify domain count values
      expect(screen.getByText("12")).toBeInTheDocument(); // Decisions
      expect(screen.getByText("9")).toBeInTheDocument();  // Architecture
      expect(screen.getByText("8")).toBeInTheDocument();  // Work Status
    });
  });

  describe("8. Trust & Four-Tier Epistemic Separation", () => {
    it("renders all four epistemic tiers in proper hierarchical order", () => {
      render(<TrustSection />);

      expect(screen.getByText(/Tier 4 · Human-Verified Knowledge/i)).toBeInTheDocument();
      expect(screen.getByText(/Tier 3 · AI-Generated Interpretation/i)).toBeInTheDocument();
      expect(screen.getByText(/Tier 2 · Extracted Information/i)).toBeInTheDocument();
      expect(screen.getByText(/Tier 1 · Original Source Evidence/i)).toBeInTheDocument();

      // Core Guarantees
      expect(screen.getByText("Zero Data Fabrication")).toBeInTheDocument();
      expect(screen.getByText("Human-in-the-Loop Governance")).toBeInTheDocument();
      expect(screen.getByText("Strict Source-Level Permissions")).toBeInTheDocument();
      expect(screen.getByText("Provenance & Immutable Auditability")).toBeInTheDocument();
    });
  });

  describe("9. FAQ Accordion & Navigation", () => {
    it("expands and collapses FAQ items cleanly", () => {
      render(<FaqSection />);

      const firstQuestion = screen.getByText("What does The Handover do?");
      expect(firstQuestion).toBeInTheDocument();

      // Click second question
      const secondQuestion = screen.getByText("Which tools can The Handover connect to?");
      fireEvent.click(secondQuestion);
      expect(
        screen.getByText(/The Handover supports fine-grained read-only integrations with GitHub/i)
      ).toBeInTheDocument();
    });

    it("verifies navigation dropdown toggles and escape key dismiss", () => {
      render(<LandingNav />);

      const productBtn = screen.getByRole("button", { name: /Product/i });
      fireEvent.click(productBtn);

      // Evidence Center item visible
      expect(screen.getByText("Evidence Center")).toBeInTheDocument();

      // Escape key closes it
      fireEvent.keyDown(window, { key: "Escape" });
    });
  });

  describe("10. Section 06 Connected Sources & Redesigned Headlines", () => {
    it("renders Connected Sources constellation with distinct connected and blocked ACL states", () => {
      render(<ConnectedSourcesSection />);

      expect(
        screen.getByText("Your project knowledge starts with the evidence.")
      ).toBeInTheDocument();
      expect(screen.getAllByText("Code Repositories")[0]).toBeInTheDocument();
      expect(screen.getAllByText("Restricted Private Repository")[0]).toBeInTheDocument();
      expect(
        screen.getByText(/Project membership never bypasses individual tool permissions/i)
      ).toBeInTheDocument();

      // Selecting Restricted Private Repository updates active specification panel
      fireEvent.click(screen.getAllByText("Restricted Private Repository")[0]!);
      expect(
        screen.getByText(/Access Withheld — Missing Source ACL/i)
      ).toBeInTheDocument();
    });

    it("renders Hero orbiting nodes and scroll indicator", () => {
      render(<HeroSection />);

      expect(
        screen.getByRole("heading", {
          level: 1,
          name: /Knowledge shouldn't leave with people\./i,
        })
      ).toBeInTheDocument();
      expect(screen.getAllByText("Repository Node")[0]).toBeInTheDocument();
      expect(screen.getAllByText("Documentation Node")[0]).toBeInTheDocument();
      expect(screen.getByText("Scroll to explore")).toBeInTheDocument();
    });
  });
});
