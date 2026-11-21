import React from "react";
import type { Metadata, Viewport } from "next";
import { Suspense } from "react";
import { Manrope, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { LiveAppProvider } from "../context/LiveAppContext";
import { QueryProvider } from "../providers/QueryProvider";
import { FigmaStoreProvider } from "../lib/figmaStore";
import { AppLayout } from "../components/layout/AppLayout";
import { AgentationToolbar } from "../components/AgentationToolbar";
import { FigmaLiveBridge } from "../components/FigmaLiveBridge";

const manrope = Manrope({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export const metadata: Metadata = {
  title: "The Handover · Intelligent Project Knowledge Reconstruction & Handover Platform",
  description:
    "Prevent Critical Knowledge From Leaving With People. Reconstruct fragmented project context across repositories, issue trackers, discussions, and documents into certified, role-tailored handovers.",
  keywords: [
    "knowledge reconstruction",
    "project handover",
    "institutional memory",
    "knowledge management",
    "developer offboarding",
    "engineering leadership",
    "architectural decision records",
    "provenance",
    "RAG assistant",
  ],
  authors: [{ name: "The Handover Team" }],
  openGraph: {
    title: "The Handover · Prevent Critical Knowledge From Leaving With People",
    description:
      "Intelligent Project Knowledge Reconstruction & Handover Platform. Reconstruct fragmented project knowledge, surface conflicts, and generate certified handovers.",
    siteName: "The Handover",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "The Handover · Prevent Critical Knowledge From Leaving With People",
    description:
      "Reconstruct fragmented project context across code, issues, discussions, and documents into verified, role-tailored handover packages.",
  },
  icons: {
    icon: "/favicon.png",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${manrope.variable} ${jetbrainsMono.variable}`} suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var t=localStorage.getItem('th_theme')||'light';var d=localStorage.getItem('th_density')||'comfortable';var r=localStorage.getItem('th_reduced_motion')==='true';var eff=t==='dark'?'dark':(t==='system'&&window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');var el=document.documentElement;el.setAttribute('data-theme',eff);el.setAttribute('data-theme-mode',t);el.classList.toggle('dark',eff==='dark');el.setAttribute('data-density',d);el.setAttribute('data-reduced-motion',String(r));}catch(e){}})();`,
          }}
        />
      </head>
      <body className="antialiased font-sans" suppressHydrationWarning>
        <QueryProvider>
          <FigmaStoreProvider>
            <Suspense fallback={<div className="min-h-screen bg-[#F6F8FC]" />}>
              <LiveAppProvider>
                <FigmaLiveBridge />
                <AppLayout>{children}</AppLayout>
                <AgentationToolbar />
              </LiveAppProvider>
            </Suspense>
          </FigmaStoreProvider>
        </QueryProvider>
      </body>
    </html>
  );
}
