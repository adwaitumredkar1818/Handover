"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  AlertTriangle,
  Award,
  FileCheck2,
  GitBranch,
  Layers,
  RefreshCw,
  Scale,
  Shield,
  Sparkles,
  Users,
} from "lucide-react";
import { api } from "../../lib/api";

interface KnowledgeQualityPanelProps {
  projectId: string;
}

interface QualityGap {
  type: string;
  severity: string;
  title: string;
  description: string;
  recommendation: string;
}

interface QualityData {
  dimension_scores: Record<string, number>;
  overall_score: number;
  gaps: QualityGap[];
  total_items: number;
}

const DIMENSION_METADATA: Record<
  string,
  { label: string; weight: string; icon: React.ReactNode; description: string }
> = {
  evidence_coverage: {
    label: "Evidence Coverage",
    weight: "15%",
    icon: <FileCheck2 className="w-4 h-4 text-blue-600" />,
    description: "Ratio of knowledge items grounded with source evidence",
  },
  verification_coverage: {
    label: "Verification Coverage",
    weight: "15%",
    icon: <Shield className="w-4 h-4 text-emerald-600" />,
    description: "Proportion of findings reviewed and verified by humans",
  },
  decision_traceability: {
    label: "Decision Traceability",
    weight: "12%",
    icon: <GitBranch className="w-4 h-4 text-indigo-600" />,
    description: "5-stage causal chains linking problem, options, and commits",
  },
  ownership_coverage: {
    label: "Ownership Coverage",
    weight: "12%",
    icon: <Users className="w-4 h-4 text-violet-600" />,
    description: "Technical components mapped to active owners/maintainers",
  },
  dependency_clarity: {
    label: "Dependency Clarity",
    weight: "10%",
    icon: <Layers className="w-4 h-4 text-amber-600" />,
    description: "Free of dependency cycles, ambiguous edges, or untracked blockers",
  },
  documentation_coverage: {
    label: "Documentation Coverage",
    weight: "10%",
    icon: <Scale className="w-4 h-4 text-sky-600" />,
    description: "Coverage across architecture, decisions, and system requirements",
  },
  operational_readiness: {
    label: "Operational Readiness",
    weight: "10%",
    icon: <Award className="w-4 h-4 text-teal-600" />,
    description: "Documented operational runbooks, environment setups, and deploy steps",
  },
  risk_coverage: {
    label: "Risk Coverage",
    weight: "8%",
    icon: <AlertTriangle className="w-4 h-4 text-rose-600" />,
    description: "Identified project risks with documented mitigation strategies",
  },
  knowledge_freshness: {
    label: "Knowledge Freshness",
    weight: "8%",
    icon: <Sparkles className="w-4 h-4 text-amber-600" />,
    description: "Active knowledge without stale, revoked, or outdated artifacts",
  },
};

