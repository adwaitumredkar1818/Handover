"use client";

import React, { useCallback, useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  AlertCircle,
  Building2,
  CheckCircle2,
  Clock,
  Eye,
  EyeOff,
  FolderKanban,
  Loader2,
  LogOut,
  Mail,
  ShieldCheck,
  UserCheck,
} from "lucide-react";
import { AuthLayout } from "../../../components/auth/AuthLayout";
import { useLiveApp } from "../../../context/LiveAppContext";
import { api, ApiError } from "../../../lib/api";
import type {
  AcceptInvitationResponse,
  InvitationPreviewResponse,
  RegisterWithInvitationResponse,
} from "../../../lib/types";

export default function InvitationAcceptancePage() {
  const params = useParams<{ token: string }>();
  const router = useRouter();
  const token = typeof params?.token === "string" ? decodeURIComponent(params.token) : "";

  const { user, isLoadingAuth, logout, refreshProjects } = useLiveApp();

  const [preview, setPreview] = useState<InvitationPreviewResponse | null>(null);
  const [isLoadingPreview, setIsLoadingPreview] = useState(true);
  const [previewError, setPreviewError] = useState<string | null>(null);

  // Mode for unauthenticated users: create new account vs sign in with existing account
  const [mode, setMode] = useState<"register" | "signin">("register");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const [registerResult, setRegisterResult] =
    useState<RegisterWithInvitationResponse | null>(null);
  const [acceptResult, setAcceptResult] =
    useState<AcceptInvitationResponse | null>(null);

  const [resendStatus, setResendStatus] = useState<string | null>(null);
  const [isResending, setIsResending] = useState(false);

  const loadPreview = useCallback(async () => {
    if (!token) {
      setPreviewError("Invalid invitation link.");
      setIsLoadingPreview(false);
      return;
    }
    setIsLoadingPreview(true);
    setPreviewError(null);
    try {
      const res = await api.invitations.preview(token);
      setPreview(res);
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 404) {
        setPreviewError("This invitation link is invalid or no longer exists.");
      } else {
        setPreviewError(
          err instanceof Error
            ? err.message
            : "Unable to load invitation details."
        );
      }
    } finally {
      setIsLoadingPreview(false);
    }
  }, [token]);

  useEffect(() => {
    void loadPreview();
  }, [loadPreview]);

  const hasMinLength = password.length >= 12;
  const hasUpper = /[A-Z]/.test(password);
  const hasLower = /[a-z]/.test(password);
  const hasNumber = /[0-9]/.test(password);
  const hasSpecial = /[^A-Za-z0-9\s]/.test(password);

  const handleRegisterSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!preview) return;
    setActionError(null);

    if (fullName.trim().length < 2) {
      setActionError("Please enter your full name (at least 2 characters).");
      return;
    }
    if (!hasMinLength || !hasUpper || !hasLower || !hasNumber || !hasSpecial) {
      setActionError(
        "Password must be at least 12 characters and include uppercase, lowercase, numbers, and special characters."
      );
      return;
    }
    if (password !== confirmPassword) {
      setActionError("Passwords do not match.");
      return;
    }

    setIsSubmitting(true);
    try {
      const res = await api.auth.registerWithInvitation({
        invitation_token: token,
        full_name: fullName.trim(),
        password,
        email: preview.email,
      });
      setRegisterResult(res);
    } catch (err: unknown) {
      setActionError(
        err instanceof Error
          ? err.message
          : "Failed to create account with this invitation."
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleAcceptAsSignedInUser = async () => {
    setActionError(null);
    setIsSubmitting(true);
    try {
      const res = await api.invitations.accept(token);
      setAcceptResult(res);
      await refreshProjects();
    } catch (err: unknown) {
      setActionError(
        err instanceof Error ? err.message : "Failed to accept invitation."
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleResendVerification = async (email: string) => {
    setIsResending(true);
    setResendStatus(null);
    try {
      const res = await api.auth.resendVerification(email);
      setResendStatus(res.message);
    } catch (err: unknown) {
      setResendStatus(
        err instanceof Error
          ? err.message
          : "Unable to resend verification email right now."
      );
    } finally {
      setIsResending(false);
    }
  };

  const roleLabel =
    preview?.project_role_name?.replace(/_/g, " ") ||
    preview?.role_name.replace(/_/g, " ") ||
    "Member";

  return (
    <AuthLayout>
      {isLoadingPreview || isLoadingAuth ? (
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <Loader2 className="size-7 animate-spin text-[#315FBA]" />
          <p className="mt-3 text-sm text-[#718096]">
            Validating invitation link...
          </p>
        </div>
      ) : previewError || !preview ? (
        <div className="space-y-4">
          <div className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50/80 p-4 text-sm text-red-800">
            <AlertCircle className="mt-0.5 size-5 shrink-0 text-red-600" />
            <div>
              <h1 className="font-semibold">Invitation Unavailable</h1>
              <p className="mt-1 text-xs leading-relaxed">
                {previewError || "This invitation could not be found."}
              </p>
            </div>
          </div>
          <Link
            href="/login"
            className="inline-flex h-10 w-full items-center justify-center rounded-xl border border-[#D9E1F0] bg-white text-sm font-semibold text-[#203653] hover:bg-[#F6F8FC]"
          >
            Go to Sign In
          </Link>
        </div>
      ) : registerResult ? (
        <div className="space-y-4">
          <div className="flex items-start gap-3 rounded-xl border border-teal-200 bg-teal-50/80 p-4 text-teal-900">
            <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-[#299B80]" />
            <div>
              <h1 className="text-base font-semibold">
                Account Created &amp; Invitation Accepted
              </h1>
              <p className="mt-1 text-xs leading-relaxed">
                {registerResult.message}
              </p>
            </div>
          </div>

          <div className="rounded-xl border border-[#D9E1F0] bg-[#F6F8FC] p-4 text-xs text-[#203653] space-y-1.5">
            <p>
              <strong>Organisation:</strong> {registerResult.organisation_name}
            </p>
            {registerResult.project_name && (
              <p>
                <strong>Project:</strong> {registerResult.project_name}
              </p>
            )}
            {registerResult.project_role_name && (
              <p>
                <strong>Assigned Role:</strong>{" "}
                {registerResult.project_role_name.replace(/_/g, " ")}
              </p>
            )}
          </div>

          {!registerResult.can_access_project_immediately && (
            <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-xs text-amber-900 space-y-2.5">
              <div className="flex items-start gap-2">
                <Mail className="mt-0.5 size-4 shrink-0 text-amber-700" />
                <div>
                  <p className="font-semibold">Email verification required</p>
                  <p className="mt-0.5 leading-relaxed">
                    We sent a verification link to{" "}
                    <strong>{registerResult.user.email}</strong>. Verify your
                    email before opening project evidence or knowledge.
                  </p>
                </div>
              </div>
              {registerResult.development_verification_token && (
                <div className="rounded-lg border border-amber-200 bg-white p-2.5">
                  <p className="text-[11px] font-medium text-[#718096]">
                    Development verification shortcut:
                  </p>
                  <Link
                    href={`/verify-email?token=${encodeURIComponent(
                      registerResult.development_verification_token
                    )}`}
                    className="mt-1 inline-block text-xs font-semibold text-[#315FBA] underline"
                  >
                    Verify email now
                  </Link>
                </div>
              )}
              <button
                type="button"
                onClick={() =>
                  void handleResendVerification(registerResult.user.email)
                }
                disabled={isResending}
                className="text-xs font-semibold text-amber-900 underline hover:opacity-80 disabled:opacity-50"
              >
                {isResending ? "Sending..." : "Resend verification email"}
              </button>
              {resendStatus && (
                <p className="text-[11px] text-amber-800">{resendStatus}</p>
              )}
            </div>
          )}

          <Link
            href={`/login?email=${encodeURIComponent(registerResult.user.email)}`}
            className="inline-flex h-11 w-full items-center justify-center rounded-xl bg-[#315FBA] text-sm font-semibold text-white hover:bg-[#264C98]"
          >
            Continue to Sign In
          </Link>
        </div>
      ) : acceptResult ? (
        <div className="space-y-4">
          <div className="flex items-start gap-3 rounded-xl border border-teal-200 bg-teal-50/80 p-4 text-teal-900">
            <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-[#299B80]" />
            <div>
              <h1 className="text-base font-semibold">Invitation Accepted</h1>
              <p className="mt-1 text-xs leading-relaxed">
                You now have access to{" "}
                <strong>
                  {acceptResult.project_name || acceptResult.organisation_name}
                </strong>
                .
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={() =>
              router.push(
                acceptResult.project_id
                  ? `/onboarding?project=${acceptResult.project_id}`
                  : "/overview"
              )
            }
            className="inline-flex h-11 w-full items-center justify-center rounded-xl bg-[#315FBA] text-sm font-semibold text-white hover:bg-[#264C98]"
          >
            Continue to Onboarding
          </button>
        </div>
      ) : (
        <div className="space-y-5">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-[#315FBA]">
              {preview.project_id ? "Project Invitation" : "Workspace Invitation"}
            </p>
            <h1 className="mt-1 text-2xl font-semibold tracking-tight text-[#203653]">
              You&apos;re invited to join{" "}
              {preview.project_name || preview.organisation_name}
            </h1>
            <p className="mt-1.5 text-sm text-[#718096]">
              {preview.inviter_name
                ? `${preview.inviter_name} invited you to collaborate on The Handover.`
                : "Accept this invitation to join your team workspace."}
            </p>
          </div>

          {/* Safe Invitation Summary Card */}
          <div className="rounded-xl border border-[#D9E1F0] bg-[#F6F8FC] p-4 space-y-2.5 text-xs text-[#203653]">
            <div className="flex items-center gap-2">
              <Building2 className="size-4 text-[#315FBA]" />
              <span>
                Organisation: <strong>{preview.organisation_name}</strong>
              </span>
            </div>
            {preview.project_name && (
              <div className="flex items-center gap-2">
                <FolderKanban className="size-4 text-[#315FBA]" />
                <span>
                  Project: <strong>{preview.project_name}</strong>
                </span>
              </div>
            )}
            <div className="flex items-center gap-2">
              <UserCheck className="size-4 text-[#299B80]" />
              <span>
                Assigned role: <strong className="capitalize">{roleLabel}</strong>
              </span>
            </div>
            <div className="flex items-center gap-2">
              <Mail className="size-4 text-[#718096]" />
              <span>
                Invited email: <strong>{preview.email}</strong>
              </span>
            </div>
            <div className="flex items-center gap-2 text-[#718096]">
              <Clock className="size-4" />
              <span>
                Expires {new Date(preview.expires_at).toLocaleString()}
              </span>
            </div>
          </div>

          {!preview.is_actionable ? (
            <div className="space-y-4">
              <div className="flex items-start gap-2.5 rounded-xl border border-amber-200 bg-amber-50 p-4 text-xs text-amber-900">
                <AlertCircle className="mt-0.5 size-4 shrink-0 text-amber-700" />
                <div>
                  <p className="font-semibold capitalize">
                    Invitation {preview.status}
                  </p>
                  <p className="mt-1 leading-relaxed">
                    {preview.status === "accepted"
                      ? "This invitation has already been accepted. Please sign in to access your workspace."
                      : preview.status === "revoked"
                        ? "This invitation has been revoked by a project or organisation administrator."
                        : "This invitation has expired. Ask a project manager to send a new invitation."}
                  </p>
                </div>
              </div>
              <Link
                href="/login"
                className="inline-flex h-10 w-full items-center justify-center rounded-xl border border-[#D9E1F0] bg-white text-sm font-semibold text-[#203653] hover:bg-[#F6F8FC]"
              >
                Go to Sign In
              </Link>
            </div>
          ) : user ? (
            <div className="space-y-4">
              {actionError && (
                <div className="flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 p-3 text-xs text-red-700">
                  <AlertCircle className="mt-0.5 size-4 shrink-0" />
                  <span>{actionError}</span>
                </div>
              )}

              {user.email.toLowerCase() === preview.email.toLowerCase() ? (
                <>
                  {!user.is_email_verified && (
                    <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900 space-y-2">
                      <p className="font-semibold">
                        Verify your email before accessing project data
                      </p>
                      <p>
                        You can accept this invitation now, then verify{" "}
                        <strong>{user.email}</strong> to unlock project access.
                      </p>
                      <button
                        type="button"
                        onClick={() => void handleResendVerification(user.email)}
                        disabled={isResending}
                        className="font-semibold underline"
                      >
                        {isResending ? "Sending..." : "Resend verification email"}
                      </button>
                    </div>
                  )}
                  <button
                    type="button"
                    onClick={() => void handleAcceptAsSignedInUser()}
                    disabled={isSubmitting}
                    className="flex h-11 w-full items-center justify-center gap-2 rounded-xl bg-[#315FBA] text-sm font-semibold text-white hover:bg-[#264C98] disabled:opacity-60"
                  >
                    {isSubmitting ? (
                      <>
                        <Loader2 className="size-4 animate-spin" />
                        Accepting invitation...
                      </>
                    ) : (
                      "Accept Invitation & Join"
                    )}
                  </button>
                </>
              ) : (
                <div className="space-y-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-xs text-amber-900">
                  <p className="font-semibold">Signed in with a different email</p>
                  <p>
                    You are currently signed in as{" "}
                    <strong>{user.email}</strong>, but this invitation was sent
                    to <strong>{preview.email}</strong>.
                  </p>
                  <button
                    type="button"
                    onClick={() => void logout()}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-amber-300 bg-white px-3 py-1.5 font-semibold text-[#203653] hover:bg-amber-100"
                  >
                    <LogOut className="size-3.5" />
                    Sign out to continue as {preview.email}
                  </button>
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-4">
              {/* Toggle between new registration and existing account sign in */}
              <div className="grid grid-cols-2 rounded-xl border border-[#D9E1F0] bg-[#F6F8FC] p-1 text-xs font-semibold">
                <button
                  type="button"
                  onClick={() => {
                    setActionError(null);
                    setMode("register");
                  }}
                  className={`rounded-lg py-2 transition ${
                    mode === "register"
                      ? "bg-white text-[#203653] shadow-2xs"
                      : "text-[#718096] hover:text-[#203653]"
                  }`}
                >
                  Create Account
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setActionError(null);
                    setMode("signin");
                  }}
                  className={`rounded-lg py-2 transition ${
                    mode === "signin"
                      ? "bg-white text-[#203653] shadow-2xs"
                      : "text-[#718096] hover:text-[#203653]"
                  }`}
                >
                  Existing Account
                </button>
              </div>

              {actionError && (
                <div className="flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 p-3 text-xs text-red-700">
                  <AlertCircle className="mt-0.5 size-4 shrink-0" />
                  <span>{actionError}</span>
                </div>
              )}

              {mode === "register" ? (
                <form onSubmit={handleRegisterSubmit} className="space-y-3.5">
                  <div>
                    <label className="block text-xs font-semibold text-[#203653]">
                      Invited Email
                    </label>
                    <input
                      type="email"
                      value={preview.email}
                      disabled
                      className="mt-1 h-10 w-full rounded-xl border border-[#D9E1F0] bg-[#F6F8FC] px-3 text-sm text-[#718096]"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-[#203653]">
                      Full Name
                    </label>
                    <input
                      type="text"
                      value={fullName}
                      onChange={(e) => setFullName(e.target.value)}
                      placeholder="Alex Rivera"
                      required
                      className="mt-1 h-10 w-full rounded-xl border border-[#D9E1F0] bg-white px-3 text-sm text-[#203653] focus:border-[#315FBA] focus:outline-none"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-[#203653]">
                      Password
                    </label>
                    <div className="relative mt-1">
                      <input
                        type={showPassword ? "text" : "password"}
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        placeholder="At least 12 characters"
                        required
                        className="h-10 w-full rounded-xl border border-[#D9E1F0] bg-white pl-3 pr-10 text-sm text-[#203653] focus:border-[#315FBA] focus:outline-none"
                      />
                      <button
                        type="button"
                        onClick={() => setShowPassword((v) => !v)}
                        className="absolute right-3 top-2.5 text-[#718096] hover:text-[#203653]"
                        aria-label="Toggle password visibility"
                      >
                        {showPassword ? (
                          <EyeOff className="size-4" />
                        ) : (
                          <Eye className="size-4" />
                        )}
                      </button>
                    </div>
                    <p className="mt-1 text-[11px] text-[#718096]">
                      12+ chars with uppercase, lowercase, number, and symbol.
                    </p>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-[#203653]">
                      Confirm Password
                    </label>
                    <input
                      type="password"
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      placeholder="Re-enter password"
                      required
                      className="mt-1 h-10 w-full rounded-xl border border-[#D9E1F0] bg-white px-3 text-sm text-[#203653] focus:border-[#315FBA] focus:outline-none"
                    />
                  </div>

                  <button
                    type="submit"
                    disabled={isSubmitting}
                    className="flex h-11 w-full items-center justify-center gap-2 rounded-xl bg-[#315FBA] text-sm font-semibold text-white hover:bg-[#264C98] disabled:opacity-60"
                  >
                    {isSubmitting ? (
                      <>
                        <Loader2 className="size-4 animate-spin" />
                        Creating account...
                      </>
                    ) : (
                      "Create Account & Accept Invitation"
                    )}
                  </button>
                </form>
              ) : (
                <div className="space-y-3 rounded-xl border border-[#D9E1F0] bg-white p-4 text-xs text-[#718096]">
                  <p className="leading-relaxed">
                    Already have a Handover account for{" "}
                    <strong className="text-[#203653]">{preview.email}</strong>?
                    Sign in to accept this invitation without creating a
                    duplicate account.
                  </p>
                  <Link
                    href={`/login?invitation_token=${encodeURIComponent(
                      token
                    )}&email=${encodeURIComponent(preview.email)}`}
                    className="inline-flex h-10 w-full items-center justify-center rounded-xl bg-[#315FBA] text-sm font-semibold text-white hover:bg-[#264C98]"
                  >
                    Sign In to Accept Invitation
                  </Link>
                </div>
              )}

              <p className="flex items-center justify-center gap-1.5 text-[11px] text-[#718096]">
                <ShieldCheck className="size-3.5 text-[#299B80]" />
                Single-use, email-bound invitation token
              </p>
            </div>
          )}
        </div>
      )}
    </AuthLayout>
  );
}
