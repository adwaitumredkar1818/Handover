"use client";

import { getApiBaseUrl } from "./api";

export type VerificationStatus =
  | "candidate"
  | "pending_review"
  | "conflicted"
  | "unresolved"
  | "verified"
  | "rejected";

export type VerificationCategory =
  | "extracted_finding_verification"
  | "conflicting_evidence"
  | "missing_evidence"
  | "outdated_information"
  | "uncertain_relationships"
  | "duplicate_findings";

export interface VerificationSummary {
  project_id: string;
  total_cases: number;
  candidate_count: number;
  pending_review_count: number;
  conflicted_count: number;
  unresolved_count: number;
  verified_count: number;
  rejected_count: number;
  open_issues_count: number;
  open_conflicts_count: number;
  pending_context_requests_count: number;
}

export interface VerificationQueueItem {
  id: string;
  project_id: string;
  target_type: string;
  target_id: string;
  title: string;
  domain: string;
  current_claim: string;
  original_ai_claim: string;
  case_status: VerificationStatus;
  priority: string;
  person_name: string | null;
  source_provider: string | null;
  assigned_reviewer_id: string | null;
  assigned_reviewer_name: string | null;
  evidence_count: number;
  open_issues_count: number;
  verification_categories: VerificationCategory[];
  model_confidence: number | null;
  uncertainty_note: string | null;
  evidence_completeness: string | null;
  priority_reason?: string | null;
  recommendation_action?: string | null;
  corroboration_level?: string | null;
  freshness_status?: string | null;
  version: number;
  last_reviewed_at: string | null;
  updated_at: string;
  created_at: string;
}

export interface VerificationQueueResponse {
  items: VerificationQueueItem[];
  total: number;
  limit: number;
  offset: number;
  available_domains: string[];
  available_sources: string[];
  available_people: string[];
  case_details?: Record<string, VerificationCaseDetail>;
}

export interface EvidenceReferenceDetail {
  id: string;
  evidence_item_id: string;
  evidence_chunk_id: string | null;
  source_provider: string;
  source_name: string;
  original_title: string;
  author: string | null;
  timestamp: string | null;
  original_source_url: string | null;
  excerpt: string | null;
  location_label: string | null;
  relationship_to_finding: string;
  acl_scope: string;
}

export interface VerificationIssueDetail {
  id: string;
  verification_category: VerificationCategory;
  issue_type: string;
  severity: string;
  description: string;
  detection_method: string;
  resolution_state: string;
  details: Record<string, unknown>;
  conflicting_evidence_id: string | null;
  created_at: string;
  resolved_at: string | null;
}

export interface ConflictClaimSide {
  evidence_item_id: string;
  source_provider: string;
  original_title: string;
  author: string | null;
  timestamp: string | null;
  original_source_url: string | null;
  claim_text: string;
}

export interface VerificationConflictPreview {
  id: string;
  conflict_type: string;
  explanation: string;
  temporal_comparison: string;
  resolution_state: string;
  side_a: ConflictClaimSide | null;
  side_b: ConflictClaimSide | null;
  restricted_by_acl: boolean;
  created_at: string;
}

export interface VerificationRevisionDetail {
  id: string;
  revision_number: number;
  claim_text: string;
  domain: string;
  is_ai_original: boolean;
  edited_by_user_id: string | null;
  edited_by_name: string | null;
  edit_reason: string | null;
  created_at: string;
}

export interface VerificationReviewEventDetail {
  id: string;
  reviewer_user_id: string;
  reviewer_name: string | null;
  action: string;
  previous_status: string;
  new_status: string;
  case_version: number;
  decision_reason: string | null;
  review_notes: string | null;
  created_at: string;
}

export interface VerificationContextRequestDetail {
  id: string;
  case_id: string;
  requested_by_user_id: string;
  requested_by_name: string | null;
  requested_from_user_id: string;
  requested_from_name: string | null;
  question: string;
  requested_information_type: string;
  status: string;
  response_text: string | null;
  response_evidence_id: string | null;
  responded_at: string | null;
  created_at: string;
}

export interface CompletenessAssessment {
  score: number;
  level: "complete" | "partial" | "sparse" | "missing";
  explanation: string;
  missing_elements: string[];
  recommendations: string[];
  direct_support: boolean;
  evidence_accessible: boolean;
  excerpt_specificity: string;
}

