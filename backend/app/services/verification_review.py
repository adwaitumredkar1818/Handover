"""Human review workflow, state machine, and ACL-enforced detail builder."""

from __future__ import annotations

import copy
import os
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.cache.local_cache import LocalTTLCache
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, UnprocessableEntityError
from app.core.logging import get_correlation_id
from app.models.enums import (
    AuditOutcome,
    ConflictResolutionState,
    ContextRequestStatus,
    EpistemicStatus,
    IssueResolutionState,
    KnowledgeReviewStatus,
    ProjectMembershipStatus,
    RelationshipVerificationStatus,
    ReviewActionType,
    SourcePermissionVerificationStatus,
    UserStatus,
    VerificationCaseStatus,
    VerificationTargetType,
)
from app.models.evidence import EvidenceItem
from app.models.integration import SourceAccessPolicy
from app.models.knowledge import KnowledgeEvidenceLink, KnowledgeItem
from app.models.project import ProjectMembership
from app.models.relationship import KnowledgeRelationship, RelationshipEvidenceLink
from app.models.user import User
from app.models.verification import (
    VerificationCase,
    VerificationConflict,
    VerificationContextRequest,
    VerificationEvidenceRef,
    VerificationFindingRevision,
    VerificationReviewEvent,
)
from app.repositories.audit import AuditLogRepository
from app.repositories.verification import VerificationRepository
from app.schemas.verification import (
    ApproveFindingRequest,
    ConflictClaimSide,
    EditFindingRequest,
    EvidenceReferenceDetail,
    MarkUnresolvedRequest,
    RejectFindingRequest,
    RequestContextRequest,
    RespondContextRequest,
    VerificationCaseDetailResponse,
    VerificationConflictPreview,
    VerificationContextRequestDetail,
    VerificationIssueDetail,
    VerificationQueueItem,
    VerificationQueueResponse,
    VerificationReviewEventDetail,
    VerificationRevisionDetail,
    VerificationSummaryResponse,
)
from app.services.audit import AuditService
from app.services.handover_sections import redact_secrets
from app.services.integrations.access_policy import SourceAccessPolicyService
from app.services.rbac import ProjectContext

_REDACTED_FINDING_TITLE = "[Restricted finding]"
_REDACTED_SOURCE_TITLE = "[Restricted source]"
_REDACTED_CLAIM_TEXT = "[Content redacted: insufficient source permissions]"
_REDACTED_EXPLANATION = "[Explanation redacted: references restricted source evidence]"
_REDACTED_ISSUE_DESC = "[Issue details redacted: references restricted source evidence]"
_REDACTED_DERIVED_TEXT = "[Redacted: references restricted source evidence]"

_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    VerificationCaseStatus.CANDIDATE.value: {
        VerificationCaseStatus.PENDING_REVIEW.value,
        VerificationCaseStatus.CONFLICTED.value,
        VerificationCaseStatus.UNRESOLVED.value,
        VerificationCaseStatus.VERIFIED.value,
        VerificationCaseStatus.REJECTED.value,
    },
    VerificationCaseStatus.PENDING_REVIEW.value: {
        VerificationCaseStatus.PENDING_REVIEW.value,
        VerificationCaseStatus.CONFLICTED.value,
        VerificationCaseStatus.UNRESOLVED.value,
        VerificationCaseStatus.VERIFIED.value,
        VerificationCaseStatus.REJECTED.value,
    },
    VerificationCaseStatus.CONFLICTED.value: {
        VerificationCaseStatus.PENDING_REVIEW.value,
        VerificationCaseStatus.UNRESOLVED.value,
        VerificationCaseStatus.VERIFIED.value,
        VerificationCaseStatus.REJECTED.value,
    },
    VerificationCaseStatus.UNRESOLVED.value: {
        VerificationCaseStatus.PENDING_REVIEW.value,
        VerificationCaseStatus.CONFLICTED.value,
        VerificationCaseStatus.VERIFIED.value,
        VerificationCaseStatus.REJECTED.value,
    },
    VerificationCaseStatus.VERIFIED.value: {
        VerificationCaseStatus.PENDING_REVIEW.value,
        VerificationCaseStatus.CONFLICTED.value,
        VerificationCaseStatus.UNRESOLVED.value,
        VerificationCaseStatus.REJECTED.value,
    },
    VerificationCaseStatus.REJECTED.value: {
        VerificationCaseStatus.PENDING_REVIEW.value,
    },
}


_VERIF_READ_CACHE = LocalTTLCache(max_items=512)


def invalidate_verification_read_cache(project_id: uuid.UUID) -> None:
    _VERIF_READ_CACHE.invalidate_prefix(f"vsum:{project_id}:")
    _VERIF_READ_CACHE.invalidate_prefix(f"vq:{project_id}:")


