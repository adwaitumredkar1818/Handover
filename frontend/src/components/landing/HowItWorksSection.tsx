"use client";

import React, { useState, useEffect } from "react";
import {
  Plug,
  Sparkles,
  ShieldCheck,
  ClipboardCheck,
  Workflow,
  Lock,
  Check,
  ArrowRight,
  AlertTriangle,
} from "lucide-react";
import { useReveal } from "./hooks/useReveal";
import { useElementScrollProgress } from "./motion/useElementScrollProgress";
import { useReducedMotion } from "./motion/useReducedMotion";

const STEPS = [
  {
    key: "Connect",
    icon: Plug,
    headline: "Authorised Source Integration",
    body: "Link authorized GitHub repos, Jira projects, Slack channels, and uploaded documents to the project workspace.",
  },
  {
    key: "Reconstruct",
    icon: Sparkles,
    headline: "Multi-Domain Knowledge Extraction",
    body: "AI extracts decisions, architecture, ownership, risks, and dependencies with full source provenance.",
  },
  {
    key: "Verify",
    icon: ShieldCheck,
    headline: "Human Verification Queue",
    body: "Human reviewers evaluate candidate findings against original evidence and confirm, edit, or reject.",
  },
  {
    key: "Review",
    icon: ClipboardCheck,
    headline: "Technical Sign-Off & Audit Readiness",
    body: "Conflicts, knowledge gaps, and outstanding items are surfaced so reviewers inspect accuracy before sign-off.",
  },
  {
    key: "Handover",
    icon: Workflow,
    headline: "Role-Tailored Dossier Publication",
    body: "Generate structured, role-tailored handover packages for incoming team members with full audit trail.",
  },
];

function PreviewBadge() {
  return (
    <div className="mb-3 flex items-center justify-between border-b border-[#D9E1F0]/70 pb-2">
      <span className="font-mono text-[10px] uppercase tracking-wider text-[#718096]">
        Workflow Preview
      </span>
      <span className="rounded-full border border-slate-200 bg-slate-50 px-1.5 py-0.5 font-mono text-[9px] font-medium text-slate-500">
        Illustrative Demo
      </span>
    </div>
  );
}

