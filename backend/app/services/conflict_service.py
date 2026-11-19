"""Service layer for the Conflict Management Workspace."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.security import utc_now
from app.models.audit import AuditLog
from app.models.enums import (
    ConflictPriority,
    ConflictResolutionState,
    ConflictResolutionStrategy,
    IssueResolutionState,
    ProjectMembershipStatus,
    ReviewActionType,
    UserStatus,
    VerificationCaseStatus,
    VerificationIssueType,
)
from app.models.evidence import EvidenceChunk, EvidenceItem
from app.models.project import ProjectMembership
from app.models.user import User
from app.models.verification import (
    VerificationCase,
    VerificationConflict,
    VerificationEvidenceRef,
    VerificationFindingRevision,
    VerificationIssue,
    VerificationReviewEvent,
)
from app.repositories.conflict import ConflictRepository
from app.schemas.conflicts import (
    ConflictAuditHistoryItem,
    ConflictDashboardMetrics,
    ConflictDetailResponse,
    ConflictEvidenceSide,
    ConflictListResponse,
    ConflictQueueItem,
    ResolveConflictRequest,
)
from app.services.handover_sections import redact_secrets
from app.services.integrations.access_policy import SourceAccessPolicyService

logger = logging.getLogger(__name__)

_REDACTED_SOURCE_TITLE = "[Restricted source]"
_REDACTED_FINDING_TITLE = "[Restricted finding]"
_REDACTED_CLAIM_TEXT = "[Content redacted: insufficient source permissions]"
_REDACTED_EXPLANATION = "[Explanation redacted: references restricted source evidence]"
_REDACTED_NOTES = "[Notes redacted: conflict references restricted source evidence]"
_REDACTED_ACL_REASON = "Access restricted by source ACL."


class ConflictService:
    """Manages the full lifecycle of cross-source contradiction investigations and resolutions."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = ConflictRepository(session)
        self.access_policy = SourceAccessPolicyService()

    def _verify_viewer_access(
        self,
        project_id: uuid.UUID,
        user_id: uuid.UUID | None,
        has_manage: bool,
    ) -> None:
        """Fail-closed validation that the caller is an active user with project membership."""
        if user_id is None:
            raise ForbiddenError("Authenticated user context is required.", code="AUTH_REQUIRED")
        user = self.session.get(User, user_id)
        if user is None or user.status != UserStatus.ACTIVE.value:
            raise ForbiddenError("Active user account is required.", code="USER_INACTIVE")
        if has_manage:
            return
        membership = self.session.execute(
            select(ProjectMembership).where(
                ProjectMembership.project_id == project_id,
                ProjectMembership.user_id == user_id,
                ProjectMembership.status == ProjectMembershipStatus.ACTIVE.value,
            )
        ).scalar_one_or_none()
        if membership is None:
            raise ForbiddenError(
                "Active project membership is required to inspect project conflicts.",
                code="PROJECT_MEMBERSHIP_REQUIRED",
            )

    def _collect_conflict_evidence_ids(
        self, conflicts: list[VerificationConflict]
    ) -> set[uuid.UUID]:
        ev_ids: set[uuid.UUID] = set()
        for c in conflicts:
            if c.claim_a_source_evidence_id is not None:
                ev_ids.add(c.claim_a_source_evidence_id)
            if c.claim_b_source_evidence_id is not None:
                ev_ids.add(c.claim_b_source_evidence_id)
            if c.related_finding is not None:
                for ref in c.related_finding.evidence_refs:
                    ev_ids.add(ref.evidence_item_id)
            if c.case is not None:
                for ref in c.case.evidence_refs:
                    ev_ids.add(ref.evidence_item_id)
        return ev_ids

    @staticmethod
    def _resolve_side_access(
        conf: VerificationConflict,
        acl_map: dict[uuid.UUID, tuple[bool, EvidenceItem | None]],
    ) -> tuple[bool, EvidenceItem | None, bool, EvidenceItem | None]:
        """Independently evaluate Side A and Side B with fail-closed null handling."""
        if conf.claim_a_source_evidence_id is None:
            allow_a, ev_a = False, None
        else:
            allow_a, ev_a = acl_map.get(conf.claim_a_source_evidence_id, (False, None))

        if conf.claim_b_source_evidence_id is None:
            allow_b, ev_b = False, None
        else:
            allow_b, ev_b = acl_map.get(conf.claim_b_source_evidence_id, (False, None))

        return allow_a, ev_a, allow_b, ev_b

    @staticmethod
    def _case_has_restricted_evidence(
        case: VerificationCase | None,
        acl_map: dict[uuid.UUID, tuple[bool, EvidenceItem | None]],
    ) -> bool:
        if case is None:
            return False
        for ref in case.evidence_refs:
            allowed, _ = acl_map.get(ref.evidence_item_id, (False, None))
            if not allowed:
                return True
        return False

    def get_dashboard_metrics(
        self,
        project_id: uuid.UUID,
        *,
        user_id: uuid.UUID | None = None,
        has_manage: bool = False,
    ) -> ConflictDashboardMetrics:
        """Return viewer-scoped summary metrics for the Conflict Management Dashboard."""
        self._verify_viewer_access(project_id, user_id, has_manage)
        assert user_id is not None

        conflicts = self.repo.list_project_conflicts_for_acl(project_id)
        acl_map = self.access_policy.evaluate_evidence_batch(
            self.session,
            self._collect_conflict_evidence_ids(conflicts),
            project_id=project_id,
            user_id=user_id,
            has_project_manage=has_manage,
        )

        status_counts: dict[str, int] = {}
        prio_counts: dict[str, int] = {}
        category_counts: dict[str, int] = {}
        for c in conflicts:
            allow_a, _, allow_b, _ = self._resolve_side_access(c, acl_map)
            if not (allow_a or allow_b):
                continue
            status_counts[c.resolution_state] = status_counts.get(c.resolution_state, 0) + 1
            prio_counts[c.priority] = prio_counts.get(c.priority, 0) + 1
            category_counts[c.conflict_type] = category_counts.get(c.conflict_type, 0) + 1

        open_count = status_counts.get("open", 0) + status_counts.get("unresolved", 0)
        investigating_count = status_counts.get("under_investigation", 0)
        awaiting_count = status_counts.get("awaiting_context", 0)
        resolved_count = (
            status_counts.get("resolved", 0)
            + status_counts.get("reconciled", 0)
            + status_counts.get("superseded", 0)
            + status_counts.get("dismissed", 0)
        )
        reopened_count = status_counts.get("reopened", 0)
        total = sum(status_counts.values())
        attention_required = open_count + investigating_count + awaiting_count

        return ConflictDashboardMetrics(
            project_id=project_id,
            total_conflicts=total,
            open_conflicts=open_count,
            under_investigation=investigating_count,
            awaiting_context=awaiting_count,
            resolved=resolved_count,
            reopened=reopened_count,
            critical_priority=prio_counts.get("critical", 0),
            high_priority=prio_counts.get("high", 0),
            medium_priority=prio_counts.get("medium", 0),
            low_priority=prio_counts.get("low", 0),
            category_counts=category_counts,
            attention_required_count=attention_required,
        )

    def list_conflicts(
        self,
        project_id: uuid.UUID,
        *,
        user_id: uuid.UUID | None = None,
        has_manage: bool = False,
        conflict_type: str | None = None,
        resolution_state: str | None = None,
        priority: str | None = None,
        assigned_to: uuid.UUID | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ConflictListResponse:
        """List viewer-authorized conflicts with per-side ACL redaction and safe search."""
        self._verify_viewer_access(project_id, user_id, has_manage)
        assert user_id is not None

        candidates = self.repo.list_project_conflicts_for_acl(
            project_id,
            conflict_type=conflict_type,
            resolution_state=resolution_state,
            priority=priority,
            assigned_to=assigned_to,
        )
        acl_map = self.access_policy.evaluate_evidence_batch(
            self.session,
            self._collect_conflict_evidence_ids(candidates),
            project_id=project_id,
            user_id=user_id,
            has_project_manage=has_manage,
        )

        search_q = search.strip().lower() if search and search.strip() else None
        authorized_items: list[ConflictQueueItem] = []

        for c in candidates:
            allow_a, ev_a, allow_b, ev_b = self._resolve_side_access(c, acl_map)
            if not (allow_a or allow_b):
                continue

            both_allowed = allow_a and allow_b
            raw_title_a = c.side_a_source_title or (ev_a.title if ev_a else "Claim A")
            raw_title_b = c.side_b_source_title or (ev_b.title if ev_b else "Opposing Evidence Claim")

            safe_title_a = redact_secrets(raw_title_a) if allow_a else _REDACTED_SOURCE_TITLE
            safe_provider_a = (
                (c.side_a_provider or (ev_a.source_type if ev_a else "source"))
                if allow_a
                else "restricted"
            )
            safe_title_b = redact_secrets(raw_title_b) if allow_b else _REDACTED_SOURCE_TITLE
            safe_provider_b = (
                (c.side_b_provider or (ev_b.source_type if ev_b else "source"))
                if allow_b
                else "restricted"
            )
            safe_explanation = (
                redact_secrets(c.explanation) if both_allowed else _REDACTED_EXPLANATION
            )

            # Search ONLY over fields the viewer is authorized to read (prevents search oracle)
            if search_q is not None:
                searchable_parts: list[str] = []
                if allow_a:
                    searchable_parts.append(safe_title_a.lower())
                    searchable_parts.append((c.claim_a_text or "").lower())
                if allow_b:
                    searchable_parts.append(safe_title_b.lower())
                    searchable_parts.append((c.claim_b_text or "").lower())
                if both_allowed:
                    searchable_parts.append(safe_explanation.lower())
                if not any(search_q in part for part in searchable_parts):
                    continue

            related_finding_restricted = self._case_has_restricted_evidence(
                c.related_finding or c.case, acl_map
            )
            authorized_items.append(
                ConflictQueueItem(
                    id=c.id,
                    project_id=c.project_id,
                    case_id=c.case_id,
                    conflict_type=c.conflict_type,
                    priority=c.priority,
                    resolution_state=c.resolution_state,
                    explanation=safe_explanation,
                    temporal_comparison=c.temporal_comparison,
                    side_a_title=safe_title_a,
                    side_a_provider=safe_provider_a,
                    side_b_title=safe_title_b,
                    side_b_provider=safe_provider_b,
                    assigned_reviewer_id=c.assigned_reviewer_id,
                    assigned_reviewer_name=(
                        c.assigned_reviewer.full_name if c.assigned_reviewer else None
                    ),
                    related_finding_id=(
                        None if related_finding_restricted and not both_allowed else c.related_finding_id
                    ),
                    created_at=c.created_at,
                    updated_at=c.updated_at,
                )
            )

        total = len(authorized_items)
        page_items = authorized_items[offset : offset + limit]
        return ConflictListResponse(items=page_items, total_count=total, offset=offset, limit=limit)

    def get_conflict_details(
        self,
        conflict_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        has_manage: bool = False,
    ) -> ConflictDetailResponse:
        """Deep side-by-side comparative inspection with fail-closed source ACL enforcement."""
        self._verify_viewer_access(project_id, user_id, has_manage)

        conf = self.repo.get_conflict_by_id(conflict_id, project_id=project_id)
        if not conf:
            raise NotFoundError("Verification conflict not found.")

        acl_map = self.access_policy.evaluate_evidence_batch(
            self.session,
            self._collect_conflict_evidence_ids([conf]),
            project_id=project_id,
            user_id=user_id,
            has_project_manage=has_manage,
        )
        allow_a, ev_a, allow_b, ev_b = self._resolve_side_access(conf, acl_map)

        if not (allow_a or allow_b):
            raise ForbiddenError(
                "You lack delegated source access to inspect this conflict.",
                code="SOURCE_ACCESS_DENIED",
            )

        both_allowed = allow_a and allow_b

        side_a = ConflictEvidenceSide(
            title=(
                redact_secrets(conf.side_a_source_title or (ev_a.title if ev_a else "Claim A"))
                if allow_a
                else _REDACTED_SOURCE_TITLE
            ),
            provider=(
                (conf.side_a_provider or (ev_a.source_type if ev_a else "source"))
                if allow_a
                else "restricted"
            ),
            claim_text=(
                redact_secrets(conf.claim_a_text) if allow_a else _REDACTED_CLAIM_TEXT
            ),
            evidence_item_id=conf.claim_a_source_evidence_id if allow_a else None,
            chunk_id=conf.claim_a_chunk_id if allow_a else None,
            source_timestamp=(
                (conf.claim_a_source_timestamp or (ev_a.source_created_at if ev_a else None))
                if allow_a
                else None
            ),
            source_url=ev_a.source_url if (ev_a and allow_a) else None,
            author=ev_a.source_author_identity if (ev_a and allow_a) else None,
            acl_scope=(ev_a.acl_scope if (ev_a and allow_a) else "source_restricted"),
            is_accessible=allow_a,
            redaction_reason=None if allow_a else _REDACTED_ACL_REASON,
        )

        side_b = ConflictEvidenceSide(
            title=(
                redact_secrets(
                    conf.side_b_source_title or (ev_b.title if ev_b else "Opposing Evidence Claim")
                )
                if allow_b
                else _REDACTED_SOURCE_TITLE
            ),
            provider=(
                (conf.side_b_provider or (ev_b.source_type if ev_b else "source"))
                if allow_b
                else "restricted"
            ),
            claim_text=(
                redact_secrets(conf.claim_b_text) if allow_b else _REDACTED_CLAIM_TEXT
            ),
            evidence_item_id=conf.claim_b_source_evidence_id if allow_b else None,
            chunk_id=conf.claim_b_chunk_id if allow_b else None,
            source_timestamp=(
                (conf.claim_b_source_timestamp or (ev_b.source_created_at if ev_b else None))
                if allow_b
                else None
            ),
            source_url=ev_b.source_url if (ev_b and allow_b) else None,
            author=ev_b.source_author_identity if (ev_b and allow_b) else None,
            acl_scope=(ev_b.acl_scope if (ev_b and allow_b) else "source_restricted"),
            is_accessible=allow_b,
            redaction_reason=None if allow_b else _REDACTED_ACL_REASON,
        )

        # Fetch Audit Trail (strip notes if either side is restricted to prevent derived leakage)
        audit_rows = self.session.execute(
            select(AuditLog)
            .where(
                AuditLog.project_id == project_id,
                AuditLog.resource_id == str(conf.id),
            )
            .order_by(AuditLog.created_at.desc())
        ).scalars().all()

        actor_ids = [a.actor_user_id for a in audit_rows if a.actor_user_id]
        actors = {}
        if actor_ids:
            u_rows = self.session.execute(select(User).where(User.id.in_(actor_ids))).scalars().all()
            actors = {u.id: u.full_name for u in u_rows}

        audit_history = [
            ConflictAuditHistoryItem(
                id=a.id,
                action=a.event_type.replace("conflict.", "").replace("_", " ").title(),
                actor_id=a.actor_user_id,
                actor_name=actors.get(a.actor_user_id, "System"),
                notes=(
                    redact_secrets(str(a.event_metadata.get("notes")))
                    if (both_allowed and a.event_metadata and a.event_metadata.get("notes"))
                    else None
                ),
                created_at=a.created_at,
            )
            for a in audit_rows
        ]

        related_case = conf.related_finding or conf.case
        related_restricted = self._case_has_restricted_evidence(related_case, acl_map)
        safe_related_title: str | None = None
        if conf.related_finding is not None:
            safe_related_title = (
                _REDACTED_FINDING_TITLE
                if (related_restricted or not both_allowed)
                else redact_secrets(conf.related_finding.title)
            )

        return ConflictDetailResponse(
            id=conf.id,
            project_id=conf.project_id,
            case_id=conf.case_id,
            conflict_type=conf.conflict_type,
            priority=conf.priority,
            resolution_state=conf.resolution_state,
            explanation=redact_secrets(conf.explanation) if both_allowed else _REDACTED_EXPLANATION,
            temporal_comparison=conf.temporal_comparison,
            side_a=side_a,
            side_b=side_b,
            assigned_reviewer_id=conf.assigned_reviewer_id,
            assigned_reviewer_name=conf.assigned_reviewer.full_name if conf.assigned_reviewer else None,
            investigation_notes=(
                (redact_secrets(conf.investigation_notes) if both_allowed else _REDACTED_NOTES)
                if conf.investigation_notes
                else None
            ),
            resolution_strategy=conf.resolution_strategy,
            authoritative_claim_text=(
                (
                    redact_secrets(conf.authoritative_claim_text)
                    if both_allowed
                    else _REDACTED_CLAIM_TEXT
                )
                if conf.authoritative_claim_text
                else None
            ),
            resolution_notes=(
                (redact_secrets(conf.resolution_notes) if both_allowed else _REDACTED_NOTES)
                if conf.resolution_notes
                else None
            ),
            resolved_by_user_id=conf.resolved_by_user_id,
            resolved_by_user_name=conf.resolved_by_user.full_name if conf.resolved_by_user else None,
            resolved_at=conf.resolved_at,
            related_finding_id=conf.related_finding_id,
            related_finding_title=safe_related_title,
            finding_domain=conf.case.domain if conf.case else None,
            created_at=conf.created_at,
            updated_at=conf.updated_at,
            audit_history=audit_history,
        )

    # -----------------------------------------------------------------------
    # Reviewer Action Handlers
    # -----------------------------------------------------------------------

    def assign_reviewer(
        self,
        conflict_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        reviewer_id: uuid.UUID | None,
        notes: str | None = None,
    ) -> ConflictDetailResponse:
        """Assign or unassign an investigator to a contradiction."""
        conf = self.repo.get_conflict_by_id(conflict_id, project_id=project_id)
        if not conf:
            raise NotFoundError("Verification conflict not found.")

        if reviewer_id is not None:
            rev = self.session.execute(select(User).where(User.id == reviewer_id)).scalars().first()
            if not rev:
                raise NotFoundError(f"User {reviewer_id} not found.")

        conf.assigned_reviewer_id = reviewer_id
        conf.updated_at = utc_now()

        # Audit log
        self.session.add(
            AuditLog(
                organisation_id=conf.organisation_id,
                project_id=conf.project_id,
                actor_user_id=user_id,
                event_type="conflict.assigned" if reviewer_id else "conflict.unassigned",
                resource_type="verification_conflict",
                resource_id=str(conf.id),
                outcome="success",
                event_metadata={
                    "assigned_to": str(reviewer_id) if reviewer_id else None,
                    "notes": notes,
                },
            )
        )
        self.session.flush()
        return self.get_conflict_details(conf.id, project_id, user_id, has_manage=True)

    def start_investigation(
        self,
        conflict_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        notes: str | None = None,
    ) -> ConflictDetailResponse:
        """Advance contradiction status to under_investigation."""
        conf = self.repo.get_conflict_by_id(conflict_id, project_id=project_id)
        if not conf:
            raise NotFoundError("Verification conflict not found.")

        conf.resolution_state = ConflictResolutionState.UNDER_INVESTIGATION.value
        conf.updated_at = utc_now()
        if not conf.assigned_reviewer_id:
            conf.assigned_reviewer_id = user_id

        if notes:
            existing = conf.investigation_notes or ""
            timestamp_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
            conf.investigation_notes = f"{existing}\n\n[{timestamp_str}] Investigation started: {notes}".strip()

        self.session.add(
            AuditLog(
                organisation_id=conf.organisation_id,
                project_id=conf.project_id,
                actor_user_id=user_id,
                event_type="conflict.investigation_started",
                resource_type="verification_conflict",
                resource_id=str(conf.id),
                outcome="success",
                event_metadata={"notes": notes},
            )
        )
        self.session.flush()
        return self.get_conflict_details(conf.id, project_id, user_id, has_manage=True)

    def request_context(
        self,
        conflict_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        context_queries: list[str],
        notes: str | None = None,
    ) -> ConflictDetailResponse:
        """Place contradiction in awaiting_context state with specific information requests."""
        conf = self.repo.get_conflict_by_id(conflict_id, project_id=project_id)
        if not conf:
            raise NotFoundError("Verification conflict not found.")

        conf.resolution_state = ConflictResolutionState.AWAITING_CONTEXT.value
        conf.updated_at = utc_now()

        queries_text = "\n".join(f"- {q}" for q in context_queries)
        timestamp_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        msg = f"[{timestamp_str}] Context requested:\n{queries_text}"
        if notes:
            msg += f"\nNotes: {notes}"

        existing = conf.investigation_notes or ""
        conf.investigation_notes = f"{existing}\n\n{msg}".strip()

        self.session.add(
            AuditLog(
                organisation_id=conf.organisation_id,
                project_id=conf.project_id,
                actor_user_id=user_id,
                event_type="conflict.context_requested",
                resource_type="verification_conflict",
                resource_id=str(conf.id),
                outcome="success",
                event_metadata={"queries": context_queries, "notes": notes},
            )
        )
        self.session.flush()
        return self.get_conflict_details(conf.id, project_id, user_id, has_manage=True)

    def add_notes(
        self,
        conflict_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        notes: str,
    ) -> ConflictDetailResponse:
        """Record an internal investigator note."""
        conf = self.repo.get_conflict_by_id(conflict_id, project_id=project_id)
        if not conf:
            raise NotFoundError("Verification conflict not found.")

        existing = conf.investigation_notes or ""
        timestamp_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        conf.investigation_notes = f"{existing}\n\n[{timestamp_str}] {notes}".strip()
        conf.updated_at = utc_now()

        self.session.add(
            AuditLog(
                organisation_id=conf.organisation_id,
                project_id=conf.project_id,
                actor_user_id=user_id,
                event_type="conflict.note_added",
                resource_type="verification_conflict",
                resource_id=str(conf.id),
                outcome="success",
                event_metadata={"notes": notes},
            )
        )
        self.session.flush()
        return self.get_conflict_details(conf.id, project_id, user_id, has_manage=True)

    def resolve_conflict(
        self,
        conflict_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        req: ResolveConflictRequest,
    ) -> ConflictDetailResponse:
        """Formally resolve a contradiction using human-guided resolution strategies."""
        conf = self.repo.get_conflict_by_id(conflict_id, project_id=project_id)
        if not conf:
            raise NotFoundError("Verification conflict not found.")

        # Determine target resolution state
        if req.resolution_strategy in {"side_a_authoritative", "side_b_authoritative"}:
            res_state = ConflictResolutionState.SUPERSEDED.value
        elif req.resolution_strategy == "dismissed_false_positive":
            res_state = ConflictResolutionState.DISMISSED.value
        else:
            res_state = ConflictResolutionState.RECONCILED.value

        conf.resolution_state = res_state
        conf.resolution_strategy = req.resolution_strategy
        conf.resolution_notes = req.resolution_notes
        conf.authoritative_claim_text = req.authoritative_claim_text
        conf.resolved_by_user_id = user_id
        conf.resolved_at = utc_now()
        conf.updated_at = utc_now()

        # Update finding claim & status if requested
        if req.sync_finding and conf.case:
            case = conf.case
            if req.authoritative_claim_text:
                case.current_claim = req.authoritative_claim_text
                max_rev = max([r.revision_number for r in case.revisions], default=0)
                self.session.add(
                    VerificationFindingRevision(
                        organisation_id=case.organisation_id,
                        project_id=case.project_id,
                        case_id=case.id,
                        revision_number=max_rev + 1,
                        claim_text=req.authoritative_claim_text,
                        domain=case.domain,
                        is_ai_original=False,
                        edited_by_user_id=user_id,
                        edit_reason=f"Resolved conflict {conf.id}: {req.resolution_strategy}",
                        evidence_snapshot_json={
                            "evidence_item_ids": [str(r.evidence_item_id) for r in case.evidence_refs]
                        },
                    )
                )

            # Check if case has any other open conflicts
            active_states = [
                ConflictResolutionState.UNRESOLVED.value,
                ConflictResolutionState.OPEN.value,
                ConflictResolutionState.UNDER_INVESTIGATION.value,
                ConflictResolutionState.AWAITING_CONTEXT.value,
                ConflictResolutionState.REOPENED.value,
            ]
            other_open = self.session.execute(
                select(VerificationConflict).where(
                    VerificationConflict.case_id == case.id,
                    VerificationConflict.id != conf.id,
                    VerificationConflict.resolution_state.in_(active_states),
                )
            ).scalars().all()

            if not other_open and case.case_status == VerificationCaseStatus.CONFLICTED.value:
                # Case has no more active conflicts! Return to reviewable status
                case.case_status = VerificationCaseStatus.PENDING_REVIEW.value

            # Resolve associated VerificationIssue for conflicting evidence
            conflict_issues = [
                iss for iss in case.issues
                if iss.issue_type == VerificationIssueType.CONFLICTING_SOURCES.value
                and iss.resolution_state == IssueResolutionState.OPEN.value
            ]
            for iss in conflict_issues:
                if not other_open:
                    iss.resolution_state = IssueResolutionState.RESOLVED.value
                    iss.resolution_reason = f"Conflict {conf.id} resolved via {req.resolution_strategy}."
                    iss.resolved_by_user_id = user_id
                    iss.resolved_at = utc_now()

        # Immutable Audit Log
        self.session.add(
            AuditLog(
                organisation_id=conf.organisation_id,
                project_id=conf.project_id,
                actor_user_id=user_id,
                event_type="conflict.resolved",
                resource_type="verification_conflict",
                resource_id=str(conf.id),
                outcome="success",
                event_metadata={
                    "strategy": req.resolution_strategy,
                    "notes": req.resolution_notes,
                    "authoritative_claim": req.authoritative_claim_text,
                    "sync_finding": req.sync_finding,
                },
            )
        )
        self.session.flush()
        return self.get_conflict_details(conf.id, project_id, user_id, has_manage=True)

    def reopen_conflict(
        self,
        conflict_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        reason: str,
    ) -> ConflictDetailResponse:
        """Reopen a previously resolved contradiction."""
        conf = self.repo.get_conflict_by_id(conflict_id, project_id=project_id)
        if not conf:
            raise NotFoundError("Verification conflict not found.")

        conf.resolution_state = ConflictResolutionState.REOPENED.value
        conf.resolved_by_user_id = None
        conf.resolved_at = None
        conf.updated_at = utc_now()

        existing = conf.investigation_notes or ""
        timestamp_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        conf.investigation_notes = f"{existing}\n\n[{timestamp_str}] Reopened by reviewer: {reason}".strip()

        # If finding was approved/verified or unreviewed, flag it as conflicted again
        if conf.case:
            conf.case.case_status = VerificationCaseStatus.CONFLICTED.value

        self.session.add(
            AuditLog(
                organisation_id=conf.organisation_id,
                project_id=conf.project_id,
                actor_user_id=user_id,
                event_type="conflict.reopened",
                resource_type="verification_conflict",
                resource_id=str(conf.id),
                outcome="success",
                event_metadata={"reason": reason},
            )
        )
        self.session.flush()
        return self.get_conflict_details(conf.id, project_id, user_id, has_manage=True)
