"use client";

import React, { useState } from "react";
import {
  X,
  FileText,
  ExternalLink,
  CheckCircle2,
  Copy,
  Check,
  Lock,
  Layers,
  MapPin,
} from "lucide-react";
import type { ChunkSourceDrawerProps } from "./types";

export const ChunkSourceDrawer: React.FC<ChunkSourceDrawerProps> = ({
  evidence,
  isOpen,
  onClose,
}) => {
  const [copied, setCopied] = useState(false);

  if (!isOpen || !evidence) return null;

  const loc = evidence.source_location || {};
  const isRestricted = evidence.restricted;

  const handleCopy = () => {
    if (evidence.chunk_text) {
      navigator.clipboard.writeText(evidence.chunk_text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-xs p-4 animate-in fade-in-50">
      <div className="bg-white rounded-2xl shadow-2xl border border-slate-200 w-full max-w-2xl max-h-[85vh] flex flex-col overflow-hidden animate-in zoom-in-95 duration-150">
        {/* Drawer Header */}
        <div className="flex items-center justify-between p-4 border-b border-slate-200 bg-slate-50">
          <div className="flex items-center gap-2.5">
            <div className="size-8 rounded-lg bg-teal-50 border border-teal-200 flex items-center justify-center text-teal-700">
              <FileText className="size-4" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-900 truncate max-w-md">
                {evidence.title || "Primary Source Chunk Context"}
              </h3>
              <div className="flex items-center gap-2 text-[11px] text-slate-500 mt-0.5">
                <span className="capitalize">{evidence.source_type.replace(/_/g, " ")}</span>
                {evidence.author && (
                  <>
                    <span>•</span>
                    <span>by {evidence.author}</span>
                  </>
                )}
                {evidence.source_url && (
                  <>
                    <span>•</span>
                    <a
                      href={evidence.source_url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-teal-600 hover:text-teal-800 flex items-center gap-0.5"
                    >
                      <span>Open Link</span>
                      <ExternalLink className="size-2.5" />
                    </a>
                  </>
                )}
              </div>
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

        {/* Drawer Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {/* Provenance Metadata Bar */}
          <div className="flex flex-wrap items-center gap-2 p-2.5 bg-slate-50 rounded-xl border border-slate-200 text-xs">
            <div className="flex items-center gap-1 text-slate-600 font-medium">
              <MapPin className="size-3 text-slate-400" />
              <span>Location:</span>
            </div>
            {loc.page_number !== undefined && (
              <span className="px-2 py-0.5 rounded bg-white border border-slate-200 text-slate-700 font-mono text-[11px]">
                Page {loc.page_number}
              </span>
            )}
            {loc.chunk_index !== undefined && (
              <span className="px-2 py-0.5 rounded bg-white border border-slate-200 text-slate-700 font-mono text-[11px]">
                Chunk #{loc.chunk_index}
              </span>
            )}
            {loc.commit_hash && (
              <span className="px-2 py-0.5 rounded bg-white border border-slate-200 text-slate-700 font-mono text-[11px]">
                Commit {String(loc.commit_hash).slice(0, 7)}
              </span>
            )}
            {loc.pull_request_number !== undefined && (
              <span className="px-2 py-0.5 rounded bg-white border border-slate-200 text-slate-700 font-mono text-[11px]">
                PR #{loc.pull_request_number}
              </span>
            )}

            <div className="ml-auto flex items-center gap-1.5">
              {evidence.excerpt_verified ? (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-200">
                  <CheckCircle2 className="size-3 text-emerald-600" />
                  Grounding Verified
                </span>
              ) : (
                <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-100 text-amber-800 border border-amber-200">
                  Ungrounded Claim
                </span>
              )}
            </div>
          </div>

          {/* Verbatim Excerpt */}
          {evidence.supporting_excerpt && (
            <div className="space-y-1">
              <div className="text-xs font-bold text-slate-700 flex items-center gap-1.5">
                <Layers className="size-3.5 text-teal-600" />
                Extracted Grounding Excerpt
              </div>
              <blockquote className="p-3 bg-teal-50/60 border-l-3 border-teal-500 rounded-r-lg text-xs font-serif italic text-slate-800 leading-relaxed">
                &ldquo;{evidence.supporting_excerpt}&rdquo;
              </blockquote>
            </div>
          )}

          {/* Full Raw Chunk Content */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-xs font-bold text-slate-700">
              <span>Full Raw Chunk Text</span>
              {evidence.chunk_text && !isRestricted && (
                <button
                  type="button"
                  onClick={handleCopy}
                  className="flex items-center gap-1 text-[11px] font-normal text-slate-500 hover:text-slate-800 cursor-pointer"
                >
                  {copied ? (
                    <>
                      <Check className="size-3 text-emerald-600" />
                      <span>Copied!</span>
                    </>
                  ) : (
                    <>
                      <Copy className="size-3" />
                      <span>Copy chunk text</span>
                    </>
                  )}
                </button>
              )}
            </div>

            {isRestricted ? (
              <div className="p-6 bg-rose-50 border border-rose-200 rounded-xl text-center space-y-2">
                <Lock className="size-6 text-rose-600 mx-auto" />
                <h4 className="text-xs font-bold text-rose-900">Restricted Source ACL</h4>
                <p className="text-[11px] text-rose-700 max-w-sm mx-auto">
                  You do not have access rights under project ACL policies to inspect the full raw text of this source document.
                </p>
              </div>
            ) : evidence.chunk_text ? (
              <div className="p-3.5 bg-slate-900 text-slate-200 rounded-xl font-mono text-[11px] leading-relaxed max-h-72 overflow-y-auto whitespace-pre-wrap select-text">
                {evidence.chunk_text}
              </div>
            ) : (
              <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl text-center text-xs text-slate-500">
                No raw chunk text stored in database for this citation link.
              </div>
            )}
          </div>
        </div>

        {/* Drawer Footer */}
        <div className="p-3 border-t border-slate-200 bg-slate-50 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 bg-slate-200 hover:bg-slate-300 text-slate-700 font-semibold text-xs rounded-lg transition cursor-pointer"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
