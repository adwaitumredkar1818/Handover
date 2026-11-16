"use client";

import React, { Suspense, useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  AlertCircle,
  CheckCircle2,
  Loader2,
  Mail,
  ShieldCheck,
} from "lucide-react";
import { AuthLayout } from "../../components/auth/AuthLayout";
import { useLiveApp } from "../../context/LiveAppContext";
import { api } from "../../lib/api";
import type { VerifyEmailResponse } from "../../lib/types";

function VerifyEmailContent() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token") || "";
  const { user, setUser } = useLiveApp();

  const [status, setStatus] = useState<
    "verifying" | "success" | "error" | "idle"
  >(token ? "verifying" : "idle");
  const [result, setResult] = useState<VerifyEmailResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [resendEmail, setResendEmail] = useState(user?.email || "");
  const [isResending, setIsResending] = useState(false);
  const [resendFeedback, setResendFeedback] = useState<string | null>(null);
  const [resendDelivery, setResendDelivery] = useState<
    "submitted" | "not_configured" | "failed" | null
  >(null);
  const [devToken, setDevToken] = useState<string | null>(null);

  useEffect(() => {
    if (user?.email && !resendEmail) {
      setResendEmail(user.email);
    }
  }, [user?.email, resendEmail]);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    setStatus("verifying");
    setErrorMessage(null);

    api.auth
      .verifyEmail(token)
      .then(async (res) => {
        if (cancelled) return;
        setResult(res);
        setStatus("success");
        try {
          const freshUser = await api.auth.me();
          setUser(freshUser);
        } catch {
          // user may not be signed in yet
        }
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setStatus("error");
        setErrorMessage(
          err instanceof Error
            ? err.message
            : "This verification link is invalid or has expired."
        );
      });

    return () => {
      cancelled = true;
    };
  }, [token, setUser]);

  const handleResend = async (e: FormEvent) => {
    e.preventDefault();
    const cleaned = resendEmail.trim();
    if (!cleaned) return;
    setIsResending(true);
    setResendFeedback(null);
    setResendDelivery(null);
    setDevToken(null);
    try {
      const res = await api.auth.resendVerification(cleaned);
      setResendFeedback(res.message);
      setResendDelivery(res.email_verification_delivery);
      if (res.development_verification_token) {
        setDevToken(res.development_verification_token);
      }
    } catch (err: unknown) {
      setResendDelivery("failed");
      setResendFeedback(
        err instanceof Error
          ? err.message
          : "Unable to resend verification email right now."
      );
    } finally {
      setIsResending(false);
    }
  };

  return (
    <AuthLayout>
      {status === "verifying" && (
        <div className="flex flex-col items-center justify-center py-10 text-center">
          <Loader2 className="size-8 animate-spin text-[#315FBA]" />
          <h1 className="mt-4 text-lg font-semibold text-[#203653]">
            Verifying your email address...
          </h1>
          <p className="mt-1 text-xs text-[#718096]">
            Confirming your verification token with The Handover.
          </p>
        </div>
      )}

      {status === "success" && result && (
        <div className="space-y-5">
          <div className="flex items-start gap-3 rounded-xl border border-teal-200 bg-teal-50/80 p-4 text-teal-900">
            <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-[#299B80]" />
            <div>
              <h1 className="text-base font-semibold">Email Verified</h1>
              <p className="mt-1 text-xs leading-relaxed">{result.message}</p>
            </div>
          </div>

          <div className="rounded-xl border border-[#D9E1F0] bg-[#F6F8FC] p-3.5 text-xs text-[#203653]">
            Verified address: <strong>{result.email}</strong>
          </div>

          <div className="space-y-2.5">
            {user ? (
              <Link
                href="/onboarding"
                className="inline-flex h-11 w-full items-center justify-center rounded-xl bg-[#315FBA] text-sm font-semibold text-white hover:bg-[#264C98]"
              >
                Continue to Onboarding
              </Link>
            ) : (
              <Link
                href={`/login?email=${encodeURIComponent(result.email)}`}
                className="inline-flex h-11 w-full items-center justify-center rounded-xl bg-[#315FBA] text-sm font-semibold text-white hover:bg-[#264C98]"
              >
                Sign In to Continue
              </Link>
            )}
          </div>
        </div>
      )}

      {(status === "error" || status === "idle") && (
        <div className="space-y-5">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-[#203653]">
              Verify your email
            </h1>
            <p className="mt-1.5 text-sm text-[#718096]">
              Email verification is required before accessing project workspaces,
              evidence, or reconstructed knowledge.
            </p>
          </div>

          {status === "error" && errorMessage && (
            <div className="flex items-start gap-2.5 rounded-xl border border-red-200 bg-red-50/80 p-3.5 text-xs text-red-800">
              <AlertCircle className="mt-0.5 size-4 shrink-0 text-red-600" />
              <span>{errorMessage}</span>
            </div>
          )}

          <form onSubmit={handleResend} className="space-y-3.5">
            <div>
              <label className="block text-xs font-semibold text-[#203653]">
                Request a new verification link
              </label>
              <div className="relative mt-1">
                <Mail className="pointer-events-none absolute left-3 top-2.5 size-4 text-[#718096]" />
                <input
                  type="email"
                  value={resendEmail}
                  onChange={(e) => setResendEmail(e.target.value)}
                  placeholder="you@company.com"
                  required
                  className="h-10 w-full rounded-xl border border-[#D9E1F0] bg-white pl-9 pr-3 text-sm text-[#203653] focus:border-[#315FBA] focus:outline-none"
                />
              </div>
            </div>

            {resendFeedback && (
              <div
                className={`rounded-xl border p-3 text-xs ${
                  resendDelivery === "submitted"
                    ? "border-teal-200 bg-teal-50/80 text-teal-900"
                    : resendDelivery === "not_configured"
                    ? "border-amber-200 bg-amber-50/80 text-amber-900"
                    : "border-red-200 bg-red-50/80 text-red-900"
                }`}
              >
                <p className="font-medium">{resendFeedback}</p>
                {resendDelivery === "submitted" && (
                  <p className="mt-0.5 text-[11px] text-teal-800">
                    Please check your inbox and spam folder.
                  </p>
                )}
                {devToken && (
                  <div className="mt-2.5 pt-2 border-t border-amber-200/60 flex items-center justify-between gap-2">
                    <span className="text-[11px] text-amber-800">Local dev shortcut:</span>
                    <Link
                      href={`/verify-email?token=${encodeURIComponent(devToken)}`}
                      className="inline-block rounded-lg bg-[#315FBA] px-2.5 py-1 text-xs font-semibold text-white hover:bg-[#264C98]"
                    >
                      Quick-Verify
                    </Link>
                  </div>
                )}
              </div>
            )}

            <button
              type="submit"
              disabled={isResending}
              className="flex h-11 w-full items-center justify-center gap-2 rounded-xl bg-[#315FBA] text-sm font-semibold text-white hover:bg-[#264C98] disabled:opacity-60"
            >
              {isResending ? (
                <>
                  <Loader2 className="size-4 animate-spin" />
                  Sending link...
                </>
              ) : (
                "Resend Verification Email"
              )}
            </button>
          </form>

          <p className="flex items-center justify-center gap-1.5 text-[11px] text-[#718096]">
            <ShieldCheck className="size-3.5 text-[#299B80]" />
            <Link href="/login" className="text-[#315FBA] hover:underline">
              Back to Sign In
            </Link>
          </p>
        </div>
      )}
    </AuthLayout>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense
      fallback={
        <AuthLayout>
          <div className="flex items-center justify-center py-12">
            <Loader2 className="size-6 animate-spin text-[#315FBA]" />
          </div>
        </AuthLayout>
      }
    >
      <VerifyEmailContent />
    </Suspense>
  );
}
