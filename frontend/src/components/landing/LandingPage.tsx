"use client";

import React, { useEffect } from "react";
import { BrandIntro } from "./BrandIntro";
import { LandingNav } from "./LandingNav";
import { ReadingProgressBar } from "./ReadingProgressBar";
import { BackToTop } from "./BackToTop";
import { HeroSection } from "./HeroSection";
import { SectionDivider } from "./SectionDivider";
import { ProblemSection } from "./ProblemSection";
import { IntroducingSection } from "./IntroducingSection";
import { HowItWorksSection } from "./HowItWorksSection";
import { ConnectedSourcesSection } from "./ConnectedSourcesSection";
import { EvidenceCenterSection } from "./EvidenceCenterSection";
import { IntelligenceSection } from "./IntelligenceSection";
import { ExplorerSection } from "./ExplorerSection";
import { KnowledgeAssistantSection } from "./KnowledgeAssistantSection";
import { HandoversSection } from "./HandoversSection";
import { RolesSection } from "./RolesSection";
import { TrustSection } from "./TrustSection";
import { FaqSection } from "./FaqSection";
import { FinalCtaSection } from "./FinalCtaSection";
import { LandingFooter } from "./LandingFooter";

export function LandingPage() {
  useEffect(() => {
    if (!window.location.hash) {
      window.scrollTo(0, 0);
    }
  }, []);

  return (
    <div className="ambient-canvas min-h-screen w-full max-w-full overflow-x-clip text-[#203653] font-sans antialiased selection:bg-[#315FBA]/15 selection:text-[#203653]">
      {/* Global Reading Progress Bar (2.5px gradient indicator) */}
      <ReadingProgressBar />

      {/* Floating Back to Top Control (appears after scrolling past hero) */}
      <BackToTop />

      {/* SECTION 01 — Cinematic Brand Intro */}
      <BrandIntro />

      {/* Global Sticky Glass Navigation */}
      <LandingNav />

      <main>
        {/* SECTION 02 — Hero */}
        <HeroSection />

        <SectionDivider label="SEC_03 // THE_PROBLEM" />

        {/* SECTION 03 — The Problem */}
        <ProblemSection />

        <SectionDivider label="SEC_04 // INTRODUCING_HANDOVER" />

        {/* SECTION 04 — Introducing Handover */}
        <IntroducingSection />

        <SectionDivider label="SEC_05 // HOW_IT_WORKS" />

        {/* SECTION 05 — How It Works (CONNECT -> RECONSTRUCT -> VERIFY -> REVIEW -> HANDOVER) */}
        <HowItWorksSection />

        <SectionDivider label="SEC_06 // CONNECTED_SOURCES" />

        {/* SECTION 06 — Connected Sources */}
        <ConnectedSourcesSection />

        <SectionDivider label="SEC_07 // EVIDENCE_RECONSTRUCTION" />

        {/* SECTION 07 — Evidence Reconstruction */}
        <EvidenceCenterSection />

        <SectionDivider label="SEC_08 // EIGHT_KNOWLEDGE_DOMAINS" />

        {/* SECTION 08 — Eight Knowledge Domains */}
        <IntelligenceSection />

        <SectionDivider label="SEC_09 // RELATIONSHIP_EXPLORER" />

        {/* SECTION 09 — Relationship Explorer */}
        <ExplorerSection />

        <SectionDivider label="SEC_10 // KNOWLEDGE_ASSISTANT" />

        {/* SECTION 10 — Knowledge Assistant */}
        <KnowledgeAssistantSection />

        <SectionDivider label="SEC_11 // HANDOVER_DOSSIER" />

        {/* SECTION 11 — Handover Dossier */}
        <HandoversSection />

        <SectionDivider label="SEC_12 // ROLE_CONTINUITY" />

        {/* SECTION 12 — Role Continuity */}
        <RolesSection />

        <SectionDivider label="SEC_13 // TRUST_AND_VERIFICATION" />

        {/* SECTION 13 — Trust & Verification (4 Epistemic Layers) */}
        <TrustSection />

        <SectionDivider label="SEC_14 // FREQUENTLY_ASKED" />

        {/* SECTION 14 — FAQ */}
        <FaqSection />

        {/* SECTION 15 — Final CTA */}
        <FinalCtaSection />
      </main>

      {/* Global Footer */}
      <LandingFooter />
    </div>
  );
}

export default LandingPage;