export function KnowledgeQualityPanel({ projectId }: KnowledgeQualityPanelProps) {
  const [data, setData] = useState<QualityData | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadQuality = useCallback(
    async (isRefresh = false) => {
      if (isRefresh) setRefreshing(true);
      else setLoading(true);
      setError(null);

      try {
        const res = await api.knowledgeIntelligence.getQuality(projectId);
        const overall =
          typeof res.overall_quality_score === "number"
            ? res.overall_quality_score
            : typeof res.overall_score === "number"
            ? res.overall_score
            : 0;
        const gaps = Array.isArray(res.identified_gaps)
          ? res.identified_gaps
          : Array.isArray(res.gaps)
          ? res.gaps
          : [];
        setData({
          dimension_scores: res.dimension_scores || {},
          overall_score: overall,
          gaps,
          total_items: res.total_items ?? 0,
        });
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load knowledge quality metrics.");
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [projectId]
  );

  useEffect(() => {
    loadQuality();
  }, [loadQuality]);

  const getScoreColor = (score: number) => {
    if (score >= 80) return "text-emerald-600 bg-emerald-500";
    if (score >= 60) return "text-amber-600 bg-amber-500";
    return "text-rose-600 bg-rose-500";
  };

  const getBarBg = (score: number) => {
    if (score >= 80) return "bg-emerald-500";
    if (score >= 60) return "bg-amber-500";
    return "bg-rose-500";
  };

  return (
    <div className="flex flex-col h-full bg-[#F6F8FC] border border-slate-200 rounded-xl overflow-hidden">
      {/* Header */}
      <div className="p-4 bg-white border-b border-slate-200 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Scale className="w-5 h-5 text-indigo-600" />
            <h2 className="text-base font-semibold text-slate-900">
              9-Dimensional Knowledge Quality Engine
            </h2>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Deterministic evaluation of project knowledge completeness, provenance grounding, and handover readiness.
          </p>
        </div>

        <button
          onClick={() => loadQuality(true)}
          disabled={loading || refreshing}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-700 bg-white border border-slate-300 rounded-md hover:bg-slate-50 transition self-start md:self-auto cursor-pointer disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? "animate-spin" : ""}`} />
          Refresh Assessment
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-5">
        {loading && !refreshing && (
          <div className="space-y-4">
            <div className="p-6 bg-white rounded-lg border border-slate-200 animate-pulse h-28"></div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {[1, 2, 3, 4, 5, 6, 7, 8, 9].map((i) => (
                <div key={i} className="p-4 bg-white rounded-lg border border-slate-200 animate-pulse h-24"></div>
              ))}
            </div>
          </div>
        )}

        {error && (
          <div className="p-4 rounded-lg bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-center justify-between">
            <div className="flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
              <span>{error}</span>
            </div>
            <button onClick={() => loadQuality()} className="underline font-medium hover:text-rose-900 ml-4 cursor-pointer">
              Retry
            </button>
          </div>
        )}

        {!loading && data && (
          <>
            {/* Overall Score Banner */}
            <div className="p-5 bg-white rounded-lg border border-slate-200 shadow-xs flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div className="space-y-1">
                <span className="text-xs font-medium text-slate-500 uppercase tracking-wider">
                  Overall Knowledge Quality Score
                </span>
                <div className="flex items-baseline gap-2">
                  <span className={`text-3xl font-extrabold ${getScoreColor(data.overall_score).split(" ")[0]}`}>
                    {Math.round(data.overall_score)}%
                  </span>
                  <span className="text-xs text-slate-500">
                    across {data.total_items} evaluated project finding{data.total_items !== 1 ? "s" : ""}
                  </span>
                </div>
                <p className="text-xs text-slate-600 max-w-xl">
                  {data.overall_score >= 80
                    ? "Excellent quality baseline. Project knowledge is well-grounded, verified, and ready for transition."
                    : data.overall_score >= 60
                    ? "Adequate baseline with gaps. Address unverified claims or unowned components before final handover sign-off."
                    : "Attention required. Significant gaps in human verification, traceability, or ownership detected."}
                </p>
              </div>

              <div className="w-full md:w-64 space-y-1.5">
                <div className="flex justify-between text-xs text-slate-500">
                  <span>Quality Progress</span>
                  <span className="font-semibold text-slate-700">{Math.round(data.overall_score)} / 100</span>
                </div>
                <div className="w-full h-3 bg-slate-100 rounded-full overflow-hidden">
                  <div
                    className={`h-full ${getBarBg(data.overall_score)} transition-all duration-500`}
                    style={{ width: `${Math.min(100, Math.max(0, data.overall_score))}%` }}
                  ></div>
                </div>
              </div>
            </div>

            {/* 9 Dimensions Grid */}
            <div>
              <h3 className="text-xs font-semibold text-slate-700 uppercase tracking-wider mb-3">
                9 Quality & Completeness Dimensions
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                {Object.entries(DIMENSION_METADATA).map(([key, meta]) => {
                  const score = data.dimension_scores[key] ?? 0;
                  return (
                    <div
                      key={key}
                      className="p-3.5 bg-white rounded-lg border border-slate-200 shadow-xs flex flex-col justify-between gap-3"
                    >
                      <div>
                        <div className="flex items-center justify-between mb-1">
                          <div className="flex items-center gap-1.5">
                            {meta.icon}
                            <span className="text-xs font-semibold text-slate-900">
                              {meta.label}
                            </span>
                          </div>
                          <span className="text-[10px] font-medium text-slate-400">
                            wt {meta.weight}
                          </span>
                        </div>
                        <p className="text-[11px] text-slate-500 leading-snug">
                          {meta.description}
                        </p>
                      </div>

                      <div className="space-y-1 pt-2 border-t border-slate-100">
                        <div className="flex items-center justify-between text-xs">
                          <span className="text-slate-500">Completeness</span>
                          <span className={`font-bold ${getScoreColor(score).split(" ")[0]}`}>
                            {score}%
                          </span>
                        </div>
                        <div className="w-full h-1.5 bg-slate-100 rounded-full overflow-hidden">
                          <div
                            className={`h-full ${getBarBg(score)} transition-all duration-300`}
                            style={{ width: `${Math.min(100, Math.max(0, score))}%` }}
                          ></div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Actionable Gaps Section */}
            {data.gaps && data.gaps.length > 0 && (
              <div className="space-y-3 pt-2">
                <div className="flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 text-amber-500" />
                  <h3 className="text-xs font-semibold text-slate-700 uppercase tracking-wider">
                    Actionable Knowledge Gaps ({data.gaps.length})
                  </h3>
                </div>

                <div className="space-y-2">
                  {data.gaps.map((gap, idx) => (
                    <div
                      key={idx}
                      className="p-3.5 bg-white rounded-lg border border-slate-200 flex flex-col md:flex-row md:items-start justify-between gap-3 text-xs"
                    >
                      <div className="space-y-1 max-w-2xl">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-slate-900">
                            {gap.title}
                          </span>
                          <span
                            className={`px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider rounded ${
                              gap.severity === "high"
                                ? "bg-rose-100 text-rose-800"
                                : gap.severity === "medium"
                                ? "bg-amber-100 text-amber-800"
                                : "bg-slate-100 text-slate-700"
                            }`}
                          >
                            {gap.severity} severity
                          </span>
                        </div>
                        <p className="text-slate-600">{gap.description}</p>
                      </div>

                      <div className="bg-slate-50 p-2.5 rounded border border-slate-200 text-[11px] md:min-w-[240px]">
                        <span className="font-semibold text-indigo-600 block mb-0.5">
                          Recommended Action:
                        </span>
                        <span className="text-slate-600">{gap.recommendation}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
