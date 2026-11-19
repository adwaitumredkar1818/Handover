"""Handover Checklist Management Service (Stage 5 Complete).

Platform: The Handover
Module: Handover Workspace (Module 4 / Knowledge Transfer Area)

Enforces:
1. Idempotent dynamic checklist generation based on offboarding standards & readiness gaps
2. Item-level tracking (pending, in_progress, completed, skipped, blocked)
3. Participant assignment validation (active project member enforcement)
4. Distinct lifecycle separation: item completion vs independent reviewer verification
5. Audited reopening with mandatory rationale
6. Fail-closed evidence ACL checks & secret redaction on attached evidence/notes
7. Optimistic concurrency (`expected_version`) & immutable PostgreSQL audit trail
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.core.security import utc_now
from app.models.audit import AuditLog
from app.models.enums import (
    AuditOutcome,
    ChecklistItemStatus,
    HandoverChecklistType,
)
from app.models.evidence import EvidenceItem
from app.models.handover import HandoverChecklist, HandoverChecklistItem
from app.models.integration import SourceAccessPolicy
from app.models.project import ProjectMembership
from app.models.user import User
from app.repositories.audit import AuditLogRepository
from app.repositories.handover import (
    HandoverCaseRepository,
    HandoverChecklistRepository,
)
from app.schemas.handover import (
    ChecklistEvidenceSummary,
    ChecklistItemCreateRequest,
    ChecklistItemReviewRequest,
    ChecklistItemUpdateRequest,
    HandoverChecklistItemResponse,
    HandoverChecklistResponse,
    HandoverChecklistWorkspaceResponse,
    HandoverStage5ActivityItem,
)
from app.services.audit import AuditService
from app.services.handover_sections import check_evidence_accessibility, redact_secrets


VALID_CHECKLIST_STATUSES: set[str] = {s.value for s in ChecklistItemStatus}

STANDARD_CHECKLIST_TEMPLATES: dict[str, list[dict[str, Any]]] = {
    HandoverChecklistType.PRE_HANDOVER.value: [
        {
            "item_text": "Verify all critical architecture decisions have supporting evidence and rationale",
            "description": "Confirm that key architectural trade-offs and system boundaries are backed by verified source evidence.",
            "completion_criteria": "All major architecture decisions linked to authorised documents or PRs with reviewer sign-off.",
            "category": "architecture",
            "blocking": True,
            "sort_order": 1,
        },
        {
            "item_text": "Review active bugs, blockers, and open risks with project team",
            "description": "Walk through unresolved defects, technical debt, and operational risks with the receiving team.",
            "completion_criteria": "Open risks and workarounds documented and cross-checked against issue tracker.",
            "category": "risks",
            "blocking": True,
            "sort_order": 2,
        },
        {
            "item_text": "Ensure departing member responsibilities have designated successors",
            "description": "Every active component, service, and operational duty owned by the departing member must map to an eligible project member.",
            "completion_criteria": "All responsibility transfer records assigned and confirmed by outgoing owner.",
            "category": "ownership",
            "blocking": True,
            "sort_order": 3,
        },
        {
            "item_text": "Verify that all connected repositories and Jira boards are up-to-date",
            "description": "Confirm latest commits, pull requests, and issue statuses have been synced into Evidence Center.",
            "completion_criteria": "Recent sync completed with zero pending ingestion errors.",
            "category": "evidence",
            "blocking": False,
            "sort_order": 4,
        },
    ],
    HandoverChecklistType.KNOWLEDGE_TRANSFER.value: [
        {
            "item_text": "Conduct deep-dive architecture walkthrough session with successor",
            "description": "Live walkthrough covering service topology, data flows, failure modes, and key design decisions.",
            "completion_criteria": "Session completed and walkthrough notes or recording link attached.",
            "category": "knowledge_transfer",
            "blocking": True,
            "sort_order": 1,
        },
        {
            "item_text": "Review deployment pipelines, secrets management, and operational runbooks",
            "description": "Cover CI/CD release steps, rollback procedures, monitoring alerts, and incident response playbooks.",
            "completion_criteria": "Operational runbooks reviewed and verified without exposing raw secrets.",
            "category": "operations",
            "blocking": True,
            "sort_order": 2,
        },
        {
            "item_text": "Successor completes dry-run execution of common operational workflows",
            "description": "Hands-on validation of local setup, test suite execution, or staging deployment by incoming successor.",
            "completion_criteria": "Successor confirms ability to execute standard workflows independently.",
            "category": "verification",
            "blocking": False,
            "sort_order": 3,
        },
    ],
    HandoverChecklistType.ACCESS_REVOCATION.value: [
        {
            "item_text": "Audit external source access (GitHub, Jira, Slack) for departing member",
            "description": "Inventory all repository permissions, cloud roles, and integration tokens held by departing member.",
            "completion_criteria": "Access inventory reviewed and revocation schedule confirmed.",
            "category": "security",
            "blocking": True,
            "sort_order": 1,
        },
        {
            "item_text": "Rotate shared API credentials, service accounts, and production secrets",
            "description": "Rotate any shared service credentials or deploy keys that the departing member had access to.",
            "completion_criteria": "Credential rotation completed and verified in production/staging environments.",
            "category": "security",
            "blocking": True,
            "sort_order": 2,
        },
        {
            "item_text": "Confirm project membership role transition or account deactivation",
            "description": "Update project role or schedule offboarding deactivation upon effective handover date.",
            "completion_criteria": "Project administrator confirms membership transition plan.",
            "category": "governance",
            "blocking": False,
            "sort_order": 3,
        },
    ],
}


def _is_overdue(due_date: datetime | None, status: str) -> bool:
    if not due_date or status in (
        ChecklistItemStatus.COMPLETED.value,
        ChecklistItemStatus.SKIPPED.value,
    ):
        return False
    now = utc_now()
    comparable_due = due_date if due_date.tzinfo is not None else due_date.replace(tzinfo=UTC)
    return comparable_due < now


def _recompute_checklist_counters(checklist: HandoverChecklist) -> None:
    items = list(checklist.items or [])
    checklist.total_items = len(items)
    completed_count = sum(
        1 for i in items if i.status == ChecklistItemStatus.COMPLETED.value
    )
    checklist.completed_items = completed_count
    checklist.is_completed = checklist.total_items > 0 and completed_count == checklist.total_items
    checklist.updated_at = utc_now()


class ChecklistService:
    """Domain service for generating, managing, reviewing, and auditing handover checklists."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.case_repo = HandoverCaseRepository(session)
        self.checklist_repo = HandoverChecklistRepository(session)
        self.audit_service = AuditService(audit_repository=AuditLogRepository(session))

    def _validate_active_project_member(self, project_id: uuid.UUID, user_id: uuid.UUID) -> None:
        pm = self.session.execute(
            select(ProjectMembership).where(
                ProjectMembership.project_id == project_id,
                ProjectMembership.user_id == user_id,
            )
        ).scalar_one_or_none()
        if not pm:
            raise BadRequestError(
                "Assigned participant must be a member of this project."
            )
        if pm.status != "active":
            raise BadRequestError(
                f"Assigned participant membership is '{pm.status}', not active."
            )

    def _validate_evidence_in_project(self, project_id: uuid.UUID, evidence_id: uuid.UUID) -> None:
        ev = self.session.execute(
            select(EvidenceItem).where(
                EvidenceItem.id == evidence_id,
                EvidenceItem.project_id == project_id,
                EvidenceItem.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if not ev:
            raise BadRequestError(
                "Supporting evidence item was not found in this project."
            )

    def generate_checklists_for_case(
        self,
        case_id: uuid.UUID,
        *,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        version_id: uuid.UUID | None = None,
        readiness_blockers: list[str] | None = None,
    ) -> list[HandoverChecklist]:
        """Idempotently generate standard pre-handover, knowledge-transfer, and access checklists."""
        case = self.case_repo.get_by_id(case_id, load_relationships=False)
        if not case or case.project_id != project_id:
            raise NotFoundError(f"Handover case {case_id} not found in this project.")

        existing = self.checklist_repo.list_by_case(case.id)
        existing_by_type = {c.checklist_type: c for c in existing}

        created_checklists: list[HandoverChecklist] = []

        for chk_type, items_meta in STANDARD_CHECKLIST_TEMPLATES.items():
            if chk_type in existing_by_type:
                continue

            title = f"{chk_type.replace('_', ' ').title()} Checklist"
            checklist = HandoverChecklist(
                organisation_id=case.organisation_id,
                project_id=project_id,
                case_id=case.id,
                version_id=version_id,
                checklist_type=chk_type,
                title=title,
                total_items=len(items_meta),
                completed_items=0,
                is_completed=False,
            )
            created_chk = self.checklist_repo.create(checklist)

            items_to_add: list[HandoverChecklistItem] = []
            for item in items_meta:
                items_to_add.append(
                    HandoverChecklistItem(
                        organisation_id=case.organisation_id,
                        project_id=project_id,
                        checklist_id=created_chk.id,
                        item_text=item["item_text"],
                        description=item.get("description"),
                        completion_criteria=item.get("completion_criteria"),
                        category=item["category"],
                        status=ChecklistItemStatus.PENDING.value,
                        blocking=item["blocking"],
                        sort_order=item["sort_order"],
                        assigned_to_user_id=(
                            case.departing_member_id
                            if "departing" in item["item_text"]
                            else case.successor_id
                        ),
                    )
                )

            if chk_type == HandoverChecklistType.PRE_HANDOVER.value and readiness_blockers:
                for idx, blocker in enumerate(readiness_blockers, start=len(items_to_add) + 1):
                    items_to_add.append(
                        HandoverChecklistItem(
                            organisation_id=case.organisation_id,
                            project_id=project_id,
                            checklist_id=created_chk.id,
                            item_text=f"Resolve Blocker: {blocker}",
                            description="Automatically tracked readiness remediation item.",
                            completion_criteria="Underlying readiness blocker resolved and verified via reassessment.",
                            category="remediation",
                            status=ChecklistItemStatus.PENDING.value,
                            blocking=True,
                            sort_order=idx,
                        )
                    )
                created_chk.total_items = len(items_to_add)

            self.checklist_repo.create_items_bulk(items_to_add)
            created_checklists.append(created_chk)

        if created_checklists:
            self.audit_service.record_event(
                event_type="handover.checklists.generated",
                resource_type="handover_case",
                resource_id=str(case.id),
                actor_user_id=user_id,
                organisation_id=case.organisation_id,
                project_id=project_id,
                outcome=AuditOutcome.SUCCESS.value,
                metadata={"checklists_count": len(created_checklists)},
            )

        return self.checklist_repo.list_by_case(case.id)

    def create_item(
        self,
        case_id: uuid.UUID,
        checklist_id: uuid.UUID,
        *,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        request: ChecklistItemCreateRequest,
    ) -> HandoverChecklistItem:
        """Add a custom transition checklist item with strict project & participant validation."""
        checklist = self.checklist_repo.get_by_id(checklist_id, load_items=True)
        if not checklist or checklist.project_id != project_id or checklist.case_id != case_id:
            raise NotFoundError(
                f"Checklist {checklist_id} not found for handover case {case_id} in this project."
            )

        if request.assigned_to_user_id is not None:
            self._validate_active_project_member(project_id, request.assigned_to_user_id)
        if request.evidence_item_id is not None:
            self._validate_evidence_in_project(project_id, request.evidence_item_id)

        next_order = max((i.sort_order for i in checklist.items), default=0) + 1
        item = HandoverChecklistItem(
            organisation_id=checklist.organisation_id,
            project_id=project_id,
            checklist_id=checklist.id,
            item_text=request.item_text.strip(),
            description=request.description.strip() if request.description else None,
            completion_criteria=(
                request.completion_criteria.strip() if request.completion_criteria else None
            ),
            category=request.category or "general",
            status=ChecklistItemStatus.PENDING.value,
            blocking=request.blocking,
            sort_order=next_order,
            assigned_to_user_id=request.assigned_to_user_id,
            due_date=request.due_date,
            evidence_item_id=request.evidence_item_id,
            version=1,
        )
        self.checklist_repo.create_item(item)
        checklist.items.append(item)
        _recompute_checklist_counters(checklist)
        self.session.flush()

        self.audit_service.record_event(
            event_type="handover.checklist_item.created",
            resource_type="handover_checklist_item",
            resource_id=str(item.id),
            actor_user_id=user_id,
            organisation_id=checklist.organisation_id,
            project_id=project_id,
            outcome=AuditOutcome.SUCCESS.value,
            metadata={
                "case_id": str(case_id),
                "checklist_id": str(checklist.id),
                "blocking": item.blocking,
                "category": item.category,
            },
        )
        return item

    def update_item_status(
        self,
        item_id: uuid.UUID,
        *,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        request: ChecklistItemUpdateRequest,
    ) -> HandoverChecklistItem:
        """Update checklist item status, assignment, due date, evidence, notes, or reopen with audit."""
        item = self.checklist_repo.get_item_by_id(item_id)
        if not item or item.project_id != project_id:
            raise NotFoundError(f"Checklist item {item_id} not found in this project.")

        checklist = self.checklist_repo.get_by_id(item.checklist_id, load_items=True)
        if not checklist or checklist.project_id != project_id:
            raise NotFoundError(f"Parent checklist for item {item_id} not found in this project.")

        # Optimistic concurrency guard
        if request.expected_version is not None and item.version != request.expected_version:
            raise ConflictError(
                f"Checklist item was modified concurrently (expected version {request.expected_version}, "
                f"current version {item.version}). Refresh and retry."
            )

        previous_status = item.status
        event_type = "handover.checklist_item.updated"

        # Validate & apply status transition
        if request.status is not None:
            if request.status not in VALID_CHECKLIST_STATUSES:
                raise BadRequestError(
                    f"Invalid checklist status '{request.status}'. "
                    f"Must be one of: {', '.join(sorted(VALID_CHECKLIST_STATUSES))}."
                )

            # Reopening a previously completed item requires explicit rationale
            if (
                previous_status == ChecklistItemStatus.COMPLETED.value
                and request.status != ChecklistItemStatus.COMPLETED.value
            ):
                reason = (request.reopen_reason or request.notes or "").strip()
                if len(reason) < 3:
                    raise BadRequestError(
                        "Reopening a completed checklist item requires a documented reason (at least 3 characters)."
                    )
                item.status = request.status
                item.completed_at = None
                item.completed_by_user_id = None
                item.reviewed_at = None
                item.reviewed_by_user_id = None
                item.review_notes = None
                item.reopened_count = (item.reopened_count or 0) + 1
                item.reopened_by_user_id = user_id
                item.reopened_at = utc_now()
                item.reopened_reason = reason
                event_type = "handover.checklist_item.reopened"
            elif request.status == ChecklistItemStatus.COMPLETED.value:
                if previous_status != ChecklistItemStatus.COMPLETED.value:
                    item.completed_at = utc_now()
                    item.completed_by_user_id = user_id
                item.status = ChecklistItemStatus.COMPLETED.value
                event_type = "handover.checklist_item.completed"
            else:
                item.status = request.status

        # Validate & apply participant assignment
        if request.clear_assignee:
            item.assigned_to_user_id = None
        elif request.assigned_to_user_id is not None:
            self._validate_active_project_member(project_id, request.assigned_to_user_id)
            item.assigned_to_user_id = request.assigned_to_user_id

        # Validate & apply evidence attachment
        if request.clear_evidence:
            item.evidence_item_id = None
        elif request.evidence_item_id is not None:
            self._validate_evidence_in_project(project_id, request.evidence_item_id)
            item.evidence_item_id = request.evidence_item_id

        # Apply due date, notes, criteria, blocking
        if request.clear_due_date:
            item.due_date = None
        elif request.due_date is not None:
            item.due_date = request.due_date

        if request.notes is not None:
            item.notes = request.notes
        if request.description is not None:
            item.description = request.description
        if request.completion_criteria is not None:
            item.completion_criteria = request.completion_criteria
        if request.blocking is not None:
            item.blocking = request.blocking

        item.version = (item.version or 1) + 1
        item.updated_at = utc_now()
        _recompute_checklist_counters(checklist)
        self.session.flush()

        self.audit_service.record_event(
            event_type=event_type,
            resource_type="handover_checklist_item",
            resource_id=str(item.id),
            actor_user_id=user_id,
            organisation_id=item.organisation_id,
            project_id=project_id,
            outcome=AuditOutcome.SUCCESS.value,
            metadata={
                "case_id": str(checklist.case_id),
                "checklist_id": str(checklist.id),
                "previous_status": previous_status,
                "status": item.status,
                "assigned_to_user_id": str(item.assigned_to_user_id) if item.assigned_to_user_id else None,
                "reopen_reason": item.reopened_reason if event_type == "handover.checklist_item.reopened" else None,
                "version": item.version,
            },
        )
        return item

    def review_item(
        self,
        item_id: uuid.UUID,
        *,
        project_id: uuid.UUID,
        reviewer_user_id: uuid.UUID,
        request: ChecklistItemReviewRequest,
        is_org_admin: bool = False,
    ) -> HandoverChecklistItem:
        """Record independent reviewer verification or reject/reopen a completed checklist item."""
        item = self.checklist_repo.get_item_by_id(item_id)
        if not item or item.project_id != project_id:
            raise NotFoundError(f"Checklist item {item_id} not found in this project.")

        checklist = self.checklist_repo.get_by_id(item.checklist_id, load_items=True)
        if not checklist or checklist.project_id != project_id:
            raise NotFoundError(f"Parent checklist for item {item_id} not found in this project.")

        if request.expected_version is not None and item.version != request.expected_version:
            raise ConflictError(
                f"Checklist item version conflict (expected {request.expected_version}, got {item.version})."
            )

        if item.status != ChecklistItemStatus.COMPLETED.value:
            raise BadRequestError(
                "Only completed checklist items can be verified by a reviewer."
            )

        if item.completed_by_user_id == reviewer_user_id and not is_org_admin:
            raise ForbiddenError(
                "Separation of duties: the participant who completed a checklist item cannot independently verify it."
            )

        if request.approved:
            item.reviewed_by_user_id = reviewer_user_id
            item.reviewed_at = utc_now()
            item.review_notes = request.review_notes
            event_type = "handover.checklist_item.reviewed"
        else:
            reason = (request.review_notes or "").strip()
            if len(reason) < 3:
                raise BadRequestError(
                    "Rejecting/reopening a completed checklist item during review requires review notes."
                )
            item.status = ChecklistItemStatus.IN_PROGRESS.value
            item.completed_at = None
            item.completed_by_user_id = None
            item.reviewed_by_user_id = None
            item.reviewed_at = None
            item.review_notes = None
            item.reopened_count = (item.reopened_count or 0) + 1
            item.reopened_by_user_id = reviewer_user_id
            item.reopened_at = utc_now()
            item.reopened_reason = reason
            event_type = "handover.checklist_item.reopened"

        item.version = (item.version or 1) + 1
        item.updated_at = utc_now()
        _recompute_checklist_counters(checklist)
        self.session.flush()

        self.audit_service.record_event(
            event_type=event_type,
            resource_type="handover_checklist_item",
            resource_id=str(item.id),
            actor_user_id=reviewer_user_id,
            organisation_id=item.organisation_id,
            project_id=project_id,
            outcome=AuditOutcome.SUCCESS.value,
            metadata={
                "case_id": str(checklist.case_id),
                "approved": request.approved,
                "review_notes": request.review_notes,
                "version": item.version,
            },
        )
        return item

    def list_checklists(
        self, case_id: uuid.UUID, *, project_id: uuid.UUID
    ) -> list[HandoverChecklist]:
        """List all checklists and items for a case."""
        case = self.case_repo.get_by_id(case_id, load_relationships=False)
        if not case or case.project_id != project_id:
            raise NotFoundError(f"Handover case {case_id} not found in this project.")
        return self.checklist_repo.list_by_case(case_id)

    def hydrate_item_response(
        self,
        item: HandoverChecklistItem,
        *,
        project_id: uuid.UUID,
        viewer_user_id: uuid.UUID,
        has_project_manage: bool = False,
        users_by_id: dict[uuid.UUID, User] | None = None,
        evidences_by_id: dict[uuid.UUID, EvidenceItem] | None = None,
        inaccessible_ev_ids: set[uuid.UUID] | None = None,
    ) -> HandoverChecklistItemResponse:
        """Build an ACL-checked, redacted response model for a single checklist item."""
        if users_by_id is None:
            uids = {
                u
                for u in (
                    item.assigned_to_user_id,
                    item.completed_by_user_id,
                    item.reviewed_by_user_id,
                    item.reopened_by_user_id,
                )
                if u
            }
            users_by_id = (
                {
                    u.id: u
                    for u in self.session.execute(select(User).where(User.id.in_(uids)))
                    .scalars()
                    .all()
                }
                if uids
                else {}
            )

        ev_summary: ChecklistEvidenceSummary | None = None
        if item.evidence_item_id:
            if evidences_by_id is None or inaccessible_ev_ids is None:
                cached_policies = list(
                    self.session.execute(
                        select(SourceAccessPolicy).where(
                            SourceAccessPolicy.project_id == project_id
                        )
                    )
                    .scalars()
                    .all()
                )
                _, denied_ids = check_evidence_accessibility(
                    self.session,
                    [item.evidence_item_id],
                    project_id=project_id,
                    viewer_user_id=viewer_user_id,
                    has_project_manage=has_project_manage,
                    cached_policies=cached_policies,
                )
                inaccessible_ev_ids = set(denied_ids)
                ev_obj = self.session.get(EvidenceItem, item.evidence_item_id)
                evidences_by_id = {ev_obj.id: ev_obj} if ev_obj else {}

            is_restricted = item.evidence_item_id in inaccessible_ev_ids
            ev_obj = evidences_by_id.get(item.evidence_item_id)
            if is_restricted:
                ev_summary = ChecklistEvidenceSummary(
                    evidence_id=item.evidence_item_id,
                    title="Restricted Source (ACL Protected)",
                    source_type=ev_obj.source_type if ev_obj else None,
                    source_url=None,
                    acl_restricted=True,
                )
            elif ev_obj:
                ev_summary = ChecklistEvidenceSummary(
                    evidence_id=ev_obj.id,
                    title=redact_secrets(ev_obj.title),
                    source_type=ev_obj.source_type,
                    source_url=ev_obj.source_url,
                    acl_restricted=False,
                )

        def _uname(uid: uuid.UUID | None) -> str | None:
            if not uid or uid not in users_by_id:
                return None
            u = users_by_id[uid]
            return u.full_name or u.email

        return HandoverChecklistItemResponse(
            id=item.id,
            checklist_id=item.checklist_id,
            item_text=redact_secrets(item.item_text),
            description=redact_secrets(item.description) if item.description else None,
            completion_criteria=(
                redact_secrets(item.completion_criteria) if item.completion_criteria else None
            ),
            status=item.status,
            blocking=bool(item.blocking),
            category=item.category,
            assigned_to_user_id=item.assigned_to_user_id,
            assigned_to_name=_uname(item.assigned_to_user_id),
            due_date=item.due_date,
            is_overdue=_is_overdue(item.due_date, item.status),
            notes=redact_secrets(item.notes) if item.notes else None,
            evidence_item_id=item.evidence_item_id,
            evidence_summary=ev_summary,
            completed_by_user_id=item.completed_by_user_id,
            completed_by_name=_uname(item.completed_by_user_id),
            completed_at=item.completed_at,
            reviewed_by_user_id=item.reviewed_by_user_id,
            reviewed_by_name=_uname(item.reviewed_by_user_id),
            reviewed_at=item.reviewed_at,
            review_notes=redact_secrets(item.review_notes) if item.review_notes else None,
            reopened_count=item.reopened_count or 0,
            reopened_by_user_id=item.reopened_by_user_id,
            reopened_by_name=_uname(item.reopened_by_user_id),
            reopened_at=item.reopened_at,
            reopened_reason=redact_secrets(item.reopened_reason) if item.reopened_reason else None,
            version=item.version or 1,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )

    def get_checklist_workspace(
        self,
        case_id: uuid.UUID,
        *,
        project_id: uuid.UUID,
        viewer_user_id: uuid.UUID,
        has_project_manage: bool = False,
    ) -> HandoverChecklistWorkspaceResponse:
        """Return full hydrated Stage 5 checklist workspace with counts, ACL-safe evidence, and audit log."""
        case = self.case_repo.get_by_id(case_id, load_relationships=False)
        if not case or case.project_id != project_id:
            raise NotFoundError(f"Handover case {case_id} not found in this project.")

        checklists = self.checklist_repo.list_by_case(case.id)
        all_items = [it for chk in checklists for it in (chk.items or [])]

        # Batch load users & ACL-checked evidences
        user_ids: set[uuid.UUID] = set()
        evidence_ids: set[uuid.UUID] = set()
        item_ids_str: set[str] = set()
        for it in all_items:
            item_ids_str.add(str(it.id))
            for uid in (
                it.assigned_to_user_id,
                it.completed_by_user_id,
                it.reviewed_by_user_id,
                it.reopened_by_user_id,
            ):
                if uid:
                    user_ids.add(uid)
            if it.evidence_item_id:
                evidence_ids.add(it.evidence_item_id)

        # Fetch checklist audit events for this project & case/items
        audit_logs = list(
            self.session.execute(
                select(AuditLog)
                .where(
                    AuditLog.project_id == project_id,
                    AuditLog.event_type.like("handover.checklist%"),
                )
                .order_by(AuditLog.created_at.desc())
                .limit(60)
            )
            .scalars()
            .all()
        )
        filtered_audits: list[AuditLog] = []
        case_id_str = str(case.id)
        for log in audit_logs:
            meta = log.event_metadata or {}
            if (
                log.resource_id == case_id_str
                or log.resource_id in item_ids_str
                or meta.get("case_id") == case_id_str
            ):
                filtered_audits.append(log)
                if log.actor_user_id:
                    user_ids.add(log.actor_user_id)

        users_by_id: dict[uuid.UUID, User] = (
            {
                u.id: u
                for u in self.session.execute(select(User).where(User.id.in_(user_ids)))
                .scalars()
                .all()
            }
            if user_ids
            else {}
        )

        evidences_by_id: dict[uuid.UUID, EvidenceItem] = {}
        inaccessible_ev_ids: set[uuid.UUID] = set()
        if evidence_ids:
            evidences_by_id = {
                ev.id: ev
                for ev in self.session.execute(
                    select(EvidenceItem).where(EvidenceItem.id.in_(evidence_ids))
                )
                .scalars()
                .all()
            }
            cached_policies = list(
                self.session.execute(
                    select(SourceAccessPolicy).where(SourceAccessPolicy.project_id == project_id)
                )
                .scalars()
                .all()
            )
            _, denied = check_evidence_accessibility(
                self.session,
                list(evidence_ids),
                project_id=project_id,
                viewer_user_id=viewer_user_id,
                has_project_manage=has_project_manage,
                cached_policies=cached_policies,
            )
            inaccessible_ev_ids = set(denied)

        chk_responses: list[HandoverChecklistResponse] = []
        total_items = 0
        completed_items = 0
        blocked_items = 0
        overdue_items = 0
        mandatory_total = 0
        mandatory_completed = 0
        optional_total = 0
        optional_completed = 0

        for chk in checklists:
            hydrated_items = [
                self.hydrate_item_response(
                    it,
                    project_id=project_id,
                    viewer_user_id=viewer_user_id,
                    has_project_manage=has_project_manage,
                    users_by_id=users_by_id,
                    evidences_by_id=evidences_by_id,
                    inaccessible_ev_ids=inaccessible_ev_ids,
                )
                for it in (chk.items or [])
            ]
            c_tot = len(hydrated_items)
            c_done = sum(1 for i in hydrated_items if i.status == ChecklistItemStatus.COMPLETED.value)
            c_blk = sum(1 for i in hydrated_items if i.status == ChecklistItemStatus.BLOCKED.value)
            c_ovr = sum(1 for i in hydrated_items if i.is_overdue)
            c_m_tot = sum(1 for i in hydrated_items if i.blocking)
            c_m_done = sum(
                1
                for i in hydrated_items
                if i.blocking and i.status == ChecklistItemStatus.COMPLETED.value
            )
            c_o_tot = c_tot - c_m_tot
            c_o_done = c_done - c_m_done

            total_items += c_tot
            completed_items += c_done
            blocked_items += c_blk
            overdue_items += c_ovr
            mandatory_total += c_m_tot
            mandatory_completed += c_m_done
            optional_total += c_o_tot
            optional_completed += c_o_done

            chk_responses.append(
                HandoverChecklistResponse(
                    id=chk.id,
                    case_id=chk.case_id,
                    generated_for_version_id=chk.version_id,
                    checklist_type=chk.checklist_type,
                    title=chk.title,
                    description=chk.description,
                    total_items=c_tot,
                    completed_items=c_done,
                    mandatory_total=c_m_tot,
                    mandatory_completed=c_m_done,
                    mandatory_outstanding=max(0, c_m_tot - c_m_done),
                    blocked_items=c_blk,
                    overdue_items=c_ovr,
                    is_completed=c_tot > 0 and c_done == c_tot,
                    created_at=chk.created_at,
                    items=hydrated_items,
                )
            )

        activity_history: list[HandoverStage5ActivityItem] = []
        for log in filtered_audits[:30]:
            actor = users_by_id.get(log.actor_user_id) if log.actor_user_id else None
            meta = log.event_metadata or {}
            summary = _summarize_checklist_audit(log.event_type, meta)
            activity_history.append(
                HandoverStage5ActivityItem(
                    id=log.id,
                    event_type=log.event_type,
                    resource_type=log.resource_type,
                    resource_id=log.resource_id,
                    actor_user_id=log.actor_user_id,
                    actor_name=(actor.full_name or actor.email) if actor else None,
                    outcome=log.outcome,
                    summary=summary,
                    metadata_json=meta,
                    created_at=log.created_at,
                )
            )

        return HandoverChecklistWorkspaceResponse(
            case_id=case.id,
            project_id=project_id,
            total_checklists=len(chk_responses),
            total_items=total_items,
            completed_items=completed_items,
            outstanding_items=max(0, total_items - completed_items),
            blocked_items=blocked_items,
            overdue_items=overdue_items,
            mandatory_total=mandatory_total,
            mandatory_completed=mandatory_completed,
            mandatory_outstanding=max(0, mandatory_total - mandatory_completed),
            optional_total=optional_total,
            optional_completed=optional_completed,
            completion_pct=int((completed_items / total_items) * 100) if total_items > 0 else 0,
            checklists=chk_responses,
            activity_history=activity_history,
        )


def _summarize_checklist_audit(event_type: str, meta: dict[str, Any]) -> str:
    if event_type == "handover.checklists.generated":
        return f"Generated {meta.get('checklists_count', 0)} standard transition checklists."
    if event_type == "handover.checklist_item.created":
        return f"Added custom checklist item ({meta.get('category', 'general')})."
    if event_type == "handover.checklist_item.completed":
        return "Marked checklist item completed."
    if event_type == "handover.checklist_item.reopened":
        reason = meta.get("reopen_reason") or meta.get("review_notes") or ""
        return f"Reopened checklist item{f': {reason}' if reason else '.'}"
    if event_type == "handover.checklist_item.reviewed":
        return "Reviewer verified completed checklist item."
    status = meta.get("status")
    return f"Updated checklist item{f' (status: {status})' if status else '.'}"
