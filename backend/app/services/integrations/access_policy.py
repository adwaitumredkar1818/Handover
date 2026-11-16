"""Fail-closed source access policy classification and pre-retrieval ACL enforcement."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenError
from app.models.enums import (
    AuditOutcome,
    EvidenceSourceType,
    SourcePermissionVerificationStatus,
    SourceVisibilityPolicy,
)
from app.models.evidence import EvidenceItem
from app.services.audit import AuditService
from app.services.rbac import ProjectContext


@dataclass(frozen=True, slots=True)
class PolicyClassification:
    """Resolved `acl_scope` and `visibility_policy` for a mapped or ingested source item."""

    acl_scope: str
    visibility_policy: str


class SourceAccessPolicyService:
    """Computes and enforces fail-closed delegated source ACLs on evidence access."""

    def classify_github_repository(
        self,
        *,
        visibility: str | None,
        is_private: bool,
        restrict_to_verified_users: bool | None = None,
    ) -> PolicyClassification:
        normalized_vis = (visibility or "").strip().lower()
        if restrict_to_verified_users is True:
            return PolicyClassification(
                acl_scope="source_restricted",
                visibility_policy=SourceVisibilityPolicy.RESTRICTED_FAIL_CLOSED.value,
            )
        if is_private or normalized_vis in {"private", "internal"} or normalized_vis != "public":
            return PolicyClassification(
                acl_scope="source_restricted",
                visibility_policy=SourceVisibilityPolicy.VERIFIED_SOURCE_ACL.value,
            )
        return PolicyClassification(
            acl_scope="project_members",
            visibility_policy=SourceVisibilityPolicy.PROJECT_MEMBERS_VERIFIED.value,
        )

    def classify_jira_project(self) -> PolicyClassification:
        """Jira projects are always governed fail-closed by verified Jira project access."""
        return PolicyClassification(
            acl_scope="source_restricted",
            visibility_policy=SourceVisibilityPolicy.VERIFIED_SOURCE_ACL.value,
        )

    def classify_jira_security_level(self) -> PolicyClassification:
        """Jira issues carrying issue-level security schemes fail closed to verified holders."""
        return PolicyClassification(
            acl_scope="source_restricted",
            visibility_policy=SourceVisibilityPolicy.RESTRICTED_FAIL_CLOSED.value,
        )

    def classify_slack_channel(
        self,
        *,
        is_private: bool = False,
    ) -> PolicyClassification:
        """Classify a Slack channel: private channels require verified source ACL."""
        if is_private:
            return PolicyClassification(
                acl_scope="source_restricted",
                visibility_policy=SourceVisibilityPolicy.VERIFIED_SOURCE_ACL.value,
            )
        return PolicyClassification(
            acl_scope="project_members",
            visibility_policy=SourceVisibilityPolicy.PROJECT_MEMBERS_VERIFIED.value,
        )

    def classify_resource(
        self,
        *,
        provider: str,
        resource_visibility: str = "private",
        policy: Any = None,
        is_private: bool | None = None,
    ) -> PolicyClassification:
        """Generic classification dispatcher for connected resources."""
        norm = provider.strip().lower()
        if norm == "slack":
            private_flag = is_private if is_private is not None else (resource_visibility == "private")
            return self.classify_slack_channel(is_private=private_flag)
        elif norm == "github":
            return self.classify_github_repository(
                visibility=resource_visibility,
                is_private=(resource_visibility in ("private", "internal")),
            )
        elif norm == "jira":
            return self.classify_jira_project()
        return PolicyClassification(
            acl_scope="source_restricted",
            visibility_policy=SourceVisibilityPolicy.VERIFIED_SOURCE_ACL.value,
        )

    def can_user_access_evidence(
        self,
        *,
        evidence: EvidenceItem,
        user_id: uuid.UUID,
        has_project_manage: bool,
    ) -> bool:
        """Return True ONLY when platform RBAC + source ACL rules both allow inspection."""
        is_legacy_upload = (
            evidence.source_type == EvidenceSourceType.DOCUMENT_UPLOAD.value
            and evidence.source_access_policy_id is None
            and evidence.source_connection_id is None
        )

        if evidence.acl_scope == "project_members":
            policy = evidence.source_access_policy
            if policy is not None:
                if (
                    policy.sync_permission_status
                    == SourcePermissionVerificationStatus.REVOKED.value
                ):
                    return False
                if (
                    policy.visibility_policy
                    != SourceVisibilityPolicy.PROJECT_MEMBERS_VERIFIED.value
                ):
                    return str(user_id) in (policy.allowed_user_ids or [])
            return True

        if evidence.acl_scope == "source_restricted":
            if is_legacy_upload:
                return has_project_manage or evidence.uploaded_by_user_id == user_id
            policy = evidence.source_access_policy
            if policy is None:
                return False
            if (
                policy.sync_permission_status
                == SourcePermissionVerificationStatus.REVOKED.value
            ):
                return False
            return str(user_id) in (policy.allowed_user_ids or [])

        return False

    def enforce_evidence_access(
        self,
        *,
        evidence: EvidenceItem,
        project_ctx: ProjectContext,
        session: Session,
        audit_service: AuditService,
    ) -> None:
        """Fail closed and emit an immutable audit record if source ACL blocks the caller."""
        allowed = self.can_user_access_evidence(
            evidence=evidence,
            user_id=project_ctx.principal.user.id,
            has_project_manage=project_ctx.has_permission("project.manage"),
        )
        if allowed:
            return

        audit_service.record_event(
            event_type="evidence.source_acl_denied",
            resource_type="evidence_item",
            actor_user_id=project_ctx.principal.user.id,
            organisation_id=evidence.organisation_id,
            project_id=evidence.project_id,
            resource_id=str(evidence.id),
            outcome=AuditOutcome.DENIED.value,
            metadata={
                "source_type": evidence.source_type,
                "acl_scope": evidence.acl_scope,
                "source_access_policy_id": (
                    str(evidence.source_access_policy_id)
                    if evidence.source_access_policy_id
                    else None
                ),
            },
            message="Denied access to source-restricted evidence item.",
            level=logging.WARNING,
        )
        session.commit()
        raise ForbiddenError(
            "You lack delegated source access to inspect this evidence item.",
            code="SOURCE_ACCESS_DENIED",
        )