function StepPreview({ index }: { index: number }) {
  const frameClass =
    "rounded-2xl border border-[#D9E1F0] bg-white p-5 shadow-card max-w-md mx-auto";

  if (index === 0) {
    return (
      <div className={frameClass}>
        <PreviewBadge />
        <p className="text-[13px] font-semibold text-[#203653]">
          Select Connected Repositories
        </p>
        <div className="mt-3 space-y-2">
          {["payment-core", "settlement-worker", "gateway-api"].map((r, j) => (
            <div
              key={r}
              className="flex items-center justify-between gap-2.5 rounded-lg border border-[#D9E1F0] px-3 py-2 text-xs"
            >
              <div className="flex items-center gap-2.5">
                <span
                  className={`flex size-4 items-center justify-center rounded ${
                    j < 2 ? "bg-[#315FBA] text-white" : "border border-slate-300"
                  }`}
                >
                  {j < 2 && <Check className="size-3" />}
                </span>
                <span className="font-mono text-[12px] text-[#203653]">{r}</span>
              </div>
              <span className="font-mono text-[10px] text-[#299B80]">
                {j < 2 ? "Converging" : "Pending ACL"}
              </span>
            </div>
          ))}
        </div>
        <p className="mt-3.5 flex items-center gap-1.5 text-[11.5px] text-[#718096]">
          <Lock className="size-3 text-[#315FBA]" />
          <span>Read-only access · Explicit user authorization</span>
        </p>
      </div>
    );
  }

  if (index === 1) {
    return (
      <div className={frameClass}>
        <PreviewBadge />
        <div className="flex items-center justify-between text-[13px]">
          <span className="font-semibold text-[#203653]">Knowledge Reconstruction</span>
          <span className="font-mono font-medium text-[#315FBA]">84%</span>
        </div>
        <div className="mt-3 h-1.5 rounded-full bg-slate-100 overflow-hidden">
          <div className="h-full w-[84%] rounded-full bg-[#315FBA]" />
        </div>
        <ul className="mt-4 space-y-2 text-[12.5px]">
          {[
            { label: "Collecting evidence records", done: true },
            { label: "Extracting decisions & ownership", done: true },
            { label: "Linking provenance citations", done: false },
          ].map((item) => (
            <li key={item.label} className="flex items-center gap-2">
              {item.done ? (
                <Check className="size-3.5 text-[#299B80]" />
              ) : (
                <span className="size-3.5 animate-pulse-soft rounded-full border-2 border-[#315FBA]" />
              )}
              <span className={item.done ? "text-[#203653]" : "text-[#718096]"}>
                {item.label}
              </span>
            </li>
          ))}
        </ul>
      </div>
    );
  }

  if (index === 2) {
    return (
      <div className={frameClass}>
        <PreviewBadge />
        <p className="text-[13px] font-semibold text-[#203653]">
          Settlement worker lacks retry logic on acquirer timeouts
        </p>
        <div className="mt-2.5 flex items-center gap-2">
          <span className="rounded-md border border-dashed border-indigo-200 bg-indigo-50 px-2 py-0.5 text-[11px] font-medium text-indigo-700">
            AI 83%
          </span>
          <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-700 ring-1 ring-inset ring-amber-600/20">
            Human Review Queue
          </span>
        </div>
        <div className="mt-4 flex gap-2">
          <span className="flex h-8 items-center gap-1.5 rounded-lg bg-[#299B80] px-3 text-[12px] font-semibold text-white shadow-xs">
            <ShieldCheck className="size-3.5" />
            Verify
          </span>
          <span className="flex h-8 items-center rounded-lg border border-[#D9E1F0] px-3 text-[12px] font-semibold text-[#203653]">
            Edit Finding
          </span>
          <span className="flex h-8 items-center rounded-lg border border-[#D9E1F0] px-3 text-[12px] font-semibold text-red-600">
            Reject
          </span>
        </div>
      </div>
    );
  }

  if (index === 3) {
    return (
      <div className={frameClass}>
        <PreviewBadge />
        <div className="flex items-center justify-between text-[13px] mb-3">
          <span className="font-semibold text-[#203653]">Technical Review</span>
          <span className="rounded-full bg-teal-50 px-2 py-0.5 text-[10.5px] font-semibold text-teal-700 ring-1 ring-inset ring-teal-600/20">
            Jordan Lee (Lead)
          </span>
        </div>
        <div className="grid grid-cols-2 gap-2">
          {[
            { label: "Decisions", count: 12, color: "#315FBA" },
            { label: "Architecture", count: 9, color: "#203653" },
            { label: "Risks", count: 5, color: "#D36D72" },
            { label: "Dependencies", count: 7, color: "#D39B43" },
          ].map((d) => (
            <div key={d.label} className="rounded-xl bg-[#F6F8FC] p-2.5 border border-[#D9E1F0]/60">
              <p className="text-[18px] font-semibold text-[#203653]">{d.count}</p>
              <p className="flex items-center gap-1 text-[11.5px] text-[#718096]">
                <span className="size-1.5 rounded-full" style={{ background: d.color }} />
                {d.label}
              </p>
            </div>
          ))}
        </div>
        <div className="mt-3 flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50/70 px-2.5 py-1.5 text-[11px] text-amber-800">
          <AlertTriangle className="size-3.5 shrink-0 text-amber-600" />
          <span>1 conflict &amp; 2 uncertainty gaps flagged for sign-off</span>
        </div>
        <div className="mt-3 pt-2.5 border-t border-[#D9E1F0] flex items-center justify-between text-[11px] text-[#718096]">
          <span>Review status</span>
          <span className="font-semibold text-teal-700">33 of 33 verified</span>
        </div>
      </div>
    );
  }

  return (
    <div className={frameClass}>
      <PreviewBadge />
      <div className="flex items-center gap-3">
        <span className="flex size-8 items-center justify-center rounded-full bg-[#203653] text-[11px] font-bold text-white">
          AC
        </span>
        <ArrowRight className="size-4 text-[#315FBA]" />
        <span className="flex size-8 items-center justify-center rounded-full bg-[#315FBA] text-[11px] font-bold text-white">
          PS
        </span>
        <span className="ml-auto rounded-full bg-blue-50 px-2 py-0.5 text-[11px] font-semibold text-[#315FBA] ring-1 ring-inset ring-blue-600/20">
          Published Handover
        </span>
      </div>
      <p className="mt-3 text-[13px] font-semibold text-[#203653]">
        HO-1042 · Payment Platform Transition
      </p>
      <div className="mt-3.5 grid grid-cols-6 gap-1">
        {[1, 1, 1, 1, 1, 0].map((d, j) => (
          <span
            key={j}
            className={`h-1.5 rounded-full ${d ? "bg-[#299B80]" : "bg-[#315FBA]"}`}
          />
        ))}
      </div>
    </div>
  );
}

