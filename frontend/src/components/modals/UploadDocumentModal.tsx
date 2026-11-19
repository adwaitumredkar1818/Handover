"use client";

import React, { useState, useRef } from "react";
import { X, UploadCloud, Shield, ArrowRight, AlertCircle, CheckCircle2 } from "lucide-react";
import { useLiveApp } from "../../context/LiveAppContext";
import { UploadProgress, ButtonLoader, type UploadProcessingStatus } from "../loading";

export function UploadDocumentModal() {
  const { isUploadModalOpen, setIsUploadModalOpen, uploadDocument, activeProject } = useLiveApp();
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [customTitle, setCustomTitle] = useState("");
  const [docCategory, setDocCategory] = useState<"team_roster" | "meeting_notes" | "project_document">("project_document");
  const [docSubtype, setDocSubtype] = useState("prd");
  const [isUploading, setIsUploading] = useState(false);
  const [uploadStage, setUploadStage] = useState<UploadProcessingStatus>("selected");
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  if (!isUploadModalOpen) return null;

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      setSelectedFile(file);
      if (!customTitle) {
        setCustomTitle(file.name);
      }
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const file = e.dataTransfer.files[0];
      setSelectedFile(file);
      if (!customTitle) {
        setCustomTitle(file.name);
      }
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) {
      setError("Please select a document file (.pdf or .docx)");
      return;
    }
    setError(null);
    setIsUploading(true);
    setUploadStage("uploading");
    try {
      // Simulate stage transition to encrypting & extracting
      const stageTimer = setTimeout(() => {
        setUploadStage("encrypting");
      }, 700);

      await uploadDocument(selectedFile, customTitle.trim() || undefined, {
        documentCategory: docCategory,
        documentSubtype: docCategory === "project_document" ? docSubtype : undefined,
      });
      clearTimeout(stageTimer);
      setUploadStage("completed");
      setTimeout(() => {
        setSelectedFile(null);
        setCustomTitle("");
        setDocCategory("project_document");
        setUploadStage("selected");
        setIsUploadModalOpen(false);
      }, 1000);
    } catch (err: unknown) {
      setUploadStage("failed");
      setError(err instanceof Error ? err.message : "Failed to upload document");
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-2xs p-4">
      <div className="w-full max-w-lg bg-white rounded-xl shadow-xl border border-[#DCE3EB] overflow-hidden">
        {/* Header */}
        <div className="px-6 py-4 bg-[#F4F6F9] border-b border-[#DCE3EB] flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm font-bold text-[#25334B]">
            <UploadCloud className="w-4 h-4 text-[#249E91]" />
            <span>Ingest Document Evidence</span>
            {activeProject && (
              <span className="text-xs px-2 py-0.5 rounded bg-teal-50 text-teal-700 font-normal border border-teal-200">
                {activeProject.name}
              </span>
            )}
          </div>
          <button
            type="button"
            onClick={() => setIsUploadModalOpen(false)}
            className="p-1 rounded text-[#69778D] hover:text-[#25334B]"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {error && (
            <div className="p-3 rounded-lg bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* Drag & Drop Area */}
          <div
            onDragOver={(e) => e.preventDefault()}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-colors ${
              selectedFile
                ? "border-[#249E91] bg-[#F0FAF8]"
                : "border-[#DCE3EB] hover:border-[#4774A9] bg-[#F4F6F9]/50"
            }`}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              onChange={handleFileChange}
              className="hidden"
            />
            {selectedFile ? (
              <div className="flex flex-col items-center">
                <CheckCircle2 className="w-8 h-8 text-[#249E91] mb-2" />
                <div className="font-semibold text-xs text-[#25334B]">{selectedFile.name}</div>
                <div className="text-[11px] text-[#69778D] mt-0.5">
                  {(selectedFile.size / 1024).toFixed(1)} KB · {selectedFile.type || "Document"}
                </div>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    setSelectedFile(null);
                    setCustomTitle("");
                  }}
                  className="mt-2 text-[11px] text-rose-600 hover:underline"
                >
                  Change file
                </button>
              </div>
            ) : (
              <div className="flex flex-col items-center">
                <UploadCloud className="w-8 h-8 text-[#4774A9] mb-2" />
                <div className="text-xs font-semibold text-[#25334B]">
                  Click to choose file or drag and drop
                </div>
                <div className="text-[11px] text-[#69778D] mt-1">
                  Supports PDF (scanned or digital) and DOCX documents up to 50MB
                </div>
              </div>
            )}
          </div>

          {/* Document Intelligence Category */}
          <div className="space-y-2">
            <label className="block text-xs font-semibold text-[#25334B]">
              Document Category <span className="text-rose-500">*</span>
            </label>
            <div className="grid grid-cols-3 gap-2">
              <button
                type="button"
                onClick={() => setDocCategory("team_roster")}
                className={`p-2.5 rounded-lg border text-left transition-all ${
                  docCategory === "team_roster"
                    ? "border-[#249E91] bg-teal-50/50 ring-1 ring-[#249E91]"
                    : "border-[#DCE3EB] hover:bg-slate-50"
                }`}
              >
                <div className="font-semibold text-[11.5px] text-slate-900">Team Roster</div>
                <div className="text-[10px] text-slate-500 mt-0.5 leading-snug">Extract roles & ownership</div>
              </button>
              <button
                type="button"
                onClick={() => setDocCategory("meeting_notes")}
                className={`p-2.5 rounded-lg border text-left transition-all ${
                  docCategory === "meeting_notes"
                    ? "border-[#249E91] bg-teal-50/50 ring-1 ring-[#249E91]"
                    : "border-[#DCE3EB] hover:bg-slate-50"
                }`}
              >
                <div className="font-semibold text-[11.5px] text-slate-900">Meeting Notes</div>
                <div className="text-[10px] text-slate-500 mt-0.5 leading-snug">Decisions & discussions</div>
              </button>
              <button
                type="button"
                onClick={() => setDocCategory("project_document")}
                className={`p-2.5 rounded-lg border text-left transition-all ${
                  docCategory === "project_document"
                    ? "border-[#249E91] bg-teal-50/50 ring-1 ring-[#249E91]"
                    : "border-[#DCE3EB] hover:bg-slate-50"
                }`}
              >
                <div className="font-semibold text-[11.5px] text-slate-900">Project Spec</div>
                <div className="text-[10px] text-slate-500 mt-0.5 leading-snug">Specs & architecture</div>
              </button>
            </div>
          </div>

          {/* Subtype for Project Document */}
          {docCategory === "project_document" && (
            <div>
              <label className="block text-xs font-semibold text-[#25334B] mb-1">
                Specification Subtype
              </label>
              <select
                value={docSubtype}
                onChange={(e) => setDocSubtype(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-[#DCE3EB] text-xs focus:outline-none focus:ring-2 focus:ring-[#249E91] text-[#25334B] bg-white"
              >
                <option value="prd">Product Requirement Document (PRD)</option>
                <option value="srs">Software Requirements Specification (SRS)</option>
                <option value="trd">Technical Requirements Document (TRD)</option>
                <option value="dd">Design Document (DD)</option>
                <option value="add">Architectural Design Document (ADD)</option>
                <option value="architecture">Architecture Blueprint</option>
                <option value="api_spec">API Specification</option>
                <option value="database_design">Database Design / Schema</option>
                <option value="security_spec">Security Specification</option>
                <option value="test_plan">Test Plan / QA Strategy</option>
                <option value="runbook">Operations Runbook / SOP</option>
                <option value="onboarding_guide">Onboarding Guide</option>
                <option value="handover_notes">Handover Notes / Wrap-up</option>
                <option value="other_spec">Other Technical Specification</option>
              </select>
            </div>
          )}

          <div>
            <label className="block text-xs font-semibold text-[#25334B] mb-1">
              Document Display Title (Optional)
            </label>
            <input
              type="text"
              value={customTitle}
              onChange={(e) => setCustomTitle(e.target.value)}
              placeholder="e.g. System Architecture Runbook v2"
              className="w-full px-3 py-2 rounded-lg border border-[#DCE3EB] text-xs focus:outline-none focus:ring-2 focus:ring-[#4774A9] text-[#25334B]"
            />
          </div>

          {/* Upload Progress Pipeline (when active or complete) */}
          {(isUploading || uploadStage === "completed" || uploadStage === "failed") && selectedFile && (
            <div className="pt-2">
              <UploadProgress
                fileName={selectedFile.name}
                fileSizeBytes={selectedFile.size}
                status={uploadStage}
                errorMessage={error || undefined}
                onRetry={() => {
                  setError(null);
                  setUploadStage("selected");
                }}
              />
            </div>
          )}

          {/* Security Notice */}
          <div className="p-3 rounded-lg bg-emerald-50/60 border border-emerald-200/60 flex items-start gap-2.5 text-emerald-950 text-[11px] leading-relaxed">
            <Shield className="w-4 h-4 text-[#249E91] shrink-0 mt-0.5" />
            <div>
              <span className="font-semibold">Client-Side Envelope Encryption:</span> All original documents are encrypted with AES-256-GCM before storage and indexed with Nomics 768-dim embeddings in project-isolated vector collections.
            </div>
          </div>

          <div className="pt-2 flex items-center justify-end gap-3 border-t border-[#DCE3EB]">
            <button
              type="button"
              disabled={isUploading}
              onClick={() => setIsUploadModalOpen(false)}
              className="px-4 py-2 rounded-lg border border-[#DCE3EB] text-xs font-semibold text-[#69778D] hover:bg-[#F4F6F9] disabled:opacity-50"
            >
              Cancel
            </button>
            <ButtonLoader
              type="submit"
              disabled={!selectedFile || isUploading}
              isLoading={isUploading}
              loadingText="Ingesting Evidence..."
              variant="teal"
              icon={<ArrowRight className="w-3.5 h-3.5" />}
              className="px-4 py-2 rounded-lg text-xs font-semibold"
            >
              Upload &amp; Ingest Evidence
            </ButtonLoader>
          </div>
        </form>
      </div>
    </div>
  );
}
