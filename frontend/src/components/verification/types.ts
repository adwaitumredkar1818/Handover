/**
 * Verification Center Component & Prop Types
 */

export * from "../../types/verification";

import type {
  VerificationCaseItem,
  VerificationCaseDetail,
  VerificationSummaryResponse,
  SupportingEvidenceItem,
  HandoverEligibilityResponse,
  VerificationConflictItem,
  ConcurrencyConflictState,
} from "../../types/verification";

export interface DashboardHeaderProps {
  summary: VerificationSummaryResponse | null;
  loading: boolean;
  assessing: boolean;
  onRefresh: () => void;
  onAssessAll: () => void;
  projectName?: string;
}

export interface SummaryCardsProps {
  summary: VerificationSummaryResponse | null;
  loading: boolean;
  activeStatusFilter: string;
  onSelectStatusFilter: (status: string) => void;
}

export interface QueueListProps {
  queue: VerificationCaseItem[];
  selectedCaseId: string | null;
  onSelectCase: (caseId: string) => void;
  loading: boolean;
  statusFilter: string;
  onStatusFilterChange: (status: string) => void;
  searchTerm: string;
  onSearchChange: (term: string) => void;
  priorityFilter: string;
  onPriorityFilterChange: (priority: string) => void;
  page: number;
  totalItems: number;
  pageSize: number;
  onPageChange: (newPage: number) => void;
}

export interface FindingInspectionPanelProps {
  caseDetail: VerificationCaseDetail | null;
  eligibility: HandoverEligibilityResponse | null;
  loadingEligibility: boolean;
  loading: boolean;
  onOpenEditModal: () => void;
}

export interface SupportingEvidencePanelProps {
  evidenceList: SupportingEvidenceItem[];
  conflicts: VerificationConflictItem[];
  issues: VerificationCaseDetail["issues"];
  confidenceScore: number | null | undefined;
  loading: boolean;
  onViewChunk: (evidence: SupportingEvidenceItem) => void;
}

export interface ReviewerActionPanelProps {
  caseDetail: VerificationCaseDetail | null;
  reviewerNote: string;
  onReviewerNoteChange: (note: string) => void;
  actionLoading: boolean;
  concurrencyConflict: ConcurrencyConflictState | null;
  onReloadLatest: () => void;
  onApprove: () => void;
  onReject: () => void;
  onOpenEditModal: () => void;
  onOpenRequestContextModal: () => void;
  onMarkUnresolved: () => void;
  onAssignReviewer: (assigneeUserId: string | null) => void;
  members: Array<{ id: string; user_id?: string; user?: { id: string; name?: string; email?: string } }>;
  currentUserId?: string;
}

export interface SideBySideConflictCardProps {
  conflict: VerificationConflictItem;
  onResolve?: (conflictId: string, state: string, notes: string, preferredClaim?: string) => Promise<void>;
  resolving?: boolean;
}

export interface ChunkSourceDrawerProps {
  evidence: SupportingEvidenceItem | null;
  isOpen: boolean;
  onClose: () => void;
}

export interface EditFindingModalProps {
  isOpen: boolean;
  onClose: () => void;
  caseDetail: VerificationCaseDetail | null;
  onSave: (payload: { title: string; summary: string; reason: string }) => Promise<void>;
  saving: boolean;
}

export interface RequestContextModalProps {
  isOpen: boolean;
  onClose: () => void;
  caseDetail: VerificationCaseDetail | null;
  members: Array<{ id: string; user_id?: string; user?: { id: string; name?: string; email?: string } }>;
  onSubmit: (payload: { targetUserId: string; question: string; informationType: string }) => Promise<void>;
  submitting: boolean;
}

export interface HandoverEligibilityBadgeProps {
  eligibility: HandoverEligibilityResponse | null;
  loading: boolean;
}
