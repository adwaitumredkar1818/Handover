/**
 * Typed client API for Conflict Management Workspace.
 */

import { request } from "./api";

export interface ConflictDashboardMetrics {
  project_id: string;
  total_conflicts: number;
  open_conflicts: number;
  under_investigation: number;
  awaiting_context: number;
  resolved: number;
  reopened: number;
  critical_priority: number;
  high_priority: number;
  medium_priority: number;
  low_priority: number;
  category_counts: Record<string, number>;
  attention_required_count: number;
}

export interface ConflictQueueItem {
  id: string;
  project_id: string;
  case_id: string;
  conflict_type: string;
  priority: "critical" | "high" | "medium" | "low" | string;
  resolution_state: "unresolved" | "open" | "under_investigation" | "awaiting_context" | "resolved" | "reconciled" | "superseded" | "dismissed" | "reopened" | string;
  explanation: string;
  temporal_comparison: string;
  side_a_title: string | null;
  side_a_provider: string | null;
  side_b_title: string | null;
  side_b_provider: string | null;
  assigned_reviewer_id: string | null;
  assigned_reviewer_name: string | null;
  related_finding_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ConflictListResponse {
  items: ConflictQueueItem[];
  total_count: number;
  offset: number;
  limit: number;
}

export interface ConflictEvidenceSide {
  title: string;
  provider: string | null;
  claim_text: string;
  evidence_item_id: string | null;
  chunk_id: string | null;
  source_timestamp: string | null;
  source_url: string | null;
  author: string | null;
  acl_scope: string;
  is_accessible: boolean;
  redaction_reason: string | null;
}

export interface ConflictAuditHistoryItem {
  id: string;
  action: string;
  actor_id: string | null;
  actor_name: string | null;
  notes: string | null;
  created_at: string;
}

export interface ConflictDetailResponse {
  id: string;
  project_id: string;
  case_id: string;
  conflict_type: string;
  priority: string;
  resolution_state: string;
  explanation: string;
  temporal_comparison: string;
  side_a: ConflictEvidenceSide;
  side_b: ConflictEvidenceSide;
  assigned_reviewer_id: string | null;
  assigned_reviewer_name: string | null;
  investigation_notes: string | null;
  resolution_strategy: string | null;
  authoritative_claim_text: string | null;
  resolution_notes: string | null;
  resolved_by_user_id: string | null;
  resolved_by_user_name: string | null;
  resolved_at: string | null;
  related_finding_id: string | null;
  related_finding_title: string | null;
  finding_domain: string | null;
  created_at: string;
  updated_at: string;
  audit_history: ConflictAuditHistoryItem[];
}

export interface ConflictFilterParams {
  conflict_type?: string;
  resolution_state?: string;
  priority?: string;
  assigned_to?: string;
  search?: string;
  limit?: number;
  offset?: number;
}

export interface ResolveConflictPayload {
  resolution_strategy: "side_a_authoritative" | "side_b_authoritative" | "reconciled" | "coexisting_variants" | "dismissed_false_positive" | string;
  resolution_notes: string;
  authoritative_claim_text?: string;
  sync_finding?: boolean;
}

export const conflictsApi = {
  async getDashboard(projectId: string): Promise<ConflictDashboardMetrics> {
    return request<ConflictDashboardMetrics>(`/projects/${projectId}/conflicts/dashboard`);
  },

  async list(projectId: string, filters: ConflictFilterParams = {}): Promise<ConflictListResponse> {
    const qs = new URLSearchParams();
    if (filters.conflict_type && filters.conflict_type !== "all") {
      qs.append("conflict_type", filters.conflict_type);
    }
    if (filters.resolution_state && filters.resolution_state !== "all") {
      qs.append("resolution_state", filters.resolution_state);
    }
    if (filters.priority && filters.priority !== "all") {
      qs.append("priority", filters.priority);
    }
    if (filters.assigned_to) {
      qs.append("assigned_to", filters.assigned_to);
    }
    if (filters.search) {
      qs.append("search", filters.search);
    }
    if (filters.limit) {
      qs.append("limit", filters.limit.toString());
    }
    if (filters.offset !== undefined) {
      qs.append("offset", filters.offset.toString());
    }
    const queryStr = qs.toString();
    return request<ConflictListResponse>(
      `/projects/${projectId}/conflicts${queryStr ? `?${queryStr}` : ""}`
    );
  },

  async getDetails(projectId: string, conflictId: string): Promise<ConflictDetailResponse> {
    return request<ConflictDetailResponse>(`/projects/${projectId}/conflicts/${conflictId}`);
  },

  async assign(
    projectId: string,
    conflictId: string,
    reviewerId: string | null,
    notes?: string
  ): Promise<ConflictDetailResponse> {
    return request<ConflictDetailResponse>(`/projects/${projectId}/conflicts/${conflictId}/assign`, {
      method: "POST",
      body: JSON.stringify({ reviewer_id: reviewerId, notes }),
    });
  },

  async investigate(projectId: string, conflictId: string, notes?: string): Promise<ConflictDetailResponse> {
    return request<ConflictDetailResponse>(`/projects/${projectId}/conflicts/${conflictId}/investigate`, {
      method: "POST",
      body: JSON.stringify({ notes }),
    });
  },

  async requestContext(
    projectId: string,
    conflictId: string,
    contextQueries: string[],
    notes?: string
  ): Promise<ConflictDetailResponse> {
    return request<ConflictDetailResponse>(`/projects/${projectId}/conflicts/${conflictId}/request-context`, {
      method: "POST",
      body: JSON.stringify({ context_queries: contextQueries, notes }),
    });
  },

  async addNotes(projectId: string, conflictId: string, notes: string): Promise<ConflictDetailResponse> {
    return request<ConflictDetailResponse>(`/projects/${projectId}/conflicts/${conflictId}/notes`, {
      method: "POST",
      body: JSON.stringify({ notes }),
    });
  },

  async resolve(
    projectId: string,
    conflictId: string,
    payload: ResolveConflictPayload
  ): Promise<ConflictDetailResponse> {
    return request<ConflictDetailResponse>(`/projects/${projectId}/conflicts/${conflictId}/resolve`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async reopen(projectId: string, conflictId: string, reason: string): Promise<ConflictDetailResponse> {
    return request<ConflictDetailResponse>(`/projects/${projectId}/conflicts/${conflictId}/reopen`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    });
  },

  async sync(projectId: string): Promise<{ status: string; assessment: any; metrics: ConflictDashboardMetrics }> {
    return request<{ status: string; assessment: any; metrics: ConflictDashboardMetrics }>(`/projects/${projectId}/conflicts/sync`, {
      method: "POST",
    });
  },
};
