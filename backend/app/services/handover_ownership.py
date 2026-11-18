"""Handover Responsibility Mapping & Ownership Transfer Service (Stage 5 Complete).

Platform: The Handover
Module: Handover Workspace (Module 4 / Knowledge Transfer Area)

Enforces:
1. Strict separation between Package Compilation, Responsibility Transfer, and Final Approval
2. Project member & active-participant validation (rejects inactive/non-members & self-transfer)
3. Explicit Stage 5 lifecycle:
   pending -> prepared -> awaiting_outgoing_confirmation ->
   awaiting_successor_acknowledgement -> acknowledged (with clarification_requested, blocked, reopened)
4. Strict separation of duties:
   - Outgoing-owner confirmation by departing owner (or project manager/admin)
   - Successor acknowledgement STRICTLY by assigned successor (cannot be forged)
   - Clarification requests & responses audited cleanly
5. Canonical 8-domain knowledge & fail-closed ACL-checked evidence hydration
6. Real unmapped responsibility candidate discovery (never auto-promoted to verified)
7. Optimistic concurrency (`expected_version`) & immutable PostgreSQL audit trail
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.core.security import utc_now
from app.models.audit import AuditLog
from app.models.enums import (
    AuditOutcome,
    EpistemicStatus,
    HandoverCaseStatus,
    KnowledgeCategory,
    KnowledgeReviewStatus,
    TransferStatus,
)
from app.models.evidence import EvidenceItem
from app.models.handover import (
    HandoverOwnershipTransfer,
    HandoverResponsibilityTransfer,
)
from app.models.integration import SourceAccessPolicy
from app.models.knowledge import KnowledgeEvidenceLink, KnowledgeItem
from app.models.project import ProjectMembership
from app.models.rbac import Role
from app.models.relationship import KnowledgeEntity
from app.models.user import User
from app.repositories.audit import AuditLogRepository
from app.repositories.handover import (
    HandoverCaseRepository,
    HandoverOwnershipTransferRepository,
    HandoverPackageVersionRepository,
    HandoverResponsibilityTransferRepository,
)
from app.schemas.handover import (
    HandoverResponsibilityTransferResponse,
    HandoverResponsibilityWorkspaceResponse,
    HandoverStage5ActivityItem,
    OwnershipTransferRequest,
    OwnershipTransferRollbackRequest,
    ResponsibilityCandidateItem,
    ResponsibilityClarificationRequest,
    ResponsibilityEvidenceRef,
    ResponsibilityKnowledgeContextItem,
    ResponsibilityOutgoingConfirmRequest,
    ResponsibilityOwnershipValidationIssue,
    ResponsibilityParticipantSummary,
    ResponsibilityReopenRequest,
    ResponsibilitySuccessorAckRequest,
    ResponsibilityTransferBulkRequest,
    ResponsibilityTransferUpdateRequest,
)
from app.services.audit import AuditService
from app.services.handover_case import HandoverCaseService
from app.services.handover_sections import check_evidence_accessibility, redact_secrets


VALID_TRANSFER_STATUSES: set[str] = {s.value for s in TransferStatus}
VALID_PRIORITIES: set[str] = {"critical", "high", "medium", "low"}
VALID_CERTAINTIES: set[str] = {"confirmed", "proposed", "uncertain"}

# Statuses that cannot be set directly through a generic PATCH without calling
# their dedicated separation-of-duties endpoints
DIRECT_EDIT_FORBIDDEN_STATUSES: set[str] = {
    TransferStatus.ACKNOWLEDGED.value,
    TransferStatus.COMPLETED.value,
}


class OwnershipTransferService:
    """Manages responsibility mappings, Stage 5 transfer governance, and ownership transfers."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.case_repo = HandoverCaseRepository(session)
        self.version_repo = HandoverPackageVersionRepository(session)
        self.resp_repo = HandoverResponsibilityTransferRepository(session)
        self.ownership_repo = HandoverOwnershipTransferRepository(session)
        self.case_service = HandoverCaseService(session)
        self.audit_service = AuditService(audit_repository=AuditLogRepository(session))

    def _get_project_membership_map(
        self, project_id: uuid.UUID
    ) -> dict[uuid.UUID, tuple[ProjectMembership, User, Role | None]]:
        rows = self.session.execute(
            select(ProjectMembership, User, Role)
            .join(User, User.id == ProjectMembership.user_id)
            .outerjoin(Role, Role.id == ProjectMembership.role_id)
            .where(ProjectMembership.project_id == project_id)
        ).all()
        return {pm.user_id: (pm, u, role) for pm, u, role in rows}

    def _validate_active_successor(
        self,
        *,
        project_id: uuid.UUID,
        current_owner_id: uuid.UUID,
        proposed_successor_id: uuid.UUID,
        membership_map: dict[uuid.UUID, tuple[ProjectMembership, User, Role | None]] | None = None,
    ) -> None:
        if proposed_successor_id == current_owner_id:
            raise BadRequestError(
                "Proposed successor cannot be the same user as the current outgoing owner."
            )
        m_map = membership_map if membership_map is not None else self._get_project_membership_map(project_id)
        entry = m_map.get(proposed_successor_id)
        if not entry:
            raise BadRequestError(
                "Proposed successor must be a member of this project."
            )
        pm, user, _ = entry
        if pm.status != "active":
            raise BadRequestError(
                f"Proposed successor membership is '{pm.status}', not active."
            )
        if getattr(user, "status", "active") != "active":
            raise BadRequestError(
                f"Proposed successor user account is '{user.status}', not active."
            )

    def _validate_project_links(
        self,
        *,
        project_id: uuid.UUID,
        related_entity_id: uuid.UUID | None,
        related_knowledge_item_id: uuid.UUID | None,
    ) -> None:
        if related_entity_id is not None:
            ent = self.session.get(KnowledgeEntity, related_entity_id)
            if not ent or ent.project_id != project_id:
                raise BadRequestError("Related component/entity was not found in this project.")
        if related_knowledge_item_id is not None:
            ki = self.session.get(KnowledgeItem, related_knowledge_item_id)
            if not ki or ki.project_id != project_id or ki.is_deleted:
                raise BadRequestError("Related knowledge item was not found in this project.")

    def create_responsibility_transfers(
        self,
        case_id: uuid.UUID,
        *,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        request: ResponsibilityTransferBulkRequest,
    ) -> list[HandoverResponsibilityTransfer]:
        """Create validated responsibility transfer records mapped from departing owner to successor."""
        case = self.case_service.get_case(case_id, project_id=project_id, load_relationships=False)
        m_map = self._get_project_membership_map(project_id)

        records_to_create: list[HandoverResponsibilityTransfer] = []
        for req in request.transfers:
            owner_id = req.current_owner_id or case.departing_member_id
            if owner_id not in m_map:
                raise BadRequestError("Current owner must be a member of this project.")

            successor_id = (
                req.proposed_successor_id
                if req.proposed_successor_id is not None
                else case.successor_id
            )
            if successor_id is not None:
                self._validate_active_successor(
                    project_id=project_id,
                    current_owner_id=owner_id,
                    proposed_successor_id=successor_id,
                    membership_map=m_map,
                )

            priority = (req.priority or "medium").lower()
            if priority not in VALID_PRIORITIES:
                raise BadRequestError(f"Invalid priority '{priority}'.")
            certainty = (req.ownership_certainty or "proposed").lower()
            if certainty not in VALID_CERTAINTIES:
                raise BadRequestError(f"Invalid ownership certainty '{certainty}'.")

            self._validate_project_links(
                project_id=project_id,
                related_entity_id=req.related_entity_id,
                related_knowledge_item_id=req.related_knowledge_item_id,
            )

            records_to_create.append(
                HandoverResponsibilityTransfer(
                    organisation_id=case.organisation_id,
                    project_id=project_id,
                    case_id=case.id,
                    title=req.title.strip() if req.title else None,
                    responsibility_description=req.responsibility_description.strip(),
                    knowledge_domain=req.knowledge_domain or "responsibilities_ownership",
                    component_name=req.component_name.strip() if req.component_name else None,
                    priority=priority,
                    ownership_certainty=certainty,
                    operational_context=(
                        req.operational_context.strip() if req.operational_context else None
                    ),
                    required_access=req.required_access.strip() if req.required_access else None,
                    effective_transfer_date=req.effective_transfer_date,
                    current_owner_id=owner_id,
                    proposed_successor_id=successor_id,
                    transfer_status=(
                        TransferStatus.PREPARED.value
                        if successor_id is not None
                        else TransferStatus.PENDING.value
                    ),
                    transfer_notes=req.transfer_notes,
                    related_entity_id=req.related_entity_id,
                    related_knowledge_item_id=req.related_knowledge_item_id,
                    version=1,
                )
            )

        created = self.resp_repo.create_bulk(records_to_create)

        self.audit_service.record_event(
            event_type="handover.responsibilities.created",
            resource_type="handover_case",
            resource_id=str(case.id),
            actor_user_id=user_id,
            organisation_id=case.organisation_id,
            project_id=project_id,
            outcome=AuditOutcome.SUCCESS.value,
            metadata={
                "case_id": str(case.id),
                "count": len(created),
                "transfer_ids": [str(t.id) for t in created],
            },
        )
        return created

    def list_responsibility_transfers(
        self, case_id: uuid.UUID, *, project_id: uuid.UUID
    ) -> list[HandoverResponsibilityTransfer]:
        """List mapped responsibilities for a case."""
        case = self.case_service.get_case(case_id, project_id=project_id, load_relationships=False)
        return self.resp_repo.list_by_case(case.id)

    def update_responsibility_transfer(
        self,
        transfer_id: uuid.UUID,
        *,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        request: ResponsibilityTransferUpdateRequest,
    ) -> HandoverResponsibilityTransfer:
        """Update responsibility details, reassign eligible successor, or update operational status."""
        transfer = self.session.get(HandoverResponsibilityTransfer, transfer_id)
        if not transfer or transfer.project_id != project_id:
            raise NotFoundError(f"Responsibility transfer {transfer_id} not found in this project.")

        if request.expected_version is not None and transfer.version != request.expected_version:
            raise ConflictError(
                f"Responsibility transfer was modified concurrently (expected version {request.expected_version}, "
                f"current version {transfer.version}). Refresh and retry."
            )

        previous_successor_id = transfer.proposed_successor_id
        previous_status = transfer.transfer_status

        if request.clear_successor:
            transfer.proposed_successor_id = None
            transfer.successor_acknowledged_by_user_id = None
            transfer.successor_acknowledged_at = None
            transfer.successor_acknowledgement_notes = None
            if transfer.transfer_status in (
                TransferStatus.AWAITING_SUCCESSOR_ACKNOWLEDGEMENT.value,
                TransferStatus.ACKNOWLEDGED.value,
            ):
                transfer.transfer_status = TransferStatus.PENDING.value
        elif request.proposed_successor_id is not None:
            self._validate_active_successor(
                project_id=project_id,
                current_owner_id=transfer.current_owner_id,
                proposed_successor_id=request.proposed_successor_id,
            )
            if request.proposed_successor_id != transfer.proposed_successor_id:
                transfer.proposed_successor_id = request.proposed_successor_id
                # Reassignment invalidates any prior successor acknowledgement!
                transfer.successor_acknowledged_by_user_id = None
                transfer.successor_acknowledged_at = None
                transfer.successor_acknowledgement_notes = None
                if transfer.transfer_status == TransferStatus.ACKNOWLEDGED.value:
                    transfer.transfer_status = (
                        TransferStatus.AWAITING_SUCCESSOR_ACKNOWLEDGEMENT.value
                        if transfer.outgoing_confirmed_at
                        else TransferStatus.PREPARED.value
                    )
                elif transfer.transfer_status == TransferStatus.PENDING.value:
                    transfer.transfer_status = TransferStatus.PREPARED.value

        if request.priority is not None:
            prio = request.priority.lower()
            if prio not in VALID_PRIORITIES:
                raise BadRequestError(f"Invalid priority '{prio}'.")
            transfer.priority = prio

        if request.ownership_certainty is not None:
            cert = request.ownership_certainty.lower()
            if cert not in VALID_CERTAINTIES:
                raise BadRequestError(f"Invalid ownership certainty '{cert}'.")
            transfer.ownership_certainty = cert

        if request.related_entity_id is not None or request.related_knowledge_item_id is not None:
            self._validate_project_links(
                project_id=project_id,
                related_entity_id=request.related_entity_id,
                related_knowledge_item_id=request.related_knowledge_item_id,
            )
            if request.related_entity_id is not None:
                transfer.related_entity_id = request.related_entity_id
            if request.related_knowledge_item_id is not None:
                transfer.related_knowledge_item_id = request.related_knowledge_item_id

        if request.title is not None:
            transfer.title = request.title.strip() or None
        if request.responsibility_description is not None:
            transfer.responsibility_description = request.responsibility_description.strip()
        if request.knowledge_domain is not None:
            transfer.knowledge_domain = request.knowledge_domain
        if request.component_name is not None:
            transfer.component_name = request.component_name.strip() or None
        if request.operational_context is not None:
            transfer.operational_context = request.operational_context.strip() or None
        if request.required_access is not None:
            transfer.required_access = request.required_access.strip() or None
        if request.clear_effective_date:
            transfer.effective_transfer_date = None
        elif request.effective_transfer_date is not None:
            transfer.effective_transfer_date = request.effective_transfer_date
        if request.transfer_notes is not None:
            transfer.transfer_notes = request.transfer_notes
        if request.blocker_reason is not None:
            transfer.blocker_reason = request.blocker_reason.strip() or None

        if request.transfer_status is not None:
            if request.transfer_status not in VALID_TRANSFER_STATUSES:
                raise BadRequestError(f"Invalid transfer status '{request.transfer_status}'.")
            if request.transfer_status in DIRECT_EDIT_FORBIDDEN_STATUSES:
                raise BadRequestError(
                    f"Cannot set transfer status to '{request.transfer_status}' directly; "
                    "use the dedicated acknowledgement or ownership execution endpoint."
                )
            if (
                request.transfer_status == TransferStatus.BLOCKED.value
                and not (transfer.blocker_reason or request.transfer_notes)
            ):
                raise BadRequestError(
                    "Marking a responsibility transfer as blocked requires a blocker reason or note."
                )
            transfer.transfer_status = request.transfer_status

        transfer.version = (transfer.version or 1) + 1
        transfer.updated_at = utc_now()
        self.session.flush()

        reassigned = previous_successor_id != transfer.proposed_successor_id
        self.audit_service.record_event(
            event_type=(
                "handover.responsibility.reassigned"
                if reassigned
                else "handover.responsibility.updated"
            ),
            resource_type="handover_responsibility_transfer",
            resource_id=str(transfer.id),
            actor_user_id=user_id,
            organisation_id=transfer.organisation_id,
            project_id=project_id,
            outcome=AuditOutcome.SUCCESS.value,
            metadata={
                "case_id": str(transfer.case_id),
                "previous_status": previous_status,
                "status": transfer.transfer_status,
                "previous_successor_id": str(previous_successor_id) if previous_successor_id else None,
                "proposed_successor_id": (
                    str(transfer.proposed_successor_id) if transfer.proposed_successor_id else None
                ),
                "version": transfer.version,
            },
        )
        return transfer

    def update_responsibility_status(
        self,
        transfer_id: uuid.UUID,
        *,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        status: str,
        notes: str | None = None,
    ) -> HandoverResponsibilityTransfer:
        """Backwards-compatible status update wrapper delegating to strict update validation."""
        return self.update_responsibility_transfer(
            transfer_id=transfer_id,
            project_id=project_id,
            user_id=user_id,
            request=ResponsibilityTransferUpdateRequest(
                transfer_status=status,
                transfer_notes=notes,
                blocker_reason=notes if status == TransferStatus.BLOCKED.value else None,
            ),
        )

    def confirm_outgoing_owner(
        self,
        transfer_id: uuid.UUID,
        *,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        request: ResponsibilityOutgoingConfirmRequest,
        can_manage_project: bool = False,
    ) -> HandoverResponsibilityTransfer:
        """Explicit Outgoing-Owner Confirmation advancing transfer to awaiting successor acknowledgement."""
        transfer = self.session.get(HandoverResponsibilityTransfer, transfer_id)
        if not transfer or transfer.project_id != project_id:
            raise NotFoundError(f"Responsibility transfer {transfer_id} not found in this project.")

        if request.expected_version is not None and transfer.version != request.expected_version:
            raise ConflictError(
                f"Version conflict on responsibility transfer (expected {request.expected_version}, got {transfer.version})."
            )

        if user_id != transfer.current_owner_id and not can_manage_project:
            raise ForbiddenError(
                "Only the outgoing responsibility owner or a project manager can confirm outgoing handover."
            )

        if not transfer.proposed_successor_id:
            raise BadRequestError(
                "Assign an eligible incoming successor before confirming outgoing transfer."
            )

        self._validate_active_successor(
            project_id=project_id,
            current_owner_id=transfer.current_owner_id,
            proposed_successor_id=transfer.proposed_successor_id,
        )

        transfer.outgoing_confirmed_by_user_id = user_id
        transfer.outgoing_confirmed_at = utc_now()
        transfer.outgoing_confirmation_notes = request.confirmation_notes
        transfer.ownership_certainty = "confirmed"
        transfer.transfer_status = TransferStatus.AWAITING_SUCCESSOR_ACKNOWLEDGEMENT.value
        transfer.blocker_reason = None
        transfer.version = (transfer.version or 1) + 1
        transfer.updated_at = utc_now()
        self.session.flush()

        self.audit_service.record_event(
            event_type="handover.responsibility.outgoing_confirmed",
            resource_type="handover_responsibility_transfer",
            resource_id=str(transfer.id),
            actor_user_id=user_id,
            organisation_id=transfer.organisation_id,
            project_id=project_id,
            outcome=AuditOutcome.SUCCESS.value,
            metadata={
                "case_id": str(transfer.case_id),
                "proposed_successor_id": str(transfer.proposed_successor_id),
                "notes": request.confirmation_notes,
                "version": transfer.version,
            },
        )
        return transfer

    def acknowledge_as_successor(
        self,
        transfer_id: uuid.UUID,
        *,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        request: ResponsibilitySuccessorAckRequest,
    ) -> HandoverResponsibilityTransfer:
        """Explicit Receiving-Successor Acknowledgement (strict separation of duties).

        NOTE: Successor acknowledgement confirms receipt and understanding of the responsibility
        context. It does NOT substitute for final managerial approval (Stage 6).
        """
        transfer = self.session.get(HandoverResponsibilityTransfer, transfer_id)
        if not transfer or transfer.project_id != project_id:
            raise NotFoundError(f"Responsibility transfer {transfer_id} not found in this project.")

        if request.expected_version is not None and transfer.version != request.expected_version:
            raise ConflictError(
                f"Version conflict on responsibility transfer (expected {request.expected_version}, got {transfer.version})."
            )

        if not transfer.proposed_successor_id or user_id != transfer.proposed_successor_id:
            raise ForbiddenError(
                "Separation of duties: only the designated incoming successor can acknowledge this responsibility transfer."
            )

        # Ensure successor still holds active project membership
        self._validate_active_successor(
            project_id=project_id,
            current_owner_id=transfer.current_owner_id,
            proposed_successor_id=user_id,
        )

        if transfer.outgoing_confirmed_at is None:
            raise BadRequestError(
                "Outgoing-owner confirmation is required before the incoming successor can acknowledge transfer."
            )

        if transfer.transfer_status not in (
            TransferStatus.AWAITING_SUCCESSOR_ACKNOWLEDGEMENT.value,
            TransferStatus.CLARIFICATION_REQUESTED.value,
            TransferStatus.REOPENED.value,
        ):
            raise BadRequestError(
                f"Cannot acknowledge responsibility transfer from status '{transfer.transfer_status}'."
            )

        transfer.successor_acknowledged_by_user_id = user_id
        transfer.successor_acknowledged_at = utc_now()
        transfer.successor_acknowledgement_notes = request.acknowledgement_notes
        transfer.transfer_status = TransferStatus.ACKNOWLEDGED.value
        transfer.version = (transfer.version or 1) + 1
        transfer.updated_at = utc_now()
        self.session.flush()

        self.audit_service.record_event(
            event_type="handover.responsibility.successor_acknowledged",
            resource_type="handover_responsibility_transfer",
            resource_id=str(transfer.id),
            actor_user_id=user_id,
            organisation_id=transfer.organisation_id,
            project_id=project_id,
            outcome=AuditOutcome.SUCCESS.value,
            metadata={
                "case_id": str(transfer.case_id),
                "notes": request.acknowledgement_notes,
                "version": transfer.version,
            },
        )
        return transfer

    def handle_clarification(
        self,
        transfer_id: uuid.UUID,
        *,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        request: ResponsibilityClarificationRequest,
        can_manage_project: bool = False,
    ) -> HandoverResponsibilityTransfer:
        """Record a successor clarification request or outgoing-owner clarification response."""
        transfer = self.session.get(HandoverResponsibilityTransfer, transfer_id)
        if not transfer or transfer.project_id != project_id:
            raise NotFoundError(f"Responsibility transfer {transfer_id} not found in this project.")

        if request.expected_version is not None and transfer.version != request.expected_version:
            raise ConflictError(
                f"Version conflict on responsibility transfer (expected {request.expected_version}, got {transfer.version})."
            )

        if request.mode == "request":
            if user_id != transfer.proposed_successor_id and not can_manage_project:
                raise ForbiddenError(
                    "Only the designated successor or a project reviewer/manager can request clarification."
                )
            transfer.clarification_requested_by_user_id = user_id
            transfer.clarification_requested_at = utc_now()
            transfer.clarification_request_notes = request.notes.strip()
            transfer.transfer_status = TransferStatus.CLARIFICATION_REQUESTED.value
            event_type = "handover.responsibility.clarification_requested"
        else:
            if user_id != transfer.current_owner_id and not can_manage_project:
                raise ForbiddenError(
                    "Only the outgoing owner or a project manager can respond to a clarification request."
                )
            transfer.clarification_response_notes = request.notes.strip()
            transfer.transfer_status = (
                TransferStatus.AWAITING_SUCCESSOR_ACKNOWLEDGEMENT.value
                if transfer.outgoing_confirmed_at is not None
                else TransferStatus.PREPARED.value
            )
            event_type = "handover.responsibility.clarification_responded"

        transfer.version = (transfer.version or 1) + 1
        transfer.updated_at = utc_now()
        self.session.flush()

        self.audit_service.record_event(
            event_type=event_type,
            resource_type="handover_responsibility_transfer",
            resource_id=str(transfer.id),
            actor_user_id=user_id,
            organisation_id=transfer.organisation_id,
            project_id=project_id,
            outcome=AuditOutcome.SUCCESS.value,
            metadata={
                "case_id": str(transfer.case_id),
                "mode": request.mode,
                "notes": request.notes.strip(),
                "version": transfer.version,
            },
        )
        return transfer

    def reopen_transfer(
        self,
        transfer_id: uuid.UUID,
        *,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        request: ResponsibilityReopenRequest,
        can_manage_project: bool = False,
    ) -> HandoverResponsibilityTransfer:
        """Reopen an acknowledged/completed transfer with mandatory rationale."""
        transfer = self.session.get(HandoverResponsibilityTransfer, transfer_id)
        if not transfer or transfer.project_id != project_id:
            raise NotFoundError(f"Responsibility transfer {transfer_id} not found in this project.")

        if request.expected_version is not None and transfer.version != request.expected_version:
            raise ConflictError(
                f"Version conflict on responsibility transfer (expected {request.expected_version}, got {transfer.version})."
            )

        if user_id not in (transfer.current_owner_id, transfer.proposed_successor_id) and not can_manage_project:
            raise ForbiddenError(
                "Only the outgoing owner, designated successor, or project manager can reopen a transfer."
            )

        transfer.transfer_status = TransferStatus.REOPENED.value
        transfer.successor_acknowledged_by_user_id = None
        transfer.successor_acknowledged_at = None
        transfer.successor_acknowledgement_notes = None
        transfer.reopened_count = (transfer.reopened_count or 0) + 1
        transfer.reopened_reason = request.reason.strip()
        transfer.version = (transfer.version or 1) + 1
        transfer.updated_at = utc_now()
        self.session.flush()

        self.audit_service.record_event(
            event_type="handover.responsibility.reopened",
            resource_type="handover_responsibility_transfer",
            resource_id=str(transfer.id),
            actor_user_id=user_id,
            organisation_id=transfer.organisation_id,
            project_id=project_id,
            outcome=AuditOutcome.SUCCESS.value,
            metadata={
                "case_id": str(transfer.case_id),
                "reason": request.reason.strip(),
                "version": transfer.version,
            },
        )
        return transfer

    def get_responsibility_workspace(
        self,
        case_id: uuid.UUID,
        *,
        project_id: uuid.UUID,
        viewer_user_id: uuid.UUID,
        has_project_manage: bool = False,
    ) -> HandoverResponsibilityWorkspaceResponse:
        """Hydrate full Stage 5 responsibility workspace with 8-domain knowledge, ACL-safe evidence & validation."""
        case = self.case_service.get_case(case_id, project_id=project_id, load_relationships=False)
        transfers = self.resp_repo.list_by_case(case.id)
        m_map = self._get_project_membership_map(project_id)

        # Build eligible participants list from real ProjectMembership rows
        participants: list[ResponsibilityParticipantSummary] = []
        for uid, (pm, usr, role) in m_map.items():
            is_active = pm.status == "active" and getattr(usr, "status", "active") == "active"
            participants.append(
                ResponsibilityParticipantSummary(
                    user_id=uid,
                    full_name=usr.full_name or usr.email,
                    email=usr.email,
                    role_name=role.name if role else "project_member",
                    membership_status=pm.status,
                    is_active=is_active,
                    is_departing_owner=(uid == case.departing_member_id),
                    is_case_successor=(uid == case.successor_id),
                    has_handover_access=is_active,
                )
            )
        participants.sort(key=lambda p: (not p.is_active, p.full_name.lower()))

        # Load additional users referenced by transfers or audit logs
        extra_user_ids: set[uuid.UUID] = set()
        entity_ids: set[uuid.UUID] = set()
        transfer_ids_str: set[str] = set()
        for t in transfers:
            transfer_ids_str.add(str(t.id))
            for uid in (
                t.current_owner_id,
                t.proposed_successor_id,
                t.outgoing_confirmed_by_user_id,
                t.successor_acknowledged_by_user_id,
                t.clarification_requested_by_user_id,
            ):
                if uid:
                    extra_user_ids.add(uid)
            if t.related_entity_id:
                entity_ids.add(t.related_entity_id)

        audit_logs = list(
            self.session.execute(
                select(AuditLog)
                .where(
                    AuditLog.project_id == project_id,
                    AuditLog.event_type.like("handover.responsibilit%"),
                )
                .order_by(AuditLog.created_at.desc())
                .limit(60)
            )
            .scalars()
            .all()
        )
        case_id_str = str(case.id)
        filtered_audits: list[AuditLog] = []
        for log in audit_logs:
            meta = log.event_metadata or {}
            if (
                log.resource_id == case_id_str
                or log.resource_id in transfer_ids_str
                or meta.get("case_id") == case_id_str
            ):
                filtered_audits.append(log)
                if log.actor_user_id:
                    extra_user_ids.add(log.actor_user_id)

        users_by_id: dict[uuid.UUID, User] = {uid: entry[1] for uid, entry in m_map.items()}
        missing_uids = extra_user_ids - set(users_by_id.keys())
        if missing_uids:
            for u in (
                self.session.execute(select(User).where(User.id.in_(missing_uids))).scalars().all()
            ):
                users_by_id[u.id] = u

        entities_by_id: dict[uuid.UUID, KnowledgeEntity] = (
            {
                e.id: e
                for e in self.session.execute(
                    select(KnowledgeEntity).where(KnowledgeEntity.id.in_(entity_ids))
                )
                .scalars()
                .all()
            }
            if entity_ids
            else {}
        )

        # Load project KnowledgeItems & Evidence links for 8-domain hydration & candidate discovery
        project_kis = list(
            self.session.execute(
                select(KnowledgeItem).where(
                    KnowledgeItem.project_id == project_id,
                    KnowledgeItem.is_deleted.is_(False),
                )
            )
            .scalars()
            .all()
        )
        kis_by_id = {k.id: k for k in project_kis}

        # Load evidence links for relevant knowledge items
        ki_ids = [k.id for k in project_kis]
        ev_links_by_ki: dict[uuid.UUID, list[KnowledgeEvidenceLink]] = {}
        referenced_ev_ids: set[uuid.UUID] = set()
        if ki_ids:
            for link in (
                self.session.execute(
                    select(KnowledgeEvidenceLink).where(
                        KnowledgeEvidenceLink.knowledge_item_id.in_(ki_ids)
                    )
                )
                .scalars()
                .all()
            ):
                ev_links_by_ki.setdefault(link.knowledge_item_id, []).append(link)
                referenced_ev_ids.add(link.evidence_id)

        evidences_by_id: dict[uuid.UUID, EvidenceItem] = {}
        inaccessible_ev_ids: set[uuid.UUID] = set()
        if referenced_ev_ids:
            evidences_by_id = {
                ev.id: ev
                for ev in self.session.execute(
                    select(EvidenceItem).where(EvidenceItem.id.in_(referenced_ev_ids))
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
            _, denied_ev = check_evidence_accessibility(
                self.session,
                list(referenced_ev_ids),
                project_id=project_id,
                viewer_user_id=viewer_user_id,
                has_project_manage=has_project_manage,
                cached_policies=cached_policies,
            )
            inaccessible_ev_ids = set(denied_ev)

        def _build_evidence_refs(ki_id: uuid.UUID) -> list[ResponsibilityEvidenceRef]:
            refs: list[ResponsibilityEvidenceRef] = []
            seen: set[uuid.UUID] = set()
            for link in ev_links_by_ki.get(ki_id, []):
                if link.evidence_id in seen:
                    continue
                seen.add(link.evidence_id)
                ev = evidences_by_id.get(link.evidence_id)
                if not ev:
                    continue
                if link.evidence_id in inaccessible_ev_ids:
                    refs.append(
                        ResponsibilityEvidenceRef(
                            evidence_id=ev.id,
                            title="Restricted Source (ACL Protected)",
                            source_type=ev.source_type,
                            source_url=None,
                            source_author=None,
                            source_timestamp=None,
                            excerpt=None,
                            acl_restricted=True,
                        )
                    )
                else:
                    refs.append(
                        ResponsibilityEvidenceRef(
                            evidence_id=ev.id,
                            title=redact_secrets(ev.title),
                            source_type=ev.source_type,
                            source_url=ev.source_url,
                            source_author=ev.source_author_identity,
                            source_timestamp=ev.source_created_at or ev.extracted_at,
                            excerpt=(
                                redact_secrets(link.supporting_excerpt)
                                if link.supporting_excerpt
                                else None
                            ),
                            acl_restricted=False,
                        )
                    )
            return refs

        def _ki_to_context(ki: KnowledgeItem) -> ResponsibilityKnowledgeContextItem:
            is_verified = (
                ki.epistemic_status == EpistemicStatus.HUMAN_VERIFIED.value
                and ki.review_status == KnowledgeReviewStatus.APPROVED.value
            )
            return ResponsibilityKnowledgeContextItem(
                id=ki.id,
                category=ki.category,
                title=redact_secrets(ki.title),
                summary=redact_secrets(ki.structured_summary or ""),
                epistemic_status=ki.epistemic_status,
                review_status=ki.review_status,
                is_verified=is_verified,
                evidence_refs=_build_evidence_refs(ki.id),
            )

        # Ownership validation across all transfers
        validation_issues: list[ResponsibilityOwnershipValidationIssue] = []
        component_owners: dict[str, set[uuid.UUID]] = {}
        mapped_ki_ids: set[uuid.UUID] = set()

        for t in transfers:
            if t.related_knowledge_item_id:
                mapped_ki_ids.add(t.related_knowledge_item_id)
            if t.component_name and t.proposed_successor_id:
                key = t.component_name.strip().lower()
                component_owners.setdefault(key, set()).add(t.proposed_successor_id)

        conflicting_components = {k for k, v in component_owners.items() if len(v) > 1}
        for comp in sorted(conflicting_components):
            validation_issues.append(
                ResponsibilityOwnershipValidationIssue(
                    severity="high",
                    code="conflicting_ownership",
                    message=f"Conflicting ownership: component '{comp}' is assigned to multiple different successors.",
                )
            )

        def _uname(uid: uuid.UUID | None) -> str | None:
            if not uid or uid not in users_by_id:
                return None
            u = users_by_id[uid]
            return u.full_name or u.email

        def _urole(uid: uuid.UUID | None) -> str | None:
            if not uid or uid not in m_map:
                return None
            role = m_map[uid][2]
            return role.name if role else "project_member"

        def _uactive(uid: uuid.UUID | None) -> bool:
            if not uid or uid not in m_map:
                return False
            pm, usr, _ = m_map[uid]
            return pm.status == "active" and getattr(usr, "status", "active") == "active"

        # Hydrate each transfer response
        transfer_responses: list[HandoverResponsibilityTransferResponse] = []
        unassigned_count = 0
        awaiting_outgoing_count = 0
        awaiting_successor_count = 0
        acknowledged_count = 0
        blocked_count = 0
        clarification_count = 0

        # Pre-index verified KIs by category for contextual operational/decision/risk enrichment
        verified_kis = [
            k
            for k in project_kis
            if k.epistemic_status == EpistemicStatus.HUMAN_VERIFIED.value
            and k.review_status == KnowledgeReviewStatus.APPROVED.value
        ]

        for t in transfers:
            row_warnings: list[str] = []
            owner_active = _uactive(t.current_owner_id)
            succ_active = _uactive(t.proposed_successor_id) if t.proposed_successor_id else None

            if not t.proposed_successor_id:
                unassigned_count += 1
                msg = "No incoming successor assigned to this responsibility."
                row_warnings.append(msg)
                validation_issues.append(
                    ResponsibilityOwnershipValidationIssue(
                        severity="critical" if t.priority in ("critical", "high") else "medium",
                        code="unassigned_successor",
                        message=f"'{t.title or t.responsibility_description[:60]}' has no assigned successor.",
                        transfer_id=t.id,
                    )
                )
            else:
                if t.proposed_successor_id == t.current_owner_id:
                    msg = "Current owner and proposed successor are the same user."
                    row_warnings.append(msg)
                    validation_issues.append(
                        ResponsibilityOwnershipValidationIssue(
                            severity="high",
                            code="self_assignment",
                            message=msg,
                            transfer_id=t.id,
                            user_id=t.proposed_successor_id,
                        )
                    )
                if not succ_active:
                    msg = "Assigned successor is inactive or lacks active project membership."
                    row_warnings.append(msg)
                    validation_issues.append(
                        ResponsibilityOwnershipValidationIssue(
                            severity="critical",
                            code="inactive_successor",
                            message=f"Successor for '{t.title or t.responsibility_description[:60]}' is inactive or lacks project access.",
                            transfer_id=t.id,
                            user_id=t.proposed_successor_id,
                        )
                    )

            if t.component_name and t.component_name.strip().lower() in conflicting_components:
                row_warnings.append(
                    f"Conflicting ownership detected for component '{t.component_name}'."
                )

            if t.ownership_certainty == "uncertain":
                row_warnings.append(
                    "Ownership certainty is marked uncertain and requires human confirmation."
                )

            st = t.transfer_status
            if st in (TransferStatus.ACKNOWLEDGED.value, TransferStatus.COMPLETED.value):
                acknowledged_count += 1
            elif st == TransferStatus.AWAITING_SUCCESSOR_ACKNOWLEDGEMENT.value:
                awaiting_successor_count += 1
            elif st == TransferStatus.BLOCKED.value:
                blocked_count += 1
            elif st in (TransferStatus.CLARIFICATION_REQUESTED.value, TransferStatus.REOPENED.value):
                clarification_count += 1
            else:
                awaiting_outgoing_count += 1

            # Hydrate related 8-domain knowledge & evidence
            related_ki_objs: list[KnowledgeItem] = []
            seen_ki: set[uuid.UUID] = set()
            if t.related_knowledge_item_id and t.related_knowledge_item_id in kis_by_id:
                ki_direct = kis_by_id[t.related_knowledge_item_id]
                related_ki_objs.append(ki_direct)
                seen_ki.add(ki_direct.id)

            # Match verified knowledge items sharing domain or component keyword (strictly grounded)
            search_terms = [
                w.lower()
                for w in (t.component_name or "").split() + (t.title or "").split()
                if len(w) >= 4
            ]
            for ki in verified_kis:
                if ki.id in seen_ki or len(related_ki_objs) >= 6:
                    break
                haystack = f"{ki.title} {ki.structured_summary or ''}".lower()
                if (t.knowledge_domain and ki.category == t.knowledge_domain) or any(
                    term in haystack for term in search_terms
                ):
                    related_ki_objs.append(ki)
                    seen_ki.add(ki.id)

            related_knowledge = [_ki_to_context(k) for k in related_ki_objs]
            supporting_ev: list[ResponsibilityEvidenceRef] = []
            seen_ev_ids: set[uuid.UUID] = set()
            for rk in related_knowledge:
                for ref in rk.evidence_refs:
                    if ref.evidence_id not in seen_ev_ids:
                        seen_ev_ids.add(ref.evidence_id)
                        supporting_ev.append(ref)

            ent = entities_by_id.get(t.related_entity_id) if t.related_entity_id else None

            transfer_responses.append(
                HandoverResponsibilityTransferResponse(
                    id=t.id,
                    case_id=t.case_id,
                    version_id=t.version_id,
                    title=redact_secrets(t.title) if t.title else None,
                    responsibility_description=redact_secrets(t.responsibility_description),
                    current_owner_id=t.current_owner_id,
                    current_owner_name=_uname(t.current_owner_id),
                    current_owner_role=_urole(t.current_owner_id),
                    current_owner_active=owner_active,
                    proposed_successor_id=t.proposed_successor_id,
                    proposed_successor_name=_uname(t.proposed_successor_id),
                    proposed_successor_role=_urole(t.proposed_successor_id),
                    proposed_successor_active=succ_active,
                    knowledge_domain=t.knowledge_domain,
                    component_name=t.component_name,
                    priority=t.priority or "medium",
                    ownership_certainty=t.ownership_certainty or "proposed",
                    operational_context=(
                        redact_secrets(t.operational_context) if t.operational_context else None
                    ),
                    required_access=(
                        redact_secrets(t.required_access) if t.required_access else None
                    ),
                    effective_transfer_date=t.effective_transfer_date,
                    transfer_status=t.transfer_status,
                    transfer_notes=redact_secrets(t.transfer_notes) if t.transfer_notes else None,
                    blocker_reason=redact_secrets(t.blocker_reason) if t.blocker_reason else None,
                    related_entity_id=t.related_entity_id,
                    related_entity_name=ent.canonical_name if ent else None,
                    related_knowledge_item_id=t.related_knowledge_item_id,
                    outgoing_confirmed_by_user_id=t.outgoing_confirmed_by_user_id,
                    outgoing_confirmed_by_name=_uname(t.outgoing_confirmed_by_user_id),
                    outgoing_confirmed_at=t.outgoing_confirmed_at,
                    outgoing_confirmation_notes=(
                        redact_secrets(t.outgoing_confirmation_notes)
                        if t.outgoing_confirmation_notes
                        else None
                    ),
                    successor_acknowledged_by_user_id=t.successor_acknowledged_by_user_id,
                    successor_acknowledged_by_name=_uname(t.successor_acknowledged_by_user_id),
                    successor_acknowledged_at=t.successor_acknowledged_at,
                    successor_acknowledgement_notes=(
                        redact_secrets(t.successor_acknowledgement_notes)
                        if t.successor_acknowledgement_notes
                        else None
                    ),
                    clarification_requested_by_user_id=t.clarification_requested_by_user_id,
                    clarification_requested_by_name=_uname(t.clarification_requested_by_user_id),
                    clarification_requested_at=t.clarification_requested_at,
                    clarification_request_notes=(
                        redact_secrets(t.clarification_request_notes)
                        if t.clarification_request_notes
                        else None
                    ),
                    clarification_response_notes=(
                        redact_secrets(t.clarification_response_notes)
                        if t.clarification_response_notes
                        else None
                    ),
                    reopened_count=t.reopened_count or 0,
                    reopened_reason=(
                        redact_secrets(t.reopened_reason) if t.reopened_reason else None
                    ),
                    version=t.version or 1,
                    transferred_at=t.transferred_at,
                    validation_warnings=row_warnings,
                    related_knowledge=related_knowledge,
                    supporting_evidence=supporting_ev,
                    created_at=t.created_at,
                    updated_at=t.updated_at,
                )
            )

        # Surface unmapped real responsibility KnowledgeItems as candidates (NEVER auto-promoted!)
        discovered_candidates: list[ResponsibilityCandidateItem] = []
        for ki in project_kis:
            if ki.category != KnowledgeCategory.RESPONSIBILITIES_OWNERSHIP.value:
                continue
            if ki.id in mapped_ki_ids:
                continue
            is_verified = (
                ki.epistemic_status == EpistemicStatus.HUMAN_VERIFIED.value
                and ki.review_status == KnowledgeReviewStatus.APPROVED.value
            )
            refs = _build_evidence_refs(ki.id)
            discovered_candidates.append(
                ResponsibilityCandidateItem(
                    knowledge_item_id=ki.id,
                    title=redact_secrets(ki.title),
                    summary=redact_secrets(ki.structured_summary or ""),
                    epistemic_status=ki.epistemic_status,
                    review_status=ki.review_status,
                    is_verified=is_verified,
                    ownership_certainty="verified" if is_verified else "uncertain",
                    source_context=(
                        "Verified ownership record in canonical Knowledge Intelligence."
                        if is_verified
                        else f"Extracted ({ki.epistemic_status}) — {ki.review_status.replace('_', ' ')}. Ownership requires explicit reviewer/owner confirmation."
                    ),
                    evidence_refs=refs,
                )
            )

        # Build Stage 5 responsibility activity history
        activity_history: list[HandoverStage5ActivityItem] = []
        for log in filtered_audits[:30]:
            actor = users_by_id.get(log.actor_user_id) if log.actor_user_id else None
            meta = log.event_metadata or {}
            activity_history.append(
                HandoverStage5ActivityItem(
                    id=log.id,
                    event_type=log.event_type,
                    resource_type=log.resource_type,
                    resource_id=log.resource_id,
                    actor_user_id=log.actor_user_id,
                    actor_name=(actor.full_name or actor.email) if actor else None,
                    outcome=log.outcome,
                    summary=_summarize_responsibility_audit(log.event_type, meta),
                    metadata_json=meta,
                    created_at=log.created_at,
                )
            )

        return HandoverResponsibilityWorkspaceResponse(
            case_id=case.id,
            project_id=project_id,
            departing_member_id=case.departing_member_id,
            case_successor_id=case.successor_id,
            total_transfers=len(transfer_responses),
            unassigned_count=unassigned_count,
            awaiting_outgoing_count=awaiting_outgoing_count,
            awaiting_successor_count=awaiting_successor_count,
            acknowledged_count=acknowledged_count,
            blocked_count=blocked_count,
            clarification_count=clarification_count,
            validation_issues=validation_issues,
            eligible_participants=participants,
            transfers=transfer_responses,
            discovered_candidates=discovered_candidates,
            activity_history=activity_history,
        )

    def execute_ownership_transfer(
        self,
        case_id: uuid.UUID,
        *,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        request: OwnershipTransferRequest,
    ) -> HandoverOwnershipTransfer:
        """Execute an explicit project or component ownership transfer (gated on approval)."""
        case = self.case_service.get_case(case_id, project_id=project_id, load_relationships=False)
        version = self.version_repo.get_by_id(request.version_id, load_sections=False)
        if not version or version.case_id != case.id:
            raise NotFoundError(f"Package version {request.version_id} not found for this case.")

        if case.status not in (
            HandoverCaseStatus.APPROVED.value,
            HandoverCaseStatus.DELIVERED.value,
            HandoverCaseStatus.ACKNOWLEDGED.value,
        ):
            raise BadRequestError(
                f"Cannot execute ownership transfer in case status '{case.status}'. "
                "The handover package must be approved and delivered first."
            )

        transfer_event = HandoverOwnershipTransfer(
            organisation_id=case.organisation_id,
            project_id=project_id,
            case_id=case.id,
            version_id=version.id,
            transfer_type=request.transfer_type,
            from_user_id=case.departing_member_id,
            to_user_id=request.to_user_id,
            entity_type=request.entity_type,
            entity_id=request.entity_id,
            transfer_notes=request.transfer_reason,
            executed_at=utc_now(),
            executed_by_user_id=user_id,
            rolled_back=False,
        )
        created_transfer = self.ownership_repo.create(transfer_event)

        transfers = self.resp_repo.list_by_case(case.id)
        for t in transfers:
            if t.transfer_status in (
                TransferStatus.PENDING.value,
                TransferStatus.ACKNOWLEDGED.value,
            ):
                self.resp_repo.update_status(t.id, status=TransferStatus.COMPLETED.value)

        self.case_service.transition_status(
            case_id,
            project_id=project_id,
            new_status=HandoverCaseStatus.TRANSFERRED.value,
            user_id=user_id,
            change_reason=f"Executed ownership transfer ({request.transfer_type}) to {request.to_user_id}",
        )

        self.audit_service.record_event(
            event_type="handover.ownership.transferred",
            resource_type="handover_ownership_transfer",
            resource_id=str(created_transfer.id),
            actor_user_id=user_id,
            organisation_id=case.organisation_id,
            project_id=project_id,
            outcome=AuditOutcome.SUCCESS.value,
            metadata={
                "transfer_type": request.transfer_type,
                "from_user_id": str(case.departing_member_id),
                "to_user_id": str(request.to_user_id),
            },
        )
        return created_transfer

    def rollback_ownership_transfer(
        self,
        transfer_id: uuid.UUID,
        *,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        request: OwnershipTransferRollbackRequest,
    ) -> HandoverOwnershipTransfer:
        """Rollback a previously executed ownership transfer."""
        transfer = self.ownership_repo.get_by_id(transfer_id)
        if not transfer or transfer.project_id != project_id:
            raise NotFoundError(f"Ownership transfer {transfer_id} not found in this project.")

        if transfer.rolled_back:
            raise BadRequestError("This ownership transfer has already been rolled back.")

        rolled_back = self.ownership_repo.mark_rolled_back(
            transfer_id,
            rolled_back_by_user_id=user_id,
            rollback_reason=request.rollback_reason,
        )

        self.audit_service.record_event(
            event_type="handover.ownership.rolled_back",
            resource_type="handover_ownership_transfer",
            resource_id=str(transfer_id),
            actor_user_id=user_id,
            organisation_id=transfer.organisation_id,
            project_id=project_id,
            outcome=AuditOutcome.SUCCESS.value,
            metadata={"reason": request.rollback_reason},
        )
        return rolled_back  # type: ignore[return-value]


def _summarize_responsibility_audit(event_type: str, meta: dict[str, Any]) -> str:
    if event_type == "handover.responsibilities.created":
        return f"Mapped {meta.get('count', 1)} responsibility transfer record(s)."
    if event_type == "handover.responsibility.reassigned":
        return "Reassigned responsibility successor."
    if event_type == "handover.responsibility.outgoing_confirmed":
        return "Outgoing owner confirmed responsibility transfer preparation."
    if event_type == "handover.responsibility.successor_acknowledged":
        return "Incoming successor acknowledged responsibility transfer."
    if event_type == "handover.responsibility.clarification_requested":
        return "Successor requested clarification on responsibility transfer."
    if event_type == "handover.responsibility.clarification_responded":
        return "Outgoing owner responded to clarification request."
    if event_type == "handover.responsibility.reopened":
        reason = meta.get("reason") or ""
        return f"Reopened responsibility transfer{f': {reason}' if reason else '.'}"
    status = meta.get("status")
    return f"Updated responsibility transfer{f' ({status})' if status else '.'}"
