"use client";

import React, { useRef } from "react";
import {
  FileText,
  ShieldCheck,
  ListTodo,
  Scale,
  Cpu,
  CheckSquare,
  Users,
  Network,
  AlertTriangle,
  Activity,
  Layers,
  Sparkles,
  type LucideIcon,
  ChevronRight,
} from "lucide-react";
import { cn, Tooltip } from "../figma-ui/index";
import type { HandoverReadinessIntelligenceResponse } from "../../lib/types";

export interface NavGroup {
  id: string;
  label: string;
  tabs: NavTabItem[];
}

export interface NavTabItem {
  id: string;
  label: string;
  icon?: LucideIcon;
  countKey?: string;
  isMilestone?: boolean;
}

export const WORKSPACE_NAV_GROUPS: readonly NavGroup[] = [
  {
    id: "overview",
    label: "Overview",
    tabs: [
      { id: "overview", label: "Overview", icon: Layers },
      { id: "readiness", label: "Readiness", icon: Sparkles, countKey: "readiness" },
    ],
  },
  {
    id: "knowledge",
    label: "Knowledge",
    tabs: [
      { id: "decisions", label: "Decisions", icon: Scale, countKey: "decisions" },
      { id: "architecture", label: "Architecture", icon: Cpu, countKey: "architecture" },
      { id: "tasks", label: "Tasks & Work", icon: CheckSquare, countKey: "tasks" },
      { id: "responsibilities", label: "Ownership", icon: Users, countKey: "responsibilities" },
      { id: "dependencies", label: "Dependencies", icon: Network, countKey: "dependencies" },
      { id: "risks", label: "Risks & Issues", icon: AlertTriangle, countKey: "risks" },
      { id: "operations", label: "Operations", icon: Activity, countKey: "operations" },
      { id: "evidence", label: "Evidence", icon: Layers, countKey: "evidence" },
    ],
  },
  {
    id: "transfer",
    label: "Transfer",
    tabs: [
      { id: "checklists", label: "Checklists", icon: ListTodo, countKey: "checklists" },
      { id: "review", label: "Sign-Off & Approval", icon: ShieldCheck, isMilestone: true },
    ],
  },
  {
    id: "output",
    label: "Output",
    tabs: [
      { id: "report", label: "Report", icon: FileText },
    ],
  },
] as const;

interface HandoverWorkspaceNavProps {
  activeTab: string;
  counts: Partial<Record<string, number>>;
  readinessData?: HandoverReadinessIntelligenceResponse | null;
  onSelectTab: (tabId: string) => void;
  className?: string;
}

export function HandoverWorkspaceNav({
  activeTab,
  counts,
  readinessData,
  onSelectTab,
  className,
}: HandoverWorkspaceNavProps) {
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const normalizedActive = activeTab === "knowledge" ? "overview" : activeTab;

  // Render count badge according to information value rules:
  // - Critical workflow alerts (blockers, mandatory items) always highlighted.
  // - Zero counts on general knowledge omitted to eliminate visual noise.
  const renderTabBadge = (tab: NavTabItem) => {
    if (tab.id === "readiness") {
      const blockers = readinessData?.blocker_count ?? 0;
      if (blockers > 0) {
        return (
          <span className="inline-flex items-center px-1.5 py-0.2 rounded-full text-[10.5px] font-bold bg-rose-100 text-rose-700 ring-1 ring-inset ring-rose-600/20">
            {blockers} {blockers === 1 ? "blocker" : "blockers"}
          </span>
        );
      }
      const score = readinessData?.overall_score;
      if (score !== undefined) {
        return (
          <span className="inline-flex items-center px-1.5 py-0.2 rounded-full text-[10.5px] font-semibold bg-slate-100 text-slate-600">
            {score}%
          </span>
        );
      }
      return null;
    }

    if (tab.id === "checklists") {
      const outstanding = readinessData?.checklist_summary?.mandatory_outstanding;
      if (outstanding && outstanding > 0) {
        return (
          <span className="inline-flex items-center px-1.5 py-0.2 rounded-full text-[10.5px] font-bold bg-amber-100 text-amber-800 ring-1 ring-inset ring-amber-600/20">
            {outstanding} open
          </span>
        );
      }
      return null;
    }

    if (tab.id === "review") {
      return (
        <span className="size-1.5 rounded-full bg-blue-600" title="Milestone" />
      );
    }

    const count = tab.countKey ? counts[tab.countKey] : undefined;
    if (count !== undefined && count > 0) {
      return (
        <span
          className={cn(
            "inline-flex items-center px-1.5 py-0.2 rounded-full text-[10.5px] font-medium transition-colors",
            normalizedActive === tab.id
              ? "bg-blue-100/80 text-blue-800 font-semibold"
              : "bg-slate-100 text-slate-600"
          )}
        >
          {count}
        </span>
      );
    }

    // Zero count on general knowledge tabs is omitted per design direction
    return null;
  };

  return (
    <nav
      aria-label="Handover Workspace Navigation"
      className={cn(
        "no-print sticky top-0 z-20 -mx-1 px-1 bg-canvas/95 backdrop-blur-md pt-1 pb-3 mb-4 border-b border-line/80 transition-all",
        className
      )}
    >
      <div
        ref={scrollContainerRef}
        role="tablist"
        className="flex items-center gap-4 overflow-x-auto scrollbar-none py-1 px-0.5"
      >
        {WORKSPACE_NAV_GROUPS.map((group, groupIdx) => (
          <div key={group.id} className="flex items-center gap-1 shrink-0">
            {/* Group Label / Visual Separator */}
            <div className="flex items-center gap-1.5 pr-1 pl-0.5">
              {groupIdx > 0 && (
                <span className="h-4 w-px bg-slate-200 mr-2 shrink-0" aria-hidden="true" />
              )}
              <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 select-none">
                {group.label}
              </span>
            </div>

            {/* Group Tabs */}
            <div className="flex items-center gap-1">
              {group.tabs.map((tab) => {
                const isActive = normalizedActive === tab.id;
                const Icon = tab.icon;

                return (
                  <button
                    key={tab.id}
                    role="tab"
                    id={`handover-tab-${tab.id}`}
                    aria-selected={isActive}
                    aria-controls={`handover-panel-${tab.id}`}
                    onClick={() => onSelectTab(tab.id)}
                    className={cn(
                      "group relative flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-150 whitespace-nowrap focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500",
                      isActive
                        ? "bg-white text-blue-700 shadow-2xs font-semibold ring-1 ring-slate-200/80 border-b-2 border-b-blue-600"
                        : "text-slate-600 hover:text-navy hover:bg-white/60 active:scale-[0.98]"
                    )}
                  >
                    {Icon && (
                      <Icon
                        className={cn(
                          "size-3.5 transition-colors shrink-0",
                          isActive
                            ? "text-blue-600"
                            : "text-slate-400 group-hover:text-slate-600"
                        )}
                      />
                    )}
                    <span>{tab.label}</span>
                    {renderTabBadge(tab)}
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </nav>
  );
}
