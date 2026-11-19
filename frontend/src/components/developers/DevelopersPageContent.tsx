"use client";

import React from "react";
import Link from "next/link";
import { ArrowLeft, Users, Sparkles, Terminal } from "lucide-react";
import { LandingNav } from "../landing/LandingNav";
import { LandingFooter } from "../landing/LandingFooter";
import { DeveloperCard } from "./DeveloperCard";
import { DeveloperEnergyEffect } from "./DeveloperEnergyEffect";
import { DevelopersGridCanvas } from "./DevelopersGridCanvas";
import { DEVELOPERS } from "./data";

export function DevelopersPageContent() {
  return (
    <div className="relative min-h-screen flex flex-col bg-[#F6F8FC] text-[#203653] font-sans antialiased selection:bg-[#315FBA] selection:text-white overflow-x-hidden">
      {/* Interactive Background Canvas Grid Effect — Developers Page Only */}
      <DevelopersGridCanvas />

      {/* Main Foreground Container */}
      <div className="relative z-10 flex flex-col min-h-screen">
        {/* Top Navigation Bar — Preserves Handover's Exact Navigation */}
        <LandingNav />

        {/* Main Content Area */}
        <main className="flex-1 pb-24">
          {/* Breadcrumb / Back Navigation */}
          <div className="mx-auto w-full max-w-[1360px] px-5 sm:px-8 pt-8">
            <Link
              href="/"
              className="inline-flex items-center gap-2 text-xs font-semibold text-[#718096] hover:text-[#315FBA] transition-colors group"
            >
              <ArrowLeft className="size-3.5 transition-transform group-hover:-translate-x-1" />
              <span>Back to The Handover</span>
            </Link>
          </div>

          {/* Section 1: Page Introduction */}
          <section className="mx-auto w-full max-w-[1360px] px-5 sm:px-8 pt-6 pb-12 sm:pb-16 text-center">
            {/* Tag / Category Badge */}
            <div className="inline-flex items-center gap-2 rounded-full border border-[#D9E1F0] bg-white/90 backdrop-blur-xs px-3.5 py-1 text-[11.5px] font-bold tracking-wider text-[#315FBA] uppercase shadow-xs mb-4">
              <Users className="size-3.5 text-[#315FBA]" />
              <span>The Team Behind The Platform</span>
            </div>

            {/* Canonical Heading */}
            <h1 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold text-[#112034] tracking-tight max-w-2xl mx-auto leading-tight">
              Meet the Developers
            </h1>

            {/* Canonical Supporting Text */}
            <p className="mt-4 text-[15px] sm:text-[16.5px] leading-relaxed text-[#4A5D78] max-w-2xl mx-auto">
              Behind Handover is a team of developers building a smarter way to preserve project knowledge, simplify collaboration, and make every project easier to continue.
            </p>

            <div className="mt-6 flex flex-wrap items-center justify-center gap-3 text-xs text-[#718096]">
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-md bg-white/90 backdrop-blur-xs border border-[#D9E1F0]">
                <Terminal className="size-3 text-[#315FBA]" />
                <span>Full-Stack Engineering</span>
              </span>
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-md bg-white/90 backdrop-blur-xs border border-[#D9E1F0]">
                <Sparkles className="size-3 text-[#299B80]" />
                <span>AI & Knowledge Graph Architecture</span>
              </span>
            </div>
          </section>

          {/* Section 2: Developer Cards with Cyan Energy Platform Underneath */}
          <section
            className="mx-auto w-full max-w-[1540px] px-4 sm:px-6 lg:px-8"
            aria-label="Developer Profiles"
          >
            {/* Responsive Layout: Desktop 4 cards in one row, Medium 2 cards, Mobile 1 card */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-y-16 gap-x-8 lg:gap-x-10 justify-items-center">
              {DEVELOPERS.map((dev, idx) => (
                <div
                  key={dev.id}
                  className="flex flex-col items-center w-[340px]"
                >
                  {/* Primary Developer Card (Enhanced Uiverse.io Card) */}
                  <DeveloperCard
                    developer={dev}
                    priority={idx < 2}
                  />

                  {/* Animated Sci-Fi Cyan Energy Pedestal with Tilted Angled Hologram Beam */}
                  <DeveloperEnergyEffect
                    ariaLabel={`Energy platform illuminating ${dev.name}'s card`}
                  />
                </div>
              ))}
            </div>
          </section>
        </main>

        {/* Website Footer — Preserves Handover's Exact Footer */}
        <LandingFooter />
      </div>
    </div>
  );
}
