"use client";

import React from "react";
import {
  Search,
  Filter,
  AlertCircle,
  ChevronLeft,
  ChevronRight,
  GitCompare,
  User,
  X,
  Loader2,
  Sparkles,
} from "lucide-react";
import type { QueueListProps, VerificationCaseItem } from "./types";

export const VerificationQueueList: React.FC<QueueListProps> = ({
  queue,
  selectedCaseId,
  onSelectCase,
  loading,
  statusFilter,
  onStatusFilterChange,
  searchTerm,
  onSearchChange,
  priorityFilter,
  onPriorityFilterChange,
  page,
  totalItems,
  pageSize,
  onPageChange,
}) => {
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));

  const statusTabs = [
    { id: "all", label: "All" },
    { id: "pending_review", label: "Pending" },
    { id: "candidate", label: "Candidate" },
    { id: "conflicted", label: "Conflicted" },
    { id: "unresolved", label: "Unresolved" },
    { id: "verified", label: "Verified" },
    { id: "rejected", label: "Rejected" },
  ];

  const getPriorityBadgeClass = (priority?: string | null) => {
    switch (priority?.toLowerCase()) {
      case "critical":
        return "bg-rose-100 text-rose-800 border-rose-300 font-bold";
      case "high":
        return "bg-amber-100 text-amber-800 border-amber-300 font-semibold";
      case "medium":
        return "bg-blue-100 text-blue-800 border-blue-300";
      case "low":
        return "bg-slate-100 text-slate-700 border-slate-300";
      default:
        return "bg-slate-100 text-slate-600 border-slate-200";
    }
  };

  const getStatusBadgeClass = (status?: string | null) => {
    switch (status?.toLowerCase()) {
      case "verified":
      case "approved":
        return "bg-emerald-100 text-emerald-800 border-emerald-300";
      case "pending_review":
      case "in_review":
        return "bg-blue-100 text-blue-800 border-blue-300";
      case "conflicted":
        return "bg-purple-100 text-purple-800 border-purple-300";
      case "unresolved":
        return "bg-amber-100 text-amber-800 border-amber-300";
      case "rejected":
        return "bg-rose-100 text-rose-800 border-rose-300";
      case "candidate":
        return "bg-cyan-100 text-cyan-800 border-cyan-300";
      default:
        return "bg-slate-100 text-slate-700 border-slate-200";
    }
  };

  return (
    <div className="flex flex-col h-full bg-white border-r border-slate-200 select-none">
      {/* Search and Filters Header */}
      <div className="p-3.5 border-b border-slate-200 space-y-2.5">
        {/* Search bar */}
        <div className="relative">
          <Search className="absolute left-3 top-2.5 size-4 text-slate-400" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search findings, domains, tags..."
            className="w-full pl-9 pr-8 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-teal-500 focus:bg-white text-slate-900 transition"
          />
          {searchTerm && (
            <button
              type="button"
              onClick={() => onSearchChange("")}
              className="absolute right-2.5 top-2.5 text-slate-400 hover:text-slate-600"
            >
              <X className="size-3.5" />
            </button>
          )}
        </div>

        {/* Priority Filter and Status Filter Row */}
        <div className="flex items-center justify-between gap-2">
          {/* Priority dropdown */}
          <div className="flex items-center gap-1.5 text-xs text-slate-600">
            <Filter className="size-3 text-slate-400" />
            <span className="text-[11px] text-slate-500">Priority:</span>
            <select
              value={priorityFilter}
              onChange={(e) => onPriorityFilterChange(e.target.value)}
              className="text-xs bg-slate-50 border border-slate-200 rounded-md px-2 py-1 text-slate-800 focus:outline-none focus:ring-1 focus:ring-teal-500 cursor-pointer"
            >
              <option value="all">All Priorities</option>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
          </div>

          <div className="text-[11px] text-slate-600 font-medium">
            {totalItems} {totalItems === 1 ? "item" : "items"}
          </div>
        </div>

        {/* Status quick tabs */}
        <div className="flex items-center gap-1 overflow-x-auto pb-1 text-xs no-scrollbar">
          {statusTabs.map((tab) => {
            const isActive = statusFilter === tab.id;
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => onStatusFilterChange(tab.id)}
                className={`px-2.5 py-1 rounded-md text-[11px] font-medium whitespace-nowrap transition cursor-pointer ${
                  isActive
                    ? "bg-teal-700 text-white shadow-2xs font-semibold"
                    : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                }`}
              >
                {tab.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Queue Items List */}
      <div className="flex-1 overflow-y-auto divide-y divide-slate-100 p-2 space-y-1.5">
        {loading && queue.length === 0 ? (
          <div className="flex flex-col items-center justify-center p-8 text-center text-slate-400">
            <Loader2 className="size-6 animate-spin text-teal-600 mb-2" />
            <p className="text-xs">Loading verification queue...</p>
          </div>
        ) : queue.length === 0 ? (
          <div className="flex flex-col items-center justify-center p-8 text-center text-slate-400">
            <AlertCircle className="size-8 text-slate-300 mb-2" />
            <p className="text-xs font-semibold text-slate-700">No findings found</p>
            <p className="text-[11px] text-slate-500 mt-1 max-w-[200px]">
              No candidate findings match the current filter or search criteria.
            </p>
          </div>
        ) : (
          queue.map((item: VerificationCaseItem) => {
            const isSelected = item.id === selectedCaseId;
            const title =
              item.finding?.title ||
              item.title ||
              `Finding (${item.target_id?.slice(0, 8)})`;
            const domain =
              item.finding?.domain || item.domain || "Architecture";
            const category = item.finding?.category || item.category;
            const priority = item.priority;
            const status = item.case_status || item.status || "pending_review";
            const confidence =
              item.confidence_score !== null && item.confidence_score !== undefined
                ? Math.round(item.confidence_score * 100)
                : null;
            const openIssues = item.open_issues_count ?? item.issue_count ?? 0;
            const openConflicts = item.open_conflicts_count ?? 0;

            return (
              <div
                key={item.id}
                onClick={() => onSelectCase(item.id)}
                className={`p-3 rounded-xl border text-left transition cursor-pointer relative ${
                  isSelected
                    ? "bg-teal-50/60 border-teal-500 ring-2 ring-teal-400/40 shadow-xs"
                    : "bg-white border-slate-200 hover:border-slate-300 hover:bg-slate-50/80 shadow-2xs"
                }`}
              >
                {/* Top row: domain tag, status pill, priority */}
                <div className="flex items-center justify-between gap-1.5 mb-1.5">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-slate-100 text-slate-700 border border-slate-200 uppercase tracking-wider">
                      {domain}
                    </span>
                    {category && (
                      <span className="text-[10px] text-slate-500">
                        {category}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-1">
                    {priority && (
                      <span
                        className={`px-1.5 py-0.2 rounded text-[10px] border uppercase ${getPriorityBadgeClass(
                          priority
                        )}`}
                      >
                        {priority}
                      </span>
                    )}
                    <span
                      className={`px-1.5 py-0.2 rounded-full text-[10px] border uppercase ${getStatusBadgeClass(
                        status
                      )}`}
                    >
                      {status.replace(/_/g, " ")}
                    </span>
                  </div>
                </div>

                {/* Finding Title */}
                <h3 className="text-xs font-semibold text-slate-900 line-clamp-2 mb-1.5">
                  {title}
                </h3>

                {/* Bottom metadata indicators row */}
                <div className="flex items-center justify-between text-[11px] text-slate-500 pt-1 border-t border-slate-100/80">
                  <div className="flex items-center gap-2">
                    {confidence !== null ? (
                      <span
                        className="inline-flex items-center gap-1 text-[10px] font-medium text-slate-600 bg-slate-100 px-1.5 py-0.2 rounded"
                        title="Advisory AI extraction confidence score"
                      >
                        <Sparkles className="size-2.5 text-teal-600" />
                        {confidence}%
                      </span>
                    ) : (
                      <span className="text-[10px] text-slate-600">Unscored</span>
                    )}

                    {openIssues > 0 && (
                      <span className="inline-flex items-center gap-0.5 text-[10px] font-semibold text-rose-700 bg-rose-50 px-1.5 py-0.2 rounded border border-rose-200">
                        <AlertCircle className="size-2.5 text-rose-600" />
                        {openIssues} {openIssues === 1 ? "flag" : "flags"}
                      </span>
                    )}

                    {openConflicts > 0 && (
                      <span className="inline-flex items-center gap-0.5 text-[10px] font-semibold text-purple-700 bg-purple-50 px-1.5 py-0.2 rounded border border-purple-200">
                        <GitCompare className="size-2.5 text-purple-600" />
                        {openConflicts}
                      </span>
                    )}
                  </div>

                  <div className="flex items-center gap-1 text-[10px] text-slate-600">
                    {item.assigned_reviewer_id ? (
                      <span className="flex items-center gap-0.5 text-blue-700" title="Assigned reviewer">
                        <User className="size-2.5" />
                        Assigned
                      </span>
                    ) : (
                      <span>Unassigned</span>
                    )}
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Pagination Footer */}
      <div className="p-2.5 border-t border-slate-200 bg-slate-50 flex items-center justify-between text-xs text-slate-600">
        <button
          type="button"
          onClick={() => onPageChange(Math.max(1, page - 1))}
          disabled={page <= 1 || loading}
          className="p-1 rounded hover:bg-slate-200 disabled:opacity-40 transition cursor-pointer"
          title="Previous page"
        >
          <ChevronLeft className="size-4" />
        </button>

        <span className="text-[11px] font-medium">
          Page {page} of {totalPages}
        </span>

        <button
          type="button"
          onClick={() => onPageChange(Math.min(totalPages, page + 1))}
          disabled={page >= totalPages || loading}
          className="p-1 rounded hover:bg-slate-200 disabled:opacity-40 transition cursor-pointer"
          title="Next page"
        >
          <ChevronRight className="size-4" />
        </button>
      </div>
    </div>
  );
};
