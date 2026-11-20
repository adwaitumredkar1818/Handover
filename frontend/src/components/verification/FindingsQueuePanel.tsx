"use client";

import React from "react";
import { AlertTriangle, Clock, FileText } from "lucide-react";
import type { VerificationQueueItem } from "../../lib/verificationApi";
import {
  CATEGORY_LABELS,
  STATUS_META,
  formatDomainLabel,
  formatTimestamp,
} from "./verificationTheme";

interface FindingsQueuePanelProps {
  items: VerificationQueueItem[];
  total: number;
  selectedCaseId: string | null;
  onSelectCase: (caseId: string) => void;
  loading: boolean;
  canReview?: boolean;
}

export function FindingsQueuePanel({
  items,
  total,
  selectedCaseId,
  onSelectCase,
  loading,
  canReview = true,
}: FindingsQueuePanelProps) {
  return (
    <section
      aria-label="Findings queue"
      className="flex flex-col bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden min-h-0 md:max-h-full"
    >
      {/* Panel header (pinned above scrollable list) */}
      <div className="px-4 py-3 border-b border-slate-200 bg-slate-50/70 flex items-center justify-between shrink-0">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">Findings Queue</h2>
          <p className="text-xs text-slate-500">
            {total} {total === 1 ? "finding" : "findings"} matching filters
          </p>
        </div>
      </div>

      {/* Scrollable list (independent vertical scroll on md+; normal document flow on mobile) */}
      <div
        data-testid="findings-queue-scroll"
        className="divide-y divide-slate-100 md:flex-auto md:min-h-0 md:overflow-y-auto md:overscroll-contain scrollbar-thin"
      >
        {loading ? (
          <div className="p-4 space-y-3">
            {[1, 2, 3, 4, 5].map((n) => (
              <div key={n} className="h-28 rounded-lg bg-slate-100 animate-pulse" />
            ))}
          </div>
        ) : items.length === 0 ? (
          <div className="p-8 text-center">
            <p className="text-sm font-medium text-slate-700">No findings in this view</p>
            <p className="text-xs text-slate-500 mt-1">
              {canReview
                ? 'Adjust your filters or click "Sync & Run Checks" to load findings from Knowledge Intelligence.'
                : "Adjust your filters or ask a Project Manager or Reviewer to sync findings from Knowledge Intelligence."}
            </p>
          </div>
        ) : (
          items.map((item) => {
            const isSelected = item.id === selectedCaseId;
            const statusMeta = STATUS_META[item.case_status] ?? STATUS_META.candidate;

            const priorityColor =
              item.priority === "critical"
                ? "text-rose-700"
                : item.priority === "high"
                ? "text-orange-700"
                : item.priority === "medium"
                ? "text-amber-700"
                : "text-slate-500";

            return (
              <button
                key={item.id}
                type="button"
                onClick={() => onSelectCase(item.id)}
                className={`w-full text-left px-4 py-3.5 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${
                  isSelected
                    ? "bg-blue-50/80 border-l-[3px] border-l-blue-600"
                    : "hover:bg-slate-50/80 border-l-[3px] border-l-transparent"
                }`}
              >
                {/* Row 1: Domain + Status badge */}
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[11px] font-medium text-slate-500 uppercase tracking-wide truncate">
                    {formatDomainLabel(item.domain)}
                  </span>
                  <span
                    className={`shrink-0 inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium border ${statusMeta.badgeClass}`}
                  >
                    <span className={`w-1.5 h-1.5 rounded-full ${statusMeta.dotClass}`} />
                    {statusMeta.label}
                  </span>
                </div>

                {/* Row 2: Title */}
                <h3 className="text-sm font-semibold text-slate-900 mt-1 line-clamp-2 leading-snug">
                  {item.title || item.current_claim}
                </h3>

                {/* Row 3: Claim excerpt */}
                {item.title && (
                  <p className="text-xs text-slate-600 mt-1 line-clamp-2 leading-relaxed">
                    {item.current_claim}
                  </p>
                )}

                {/* Row 4: Category & Intelligence pills */}
                <div className="flex flex-wrap items-center gap-1 mt-2">
                  {item.verification_categories.slice(0, 2).map((cat) => (
                    <span
                      key={cat}
                      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-amber-50 text-amber-800 border border-amber-200 text-[10px] font-medium"
                    >
                      <AlertTriangle className="w-2.5 h-2.5" />
                      {CATEGORY_LABELS[cat] ?? cat}
                    </span>
                  ))}
                  {item.corroboration_level === "strong_cross_source" && (
                    <span className="px-1.5 py-0.5 rounded bg-purple-50 text-purple-700 border border-purple-200 text-[10px] font-medium">
                      Cross-Source
                    </span>
                  )}
                  {item.freshness_status === "outdated" && (
                    <span className="px-1.5 py-0.5 rounded bg-rose-50 text-rose-700 border border-rose-200 text-[10px] font-medium">
                      Outdated
                    </span>
                  )}
                  {item.recommendation_action === "ready_for_review" && (
                    <span className="px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200 text-[10px] font-medium">
                      Ready
                    </span>
                  )}
                </div>

                {/* Row 5: Metadata footer */}
                <div className="flex items-center justify-between text-[11px] text-slate-500 mt-2.5 pt-2 border-t border-slate-100 gap-1">
                  <span className="inline-flex items-center gap-1 shrink-0" title={`${item.evidence_count} attached evidence reference(s)`}>
                    <FileText className="w-3 h-3" />
                    {item.evidence_count}
                  </span>
                  {item.person_name && (
                    <span className="truncate max-w-[80px]" title={item.person_name}>
                      {item.person_name}
                    </span>
                  )}
                  <span
                    className={`font-semibold capitalize shrink-0 ${priorityColor}`}
                    title={item.priority_reason ?? `${item.priority} priority`}
                  >
                    {item.priority}
                  </span>
                  <span className="inline-flex items-center gap-1 shrink-0">
                    <Clock className="w-3 h-3" />
                    {formatTimestamp(item.updated_at).split(",")[0]}
                  </span>
                </div>
              </button>
            );
          })
        )}
      </div>
    </section>
  );
}
