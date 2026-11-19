"use client";

import React, { useState } from "react";
import {
  ShieldCheck,
  Lock,
  Check,
  Layers,
  FileCheck2,
  Sparkles,
  GitBranch,
} from "lucide-react";
import { useReveal } from "./hooks/useReveal";

export function TrustSection() {
  const ref = useReveal<HTMLElement>();
  const [selectedTier, setSelectedTier] = useState<number>(4);

  const tierDetails: Record<number, { title: string; guarantee: string }> = {
    4: {
      title: "Selected Governance Rule · Human Verification Required (Verified Teal)",
      guarantee:
        "Established solely through explicit human review and approval. Only verified findings count toward official handover readiness.",
    },
    3: {
      title: "Selected Governance Rule · Provisional AI Synthesis (Indigo)",
      guarantee:
        "Provisional candidate summaries, confidence estimates, and contradiction flags produced by Qwen3 8B. Never auto-approved.",
    },
    2: {
      title: "Selected Governance Rule · Structured Extraction (Brand Blue)",
      guarantee:
        "Deterministic structured parsing—entity mentions, file chunks, timestamps, and GLM OCR text spans tied back to source offsets.",
    },
    1: {
      title: "Selected Governance Rule · Raw Source Retention (Neutral Blue/Slate)",
      guarantee:
        "Immutable authorized artifacts stored outside frontend directories with AES-256-GCM encryption and read-time ACL gating.",
    },
  };

  const activeMeaning = tierDetails[selectedTier] ?? tierDetails[4]!;

  return (
    <section
      ref={ref}
      id="security"
      className="relative scroll-mt-20 overflow-hidden bg-[#203653] py-24 text-white sm:py-32"
    >
      <div className="pointer-events-none absolute inset-0 opacity-[0.04] hairline-grid" />
      <div
        className="pointer-events-none absolute -right-40 top-0 size-[620px] rounded-full"
        style={{
          background:
            "radial-gradient(circle, rgba(41,155,128,0.18), rgba(139,120,201,0.18) 45%, transparent 65%)",
        }}
      />

      <div className="mx-auto w-full max-w-[1240px] px-5 sm:px-8">
        <div className="relative grid gap-14 grid-cols-1 lg:grid-cols-[1fr_1fr] lg:gap-16">
          {/* Left Narrative: Core Guarantees */}
          <div>
            <p className="reveal flex items-center gap-2 text-[12.5px] font-semibold uppercase tracking-[0.16em] text-[#a9b8d0]">
              <span className="h-px w-6 bg-current opacity-60" />
              Trust &amp; Verification
            </p>
            <h2 className="reveal mt-5 text-[34px] font-semibold leading-[1.06] tracking-[-0.035em] sm:text-[44px] lg:text-[50px]">
              AI can reconstruct knowledge. People establish what is verified.
            </h2>
            <p className="reveal mt-6 max-w-lg text-[17px] leading-[1.65] text-[#c3cfe0]">
              Built for accuracy, transparency, and control. Every finding maintains strict four-tier epistemic separation so AI-generated candidates are never mistaken for human-verified facts.
            </p>

            <ul className="reveal mt-10 space-y-6">
              {[
                {
                  icon: ShieldCheck,
                  title: "Zero Data Fabrication",
                  body: "The platform never generates synthetic or speculative records as real organizational evidence. Every finding requires grounding in authorized sources.",
                },
                {
                  icon: FileCheck2,
                  title: "Human-in-the-Loop Governance",
                  body: "AI models cannot approve handovers, certify official task completion, or resolve conflicting facts independently. Human review is an unbypassable gate.",
                },
                {
                  icon: Lock,
                  title: "Strict Source-Level Permissions",
                  body: "Project membership does not grant automatic access to private repos or restricted issues. External source ACLs are strictly enforced at read time before retrieval.",
                },
                {
                  icon: GitBranch,
                  title: "Provenance & Immutable Auditability",
                  body: "Every decision, responsibility, and risk retains source identifiers, authors, timestamps, and provenance metadata in an immutable PostgreSQL audit trail.",
                },
              ].map((item) => (
                <li key={item.title} className="flex gap-4">
                  <span className="flex size-10 shrink-0 items-center justify-center rounded-xl border border-white/15 bg-white/5">
                    <item.icon className="size-4 text-[#c3cfe0]" />
                  </span>
                  <div>
                    <p className="text-[16px] font-semibold">{item.title}</p>
                    <p className="mt-0.5 text-[14px] leading-relaxed text-[#a9b8d0]">
                      {item.body}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          </div>

          {/* Right Epistemic Separation Showcase (4 Stacked Translucent Layers) */}
          <div className="reveal">
            <div className="rounded-[22px] border border-white/15 bg-white/95 backdrop-blur-md p-5 text-[#203653] shadow-pop sm:p-7">
              <div className="mb-5 flex items-center justify-between border-b border-[#D9E1F0] pb-2.5">
                <span className="font-mono text-[10.5px] uppercase tracking-wider text-[#718096]">
                  Four-Tier Epistemic Separation Model
                </span>
                <span className="rounded-full border border-slate-200 bg-slate-100 px-2 py-0.5 font-mono text-[9.5px] font-medium text-slate-600">
                  Interactive Architectural Model
                </span>
              </div>

              {/* 4 Stacked Epistemic Layers */}
              <div className="space-y-3">
                {/* Tier 4: Human-Verified Knowledge (Distinct Teal) */}
                <button
                  type="button"
                  onClick={() => setSelectedTier(4)}
                  onMouseEnter={() => setSelectedTier(4)}
                  className={`w-full text-left rounded-2xl p-4 transition-all duration-300 cursor-pointer ${
                    selectedTier === 4
                      ? "border-2 border-[#299B80] bg-[#EEF6F3] shadow-md ring-2 ring-[#299B80]/25 scale-[1.01]"
                      : "border-2 border-[#299B80]/65 bg-[#EEF6F3]/60 hover:bg-[#EEF6F3]"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-[#299B80]">
                      <ShieldCheck className="size-3.5" />
                      Tier 4 · Human-Verified Knowledge
                    </span>
                    <span className="rounded-full bg-[#299B80] px-2 py-0.5 text-[10px] font-semibold text-white">
                      Human Signed Off
                    </span>
                  </div>
                  <p className="mt-1.5 text-[13.5px] font-semibold text-[#203653]">
                    Confirmed by Jordan Lee &amp; Alex Chen
                  </p>
                  <p className="mt-1 text-[12px] text-[#56657c] leading-relaxed">
                    Decisions, dependencies, and risks explicitly approved by designated human reviewers.
                  </p>
                </button>

                {/* Tier 3: AI-Generated Interpretation (Indigo) */}
                <button
                  type="button"
                  onClick={() => setSelectedTier(3)}
                  onMouseEnter={() => setSelectedTier(3)}
                  className={`w-full text-left rounded-2xl p-4 transition-all duration-300 cursor-pointer ${
                    selectedTier === 3
                      ? "border border-[#8B78C9] bg-[#F4F2FA] shadow-md ring-2 ring-[#8B78C9]/25 scale-[1.01]"
                      : "border border-[#D3CCEC] bg-[#F4F2FA]/60 hover:bg-[#F4F2FA]"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-[#8B78C9]">
                      <Sparkles className="size-3.5" />
                      Tier 3 · AI-Generated Interpretation
                    </span>
                    <span className="rounded-full bg-indigo-100 px-2 py-0.5 text-[10px] font-semibold text-indigo-700">
                      Unverified Candidates
                    </span>
                  </div>
                  <p className="mt-1.5 text-[13.5px] font-semibold text-[#203653]">
                    Structured Candidate Findings &amp; Inferences (Sample Confidence 94%)
                  </p>
                  <p className="mt-1 text-[12px] text-[#56657c] leading-relaxed">
                    Draft summaries, contradiction flags, and confidence scores requiring human verification before approval.
                  </p>
                </button>

                {/* Tier 2: Extracted Information (Brand Blue) */}
                <button
                  type="button"
                  onClick={() => setSelectedTier(2)}
                  onMouseEnter={() => setSelectedTier(2)}
                  className={`w-full text-left rounded-2xl p-4 transition-all duration-300 cursor-pointer ${
                    selectedTier === 2
                      ? "border border-[#315FBA] bg-[#EEF2FA] shadow-md ring-2 ring-[#315FBA]/25 scale-[1.01]"
                      : "border border-[#C3D2EC] bg-[#EEF2FA]/60 hover:bg-[#EEF2FA]"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-[#315FBA]">
                      <Layers className="size-3.5" />
                      Tier 2 · Extracted Information
                    </span>
                    <span className="rounded-full bg-blue-100 px-2 py-0.5 text-[10px] font-semibold text-[#315FBA]">
                      Parsed Artifacts
                    </span>
                  </div>
                  <p className="mt-1.5 text-[13.5px] font-semibold text-[#203653]">
                    Entity Mentions, Timestamps, Commit Diffs &amp; OCR
                  </p>
                  <p className="mt-1 text-[12px] text-[#56657c] leading-relaxed">
                    Deterministic normalization from pull requests, Slack threads, Jira tickets, and documents.
                  </p>
                </button>

                {/* Tier 1: Original Source Evidence (Neutral Blue / Slate) */}
                <button
                  type="button"
                  onClick={() => setSelectedTier(1)}
                  onMouseEnter={() => setSelectedTier(1)}
                  className={`w-full text-left rounded-2xl p-4 transition-all duration-300 cursor-pointer ${
                    selectedTier === 1
                      ? "border border-[#7997BE] bg-[#F7FAFC] shadow-md ring-2 ring-[#7997BE]/30 scale-[1.01]"
                      : "border border-[#D9E1F0] bg-[#F7FAFC]/70 hover:bg-[#F7FAFC]"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-[#56657c]">
                      <GitBranch className="size-3.5 text-[#7997BE]" />
                      Tier 1 · Original Source Evidence
                    </span>
                    <span className="rounded-full bg-slate-200 px-2 py-0.5 text-[10px] font-semibold text-slate-700">
                      Source Ground Truth
                    </span>
                  </div>
                  <p className="mt-1.5 text-[13.5px] font-semibold text-[#203653]">
                    Authorized Commits, PRs, Issues, Messages &amp; Uploaded Files
                  </p>
                  <p className="mt-1 text-[12px] text-[#56657c] leading-relaxed">
                    Private artifacts encrypted at rest with AES-256-GCM, preserving author, timestamp, and provenance references.
                  </p>
                </button>
              </div>

              {/* Active Selected Layer Meaning Callout */}
              <div className="mt-4 rounded-xl border border-[#D9E1F0] bg-[#F8FAFD] p-3.5 text-[12px] text-[#203653]">
                <p className="font-mono text-[10.5px] font-bold uppercase tracking-wider text-[#315FBA]">
                  {activeMeaning.title}
                </p>
                <p className="mt-1 text-[#56657c] leading-relaxed">{activeMeaning.guarantee}</p>
              </div>

              {/* Platform Security Badges */}
              <div className="mt-5 pt-4 border-t border-[#D9E1F0] grid grid-cols-2 gap-x-4 gap-y-2 text-[12px] text-[#56657c]">
                {[
                  "Fine-grained read-only tokens",
                  "AES-256-GCM envelope encryption",
                  "Strict read-time ACL checks",
                  "Immutable PostgreSQL audit log",
                ].map((b) => (
                  <p key={b} className="flex items-center gap-1.5">
                    <Check className="size-3.5 text-[#299B80] shrink-0" />
                    <span>{b}</span>
                  </p>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