export interface ReliabilityAssessment {
  score: number;
  tier: "high" | "medium" | "low" | "uncertain";
  explanation: string;
  factors: string[];
  provider_authorities: Record<string, number>;
  primary_provider: string;
}

export interface FreshnessAssessment {
  status: "fresh" | "aging" | "stale" | "outdated" | "superseded" | "unknown";
  age_days: number | null;
  explanation: string;
  superseded_by_record_title: string | null;
  reverification_required: boolean;
  recommendations: string[];
}

export interface CorroborationAssessment {
  level: "strong_cross_source" | "moderate_multi_source" | "single_source" | "uncorroborated";
  independent_sources_count: number;
  supporting_providers: string[];
  opposing_providers: string[];
  explanation: string;
}

export interface ContradictionCandidate {
  conflict_type: string;
  explanation: string;
  severity: string;
  side_a_title: string;
  side_a_claim: string;
  side_a_provider: string;
  side_b_title: string;
  side_b_claim: string;
  side_b_provider: string;
}

export interface ContradictionAnalysis {
  has_contradiction: boolean;
  contradiction_count: number;
  summary: string;
  contradictions: ContradictionCandidate[];
}

export interface VerificationRecommendation {
  action: string;
  headline: string;
  reason: string;
  supporting_factors: string[];
  confidence_tier: "high" | "medium" | "low";
}

export interface MonitoringStatus {
  last_monitored_at?: string;
  last_evidence_change_id?: string;
  change_type?: string;
  reverification_triggered?: boolean;
  reverification_reason?: string;
}

