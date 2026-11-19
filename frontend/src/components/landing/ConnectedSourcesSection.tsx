"use client";

import React, { useState } from "react";
import { Lock, ShieldCheck, CheckCircle2, Ban, Database } from "lucide-react";
import { LogoMark, SourceIcon } from "../brand";
import { OrganicScene } from "../brand/OrganicScene";
import { useReveal } from "./hooks/useReveal";
import { useReducedMotion } from "./motion/useReducedMotion";

interface SourceCategoryNode {
  id: string;
  title: string;
  category: string;
  status: "connected" | "unavailable";
  authMode: string;
  items: string;
  detail: string;
  iconType?: "github" | "jira" | "slack" | "docs";
  cluster: number;
  accent: string;
  posClass: string;
  linePath: string;
}

const SOURCE_NODES: SourceCategoryNode[] = [
  {
    id: "github",
    title: "Code Repositories",
    category: "GitHub",
    status: "connected",
    authMode: "Fine-Grained Read-Only PAT",
    items: "payment-core, settlement-worker, gateway-api",
    detail: "Reads merged pull requests, commit diffs, and review threads using delegated read-only scopes.",
    iconType: "github",
    cluster: 0,
    accent: "#315FBA",
    posClass: "lg:top-6 lg:left-4",
    linePath: "M 220 95 Q 340 120 420 205",
  },
  {
    id: "jira",
    title: "Work Tracking",
    category: "Jira",
    status: "connected",
    authMode: "OAuth 2.0 3LO Read-Only",
    items: "PAY · PROJ-103, DEP-014, SPRINT-34",
    detail: "Syncs sprint tickets, blockers, acceptance history, and assignee transitions scoped by user ACLs.",
    iconType: "jira",
    cluster: 2,
    accent: "#2684FF",
    posClass: "lg:top-6 lg:right-4",
    linePath: "M 680 95 Q 560 120 480 205",
  },
  {
    id: "slack",
    title: "Conversations",
    category: "Slack",
    status: "connected",
    authMode: "OAuth v2 Read-Only Channel Scope",
    items: "#payments-arch, #incidents",
    detail: "Captures resolved technical threads and architectural debates in explicitly authorized channels.",
    iconType: "slack",
    cluster: 1,
    accent: "#8B78C9",
    posClass: "lg:top-1/2 lg:-translate-y-1/2 lg:left-0",
    linePath: "M 210 230 Q 320 230 410 230",
  },
  {
    id: "docs",
    title: "Uploaded Documents",
    category: "PDF & DOCX",
    status: "connected",
    authMode: "AES-256-GCM Encrypted Storage",
    items: "ADR-007.pdf, ADR-012.pdf, settlement-runbook.pdf",
    detail: "Parses digital documents via PyMuPDF/python-docx and scanned architecture diagrams via GLM OCR.",
    iconType: "docs",
    cluster: 0,
    accent: "#299B80",
    posClass: "lg:top-1/2 lg:-translate-y-1/2 lg:right-0",
    linePath: "M 690 230 Q 580 230 490 230",
  },
  {
    id: "postgres",
    title: "Project & Transition Records",
    category: "Canonical Workspace",
    status: "connected",
    authMode: "PostgreSQL RBAC + Audit Trail",
    items: "HO-1042, Transition Roles, Ownership Map",
    detail: "Links organizational membership, outgoing/incoming participants, and human verification decisions.",
    cluster: 1,
    accent: "#203653",
    posClass: "lg:bottom-6 lg:left-4",
    linePath: "M 220 365 Q 340 340 420 255",
  },
  {
    id: "restricted",
    title: "Restricted Private Repository",
    category: "Unconnected / Gated",
    status: "unavailable",
    authMode: "Access Withheld — Missing Source ACL",
    items: "infra-secrets-vault (excluded at read time)",
    detail: "Unavailable sources or repos without individual authorization never enter vector retrieval or AI prompts.",
    cluster: 2,
    accent: "#D36D72",
    posClass: "lg:bottom-6 lg:right-4",
    linePath: "M 680 365 Q 560 340 480 255",
  },
];

