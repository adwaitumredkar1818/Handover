"use client";

import React, { useState, useEffect } from "react";
import {
  ArrowDown,
  ArrowRight,
  Plug,
  Sparkles,
  ShieldCheck,
  Workflow,
  GitPullRequest,
  Layers,
  MessageSquare,
  FileText,
  Compass,
} from "lucide-react";
import { OrganicScene } from "../brand/OrganicScene";
import { useLiveApp } from "../../context/LiveAppContext";
import { useRouter } from "next/navigation";
import { useReveal } from "./hooks/useReveal";
import { useScrollProgress } from "./motion/useScrollProgress";
import { useReducedMotion } from "./motion/useReducedMotion";

const ORBIT_NODES = [
  {
    id: "repo",
    label: "Repository Node",
    meta: "payment-core · PR #4827",
    icon: GitPullRequest,
    color: "#315FBA",
    cluster: 0,
    posClass: "lg:top-[10%] lg:left-[12%]",
    filamentPath: "M 100 65 Q 185 110 240 180",
    animClass: "animate-float-1",
  },
  {
    id: "docs",
    label: "Documentation Node",
    meta: "ADR-007.pdf & Runbooks",
    icon: FileText,
    color: "#299B80",
    cluster: 2,
    posClass: "lg:top-[14%] lg:right-[6%]",
    filamentPath: "M 390 80 Q 325 125 265 185",
    animClass: "animate-float-2",
  },
  {
    id: "chat",
    label: "Conversation Node",
    meta: "#payments-arch Threads",
    icon: MessageSquare,
    color: "#8B78C9",
    cluster: 1,
    posClass: "lg:top-[46%] lg:left-[4%]",
    filamentPath: "M 80 205 Q 160 200 230 195",
    animClass: "animate-float-3",
  },
  {
    id: "task",
    label: "Task Node",
    meta: "PAY / PROJ-103",
    icon: Layers,
    color: "#D39B43",
    cluster: 2,
    posClass: "lg:bottom-[14%] lg:left-[14%]",
    filamentPath: "M 125 325 Q 195 265 240 215",
    animClass: "animate-float-4",
  },
  {
    id: "knowledge",
    label: "Project Knowledge Node",
    meta: "Verified Context & Decisions",
    icon: Sparkles,
    color: "#315FBA",
    cluster: 0,
    posClass: "lg:bottom-[12%] lg:right-[8%]",
    filamentPath: "M 375 320 Q 315 265 265 215",
    animClass: "animate-float-1",
  },
] as const;

