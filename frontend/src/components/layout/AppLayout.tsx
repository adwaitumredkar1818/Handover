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
import { Mail, ShieldAlert } from "lucide-react";

export { RoleBadge };

export function AppLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, isLoadingAuth, setUser } = useLiveApp();
  const [resendMessage, setResendMessage] = useState<string | null>(null);
  const [isResendingVerification, setIsResendingVerification] = useState(false);

  const [collapsed, setCollapsed] = useState(() => {
    if (typeof window !== "undefined") {
      return (
        localStorage.getItem("handover_sidebar_collapsed") === "true" ||
        window.location.search.includes("collapsed=true")
      );
    }
    return false;
  });
  const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState(() => {
    if (typeof window !== "undefined") {
      return window.location.search.includes("openPalette=true");
    }
    return false;
  });

  // Restore collapsed sidebar preference from localStorage or URL query
  useEffect(() => {
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
  const isWide =
    pathname === "/evidence" ||
    pathname === "/audit" ||
    pathname === "/knowledge" ||
    pathname === "/relationships" ||
    pathname === "/verification" ||
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

        <main id="main-scroll" className="ambient-canvas scrollbar-thin flex-1 overflow-y-auto relative">
          <BrandLoadingScreen isLoading={!user || isLoadingAuth} />

          <div
            className={`animate-fade mx-auto w-full px-4 py-6 sm:px-6 lg:px-8 lg:py-8 ${
              isWide ? "max-w-[1600px]" : "max-w-[1360px]"
            }`}
          >
            {user && !user.is_email_verified ? (
              <div className="mx-auto max-w-xl rounded-2xl border border-amber-200 bg-white p-6 shadow-sm">
                <div className="flex items-start gap-3">
                  <div className="rounded-xl bg-amber-50 p-2.5 text-amber-700">
                    <ShieldAlert className="size-5" />
                  </div>
                  <div className="space-y-2">
                    <h2 className="text-base font-semibold text-[#203653]">
                      Verify your email to access project workspaces
                    </h2>
                    <p className="text-xs leading-relaxed text-[#718096]">
                      Your account (<strong>{user.email}</strong>) is signed in,
                      but project evidence, knowledge, and handovers remain
                      locked until your email address is verified.
                    </p>
                    {resendMessage && (
                      <p className="rounded-lg border border-sky-200 bg-sky-50 px-3 py-2 text-xs text-sky-900">
                        {resendMessage}
                      </p>
                    )}
                    <div className="flex flex-wrap items-center gap-2 pt-2">
                      <button
                        type="button"
                        disabled={isResendingVerification}
                        onClick={async () => {
                          setIsResendingVerification(true);
                          setResendMessage(null);
                          try {
                            const res = await api.auth.resendVerification(user.email);
                            setResendMessage(res.message);
                          } catch (err: unknown) {
                            setResendMessage(
                              err instanceof Error
                                ? err.message
                                : "Unable to resend verification email."
                            );
                          } finally {
                            setIsResendingVerification(false);
                          }
                        }}
                        className="inline-flex items-center gap-1.5 rounded-xl bg-[#315FBA] px-3.5 py-2 text-xs font-semibold text-white hover:bg-[#264C98] disabled:opacity-60"
                      >
                        <Mail className="size-3.5" />
                        {isResendingVerification
                          ? "Sending..."
                          : "Resend verification email"}
                      </button>
                      <button
                        type="button"
                        onClick={async () => {
                          try {
                            const fresh = await api.auth.me();
                            setUser(fresh);
                          } catch {
                            // ignore
                          }
                        }}
                        className="inline-flex items-center rounded-xl border border-[#D9E1F0] bg-white px-3.5 py-2 text-xs font-semibold text-[#203653] hover:bg-[#F6F8FC]"
                      >
                        I&apos;ve verified — refresh
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
