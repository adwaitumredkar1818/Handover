"use client";

import React from "react";
import { ArrowUp } from "lucide-react";
import { Logo } from "../brand";
import { useLiveApp } from "../../context/LiveAppContext";
import { useRouter } from "next/navigation";
import { useReveal } from "./hooks/useReveal";

const scrollToSection = (id: string) => {
  const el = document.getElementById(id);
  if (el) {
    el.scrollIntoView({ behavior: "smooth", block: "start" });
  }
};

export function LandingFooter() {
  const ref = useReveal<HTMLElement>();
  const { user } = useLiveApp();
  const router = useRouter();

  const handleAuth = (mode: "login" | "register") => {
    if (user) {
      router.push("/overview");
    } else {
      router.push(mode === "login" ? "/login" : "/signup");
    }
  };

  const columns: {
    title: string;
    links: { label: string; action: () => void }[];
  }[] = [
    {
      title: "Product",
      links: [
        { label: "Connected Sources", action: () => scrollToSection("sources") },
        { label: "Evidence Center", action: () => scrollToSection("evidence") },
        { label: "Knowledge Intelligence", action: () => scrollToSection("intelligence") },
        { label: "Relationship Explorer", action: () => scrollToSection("explorer") },
        { label: "Knowledge Assistant", action: () => scrollToSection("assistant") },
        { label: "Structured Handovers", action: () => scrollToSection("handovers") },
      ],
    },
    {
      title: "Solutions",
      links: [
        { label: "Departing Members", action: () => scrollToSection("roles") },
        { label: "Technical Reviewers", action: () => scrollToSection("roles") },
        { label: "Incoming Successors", action: () => scrollToSection("roles") },
      ],
    },
    {
      title: "Resources",
      links: [
        { label: "How It Works", action: () => scrollToSection("how") },
        { label: "Trust & Verification", action: () => scrollToSection("security") },
        { label: "Frequently Asked Questions", action: () => scrollToSection("faq") },
      ],
    },
    {
      title: "Platform",
      links: [
        { label: "Platform Overview", action: () => scrollToSection("product") },
        { label: "Sign In to Workspace", action: () => handleAuth("login") },
        { label: "Create Account", action: () => handleAuth("register") },
      ],
    },
  ];

  return (
    <footer ref={ref} className="border-t border-white/10 bg-[#112034] text-white">
      <div className="mx-auto w-full max-w-[1240px] px-5 sm:px-8">
        {/* Main Footer Columns */}
        <div className="reveal grid gap-12 py-16 grid-cols-2 md:grid-cols-[1.4fr_repeat(4,1fr)]">
          <div className="col-span-2 md:col-span-1">
            <button
              type="button"
              onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
              className="cursor-pointer focus-visible:ring-2 focus-visible:ring-[#315FBA] rounded-md"
              aria-label="Handover home"
            >
              <Logo size={28} light={true} />
            </button>
            <p className="mt-4 max-w-xs text-[14px] leading-relaxed text-[#c3cfe0]">
              People change. Projects evolve. Critical institutional knowledge should remain accessible, verifiable, and transferable.
            </p>
            <p className="mt-6 font-mono text-[11.5px] tracking-[0.18em] text-[#7997BE] uppercase">
              KNOWLEDGE CONTINUES.
            </p>
          </div>

          {columns.map((col) => (
            <div key={col.title}>
              <p className="text-[12.5px] font-semibold text-[#a9b8d0] uppercase tracking-[0.1em]">
                {col.title}
              </p>
              <ul className="mt-4 space-y-2.5">
                {col.links.map((link) => (
                  <li key={link.label}>
                    <button
                      type="button"
                      onClick={link.action}
                      className="text-[13.5px] text-[#c3cfe0] transition hover:text-white cursor-pointer text-left rounded focus-visible:ring-2 focus-visible:ring-[#315FBA]"
                    >
                      {link.label}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        {/* Bottom Subfooter */}
        <div className="flex flex-col gap-3 border-t border-white/10 py-6 text-[13px] text-[#a9b8d0] sm:flex-row sm:items-center sm:justify-between">
          <span>© {new Date().getFullYear()} Handover. All rights reserved.</span>
          <span className="font-mono text-[11px] sm:text-[11.5px] text-[#7997BE] max-w-xs sm:max-w-none text-center sm:text-left">
            Prevent Critical Knowledge From Leaving With People.
          </span>
          <div className="flex items-center gap-5 justify-center sm:justify-end sm:pr-14">
            <button
              type="button"
              onClick={() => handleAuth("login")}
              className="hover:text-white transition cursor-pointer"
            >
              Sign In
            </button>
            <button
              type="button"
              onClick={() => handleAuth("register")}
              className="hover:text-white transition cursor-pointer font-medium text-[#7997BE]"
            >
              Get Started
            </button>
            <button
              type="button"
              onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
              className="inline-flex items-center gap-1 rounded-full border border-white/15 bg-white/5 px-3 py-1 text-[11.5px] text-[#c3cfe0] hover:bg-white/15 hover:text-white transition cursor-pointer"
              aria-label="Scroll back to top"
            >
              <ArrowUp className="size-3" />
              <span>Top</span>
            </button>
          </div>
        </div>
      </div>
    </footer>
  );
}