export function HeroSection() {
  const { user } = useLiveApp();
  const router = useRouter();
  const containerRef = useReveal<HTMLElement>();
  const { scrollY } = useScrollProgress();
  const reducedMotion = useReducedMotion();
  const [mounted, setMounted] = useState(false);
  const [activeNodeId, setActiveNodeId] = useState<string | null>(null);

  useEffect(() => {
    setMounted(true);
  }, []);

  const handleGetStarted = () => {
    if (user) {
      router.push("/overview");
    } else {
      router.push("/signup");
    }
  };

  const scrollToHow = () => {
    const el = document.getElementById("how");
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };

  const activeNode = ORBIT_NODES.find((n) => n.id === activeNodeId) ?? null;

  // Scroll-linked subtle sphere scaling & downward drift toward next section
  const heroScale = reducedMotion ? 1 : Math.max(0.86, 1 - scrollY * 0.00028);
  const heroShiftY = reducedMotion ? 0 : Math.min(60, scrollY * 0.09);
  const heroCanvasOpacity = reducedMotion ? 1 : Math.max(0.35, 1 - scrollY * 0.0009);

  return (
    <section
      ref={containerRef}
      id="product"
      className="ambient-hero relative min-h-[690px] sm:min-h-[760px] lg:min-h-[840px] overflow-hidden pb-16 pt-8 sm:pt-12 lg:pb-20 flex flex-col justify-center"
    >
      {/* LAYER 1 — Canvas Ambient Gradients */}
      <div
        className="pointer-events-none absolute inset-0 z-0"
        style={{
          background:
            "radial-gradient(ellipse 75% 65% at 75% 48%, rgba(49,95,186,0.11), rgba(41,155,128,0.05) 45%, transparent 75%)",
        }}
      />

      {/* LAYER 2 & 3 — True Full-Bleed Organic Knowledge Universe (Desktop & Tablet) */}
      <div className="pointer-events-none absolute inset-0 z-0 overflow-hidden flex items-center justify-end">
        <div
          className="relative right-[-10%] sm:right-[-4%] lg:right-[0%] w-[580px] h-[580px] sm:w-[740px] sm:h-[740px] lg:w-[960px] lg:h-[960px] xl:w-[1080px] xl:h-[1080px] transition-transform duration-200 ease-out"
          style={{
            transform: `translateY(${heroShiftY}px) scale(${heroScale})`,
            opacity: heroCanvasOpacity,
          }}
        >
          <OrganicScene
            variant="hero"
            camZoom={1.1}
            highlightCluster={activeNode ? activeNode.cluster : null}
            showTags={false}
            className="h-full w-full"
            label="Organic 3D knowledge sphere seamlessly integrated into the atmospheric hero background"
          />
        </div>

        {/* Soft atmospheric gradient masks: blends scene edges invisibly into canvas without hard boxes */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background:
              "radial-gradient(ellipse 65% 55% at 75% 50%, transparent 35%, rgba(246,248,252,0.45) 65%, #F6F8FC 100%)",
          }}
        />
        <div className="absolute inset-y-0 left-0 w-full sm:w-[50%] lg:w-[42%] bg-gradient-to-r from-[#F6F8FC] via-[#F6F8FC]/90 to-transparent pointer-events-none" />
      </div>

      {/* LAYER 5 — Foreground Content Container */}
      <div className="relative z-10 mx-auto w-full max-w-[1240px] px-5 sm:px-8">
        <div className="grid grid-cols-1 lg:grid-cols-[1.1fr_0.9fr] items-center gap-10 lg:gap-8">
          {/* Left Editorial Column */}
          <div className="min-w-0 w-full max-w-[640px] lg:py-6">
            {/* Canonical Eyebrow & Narrative Line */}
            <div className="reveal flex flex-wrap items-center gap-2 max-w-full">
              <span className="inline-flex max-w-full items-center gap-2 rounded-2xl sm:rounded-full border border-[#D9E1F0] bg-white/95 px-3.5 py-1.5 sm:py-1 text-[10.5px] sm:text-[11px] font-semibold text-[#3e5373] shadow-xs backdrop-blur-xs">
                <span className="size-2 shrink-0 rounded-full bg-[#299B80] animate-pulse-soft" />
                <span className="tracking-wide uppercase font-mono leading-snug whitespace-normal break-words">
                  Intelligent Project Knowledge Reconstruction &amp; Handover Platform
                </span>
              </span>
            </div>

            <p className="reveal mt-4 font-mono text-[11.5px] sm:text-[12px] font-semibold uppercase tracking-[0.14em] text-[#315FBA]">
              People move on. Knowledge shouldn&apos;t.
            </p>

            {/* Editorial Headline */}
            <h1 className="reveal mt-3 text-[32px] min-[410px]:text-[38px] font-semibold leading-[1.06] tracking-[-0.036em] text-[#203653] sm:text-[54px] lg:text-[66px] break-words">
              <span className="block">Knowledge shouldn&apos;t</span>{" "}
              <span className="block bg-gradient-to-r from-[#203653] via-[#315FBA] to-[#299B80] bg-clip-text text-transparent">
                leave with people.
              </span>
            </h1>

            {/* Supporting Message */}
            <p className="reveal mt-6 text-[16.5px] leading-[1.65] text-[#56657c] sm:text-[18px]">
              When people move on, critical project knowledge shouldn&apos;t disappear with them.
              Handover reconstructs, organizes, and verifies the knowledge your next team needs.
            </p>

            {/* Primary & Secondary CTAs */}
            <div className="reveal mt-9 flex flex-wrap items-center gap-3.5">
              <button
                onClick={handleGetStarted}
                className="group inline-flex h-12 items-center gap-2 rounded-[10px] bg-[#203653] px-6 text-[15px] font-semibold text-white shadow-[0_1px_0_rgba(255,255,255,0.1)_inset,0_8px_20px_-8px_rgba(32,54,83,0.5)] transition-all duration-200 hover:bg-[#315FBA] active:scale-[0.98] cursor-pointer focus-visible:ring-2 focus-visible:ring-[#315FBA]"
              >
                <span suppressHydrationWarning>
                  {mounted && user ? "Go to Workspace" : "Get Started"}
                </span>
                <ArrowRight className="size-4 transition-transform duration-200 group-hover:translate-x-0.5" />
              </button>

              <button
                onClick={scrollToHow}
                className="group inline-flex h-12 items-center gap-2 rounded-[10px] border border-[#D9E1F0] bg-white/95 px-5 text-[15px] font-semibold text-[#203653] shadow-xs backdrop-blur-xs transition hover:bg-white hover:border-[#315FBA]/50 cursor-pointer focus-visible:ring-2 focus-visible:ring-[#315FBA]"
              >
                <span>Explore How It Works</span>
                <ArrowDown className="size-4 text-[#315FBA] transition-transform duration-200 group-hover:translate-y-0.5" />
              </button>
            </div>

            {/* Concise Trust Statement & Capability Strip */}
            <div className="reveal mt-10 flex flex-wrap items-center gap-x-5 gap-y-2.5 text-[12.5px] sm:text-[13px] text-[#718096]">
              <span className="flex items-center gap-1.5 transition-colors hover:text-[#203653]">
                <Plug className="size-3.5 text-[#315FBA]" />
                <span>Connect Your Tools</span>
              </span>
              <span className="flex items-center gap-1.5 transition-colors hover:text-[#203653]">
                <Sparkles className="size-3.5 text-[#8B78C9]" />
                <span>Reconstruct Knowledge</span>
              </span>
              <span className="flex items-center gap-1.5 transition-colors hover:text-[#203653]">
                <ShieldCheck className="size-3.5 text-[#299B80]" />
                <span>Human-Verified</span>
              </span>
              <span className="flex items-center gap-1.5 transition-colors hover:text-[#203653]">
                <Workflow className="size-3.5 text-[#203653]" />
                <span>Role-Tailored Handovers</span>
              </span>
            </div>
          </div>

          {/* LAYER 4 — Desktop Floating Interactive Orbit Nodes (Unboxed, Open Space Overlay) */}
          <div className="min-w-0 relative h-[420px] lg:h-[520px] w-full hidden lg:block pointer-events-auto">
            {/* Orbiting Connection Filaments SVG Overlay */}
            <svg
              viewBox="0 0 500 400"
              className="pointer-events-none absolute inset-0 h-full w-full"
              aria-hidden="true"
            >
              {ORBIT_NODES.map((node) => {
                const isHighlighted = activeNodeId === node.id;
                return (
                  <g key={node.id}>
                    <path
                      d={node.filamentPath}
                      fill="none"
                      stroke={isHighlighted ? node.color : "#7997BE"}
                      strokeOpacity={isHighlighted ? 0.85 : 0.26}
                      strokeWidth={isHighlighted ? 2.2 : 1.1}
                      strokeDasharray={isHighlighted ? "4 3" : "3 5"}
                      className={`transition-all duration-300 ${
                        isHighlighted && !reducedMotion ? "animate-stream-flow" : ""
                      }`}
                    />
                  </g>
                );
              })}
            </svg>

            {/* 5 Orbiting Interactive Source & Knowledge Nodes */}
            {ORBIT_NODES.map((node) => {
              const isHighlighted = activeNodeId === node.id;
              return (
                <button
                  key={node.id}
                  type="button"
                  onMouseEnter={() => setActiveNodeId(node.id)}
                  onMouseLeave={() => setActiveNodeId(null)}
                  onFocus={() => setActiveNodeId(node.id)}
                  onBlur={() => setActiveNodeId(null)}
                  className={`absolute ${node.posClass} ${
                    reducedMotion ? "" : node.animClass
                  } flex items-center gap-2.5 rounded-2xl border bg-white/95 px-3.5 py-2.5 text-left shadow-card backdrop-blur-md transition-all duration-300 cursor-pointer focus-visible:ring-2 focus-visible:ring-[#315FBA] ${
                    isHighlighted
                      ? "border-[#315FBA] shadow-pop scale-105 ring-2 ring-[#315FBA]/25 z-20"
                      : "border-[#D9E1F0] hover:border-[#315FBA]/50 z-10"
                  }`}
                >
                  <span
                    className="flex size-8 shrink-0 items-center justify-center rounded-xl"
                    style={{ background: `${node.color}16`, color: node.color }}
                  >
                    <node.icon className="size-4" />
                  </span>
                  <span className="min-w-0">
                    <span className="block text-[12px] font-semibold text-[#203653] leading-tight whitespace-nowrap">
                      {node.label}
                    </span>
                    <span className="block font-mono text-[10px] text-[#718096] whitespace-nowrap">
                      {node.meta}
                    </span>
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Mobile Compact Orbit Summary Strip */}
        <div className="reveal mt-8 flex flex-wrap items-center justify-center gap-2 lg:hidden">
          {ORBIT_NODES.map((node) => (
            <span
              key={node.id}
              className="inline-flex items-center gap-1.5 rounded-full border border-[#D9E1F0] bg-white/95 px-3 py-1 text-[11px] font-medium text-[#203653] shadow-xs"
            >
              <node.icon className="size-3" style={{ color: node.color }} />
              <span>{node.label.replace(" Node", "")}</span>
            </span>
          ))}
        </div>
      </div>

      {/* Subtle Scroll Indicator */}
      <div className="mt-8 flex justify-center relative z-10">
        <button
          onClick={scrollToHow}
          className="inline-flex items-center gap-2 rounded-full border border-[#D9E1F0]/80 bg-white/90 px-4 py-1.5 font-mono text-[10.5px] uppercase tracking-[0.14em] text-[#718096] shadow-xs backdrop-blur-xs transition hover:border-[#315FBA]/50 hover:text-[#203653] cursor-pointer"
          aria-label="Scroll to explore platform"
        >
          <Compass className="size-3 text-[#315FBA]" />
          <span>Scroll to explore</span>
          <ArrowDown className="size-3 animate-bounce" />
        </button>
      </div>
    </section>
  );
}

export default HeroSection;
