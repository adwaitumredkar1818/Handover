"use client";

import React, { useState } from "react";
import { useReveal } from "./hooks/useReveal";

const FAQ_ITEMS = [
  {
    q: "What does The Handover do?",
    a: "The Handover connects authorized organizational tools (GitHub, Jira, Slack, and uploaded project documents), reconstructs fragmented project context into structured records across eight canonical domains, surfaces contradictions and missing information, supports human verification, and produces certified, role-tailored handover dossiers for incoming team members.",
  },
  {
    q: "Which tools can The Handover connect to?",
    a: "The Handover supports fine-grained read-only integrations with GitHub repositories, Jira projects, Slack channels, and direct uploads of PDF and DOCX documentation (such as Architecture Decision Records and operational runbooks). Source connections use delegated per-user authorizations with strict read-time permission checks.",
  },
  {
    q: "Does The Handover replace our existing project management tools?",
    a: "No. The Handover is not an issue tracker, sprint board, or documentation editor. It reads from the tools your engineering and product teams already use and focuses exclusively on preserving architectural memory, operational context, and transition governance. Daily work continues in GitHub and Jira.",
  },
  {
    q: "How does The Handover use AI?",
    a: "AI models extract candidate findings from authorized evidence chunks, detect contradictions across sources, score extraction confidence, and synthesize draft summaries. The LLM is strictly not a source of truth—it cannot independently approve handovers, override source permissions, or invent project facts without grounding.",
  },
  {
    q: "Can team members verify AI-generated findings?",
    a: "Yes. Human verification is a mandatory platform gate. Outgoing members and technical reviewers inspect candidate findings, review supporting citations, edit descriptions, flag conflicts, or reject invalid candidates. Only human-verified items contribute to official handover completeness scores.",
  },
  {
    q: "How does The Handover handle permissions and access control?",
    a: "Project membership does not grant automatic access to private repositories or restricted issues. External source ACLs are strictly evaluated at read time before any evidence or finding enters retrieval context or assistant prompts. The system fails closed if permissions cannot be established.",
  },
  {
    q: "Can users participate in multiple transitions with different roles?",
    a: "Yes. Roles and transition participation are assigned per project. A team member can be a departing contributor on one project, an approving technical reviewer on another, and an incoming successor on a third, with tailored workspace views for each responsibility.",
  },
  {
    q: "What does an approved handover package contain?",
    a: "A certified handover dossier contains an executive system overview, verified findings across all eight knowledge domains (decisions, technical architecture, work status, ownership, dependencies, risks, procedures, and discussions), role-tailored views, and cryptographic provenance links back to original source evidence.",
  },
];

export function FaqSection() {
  const ref = useReveal<HTMLElement>();
  const [openIndex, setOpenIndex] = useState<number | null>(0);

  const toggle = (i: number) => {
    setOpenIndex(openIndex === i ? null : i);
  };

  return (
    <section ref={ref} id="faq" className="scroll-mt-20 py-24 sm:py-32">
      <div className="mx-auto w-full max-w-[1240px] px-5 sm:px-8">
        <div className="grid gap-12 grid-cols-1 lg:grid-cols-[0.8fr_1.2fr] lg:gap-20">
          {/* Header Column */}
          <div>
            <div className="reveal">
              <p className="flex items-center gap-2 text-[12.5px] font-semibold uppercase tracking-[0.16em] text-[#315FBA]">
                <span className="h-px w-6 bg-current opacity-60" />
                Frequently Asked Questions
              </p>
            </div>
            <h2 className="reveal mt-5 text-[32px] font-semibold leading-[1.06] tracking-[-0.035em] text-[#203653] sm:text-[40px] lg:text-[44px]">
              Common questions about The Handover.
            </h2>
            <p className="reveal mt-4 text-[15px] leading-relaxed text-[#718096]">
              Everything you need to know about knowledge continuity, source integrations, and verification governance.
            </p>
          </div>

          {/* Accordion Column */}
          <ul className="reveal divide-y divide-[#D9E1F0] border-y border-[#D9E1F0]">
            {FAQ_ITEMS.map((item, i) => (
              <li key={item.q}>
                <button
                  type="button"
                  onClick={() => toggle(i)}
                  aria-expanded={openIndex === i}
                  className="flex w-full items-center justify-between gap-6 py-5 text-left cursor-pointer rounded-lg px-2 -mx-2 focus-visible:ring-2 focus-visible:ring-[#315FBA]"
                >
                  <span className="text-[16.5px] font-semibold tracking-[-0.01em] text-[#203653]">
                    {item.q}
                  </span>
                  <span
                    className={`flex size-8 shrink-0 items-center justify-center rounded-full border border-[#D9E1F0] transition-all duration-300 ${
                      openIndex === i
                        ? "rotate-45 border-[#203653] bg-[#203653] text-white"
                        : "text-[#718096] hover:border-[#315FBA] hover:text-[#315FBA]"
                    }`}
                  >
                    <span className="text-lg leading-none font-light">+</span>
                  </span>
                </button>
                <div
                  className={`grid transition-all duration-300 ease-out ${
                    openIndex === i
                      ? "grid-rows-[1fr] opacity-100"
                      : "grid-rows-[0fr] opacity-0"
                  }`}
                >
                  <div className="overflow-hidden">
                    <p className="max-w-2xl pb-6 text-[14.5px] leading-relaxed text-[#56657c]">
                      {item.a}
                    </p>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
