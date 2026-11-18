"use client";

import React from "react";
import {
  Layers,
  Clock,
  GitCompare,
  HelpCircle,
  CheckCircle2,
  XCircle,
  History,
  ShieldCheck,
} from "lucide-react";
import type { SummaryCardsProps } from "./types";

interface MetricCardConfig {
  id: string;
  label: string;
  filterKey: string;
  count: number;
  icon: React.ElementType;
  colorStyles: {
    borderActive: string;
    bgActive: string;
    iconBg: string;
    iconColor: string;
    badgeBg: string;
    badgeText: string;
  };
}

export const VerificationSummaryCards: React.FC<SummaryCardsProps> = ({
  summary,
  loading,
  activeStatusFilter,
  onSelectStatusFilter,
}) => {
  const cards: MetricCardConfig[] = [
    {
      id: "total",
      label: "Total Findings",
      filterKey: "all",
      count: summary?.total_cases ?? 0,
      icon: Layers,
      colorStyles: {
        borderActive: "border-slate-500 ring-2 ring-slate-400",
        bgActive: "bg-slate-50",
        iconBg: "bg-slate-100",
        iconColor: "text-slate-700",
        badgeBg: "bg-slate-100",
        badgeText: "text-slate-800",
      },
    },
    {
      id: "pending",
      label: "Pending Review",
      filterKey: "pending_review",
      count: summary?.pending_review ?? 0,
      icon: Clock,
      colorStyles: {
        borderActive: "border-blue-500 ring-2 ring-blue-300",
        bgActive: "bg-blue-50/50",
        iconBg: "bg-blue-100",
        iconColor: "text-blue-700",
        badgeBg: "bg-blue-100",
        badgeText: "text-blue-900",
      },
    },
    {
      id: "conflicted",
      label: "Conflicted",
      filterKey: "conflicted",
      count: summary?.conflicts_count ?? 0,
      icon: GitCompare,
      colorStyles: {
        borderActive: "border-purple-500 ring-2 ring-purple-300",
        bgActive: "bg-purple-50/50",
        iconBg: "bg-purple-100",
        iconColor: "text-purple-700",
        badgeBg: "bg-purple-100",
        badgeText: "text-purple-900",
      },
    },
    {
      id: "unresolved",
      label: "Unresolved",
      filterKey: "unresolved",
      count: summary?.unresolved ?? 0,
      icon: HelpCircle,
      colorStyles: {
        borderActive: "border-amber-500 ring-2 ring-amber-300",
        bgActive: "bg-amber-50/50",
        iconBg: "bg-amber-100",
        iconColor: "text-amber-700",
        badgeBg: "bg-amber-100",
        badgeText: "text-amber-900",
      },
    },
    {
      id: "approved",
      label: "Approved / Verified",
      filterKey: "verified",
      count: summary?.approved ?? 0,
      icon: CheckCircle2,
      colorStyles: {
        borderActive: "border-emerald-500 ring-2 ring-emerald-300",
        bgActive: "bg-emerald-50/50",
        iconBg: "bg-emerald-100",
        iconColor: "text-emerald-700",
        badgeBg: "bg-emerald-100",
        badgeText: "text-emerald-900",
      },
    },
    {
      id: "rejected",
      label: "Rejected",
      filterKey: "rejected",
      count: summary?.rejected ?? 0,
      icon: XCircle,
      colorStyles: {
        borderActive: "border-rose-500 ring-2 ring-rose-300",
        bgActive: "bg-rose-50/50",
        iconBg: "bg-rose-100",
        iconColor: "text-rose-700",
        badgeBg: "bg-rose-100",
        badgeText: "text-rose-900",
      },
    },
    {
      id: "stale",
      label: "Stale Findings",
      filterKey: "stale",
      count: summary?.stale_count ?? 0,
      icon: History,
      colorStyles: {
        borderActive: "border-orange-500 ring-2 ring-orange-300",
        bgActive: "bg-orange-50/50",
        iconBg: "bg-orange-100",
        iconColor: "text-orange-700",
        badgeBg: "bg-orange-100",
        badgeText: "text-orange-900",
      },
    },
    {
      id: "handover_eligible",
      label: "Handover Eligible",
      filterKey: "eligible",
      count: summary?.handover_eligible_count ?? 0,
      icon: ShieldCheck,
      colorStyles: {
        borderActive: "border-teal-500 ring-2 ring-teal-300",
        bgActive: "bg-teal-50/50",
        iconBg: "bg-teal-100",
        iconColor: "text-teal-700",
        badgeBg: "bg-teal-100",
        badgeText: "text-teal-900",
      },
    },
  ];

  return (
    <div className="bg-slate-50/70 border-b border-slate-200 px-6 py-3.5">
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2.5">
        {cards.map((card) => {
          const Icon = card.icon;
          const isSelected =
            (card.filterKey === "all" && activeStatusFilter === "all") ||
            (card.filterKey !== "all" && activeStatusFilter === card.filterKey);

          return (
            <button
              key={card.id}
              type="button"
              onClick={() => onSelectStatusFilter(card.filterKey)}
              className={`p-2.5 rounded-xl border text-left transition relative cursor-pointer group shadow-2xs hover:shadow-xs ${
                isSelected
                  ? `${card.colorStyles.borderActive} ${card.colorStyles.bgActive} bg-white`
                  : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50/80"
              }`}
            >
              <div className="flex items-center justify-between mb-1.5">
                <div
                  className={`size-6 rounded-md flex items-center justify-center ${card.colorStyles.iconBg} ${card.colorStyles.iconColor} transition group-hover:scale-105`}
                >
                  <Icon className="size-3.5" />
                </div>
                {loading ? (
                  <div className="h-4 w-7 bg-slate-200 rounded animate-pulse" />
                ) : (
                  <span
                    className={`text-sm font-extrabold ${
                      card.count > 0 ? "text-slate-900" : "text-slate-400"
                    }`}
                  >
                    {card.count}
                  </span>
                )}
              </div>
              <div className="text-[11px] font-medium text-slate-600 truncate" title={card.label}>
                {card.label}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
};
