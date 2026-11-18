"use client";

import React from "react";
import {
  FileText,
  AlertTriangle,
  GitCompare,
  CheckCircle2,
  Lock,
  ExternalLink,
  ChevronRight,
  FileCode,
  MessageSquare,
  ShieldAlert,
  Loader2,
} from "lucide-react";
import { SideBySideConflictCard } from "./SideBySideConflictCard";
import type { SupportingEvidencePanelProps, SupportingEvidenceItem } from "./types";

export const SupportingEvidencePanel: React.FC<SupportingEvidencePanelProps> = ({
  evidenceList,
  conflicts,
  issues,
  confidenceScore: _confidenceScore,
  loading,
  onViewChunk,
}) => {
  const getSourceIcon = (sourceType?: string | null) => {
    switch (sourceType?.toLowerCase()) {
      case "github":
      case "github_pull_request":
      case "github_commit":
        return <FileCode className="size-4 text-slate-700" />;
      case "jira":
      case "jira_issue":
        return <FileText className="size-4 text-blue-600" />;
      case "slack":
      case "slack_message":
        return <MessageSquare className="size-4 text-emerald-600" />;
      default:
        return <FileText className="size-4 text-slate-600" />;
    }
  };

  const getSeverityBadgeClass = (severity?: string) => {
    switch (severity?.toLowerCase()) {
      case "critical":
        return "bg-rose-100 text-rose-800 border-rose-300 font-bold";
      case "high":
        return "bg-amber-100 text-amber-800 border-amber-300 font-semibold";
      case "medium":
        return "bg-blue-100 text-blue-800 border-blue-300";
      case "low":
      default:
        return "bg-slate-100 text-slate-700 border-slate-300";
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-8 text-center text-slate-400">
        <Loader2 className="size-6 animate-spin text-teal-600 mb-2" />
        <p className="text-xs">Loading supporting citations and validation flags...</p>
      </div>
    );
  }

  const criticalIssuesCount = issues.filter((i) => i.severity === "critical").length;

  return (
    <div className="flex flex-col h-full bg-white overflow-y-auto p-5 space-y-5">
      {/* Panel Header */}
      <div className="flex items-center justify-between pb-2 border-b border-slate-200">
        <div>
          <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2">
            <FileText className="size-4 text-teal-700" />
            Supporting Evidence & Citations
          </h2>
          <p className="text-[11px] text-slate-500 mt-0.5">
            Primary sources, verbatim excerpt grounding, and validation issues
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <span className="px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 font-semibold">
            {evidenceList.length} {evidenceList.length === 1 ? "Citation" : "Citations"}
          </span>
          {conflicts.length > 0 && (
            <span className="px-2 py-0.5 rounded-full bg-purple-100 text-purple-800 font-bold flex items-center gap-1">
              <GitCompare className="size-3" />
              {conflicts.length}
            </span>
          )}
        </div>
      </div>

      {/* Critical Issues / Blocking Banner */}
      {criticalIssuesCount > 0 && (
        <div className="p-3 bg-rose-50 border-l-4 border-rose-500 rounded-r-xl space-y-1">
          <div className="flex items-center gap-1.5 text-xs font-bold text-rose-900">
            <ShieldAlert className="size-4 text-rose-600 shrink-0" />
            <span>Approval Blocked: {criticalIssuesCount} Critical Grounding Issues</span>
          </div>
          <p className="text-[11px] text-rose-700 leading-relaxed">
            This finding cannot be approved until critical grounding flaws (e.g. ungrounded claims or revoked source access) are resolved.
          </p>
        </div>
      )}

      {/* Section 1: Validation Issues */}
      <div className="space-y-2">
        <div className="flex items-center justify-between text-xs font-bold text-slate-700">
          <span className="flex items-center gap-1.5">
            <AlertTriangle className="size-3.5 text-amber-500" />
            Validation Issues ({issues.length})
          </span>
        </div>

        {issues.length === 0 ? (
          <div className="p-3 bg-emerald-50/70 border border-emerald-200 rounded-xl flex items-center gap-2 text-xs text-emerald-800">
            <CheckCircle2 className="size-4 text-emerald-600 shrink-0" />
            <span>No validation flaws detected. Claims align with primary source evidence.</span>
          </div>
        ) : (
          <div className="space-y-2">
            {issues.map((issue) => (
              <div
                key={issue.id}
                className="p-3 rounded-xl border border-slate-200 bg-slate-50/60 space-y-1.5"
              >
                <div className="flex items-center justify-between text-xs">
                  <div className="flex items-center gap-1.5">
                    <span
                      className={`px-1.5 py-0.2 rounded text-[10px] border uppercase ${getSeverityBadgeClass(
                        issue.severity
                      )}`}
                    >
                      {issue.severity}
                    </span>
                    <span className="font-semibold text-slate-900 capitalize">
                      {issue.issue_type.replace(/_/g, " ")}
                    </span>
                  </div>
                  <span className="text-[10px] text-slate-600 uppercase font-mono">
                    {issue.resolution_state}
                  </span>
                </div>
                <p className="text-xs text-slate-700 leading-snug">
                  {issue.description}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Section 2: Contradictions & Conflicts */}
      {conflicts.length > 0 && (
        <div className="space-y-2.5">
          <div className="flex items-center justify-between text-xs font-bold text-slate-700">
            <span className="flex items-center gap-1.5 text-purple-900">
              <GitCompare className="size-4 text-purple-600" />
              Contradictions & Cross-Source Conflicts ({conflicts.length})
            </span>
          </div>

          <div className="space-y-3">
            {conflicts.map((conflict) => (
              <SideBySideConflictCard key={conflict.id} conflict={conflict} />
            ))}
          </div>
        </div>
      )}

      {/* Section 3: Cited Primary Evidence Cards */}
      <div className="space-y-2.5">
        <div className="text-xs font-bold text-slate-700 flex items-center gap-1.5">
          <FileText className="size-3.5 text-slate-500" />
          Primary Source Citations ({evidenceList.length})
        </div>

        {evidenceList.length === 0 ? (
          <div className="p-6 bg-slate-50 border border-dashed border-slate-200 rounded-xl text-center space-y-1">
            <FileText className="size-8 text-slate-300 mx-auto" />
            <p className="text-xs font-semibold text-slate-700">
              No Direct Supporting Evidence Records Cited
            </p>
            <p className="text-[11px] text-slate-500 max-w-sm mx-auto">
              This candidate finding currently has no direct cited source records in the knowledge base.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {evidenceList.map((ev: SupportingEvidenceItem, idx: number) => {
              const loc = ev.source_location || {};
              const isRestricted = ev.restricted;

              return (
                <div
                  key={ev.evidence_id || idx}
                  className="p-3.5 rounded-xl border border-slate-200 bg-white hover:border-slate-300 transition shadow-2xs space-y-2.5"
                >
                  {/* Top row: Source type badge, title, location */}
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <div className="size-7 rounded-lg bg-slate-100 flex items-center justify-center shrink-0">
                        {getSourceIcon(ev.source_type)}
                      </div>
                      <div>
                        <h4 className="text-xs font-bold text-slate-900 line-clamp-1">
                          {ev.title || `Source Citation #${idx + 1}`}
                        </h4>
                        <div className="flex items-center gap-2 text-[10px] text-slate-500">
                          <span className="capitalize">{ev.source_type?.replace(/_/g, " ")}</span>
                          {ev.author && <span>by {ev.author}</span>}
                          {ev.source_url && (
                            <a
                              href={ev.source_url}
                              target="_blank"
                              rel="noreferrer"
                              className="text-teal-600 hover:text-teal-800 flex items-center gap-0.5"
                            >
                              <span>Link</span>
                              <ExternalLink className="size-2" />
                            </a>
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Grounding badge / Restricted badge */}
                    <div>
                      {isRestricted ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-100 text-rose-800 border border-rose-200">
                          <Lock className="size-2.5 text-rose-600" />
                          Restricted ACL
                        </span>
                      ) : ev.excerpt_verified ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-200">
                          <CheckCircle2 className="size-2.5 text-emerald-600" />
                          Grounding Verified
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-100 text-amber-800 border border-amber-200">
                          Ungrounded Claim
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Verbatim Excerpt Quote */}
                  {isRestricted ? (
                    <div className="p-2.5 bg-slate-50 rounded-lg text-xs text-slate-400 italic">
                      Source excerpt masked by project access control policies.
                    </div>
                  ) : ev.supporting_excerpt ? (
                    <blockquote className="p-2.5 bg-slate-50 border-l-2 border-teal-500 rounded-r-lg text-xs font-serif italic text-slate-800 leading-relaxed">
                      &ldquo;{ev.supporting_excerpt}&rdquo;
                    </blockquote>
                  ) : null}

                  {/* Bottom metadata chips & View Chunk drawer trigger */}
                  <div className="flex items-center justify-between pt-1 border-t border-slate-100 text-[11px] text-slate-500">
                    <div className="flex items-center gap-2 flex-wrap">
                      {loc.page_number !== undefined && (
                        <span className="px-1.5 py-0.2 rounded bg-slate-100 text-slate-700 text-[10px] font-mono">
                          Page {loc.page_number}
                        </span>
                      )}
                      {loc.chunk_index !== undefined && (
                        <span className="px-1.5 py-0.2 rounded bg-slate-100 text-slate-700 text-[10px] font-mono">
                          Chunk #{loc.chunk_index}
                        </span>
                      )}
                      {loc.commit_hash && (
                        <span className="px-1.5 py-0.2 rounded bg-slate-100 text-slate-700 text-[10px] font-mono">
                          Commit {String(loc.commit_hash).slice(0, 7)}
                        </span>
                      )}
                    </div>

                    <button
                      type="button"
                      onClick={() => onViewChunk(ev)}
                      className="inline-flex items-center gap-1 text-[11px] font-medium text-teal-700 hover:text-teal-900 transition cursor-pointer"
                    >
                      <span>View Full Context</span>
                      <ChevronRight className="size-3" />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
