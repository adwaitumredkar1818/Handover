"use client";

import React from "react";
import {
  AlertTriangle,
  Clock,
  CheckCircle2,
  HelpCircle,
  RefreshCw,
  User,
  ChevronRight,
  GitCompare,
  Users,
  Cpu,
  Calendar,
  Network,
  ArrowRight,
} from "lucide-react";
import { ConflictQueueItem } from "../../lib/conflictsApi";

interface ConflictQueuePanelProps {
  conflicts: ConflictQueueItem[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  loading: boolean;
}

export function ConflictQueuePanel({
  conflicts,
  selectedId,
  onSelect,
  loading,
}: ConflictQueuePanelProps) {
  const getCategoryConfig = (type: string) => {
    switch (type) {
      case "ownership_conflict":
        return { label: "Ownership", icon: Users, bg: "bg-blue-50 text-blue-700 border-blue-200" };
      case "status_conflict":
        return { label: "Task Status", icon: Clock, bg: "bg-amber-50 text-amber-700 border-amber-200" };
      case "decision_conflict":
        return { label: "Decision", icon: GitCompare, bg: "bg-purple-50 text-purple-700 border-purple-200" };
      case "technical_conflict":
        return { label: "Technical", icon: Cpu, bg: "bg-emerald-50 text-emerald-700 border-emerald-200" };
      case "temporal_conflict":
        return { label: "Temporal", icon: Calendar, bg: "bg-orange-50 text-orange-700 border-orange-200" };
      case "relationship_conflict":
        return { label: "Dependency", icon: Network, bg: "bg-indigo-50 text-indigo-700 border-indigo-200" };
      default:
        return { label: "Contradiction", icon: GitCompare, bg: "bg-slate-50 text-slate-700 border-slate-200" };
    }
  };

  const getPriorityBadge = (prio: string) => {
    switch (prio.toLowerCase()) {
      case "critical":
        return <span className="px-1.5 py-0.5 rounded text-[10px] font-extrabold uppercase tracking-wider bg-red-100 text-red-800 border border-red-200">Critical</span>;
      case "high":
        return <span className="px-1.5 py-0.5 rounded text-[10px] font-extrabold uppercase tracking-wider bg-orange-100 text-orange-800 border border-orange-200">High</span>;
      case "medium":
        return <span className="px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider bg-blue-100 text-blue-800 border border-blue-200">Medium</span>;
      default:
        return <span className="px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider bg-slate-100 text-slate-700 border border-slate-200">Low</span>;
    }
  };

  const getStatusPill = (status: string) => {
    switch (status) {
      case "open":
      case "unresolved":
        return (
          <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-rose-700">
            <AlertTriangle className="w-3 h-3 text-rose-500" />
            Open
          </span>
        );
      case "under_investigation":
        return (
          <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-indigo-700">
            <Clock className="w-3 h-3 text-indigo-500" />
            Investigating
          </span>
        );
      case "awaiting_context":
        return (
          <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-amber-700">
            <HelpCircle className="w-3 h-3 text-amber-500" />
            Awaiting Context
          </span>
        );
      case "resolved":
      case "superseded":
      case "reconciled":
      case "dismissed":
        return (
          <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-700">
            <CheckCircle2 className="w-3 h-3 text-emerald-600" />
            Resolved
          </span>
        );
      case "reopened":
        return (
          <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-purple-700">
            <RefreshCw className="w-3 h-3 text-purple-500" />
            Reopened
          </span>
        );
      default:
        return <span className="text-[11px] text-slate-600">{status}</span>;
    }
  };

  if (loading) {
    return (
      <div className="w-full md:w-96 border-r border-slate-200 bg-white p-4 space-y-3 shrink-0">
        {[1, 2, 3, 4, 5].map((i) => (
          <div key={i} className="h-28 bg-slate-100 rounded-xl animate-pulse" />
        ))}
      </div>
    );
  }

  if (conflicts.length === 0) {
    return (
      <div className="w-full md:w-96 border-r border-slate-200 bg-white p-8 text-center flex flex-col items-center justify-center shrink-0">
        <CheckCircle2 className="w-10 h-10 text-emerald-500 mb-3" />
        <h4 className="text-sm font-bold text-slate-800">Zero Active Conflicts</h4>
        <p className="text-xs text-slate-500 mt-1 max-w-xs">
          No cross-source contradictions match your selected filter criteria.
        </p>
      </div>
    );
  }

  return (
    <div className="w-full md:w-96 border-r border-slate-200 bg-slate-50/50 overflow-y-auto shrink-0 flex flex-col divide-y divide-slate-200/80">
      <div className="p-3 bg-white border-b border-slate-200 text-xs font-bold text-slate-500 flex justify-between items-center">
        <span>CONTRADICTIONS QUEUE</span>
        <span className="bg-slate-100 text-slate-700 px-2 py-0.5 rounded-full text-[10px]">
          {conflicts.length} items
        </span>
      </div>

      <div className="divide-y divide-slate-100">
        {conflicts.map((conf) => {
          const isSelected = conf.id === selectedId;
          const cat = getCategoryConfig(conf.conflict_type);
          const CatIcon = cat.icon;

          return (
            <div
              key={conf.id}
              onClick={() => onSelect(conf.id)}
              className={`p-3.5 cursor-pointer transition-all border-l-4 ${
                isSelected
                  ? "bg-white border-blue-600 shadow-xs"
                  : "bg-transparent border-transparent hover:bg-white hover:border-slate-300"
              }`}
            >
              {/* Category, Priority & Status header */}
              <div className="flex items-center justify-between gap-2 mb-2">
                <span
                  className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold border ${cat.bg}`}
                >
                  <CatIcon className="w-3 h-3" />
                  {cat.label}
                </span>

                <div className="flex items-center gap-1.5">
                  {getPriorityBadge(conf.priority)}
                  {getStatusPill(conf.resolution_state)}
                </div>
              </div>

              {/* Side A vs Side B short compare */}
              <div className="space-y-1 mb-2">
                <div className="text-xs font-medium text-slate-800 line-clamp-1 flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-blue-500 shrink-0" />
                  <span className="text-[11px] font-semibold text-blue-700 shrink-0">Claim A:</span>
                  <span className="truncate">{conf.side_a_title || "Claim A"}</span>
                </div>
                <div className="text-xs font-medium text-slate-800 line-clamp-1 flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-rose-500 shrink-0" />
                  <span className="text-[11px] font-semibold text-rose-700 shrink-0">Claim B:</span>
                  <span className="truncate">{conf.side_b_title || "Claim B"}</span>
                </div>
              </div>

              {/* Explanation excerpt */}
              <p className="text-[11px] text-slate-500 line-clamp-2 leading-relaxed mb-2.5">
                {conf.explanation}
              </p>

              {/* Reviewer & Time footer */}
              <div className="flex items-center justify-between text-[10px] text-slate-400 pt-1 border-t border-slate-100">
                <div className="flex items-center gap-1 truncate max-w-[180px]">
                  <User className="w-3 h-3 text-slate-400 shrink-0" />
                  <span className="truncate text-slate-600">
                    {conf.assigned_reviewer_name ? conf.assigned_reviewer_name : "Unassigned"}
                  </span>
                </div>

                <div className="flex items-center gap-1 text-slate-400">
                  <span>{new Date(conf.created_at).toLocaleDateString()}</span>
                  <ChevronRight className="w-3.5 h-3.5 text-slate-300" />
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
