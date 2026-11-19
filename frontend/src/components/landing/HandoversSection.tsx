"use client";

import React, { useState } from "react";
import { ArrowRight, Check, ShieldCheck, FileCheck2, UserCheck, BarChart3, Link2 } from "lucide-react";
import { OrganicScene } from "../brand/OrganicScene";
import { useReveal } from "./hooks/useReveal";
import { useElementScrollProgress } from "./motion/useElementScrollProgress";

const TABS = [
  "Overview",
  "Responsibilities",
  "Decisions",
  "Tasks",
  "Risks",
  "Evidence",
  "Report",
] as const;

const ASSEMBLY_STEPS = [
  "Dossier Shell",
  "Project Identity",
  "Domain Summaries",
  "Evidence References",
  "Unfinished Work",
  "Review States",
  "Complete Dossier",
] as const;

const DOMAIN_BREAKDOWN = [
  { name: "Decisions & Rationale", count: 12, color: "#315FBA" },
  { name: "Architecture", count: 9, color: "#203653" },
  { name: "Work Status", count: 8, color: "#299B80" },
  { name: "Ownership", count: 6, color: "#7997BE" },
  { name: "Dependencies", count: 7, color: "#D39B43" },
  { name: "Bugs & Risks", count: 5, color: "#D36D72" },
  { name: "Procedures", count: 6, color: "#8B78C9" },
  { name: "Discussions", count: 5, color: "#A0AEC0" },
];

