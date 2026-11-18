"use client";

import React, { useState } from "react";
import {
  Send,
  Inbox,
  ClipboardCheck,
  Plug,
  AlertTriangle,
  ShieldCheck,
  Check,
  Layers,
  UserRound,
  ListTodo,
  Link2,
} from "lucide-react";
import { OrganicScene } from "../brand/OrganicScene";
import { useReveal } from "./hooks/useReveal";

type RoleId = "departing" | "reviewer" | "successor";

const ROLE_BRIDGE_ITEMS: {
  id: RoleId;
  title: string;
  subtitle: string;
  responsibility: string;
  color: string;
}[] = [
  {
    id: "departing",
    title: "DEPARTING MEMBER",
    subtitle: "Contributes existing project knowledge",
    responsibility:
      "Confirms extracted decisions, annotates unwritten operational workarounds, and flags incomplete tasks before departure.",
    color: "#D39B43",
  },
  {
    id: "reviewer",
    title: "TECHNICAL REVIEWER",
    subtitle: "Checks findings, resolves uncertainty & validates",
    responsibility:
      "Audits candidate AI findings against original commits and documents, resolves conflicts, and signs off verified knowledge.",
    color: "#315FBA",
  },
  {
    id: "successor",
    title: "INCOMING SUCCESSOR",
    subtitle: "Receives structured project context",
    responsibility:
      "Onboards using role-tailored dossiers, dependency graphs, and evidence-grounded Q&A, and acknowledges handover receipt.",
    color: "#299B80",
  },
];

