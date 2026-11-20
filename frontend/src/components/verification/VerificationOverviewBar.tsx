"use client";

import React from "react";
import { RefreshCw, Search, ShieldCheck } from "lucide-react";
import type { QueueFilters, VerificationSummary, VerificationStatus } from "../../lib/verificationApi";
import { CATEGORY_LABELS, STATUS_META, formatDomainLabel } from "./verificationTheme";
import type { ProjectMember } from "../../lib/types";

const STATUS_ORDER: VerificationStatus[] = [
  "candidate",
  "pending_review",
  "conflicted",
  "unresolved",
  "verified",
  "rejected",
];

interface VerificationOverviewBarProps {
  projectName: string | undefined;
  summary: VerificationSummary | null;
  filters: QueueFilters;
  onFiltersChange: (f: QueueFilters) => void;
  availableDomains: string[];
  availableSources: string[];
  availablePeople: string[];
  members: ProjectMember[];
  actionBusy: boolean;
  canReview?: boolean;
  onSync: () => void;
  statusNotice: string | null;
  errorMsg: string | null;
}

export function VerificationOverviewBar({
  projectName,
  summary,
  filters,
  onFiltersChange,
  availableDomains,
  availableSources,
  availablePeople,
  members,
  actionBusy,
  canReview = true,
  onSync,
  statusNotice,
  errorMsg,
}: VerificationOverviewBarProps) {
  const countFor = (st: VerificationStatus): number => {
    if (!summary) return 0;
    const m: Record<VerificationStatus, number> = {
      candidate: summary.candidate_count,
      pending_review: summary.pending_review_count,
      conflicted: summary.conflicted_count,
      unresolved: summary.unresolved_count,
      verified: summary.verified_count,
      rejected: summary.rejected_count,
    };
    return m[st] ?? 0;
  };

  return (
    <header className="shrink-0 bg-white border border-slate-200 rounded-xl shadow-sm p-4 space-y-3">
      {/* Title row */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-xs font-medium text-blue-700">
            <ShieldCheck className="w-4 h-4" />
            <span>{projectName ?? "Project Workspace"} · Quality Gate</span>
          </div>
          <h1 className="text-xl font-bold text-slate-900 mt-0.5">Verification Center</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Inspect extracted findings against original source records before they enter an approved handover.
          </p>
        </div>

        <div className="flex flex-col items-end gap-1">
          <button
            type="button"
            disabled={actionBusy || !canReview}
            title={
              canReview
                ? "Sync findings from Knowledge Intelligence and run automated checks"
                : "Requires Project Manager or Reviewer role to sync and run checks"
            }
            onClick={onSync}
            className="inline-flex items-center gap-2 px-3.5 py-2 rounded-lg bg-slate-900 text-white text-xs font-semibold hover:bg-slate-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${actionBusy ? "animate-spin" : ""}`} />
            Sync &amp; Run Checks
          </button>
          {!canReview && (
            <span className="text-[11px] text-slate-500">
              View-only · Reviewer or Project Manager role required to run checks
            </span>
          )}
        </div>
      </div>

      {/* 6 Status pills — clickable to filter */}
      <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
        {STATUS_ORDER.map((st) => {
          const meta = STATUS_META[st];
          const active = filters.status === st;
          return (
            <button
              key={st}
              type="button"
              onClick={() => onFiltersChange({ ...filters, status: active ? "all" : st })}
              className={`text-left p-2.5 rounded-lg border transition-all ${
                active
                  ? "border-blue-500 bg-blue-50 ring-1 ring-blue-500"
                  : "border-slate-200 bg-slate-50/60 hover:bg-slate-100/70"
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-medium text-slate-600">{meta.label}</span>
                <span className={`w-2 h-2 rounded-full ${meta.dotClass}`} />
              </div>
              <p className="text-lg font-bold text-slate-900 mt-0.5">{countFor(st)}</p>
            </button>
          );
        })}
      </div>

      {/* Search & Filters */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-7 gap-2">
        {/* Search */}
        <div className="relative lg:col-span-2">
          <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={filters.search ?? ""}
            onChange={(e) => onFiltersChange({ ...filters, search: e.target.value })}
            placeholder="Search findings or claims..."
            className="w-full pl-8 pr-3 py-1.5 text-xs rounded-lg border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        <select
          aria-label="Filter by status"
          value={filters.status ?? "all"}
          onChange={(e) => onFiltersChange({ ...filters, status: e.target.value })}
          className="text-xs px-2.5 py-1.5 rounded-lg border border-slate-300 bg-white"
        >
          <option value="all">All Statuses</option>
          {STATUS_ORDER.map((st) => (
            <option key={st} value={st}>{STATUS_META[st].label}</option>
          ))}
        </select>

        <select
          aria-label="Filter by domain"
          value={filters.domain ?? "all"}
          onChange={(e) => onFiltersChange({ ...filters, domain: e.target.value })}
          className="text-xs px-2.5 py-1.5 rounded-lg border border-slate-300 bg-white"
        >
          <option value="all">All Domains</option>
          {availableDomains.map((d) => (
            <option key={d} value={d}>{formatDomainLabel(d)}</option>
          ))}
        </select>

        <select
          aria-label="Filter by source"
          value={filters.source ?? "all"}
          onChange={(e) => onFiltersChange({ ...filters, source: e.target.value })}
          className="text-xs px-2.5 py-1.5 rounded-lg border border-slate-300 bg-white"
        >
          <option value="all">All Sources</option>
          {availableSources.map((s) => (
            <option key={s} value={s}>{s.replace(/_/g, " ").toUpperCase()}</option>
          ))}
        </select>

        <select
          aria-label="Filter by person"
          value={filters.person ?? "all"}
          onChange={(e) => onFiltersChange({ ...filters, person: e.target.value })}
          className="text-xs px-2.5 py-1.5 rounded-lg border border-slate-300 bg-white"
        >
          <option value="all">All People</option>
          {availablePeople.map((p) => (
            <option key={p} value={p}>{p}</option>
          ))}
        </select>

        <select
          aria-label="Filter by check category"
          value={filters.category ?? "all"}
          onChange={(e) => onFiltersChange({ ...filters, category: e.target.value })}
          className="text-xs px-2.5 py-1.5 rounded-lg border border-slate-300 bg-white"
        >
          <option value="all">All Check Categories</option>
          {Object.entries(CATEGORY_LABELS).map(([val, label]) => (
            <option key={val} value={val}>{label}</option>
          ))}
        </select>
      </div>

      {/* Secondary filter row */}
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
        <div className="flex flex-wrap items-center gap-3">
          <label className="inline-flex items-center gap-1.5">
            <span>Reviewer:</span>
            <select
              value={filters.reviewer_id ?? "all"}
              onChange={(e) => onFiltersChange({ ...filters, reviewer_id: e.target.value })}
              className="text-xs px-2 py-1 rounded border border-slate-300 bg-white text-slate-700"
            >
              <option value="all">Any Reviewer</option>
              {members.map((m) => (
                <option key={m.user_id} value={m.user_id}>{m.full_name || m.email}</option>
              ))}
            </select>
          </label>

          <label className="inline-flex items-center gap-1.5">
            <span>Sort:</span>
            <select
              value={filters.sort_by ?? "updated_at"}
              onChange={(e) => onFiltersChange({ ...filters, sort_by: e.target.value })}
              className="text-xs px-2 py-1 rounded border border-slate-300 bg-white text-slate-700"
            >
              <option value="updated_at">Last Updated</option>
              <option value="priority">Priority</option>
              <option value="status">Status</option>
              <option value="domain">Domain</option>
            </select>
          </label>
        </div>

        <div className="flex items-center gap-3">
          {statusNotice && <span className="text-emerald-700 font-medium">{statusNotice}</span>}
          {errorMsg && <span className="text-rose-700 font-medium">{errorMsg}</span>}
        </div>
      </div>
    </header>
  );
}
