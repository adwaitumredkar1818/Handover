"use client";

import React from "react";
import {
  Clock,
  ExternalLink,
  History,
  Lock,
  MessageSquarePlus,
  User as UserIcon,
  X,
} from "lucide-react";
import type {
  EvidenceReferenceDetail,
  VerificationCaseDetail,
} from "../../lib/verificationApi";
import { formatTimestamp } from "./verificationTheme";

interface EvidenceSourceDrawerProps {
  evidence: EvidenceReferenceDetail | null;
  caseDetail: VerificationCaseDetail | null;
  onClose: () => void;
}

type DrawerTab = "source" | "history" | "audit";

export function EvidenceSourceDrawer({
  evidence,
  caseDetail,
  onClose,
}: EvidenceSourceDrawerProps) {
  const [activeTab, setActiveTab] = React.useState<DrawerTab>("source");

  // Reset tab when evidence changes
  React.useEffect(() => {
    setActiveTab("source");
  }, [evidence?.id]);

  if (!evidence) return null;

  const tabs: { id: DrawerTab; label: string }[] = [
    { id: "source", label: "Source Detail" },
    { id: "history", label: "Version History" },
    { id: "audit", label: "Review Audit" },
  ];

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/20 z-30"
        aria-hidden="true"
        onClick={onClose}
      />

      {/* Drawer panel — slides in from the right */}
      <aside
        aria-label="Evidence source detail"
        className="fixed inset-y-0 right-0 z-40 w-full max-w-sm sm:max-w-md bg-white border-l border-slate-200 shadow-2xl flex flex-col"
      >
        {/* Drawer header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-200 bg-slate-50/80 shrink-0">
          <div>
            <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-200 text-[11px] font-semibold uppercase">
              {evidence.source_name}
            </span>
            <h2 className="text-sm font-semibold text-slate-900 mt-1 line-clamp-2">
              {evidence.original_title}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close evidence drawer"
            className="ml-4 shrink-0 p-1.5 rounded-lg hover:bg-slate-200 text-slate-500 hover:text-slate-900 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Tab navigation */}
        <div className="flex border-b border-slate-200 shrink-0">
          {tabs.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setActiveTab(t.id)}
              className={`flex-1 py-2.5 text-xs font-medium transition-colors ${
                activeTab === t.id
                  ? "text-blue-700 border-b-2 border-blue-600 bg-blue-50/40"
                  : "text-slate-600 hover:text-slate-900 hover:bg-slate-50"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {/* ── Source Detail ── */}
          {activeTab === "source" && (
            <>
              {/* Meta grid */}
              <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-xs">
                <div>
                  <dt className="text-slate-500 font-medium">Source provider</dt>
                  <dd className="text-slate-900 mt-0.5 uppercase font-semibold">
                    {evidence.source_provider}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500 font-medium">Relationship</dt>
                  <dd className="text-slate-900 mt-0.5 capitalize">
                    {evidence.relationship_to_finding.replace(/_/g, " ")}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500 font-medium flex items-center gap-1">
                    <UserIcon className="w-3 h-3" />
                    Author
                  </dt>
                  <dd className="text-slate-900 mt-0.5">{evidence.author ?? "Unknown"}</dd>
                </div>
                <div>
                  <dt className="text-slate-500 font-medium flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    Timestamp
                  </dt>
                  <dd className="text-slate-900 mt-0.5">{formatTimestamp(evidence.timestamp)}</dd>
                </div>
                {evidence.location_label && (
                  <div className="col-span-2">
                    <dt className="text-slate-500 font-medium">Record / Location</dt>
                    <dd className="text-slate-900 mt-0.5 font-mono text-[11px]">
                      {evidence.location_label}
                    </dd>
                  </div>
                )}
                <div className="col-span-2">
                  <dt className="text-slate-500 font-medium">ACL scope</dt>
                  <dd className="text-slate-900 mt-0.5 capitalize">{evidence.acl_scope}</dd>
                </div>
              </dl>

              {/* Source URL */}
              {evidence.original_source_url && (
                <a
                  href={evidence.original_source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 text-xs font-medium text-blue-600 hover:text-blue-800 hover:underline"
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                  Open original source
                </a>
              )}

              {/* Full excerpt */}
              {evidence.excerpt && (
                <div>
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-600 mb-2">
                    Excerpt
                  </h3>
                  <blockquote className="text-xs text-slate-700 bg-slate-50 border-l-2 border-slate-300 pl-3 py-3 rounded-r whitespace-pre-wrap leading-relaxed">
                    {evidence.excerpt}
                  </blockquote>
                </div>
              )}

              {/* ACL notice */}
              {evidence.acl_scope !== "public" && (
                <p className="inline-flex items-center gap-1.5 text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded px-2.5 py-1.5">
                  <Lock className="w-3.5 h-3.5" />
                  This source is restricted by delegated source ACL.
                </p>
              )}
            </>
          )}

          {/* ── Version History ── */}
          {activeTab === "history" && (
            <div className="space-y-3">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-600 flex items-center gap-1.5">
                <History className="w-3.5 h-3.5" />
                Claim Revisions
              </h3>
              {!caseDetail || caseDetail.revisions.length === 0 ? (
                <p className="text-xs text-slate-500">No revisions recorded yet.</p>
              ) : (
                <div className="space-y-2.5">
                  {caseDetail.revisions.map((rev) => (
                    <div
                      key={rev.id}
                      className="p-3.5 rounded-lg border border-slate-200 bg-slate-50/60 space-y-1.5"
                    >
                      <div className="flex items-center justify-between text-[11px]">
                        <span className="font-semibold text-slate-700">
                          v{rev.revision_number}
                          {rev.is_ai_original && (
                            <span className="ml-2 text-amber-700 font-normal">AI original</span>
                          )}
                        </span>
                        <span className="text-slate-500">{formatTimestamp(rev.created_at)}</span>
                      </div>
                      <p className="text-xs text-slate-800 leading-relaxed whitespace-pre-wrap">
                        {rev.claim_text}
                      </p>
                      {rev.edited_by_name && (
                        <p className="text-[11px] text-slate-500">
                          Edited by {rev.edited_by_name}
                          {rev.edit_reason && ` · ${rev.edit_reason}`}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* ── Review Audit ── */}
          {activeTab === "audit" && (
            <div className="space-y-3">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-600 flex items-center gap-1.5">
                <MessageSquarePlus className="w-3.5 h-3.5" />
                Reviewer Decisions
              </h3>
              {!caseDetail || caseDetail.review_events.length === 0 ? (
                <p className="text-xs text-slate-500">No human review decisions recorded yet.</p>
              ) : (
                <div className="space-y-2.5">
                  {caseDetail.review_events.map((evt) => (
                    <div
                      key={evt.id}
                      className="p-3.5 rounded-lg border border-slate-200 bg-slate-50/60 space-y-1.5"
                    >
                      <div className="flex items-center justify-between text-[11px]">
                        <span className="font-semibold text-slate-800 capitalize">
                          {evt.action.replace(/_/g, " ")}
                        </span>
                        <span className="text-slate-500">{formatTimestamp(evt.created_at)}</span>
                      </div>
                      <p className="text-[11px] text-slate-500">
                        {evt.previous_status} → {evt.new_status} · v{evt.case_version}
                      </p>
                      <p className="text-[11px] text-slate-600">
                        Reviewer: {evt.reviewer_name ?? evt.reviewer_user_id}
                      </p>
                      {evt.decision_reason && (
                        <p className="text-xs text-slate-700">Reason: {evt.decision_reason}</p>
                      )}
                      {evt.review_notes && (
                        <p className="text-xs text-slate-600 italic">{evt.review_notes}</p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </aside>
    </>
  );
}
