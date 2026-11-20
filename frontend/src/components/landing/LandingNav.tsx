"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  ChevronDown,
  Menu,
  X,
  ArrowRight,
  Network,
  Sparkles,
  Workflow,
  ShieldCheck,
  Send,
  Inbox,
  FileSearch,
  Bot,
  Plug,
} from "lucide-react";
import { Logo } from "../brand";
import { useLiveApp } from "../../context/LiveAppContext";
import { useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import { useScrollProgress } from "./motion/useScrollProgress";

const PRODUCT_MENU = [
  {
    icon: Sparkles,
    title: "Knowledge Intelligence",
    body: "Reconstructs 8 domains of project knowledge with citations",
    id: "intelligence",
  },
  {
    icon: Plug,
    title: "Connected Sources",
    body: "Fine-grained, ACL-enforced connections to repos, tickets, threads & docs",
    id: "sources",
  },
  {
    icon: FileSearch,
    title: "Evidence Center",
    body: "Three-panel workspace tracing findings to raw evidence",
    id: "evidence",
  },
  {
    icon: Network,
    title: "Knowledge Explorer",
    body: "Interactive graph linking decisions, tasks, people & components",
    id: "explorer",
  },
  {
    icon: Bot,
    title: "Knowledge Assistant",
    body: "Grounded Q&A with strict citations and uncertainty disclosure",
    id: "assistant",
  },
  {
    icon: Workflow,
    title: "Structured Handovers",
    body: "Verified, publishable transition dossiers for incoming members",
    id: "handovers",
  },
  {
    icon: ShieldCheck,
    title: "Trust & Governance",
    body: "Four-tier epistemic separation and human verification gates",
    id: "security",
  },
];

const SOLUTIONS_MENU = [
  {
    icon: Send,
    title: "Departing Members",
    body: "Review reconstructed findings and leave critical context effortlessly",
    id: "roles",
  },
  {
    icon: ShieldCheck,
    title: "Technical Reviewers",
    body: "Verify candidate findings against original evidence and approve packages",
    id: "roles",
  },
  {
    icon: Inbox,
    title: "Incoming Successors",
    body: "Step into the project with complete, verified architectural context",
    id: "roles",
  },
];

const scrollToSection = (id: string) => {
  const el = document.getElementById(id);
  if (el) {
    el.scrollIntoView({ behavior: "smooth", block: "start" });
  }
};

export function LandingNav() {
  const { user, login, addToast } = useLiveApp();
  const router = useRouter();
  const pathname = usePathname();
  const { isScrolled } = useScrollProgress();
  const [mounted, setMounted] = useState(false);
  const [demoLoading, setDemoLoading] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [productOpen, setProductOpen] = useState(false);
  const [solutionsOpen, setSolutionsOpen] = useState(false);

  const navigateToSection = (id: string) => {
    if (pathname === "/") {
      const el = document.getElementById(id);
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "start" });
        return;
      }
    }
    router.push(`/#${id}`);
  };

  useEffect(() => {
    setMounted(true);
  }, []);

  // Handle escape key to close open menus
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setProductOpen(false);
        setSolutionsOpen(false);
        setMobileMenuOpen(false);
      }
    },
    []
  );

  useEffect(() => {
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  // Lock body scroll when mobile menu is active
  useEffect(() => {
    if (mobileMenuOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [mobileMenuOpen]);

  const handleAuthAction = (mode: "login" | "register") => {
    if (user) {
      router.push("/overview");
    } else {
      router.push(mode === "login" ? "/login" : "/signup");
    }
  };

  const handleDemoLogin = async () => {
    if (demoLoading) return;
    setDemoLoading(true);
    try {
      await login("vernit.gerg25@pccoepune.org", "Handover!Vernit2026");
      router.push("/overview");
    } catch (err) {
      addToast?.({
        type: "error",
        title: "Demo login failed",
        message: err instanceof Error ? err.message : "Could not sign in to demo account.",
      });
    } finally {
      setDemoLoading(false);
    }
  };

  return (
    <header
      className={`sticky top-0 z-40 transition-all duration-300 ${
        isScrolled
          ? "border-b border-[#D9E1F0]/80 bg-white/90 backdrop-blur-xl shadow-xs"
          : "border-b border-transparent bg-transparent"
      }`}
    >
      <div className="mx-auto flex h-[76px] w-full max-w-[1240px] items-center px-5 sm:px-8">
        {/* Brand Logo & Demo Quick-Login */}
        <div className="flex items-center gap-3">
          <button
            onClick={() => {
              if (pathname === "/") {
                window.scrollTo({ top: 0, behavior: "smooth" });
              } else {
                router.push("/");
              }
            }}
            className="flex items-center gap-2 cursor-pointer focus:outline-none"
            aria-label="The Handover home"
          >
            <Logo size={28} />
          </button>
          <button
            type="button"
            onClick={handleDemoLogin}
            disabled={demoLoading}
            className="inline-flex h-10 items-center justify-center rounded-lg border border-[#D9E1F0] bg-white/80 px-4 text-[14.5px] font-semibold text-[#203653] transition hover:bg-white cursor-pointer disabled:opacity-60"
          >
            {demoLoading ? "Signing in..." : "Demo"}
          </button>
        </div>

        {/* Desktop Primary Navigation */}
        <nav
          className="mx-auto hidden items-center gap-1 lg:flex"
          aria-label="Primary navigation"
        >
          {/* Product Dropdown */}
          <div
            className="relative"
            onMouseEnter={() => setProductOpen(true)}
            onMouseLeave={() => setProductOpen(false)}
          >
            <button
              onClick={() => setProductOpen(!productOpen)}
              aria-expanded={productOpen}
              className="flex h-10 items-center gap-1 rounded-lg px-3.5 text-[14.5px] font-medium text-[#3e5373] transition hover:text-[#203653] cursor-pointer"
            >
              Product
              <ChevronDown
                className={`size-3.5 transition-transform duration-200 ${
                  productOpen ? "rotate-180 text-[#315FBA]" : "text-[#7997BE]"
                }`}
              />
            </button>
            <div
              className={`absolute left-1/2 top-full w-[410px] -translate-x-1/2 pt-2 transition-all duration-200 ${
                productOpen
                  ? "visible translate-y-0 opacity-100"
                  : "invisible -translate-y-1 opacity-0 pointer-events-none"
              }`}
            >
              <div className="rounded-2xl border border-[#D9E1F0] bg-white p-2 shadow-pop">
                {PRODUCT_MENU.map((item) => (
                  <button
                    key={item.title}
                    onClick={() => {
                      setProductOpen(false);
                      navigateToSection(item.id);
                    }}
                    className="flex w-full items-start gap-3 rounded-xl p-2.5 text-left transition hover:bg-[#F6F8FC] cursor-pointer"
                  >
                    <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg border border-[#D9E1F0] bg-white text-[#315FBA]">
                      <item.icon className="size-4" />
                    </span>
                    <span>
                      <span className="block text-[13.5px] font-semibold text-[#203653]">
                        {item.title}
                      </span>
                      <span className="block text-[12px] leading-snug text-[#718096]">
                        {item.body}
                      </span>
                    </span>
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* How It Works Link */}
          <button
            onClick={() => navigateToSection("how")}
            className="h-10 rounded-lg px-3.5 text-[14.5px] font-medium text-[#3e5373] transition hover:text-[#203653] cursor-pointer"
          >
            How it works
          </button>

          {/* Solutions Dropdown */}
          <div
            className="relative"
            onMouseEnter={() => setSolutionsOpen(true)}
            onMouseLeave={() => setSolutionsOpen(false)}
          >
            <button
              onClick={() => setSolutionsOpen(!solutionsOpen)}
              aria-expanded={solutionsOpen}
              className="flex h-10 items-center gap-1 rounded-lg px-3.5 text-[14.5px] font-medium text-[#3e5373] transition hover:text-[#203653] cursor-pointer"
            >
              Solutions
              <ChevronDown
                className={`size-3.5 transition-transform duration-200 ${
                  solutionsOpen ? "rotate-180 text-[#315FBA]" : "text-[#7997BE]"
                }`}
              />
            </button>
            <div
              className={`absolute left-1/2 top-full w-[380px] -translate-x-1/2 pt-2 transition-all duration-200 ${
                solutionsOpen
                  ? "visible translate-y-0 opacity-100"
                  : "invisible -translate-y-1 opacity-0 pointer-events-none"
              }`}
            >
              <div className="rounded-2xl border border-[#D9E1F0] bg-white p-2 shadow-pop">
                {SOLUTIONS_MENU.map((item) => (
                  <button
                    key={item.title}
                    onClick={() => {
                      setSolutionsOpen(false);
                      navigateToSection(item.id);
                    }}
                    className="flex w-full items-start gap-3 rounded-xl p-2.5 text-left transition hover:bg-[#F6F8FC] cursor-pointer"
                  >
                    <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg border border-[#D9E1F0] bg-white text-[#315FBA]">
                      <item.icon className="size-4" />
                    </span>
                    <span>
                      <span className="block text-[13.5px] font-semibold text-[#203653]">
                        {item.title}
                      </span>
                      <span className="block text-[12px] leading-snug text-[#718096]">
                        {item.body}
                      </span>
                    </span>
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Trust & Security Link */}
          <button
            onClick={() => navigateToSection("security")}
            className="h-10 rounded-lg px-3.5 text-[14.5px] font-medium text-[#3e5373] transition hover:text-[#203653] cursor-pointer"
          >
            Trust & Security
          </button>

          {/* Developers Link */}
          <Link
            href="/developers"
            className={`h-10 rounded-lg px-3.5 text-[14.5px] font-medium transition flex items-center cursor-pointer ${
              pathname === "/developers"
                ? "text-[#315FBA] font-semibold"
                : "text-[#3e5373] hover:text-[#203653]"
            }`}
          >
            Developers
          </Link>

          {/* FAQ Link */}
          <button
            onClick={() => navigateToSection("faq")}
            className="h-10 rounded-lg px-3.5 text-[14.5px] font-medium text-[#3e5373] transition hover:text-[#203653] cursor-pointer"
          >
            FAQ
          </button>
        </nav>

        {/* Action CTAs */}
        <div className="ml-auto hidden items-center gap-2.5 lg:ml-0 lg:flex">
          {mounted && user ? (
            <button
              onClick={() => router.push("/overview")}
              className="inline-flex h-10 items-center gap-1.5 rounded-[10px] bg-[#315FBA] px-4 text-[14.5px] font-semibold text-white shadow-xs transition hover:bg-[#203653] cursor-pointer"
            >
              Open Workspace
              <ArrowRight className="size-3.5" />
            </button>
          ) : (
            <>
              <button
                onClick={() => handleAuthAction("login")}
                className="h-10 rounded-lg px-4 text-[14.5px] font-semibold text-[#203653] transition hover:bg-white/80 cursor-pointer"
              >
                Log in
              </button>
              <button
                onClick={() => handleAuthAction("register")}
                className="group inline-flex h-10 items-center gap-1.5 rounded-[10px] bg-[#315FBA] px-4 text-[14.5px] font-semibold text-white shadow-xs transition hover:bg-[#203653] cursor-pointer"
              >
                Get started
                <ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5" />
              </button>
            </>
          )}
        </div>

        {/* Mobile Hamburger Button */}
        <button
          onClick={() => setMobileMenuOpen(true)}
          className="ml-auto flex size-10 items-center justify-center rounded-lg text-[#203653] transition hover:bg-slate-100 lg:hidden cursor-pointer"
          aria-label="Open mobile menu"
        >
          <Menu className="size-5" />
        </button>
      </div>

      {/* Mobile Menu Overlay & Drawer */}
      {mobileMenuOpen && (
        <div
          className="fixed inset-0 z-50 bg-[#203653]/40 backdrop-blur-xs lg:hidden"
          onClick={() => setMobileMenuOpen(false)}
        >
          <div
            className="ml-auto flex h-full w-[86%] max-w-sm flex-col bg-white p-6 shadow-pop overflow-y-auto animate-slide"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between">
              <Logo size={26} />
              <button
                onClick={() => setMobileMenuOpen(false)}
                className="flex size-10 items-center justify-center rounded-lg text-[#203653] hover:bg-slate-100 cursor-pointer"
                aria-label="Close menu"
              >
                <X className="size-5" />
              </button>
            </div>

            <div className="mt-8 flex-1 space-y-2">
              <p className="px-3 pb-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">
                Product Modules
              </p>
              {PRODUCT_MENU.map((item) => (
                <button
                  key={item.title}
                  onClick={() => {
                    setMobileMenuOpen(false);
                    setTimeout(() => navigateToSection(item.id), 50);
                  }}
                  className="flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-[14px] font-medium text-[#203653] hover:bg-[#F6F8FC] cursor-pointer"
                >
                  <item.icon className="size-4 text-[#315FBA] shrink-0" />
                  <span>{item.title}</span>
                </button>
              ))}

              <p className="px-3 pb-1 pt-4 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">
                Explore &amp; Solutions
              </p>
              {([
                ["How it works", "how"],
                ["Role Experiences", "roles"],
                ["Trust & Security", "security"],
                ["FAQ", "faq"],
              ] as const).map(([label, id]) => (
                <button
                  key={id}
                  onClick={() => {
                    setMobileMenuOpen(false);
                    setTimeout(() => navigateToSection(id), 50);
                  }}
                  className="block w-full rounded-xl px-3 py-2 text-left text-[14px] font-medium text-[#203653] hover:bg-[#F6F8FC] cursor-pointer"
                >
                  {label}
                </button>
              ))}

              <Link
                href="/developers"
                onClick={() => setMobileMenuOpen(false)}
                className={`block w-full rounded-xl px-3 py-2 text-left text-[14px] font-medium transition cursor-pointer ${
                  pathname === "/developers"
                    ? "text-[#315FBA] font-semibold bg-[#EEF2FA]"
                    : "text-[#203653] hover:bg-[#F6F8FC]"
                }`}
              >
                Meet the Developers
              </Link>
            </div>

            <div className="mt-6 pt-6 border-t border-[#D9E1F0] space-y-2.5">
              {mounted && user ? (
                <button
                  onClick={() => {
                    setMobileMenuOpen(false);
                    router.push("/overview");
                  }}
                  className="flex h-12 w-full items-center justify-center gap-2 rounded-[10px] bg-[#315FBA] text-[15px] font-semibold text-white shadow-xs cursor-pointer"
                >
                  Open Workspace
                  <ArrowRight className="size-4" />
                </button>
              ) : (
                <>
                  <button
                    onClick={() => {
                      setMobileMenuOpen(false);
                      handleAuthAction("register");
                    }}
                    className="flex h-12 w-full items-center justify-center gap-2 rounded-[10px] bg-[#315FBA] text-[15px] font-semibold text-white shadow-xs cursor-pointer"
                  >
                    Get started
                    <ArrowRight className="size-4" />
                  </button>
                  <button
                    onClick={() => {
                      setMobileMenuOpen(false);
                      handleAuthAction("login");
                    }}
                    className="h-12 w-full rounded-[10px] border border-[#D9E1F0] text-[15px] font-semibold text-[#203653] hover:bg-slate-50 cursor-pointer"
                  >
                    Log in
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </header>
  );
}
