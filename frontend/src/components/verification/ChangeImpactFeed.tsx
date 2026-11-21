"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
  Activity,
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  ExternalLink,
  FileText,
  Filter,
  GitPullRequest,
  HelpCircle,
  Layers,
  MessageSquare,
  RefreshCw,
  Search,
  ShieldAlert,
} from "lucide-react";
import { SourceIcon } from "../brand/brand";
import { api } from "../../lib/api";
import { getCachedGraph, setCachedGraph } from "../../lib/graphCache";
import type { ChangeImpactItem } from "../../types/verification";

interface ChangeImpactFeedProps {
  projectId: string;
  onSelectFinding?: (caseId: string) => void;
}

export function ChangeImpactFeed({ projectId, onSelectFinding }: ChangeImpactFeedProps) {
  const [items, setItems] = useState<ChangeImpactItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [changeTypeFilter, setChangeTypeFilter] = useState<string>("all");
  const [natureFilter, setNatureFilter] = useState<string>("all");
  const [reverificationOnly, setReverificationOnly] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");

  const loadFeed = useCallback(async (isRefresh = false) => {
    const cacheKey = `verif_change_impact:${projectId}`;
    const cached = !isRefresh
      ? getCachedGraph<{ items: ChangeImpactItem[]; total: number }>(cacheKey)
      : null;
    if (cached) {
      setItems(cached.items || []);
      setTotal(cached.total || 0);
      setLoading(false);
    } else if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);

    try {
      const res = await api.verification.getChangeImpact(projectId, 100, 0);
      const nextItems = res.items || [];
      const nextTotal = res.total || 0;
      setCachedGraph(cacheKey, { items: nextItems, total: nextTotal });
      setItems(nextItems);
      setTotal(nextTotal);
    } catch (err) {
      if (!cached) {
        setError(err instanceof Error ? err.message : "Failed to load change impact feed.");
      }
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [projectId]);

  useEffect(() => {
    loadFeed();
  }, [loadFeed]);

  const filteredItems = items.filter((item) => {
    if (changeTypeFilter !== "all" && item.change_type !== changeTypeFilter) return false;
    if (natureFilter !== "all" && item.impact_nature !== natureFilter) return false;
    if (reverificationOnly && !item.reverification_triggered) return false;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const matchTitle = item.finding_title?.toLowerCase().includes(q);
      const matchClaim = item.current_claim?.toLowerCase().includes(q);
      const matchEv = item.evidence_title?.toLowerCase().includes(q);
      const matchDomain = item.domain?.toLowerCase().includes(q);
      if (!matchTitle && !matchClaim && !matchEv && !matchDomain) return false;
    }
    return true;
  });

  const getSourceIcon = (sourceType: string) => {
    const s = sourceType?.toLowerCase();
    if (s.includes("github")) return <SourceIcon type="github" size={16} />;
    if (s.includes("jira")) return <GitPullRequest className="w-4 h-4 text-blue-600" />;
    if (s.includes("slack")) return <MessageSquare className="w-4 h-4 text-emerald-600" />;
    return <FileText className="w-4 h-4 text-amber-600" />;
  };

  const getStatusBadge = (status: string) => {
    const s = status?.toLowerCase();
    if (s === "verified") {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-emerald-100 text-emerald-800">
          <CheckCircle2 className="w-3 h-3" /> Verified
        </span>
      );
    }
    if (s === "conflicted") {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-rose-100 text-rose-800">
          <ShieldAlert className="w-3 h-3" /> Conflicted
        </span>
      );
    }
    if (s === "candidate") {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800">
          <Layers className="w-3 h-3" /> Candidate
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-700 capitalize">
        <HelpCircle className="w-3 h-3" /> {status}
      </span>
    );
  };

  return (
    <div className="flex flex-col h-full bg-[#F6F8FC] border border-slate-200 rounded-xl overflow-hidden">
      {/* Header */}
      <div className="p-4 bg-white border-b border-slate-200 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Activity className="w-5 h-5 text-indigo-600" />
            <h2 className="text-base font-semibold text-slate-900">
              Continuous Change Impact Feed
            </h2>
            <span className="px-2 py-0.5 text-xs font-medium bg-indigo-50 text-indigo-700 border border-indigo-200 rounded-full">
              {total} Event{total !== 1 ? "s" : ""}
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Real-time cross-source change analysis and automatic knowledge re-verification alerts.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => loadFeed(true)}
            disabled={loading || refreshing}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-700 bg-white border border-slate-300 rounded-md hover:bg-slate-50 transition cursor-pointer disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Filter Toolbar */}
      <div className="p-3 bg-slate-50 border-b border-slate-200 flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-slate-400" />
          <input
            type="text"
            placeholder="Search affected findings, claims, or sources..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 text-xs bg-white text-slate-900 placeholder:text-slate-400 border border-slate-300 rounded-md focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Filter className="w-3.5 h-3.5 text-slate-400" />
          <select
            value={changeTypeFilter}
            onChange={(e) => setChangeTypeFilter(e.target.value)}
            className="px-2.5 py-1.5 text-xs bg-white border border-slate-300 rounded-md text-slate-700"
          >
            <option value="all">All Changes</option>
            <option value="modified">Modified</option>
            <option value="created">Created</option>
            <option value="deleted">Deleted</option>
          </select>

          <select
            value={natureFilter}
            onChange={(e) => setNatureFilter(e.target.value)}
            className="px-2.5 py-1.5 text-xs bg-white border border-slate-300 rounded-md text-slate-700"
          >
            <option value="all">All Impact Natures</option>
            <option value="confirmed">Confirmed Direct Link</option>
            <option value="inferred">Inferred Correlation</option>
          </select>

          <label className="inline-flex items-center gap-1.5 text-xs text-slate-700 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={reverificationOnly}
              onChange={(e) => setReverificationOnly(e.target.checked)}
              className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500 w-3.5 h-3.5"
            />
            Re-verification Required Only
          </label>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {loading && !refreshing && (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="p-4 bg-white rounded-lg border border-slate-200 animate-pulse space-y-2">
                <div className="h-4 bg-slate-200 rounded w-1/4"></div>
                <div className="h-3 bg-slate-200 rounded w-3/4"></div>
                <div className="h-3 bg-slate-200 rounded w-1/2"></div>
              </div>
            ))}
          </div>
        )}

        {error && (
          <div className="p-4 rounded-lg bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-center justify-between">
            <div className="flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
              <span>{error}</span>
            </div>
            <button
              onClick={() => loadFeed()}
              className="underline font-medium hover:text-rose-900 ml-4 cursor-pointer"
            >
              Retry
            </button>
          </div>
        )}

        {!loading && !error && filteredItems.length === 0 && (
          <div className="text-center py-12 px-4 bg-white rounded-lg border border-slate-200">
            <Activity className="w-10 h-10 text-slate-300 mx-auto mb-3" />
            <h3 className="text-sm font-medium text-slate-800">
              No change impact events recorded
            </h3>
            <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
              When connected repositories, Jira boards, or documents are synchronized and updated, continuous intelligence automatically tracks their impact on reconstructed project knowledge here.
            </p>
          </div>
        )}

        {!loading &&
          filteredItems.map((event, idx) => (
            <div
              key={`${event.case_id}-${event.evidence_id || idx}`}
              className="p-4 bg-white rounded-lg border border-slate-200 shadow-xs hover:border-indigo-300 transition"
            >
              {/* Event Top Bar */}
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-2.5">
                <div className="flex items-center gap-2">
                  <div className="p-1 rounded bg-slate-100">
                    {getSourceIcon(event.evidence_source_type)}
                  </div>
                  <span className="text-xs font-semibold text-slate-900">
                    {event.evidence_title}
                  </span>
                  <span className="px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider rounded bg-slate-100 text-slate-600">
                    {event.evidence_source_type}
                  </span>
                  <span
                    className={`px-1.5 py-0.5 text-[10px] font-medium rounded uppercase tracking-wider ${
                      event.change_type === "created"
                        ? "bg-emerald-100 text-emerald-800"
                        : event.change_type === "deleted"
                        ? "bg-rose-100 text-rose-800"
                        : "bg-blue-100 text-blue-800"
                    }`}
                  >
                    {event.change_type}
                  </span>
                </div>

                <div className="flex items-center gap-2">
                  <span
                    className={`px-2 py-0.5 text-[10px] font-medium rounded-full ${
                      event.impact_nature === "confirmed"
                        ? "bg-indigo-50 text-indigo-700 border border-indigo-200"
                        : "bg-slate-100 text-slate-600 border border-dashed border-slate-300"
                    }`}
                  >
                    {event.impact_nature === "confirmed" ? "Direct Evidence Link" : "Inferred Topical Impact"}
                  </span>
                  {event.timestamp && (
                    <span className="text-[11px] text-slate-400">
                      {new Date(event.timestamp).toLocaleString()}
                    </span>
                  )}
                </div>
              </div>

              {/* Finding Title & Domain */}
              <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h4 className="text-sm font-semibold text-slate-900">
                    {event.finding_title}
                  </h4>
                  <p className="text-xs text-slate-500 capitalize">
                    Domain: <span className="font-medium text-slate-700">{event.domain?.replace(/_/g, " ")}</span>
                  </p>
                </div>
                <div className="flex items-center gap-1.5">
                  {getStatusBadge(event.case_status)}
                  <span className="px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider rounded bg-slate-100 text-slate-600">
                    {event.priority} Priority
                  </span>
                </div>
              </div>

              {/* Current Claim Excerpt */}
              <div className="mt-2 text-xs text-slate-600 bg-slate-50 p-2.5 rounded border border-slate-200/70">
                <span className="font-medium text-slate-500">Recorded Claim: </span>
                {event.current_claim}
              </div>

              {/* Re-verification Trigger Banner */}
              {event.reverification_triggered && (
                <div className="mt-2.5 p-2.5 rounded bg-amber-50 border border-amber-200 text-xs text-amber-900 flex items-start gap-2">
                  <ShieldAlert className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
                  <div>
                    <span className="font-semibold">Re-verification Flagged: </span>
                    {event.reverification_reason || "Supporting source record was modified. Reviewer validation recommended."}
                  </div>
                </div>
              )}

              {/* Impact Explanation */}
              <div className="mt-2.5 text-xs text-slate-700">
                <span className="font-medium text-slate-500">Impact Assessment: </span>
                {event.impact_summary}
              </div>

              {/* Footer Actions */}
              <div className="mt-3 pt-2.5 border-t border-slate-100 flex items-center justify-between text-xs">
                <div>
                  {event.evidence_url && (
                    <a
                      href={event.evidence_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-slate-500 hover:text-indigo-600 transition"
                    >
                      <ExternalLink className="w-3.5 h-3.5" />
                      View External Source
                    </a>
                  )}
                </div>

                {onSelectFinding && (
                  <button
                    onClick={() => onSelectFinding(event.case_id)}
                    className="inline-flex items-center gap-1 font-medium text-indigo-600 hover:underline cursor-pointer"
                  >
                    Inspect in Verification Queue
                    <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            </div>
          ))}
      </div>
    </div>
  );
}