export function RolesSection() {
  const ref = useReveal<HTMLElement>();
  const [selectedRole, setSelectedRole] = useState<RoleId>("reviewer");

  const activeBridgeRole =
    ROLE_BRIDGE_ITEMS.find((r) => r.id === selectedRole) ?? ROLE_BRIDGE_ITEMS[1]!;

  return (
    <section
      ref={ref}
      id="roles"
      className="ambient-section scroll-mt-20 bg-white py-24 sm:py-32"
    >
      <div className="mx-auto w-full max-w-[1240px] px-5 sm:px-8">
        {/* Section Heading */}
        <div className="max-w-3xl">
          <div className="reveal">
            <p className="flex items-center gap-2 text-[12.5px] font-semibold uppercase tracking-[0.16em] text-[#315FBA]">
              <span className="h-px w-6 bg-current opacity-60" />
              Role Continuity
            </p>
          </div>
          <h2 className="reveal mt-5 text-[34px] font-semibold leading-[1.06] tracking-[-0.035em] text-[#203653] sm:text-[44px] lg:text-[50px]">
            A smoother transition for everyone involved.
          </h2>
          <p className="reveal mt-6 max-w-2xl text-[17px] leading-[1.65] text-[#56657c]">
            Every transition involves distinct responsibilities. Handover structures workflows across departing contributors, technical reviewers, and incoming successors—while requiring explicit human verification before knowledge is approved.
          </p>
        </div>

        {/* Interactive Organic Particle Continuity Bridge */}
        <div className="reveal mt-12 rounded-[24px] border border-[#D9E1F0] bg-[#F8FAFD] p-5 sm:p-6 shadow-xs">
          <div className="grid gap-6 lg:grid-cols-[1fr_auto_1fr] lg:items-center">
            {ROLE_BRIDGE_ITEMS.slice(0, 1).map((role) => (
              <button
                key={role.id}
                type="button"
                onClick={() => setSelectedRole(role.id)}
                className={`rounded-2xl border p-4 text-left transition-all cursor-pointer ${
                  selectedRole === role.id
                    ? "border-[#D39B43] bg-white shadow-card ring-2 ring-[#D39B43]/25"
                    : "border-[#D9E1F0] bg-white/80 hover:bg-white"
                }`}
              >
                <div className="flex items-center justify-between">
                  <p className="font-mono text-[10.5px] font-bold uppercase tracking-wider text-amber-700">
                    {role.title}
                  </p>
                  {selectedRole === role.id && (
                    <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[9.5px] font-semibold text-amber-800">
                      Active
                    </span>
                  )}
                </div>
                <p className="mt-1 text-[14px] font-semibold text-[#203653]">{role.subtitle}</p>
              </button>
            ))}

            {/* Central Organic Particle Bridge with Reviewer Gate */}
            <div className="flex flex-col items-center">
              <div className="relative h-[100px] w-full min-w-[220px] sm:w-[280px] rounded-xl bg-white border border-[#D9E1F0] overflow-hidden">
                <OrganicScene
                  variant="continuity"
                  showTags={false}
                  interactive={false}
                  className="h-full w-full"
                  label="Organic knowledge continuity bridge connecting outgoing and incoming roles"
                />
              </div>
              <button
                type="button"
                onClick={() => setSelectedRole("reviewer")}
                className={`-mt-4 relative z-10 rounded-full border px-4 py-1.5 text-[11px] font-mono font-bold uppercase tracking-wider transition cursor-pointer shadow-xs ${
                  selectedRole === "reviewer"
                    ? "border-[#315FBA] bg-[#315FBA] text-white ring-2 ring-[#315FBA]/25"
                    : "border-[#D9E1F0] bg-white text-[#203653] hover:border-[#315FBA]"
                }`}
              >
                TECHNICAL REVIEWER GATE
              </button>
            </div>

            {ROLE_BRIDGE_ITEMS.slice(2).map((role) => (
              <button
                key={role.id}
                type="button"
                onClick={() => setSelectedRole(role.id)}
                className={`rounded-2xl border p-4 text-left transition-all cursor-pointer ${
                  selectedRole === role.id
                    ? "border-[#299B80] bg-white shadow-card ring-2 ring-[#299B80]/25"
                    : "border-[#D9E1F0] bg-white/80 hover:bg-white"
                }`}
              >
                <div className="flex items-center justify-between">
                  <p className="font-mono text-[10.5px] font-bold uppercase tracking-wider text-teal-700">
                    {role.title}
                  </p>
                  {selectedRole === role.id && (
                    <span className="rounded-full bg-teal-100 px-2 py-0.5 text-[9.5px] font-semibold text-teal-800">
                      Active
                    </span>
                  )}
                </div>
                <p className="mt-1 text-[14px] font-semibold text-[#203653]">{role.subtitle}</p>
              </button>
            ))}
          </div>

          <div className="mt-5 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[#D9E1F0] bg-white px-4 py-3 text-[13px] text-[#56657c]">
            <div>
              <span className="font-semibold text-[#203653] mr-2">
                {activeBridgeRole.title}:
              </span>
              <span>{activeBridgeRole.responsibility}</span>
            </div>
            <span className="font-mono text-[10.5px] text-[#718096]">
              Role assignment never auto-approves findings
            </span>
          </div>
        </div>

        {/* Quick Role Selection Tabs */}
        <div className="reveal mt-8 flex flex-wrap items-center justify-center gap-2.5">
          {ROLE_BRIDGE_ITEMS.map((r) => {
            const isSelected = selectedRole === r.id;
            return (
              <button
                key={r.id}
                type="button"
                onClick={() => setSelectedRole(r.id)}
                className={`flex items-center gap-2 rounded-xl px-4 py-2 text-[12.5px] font-semibold transition cursor-pointer ${
                  isSelected
                    ? r.id === "departing"
                      ? "bg-amber-600 text-white shadow-sm"
                      : r.id === "reviewer"
                      ? "bg-[#315FBA] text-white shadow-sm"
                      : "bg-[#299B80] text-white shadow-sm"
                    : "bg-[#F6F8FC] text-[#56657c] border border-[#D9E1F0] hover:bg-white"
                }`}
              >
                {r.id === "departing" && <Send className="size-3.5" />}
                {r.id === "reviewer" && <ShieldCheck className="size-3.5" />}
                {r.id === "successor" && <Inbox className="size-3.5" />}
                <span>{r.title}</span>
              </button>
            );
          })}
        </div>

        {/* Dynamic In-Place Role Showcase */}
        <div className="reveal mt-8">
          {/* 1. Departing Member */}
          {selectedRole === "departing" && (
            <div className="animate-fade grid items-center gap-10 grid-cols-1 lg:grid-cols-[0.9fr_1.1fr] lg:gap-16 rounded-3xl border border-[#D9E1F0] bg-[#FBF5EA]/40 p-6 sm:p-8 shadow-xs">
              <div>
                <span className="inline-flex items-center gap-2 rounded-full bg-amber-50 px-3 py-1 text-[12.5px] font-semibold text-amber-700 ring-1 ring-inset ring-amber-600/20">
                  <Send className="size-3.5" />
                  Departing Member
                </span>
                <h3 className="mt-5 text-[28px] font-semibold leading-tight tracking-[-0.03em] text-[#203653] sm:text-[34px]">
                  Leave the knowledge, not just the role.
                </h3>
                <p className="mt-4 max-w-md text-[16px] leading-relaxed text-[#718096]">
                  Review reconstructed findings from your actual commits and threads, clarify edge cases, and add operational context without writing manual handoff docs from scratch.
                </p>
              </div>

              <div className="rounded-[20px] border border-[#D9E1F0] bg-[#F6F8FC] p-4 sm:p-5 shadow-xs">
                <div className="mb-3 flex items-center justify-between border-b border-[#D9E1F0]/80 pb-2">
                  <span className="font-mono text-[10.5px] uppercase tracking-wider text-[#718096]">
                    Contributor Queue Preview · 7 of 23
                  </span>
                  <span className="rounded-full border border-slate-200 bg-white px-2 py-0.5 font-mono text-[9.5px] font-medium text-slate-500">
                    Illustrative
                  </span>
                </div>
                <div className="tile relative rounded-2xl border border-[#D9E1F0] bg-white p-5 shadow-card">
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-[11px] font-semibold text-[#315FBA]">
                      PAY / SPRINT-34
                    </span>
                    <span className="font-mono text-[11px] text-[#718096]">HO-1038</span>
                  </div>
                  <p className="mt-3 text-[15px] font-semibold text-[#203653]">
                    Offline edits to merchant banking details can silently overwrite
                  </p>
                  <p className="mt-1.5 text-[13px] leading-relaxed text-[#718096]">
                    No concurrency conflict resolution strategy was defined for offline payout modifications.
                  </p>
                  <div className="mt-4 h-1.5 rounded-full bg-slate-100 overflow-hidden">
                    <div className="h-full w-[35%] rounded-full bg-[#299B80]" />
                  </div>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <span className="flex h-9 items-center gap-1.5 rounded-lg bg-[#299B80] px-3.5 text-[12.5px] font-semibold text-white shadow-xs">
                      <ShieldCheck className="size-3.5" />
                      Submit for Review
                    </span>
                    <span className="flex h-9 items-center rounded-lg border border-[#D9E1F0] px-3.5 text-[12.5px] font-semibold text-[#203653]">
                      Add context
                    </span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* 2. Technical Reviewer */}
          {selectedRole === "reviewer" && (
            <div className="animate-fade grid items-center gap-10 grid-cols-1 lg:grid-cols-[1.1fr_0.9fr] lg:gap-16 rounded-3xl border border-[#D9E1F0] bg-[#EEF2FA]/55 p-6 sm:p-8 shadow-xs">
              <div className="order-2 lg:order-1">
                <div className="rounded-[20px] border border-[#D9E1F0] bg-[#F6F8FC] p-4 sm:p-5 shadow-xs">
                  <div className="mb-3 flex items-center justify-between border-b border-[#D9E1F0]/80 pb-2">
                    <span className="font-mono text-[10.5px] uppercase tracking-wider text-[#718096]">
                      Technical Review Dashboard
                    </span>
                    <span className="rounded-full border border-slate-200 bg-white px-2 py-0.5 font-mono text-[9.5px] font-medium text-slate-500">
                      Illustrative
                    </span>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-[1.2fr_1fr]">
                    <div className="tile rounded-2xl border border-[#D9E1F0] bg-white p-4 shadow-card">
                      <p className="text-[12px] font-semibold text-[#203653]">
                        Attention Required
                      </p>
                      <ul className="mt-3 space-y-2.5">
                        {[
                          {
                            icon: ClipboardCheck,
                            color: "text-amber-600 bg-amber-50",
                            text: "HO-1042 awaiting reviewer verification",
                          },
                          {
                            icon: Plug,
                            color: "text-red-600 bg-red-50",
                            text: "Slack OAuth scope re-authorization needed",
                          },
                          {
                            icon: AlertTriangle,
                            color: "text-red-600 bg-red-50",
                            text: "Critical timeout risk unresolved",
                          },
                        ].map((item) => (
                          <li key={item.text} className="flex items-center gap-2.5">
                            <span
                              className={`flex size-6 shrink-0 items-center justify-center rounded-md ${item.color}`}
                            >
                              <item.icon className="size-3" />
                            </span>
                            <span className="text-[12px] text-[#203653] leading-snug">
                              {item.text}
                            </span>
                          </li>
                        ))}
                      </ul>
                    </div>

                    <div className="tile rounded-2xl border border-[#D9E1F0] bg-white p-4 shadow-card">
                      <p className="text-[12px] font-semibold text-[#203653]">
                        Sample Readiness
                      </p>
                      <ul className="mt-3 space-y-3">
                        {[
                          { name: "Payment Platform", val: 86, color: "#299B80" },
                          { name: "Gateway API", val: 64, color: "#D39B43" },
                          { name: "Settlement Batch", val: 92, color: "#299B80" },
                        ].map((p) => (
                          <li key={p.name}>
                            <div className="flex justify-between text-[11.5px]">
                              <span className="font-medium text-[#203653]">{p.name}</span>
                              <span className="font-mono text-[#718096]">{p.val}%</span>
                            </div>
                            <div className="mt-1 h-1 rounded-full bg-slate-100 overflow-hidden">
                              <div
                                className="h-full rounded-full"
                                style={{ width: `${p.val}%`, background: p.color }}
                              />
                            </div>
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </div>
              </div>

              <div className="order-1 lg:order-2">
                <span className="inline-flex items-center gap-2 rounded-full bg-blue-50 px-3 py-1 text-[12.5px] font-semibold text-[#315FBA] ring-1 ring-inset ring-blue-600/20">
                  <ShieldCheck className="size-3.5" />
                  Technical Reviewer
                </span>
                <h3 className="mt-5 text-[28px] font-semibold leading-tight tracking-[-0.03em] text-[#203653] sm:text-[34px]">
                  Verify what matters before it transfers.
                </h3>
                <p className="mt-4 max-w-md text-[16px] leading-relaxed text-[#718096]">
                  Inspect candidate findings against original evidence, evaluate conflict flags, and explicitly sign off verified knowledge prior to transition approval.
                </p>
              </div>
            </div>
          )}

          {/* 3. Incoming Successor */}
          {selectedRole === "successor" && (
            <div className="animate-fade grid items-center gap-10 grid-cols-1 lg:grid-cols-[0.9fr_1.1fr] lg:gap-16 rounded-3xl border border-[#D9E1F0] bg-[#EEF6F3]/60 p-6 sm:p-8 shadow-xs">
              <div>
                <span className="inline-flex items-center gap-2 rounded-full bg-teal-50 px-3 py-1 text-[12.5px] font-semibold text-teal-700 ring-1 ring-inset ring-teal-600/20">
                  <Inbox className="size-3.5" />
                  Incoming Successor
                </span>
                <h3 className="mt-5 text-[28px] font-semibold leading-tight tracking-[-0.03em] text-[#203653] sm:text-[34px]">
                  Step into the project with complete context.
                </h3>
                <p className="mt-4 max-w-md text-[16px] leading-relaxed text-[#718096]">
                  Explore verified project decisions, understand architectural assumptions, acknowledge receipt cleanly, and query the assistant with source attribution from day one.
                </p>
              </div>

              <div className="rounded-[20px] border border-[#D9E1F0] bg-[#F6F8FC] p-4 sm:p-5 shadow-xs">
                <div className="mb-3 flex items-center justify-between border-b border-[#D9E1F0]/80 pb-2">
                  <span className="font-mono text-[10.5px] uppercase tracking-wider text-[#718096]">
                    Successor Onboarding Demo
                  </span>
                  <span className="rounded-full border border-slate-200 bg-white px-2 py-0.5 font-mono text-[9.5px] font-medium text-slate-500">
                    Illustrative
                  </span>
                </div>
                <div className="grid gap-3 sm:grid-cols-[200px_1fr]">
                  <ol className="rounded-2xl border border-[#D9E1F0] bg-white p-3 shadow-xs">
                    {[
                      { icon: UserRound, label: "System Overview", done: true },
                      { icon: Layers, label: "Architecture", done: true },
                      { icon: UserRound, label: "Responsibilities", done: false },
                      { icon: ListTodo, label: "Pending Tasks", done: false },
                    ].map((item, i) => (
                      <li
                        key={item.label}
                        className={`flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[12px] ${
                          i === 2 ? "bg-[#F6F8FC] font-semibold text-[#203653]" : ""
                        }`}
                      >
                        <span
                          className={`flex size-6 items-center justify-center rounded-md ${
                            item.done
                              ? "bg-teal-50 text-[#299B80]"
                              : i === 2
                              ? "bg-[#315FBA] text-white"
                              : "bg-slate-100 text-slate-400"
                          }`}
                        >
                          {item.done ? <Check className="size-3" /> : <item.icon className="size-3" />}
                        </span>
                        <span className="text-[#203653]">{item.label}</span>
                      </li>
                    ))}
                  </ol>

                  <div className="tile rounded-2xl border border-[#D9E1F0] bg-white p-4 shadow-card">
                    <p className="ml-auto w-fit rounded-2xl rounded-br-xs bg-[#315FBA] px-3.5 py-2 text-[12.5px] text-white">
                      Why was Kafka chosen over RabbitMQ for settlement?
                    </p>
                    <div className="mt-3 rounded-2xl rounded-tl-xs border border-[#D9E1F0] bg-[#F8FAFD] p-3 text-[12.5px] leading-relaxed text-[#3e5373]">
                      Decoupled transaction lock path, persistent audit event log, and native horizontal scaling for batch acquirer reconciliations.
                      <p className="mt-2 flex items-center gap-1.5 font-mono text-[11px] text-[#315FBA]">
                        <Link2 className="size-3" />
                        [1] ADR-007 Event-driven settlement.pdf
                      </p>
                    </div>
                    <span className="mt-2.5 inline-flex items-center gap-1 rounded-full bg-teal-50 px-2.5 py-0.5 text-[11px] font-medium text-teal-700 ring-1 ring-inset ring-teal-600/20">
                      <ShieldCheck className="size-3" />
                      Grounded in verified project findings
                    </span>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