export function ConnectedSourcesSection() {
  const ref = useReveal<HTMLElement>();
  const reducedMotion = useReducedMotion();
  const [selectedId, setSelectedId] = useState<string>("github");

  const activeNode = SOURCE_NODES.find((n) => n.id === selectedId) ?? SOURCE_NODES[0]!;

  return (
    <section
      ref={ref}
      id="sources"
      className="scroll-mt-20 bg-[#F8FAFD] py-24 sm:py-32 border-y border-[#D9E1F0]/70 overflow-x-clip"
    >
      <div className="mx-auto w-full max-w-[1240px] px-5 sm:px-8">
        {/* Section Heading */}
        <div className="mx-auto max-w-3xl text-center">
          <div className="reveal flex justify-center">
            <p className="flex items-center gap-2 text-[12.5px] font-semibold uppercase tracking-[0.16em] text-[#315FBA]">
              <span className="h-px w-6 bg-current opacity-60" />
              Connected Sources
            </p>
          </div>
          <h2 className="reveal mt-5 text-[34px] font-semibold leading-[1.06] tracking-[-0.035em] text-[#203653] sm:text-[44px] lg:text-[50px]">
            Your project knowledge starts with the evidence.
          </h2>
          <p className="reveal mx-auto mt-6 max-w-2xl text-[17px] leading-[1.65] text-[#56657c]">
            Handover connects strictly to supported engineering tools and encrypted document uploads. Connected sources stream verifiable evidence toward the core, while unauthorized or unconnected sources remain isolated and inaccessible.
          </p>
        </div>

        {/* Desktop Radial Core & Source Constellation */}
        <div className="reveal relative mt-16 hidden lg:block min-h-[470px] rounded-[28px] border border-[#D9E1F0] bg-white p-6 shadow-pop">
          {/* SVG Connection Lines Extending Toward Core */}
          <svg
            viewBox="0 0 900 460"
            className="pointer-events-none absolute inset-0 h-full w-full"
            aria-hidden="true"
          >
            {SOURCE_NODES.map((node) => {
              const isSelected = selectedId === node.id;
              const isUnavailable = node.status === "unavailable";
              return (
                <g key={node.id}>
                  <path
                    d={node.linePath}
                    fill="none"
                    stroke={isUnavailable ? "#D36D72" : isSelected ? node.accent : "#DCE3EF"}
                    strokeWidth={isSelected ? 2.2 : 1.4}
                    strokeDasharray={isUnavailable ? "4 6" : isSelected ? "5 4" : undefined}
                    strokeOpacity={isUnavailable ? 0.45 : isSelected ? 0.9 : 0.75}
                    className={
                      !isUnavailable && isSelected && !reducedMotion
                        ? "animate-stream-flow"
                        : ""
                    }
                  />
                  {!isUnavailable && !reducedMotion && (
                    <circle
                      r={isSelected ? 3.5 : 2.2}
                      fill={isSelected ? node.accent : "#315FBA"}
                      opacity={isSelected ? 1 : 0.6}
                    >
                      <animateMotion
                        path={node.linePath}
                        dur={isSelected ? "2s" : "3.6s"}
                        repeatCount="indefinite"
                      />
                    </circle>
                  )}
                </g>
              );
            })}
          </svg>

          {/* Central Handover Core */}
          <div className="pointer-events-none absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 z-10 flex flex-col items-center">
            <div className="relative size-48 rounded-full border border-[#D9E1F0] bg-[#F6F8FC]/85 shadow-lift flex items-center justify-center overflow-hidden">
              <OrganicScene
                variant="reconstruct"
                progress={activeNode.status === "connected" ? 0.9 : 0.45}
                highlightCluster={activeNode.cluster}
                showTags={false}
                interactive={false}
                className="h-full w-full"
                label="Handover knowledge ingestion core"
              />
              <div className="absolute flex size-12 items-center justify-center rounded-2xl border border-[#D9E1F0] bg-white shadow-card">
                <LogoMark size={24} />
              </div>
            </div>
            <span className="mt-2 rounded-full border border-[#D9E1F0] bg-white px-3 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider text-[#203653] shadow-xs">
              ACL-Enforced Ingestion Core
            </span>
          </div>

          {/* 6 Source Cards Positioned Around Core */}
          {SOURCE_NODES.map((node) => {
            const isSelected = selectedId === node.id;
            const isUnavailable = node.status === "unavailable";
            return (
              <button
                key={node.id}
                type="button"
                onClick={() => setSelectedId(node.id)}
                onMouseEnter={() => setSelectedId(node.id)}
                className={`absolute ${node.posClass} z-20 w-[295px] xl:w-[315px] rounded-2xl border p-4 text-left transition-all duration-300 cursor-pointer focus-visible:ring-2 focus-visible:ring-[#315FBA] ${
                  isUnavailable
                    ? isSelected
                      ? "border-red-300 bg-red-50/70 shadow-card ring-2 ring-red-200"
                      : "border-dashed border-red-200 bg-slate-50/90 opacity-85 hover:opacity-100"
                    : isSelected
                    ? "border-[#315FBA] bg-white shadow-pop ring-2 ring-[#315FBA]/20 scale-[1.02]"
                    : "border-[#D9E1F0] bg-white/95 shadow-card hover:border-[#315FBA]/50"
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2.5 min-w-0">
                    {node.iconType ? (
                      <SourceIcon type={node.iconType} size={30} />
                    ) : (
                      <span
                        className={`flex size-[30px] shrink-0 items-center justify-center rounded-[10px] border ${
                          isUnavailable
                            ? "border-red-200 bg-red-50 text-red-600"
                            : "border-[#D9E1F0] bg-[#EDF2FA] text-[#203653]"
                        }`}
                      >
                        {isUnavailable ? <Ban className="size-4" /> : <Database className="size-4" />}
                      </span>
                    )}
                    <div className="min-w-0">
                      <p className="text-[13px] font-semibold text-[#203653] leading-snug">
                        {node.title}
                      </p>
                      <p className="font-mono text-[10px] text-[#718096]">{node.category}</p>
                    </div>
                  </div>
                  <span
                    className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 font-mono text-[9.5px] font-semibold shrink-0 ${
                      isUnavailable
                        ? "bg-red-100 text-red-700"
                        : "bg-teal-50 text-[#299B80] ring-1 ring-inset ring-teal-600/20"
                    }`}
                  >
                    {isUnavailable ? "Blocked" : "Connected"}
                  </span>
                </div>
                <p className="mt-2.5 font-mono text-[11px] text-[#3e5373] line-clamp-1">
                  {node.items}
                </p>
              </button>
            );
          })}
        </div>

        {/* Tablet & Mobile Sequential Source Cards Grid */}
        <div className="reveal mt-12 grid gap-3 sm:grid-cols-2 lg:hidden">
          {SOURCE_NODES.map((node) => {
            const isSelected = selectedId === node.id;
            const isUnavailable = node.status === "unavailable";
            return (
              <button
                key={node.id}
                type="button"
                onClick={() => setSelectedId(node.id)}
                className={`rounded-2xl border p-4 text-left transition-all cursor-pointer ${
                  isUnavailable
                    ? "border-dashed border-red-200 bg-red-50/40"
                    : isSelected
                    ? "border-[#315FBA] bg-white shadow-card ring-2 ring-[#315FBA]/20"
                    : "border-[#D9E1F0] bg-white"
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2.5 min-w-0">
                    {node.iconType ? (
                      <SourceIcon type={node.iconType} size={28} />
                    ) : (
                      <span className="flex size-7 shrink-0 items-center justify-center rounded-lg border border-[#D9E1F0] bg-[#EDF2FA] text-[#203653]">
                        {isUnavailable ? <Ban className="size-3.5 text-red-600" /> : <Database className="size-3.5" />}
                      </span>
                    )}
                    <span className="text-[13.5px] font-semibold text-[#203653] truncate">
                      {node.title}
                    </span>
                  </div>
                  <span
                    className={`rounded-full px-2 py-0.5 font-mono text-[9.5px] font-semibold ${
                      isUnavailable
                        ? "bg-red-100 text-red-700"
                        : "bg-teal-50 text-[#299B80]"
                    }`}
                  >
                    {isUnavailable ? "Unavailable" : "Connected"}
                  </span>
                </div>
                <p className="mt-2 text-[12px] text-[#56657c]">{node.detail}</p>
              </button>
            );
          })}
        </div>

        {/* Active Source Detail & Permission-Aware Access Explanation */}
        <div className="reveal mt-6 grid gap-4 md:grid-cols-[1.15fr_0.85fr]">
          <div className="rounded-2xl border border-[#D9E1F0] bg-white p-5 shadow-xs">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                {activeNode.status === "connected" ? (
                  <CheckCircle2 className="size-4 text-[#299B80]" />
                ) : (
                  <Ban className="size-4 text-red-600" />
                )}
                <span className="text-[14.5px] font-semibold text-[#203653]">
                  {activeNode.title} ({activeNode.category})
                </span>
              </div>
              <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-0.5 font-mono text-[10px] text-[#56657c]">
                {activeNode.authMode}
              </span>
            </div>
            <p className="mt-2.5 text-[13.5px] leading-relaxed text-[#56657c]">
              {activeNode.detail}
            </p>
            <p className="mt-2 font-mono text-[11px] text-[#315FBA]">
              Illustrative sample scope: {activeNode.items}
            </p>
          </div>

          <div className="rounded-2xl border border-[#315FBA]/25 bg-[#203653] p-5 text-white shadow-xs">
            <div className="flex items-center gap-2 text-[13px] font-semibold text-[#A5A0D9]">
              <Lock className="size-4 text-[#299B80]" />
              <span>Permission-Aware Source Access</span>
            </div>
            <p className="mt-2 text-[13px] leading-relaxed text-[#c3cfe0]">
              Project membership never bypasses individual tool permissions. Delegated source ACLs are evaluated at read time before any record enters retrieval or AI reconstruction—failing closed if access cannot be verified.
            </p>
            <div className="mt-3 flex items-center gap-1.5 font-mono text-[10.5px] text-[#299B80]">
              <ShieldCheck className="size-3.5" />
              <span>Zero fabricated or unauthorized data</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
