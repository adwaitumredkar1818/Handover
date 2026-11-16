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