export function HandoversSection() {
  const revealRef = useReveal<HTMLDivElement>();
  const { ref: scrollRef, progress: scrollProgress } = useElementScrollProgress<HTMLElement>({
    startOffset: 0.85,
    endOffset: 0.25,
  });
  const [activeTab, setActiveTab] = useState<(typeof TABS)[number]>("Overview");
  const [selectedRolePackage, setSelectedRolePackage] = useState<
    "developer" | "lead" | "leadership"
  >("developer");

  const assemblyStepCount = Math.min(7, Math.max(1, Math.ceil(scrollProgress * 7)));

  return (
    <section
      ref={scrollRef}
      id="handovers"
      className="relative scroll-mt-20 py-24 sm:py-32 overflow-x-clip"
    >
      <div ref={revealRef} className="mx-auto w-full max-w-[1240px] px-5 sm:px-8">
        <div className="grid items-start gap-14 grid-cols-1 lg:grid-cols-[0.78fr_1.22fr] lg:gap-16">
          {/* Left Narrative Column */}
          <div className="lg:sticky lg:top-24 self-start space-y-6">
            <div>
              <div className="reveal">
                <p className="flex items-center gap-2 text-[12.5px] font-semibold uppercase tracking-[0.16em] text-[#315FBA]">
                  <span className="h-px w-6 bg-current opacity-60" />
                  Handover Dossier
                </p>
              </div>
              <h2 className="reveal mt-5 text-[34px] font-semibold leading-[1.06] tracking-[-0.035em] text-[#203653] sm:text-[44px] lg:text-[50px]">
                Everything the next person needs.
              </h2>
              <p className="reveal mt-6 text-[17px] leading-[1.65] text-[#56657c]">
                Bring reconstructed, evidence-backed knowledge together into an auditable transition dossier across eight canonical domains—covering technical architecture, finished and unfinished work, operational procedures, risks, and review states.
              </p>
            </div>

            {/* Scroll-driven Dossier Assembly Strata Card */}
            <div className="reveal rounded-2xl border border-[#D9E1F0] bg-[#F8FAFD] p-4 shadow-xs">
              <div className="flex items-center justify-between mb-2">
                <span className="font-mono text-[10px] font-semibold uppercase tracking-wider text-[#315FBA]">
                  Scroll-Driven Dossier Assembly
                </span>
                <span className="font-mono text-[10px] text-[#718096]">
                  Stage {assemblyStepCount}/7
                </span>
              </div>
              <div className="h-[95px] w-full rounded-xl bg-white border border-[#D9E1F0]/70 overflow-hidden mb-3">
                <OrganicScene
                  variant="dossier"
                  progress={scrollProgress}
                  showTags={false}
                  interactive={false}
                  className="h-full w-full"
                  label="Structured dossier layers assembling in order"
                />
              </div>
              <div className="flex flex-wrap gap-1.5">
                {ASSEMBLY_STEPS.map((st, idx) => {
                  const active = idx < assemblyStepCount;
                  return (
                    <span
                      key={st}
                      className={`rounded-md px-2 py-0.5 font-mono text-[9.5px] transition-colors ${
                        active
                          ? "bg-[#299B80]/15 text-[#1d6e5b] font-semibold"
                          : "bg-white text-[#718096] border border-[#D9E1F0]"
                      }`}
                    >
                      {idx + 1}. {st}
                    </span>
                  );
                })}
              </div>
            </div>

            {/* 3 Role-Tailored Package Selectors */}
            <div className="reveal grid grid-cols-1 sm:grid-cols-3 gap-3">
              {[
                {
                  id: "developer" as const,
                  icon: UserCheck,
                  title: "Incoming Developer",
                  detail: "Architecture, tasks, runbooks & blockers",
                },
                {
                  id: "lead" as const,
                  icon: FileCheck2,
                  title: "Technical Lead",
                  detail: "Decision audit trail & dependency map",
                },
                {
                  id: "leadership" as const,
                  icon: BarChart3,
                  title: "Engineering Leadership",
                  detail: "Risk summary & readiness overview",
                },
              ].map((pkg) => (
                <button
                  key={pkg.title}
                  type="button"
                  onClick={() => setSelectedRolePackage(pkg.id)}
                  className={`rounded-xl border p-3 text-left transition-all duration-200 cursor-pointer ${
                    selectedRolePackage === pkg.id
                      ? "border-[#315FBA] bg-white ring-2 ring-[#315FBA]/20 shadow-sm"
                      : "border-[#D9E1F0] bg-white/70 hover:bg-white hover:border-[#7997BE]"
                  }`}
                >
                  <pkg.icon className="size-4 text-[#315FBA] mb-1.5" />
                  <p className="text-[12.5px] font-semibold text-[#203653]">
                    {pkg.title}
                  </p>
                  <p className="text-[11px] text-[#718096] mt-0.5 leading-snug">
                    {pkg.detail}
                  </p>
                </button>
              ))}
            </div>

            {/* Two-Stage Transition Governance */}
            <div className="reveal rounded-xl border border-[#D9E1F0] bg-white p-3.5 text-[12px] text-[#56657c] shadow-xs">
              <div className="flex items-center gap-2 font-mono text-[10.5px] font-semibold uppercase tracking-wider text-[#203653]">
                <ShieldCheck className="size-3.5 text-[#299B80]" />
                Two-Stage Transition Governance
              </div>
              <p className="mt-1.5 text-[11px] leading-relaxed text-[#718096]">
                Dossiers require formal reviewer approval by designated technical leads before publication. Successor receipt acknowledgement confirms access without replacing supervisory sign-off.
              </p>
            </div>
          </div>

          {/* Right Handover Dossier Preview */}
          <div className="reveal relative">
            <div
              className="absolute -inset-6 rounded-[32px] opacity-75 pointer-events-none"
              style={{
                background:
                  "radial-gradient(ellipse at 70% 20%, rgba(165,160,217,0.25), transparent 60%)",
              }}
            />
            <div className="relative overflow-hidden rounded-[20px] border border-[#D9E1F0] bg-white shadow-pop">
              {/* Package Header */}
              <div className="border-b border-[#D9E1F0] p-5 sm:p-6 bg-white">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-[11.5px] font-medium text-[#718096]">
                    HO-1042
                  </span>
                  <span className="rounded-full bg-amber-50 px-2.5 py-0.5 text-[11px] font-semibold text-amber-700 ring-1 ring-inset ring-amber-600/20">
                    Pending Review
                  </span>
                  <span className="rounded-full border border-slate-200 bg-slate-100 px-2 py-0.5 font-mono text-[10px] font-medium text-slate-600">
                    Illustrative Dossier Preview · {selectedRolePackage.toUpperCase()} View
                  </span>
                </div>

                <div className="mt-2.5 flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
                  <div className="min-w-0">
                    <h3 className="text-[18px] sm:text-[20px] font-semibold tracking-[-0.02em] text-[#203653] truncate sm:whitespace-normal">
                      Payment Platform
                    </h3>
                    <div className="mt-3 flex items-center gap-2.5 text-[12.5px]">
                      <span className="flex size-7 items-center justify-center rounded-full bg-[#203653]/10 text-[10px] font-bold text-[#203653]">
                        AC
                      </span>
                      <span className="font-medium text-[#203653]">Alex Chen</span>
                      <ArrowRight className="size-3.5 text-[#315FBA]" />
                      <span className="flex size-7 items-center justify-center rounded-full bg-blue-50 text-[10px] font-bold text-[#315FBA]">
                        PS
                      </span>
                      <span className="font-medium text-[#203653]">Priya Shah</span>
                    </div>
                  </div>

                  {/* Circular Sample Readiness Ring (explicitly marked illustrative) */}
                  <div className="flex flex-col items-center shrink-0">
                    <div className="relative size-16">
                      <svg viewBox="0 0 64 64" className="-rotate-90">
                        <circle
                          cx="32"
                          cy="32"
                          r="27"
                          fill="none"
                          stroke="#EDF1F8"
                          strokeWidth="5"
                        />
                        <circle
                          cx="32"
                          cy="32"
                          r="27"
                          fill="none"
                          stroke="#299B80"
                          strokeWidth="5"
                          strokeLinecap="round"
                          strokeDasharray={`${0.86 * 170} 170`}
                        />
                      </svg>
                      <span className="absolute inset-0 flex items-center justify-center text-[13px] font-bold text-[#203653]">
                        86%
                      </span>
                    </div>
                    <span className="mt-1 font-mono text-[9px] text-[#718096]">
                      Sample metric
                    </span>
                  </div>
                </div>

                {/* Workflow Stage Bars */}
                <div className="mt-5 grid grid-cols-6 gap-1.5">
                  {["Draft", "Verify", "Review", "Approve", "Publish", "Ack"].map(
                    (stage, i) => (
                      <div key={stage}>
                        <div
                          className={`h-1.5 rounded-full relative overflow-hidden ${
                            i < 2
                              ? "bg-[#299B80]"
                              : i === 2
                              ? "bg-[#315FBA]"
                              : "bg-slate-200"
                          }`}
                        >
                          {i === 2 && (
                            <span className="absolute inset-0 bg-gradient-to-r from-transparent via-white/80 to-transparent animate-beam" />
                          )}
                        </div>
                        <p
                          className={`mt-1.5 hidden text-[10.5px] font-medium sm:block ${
                            i === 2 ? "text-[#315FBA] font-semibold" : "text-slate-400"
                          }`}
                        >
                          {stage}
                        </p>
                      </div>
                    )
                  )}
                </div>

                {/* 8-Domain Knowledge Breakdown Summary Grid (Total: 58) */}
                <div className="mt-5 rounded-xl border border-[#D9E1F0] bg-[#F8FAFD] p-3">
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-mono text-[10.5px] uppercase tracking-wider text-[#718096] font-semibold">
                      Sample Breakdown Across 8 Domains
                    </span>
                    <span className="font-mono text-[11px] font-bold text-[#203653]">
                      58 Total Findings
                    </span>
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                    {DOMAIN_BREAKDOWN.map((d) => (
                      <div
                        key={d.name}
                        className="rounded-lg bg-white p-2 border border-[#D9E1F0]/70 flex items-center justify-between"
                      >
                        <span className="text-[11px] text-[#56657c] truncate pr-1 flex items-center gap-1">
                          <span
                            className="size-1.5 rounded-full shrink-0"
                            style={{ background: d.color }}
                          />
                          <span className="truncate">{d.name}</span>
                        </span>
                        <span className="font-mono text-[11.5px] font-bold text-[#203653]">
                          {d.count}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* Navigation Tabs */}
              <div className="flex gap-5 overflow-x-auto border-b border-[#D9E1F0] px-6 text-[12.5px] font-medium text-[#718096] bg-[#F8FAFD]">
                {TABS.map((tab) => (
                  <button
                    key={tab}
                    type="button"
                    onClick={() => setActiveTab(tab)}
                    className={`shrink-0 border-b-2 py-2.5 transition-colors cursor-pointer ${
                      activeTab === tab
                        ? "border-[#315FBA] text-[#315FBA] font-semibold"
                        : "border-transparent text-[#718096] hover:text-[#203653]"
                    }`}
                  >
                    {tab}
                  </button>
                ))}
              </div>

              {/* Dynamic Dossier Tab Panels */}
              {activeTab === "Overview" ? (
                <div className="grid gap-px bg-[#D9E1F0] sm:grid-cols-2">
                  <div className="bg-white p-5">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-slate-400">
                      Project Overview &amp; Technical Architecture
                    </p>
                    <p className="mt-2 text-[13px] leading-relaxed text-[#3e5373]">
                      Core payments ledger publishing Kafka events to an asynchronous settlement worker, fronted by a Redis-cached API gateway.
                    </p>
                  </div>

                  <div className="bg-white p-5">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-slate-400">
                      Responsibilities &amp; Operational Procedures
                    </p>
                    <ul className="mt-2 space-y-1.5 text-[13px] text-[#203653]">
                      {[
                        "Settlement worker & manual timeout reconcile runbook",
                        "Ledger schema migrations & Kafka partition balancing",
                        "Acquirer credential rotation (due Jun 30)",
                      ].map((r) => (
                        <li key={r} className="flex items-center gap-2">
                          <Check className="size-3.5 text-[#299B80] shrink-0" />
                          <span>{r}</span>
                        </li>
                      ))}
                    </ul>
                  </div>

                  <div className="bg-white p-5">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-slate-400">
                      Decisions, Context &amp; Dependencies
                    </p>
                    <ul className="mt-2 space-y-2 text-[13px] text-[#203653]">
                      {[
                        { title: "Event-driven settlement via Kafka", ok: true },
                        { title: "SOAP migration depends on credential swap", ok: true },
                        { title: "Retention period conflict flagged", ok: false },
                      ].map((d) => (
                        <li key={d.title} className="flex items-center justify-between gap-2">
                          <span className="truncate">{d.title}</span>
                          {d.ok ? (
                            <ShieldCheck className="size-3.5 shrink-0 text-[#299B80]" />
                          ) : (
                            <span className="shrink-0 rounded bg-red-50 px-1.5 text-[10px] font-semibold text-red-700 ring-1 ring-inset ring-red-600/20">
                              Conflict
                            </span>
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>

                  <div className="bg-white p-5">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-slate-400">
                      Completed &amp; Unfinished Work · Bugs &amp; Risks
                    </p>
                    <ul className="mt-2 space-y-2 text-[13px] text-[#203653]">
                      {[
                        { sev: "Done", text: "Redis session cache merged (PR #4827)" },
                        { sev: "Unfinished", text: "Add retry backoff on acquirer timeouts" },
                      ].map((r) => (
                        <li key={r.text} className="flex items-center gap-2">
                          <span
                            className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                              r.sev === "Done"
                                ? "bg-teal-50 text-teal-700"
                                : "bg-amber-50 text-amber-700"
                            }`}
                          >
                            {r.sev}
                          </span>
                          <span className="truncate">{r.text}</span>
                        </li>
                      ))}
                    </ul>
                  </div>

                  <div className="bg-white p-5">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-slate-400">
                      Evidence References
                    </p>
                    <ul className="mt-2 space-y-1.5 font-mono text-[11.5px] text-[#315FBA]">
                      {["payment-core #4827", "ADR-007.pdf", "settlement-runbook.pdf"].map(
                        (ev) => (
                          <li key={ev} className="flex items-center gap-1.5">
                            <Link2 className="size-3 shrink-0" />
                            <span>{ev}</span>
                          </li>
                        )
                      )}
                    </ul>
                  </div>

                  <div className="bg-white p-5">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-slate-400">
                      Review States &amp; Next Actions
                    </p>
                    <ol className="mt-2 space-y-1.5 text-[13px] text-[#203653]">
                      {[
                        "Resolve Kafka retention parameter conflict",
                        "Manager sign-off before publication to Priya Shah",
                      ].map((a, i) => (
                        <li key={a} className="flex gap-2">
                          <span className="flex size-4 shrink-0 items-center justify-center rounded-full bg-blue-50 text-[10px] font-bold text-[#315FBA]">
                            {i + 1}
                          </span>
                          <span className="truncate">{a}</span>
                        </li>
                      ))}
                    </ol>
                  </div>
                </div>
              ) : (
                <div className="bg-white p-6 space-y-3 animate-fade">
                  <div className="flex items-center justify-between">
                    <p className="font-mono text-[11px] font-semibold uppercase tracking-wider text-[#315FBA]">
                      {activeTab} Section · Illustrative HO-1042 Dossier View
                    </p>
                    <span className="rounded-full bg-teal-50 px-2.5 py-0.5 text-[10.5px] font-semibold text-teal-700">
                      Human Review Gate Active
                    </span>
                  </div>
                  <p className="text-[13.5px] leading-relaxed text-[#56657c]">
                    Detailed {activeTab.toLowerCase()} records for the Payment Platform transition include verified citations (`payment-core #4827`, `ADR-007.pdf`, `PROJ-103`), historical context from `#payments-arch`, and explicit human reviewer sign-off statuses before handoff.
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
