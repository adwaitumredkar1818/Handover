"""Human review workflow, state machine, and ACL-enforced detail builder."""

from __future__ import annotations

import copy
import json
import os
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, insert, or_, select, update
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
    VerificationIssue,
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
    VerifyAllFindingsRequest,
    VerifyAllFindingsResponse,
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


_VERIF_READ_CACHE = LocalTTLCache(max_items=2048)

_STATUS_TO_SUMMARY_FIELD: dict[str, str] = {
    VerificationCaseStatus.CANDIDATE.value: "candidate_count",
    VerificationCaseStatus.PENDING_REVIEW.value: "pending_review_count",
    VerificationCaseStatus.CONFLICTED.value: "conflicted_count",
    VerificationCaseStatus.UNRESOLVED.value: "unresolved_count",
    VerificationCaseStatus.VERIFIED.value: "verified_count",
    VerificationCaseStatus.REJECTED.value: "rejected_count",
}


def invalidate_verification_read_cache(project_id: uuid.UUID) -> None:
    _VERIF_READ_CACHE.invalidate_prefix(f"vsum:{project_id}:")
    _VERIF_READ_CACHE.invalidate_prefix(f"vq:{project_id}:")
    _VERIF_READ_CACHE.invalidate_prefix(f"vcase:{project_id}:")
    _VERIF_READ_CACHE.invalidate_prefix(f"vrest:{project_id}:")
    _VERIF_READ_CACHE.invalidate_prefix(f"vunrest:{project_id}:")
    _VERIF_READ_CACHE.delete(f"vfacets:{project_id}")
    _VERIF_READ_CACHE.invalidate_prefix(f"vci:{project_id}:")
    from app.core.cache.local_cache import local_response_cache
    from app.services.handover_sections import invalidate_handover_sections_cache

    local_response_cache.invalidate_prefix(f"handover_ws:{project_id}:")
    invalidate_handover_sections_cache(project_id)


