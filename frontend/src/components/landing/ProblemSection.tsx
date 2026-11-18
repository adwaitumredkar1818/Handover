"use client";

import React from "react";
import { CircleAlert, Network, RefreshCw } from "lucide-react";
import { SourceIcon } from "../brand";
import { OrganicScene } from "../brand/OrganicScene";
import { useReveal } from "./hooks/useReveal";
import { useElementScrollProgress } from "./motion/useElementScrollProgress";
import { useReducedMotion } from "./motion/useReducedMotion";

export function ProblemSection() {
  const revealRef = useReveal<HTMLDivElement>();
  const { ref: scrollRef, progress: scrollProgress } = useElementScrollProgress<HTMLElement>({
    startOffset: 0.9,
    endOffset: 0.25,
  });
  const reducedMotion = useReducedMotion();

  // As the visitor scrolls through the problem narrative, connection filaments fade
  const filamentOpacity = reducedMotion ? 0.55 : Math.max(0.16, 0.9 - scrollProgress * 0.75);
  const driftOffset = reducedMotion ? 0 : Math.round((scrollProgress - 0.5) * 14);

  const rows = [
    {
      num: "01",
      title: "Decisions without context",
      body: "Teams inherit architecture and production code without knowing why choices were made: the constraints, rejected alternatives, and trade-offs negotiated under pressure in scattered threads.",
      visual: (
        <div className="w-full max-w-[310px] rounded-2xl border border-[#D9E1F0] bg-white p-4.5 shadow-card">
          <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-[#718096]">
            Decision · Architecture
          </p>
          <p className="mt-1 text-[14px] font-semibold text-[#203653]">
            Decouple settlement via Kafka event stream
          </p>
          <p className="mt-3 text-[11px] font-semibold text-slate-400">
            WHY WAS THIS CHOSEN?
          </p>
          <div className="mt-1.5 space-y-1.5">
            {[88, 65, 78].map((w, i) => (
              <span
                key={i}
                className="block h-2 rounded-full bg-slate-100 animate-soft-shimmer"
                style={{ width: `${w}%`, animationDelay: `${i * 0.4}s` }}
              />
            ))}
          </div>
          <div className="mt-3.5 flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11.5px] font-medium text-red-600 animate-alert-breathe">
            <CircleAlert className="size-3.5 shrink-0" />
            <span>Author moved on without recorded rationale</span>
          </div>
        </div>
      ),
    },
    {
      num: "02",
      title: "Hidden dependencies",
      body: "Service links, credential rotation schedules, and blocking migrations sit isolated across GitHub pull requests, Jira tickets, Slack messages, and unlinked docs with fading traceability.",
      visual: (
        <div className="relative h-44 w-full max-w-[320px] rounded-2xl border border-[#D9E1F0] bg-[#F8FAFD] p-3 overflow-hidden">
          {[
            { type: "github" as const, x: 8, y: 16, animClass: "animate-float-1" },
            { type: "slack" as const, x: 58, y: 10, animClass: "animate-float-2" },
            { type: "jira" as const, x: 18, y: 60, animClass: "animate-float-3" },
            { type: "docs" as const, x: 66, y: 62, animClass: "animate-float-4" },
          ].map((item, idx) => (
            <div
              key={item.type}
              className={`absolute flex items-center gap-2 rounded-xl border border-[#D9E1F0] bg-white px-2.5 py-1.5 shadow-card ${item.animClass}`}
              style={{
                left: `${item.x}%`,
                top: `${item.y}%`,
                transform: `translateY(${idx % 2 === 0 ? driftOffset * 0.4 : -driftOffset * 0.4}px)`,
              }}
            >
              <SourceIcon type={item.type} size={22} />
              <span className="h-1.5 w-10 rounded-full bg-slate-100" />
            </div>
          ))}
          <svg
            className="absolute inset-0 h-full w-full pointer-events-none transition-opacity duration-300"
            style={{ opacity: filamentOpacity }}
            aria-hidden="true"
          >
            <path d="M90 50 L175 42" stroke="#D36D72" strokeDasharray="3 5" strokeWidth="1.4" />
            <path d="M135 120 L215 122" stroke="#D39B43" strokeDasharray="3 5" strokeWidth="1.4" />
            <path d="M85 65 L105 112" stroke="#7997BE" strokeDasharray="2 6" strokeWidth="1.2" />
            <circle cx="0" cy="0" r="2.5" fill="#315FBA" className="animate-particle-1" />
            <circle cx="0" cy="0" r="2.5" fill="#D36D72" className="animate-particle-2" />
          </svg>
          <div className="absolute bottom-2 left-3 right-3 flex items-center justify-between font-mono text-[10px] text-[#718096]">
            <span className="flex items-center gap-1">
              <Network className="size-3 text-[#D39B43]" />
              Severed trace links
            </span>
            <span className="text-red-500 font-semibold">Fragmenting</span>
          </div>
        </div>
      ),
    },
    {
      num: "03",
      title: "Unfinished work and undocumented responsibilities",
      body: "Incoming engineers spend months rediscovering incomplete migrations, edge-case timeout behaviors, and manual runbooks that no static wiki ever kept up to date.",
      visual: (
        <div className="flex w-full max-w-[320px] items-center gap-4">
          <div className="relative shrink-0">
            <svg width="84" height="84" viewBox="0 0 96 96" aria-hidden="true">
              <circle cx="48" cy="48" r="36" fill="none" stroke="#EDF1F8" strokeWidth="8" />
              <path
                d="M48 12 A36 36 0 1 1 13 40"
                fill="none"
                stroke="#D39B43"
                strokeWidth="3.5"
                strokeLinecap="round"
              />
              <path
                d="M8 33 l5 7 7-5"
                fill="none"
                stroke="#D39B43"
                strokeWidth="3.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            <RefreshCw className="absolute inset-0 m-auto size-6 text-[#D39B43] animate-spin-12" />
          </div>
          <div className="space-y-2 text-[12.5px] min-w-0 flex-1">
            {[
              { text: "Where is the deploy runbook?", animClass: "animate-queue-1" },
              { text: "Who owns credential rotation?", animClass: "animate-queue-2" },
              { text: "Why was this retry skipped?", animClass: "animate-queue-3" },
            ].map((q) => (
              <p
                key={q.text}
                className={`truncate rounded-lg border border-[#D9E1F0] bg-white px-3 py-1.5 text-[#56657c] shadow-xs ${q.animClass}`}
              >
                {q.text}
              </p>
            ))}
          </div>
        </div>
      ),
    },
  ];

  return (
    <section ref={scrollRef} className="relative bg-white py-24 sm:py-32 overflow-x-clip">
      {/* Subtle Ambient Fragmented Canvas Backing */}
      <div className="pointer-events-none absolute inset-y-0 right-0 w-full lg:w-[45%] opacity-35">
        <OrganicScene
          variant="fragmented"
          progress={scrollProgress}
          showTags={false}
          interactive={false}
          className="h-full w-full"
          label="Fragmented organizational knowledge drifting apart"
        />
      </div>

      <div ref={revealRef} className="relative z-10 mx-auto w-full max-w-[1240px] px-5 sm:px-8">
        <div className="grid gap-14 grid-cols-1 lg:grid-cols-[0.9fr_1.1fr] lg:gap-20">
          {/* Left Sticky Problem Anchor */}
          <div className="lg:sticky lg:top-28 lg:self-start">
            <div className="reveal-left">
              <p className="flex items-center gap-2 text-[12.5px] font-semibold uppercase tracking-[0.16em] text-[#315FBA]">
                <span className="h-px w-6 bg-current opacity-60" />
                The Problem
              </p>
            </div>
            <h2 className="reveal-left mt-5 text-[34px] font-semibold leading-[1.06] tracking-[-0.035em] text-[#203653] sm:text-[44px] lg:text-[50px]">
              When people leave, knowledge leaves with them.
            </h2>
            <p className="reveal-left mt-4 text-[18px] font-medium text-[#315FBA]">
              Project knowledge is fragile.
            </p>
            <p className="reveal-left mt-4 max-w-md text-[16.5px] leading-[1.65] text-[#56657c]">
              When an engineer or lead moves on, the next team doesn&apos;t just inherit open tickets. They inherit years of unwritten architectural decisions, hidden service dependencies, and operational edge cases no documentation tool ever connected.
            </p>
          </div>

          {/* Right Structured Problem List */}
          <ol className="divide-y divide-[#D9E1F0] border-y border-[#D9E1F0] bg-white/85 backdrop-blur-xs">
            {rows.map((r, idx) => (
              <li
                key={r.num}
                data-stagger-index={idx}
                className="reveal grid gap-6 py-10 sm:grid-cols-[1fr_310px] sm:items-center"
              >
                <div>
                  <p className="font-mono text-[13px] font-semibold text-[#7997BE]">{r.num}</p>
                  <h3 className="mt-2 text-[22px] sm:text-[25px] font-semibold tracking-[-0.025em] text-[#203653]">
                    {r.title}
                  </h3>
                  <p className="mt-2.5 max-w-sm text-[15px] leading-relaxed text-[#56657c]">
                    {r.body}
                  </p>
                </div>
                <div className="flex justify-start sm:justify-end">{r.visual}</div>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </section>
  );
}
