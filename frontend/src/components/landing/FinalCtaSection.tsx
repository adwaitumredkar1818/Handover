"use client";

import React, { useState, useEffect } from "react";
import { ArrowRight, HelpCircle } from "lucide-react";
import { OrganicScene } from "../brand/OrganicScene";
import { useLiveApp } from "../../context/LiveAppContext";
import { useRouter } from "next/navigation";
import { useReveal } from "./hooks/useReveal";

export function FinalCtaSection() {
  const ref = useReveal<HTMLElement>();
  const { user } = useLiveApp();
  const router = useRouter();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const handleAction = () => {
    if (user) {
      router.push("/overview");
    } else {
      router.push("/signup");
    }
  };

  const scrollToFaq = () => {
    const el = document.getElementById("faq");
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };

  return (
    <section ref={ref} className="bg-[#112034] px-4 py-20 sm:px-8 sm:py-28 relative overflow-hidden">
      {/* Ambient Blue & Verified Teal Atmospheric Glows */}
      <div
        className="pointer-events-none absolute inset-0 opacity-75"
        style={{
          background:
            "radial-gradient(ellipse 65% 55% at 50% 45%, rgba(49,95,186,0.32), rgba(41,155,128,0.16) 45%, transparent 78%)",
        }}
      />

      {/* Full Connected Organic 3D Sphere Background (echoing BrandIntro) */}
      <div className="pointer-events-none absolute inset-0 flex items-center justify-center opacity-45">
        <OrganicScene
          variant="cinematic"
          dark={true}
          progress={1}
          showTags={false}
          interactive={false}
          className="h-full w-full max-w-[1000px]"
          label="Connected organic knowledge sphere representing unified institutional continuity"
        />
      </div>

      <div className="reveal relative z-10 mx-auto max-w-[1240px] overflow-hidden rounded-[28px] border border-white/15 bg-[#192B44]/85 backdrop-blur-md px-6 py-16 text-center text-white shadow-pop sm:py-24">
        <div className="absolute right-6 top-6 hidden font-mono text-[9.5px] uppercase tracking-[0.14em] text-[#7997BE]/80 sm:block">
          SEC_15 // CONTINUITY
        </div>

        <div className="relative mx-auto max-w-2xl">
          {/* Organic Continuity Bridge Visual */}
          <div className="relative mx-auto -mt-4 mb-6 max-w-[520px] sm:-mt-8">
            <div className="h-[140px] w-full sm:h-[170px]">
              <OrganicScene
                variant="continuity"
                dark={true}
                className="h-full w-full"
                label="Connected continuity bridge between outgoing and incoming team members"
              />
            </div>
            <div className="pointer-events-none flex justify-between px-[14%] font-mono text-[10.5px] tracking-[0.12em] uppercase text-[#a9b8d0]">
              <span>Outgoing</span>
              <span className="text-[#299B80]">Continuity</span>
              <span>Incoming</span>
            </div>
          </div>

          <h2 className="reveal mt-4 text-[34px] font-semibold leading-[1.06] tracking-[-0.04em] text-white sm:text-[46px] lg:text-[54px]">
            Don&apos;t let critical knowledge walk out the door.
          </h2>
          <p className="reveal mx-auto mt-6 max-w-xl text-[16.5px] leading-relaxed text-[#c3cfe0]">
            Reconstruct what your project knows. Verify findings against original evidence. Deliver role-tailored handover dossiers so the next team builds on solid ground.
          </p>

          <div className="reveal mt-10 flex flex-wrap items-center justify-center gap-3.5">
            <button
              onClick={handleAction}
              className="group inline-flex h-12 items-center gap-2 rounded-[10px] bg-white px-6 text-[15px] font-semibold text-[#112034] shadow-lg hover:bg-slate-100 hover:shadow-xl active:scale-[0.98] transition-all duration-200 cursor-pointer focus-visible:ring-2 focus-visible:ring-white"
            >
              <span suppressHydrationWarning>
                {mounted && user ? "Open Project Workspace" : "Get Started"}
              </span>
              <ArrowRight className="size-4 text-[#315FBA] transition-transform duration-200 group-hover:translate-x-0.5" />
            </button>

            <button
              onClick={scrollToFaq}
              className="inline-flex h-12 items-center gap-2 rounded-[10px] border border-white/40 bg-white/10 px-5 text-[15px] font-semibold text-white backdrop-blur-sm transition hover:bg-white/20 cursor-pointer focus-visible:ring-2 focus-visible:ring-white"
            >
              <HelpCircle className="size-4 text-[#c3cfe0]" />
              <span>Review FAQ</span>
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}