def patch_verification_read_cache_for_case(
    *,
    project_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    case_id: uuid.UUID,
    previous_status: str,
    new_status: str,
    version: int,
    updated_at: datetime,
    last_reviewed_at: datetime | None,
    current_claim: str | None = None,
    domain: str | None = None,
    claim_changed: bool = False,
    domain_changed: bool = False,
    assigned_reviewer_id: uuid.UUID | None = None,
    assigned_reviewer_name: str | None = None,
    assigned_reviewer_changed: bool = False,
    pending_context_delta: int = 0,
    patched_case_detail: dict[str, Any] | None = None,
) -> None:
    """Update cached summary and queue entries in-place when a single case changes."""
    status_changed = previous_status != new_status
    if status_changed or pending_context_delta:
        prev_field = _STATUS_TO_SUMMARY_FIELD.get(previous_status)
        new_field = _STATUS_TO_SUMMARY_FIELD.get(new_status)
        for skey in _VERIF_READ_CACHE.keys_with_prefix(f"vsum:{project_id}:"):
            sdata = _VERIF_READ_CACHE.get(skey)
            if not isinstance(sdata, dict):
                continue
            if status_changed:
                if prev_field and prev_field in sdata:
                    sdata[prev_field] = max(0, int(sdata[prev_field]) - 1)
                if new_field and new_field in sdata:
                    sdata[new_field] = int(sdata[new_field]) + 1
            if pending_context_delta:
                sdata["pending_context_requests_count"] = max(
                    0,
                    int(sdata.get("pending_context_requests_count", 0)) + pending_context_delta,
                )
            _VERIF_READ_CACHE.set(skey, sdata, ttl_seconds=300)

    q_prefix = f"vq:{project_id}:"
    case_id_str = str(case_id)
    updated_iso = updated_at.isoformat()
    reviewed_iso = last_reviewed_at.isoformat() if last_reviewed_at else None

    for qkey in _VERIF_READ_CACHE.keys_with_prefix(q_prefix):
        rest = qkey[len(q_prefix) :]
        parts = rest.split(":", 2)
        if len(parts) != 3:
            _VERIF_READ_CACHE.delete(qkey)
            continue
        key_user_id, _key_has_manage, filter_json = parts
        try:
            (
                f_status,
                f_domain,
                _f_person,
                _f_source,
                f_reviewer_id,
                _f_category,
                f_search,
                f_sort_by,
                f_sort_dir,
                _f_limit,
                f_offset,
            ) = json.loads(filter_json)
        except Exception:
            _VERIF_READ_CACHE.delete(qkey)
            continue

        # Never propagate unredacted text edits across different viewers
        if (claim_changed or domain_changed) and key_user_id != str(actor_user_id):
            _VERIF_READ_CACHE.delete(qkey)
            continue

        if status_changed and f_status is not None:
            _VERIF_READ_CACHE.delete(qkey)
            continue
        if domain_changed and f_domain is not None:
            _VERIF_READ_CACHE.delete(qkey)
            continue
        if assigned_reviewer_changed and f_reviewer_id is not None:
            _VERIF_READ_CACHE.delete(qkey)
            continue
        if (claim_changed or domain_changed) and f_search is not None:
            _VERIF_READ_CACHE.delete(qkey)
            continue
        if status_changed and f_sort_by == "status":
            _VERIF_READ_CACHE.delete(qkey)
            continue
        if domain_changed and f_sort_by == "domain":
            _VERIF_READ_CACHE.delete(qkey)
            continue

        qdata = _VERIF_READ_CACHE.get(qkey)
        if not isinstance(qdata, dict) or not isinstance(qdata.get("items"), list):
            continue

        items: list[dict[str, Any]] = qdata["items"]
        match_idx = next(
            (idx for idx, item in enumerate(items) if isinstance(item, dict) and item.get("id") == case_id_str),
            None,
        )
        if match_idx is None:
            if f_sort_by == "updated_at":
                _VERIF_READ_CACHE.delete(qkey)
            continue

        patched = dict(items[match_idx])
        patched["case_status"] = new_status
        patched["version"] = version
        patched["updated_at"] = updated_iso
        patched["last_reviewed_at"] = reviewed_iso
        if claim_changed and current_claim is not None:
            patched["current_claim"] = current_claim
        if domain_changed and domain is not None:
            patched["domain"] = domain
        if assigned_reviewer_changed:
            patched["assigned_reviewer_id"] = (
                str(assigned_reviewer_id) if assigned_reviewer_id else None
            )
            patched["assigned_reviewer_name"] = assigned_reviewer_name

        if f_sort_by == "updated_at":
            if int(f_offset or 0) == 0 and str(f_sort_dir or "desc").lower() != "asc":
                items.pop(match_idx)
                items.insert(0, patched)
            else:
                _VERIF_READ_CACHE.delete(qkey)
                continue
        else:
            items[match_idx] = patched

        case_details_map = qdata.get("case_details")
        if isinstance(case_details_map, dict):
            if patched_case_detail is not None and key_user_id == str(actor_user_id):
                case_details_map[case_id_str] = patched_case_detail
            elif key_user_id != str(actor_user_id):
                case_details_map.pop(case_id_str, None)

        _VERIF_READ_CACHE.set(qkey, qdata, ttl_seconds=300)


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

    def _get_restricted_titles(
        self,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        has_manage: bool,
    ) -> set[str]:
        use_cache = not bool(os.getenv("PYTEST_CURRENT_TEST"))
        rest_cache_key = f"vrest:{project_id}:{user_id}:{has_manage}"
        if use_cache:
            cached = _VERIF_READ_CACHE.get(rest_cache_key)
            if isinstance(cached, list):
                return set(cached)
        titles = self.access_policy.list_restricted_titles_for_viewer(
            self.session,
            project_id=project_id,
            user_id=user_id,
            has_project_manage=has_manage,
        )
        if use_cache:
            _VERIF_READ_CACHE.set(rest_cache_key, sorted(titles), ttl_seconds=300)
        return titles

    def _has_viewer_restrictions(
        self,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        has_manage: bool,
    ) -> bool:
        use_cache = not bool(os.getenv("PYTEST_CURRENT_TEST"))
        cache_key = f"vunrest:{project_id}:{user_id}:{has_manage}"
        if use_cache:
            cached = _VERIF_READ_CACHE.get(cache_key)
            if isinstance(cached, bool):
                return cached

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
        if use_cache:
            _VERIF_READ_CACHE.set(cache_key, has_restrictions, ttl_seconds=300)
        return has_restrictions

    def _get_project_facets(
        self, project_id: uuid.UUID
    ) -> tuple[list[str], list[str], list[str]]:
        use_cache = not bool(os.getenv("PYTEST_CURRENT_TEST"))
        cache_key = f"vfacets:{project_id}"
        if use_cache:
            cached = _VERIF_READ_CACHE.get(cache_key)
            if (
                isinstance(cached, dict)
                and isinstance(cached.get("domains"), list)
                and isinstance(cached.get("sources"), list)
                and isinstance(cached.get("people"), list)
            ):
                return cached["domains"], cached["sources"], cached["people"]

        from app.services.knowledge_domains import resolve_canonical_domain

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

        result = (sorted(f_domains), sorted(f_sources), sorted(f_people))
        if use_cache:
            _VERIF_READ_CACHE.set(
                cache_key,
                {"domains": result[0], "sources": result[1], "people": result[2]},
                ttl_seconds=300,
            )
        return result

    def _build_case_sql_filters(
        self,
        project_id: uuid.UUID,
        *,
        status: str | None = None,
        domain: str | None = None,
        person: str | None = None,
        source: str | None = None,
        reviewer_id: uuid.UUID | None = None,
        category: str | None = None,
        search: str | None = None,
    ) -> list[Any]:
        from app.services.knowledge_domains import (
            canonical_domain_to_legacy_category,
            resolve_canonical_domain,
        )

        base_filter: list[Any] = [
            VerificationCase.project_id == project_id,
            VerificationCase.case_status != VerificationCaseStatus.ARCHIVED.value,
        ]
        if status:
            base_filter.append(VerificationCase.case_status == status)
        if domain:
            dom_clean = domain.strip()
            allowed_doms = {dom_clean.lower()}
            try:
                c_dom = resolve_canonical_domain(dom_clean)
                allowed_doms.add(c_dom.value.lower())
                allowed_doms.add(canonical_domain_to_legacy_category(c_dom).lower())
            except (ValueError, KeyError):
                pass
            base_filter.append(func.lower(VerificationCase.domain).in_(allowed_doms))
        if source:
            base_filter.append(VerificationCase.source_provider == source)
        if reviewer_id:
            base_filter.append(VerificationCase.assigned_reviewer_id == reviewer_id)
        person_q = person.strip().lower() if person and person.strip() else None
        if person_q:
            base_filter.append(
                func.lower(func.coalesce(VerificationCase.person_name, "")).contains(
                    person_q, autoescape=True
                )
            )
        if category:
            cat_exists = (
                select(VerificationIssue.id)
                .where(
                    VerificationIssue.case_id == VerificationCase.id,
                    VerificationIssue.resolution_state == IssueResolutionState.OPEN.value,
                    VerificationIssue.verification_category == category,
                )
                .exists()
            )
            base_filter.append(cat_exists)
        search_q = search.strip().lower() if search and search.strip() else None
        if search_q:
            base_filter.append(
                or_(
                    func.lower(func.coalesce(VerificationCase.title, "")).contains(
                        search_q, autoescape=True
                    ),
                    func.lower(VerificationCase.current_claim).contains(
                        search_q, autoescape=True
                    ),
                    func.lower(VerificationCase.original_ai_claim).contains(
                        search_q, autoescape=True
                    ),
                    func.lower(VerificationCase.domain).contains(
                        search_q, autoescape=True
                    ),
                )
            )
        return base_filter

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

        # Fast SQL GROUP BY + scalar subquery path when viewer has full access to all project sources
        if not self._has_viewer_restrictions(project_id, user_id, has_manage):
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
                issues_scalar = (
                    select(func.count(VerificationIssue.id))
                    .where(
                        VerificationIssue.case_id.in_(active_subq),
                        VerificationIssue.resolution_state == IssueResolutionState.OPEN.value,
                    )
                    .scalar_subquery()
                )
                conflicts_scalar = (
                    select(func.count(VerificationConflict.id))
                    .where(
                        VerificationConflict.case_id.in_(active_subq),
                        VerificationConflict.resolution_state == ConflictResolutionState.UNRESOLVED.value,
                    )
                    .scalar_subquery()
                )
                ctx_scalar = (
                    select(func.count(VerificationContextRequest.id))
                    .where(
                        VerificationContextRequest.case_id.in_(active_subq),
                        VerificationContextRequest.status == ContextRequestStatus.PENDING.value,
                    )
                    .scalar_subquery()
                )
                open_issues, open_conflicts, pending_ctx = self.session.execute(
                    select(issues_scalar, conflicts_scalar, ctx_scalar)
                ).one()
                resp = VerificationSummaryResponse(
                    project_id=project_id,
                    total_cases=sum(status_counts.values()),
                    candidate_count=status_counts.get(VerificationCaseStatus.CANDIDATE.value, 0),
                    pending_review_count=status_counts.get(VerificationCaseStatus.PENDING_REVIEW.value, 0),
                    conflicted_count=status_counts.get(VerificationCaseStatus.CONFLICTED.value, 0),
                    unresolved_count=status_counts.get(VerificationCaseStatus.UNRESOLVED.value, 0),
                    verified_count=status_counts.get(VerificationCaseStatus.VERIFIED.value, 0),
                    rejected_count=status_counts.get(VerificationCaseStatus.REJECTED.value, 0),
                    open_issues_count=int(open_issues or 0),
                    open_conflicts_count=int(open_conflicts or 0),
                    pending_context_requests_count=int(pending_ctx or 0),
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
        q_filter_json = json.dumps(
            [
                status,
                domain,
                person,
                source,
                str(reviewer_id) if reviewer_id else None,
                category,
                search,
                sort_by,
                sort_dir,
                limit,
                offset,
            ],
            separators=(",", ":"),
        )
        q_cache_key = f"vq:{project_id}:{user_id}:{has_manage}:{q_filter_json}"
        if use_cache:
            cached_q = _VERIF_READ_CACHE.get(q_cache_key)
            if isinstance(cached_q, dict):
                return VerificationQueueResponse.model_validate(cached_q)

        search_q = search.strip().lower() if search and search.strip() else None
        person_q = person.strip().lower() if person and person.strip() else None

        # Fast SQL-paginated path supporting all filters whenever viewer has unrestricted access
        if not self._has_viewer_restrictions(project_id, user_id, has_manage):
            base_filter = self._build_case_sql_filters(
                project_id,
                status=status,
                domain=domain,
                person=person,
                source=source,
                reviewer_id=reviewer_id,
                category=category,
                search=search,
            )
            sort_col = {
                "updated_at": VerificationCase.updated_at,
                "created_at": VerificationCase.created_at,
                "priority": VerificationCase.priority,
                "status": VerificationCase.case_status,
                "domain": VerificationCase.domain,
            }.get(sort_by, VerificationCase.updated_at)
            order_expr = sort_col.asc() if sort_dir.lower() == "asc" else sort_col.desc()

            id_count_rows = self.session.execute(
                select(VerificationCase.id, func.count(VerificationCase.id).over())
                .where(*base_filter)
                .order_by(order_expr, VerificationCase.id.asc())
                .limit(limit)
                .offset(offset)
            ).all()
            if id_count_rows:
                page_ids = [r[0] for r in id_count_rows]
                total_fast = int(id_count_rows[0][1])
            else:
                page_ids = []
                total_fast = (
                    int(
                        self.session.execute(
                            select(func.count(VerificationCase.id)).where(*base_filter)
                        ).scalar()
                        or 0
                    )
                    if offset > 0
                    else 0
                )

            f_domains, f_sources, f_people = self._get_project_facets(project_id)
            has_any_filter = any([status, domain, person_q, source, reviewer_id, category, search_q])
            if total_fast > 0 or has_any_filter or f_domains or f_sources or f_people:
                page_cases = (
                    self.repo.list_project_cases_by_ids(project_id, page_ids) if page_ids else []
                )
                acl_map, fallback_target_evs = (
                    self._batch_evaluate_cases_acl(
                        page_cases, project_id=project_id, user_id=user_id, has_manage=has_manage
                    )
                    if page_cases
                    else ({}, {})
                )
                user_names = (
                    self._resolve_user_names_for_cases(
                        page_cases, viewer=project_ctx.principal.user
                    )
                    if page_cases
                    else {}
                )
                fast_items: list[VerificationQueueItem] = []
                fast_details: dict[str, VerificationCaseDetailResponse] = {}
                for case in page_cases:
                    accessible_refs, _restricted_cnt, _ = self._classify_case_access(
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
                    detail_resp = self._build_case_detail_from_loaded(
                        case,
                        acl_map=acl_map,
                        fallback_target_evs=fallback_target_evs,
                        restricted_titles=set(),
                        user_names=user_names,
                    )
                    fast_details[str(case.id)] = detail_resp
                    if use_cache:
                        _VERIF_READ_CACHE.set(
                            f"vcase:{project_id}:{case.id}:{user_id}:{has_manage}",
                            detail_resp.model_dump(mode="json"),
                            ttl_seconds=300,
                        )
                fast_resp = VerificationQueueResponse(
                    items=fast_items,
                    total=total_fast,
                    limit=limit,
                    offset=offset,
                    available_domains=f_domains,
                    available_sources=f_sources,
                    available_people=f_people,
                    case_details=fast_details,
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
        restricted_titles = self._get_restricted_titles(project_id, user_id, has_manage)

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

        user_names = (
            self._resolve_user_names_for_cases(
                page_cases, viewer=project_ctx.principal.user
            )
            if page_cases
            else {}
        )
        page_items: list[VerificationQueueItem] = []
        page_details: dict[str, VerificationCaseDetailResponse] = {}
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
            detail_resp = self._build_case_detail_from_loaded(
                case,
                acl_map=acl_map,
                fallback_target_evs=fallback_target_evs,
                restricted_titles=restricted_titles,
                user_names=user_names,
            )
            page_details[str(case.id)] = detail_resp
            if use_cache:
                _VERIF_READ_CACHE.set(
                    f"vcase:{project_id}:{case.id}:{user_id}:{has_manage}",
                    detail_resp.model_dump(mode="json"),
                    ttl_seconds=300,
                )

        q_resp = VerificationQueueResponse(
            items=page_items,
            total=total,
            limit=limit,
            offset=offset,
            available_domains=sorted(facet_domains),
            available_sources=sorted(facet_sources),
            available_people=sorted(facet_people),
            case_details=page_details,
        )
        if use_cache:
            _VERIF_READ_CACHE.set(q_cache_key, q_resp.model_dump(mode="json"), ttl_seconds=300)
        return q_resp

    def get_case_detail(
        self,
        case_id: uuid.UUID,
        *,
        project_ctx: ProjectContext,
        force_reload: bool = False,
    ) -> VerificationCaseDetailResponse:
        user_id, has_manage = self._verify_viewer_access(project_ctx)

        use_cache = not bool(os.getenv("PYTEST_CURRENT_TEST"))
        case_cache_key = f"vcase:{project_ctx.project.id}:{case_id}:{user_id}:{has_manage}"
        if use_cache and not force_reload:
            cached_case = _VERIF_READ_CACHE.get(case_cache_key)
            if isinstance(cached_case, dict):
                return VerificationCaseDetailResponse.model_validate(cached_case)

        case = self.repo.get_case(case_id, project_id=project_ctx.project.id, load_details=True)
        if case is None:
            raise NotFoundError(f"Verification case {case_id} not found in this project.")

        acl_map, fallback_target_evs = self._batch_evaluate_cases_acl(
            [case], project_id=project_ctx.project.id, user_id=user_id, has_manage=has_manage
        )
        restricted_titles = self._get_restricted_titles(
            project_ctx.project.id, user_id, has_manage
        )
        user_names = self._resolve_user_names_for_cases(
            [case], viewer=project_ctx.principal.user
        )
        detail_resp = self._build_case_detail_from_loaded(
            case,
            acl_map=acl_map,
            fallback_target_evs=fallback_target_evs,
            restricted_titles=restricted_titles,
            user_names=user_names,
        )
        if use_cache:
            _VERIF_READ_CACHE.set(
                case_cache_key, detail_resp.model_dump(mode="json"), ttl_seconds=300
            )
        return detail_resp

    def _resolve_user_names_for_cases(
        self,
        cases: list[VerificationCase],
        *,
        viewer: User,
    ) -> dict[uuid.UUID, str]:
        known_names: dict[uuid.UUID, str] = {
            viewer.id: viewer.full_name or viewer.email,
        }
        user_ids: set[uuid.UUID] = set()
        for case in cases:
            if case.assigned_reviewer is not None:
                known_names[case.assigned_reviewer.id] = (
                    case.assigned_reviewer.full_name or case.assigned_reviewer.email
                )
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

        missing_user_ids = {uid for uid in user_ids if uid not in known_names}
        user_names = dict(known_names)
        if missing_user_ids:
            user_names.update(self._load_user_names(missing_user_ids))
        return user_names

    def _build_case_detail_from_loaded(
        self,
        case: VerificationCase,
        *,
        acl_map: dict[uuid.UUID, tuple[bool, EvidenceItem | None]],
        fallback_target_evs: dict[uuid.UUID, set[uuid.UUID]],
        restricted_titles: set[str],
        user_names: dict[uuid.UUID, str],
    ) -> VerificationCaseDetailResponse:
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

        detail_resp = VerificationCaseDetailResponse(
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
        return detail_resp

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
        case.updated_at = now

        self._sync_target_review_state(
            case,
            epistemic_status=EpistemicStatus.HUMAN_VERIFIED.value,
            review_status=KnowledgeReviewStatus.APPROVED.value,
            rel_status=RelationshipVerificationStatus.VERIFIED.value,
            now=now,
        )
        evt = self._record_review_event(
            case=case,
            reviewer_id=project_ctx.principal.user.id,
            action=ReviewActionType.APPROVE.value,
            previous_status=prev_status,
            new_status=case.case_status,
            decision_reason=payload.decision_reason,
            review_notes=payload.reviewer_note,
            now=now,
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
        return self._finalize_case_action_response(
            case=case,
            project_ctx=project_ctx,
            previous_status=prev_status,
            review_event=evt,
        )

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
        case.updated_at = now

        self._sync_target_review_state(
            case,
            epistemic_status=None,
            review_status=KnowledgeReviewStatus.REJECTED.value,
            rel_status=RelationshipVerificationStatus.REJECTED.value,
            now=now,
        )
        evt = self._record_review_event(
            case=case,
            reviewer_id=project_ctx.principal.user.id,
            action=ReviewActionType.REJECT.value,
            previous_status=prev_status,
            new_status=case.case_status,
            decision_reason=payload.decision_reason,
            review_notes=payload.reviewer_note,
            now=now,
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
        return self._finalize_case_action_response(
            case=case,
            project_ctx=project_ctx,
            previous_status=prev_status,
            review_event=evt,
        )

    def edit_finding(
        self,
        case_id: uuid.UUID,
        *,
        project_ctx: ProjectContext,
        payload: EditFindingRequest,
    ) -> VerificationCaseDetailResponse:
        case = self._require_case(case_id, project_ctx.project.id)
        evidence_item_ids = list(
            self.session.execute(
                select(VerificationEvidenceRef.evidence_item_id).where(
                    VerificationEvidenceRef.case_id == case.id
                )
            )
            .scalars()
            .all()
        )
        if not evidence_item_ids:
            raise UnprocessableEntityError(
                "Factual claims must be supported by at least one evidence reference before editing. "
                "Request additional context or attach evidence first."
            )

        now = datetime.now(UTC)
        prev_status = case.case_status
        prev_claim = case.current_claim
        prev_domain = case.domain
        new_domain = payload.domain.strip() if payload.domain else case.domain

        case.version += 1
        case.current_claim = payload.current_claim
        case.domain = new_domain
        case.last_reviewed_at = now
        case.updated_at = now
        # Editing returns a finding to PENDING_REVIEW so the updated claim is explicitly confirmed
        if case.case_status != VerificationCaseStatus.CONFLICTED.value:
            case.case_status = VerificationCaseStatus.PENDING_REVIEW.value

        revision = VerificationFindingRevision(
            id=uuid.uuid4(),
            organisation_id=case.organisation_id,
            project_id=case.project_id,
            case_id=case.id,
            revision_number=case.version,
            claim_text=payload.current_claim,
            domain=new_domain,
            is_ai_original=False,
            edited_by_user_id=project_ctx.principal.user.id,
            edit_reason=payload.edit_reason,
            evidence_snapshot_json={
                "evidence_item_ids": [str(eid) for eid in evidence_item_ids]
            },
            created_at=now,
        )
        self.session.add(revision)

        # Sync edited statement back to KnowledgeItem without overwriting AI original on case
        if case.target_type == VerificationTargetType.KNOWLEDGE_ITEM.value:
            self.session.execute(
                update(KnowledgeItem)
                .where(
                    KnowledgeItem.id == case.target_id,
                    KnowledgeItem.project_id == case.project_id,
                )
                .values(
                    structured_summary=payload.current_claim,
                    category=new_domain,
                    review_status=KnowledgeReviewStatus.PENDING_REVIEW.value,
                    updated_at=now,
                )
            )

        evt = self._record_review_event(
            case=case,
            reviewer_id=project_ctx.principal.user.id,
            action=ReviewActionType.EDIT.value,
            previous_status=prev_status,
            new_status=case.case_status,
            decision_reason=payload.edit_reason,
            review_notes=payload.reviewer_note,
            previous_snapshot={"claim": prev_claim},
            new_snapshot={"claim": payload.current_claim, "domain": new_domain},
            now=now,
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
        return self._finalize_case_action_response(
            case=case,
            project_ctx=project_ctx,
            previous_status=prev_status,
            review_event=evt,
            revision=revision,
            claim_changed=True,
            domain_changed=(new_domain != prev_domain),
        )

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
            id=uuid.uuid4(),
            organisation_id=case.organisation_id,
            project_id=case.project_id,
            case_id=case.id,
            requested_by_user_id=project_ctx.principal.user.id,
            requested_from_user_id=payload.requested_from_user_id,
            question=payload.question,
            requested_information_type=payload.requested_information_type,
            status=ContextRequestStatus.PENDING.value,
            created_at=now,
            updated_at=now,
        )
        self.session.add(req)

        if case.case_status == VerificationCaseStatus.CANDIDATE.value:
            case.case_status = VerificationCaseStatus.PENDING_REVIEW.value
        case.last_reviewed_at = now
        case.updated_at = now

        requested_from_name: str | None = None
        viewer = project_ctx.principal.user
        has_manage = project_ctx.has_permission("project.manage")
        use_cache = not bool(os.getenv("PYTEST_CURRENT_TEST"))
        case_cache_key = f"vcase:{case.project_id}:{case.id}:{viewer.id}:{has_manage}"
        if use_cache and _VERIF_READ_CACHE.get(case_cache_key) is not None:
            if payload.requested_from_user_id == viewer.id:
                requested_from_name = viewer.full_name or viewer.email
            else:
                requested_from_name = self._load_user_names({payload.requested_from_user_id}).get(
                    payload.requested_from_user_id
                )

        evt = self._record_review_event(
            case=case,
            reviewer_id=project_ctx.principal.user.id,
            action=ReviewActionType.REQUEST_CONTEXT.value,
            previous_status=prev_status,
            new_status=case.case_status,
            decision_reason=payload.question,
            review_notes=payload.reviewer_note,
            now=now,
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
        return self._finalize_case_action_response(
            case=case,
            project_ctx=project_ctx,
            previous_status=prev_status,
            review_event=evt,
            context_request=req,
            requested_from_name=requested_from_name,
            pending_context_delta=1,
        )

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
        invalidate_verification_read_cache(case.project_id)
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
        case.updated_at = now

        self._sync_target_review_state(
            case,
            epistemic_status=None,
            review_status=KnowledgeReviewStatus.NEEDS_CLARIFICATION.value,
            rel_status=RelationshipVerificationStatus.UNRESOLVED.value,
            now=now,
        )
        evt = self._record_review_event(
            case=case,
            reviewer_id=project_ctx.principal.user.id,
            action=ReviewActionType.MARK_UNRESOLVED.value,
            previous_status=prev_status,
            new_status=case.case_status,
            decision_reason=payload.decision_reason,
            review_notes=payload.reviewer_note,
            now=now,
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
        return self._finalize_case_action_response(
            case=case,
            project_ctx=project_ctx,
            previous_status=prev_status,
            review_event=evt,
        )

    def assign_reviewer(
        self,
        case_id: uuid.UUID,
        *,
        project_ctx: ProjectContext,
        assigned_reviewer_id: uuid.UUID | None,
    ) -> VerificationCaseDetailResponse:
        case = self._require_case(case_id, project_ctx.project.id)
        now = datetime.now(UTC)
        prev_status = case.case_status
        case.assigned_reviewer_id = assigned_reviewer_id
        case.updated_at = now
        if assigned_reviewer_id is not None and case.case_status == VerificationCaseStatus.CANDIDATE.value:
            case.case_status = VerificationCaseStatus.PENDING_REVIEW.value

        assigned_reviewer_name: str | None = None
        viewer = project_ctx.principal.user
        has_manage = project_ctx.has_permission("project.manage")
        use_cache = not bool(os.getenv("PYTEST_CURRENT_TEST"))
        if assigned_reviewer_id is not None and use_cache:
            case_cached = (
                _VERIF_READ_CACHE.get(
                    f"vcase:{case.project_id}:{case.id}:{viewer.id}:{has_manage}"
                )
                is not None
            )
            queue_cached = bool(_VERIF_READ_CACHE.keys_with_prefix(f"vq:{case.project_id}:"))
            if case_cached or queue_cached:
                if assigned_reviewer_id == viewer.id:
                    assigned_reviewer_name = viewer.full_name or viewer.email
                else:
                    assigned_reviewer_name = self._load_user_names({assigned_reviewer_id}).get(
                        assigned_reviewer_id
                    )

        evt = self._record_review_event(
            case=case,
            reviewer_id=project_ctx.principal.user.id,
            action=ReviewActionType.ASSIGN.value,
            previous_status=prev_status,
            new_status=case.case_status,
            decision_reason="Assigned reviewer" if assigned_reviewer_id else "Unassigned reviewer",
            now=now,
        )
        self.session.commit()
        return self._finalize_case_action_response(
            case=case,
            project_ctx=project_ctx,
            previous_status=prev_status,
            review_event=evt,
            assigned_reviewer_changed=True,
            assigned_reviewer_name=assigned_reviewer_name,
        )

    def verify_all_cases(
        self,
        *,
        project_ctx: ProjectContext,
        payload: VerifyAllFindingsRequest,
    ) -> VerifyAllFindingsResponse:
        user_id, has_manage = self._verify_viewer_access(project_ctx)
        project_id = project_ctx.project.id

        eligible_statuses = {
            VerificationCaseStatus.CANDIDATE.value,
            VerificationCaseStatus.PENDING_REVIEW.value,
            VerificationCaseStatus.CONFLICTED.value,
            VerificationCaseStatus.UNRESOLVED.value,
        }

        target_rows: list[tuple[uuid.UUID, uuid.UUID, str, str, uuid.UUID, int]] = []
        already_verified_count = 0

        if not self._has_viewer_restrictions(project_id, user_id, has_manage):
            base_filter = self._build_case_sql_filters(
                project_id,
                status=payload.status,
                domain=payload.domain,
                person=payload.person,
                source=payload.source,
                reviewer_id=payload.reviewer_id,
                category=payload.category,
                search=payload.search,
            )
            raw_rows = self.session.execute(
                select(
                    VerificationCase.id,
                    VerificationCase.organisation_id,
                    VerificationCase.case_status,
                    VerificationCase.target_type,
                    VerificationCase.target_id,
                    VerificationCase.version,
                ).where(*base_filter)
            ).all()
            for row in raw_rows:
                st = str(row[2])
                if st == VerificationCaseStatus.VERIFIED.value:
                    already_verified_count += 1
                elif st in eligible_statuses:
                    target_rows.append(
                        (row[0], row[1], st, str(row[3]), row[4], int(row[5] or 1))
                    )
            if payload.status and payload.status != VerificationCaseStatus.VERIFIED.value:
                already_verified_count = int(
                    self.session.execute(
                        select(func.count(VerificationCase.id)).where(
                            VerificationCase.project_id == project_id,
                            VerificationCase.case_status == VerificationCaseStatus.VERIFIED.value,
                        )
                    ).scalar()
                    or 0
                )
        else:
            from app.services.knowledge_domains import (
                canonical_domain_to_legacy_category,
                resolve_canonical_domain,
            )

            search_q = payload.search.strip().lower() if payload.search and payload.search.strip() else None
            person_q = payload.person.strip().lower() if payload.person and payload.person.strip() else None
            light_data = self.repo.list_project_cases_lightweight(
                project_id,
                include_claim_text=search_q is not None,
            )
            acl_map, fallback_target_evs = self._batch_evaluate_lightweight_acl(
                light_data, project_id=project_id, user_id=user_id, has_manage=has_manage
            )
            restricted_titles = self._get_restricted_titles(project_id, user_id, has_manage)
            refs_by_case = light_data["refs_by_case"]
            open_issues_by_case = light_data["open_issues_by_case"]

            allowed_doms: set[str] | None = None
            if payload.domain:
                dom_clean = payload.domain.strip()
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

            eligible_ids: list[uuid.UUID] = []
            for row in light_data["cases"]:
                _, _, fully_restricted = self._classify_lightweight_access(
                    row, refs_by_case, acl_map, fallback_target_evs
                )
                if fully_restricted:
                    continue
                if row.case_status == VerificationCaseStatus.VERIFIED.value:
                    already_verified_count += 1
                if payload.status and row.case_status != payload.status:
                    continue
                if allowed_doms is not None and row.domain not in allowed_doms and (row.domain or "").lower() not in allowed_doms:
                    continue
                if payload.source and row.source_provider != payload.source:
                    continue
                if payload.reviewer_id and row.assigned_reviewer_id != payload.reviewer_id:
                    continue
                if person_q and (not row.person_name or person_q not in row.person_name.lower()):
                    continue
                if payload.category:
                    has_cat = any(
                        cat == payload.category
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
                if row.case_status in eligible_statuses:
                    eligible_ids.append(row.id)

            for idx in range(0, len(eligible_ids), 500):
                batch_ids = eligible_ids[idx : idx + 500]
                raw_rows = self.session.execute(
                    select(
                        VerificationCase.id,
                        VerificationCase.organisation_id,
                        VerificationCase.case_status,
                        VerificationCase.target_type,
                        VerificationCase.target_id,
                        VerificationCase.version,
                    ).where(
                        VerificationCase.project_id == project_id,
                        VerificationCase.id.in_(batch_ids),
                    )
                ).all()
                for row in raw_rows:
                    target_rows.append(
                        (row[0], row[1], str(row[2]), str(row[3]), row[4], int(row[5] or 1))
                    )

        ki_target_ids: list[uuid.UUID] = []
        rel_target_ids: list[uuid.UUID] = []
        if target_rows:
            now = datetime.now(UTC)
            reason_text = (
                (payload.decision_reason or "").strip()
                or "Bulk verified via Verify All in Verification Center"
            )
            note_text = (payload.reviewer_note or "").strip() or None
            corr_id = (get_correlation_id() or "-")[:64]

            case_ids = [r[0] for r in target_rows]
            ki_target_ids = list(
                {r[4] for r in target_rows if r[3] == VerificationTargetType.KNOWLEDGE_ITEM.value}
            )
            rel_target_ids = list(
                {r[4] for r in target_rows if r[3] == VerificationTargetType.RELATIONSHIP.value}
            )

            for idx in range(0, len(case_ids), 500):
                batch_ids = case_ids[idx : idx + 500]
                self.session.execute(
                    update(VerificationCase)
                    .where(
                        VerificationCase.project_id == project_id,
                        VerificationCase.id.in_(batch_ids),
                    )
                    .values(
                        case_status=VerificationCaseStatus.VERIFIED.value,
                        resolved_at=now,
                        last_reviewed_at=now,
                        updated_at=now,
                    )
                )

            for idx in range(0, len(ki_target_ids), 500):
                batch_ids = ki_target_ids[idx : idx + 500]
                self.session.execute(
                    update(KnowledgeItem)
                    .where(
                        KnowledgeItem.project_id == project_id,
                        KnowledgeItem.id.in_(batch_ids),
                    )
                    .values(
                        epistemic_status=EpistemicStatus.HUMAN_VERIFIED.value,
                        review_status=KnowledgeReviewStatus.APPROVED.value,
                        updated_at=now,
                    )
                )

            for idx in range(0, len(rel_target_ids), 500):
                batch_ids = rel_target_ids[idx : idx + 500]
                self.session.execute(
                    update(KnowledgeRelationship)
                    .where(
                        KnowledgeRelationship.project_id == project_id,
                        KnowledgeRelationship.id.in_(batch_ids),
                    )
                    .values(
                        verification_status=RelationshipVerificationStatus.VERIFIED.value,
                        updated_at=now,
                    )
                )

            event_rows = [
                {
                    "id": uuid.uuid4(),
                    "organisation_id": org_id,
                    "project_id": project_id,
                    "case_id": cid,
                    "reviewer_user_id": user_id,
                    "action": ReviewActionType.APPROVE.value,
                    "previous_status": prev_st,
                    "new_status": VerificationCaseStatus.VERIFIED.value,
                    "case_version": ver,
                    "decision_reason": reason_text,
                    "review_notes": note_text,
                    "previous_snapshot_json": None,
                    "new_snapshot_json": None,
                    "correlation_id": corr_id,
                    "created_at": now,
                }
                for cid, org_id, prev_st, _ttype, _tid, ver in target_rows
            ]
            for idx in range(0, len(event_rows), 500):
                self.session.execute(
                    insert(VerificationReviewEvent), event_rows[idx : idx + 500]
                )

            self.audit.record_event(
                event_type="verification.cases.bulk_approved",
                resource_type="verification_case",
                actor_user_id=user_id,
                organisation_id=project_ctx.organisation.id,
                project_id=project_id,
                resource_id=str(project_id),
                outcome=AuditOutcome.SUCCESS.value,
                metadata={
                    "verified_count": len(case_ids),
                    "knowledge_items_verified": len(ki_target_ids),
                    "relationships_verified": len(rel_target_ids),
                },
            )
            self.session.commit()

        invalidate_verification_read_cache(project_id)
        summary = self.get_summary(project_id, project_ctx=project_ctx)
        return VerifyAllFindingsResponse(
            project_id=project_id,
            verified_count=len(target_rows),
            knowledge_items_verified=len(ki_target_ids),
            relationships_verified=len(rel_target_ids),
            already_verified_count=already_verified_count,
            summary=summary,
        )

    # -----------------------------------------------------------------------
    # Internal Helpers
    # -----------------------------------------------------------------------

    def _require_case(
        self,
        case_id: uuid.UUID,
        project_id: uuid.UUID,
        *,
        load_details: bool = False,
    ) -> VerificationCase:
        case = self.repo.get_case(case_id, project_id=project_id, load_details=load_details)
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
        now: datetime | None = None,
    ) -> None:
        ts = now or datetime.now(UTC)
        if case.target_type == VerificationTargetType.KNOWLEDGE_ITEM.value:
            values: dict[str, Any] = {
                "review_status": review_status,
                "updated_at": ts,
            }
            if epistemic_status is not None:
                values["epistemic_status"] = epistemic_status
            self.session.execute(
                update(KnowledgeItem)
                .where(
                    KnowledgeItem.id == case.target_id,
                    KnowledgeItem.project_id == case.project_id,
                )
                .values(**values)
            )
        elif case.target_type == VerificationTargetType.RELATIONSHIP.value:
            self.session.execute(
                update(KnowledgeRelationship)
                .where(
                    KnowledgeRelationship.id == case.target_id,
                    KnowledgeRelationship.project_id == case.project_id,
                )
                .values(verification_status=rel_status, updated_at=ts)
            )

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
        now: datetime | None = None,
    ) -> VerificationReviewEvent:
        corr_id = get_correlation_id() or "-"
        event_time = now or datetime.now(UTC)
        evt = VerificationReviewEvent(
            id=uuid.uuid4(),
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
            created_at=event_time,
        )
        self.session.add(evt)
        return evt

    def _finalize_case_action_response(
        self,
        *,
        case: VerificationCase,
        project_ctx: ProjectContext,
        previous_status: str,
        review_event: VerificationReviewEvent,
        revision: VerificationFindingRevision | None = None,
        context_request: VerificationContextRequest | None = None,
        requested_from_name: str | None = None,
        claim_changed: bool = False,
        domain_changed: bool = False,
        assigned_reviewer_changed: bool = False,
        assigned_reviewer_name: str | None = None,
        pending_context_delta: int = 0,
    ) -> VerificationCaseDetailResponse:
        viewer = project_ctx.principal.user
        user_id = viewer.id
        viewer_name = viewer.full_name or viewer.email
        has_manage = project_ctx.has_permission("project.manage")

        use_cache = not bool(os.getenv("PYTEST_CURRENT_TEST"))
        case_cache_key = f"vcase:{case.project_id}:{case.id}:{user_id}:{has_manage}"
        cached_case = _VERIF_READ_CACHE.get(case_cache_key) if use_cache else None

        safe_claim_for_queue: str | None = None
        if isinstance(cached_case, dict):
            restricted_count = int(cached_case.get("restricted_evidence_count") or 0)
            fully_restricted = (
                cached_case.get("source_provider") == "restricted"
                and cached_case.get("evidence_completeness") == "restricted"
            )
            restricted_titles = (
                self._get_restricted_titles(case.project_id, user_id, has_manage)
                if not fully_restricted
                else set()
            )
            if fully_restricted or restricted_count > 0:
                eligible = False
                eligibility_reason = (
                    "Blocked: supporting source evidence is restricted for the current viewer."
                )
            else:
                eligible, eligibility_reason = self._compute_handover_eligibility(case)

            updated_ts = case.updated_at or review_event.created_at
            cached_case["case_status"] = case.case_status
            cached_case["version"] = case.version
            cached_case["handover_eligible"] = eligible
            cached_case["handover_eligibility_reason"] = eligibility_reason
            cached_case["last_reviewed_at"] = (
                case.last_reviewed_at.isoformat() if case.last_reviewed_at else None
            )
            cached_case["resolved_at"] = (
                case.resolved_at.isoformat() if case.resolved_at else None
            )
            cached_case["updated_at"] = updated_ts.isoformat()

            if claim_changed:
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
                cached_case["current_claim"] = safe_curr_claim
                safe_claim_for_queue = safe_curr_claim

            if domain_changed:
                cached_case["domain"] = case.domain

            if assigned_reviewer_changed:
                cached_case["assigned_reviewer_id"] = (
                    str(case.assigned_reviewer_id) if case.assigned_reviewer_id else None
                )
                cached_case["assigned_reviewer_name"] = assigned_reviewer_name

            evt_detail = VerificationReviewEventDetail(
                id=review_event.id,
                reviewer_user_id=review_event.reviewer_user_id,
                reviewer_name=viewer_name,
                action=review_event.action,
                previous_status=review_event.previous_status,
                new_status=review_event.new_status,
                case_version=review_event.case_version,
                decision_reason=(
                    None
                    if fully_restricted
                    else self._scrub_derived_text(
                        review_event.decision_reason, restricted_titles=restricted_titles
                    )
                ),
                review_notes=(
                    None
                    if fully_restricted
                    else self._scrub_derived_text(
                        review_event.review_notes, restricted_titles=restricted_titles
                    )
                ),
                created_at=review_event.created_at,
            )
            events = list(cached_case.get("review_events") or [])
            events.insert(0, evt_detail.model_dump(mode="json"))
            cached_case["review_events"] = events

            if revision is not None:
                redact_revisions = fully_restricted or restricted_count > 0
                rev_restricted = redact_revisions or self._text_mentions_restricted(
                    revision.claim_text, restricted_titles
                )
                rev_detail = VerificationRevisionDetail(
                    id=revision.id,
                    revision_number=revision.revision_number,
                    claim_text=(
                        _REDACTED_CLAIM_TEXT
                        if rev_restricted
                        else redact_secrets(revision.claim_text)
                    ),
                    domain=revision.domain,
                    is_ai_original=revision.is_ai_original,
                    edited_by_user_id=revision.edited_by_user_id,
                    edited_by_name=viewer_name if revision.edited_by_user_id else None,
                    edit_reason=(
                        None
                        if rev_restricted
                        else self._scrub_derived_text(
                            revision.edit_reason, restricted_titles=restricted_titles
                        )
                    ),
                    created_at=revision.created_at,
                )
                revs = list(cached_case.get("revisions") or [])
                revs.insert(0, rev_detail.model_dump(mode="json"))
                cached_case["revisions"] = revs

            if context_request is not None:
                ctx_detail = VerificationContextRequestDetail(
                    id=context_request.id,
                    case_id=context_request.case_id,
                    requested_by_user_id=context_request.requested_by_user_id,
                    requested_by_name=viewer_name,
                    requested_from_user_id=context_request.requested_from_user_id,
                    requested_from_name=requested_from_name,
                    question=(
                        _REDACTED_CLAIM_TEXT
                        if fully_restricted
                        else (
                            self._scrub_derived_text(
                                context_request.question, restricted_titles=restricted_titles
                            )
                            or _REDACTED_CLAIM_TEXT
                        )
                    ),
                    requested_information_type=context_request.requested_information_type,
                    status=context_request.status,
                    response_text=None,
                    response_evidence_id=None,
                    responded_at=None,
                    created_at=context_request.created_at,
                )
                ctxs = list(cached_case.get("context_requests") or [])
                ctxs.insert(0, ctx_detail.model_dump(mode="json"))
                cached_case["context_requests"] = ctxs

            for other_key in _VERIF_READ_CACHE.keys_with_prefix(
                f"vcase:{case.project_id}:{case.id}:"
            ):
                if other_key != case_cache_key:
                    _VERIF_READ_CACHE.delete(other_key)

            validated = VerificationCaseDetailResponse.model_validate(cached_case)
            validated_dict = validated.model_dump(mode="json")
            _VERIF_READ_CACHE.set(case_cache_key, validated_dict, ttl_seconds=300)

            patch_verification_read_cache_for_case(
                project_id=case.project_id,
                actor_user_id=user_id,
                case_id=case.id,
                previous_status=previous_status,
                new_status=case.case_status,
                version=case.version,
                updated_at=updated_ts,
                last_reviewed_at=case.last_reviewed_at,
                current_claim=safe_claim_for_queue,
                domain=case.domain,
                claim_changed=claim_changed,
                domain_changed=domain_changed,
                assigned_reviewer_id=case.assigned_reviewer_id,
                assigned_reviewer_name=assigned_reviewer_name,
                assigned_reviewer_changed=assigned_reviewer_changed,
                pending_context_delta=pending_context_delta,
                patched_case_detail=validated_dict,
            )
            return validated

        _VERIF_READ_CACHE.invalidate_prefix(f"vcase:{case.project_id}:{case.id}:")
        if use_cache:
            if claim_changed:
                restricted_titles = self._get_restricted_titles(
                    case.project_id, user_id, has_manage
                )
                safe_claim_for_queue = (
                    self._scrub_derived_text(
                        case.current_claim,
                        restricted_titles=restricted_titles,
                        replacement=_REDACTED_CLAIM_TEXT,
                    )
                    or ""
                )
            patch_verification_read_cache_for_case(
                project_id=case.project_id,
                actor_user_id=user_id,
                case_id=case.id,
                previous_status=previous_status,
                new_status=case.case_status,
                version=case.version,
                updated_at=case.updated_at or review_event.created_at,
                last_reviewed_at=case.last_reviewed_at,
                current_claim=safe_claim_for_queue,
                domain=case.domain,
                claim_changed=claim_changed,
                domain_changed=domain_changed,
                assigned_reviewer_id=case.assigned_reviewer_id,
                assigned_reviewer_name=assigned_reviewer_name,
                assigned_reviewer_changed=assigned_reviewer_changed,
                pending_context_delta=pending_context_delta,
            )
        self.session.expire(case)
        return self.get_case_detail(case.id, project_ctx=project_ctx, force_reload=True)

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
