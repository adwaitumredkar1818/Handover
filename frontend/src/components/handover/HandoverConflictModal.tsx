"use client";

import React, { useState } from "react";
import {
  GitCompare,
  ShieldAlert,
  CheckCircle2,
  ExternalLink,
  Clock,
  ArrowRight,
  FileText,
  AlertTriangle,
} from "lucide-react";
import { Badge, Button, Modal, cn } from "../figma-ui/index";
import type { HandoverSectionConflictItem } from "../../lib/types";
import { api } from "../../lib/api";

interface HandoverConflictModalProps {
  isOpen: boolean;
  onClose: () => void;
  projectId: string;
  conflicts: HandoverSectionConflictItem[];
  onOpenConflictsWorkspace: () => void;
  onDataChanged: () => void;
  canReview?: boolean;
}

export function HandoverConflictModal({
  isOpen,
  onClose,
  projectId,
  conflicts,
  onOpenConflictsWorkspace,
  onDataChanged,
  canReview = true,
}: HandoverConflictModalProps) {
  const [selectedConflictId, setSelectedConflictId] = useState<string | null>(null);
  const [resolutionChoice, setResolutionChoice] = useState<"side_a" | "side_b" | "custom">("side_a");
  const [resolutionNotes, setResolutionNotes] = useState<string>("");
  const [authoritativeText, setAuthoritativeText] = useState<string>("");
  const [isResolving, setIsResolving] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const activeConflict =
    conflicts.find((c) => c.id === selectedConflictId) || conflicts[0] || null;

  const handleResolve = async () => {
    if (!activeConflict || isResolving) return;
    if (!resolutionNotes.trim()) {
      setErrorMsg("Please provide an adjudication note explaining the resolution decision.");
      return;
    }
    setIsResolving(true);
    setErrorMsg(null);
    try {
      const chosenText =
        resolutionChoice === "side_a"
          ? activeConflict.claim_a_text
          : resolutionChoice === "side_b"
          ? activeConflict.claim_b_text
          : authoritativeText.trim();

      await api.conflicts.resolve(projectId, activeConflict.id, {
        resolution_state: "resolved",
        resolution_strategy:
          resolutionChoice === "side_a"
            ? "side_a_authoritative"
            : resolutionChoice === "side_b"
            ? "side_b_authoritative"
            : "reconciled",
        authoritative_claim_text: chosenText,
        resolution_notes: resolutionNotes.trim(),
      });

      onDataChanged();
      setSelectedConflictId(null);
      setResolutionNotes("");
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to resolve conflict.");
    } finally {
      setIsResolving(false);
    }
  };

  if (!isOpen) return null;

  return (
    <Modal
      open={isOpen}
      onClose={onClose}
      title="Investigate Contradictions & Conflicts"
      subtitle="Conflicting claims identified across sources. Human adjudication determines authoritative truth for handover packages."
      footer={
        <div className="flex flex-wrap items-center justify-between gap-2 w-full">
          <Button
            variant="ghost"
            icon={ExternalLink}
            onClick={onOpenConflictsWorkspace}
            className="text-xs text-muted hover:text-navy"
          >
            Open Conflicts Workspace
          </Button>
          <Button variant="secondary" onClick={onClose}>
            Close
          </Button>
        </div>
      }
    >
      <div className="space-y-4 py-2">
        {errorMsg && (
          <div className="rounded-lg bg-red-50 p-2.5 text-xs text-red-800 border border-red-200">
            {errorMsg}
          </div>
        )}

        {conflicts.length === 0 ? (
          <div className="p-8 text-center text-muted">
            <CheckCircle2 className="mx-auto size-8 text-ok mb-2" />
            <p className="text-sm font-semibold text-navy">No unresolved conflicts</p>
            <p className="text-xs text-muted mt-1">
              All connected sources are consistent or previously reconciled.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {/* Multiple conflicts tabs if > 1 */}
            {conflicts.length > 1 && (
              <div className="flex items-center gap-1.5 overflow-x-auto pb-1 border-b border-line">
                {conflicts.map((c, i) => (
                  <button
                    key={c.id}
                    type="button"
                    onClick={() => setSelectedConflictId(c.id)}
                    className={cn(
                      "px-3 py-1 rounded-md text-xs font-semibold whitespace-nowrap transition",
                      (activeConflict?.id === c.id)
                        ? "bg-red-50 text-red-800 border border-red-200"
                        : "text-slate-600 hover:bg-slate-100"
                    )}
                  >
                    Conflict {i + 1}: {(c.conflict_type || "Contradiction").replace(/_/g, " ")}
                  </button>
                ))}
              </div>
            )}

            {activeConflict && (
              <div className="space-y-3">
                {/* Conflict Explanation Header */}
                <div className="rounded-xl bg-red-50/50 p-3.5 border border-red-200/80 space-y-1">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-bold uppercase tracking-wider text-red-800">
                      {(activeConflict.conflict_type || "Factual Contradiction").replace(/_/g, " ")}
                    </span>
                    <Badge tone="red">{activeConflict.resolution_state}</Badge>
                  </div>
                  <p className="text-sm font-medium text-navy">{activeConflict.explanation}</p>
                </div>

                {/* Side-by-Side Comparison */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {/* Side A */}
                  <div className="rounded-xl border border-line bg-slate-50/70 p-3.5 space-y-2 flex flex-col justify-between">
                    <div>
                      <div className="flex items-center justify-between text-xs pb-1 border-b border-line/60">
                        <span className="font-bold text-muted uppercase text-[10.5px]">Claim A</span>
                        <span className="font-semibold text-navy truncate max-w-[180px]">
                          {activeConflict.side_a_source_title || "Source A"}
                        </span>
                      </div>
                      <p className="text-xs text-slate-800 mt-2 leading-relaxed font-medium">
                        "{activeConflict.claim_a_text}"
                      </p>
                    </div>
                    {canReview && activeConflict.resolution_state === "unresolved" && (
                      <label className="flex items-center gap-2 pt-2 border-t border-line/40 text-xs text-slate-700 cursor-pointer">
                        <input
                          type="radio"
                          name="conflict_choice"
                          checked={resolutionChoice === "side_a"}
                          onChange={() => setResolutionChoice("side_a")}
                        />
                        <span>Accept Claim A as Authoritative</span>
                      </label>
                    )}
                  </div>

                  {/* Side B */}
                  <div className="rounded-xl border border-line bg-slate-50/70 p-3.5 space-y-2 flex flex-col justify-between">
                    <div>
                      <div className="flex items-center justify-between text-xs pb-1 border-b border-line/60">
                        <span className="font-bold text-muted uppercase text-[10.5px]">Claim B</span>
                        <span className="font-semibold text-navy truncate max-w-[180px]">
                          {activeConflict.side_b_source_title || "Source B"}
                        </span>
                      </div>
                      <p className="text-xs text-slate-800 mt-2 leading-relaxed font-medium">
                        "{activeConflict.claim_b_text}"
                      </p>
                    </div>
                    {canReview && activeConflict.resolution_state === "unresolved" && (
                      <label className="flex items-center gap-2 pt-2 border-t border-line/40 text-xs text-slate-700 cursor-pointer">
                        <input
                          type="radio"
                          name="conflict_choice"
                          checked={resolutionChoice === "side_b"}
                          onChange={() => setResolutionChoice("side_b")}
                        />
                        <span>Accept Claim B as Authoritative</span>
                      </label>
                    )}
                  </div>
                </div>

                {/* Resolution Form (if authorized and unresolved) */}
                {canReview && activeConflict.resolution_state === "unresolved" && (
                  <div className="rounded-xl border border-line bg-white p-3.5 space-y-2.5">
                    <span className="text-xs font-bold uppercase tracking-wider text-navy">
                      Adjudicate Conflict
                    </span>
                    <div>
                      <label className="text-[11.5px] font-semibold text-navy block mb-1">
                        Adjudication Notes <span className="text-bad">*</span>:
                      </label>
                      <input
                        type="text"
                        value={resolutionNotes}
                        onChange={(e) => setResolutionNotes(e.target.value)}
                        placeholder="e.g. Source B represents the latest approved architecture decision from Sprint 14…"
                        className="w-full rounded-lg border border-line p-2 text-xs text-navy focus:border-brand focus:outline-none"
                      />
                    </div>
                    <div className="flex justify-end pt-1">
                      <Button
                        size="sm"
                        disabled={isResolving || !resolutionNotes.trim()}
                        onClick={handleResolve}
                      >
                        {isResolving ? "Adjudicating…" : "Resolve Conflict"}
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </Modal>
  );
}
