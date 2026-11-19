/**
 * Verification Center Strict TypeScript Definitions
 * 1-to-1 parity with Backend Pydantic Schemas and REST API Contracts
 * (Phase 1 Architecture, Phase 2 Domain, Phase 3 Intelligence)
 */

export type UUID = string;

export type VerificationTargetType = "knowledge_item" | "relationship";

export type VerificationCaseStatus =
  | "candidate"
  | "pending_review"
  | "in_review"
  | "verified"
  | "conflicted"
  | "rejected"
  | "unresolved"
  | "archived";

export type MachineAssessmentStatus = "passed" | "issues_detected" | "critical_flaws";

export type VerificationPriority = "critical" | "high" | "medium" | "low";

export type IssueType =
  | "unsupported_claim"
  | "missing_evidence"
  | "contradictory_sources"
  | "stale_knowledge"
  | "uncertain_relationship"
  | "revoked_source_access"
  | "low_confidence_extraction"
  | "duplicate_record";

export type IssueSeverity = "critical" | "high" | "medium" | "low";

export type IssueResolutionState = "open" | "resolved" | "dismissed" | "acknowledged";

export type ConflictType =
  | "status_conflict"
  | "technical_conflict"
  | "decision_conflict"
  | "temporal_conflict"
  | "ownership_conflict";

export type ConflictResolutionState = "unresolved" | "reconciled" | "superseded" | "dismissed";

export type TemporalComparison = "a_supersedes_b" | "b_supersedes_a" | "simultaneous" | "ambiguous";

export type ContextRequestStatus = "pending" | "responded" | "expired" | "refused";

export interface SourceLocation {
  page?: number;
  page_number?: number;
  chunk_index?: number;
  paragraph?: number;
  line_start?: number;
  line_end?: number;
  commit_hash?: string;
  pull_request_number?: number;
  ticket_key?: string;
  channel?: string;
  [key: string]: unknown;
}

export interface VerificationIssue {
  id: UUID;
  case_id: UUID;
  issue_type: IssueType | string;
  severity: IssueSeverity | string;
  description: string;
  detection_method: string;
  details_json: Record<string, unknown>;
  conflicting_evidence_id?: UUID | null;
  conflicting_chunk_id?: UUID | null;
  resolution_state: IssueResolutionState | string;
  resolution_reason?: string | null;
  resolved_by_user_id?: UUID | null;
  resolved_at?: string | null;
  created_at: string;
}

export interface VerificationConflictItem {
  id: UUID;
  case_id: UUID;
  conflict_type: ConflictType | string;
  claim_a_text: string;
  claim_a_source_evidence_id: UUID;
  claim_a_chunk_id?: UUID | null;
  claim_a_source_timestamp?: string | null;
  claim_a_source_title?: string | null;
  claim_a_source_type?: string | null;
  claim_b_text: string;
  claim_b_source_evidence_id: UUID;
  claim_b_chunk_id?: UUID | null;
  claim_b_source_timestamp?: string | null;
  claim_b_source_title?: string | null;
  claim_b_source_type?: string | null;
  explanation: string;
  temporal_comparison: TemporalComparison | string;
  resolution_state: ConflictResolutionState | string;
  resolution_notes?: string | null;
  resolved_by_user_id?: UUID | null;
  resolved_at?: string | null;
  created_at: string;
  target_id?: UUID | null;
  target_type?: string | null;
  target_title?: string | null;
  target_category?: string | null;
}

export interface VerificationReviewEvent {
  id: UUID;
  case_id: UUID;
  reviewer_user_id: UUID;
  action: string;
  previous_status: string;
  new_status: string;
  review_notes?: string | null;
  event_type?: string | null;
  notes?: string | null;
  finding_patch_json?: Record<string, unknown> | null;
  previous_snapshot_json?: Record<string, unknown> | null;
  new_snapshot_json?: Record<string, unknown> | null;
  correlation_id: string;
  created_at: string;
}

export interface VerificationContextRequest {
  id: UUID;
  case_id: UUID;
  requested_by_user_id: UUID;
  requested_from_user_id: UUID;
  question: string;
  requested_information_type: string;
  status: ContextRequestStatus | string;
  response_text?: string | null;
  response_evidence_id?: UUID | null;
  responded_at?: string | null;
  created_at: string;
}

export interface VerificationCaseItem {
  id: UUID;
  organisation_id: UUID;
  project_id: UUID;
  target_type: VerificationTargetType | string;
  target_id: UUID;
  case_status: VerificationCaseStatus | string;
  machine_assessment_status: MachineAssessmentStatus | string;
  priority: VerificationPriority | string;
  assigned_reviewer_id?: UUID | null;
  assigned_to_user_id?: UUID | null;
  machine_assessment_json: Record<string, unknown>;
  version: number;
  open_issues_count: number;
  open_conflicts_count: number;
  last_assessed_at?: string | null;
  last_reviewed_at?: string | null;
  resolved_at?: string | null;
  created_at: string;
  updated_at: string;