export interface VerificationCaseDetail {
  id: string;
  project_id: string;
  target_type: string;
  target_id: string;
  title: string;
  domain: string;
  original_ai_claim: string;
  current_claim: string;
  case_status: VerificationStatus;
  priority: string;
  person_name: string | null;
  source_provider: string | null;
  assigned_reviewer_id: string | null;
  assigned_reviewer_name: string | null;
  model_confidence: number | null;
  uncertainty_note: string | null;
  evidence_completeness: string | null;
  version: number;
  handover_eligible: boolean;
  handover_eligibility_reason: string;
  restricted_evidence_count: number;
  evidence_references: EvidenceReferenceDetail[];
  issues: VerificationIssueDetail[];
  conflicts: VerificationConflictPreview[];
  revisions: VerificationRevisionDetail[];
  review_events: VerificationReviewEventDetail[];
  context_requests: VerificationContextRequestDetail[];
  machine_assessment?: Record<string, unknown>;
  priority_reason?: string | null;
  recommendation?: VerificationRecommendation | null;
  completeness_assessment?: CompletenessAssessment | null;
  reliability_assessment?: ReliabilityAssessment | null;
  freshness_assessment?: FreshnessAssessment | null;
  corroboration_assessment?: CorroborationAssessment | null;
  contradiction_analysis?: ContradictionAnalysis | null;
  monitoring_status?: MonitoringStatus | null;
  last_assessed_at: string | null;
  last_reviewed_at: string | null;
  resolved_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface QueueFilters {
  status?: string;
  domain?: string;
  person?: string;
  source?: string;
  reviewer_id?: string;
  category?: string;
  search?: string;
  sort_by?: string;
  sort_dir?: string;
  limit?: number;
  offset?: number;
}

export const DEFAULT_VERIFICATION_FILTERS: QueueFilters = {
  status: "all",
  domain: "all",
  person: "all",
  source: "all",
  reviewer_id: "all",
  category: "all",
  search: "",
  sort_by: "updated_at",
  sort_dir: "desc",
};

const inFlightGetRequests = new Map<string, Promise<unknown>>();

function dedupedGet<T>(key: string, fetcher: () => Promise<T>): Promise<T> {
  const existing = inFlightGetRequests.get(key) as Promise<T> | undefined;
  if (existing) return existing;
  const pending = fetcher().finally(() => {
    inFlightGetRequests.delete(key);
  });
  inFlightGetRequests.set(key, pending);
  return pending;
}

async function vcRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const base = getApiBaseUrl();
  const token =
    typeof window !== "undefined" ? localStorage.getItem("handover_access_token") : null;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((init.headers as Record<string, string>) || {}),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${base}${path}`, {
    ...init,
    credentials: "include",
    headers,
  });

  if (!res.ok) {
    let message = `Request failed (${res.status})`;
    try {
      const data = await res.json();
      message = data?.error?.message || data?.detail || message;
    } catch {
      // ignore JSON parse failure
    }
    throw new Error(message);
  }
  return (await res.json()) as T;
}

export interface VerifyAllFindingsRequest {
  status?: string;
  domain?: string;
  person?: string;
  source?: string;
  reviewer_id?: string;
  category?: string;
  search?: string;
  reviewer_note?: string;
  decision_reason?: string;
}

export interface VerifyAllFindingsResponse {
  project_id: string;
  verified_count: number;
  knowledge_items_verified: number;
  relationships_verified: number;
  already_verified_count: number;
  summary: VerificationSummary;
}

export const verificationApi = {
  getSummary(projectId: string) {
    const path = `/projects/${projectId}/verification/summary`;
    return dedupedGet(path, () => vcRequest<VerificationSummary>(path));
  },
  getQueue(projectId: string, filters: QueueFilters = {}) {
    const qs = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "" && v !== "all") {
        qs.set(k, String(v));
      }
    });
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    const path = `/projects/${projectId}/verification/queue${suffix}`;
    return dedupedGet(path, () => vcRequest<VerificationQueueResponse>(path));
  },
  getCaseDetail(projectId: string, caseId: string) {
    return vcRequest<VerificationCaseDetail>(
      `/projects/${projectId}/verification/cases/${caseId}`
    );
  },
  syncAndAssess(projectId: string) {
    return vcRequest<{
      project_id: string;
      cases_created: number;
      cases_updated: number;
      cases_assessed: number;
      issues_detected: number;
    }>(`/projects/${projectId}/verification/sync`, { method: "POST" });
  },
  approveCase(
    projectId: string,
    caseId: string,
    payload: { reviewer_note?: string; decision_reason?: string }
  ) {
    return vcRequest<VerificationCaseDetail>(
      `/projects/${projectId}/verification/cases/${caseId}/approve`,
      { method: "POST", body: JSON.stringify(payload) }
    );
  },
  rejectCase(
    projectId: string,
    caseId: string,
    payload: { decision_reason: string; reviewer_note?: string }
  ) {
    return vcRequest<VerificationCaseDetail>(
      `/projects/${projectId}/verification/cases/${caseId}/reject`,
      { method: "POST", body: JSON.stringify(payload) }
    );
  },
  editFinding(
    projectId: string,
    caseId: string,
    payload: {
      current_claim: string;
      domain?: string;
      edit_reason: string;
      reviewer_note?: string;
    }
  ) {
    return vcRequest<VerificationCaseDetail>(
      `/projects/${projectId}/verification/cases/${caseId}/finding`,
      { method: "PATCH", body: JSON.stringify(payload) }
    );
  },
  requestContext(
    projectId: string,
    caseId: string,
    payload: {
      question: string;
      requested_from_user_id: string;
      requested_information_type?: string;
      reviewer_note?: string;
    }
  ) {
    return vcRequest<VerificationCaseDetail>(
      `/projects/${projectId}/verification/cases/${caseId}/request-context`,
      { method: "POST", body: JSON.stringify(payload) }
    );
  },
  respondContextRequest(
    projectId: string,
    requestId: string,
    payload: { response_text: string; response_evidence_id?: string; excerpt?: string }
  ) {
    return vcRequest<VerificationContextRequestDetail>(
      `/projects/${projectId}/verification/context-requests/${requestId}/respond`,
      { method: "POST", body: JSON.stringify(payload) }
    );
  },
  markUnresolved(
    projectId: string,
    caseId: string,
    payload: { decision_reason: string; reviewer_note?: string }
  ) {
    return vcRequest<VerificationCaseDetail>(
      `/projects/${projectId}/verification/cases/${caseId}/mark-unresolved`,
      { method: "POST", body: JSON.stringify(payload) }
    );
  },
  assignReviewer(
    projectId: string,
    caseId: string,
    assigned_reviewer_id: string | null
  ) {
    return vcRequest<VerificationCaseDetail>(
      `/projects/${projectId}/verification/cases/${caseId}/assign`,
      { method: "POST", body: JSON.stringify({ assigned_reviewer_id }) }
    );
  },
  verifyAll(
    projectId: string,
    payload: VerifyAllFindingsRequest = {}
  ) {
    return vcRequest<VerifyAllFindingsResponse>(
      `/projects/${projectId}/verification/verify-all`,
      { method: "POST", body: JSON.stringify(payload) }
    );
  },
};
