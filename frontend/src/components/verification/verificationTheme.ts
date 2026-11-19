"use client";

import type { VerificationCategory, VerificationStatus } from "../../lib/verificationApi";

export const STATUS_META: Record<
  VerificationStatus,
  { label: string; badgeClass: string; dotClass: string; description: string }
> = {
  candidate: {
    label: "Candidate",
    badgeClass: "bg-slate-100 text-slate-700 border-slate-200",
    dotClass: "bg-slate-400",
    description: "Newly extracted finding awaiting review",
  },
  pending_review: {
    label: "Pending Review",
    badgeClass: "bg-blue-50 text-blue-700 border-blue-200",
    dotClass: "bg-blue-500",
    description: "Submitted or assigned for human review",
  },
  conflicted: {
    label: "Conflicted",
    badgeClass: "bg-rose-50 text-rose-700 border-rose-200",
    dotClass: "bg-rose-500",
    description: "Contradictory source evidence exists",
  },
  unresolved: {
    label: "Unresolved",
    badgeClass: "bg-amber-50 text-amber-800 border-amber-200",
    dotClass: "bg-amber-500",
    description: "Insufficient evidence to establish a conclusion",
  },
  verified: {
    label: "Verified",
    badgeClass: "bg-emerald-50 text-emerald-700 border-emerald-200",
    dotClass: "bg-emerald-500",
    description: "Human reviewer has confirmed the finding",
  },
  rejected: {
    label: "Rejected",
    badgeClass: "bg-zinc-100 text-zinc-600 border-zinc-300",
    dotClass: "bg-zinc-500",
    description: "Human reviewer has rejected the finding",
  },
};

export const CATEGORY_LABELS: Record<VerificationCategory, string> = {
  extracted_finding_verification: "Extracted Finding",
  conflicting_evidence: "Conflicting Evidence",
  missing_evidence: "Missing Evidence",
  outdated_information: "Outdated Information",
  uncertain_relationships: "Uncertain Relationship",
  duplicate_findings: "Duplicate Finding",
};

export function formatDomainLabel(domain: string): string {
  return domain
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function formatTimestamp(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
