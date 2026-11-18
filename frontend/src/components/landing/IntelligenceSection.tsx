"use client";

import React, { useState } from "react";
import {
  Lightbulb,
  Layers,
  ListChecks,
  UserRound,
  Network,
  AlertTriangle,
  ClipboardList,
  MessageSquare,
  GitPullRequest,
  FileText,
  SquareKanban,
  Sparkles,
  ShieldCheck,
  Link2,
} from "lucide-react";
import { LogoMark } from "../brand";
import { OrganicScene } from "../brand/OrganicScene";
import { useReveal } from "./hooks/useReveal";
import { useReducedMotion } from "./motion/useReducedMotion";

interface Category {
  key: string;
  shortKey: string;
  icon: React.ElementType;
  color: string;
  accentRgb: string;
  body: string;
  finding: string;
  meta: string;
  evidenceIndices: number[];
  confidence: number;
  verified: boolean;
}

const CATEGORIES: Category[] = [
  {
    key: "Decisions & Rationale",
    shortKey: "Decisions",
    icon: Lightbulb,
    color: "#315FBA",
    accentRgb: "49,95,186",
    body: "Understand what architectural choices were made, who decided them, and the underlying trade-offs.",
    finding: "Decouple settlement from ledger via Kafka event stream",
    meta: "Alex Chen · Accepted · 3 evidence sources",
    evidenceIndices: [0, 1, 2],
    confidence: 94,
    verified: true,
  },
  {
    key: "Technical & Architectural Knowledge",
    shortKey: "Architecture",
    icon: Layers,
    color: "#203653",
    accentRgb: "32,54,83",
    body: "Map system topology, asynchronous queues, data models, and persistence layer constraints.",
    finding: "Settlement worker consumes Kafka events with idempotent writes",
    meta: "Component: Settlement Service · 4 evidence sources",
    evidenceIndices: [0, 2],
    confidence: 91,
    verified: true,
  },
  {
    key: "Completed & Unfinished Work",
    shortKey: "Work Status",
    icon: ListChecks,
    color: "#299B80",
    accentRgb: "41,155,128",
    body: "Track delivered features, partial migrations, deferred refactors, and active in-flight PRs.",
    finding: "Redis session cache merged; performance benchmarks pending in staging",
    meta: "PR-4827 · Merged · Follow-up PROJ-108 pending",
    evidenceIndices: [0, 3],
    confidence: 88,
    verified: false,
  },
  {
    key: "Responsibilities & Ownership",
    shortKey: "Ownership",
    icon: UserRound,
    color: "#7997BE",
    accentRgb: "121,151,190",
    body: "Assign explicit service maintenance, on-call runbooks, and transition ownership participants.",
    finding: "Rotate acquirer API credentials and update certificates",
    meta: "Primary: Alex Chen → Successor: Priya Shah · Due Jun 30",
    evidenceIndices: [3, 2],
    confidence: 86,
    verified: true,
  },
  {
    key: "Dependencies",
    shortKey: "Dependencies",
    icon: Network,
    color: "#D39B43",
    accentRgb: "211,155,67",
    body: "Map relationships between microservices, database schemas, third-party APIs, and team owners.",
    finding: "SOAP migration is blocked until acquirer credential rotation is complete",
    meta: "Component blocking dependency · Critical path",
    evidenceIndices: [3, 0],
    confidence: 90,
    verified: true,
  },
  {
    key: "Bugs, Blockers & Risks",
    shortKey: "Risks",
    icon: AlertTriangle,
    color: "#D36D72",
    accentRgb: "211,109,114",
    body: "Identify unresolved failure modes, single points of failure, technical debt, and pending blockers.",
    finding: "Settlement worker has no retry mechanism on acquirer timeouts",
    meta: "High severity · Settlement Service · Manual recovery required",
    evidenceIndices: [1, 3],
    confidence: 83,
    verified: false,
  },
  {
    key: "Operational Procedures",
    shortKey: "Procedures",
    icon: ClipboardList,
    color: "#8B78C9",
    accentRgb: "139,120,201",
    body: "Document runbooks, deployment pipelines, failover steps, and incident response procedures.",
    finding: "Settlement batch requires manual reconcile script after acquirer outages",
    meta: "Runbook section 4.2 · Last updated Mar 02",
    evidenceIndices: [2, 1],
    confidence: 89,
    verified: true,
  },
  {
    key: "Historical Discussions & Context",
    shortKey: "Discussions",
    icon: MessageSquare,
    color: "#A0AEC0",
    accentRgb: "160,174,192",
    body: "Surface past architectural debates, rejected alternatives, and why legacy code is structured as it is.",
    finding: "RabbitMQ was rejected for settlement due to lack of persistent event audit log",
    meta: "#payments-arch · 14 replies · Concluded Feb 20",
    evidenceIndices: [1, 2],
    confidence: 87,
    verified: true,
  },
];

