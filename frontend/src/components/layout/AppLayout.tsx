"use client";

import React, { useEffect, useState, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Sidebar, RoleBadge } from "./Sidebar";
import { TopNav } from "./TopNav";
import { CommandPalette } from "./CommandPalette";
import { ToastContainer } from "../common/ToastContainer";
import { Logo, BrandLoadingScreen } from "../brand";
import { CreateOrganisationModal } from "../modals/CreateOrganisationModal";
import { CreateProjectModal } from "../modals/CreateProjectModal";
import { UploadDocumentModal } from "../modals/UploadDocumentModal";
import { ConnectSourceModal } from "../modals/ConnectSourceModal";
import { AddMemberModal } from "../modals/AddMemberModal";
import { useLiveApp } from "../../context/LiveAppContext";
import { api } from "../../lib/api";
import Link from "next/link";
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  Loader2,
  Mail,
  RefreshCw,
  ShieldAlert,
} from "lucide-react";

export { RoleBadge };

export function AppLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, isLoadingAuth, setUser, addToast, projects, activeProject, setActiveProject } = useLiveApp();
  const [resendStatus, setResendStatus] = useState<
    "idle" | "submitted" | "not_configured" | "failed" | "rate_limited"
  >("idle");
  const [resendMessage, setResendMessage] = useState<string | null>(null);
  const [devToken, setDevToken] = useState<string | null>(null);
  const [isResendingVerification, setIsResendingVerification] = useState(false);
  const [isRefreshingVerification, setIsRefreshingVerification] = useState(false);
  const [refreshFeedback, setRefreshFeedback] = useState<string | null>(null);

  // SSR-safe state defaults: client-only browser storage/URL params restore on mount
  const [isMounted, setIsMounted] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState(false);

  // Restore collapsed sidebar preference and command palette trigger from localStorage / URL query on mount
  useEffect(() => {
    setIsMounted(true);
    if (typeof window !== "undefined") {
      const saved = localStorage.getItem("handover_sidebar_collapsed");
      const urlHasCollapsed = window.location.search.includes("collapsed=true");
      if (saved === "true" || urlHasCollapsed) {
        setCollapsed(true);
      }
      if (window.location.search.includes("openPalette=true")) {
        setIsCommandPaletteOpen(true);
      }
    }
  }, []);

  // Synchronise route project ID into activeProject is handled centrally by LiveAppContext

  const handleToggleCollapse = () => {
    setCollapsed((prev) => {
      const next = !prev;
      if (typeof window !== "undefined") {
        localStorage.setItem("handover_sidebar_collapsed", String(next));
      }
      return next;
    });
  };

  const isAuthPage =
    pathname === "/login" ||
    pathname === "/signup" ||
    pathname === "/forgot-password" ||
    pathname === "/reset-password" ||
    pathname === "/verify-email" ||
    pathname === "/onboarding" ||
    pathname?.startsWith("/invitations/") ||
    pathname?.startsWith("/auth/");

  const isPublicRoute = pathname === "/" || pathname === "/landing" || isAuthPage;

  // Protect all non-public routes by cleanly redirecting unauthenticated users to /login
  useEffect(() => {
    if (!isPublicRoute && !isLoadingAuth && !user) {
      router.push("/login");
    }
  }, [isPublicRoute, isLoadingAuth, user, router]);

  // Public and authentication pages bypass the authenticated shell
  if (isPublicRoute) {
    return (
      <div className="min-h-screen w-full bg-[#F6F8FC] text-navy font-sans antialiased">
        {children}
        <ToastContainer />
      </div>
    );
  }

  // Wide container for data-dense routes
  const isVerificationViewportRoute =
    pathname === "/verification" ||
    Boolean(pathname && /^\/projects\/[^/]+\/verification\/?$/.test(pathname));

  const isWide =
    pathname === "/evidence" ||
    pathname === "/audit" ||
    pathname === "/knowledge" ||
    pathname === "/relationships" ||
    isVerificationViewportRoute ||
    pathname === "/conflicts" ||
    pathname === "/handover";

  return (
    <div className="flex h-dvh overflow-hidden bg-canvas font-sans antialiased text-navy">
      {/* Desktop Persistent Sidebar & Mobile Drawer */}
      <Sidebar
        collapsed={collapsed}
        onToggleCollapse={handleToggleCollapse}
        onOpenSearch={() => setIsCommandPaletteOpen(true)}
      />

      {/* Main Content Column */}
      <div className="flex min-w-0 flex-1 flex-col h-full overflow-hidden">
        <TopNav
          collapsed={collapsed}
          onToggleCollapse={handleToggleCollapse}
          onOpenSearch={() => setIsCommandPaletteOpen(true)}
        />

        <main
          id="main-scroll"
          className={`ambient-canvas scrollbar-thin flex-1 min-h-0 relative ${
            isVerificationViewportRoute
              ? "overflow-y-auto md:overflow-hidden md:flex md:flex-col"
              : "overflow-y-auto"
          }`}
        >
          <BrandLoadingScreen isLoading={!isMounted || !user || isLoadingAuth} />

          <div
            className={`animate-fade mx-auto w-full px-4 sm:px-6 lg:px-8 ${
              isVerificationViewportRoute
                ? "max-w-[1600px] py-4 lg:py-5 md:flex-1 md:min-h-0 md:flex md:flex-col"
                : `py-6 lg:py-8 ${isWide ? "max-w-[1600px]" : "max-w-[1360px]"}`
            }`}
          >
            {isMounted && user && !user.is_email_verified ? (
              <div className="mx-auto max-w-xl rounded-2xl border border-amber-200 bg-white p-6 shadow-sm">
                <div className="flex items-start gap-3">
                  <div className="rounded-xl bg-amber-50 p-2.5 text-amber-700">
                    <ShieldAlert className="size-5" />
                  </div>
                  <div className="space-y-3 flex-1 min-w-0">
                    <div>
                      <h2 className="text-base font-semibold text-[#203653]">
                        Verify your email to access project workspaces
                      </h2>
                      <p className="mt-1 text-xs leading-relaxed text-[#718096]">
                        Your account (<strong>{user.email}</strong>) is signed in,
                        but project evidence, knowledge, and handovers remain
                        locked until your email address is verified.
                      </p>
                    </div>

                    {resendStatus === "submitted" && (
                      <div className="rounded-xl border border-teal-200 bg-teal-50/80 p-3 text-xs text-teal-900 flex items-start gap-2">
                        <CheckCircle2 className="size-4 shrink-0 mt-0.5 text-[#299B80]" />
                        <div>
                          <p className="font-medium">Verification email dispatched</p>
                          <p className="mt-0.5 text-[11px] text-teal-800 leading-relaxed">
                            {resendMessage || `A verification link has been sent to ${user.email}. Please check your inbox and spam folder.`}
                          </p>
                        </div>
                      </div>
                    )}

                    {resendStatus === "not_configured" && (
                      <div className="rounded-xl border border-amber-200 bg-amber-50/80 p-3 text-xs text-amber-900 flex items-start gap-2">
                        <AlertCircle className="size-4 shrink-0 mt-0.5 text-amber-600" />
                        <div>
                          <p className="font-medium">Outbound email delivery not active</p>
                          <p className="mt-0.5 text-[11px] text-amber-800 leading-relaxed">
                            {resendMessage || "Email delivery is disabled or not configured in this environment. In development mode, use the quick-verify option below."}
                          </p>
                        </div>
                      </div>
                    )}

                    {resendStatus === "failed" && (
                      <div className="rounded-xl border border-red-200 bg-red-50/80 p-3 text-xs text-red-900 flex items-start gap-2">
                        <AlertCircle className="size-4 shrink-0 mt-0.5 text-red-600" />
                        <div>
                          <p className="font-medium">Email delivery failed</p>
                          <p className="mt-0.5 text-[11px] text-red-800 leading-relaxed">
                            {resendMessage}
                          </p>
                        </div>
                      </div>
                    )}

                    {resendStatus === "rate_limited" && (
                      <div className="rounded-xl border border-amber-200 bg-amber-50/80 p-3 text-xs text-amber-900 flex items-start gap-2">
                        <Clock className="size-4 shrink-0 mt-0.5 text-amber-600" />
                        <div>
                          <p className="font-medium">Rate limit reached</p>
                          <p className="mt-0.5 text-[11px] text-amber-800 leading-relaxed">
                            {resendMessage}
                          </p>
                        </div>
                      </div>
                    )}

                    {devToken && (
                      <div className="rounded-xl border border-blue-200 bg-blue-50/80 p-3 text-xs text-blue-900 flex items-center justify-between gap-2">
                        <div>
                          <p className="font-medium text-blue-950">Development Bypass Available</p>
                          <p className="text-[11px] text-blue-800">
                            Development token issued for immediate local testing:
                          </p>
                        </div>
                        <Link
                          href={`/verify-email?token=${encodeURIComponent(devToken)}`}
                          className="shrink-0 rounded-lg bg-[#315FBA] px-3 py-1.5 text-xs font-semibold text-white hover:bg-[#264C98]"
                        >
                          Quick-Verify
                        </Link>
                      </div>
                    )}

                    {refreshFeedback && (
                      <div className="rounded-xl border border-amber-200 bg-amber-50/80 p-3 text-xs text-amber-900 flex items-start gap-2">
                        <AlertCircle className="size-4 shrink-0 mt-0.5 text-amber-600" />
                        <p className="text-[11px] text-amber-800 leading-relaxed">{refreshFeedback}</p>
                      </div>
                    )}

                    <div className="flex flex-wrap items-center gap-2 pt-1">
                      <button
                        type="button"
                        disabled={isResendingVerification}
                        onClick={async () => {
                          setIsResendingVerification(true);
                          setResendMessage(null);
                          setDevToken(null);
                          setRefreshFeedback(null);
                          try {
                            const res = await api.auth.resendVerification(user.email);
                            setResendStatus(res.email_verification_delivery);
                            setResendMessage(res.message);
                            if (res.development_verification_token) {
                              setDevToken(res.development_verification_token);
                            }
                          } catch (err: unknown) {
                            const errMsg =
                              err instanceof Error
                                ? err.message
                                : "Unable to resend verification email.";
                            if (
                              errMsg.includes("429") ||
                              errMsg.toLowerCase().includes("too many requests") ||
                              errMsg.toLowerCase().includes("rate limit")
                            ) {
                              setResendStatus("rate_limited");
                              setResendMessage(
                                "Too many verification requests. Please wait a minute before requesting another email."
                              );
                            } else {
                              setResendStatus("failed");
                              setResendMessage(errMsg);
                            }
                          } finally {
                            setIsResendingVerification(false);
                          }
                        }}
                        className="inline-flex items-center gap-1.5 rounded-xl bg-[#315FBA] px-3.5 py-2 text-xs font-semibold text-white hover:bg-[#264C98] disabled:opacity-60"
                      >
                        {isResendingVerification ? (
                          <>
                            <Loader2 className="size-3.5 animate-spin" />
                            Sending...
                          </>
                        ) : (
                          <>
                            <Mail className="size-3.5" />
                            Resend verification email
                          </>
                        )}
                      </button>
                      <button
                        type="button"
                        disabled={isRefreshingVerification}
                        onClick={async () => {
                          setIsRefreshingVerification(true);
                          setRefreshFeedback(null);
                          try {
                            const fresh = await api.auth.me();
                            setUser(fresh);
                            if (fresh.is_email_verified) {
                              addToast({
                                type: "success",
                                title: "Email Verified",
                                message: "Your email address has been verified. Project workspaces unlocked!",
                              });
                            } else {
                              setRefreshFeedback(
                                "Your account is not verified yet. Please check your inbox and click the verification link, or click Resend."
                              );
                            }
                          } catch (err: unknown) {
                            setRefreshFeedback(
                              err instanceof Error
                                ? err.message
                                : "Unable to refresh verification status right now."
                            );
                          } finally {
                            setIsRefreshingVerification(false);
                          }
                        }}
                        className="inline-flex items-center gap-1.5 rounded-xl border border-[#D9E1F0] bg-white px-3.5 py-2 text-xs font-semibold text-[#203653] hover:bg-[#F6F8FC] disabled:opacity-60"
                      >
                        {isRefreshingVerification ? (
                          <>
                            <Loader2 className="size-3.5 animate-spin" />
                            Checking...
                          </>
                        ) : (
                          <>
                            <RefreshCw className="size-3.5" />
                            I&apos;ve verified — refresh
                          </>
                        )}
                      </button>
                      <Link
                        href="/verify-email"
                        className="text-xs font-semibold text-[#315FBA] hover:underline px-2"
                      >
                        Open verification page
                      </Link>
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              children
            )}
          </div>
        </main>
      </div>

      {/* Global Modals & Keyboard Spotlight */}
      <CommandPalette
        open={isCommandPaletteOpen}
        onClose={() => setIsCommandPaletteOpen(false)}
      />
      <ToastContainer />
      <CreateOrganisationModal />
      <CreateProjectModal />
      <UploadDocumentModal />
      <ConnectSourceModal />
      <AddMemberModal />
    </div>
  );
}
