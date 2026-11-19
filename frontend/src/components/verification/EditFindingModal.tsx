"use client";

import React, { useState, useEffect } from "react";
import { X, Edit3, AlertTriangle, Loader2 } from "lucide-react";
import type { EditFindingModalProps } from "./types";

export const EditFindingModal: React.FC<EditFindingModalProps> = ({
  isOpen,
  onClose,
  caseDetail,
  onSave,
  saving,
}) => {
  const [title, setTitle] = useState("");
  const [summary, setSummary] = useState("");
  const [reason, setReason] = useState("");
  const [errorMsg, setErrorMsg] = useState("");

  useEffect(() => {
    if (caseDetail) {
      const td = caseDetail.target_data || {};
      setTitle(td.title || "");
      setSummary(td.summary || "");
      setReason("Auditor correction and factual refinement");
      setErrorMsg("");
    }
  }, [caseDetail, isOpen]);

  if (!isOpen || !caseDetail) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) {
      setErrorMsg("Finding title cannot be empty.");
      return;
    }
    setErrorMsg("");
    await onSave({
      title: title.trim(),
      summary: summary.trim(),
      reason: reason.trim() || "Auditor correction",
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-xs p-4 animate-in fade-in-50">
      <div className="bg-white rounded-2xl shadow-2xl border border-slate-200 w-full max-w-lg overflow-hidden animate-in zoom-in-95 duration-150">
        {/* Modal Header */}
        <div className="flex items-center justify-between p-4 border-b border-slate-200 bg-slate-50">
          <div className="flex items-center gap-2">
            <div className="size-8 rounded-lg bg-teal-50 border border-teal-200 flex items-center justify-center text-teal-700">
              <Edit3 className="size-4" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-900">
                Edit & Correct Candidate Finding
              </h3>
              <p className="text-[11px] text-slate-500">
                Creates an audited modification snapshot under optimistic concurrency
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-200 transition cursor-pointer"
          >
            <X className="size-4" />
          </button>
        </div>

        {/* Modal Form */}
        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          {/* Finding Title Input */}
          <div className="space-y-1">
            <label className="text-xs font-bold text-slate-700">Finding Title</label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Descriptive title of the finding..."
              className="w-full text-xs p-2.5 bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-teal-500 focus:bg-white text-slate-900"
              required
            />
          </div>

          {/* Structured Summary Textarea */}
          <div className="space-y-1">
            <label className="text-xs font-bold text-slate-700">Structured Summary</label>
            <textarea
              value={summary}
              onChange={(e) => setSummary(e.target.value)}
              placeholder="Comprehensive summary describing the finding..."
              rows={4}
              className="w-full text-xs p-2.5 bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-teal-500 focus:bg-white text-slate-900 leading-relaxed"
            />
          </div>

          {/* Audit Reason Input */}
          <div className="space-y-1">
            <label className="text-xs font-bold text-slate-700">
              Audit Reason / Provenance Rationale
            </label>
            <input
              type="text"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Why is this finding being modified? (e.g. Updated deprecated port reference)"
              className="w-full text-xs p-2.5 bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-teal-500 focus:bg-white text-slate-900"
            />
          </div>

          {errorMsg && (
            <div className="p-2.5 bg-rose-50 border border-rose-200 rounded-lg text-xs text-rose-700 flex items-center gap-1.5">
              <AlertTriangle className="size-4 shrink-0 text-rose-600" />
              <span>{errorMsg}</span>
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100">
            <button
              type="button"
              onClick={onClose}
              disabled={saving}
              className="px-3.5 py-1.5 rounded-lg border border-slate-200 text-xs font-medium text-slate-600 hover:bg-slate-50 transition cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="px-4 py-1.5 rounded-lg bg-teal-700 hover:bg-teal-800 text-white text-xs font-semibold shadow-xs transition flex items-center gap-1.5 disabled:opacity-50 cursor-pointer"
            >
              {saving ? (
                <>
                  <Loader2 className="size-3.5 animate-spin" />
                  <span>Saving Changes...</span>
                </>
              ) : (
                <span>Save Finding Correction</span>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
