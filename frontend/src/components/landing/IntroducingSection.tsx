"use client";

import React, { useState, useEffect } from "react";
import {
  Check,
  ShieldCheck,
  Lightbulb,
  UserRound,
  AlertTriangle,
  Network,
  Sparkles,
  ArrowRight,
} from "lucide-react";
import { SourceIcon } from "../brand";
import { OrganicScene } from "../brand/OrganicScene";
import { useReveal } from "./hooks/useReveal";
import { useElementScrollProgress } from "./motion/useElementScrollProgress";
import { useReducedMotion } from "./motion/useReducedMotion";

const STAGES = [
  {
    num: 1 as const,
    tag: "STAGE 1 — BRING IT TOGETHER",
    title: "Bring It Together",
    subtitle: "Authorized sources converge without disrupting workflows",
    description:
      "Scattered repositories, Jira sprints, Slack architecture threads, and runbook PDFs converge toward a unified project knowledge core without disrupting daily tools.",
    items: [
      { type: "github" as const, name: "payment-core", label: "Pull requests & commits" },
      { type: "jira" as const, name: "PAY · SPRINT-34", label: "Sprint issues & blockers" },
      { type: "slack" as const, name: "#payments-arch", label: "Threaded discussions" },
      { type: "docs" as const, name: "ADR-007 & Runbooks", label: "Uploaded PDF & DOCX" },
    ],
  },
  {
    num: 2 as const,
    tag: "STAGE 2 — RECONSTRUCT AND STRUCTURE",
    title: "Reconstruct and Structure",
    subtitle: "AI maps findings across eight canonical domains",
    description:
      "Fragmented artifacts transform into organized findings across eight canonical domains, preserving source provenance, author timestamps, and contradiction flags.",
    features: [
      "Extract decisions, ownership, and risks",
      "Link candidate findings to original evidence",
      "Surface contradictions and missing context",
      "Preserve four-tier epistemic separation",
    ],
  },
  {
    num: 3 as const,
    tag: "STAGE 3 — VERIFY AND HAND OVER",
    title: "Verify and Hand Over",
    subtitle: "Human reviewers evaluate and sign off verified knowledge",
    description:
      "Human reviewers validate candidate findings with distinct teal verification, assembling an auditable handover dossier ready for the incoming team.",
    verifications: [
      { type: "Decision", name: "Event-driven settlement via Kafka", status: "Verified" },
      { type: "Responsibility", name: "Acquirer credential rotation", status: "Verified" },
      { type: "Risk", name: "No retry on acquirer timeouts", status: "Review" },
      { type: "Dependency", name: "Settlement -> Platform Vault", status: "Review" },
    ],
  },
] as const;

