"use client";

import React, { useState, useEffect, useCallback, useMemo } from "react";
import {
  GitCompare,
  AlertTriangle,
  Clock,
  CheckCircle2,
  XCircle,
  HelpCircle,
  FileText,
  GitCommit,
  GitBranch,
  Search,
  Filter,
  RefreshCw,
  ExternalLink,
  ShieldAlert,
  ShieldCheck,
  ArrowRight,
  Sparkles,
  Info,
  Check,
  Calendar,
  Layers,
  ChevronRight,
} from "lucide-react";
import Link from "next/link";
import { api } from "../../lib/api";
import { useLiveApp } from "../../context/LiveAppContext";

interface ConflictItem {
  id: string;
  case_id: string;
  conflict_type: string;
  claim_a_text: string;
  claim_a_source_evidence_id: string;
  claim_a_chunk_id?: string | null;
  claim_a_source_timestamp?: string | null;
  claim_a_source_title?: string | null;
  claim_a_source_type?: string | null;
  claim_b_text: string;
  claim_b_source_evidence_id: string;
  claim_b_chunk_id?: string | null;
  claim_b_source_timestamp?: string | null;
  claim_b_source_title?: string | null;
  claim_b_source_type?: string | null;
  explanation: string;
  temporal_comparison: string;
  resolution_state: string;
  resolution_notes?: string | null;
  resolved_by_user_id?: string | null;
  resolved_at?: string | null;
  created_at: string;
  target_id?: string | null;
  target_type?: string | null;
  target_title?: string | null;
  target_category?: string | null;
}

interface ConflictSummary {
  total_conflicts: number;
  unresolved_count: number;
  reconciled_count: number;
  superseded_count: number;
  dismissed_count: number;
  by_type: Record<string, number>;
}

