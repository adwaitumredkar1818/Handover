export type UUID = string;

export interface User {
  id: UUID;
  email: string;
  full_name: string;
  is_active?: boolean;
  status?: string;
  is_email_verified?: boolean;
  roles?: string[];
  permissions?: string[];
}

export interface AuthSessionResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export interface Organisation {
  id: UUID;
  name: string;
  slug: string;
  created_at: string;
}

export interface Project {
  id: UUID;
  organisation_id: UUID;
  name: string;
  slug: string;
  description: string | null;
  status: "planning" | "active" | "on_hold" | "completed" | "archived" | string;
  visibility?: "private" | "organisation";
  start_date?: string | null;
  target_completion_date?: string | null;
  target_handover_date?: string | null;
  created_at: string;
  updated_at: string;
  created_by_id?: UUID;
  owner_id?: UUID;
  my_project_role?: string | null;
  effective_permissions?: string[];
}

export interface OrganisationMember {
  id: UUID;
  organisation_id: UUID;
  user_id: UUID;
  full_name: string;
  email: string;
  role_name: string;
  status: string;
  joined_at: string;
}

export interface ProjectMember {
  id: UUID;
  project_id: UUID;
  user_id: UUID;
  role_name: string;
  transition_role: "departing_owner" | "incoming_assignee" | "reviewer" | "observer" | null;
  created_at: string;
  user_full_name?: string | null;
  user_email?: string | null;
  full_name?: string | null;
  email?: string | null;
  status?: string;
  responsibility_description?: string | null;
  assigned_by_id?: UUID | null;
}

