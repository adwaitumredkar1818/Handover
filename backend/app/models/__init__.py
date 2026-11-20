"""ORM model package exporting canonical SQLAlchemy metadata for Alembic discovery."""

from app.db.base import Base
from app.models.audit import AuditLog
from app.models.auth import PasswordResetToken, RefreshSession
from app.models.evidence import (
    EvidenceChunk,
    EvidenceContent,
    EvidenceItem,
    EvidencePageContent,
)
from app.models.integration import (
    OAuthState,
    ProjectSourceMapping,
    SourceAccessPolicy,
    SourceConnection,
    SourceSyncRun,
    UserSourceAuthorisation,
)
from app.models.job import BackgroundJob
from app.models.knowledge import (
    KnowledgeEvidenceLink,
    KnowledgeExtractionRun,
    KnowledgeItem,
)
from app.models.organisation import (
    Organisation,
    OrganisationInvitation,
    OrganisationMembership,
)
from app.models.project import Project, ProjectMembership, ProjectTransition
from app.models.rbac import Permission, Role, RolePermission, UserRole
from app.models.relationship import (
    DecisionTraceabilityChain,
    EntityAlias,
    IdentityResolutionCandidate,
    KnowledgeEntity,
    KnowledgeRelationship,
    KnowledgeTimelineEvent,
    RelationshipEvidenceLink,
    RelationshipReconstructionRun,
)
from app.models.user import User
from app.models.vector_index import ProjectVectorIndex
from app.models.verification import (
    VerificationCase,
    VerificationConflict,
    VerificationContextRequest,
    VerificationEvidenceRef,
    VerificationFindingRevision,
    VerificationIssue,
    VerificationReviewEvent,
)
from app.models.handover import (
    HandoverAcknowledgement,
    HandoverCase,
    HandoverChecklist,
    HandoverChecklistItem,
    HandoverContentLink,
    HandoverDelivery,
    HandoverOwnershipTransfer,
    HandoverPackage,
    HandoverPackageSection,
    HandoverPackageVersion,
    HandoverReadinessAssessment,
    HandoverResponsibilityTransfer,
    HandoverSignoff,
    HandoverStatusHistory,
    ProjectOnboardingProgress,
)
from app.models.assistant import (
    AssistantCitation,
    AssistantConversation,
    AssistantFeedback,
    AssistantMessage,
    AssistantRetrievalRun,
)
from app.models.notification import NotificationItem
from app.models.team_roster import ContributionAttribution, TeamRosterMember

__all__ = [
    "AssistantCitation",
    "AssistantConversation",
    "AssistantFeedback",
    "AssistantMessage",
    "AssistantRetrievalRun",
    "AuditLog",
    "BackgroundJob",
    "Base",
    "ContributionAttribution",
    "DecisionTraceabilityChain",
    "EntityAlias",
    "EvidenceChunk",
    "EvidenceContent",
    "EvidenceItem",
    "EvidencePageContent",
    "HandoverAcknowledgement",
    "HandoverCase",
    "HandoverChecklist",
    "HandoverChecklistItem",
    "HandoverContentLink",
    "HandoverDelivery",
    "HandoverOwnershipTransfer",
    "HandoverPackage",
    "HandoverPackageSection",
    "HandoverPackageVersion",
    "HandoverReadinessAssessment",
    "HandoverResponsibilityTransfer",
    "HandoverSignoff",
    "HandoverStatusHistory",
    "IdentityResolutionCandidate",
    "KnowledgeEntity",
    "KnowledgeEvidenceLink",
    "KnowledgeExtractionRun",
    "KnowledgeItem",
    "KnowledgeRelationship",
    "KnowledgeTimelineEvent",
    "NotificationItem",
    "OAuthState",
    "Organisation",
    "OrganisationInvitation",
    "OrganisationMembership",
    "PasswordResetToken",
    "Permission",
    "Project",
    "ProjectMembership",
    "ProjectOnboardingProgress",
    "ProjectSourceMapping",
    "ProjectTransition",
    "ProjectVectorIndex",
    "RefreshSession",
    "RelationshipEvidenceLink",
    "RelationshipReconstructionRun",
    "Role",
    "RolePermission",
    "SourceAccessPolicy",
    "SourceConnection",
    "SourceSyncRun",
    "TeamRosterMember",
    "User",
    "UserRole",
    "UserSourceAuthorisation",
    "VerificationCase",
    "VerificationConflict",
    "VerificationContextRequest",
    "VerificationEvidenceRef",
    "VerificationFindingRevision",
    "VerificationIssue",
    "VerificationReviewEvent",
]