export function ConflictsWorkspace() {
  const { activeProject } = useLiveApp();

  const [conflicts, setConflicts] = useState<ConflictItem[]>([]);
  const [summary, setSummary] = useState<ConflictSummary | null>(null);
  const [selectedConflictId, setSelectedConflictId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [detecting, setDetecting] = useState(false);
  const [resolving, setResolving] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [filterTab, setFilterTab] = useState<"all" | "unresolved" | "temporal" | "decision" | "status" | "resolved">("all");
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Adjudication form state
  const [resolutionChoice, setResolutionChoice] = useState<"superseded_b" | "reconciled" | "superseded_a" | "dismissed">("superseded_b");
  const [resolutionNotes, setResolutionNotes] = useState("");
  const [preferredClaim, setPreferredClaim] = useState<"a" | "b" | "both" | "dismissed">("b");

  const loadData = useCallback(async (projId: string) => {
    setLoading(true);
    setErrorMessage(null);
    try {
      const [sumRes, listRes] = await Promise.all([
        api.conflicts.getSummary(projId).catch(() => null),
        api.conflicts.list(projId, undefined, undefined, 100, 0).catch(() => null),
      ]);

      if (sumRes) setSummary(sumRes);
      if (listRes && listRes.items) {
        setConflicts(listRes.items);
        const firstItem = listRes.items[0];
        if (firstItem && !selectedConflictId) {
          setSelectedConflictId(firstItem.id);
        }
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load project conflicts.";
      setErrorMessage(msg);
    } finally {
      setLoading(false);
    }
  }, [selectedConflictId]);

  useEffect(() => {
    if (activeProject?.id) {
      loadData(activeProject.id);
    }
  }, [activeProject?.id, loadData]);

  const handleRunDetection = async () => {
    if (!activeProject?.id) return;
    setDetecting(true);
    setErrorMessage(null);
    setSuccessMessage(null);
    try {
      const res = await api.conflicts.detect(activeProject.id);
      setSuccessMessage(res.message || "Conflict detection executed successfully.");
      await loadData(activeProject.id);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to run conflict detection.";
      setErrorMessage(msg);
    } finally {
      setDetecting(false);
    }
  };

  const selectedConflict = useMemo(() => {
    return conflicts.find((c) => c.id === selectedConflictId) || conflicts[0] || null;
  }, [conflicts, selectedConflictId]);

  // Set default notes when switching conflict
  useEffect(() => {
    if (selectedConflict) {
      if (selectedConflict.resolution_state === "unresolved") {
        if (selectedConflict.temporal_comparison === "b_supersedes_a") {
          setResolutionChoice("superseded_b");
          setPreferredClaim("b");
          setResolutionNotes(`Verified newer repository implementation supersedes previous specification claim.`);
        } else {
          setResolutionChoice("reconciled");
          setPreferredClaim("both");
          setResolutionNotes(`Harmonized contextual scope across sources.`);
        }
      } else {
        setResolutionNotes(selectedConflict.resolution_notes || "");
      }
    }
  }, [selectedConflict]);

  const handleResolveConflict = async () => {
    if (!activeProject?.id || !selectedConflict) return;
    if (!resolutionNotes.trim()) {
      setErrorMessage("Please enter an adjudication rationale for the audit record.");
      return;
    }

    setResolving(true);
    setErrorMessage(null);
    setSuccessMessage(null);

    let state = "reconciled";
    if (resolutionChoice === "superseded_b" || resolutionChoice === "superseded_a") {
      state = "superseded";
    } else if (resolutionChoice === "dismissed") {
      state = "dismissed";
    }

    try {
      await api.conflicts.resolve(activeProject.id, selectedConflict.id, {
        resolution_state: state,
        resolution_notes: resolutionNotes.trim(),
        preferred_claim: preferredClaim,
      });

      setSuccessMessage(`Conflict adjudicated as ${state.toUpperCase()} successfully.`);
      await loadData(activeProject.id);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to resolve conflict.";
      setErrorMessage(msg);
    } finally {
      setResolving(false);
    }
  };

  // Filtered conflicts list
  const filteredConflicts = useMemo(() => {
    return conflicts.filter((c) => {
      // Tab filter
      if (filterTab === "unresolved" && c.resolution_state !== "unresolved") return false;
      if (filterTab === "resolved" && c.resolution_state === "unresolved") return false;
      if (filterTab === "temporal" && c.conflict_type !== "temporal_conflict") return false;
      if (filterTab === "decision" && c.conflict_type !== "decision_conflict") return false;
      if (filterTab === "status" && c.conflict_type !== "status_conflict") return false;

      // Text search
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const title = (c.target_title || "").toLowerCase();
        const expl = (c.explanation || "").toLowerCase();
        const cA = (c.claim_a_text || "").toLowerCase();
        const cB = (c.claim_b_text || "").toLowerCase();
        const sA = (c.claim_a_source_title || "").toLowerCase();
        const sB = (c.claim_b_source_title || "").toLowerCase();
        return (
          title.includes(q) ||
          expl.includes(q) ||
          cA.includes(q) ||
          cB.includes(q) ||
          sA.includes(q) ||
          sB.includes(q)
        );
      }
      return true;
    });
  }, [conflicts, filterTab, searchQuery]);

  const formatTimestamp = (ts?: string | null) => {
    if (!ts) return "Timestamp not recorded";
    try {
      const d = new Date(ts);
      return d.toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return ts;
    }
  };

  const getConflictTypeBadge = (type: string) => {
    switch (type) {
      case "decision_conflict":
        return <span className="px-2 py-0.5 rounded text-xs font-medium bg-purple-100 text-purple-800 border border-purple-200">Decision Divergence</span>;
      case "status_conflict":
        return <span className="px-2 py-0.5 rounded text-xs font-medium bg-orange-100 text-orange-800 border border-orange-200">Status Mismatch</span>;
      case "temporal_conflict":
        return <span className="px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800 border border-blue-200">Temporal Supersession</span>;
      case "technical_conflict":
        return <span className="px-2 py-0.5 rounded text-xs font-medium bg-rose-100 text-rose-800 border border-rose-200">Technical Contradiction</span>;
      case "ownership_conflict":
        return <span className="px-2 py-0.5 rounded text-xs font-medium bg-amber-100 text-amber-800 border border-amber-200">Ownership Dispute</span>;
      default:
        return <span className="px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-800 border border-slate-200">{type.replace("_", " ")}</span>;
    }
  };

  const getResolutionBadge = (state: string) => {
    switch (state) {
      case "unresolved":
        return <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-900 border border-amber-300 flex items-center gap-1"><AlertTriangle className="w-3 h-3 text-amber-600" /> Unresolved</span>;
      case "reconciled":
        return <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-900 border border-emerald-300 flex items-center gap-1"><CheckCircle2 className="w-3 h-3 text-emerald-600" /> Reconciled</span>;
      case "superseded":
        return <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-900 border border-blue-300 flex items-center gap-1"><Clock className="w-3 h-3 text-blue-600" /> Superseded</span>;
      case "dismissed":
        return <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-700 border border-slate-300 flex items-center gap-1"><XCircle className="w-3 h-3 text-slate-500" /> Dismissed</span>;
      default:
        return <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-800">{state}</span>;
    }
  };

  return (
    <div className="flex flex-col min-h-screen bg-slate-50 text-slate-900">
      {/* Top Header */}
      <div className="bg-white border-b border-slate-200 px-6 py-4">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-xs font-medium text-slate-500 mb-1">
              <span>The Sapiens</span>
              <span>&gt;</span>
              <span>Validation</span>
              <span>&gt;</span>
              <span className="text-blue-600 font-semibold">Conflicts & Contradictions</span>
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 flex items-center gap-2">
              <GitCompare className="w-6 h-6 text-blue-600" />
              Conflicts & Contradictions
            </h1>
            <p className="text-sm text-slate-500 mt-0.5">
              Automated detection and human adjudication of contradictory facts or conflicting timelines across disparate sources.
            </p>
          </div>

          <div className="flex items-center gap-2.5">
            <button
              onClick={handleRunDetection}
              disabled={detecting}
              className="inline-flex items-center gap-2 px-3.5 py-2 text-sm font-medium rounded-lg bg-blue-600 hover:bg-blue-700 text-white transition-colors disabled:opacity-50 shadow-sm"
            >
              <RefreshCw className={`w-4 h-4 ${detecting ? "animate-spin" : ""}`} />
              {detecting ? "Detecting Contradictions..." : "Run Conflict Detection"}
            </button>

            <Link
              href="/verification"
              className="inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 transition-colors"
            >
              <ShieldCheck className="w-4 h-4 text-emerald-600" />
              Verification Center
            </Link>

            <Link
              href="/evidence"
              className="inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 transition-colors"
            >
              Evidence Center
              <ChevronRight className="w-4 h-4 text-slate-400" />
            </Link>
          </div>
        </div>

        {/* Success / Error notification */}
        {successMessage && (
          <div className="mt-3 p-3 bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-lg text-sm flex items-center justify-between">
            <span className="flex items-center gap-2">
              <Check className="w-4 h-4 text-emerald-600" />
              {successMessage}
            </span>
            <button onClick={() => setSuccessMessage(null)} className="text-emerald-600 hover:text-emerald-900 text-xs">Dismiss</button>
          </div>
        )}
        {errorMessage && (
          <div className="mt-3 p-3 bg-rose-50 border border-rose-200 text-rose-800 rounded-lg text-sm flex items-center justify-between">
            <span className="flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-rose-600" />
              {errorMessage}
            </span>
            <button onClick={() => setErrorMessage(null)} className="text-rose-600 hover:text-rose-900 text-xs">Dismiss</button>
          </div>
        )}

        {/* Metrics Row */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-5">
          <div className="bg-slate-50 border border-slate-200 rounded-xl p-3.5 flex items-center justify-between">
            <div>
              <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">Total Contradictions</p>
              <p className="text-2xl font-bold text-slate-900 mt-0.5">{summary?.total_conflicts ?? conflicts.length}</p>
            </div>
            <div className="w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center text-blue-700">
              <GitCompare className="w-5 h-5" />
            </div>
          </div>

          <div className="bg-amber-50/70 border border-amber-200 rounded-xl p-3.5 flex items-center justify-between">
            <div>
              <p className="text-xs font-medium text-amber-800 uppercase tracking-wider">Unresolved (Requires Human)</p>
              <p className="text-2xl font-bold text-amber-900 mt-0.5">{summary?.unresolved_count ?? conflicts.filter(c => c.resolution_state === "unresolved").length}</p>
            </div>
            <div className="w-10 h-10 rounded-lg bg-amber-100 flex items-center justify-center text-amber-700">
              <AlertTriangle className="w-5 h-5" />
            </div>
          </div>

          <div className="bg-blue-50/70 border border-blue-200 rounded-xl p-3.5 flex items-center justify-between">
            <div>
              <p className="text-xs font-medium text-blue-800 uppercase tracking-wider">Superseded Updates</p>
              <p className="text-2xl font-bold text-blue-900 mt-0.5">{summary?.superseded_count ?? conflicts.filter(c => c.resolution_state === "superseded").length}</p>
            </div>
            <div className="w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center text-blue-700">
              <Clock className="w-5 h-5" />
            </div>
          </div>

          <div className="bg-emerald-50/70 border border-emerald-200 rounded-xl p-3.5 flex items-center justify-between">
            <div>
              <p className="text-xs font-medium text-emerald-800 uppercase tracking-wider">Reconciled / Harmonized</p>
              <p className="text-2xl font-bold text-emerald-900 mt-0.5">
                {(summary?.reconciled_count ?? 0) + (summary?.dismissed_count ?? 0)}
              </p>
            </div>
            <div className="w-10 h-10 rounded-lg bg-emerald-100 flex items-center justify-center text-emerald-700">
              <ShieldCheck className="w-5 h-5" />
            </div>
          </div>
        </div>
      </div>

      {/* Main Split-Screen Workspace */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Column: Conflict Queue & Filters */}
        <div className="w-full md:w-[420px] lg:w-[460px] border-r border-slate-200 bg-white flex flex-col shrink-0">
          {/* Search & Tabs */}
          <div className="p-3.5 border-b border-slate-200 space-y-2.5">
            <div className="relative">
              <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-400" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search conflicts by title, source, text..."
                className="w-full pl-9 pr-3 py-1.5 text-sm bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-blue-500 focus:bg-white"
              />
            </div>

            <div className="flex items-center gap-1 overflow-x-auto text-xs font-medium scrollbar-none pb-1">
              <button
                onClick={() => setFilterTab("all")}
                className={`px-2.5 py-1 rounded-md transition-colors ${
                  filterTab === "all"
                    ? "bg-slate-900 text-white"
                    : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                }`}
              >
                All ({conflicts.length})
              </button>
              <button
                onClick={() => setFilterTab("unresolved")}
                className={`px-2.5 py-1 rounded-md transition-colors ${
                  filterTab === "unresolved"
                    ? "bg-amber-600 text-white"
                    : "bg-amber-50 text-amber-800 border border-amber-200 hover:bg-amber-100"
                }`}
              >
                Unresolved ({summary?.unresolved_count ?? 0})
              </button>
              <button
                onClick={() => setFilterTab("temporal")}
                className={`px-2.5 py-1 rounded-md transition-colors ${
                  filterTab === "temporal"
                    ? "bg-blue-600 text-white"
                    : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                }`}
              >
                Temporal
              </button>
              <button
                onClick={() => setFilterTab("decision")}
                className={`px-2.5 py-1 rounded-md transition-colors ${
                  filterTab === "decision"
                    ? "bg-purple-600 text-white"
                    : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                }`}
              >
                Decisions
              </button>
              <button
                onClick={() => setFilterTab("status")}
                className={`px-2.5 py-1 rounded-md transition-colors ${
                  filterTab === "status"
                    ? "bg-orange-600 text-white"
                    : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                }`}
              >
                Status
              </button>
              <button
                onClick={() => setFilterTab("resolved")}
                className={`px-2.5 py-1 rounded-md transition-colors ${
                  filterTab === "resolved"
                    ? "bg-emerald-600 text-white"
                    : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                }`}
              >
                Resolved
              </button>
            </div>
          </div>

          {/* Conflict List */}
          <div className="flex-1 overflow-y-auto divide-y divide-slate-100">
            {loading ? (
              <div className="p-8 text-center text-slate-400">
                <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-slate-300" />
                <p className="text-sm">Loading project contradictions...</p>
              </div>
            ) : filteredConflicts.length === 0 ? (
              <div className="p-8 text-center text-slate-400 space-y-3">
                <CheckCircle2 className="w-10 h-10 mx-auto text-emerald-400" />
                <p className="text-sm font-medium text-slate-700">No contradictions in this view</p>
                <p className="text-xs text-slate-400 max-w-xs mx-auto">
                  Click &apos;Run Conflict Detection&apos; to scan all project knowledge items, documents, and code commits.
                </p>
              </div>
            ) : (
              filteredConflicts.map((c) => {
                const isSelected = c.id === selectedConflictId;
                return (
                  <button
                    key={c.id}
                    onClick={() => setSelectedConflictId(c.id)}
                    className={`w-full text-left p-3.5 transition-colors flex flex-col gap-1.5 ${
                      isSelected
                        ? "bg-blue-50/70 border-l-4 border-l-blue-600"
                        : "hover:bg-slate-50 border-l-4 border-l-transparent"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-1.5">
                        {getConflictTypeBadge(c.conflict_type)}
                      </div>
                      {getResolutionBadge(c.resolution_state)}
                    </div>

                    <h3 className="text-sm font-semibold text-slate-900 line-clamp-1">
                      {c.target_title || "Cross-Source Discrepancy"}
                    </h3>

                    <p className="text-xs text-slate-500 line-clamp-2">
                      {c.explanation}
                    </p>

                    <div className="flex items-center gap-2 mt-1 text-[11px] text-slate-400">
                      <span className="flex items-center gap-1">
                        <FileText className="w-3 h-3 text-slate-400" />
                        {c.claim_a_source_type || "Source A"}
                      </span>
                      <span>vs</span>
                      <span className="flex items-center gap-1 text-slate-600 font-medium">
                        <GitCommit className="w-3 h-3 text-blue-500" />
                        {c.claim_b_source_type || "Source B"}
                      </span>
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </div>

        {/* Right Area: Side-by-Side Adjudication Canvas */}
        <div className="flex-1 overflow-y-auto bg-slate-50 p-6">
          {!selectedConflict ? (
            <div className="h-full flex flex-col items-center justify-center text-center p-8 text-slate-400">
              <GitCompare className="w-12 h-12 text-slate-300 mb-3" />
              <h3 className="text-base font-semibold text-slate-700">Select a Conflict to Adjudicate</h3>
              <p className="text-sm max-w-sm text-slate-500 mt-1">
                Choose any item from the left queue to inspect verbatim source claims side-by-side and record human verification.
              </p>
            </div>
          ) : (
            <div className="max-w-5xl mx-auto space-y-6">
              {/* Conflict Header Card */}
              <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    {getConflictTypeBadge(selectedConflict.conflict_type)}
                    {selectedConflict.target_category && (
                      <span className="text-xs px-2 py-0.5 rounded bg-slate-100 text-slate-600 border border-slate-200">
                        Domain: {selectedConflict.target_category}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    {getResolutionBadge(selectedConflict.resolution_state)}
                    <span className="text-xs text-slate-400">
                      Detected: {formatTimestamp(selectedConflict.created_at)}
                    </span>
                  </div>
                </div>

                <h2 className="text-xl font-bold text-slate-900">
                  {selectedConflict.target_title || "Contradiction Record"}
                </h2>

                <div className="p-3.5 bg-blue-50/60 border border-blue-200 rounded-lg text-sm text-blue-950 flex items-start gap-2.5">
                  <Info className="w-5 h-5 text-blue-600 shrink-0 mt-0.5" />
                  <div>
                    <p className="font-semibold text-blue-900">Discrepancy Analysis</p>
                    <p className="text-blue-800 text-xs mt-0.5 leading-relaxed">
                      {selectedConflict.explanation}
                    </p>
                  </div>
                </div>

                {/* Temporal Precedence Insight */}
                <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg text-xs text-slate-600 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Clock className="w-4 h-4 text-amber-600" />
                    <span>
                      <strong className="text-slate-900">Temporal Ordering:</strong>{" "}
                      {selectedConflict.temporal_comparison === "b_supersedes_a"
                        ? "Claim B timestamp occurred after Claim A (indicates code or newer update may supersede prior doc)."
                        : selectedConflict.temporal_comparison === "a_supersedes_b"
                        ? "Claim A timestamp occurred after Claim B."
                        : "Claims are contemporaneous or timestamp ordering is ambiguous."}
                    </span>
                  </div>
                  <span className="text-slate-400 font-mono">
                    Mode: {selectedConflict.temporal_comparison}
                  </span>
                </div>
              </div>

              {/* Side-by-Side Comparison Panels */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                {/* Panel A */}
                <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm flex flex-col justify-between space-y-4">
                  <div className="space-y-3">
                    <div className="flex items-center justify-between pb-3 border-b border-slate-100">
                      <div className="flex items-center gap-2">
                        <div className="w-7 h-7 rounded bg-slate-100 flex items-center justify-center text-slate-700">
                          <FileText className="w-4 h-4" />
                        </div>
                        <div>
                          <p className="text-xs font-semibold uppercase text-slate-500 tracking-wider">Claim A (Baseline)</p>
                          <p className="text-xs font-medium text-slate-800 line-clamp-1">
                            {selectedConflict.claim_a_source_title || "Supporting Documentation"}
                          </p>
                        </div>
                      </div>
                      <span className="text-[11px] px-2 py-0.5 rounded bg-slate-100 text-slate-600">
                        {selectedConflict.claim_a_source_type || "document"}
                      </span>
                    </div>

                    <div className="text-xs text-slate-500 flex items-center gap-1.5">
                      <Calendar className="w-3.5 h-3.5 text-slate-400" />
                      <span>Timestamp: {formatTimestamp(selectedConflict.claim_a_source_timestamp)}</span>
                    </div>

                    {/* Excerpt */}
                    <div className="p-3.5 bg-slate-50 border border-slate-200 rounded-lg">
                      <p className="text-xs font-serif italic text-slate-800 leading-relaxed">
                        &quot;{selectedConflict.claim_a_text}&quot;
                      </p>
                    </div>

                    <div className="text-[11px] font-mono text-slate-400 truncate">
                      Evidence ID: {selectedConflict.claim_a_source_evidence_id}
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={() => {
                      setResolutionChoice("superseded_a");
                      setPreferredClaim("a");
                      setResolutionNotes(`Adjudicated: Claim A is accepted as the canonical truth; newer claim B is rejected.`);
                    }}
                    className={`w-full py-2 px-3 text-xs font-semibold rounded-lg border transition-colors flex items-center justify-center gap-1.5 ${
                      resolutionChoice === "superseded_a"
                        ? "bg-slate-900 text-white border-slate-900"
                        : "bg-white text-slate-700 border-slate-300 hover:bg-slate-50"
                    }`}
                  >
                    <Check className="w-3.5 h-3.5" />
                    Prefer Claim A as Canonical
                  </button>
                </div>

                {/* Panel B */}
                <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm flex flex-col justify-between space-y-4">
                  <div className="space-y-3">
                    <div className="flex items-center justify-between pb-3 border-b border-slate-100">
                      <div className="flex items-center gap-2">
                        <div className="w-7 h-7 rounded bg-blue-50 flex items-center justify-center text-blue-700">
                          <GitCommit className="w-4 h-4" />
                        </div>
                        <div>
                          <p className="text-xs font-semibold uppercase text-blue-600 tracking-wider">Claim B (Competitor / Update)</p>
                          <p className="text-xs font-medium text-slate-800 line-clamp-1">
                            {selectedConflict.claim_b_source_title || "Repository Activity"}
                          </p>
                        </div>
                      </div>
                      <span className="text-[11px] px-2 py-0.5 rounded bg-blue-100 text-blue-700">
                        {selectedConflict.claim_b_source_type || "github"}
                      </span>
                    </div>

                    <div className="text-xs text-slate-500 flex items-center gap-1.5">
                      <Calendar className="w-3.5 h-3.5 text-slate-400" />
                      <span>Timestamp: {formatTimestamp(selectedConflict.claim_b_source_timestamp)}</span>
                    </div>

                    {/* Excerpt */}
                    <div className="p-3.5 bg-blue-50/50 border border-blue-200 rounded-lg">
                      <p className="text-xs font-serif italic text-slate-800 leading-relaxed">
                        &quot;{selectedConflict.claim_b_text}&quot;
                      </p>
                    </div>

                    <div className="text-[11px] font-mono text-slate-400 truncate">
                      Evidence ID: {selectedConflict.claim_b_source_evidence_id}
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={() => {
                      setResolutionChoice("superseded_b");
                      setPreferredClaim("b");
                      setResolutionNotes(`Adjudicated: Newer Claim B supersedes prior specification Claim A.`);
                    }}
                    className={`w-full py-2 px-3 text-xs font-semibold rounded-lg border transition-colors flex items-center justify-center gap-1.5 ${
                      resolutionChoice === "superseded_b"
                        ? "bg-blue-600 text-white border-blue-600"
                        : "bg-white text-blue-700 border-blue-300 hover:bg-blue-50"
                    }`}
                  >
                    <Check className="w-3.5 h-3.5" />
                    Prefer Claim B as Superseding
                  </button>
                </div>
              </div>

              {/* Human Adjudication Center */}
              <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm space-y-4">
                <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                  <div className="flex items-center gap-2">
                    <ShieldAlert className="w-5 h-5 text-indigo-600" />
                    <h3 className="text-base font-bold text-slate-900">Human Adjudication Authority</h3>
                  </div>
                  <span className="text-xs text-slate-500 font-mono">
                    Status: {selectedConflict.resolution_state.toUpperCase()}
                  </span>
                </div>

                {selectedConflict.resolution_state !== "unresolved" ? (
                  /* Already Resolved Details */
                  <div className="p-4 bg-emerald-50 border border-emerald-200 rounded-xl space-y-3">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2 text-emerald-900 font-semibold text-sm">
                        <CheckCircle2 className="w-5 h-5 text-emerald-600" />
                        Conflict Adjudicated as {selectedConflict.resolution_state.toUpperCase()}
                      </div>
                      <span className="text-xs text-emerald-700">
                        Resolved: {formatTimestamp(selectedConflict.resolved_at)}
                      </span>
                    </div>

                    <div className="p-3 bg-white border border-emerald-200 rounded-lg text-xs text-slate-800">
                      <p className="font-semibold text-slate-700 mb-1">Adjudicator Rationale:</p>
                      <p>{selectedConflict.resolution_notes || "No additional notes provided."}</p>
                    </div>

                    <div className="pt-2 flex justify-end">
                      <button
                        onClick={() => {
                          setResolutionChoice("reconciled");
                          setResolutionNotes(selectedConflict.resolution_notes || "");
                        }}
                        className="text-xs font-medium text-blue-600 hover:underline"
                      >
                        Modify Adjudication Decision
                      </button>
                    </div>
                  </div>
                ) : null}

                {/* Adjudication Controls (Always active or available for re-adjudication) */}
                <div className="space-y-4 pt-1">
                  <div>
                    <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-2">
                      Select Adjudication Action
                    </label>
                    <div className="grid grid-cols-1 md:grid-cols-4 gap-2.5">
                      <button
                        type="button"
                        onClick={() => {
                          setResolutionChoice("superseded_b");
                          setPreferredClaim("b");
                        }}
                        className={`p-3 rounded-lg border text-left text-xs transition-colors flex flex-col gap-1 ${
                          resolutionChoice === "superseded_b"
                            ? "bg-blue-50 border-blue-500 ring-2 ring-blue-500/20 text-blue-900 font-semibold"
                            : "bg-slate-50 border-slate-200 text-slate-700 hover:bg-slate-100"
                        }`}
                      >
                        <span className="flex items-center gap-1 font-bold">
                          <Clock className="w-3.5 h-3.5 text-blue-600" />
                          Claim B Supersedes
                        </span>
                        <span className="text-[11px] text-slate-500 font-normal">
                          Accept Claim B as the newer canonical truth.
                        </span>
                      </button>

                      <button
                        type="button"
                        onClick={() => {
                          setResolutionChoice("reconciled");
                          setPreferredClaim("both");
                        }}
                        className={`p-3 rounded-lg border text-left text-xs transition-colors flex flex-col gap-1 ${
                          resolutionChoice === "reconciled"
                            ? "bg-emerald-50 border-emerald-500 ring-2 ring-emerald-500/20 text-emerald-900 font-semibold"
                            : "bg-slate-50 border-slate-200 text-slate-700 hover:bg-slate-100"
                        }`}
                      >
                        <span className="flex items-center gap-1 font-bold">
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                          Reconcile Both
                        </span>
                        <span className="text-[11px] text-slate-500 font-normal">
                          Harmonize both claims across different scopes.
                        </span>
                      </button>

                      <button
                        type="button"
                        onClick={() => {
                          setResolutionChoice("superseded_a");
                          setPreferredClaim("a");
                        }}
                        className={`p-3 rounded-lg border text-left text-xs transition-colors flex flex-col gap-1 ${
                          resolutionChoice === "superseded_a"
                            ? "bg-slate-200 border-slate-600 ring-2 ring-slate-500/20 text-slate-900 font-semibold"
                            : "bg-slate-50 border-slate-200 text-slate-700 hover:bg-slate-100"
                        }`}
                      >
                        <span className="flex items-center gap-1 font-bold">
                          <FileText className="w-3.5 h-3.5 text-slate-700" />
                          Claim A Canonical
                        </span>
                        <span className="text-[11px] text-slate-500 font-normal">
                          Retain Claim A as baseline and reject Claim B.
                        </span>
                      </button>

                      <button
                        type="button"
                        onClick={() => {
                          setResolutionChoice("dismissed");
                          setPreferredClaim("dismissed");
                        }}
                        className={`p-3 rounded-lg border text-left text-xs transition-colors flex flex-col gap-1 ${
                          resolutionChoice === "dismissed"
                            ? "bg-slate-200 border-slate-600 ring-2 ring-slate-500/20 text-slate-900 font-semibold"
                            : "bg-slate-50 border-slate-200 text-slate-700 hover:bg-slate-100"
                        }`}
                      >
                        <span className="flex items-center gap-1 font-bold">
                          <XCircle className="w-3.5 h-3.5 text-slate-500" />
                          Dismiss (Non-Conflict)
                        </span>
                        <span className="text-[11px] text-slate-500 font-normal">
                          Mark as false positive; semantically compatible.
                        </span>
                      </button>
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
                      Reviewer Rationale (Audit Record)
                    </label>
                    <textarea
                      rows={3}
                      value={resolutionNotes}
                      onChange={(e) => setResolutionNotes(e.target.value)}
                      placeholder="Explain the rationale for this adjudication decision for the immutable audit trail..."
                      className="w-full p-3 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-blue-500 focus:bg-white"
                    />
                  </div>

                  <div className="flex justify-end pt-1">
                    <button
                      type="button"
                      onClick={handleResolveConflict}
                      disabled={resolving || !resolutionNotes.trim()}
                      className="inline-flex items-center gap-2 px-5 py-2.5 text-sm font-semibold rounded-lg bg-slate-900 hover:bg-slate-800 text-white transition-colors disabled:opacity-50 shadow-sm"
                    >
                      <CheckCircle2 className={`w-4 h-4 ${resolving ? "animate-spin" : ""}`} />
                      {resolving ? "Submitting Adjudication..." : "Confirm Adjudication & Update Canonical State"}
                    </button>
                  </div>
                </div>
              </div>

              {/* Bottom Regulatory / Epistemic Banner */}
              <div className="p-4 bg-emerald-50/60 border border-emerald-200 rounded-xl flex items-center gap-3 text-xs text-emerald-900">
                <ShieldCheck className="w-5 h-5 text-emerald-600 shrink-0" />
                <p>
                  <strong>Epistemic Separation Guarantee:</strong> The platform flags cross-source contradictions automatically, but
                  <strong> the AI never independently decides truth or overrides human judgment</strong>. Final conflict resolution is
                  an auditable human decision recorded in the permanent PostgreSQL ledger.
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
