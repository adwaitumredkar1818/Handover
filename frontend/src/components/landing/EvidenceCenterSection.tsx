"use client";

import React, { useState } from "react";
import {
  FileSearch,
  ExternalLink,
  Hash,
  Clock,
  User,
  ShieldCheck,
  CheckCircle2,
  Filter,
  Search,
  ArrowRight,
} from "lucide-react";
import { SourceIcon } from "../brand";
import { useReveal } from "./hooks/useReveal";

type SourceFilter = "all" | "github" | "jira" | "slack" | "docs";

interface EvidenceItem {
  id: string;
  sourceType: "github" | "jira" | "slack" | "docs";
  sourceName: string;
  title: string;
  author: string;
  timestamp: string;
  hash: string;
  snippet: string;
  linkedFindings: {
    domain: string;
    text: string;
    status: "verified" | "review";
  }[];
}

const EVIDENCE_ITEMS: EvidenceItem[] = [
  {
    id: "ev-1",
    sourceType: "github",
    sourceName: "payment-core #4827",
    title: "Introduce Redis caching layer for session tokens",
    author: "Alex Chen",
    timestamp: "2026-03-12 14:22 UTC",
    hash: "sha256:7f9b8c2d1e0a4f5...",
    snippet: "Merged pull request implementing cluster-aware Redis connection pooling and fallback to Postgres session table on cache miss.",
    linkedFindings: [
      { domain: "Decision", text: "Redis chosen for session token caching over Memcached", status: "verified" },
      { domain: "Risk", text: "Cold-start cache stampede during deployment rollout", status: "review" },
    ],
  },
  {
    id: "ev-2",
    sourceType: "jira",
    sourceName: "PAY / PROJ-103",
    title: "Improve API response time for dashboard endpoints",
    author: "Jordan Lee",
    timestamp: "2026-03-08 09:45 UTC",
    hash: "sha256:3a1b4c7d9e2f6a8...",
    snippet: "Resolution: Done. Latency reduced from 420ms to 68ms via Redis cache warming on authentication exchange.",
    linkedFindings: [
      { domain: "Work Status", text: "Session cache deployment completed and verified in staging", status: "verified" },
    ],
  },
  {
    id: "ev-3",
    sourceType: "slack",
    sourceName: "#payments-arch",
    title: "Thread: Redis vs Memcached for session caching",
    author: "Alex Chen",
    timestamp: "2026-02-20 18:10 UTC",
    hash: "sha256:8c4d2e1f9a7b3c5...",
    snippet: "“Memcached was rejected because we need persistence across restarts and pub/sub for invalidation across worker nodes.”",
    linkedFindings: [
      { domain: "Historical Context", text: "Memcached rejected due to lack of native pub/sub invalidation", status: "verified" },
      { domain: "Decision", text: "Redis selected as unified cache and session store", status: "verified" },
    ],
  },
  {
    id: "ev-4",
    sourceType: "docs",
    sourceName: "ADR-007.pdf",
    title: "Architecture Decision Record: Event-driven settlement",
    author: "Alex Chen",
    timestamp: "2026-01-15 11:30 UTC",
    hash: "sha256:1e2f3a4b5c6d7e8...",
    snippet: "Status: Accepted. Ledger publishes ledger.entry.posted events to Kafka; settlement worker consumes asynchronously with idempotent writes.",
    linkedFindings: [
      { domain: "Architecture", text: "Decoupled settlement worker from synchronous ledger path", status: "verified" },
      { domain: "Dependency", text: "Kafka broker cluster replication factor set to 3", status: "verified" },
    ],
  },
  {
    id: "ev-5",
    sourceType: "jira",
    sourceName: "PAY / DEP-014",
    title: "Redis 7.x dependency — upgrade before EOL",
    author: "Priya Shah",
    timestamp: "2026-03-14 16:05 UTC",
    hash: "sha256:9f8e7d6c5b4a3a2...",
    snippet: "Redis 6.2 reaching end-of-life Q3. Upgrade to Redis 7.2 cluster planned before peak holiday settlement volume.",
    linkedFindings: [
      { domain: "Dependency", text: "Redis 7.x cluster upgrade scheduled prior to Q3 EOL", status: "review" },
      { domain: "Ownership", text: "Priya Shah assigned to lead cluster migration", status: "verified" },
    ],
  },
  {
    id: "ev-6",
    sourceType: "docs",
    sourceName: "settlement-runbook.pdf",
    title: "Settlement Worker Operational Runbook (v3.2)",
    author: "Alex Chen",
    timestamp: "2026-03-02 10:15 UTC",
    hash: "sha256:5b6c7d8e9f0a1b2...",
    snippet: "Section 4.2: Handling acquirer timeout recovery. If batch timeout exceeds 9 minutes, run manual reconcile script ./scripts/reconcile-acquirer.sh.",
    linkedFindings: [
      { domain: "Operational Procedure", text: "Manual reconciliation script required after acquirer timeouts", status: "verified" },
      { domain: "Risk", text: "Settlement worker lacks automated retry logic on timeouts", status: "review" },
    ],
  },
];

