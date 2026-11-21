"""Fail-closed source access policy classification and pre-retrieval ACL enforcement."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.exceptions import ForbiddenError
from app.models.enums import (
    AuditOutcome,
    EvidenceProcessingStatus,
    EvidenceSourceType,
    SourcePermissionVerificationStatus,
    SourceVisibilityPolicy,
)
from app.models.evidence import EvidenceItem
from app.models.integration import SourceAccessPolicy
from app.services.audit import AuditService
from app.services.rbac import ProjectContext

logger = logging.getLogger(__name__)


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
        evidence: EvidenceItem | None,
        user_id: uuid.UUID,
        has_project_manage: bool,
    ) -> bool:
        """Return True ONLY when platform RBAC + source ACL rules both allow inspection."""
        if evidence is None:
            return False
        if (
            evidence.deleted_at is not None
            or evidence.processing_status == EvidenceProcessingStatus.DELETED.value
        ):
            return False

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

    def can_user_access_evidence_safe(
        self,
        *,
        evidence: EvidenceItem | None,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        has_project_manage: bool,
    ) -> bool:
        """Fail-closed wrapper enforcing project scope, deletion check, and exception safety."""
        if evidence is None or evidence.project_id != project_id:
            return False
        try:
            return bool(
                self.can_user_access_evidence(
                    evidence=evidence,
                    user_id=user_id,
                    has_project_manage=has_project_manage,
                )
            )
        except Exception:
            logger.warning(
                "Source ACL evaluation failed closed for evidence_id=%s project_id=%s",
                evidence.id,
                project_id,
            )
            return False

    def evaluate_evidence_batch(
        self,
        session: Session,
        evidence_ids: Iterable[uuid.UUID | None],
        *,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        has_project_manage: bool,
    ) -> dict[uuid.UUID, tuple[bool, EvidenceItem | None]]:
        """Batch-evaluate viewer source ACL for a set of evidence IDs in <=2 SQL queries.

        Never caches decisions across users. Always fails closed for missing,
        deleted, cross-project, or evaluation-error evidence records.
        """
        unique_ids = {eid for eid in evidence_ids if eid is not None}
        if not unique_ids:
            return {}

        try:
            rows = (
                session.execute(
                    select(EvidenceItem)
                    .where(
                        EvidenceItem.id.in_(unique_ids),
                        EvidenceItem.project_id == project_id,
                    )
                    .options(joinedload(EvidenceItem.source_access_policy))
                )
                .scalars()
                .all()
            )
        except Exception:
            logger.warning(
                "Batch source ACL query failed closed for project_id=%s count=%d",
                project_id,
                len(unique_ids),
            )
            return {eid: (False, None) for eid in unique_ids}

        ev_map: dict[uuid.UUID, EvidenceItem] = {ev.id: ev for ev in rows}
        results: dict[uuid.UUID, tuple[bool, EvidenceItem | None]] = {}
        for eid in unique_ids:
            ev = ev_map.get(eid)
            allowed = self.can_user_access_evidence_safe(
                evidence=ev,
                project_id=project_id,
                user_id=user_id,
                has_project_manage=has_project_manage,
            )
            results[eid] = (allowed, ev)
        return results

    def list_restricted_titles_for_viewer(
        self,
        session: Session,
        *,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        has_project_manage: bool,
    ) -> set[str]:
        """Return titles of project evidence items that the viewer is NOT authorized to inspect.

        Used to scrub restricted source titles that may appear inside derived
        machine assessments (e.g., freshness supersession or contradiction candidates).
        """
        try:
            restricted_candidates = (
                session.execute(
                    select(EvidenceItem)
                    .outerjoin(
                        SourceAccessPolicy,
                        EvidenceItem.source_access_policy_id == SourceAccessPolicy.id,
                    )
                    .where(
                        EvidenceItem.project_id == project_id,
                        or_(
                            EvidenceItem.acl_scope != "project_members",
                            EvidenceItem.deleted_at.is_not(None),
                            EvidenceItem.processing_status == EvidenceProcessingStatus.DELETED.value,
                            SourceAccessPolicy.sync_permission_status
                            == SourcePermissionVerificationStatus.REVOKED.value,
                            SourceAccessPolicy.visibility_policy
                            != SourceVisibilityPolicy.PROJECT_MEMBERS_VERIFIED.value,
                        ),
                    )
                    .options(joinedload(EvidenceItem.source_access_policy))
                )
                .scalars()
                .all()
            )
        except Exception:
            logger.warning(
                "Restricted-title lookup failed for project_id=%s",
                project_id,
            )
            return set()

        restricted_titles: set[str] = set()
        for ev in restricted_candidates:
            allowed = self.can_user_access_evidence_safe(
                evidence=ev,
                project_id=project_id,
                user_id=user_id,
                has_project_manage=has_project_manage,
            )
            if not allowed and ev.title and ev.title.strip():
                restricted_titles.add(ev.title.strip())
        return restricted_titles

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
