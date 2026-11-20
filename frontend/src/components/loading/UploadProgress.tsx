"use client";

import React from "react";
import {
  UploadCloud,
  FileText,
  CheckCircle2,
  AlertCircle,
  Shield,
  Cpu,
  Database,
  RefreshCw,
} from "lucide-react";

export type UploadProcessingStatus =
  | "selected"
  | "uploading"
  | "uploaded"
  | "encrypting"
  | "extracting"
  | "indexing"
  | "completed"
  | "failed";

export interface UploadProgressProps {
  fileName: string;
  fileSizeBytes?: number;
  uploadedBytes?: number;
  status: UploadProcessingStatus;
  errorMessage?: string;
  onRetry?: () => void;
  className?: string;
}

export function UploadProgress({
  fileName,
  fileSizeBytes,
  uploadedBytes,
  status,
  errorMessage,
  onRetry,
  className = "",
}: UploadProgressProps) {
  const percent =
    fileSizeBytes && uploadedBytes
      ? Math.min(100, Math.round((uploadedBytes / fileSizeBytes) * 100))
      : status === "uploading"
      ? null
      : status === "completed"
      ? 100
      : null;

  const stageDescriptions: Record<UploadProcessingStatus, { title: string; desc: string; icon: React.ReactNode }> = {
    selected: {
      title: "File Ready to Ingest",
      desc: "Document validated for AES-256 client envelope encryption",
      icon: <FileText className="w-4 h-4 text-[#4774A9]" />,
    },
    uploading: {
      title: percent !== null ? `Uploading (${percent}%)` : "Uploading encrypted stream...",
      desc: fileSizeBytes
        ? `${((uploadedBytes || 0) / (1024 * 1024)).toFixed(2)} MB of ${(fileSizeBytes / (1024 * 1024)).toFixed(2)} MB`
        : "Transferring binary payload to private vault",
      icon: <UploadCloud className="w-4 h-4 text-[#315FBA] animate-bounce" />,
    },
    uploaded: {
      title: "Payload Staged Successfully",
      desc: "Vault delivery confirmed with SHA-256 integrity hash",
      icon: <CheckCircle2 className="w-4 h-4 text-[#299B80]" />,
    },
    encrypting: {
      title: "AES-256 Envelope Encryption",
      desc: "Applying envelope key wrapping before storage",
      icon: <Shield className="w-4 h-4 text-[#299B80] animate-pulse" />,
    },
    extracting: {
      title: "OCR & Document Parsing",
      desc: "PyMuPDF digital parsing and GLM-OCR visual layout analysis",
      icon: <Cpu className="w-4 h-4 text-[#8B78C9] animate-spin" style={{ animationDuration: "3s" }} />,
    },
    indexing: {
      title: "Vector Indexing (768-dim)",
      desc: "Chunking and indexing into project-isolated ChromaDB collection",
      icon: <Database className="w-4 h-4 text-[#315FBA] animate-pulse" />,
    },
    completed: {
      title: "Evidence Ingested & Indexed",
      desc: "Ready for knowledge reconstruction and semantic search",
      icon: <CheckCircle2 className="w-4 h-4 text-[#299B80]" />,
    },
    failed: {
      title: "Ingestion Failed",
      desc: errorMessage || "An error occurred during document processing",
      icon: <AlertCircle className="w-4 h-4 text-rose-600" />,
    },
  };

  const current = stageDescriptions[status] || stageDescriptions.uploading;

  return (
    <div
      className={`p-4 rounded-xl border ${
        status === "failed"
          ? "border-rose-200 bg-rose-50/50"
          : status === "completed"
          ? "border-teal-200 bg-teal-50/40"
          : "border-[#DCE3EB] bg-[#F8FAFC]"
      } space-y-3 transition-colors ${className}`}
      role="status"
      aria-live="polite"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="p-2 rounded-lg bg-white border border-[#DCE3EB] shadow-2xs shrink-0">
            {current.icon}
          </div>
          <div className="min-w-0">
            <h4 className="text-xs font-bold text-[#203653] truncate">{fileName}</h4>
            <p className="text-[11px] text-[#69778D]">{current.desc}</p>
          </div>
        </div>

        {status === "failed" && onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="px-2.5 py-1 rounded bg-rose-100 hover:bg-rose-200 text-rose-800 text-[11px] font-semibold flex items-center gap-1 transition-colors shrink-0"
          >
            <RefreshCw className="w-3 h-3" />
            <span>Retry</span>
          </button>
        )}
      </div>

      {/* Progress Bar (During Upload or Processing) */}
      {(status === "uploading" ||
        status === "encrypting" ||
        status === "extracting" ||
        status === "indexing") && (
        <div className="space-y-1">
          <div className="h-1.5 w-full bg-[#E2E8F0] rounded-full overflow-hidden">
            {percent !== null ? (
              <div
                className="h-full bg-[#315FBA] transition-all duration-200 rounded-full"
                style={{ width: `${percent}%` }}
              />
            ) : (
              <div
                className="h-full w-1/3 bg-gradient-to-r from-transparent via-[#315FBA] to-transparent animate-beam rounded-full"
                style={{ animationDuration: "1.5s" }}
              />
            )}
          </div>
          <div className="flex items-center justify-between text-[10px] text-[#69778D] font-medium">
            <span>{current.title}</span>
            {percent !== null && <span>{percent}%</span>}
          </div>
        </div>
      )}
    </div>
  );
}

export default UploadProgress;
