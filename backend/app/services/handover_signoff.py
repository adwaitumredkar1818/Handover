"""Handover Human Sign-Off, Approval, Publication & Recipient Acknowledgement Service (Stage 6).

Platform: The Handover
Module: Handover Workspace (Module 4 / Knowledge Transfer Area)

Enforces:
1. Three-phase human sign-off protocol (departing -> independent reviewer -> published recipient)
2. Strict separation of duties (departing member cannot be approving reviewer; recipient cannot be impersonated)
3. Authoritative 4-gate readiness eligibility enforcement before Phase 2 approval
4. Exact package version & SHA-256 content hash binding (detects and invalidates stale approvals)
5. Controlled publication requiring completed approvals and active eligible recipients (prevents duplicate publication)
6. Complete-package recipient acknowledgement & clarification workflow (distinct from Stage 5 responsibility ack)
7. Reviewer assignment/reassignment, justified phase reopening, optimistic concurrency & immutable audit history
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.core.security import utc_now
from app.models.audit import AuditLog
from app.models.enums import (
    AuditOutcome,
    HandoverCaseStatus,
    HandoverDeliveryMethod,
    SignoffDecision,
    SignoffType,
)
from app.models.handover import (
    HandoverAcknowledgement,
    HandoverCase,
    HandoverDelivery,
    HandoverPackageVersion,
    HandoverSignoff,
)
from app.models.project import ProjectMembership
from app.models.rbac import Role
from app.models.user import User
from app.repositories.audit import AuditLogRepository
from app.repositories.handover import (
    HandoverAcknowledgementRepository,
    HandoverCaseRepository,
    HandoverDeliveryRepository,
    HandoverPackageVersionRepository,
    HandoverReadinessRepository,
    HandoverSignoffRepository,
    HandoverStatusHistoryRepository,
)
from app.schemas.handover import (
    AcknowledgementRequest,
    DeliveryClarificationEntry,
    DeliveryClarificationRequest,
    DeliveryRequest,
    HandoverAcknowledgementResponse,
    HandoverDeliveryResponse,
    HandoverSignoffResponse,
    HandoverSignoffWorkspaceResponse,
    HandoverStage5ActivityItem,
    HandoverStatusHistoryResponse,
    ResponsibilityParticipantSummary,
    ReviewerAssignRequest,
    SignoffLifecycleSummary,
    SignoffPhaseDetail,
    SignoffPhaseReopenRequest,
    SignoffPublicationStatus,
    SignoffRequest,
)
from app.services.audit import AuditService
from app.services.handover_case import VALID_TRANSITIONS, HandoverCaseService
from app.services.handover_readiness import HandoverReadinessEngine
from app.services.handover_sections import redact_secrets


class HandoverSignoffService:
    """Manages the 3-phase human approval, publication, and recipient acknowledgement lifecycle."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.case_repo = HandoverCaseRepository(session)
        self.version_repo = HandoverPackageVersionRepository(session)
        self.signoff_repo = HandoverSignoffRepository(session)
        self.delivery_repo = HandoverDeliveryRepository(session)
        self.ack_repo = HandoverAcknowledgementRepository(session)
        self.readiness_repo = HandoverReadinessRepository(session)
        self.history_repo = HandoverStatusHistoryRepository(session)
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

    def _active_signoffs_for_version(
        self, case_id: uuid.UUID, version_id: uuid.UUID
    ) -> list[HandoverSignoff]:
        stmt = (
            select(HandoverSignoff)
            .where(
                HandoverSignoff.case_id == case_id,
                HandoverSignoff.version_id == version_id,
                HandoverSignoff.is_superseded.is_(False),
            )
            .order_by(HandoverSignoff.signed_at.desc())
        )
        return list(self.session.execute(stmt).scalars().all())

    def _latest_active_by_type(
        self, signoffs: list[HandoverSignoff], signoff_type: str
    ) -> HandoverSignoff | None:
        for s in signoffs:
            if s.signoff_type == signoff_type and not s.is_superseded:
                return s
        return None

    def _verify_version_integrity(
        self,
        *,
        case: HandoverCase,
        project_id: uuid.UUID,
        version_id: uuid.UUID,
        expected_content_hash: str | None = None,
        expected_case_version: int | None = None,
    ) -> HandoverPackageVersion:
        if expected_case_version is not None and case.version != expected_case_version:
            raise ConflictError(
                f"Concurrency conflict: case version is {case.version}, expected {expected_case_version}."
            )
        version = self.version_repo.get_by_id(version_id, load_sections=False)
        if not version or version.case_id != case.id or version.project_id != project_id:
            raise NotFoundError(
                f"Package version {version_id} does not belong to handover case {case.id} in this project."
            )
        if expected_content_hash and version.content_hash != expected_content_hash:
            raise ConflictError(
                "Package integrity mismatch: the package SHA-256 hash has changed since review began. "
                "Refresh and review the current package version before submitting a decision."
            )
        return version

    def assign_reviewer(
        self,
        case_id: uuid.UUID,
        *,
        project_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        request: ReviewerAssignRequest,
    ) -> HandoverCase:
        """Assign or reassign an eligible independent reviewer to a handover case."""
        case = self.case_service.get_case(case_id, project_id=project_id, load_relationships=False)
        if request.expected_case_version is not None and case.version != request.expected_case_version:
            raise ConflictError(
                f"Case version conflict (expected {request.expected_case_version}, got {case.version})."
            )
        if case.status in (
            HandoverCaseStatus.DELIVERED.value,
            HandoverCaseStatus.ACKNOWLEDGED.value,
            HandoverCaseStatus.TRANSFERRED.value,
            HandoverCaseStatus.ARCHIVED.value,
        ):
            raise BadRequestError(
                f"Cannot reassign reviewer while handover case is in status '{case.status}'."
            )

        if request.reviewer_user_id == case.departing_member_id:
            raise ForbiddenError(
                "Separation of duties: the departing member cannot be assigned as the approving reviewer."
            )

        m_map = self._get_project_membership_map(project_id)
        entry = m_map.get(request.reviewer_user_id)
        if not entry:
            raise BadRequestError("Assigned reviewer must be a member of this project.")
        pm, usr, _ = entry
        if pm.status != "active" or getattr(usr, "status", "active") != "active":
            raise BadRequestError("Assigned reviewer must hold an active project membership.")

        previous_reviewer_id = case.assigned_reviewer_id
        case.assigned_reviewer_id = request.reviewer_user_id
        case.version += 1
        case.updated_at = utc_now()
        self.session.flush()

        self.audit_service.record_event(
            event_type="handover.reviewer.assigned",
            resource_type="handover_case",
            resource_id=str(case.id),
            actor_user_id=actor_user_id,
            organisation_id=case.organisation_id,
            project_id=project_id,
            outcome=AuditOutcome.SUCCESS.value,
            metadata={
                "case_id": str(case.id),
                "previous_reviewer_id": str(previous_reviewer_id) if previous_reviewer_id else None,
                "assigned_reviewer_id": str(request.reviewer_user_id),
                "reason": request.reason,
            },
        )
        return case

    def reopen_signoff_phase(
        self,
        case_id: uuid.UUID,
        *,
        project_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        request: SignoffPhaseReopenRequest,
    ) -> HandoverCase:
        """Authorised reopening of a signoff phase, preserving previous signoff rows immutably."""
        case = self.case_service.get_case(case_id, project_id=project_id, load_relationships=False)
        if request.expected_case_version is not None and case.version != request.expected_case_version:
            raise ConflictError(
                f"Case version conflict (expected {request.expected_case_version}, got {case.version})."
            )
        if case.status in (
            HandoverCaseStatus.DELIVERED.value,
            HandoverCaseStatus.ACKNOWLEDGED.value,
            HandoverCaseStatus.TRANSFERRED.value,
            HandoverCaseStatus.ARCHIVED.value,
        ):
            raise BadRequestError(
                f"Cannot reopen signoff phase after handover is '{case.status}'."
            )

        if request.signoff_type not in (
            SignoffType.DEPARTING_SIGNOFF.value,
            SignoffType.REVIEWER_APPROVAL.value,
        ):
            raise BadRequestError(
                f"Cannot reopen phase '{request.signoff_type}'. Only Phase 1 or Phase 2 may be reopened prior to publication."
            )

        phases_to_supersede = {request.signoff_type}
        if request.signoff_type == SignoffType.DEPARTING_SIGNOFF.value:
            phases_to_supersede.add(SignoffType.REVIEWER_APPROVAL.value)

        all_signoffs = self.signoff_repo.list_by_case(case.id)
        superseded_count = 0
        for sig in all_signoffs:
            if sig.signoff_type in phases_to_supersede and not sig.is_superseded:
                sig.is_superseded = True
                superseded_count += 1

        if superseded_count == 0:
            raise BadRequestError(
                f"No active signoff decision exists to reopen for phase '{request.signoff_type}'."
            )

        # Transition case back via canonical VALID_TRANSITIONS
        if request.signoff_type == SignoffType.REVIEWER_APPROVAL.value:
            if case.status == HandoverCaseStatus.APPROVED.value:
                self.case_service.transition_status(
                    case.id,
                    project_id=project_id,
                    new_status=HandoverCaseStatus.UNDER_REVIEW.value,
                    user_id=actor_user_id,
                    change_reason=f"Reopened Phase 2 approval: {request.reason}",
                )
        else:
            # Reopening Phase 1 returns case to READINESS_ASSESSED (or UNDER_REVIEW -> READINESS_ASSESSED)
            if case.status == HandoverCaseStatus.APPROVED.value:
                self.case_service.transition_status(
                    case.id,
                    project_id=project_id,
                    new_status=HandoverCaseStatus.UNDER_REVIEW.value,
                    user_id=actor_user_id,
                    change_reason=f"Reopening Phase 1 sign-off: {request.reason}",
                )
            if case.status in (
                HandoverCaseStatus.REVIEW_PENDING.value,
                HandoverCaseStatus.UNDER_REVIEW.value,
            ):
                self.case_service.transition_status(
                    case.id,
                    project_id=project_id,
                    new_status=HandoverCaseStatus.READINESS_ASSESSED.value,
                    user_id=actor_user_id,
                    change_reason=f"Reopened Phase 1 departing sign-off: {request.reason}",
                )

        self.audit_service.record_event(
            event_type="handover.signoff.reopened",
            resource_type="handover_case",
            resource_id=str(case.id),
            actor_user_id=actor_user_id,
            organisation_id=case.organisation_id,
            project_id=project_id,
            outcome=AuditOutcome.SUCCESS.value,
            metadata={
                "case_id": str(case.id),
                "signoff_type": request.signoff_type,
                "reason": request.reason,
                "superseded_count": superseded_count,
            },
        )
        self.session.flush()
        return case

    def submit_signoff(
        self,
        case_id: uuid.UUID,
        *,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        request: SignoffRequest,
        is_org_admin: bool = False,
        can_approve: bool = True,
        has_project_manage: bool = False,
    ) -> HandoverSignoff:
        """Process a three-phase sign-off or approval action with full governance enforcement."""
        case = self.case_service.get_case(case_id, project_id=project_id, load_relationships=False)
        version = self._verify_version_integrity(
            case=case,
            project_id=project_id,
            version_id=request.version_id,
            expected_content_hash=request.expected_content_hash,
            expected_case_version=request.expected_case_version,
        )

        if request.decision not in (
            SignoffDecision.APPROVED.value,
            SignoffDecision.REJECTED.value,
            SignoffDecision.RETURNED_FOR_REVISION.value,
        ):
            raise BadRequestError(f"Unsupported sign-off decision '{request.decision}'.")

        active_version_signoffs = self._active_signoffs_for_version(case.id, version.id)

        # ------------------------------------------------------------------
        # Phase 1: Departing Member Sign-Off
        # ------------------------------------------------------------------
        if request.signoff_type == SignoffType.DEPARTING_SIGNOFF.value:
            if user_id != case.departing_member_id and not is_org_admin:
                raise ForbiddenError(
                    "Only the designated departing member or an administrator can submit Phase 1 sign-off."
                )

            if case.status in (
                HandoverCaseStatus.APPROVED.value,
                HandoverCaseStatus.DELIVERED.value,
                HandoverCaseStatus.ACKNOWLEDGED.value,
                HandoverCaseStatus.TRANSFERRED.value,
                HandoverCaseStatus.ARCHIVED.value,
            ):
                raise BadRequestError(
                    f"Cannot submit Phase 1 sign-off while case is in status '{case.status}'."
                )

            existing_p1 = self._latest_active_by_type(
                active_version_signoffs, SignoffType.DEPARTING_SIGNOFF.value
            )
            if (
                request.decision == SignoffDecision.APPROVED.value
                and existing_p1
                and existing_p1.decision == SignoffDecision.APPROVED.value
            ):
                raise ConflictError(
                    "Phase 1 departing sign-off has already been recorded for this package version."
                )

            if (
                request.decision
                in (SignoffDecision.REJECTED.value, SignoffDecision.RETURNED_FOR_REVISION.value)
                and len((request.comments or "").strip()) < 5
            ):
                raise BadRequestError(
                    "A documented reason (at least 5 characters) is required when rejecting or returning a handover."
                )

            signoff = self._record_signoff(
                case=case,
                version=version,
                signoff_type=request.signoff_type,
                signer_user_id=user_id,
                decision=request.decision,
                comments=request.comments,
                conditions=request.conditions,
                affected_sections=request.affected_sections,
            )

            if request.decision == SignoffDecision.APPROVED.value:
                if case.status == HandoverCaseStatus.DRAFT.value:
                    self.case_service.transition_status(
                        case_id,
                        project_id=project_id,
                        new_status=HandoverCaseStatus.ASSEMBLING.value,
                        user_id=user_id,
                        change_reason="Preparing review submission",
                    )
                if case.status in (
                    HandoverCaseStatus.ASSEMBLED.value,
                    HandoverCaseStatus.READINESS_PENDING.value,
                ):
                    self.case_service.transition_status(
                        case_id,
                        project_id=project_id,
                        new_status=HandoverCaseStatus.READINESS_ASSESSED.value,
                        user_id=user_id,
                        change_reason="Transitioning to readiness assessed prior to review",
                    )
                if case.status in (
                    HandoverCaseStatus.READINESS_ASSESSED.value,
                    HandoverCaseStatus.REJECTED.value,
                    HandoverCaseStatus.UNDER_REVIEW.value,
                ):
                    self.case_service.transition_status(
                        case_id,
                        project_id=project_id,
                        new_status=HandoverCaseStatus.REVIEW_PENDING.value,
                        user_id=user_id,
                        change_reason="Departing member completed Phase 1 sign-off",
                    )
            return signoff

        # ------------------------------------------------------------------
        # Phase 2: Independent Managerial / Reviewer Approval
        # ------------------------------------------------------------------
        elif request.signoff_type == SignoffType.REVIEWER_APPROVAL.value:
            # Strict Separation of Duties: departing member can NEVER approve their own handover
            if user_id == case.departing_member_id:
                raise ForbiddenError(
                    "Separation of duties violation: The departing member cannot act as the approving reviewer."
                )

            # Enforce assigned reviewer authority if an explicit reviewer is assigned
            if (
                case.assigned_reviewer_id is not None
                and user_id != case.assigned_reviewer_id
                and not is_org_admin
            ):
                raise ForbiddenError(
                    "Only the assigned independent reviewer can submit Phase 2 review decisions for this case."
                )

            if case.status not in (
                HandoverCaseStatus.REVIEW_PENDING.value,
                HandoverCaseStatus.UNDER_REVIEW.value,
            ):
                raise BadRequestError(
                    f"Phase 2 reviewer decisions require the handover case to be in 'review_pending' or 'under_review' "
                    f"(current status: '{case.status}')."
                )

            if request.decision == SignoffDecision.APPROVED.value:
                if not can_approve and not is_org_admin:
                    raise ForbiddenError(
                        "You do not hold the 'handover.approve' permission required for final managerial approval."
                    )

                existing_p2 = self._latest_active_by_type(
                    active_version_signoffs, SignoffType.REVIEWER_APPROVAL.value
                )
                if existing_p2 and existing_p2.decision == SignoffDecision.APPROVED.value:
                    raise ConflictError(
                        "Phase 2 managerial approval has already been recorded for this package version."
                    )

                # Phase 1 departing sign-off must be completed on THIS EXACT package version
                p1 = self._latest_active_by_type(
                    active_version_signoffs, SignoffType.DEPARTING_SIGNOFF.value
                )
                if not p1 or p1.decision != SignoffDecision.APPROVED.value:
                    raise BadRequestError(
                        "Phase 1 departing-owner sign-off must be completed on this exact package version "
                        "before Phase 2 approval can be granted."
                    )

                # Authoritative Readiness Intelligence & 4-gate approval eligibility check
                readiness_engine = HandoverReadinessEngine(self.session)
                try:
                    readiness = readiness_engine.get_readiness_intelligence(
                        case_id=case.id,
                        version_id=version.id,
                        project_id=project_id,
                        viewer_user_id=user_id,
                        has_project_manage=has_project_manage or is_org_admin,
                    )
                except NotFoundError as exc:
                    raise BadRequestError(
                        "A persisted readiness assessment for this exact package version is required before approval."
                    ) from exc

                elig = readiness.approval_eligibility
                blocking_reasons: list[str] = list(elig.blocking_requirements) if elig else []
                is_blocked = (
                    (elig is not None and not elig.is_eligible_for_approval)
                    or readiness.blocker_count > 0
                )

                if is_blocked:
                    reason_summary = "; ".join(blocking_reasons) if blocking_reasons else "Active readiness blockers present."
                    if not is_org_admin:
                        raise BadRequestError(
                            f"Package cannot be approved because unresolved readiness blockers exist: {reason_summary}"
                        )
                    # Existing policy permits Organisation Administrator override ONLY with explicit documented rationale
                    override_rationale = (request.conditions or "").strip()
                    if len(override_rationale) < 10:
                        raise BadRequestError(
                            "Package cannot be approved because unresolved readiness blockers exist. "
                            "An Organisation Administrator override requires documented exception conditions (min 10 characters)."
                        )
                    self.audit_service.record_event(
                        event_type="handover.signoff.blocker_override",
                        resource_type="handover_package_version",
                        resource_id=str(version.id),
                        actor_user_id=user_id,
                        organisation_id=case.organisation_id,
                        project_id=project_id,
                        outcome=AuditOutcome.SUCCESS.value,
                        metadata={
                            "case_id": str(case.id),
                            "version_id": str(version.id),
                            "overridden_blockers": blocking_reasons,
                            "override_conditions": override_rationale,
                        },
                    )

                signoff = self._record_signoff(
                    case=case,
                    version=version,
                    signoff_type=request.signoff_type,
                    signer_user_id=user_id,
                    decision=request.decision,
                    comments=request.comments,
                    conditions=request.conditions,
                    affected_sections=request.affected_sections,
                )

                self.case_service.transition_status(
                    case_id,
                    project_id=project_id,
                    new_status=HandoverCaseStatus.APPROVED.value,
                    user_id=user_id,
                    change_reason=f"Approved package v{version.version_number} (SHA-256 {version.content_hash[:12]})",
                )
                return signoff

            elif request.decision == SignoffDecision.REJECTED.value:
                if len((request.comments or "").strip()) < 5:
                    raise BadRequestError(
                        "Rejecting a handover package requires a mandatory reason (at least 5 characters)."
                    )
                signoff = self._record_signoff(
                    case=case,
                    version=version,
                    signoff_type=request.signoff_type,
                    signer_user_id=user_id,
                    decision=request.decision,
                    comments=request.comments,
                    conditions=request.conditions,
                    affected_sections=request.affected_sections,
                )
                self.case_service.transition_status(
                    case_id,
                    project_id=project_id,
                    new_status=HandoverCaseStatus.REJECTED.value,
                    user_id=user_id,
                    change_reason=f"Rejected by reviewer: {request.comments.strip()}",
                )
                return signoff

            elif request.decision == SignoffDecision.RETURNED_FOR_REVISION.value:
                if len((request.comments or "").strip()) < 5:
                    raise BadRequestError(
                        "Requesting changes requires a mandatory description of required corrections (at least 5 characters)."
                    )
                signoff = self._record_signoff(
                    case=case,
                    version=version,
                    signoff_type=request.signoff_type,
                    signer_user_id=user_id,
                    decision=request.decision,
                    comments=request.comments,
                    conditions=request.conditions,
                    affected_sections=request.affected_sections,
                )
                next_status = (
                    HandoverCaseStatus.UNDER_REVIEW.value
                    if case.status == HandoverCaseStatus.REVIEW_PENDING.value
                    else HandoverCaseStatus.READINESS_ASSESSED.value
                )
                self.case_service.transition_status(
                    case_id,
                    project_id=project_id,
                    new_status=next_status,
                    user_id=user_id,
                    change_reason=f"Changes requested: {request.comments.strip()}",
                )
                return signoff

        # ------------------------------------------------------------------
        # Phase 3: Recipient Acknowledgement (Published Package Only!)
        # ------------------------------------------------------------------
        elif request.signoff_type == SignoffType.SUCCESSOR_ACKNOWLEDGEMENT.value:
            if case.status != HandoverCaseStatus.DELIVERED.value:
                raise BadRequestError(
                    "Recipient acknowledgement is only permitted after the approved handover package has been published."
                )
            deliveries = self.delivery_repo.list_by_version(version.id)
            recipient_delivery = next(
                (d for d in deliveries if d.is_active and d.delivered_to_user_id == user_id),
                None,
            )
            if not recipient_delivery:
                raise ForbiddenError(
                    "Only a designated recipient of the published handover package can submit Phase 3 acknowledgement."
                )

            if request.decision != SignoffDecision.APPROVED.value:
                raise BadRequestError(
                    "Use the delivery clarification workflow to raise questions on a published package."
                )

            self.acknowledge_delivery(
                recipient_delivery.id,
                project_id=project_id,
                user_id=user_id,
                request=AcknowledgementRequest(
                    acknowledgement_notes=request.comments,
                    expected_content_hash=request.expected_content_hash,
                ),
            )
            latest_p3 = self._latest_active_by_type(
                self._active_signoffs_for_version(case.id, version.id),
                SignoffType.SUCCESSOR_ACKNOWLEDGEMENT.value,
            )
            assert latest_p3 is not None
            return latest_p3

        else:
            raise BadRequestError(f"Unsupported sign-off type '{request.signoff_type}'.")

    def deliver_package(
        self,
        case_id: uuid.UUID,
        *,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        request: DeliveryRequest,
    ) -> list[HandoverDelivery]:
        """Controlled publication & delivery of an approved, integrity-verified package version."""
        case = self.case_service.get_case(case_id, project_id=project_id, load_relationships=False)
        version = self._verify_version_integrity(
            case=case,
            project_id=project_id,
            version_id=request.version_id,
            expected_content_hash=request.expected_content_hash,
            expected_case_version=request.expected_case_version,
        )

        # Publication strictly requires APPROVED lifecycle status
        if case.status != HandoverCaseStatus.APPROVED.value:
            raise BadRequestError(
                f"Cannot publish package version in case status '{case.status}'. "
                "The handover must complete Phase 1 and Phase 2 approval first."
            )

        # Verify active non-superseded Phase 1 + Phase 2 approvals exist on THIS EXACT version & hash
        active_signoffs = self._active_signoffs_for_version(case.id, version.id)
        p1 = self._latest_active_by_type(active_signoffs, SignoffType.DEPARTING_SIGNOFF.value)
        p2 = self._latest_active_by_type(active_signoffs, SignoffType.REVIEWER_APPROVAL.value)
        if not p1 or p1.decision != SignoffDecision.APPROVED.value:
            raise BadRequestError(
                "Cannot publish: Phase 1 departing sign-off is missing for this exact package version."
            )
        if not p2 or p2.decision != SignoffDecision.APPROVED.value:
            raise BadRequestError(
                "Cannot publish: Phase 2 managerial approval is missing for this exact package version."
            )
        if p2.package_content_hash and version.content_hash and p2.package_content_hash != version.content_hash:
            raise ConflictError(
                "Cannot publish: package integrity hash no longer matches the approved SHA-256 snapshot."
            )

        # Prevent duplicate publication of the same version
        existing_deliveries = [
            d for d in self.delivery_repo.list_by_version(version.id) if d.is_active
        ]
        if existing_deliveries:
            raise ConflictError(
                f"Package version v{version.version_number} has already been published."
            )

        # Validate all recipients are active project members
        m_map = self._get_project_membership_map(project_id)
        unique_recipient_ids: list[uuid.UUID] = []
        for target_uid in request.deliver_to_user_ids:
            if target_uid in unique_recipient_ids:
                continue
            entry = m_map.get(target_uid)
            if not entry:
                raise BadRequestError(
                    "All publication recipients must be members of this project."
                )
            pm, usr, _ = entry
            if pm.status != "active" or getattr(usr, "status", "active") != "active":
                raise BadRequestError(
                    "All publication recipients must hold active project memberships."
                )
            unique_recipient_ids.append(target_uid)

        now = utc_now()
        expires_at = (
            now + timedelta(days=request.expires_in_days) if request.expires_in_days else None
        )

        deliveries: list[HandoverDelivery] = []
        for target_user_id in unique_recipient_ids:
            delivery = HandoverDelivery(
                organisation_id=case.organisation_id,
                project_id=project_id,
                case_id=case.id,
                version_id=version.id,
                delivered_to_user_id=target_user_id,
                delivered_by_user_id=user_id,
                delivery_method=request.delivery_method or HandoverDeliveryMethod.INTERNAL_DOWNLOAD.value,
                message=request.message,
                artifact_checksum=version.content_hash,
                delivered_at=now,
                expires_at=expires_at,
                is_active=True,
                clarifications_json=[],
            )
            created_d = self.delivery_repo.create(delivery)
            deliveries.append(created_d)

        # Transition Case to DELIVERED (Published)
        self.case_service.transition_status(
            case_id,
            project_id=project_id,
            new_status=HandoverCaseStatus.DELIVERED.value,
            user_id=user_id,
            change_reason=f"Published approved package v{version.version_number} (SHA-256 {version.content_hash[:12]}) to {len(deliveries)} recipient(s)",
        )

        self.audit_service.record_event(
            event_type="handover.package.published",
            resource_type="handover_package_version",
            resource_id=str(version.id),
            actor_user_id=user_id,
            organisation_id=case.organisation_id,
            project_id=project_id,
            outcome=AuditOutcome.SUCCESS.value,
            metadata={
                "case_id": str(case.id),
                "version_id": str(version.id),
                "version_number": version.version_number,
                "content_hash": version.content_hash,
                "recipients_count": len(deliveries),
                "recipient_ids": [str(u) for u in unique_recipient_ids],
            },
        )
        return deliveries

    def acknowledge_delivery(
        self,
        delivery_id: uuid.UUID,
        *,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        request: AcknowledgementRequest,
    ) -> HandoverAcknowledgement:
        """Designated recipient submits formal acknowledgement of the complete published package."""
        delivery = self.delivery_repo.get_by_id(delivery_id)
        if not delivery or delivery.project_id != project_id or not delivery.is_active:
            raise NotFoundError(f"Published delivery {delivery_id} not found in this project.")

        case = self.case_service.get_case(
            delivery.case_id, project_id=project_id, load_relationships=False
        )
        if case.status not in (
            HandoverCaseStatus.DELIVERED.value,
            HandoverCaseStatus.ACKNOWLEDGED.value,
        ):
            raise BadRequestError(
                "Cannot acknowledge an unpublished or unapproved handover package."
            )

        if delivery.delivered_to_user_id != user_id:
            raise ForbiddenError(
                "Separation of duties: only the designated publication recipient can acknowledge receipt."
            )

        if (
            request.expected_content_hash
            and delivery.artifact_checksum
            and request.expected_content_hash != delivery.artifact_checksum
        ):
            raise ConflictError(
                "Package integrity hash mismatch on delivery acknowledgement."
            )

        existing_ack = self.ack_repo.get_by_delivery(delivery.id)
        if existing_ack:
            raise ConflictError("This published handover delivery has already been acknowledged.")

        version = self.version_repo.get_by_id(delivery.version_id, load_sections=False)
        if not version:
            raise NotFoundError("Published package version record could not be found.")

        now = utc_now()
        ack_str = (
            f"{delivery.id}:{delivery.artifact_checksum or ''}:{user_id}:"
            f"{now.isoformat()}:{request.acknowledgement_notes or ''}"
        )
        ack_hash = hashlib.sha256(ack_str.encode("utf-8")).hexdigest()

        ack = HandoverAcknowledgement(
            organisation_id=delivery.organisation_id,
            project_id=project_id,
            delivery_id=delivery.id,
            case_id=delivery.case_id,
            version_id=delivery.version_id,
            acknowledged_by_user_id=user_id,
            acknowledged_at=now,
            acknowledgement_notes=request.acknowledgement_notes,
            confirmations_json=dict(request.confirmations or {}),
            acknowledgement_hash=ack_hash,
        )
        created_ack = self.ack_repo.create(ack)

        # Record corresponding Phase 3 signoff atomically
        self._record_signoff(
            case=case,
            version=version,
            signoff_type=SignoffType.SUCCESSOR_ACKNOWLEDGEMENT.value,
            signer_user_id=user_id,
            decision=SignoffDecision.APPROVED.value,
            comments=request.acknowledgement_notes,
            conditions=None,
            affected_sections=[],
        )

        # Transition case to ACKNOWLEDGED
        if case.status == HandoverCaseStatus.DELIVERED.value:
            self.case_service.transition_status(
                case.id,
                project_id=project_id,
                new_status=HandoverCaseStatus.ACKNOWLEDGED.value,
                user_id=user_id,
                change_reason=f"Recipient acknowledged published package v{version.version_number} (hash {ack_hash[:12]})",
            )

        self.audit_service.record_event(
            event_type="handover.delivery.acknowledged",
            resource_type="handover_delivery",
            resource_id=str(delivery.id),
            actor_user_id=user_id,
            organisation_id=delivery.organisation_id,
            project_id=project_id,
            outcome=AuditOutcome.SUCCESS.value,
            metadata={
                "case_id": str(case.id),
                "version_id": str(version.id),
                "acknowledgement_hash": ack_hash,
                "package_content_hash": delivery.artifact_checksum,
            },
        )
        return created_ack

    def handle_delivery_clarification(
        self,
        delivery_id: uuid.UUID,
        *,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        request: DeliveryClarificationRequest,
        can_manage_project: bool = False,
    ) -> HandoverDelivery:
        """Record a recipient clarification request or outgoing/manager response on a published delivery."""
        delivery = self.delivery_repo.get_by_id(delivery_id)
        if not delivery or delivery.project_id != project_id or not delivery.is_active:
            raise NotFoundError(f"Published delivery {delivery_id} not found in this project.")

        case = self.case_service.get_case(
            delivery.case_id, project_id=project_id, load_relationships=False
        )

        if request.mode == "request":
            if user_id != delivery.delivered_to_user_id:
                raise ForbiddenError(
                    "Only the designated handover recipient can submit a clarification request."
                )
            event_type = "handover.delivery.clarification_requested"
        else:
            if (
                user_id not in (case.departing_member_id, delivery.delivered_by_user_id)
                and not can_manage_project
            ):
                raise ForbiddenError(
                    "Only the outgoing owner, publisher, or project manager can respond to recipient clarifications."
                )
            event_type = "handover.delivery.clarification_responded"

        actor = self.session.get(User, user_id)
        entry = {
            "id": str(uuid.uuid4()),
            "mode": request.mode,
            "author_user_id": str(user_id),
            "author_name": (actor.full_name or actor.email) if actor else None,
            "notes": request.notes.strip(),
            "created_at": utc_now().isoformat(),
        }
        updated_list = list(delivery.clarifications_json or [])
        updated_list.append(entry)
        delivery.clarifications_json = updated_list
        self.session.flush()

        self.audit_service.record_event(
            event_type=event_type,
            resource_type="handover_delivery",
            resource_id=str(delivery.id),
            actor_user_id=user_id,
            organisation_id=delivery.organisation_id,
            project_id=project_id,
            outcome=AuditOutcome.SUCCESS.value,
            metadata={
                "case_id": str(case.id),
                "delivery_id": str(delivery.id),
                "mode": request.mode,
                "notes": request.notes.strip(),
            },
        )
        return delivery

    def get_signoff_workspace(
        self,
        case_id: uuid.UUID,
        *,
        project_id: uuid.UUID,
        viewer_user_id: uuid.UUID,
        version_id: uuid.UUID | None = None,
        is_org_admin: bool = False,
        can_review: bool = False,
        can_approve: bool = False,
        can_deliver: bool = False,
        can_acknowledge: bool = False,
        has_project_manage: bool = False,
    ) -> HandoverSignoffWorkspaceResponse:
        """Build the complete authoritative Stage 6 Signoff, Approval, Publication & Recipient workspace."""
        case = self.case_service.get_case(case_id, project_id=project_id, load_relationships=False)
        versions = list(
            self.session.execute(
                select(HandoverPackageVersion)
                .where(HandoverPackageVersion.case_id == case.id)
                .order_by(HandoverPackageVersion.version_number.desc())
            )
            .scalars()
            .all()
        )
        selected_version: HandoverPackageVersion | None = None
        if version_id:
            selected_version = next((v for v in versions if v.id == version_id), None)
            if not selected_version:
                raise NotFoundError(f"Package version {version_id} not found for case {case_id}.")
        elif versions:
            selected_version = next((v for v in versions if v.is_current), versions[0])

        m_map = self._get_project_membership_map(project_id)
        all_signoffs = self.signoff_repo.list_by_case(case.id)
        status_history = self.history_repo.list_by_case(case.id)

        # Load deliveries & acknowledgements for this case
        all_deliveries = list(
            self.session.execute(
                select(HandoverDelivery)
                .where(HandoverDelivery.case_id == case.id)
                .order_by(HandoverDelivery.delivered_at.desc())
            )
            .scalars()
            .all()
        )
        all_acks = self.ack_repo.list_by_case(case.id)
        ack_by_delivery = {a.delivery_id: a for a in all_acks}

        # Load Stage 6 audit events
        audit_logs = list(
            self.session.execute(
                select(AuditLog)
                .where(
                    AuditLog.project_id == project_id,
                    AuditLog.event_type.like("handover.%"),
                )
                .order_by(AuditLog.created_at.desc())
                .limit(80)
            )
            .scalars()
            .all()
        )
        stage6_prefixes = (
            "handover.signoff.",
            "handover.reviewer.",
            "handover.package.published",
            "handover.package.delivered",
            "handover.delivery.",
            "handover.case.status_changed",
        )
        case_id_str = str(case.id)
        version_ids_str = {str(v.id) for v in versions}
        signoff_ids_str = {str(s.id) for s in all_signoffs}
        delivery_ids_str = {str(d.id) for d in all_deliveries}
        filtered_audits: list[AuditLog] = []
        extra_uids: set[uuid.UUID] = {
            u
            for u in (case.departing_member_id, case.successor_id, case.assigned_reviewer_id)
            if u
        }
        for s in all_signoffs:
            extra_uids.add(s.signer_user_id)
        for d in all_deliveries:
            extra_uids.add(d.delivered_to_user_id)
            extra_uids.add(d.delivered_by_user_id)
        for a in all_acks:
            extra_uids.add(a.acknowledged_by_user_id)
        for log in audit_logs:
            if not any(log.event_type.startswith(p) for p in stage6_prefixes):
                continue
            meta = log.event_metadata or {}
            if (
                log.resource_id in (case_id_str,)
                or log.resource_id in version_ids_str
                or log.resource_id in signoff_ids_str
                or log.resource_id in delivery_ids_str
                or meta.get("case_id") == case_id_str
            ):
                filtered_audits.append(log)
                if log.actor_user_id:
                    extra_uids.add(log.actor_user_id)

        users_by_id: dict[uuid.UUID, User] = {uid: entry[1] for uid, entry in m_map.items()}
        missing_uids = extra_uids - set(users_by_id.keys())
        if missing_uids:
            for u in self.session.execute(select(User).where(User.id.in_(missing_uids))).scalars().all():
                users_by_id[u.id] = u

        def _uname(uid: uuid.UUID | None) -> str | None:
            if not uid or uid not in users_by_id:
                return None
            return users_by_id[uid].full_name or users_by_id[uid].email

        def _urole(uid: uuid.UUID | None) -> str | None:
            if not uid or uid not in m_map:
                return None
            role = m_map[uid][2]
            return role.name if role else "project_member"

        # Authoritative Readiness Intelligence for selected version
        readiness = None
        if selected_version:
            try:
                readiness = HandoverReadinessEngine(self.session).get_readiness_intelligence(
                    case_id=case.id,
                    version_id=selected_version.id,
                    project_id=project_id,
                    viewer_user_id=viewer_user_id,
                    has_project_manage=has_project_manage or is_org_admin,
                )
            except NotFoundError:
                readiness = None

        approval_eligibility = readiness.approval_eligibility if readiness else None

        # Detect package version change after prior approval
        version_by_id = {v.id: v for v in versions}
        latest_approved_p2_any = next(
            (
                s
                for s in all_signoffs
                if s.signoff_type == SignoffType.REVIEWER_APPROVAL.value
                and s.decision == SignoffDecision.APPROVED.value
            ),
            None,
        )
        package_changed_since_approval = False
        package_change_notice: str | None = None
        if latest_approved_p2_any and selected_version and latest_approved_p2_any.version_id != selected_version.id:
            prev_ver = version_by_id.get(latest_approved_p2_any.version_id)
            package_changed_since_approval = True
            package_change_notice = (
                f"Package changed since previous approval on v{prev_ver.version_number if prev_ver else '?'}. "
                f"Current version v{selected_version.version_number} requires fresh readiness assessment and re-review."
            )

        # Hydrate signoff history
        def _hydrate_signoff(s: HandoverSignoff) -> HandoverSignoffResponse:
            return HandoverSignoffResponse(
                id=s.id,
                case_id=s.case_id,
                version_id=s.version_id,
                signoff_type=s.signoff_type,
                signer_user_id=s.signer_user_id,
                signer_name=_uname(s.signer_user_id),
                decision=s.decision,
                comments=redact_secrets(s.comments) if s.comments else None,
                conditions=redact_secrets(s.conditions) if s.conditions else None,
                package_content_hash=s.package_content_hash,
                affected_sections_json=list(s.affected_sections_json or []),
                is_superseded=bool(s.is_superseded),
                signature_hash=s.signature_hash,
                signed_at=s.signed_at,
                created_at=s.created_at,
            )

        signoff_history = [_hydrate_signoff(s) for s in all_signoffs]

        # Active signoffs on selected version
        sel_signoffs = (
            [s for s in all_signoffs if s.version_id == selected_version.id and not s.is_superseded]
            if selected_version
            else []
        )
        p1_sig = self._latest_active_by_type(sel_signoffs, SignoffType.DEPARTING_SIGNOFF.value)
        p2_sig = self._latest_active_by_type(sel_signoffs, SignoffType.REVIEWER_APPROVAL.value)
        p3_sig = self._latest_active_by_type(
            sel_signoffs, SignoffType.SUCCESSOR_ACKNOWLEDGEMENT.value
        )

        # Hydrate deliveries
        hydrated_deliveries: list[HandoverDeliveryResponse] = []
        for d in all_deliveries:
            ack = ack_by_delivery.get(d.id)
            ack_resp = (
                HandoverAcknowledgementResponse(
                    id=ack.id,
                    delivery_id=ack.delivery_id,
                    acknowledged_by_user_id=ack.acknowledged_by_user_id,
                    acknowledged_by_name=_uname(ack.acknowledged_by_user_id),
                    acknowledgement_notes=(
                        redact_secrets(ack.acknowledgement_notes)
                        if ack.acknowledgement_notes
                        else None
                    ),
                    confirmations_json=dict(ack.confirmations_json or {}),
                    acknowledgement_hash=ack.acknowledgement_hash,
                    acknowledged_at=ack.acknowledged_at,
                    created_at=ack.created_at,
                )
                if ack
                else None
            )
            clar_entries: list[DeliveryClarificationEntry] = []
            for raw in d.clarifications_json or []:
                try:
                    clar_entries.append(
                        DeliveryClarificationEntry(
                            id=str(raw.get("id", "")),
                            mode=str(raw.get("mode", "request")),
                            author_user_id=uuid.UUID(str(raw["author_user_id"])),
                            author_name=raw.get("author_name")
                            or _uname(uuid.UUID(str(raw["author_user_id"]))),
                            notes=redact_secrets(str(raw.get("notes", ""))),
                            created_at=raw["created_at"],
                        )
                    )
                except Exception:
                    continue

            hydrated_deliveries.append(
                HandoverDeliveryResponse(
                    id=d.id,
                    version_id=d.version_id,
                    delivered_to_user_id=d.delivered_to_user_id,
                    delivered_to_name=_uname(d.delivered_to_user_id),
                    delivered_by_user_id=d.delivered_by_user_id,
                    delivered_by_name=_uname(d.delivered_by_user_id),
                    delivery_method=d.delivery_method,
                    artifact_storage_path=d.artifact_storage_path,
                    artifact_checksum=d.artifact_checksum,
                    message=redact_secrets(d.message) if d.message else None,
                    is_active=bool(d.is_active),
                    delivered_at=d.delivered_at,
                    expires_at=d.expires_at,
                    acknowledged=ack is not None,
                    acknowledgement=ack_resp,
                    clarifications=clar_entries,
                    created_at=d.created_at,
                )
            )

        # Build the 3 authoritative SignoffPhaseDetail objects
        p1_completed = bool(p1_sig and p1_sig.decision == SignoffDecision.APPROVED.value)
        p2_approved = bool(p2_sig and p2_sig.decision == SignoffDecision.APPROVED.value)
        p3_acked = bool(p3_sig and p3_sig.decision == SignoffDecision.APPROVED.value)

        # Phase 1 eligibility
        p1_reqs: list[str] = []
        if not selected_version:
            p1_reqs.append("Assemble a package version before submitting Phase 1 sign-off.")
        p1_can_act = False
        p1_inelig: str | None = None
        if p1_completed:
            p1_inelig = "Phase 1 departing sign-off is already complete for this package version."
        elif case.status in (
            HandoverCaseStatus.APPROVED.value,
            HandoverCaseStatus.DELIVERED.value,
            HandoverCaseStatus.ACKNOWLEDGED.value,
            HandoverCaseStatus.TRANSFERRED.value,
        ):
            p1_inelig = f"Phase 1 is locked in status '{case.status}'."
        elif viewer_user_id != case.departing_member_id and not is_org_admin:
            p1_inelig = "Only the designated departing member (or an administrator) can submit Phase 1 sign-off."
        elif not selected_version:
            p1_inelig = "No assembled package version available."
        else:
            p1_can_act = True

        # Phase 2 eligibility
        p2_reqs: list[str] = []
        if not p1_completed:
            p2_reqs.append("Phase 1 departing-owner sign-off must be completed on this version first.")
        if not readiness:
            p2_reqs.append("Run a readiness assessment on this package version.")
        elif approval_eligibility and not approval_eligibility.is_eligible_for_approval:
            p2_reqs.extend(approval_eligibility.blocking_requirements)

        p2_status = "pending"
        if p2_approved:
            p2_status = "completed"
        elif p2_sig and p2_sig.decision == SignoffDecision.REJECTED.value:
            p2_status = "rejected"
        elif p2_sig and p2_sig.decision == SignoffDecision.RETURNED_FOR_REVISION.value:
            p2_status = "returned_for_revision"
        elif p2_reqs:
            p2_status = "blocked"
        elif case.status in (HandoverCaseStatus.REVIEW_PENDING.value, HandoverCaseStatus.UNDER_REVIEW.value):
            p2_status = "in_progress"

        p2_can_act = False
        p2_inelig: str | None = None
        if p2_approved:
            p2_inelig = "Phase 2 managerial approval is already complete for this package version."
        elif viewer_user_id == case.departing_member_id:
            p2_inelig = "Separation of duties: the departing member cannot approve their own handover."
        elif case.assigned_reviewer_id and viewer_user_id != case.assigned_reviewer_id and not is_org_admin:
            p2_inelig = f"Assigned to independent reviewer {_uname(case.assigned_reviewer_id)}."
        elif not (can_review or can_approve or is_org_admin):
            p2_inelig = "Requires 'handover.review' / 'handover.approve' permission."
        elif case.status not in (
            HandoverCaseStatus.REVIEW_PENDING.value,
            HandoverCaseStatus.UNDER_REVIEW.value,
        ):
            p2_inelig = f"Case must be in 'review_pending' or 'under_review' (currently '{case.status}')."
        else:
            p2_can_act = True

        # Phase 3 eligibility
        active_deliveries = [d for d in hydrated_deliveries if d.is_active]
        viewer_delivery = next(
            (d for d in active_deliveries if d.delivered_to_user_id == viewer_user_id), None
        )
        p3_reqs: list[str] = []
        if not p2_approved:
            p3_reqs.append("Phase 2 managerial approval must be granted first.")
        if not active_deliveries:
            p3_reqs.append("Approved handover package must be published to the recipient first.")

        p3_status = "completed" if p3_acked else ("in_progress" if active_deliveries else "pending")
        p3_can_act = False
        p3_inelig: str | None = None
        if p3_acked:
            p3_inelig = "Published handover package has already been acknowledged."
        elif not active_deliveries or case.status != HandoverCaseStatus.DELIVERED.value:
            p3_inelig = "Recipient acknowledgement opens only after controlled publication."
        elif not viewer_delivery:
            p3_inelig = "Only the designated recipient of the published delivery can acknowledge receipt."
        elif not can_acknowledge:
            p3_inelig = "Requires 'handover.acknowledge' permission."
        else:
            p3_can_act = True

        phases = [
            SignoffPhaseDetail(
                phase_number=1,
                phase_name="Phase 1: Departing Member Sign-Off",
                signoff_type=SignoffType.DEPARTING_SIGNOFF.value,
                purpose="Outgoing owner confirms that compiled package domains, operational context, and transfer materials are ready for independent review.",
                assigned_user_id=case.departing_member_id,
                assigned_user_name=_uname(case.departing_member_id),
                assigned_user_role=_urole(case.departing_member_id),
                required_permission="handover.review (departing owner)",
                status="completed" if p1_completed else ("in_progress" if selected_version else "pending"),
                viewer_can_act=p1_can_act,
                viewer_ineligibility_reason=p1_inelig,
                pending_requirements=p1_reqs,
                latest_decision=_hydrate_signoff(p1_sig) if p1_sig else None,
            ),
            SignoffPhaseDetail(
                phase_number=2,
                phase_name="Phase 2: Independent Managerial Approval",
                signoff_type=SignoffType.REVIEWER_APPROVAL.value,
                purpose="Independent reviewer/manager verifies readiness gates, approves the immutable package snapshot, or returns it with mandatory change requests.",
                assigned_user_id=case.assigned_reviewer_id,
                assigned_user_name=_uname(case.assigned_reviewer_id),
                assigned_user_role=_urole(case.assigned_reviewer_id),
                required_permission="handover.approve (independent reviewer)",
                status=p2_status,
                viewer_can_act=p2_can_act,
                viewer_ineligibility_reason=p2_inelig,
                pending_requirements=p2_reqs,
                latest_decision=_hydrate_signoff(p2_sig) if p2_sig else None,
            ),
            SignoffPhaseDetail(
                phase_number=3,
                phase_name="Phase 3: Published Package Recipient Acknowledgement",
                signoff_type=SignoffType.SUCCESSOR_ACKNOWLEDGEMENT.value,
                purpose="Receiving participant reviews the complete published package and confirms formal receipt (distinct from managerial approval and individual responsibility acks).",
                assigned_user_id=case.successor_id,
                assigned_user_name=_uname(case.successor_id),
                assigned_user_role=_urole(case.successor_id),
                required_permission="handover.acknowledge (designated recipient)",
                status=p3_status,
                viewer_can_act=p3_can_act,
                viewer_ineligibility_reason=p3_inelig,
                pending_requirements=p3_reqs,
                latest_decision=_hydrate_signoff(p3_sig) if p3_sig else None,
            ),
        ]

        # Publication Status
        pub_blocking: list[str] = []
        if case.status != HandoverCaseStatus.APPROVED.value and not active_deliveries:
            pub_blocking.append(
                f"Case must be in 'approved' status before publication (currently '{case.status}')."
            )
        if not p1_completed:
            pub_blocking.append("Phase 1 departing sign-off must be complete on this package version.")
        if not p2_approved:
            pub_blocking.append("Phase 2 managerial approval must be complete on this package version.")
        if package_changed_since_approval:
            pub_blocking.append("Package version changed since previous approval; re-review required.")
        if not can_deliver and not is_org_admin:
            pub_blocking.append("Requires 'handover.deliver' permission to publish.")

        latest_pub = active_deliveries[0] if active_deliveries else None
        pub_ver = version_by_id.get(latest_pub.version_id) if latest_pub else None

        publication = SignoffPublicationStatus(
            is_eligible_to_publish=(len(pub_blocking) == 0 and not active_deliveries),
            is_published=len(active_deliveries) > 0,
            blocking_reasons=pub_blocking,
            approved_version_id=selected_version.id if (selected_version and p2_approved) else None,
            approved_version_number=(
                selected_version.version_number if (selected_version and p2_approved) else None
            ),
            approved_content_hash=(
                selected_version.content_hash if (selected_version and p2_approved) else None
            ),
            published_version_id=latest_pub.version_id if latest_pub else None,
            published_version_number=pub_ver.version_number if pub_ver else None,
            published_content_hash=latest_pub.artifact_checksum if latest_pub else None,
            published_at=latest_pub.delivered_at if latest_pub else None,
            published_by_name=latest_pub.delivered_by_name if latest_pub else None,
            deliveries=hydrated_deliveries,
        )

        # Lifecycle Summary
        previous_status = status_history[0].previous_status if status_history else None
        responsible_role, responsible_user = _responsible_for_status(
            case, _uname(case.departing_member_id), _uname(case.assigned_reviewer_id), _uname(case.successor_id)
        )
        blocked_transitions: list[str] = []
        if case.status in (HandoverCaseStatus.REVIEW_PENDING.value, HandoverCaseStatus.UNDER_REVIEW.value):
            blocked_transitions.extend(p2_reqs)
        elif case.status == HandoverCaseStatus.APPROVED.value:
            blocked_transitions.extend(pub_blocking)
        elif case.status in (HandoverCaseStatus.READINESS_ASSESSED.value, HandoverCaseStatus.ASSEMBLED.value):
            if approval_eligibility and not approval_eligibility.is_eligible_for_approval:
                blocked_transitions.extend(approval_eligibility.blocking_requirements)

        lifecycle = SignoffLifecycleSummary(
            current_status=case.status,
            previous_status=previous_status,
            next_permitted_transitions=sorted(VALID_TRANSITIONS.get(case.status, set())),
            responsible_role_label=responsible_role,
            responsible_user_name=responsible_user,
            blocked_transition_reasons=blocked_transitions,
            case_version=case.version,
            status_history=[HandoverStatusHistoryResponse.model_validate(h) for h in status_history[:25]],
        )

        # Eligible independent reviewers (active project members excluding departing owner) & recipients
        eligible_reviewers: list[ResponsibilityParticipantSummary] = []
        eligible_recipients: list[ResponsibilityParticipantSummary] = []
        for uid, (pm, usr, role) in m_map.items():
            is_active = pm.status == "active" and getattr(usr, "status", "active") == "active"
            if not is_active:
                continue
            summary = ResponsibilityParticipantSummary(
                user_id=uid,
                full_name=usr.full_name or usr.email,
                email=usr.email,
                role_name=role.name if role else "project_member",
                membership_status=pm.status,
                is_active=True,
                is_departing_owner=(uid == case.departing_member_id),
                is_case_successor=(uid == case.successor_id),
                has_handover_access=True,
            )
            eligible_recipients.append(summary)
            if uid != case.departing_member_id:
                eligible_reviewers.append(summary)

        # Activity history
        activity_history: list[HandoverStage5ActivityItem] = []
        for log in filtered_audits[:35]:
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
                    summary=_summarize_stage6_audit(log.event_type, meta),
                    metadata_json=meta,
                    created_at=log.created_at,
                )
            )

        return HandoverSignoffWorkspaceResponse(
            case_id=case.id,
            project_id=project_id,
            case_title=case.title,
            case_status=case.status,
            case_version=case.version,
            departing_member_id=case.departing_member_id,
            departing_member_name=_uname(case.departing_member_id),
            successor_id=case.successor_id,
            successor_name=_uname(case.successor_id),
            assigned_reviewer_id=case.assigned_reviewer_id,
            assigned_reviewer_name=_uname(case.assigned_reviewer_id),
            selected_version_id=selected_version.id if selected_version else None,
            selected_version_number=selected_version.version_number if selected_version else None,
            selected_content_hash=selected_version.content_hash if selected_version else None,
            package_changed_since_approval=package_changed_since_approval,
            package_change_notice=package_change_notice,
            readiness_score=readiness.overall_score if readiness else None,
            readiness_level=readiness.overall_level if readiness else None,
            readiness_assessed_at=readiness.assessed_at if readiness else None,
            approval_eligibility=approval_eligibility,
            lifecycle=lifecycle,
            phases=phases,
            publication=publication,
            eligible_reviewers=eligible_reviewers,
            eligible_recipients=eligible_recipients,
            signoff_history=signoff_history,
            activity_history=activity_history,
        )

    def _record_signoff(
        self,
        *,
        case: HandoverCase,
        version: HandoverPackageVersion,
        signoff_type: str,
        signer_user_id: uuid.UUID,
        decision: str,
        comments: str | None,
        conditions: str | None = None,
        affected_sections: list[str] | None = None,
    ) -> HandoverSignoff:
        now = utc_now()
        pkg_hash = version.content_hash or ""
        sig_data = (
            f"{version.id}:{pkg_hash}:{signoff_type}:{decision}:{signer_user_id}:"
            f"{now.isoformat()}:{comments or ''}"
        )
        sig_hash = hashlib.sha256(sig_data.encode("utf-8")).hexdigest()

        signoff = HandoverSignoff(
            organisation_id=case.organisation_id,
            project_id=case.project_id,
            case_id=case.id,
            version_id=version.id,
            signoff_type=signoff_type,
            signer_user_id=signer_user_id,
            decision=decision,
            comments=comments,
            conditions=conditions,
            package_content_hash=version.content_hash,
            affected_sections_json=list(affected_sections or []),
            is_superseded=False,
            signed_at=now,
            signature_hash=sig_hash,
        )
        created_sig = self.signoff_repo.create(signoff)

        self.audit_service.record_event(
            event_type="handover.signoff.recorded",
            resource_type="handover_signoff",
            resource_id=str(created_sig.id),
            actor_user_id=signer_user_id,
            organisation_id=case.organisation_id,
            project_id=case.project_id,
            outcome=AuditOutcome.SUCCESS.value,
            metadata={
                "case_id": str(case.id),
                "version_id": str(version.id),
                "package_content_hash": version.content_hash,
                "signoff_type": signoff_type,
                "decision": decision,
                "affected_sections": list(affected_sections or []),
                "signature_hash": sig_hash,
            },
        )
        return created_sig