export function EvidenceCenterSection() {
  const ref = useReveal<HTMLElement>();
  const [activeFilter, setActiveFilter] = useState<SourceFilter>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string>("ev-1");
  const [mobileTab, setMobileTab] = useState<"sources" | "library" | "details">("library");

  const filteredItems = EVIDENCE_ITEMS.filter((item) => {
    const matchesFilter = activeFilter === "all" || item.sourceType === activeFilter;
    const matchesQuery =
      searchQuery.trim() === "" ||
      item.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      item.sourceName.toLowerCase().includes(searchQuery.toLowerCase()) ||
      item.author.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesFilter && matchesQuery;
  });

  const selectedItem =
    EVIDENCE_ITEMS.find((item) => item.id === selectedId) || EVIDENCE_ITEMS[0]!;

  return (
    <section
      ref={ref}
      id="evidence"
      className="ambient-section scroll-mt-20 bg-[#F6F8FC] py-24 sm:py-32"
    >
      <div className="mx-auto w-full max-w-[1240px] px-5 sm:px-8">
        {/* Section Header */}
        <div className="mx-auto max-w-3xl text-center">
          <div className="reveal flex justify-center">
            <p className="flex items-center gap-2 text-[12.5px] font-semibold uppercase tracking-[0.16em] text-[#315FBA]">
              <span className="h-px w-6 bg-current opacity-60" />
              Evidence Center
            </p>
          </div>
          <h2 className="reveal mt-5 text-[34px] font-semibold leading-[1.06] tracking-[-0.035em] text-[#203653] sm:text-[44px] lg:text-[50px]">
            Every insight starts with something real.
          </h2>
          <p className="reveal mt-3 text-[17px] font-medium text-[#315FBA]">
            Every finding traced to its source.
          </p>
          <p className="reveal mx-auto mt-4 max-w-2xl text-[16.5px] leading-[1.65] text-[#56657c]">
            The Evidence Center brings together illustrative connected artifacts — pull requests, issue threads, discussions, and documents — into a searchable three-panel workspace tracing every candidate finding back to original evidence.
          </p>
        </div>

        {/* Three-Panel Showcase Container */}
        <div className="reveal mt-14 overflow-hidden rounded-[22px] border border-[#D9E1F0] bg-white shadow-pop">
          {/* Top Bar */}
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#D9E1F0] bg-white px-5 py-3">
            <div className="flex items-center gap-2.5 flex-wrap">
              <span className="flex size-7 items-center justify-center rounded-lg bg-[#315FBA]/10 text-[#315FBA]">
                <FileSearch className="size-4" />
              </span>
              <span className="text-[13px] font-semibold text-[#203653]">
                Payment Platform
              </span>
              <span className="text-slate-300">/</span>
              <span className="text-[13px] text-[#718096]">Evidence Center</span>
              <span className="rounded-full border border-slate-200 bg-slate-100 px-2 py-0.5 font-mono text-[10px] font-medium text-slate-500">
                Illustrative product preview
              </span>
            </div>

            {/* Mobile View Toggle */}
            <div className="flex md:hidden rounded-lg bg-slate-100 p-0.5 text-[11.5px] font-medium text-[#718096]">
              <button
                type="button"
                onClick={() => setMobileTab("sources")}
                className={`rounded-md px-2.5 py-1 ${
                  mobileTab === "sources" ? "bg-white font-semibold text-[#203653] shadow-xs" : ""
                }`}
              >
                Sources
              </button>
              <button
                type="button"
                onClick={() => setMobileTab("library")}
                className={`rounded-md px-2.5 py-1 ${
                  mobileTab === "library" ? "bg-white font-semibold text-[#203653] shadow-xs" : ""
                }`}
              >
                Library
              </button>
              <button
                type="button"
                onClick={() => setMobileTab("details")}
                className={`rounded-md px-2.5 py-1 ${
                  mobileTab === "details" ? "bg-white font-semibold text-[#203653] shadow-xs" : ""
                }`}
              >
                Details
              </button>
            </div>
          </div>

          {/* Three-Panel Body */}
          <div className="grid min-h-[510px] md:grid-cols-[235px_1fr_345px]">
            {/* PANEL A: Connected Sources Sidebar (Interactive filter buttons) */}
            <div
              className={`border-r border-[#D9E1F0] bg-[#F8FAFD] p-4 ${
                mobileTab === "sources" ? "block" : "hidden md:block"
              }`}
            >
              <div className="flex items-center justify-between mb-3">
                <p className="font-mono text-[11px] font-semibold uppercase tracking-wider text-[#718096]">
                  Connected Sources
                </p>
                {activeFilter !== "all" && (
                  <button
                    type="button"
                    onClick={() => setActiveFilter("all")}
                    className="font-mono text-[10px] text-[#315FBA] hover:underline cursor-pointer"
                  >
                    Show all
                  </button>
                )}
              </div>

              <div className="space-y-1.5">
                {[
                  { type: "github" as const, label: "GitHub Repositories", count: 3, detail: "payment-core, settlement, gateway" },
                  { type: "jira" as const, label: "Jira Projects", count: 2, detail: "PAY, SPRINT-34" },
                  { type: "slack" as const, label: "Slack Channels", count: 4, detail: "#payments-arch, #incidents" },
                  { type: "docs" as const, label: "Uploaded Documents", count: 8, detail: "ADRs, Runbooks, Specs" },
                ].map((s) => {
                  const isActiveSource = activeFilter === s.type;
                  return (
                    <button
                      key={s.label}
                      type="button"
                      onClick={() => {
                        setActiveFilter(isActiveSource ? "all" : s.type);
                        setMobileTab("library");
                      }}
                      className={`group w-full rounded-xl border p-3 text-left transition cursor-pointer shadow-xs ${
                        isActiveSource
                          ? "border-[#315FBA] bg-white ring-2 ring-[#315FBA]/15"
                          : "border-[#D9E1F0]/80 bg-white hover:border-[#315FBA]/40"
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 min-w-0">
                          <SourceIcon type={s.type} size={20} />
                          <span className="text-[12.5px] font-semibold text-[#203653] truncate">
                            {s.label}
                          </span>
                        </div>
                        <span className="rounded-full bg-slate-100 px-2 py-0.5 font-mono text-[11px] font-bold text-[#315FBA]">
                          {s.count}
                        </span>
                      </div>
                      <p className="mt-1.5 text-[11px] text-[#718096] truncate">
                        {s.detail}
                      </p>
                    </button>
                  );
                })}
              </div>

              <div className="mt-6 rounded-xl border border-dashed border-[#D9E1F0] bg-white/70 p-3 text-[11px] text-[#718096]">
                <p className="font-semibold text-[#203653] flex items-center gap-1.5">
                  <ShieldCheck className="size-3.5 text-[#299B80]" />
                  Strict Read-Only Access
                </p>
                <p className="mt-1 leading-snug">
                  Source-level ACLs are evaluated before any evidence item enters retrieval.
                </p>
              </div>
            </div>

            {/* PANEL B: Evidence Library Table */}
            <div
              className={`flex flex-col border-r border-[#D9E1F0] bg-white ${
                mobileTab === "library" ? "block" : "hidden md:flex"
              }`}
            >
              {/* Filter Tabs */}
              <div className="flex items-center gap-1.5 border-b border-[#D9E1F0] px-4 py-2.5 bg-[#FBFDFE] overflow-x-auto">
                <Filter className="size-3.5 text-[#7997BE] mr-1 shrink-0" />
                {(
                  [
                    { id: "all", label: "All Evidence" },
                    { id: "github", label: "GitHub" },
                    { id: "jira", label: "Jira" },
                    { id: "slack", label: "Slack" },
                    { id: "docs", label: "Documents" },
                  ] as const
                ).map((tab) => (
                  <button
                    key={tab.id}
                    type="button"
                    onClick={() => setActiveFilter(tab.id)}
                    className={`rounded-lg px-2.5 py-1 text-[12px] font-medium transition cursor-pointer shrink-0 ${
                      activeFilter === tab.id
                        ? "bg-[#203653] text-white"
                        : "text-[#718096] hover:bg-slate-100 hover:text-[#203653]"
                    }`}
                  >
                    {tab.label}
                  </button>
                ))}
                <span className="ml-auto font-mono text-[11px] text-[#718096] hidden sm:inline">
                  {filteredItems.length} items
                </span>
              </div>

              {/* Search Bar */}
              <div className="relative border-b border-[#D9E1F0] px-4 py-2 bg-white">
                <Search className="absolute left-7 top-1/2 -translate-y-1/2 size-3.5 text-[#7997BE]" />
                <input
                  type="text"
                  aria-label="Filter evidence records"
                  placeholder="Filter by title, author, or identifier..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full rounded-lg border border-[#D9E1F0] bg-[#F8FAFD] pl-8 pr-3 py-1.5 text-[12px] text-[#203653] placeholder:text-[#718096]/60 focus:border-[#315FBA] focus:bg-white outline-none transition"
                />
              </div>

              {/* Items List */}
              <div className="flex-1 divide-y divide-[#D9E1F0] overflow-y-auto">
                {filteredItems.map((item) => {
                  const isSelected = item.id === selectedId;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => {
                        setSelectedId(item.id);
                        setMobileTab("details");
                      }}
                      className={`flex w-full items-start gap-3 p-4 text-left transition cursor-pointer ${
                        isSelected
                          ? "bg-[#F0F5FD] border-l-3 border-[#315FBA]"
                          : "hover:bg-[#F9FBFE]"
                      }`}
                    >
                      <SourceIcon type={item.sourceType} size={24} />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-[11px] font-semibold text-[#315FBA] truncate">
                            {item.sourceName}
                          </span>
                          <span className="text-[11px] text-slate-300">·</span>
                          <span className="text-[11px] text-[#718096] truncate">
                            {item.author}
                          </span>
                        </div>
                        <p className="mt-1 text-[13px] font-semibold leading-snug text-[#203653] line-clamp-1">
                          {item.title}
                        </p>
                        <p className="mt-1 text-[11.5px] leading-snug text-[#718096] line-clamp-1">
                          {item.snippet}
                        </p>
                      </div>
                    </button>
                  );
                })}
                {filteredItems.length === 0 && (
                  <div className="p-8 text-center text-[13px] text-[#718096]">
                    No illustrative records match your filter.
                  </div>
                )}
              </div>
            </div>

            {/* PANEL C: Evidence Details Pane */}
            <div
              className={`bg-[#FAFCFF] p-5 ${
                mobileTab === "details" ? "block" : "hidden md:block"
              }`}
            >
              <div className="flex items-center justify-between border-b border-[#D9E1F0] pb-3">
                <span className="flex items-center gap-1.5 font-mono text-[11px] font-semibold text-[#718096] uppercase tracking-wider">
                  <SourceIcon type={selectedItem.sourceType} size={16} />
                  {selectedItem.sourceType.toUpperCase()} ITEM
                </span>
                <span className="rounded-md bg-slate-100 px-2 py-0.5 font-mono text-[10px] text-[#718096]">
                  {selectedItem.id}
                </span>
              </div>

              <div className="mt-4 space-y-4">
                <div>
                  <h4 className="text-[15px] font-semibold leading-snug text-[#203653]">
                    {selectedItem.title}
                  </h4>
                  <p className="mt-1 font-mono text-[11px] text-[#315FBA]">
                    {selectedItem.sourceName}
                  </p>
                </div>

                {/* Metadata Grid */}
                <div className="grid grid-cols-2 gap-2 text-[11.5px] text-[#718096]">
                  <div className="flex items-center gap-1.5 rounded-lg bg-white p-2 border border-[#D9E1F0]">
                    <User className="size-3 text-[#7997BE]" />
                    <span className="truncate">{selectedItem.author}</span>
                  </div>
                  <div className="flex items-center gap-1.5 rounded-lg bg-white p-2 border border-[#D9E1F0]">
                    <Clock className="size-3 text-[#7997BE]" />
                    <span className="truncate">Mar 2026</span>
                  </div>
                </div>

                {/* Snippet Card */}
                <div className="rounded-xl border border-[#D9E1F0] bg-white p-3">
                  <p className="font-mono text-[10px] uppercase tracking-wider text-slate-400 mb-1.5">
                    Original Evidence Excerpt
                  </p>
                  <p className="text-[12px] leading-relaxed text-[#3e5373] italic">
                    &ldquo;{selectedItem.snippet}&rdquo;
                  </p>
                </div>

                {/* Canonical Provenance Chain */}
                <div className="rounded-xl border border-[#D9E1F0] bg-white p-3">
                  <p className="font-mono text-[9.5px] uppercase tracking-wider text-[#718096] mb-2 flex items-center justify-between">
                    <span>Provenance Chain</span>
                    <span className="text-[#299B80] font-semibold">Traceable</span>
                  </p>
                  <div className="flex flex-wrap items-center gap-1 text-[9.5px] font-mono">
                    <span className="rounded bg-slate-100 px-1.5 py-1 text-[#203653] font-semibold">
                      ORIGINAL SOURCE
                    </span>
                    <ArrowRight className="size-3 text-[#315FBA] shrink-0" />
                    <span className="rounded bg-blue-50 px-1.5 py-1 text-[#315FBA] font-semibold">
                      EXTRACTED INFORMATION
                    </span>
                    <ArrowRight className="size-3 text-[#8B78C9] shrink-0" />
                    <span className="rounded bg-indigo-50 px-1.5 py-1 text-indigo-700 font-semibold">
                      CANDIDATE FINDING
                    </span>
                  </div>
                </div>

                {/* Linked Reconstructed Findings */}
                <div>
                  <p className="font-mono text-[10.5px] font-semibold uppercase tracking-wider text-[#718096] mb-2">
                    Linked Findings ({selectedItem.linkedFindings.length})
                  </p>
                  <div className="space-y-1.5">
                    {selectedItem.linkedFindings.map((f, i) => (
                      <div
                        key={i}
                        className="rounded-lg border border-[#D9E1F0] bg-white p-2.5 text-[11.5px]"
                      >
                        <div className="flex items-center justify-between mb-1">
                          <span className="font-semibold text-[#315FBA]">
                            {f.domain}
                          </span>
                          <span
                            className={`inline-flex items-center gap-1 rounded-full px-1.5 py-0.2 text-[9.5px] font-semibold ${
                              f.status === "verified"
                                ? "bg-teal-50 text-teal-700"
                                : "bg-amber-50 text-amber-700"
                            }`}
                          >
                            {f.status === "verified" && <CheckCircle2 className="size-2.5" />}
                            {f.status === "verified" ? "Verified Finding" : "Candidate Review"}
                          </span>
                        </div>
                        <p className="text-[#203653] leading-snug">{f.text}</p>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Illustrative Hash / Timestamp */}
                <div className="rounded-xl border border-dashed border-[#D9E1F0] p-2.5 font-mono text-[10px] text-[#718096] space-y-1">
                  <div className="flex items-center justify-between gap-1.5">
                    <span className="flex items-center gap-1.5 truncate">
                      <Hash className="size-3 text-[#315FBA] shrink-0" />
                      <span className="truncate">{selectedItem.hash}</span>
                    </span>
                    <span className="text-[9px] text-slate-400 shrink-0">Sample ref</span>
                  </div>
                  <div className="text-[9.5px] text-slate-400">
                    Timestamp: {selectedItem.timestamp}
                  </div>
                </div>

                <button
                  type="button"
                  className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-[#D9E1F0] py-2 text-[12px] font-semibold text-[#203653] hover:bg-white transition cursor-pointer"
                >
                  <span>Inspect Source Metadata</span>
                  <ExternalLink className="size-3 text-[#7997BE]" />
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
