"use client";

import React from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  HelpCircle,
  RefreshCw,
  Search,
  ShieldAlert,
  GitCompare,
  Layers,
  Users,
  Cpu,
  Calendar,
  Network,
} from "lucide-react";
import { ConflictDashboardMetrics } from "../../lib/conflictsApi";

interface ConflictDashboardBarProps {
  metrics: ConflictDashboardMetrics | null;
  selectedCategory: string;
  onSelectCategory: (cat: string) => void;
  selectedStatus: string;
  onSelectStatus: (status: string) => void;
  selectedPriority: string;
  onSelectPriority: (prio: string) => void;
  searchQuery: string;
  onSearchChange: (q: string) => void;
  onSync: () => void;
  syncing: boolean;
}

export function ConflictDashboardBar({
  metrics,
  selectedCategory,
  onSelectCategory,
  selectedStatus,
  onSelectStatus,
  selectedPriority,
  onSelectPriority,
  searchQuery,
  onSearchChange,
  onSync,
  syncing,
}: ConflictDashboardBarProps) {
  const categories = [
    { id: "all", label: "All Categories", icon: Layers },
    { id: "ownership_conflict", label: "Ownership", icon: Users },
    { id: "status_conflict", label: "Task Status", icon: Clock },
    { id: "decision_conflict", label: "Decisions", icon: GitCompare },
    { id: "technical_conflict", label: "Technical & Arch", icon: Cpu },
    { id: "temporal_conflict", label: "Temporal & Sequence", icon: Calendar },
    { id: "relationship_conflict", label: "Dependencies", icon: Network },
  ];

  return (
    <div className="bg-white border-b border-slate-200 shadow-xs">
      {/* Metrics Row */}
      <div className="px-6 py-4 grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3 border-b border-slate-100">
        <div className="bg-slate-50 border border-slate-200/80 rounded-xl p-3 flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-500 mb-1">
            <span className="text-[11px] font-bold uppercase tracking-wider">Total Detected</span>
            <GitCompare className="w-4 h-4 text-slate-400" />
          </div>
          <div className="flex items-baseline gap-1.5">
            <span className="text-2xl font-extrabold text-slate-900 tracking-tight">
              {metrics?.total_conflicts ?? 0}
            </span>
            <span className="text-xs text-slate-500 font-medium">contradictions</span>
          </div>
        </div>

        <div className="bg-rose-50/60 border border-rose-200/80 rounded-xl p-3 flex flex-col justify-between">
          <div className="flex items-center justify-between text-rose-700 mb-1">
            <span className="text-[11px] font-bold uppercase tracking-wider">Open / Unresolved</span>
            <AlertTriangle className="w-4 h-4 text-rose-500" />
          </div>
          <div className="flex items-baseline gap-1.5">
            <span className="text-2xl font-extrabold text-rose-950 tracking-tight">
              {metrics?.open_conflicts ?? 0}
            </span>
            <span className="text-xs text-rose-700 font-medium">pending</span>
          </div>
        </div>

        <div className="bg-indigo-50/60 border border-indigo-200/80 rounded-xl p-3 flex flex-col justify-between">
          <div className="flex items-center justify-between text-indigo-700 mb-1">
            <span className="text-[11px] font-bold uppercase tracking-wider">Investigating</span>
            <Clock className="w-4 h-4 text-indigo-500" />
          </div>
          <div className="flex items-baseline gap-1.5">
            <span className="text-2xl font-extrabold text-indigo-950 tracking-tight">
              {metrics?.under_investigation ?? 0}
            </span>
            <span className="text-xs text-indigo-700 font-medium">active</span>
          </div>
        </div>

        <div className="bg-amber-50/60 border border-amber-200/80 rounded-xl p-3 flex flex-col justify-between">
          <div className="flex items-center justify-between text-amber-700 mb-1">
            <span className="text-[11px] font-bold uppercase tracking-wider">Awaiting Context</span>
            <HelpCircle className="w-4 h-4 text-amber-500" />
          </div>
          <div className="flex items-baseline gap-1.5">
            <span className="text-2xl font-extrabold text-amber-950 tracking-tight">
              {metrics?.awaiting_context ?? 0}
            </span>
            <span className="text-xs text-amber-700 font-medium">blocked</span>
          </div>
        </div>

        <div className="bg-emerald-50/60 border border-emerald-200/80 rounded-xl p-3 flex flex-col justify-between">
          <div className="flex items-center justify-between text-emerald-700 mb-1">
            <span className="text-[11px] font-bold uppercase tracking-wider">Resolved</span>
            <CheckCircle2 className="w-4 h-4 text-emerald-600" />
          </div>
          <div className="flex items-baseline gap-1.5">
            <span className="text-2xl font-extrabold text-emerald-950 tracking-tight">
              {metrics?.resolved ?? 0}
            </span>
            <span className="text-xs text-emerald-700 font-medium">adjudicated</span>
          </div>
        </div>

        <div className="bg-purple-50/60 border border-purple-200/80 rounded-xl p-3 flex flex-col justify-between">
          <div className="flex items-center justify-between text-purple-700 mb-1">
            <span className="text-[11px] font-bold uppercase tracking-wider">Reopened</span>
            <RefreshCw className="w-4 h-4 text-purple-500" />
          </div>
          <div className="flex items-baseline gap-1.5">
            <span className="text-2xl font-extrabold text-purple-950 tracking-tight">
              {metrics?.reopened ?? 0}
            </span>
            <span className="text-xs text-purple-700 font-medium">re-assessed</span>
          </div>
        </div>

        <div className="bg-red-50/70 border border-red-300 rounded-xl p-3 flex flex-col justify-between">
          <div className="flex items-center justify-between text-red-700 mb-1">
            <span className="text-[11px] font-bold uppercase tracking-wider">Needs Attention</span>
            <ShieldAlert className="w-4 h-4 text-red-600" />
          </div>
          <div className="flex items-baseline gap-1.5">
            <span className="text-2xl font-extrabold text-red-950 tracking-tight">
              {metrics?.attention_required_count ?? 0}
            </span>
            <span className="text-xs text-red-700 font-medium">critical</span>
          </div>
        </div>
      </div>

      {/* Category Pills & Filters */}
      <div className="px-6 py-3 flex flex-wrap items-center justify-between gap-3">
        {/* Category Pills */}
        <div className="flex flex-wrap items-center gap-1.5">
          {categories.map((cat) => {
            const Icon = cat.icon;
            const count =
              cat.id === "all"
                ? metrics?.total_conflicts ?? 0
                : metrics?.category_counts?.[cat.id] ?? 0;
            const isSelected = selectedCategory === cat.id;

            return (
              <button
                key={cat.id}
                onClick={() => onSelectCategory(cat.id)}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                  isSelected
                    ? "bg-slate-900 text-white shadow-xs"
                    : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                }`}
              >
                <Icon className={`w-3.5 h-3.5 ${isSelected ? "text-white" : "text-slate-500"}`} />
                <span>{cat.label}</span>
                <span
                  className={`px-1.5 py-0.2 rounded-full text-[10px] font-bold ${
                    isSelected ? "bg-slate-700 text-slate-200" : "bg-slate-200 text-slate-600"
                  }`}
                >
                  {count}
                </span>
              </button>
            );
          })}
        </div>

        {/* Controls: Search, Dropdowns, Sync */}
        <div className="flex items-center gap-2">
          {/* Search Input */}
          <div className="relative">
            <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => onSearchChange(e.target.value)}
              placeholder="Search claims, sources..."
              className="pl-8 pr-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-slate-400 w-44 md:w-56"
            />
          </div>

          {/* Status Filter Dropdown */}
          <select
            value={selectedStatus}
            onChange={(e) => onSelectStatus(e.target.value)}
            className="text-xs bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1.5 text-slate-700 font-medium focus:outline-none focus:ring-1 focus:ring-slate-400"
          >
            <option value="all">All Statuses</option>
            <option value="open">Open / Unresolved</option>
            <option value="under_investigation">Under Investigation</option>
            <option value="awaiting_context">Awaiting Context</option>
            <option value="resolved">Resolved</option>
            <option value="reopened">Reopened</option>
          </select>

          {/* Priority Filter Dropdown */}
          <select
            value={selectedPriority}
            onChange={(e) => onSelectPriority(e.target.value)}
            className="text-xs bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1.5 text-slate-700 font-medium focus:outline-none focus:ring-1 focus:ring-slate-400"
          >
            <option value="all">All Priorities</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>

          {/* Re-sync Button */}
          <button
            onClick={onSync}
            disabled={syncing}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 transition-colors disabled:opacity-50"
            title="Re-run contradiction detection across project knowledge"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${syncing ? "animate-spin text-blue-600" : "text-slate-500"}`} />
            <span className="hidden sm:inline">{syncing ? "Assessing..." : "Sync Conflicts"}</span>
          </button>
        </div>
      </div>
    </div>
  );
}