const RAW_EVIDENCE = [
  {
    icon: GitPullRequest,
    source: "payment-core #4827",
    text: "Move settlement out of the synchronous ledger transaction path to eliminate database lock contention.",
  },
  {
    icon: MessageSquare,
    source: "#payments-arch",
    text: "“Publish ledger.entry.posted events to Kafka and let the settlement worker consume asynchronously with idempotent writes.”",
  },
  {
    icon: FileText,
    source: "ADR-007.pdf",
    text: "Status: Accepted. At-least-once delivery with idempotent consumer writes across partition replicas.",
  },
  {
    icon: SquareKanban,
    source: "PROJ-103",
    text: "Quarterly acquirer credential rotation. Blocks gateway cutover and SOAP migration tasks.",
  },
];

export function IntelligenceSection() {
  const ref = useReveal<HTMLElement>();
  const reducedMotion = useReducedMotion();
  const [activeCategory, setActiveCategory] = useState(0);
  const current = CATEGORIES[activeCategory] ?? CATEGORIES[0]!;

  // Coordinates around center (160, 125) in a 320x250 radial SVG ring
  const radialPositions = CATEGORIES.map((c, idx) => {
    const angle = (idx / CATEGORIES.length) * Math.PI * 2 - Math.PI / 2;
    const rx = 112;
    const ry = 88;
    return {
      idx,
      c,
      x: 160 + Math.cos(angle) * rx,
      y: 125 + Math.sin(angle) * ry,
    };
  });

  return (
    <section
      ref={ref}
      id="intelligence"
      className="ambient-section relative scroll-mt-20 overflow-hidden py-24 sm:py-32"
    >
      {/* Expansive Background Knowledge Network */}
      <div className="pointer-events-none absolute inset-0 z-0 overflow-hidden">
        <OrganicScene
          variant="network"
          accent={current.accentRgb}
          camZoom={1.38}
          camOffset={[0.24, 0.02]}
          className="h-full w-full opacity-65"
          label="Expansive organic knowledge network representing relationship graphs of project knowledge"
        />
        <div
          className="absolute inset-y-0 left-0 w-full sm:w-[54%] lg:w-[44%] z-[1]"
          style={{
            background:
              "linear-gradient(to right, #F6F8FC 0%, rgba(246,248,252,0.94) 40%, rgba(246,248,252,0.7) 75%, transparent 100%)",
          }}
        />
        <div className="absolute inset-x-0 top-0 h-20 bg-gradient-to-b from-[#F6F8FC] to-transparent z-[1]" />
        <div className="absolute inset-x-0 bottom-0 h-44 bg-gradient-to-t from-[#F6F8FC] via-[#F6F8FC]/95 to-transparent z-[1]" />
      </div>

      <div className="relative z-10 mx-auto w-full max-w-[1240px] px-5 sm:px-8">
        <div className="relative grid gap-14 grid-cols-1 lg:grid-cols-[0.95fr_1.05fr] lg:gap-16">
          {/* Left Column: 8-Domain Constellation + Cards */}
          <div>
            <div className="reveal">
              <p className="flex items-center gap-2 text-[12.5px] font-semibold uppercase tracking-[0.16em] text-[#8B78C9]">
                <span className="h-px w-6 bg-current opacity-60" />
                Eight Knowledge Domains
              </p>
            </div>
            <h2 className="reveal mt-5 text-[34px] font-semibold leading-[1.06] tracking-[-0.035em] text-[#203653] sm:text-[42px] lg:text-[48px]">
              Understand the complete picture.
            </h2>
            <p className="reveal mt-3 text-[16.5px] font-medium text-[#315FBA]">
              Eight domains of project knowledge. One connected intelligence layer.
            </p>
            <p className="reveal mt-3 text-[15.5px] leading-[1.65] text-[#56657c]">
              Handover classifies reconstructed artifacts into eight canonical project domains, distinguishing provisional AI candidates from findings explicitly confirmed by humans.
            </p>

            {/* Radial 8-Domain Network Map */}
            <div className="reveal mt-6 rounded-2xl border border-[#D9E1F0] bg-white/85 p-3 shadow-xs backdrop-blur-xs">
              <svg viewBox="0 0 320 250" className="w-full h-[210px]" aria-label="Eight knowledge domains connected to central core">
                {radialPositions.map(({ idx, c, x, y }) => {
                  const isActive = idx === activeCategory;
                  return (
                    <g key={c.key}>
                      <line
                        x1="160"
                        y1="125"
                        x2={x}
                        y2={y}
                        stroke={isActive ? c.color : "#D9E1F0"}
                        strokeWidth={isActive ? 2.2 : 1.1}
                        strokeDasharray={isActive ? "4 3" : undefined}
                        className={isActive && !reducedMotion ? "animate-stream-flow" : ""}
                      />
                      <g
                        onClick={() => setActiveCategory(idx)}
                        className="cursor-pointer"
                        tabIndex={0}
                        aria-label={`Select domain ${c.key}`}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            setActiveCategory(idx);
                          }
                        }}
                      >
                        <title>{c.key}</title>
                        <circle
                          cx={x}
                          cy={y}
                          r={isActive ? 15 : 12}
                          fill={isActive ? c.color : "white"}
                          stroke={c.color}
                          strokeWidth="2"
                          className="transition-all duration-300"
                        />
                        <text
                          x={x}
                          y={y + 3.5}
                          textAnchor="middle"
                          fontSize="8.5"
                          fontWeight="700"
                          fill={isActive ? "white" : "#203653"}
                          fontFamily="var(--font-mono), monospace"
                        >
                          0{idx + 1}
                        </text>
                      </g>
                    </g>
                  );
                })}
                {/* Central Organic Core */}
                <circle cx="160" cy="125" r="24" fill="#EEF2FA" stroke="#315FBA" strokeWidth="1.5" />
                <circle cx="160" cy="125" r="14" fill="#203653" />
                <text
                  x="160"
                  y="128"
                  textAnchor="middle"
                  fontSize="8.5"
                  fontWeight="700"
                  fill="white"
                  fontFamily="var(--font-mono), monospace"
                >
                  CORE
                </text>
              </svg>
            </div>

            {/* 8-Domain Grid Selector */}
            <div className="reveal mt-5 grid grid-cols-1 sm:grid-cols-2 gap-2">
              {CATEGORIES.map((c, i) => (
                <button
                  key={c.key}
                  type="button"
                  onClick={() => setActiveCategory(i)}
                  className={`flex items-start gap-3 rounded-xl border p-3 text-left transition-all duration-300 cursor-pointer ${
                    i === activeCategory
                      ? "border-[#315FBA] bg-white shadow-card ring-2 ring-[#315FBA]/25 scale-[1.02] opacity-100"
                      : "border-transparent bg-white/70 hover:bg-white/95 opacity-75 hover:opacity-100"
                  }`}
                >
                  <span
                    className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg"
                    style={{ background: `${c.color}15`, color: c.color }}
                  >
                    <c.icon className="size-4" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[13px] font-semibold text-[#203653]">
                      {c.shortKey}
                    </span>
                    <span className="block text-[11px] text-[#718096] truncate">
                      {c.key}
                    </span>
                  </span>
                </button>
              ))}
            </div>

            {/* Active Domain Description */}
            <div className="reveal mt-4 rounded-xl border border-[#D9E1F0] bg-white/90 p-4 shadow-xs">
              <p className="flex items-center gap-2 text-[13px] font-semibold text-[#203653]">
                <span className="size-2 rounded-full" style={{ background: current.color }} />
                {current.key}
              </p>
              <p className="mt-1 text-[13px] leading-relaxed text-[#718096]">
                {current.body}
              </p>
            </div>
          </div>

          {/* Right Column: Raw Evidence -> Structured Finding Card */}
          <div className="reveal relative self-center rounded-[24px] border border-[#D9E1F0] bg-white/95 p-5 shadow-card backdrop-blur-xs sm:p-7">
            <div className="mb-5 flex flex-wrap items-center justify-between gap-2 border-b border-[#D9E1F0] pb-3">
              <span className="font-mono text-[11px] uppercase tracking-wider text-[#718096]">
                Architecture Preview · Sample Data
              </span>
              <span className="rounded-full border border-slate-200 bg-slate-100 px-2 py-0.5 font-mono text-[10px] font-semibold text-slate-500">
                Illustrative demonstration · Not live data
              </span>
            </div>

            <div className="grid gap-6 sm:grid-cols-[1fr_40px_1fr] sm:items-center">
              {/* Raw Evidence List */}
              <div className="space-y-2.5">
                <p className="font-mono text-[11px] font-medium text-[#718096]">
                  SUPPORTING EVIDENCE
                </p>
                {RAW_EVIDENCE.map((f, i) => (
                  <div
                    key={f.source}
                    className={`rounded-xl border bg-white p-3 transition-all duration-300 ${
                      current.evidenceIndices.includes(i)
                        ? "border-[#7997BE]/80 shadow-xs ring-1 ring-[#7997BE]/20"
                        : "border-[#D9E1F0] opacity-45"
                    }`}
                  >
                    <p className="flex items-center gap-1.5 font-mono text-[11px] text-[#718096]">
                      <f.icon className="size-3 text-[#315FBA]" />
                      <span>{f.source}</span>
                    </p>
                    <p className="mt-1 text-[12px] leading-snug text-[#3e5373]">
                      {f.text}
                    </p>
                  </div>
                ))}
              </div>

              {/* Connecting Brand Anchor */}
              <div className="hidden h-full flex-col items-center justify-center gap-2 sm:flex" aria-hidden="true">
                <span className="relative h-16 w-px bg-[#D9E1F0] overflow-hidden">
                  <span className="absolute inset-0 bg-gradient-to-b from-transparent via-[#315FBA] to-transparent animate-beam" />
                </span>
                <span className="flex size-10 items-center justify-center rounded-xl border border-[#D9E1F0] bg-white shadow-xs">
                  <LogoMark size={22} />
                </span>
                <span className="relative h-16 w-px bg-[#D9E1F0] overflow-hidden">
                  <span
                    className="absolute inset-0 bg-gradient-to-t from-transparent via-[#299B80] to-transparent animate-beam"
                    style={{ animationDelay: "1.2s" }}
                  />
                </span>
              </div>

              {/* Reconstructed Finding Box */}
              <div key={activeCategory} className="animate-fade space-y-3">
                <p className="font-mono text-[11px] font-medium text-[#718096]">
                  STRUCTURED FINDING
                </p>
                <div className="rounded-2xl border border-[#D9E1F0] bg-white p-4.5 shadow-lift">
                  <p
                    className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.1em]"
                    style={{ color: current.color }}
                  >
                    <current.icon className="size-3.5" />
                    <span>{current.shortKey}</span>
                  </p>
                  <p className="mt-2 text-[14.5px] font-semibold leading-snug text-[#203653]">
                    {current.finding}
                  </p>
                  <p className="mt-1 text-[12px] text-[#718096]">{current.meta}</p>

                  <div className="mt-4 flex flex-wrap items-center gap-1.5">
                    <span className="inline-flex items-center gap-1 rounded-md border border-dashed border-indigo-200 bg-indigo-50 px-2 py-0.5 text-[11px] font-medium text-indigo-700">
                      <Sparkles className="size-3" />
                      AI {current.confidence}%
                    </span>
                    <span
                      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset ${
                        current.verified
                          ? "bg-teal-50 text-teal-700 ring-teal-600/20"
                          : "bg-amber-50 text-amber-700 ring-amber-600/20"
                      }`}
                    >
                      {current.verified ? (
                        <>
                          <ShieldCheck className="size-3" />
                          Verified
                        </>
                      ) : (
                        "Candidate (Needs Review)"
                      )}
                    </span>
                  </div>

                  {/* Epistemic 4-Tier Transformation Progress */}
                  <div className="mt-3.5 pt-3 border-t border-[#D9E1F0]">
                    <div className="flex items-center justify-between text-[10px] font-mono mb-1.5">
                      <span className="text-[#718096]">EPISTEMIC STATE</span>
                      <span className={`font-semibold ${current.verified ? "text-[#299B80]" : "text-amber-600"}`}>
                        {current.verified ? "Human-Verified (Tier 4)" : "AI Candidate (Tier 3)"}
                      </span>
                    </div>
                    <div className="grid grid-cols-4 gap-1">
                      <span className="h-1 rounded-full bg-[#718096]" title="Tier 1: Original Source Evidence" />
                      <span className="h-1 rounded-full bg-[#315FBA]" title="Tier 2: Extracted Information" />
                      <span className="h-1 rounded-full bg-[#8B78C9]" title="Tier 3: AI Interpretation" />
                      <span
                        className={`h-1 rounded-full ${current.verified ? "bg-[#299B80]" : "bg-slate-200"}`}
                        title="Tier 4: Human-Verified Knowledge"
                      />
                    </div>
                  </div>
                </div>

                <div className="rounded-xl border border-dashed border-[#D9E1F0] p-3 text-[12px] text-[#718096] bg-[#F6F8FC]/50">
                  <Link2 className="mr-1.5 inline size-3 text-[#315FBA]" />
                  Linked to {current.evidenceIndices.length} illustrative source records
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
