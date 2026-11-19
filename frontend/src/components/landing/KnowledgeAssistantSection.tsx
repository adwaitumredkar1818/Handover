"use client";

import React, { useState } from "react";
import {
  Bot,
  Link2,
  AlertTriangle,
  Lock,
  ShieldCheck,
  Send,
  User,
  Sparkles,
  Info,
} from "lucide-react";
import { useReveal } from "./hooks/useReveal";

interface CitationDetail {
  ref: string;
  excerpt: string;
}

interface ConversationSample {
  id: number;
  question: string;
  answer: string;
  citations: CitationDetail[];
  badge: {
    label: string;
    type: "verified" | "uncertain" | "ownership";
  };
}

const SAMPLES: ConversationSample[] = [
  {
    id: 0,
    question: "Why was Redis chosen over Memcached for session caching?",
    answer:
      "Redis was selected because the team required session persistence across cluster restarts and native pub/sub for real-time cache invalidation across asynchronous worker nodes. Memcached was evaluated in early February but rejected due to lack of durable storage.",
    citations: [
      {
        ref: "ADR-012 Redis caching strategy.pdf · Page 2",
        excerpt:
          "Decision: Adopt Redis 7 cluster mode for session token storage to preserve pub/sub invalidation channels and snapshot recovery.",
      },
      {
        ref: "payment-core #4827 · Merged commit 7f9b8c2",
        excerpt:
          "Implemented cluster-aware Redis connection pooling with graceful fallback to PostgreSQL session table on cold miss.",
      },
      {
        ref: "#payments-arch · Thread concluded Feb 20",
        excerpt:
          "Alex Chen: “Memcached was rejected because we need persistence across restarts and pub/sub invalidation across worker nodes.”",
      },
    ],
    badge: {
      label: "Grounded in verified project findings",
      type: "verified",
    },
  },
  {
    id: 1,
    question: "Who owns the payment service and acquirer credential rotation?",
    answer:
      "Alex Chen was the outgoing primary owner of the payment service and acquirer credentials. In transition HO-1042, operational ownership is assigned to Priya Shah with a scheduled rotation completion deadline of June 30.",
    citations: [
      {
        ref: "PROJ-103 · Quarterly credential rotation task",
        excerpt:
          "Ownership transfer checklist: rotate acquirer TLS certificates prior to Q3 peak settlement traffic.",
      },
      {
        ref: "HO-1042 · Transition ownership allocation",
        excerpt:
          "Outgoing: Alex Chen (Staff Backend Engineer) -> Incoming: Priya Shah (Backend Engineer), verified by Jordan Lee.",
      },
      {
        ref: "settlement-runbook.pdf · Section 4.2",
        excerpt:
          "Runbook specifies dual-key overlap window of 48 hours during scheduled credential swaps.",
      },
    ],
    badge: {
      label: "Human-verified transition ownership",
      type: "ownership",
    },
  },
  {
    id: 2,
    question: "What is the disaster recovery failover plan for the settlement database?",
    answer:
      "I do not have sufficient evidence in connected repositories or uploaded documents to answer this question. No multi-region replica failover procedure or disaster recovery runbook was found.",
    citations: [
      {
        ref: "0 supporting sources found · Gap flagged for human review",
        excerpt:
          "Retrieval search returned no documents covering PostgreSQL primary failover or multi-region disaster recovery procedures.",
      },
    ],
    badge: {
      label: "Insufficient Evidence Disclosed — Never Guessed",
      type: "uncertain",
    },
  },
  {
    id: 3,
    question: "What work is still unfinished before the Q3 settlement cutover?",
    answer:
      "Three items remain incomplete in HO-1042: (1) adding exponential retry backoff on settlement worker acquirer timeouts (unverified candidate risk), (2) executing Redis 7.x staging latency benchmarks, and (3) completing the June 30 acquirer certificate rotation.",
    citations: [
      {
        ref: "PROJ-108 · Settlement worker backoff & DLQ",
        excerpt:
          "Open work item: add dead-letter queue and retry strategy when acquirer timeouts exceed 9 minutes.",
      },
      {
        ref: "PAY / DEP-014 · Redis 7.x EOL upgrade",
        excerpt:
          "Staging cluster upgrade pending final load verification before Q3 production cutover.",
      },
    ],
    badge: {
      label: "Mixed Verified & Candidate Status Disclosed",
      type: "uncertain",
    },
  },
];