def _responsible_for_status(
    case: HandoverCase,
    departing_name: str | None,
    reviewer_name: str | None,
    successor_name: str | None,
) -> tuple[str, str | None]:
    st = case.status
    if st in (
        HandoverCaseStatus.DRAFT.value,
        HandoverCaseStatus.ASSEMBLING.value,
        HandoverCaseStatus.ASSEMBLED.value,
        HandoverCaseStatus.READINESS_PENDING.value,
        HandoverCaseStatus.READINESS_ASSESSED.value,
        HandoverCaseStatus.REJECTED.value,
    ):
        return ("Departing Member", departing_name)
    if st in (HandoverCaseStatus.REVIEW_PENDING.value, HandoverCaseStatus.UNDER_REVIEW.value):
        return ("Independent Reviewer / Manager", reviewer_name)
    if st == HandoverCaseStatus.APPROVED.value:
        return ("Project Manager (Publication)", reviewer_name)
    if st == HandoverCaseStatus.DELIVERED.value:
        return ("Incoming Recipient", successor_name)
    if st == HandoverCaseStatus.ACKNOWLEDGED.value:
        return ("Project Manager (Transfer Closeout)", reviewer_name)
    return ("Project Governance", None)


def _summarize_stage6_audit(event_type: str, meta: dict[str, Any]) -> str:
    if event_type == "handover.signoff.recorded":
        stype = str(meta.get("signoff_type", "")).replace("_", " ")
        dec = str(meta.get("decision", "")).replace("_", " ")
        return f"Recorded {stype}: {dec}."
    if event_type == "handover.signoff.reopened":
        return f"Reopened {str(meta.get('signoff_type', '')).replace('_', ' ')}: {meta.get('reason', '')}"
    if event_type == "handover.signoff.superseded_by_new_version":
        return f"Superseded {meta.get('superseded_signoff_count', 0)} prior signoff(s) after assembling v{meta.get('new_version_number', '?')}."
    if event_type == "handover.signoff.blocker_override":
        return "Organisation administrator documented blocker override rationale."
    if event_type == "handover.reviewer.assigned":
        return "Assigned independent reviewer to handover case."
    if event_type in ("handover.package.published", "handover.package.delivered"):
        return f"Published approved package v{meta.get('version_number', '?')} to {meta.get('recipients_count', 1)} recipient(s)."
    if event_type == "handover.delivery.acknowledged":
        return "Recipient formally acknowledged published handover package."
    if event_type == "handover.delivery.clarification_requested":
        return "Recipient requested clarification on published handover package."
    if event_type == "handover.delivery.clarification_responded":
        return "Posted clarification response on published handover package."
    if event_type == "handover.case.status_changed":
        return f"Lifecycle transitioned {meta.get('previous_status', '?')} → {meta.get('new_status', '?')}."
    return event_type