export interface ProjectTransition {
  id: UUID;
  project_id: UUID;
  departing_user: { id: UUID; full_name: string; email: string };
  successor_user: { id: UUID; full_name: string; email: string };
  workflow_stage: string;
  handover_scope?: string | null;
  source_scope?: string[] | null;
  capture_start_date?: string | null;
  capture_end_date?: string | null;
  context_notes?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ReadinessScoreCard {
  overall_readiness_pct: number;
  status: string;
  target_date: string | null;
  days_remaining: number | null;
}

export interface SourceOverviewCard {
  connected_count: number;
  active_count: number;
  failed_count: number;
  total_resources: number;
}

export interface EvidenceOverviewCard {
  total_evidence_items: number;
  indexed_chunks_count: number;
  last_ingested_at: string | null;
  providers_breakdown: Record<string, number>;
}

export interface KnowledgeOverviewCard {
  decisions_count: number;
  tasks_count: number;
  risks_count: number;
  responsibilities_count: number;
  dependencies_count: number;
  availability: string;
}

export interface AttentionItemCard {
  id: string;
  type: string;
  message: string;
  resource_id?: string | null;
}

export interface ProjectActivityCard {
  id: string;
  event_type: string;
  description: string;
  actor_name?: string | null;
  timestamp: string;
}

export interface ProjectOverview {
  project_id: UUID;
  project_name: string;
  status: string;
  target_handover_date: string | null;
  readiness: ReadinessScoreCard;
  sources: SourceOverviewCard;
  evidence: EvidenceOverviewCard;
  knowledge: KnowledgeOverviewCard;
  attention_items: AttentionItemCard[];
  recent_activity: ProjectActivityCard[];
  departing_member?: { id: UUID; full_name: string; email: string } | null;
  successor?: { id: UUID; full_name: string; email: string } | null;
  owner?: { id: UUID; full_name: string; email: string } | null;
}

export interface SourceConnection {
  id: UUID;
  organisation_id: UUID;
  provider: "github" | "jira" | "slack";
  display_name: string;
  account_identifier?: string;
  status: string;
  last_synced_at: string | null;
  last_error_code?: string | null;
  last_error_summary?: string | null;
}

export interface ProjectSourceMapping {
  id: UUID;
  organisation_id: UUID;
  project_id: UUID;
  source_connection_id: UUID;
  provider: "github" | "jira" | "slack";
  resource_type: string;
  external_resource_key: string;
  external_resource_name: string;
  external_resource_url: string | null;
  status: string;
  last_synced_at: string | null;
  last_sync_status: string | null;
  last_error_code?: string | null;
  last_error_summary: string | null;
}

export interface EvidenceChunkDetail {
  id: UUID;
  chunk_index: number;
  content_text?: string;
  content_preview?: string;
  char_length?: number;
  character_count?: number;
  word_count?: number;
  chunk_type?: string;
  section_title?: string | null;
  page_number?: number | null;
}

export interface EvidenceSummary {
  id: UUID;
  project_id: UUID;
  source_type: string;
  source_provider?: string;
  provider: string;
  category: string;
  title: string;
  original_filename?: string | null;
  mime_type?: string | null;
  file_size_bytes?: number | null;
  page_count?: number | null;
  source_url: string | null;
  author_name: string | null;
  source_author_identity?: string | null;
  content_hash: string;
  indexing_status: string;
  processing_status?: string;
  lifecycle_stage?: string;
  semantic_status?: string | null;
  knowledge_count?: number;
  error_code?: string | null;
  error_message?: string | null;
  extracted_text_preview?: string | null;
  created_at: string;
  source_created_at: string | null;
}

export interface EvidenceDetail {
  id: UUID;
  project_id: UUID;
  organisation_id?: UUID;
  source_type: string;
  source_provider?: string;
  provider: string;
  category?: string;
  source_external_id?: string;
  title: string;
  original_filename?: string | null;
  mime_type?: string | null;
  file_size_bytes?: number | null;
  source_url: string | null;
  author_name: string | null;
  source_author_identity?: string | null;
  content_hash: string;
  acl_scope?: string;
  indexing_status: string;
  processing_status?: string;
  error_code?: string | null;
  error_message?: string | null;
  extraction_method?: string | null;
  page_count?: number | null;
  ocr_pages_count?: number;
  truncated_pages_count?: number;
  embedding_model?: string | null;
  index_version?: string | null;
  created_at: string;
  updated_at?: string;
  source_created_at: string | null;
  source_updated_at?: string | null;
  extracted_at?: string | null;
  extracted_text_preview?: string | null;
  extracted_content?: {
    char_count?: number;
    word_count?: number;
    extraction_warnings?: string[];
    extracted_text?: string;
  } | null;
  metadata_json?: Record<string, unknown>;
  can_download: boolean;
  download_url?: string | null;
  chunks: EvidenceChunkDetail[];
  lifecycle_stage?: string;
  semantic_status?: string | null;
  knowledge_count?: number;
  linked_knowledge_items?: Array<{
    id: string;
    category: string;
    title: string;
    summary: string;
    confidence?: number;
    epistemic_status?: string;
  }>;
  linked_entities?: Array<{
    id: string;
    name: string;
    entity_type: string;
    category?: string;
  }>;
  linked_relationships?: Array<{
    id: string;
    source: string;
    target: string;
    relationship_type: string;
  }>;
}

export interface EvidenceMetrics {
  total_items: number;
  by_type: Record<string, number>;
  by_indexing_status: Record<string, number>;
}


// ─── Downstream Platform Types ────────────────────────────────────────────────

export interface KnowledgeFinding {
  id: UUID;
  project_id: UUID;
  knowledge_domain: string;
  category: string;
  title: string;
  summary: string;
  confidence_score: number;
  epistemic_status: "extracted" | "interpreted" | "human_verified";
  review_status: "unreviewed" | "approved" | "rejected" | "disputed";
  evidence_citations_count: number;
  extracted_at: string;
  item_payload?: Record<string, unknown>;
  citations?: Array<{
    chunk_id: string;
    evidence_id: string;
    excerpt_text: string;
    similarity_score?: number;
  }>;
}

export interface KnowledgeDomainMetric {
  domain: string;
  total_findings: number;
  confidence_distribution: Record<string, number>;
  verified_percentage: number;
}

export interface KnowledgeSummaryTelemetry {
  total_findings: number;
  by_category: Record<string, number>;
  by_domain: Record<string, number>;
  verified_count: number;
  candidate_count: number;
  readiness_percentage?: number;
}

export interface TimelineStreamEvent {
  id: UUID;
  project_id: UUID;
  title: string;
  event_type: "decision" | "milestone" | "incident" | "commit" | "task" | string;
  event_timestamp: string;
  confidence: number;
  source_evidence_ids: string[];
  summary?: string;
}

export interface GraphNodeData {
  id: string;
  label: string;
  type?: string;
  entity_type?: string;
  canonical_name?: string;
  confidence?: number;
  resolution_status?: string;
  status?: string;
  verification_status?: string;
  description?: string | null;
  domain?: string;
  source_provider?: string | null;
  properties?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
}

export interface GraphEdgeData {
  id: string;
  source: string;
  target: string;
  type?: string;
  relationship_type?: string;
  label?: string;
  relationship_basis?: string;
  verification_status?: string;
  confidence?: number;
  evidence_count?: number;
  supporting_evidence_available?: boolean;
  is_bidirectional?: boolean;
}

export interface KnowledgeGraphData {
  nodes: GraphNodeData[];
  edges: GraphEdgeData[];
}

export interface VerificationCaseQueueItem {
  id: UUID;
  target_type: string;
  target_id: UUID;
  status: "pending_review" | "approved" | "rejected" | "unresolved";
  priority: "critical" | "high" | "medium" | "low";
  confidence_score: number;
  created_at: string;
  issue_count: number;
  version?: number;
  assigned_to_user_id?: string;
  finding?: {
    title: string;
    summary: string;
    domain: string;
    epistemic_status: string;
  };
}

export interface VerificationSummaryData {
  total_cases: number;
  pending_review: number;
  approved: number;
  rejected: number;
  unresolved: number;
  conflicts_count: number;
  stale_count: number;
  handover_eligible_count: number;
}

export interface HandoverCaseItem {
  id: UUID;
  project_id: UUID;
  title: string;
  description?: string;
  status: string;
  version: number;
  created_at: string;
  updated_at: string;
  outgoing_owner_user_id?: string;
  incoming_owner_user_id?: string;
  departing_member_id?: string;
  successor_id?: string;
  current_version_id?: string;
  readiness_score?: number;
  latest_readiness_score?: number;
}

export interface HandoverReadinessData {
  readiness_score: number;
  dimension_scores: Record<string, number>;
  unmet_requirements: string[];
  recommendations: string[];
}

export type CanonicalHandoverSectionType =
  | "project_overview_context"
  | "decisions_rationale"
  | "technical_architecture"
  | "work_progress"
  | "responsibilities_ownership"
  | "dependencies_relationships"
  | "bugs_blockers_risks"
  | "operational_historical";

export interface HandoverPackageVersionSummary {
  id: UUID;
  package_id: UUID;
  version_number: number;
  assembly_status?: string | null;
  assembly_notes?: string | null;
  notes?: string | null;
  content_hash?: string | null;
  assembly_snapshot_json?: Record<string, unknown> | null;
  assembled_by_user_id?: UUID | null;
  assembled_at?: string | null;
  is_current: boolean;
  created_at: string;
}

export interface HandoverContentLinkItem {
  id: UUID;
  section_id: UUID;
  knowledge_item_id?: UUID | null;
  relationship_id?: UUID | null;
  evidence_id?: UUID | null;
  link_type: string;
  eligibility_status_json?: Record<string, unknown> | null;
  created_at: string;
}

export interface HandoverEvidenceProvenance {
  evidence_id: UUID;
  source_type: string;
  source_provider?: string | null;
  source_name: string;
  source_reference?: string | null;
  source_url?: string | null;
  author?: string | null;
  source_timestamp?: string | null;
  extracted_at?: string | null;
  support_type: string;
  supporting_excerpt?: string | null;
  acl_restricted: boolean;
}

export interface HandoverVerificationSummary {
  verification_case_id?: UUID | null;
  case_status?: string | null;
  reviewer_decision?: string | null;
  reviewed_by_user_id?: UUID | null;
  reviewed_by_name?: string | null;
  reviewed_at?: string | null;
  review_notes?: string | null;
}

export interface HandoverSectionKnowledgeItem {
  id: UUID;
  content_link_id: UUID;
  title: string;
  content: string;
  category: string;
  epistemic_status: string;
  review_status: string;
  support_classification: string;
  normalised_status?: string | null;
  owner_label?: string | null;
  structured_payload: Record<string, unknown>;
  confidence_score?: number | null;
  is_stale: boolean;
  created_at: string;
  updated_at: string;
  source_observed_at?: string | null;
  eligibility: Record<string, unknown>;
  verification: HandoverVerificationSummary;
  provenance: HandoverEvidenceProvenance[];
  provenance_available: boolean;
}

export interface HandoverSectionRelationship {
  id: UUID;
  content_link_id: UUID;
  relationship_type: string;
  source_entity_id: UUID;
  source_entity_name: string;
  source_entity_type: string;
  target_entity_id: UUID;
  target_entity_name: string;
  target_entity_type: string;
  verification_status: string;
  confidence_score: number;
  is_stale: boolean;
  reviewed_at?: string | null;
  eligibility: Record<string, unknown>;
  provenance: HandoverEvidenceProvenance[];
  provenance_available: boolean;
}

export interface HandoverSectionConflictItem {
  id: UUID;
  verification_case_id: UUID;
  conflict_type: string;
  priority: string;
  resolution_state: string;
  explanation: string;
  claim_a_text: string;
  claim_b_text: string;
  side_a_source_title?: string | null;
  side_b_source_title?: string | null;
  authoritative_claim_text?: string | null;
  resolution_notes?: string | null;
  resolved_at?: string | null;
  updated_at: string;
}

export interface HandoverDomainEpistemicBreakdown {
  human_verified_included: number;
  pending_verification: number;
  rejected: number;
  unresolved_conflicts: number;
  resolved_conflicts: number;
  outdated: number;
}

export interface HandoverSectionDetail {
  id: UUID;
  version_id: UUID;
  section_type: string;
  section_title: string;
  section_content?: string | null;
  content_summary?: string | null;
  section_order: number;
  knowledge_item_count: number;
  relationship_count: number;
  metadata_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  content_links: HandoverContentLinkItem[];
  knowledge_items: HandoverSectionKnowledgeItem[];
  relationships: HandoverSectionRelationship[];
  unresolved_conflicts: HandoverSectionConflictItem[];
  resolved_conflicts: HandoverSectionConflictItem[];
  epistemic_breakdown: HandoverDomainEpistemicBreakdown;
  domain_context: Record<string, unknown>;
}

export interface HandoverVersionSectionsResponse {
  case_id: UUID;
  project_id: UUID;
  version: HandoverPackageVersionSummary;
  sections: HandoverSectionDetail[];
  missing_section_types: string[];
  epistemic_summary: HandoverDomainEpistemicBreakdown;
}

// ---------------------------------------------------------------------------
// Stage 4: Live Handover Readiness Intelligence & Conflict Integration
// ---------------------------------------------------------------------------

export interface HandoverReadinessCategoryItem {
  id: UUID;
  version_id: UUID;
  category: string;
  label: string;
  score: number;
  max_score: number;
  weight?: number | null;
  level: "not_ready" | "partially_ready" | "ready" | "ready_with_warnings" | string;
  blockers_json: string[];
  warnings_json: string[];
  missing_requirements: string[];
  recommendations: string[];
  related_section_tab?: string | null;
  supporting_metrics: Record<string, unknown>;
  details_json: Record<string, unknown>;
  assessed_by_user_id?: UUID | null;
  assessed_at: string;
  created_at: string;
}

export interface ReadinessStructuredBlocker {
  id: string;
  group: string;
  severity: "critical" | "high" | "medium" | "low" | string;
  description: string;
  originating_subsystem: string;
  related_section_tab?: string | null;
  related_record_id?: string | null;
  recommended_action: string;
  target_url?: string | null;
}

export interface ReadinessReviewEventItem {
  id: UUID;
  case_id: UUID;
  case_title?: string | null;
  action: string;
  reviewer_name?: string | null;
  new_status: string;
  review_notes?: string | null;
  created_at: string;
}

export interface ReadinessVerificationSummary {
  total_knowledge_items: number;
  eligible_human_verified: number;
  pending_verification: number;
  rejected_items: number;
  verification_coverage_pct: number;
  case_counts: Record<string, number>;
  outstanding_blockers: string[];
  recent_reviews: ReadinessReviewEventItem[];
}

export interface ReadinessConflictItem {
  id: UUID;
  verification_case_id: UUID;
  conflict_type: string;
  priority: "critical" | "high" | "medium" | "low" | string;
  resolution_state: string;
  is_blocking: boolean;
  explanation: string;
  affected_section_tab?: string | null;
  side_a_source_title?: string | null;
  side_b_source_title?: string | null;
  acl_restricted: boolean;
  resolution_notes?: string | null;
  resolved_at?: string | null;
  updated_at?: string | null;
  conflict_url: string;
}

export interface ReadinessConflictSummary {
  total_conflicts: number;
  open_conflicts: number;
  under_investigation: number;
  awaiting_context: number;
  resolved_conflicts: number;
  critical_and_high_count: number;
  blocking_approval_count: number;
  items: ReadinessConflictItem[];
}

export interface ReadinessEvidenceQualitySummary {
  total_knowledge_items: number;
  items_with_evidence: number;
  items_missing_evidence: number;
  evidence_coverage_pct: number;
  corroborated_items: number;
  uncertain_items: number;
  stale_items: number;
  superseded_items: number;
  total_evidence_sources: number;
  accessible_evidence_count: number;
  restricted_evidence_count: number;
}

export interface ReadinessChecklistItemEntry {
  id: UUID;
  item_text: string;
  status: string;
  blocking: boolean;
  category?: string | null;
  assigned_to_user_id?: UUID | null;
  due_date?: string | null;
}

export interface ReadinessChecklistGroupSummary {
  id: UUID;
  checklist_type: string;
  title: string;
  total_items: number;
  completed_items: number;
  mandatory_total: number;
  mandatory_completed: number;
  mandatory_outstanding: number;
  is_completed: boolean;
  items: ReadinessChecklistItemEntry[];
}

export interface ReadinessChecklistSummary {
  total_groups: number;
  total_items: number;
  completed_items: number;
  completion_pct: number;
  mandatory_total: number;
  mandatory_completed: number;
  mandatory_outstanding: number;
  groups: ReadinessChecklistGroupSummary[];
}

export interface ReadinessSignoffPhaseStatus {
  phase: string;
  signoff_type: string;
  status: string;
  signed_at?: string | null;
}

export interface ReadinessApprovalEligibility {
  current_case_status: string;
  next_lifecycle_state?: string | null;
  is_eligible_for_approval: boolean;
  score_gate_passed: boolean;
  verification_gate_passed: boolean;
  conflict_gate_passed: boolean;
  checklist_gate_passed: boolean;
  blocking_requirements: string[];
  warnings: string[];
  required_signoffs: ReadinessSignoffPhaseStatus[];
}

export interface ReadinessAssessmentHistoryItem {
  id: UUID;
  assessed_at: string;
  overall_score: number;
  overall_level: string;
  blocker_count: number;
  warning_count: number;
  assessed_by_name?: string | null;
  notes?: string | null;
}

export interface HandoverReadinessIntelligenceResponse {
  version_id: UUID;
  case_id?: UUID | null;
  project_id?: UUID | null;
  version_number?: number | null;
  content_hash?: string | null;
  assessed_at?: string | null;
  overall_score: number;
  overall_level: "not_ready" | "partially_ready" | "ready" | "ready_with_warnings" | string;
  categories: HandoverReadinessCategoryItem[];
  is_ready_for_signoff: boolean;
  blocker_count: number;
  warning_count: number;
  structured_blockers: ReadinessStructuredBlocker[];
  recommendations: string[];
  verification_summary?: ReadinessVerificationSummary | null;
  conflict_summary?: ReadinessConflictSummary | null;
  evidence_quality?: ReadinessEvidenceQualitySummary | null;
  checklist_summary?: ReadinessChecklistSummary | null;
  approval_eligibility?: ReadinessApprovalEligibility | null;
  assessment_history: ReadinessAssessmentHistoryItem[];
}

// ---------------------------------------------------------------------------
// Stage 5: Transition Checklists, Responsibility Transfer & Ownership Management
// ---------------------------------------------------------------------------

export interface HandoverStage5ActivityItem {
  id: UUID;
  event_type: string;
  resource_type: string;
  resource_id?: string | null;
  actor_user_id?: UUID | null;
  actor_name?: string | null;
  outcome: string;
  summary: string;
  metadata_json: Record<string, unknown>;
  created_at: string;
}

export interface ChecklistEvidenceSummary {
  evidence_id: UUID;
  title: string;
  source_type?: string | null;
  source_url?: string | null;
  acl_restricted: boolean;
}

export interface HandoverChecklistItemDetail {
  id: UUID;
  checklist_id: UUID;
  item_text: string;
  description?: string | null;
  completion_criteria?: string | null;
  status: "pending" | "in_progress" | "completed" | "skipped" | "blocked" | string;
  blocking: boolean;
  category?: string | null;
  assigned_to_user_id?: UUID | null;
  assigned_to_name?: string | null;
  due_date?: string | null;
  is_overdue: boolean;
  notes?: string | null;
  evidence_item_id?: UUID | null;
  evidence_summary?: ChecklistEvidenceSummary | null;
  completed_by_user_id?: UUID | null;
  completed_by_name?: string | null;
  completed_at?: string | null;
  reviewed_by_user_id?: UUID | null;
  reviewed_by_name?: string | null;
  reviewed_at?: string | null;
  review_notes?: string | null;
  reopened_count: number;
  reopened_by_user_id?: UUID | null;
  reopened_by_name?: string | null;
  reopened_at?: string | null;
  reopened_reason?: string | null;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface HandoverChecklistGroupDetail {
  id: UUID;
  case_id: UUID;
  generated_for_version_id?: UUID | null;
  checklist_type: string;
  title?: string | null;
  description?: string | null;
  total_items: number;
  completed_items: number;
  mandatory_total: number;
  mandatory_completed: number;
  mandatory_outstanding: number;
  blocked_items: number;
  overdue_items: number;
  is_completed: boolean;
  created_at: string;
  items: HandoverChecklistItemDetail[];
}

export interface HandoverChecklistWorkspaceResponse {
  case_id: UUID;
  project_id: UUID;
  total_checklists: number;
  total_items: number;
  completed_items: number;
  outstanding_items: number;
  blocked_items: number;
  overdue_items: number;
  mandatory_total: number;
  mandatory_completed: number;
  mandatory_outstanding: number;
  optional_total: number;
  optional_completed: number;
  completion_pct: number;
  checklists: HandoverChecklistGroupDetail[];
  activity_history: HandoverStage5ActivityItem[];
}

export interface ResponsibilityEvidenceRef {
  evidence_id: UUID;
  title: string;
  source_type?: string | null;
  source_url?: string | null;
  source_author?: string | null;
  source_timestamp?: string | null;
  excerpt?: string | null;
  acl_restricted: boolean;
}

export interface ResponsibilityKnowledgeContextItem {
  id: UUID;
  category: string;
  title: string;
  summary: string;
  epistemic_status: string;
  review_status: string;
  is_verified: boolean;
  evidence_refs: ResponsibilityEvidenceRef[];
}

export interface ResponsibilityOwnershipValidationIssue {
  severity: "critical" | "high" | "medium" | "low" | string;
  code: string;
  message: string;
  transfer_id?: UUID | null;
  user_id?: UUID | null;
}

export interface ResponsibilityParticipantSummary {
  user_id: UUID;
  full_name: string;
  email: string;
  role_name: string;
  membership_status: string;
  is_active: boolean;
  is_departing_owner: boolean;
  is_case_successor: boolean;
  has_handover_access: boolean;
}

export interface ResponsibilityCandidateItem {
  knowledge_item_id: UUID;
  title: string;
  summary: string;
  epistemic_status: string;
  review_status: string;
  is_verified: boolean;
  ownership_certainty: string;
  source_context?: string | null;
  evidence_refs: ResponsibilityEvidenceRef[];
}

export interface HandoverResponsibilityTransferDetail {
  id: UUID;
  case_id: UUID;
  version_id?: UUID | null;
  title?: string | null;
  responsibility_description: string;
  current_owner_id: UUID;
  current_owner_name?: string | null;
  current_owner_role?: string | null;
  current_owner_active: boolean;
  proposed_successor_id?: UUID | null;
  proposed_successor_name?: string | null;
  proposed_successor_role?: string | null;
  proposed_successor_active?: boolean | null;
  knowledge_domain?: string | null;
  component_name?: string | null;
  priority: "critical" | "high" | "medium" | "low" | string;
  ownership_certainty: "confirmed" | "proposed" | "uncertain" | string;
  operational_context?: string | null;
  required_access?: string | null;
  effective_transfer_date?: string | null;
  transfer_status: string;
  transfer_notes?: string | null;
  blocker_reason?: string | null;
  related_entity_id?: UUID | null;
  related_entity_name?: string | null;
  related_knowledge_item_id?: UUID | null;
  outgoing_confirmed_by_user_id?: UUID | null;
  outgoing_confirmed_by_name?: string | null;
  outgoing_confirmed_at?: string | null;
  outgoing_confirmation_notes?: string | null;
  successor_acknowledged_by_user_id?: UUID | null;
  successor_acknowledged_by_name?: string | null;
  successor_acknowledged_at?: string | null;
  successor_acknowledgement_notes?: string | null;
  clarification_requested_by_user_id?: UUID | null;
  clarification_requested_by_name?: string | null;
  clarification_requested_at?: string | null;
  clarification_request_notes?: string | null;
  clarification_response_notes?: string | null;
  reopened_count: number;
  reopened_reason?: string | null;
  version: number;
  transferred_at?: string | null;
  validation_warnings: string[];
  related_knowledge: ResponsibilityKnowledgeContextItem[];
  supporting_evidence: ResponsibilityEvidenceRef[];
  created_at: string;
  updated_at: string;
}

export interface HandoverResponsibilityWorkspaceResponse {
  case_id: UUID;
  project_id: UUID;
  departing_member_id: UUID;
  case_successor_id?: UUID | null;
  total_transfers: number;
  unassigned_count: number;
  awaiting_outgoing_count: number;
  awaiting_successor_count: number;
  acknowledged_count: number;
  blocked_count: number;
  clarification_count: number;
  validation_issues: ResponsibilityOwnershipValidationIssue[];
  eligible_participants: ResponsibilityParticipantSummary[];
  transfers: HandoverResponsibilityTransferDetail[];
  discovered_candidates: ResponsibilityCandidateItem[];
  activity_history: HandoverStage5ActivityItem[];
}

// ---------------------------------------------------------------------------
// Stage 6: Three-Phase Signoff, Approval, Publication & Recipient Acknowledgement
// ---------------------------------------------------------------------------

export interface DeliveryClarificationEntry {
  id: string;
  mode: "request" | "response" | string;
  author_user_id: UUID;
  author_name?: string | null;
  notes: string;
  created_at: string;
}

export interface HandoverSignoffRecord {
  id: UUID;
  case_id: UUID;
  version_id: UUID;
  signoff_type: "departing_signoff" | "reviewer_approval" | "successor_acknowledgement" | string;
  signer_user_id: UUID;
  signer_name?: string | null;
  decision: "approved" | "rejected" | "returned_for_revision" | string;
  comments?: string | null;
  conditions?: string | null;
  package_content_hash?: string | null;
  affected_sections_json: string[];
  is_superseded: boolean;
  signature_hash?: string | null;
  signed_at: string;
  created_at: string;
}

export interface HandoverAcknowledgementRecord {
  id: UUID;
  delivery_id: UUID;
  acknowledged_by_user_id: UUID;
  acknowledged_by_name?: string | null;
  acknowledgement_notes?: string | null;
  confirmations_json: Record<string, unknown>;
  acknowledgement_hash?: string | null;
  acknowledged_at: string;
  created_at: string;
}

export interface HandoverDeliveryRecord {
  id: UUID;
  version_id: UUID;
  delivered_to_user_id: UUID;
  delivered_to_name?: string | null;
  delivered_by_user_id?: UUID | null;
  delivered_by_name?: string | null;
  delivery_method: string;
  artifact_storage_path?: string | null;
  artifact_checksum?: string | null;
  message?: string | null;
  is_active: boolean;
  delivered_at: string;
  expires_at?: string | null;
  acknowledged: boolean;
  acknowledgement?: HandoverAcknowledgementRecord | null;
  clarifications: DeliveryClarificationEntry[];
  created_at: string;
}

export interface HandoverStatusHistoryItem {
  id: UUID;
  case_id: UUID;
  previous_status: string;
  new_status: string;
  changed_by_user_id: UUID;
  change_reason?: string | null;
  changed_at: string;
}

export interface SignoffPhaseDetail {
  phase_number: number;
  phase_name: string;
  signoff_type: string;
  purpose: string;
  assigned_user_id?: UUID | null;
  assigned_user_name?: string | null;
  assigned_user_role?: string | null;
  required_permission: string;
  status: string;
  viewer_can_act: boolean;
  viewer_ineligibility_reason?: string | null;
  pending_requirements: string[];
  latest_decision?: HandoverSignoffRecord | null;
}

export interface SignoffLifecycleSummary {
  current_status: string;
  previous_status?: string | null;
  next_permitted_transitions: string[];
  responsible_role_label: string;
  responsible_user_name?: string | null;
  blocked_transition_reasons: string[];
  case_version: number;
  status_history: HandoverStatusHistoryItem[];
}

export interface SignoffPublicationStatus {
  is_eligible_to_publish: boolean;
  is_published: boolean;
  blocking_reasons: string[];
  approved_version_id?: UUID | null;
  approved_version_number?: number | null;
  approved_content_hash?: string | null;
  published_version_id?: UUID | null;
  published_version_number?: number | null;
  published_content_hash?: string | null;
  published_at?: string | null;
  published_by_name?: string | null;
  deliveries: HandoverDeliveryRecord[];
}

export interface HandoverSignoffWorkspaceResponse {
  case_id: UUID;
  project_id: UUID;
  case_title: string;
  case_status: string;
  case_version: number;
  departing_member_id: UUID;
  departing_member_name?: string | null;
  successor_id?: UUID | null;
  successor_name?: string | null;
  assigned_reviewer_id?: UUID | null;
  assigned_reviewer_name?: string | null;
  selected_version_id?: UUID | null;
  selected_version_number?: number | null;
  selected_content_hash?: string | null;
  package_changed_since_approval: boolean;
  package_change_notice?: string | null;
  readiness_score?: number | null;
  readiness_level?: string | null;
  readiness_assessed_at?: string | null;
  approval_eligibility?: ReadinessApprovalEligibility | null;
  lifecycle: SignoffLifecycleSummary;
  phases: SignoffPhaseDetail[];
  publication: SignoffPublicationStatus;
  eligible_reviewers: ResponsibilityParticipantSummary[];
  eligible_recipients: ResponsibilityParticipantSummary[];
  signoff_history: HandoverSignoffRecord[];
  activity_history: HandoverStage5ActivityItem[];
}

export interface AuditEventItem {
  id: UUID;
  organisation_id: UUID;
  project_id?: UUID | null;
  user_id?: UUID | null;
  action: string;
  entity_type: string;
  entity_id?: string | null;
  outcome: string;
  created_at: string;
  actor_name?: string | null;
  details?: Record<string, unknown> | null;
}

// ---------------------------------------------------------------------------
// Project Knowledge Assistant (Module 5 / AI Assistant)
// ---------------------------------------------------------------------------

export type AssistantAnswerStatus =
  | "answered"
  | "partially_answered"
  | "insufficient_evidence"
  | "conflicted_evidence"
  | "outdated_evidence"
  | "access_restricted"
  | "unsupported_query"
  | "processing_error"
  | "declined";

export type AssistantResponseMode = "standard" | "deep_research" | "deep_think" | "deep_extract";

export type AssistantSenderType = "user" | "assistant";

export interface ResearchReportSection {
  section_title: string;
  content: string;
  citation_labels: string[];
  key_takeaways: string[];
}

export interface ResearchReportPayload {
  executive_summary: string;
  sections: ResearchReportSection[];
  cross_source_corroboration: string[];
  recommendations: string[];
  coverage_assessment?: string | null;
}

export interface CausalStep {
  step_number: number;
  event_or_decision: string;
  actor_or_source?: string | null;
  consequences: string[];
  citation_labels: string[];
}

export interface DeepThinkPayload {
  core_hypothesis: string;
  causal_chain: CausalStep[];
  alternative_explanations: string[];
  tradeoffs_and_risks: string[];
  synthesis_reasoning: string;
}

export interface ExtractedRecord {
  entity_name: string;
  category: string;
  attributes: Record<string, unknown>;
  field_citations: Record<string, string[]>;
  status_or_state?: string | null;
}

export interface DeepExtractPayload {
  target_schema: string;
  columns: string[];
  records: ExtractedRecord[];
  missing_fields: string[];
  summary: string;
}

export interface AssistantCitation {
  id?: string;
  citation_label: string; // e.g. "S1", "S2"
  evidence_id: string;
  chunk_id?: string | null;
  knowledge_item_id?: string | null;
  source_title: string;
  source_provider: string; // "github", "jira", "document_upload", "slack", etc.
  source_url?: string | null;
  source_external_id?: string | null;
  author?: string | null;
  source_timestamp?: string | null;
  page_number?: number | null;
  section_title?: string | null;
  excerpt: string;
  is_verified: boolean;
}

export interface AssistantClaim {
  claim_text: string;
  citation_labels: string[];
  confidence: number;
}

export interface AssistantConversation {
  id: string;
  organisation_id: string;
  project_id: string;
  created_by_user_id: string;
  title: string;
  status: "active" | "archived";
  metadata_json?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
  last_message_at?: string | null;
}

export interface AssistantMessage {
  id: string;
  conversation_id: string;
  sender_type: AssistantSenderType;
  content: string;
  answer_status?: AssistantAnswerStatus | null;
  response_mode?: AssistantResponseMode;
  structured_payload_json?: {
    claims?: AssistantClaim[];
    conflicts?: string[];
    uncertainty?: string | null;
    missing_information?: string[];
    suggested_followup_questions?: string[];
    query_type?: string;
    response_mode?: AssistantResponseMode;
    research_report?: ResearchReportPayload | null;
    deep_think?: DeepThinkPayload | null;
    deep_extract?: DeepExtractPayload | null;
  } | null;
  citations: AssistantCitation[];
  model_name?: string | null;
  prompt_tokens?: number | null;
  completion_tokens?: number | null;
  duration_ms?: number | null;
  retrieval_run_id?: string | null;
  created_at: string;
}

export interface AssistantConversationDetail {
  conversation: AssistantConversation;
  messages: AssistantMessage[];
}

export interface AssistantAnswerResponse {
  message_id: string;
  conversation_id: string;
  answer: string;
  answer_status: AssistantAnswerStatus;
  response_mode?: AssistantResponseMode;
  query_type: string;
  claims: AssistantClaim[];
  citations: AssistantCitation[];
  uncertainty?: string | null;
  conflicts: string[];
  missing_information: string[];
  suggested_followup_questions: string[];
  research_report?: ResearchReportPayload | null;
  deep_think?: DeepThinkPayload | null;
  deep_extract?: DeepExtractPayload | null;
  model_name: string;
  retrieval_run_id?: string | null;
  duration_ms: number;
  created_at: string;
}

export type InvitationStatus = "pending" | "accepted" | "expired" | "revoked";

export interface InvitationSummary {
  id: UUID;
  organisation_id: UUID;
  email: string;
  role_name: string;
  project_id?: UUID | null;
  project_role_name?: string | null;
  status: InvitationStatus | string;
  invited_by_id: UUID;
  expires_at: string;
  accepted_at?: string | null;
  revoked_at?: string | null;
  created_at: string;
}

export interface CreateInvitationResponse {
  invitation: InvitationSummary;
  invitation_delivery: "not_configured" | "submitted" | "failed";
  message: string;
  development_invitation_token?: string | null;
}

export interface InvitationListResponse {
  items: InvitationSummary[];
  total: number;
}

export interface InvitationPreviewResponse {
  email: string;
  organisation_id: UUID;
  organisation_name: string;
  organisation_slug: string;
  role_name: string;
  project_id?: UUID | null;
  project_name?: string | null;
  project_slug?: string | null;
  project_role_name?: string | null;
  inviter_name?: string | null;
  status: InvitationStatus | string;
  expires_at: string;
  is_actionable: boolean;
}

export interface AcceptInvitationResponse {
  organisation_id: UUID;
  organisation_name: string;
  organisation_slug: string;
  role_name: string;
  membership_status: string;
  joined_at: string;
  project_id?: UUID | null;
  project_name?: string | null;
  project_slug?: string | null;
  project_role_name?: string | null;
  project_membership_status?: string | null;
  is_new_organisation_member: boolean;
}

export interface RegisterWithInvitationResponse {
  user: User;
  email_verification_required: boolean;
  email_verification_delivery: "not_configured" | "submitted" | "failed";
  organisation_id: UUID;
  organisation_name: string;
  project_id?: UUID | null;
  project_name?: string | null;
  project_role_name?: string | null;
  project_membership_status?: string | null;
  can_access_project_immediately: boolean;
  development_verification_token?: string | null;
  message: string;
}

export interface VerifyEmailResponse {
  message: string;
  email: string;
  is_email_verified: boolean;
  can_access_project_immediately: boolean;
}

export interface RequestEmailVerificationResponse {
  message: string;
  email_verification_delivery: "not_configured" | "submitted" | "failed";
  development_verification_token?: string | null;
}

export interface NotificationItem {
  id: string;
  organisation_id: string;
  project_id?: string | null;
  user_id?: string | null;
  notification_type: string;
  type?: string;
  title: string;
  body: string;
  link?: string | null;
  severity: "info" | "success" | "warning" | "error";
  is_read: boolean;
  read_at?: string | null;
  metadata_json: Record<string, unknown>;
  created_at: string;
}

export interface ActiveSyncJob {
  id: string;
  project_id: string;
  job_type: string;
  status: string;
  stage?: string;
  progress_percent: number;
  attempt_count: number;
  message?: string;
  created_at: string;
  started_at?: string;
}

export interface TeamRosterMemberItem {
  id: string;
  project_id: string;
  evidence_item_id: string;
  member_id_in_roster?: string;
  full_name: string;
  email?: string;
  role_name?: string;
  primary_responsibilities: string[];
  component_ownership: string[];
  github_username?: string;
  git_commit_email?: string;
  jira_account_id?: string;
  slack_user_id?: string;
  reconciliation_status: "MATCHED" | "POSSIBLE_MATCH" | "NEW_CANDIDATE" | "AMBIGUOUS" | "CONFLICT" | "REJECTED" | string;
  matched_project_membership_id?: string;
  matched_member_name?: string;
  reconciliation_confidence?: number;
  reconciliation_notes?: string;
  created_at: string;
}

export interface ContributionAttributionItem {
  id: string;
  project_id: string;
  evidence_item_id: string;
  contributor_identifier: string;
  identifier_type: string;
  matched_roster_member_id?: string;
  matched_roster_name?: string;
  matched_project_membership_id?: string;
  match_method?: string;
  match_confidence?: number;
  contribution_category?: string;
  responsibility_alignment?: "ALIGNED" | "PARTIALLY_ALIGNED" | "OUTSIDE_DECLARED_RESPONSIBILITY" | "UNCERTAIN" | "NOT_APPLICABLE" | string;
  alignment_explanation?: string;
  created_at: string;
}

export type NotificationType =
  | "invitation"
  | "review"
  | "approval"
  | "ingestion"
  | "integration"
  | "project";

export interface AppNotification {
  id: UUID;
  user_id: UUID;
  organisation_id?: UUID | null;
  project_id?: UUID | null;
  type: NotificationType;
  title: string;
  body: string;
  link?: string | null;
  is_read: boolean;
  read_at?: string | null;
  metadata_json?: Record<string, unknown> | null;
  created_at: string;
}

export interface NotificationListResponse {
  items: AppNotification[];
  total: number;
  unread_count: number;
}

export interface NotificationPreferences {
  user_id: UUID;
  in_app_enabled: boolean;
  email_digest_enabled: boolean;
  invitations: boolean;
  review_requests: boolean;
  approvals: boolean;
  ingestion_updates: boolean;
  integration_alerts: boolean;
  project_updates: boolean;
  updated_at?: string | null;
}

export interface ProjectProcessingStatus {
  state: "no_evidence" | "queued" | "processing" | "partially_ready" | "ready" | "failed" | "insufficient_evidence";
  state_label: string;
  is_processing: boolean;
  stage: "parsing" | "syncing" | "indexing" | "extracting_knowledge" | "reconstructing_graphs" | "idle" | null;
  stage_label: string | null;
  total_evidence_count: number;
  processed_evidence_count: number;
  queued_evidence_count: number;
  failed_evidence_count: number;
  has_existing_graphs: boolean;
  knowledge_item_count: number;
  entity_count: number;
  relationship_count: number;
  last_reconstructed_at: string | null;
  error_message: string | null;
  updated_at: string;
  graph_version?: string | null;
  stage_counts?: Record<string, number>;
  total_imported?: number;
  deterministic_ready?: number;
  semantic_queued?: number;
  semantic_extracting?: number;
  semantic_ready?: number;
  graph_published?: number;
  failed?: number;
  not_applicable?: number;
  item_states?: Record<
    string,
    {
      lifecycle_stage?: string;
      semantic_status?: string;
      processing_status?: string;
      indexing_status?: string;
      knowledge_count?: number;
    }
  >;
}