class VerificationReviewService:
    """Orchestrates Verification Center reads, ACL filtering, and human review actions."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = VerificationRepository(session)
        self.audit = AuditService(audit_repository=AuditLogRepository(session))
        self.access_policy = SourceAccessPolicyService()

    # -----------------------------------------------------------------------
    # Batch ACL & Derived-Content Sanitization Helpers
    # -----------------------------------------------------------------------

    def _verify_viewer_access(self, project_ctx: ProjectContext) -> tuple[uuid.UUID, bool]:
        """Fail-closed validation that the caller is an active project member."""
        user = getattr(getattr(project_ctx, "principal", None), "user", None)
        if user is None or user.status != UserStatus.ACTIVE.value:
            raise ForbiddenError("Active authenticated user is required.", code="USER_INACTIVE")
        has_manage = project_ctx.has_permission("project.manage")
        if not has_manage:
            membership = self.session.execute(
                select(ProjectMembership).where(
                    ProjectMembership.project_id == project_ctx.project.id,
                    ProjectMembership.user_id == user.id,
                    ProjectMembership.status == ProjectMembershipStatus.ACTIVE.value,
                )
            ).scalar_one_or_none()
            if membership is None:
                raise ForbiddenError(
                    "Active project membership is required.",
                    code="PROJECT_MEMBERSHIP_REQUIRED",
                )
        return user.id, has_manage

    @staticmethod
    def _parse_uuid(value: Any) -> uuid.UUID | None:
        if isinstance(value, uuid.UUID):
            return value
        if isinstance(value, str) and value.strip():
            try:
                return uuid.UUID(value.strip())
            except ValueError:
                return None
        return None

    def _extract_assessment_evidence_ids(self, assessment: dict[str, Any] | None) -> set[uuid.UUID]:
        ids: set[uuid.UUID] = set()
        if not isinstance(assessment, dict):
            return ids
        ca = assessment.get("contradiction_analysis")
        if isinstance(ca, dict):
            for cand in ca.get("contradictions") or []:
                if isinstance(cand, dict):
                    for key in ("side_a_evidence_id", "side_b_evidence_id"):
                        parsed = self._parse_uuid(cand.get(key))
                        if parsed is not None:
                            ids.add(parsed)
        fa = assessment.get("freshness_assessment")
        if isinstance(fa, dict):
            parsed = self._parse_uuid(fa.get("superseded_by_evidence_id"))
            if parsed is not None:
                ids.add(parsed)
        ms = assessment.get("monitoring_status")
        if isinstance(ms, dict):
            parsed = self._parse_uuid(ms.get("last_evidence_change_id"))
            if parsed is not None:
                ids.add(parsed)
        return ids

    def _batch_evaluate_cases_acl(
        self,
        cases: list[VerificationCase],
        *,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        has_manage: bool,
    ) -> tuple[
        dict[uuid.UUID, tuple[bool, EvidenceItem | None]],
        dict[uuid.UUID, set[uuid.UUID]],
    ]:
        """Batch-evaluate ACL for all evidence referenced across cases in <=3 SQL queries."""
        ev_ids: set[uuid.UUID] = set()
        unref_ki_case_map: dict[uuid.UUID, list[uuid.UUID]] = {}
        unref_rel_case_map: dict[uuid.UUID, list[uuid.UUID]] = {}

        for case in cases:
            if case.evidence_refs:
                for ref in case.evidence_refs:
                    ev_ids.add(ref.evidence_item_id)
            else:
                if case.target_type == VerificationTargetType.KNOWLEDGE_ITEM.value:
                    unref_ki_case_map.setdefault(case.target_id, []).append(case.id)
                elif case.target_type == VerificationTargetType.RELATIONSHIP.value:
                    unref_rel_case_map.setdefault(case.target_id, []).append(case.id)

            for conf in case.conflicts:
                if conf.claim_a_source_evidence_id is not None:
                    ev_ids.add(conf.claim_a_source_evidence_id)
                if conf.claim_b_source_evidence_id is not None:
                    ev_ids.add(conf.claim_b_source_evidence_id)

            for iss in case.issues:
                if iss.conflicting_evidence_id is not None:
                    ev_ids.add(iss.conflicting_evidence_id)

            ev_ids.update(self._extract_assessment_evidence_ids(case.machine_assessment_json))

        fallback_target_evs: dict[uuid.UUID, set[uuid.UUID]] = {}
        if unref_ki_case_map:
            kl_rows = self.session.execute(
                select(
                    KnowledgeEvidenceLink.knowledge_item_id,
                    KnowledgeEvidenceLink.evidence_id,
                ).where(
                    KnowledgeEvidenceLink.project_id == project_id,
                    KnowledgeEvidenceLink.knowledge_item_id.in_(unref_ki_case_map.keys()),
                )
            ).all()
            for ki_id, eid in kl_rows:
                ev_ids.add(eid)
                for cid in unref_ki_case_map.get(ki_id, []):
                    fallback_target_evs.setdefault(cid, set()).add(eid)

        if unref_rel_case_map:
            rl_rows = self.session.execute(
                select(
                    RelationshipEvidenceLink.relationship_id,
                    RelationshipEvidenceLink.evidence_id,
                ).where(
                    RelationshipEvidenceLink.project_id == project_id,
                    RelationshipEvidenceLink.relationship_id.in_(unref_rel_case_map.keys()),
                )
            ).all()
            for rel_id, eid in rl_rows:
                ev_ids.add(eid)
                for cid in unref_rel_case_map.get(rel_id, []):
                    fallback_target_evs.setdefault(cid, set()).add(eid)

        acl_map = self.access_policy.evaluate_evidence_batch(
            self.session,
            ev_ids,
            project_id=project_id,
            user_id=user_id,
            has_project_manage=has_manage,
        )
        return acl_map, fallback_target_evs

    @staticmethod
    def _classify_case_access(
        case: VerificationCase,
        acl_map: dict[uuid.UUID, tuple[bool, EvidenceItem | None]],
        fallback_target_evs: dict[uuid.UUID, set[uuid.UUID]],
    ) -> tuple[list[VerificationEvidenceRef], int, bool]:
        """Return (accessible_refs, restricted_ref_count, fully_restricted)."""
        if case.evidence_refs:
            accessible: list[VerificationEvidenceRef] = []
            restricted_count = 0
            for ref in case.evidence_refs:
                allowed, ev = acl_map.get(ref.evidence_item_id, (False, None))
                if allowed and ev is not None:
                    accessible.append(ref)
                else:
                    restricted_count += 1
            fully_restricted = len(accessible) == 0 and restricted_count > 0
            return accessible, restricted_count, fully_restricted

        target_evs = fallback_target_evs.get(case.id, set())
        if target_evs:
            accessible_cnt = sum(
                1 for eid in target_evs if acl_map.get(eid, (False, None))[0]
            )
            restricted_cnt = len(target_evs) - accessible_cnt
            fully_restricted = accessible_cnt == 0 and restricted_cnt > 0
            return [], restricted_cnt, fully_restricted

        return [], 0, False

    @staticmethod
    def _text_mentions_restricted(text: str | None, restricted_titles: set[str]) -> bool:
        if not text or not restricted_titles:
            return False
        low = text.lower()
        return any(len(t) >= 3 and t.lower() in low for t in restricted_titles)

    def _scrub_derived_text(
        self,
        text: str | None,
        *,
        restricted_titles: set[str],
        replacement: str = _REDACTED_DERIVED_TEXT,
    ) -> str | None:
        if text is None:
            return None
        if self._text_mentions_restricted(text, restricted_titles):
            return replacement
        return redact_secrets(text)

    def _sanitize_machine_assessment(
        self,
        raw_assessment: dict[str, Any] | None,
        *,
        fully_restricted: bool,
        restricted_ref_count: int,
        any_conflict_restricted: bool,
        acl_map: dict[uuid.UUID, tuple[bool, EvidenceItem | None]],
        restricted_titles: set[str],
    ) -> dict[str, Any]:
        """Return a viewer-safe copy of machine_assessment_json with zero restricted leakage."""
        if fully_restricted or not raw_assessment:
            return {}

        assessment = copy.deepcopy(dict(raw_assessment))

        ca = assessment.get("contradiction_analysis")
        if isinstance(ca, dict):
            raw_cands = ca.get("contradictions") or []
            safe_cands: list[dict[str, Any]] = []
            had_redacted_cand = False
            for cand in raw_cands:
                if not isinstance(cand, dict):
                    continue
                ev_a_id = self._parse_uuid(cand.get("side_a_evidence_id"))
                ev_b_id = self._parse_uuid(cand.get("side_b_evidence_id"))
                allow_a = (
                    acl_map.get(ev_a_id, (False, None))[0]
                    if ev_a_id is not None
                    else not (
                        self._text_mentions_restricted(cand.get("side_a_title"), restricted_titles)
                        or self._text_mentions_restricted(cand.get("side_a_claim"), restricted_titles)
                        or any_conflict_restricted
                        or restricted_ref_count > 0
                    )
                )
                allow_b = (
                    acl_map.get(ev_b_id, (False, None))[0]
                    if ev_b_id is not None
                    else not (
                        self._text_mentions_restricted(cand.get("side_b_title"), restricted_titles)
                        or self._text_mentions_restricted(cand.get("side_b_claim"), restricted_titles)
                        or any_conflict_restricted
                        or restricted_ref_count > 0
                    )
                )
                if not allow_a and not allow_b:
                    had_redacted_cand = True
                    continue
                sanitized_cand = dict(cand)
                if not allow_a:
                    had_redacted_cand = True
                    sanitized_cand["side_a_title"] = _REDACTED_SOURCE_TITLE
                    sanitized_cand["side_a_claim"] = _REDACTED_CLAIM_TEXT
                    sanitized_cand["side_a_provider"] = "restricted"
                    sanitized_cand.pop("side_a_evidence_id", None)
                else:
                    sanitized_cand["side_a_title"] = self._scrub_derived_text(
                        sanitized_cand.get("side_a_title"),
                        restricted_titles=restricted_titles,
                        replacement=_REDACTED_SOURCE_TITLE,
                    )
                    sanitized_cand["side_a_claim"] = self._scrub_derived_text(
                        sanitized_cand.get("side_a_claim"),
                        restricted_titles=restricted_titles,
                        replacement=_REDACTED_CLAIM_TEXT,
                    )
                if not allow_b:
                    had_redacted_cand = True
                    sanitized_cand["side_b_title"] = _REDACTED_SOURCE_TITLE
                    sanitized_cand["side_b_claim"] = _REDACTED_CLAIM_TEXT
                    sanitized_cand["side_b_provider"] = "restricted"
                    sanitized_cand.pop("side_b_evidence_id", None)
                else:
                    sanitized_cand["side_b_title"] = self._scrub_derived_text(
                        sanitized_cand.get("side_b_title"),
                        restricted_titles=restricted_titles,
                        replacement=_REDACTED_SOURCE_TITLE,
                    )
                    sanitized_cand["side_b_claim"] = self._scrub_derived_text(
                        sanitized_cand.get("side_b_claim"),
                        restricted_titles=restricted_titles,
                        replacement=_REDACTED_CLAIM_TEXT,
                    )
                if not (allow_a and allow_b) or self._text_mentions_restricted(
                    sanitized_cand.get("explanation"), restricted_titles
                ):
                    sanitized_cand["explanation"] = _REDACTED_EXPLANATION
                else:
                    sanitized_cand["explanation"] = redact_secrets(sanitized_cand.get("explanation"))
                safe_cands.append(sanitized_cand)

            ca["contradictions"] = safe_cands
            ca["contradiction_count"] = len(safe_cands)
            ca["has_contradiction"] = len(safe_cands) > 0
            if had_redacted_cand or any_conflict_restricted or self._text_mentions_restricted(
                ca.get("summary"), restricted_titles
            ):
                ca["summary"] = _REDACTED_EXPLANATION if safe_cands else "No accessible contradictions."
            elif isinstance(ca.get("summary"), str):
                ca["summary"] = redact_secrets(ca["summary"])

        fa = assessment.get("freshness_assessment")
        if isinstance(fa, dict):
            sup_ev_id = self._parse_uuid(fa.get("superseded_by_evidence_id"))
            sup_title = fa.get("superseded_by_record_title")
            sup_restricted = False
            if sup_ev_id is not None and not acl_map.get(sup_ev_id, (False, None))[0]:
                sup_restricted = True
            if isinstance(sup_title, str) and sup_title.strip():
                if self._text_mentions_restricted(sup_title, restricted_titles):
                    sup_restricted = True
            if sup_restricted:
                fa["superseded_by_record_title"] = _REDACTED_SOURCE_TITLE
                fa.pop("superseded_by_evidence_id", None)
                fa["explanation"] = _REDACTED_DERIVED_TEXT
            else:
                if isinstance(sup_title, str):
                    fa["superseded_by_record_title"] = redact_secrets(sup_title)
                if isinstance(fa.get("explanation"), str):
                    fa["explanation"] = self._scrub_derived_text(
                        fa["explanation"], restricted_titles=restricted_titles
                    )
            if isinstance(fa.get("recommendations"), list):
                fa["recommendations"] = [
                    self._scrub_derived_text(str(r), restricted_titles=restricted_titles) or ""
                    for r in fa["recommendations"]
                ]

        ms = assessment.get("monitoring_status")
        if isinstance(ms, dict):
            ch_id = self._parse_uuid(ms.get("last_evidence_change_id"))
            if (ch_id is not None and not acl_map.get(ch_id, (False, None))[0]) or (
                self._text_mentions_restricted(ms.get("reverification_reason"), restricted_titles)
            ):
                ms["last_evidence_change_id"] = None
                ms["reverification_reason"] = _REDACTED_DERIVED_TEXT

        comp = assessment.get("completeness_assessment")
        if isinstance(comp, dict):
            if restricted_ref_count > 0:
                comp["evidence_accessible"] = False
            if isinstance(comp.get("explanation"), str):
                comp["explanation"] = self._scrub_derived_text(
                    comp["explanation"], restricted_titles=restricted_titles
                )

        rel = assessment.get("reliability_assessment")
        if isinstance(rel, dict):
            if isinstance(rel.get("explanation"), str):
                rel["explanation"] = self._scrub_derived_text(
                    rel["explanation"], restricted_titles=restricted_titles
                )
            if isinstance(rel.get("factors"), list):
                rel["factors"] = [
                    self._scrub_derived_text(str(f), restricted_titles=restricted_titles) or ""
                    for f in rel["factors"]
                ]

        corrob = assessment.get("corroboration_assessment")
        if isinstance(corrob, dict):
            if isinstance(corrob.get("explanation"), str):
                corrob["explanation"] = self._scrub_derived_text(
                    corrob["explanation"], restricted_titles=restricted_titles
                )

        rec = assessment.get("recommendation")
        if isinstance(rec, dict):
            if isinstance(rec.get("reason"), str):
                rec["reason"] = self._scrub_derived_text(
                    rec["reason"], restricted_titles=restricted_titles
                )
            if isinstance(rec.get("supporting_factors"), list):
                rec["supporting_factors"] = [
                    self._scrub_derived_text(str(f), restricted_titles=restricted_titles) or ""
                    for f in rec["supporting_factors"]
                ]

        if isinstance(assessment.get("priority_reason"), str):
            assessment["priority_reason"] = self._scrub_derived_text(
                assessment["priority_reason"], restricted_titles=restricted_titles
            )

        return assessment

    # -----------------------------------------------------------------------
    # Read Queries (Fail-Closed Per-Viewer ACL Enforced)
    # -----------------------------------------------------------------------

    def _batch_evaluate_lightweight_acl(
        self,
        light_data: dict[str, Any],
        *,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        has_manage: bool,
    ) -> tuple[
        dict[uuid.UUID, tuple[bool, EvidenceItem | None]],
        dict[uuid.UUID, set[uuid.UUID]],
    ]:
        """Batch-evaluate ACL for lightweight VerificationCase rows in <=3 SQL queries."""
        ev_ids: set[uuid.UUID] = set()
        unref_ki_case_map: dict[uuid.UUID, list[uuid.UUID]] = {}
        unref_rel_case_map: dict[uuid.UUID, list[uuid.UUID]] = {}

        refs_by_case = light_data["refs_by_case"]
        open_issues_by_case = light_data["open_issues_by_case"]
        conflicts_by_case = light_data["conflicts_by_case"]

        for row in light_data["cases"]:
            cid = row.id
            c_refs = refs_by_case.get(cid)
            if c_refs:
                ev_ids.update(c_refs)
            else:
                if row.target_type == VerificationTargetType.KNOWLEDGE_ITEM.value:
                    unref_ki_case_map.setdefault(row.target_id, []).append(cid)
                elif row.target_type == VerificationTargetType.RELATIONSHIP.value:
                    unref_rel_case_map.setdefault(row.target_id, []).append(cid)

            for _, ev_a, ev_b in conflicts_by_case.get(cid, ()):
                if ev_a is not None:
                    ev_ids.add(ev_a)
                if ev_b is not None:
                    ev_ids.add(ev_b)
            for _, conf_ev_id in open_issues_by_case.get(cid, ()):
                if conf_ev_id is not None:
                    ev_ids.add(conf_ev_id)

        fallback_target_evs: dict[uuid.UUID, set[uuid.UUID]] = {}
        if unref_ki_case_map:
            kl_rows = self.session.execute(
                select(
                    KnowledgeEvidenceLink.knowledge_item_id,
                    KnowledgeEvidenceLink.evidence_id,
                ).where(
                    KnowledgeEvidenceLink.project_id == project_id,
                    KnowledgeEvidenceLink.knowledge_item_id.in_(unref_ki_case_map.keys()),
                )
            ).all()
            for ki_id, eid in kl_rows:
                ev_ids.add(eid)
                for cid in unref_ki_case_map.get(ki_id, []):
                    fallback_target_evs.setdefault(cid, set()).add(eid)

        if unref_rel_case_map:
            rl_rows = self.session.execute(
                select(
                    RelationshipEvidenceLink.relationship_id,
                    RelationshipEvidenceLink.evidence_id,
                ).where(
                    RelationshipEvidenceLink.project_id == project_id,
                    RelationshipEvidenceLink.relationship_id.in_(unref_rel_case_map.keys()),
                )
            ).all()
            for rel_id, eid in rl_rows:
                ev_ids.add(eid)
                for cid in unref_rel_case_map.get(rel_id, []):
                    fallback_target_evs.setdefault(cid, set()).add(eid)

        acl_map = self.access_policy.evaluate_evidence_batch(
            self.session,
            ev_ids,
            project_id=project_id,
            user_id=user_id,
            has_project_manage=has_manage,
        )
        return acl_map, fallback_target_evs

    @staticmethod
    def _classify_lightweight_access(
        row: Any,
        refs_by_case: dict[uuid.UUID, list[uuid.UUID]],
        acl_map: dict[uuid.UUID, tuple[bool, EvidenceItem | None]],
        fallback_target_evs: dict[uuid.UUID, set[uuid.UUID]],
    ) -> tuple[list[uuid.UUID], int, bool]:
        """Return (accessible_ref_ev_ids, restricted_ref_count, fully_restricted)."""
        c_refs = refs_by_case.get(row.id)
        if c_refs:
            accessible: list[uuid.UUID] = []
            restricted_count = 0
            for eid in c_refs:
                allowed, ev = acl_map.get(eid, (False, None))
                if allowed and ev is not None:
                    accessible.append(eid)
                else:
                    restricted_count += 1
            return accessible, restricted_count, len(accessible) == 0
        fallback_ids = fallback_target_evs.get(row.id, set())
        if fallback_ids:
            any_allowed = any(
                acl_map.get(eid, (False, None))[0] and acl_map.get(eid, (False, None))[1] is not None
                for eid in fallback_ids
            )
            return [], (0 if any_allowed else len(fallback_ids)), not any_allowed
        return [], 0, False

    def get_summary(
        self,
        project_id: uuid.UUID,
        *,
        project_ctx: ProjectContext | None = None,
    ) -> VerificationSummaryResponse:
        if project_ctx is None:
            raise ForbiddenError("Project authorization context is required.", code="AUTH_REQUIRED")
        user_id, has_manage = self._verify_viewer_access(project_ctx)

        use_cache = not bool(os.getenv("PYTEST_CURRENT_TEST"))
        cache_key = f"vsum:{project_id}:{user_id}:{has_manage}"
        if use_cache:
            cached = _VERIF_READ_CACHE.get(cache_key)
            if isinstance(cached, dict):
                return VerificationSummaryResponse.model_validate(cached)

        from app.models.verification import (
            VerificationCase,
            VerificationConflict,
            VerificationContextRequest,
            VerificationIssue,
        )

        # Fast SQL GROUP BY path when viewer has full access to all project sources
        policies = list(
            self.session.execute(
                select(SourceAccessPolicy).where(SourceAccessPolicy.project_id == project_id)
            )
            .scalars()
            .all()
        )
        viewer_str = str(user_id)
        has_restrictions = any(
            p.sync_permission_status == SourcePermissionVerificationStatus.REVOKED.value
            or (not has_manage and viewer_str not in (p.allowed_user_ids or []))
            for p in policies
        )
        if not has_restrictions:
            rows = self.session.execute(
                select(VerificationCase.case_status, func.count(VerificationCase.id))
                .where(
                    VerificationCase.project_id == project_id,
                    VerificationCase.case_status != VerificationCaseStatus.ARCHIVED.value,
                )
                .group_by(VerificationCase.case_status)
            ).all()
            if rows:
                status_counts = {str(st): int(cnt) for st, cnt in rows}
                active_subq = select(VerificationCase.id).where(
                    VerificationCase.project_id == project_id,
                    VerificationCase.case_status != VerificationCaseStatus.ARCHIVED.value,
                )
                open_issues = (
                    self.session.execute(
                        select(func.count(VerificationIssue.id)).where(
                            VerificationIssue.case_id.in_(active_subq),
                            VerificationIssue.resolution_state == IssueResolutionState.OPEN.value,
                        )
                    ).scalar()
                    or 0
                )
                open_conflicts = (
                    self.session.execute(
                        select(func.count(VerificationConflict.id)).where(
                            VerificationConflict.case_id.in_(active_subq),
                            VerificationConflict.resolution_state == ConflictResolutionState.UNRESOLVED.value,
                        )
                    ).scalar()
                    or 0
                )
                pending_ctx = (
                    self.session.execute(
                        select(func.count(VerificationContextRequest.id)).where(
                            VerificationContextRequest.case_id.in_(active_subq),
                            VerificationContextRequest.status == ContextRequestStatus.PENDING.value,
                        )
                    ).scalar()
                    or 0
                )
                resp = VerificationSummaryResponse(
                    project_id=project_id,
                    total_cases=sum(status_counts.values()),
                    candidate_count=status_counts.get(VerificationCaseStatus.CANDIDATE.value, 0),
                    pending_review_count=status_counts.get(VerificationCaseStatus.PENDING_REVIEW.value, 0),
                    conflicted_count=status_counts.get(VerificationCaseStatus.CONFLICTED.value, 0),
                    unresolved_count=status_counts.get(VerificationCaseStatus.UNRESOLVED.value, 0),
                    verified_count=status_counts.get(VerificationCaseStatus.VERIFIED.value, 0),
                    rejected_count=status_counts.get(VerificationCaseStatus.REJECTED.value, 0),
                    open_issues_count=int(open_issues),
                    open_conflicts_count=int(open_conflicts),
                    pending_context_requests_count=int(pending_ctx),
                )
                if use_cache:
                    _VERIF_READ_CACHE.set(cache_key, resp.model_dump(mode="json"), ttl_seconds=300)
                return resp

        light_data = self.repo.list_project_cases_lightweight(project_id)
        if not light_data["cases"]:
            from app.services.verification_engine import VerificationEngine

            engine = VerificationEngine(self.session)
            sync_res = engine.sync_project_findings(project_id)
            if sync_res.get("cases_created", 0) > 0:
                self.session.commit()
                light_data = self.repo.list_project_cases_lightweight(project_id)

        acl_map, fallback_target_evs = self._batch_evaluate_lightweight_acl(
            light_data, project_id=project_id, user_id=user_id, has_manage=has_manage
        )
        refs_by_case = light_data["refs_by_case"]
        open_issues_by_case = light_data["open_issues_by_case"]
        conflicts_by_case = light_data["conflicts_by_case"]
        pending_ctx_by_case = light_data["pending_ctx_by_case"]

        status_counts: dict[str, int] = {}
        open_issues = 0
        open_conflicts = 0
        pending_ctx = 0

        for row in light_data["cases"]:
            _, _, fully_restricted = self._classify_lightweight_access(
                row, refs_by_case, acl_map, fallback_target_evs
            )
            if fully_restricted:
                continue

            status_counts[row.case_status] = status_counts.get(row.case_status, 0) + 1

            for _, conf_ev_id in open_issues_by_case.get(row.id, ()):
                if conf_ev_id is not None and not acl_map.get(conf_ev_id, (False, None))[0]:
                    continue
                open_issues += 1

            for res_state, ev_a, ev_b in conflicts_by_case.get(row.id, ()):
                if res_state != ConflictResolutionState.UNRESOLVED.value:
                    continue
                allow_a = acl_map.get(ev_a, (False, None))[0] if ev_a is not None else False
                allow_b = acl_map.get(ev_b, (False, None))[0] if ev_b is not None else False
                if allow_a or allow_b:
                    open_conflicts += 1

            pending_ctx += pending_ctx_by_case.get(row.id, 0)

        resp = VerificationSummaryResponse(
            project_id=project_id,
            total_cases=sum(status_counts.values()),
            candidate_count=status_counts.get(VerificationCaseStatus.CANDIDATE.value, 0),
            pending_review_count=status_counts.get(VerificationCaseStatus.PENDING_REVIEW.value, 0),
            conflicted_count=status_counts.get(VerificationCaseStatus.CONFLICTED.value, 0),
            unresolved_count=status_counts.get(VerificationCaseStatus.UNRESOLVED.value, 0),
            verified_count=status_counts.get(VerificationCaseStatus.VERIFIED.value, 0),
            rejected_count=status_counts.get(VerificationCaseStatus.REJECTED.value, 0),
            open_issues_count=open_issues,
            open_conflicts_count=open_conflicts,
            pending_context_requests_count=pending_ctx,
        )
        if use_cache:
            _VERIF_READ_CACHE.set(cache_key, resp.model_dump(mode="json"), ttl_seconds=300)
        return resp

    def list_queue(
        self,
        project_id: uuid.UUID,
        *,
        project_ctx: ProjectContext | None = None,
        status: str | None = None,
        domain: str | None = None,
        person: str | None = None,
        source: str | None = None,
        reviewer_id: uuid.UUID | None = None,
        category: str | None = None,
        search: str | None = None,
        sort_by: str = "updated_at",
        sort_dir: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> VerificationQueueResponse:
        if project_ctx is None:
            raise ForbiddenError("Project authorization context is required.", code="AUTH_REQUIRED")
        user_id, has_manage = self._verify_viewer_access(project_ctx)

        use_cache = not bool(os.getenv("PYTEST_CURRENT_TEST"))
        q_cache_key = (
            f"vq:{project_id}:{user_id}:{has_manage}:{status}:{domain}:{person}:{source}:"
            f"{reviewer_id}:{category}:{search}:{sort_by}:{sort_dir}:{limit}:{offset}"
        )
        if use_cache:
            cached_q = _VERIF_READ_CACHE.get(q_cache_key)
            if isinstance(cached_q, dict):
                return VerificationQueueResponse.model_validate(cached_q)

        search_q = search.strip().lower() if search and search.strip() else None
        person_q = person.strip().lower() if person and person.strip() else None

        # Fast SQL-paginated path when viewer has unrestricted access and no text/category filter
        if (
            not search_q
            and not category
            and not person_q
            and not domain
        ):
            policies = list(
                self.session.execute(
                    select(SourceAccessPolicy).where(SourceAccessPolicy.project_id == project_id)
                )
                .scalars()
                .all()
            )
            viewer_str = str(user_id)
            has_restrictions = any(
                p.sync_permission_status == SourcePermissionVerificationStatus.REVOKED.value
                or (not has_manage and viewer_str not in (p.allowed_user_ids or []))
                for p in policies
            )
            if not has_restrictions:
                from app.models.verification import VerificationCase
                from app.services.knowledge_domains import resolve_canonical_domain

                base_filter = [
                    VerificationCase.project_id == project_id,
                    VerificationCase.case_status != VerificationCaseStatus.ARCHIVED.value,
                ]
                if status:
                    base_filter.append(VerificationCase.case_status == status)
                if source:
                    base_filter.append(VerificationCase.source_provider == source)
                if reviewer_id:
                    base_filter.append(VerificationCase.assigned_reviewer_id == reviewer_id)

                total_fast = int(
                    self.session.execute(
                        select(func.count(VerificationCase.id)).where(*base_filter)
                    ).scalar()
                    or 0
                )
                if total_fast > 0:
                    sort_col = {
                        "updated_at": VerificationCase.updated_at,
                        "created_at": VerificationCase.created_at,
                        "priority": VerificationCase.priority,
                        "status": VerificationCase.case_status,
                        "domain": VerificationCase.domain,
                    }.get(sort_by, VerificationCase.updated_at)
                    order_expr = sort_col.asc() if sort_dir.lower() == "asc" else sort_col.desc()
                    page_ids = list(
                        self.session.execute(
                            select(VerificationCase.id)
                            .where(*base_filter)
                            .order_by(order_expr, VerificationCase.id.asc())
                            .limit(limit)
                            .offset(offset)
                        )
                        .scalars()
                        .all()
                    )
                    facet_rows = self.session.execute(
                        select(
                            VerificationCase.domain,
                            VerificationCase.source_provider,
                            VerificationCase.person_name,
                        )
                        .where(
                            VerificationCase.project_id == project_id,
                            VerificationCase.case_status != VerificationCaseStatus.ARCHIVED.value,
                        )
                        .distinct()
                    ).all()
                    f_domains: set[str] = set()
                    f_sources: set[str] = set()
                    f_people: set[str] = set()
                    for d_val, s_val, p_val in facet_rows:
                        if d_val:
                            try:
                                f_domains.add(resolve_canonical_domain(d_val).value)
                            except (ValueError, KeyError):
                                f_domains.add(d_val)
                        if s_val:
                            f_sources.add(s_val)
                        if p_val:
                            f_people.add(p_val)

                    page_cases = self.repo.list_project_cases_by_ids(project_id, page_ids)
                    acl_map, fallback_target_evs = self._batch_evaluate_cases_acl(
                        page_cases, project_id=project_id, user_id=user_id, has_manage=has_manage
                    )
                    fast_items: list[VerificationQueueItem] = []
                    for case in page_cases:
                        accessible_refs, restricted_cnt, _ = self._classify_case_access(
                            case, acl_map, fallback_target_evs
                        )
                        accessible_open_issues = [
                            i
                            for i in case.issues
                            if i.resolution_state == IssueResolutionState.OPEN.value
                        ]
                        fast_items.append(
                            self._to_queue_item(
                                case,
                                accessible_evidence_count=len(accessible_refs),
                                accessible_open_issues=accessible_open_issues,
                                sanitized_assessment=case.machine_assessment_json,
                                safe_title=case.title or case.current_claim[:80],
                                safe_current_claim=case.current_claim,
                                safe_original_ai_claim=case.original_ai_claim,
                                restricted_titles=set(),
                            )
                        )
                    fast_resp = VerificationQueueResponse(
                        items=fast_items,
                        total=total_fast,
                        limit=limit,
                        offset=offset,
                        available_domains=sorted(f_domains),
                        available_sources=sorted(f_sources),
                        available_people=sorted(f_people),
                    )
                    if use_cache:
                        _VERIF_READ_CACHE.set(q_cache_key, fast_resp.model_dump(mode="json"), ttl_seconds=300)
                    return fast_resp

        light_data = self.repo.list_project_cases_lightweight(
            project_id,
            sort_by=sort_by,
            sort_dir=sort_dir,
            include_claim_text=search_q is not None,
        )
        if not light_data["cases"]:
            from app.services.verification_engine import VerificationEngine

            engine = VerificationEngine(self.session)
            sync_res = engine.sync_project_findings(project_id)
            if sync_res.get("cases_created", 0) > 0:
                self.session.commit()
                light_data = self.repo.list_project_cases_lightweight(
                    project_id,
                    sort_by=sort_by,
                    sort_dir=sort_dir,
                    include_claim_text=search_q is not None,
                )

        acl_map, fallback_target_evs = self._batch_evaluate_lightweight_acl(
            light_data, project_id=project_id, user_id=user_id, has_manage=has_manage
        )
        restricted_titles = self.access_policy.list_restricted_titles_for_viewer(
            self.session,
            project_id=project_id,
            user_id=user_id,
            has_project_manage=has_manage,
        )

        refs_by_case = light_data["refs_by_case"]
        open_issues_by_case = light_data["open_issues_by_case"]

        facet_domains: set[str] = set()
        facet_sources: set[str] = set()
        facet_people: set[str] = set()
        person_q = person.strip().lower() if person and person.strip() else None

        allowed_doms: set[str] | None = None
        if domain:
            from app.services.knowledge_domains import (
                canonical_domain_to_legacy_category,
                resolve_canonical_domain,
            )

            dom_clean = domain.strip()
            allowed_doms = {dom_clean, dom_clean.lower(), dom_clean.upper()}
            try:
                c_dom = resolve_canonical_domain(dom_clean)
                allowed_doms.add(c_dom.value)
                allowed_doms.add(c_dom.value.lower())
                leg_cat = canonical_domain_to_legacy_category(c_dom)
                allowed_doms.add(leg_cat)
                allowed_doms.add(leg_cat.upper())
            except (ValueError, KeyError):
                pass

        from app.services.knowledge_domains import resolve_canonical_domain

        matching_case_ids: list[uuid.UUID] = []
        for row in light_data["cases"]:
            accessible_eids, restricted_cnt, fully_restricted = self._classify_lightweight_access(
                row, refs_by_case, acl_map, fallback_target_evs
            )
            if fully_restricted:
                continue

            if row.domain:
                try:
                    canon = resolve_canonical_domain(row.domain)
                    facet_domains.add(canon.value)
                except (ValueError, KeyError):
                    facet_domains.add(row.domain)
            if row.source_provider and restricted_cnt == 0:
                facet_sources.add(row.source_provider)
            elif accessible_eids:
                for eid in accessible_eids:
                    _, ev = acl_map.get(eid, (False, None))
                    if ev is not None and ev.source_type:
                        facet_sources.add(ev.source_type)
            if row.person_name and not self._text_mentions_restricted(
                row.person_name, restricted_titles
            ):
                facet_people.add(row.person_name)

            if status and row.case_status != status:
                continue
            if allowed_doms is not None:
                if row.domain not in allowed_doms and (row.domain or "").lower() not in allowed_doms:
                    continue
            if source and row.source_provider != source:
                continue
            if reviewer_id and row.assigned_reviewer_id != reviewer_id:
                continue
            if person_q and (not row.person_name or person_q not in row.person_name.lower()):
                continue

            if category:
                has_cat = any(
                    cat == category
                    and (conf_ev_id is None or acl_map.get(conf_ev_id, (False, None))[0])
                    for cat, conf_ev_id in open_issues_by_case.get(row.id, ())
                )
                if not has_cat:
                    continue

            if search_q is not None:
                s_title = (
                    self._scrub_derived_text(
                        row.title or (row.current_claim or "")[:80],
                        restricted_titles=restricted_titles,
                        replacement=_REDACTED_FINDING_TITLE,
                    )
                    or _REDACTED_FINDING_TITLE
                )
                s_curr = (
                    self._scrub_derived_text(
                        row.current_claim,
                        restricted_titles=restricted_titles,
                        replacement=_REDACTED_CLAIM_TEXT,
                    )
                    or ""
                )
                s_orig = (
                    self._scrub_derived_text(
                        row.original_ai_claim,
                        restricted_titles=restricted_titles,
                        replacement=_REDACTED_CLAIM_TEXT,
                    )
                    or ""
                )
                if not any(
                    search_q in field.lower()
                    for field in (s_title, s_curr, s_orig, row.domain or "")
                ):
                    continue

            matching_case_ids.append(row.id)

        total = len(matching_case_ids)
        page_ids = matching_case_ids[offset : offset + limit]
        page_cases = self.repo.list_project_cases_by_ids(project_id, page_ids)

        # Evaluate assessment-embedded evidence IDs only for the hydrated page (<= limit)
        extra_ev_ids: set[uuid.UUID] = set()
        for case in page_cases:
            for eid in self._extract_assessment_evidence_ids(case.machine_assessment_json):
                if eid not in acl_map:
                    extra_ev_ids.add(eid)
        if extra_ev_ids:
            acl_map.update(
                self.access_policy.evaluate_evidence_batch(
                    self.session,
                    extra_ev_ids,
                    project_id=project_id,
                    user_id=user_id,
                    has_project_manage=has_manage,
                )
            )

        page_items: list[VerificationQueueItem] = []
        for case in page_cases:
            accessible_refs, restricted_cnt, _ = self._classify_case_access(
                case, acl_map, fallback_target_evs
            )
            accessible_open_issues = [
                i
                for i in case.issues
                if i.resolution_state == IssueResolutionState.OPEN.value
                and (
                    i.conflicting_evidence_id is None
                    or acl_map.get(i.conflicting_evidence_id, (False, None))[0]
                )
            ]
            any_conf_restricted = any(
                not (
                    (
                        conf.claim_a_source_evidence_id is not None
                        and acl_map.get(conf.claim_a_source_evidence_id, (False, None))[0]
                    )
                    and (
                        conf.claim_b_source_evidence_id is not None
                        and acl_map.get(conf.claim_b_source_evidence_id, (False, None))[0]
                    )
                )
                for conf in case.conflicts
            )
            safe_assessment = self._sanitize_machine_assessment(
                case.machine_assessment_json,
                fully_restricted=False,
                restricted_ref_count=restricted_cnt,
                any_conflict_restricted=any_conf_restricted,
                acl_map=acl_map,
                restricted_titles=restricted_titles,
            )
            safe_title = (
                self._scrub_derived_text(
                    case.title or case.current_claim[:80],
                    restricted_titles=restricted_titles,
                    replacement=_REDACTED_FINDING_TITLE,
                )
                or _REDACTED_FINDING_TITLE
            )
            safe_current_claim = (
                self._scrub_derived_text(
                    case.current_claim,
                    restricted_titles=restricted_titles,
                    replacement=_REDACTED_CLAIM_TEXT,
                )
                or ""
            )
            safe_orig_claim = (
                self._scrub_derived_text(
                    case.original_ai_claim,
                    restricted_titles=restricted_titles,
                    replacement=_REDACTED_CLAIM_TEXT,
                )
                or ""
            )
            page_items.append(
                self._to_queue_item(
                    case,
                    accessible_evidence_count=len(accessible_refs),
                    accessible_open_issues=accessible_open_issues,
                    sanitized_assessment=safe_assessment,
                    safe_title=safe_title,
                    safe_current_claim=safe_current_claim,
                    safe_original_ai_claim=safe_orig_claim,
                    restricted_titles=restricted_titles,
                )
            )

        q_resp = VerificationQueueResponse(
            items=page_items,
            total=total,
            limit=limit,
            offset=offset,
            available_domains=sorted(facet_domains),
            available_sources=sorted(facet_sources),
            available_people=sorted(facet_people),
        )
        if use_cache:
            _VERIF_READ_CACHE.set(q_cache_key, q_resp.model_dump(mode="json"), ttl_seconds=300)
        return q_resp

    def get_case_detail(
        self,
        case_id: uuid.UUID,
        *,
        project_ctx: ProjectContext,
    ) -> VerificationCaseDetailResponse:
        user_id, has_manage = self._verify_viewer_access(project_ctx)

        case = self.repo.get_case(case_id, project_id=project_ctx.project.id, load_details=True)
        if case is None:
            raise NotFoundError(f"Verification case {case_id} not found in this project.")

        acl_map, fallback_target_evs = self._batch_evaluate_cases_acl(
            [case], project_id=project_ctx.project.id, user_id=user_id, has_manage=has_manage
        )
        restricted_titles = self.access_policy.list_restricted_titles_for_viewer(
            self.session,
            project_id=project_ctx.project.id,
            user_id=user_id,
            has_project_manage=has_manage,
        )

        accessible_ref_objs, restricted_count, fully_restricted = self._classify_case_access(
            case, acl_map, fallback_target_evs
        )

        accessible_refs: list[EvidenceReferenceDetail] = []
        for ref in accessible_ref_objs:
            _, ev = acl_map.get(ref.evidence_item_id, (False, None))
            if ev is None:
                continue
            accessible_refs.append(
                EvidenceReferenceDetail(
                    id=ref.id,
                    evidence_item_id=ev.id,
                    evidence_chunk_id=ref.evidence_chunk_id,
                    source_provider=ev.source_type,
                    source_name=ev.source_type.replace("_", " ").title(),
                    original_title=redact_secrets(ev.title),
                    author=ev.source_author_identity,
                    timestamp=ref.source_timestamp or ev.source_created_at,
                    original_source_url=ev.source_url,
                    excerpt=redact_secrets(ref.excerpt) if ref.excerpt is not None else None,
                    location_label=ref.location_label or ev.source_external_id,
                    relationship_to_finding=ref.relationship_to_finding,
                    acl_scope=ev.acl_scope,
                )
            )

        conflict_previews: list[VerificationConflictPreview] = []
        any_conflict_restricted = False
        for conf in case.conflicts:
            allow_a, ev_a = (
                acl_map.get(conf.claim_a_source_evidence_id, (False, None))
                if conf.claim_a_source_evidence_id is not None
                else (False, None)
            )
            allow_b, ev_b = (
                acl_map.get(conf.claim_b_source_evidence_id, (False, None))
                if conf.claim_b_source_evidence_id is not None
                else (False, None)
            )
            restricted_by_acl = not (allow_a and allow_b)
            if restricted_by_acl:
                any_conflict_restricted = True
            safe_conf_explanation = (
                _REDACTED_EXPLANATION
                if (
                    restricted_by_acl
                    or fully_restricted
                    or self._text_mentions_restricted(conf.explanation, restricted_titles)
                )
                else redact_secrets(conf.explanation)
            )
            conflict_previews.append(
                VerificationConflictPreview(
                    id=conf.id,
                    conflict_type=conf.conflict_type,
                    explanation=safe_conf_explanation,
                    temporal_comparison=conf.temporal_comparison,
                    resolution_state=conf.resolution_state,
                    side_a=(
                        ConflictClaimSide(
                            evidence_item_id=ev_a.id,
                            source_provider=ev_a.source_type,
                            original_title=redact_secrets(ev_a.title),
                            author=ev_a.source_author_identity,
                            timestamp=conf.claim_a_source_timestamp or ev_a.source_created_at,
                            original_source_url=ev_a.source_url,
                            claim_text=redact_secrets(conf.claim_a_text),
                        )
                        if (allow_a and ev_a is not None and not fully_restricted)
                        else None
                    ),
                    side_b=(
                        ConflictClaimSide(
                            evidence_item_id=ev_b.id,
                            source_provider=ev_b.source_type,
                            original_title=redact_secrets(ev_b.title),
                            author=ev_b.source_author_identity,
                            timestamp=conf.claim_b_source_timestamp or ev_b.source_created_at,
                            original_source_url=ev_b.source_url,
                            claim_text=redact_secrets(conf.claim_b_text),
                        )
                        if (allow_b and ev_b is not None and not fully_restricted)
                        else None
                    ),
                    restricted_by_acl=restricted_by_acl or fully_restricted,
                    created_at=conf.created_at,
                )
            )

        user_ids: set[uuid.UUID] = set()
        if case.assigned_reviewer_id:
            user_ids.add(case.assigned_reviewer_id)
        for rev in case.revisions:
            if rev.edited_by_user_id:
                user_ids.add(rev.edited_by_user_id)
        for evt in case.review_events:
            user_ids.add(evt.reviewer_user_id)
        for req in case.context_requests:
            user_ids.add(req.requested_by_user_id)
            user_ids.add(req.requested_from_user_id)

        user_names = self._load_user_names(user_ids)

        if fully_restricted or restricted_count > 0:
            eligible = False
            eligibility_reason = (
                "Blocked: supporting source evidence is restricted for the current viewer."
            )
        else:
            eligible, eligibility_reason = self._compute_handover_eligibility(case)

        assessment = self._sanitize_machine_assessment(
            case.machine_assessment_json,
            fully_restricted=fully_restricted,
            restricted_ref_count=restricted_count,
            any_conflict_restricted=any_conflict_restricted,
            acl_map=acl_map,
            restricted_titles=restricted_titles,
        )

        sanitized_issues: list[VerificationIssueDetail] = []
        for iss in case.issues:
            iss_ev_restricted = (
                iss.conflicting_evidence_id is not None
                and not acl_map.get(iss.conflicting_evidence_id, (False, None))[0]
            )
            iss_restricted = (
                fully_restricted
                or iss_ev_restricted
                or (iss.verification_category == "conflicting_evidence" and any_conflict_restricted)
                or self._text_mentions_restricted(iss.description, restricted_titles)
            )
            sanitized_issues.append(
                VerificationIssueDetail(
                    id=iss.id,
                    verification_category=iss.verification_category,
                    issue_type=iss.issue_type,
                    severity=iss.severity,
                    description=(
                        _REDACTED_ISSUE_DESC if iss_restricted else redact_secrets(iss.description)
                    ),
                    detection_method=iss.detection_method,
                    resolution_state=iss.resolution_state,
                    details={} if iss_restricted else (iss.details_json or {}),
                    conflicting_evidence_id=(
                        None if iss_restricted else iss.conflicting_evidence_id
                    ),
                    created_at=iss.created_at,
                    resolved_at=iss.resolved_at,
                )
            )

        redact_revisions = fully_restricted or restricted_count > 0
        sanitized_revisions: list[VerificationRevisionDetail] = []
        for rev in case.revisions:
            rev_restricted = redact_revisions or self._text_mentions_restricted(
                rev.claim_text, restricted_titles
            )
            sanitized_revisions.append(
                VerificationRevisionDetail(
                    id=rev.id,
                    revision_number=rev.revision_number,
                    claim_text=(
                        _REDACTED_CLAIM_TEXT
                        if rev_restricted
                        else redact_secrets(rev.claim_text)
                    ),
                    domain=rev.domain,
                    is_ai_original=rev.is_ai_original,
                    edited_by_user_id=rev.edited_by_user_id,
                    edited_by_name=(
                        user_names.get(rev.edited_by_user_id) if rev.edited_by_user_id else None
                    ),
                    edit_reason=(
                        None
                        if rev_restricted
                        else self._scrub_derived_text(
                            rev.edit_reason, restricted_titles=restricted_titles
                        )
                    ),
                    created_at=rev.created_at,
                )
            )

        sanitized_events = [
            VerificationReviewEventDetail(
                id=evt.id,
                reviewer_user_id=evt.reviewer_user_id,
                reviewer_name=user_names.get(evt.reviewer_user_id),
                action=evt.action,
                previous_status=evt.previous_status,
                new_status=evt.new_status,
                case_version=evt.case_version,
                decision_reason=(
                    None
                    if fully_restricted
                    else self._scrub_derived_text(
                        evt.decision_reason, restricted_titles=restricted_titles
                    )
                ),
                review_notes=(
                    None
                    if fully_restricted
                    else self._scrub_derived_text(
                        evt.review_notes, restricted_titles=restricted_titles
                    )
                ),
                created_at=evt.created_at,
            )
            for evt in case.review_events
        ]

        sanitized_ctx_reqs = [
            VerificationContextRequestDetail(
                id=q.id,
                case_id=q.case_id,
                requested_by_user_id=q.requested_by_user_id,
                requested_by_name=user_names.get(q.requested_by_user_id),
                requested_from_user_id=q.requested_from_user_id,
                requested_from_name=user_names.get(q.requested_from_user_id),
                question=(
                    _REDACTED_CLAIM_TEXT
                    if fully_restricted
                    else (
                        self._scrub_derived_text(q.question, restricted_titles=restricted_titles)
                        or _REDACTED_CLAIM_TEXT
                    )
                ),
                requested_information_type=q.requested_information_type,
                status=q.status,
                response_text=(
                    None
                    if fully_restricted
                    else self._scrub_derived_text(
                        q.response_text, restricted_titles=restricted_titles
                    )
                ),
                response_evidence_id=None if fully_restricted else q.response_evidence_id,
                responded_at=q.responded_at,
                created_at=q.created_at,
            )
            for q in case.context_requests
        ]

        safe_title = (
            _REDACTED_FINDING_TITLE
            if fully_restricted
            else (
                self._scrub_derived_text(
                    case.title,
                    restricted_titles=restricted_titles,
                    replacement=_REDACTED_FINDING_TITLE,
                )
                or _REDACTED_FINDING_TITLE
            )
        )
        safe_orig_claim = (
            _REDACTED_CLAIM_TEXT
            if fully_restricted
            else (
                self._scrub_derived_text(
                    case.original_ai_claim,
                    restricted_titles=restricted_titles,
                    replacement=_REDACTED_CLAIM_TEXT,
                )
                or ""
            )
        )
        safe_curr_claim = (
            _REDACTED_CLAIM_TEXT
            if fully_restricted
            else (
                self._scrub_derived_text(
                    case.current_claim,
                    restricted_titles=restricted_titles,
                    replacement=_REDACTED_CLAIM_TEXT,
                )
                or ""
            )
        )

        return VerificationCaseDetailResponse(
            id=case.id,
            project_id=case.project_id,
            target_type=case.target_type,
            target_id=case.target_id,
            title=safe_title,
            domain=case.domain,
            original_ai_claim=safe_orig_claim,
            current_claim=safe_curr_claim,
            case_status=case.case_status,
            priority=case.priority,
            person_name=None if fully_restricted else case.person_name,
            source_provider="restricted" if fully_restricted else case.source_provider,
            assigned_reviewer_id=case.assigned_reviewer_id,
            assigned_reviewer_name=(
                user_names.get(case.assigned_reviewer_id) if case.assigned_reviewer_id else None
            ),
            model_confidence=None if fully_restricted else case.model_confidence,
            uncertainty_note=(
                None
                if fully_restricted
                else self._scrub_derived_text(
                    case.uncertainty_note, restricted_titles=restricted_titles
                )
            ),
            evidence_completeness="restricted" if fully_restricted else case.evidence_completeness,
            version=case.version,
            handover_eligible=eligible,
            handover_eligibility_reason=eligibility_reason,
            restricted_evidence_count=restricted_count,
            evidence_references=accessible_refs,
            issues=sanitized_issues,
            conflicts=conflict_previews,
            revisions=sanitized_revisions,
            review_events=sanitized_events,
            context_requests=sanitized_ctx_reqs,
            machine_assessment=assessment,
            priority_reason=assessment.get("priority_reason"),
            recommendation=assessment.get("recommendation"),
            completeness_assessment=assessment.get("completeness_assessment"),
            reliability_assessment=assessment.get("reliability_assessment"),
            freshness_assessment=assessment.get("freshness_assessment"),
            corroboration_assessment=assessment.get("corroboration_assessment"),
            contradiction_analysis=assessment.get("contradiction_analysis"),
            monitoring_status=assessment.get("monitoring_status"),
            last_assessed_at=case.last_assessed_at,
            last_reviewed_at=case.last_reviewed_at,
            resolved_at=case.resolved_at,
            created_at=case.created_at,
            updated_at=case.updated_at,
        )

    def list_context_requests(
        self,
        project_id: uuid.UUID,
        *,
        project_ctx: ProjectContext | None = None,
        case_id: uuid.UUID | None = None,
        status: str | None = None,
    ) -> list[VerificationContextRequestDetail]:
        if project_ctx is None:
            raise ForbiddenError("Project authorization context is required.", code="AUTH_REQUIRED")
        user_id, has_manage = self._verify_viewer_access(project_ctx)

        reqs = self.repo.list_context_requests(project_id, case_id=case_id, status=status)
        if not reqs:
            return []

        req_case_ids = {q.case_id for q in reqs}
        cases = [
            c
            for c in self.repo.list_project_cases_for_acl(project_id)
            if c.id in req_case_ids
        ]
        acl_map, fallback_target_evs = self._batch_evaluate_cases_acl(
            cases, project_id=project_id, user_id=user_id, has_manage=has_manage
        )
        allowed_case_ids: set[uuid.UUID] = set()
        for c in cases:
            _, _, fully_restricted = self._classify_case_access(c, acl_map, fallback_target_evs)
            if not fully_restricted:
                allowed_case_ids.add(c.id)

        visible_reqs = [q for q in reqs if q.case_id in allowed_case_ids]
        user_ids: set[uuid.UUID] = set()
        for q in visible_reqs:
            user_ids.add(q.requested_by_user_id)
            user_ids.add(q.requested_from_user_id)
        names = self._load_user_names(user_ids)
        return [
            VerificationContextRequestDetail(
                id=q.id,
                case_id=q.case_id,
                requested_by_user_id=q.requested_by_user_id,
                requested_by_name=names.get(q.requested_by_user_id),
                requested_from_user_id=q.requested_from_user_id,
                requested_from_name=names.get(q.requested_from_user_id),
                question=redact_secrets(q.question),
                requested_information_type=q.requested_information_type,
                status=q.status,
                response_text=(
                    redact_secrets(q.response_text) if q.response_text is not None else None
                ),
                response_evidence_id=q.response_evidence_id,
                responded_at=q.responded_at,
                created_at=q.created_at,
            )
            for q in visible_reqs
        ]

    # -----------------------------------------------------------------------
    # Five Reviewer Actions + Context Response + Assignment
    # -----------------------------------------------------------------------

    def approve_case(
        self,
        case_id: uuid.UUID,
        *,
        project_ctx: ProjectContext,
        payload: ApproveFindingRequest,
    ) -> VerificationCaseDetailResponse:
        case = self._require_case(case_id, project_ctx.project.id)
        self._assert_transition(case.case_status, VerificationCaseStatus.VERIFIED.value)

        if case.case_status == VerificationCaseStatus.CONFLICTED.value:
            note = (payload.reviewer_note or payload.decision_reason or "").strip()
            if not note:
                raise UnprocessableEntityError(
                    "A reviewer note or decision reason is required when approving a conflicted finding."
                )

        now = datetime.now(UTC)
        prev_status = case.case_status
        case.case_status = VerificationCaseStatus.VERIFIED.value
        case.resolved_at = now
        case.last_reviewed_at = now

        self._sync_target_review_state(
            case,
            epistemic_status=EpistemicStatus.HUMAN_VERIFIED.value,
            review_status=KnowledgeReviewStatus.APPROVED.value,
            rel_status=RelationshipVerificationStatus.VERIFIED.value,
        )
        self._record_review_event(
            case=case,
            reviewer_id=project_ctx.principal.user.id,
            action=ReviewActionType.APPROVE.value,
            previous_status=prev_status,
            new_status=case.case_status,
            decision_reason=payload.decision_reason,
            review_notes=payload.reviewer_note,
        )
        self.audit.record_event(
            event_type="verification.case.approved",
            resource_type="verification_case",
            actor_user_id=project_ctx.principal.user.id,
            organisation_id=case.organisation_id,
            project_id=case.project_id,
            resource_id=str(case.id),
            outcome=AuditOutcome.SUCCESS.value,
            metadata={"previous_status": prev_status, "version": case.version},
        )
        self.session.commit()
        self.session.expire_all()
        return self.get_case_detail(case.id, project_ctx=project_ctx)

    def reject_case(
        self,
        case_id: uuid.UUID,
        *,
        project_ctx: ProjectContext,
        payload: RejectFindingRequest,
    ) -> VerificationCaseDetailResponse:
        case = self._require_case(case_id, project_ctx.project.id)
        self._assert_transition(case.case_status, VerificationCaseStatus.REJECTED.value)

        now = datetime.now(UTC)
        prev_status = case.case_status
        case.case_status = VerificationCaseStatus.REJECTED.value
        case.resolved_at = now
        case.last_reviewed_at = now

        self._sync_target_review_state(
            case,
            epistemic_status=None,
            review_status=KnowledgeReviewStatus.REJECTED.value,
            rel_status=RelationshipVerificationStatus.REJECTED.value,
        )
        self._record_review_event(
            case=case,
            reviewer_id=project_ctx.principal.user.id,
            action=ReviewActionType.REJECT.value,
            previous_status=prev_status,
            new_status=case.case_status,
            decision_reason=payload.decision_reason,
            review_notes=payload.reviewer_note,
        )
        self.audit.record_event(
            event_type="verification.case.rejected",
            resource_type="verification_case",
            actor_user_id=project_ctx.principal.user.id,
            organisation_id=case.organisation_id,
            project_id=case.project_id,
            resource_id=str(case.id),
            outcome=AuditOutcome.SUCCESS.value,
            metadata={"previous_status": prev_status, "reason": payload.decision_reason},
        )
        self.session.commit()
        self.session.expire_all()
        return self.get_case_detail(case.id, project_ctx=project_ctx)

    def edit_finding(
        self,
        case_id: uuid.UUID,
        *,
        project_ctx: ProjectContext,
        payload: EditFindingRequest,
    ) -> VerificationCaseDetailResponse:
        case = self._require_case(case_id, project_ctx.project.id)
        if not case.evidence_refs:
            raise UnprocessableEntityError(
                "Factual claims must be supported by at least one evidence reference before editing. "
                "Request additional context or attach evidence first."
            )

        now = datetime.now(UTC)
        prev_status = case.case_status
        prev_claim = case.current_claim
        new_domain = payload.domain.strip() if payload.domain else case.domain

        case.version += 1
        case.current_claim = payload.current_claim
        case.domain = new_domain
        case.last_reviewed_at = now
        # Editing returns a finding to PENDING_REVIEW so the updated claim is explicitly confirmed
        if case.case_status != VerificationCaseStatus.CONFLICTED.value:
            case.case_status = VerificationCaseStatus.PENDING_REVIEW.value

        self.session.add(
            VerificationFindingRevision(
                organisation_id=case.organisation_id,
                project_id=case.project.id,
                case_id=case.id,
                revision_number=case.version,
                claim_text=payload.current_claim,
                domain=new_domain,
                is_ai_original=False,
                edited_by_user_id=project_ctx.principal.user.id,
                edit_reason=payload.edit_reason,
                evidence_snapshot_json={
                    "evidence_item_ids": [str(r.evidence_item_id) for r in case.evidence_refs]
                },
            )
        )

        # Sync edited statement back to KnowledgeItem without overwriting AI original on case
        if case.target_type == VerificationTargetType.KNOWLEDGE_ITEM.value:
            ki = self.session.get(KnowledgeItem, case.target_id)
            if ki is not None and ki.project_id == case.project_id:
                ki.structured_summary = payload.current_claim
                ki.category = new_domain
                ki.review_status = KnowledgeReviewStatus.PENDING_REVIEW.value

        self._record_review_event(
            case=case,
            reviewer_id=project_ctx.principal.user.id,
            action=ReviewActionType.EDIT.value,
            previous_status=prev_status,
            new_status=case.case_status,
            decision_reason=payload.edit_reason,
            review_notes=payload.reviewer_note,
            previous_snapshot={"claim": prev_claim},
            new_snapshot={"claim": payload.current_claim, "domain": new_domain},
        )
        self.audit.record_event(
            event_type="verification.case.edited",
            resource_type="verification_case",
            actor_user_id=project_ctx.principal.user.id,
            organisation_id=case.organisation_id,
            project_id=case.project_id,
            resource_id=str(case.id),
            outcome=AuditOutcome.SUCCESS.value,
            metadata={"version": case.version, "edit_reason": payload.edit_reason},
        )
        self.session.commit()
        self.session.expire_all()
        return self.get_case_detail(case.id, project_ctx=project_ctx)

    def request_context(
        self,
        case_id: uuid.UUID,
        *,
        project_ctx: ProjectContext,
        payload: RequestContextRequest,
    ) -> VerificationCaseDetailResponse:
        case = self._require_case(case_id, project_ctx.project.id)
        now = datetime.now(UTC)
        prev_status = case.case_status

        req = VerificationContextRequest(
            organisation_id=case.organisation_id,
            project_id=case.project_id,
            case_id=case.id,
            requested_by_user_id=project_ctx.principal.user.id,
            requested_from_user_id=payload.requested_from_user_id,
            question=payload.question,
            requested_information_type=payload.requested_information_type,
            status=ContextRequestStatus.PENDING.value,
        )
        self.session.add(req)

        if case.case_status == VerificationCaseStatus.CANDIDATE.value:
            case.case_status = VerificationCaseStatus.PENDING_REVIEW.value
        case.last_reviewed_at = now

        self._record_review_event(
            case=case,
            reviewer_id=project_ctx.principal.user.id,
            action=ReviewActionType.REQUEST_CONTEXT.value,
            previous_status=prev_status,
            new_status=case.case_status,
            decision_reason=payload.question,
            review_notes=payload.reviewer_note,
        )
        self.audit.record_event(
            event_type="verification.context_request.created",
            resource_type="verification_case",
            actor_user_id=project_ctx.principal.user.id,
            organisation_id=case.organisation_id,
            project_id=case.project_id,
            resource_id=str(case.id),
            outcome=AuditOutcome.SUCCESS.value,
            metadata={"requested_from_user_id": str(payload.requested_from_user_id)},
        )
        self.session.commit()
        self.session.expire_all()
        return self.get_case_detail(case.id, project_ctx=project_ctx)

    def respond_context_request(
        self,
        request_id: uuid.UUID,
        *,
        project_ctx: ProjectContext,
        payload: RespondContextRequest,
    ) -> VerificationContextRequestDetail:
        req = self.repo.get_context_request(request_id, project_id=project_ctx.project.id)
        if req is None:
            raise NotFoundError(f"Context request {request_id} not found in this project.")
        actor_id = project_ctx.principal.user.id
        if (
            actor_id != req.requested_from_user_id
            and not project_ctx.has_permission("project.knowledge.review")
            and not project_ctx.has_permission("project.manage")
        ):
            raise ForbiddenError(
                "Only the requested team member or an authorised reviewer may respond to this context request."
            )
        if req.status != ContextRequestStatus.PENDING.value:
            raise ConflictError("This context request has already been answered or closed.")

        case = self._require_case(req.case_id, project_ctx.project.id)
        now = datetime.now(UTC)

        if payload.response_evidence_id is not None:
            ev = self.session.get(EvidenceItem, payload.response_evidence_id)
            if ev is None or ev.project_id != project_ctx.project.id:
                raise NotFoundError("Attached response evidence item not found in this project.")
            self.session.add(
                VerificationEvidenceRef(
                    organisation_id=case.organisation_id,
                    project_id=case.project_id,
                    case_id=case.id,
                    evidence_item_id=ev.id,
                    relationship_to_finding="additional_context",
                    excerpt=payload.excerpt or payload.response_text[:500],
                    location_label="Context response attachment",
                    source_timestamp=ev.source_created_at or now,
                )
            )

        req.status = ContextRequestStatus.RESPONDED.value
        req.response_text = payload.response_text
        req.response_evidence_id = payload.response_evidence_id
        req.responded_at = now

        prev_status = case.case_status
        if case.case_status not in {
            VerificationCaseStatus.VERIFIED.value,
            VerificationCaseStatus.REJECTED.value,
        }:
            case.case_status = VerificationCaseStatus.PENDING_REVIEW.value

        self._record_review_event(
            case=case,
            reviewer_id=project_ctx.principal.user.id,
            action=ReviewActionType.RETURN_FOR_CORRECTION.value,
            previous_status=prev_status,
            new_status=case.case_status,
            decision_reason="Additional context received",
            review_notes=payload.response_text,
        )
        self.audit.record_event(
            event_type="verification.context_request.responded",
            resource_type="verification_context_request",
            actor_user_id=project_ctx.principal.user.id,
            organisation_id=case.organisation_id,
            project_id=case.project_id,
            resource_id=str(req.id),
            outcome=AuditOutcome.SUCCESS.value,
        )
        self.session.commit()
        names = self._load_user_names({req.requested_by_user_id, req.requested_from_user_id})
        return VerificationContextRequestDetail(
            id=req.id,
            case_id=req.case_id,
            requested_by_user_id=req.requested_by_user_id,
            requested_by_name=names.get(req.requested_by_user_id),
            requested_from_user_id=req.requested_from_user_id,
            requested_from_name=names.get(req.requested_from_user_id),
            question=req.question,
            requested_information_type=req.requested_information_type,
            status=req.status,
            response_text=req.response_text,
            response_evidence_id=req.response_evidence_id,
            responded_at=req.responded_at,
            created_at=req.created_at,
        )

    def mark_unresolved(
        self,
        case_id: uuid.UUID,
        *,
        project_ctx: ProjectContext,
        payload: MarkUnresolvedRequest,
    ) -> VerificationCaseDetailResponse:
        case = self._require_case(case_id, project_ctx.project.id)
        self._assert_transition(case.case_status, VerificationCaseStatus.UNRESOLVED.value)

        now = datetime.now(UTC)
        prev_status = case.case_status
        case.case_status = VerificationCaseStatus.UNRESOLVED.value
        case.last_reviewed_at = now
        case.resolved_at = None

        self._sync_target_review_state(
            case,
            epistemic_status=None,
            review_status=KnowledgeReviewStatus.NEEDS_CLARIFICATION.value,
            rel_status=RelationshipVerificationStatus.UNRESOLVED.value,
        )
        self._record_review_event(
            case=case,
            reviewer_id=project_ctx.principal.user.id,
            action=ReviewActionType.MARK_UNRESOLVED.value,
            previous_status=prev_status,
            new_status=case.case_status,
            decision_reason=payload.decision_reason,
            review_notes=payload.reviewer_note,
        )
        self.audit.record_event(
            event_type="verification.case.marked_unresolved",
            resource_type="verification_case",
            actor_user_id=project_ctx.principal.user.id,
            organisation_id=case.organisation_id,
            project_id=case.project_id,
            resource_id=str(case.id),
            outcome=AuditOutcome.SUCCESS.value,
            metadata={"previous_status": prev_status, "reason": payload.decision_reason},
        )
        self.session.commit()
        self.session.expire_all()
        return self.get_case_detail(case.id, project_ctx=project_ctx)

    def assign_reviewer(
        self,
        case_id: uuid.UUID,
        *,
        project_ctx: ProjectContext,
        assigned_reviewer_id: uuid.UUID | None,
    ) -> VerificationCaseDetailResponse:
        case = self._require_case(case_id, project_ctx.project.id)
        prev_status = case.case_status
        case.assigned_reviewer_id = assigned_reviewer_id
        if assigned_reviewer_id is not None and case.case_status == VerificationCaseStatus.CANDIDATE.value:
            case.case_status = VerificationCaseStatus.PENDING_REVIEW.value

        self._record_review_event(
            case=case,
            reviewer_id=project_ctx.principal.user.id,
            action=ReviewActionType.ASSIGN.value,
            previous_status=prev_status,
            new_status=case.case_status,
            decision_reason="Assigned reviewer" if assigned_reviewer_id else "Unassigned reviewer",
        )
        self.session.commit()
        self.session.expire_all()
        return self.get_case_detail(case.id, project_ctx=project_ctx)

    # -----------------------------------------------------------------------
    # Internal Helpers
    # -----------------------------------------------------------------------

    def _require_case(self, case_id: uuid.UUID, project_id: uuid.UUID) -> VerificationCase:
        case = self.repo.get_case(case_id, project_id=project_id, load_details=True)
        if case is None:
            raise NotFoundError(f"Verification case {case_id} not found in this project.")
        return case

    def _assert_transition(self, current_status: str, target_status: str) -> None:
        allowed = _ALLOWED_TRANSITIONS.get(current_status, set())
        if target_status not in allowed:
            raise ConflictError(
                f"Invalid status transition from '{current_status}' to '{target_status}'."
            )

    def _sync_target_review_state(
        self,
        case: VerificationCase,
        *,
        epistemic_status: str | None,
        review_status: str,
        rel_status: str,
    ) -> None:
        if case.target_type == VerificationTargetType.KNOWLEDGE_ITEM.value:
            ki = self.session.get(KnowledgeItem, case.target_id)
            if ki is not None and ki.project_id == case.project_id:
                if epistemic_status is not None:
                    ki.epistemic_status = epistemic_status
                ki.review_status = review_status
        elif case.target_type == VerificationTargetType.RELATIONSHIP.value:
            rel = self.session.get(KnowledgeRelationship, case.target_id)
            if rel is not None and rel.project_id == case.project_id:
                rel.verification_status = rel_status

    def _record_review_event(
        self,
        *,
        case: VerificationCase,
        reviewer_id: uuid.UUID,
        action: str,
        previous_status: str,
        new_status: str,
        decision_reason: str | None = None,
        review_notes: str | None = None,
        previous_snapshot: dict[str, Any] | None = None,
        new_snapshot: dict[str, Any] | None = None,
    ) -> None:
        corr_id = get_correlation_id() or "-"
        self.session.add(
            VerificationReviewEvent(
                organisation_id=case.organisation_id,
                project_id=case.project_id,
                case_id=case.id,
                reviewer_user_id=reviewer_id,
                action=action,
                previous_status=previous_status,
                new_status=new_status,
                case_version=case.version,
                decision_reason=decision_reason,
                review_notes=review_notes,
                previous_snapshot_json=previous_snapshot,
                new_snapshot_json=new_snapshot,
                correlation_id=corr_id[:64],
            )
        )
        invalidate_verification_read_cache(case.project_id)

    def _load_user_names(self, user_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
        if not user_ids:
            return {}
        rows = self.session.execute(
            select(User.id, User.full_name, User.email).where(User.id.in_(user_ids))
        ).all()
        return {uid: (full_name or email) for uid, full_name, email in rows}

    def _compute_handover_eligibility(self, case: VerificationCase) -> tuple[bool, str]:
        if case.case_status == VerificationCaseStatus.VERIFIED.value:
            return True, "Human-verified and eligible for Handover Workspace."
        if case.case_status == VerificationCaseStatus.REJECTED.value:
            return False, "Rejected by human reviewer; excluded from handover."
        if case.case_status == VerificationCaseStatus.CONFLICTED.value:
            return False, "Blocked: contradictory source evidence requires human resolution."
        if case.case_status == VerificationCaseStatus.UNRESOLVED.value:
            return False, "Blocked: insufficient evidence; cannot enter approved handover."
        return False, "Awaiting human verification before handover eligibility."

    def _to_queue_item(
        self,
        case: VerificationCase,
        *,
        accessible_evidence_count: int | None = None,
        accessible_open_issues: list[Any] | None = None,
        sanitized_assessment: dict[str, Any] | None = None,
        safe_title: str | None = None,
        safe_current_claim: str | None = None,
        safe_original_ai_claim: str | None = None,
        restricted_titles: set[str] | None = None,
    ) -> VerificationQueueItem:
        open_issues = (
            accessible_open_issues
            if accessible_open_issues is not None
            else [i for i in case.issues if i.resolution_state == "open"]
        )
        categories = sorted({i.verification_category for i in open_issues})
        reviewer_name = None
        if case.assigned_reviewer is not None:
            reviewer_name = case.assigned_reviewer.full_name or case.assigned_reviewer.email

        assessment = (
            sanitized_assessment
            if sanitized_assessment is not None
            else dict(case.machine_assessment_json or {})
        )
        rec = dict(assessment.get("recommendation") or {})
        corrob = dict(assessment.get("corroboration_assessment") or {})
        freshness = dict(assessment.get("freshness_assessment") or {})

        return VerificationQueueItem(
            id=case.id,
            project_id=case.project_id,
            target_type=case.target_type,
            target_id=case.target_id,
            title=safe_title if safe_title is not None else (case.title or case.current_claim[:80]),
            domain=case.domain,
            current_claim=safe_current_claim if safe_current_claim is not None else case.current_claim,
            original_ai_claim=(
                safe_original_ai_claim if safe_original_ai_claim is not None else case.original_ai_claim
            ),
            case_status=case.case_status,
            priority=case.priority,
            person_name=case.person_name,
            source_provider=case.source_provider,
            assigned_reviewer_id=case.assigned_reviewer_id,
            assigned_reviewer_name=reviewer_name,
            evidence_count=(
                accessible_evidence_count
                if accessible_evidence_count is not None
                else len(case.evidence_refs)
            ),
            open_issues_count=len(open_issues),
            verification_categories=categories,
            model_confidence=case.model_confidence,
            uncertainty_note=(
                self._scrub_derived_text(
                    case.uncertainty_note, restricted_titles=restricted_titles or set()
                )
                if restricted_titles is not None
                else case.uncertainty_note
            ),
            evidence_completeness=case.evidence_completeness,
            priority_reason=assessment.get("priority_reason"),
            recommendation_action=rec.get("action"),
            corroboration_level=corrob.get("level"),
            freshness_status=freshness.get("status"),
            version=case.version,
            last_reviewed_at=case.last_reviewed_at,
            updated_at=case.updated_at,
            created_at=case.created_at,
        )