export function IntroducingSection() {
  const revealRef = useReveal<HTMLDivElement>();
  const { ref: scrollRef, progress: scrollProgress } = useElementScrollProgress<HTMLElement>({
    startOffset: 0.85,
    endOffset: 0.2,
  });
  const reducedMotion = useReducedMotion();

  const scrollDerivedStage: 1 | 2 | 3 =
    scrollProgress < 0.38 ? 1 : scrollProgress < 0.72 ? 2 : 3;

  const [activeStage, setActiveStage] = useState<1 | 2 | 3>(1);

  // Sync scroll progress smoothly unless user manually clicks
  useEffect(() => {
    setActiveStage(scrollDerivedStage);
  }, [scrollDerivedStage]);

  const sceneProgress =
    activeStage === 1
      ? 0.35
      : activeStage === 2
      ? 0.72
      : 1.0;

  const currentStage = STAGES.find((s) => s.num === activeStage) ?? STAGES[0]!;

  return (
    <section
      ref={scrollRef}
      id="introducing"
      className="ambient-section relative overflow-x-clip py-24 sm:py-32 bg-[#F8FAFD] border-y border-[#D9E1F0]/70"
    >
      <div ref={revealRef} className="mx-auto w-full max-w-[1240px] px-5 sm:px-8">
        {/* Section Heading */}
        <div className="mx-auto max-w-3xl text-center">
          <div className="reveal flex justify-center">
            <p className="flex items-center gap-2 text-[12.5px] font-semibold uppercase tracking-[0.16em] text-[#315FBA]">
              <span className="h-px w-6 bg-current opacity-60" />
              Introducing Handover
            </p>
          </div>
          <h2 className="reveal mt-5 text-[34px] font-semibold leading-[1.06] tracking-[-0.035em] text-[#203653] sm:text-[44px] lg:text-[52px]">
            One system. Complete project understanding.
          </h2>
          <p className="reveal mx-auto mt-6 max-w-2xl text-[17px] leading-[1.65] text-[#56657c]">
            Handover connects authorized organizational sources, reconstructs fragmented context into structured records with full provenance, surfaces conflicts, and produces auditable transition packages.
          </p>
        </div>

        {/* 3-Stage Interactive Stepper Bar */}
        <div className="reveal mt-12 flex justify-center">
          <div className="inline-flex max-w-full overflow-x-auto rounded-2xl border border-[#D9E1F0] bg-white p-1.5 shadow-sm">
            {STAGES.map((st) => {
              const isActive = activeStage === st.num;
              const isVerified = st.num === 3;
              return (
                <button
                  key={st.num}
                  type="button"
                  onClick={() => setActiveStage(st.num)}
                  className={`flex items-center gap-2.5 rounded-xl px-4 py-2.5 text-left transition-all duration-300 cursor-pointer shrink-0 ${
                    isActive
                      ? isVerified
                        ? "bg-teal-50 text-[#1d6e5b] shadow-xs ring-1 ring-teal-500/30"
                        : "bg-blue-50 text-[#315FBA] shadow-xs ring-1 ring-blue-500/30"
                      : "text-[#56657c] hover:bg-slate-50 hover:text-[#203653]"
                  }`}
                >
                  <span
                    className={`flex size-6 items-center justify-center rounded-lg font-mono text-[11px] font-bold ${
                      isActive
                        ? isVerified
                          ? "bg-[#299B80] text-white"
                          : "bg-[#315FBA] text-white"
                        : "bg-slate-100 text-[#718096]"
                    }`}
                  >
                    0{st.num}
                  </span>
                  <span className="text-[13px] font-semibold whitespace-nowrap">
                    {st.title}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Unified Interactive Transformation Workspace */}
        <div className="reveal mt-10 rounded-[28px] border border-[#D9E1F0] bg-white p-6 sm:p-8 lg:p-10 shadow-pop">
          <div className="grid gap-10 lg:grid-cols-[1.05fr_0.95fr] lg:items-center">
            {/* Left Column: Active Stage Demonstration Details */}
            <div className="space-y-6">
              <div>
                <span
                  className={`font-mono text-[11px] font-semibold uppercase tracking-wider ${
                    activeStage === 3 ? "text-[#299B80]" : "text-[#315FBA]"
                  }`}
                >
                  {currentStage.tag}
                </span>
                <h3 className="mt-2 text-[26px] sm:text-[30px] font-semibold tracking-[-0.025em] text-[#203653]">
                  {currentStage.subtitle}
                </h3>
                <p className="mt-3 text-[15px] leading-relaxed text-[#56657c]">
                  {currentStage.description}
                </p>
              </div>

              {/* Stage-Specific Visual Artifact Container */}
              <div className="rounded-2xl border border-[#D9E1F0] bg-[#F8FAFD] p-5 shadow-xs">
                {activeStage === 1 && (
                  <div className="space-y-3">
                    <p className="font-mono text-[11px] font-semibold uppercase tracking-wider text-[#718096] mb-3">
                      Converging Source Streams
                    </p>
                    {STAGES[0].items.map((s) => (
                      <div
                        key={s.name}
                        className="flex items-center justify-between gap-3 rounded-xl border border-[#D9E1F0] bg-white p-3 shadow-xs"
                      >
                        <div className="flex items-center gap-3 min-w-0">
                          <SourceIcon type={s.type} size={28} />
                          <div className="min-w-0">
                            <span className="block truncate font-mono text-[12.5px] font-semibold text-[#203653]">
                              {s.name}
                            </span>
                            <span className="block text-[11px] text-[#718096]">
                              {s.label}
                            </span>
                          </div>
                        </div>
                        <span className="flex items-center gap-1.5 font-mono text-[10.5px] text-[#299B80] shrink-0 font-semibold">
                          <span className="size-2 rounded-full bg-[#299B80] animate-pulse-soft" />
                          Streaming
                        </span>
                      </div>
                    ))}
                  </div>
                )}

                {activeStage === 2 && (
                  <div className="space-y-3">
                    <p className="font-mono text-[11px] font-semibold uppercase tracking-wider text-[#718096] mb-3">
                      Reconstructed Knowledge Core
                    </p>
                    <div className="rounded-xl border border-[#D9E1F0] bg-white p-4 shadow-xs">
                      <div className="flex items-center justify-between mb-3 border-b border-[#D9E1F0]/70 pb-2.5">
                        <span className="font-mono text-[11.5px] font-semibold text-[#315FBA]">
                          Canonical Knowledge Extraction
                        </span>
                        <span className="rounded-full bg-indigo-50 px-2 py-0.5 font-mono text-[10px] font-semibold text-[#8B78C9] ring-1 ring-indigo-500/20">
                          AI Reconstruction
                        </span>
                      </div>
                      <ul className="space-y-2.5 text-[13px] text-[#203653]">
                        {STAGES[1].features.map((f) => (
                          <li key={f} className="flex items-center gap-2.5">
                            <span className="flex size-4 shrink-0 items-center justify-center rounded-full bg-[#315FBA]/10 text-[#315FBA]">
                              <Check className="size-3" />
                            </span>
                            <span>{f}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                )}

                {activeStage === 3 && (
                  <div className="space-y-3">
                    <p className="font-mono text-[11px] font-semibold uppercase tracking-wider text-[#718096] mb-3">
                      Human Verification Sign-Off
                    </p>
                    <div className="space-y-2">
                      {STAGES[2].verifications.map((v) => (
                        <div
                          key={v.name}
                          className="flex items-center justify-between gap-3 rounded-xl border border-[#D9E1F0] bg-white p-3 shadow-xs"
                        >
                          <div className="min-w-0">
                            <span className="block font-mono text-[10.5px] font-semibold text-[#718096] uppercase">
                              {v.type}
                            </span>
                            <span className="block text-[13px] font-semibold text-[#203653] truncate">
                              {v.name}
                            </span>
                          </div>
                          <span
                            className={`rounded-full px-2.5 py-0.5 font-mono text-[10px] font-semibold shrink-0 ${
                              v.status === "Verified"
                                ? "bg-teal-50 text-[#299B80] ring-1 ring-teal-600/20 flex items-center gap-1"
                                : "bg-amber-50 text-amber-700 ring-1 ring-amber-600/20"
                            }`}
                          >
                            {v.status === "Verified" && <ShieldCheck className="size-3" />}
                            {v.status}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Right Column: 3D Transformation Knowledge Core */}
            <div>
              <div className="relative overflow-hidden rounded-[24px] border border-[#D9E1F0] bg-gradient-to-b from-white via-[#F6F8FC] to-white p-4 sm:p-5 shadow-card">
                {/* Header Badge */}
                <div className="flex items-center justify-between border-b border-[#D9E1F0]/70 pb-3 px-2">
                  <span className="font-mono text-[10.5px] font-semibold uppercase tracking-wider text-[#718096]">
                    Organic Reconstruction Engine
                  </span>
                  <span
                    className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 font-mono text-[10.5px] font-semibold ${
                      activeStage === 3
                        ? "bg-teal-50 text-[#299B80] ring-1 ring-inset ring-teal-600/20"
                        : activeStage === 2
                        ? "bg-indigo-50 text-[#8B78C9] ring-1 ring-inset ring-indigo-600/20"
                        : "bg-blue-50 text-[#315FBA] ring-1 ring-inset ring-blue-600/20"
                    }`}
                  >
                    <span
                      className={`size-1.5 rounded-full ${
                        activeStage === 3
                          ? "bg-[#299B80]"
                          : activeStage === 2
                          ? "bg-[#8B78C9] animate-pulse"
                          : "bg-[#315FBA]"
                      }`}
                    />
                    Stage 0{activeStage} of 03
                  </span>
                </div>

                {/* 3D Canvas */}
                <div className="h-[320px] sm:h-[380px] w-full">
                  <OrganicScene
                    variant="assemble"
                    progress={sceneProgress}
                    showTags={activeStage >= 2}
                    className="h-full w-full"
                    label="Dimensional knowledge reconstruction core transforming scattered sources into verified structure"
                  />
                </div>

                {/* Quick Stage Controls */}
                <div className="flex items-center justify-between border-t border-[#D9E1F0]/70 pt-3 px-2 font-mono text-[10.5px] text-[#718096]">
                  <span>Knowledge State:</span>
                  <div className="flex gap-2">
                    {[1, 2, 3].map((num) => (
                      <button
                        key={num}
                        type="button"
                        onClick={() => setActiveStage(num as 1 | 2 | 3)}
                        className={`size-6 rounded-md font-bold transition cursor-pointer flex items-center justify-center ${
                          activeStage === num
                            ? num === 3
                              ? "bg-[#299B80] text-white"
                              : "bg-[#315FBA] text-white"
                            : "bg-slate-100 text-[#718096] hover:bg-slate-200"
                        }`}
                      >
                        {num}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

export default IntroducingSection;