export function KnowledgeAssistantSection() {
  const ref = useReveal<HTMLElement>();
  const [activeSample, setActiveSample] = useState(0);
  const [isTyping, setIsTyping] = useState(false);
  const [expandedCitationIndex, setExpandedCitationIndex] = useState<number | null>(null);

  const current = SAMPLES[activeSample] ?? SAMPLES[0]!;

  const handleSelectSample = (idx: number) => {
    if (idx === activeSample) return;
    setActiveSample(idx);
    setExpandedCitationIndex(null);
    setIsTyping(true);
    window.setTimeout(() => {
      setIsTyping(false);
    }, 240);
  };

  return (
    <section
      ref={ref}
      id="assistant"
      className="ambient-section scroll-mt-20 bg-white py-24 sm:py-32"
    >
      <div className="mx-auto w-full max-w-[1240px] px-5 sm:px-8">
        <div className="grid gap-14 grid-cols-1 lg:grid-cols-[0.9fr_1.1fr] lg:gap-16 items-center">
          {/* Left Column: Narrative & Guarantees */}
          <div>
            <div className="reveal">
              <p className="flex items-center gap-2 text-[12.5px] font-semibold uppercase tracking-[0.16em] text-[#315FBA]">
                <span className="h-px w-6 bg-current opacity-60" />
                Project Knowledge Assistant
              </p>
            </div>
            <h2 className="reveal mt-5 text-[34px] font-semibold leading-[1.06] tracking-[-0.035em] text-[#203653] sm:text-[44px] lg:text-[50px]">
              Ask questions. Get answers grounded in project evidence.
            </h2>
            <p className="reveal mt-6 text-[17px] leading-[1.65] text-[#56657c]">
              The Knowledge Assistant helps incoming successors interrogate reconstructed project history. Every sample response cites supporting records, communicates uncertainty honestly, and enforces read-time permissions.
            </p>

            {/* Core Architectural Guarantees */}
            <ul className="reveal mt-9 space-y-5 border-l-2 border-[#D9E1F0] pl-6">
              {[
                {
                  icon: Link2,
                  title: "Every Answer Cites Its Sources",
                  body: "Every decision, responsibility, and risk cites the exact commits, pull requests, issue threads, or documents from which it was derived.",
                },
                {
                  icon: AlertTriangle,
                  title: "Uncertainty Is Disclosed, Never Guessed",
                  body: "When supporting evidence is incomplete, absent, or conflicting, the assistant explicitly communicates what is unknown rather than inventing an answer.",
                },
                {
                  icon: Lock,
                  title: "Source Permissions Enforced at Read Time",
                  body: "Project membership does not bypass tool permissions. External source ACLs are strictly checked before evidence enters retrieval context.",
                },
                {
                  icon: ShieldCheck,
                  title: "AI Never Approves Handovers",
                  body: "The model proposes findings and drafts answers. Only designated human reviewers confirm facts and authorize official handover packages.",
                },
              ].map((item) => (
                <li key={item.title}>
                  <p className="flex items-center gap-2 text-[15.5px] font-semibold text-[#203653]">
                    <item.icon className="size-4 text-[#315FBA] shrink-0" />
                    <span>{item.title}</span>
                  </p>
                  <p className="mt-1 text-[13.5px] leading-relaxed text-[#718096]">
                    {item.body}
                  </p>
                </li>
              ))}
            </ul>
          </div>

          {/* Right Column: Interactive Chat Interface Preview (Illustrative Only) */}
          <div className="reveal">
            <div className="rounded-[22px] border border-[#D9E1F0] bg-[#F8FAFD] shadow-pop overflow-hidden">
              {/* Chat Window Header */}
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#D9E1F0] bg-white px-5 py-3.5">
                <div className="flex items-center gap-2.5">
                  <span className="flex size-7 items-center justify-center rounded-lg bg-[#315FBA] text-white">
                    <Bot className="size-4" />
                  </span>
                  <div>
                    <span className="block text-[13px] font-semibold text-[#203653]">
                      Project Knowledge Assistant
                    </span>
                    <span className="block text-[11px] text-[#718096]">
                      Payment Platform · Hybrid RAG Preview
                    </span>
                  </div>
                </div>
                <span className="rounded-full border border-slate-200 bg-slate-100 px-2.5 py-0.5 font-mono text-[9.5px] font-medium text-slate-600">
                  Illustrative Demo · Predefined Samples
                </span>
              </div>

              {/* Sample Query Selectors */}
              <div className="border-b border-[#D9E1F0] bg-white/70 px-4 py-2.5 flex items-center gap-2 overflow-x-auto">
                <span className="text-[11px] font-semibold text-[#718096] uppercase font-mono tracking-wider shrink-0">
                  Try asking:
                </span>
                {SAMPLES.map((s, i) => (
                  <button
                    key={s.id}
                    type="button"
                    onClick={() => handleSelectSample(i)}
                    className={`rounded-lg px-2.5 py-1 text-[11.5px] font-medium transition cursor-pointer shrink-0 ${
                      i === activeSample
                        ? "bg-[#315FBA] text-white shadow-xs"
                        : "bg-white border border-[#D9E1F0] text-[#203653] hover:border-[#315FBA]"
                    }`}
                  >
                    Sample 0{i + 1}
                  </button>
                ))}
              </div>

              {/* Chat Message History */}
              <div className="p-5 sm:p-6 space-y-4 min-h-[350px]">
                {/* User Message */}
                <div className="flex justify-end items-start gap-2.5">
                  <div className="rounded-2xl rounded-tr-xs bg-[#203653] px-4 py-3 text-[13px] text-white max-w-[85%] shadow-xs">
                    {current.question}
                  </div>
                  <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-[#203653]/10 text-[11px] font-bold text-[#203653]">
                    <User className="size-3.5" />
                  </span>
                </div>

                {/* Assistant Response */}
                <div className="flex items-start gap-2.5">
                  <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-[#315FBA] text-white">
                    <Sparkles className="size-3.5" />
                  </span>
                  <div className="space-y-3 max-w-[90%]">
                    <div className="rounded-2xl rounded-tl-xs border border-[#D9E1F0] bg-white p-4 text-[13px] leading-relaxed text-[#203653] shadow-xs animate-fade">
                      {isTyping && (
                        <div className="flex items-center gap-1.5 mb-2.5 pb-2 border-b border-[#D9E1F0]">
                          <span className="size-1.5 rounded-full bg-[#315FBA] animate-bounce" />
                          <span className="size-1.5 rounded-full bg-[#315FBA] animate-bounce [animation-delay:0.15s]" />
                          <span className="size-1.5 rounded-full bg-[#315FBA] animate-bounce [animation-delay:0.3s]" />
                          <span className="text-[11px] font-mono text-[#718096] ml-1">
                            Displaying illustrative response...
                          </span>
                        </div>
                      )}
                      {current.answer}

                      {/* Supporting Citations */}
                      <div className="mt-3.5 pt-3 border-t border-[#D9E1F0] space-y-1.5">
                        <p className="font-mono text-[10px] uppercase tracking-wider text-[#718096] flex items-center justify-between">
                          <span className="flex items-center gap-1">
                            <Link2 className="size-3 text-[#315FBA]" />
                            Illustrative Source Citations
                          </span>
                          <span className="text-[9.5px] text-[#718096]/70">
                            Click citation to inspect
                          </span>
                        </p>
                        {current.citations.map((c, idx) => (
                          <div key={idx}>
                            <button
                              type="button"
                              onClick={() =>
                                setExpandedCitationIndex(expandedCitationIndex === idx ? null : idx)
                              }
                              className="flex w-full items-start sm:items-center justify-between gap-2 font-mono text-[11px] text-[#315FBA] bg-[#F6F8FC] hover:bg-[#EDF2FA] transition rounded-md px-2.5 py-1.5 text-left cursor-pointer"
                            >
                              <span className="min-w-0 text-[10.5px] leading-snug break-words">
                                <span className="font-semibold mr-1.5">[{idx + 1}]</span>
                                {c.ref}
                              </span>
                              <span className="text-[10px] text-[#7997BE] shrink-0 font-sans mt-0.5 sm:mt-0">
                                {expandedCitationIndex === idx ? "Hide" : "Inspect"}
                              </span>
                            </button>
                            {expandedCitationIndex === idx && (
                              <div className="mt-1 rounded-md border border-dashed border-[#7997BE]/40 bg-white p-2.5 text-[11.5px] font-sans text-[#56657c] animate-fade">
                                <p className="font-semibold text-[#203653] mb-1">
                                  Illustrative Source Excerpt · [{idx + 1}]
                                </p>
                                <p className="italic leading-relaxed">
                                  &ldquo;{c.excerpt}&rdquo;
                                </p>
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Verification Status Pill */}
                    <div>
                      <span
                        className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium ring-1 ring-inset ${
                          current.badge.type === "verified"
                            ? "bg-teal-50 text-teal-700 ring-teal-600/20"
                            : current.badge.type === "ownership"
                            ? "bg-blue-50 text-blue-700 ring-blue-600/20"
                            : "bg-amber-50 text-amber-700 ring-amber-600/20"
                        }`}
                      >
                        {current.badge.type === "verified" && <ShieldCheck className="size-3" />}
                        {current.badge.type === "uncertain" && <Info className="size-3" />}
                        <span>{current.badge.label}</span>
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Static Illustrative Notice & Read-Only Input Footer */}
              <div className="border-t border-[#D9E1F0] bg-white p-3.5 flex items-center gap-2">
                <input
                  type="text"
                  readOnly
                  aria-label="Static demonstration query input"
                  value="Static demo — select Sample 01–04 above to inspect grounded outputs"
                  className="flex-1 rounded-xl border border-[#D9E1F0] bg-slate-50 px-3.5 py-2 text-[12px] text-[#718096] outline-none cursor-not-allowed"
                />
                <button
                  type="button"
                  disabled
                  aria-label="Disabled demo send button"
                  className="flex size-9 items-center justify-center rounded-xl bg-[#203653] text-white opacity-50 cursor-not-allowed"
                >
                  <Send className="size-3.5" />
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