  // Convenient projections
  title?: string | null;
  summary?: string | null;
  domain?: string | null;
  category?: string | null;
  confidence_score?: number | null;
  finding?: {
    title?: string | null;
    summary?: string | null;
    domain?: string | null;
    category?: string | null;
  } | null;
  status?: string | null;
  risk_level?: string | null;
  issue_count?: number | null;
}

export interface VerificationCaseDetailTargetData {
  id?: UUID;
  title?: string;
  summary?: string;
  knowledge_domain?: string;
  category?: string;
  epistemic_status?: string;
  review_status?: string;
  confidence_score?: number | null;
  item_payload?: Record<string, unknown>;
}

export interface VerificationCaseDetail {
  id: UUID;
  organisation_id: UUID;
  project_id: UUID;
  target_type: VerificationTargetType | string;
  target_id: UUID;
  case_status: VerificationCaseStatus | string;
  machine_assessment_status: MachineAssessmentStatus | string;
  priority: VerificationPriority | string;
  assigned_reviewer_id?: UUID | null;
  machine_assessment_json: Record<string, unknown>;
  version: number;
  last_assessed_at?: string | null;
  last_reviewed_at?: string | null;
  resolved_at?: string | null;
  created_at: string;
  updated_at: string;

  target_data: VerificationCaseDetailTargetData;
  issues: VerificationIssue[];
  conflicts: VerificationConflictItem[];
  review_events: VerificationReviewEvent[];
  context_requests: VerificationContextRequest[];

  // Backwards compatibility convenience fields
  status?: string;
  risk_level?: string;
  confidence_score?: number | null;
  events?: Array<{
    id: UUID;
    event_type: string;
    actor_user_id: UUID;
    created_at: string;
    payload: Record<string, unknown>;
  }>;
}

export interface VerificationQueueResponse {
  items: VerificationCaseItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface VerificationSummaryResponse {
  total_cases: number;
  pending_review: number;
  approved: number;
  rejected: number;
  unresolved: number;
  conflicts_count: number;
  stale_count: number;
  handover_eligible_count: number;
  by_status?: Record<string, number>;
  by_priority?: Record<string, number>;
  open_issues_count?: number;
  open_conflicts_count?: number;
  pending_context_requests_count?: number;
}

export interface SupportingEvidenceItem {
  evidence_id: UUID;
  title: string;
  source_type: string;
  source_url?: string | null;
  author?: string | null;
  support_type?: string;
  supporting_excerpt?: string | null;
  excerpt_verified?: boolean;
  source_location?: SourceLocation;
  chunk_id?: UUID | null;
  chunk_text?: string | null;
  confidence_score?: number | null;
  restricted?: boolean;
  reason?: string;
}

export interface CaseEvidenceResponse {
  case_id: UUID;
  target_type?: string;
  target_id?: UUID;
  supporting_evidence: SupportingEvidenceItem[];
  conflicts: Array<{
    id: UUID;
    conflict_type: string;
    claim_a_text: string;
    claim_a_evidence_id: UUID;
    claim_a_timestamp?: string | null;
    claim_b_text: string;
    claim_b_evidence_id: UUID;
    claim_b_timestamp?: string | null;
    explanation: string;
    temporal_comparison: string;
    resolution_state: string;
  }>;
}

export interface HandoverEligibilityResponse {
  is_eligible: boolean;
  target_type: string;
  target_id: UUID;
  case_status: string;
  epistemic_status: string;
  blockers: string[];
  warnings: string[];
  reason?: string;
}

export interface ConflictListResponse {
  items: VerificationConflictItem[];
  total: number;
  unresolved_count: number;
  reconciled_count: number;
  superseded_count: number;
  dismissed_count: number;
}

export interface ConflictSummaryResponse {
  total_conflicts: number;
  unresolved_count: number;
  reconciled_count: number;
  superseded_count: number;
  dismissed_count: number;
  by_type: Record<string, number>;
}

export interface DetectConflictsResponse {
  detected_count: number;
  new_conflicts_count: number;
  message: string;
}

export interface QueueFilterParams {
  status?: string;
  case_status?: string;
  priority?: string;
  target_type?: string;
  assigned_reviewer_id?: string;
  unassigned_only?: boolean;
  search?: string;
  limit?: number;
  offset?: number;
  page?: number;
}

export interface ConcurrencyConflictState {
  isConflict: boolean;
  message?: string;
}