export function HowItWorksSection() {
  const revealRef = useReveal<HTMLDivElement>();
  const reducedMotion = useReducedMotion();
  const { ref: scrollRef, progress: scrollProgress } = useElementScrollProgress<HTMLElement>({
    mode: "pinned",
    navOffset: 64,
  });

  const scrollDerivedStep = Math.min(4, Math.floor(scrollProgress * 5));
  const [activeStep, setActiveStep] = useState(0);

  useEffect(() => {
    setActiveStep(scrollDerivedStep);
  }, [scrollDerivedStep]);

  return (
    <section
      ref={scrollRef}
      id="how"
      className="scroll-mt-20 bg-white overflow-x-clip border-b border-[#D9E1F0]/70 py-16 lg:py-0 lg:h-[320vh] motion-reduce:py-24 motion-reduce:sm:py-32 motion-reduce:lg:h-auto"
    >
      <div className="lg:sticky lg:top-16 lg:h-[calc(100vh-4rem)] lg:flex lg:flex-col lg:justify-center motion-reduce:lg:static motion-reduce:lg:h-auto motion-reduce:lg:flex-initial">
        <div ref={revealRef} className="mx-auto w-full max-w-[1240px] px-5 sm:px-8">
          {/* Header */}
          <div className="grid gap-6 lg:grid-cols-[1fr_auto] lg:items-end">
            <div>
              <div className="reveal">
                <p className="flex items-center gap-2 text-[12.5px] font-semibold uppercase tracking-[0.16em] text-[#315FBA]">
                  <span className="h-px w-6 bg-current opacity-60" />
                  How It Works
                </p>
              </div>
              <h2 className="reveal mt-3 sm:mt-5 max-w-3xl text-[30px] font-semibold leading-[1.08] tracking-[-0.035em] text-[#203653] sm:text-[40px] lg:text-[46px]">
                From scattered information to a structured handover.
              </h2>
            </div>
            <div className="reveal lg:text-right">
              <p className="text-[13.5px] text-[#718096]">
                Scroll to advance or select any stage directly
              </p>
              <div className="hidden lg:flex items-center justify-end gap-2 mt-1.5 font-mono text-[11px] text-[#718096]">
                <span
                  className={`size-1.5 rounded-full ${
                    activeStep === 4 ? "bg-[#299B80]" : "bg-[#315FBA] animate-pulse"
                  }`}
                />
                <span>
                  {activeStep === 4
                    ? "Stage 05 of 05 · Complete · Scroll to continue ↓"
                    : `Stage 0${activeStep + 1} of 05 · ${STEPS[activeStep]?.key}`}
                </span>
              </div>
            </div>
          </div>

        {/* Canonical 5-Stage Timeline Stepper */}
        <div className="relative mt-14">
          <ol className="reveal relative grid gap-0 lg:grid-cols-5 lg:gap-4">
            {/* Horizontal Connector Line (Desktop) */}
            <span className="absolute left-0 right-0 top-[19px] hidden h-px bg-[#D9E1F0] lg:block" />
            <span
              className="absolute left-0 top-[19px] hidden h-px bg-[#315FBA] transition-all duration-500 lg:block overflow-hidden"
              style={{ width: `${(activeStep / 4) * 100}%` }}
            >
              <span className="absolute inset-0 bg-gradient-to-r from-transparent via-white/75 to-transparent animate-beam" />
            </span>
            <span className="absolute bottom-0 left-[19px] top-0 w-px bg-[#D9E1F0] lg:hidden" />

            {STEPS.map((s, i) => (
              <li key={s.key} className="relative pb-8 pl-14 lg:pb-0 lg:pl-0">
                <button
                  type="button"
                  onClick={() => setActiveStep(i)}
                  className="group w-full text-left cursor-pointer focus-visible:ring-2 focus-visible:ring-[#315FBA] rounded-xl p-1 -m-1"
                >
                  <span
                    className={`absolute left-0 top-0 flex size-10 items-center justify-center rounded-full border bg-white transition-all duration-300 lg:relative ${
                      i <= activeStep
                        ? "border-[#315FBA] text-[#315FBA]"
                        : "border-[#D9E1F0] text-slate-400 group-hover:border-[#7997BE]"
                    } ${i === activeStep ? "ring-4 ring-[#315FBA]/15 shadow-xs scale-105" : ""}`}
                  >
                    <s.icon className="size-4" />
                  </span>
                  <p className="font-mono text-[12px] text-[#718096] lg:mt-5">
                    Step 0{i + 1}
                  </p>
                  <h3
                    className={`mt-1 text-[20px] font-semibold tracking-[-0.02em] transition-colors ${
                      i === activeStep ? "text-[#203653]" : "text-[#56657c]"
                    }`}
                  >
                    {s.key}
                  </h3>
                  <p className="mt-1.5 max-w-[240px] text-[13.5px] leading-relaxed text-[#718096]">
                    {s.body}
                  </p>
                </button>

                {/* Mobile Embedded Preview */}
                <div className="mt-5 lg:hidden">
                  {i === activeStep && (
                    <div className="animate-fade">
                      <StepPreview index={i} />
                    </div>
                  )}
                </div>
              </li>
            ))}
          </ol>

          {/* Desktop Centered Balanced Showcase Container */}
          <div className="mt-14 hidden lg:block">
            <div className="mx-auto max-w-4xl rounded-[24px] border border-[#D9E1F0] bg-[#F8FAFD] p-7 shadow-card">
              <div className="grid grid-cols-[1fr_1.1fr] items-center gap-10">
                {/* Left Stage Architectural Overview */}
                <div className="space-y-4">
                  <div className="flex items-center gap-2.5">
                    <span className="flex size-7 items-center justify-center rounded-lg bg-[#315FBA] text-white font-mono text-xs font-bold shadow-xs">
                      0{activeStep + 1}
                    </span>
                    <span className="font-mono text-[11.5px] font-semibold uppercase tracking-wider text-[#315FBA]">
                      Stage 0{activeStep + 1} of 05 · {STEPS[activeStep]?.key}
                    </span>
                  </div>
                  <h4 className="text-[22px] font-semibold tracking-[-0.025em] text-[#203653]">
                    {STEPS[activeStep]?.headline}
                  </h4>
                  <p className="text-[14.5px] leading-relaxed text-[#56657c]">
                    {STEPS[activeStep]?.body}
                  </p>
                  <div className="pt-2 flex items-center gap-2 text-[12px] font-mono text-[#718096]">
                    <span className="size-2 rounded-full bg-[#299B80] animate-pulse-soft" />
                    <span>Interactive verification artifact preview</span>
                  </div>
                </div>

                {/* Right Stage Interactive Preview Component */}
                <div className="min-w-0">
                  <StepPreview index={activeStep} />
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

export default HowItWorksSection;
