"use client";

import React, { useState } from "react";
import { X, HelpCircle, AlertTriangle, Loader2 } from "lucide-react";
import type { RequestContextModalProps } from "./types";

export const RequestContextModal: React.FC<RequestContextModalProps> = ({
  isOpen,
  onClose,
  caseDetail,
  members,
  onSubmit,
  submitting,
}) => {
  const [targetUserId, setTargetUserId] = useState(
    members[0]?.user_id || members[0]?.user?.id || members[0]?.id || ""
  );
  const [informationType, setInformationType] = useState("clarification");
  const [question, setQuestion] = useState("");
  const [errorMsg, setErrorMsg] = useState("");

  if (!isOpen || !caseDetail) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!targetUserId) {
      setErrorMsg("Please select a team member to request context from.");
      return;
    }
    if (question.trim().length < 5) {
      setErrorMsg("Clarification question must be at least 5 characters.");
      return;
    }
    setErrorMsg("");
    await onSubmit({
      targetUserId,
      question: question.trim(),
      informationType,
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-xs p-4 animate-in fade-in-50">
      <div className="bg-white rounded-2xl shadow-2xl border border-slate-200 w-full max-w-lg overflow-hidden animate-in zoom-in-95 duration-150">
        {/* Modal Header */}
        <div className="flex items-center justify-between p-4 border-b border-slate-200 bg-slate-50">
          <div className="flex items-center gap-2">
            <div className="size-8 rounded-lg bg-purple-50 border border-purple-200 flex items-center justify-center text-purple-700">
              <HelpCircle className="size-4" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-900">
                Request Context & Clarification
              </h3>
              <p className="text-[11px] text-slate-500">
                Dispatch an inquiry to the domain author or project teammate
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
          {/* Recipient Picker */}
          <div className="space-y-1">
            <label className="text-xs font-bold text-slate-700">
              Send Clarification Inquiry To
            </label>
            {members.length > 0 ? (
              <select
                value={targetUserId}
                onChange={(e) => setTargetUserId(e.target.value)}
                className="w-full text-xs p-2.5 bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500 focus:bg-white text-slate-900 cursor-pointer"
                required
              >
                {members.map((m) => {
                  const uId = m.user_id || m.user?.id || m.id;
                  const label = m.user?.name || m.user?.email || `Member (${uId.slice(0, 8)})`;
                  return (
                    <option key={uId} value={uId}>
                      {label}
                    </option>
                  );
                })}
              </select>
            ) : (
              <input
                type="text"
                value={targetUserId}
                onChange={(e) => setTargetUserId(e.target.value)}
                placeholder="Enter recipient User ID (UUID)..."
                className="w-full text-xs p-2.5 bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500 focus:bg-white text-slate-900"
                required
              />
            )}
          </div>

          {/* Information Type */}
          <div className="space-y-1">
            <label className="text-xs font-bold text-slate-700">Information Type</label>
            <select
              value={informationType}
              onChange={(e) => setInformationType(e.target.value)}
              className="w-full text-xs p-2.5 bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500 focus:bg-white text-slate-900 cursor-pointer"
            >
              <option value="clarification">Clarification of Claim</option>
              <option value="missing_evidence">Missing Primary Evidence</option>
              <option value="code_walkthrough">Code or Implementation Detail</option>
              <option value="architectural_rationale">Architectural / Design Decision Rationale</option>
            </select>
          </div>

          {/* Question Textarea */}
          <div className="space-y-1">
            <label className="text-xs font-bold text-slate-700">Clarification Question</label>
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="What specific ambiguity, context, or evidence is needed to verify this finding?"
              rows={4}
              className="w-full text-xs p-2.5 bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500 focus:bg-white text-slate-900 leading-relaxed"
              required
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
              disabled={submitting}
              className="px-3.5 py-1.5 rounded-lg border border-slate-200 text-xs font-medium text-slate-600 hover:bg-slate-50 transition cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="px-4 py-1.5 rounded-lg bg-purple-700 hover:bg-purple-800 text-white text-xs font-semibold shadow-xs transition flex items-center gap-1.5 disabled:opacity-50 cursor-pointer"
            >
              {submitting ? (
                <>
                  <Loader2 className="size-3.5 animate-spin" />
                  <span>Dispatching Inquiry...</span>
                </>
              ) : (
                <span>Send Context Request</span>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
