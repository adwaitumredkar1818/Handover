"""Handover Readiness Assessment Engine & Readiness Intelligence Service.

Platform: The Handover
Module: Handover Workspace (Module 4 / Knowledge Transfer Area)

Enforces:
1. Multi-dimensional evaluation across 9 canonical categories
2. Deterministic scoring (0-100) with clear blocker and warning attribution
3. Human sign-off gating (packages with active blockers cannot be approved)
4. Full immutable audit trail of readiness assessments per package version
5. Live Verification Intelligence, Conflict Management, Checklist, and Evidence
   Completeness integration with strict RBAC and fail-closed source ACL enforcement
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import NotFoundError
from app.core.security import utc_now
from app.models.enums import (
    AuditOutcome,
    ConflictResolutionState,
    EpistemicStatus,
    HandoverCaseStatus,
    HandoverReadinessCategory,
    KnowledgeReviewStatus,
    ReadinessLevel,
    RelationshipVerificationStatus,
    SignoffDecision,
    SignoffType,
    TransferStatus,
    VerificationCaseStatus,
)
from app.models.evidence import EvidenceItem
from app.models.handover import (
    HandoverCase,
    HandoverChecklist,
    HandoverPackageVersion,
    HandoverReadinessAssessment,
    HandoverResponsibilityTransfer,
    HandoverSignoff,
)
from app.models.integration import SourceAccessPolicy
from app.models.knowledge import KnowledgeEvidenceLink, KnowledgeItem
from app.models.relationship import KnowledgeRelationship
from app.models.user import User
from app.models.verification import (
    VerificationCase,
    VerificationConflict,
    VerificationReviewEvent,
)
from app.repositories.audit import AuditLogRepository
from app.repositories.handover import (
    HandoverCaseRepository,
    HandoverChecklistRepository,
    HandoverPackageVersionRepository,
    HandoverReadinessRepository,
    HandoverResponsibilityTransferRepository,
    HandoverSignoffRepository,
)
from app.schemas.handover import (
    HandoverReadinessAssessmentResponse,
    HandoverReadinessSummaryResponse,
    ReadinessApprovalEligibility,
    ReadinessAssessmentHistoryItem,
    ReadinessChecklistGroupSummary,
    ReadinessChecklistSummary,
    ReadinessConflictItem,
    ReadinessConflictSummary,
    ReadinessEvidenceQualitySummary,
    ReadinessReviewEventItem,
    ReadinessStructuredBlockerResponse,
    ReadinessVerificationSummary,
)
from app.services.audit import AuditService
from app.services.handover_case import HandoverCaseService
from app.services.handover_eligibility import check_evidence_accessibility
from app.services.handover_sections import redact_secrets

CATEGORY_WEIGHTS: dict[str, float] = {
    HandoverReadinessCategory.EVIDENCE_COVERAGE.value: 0.15,
    HandoverReadinessCategory.VERIFICATION_COMPLETENESS.value: 0.20,
    HandoverReadinessCategory.CONFLICT_RESOLUTION.value: 0.15,
    HandoverReadinessCategory.KNOWLEDGE_FRESHNESS.value: 0.10,
    HandoverReadinessCategory.RELATIONSHIP_VALIDATION.value: 0.10,
    HandoverReadinessCategory.RESPONSIBILITY_COVERAGE.value: 0.15,
    HandoverReadinessCategory.RISK_ASSESSMENT.value: 0.05,
    HandoverReadinessCategory.DEPENDENCY_MAPPING.value: 0.10,
}

CANONICAL_CATEGORY_ORDER: list[str] = [
    HandoverReadinessCategory.EVIDENCE_COVERAGE.value,
    HandoverReadinessCategory.VERIFICATION_COMPLETENESS.value,
    HandoverReadinessCategory.CONFLICT_RESOLUTION.value,
    HandoverReadinessCategory.KNOWLEDGE_FRESHNESS.value,
    HandoverReadinessCategory.RELATIONSHIP_VALIDATION.value,
    HandoverReadinessCategory.RESPONSIBILITY_COVERAGE.value,
    HandoverReadinessCategory.RISK_ASSESSMENT.value,
    HandoverReadinessCategory.DEPENDENCY_MAPPING.value,
    HandoverReadinessCategory.OVERALL_QUALITY.value,
]

CATEGORY_METADATA: dict[str, dict[str, str]] = {
    HandoverReadinessCategory.EVIDENCE_COVERAGE.value: {
        "label": "Evidence Coverage",
        "tab": "evidence",
    },
    HandoverReadinessCategory.VERIFICATION_COMPLETENESS.value: {
        "label": "Verification Completeness",
        "tab": "decisions",
    },
    HandoverReadinessCategory.CONFLICT_RESOLUTION.value: {
        "label": "Conflict Resolution",
        "tab": "risks",
    },
    HandoverReadinessCategory.KNOWLEDGE_FRESHNESS.value: {
        "label": "Knowledge Freshness",
        "tab": "overview",
    },
    HandoverReadinessCategory.RELATIONSHIP_VALIDATION.value: {
        "label": "Relationship Validation",
        "tab": "dependencies",
    },
    HandoverReadinessCategory.RESPONSIBILITY_COVERAGE.value: {
        "label": "Responsibility Coverage",
        "tab": "responsibilities",
    },
    HandoverReadinessCategory.RISK_ASSESSMENT.value: {
        "label": "Risk Assessment",
        "tab": "risks",
    },
    HandoverReadinessCategory.DEPENDENCY_MAPPING.value: {
        "label": "Dependency Mapping",
        "tab": "dependencies",
    },
    HandoverReadinessCategory.OVERALL_QUALITY.value: {
        "label": "Overall Quality",
        "tab": "overview",
    },
}

RESOLVED_CONFLICT_STATES: set[str] = {
    ConflictResolutionState.RESOLVED.value,
    ConflictResolutionState.RECONCILED.value,
    ConflictResolutionState.SUPERSEDED.value,
    ConflictResolutionState.DISMISSED.value,
}

NEXT_LIFECYCLE_MAP: dict[str, str | None] = {
    HandoverCaseStatus.DRAFT.value: HandoverCaseStatus.ASSEMBLED.value,
    HandoverCaseStatus.ASSEMBLING.value: HandoverCaseStatus.ASSEMBLED.value,
    HandoverCaseStatus.ASSEMBLED.value: HandoverCaseStatus.READINESS_ASSESSED.value,
    HandoverCaseStatus.READINESS_PENDING.value: HandoverCaseStatus.READINESS_ASSESSED.value,
    HandoverCaseStatus.READINESS_ASSESSED.value: HandoverCaseStatus.REVIEW_PENDING.value,
    HandoverCaseStatus.REVIEW_PENDING.value: HandoverCaseStatus.UNDER_REVIEW.value,
    HandoverCaseStatus.UNDER_REVIEW.value: HandoverCaseStatus.APPROVED.value,
    HandoverCaseStatus.REJECTED.value: HandoverCaseStatus.REVIEW_PENDING.value,
    HandoverCaseStatus.APPROVED.value: HandoverCaseStatus.DELIVERED.value,
    HandoverCaseStatus.DELIVERED.value: HandoverCaseStatus.ACKNOWLEDGED.value,
    HandoverCaseStatus.ACKNOWLEDGED.value: HandoverCaseStatus.TRANSFERRED.value,
    HandoverCaseStatus.TRANSFERRED.value: HandoverCaseStatus.ARCHIVED.value,
    HandoverCaseStatus.ARCHIVED.value: None,
    HandoverCaseStatus.SUPERSEDED.value: None,
}


def _score_to_level(score: int, has_blockers: bool) -> str:
    if has_blockers or score < 50:
        return ReadinessLevel.NOT_READY.value
    if score >= 90:
        return ReadinessLevel.READY.value
    if score >= 75:
        return ReadinessLevel.READY_WITH_WARNINGS.value
    return ReadinessLevel.PARTIALLY_READY.value


def _val(x: Any) -> str:
    if hasattr(x, "value"):
        return str(x.value)
    return str(x) if x is not None else ""


def _sort_ts(dt: datetime | None) -> float:
    """Return a timezone-safe monotonic float timestamp for sorting."""
    if dt is None:
        return 0.0
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC).timestamp()
    return dt.timestamp()


def _latest_assessments_by_category(
    assessments: list[HandoverReadinessAssessment],
) -> list[HandoverReadinessAssessment]:
    """Select the single most recent persisted assessment per canonical category."""
    latest: dict[str, HandoverReadinessAssessment] = {}
    for row in sorted(assessments, key=lambda a: (_sort_ts(a.assessed_at), _sort_ts(a.created_at))):
        latest[row.category] = row
    ordered: list[HandoverReadinessAssessment] = []
    for cat in CANONICAL_CATEGORY_ORDER:
        if cat in latest:
            ordered.append(latest[cat])
    for cat, row in latest.items():
        if cat not in CANONICAL_CATEGORY_ORDER:
            ordered.append(row)
    return ordered


class HandoverReadinessEngine:
    """Evaluates whether an assembled handover package is ready for human review and sign-off."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.case_repo = HandoverCaseRepository(session)
        self.version_repo = HandoverPackageVersionRepository(session)
        self.readiness_repo = HandoverReadinessRepository(session)
        self.resp_repo = HandoverResponsibilityTransferRepository(session)
        self.checklist_repo = HandoverChecklistRepository(session)
        self.signoff_repo = HandoverSignoffRepository(session)
        self.case_service = HandoverCaseService(session)
        self.audit_service = AuditService(audit_repository=AuditLogRepository(session))

    def assess_version(
        self,
        version_id: uuid.UUID,
        *,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        notes: str | None = None,
        has_project_manage: bool = True,
    ) -> HandoverReadinessSummaryResponse:
        """Run 9-category readiness assessment on an assembled package version and persist snapshot."""
        version = self.version_repo.get_by_id(version_id, load_sections=True)
        if not version or version.project_id != project_id:
            raise NotFoundError(f"Package version {version_id} not found in this project.")

        case = self.case_service.get_case(
            version.case_id, project_id=project_id, load_relationships=False
        )

        # 1. Evidence Coverage
        stmt_ki = select(KnowledgeItem).where(
            KnowledgeItem.project_id == project_id,
            KnowledgeItem.is_deleted.is_(False),
        )
        all_kis = list(self.session.execute(stmt_ki).scalars().all())
        total_kis = len(all_kis)

        stmt_linked_ki = (
            select(func.count(func.distinct(KnowledgeEvidenceLink.knowledge_item_id)))
            .join(KnowledgeItem, KnowledgeEvidenceLink.knowledge_item_id == KnowledgeItem.id)
            .where(KnowledgeItem.project_id == project_id, KnowledgeItem.is_deleted.is_(False))
        )
        linked_ki_count = int(self.session.execute(stmt_linked_ki).scalar_one() or 0)

        cov_score = int((linked_ki_count / total_kis * 100)) if total_kis > 0 else 100
        cov_blockers: list[str] = []
        cov_warnings: list[str] = []
        cov_missing: list[str] = []
        cov_recs: list[str] = []
        if total_kis == 0:
            cov_warnings.append("No active knowledge items found for this project.")
            cov_missing.append("Upload project documents or sync connected sources to extract knowledge.")
            cov_recs.append("Connect authorised sources or upload documents in Evidence Center.")
        elif cov_score < 70:
            missing_ev_cnt = total_kis - linked_ki_count
            cov_warnings.append(f"Only {cov_score}% of knowledge items have cited supporting evidence.")
            cov_missing.append(f"{missing_ev_cnt} knowledge items lack supporting source evidence links.")
            cov_recs.append("Attach supporting evidence citations in Verification Center.")

        # 2. Verification Completeness
        verified_kis = [
            k
            for k in all_kis
            if k.epistemic_status == EpistemicStatus.HUMAN_VERIFIED.value
            and k.review_status == KnowledgeReviewStatus.APPROVED.value
        ]
        ver_score = int((len(verified_kis) / total_kis * 100)) if total_kis > 0 else 100
        ver_blockers: list[str] = []
        ver_warnings: list[str] = []
        ver_missing: list[str] = []
        ver_recs: list[str] = []
        unverified_count = total_kis - len(verified_kis)
        if unverified_count > 0:
            ver_missing.append(
                f"{unverified_count} of {total_kis} knowledge items have not completed reviewer verification."
            )
            ver_recs.append(
                "Review and approve eligible findings in Verification Center, then re-assemble the handover package."
            )
            if ver_score < 50:
                ver_blockers.append(
                    f"{unverified_count} knowledge items have not been verified by a human reviewer."
                )
            else:
                ver_warnings.append(f"{unverified_count} knowledge items remain unverified.")

        # 3. Conflict Resolution (counts ALL active non-resolved states)
        stmt_conflicts = select(VerificationConflict).where(
            VerificationConflict.project_id == project_id,
            VerificationConflict.resolution_state.notin_(RESOLVED_CONFLICT_STATES),
        )
        unresolved_conflicts = list(self.session.execute(stmt_conflicts).scalars().all())
        critical_high_conflicts = [
            c for c in unresolved_conflicts if str(c.priority or "").lower() in ("critical", "high")
        ]
        conf_blockers: list[str] = []
        conf_warnings: list[str] = []
        conf_missing: list[str] = []
        conf_recs: list[str] = []
        if unresolved_conflicts:
            conf_score = max(0, 100 - len(unresolved_conflicts) * 25)
            conf_blockers.append(
                f"Found {len(unresolved_conflicts)} unresolved cross-source contradictions."
            )
            if critical_high_conflicts:
                conf_blockers.append(
                    f"{len(critical_high_conflicts)} unresolved critical/high-priority conflicts block approval."
                )
            conf_missing.append(
                f"Human resolution required for {len(unresolved_conflicts)} open contradictions."
            )
            conf_recs.append("Investigate and resolve open contradictions in Conflict Management.")
        else:
            conf_score = 100

        # 4. Knowledge Freshness
        stale_kis = [k for k in all_kis if getattr(k, "is_stale", False)]
        fresh_score = max(0, 100 - len(stale_kis) * 15)
        fresh_blockers: list[str] = []
        fresh_warnings: list[str] = []
        fresh_missing: list[str] = []
        fresh_recs: list[str] = []
        if stale_kis:
            fresh_warnings.append(f"{len(stale_kis)} knowledge items are marked stale.")
            fresh_missing.append(f"{len(stale_kis)} outdated knowledge items need re-validation.")
            fresh_recs.append("Re-sync connected sources and refresh stale findings.")

        # 5. Relationship Validation
        stmt_rels = select(KnowledgeRelationship).where(
            KnowledgeRelationship.project_id == project_id
        )
        all_rels = list(self.session.execute(stmt_rels).scalars().all())
        total_rels = len(all_rels)
        verified_rels = [
            r
            for r in all_rels
            if r.verification_status == RelationshipVerificationStatus.VERIFIED.value
        ]
        rel_score = int((len(verified_rels) / total_rels * 100)) if total_rels > 0 else 100
        rel_blockers: list[str] = []
        rel_warnings: list[str] = []
        rel_missing: list[str] = []
        rel_recs: list[str] = []
        if total_rels > 0 and rel_score < 60:
            rel_warnings.append(f"Only {rel_score}% of graph relationships have been verified.")
            rel_missing.append(f"{total_rels - len(verified_rels)} relationships awaiting validation.")
            rel_recs.append("Confirm key component relationships in Relationship Explorer.")

        # 6. Responsibility Coverage (Stage 5 live transfer lifecycle integration)
        stmt_transfers = select(HandoverResponsibilityTransfer).where(
            HandoverResponsibilityTransfer.case_id == case.id
        )
        transfers = list(self.session.execute(stmt_transfers).scalars().all())
        resp_blockers: list[str] = []
        resp_warnings: list[str] = []
        resp_missing: list[str] = []
        resp_recs: list[str] = []
        if not transfers:
            resp_score = 40
            resp_warnings.append(
                "No explicit responsibility transfers mapped for the departing member."
            )
            resp_missing.append("Departing member responsibilities have not been mapped to successors.")
            resp_recs.append("Map component responsibilities and assign successors in Ownership.")
        else:
            unassigned = [t for t in transfers if not t.proposed_successor_id]
            critical_unassigned = [
                t
                for t in unassigned
                if (t.priority or "medium").lower() in ("critical", "high")
            ]
            blocked_transfers = [
                t for t in transfers if t.transfer_status == TransferStatus.BLOCKED.value
            ]
            reopened_or_clar = [
                t
                for t in transfers
                if t.transfer_status
                in (
                    TransferStatus.REOPENED.value,
                    TransferStatus.CLARIFICATION_REQUESTED.value,
                )
            ]
            awaiting_ack = [
                t
                for t in transfers
                if t.transfer_status == TransferStatus.AWAITING_SUCCESSOR_ACKNOWLEDGEMENT.value
            ]
            acknowledged = [
                t
                for t in transfers
                if t.transfer_status
                in (TransferStatus.ACKNOWLEDGED.value, TransferStatus.COMPLETED.value)
            ]
            missing_ops_ctx = [t for t in transfers if not (t.operational_context or "").strip()]

            credit_sum = 0.0
            for t in transfers:
                if not t.proposed_successor_id:
                    credit_sum += 0.0
                elif t.transfer_status in (
                    TransferStatus.ACKNOWLEDGED.value,
                    TransferStatus.COMPLETED.value,
                ):
                    credit_sum += 1.0
                elif t.transfer_status == TransferStatus.AWAITING_SUCCESSOR_ACKNOWLEDGEMENT.value:
                    credit_sum += 0.75
                elif t.transfer_status in (
                    TransferStatus.BLOCKED.value,
                    TransferStatus.REOPENED.value,
                    TransferStatus.CLARIFICATION_REQUESTED.value,
                ):
                    credit_sum += 0.25
                else:
                    credit_sum += 0.50

            resp_score = int(round((credit_sum / len(transfers)) * 100))

            if critical_unassigned:
                resp_blockers.append(
                    f"{len(critical_unassigned)} critical/high-priority responsibility transfer(s) have no assigned successor."
                )
            if blocked_transfers:
                resp_blockers.append(
                    f"{len(blocked_transfers)} responsibility transfer(s) are currently blocked."
                )
            if unassigned:
                resp_warnings.append(
                    f"{len(unassigned)} of {len(transfers)} mapped responsibilities have no proposed successor."
                )
                resp_missing.append(f"{len(unassigned)} mapped responsibilities lack a successor.")
                resp_recs.append("Assign an eligible incoming successor for each open responsibility.")
            if reopened_or_clar:
                resp_warnings.append(
                    f"{len(reopened_or_clar)} responsibility transfer(s) are reopened or require clarification."
                )
                resp_missing.append(
                    f"{len(reopened_or_clar)} responsibility transfer(s) require clarification or re-acknowledgement."
                )
                resp_recs.append("Resolve open clarification requests in the Ownership tab.")
            if awaiting_ack:
                resp_warnings.append(
                    f"{len(awaiting_ack)} responsibility transfer(s) are awaiting incoming successor acknowledgement."
                )
                resp_missing.append(
                    f"{len(awaiting_ack)} confirmed transfers have not yet been acknowledged by the successor."
                )
                resp_recs.append("Have the assigned successor review and acknowledge transferred responsibilities.")
            if missing_ops_ctx:
                resp_missing.append(
                    f"{len(missing_ops_ctx)} responsibility transfer(s) lack documented operational context."
                )
            if not resp_recs and len(acknowledged) < len(transfers):
                resp_recs.append(
                    "Confirm outgoing ownership and complete successor acknowledgement in Ownership."
                )

        # 7. Risk Assessment
        risk_kis = [
            k
            for k in all_kis
            if k.category in ("bugs_blockers_risks", "risks_blockers_questions")
        ]
        risk_score = 100
        risk_blockers: list[str] = []
        risk_warnings: list[str] = []
        risk_missing: list[str] = []
        risk_recs: list[str] = []
        if not risk_kis:
            risk_warnings.append("No active bugs, blockers, or risks documented in this project.")
            risk_missing.append("No documented risks or operational caveats captured.")
            risk_recs.append("Review known issues and open limitations in Risks & Issues.")

        # 8. Dependency Mapping
        dep_kis = [
            k
            for k in all_kis
            if k.category in ("dependencies", "dependencies_relationships")
        ]
        dep_score = 100 if (dep_kis or all_rels) else 60
        dep_blockers: list[str] = []
        dep_warnings: list[str] = []
        dep_missing: list[str] = []
        dep_recs: list[str] = []
        if not dep_kis and not all_rels:
            dep_warnings.append("No technical dependencies or architectural links identified.")
            dep_missing.append("Upstream and downstream system dependencies are undocumented.")
            dep_recs.append("Document external services and upstream dependencies.")

        # Aggregate Overall Score across the 8 weighted canonical dimensions
        category_evals: list[dict[str, Any]] = [
            {
                "category": HandoverReadinessCategory.EVIDENCE_COVERAGE.value,
                "score": cov_score,
                "blockers": cov_blockers,
                "warnings": cov_warnings,
                "missing": cov_missing,
                "recs": cov_recs,
                "metrics": {"linked_items": linked_ki_count, "total_items": total_kis},
            },
            {
                "category": HandoverReadinessCategory.VERIFICATION_COMPLETENESS.value,
                "score": ver_score,
                "blockers": ver_blockers,
                "warnings": ver_warnings,
                "missing": ver_missing,
                "recs": ver_recs,
                "metrics": {"verified_items": len(verified_kis), "total_items": total_kis},
            },
            {
                "category": HandoverReadinessCategory.CONFLICT_RESOLUTION.value,
                "score": conf_score,
                "blockers": conf_blockers,
                "warnings": conf_warnings,
                "missing": conf_missing,
                "recs": conf_recs,
                "metrics": {
                    "unresolved_conflicts": len(unresolved_conflicts),
                    "critical_high_conflicts": len(critical_high_conflicts),
                },
            },
            {
                "category": HandoverReadinessCategory.KNOWLEDGE_FRESHNESS.value,
                "score": fresh_score,
                "blockers": fresh_blockers,
                "warnings": fresh_warnings,
                "missing": fresh_missing,
                "recs": fresh_recs,
                "metrics": {"stale_items": len(stale_kis), "total_items": total_kis},
            },
            {
                "category": HandoverReadinessCategory.RELATIONSHIP_VALIDATION.value,
                "score": rel_score,
                "blockers": rel_blockers,
                "warnings": rel_warnings,
                "missing": rel_missing,
                "recs": rel_recs,
                "metrics": {"verified_relationships": len(verified_rels), "total_relationships": total_rels},
            },
            {
                "category": HandoverReadinessCategory.RESPONSIBILITY_COVERAGE.value,
                "score": resp_score,
                "blockers": resp_blockers,
                "warnings": resp_warnings,
                "missing": resp_missing,
                "recs": resp_recs,
                "metrics": {"mapped_transfers": len(transfers)},
            },
            {
                "category": HandoverReadinessCategory.RISK_ASSESSMENT.value,
                "score": risk_score,
                "blockers": risk_blockers,
                "warnings": risk_warnings,
                "missing": risk_missing,
                "recs": risk_recs,
                "metrics": {"risk_items": len(risk_kis)},
            },
            {
                "category": HandoverReadinessCategory.DEPENDENCY_MAPPING.value,
                "score": dep_score,
                "blockers": dep_blockers,
                "warnings": dep_warnings,
                "missing": dep_missing,
                "recs": dep_recs,
                "metrics": {"dependency_items": len(dep_kis), "relationships": total_rels},
            },
        ]

        weighted_sum = sum(
            c["score"] * CATEGORY_WEIGHTS[c["category"]] for c in category_evals
        )
        overall_score = int(round(weighted_sum))

        all_blockers = [b for c in category_evals for b in c["blockers"]]
        all_warnings = [w for c in category_evals for w in c["warnings"]]
        all_missing = [m for c in category_evals for m in c["missing"]]
        all_recs = [r for c in category_evals for r in c["recs"]]

        overall_eval = {
            "category": HandoverReadinessCategory.OVERALL_QUALITY.value,
            "score": overall_score,
            "blockers": all_blockers,
            "warnings": all_warnings,
            "missing": all_missing,
            "recs": all_recs,
            "metrics": {"weighted_categories": 8, "score_threshold": 70},
        }
        category_evals.append(overall_eval)

        now = utc_now()
        assessments_to_create: list[HandoverReadinessAssessment] = []
        for eval_data in category_evals:
            has_b = len(eval_data["blockers"]) > 0
            details: dict[str, Any] = {
                "missing_requirements": eval_data["missing"],
                "recommendations": eval_data["recs"],
                "metrics": eval_data["metrics"],
            }
            if notes:
                details["notes"] = notes
            assessments_to_create.append(
                HandoverReadinessAssessment(
                    organisation_id=case.organisation_id,
                    project_id=project_id,
                    case_id=case.id,
                    version_id=version.id,
                    category=eval_data["category"],
                    score=eval_data["score"],
                    level=_score_to_level(eval_data["score"], has_b),
                    blockers_json=eval_data["blockers"],
                    warnings_json=eval_data["warnings"],
                    details_json=details,
                    assessed_by_user_id=user_id,
                    assessed_at=now,
                )
            )

        self.readiness_repo.create_bulk(assessments_to_create)

        # Transition case status to READINESS_ASSESSED only when not already in READINESS_ASSESSED
        if case.status in (
            HandoverCaseStatus.ASSEMBLED.value,
            HandoverCaseStatus.READINESS_PENDING.value,
        ):
            self.case_service.transition_status(
                case.id,
                project_id=project_id,
                new_status=HandoverCaseStatus.READINESS_ASSESSED.value,
                user_id=user_id,
                change_reason=f"Readiness assessed: score {overall_score}/100",
            )

        self.audit_service.record_event(
            event_type="handover.readiness.assessed",
            resource_type="handover_package_version",
            resource_id=str(version.id),
            actor_user_id=user_id,
            organisation_id=case.organisation_id,
            project_id=project_id,
            outcome=AuditOutcome.SUCCESS.value,
            metadata={
                "overall_score": overall_score,
                "blocker_count": len(all_blockers),
                "warning_count": len(all_warnings),
            },
        )

        self.session.flush()

        return self.get_readiness_intelligence(
            case_id=case.id,
            version_id=version.id,
            project_id=project_id,
            viewer_user_id=user_id,
            has_project_manage=has_project_manage,
        )

    def get_readiness_intelligence(
        self,
        *,
        case_id: uuid.UUID,
        version_id: uuid.UUID,
        project_id: uuid.UUID,
        viewer_user_id: uuid.UUID,
        has_project_manage: bool = False,
    ) -> HandoverReadinessSummaryResponse:
        """Return authoritative, ACL-checked live readiness intelligence for a case version."""
        version = self.version_repo.get_by_id(version_id, load_sections=True)
        if not version or version.project_id != project_id or version.case_id != case_id:
            raise NotFoundError("Package version not found for this handover case and project.")

        case = version.case or self.case_service.get_case(
            case_id, project_id=project_id, load_relationships=False
        )

        all_assessments = self.readiness_repo.list_by_version(version_id)
        if not all_assessments:
            raise NotFoundError("No readiness assessment found for this version.")

        latest_rows = _latest_assessments_by_category(all_assessments)
        overall_row = next(
            (a for a in latest_rows if a.category == HandoverReadinessCategory.OVERALL_QUALITY.value),
            None,
        )
        non_overall_rows = [
            a for a in latest_rows if a.category != HandoverReadinessCategory.OVERALL_QUALITY.value
        ]

        # Build historical overall snapshots (newest first)
        overall_history_rows = sorted(
            [
                a
                for a in all_assessments
                if a.category == HandoverReadinessCategory.OVERALL_QUALITY.value
            ],
            key=lambda x: (_sort_ts(x.assessed_at), _sort_ts(x.created_at)),
            reverse=True,
        )
        assessor_ids = {a.assessed_by_user_id for a in overall_history_rows if a.assessed_by_user_id}

        # Live Verification & Knowledge Intelligence
        all_kis = list(
            self.session.execute(
                select(KnowledgeItem).where(
                    KnowledgeItem.project_id == project_id,
                    KnowledgeItem.is_deleted.is_(False),
                )
            )
            .scalars()
            .all()
        )
        total_kis = len(all_kis)
        verified_kis = [
            k
            for k in all_kis
            if k.epistemic_status == EpistemicStatus.HUMAN_VERIFIED.value
            and k.review_status == KnowledgeReviewStatus.APPROVED.value
        ]
        rejected_kis = [
            k for k in all_kis if k.review_status == KnowledgeReviewStatus.REJECTED.value
        ]
        stale_kis = [k for k in all_kis if k.is_stale]
        superseded_kis = [k for k in all_kis if k.superseded_by_id is not None]
        corroborated_kis = [k for k in all_kis if k.support_classification == "corroborated"]
        uncertain_kis = [k for k in all_kis if k.support_classification == "uncertain"]
        pending_kis_count = max(0, total_kis - len(verified_kis) - len(rejected_kis))
        ver_cov_pct = int((len(verified_kis) / total_kis * 100)) if total_kis > 0 else 100

        # VerificationCase 6-status breakdown
        vc_rows = list(
            self.session.execute(
                select(VerificationCase.case_status, func.count(VerificationCase.id))
                .where(VerificationCase.project_id == project_id)
                .group_by(VerificationCase.case_status)
            ).all()
        )
        case_counts: dict[str, int] = {
            VerificationCaseStatus.CANDIDATE.value: 0,
            VerificationCaseStatus.PENDING_REVIEW.value: 0,
            VerificationCaseStatus.CONFLICTED.value: 0,
            VerificationCaseStatus.UNRESOLVED.value: 0,
            VerificationCaseStatus.VERIFIED.value: 0,
            VerificationCaseStatus.REJECTED.value: 0,
        }
        for st_val, cnt in vc_rows:
            key = _val(st_val)
            case_counts[key] = case_counts.get(key, 0) + int(cnt)

        # Recent human verification review events
        recent_events = list(
            self.session.execute(
                select(VerificationReviewEvent)
                .where(VerificationReviewEvent.project_id == project_id)
                .order_by(VerificationReviewEvent.created_at.desc())
                .limit(6)
            )
            .scalars()
            .all()
        )
        for ev in recent_events:
            assessor_ids.add(ev.reviewer_user_id)

        # Evidence coverage & ACL visibility check
        linked_ki_count = int(
            self.session.execute(
                select(func.count(func.distinct(KnowledgeEvidenceLink.knowledge_item_id)))
                .join(KnowledgeItem, KnowledgeEvidenceLink.knowledge_item_id == KnowledgeItem.id)
                .where(KnowledgeItem.project_id == project_id, KnowledgeItem.is_deleted.is_(False))
            ).scalar_one()
            or 0
        )
        ev_cov_pct = int((linked_ki_count / total_kis * 100)) if total_kis > 0 else 100

        project_evidence_rows = list(
            self.session.execute(
                select(EvidenceItem.id, EvidenceItem.title).where(
                    EvidenceItem.project_id == project_id,
                    EvidenceItem.deleted_at.is_(None),
                )
            ).all()
        )
        project_evidence_ids = [row[0] for row in project_evidence_rows]
        ev_title_by_id: dict[uuid.UUID, str] = {
            row[0]: row[1] for row in project_evidence_rows if row[1]
        }
        cached_policies = list(
            self.session.execute(
                select(SourceAccessPolicy).where(SourceAccessPolicy.project_id == project_id)
            )
            .scalars()
            .all()
        )
        _, inaccessible_ev_list = check_evidence_accessibility(
            self.session,
            project_evidence_ids,
            project_id=project_id,
            viewer_user_id=viewer_user_id,
            has_project_manage=has_project_manage,
            cached_policies=cached_policies,
        )
        inaccessible_ev_ids = set(inaccessible_ev_list)

        # Canonical Conflict Management records (ACL-checked)
        conflicts = list(
            self.session.execute(
                select(VerificationConflict)
                .where(VerificationConflict.project_id == project_id)
                .order_by(VerificationConflict.updated_at.desc())
            )
            .scalars()
            .all()
        )
        open_cf = 0
        under_inv_cf = 0
        awaiting_ctx_cf = 0
        resolved_cf = 0
        crit_high_cf = 0
        blocking_cf = 0
        conflict_items: list[ReadinessConflictItem] = []

        for cf in conflicts:
            r_state = _val(cf.resolution_state)
            prio = str(cf.priority or "medium").lower()
            is_resolved = r_state in RESOLVED_CONFLICT_STATES
            if is_resolved:
                resolved_cf += 1
            else:
                blocking_cf += 1
                if r_state == ConflictResolutionState.UNDER_INVESTIGATION.value:
                    under_inv_cf += 1
                elif r_state == ConflictResolutionState.AWAITING_CONTEXT.value:
                    awaiting_ctx_cf += 1
                else:
                    open_cf += 1
                if prio in ("critical", "high"):
                    crit_high_cf += 1

            # Fail-closed ACL check on conflict source references
            side_a_restricted = bool(
                cf.claim_a_source_evidence_id and cf.claim_a_source_evidence_id in inaccessible_ev_ids
            )
            side_b_restricted = bool(
                cf.claim_b_source_evidence_id and cf.claim_b_source_evidence_id in inaccessible_ev_ids
            )
            any_restricted = side_a_restricted or side_b_restricted

            conflict_items.append(
                ReadinessConflictItem(
                    id=cf.id,
                    verification_case_id=cf.case_id,
                    conflict_type=_val(cf.conflict_type),
                    priority=prio,
                    resolution_state=r_state,
                    is_blocking=not is_resolved,
                    explanation=redact_secrets(cf.explanation),
                    affected_section_tab="risks",
                    side_a_source_title=(
                        "Restricted Source (ACL Protected)"
                        if side_a_restricted
                        else (
                            cf.side_a_source_title
                            or (
                                ev_title_by_id.get(cf.claim_a_source_evidence_id)
                                if cf.claim_a_source_evidence_id
                                else None
                            )
                        )
                    ),
                    side_b_source_title=(
                        "Restricted Source (ACL Protected)"
                        if side_b_restricted
                        else (
                            cf.side_b_source_title
                            or (
                                ev_title_by_id.get(cf.claim_b_source_evidence_id)
                                if cf.claim_b_source_evidence_id
                                else None
                            )
                        )
                    ),
                    acl_restricted=any_restricted,
                    resolution_notes=(
                        redact_secrets(cf.resolution_notes) if cf.resolution_notes else None
                    ),
                    resolved_at=cf.resolved_at,
                    updated_at=cf.updated_at,
                    conflict_url=f"/conflicts?case_id={cf.case_id}&conflict={cf.id}",
                )
            )

        # Persisted Checklists Integration
        checklists = self.checklist_repo.list_by_case(case_id)
        chk_groups: list[ReadinessChecklistGroupSummary] = []
        chk_total = 0
        chk_done = 0
        mandatory_total = 0
        mandatory_done = 0
        for chk in checklists:
            items = list(chk.items or [])
            c_tot = len(items)
            c_done = sum(1 for i in items if i.status == "completed")
            m_tot = sum(1 for i in items if getattr(i, "blocking", False))
            m_done = sum(
                1 for i in items if getattr(i, "blocking", False) and i.status == "completed"
            )
            chk_total += c_tot
            chk_done += c_done
            mandatory_total += m_tot
            mandatory_done += m_done
            chk_groups.append(
                ReadinessChecklistGroupSummary(
                    id=chk.id,
                    checklist_type=chk.checklist_type,
                    title=chk.title,
                    total_items=c_tot,
                    completed_items=c_done,
                    mandatory_total=m_tot,
                    mandatory_completed=m_done,
                    mandatory_outstanding=m_tot - m_done,
                    is_completed=(c_tot > 0 and c_done == c_tot),
                    items=[
                        {
                            "id": str(i.id),
                            "item_text": i.item_text,
                            "status": i.status,
                            "blocking": bool(getattr(i, "blocking", False)),
                            "category": i.category,
                            "assigned_to_user_id": str(i.assigned_to_user_id)
                            if i.assigned_to_user_id
                            else None,
                            "due_date": i.due_date.isoformat()
                            if getattr(i, "due_date", None)
                            else None,
                        }
                        for i in items
                    ],
                )
            )
        mandatory_outstanding = mandatory_total - mandatory_done
        chk_pct = int((chk_done / chk_total * 100)) if chk_total > 0 else 100

        # Signoff status for approval readiness
        signoffs = self.signoff_repo.list_by_case(case_id)
        version_signoffs = [s for s in signoffs if s.version_id == version_id]
        for sf in version_signoffs:
            assessor_ids.add(sf.signer_user_id)

        user_map: dict[uuid.UUID, User] = {}
        if assessor_ids:
            for u in self.session.execute(select(User).where(User.id.in_(assessor_ids))).scalars().all():
                user_map[u.id] = u

        # Enrich the 9 canonical category responses
        cat_responses: list[HandoverReadinessAssessmentResponse] = []
        dedup_recommendations: list[str] = []
        for row in latest_rows:
            meta = CATEGORY_METADATA.get(row.category, {"label": row.category.replace("_", " ").title(), "tab": "overview"})
            details = row.details_json or {}
            missing_reqs = list(details.get("missing_requirements") or [])
            recs = list(details.get("recommendations") or [])
            metrics = dict(details.get("metrics") or {})

            # Backfill contextual missing/recs for assessments persisted prior to Stage 4 details_json
            if not missing_reqs and not recs:
                if row.category == HandoverReadinessCategory.VERIFICATION_COMPLETENESS.value and pending_kis_count > 0:
                    missing_reqs.append(f"{pending_kis_count} knowledge items awaiting reviewer verification.")
                    recs.append("Approve verified findings in Verification Center and re-assemble package.")
                elif row.category == HandoverReadinessCategory.CONFLICT_RESOLUTION.value and blocking_cf > 0:
                    missing_reqs.append(f"{blocking_cf} cross-source contradictions remain unresolved.")
                    recs.append("Resolve open conflicts in Conflict Management.")
                elif row.category == HandoverReadinessCategory.RESPONSIBILITY_COVERAGE.value and row.score < 100:
                    missing_reqs.append("Departing member responsibilities require explicit transfer mapping.")
                    recs.append("Map component responsibilities and successors in Ownership tab.")

            for r_txt in recs:
                if r_txt not in dedup_recommendations:
                    dedup_recommendations.append(r_txt)

            cat_responses.append(
                HandoverReadinessAssessmentResponse(
                    id=row.id,
                    version_id=row.version_id,
                    category=row.category,
                    label=meta["label"],
                    score=row.score,
                    max_score=100,
                    weight=CATEGORY_WEIGHTS.get(row.category),
                    level=row.level,
                    blockers_json=list(row.blockers_json or []),
                    warnings_json=list(row.warnings_json or []),
                    missing_requirements=missing_reqs,
                    recommendations=recs,
                    related_section_tab=meta["tab"],
                    supporting_metrics=metrics,
                    details_json=details,
                    assessed_by_user_id=row.assessed_by_user_id,
                    assessed_at=row.assessed_at,
                    created_at=row.created_at,
                )
            )

        # Accurate non-doubled blocker/warning counts from the 8 non-aggregate categories
        category_blockers = [b for a in non_overall_rows for b in (a.blockers_json or [])]
        category_warnings = [w for a in non_overall_rows for w in (a.warnings_json or [])]

        # Build structured grouped blockers & corrective actions
        structured_blockers: list[ReadinessStructuredBlockerResponse] = []
        if pending_kis_count > 0:
            structured_blockers.append(
                ReadinessStructuredBlockerResponse(
                    id="blocker-pending-verification",
                    group="pending_verification",
                    severity="critical" if ver_cov_pct < 50 else "high",
                    description=f"{pending_kis_count} extracted knowledge items have not been verified by a human reviewer ({ver_cov_pct}% verified).",
                    originating_subsystem="Verification Center",
                    related_section_tab="decisions",
                    recommended_action="Review and approve eligible findings in Verification Center, then re-assemble the package.",
                    target_url=f"/verification?project={project_id}",
                )
            )
        if blocking_cf > 0:
            first_open_cf = next((c for c in conflict_items if c.is_blocking), None)
            structured_blockers.append(
                ReadinessStructuredBlockerResponse(
                    id="blocker-unresolved-conflicts",
                    group="unresolved_conflicts",
                    severity="critical" if crit_high_cf > 0 else "high",
                    description=f"{blocking_cf} cross-source verification contradictions remain unresolved ({crit_high_cf} critical/high).",
                    originating_subsystem="Conflict Management",
                    related_section_tab="risks",
                    related_record_id=str(first_open_cf.id) if first_open_cf else None,
                    recommended_action="Investigate contradictory claims and record human resolution decisions in Conflict Management.",
                    target_url=(
                        first_open_cf.conflict_url
                        if first_open_cf
                        else f"/conflicts?project={project_id}"
                    ),
                )
            )
        if mandatory_outstanding > 0:
            structured_blockers.append(
                ReadinessStructuredBlockerResponse(
                    id="blocker-incomplete-checklists",
                    group="incomplete_checklists",
                    severity="high",
                    description=f"{mandatory_outstanding} of {mandatory_total} mandatory transition checklist items are incomplete.",
                    originating_subsystem="Transition Checklists",
                    related_section_tab="checklists",
                    recommended_action="Complete all blocking pre-handover, knowledge transfer, and access revocation checklist items.",
                    target_url=f"/handovers/{case_id}?tab=checklists",
                )
            )
        # Missing / blocked / unacknowledged responsibilities
        resp_row = next(
            (a for a in non_overall_rows if a.category == HandoverReadinessCategory.RESPONSIBILITY_COVERAGE.value),
            None,
        )
        if resp_row and (resp_row.score < 70 or resp_row.blockers_json):
            resp_desc = (
                (resp_row.blockers_json or [])[0]
                if resp_row.blockers_json
                else (
                    (resp_row.warnings_json or [])[0]
                    if resp_row.warnings_json
                    else "No explicit responsibility transfers mapped for the departing member."
                )
            )
            structured_blockers.append(
                ReadinessStructuredBlockerResponse(
                    id="blocker-missing-responsibilities",
                    group="missing_responsibilities",
                    severity="high" if resp_row.blockers_json else "medium",
                    description=resp_desc,
                    originating_subsystem="Handover Workspace",
                    related_section_tab="responsibilities",
                    recommended_action="Map responsibilities, assign eligible successors, confirm outgoing handover, and obtain successor acknowledgement.",
                    target_url=f"/handovers/{case_id}?tab=responsibilities",
                )
            )
        ops_sec = next(
            (s for s in version.sections if s.section_type == "operational_historical"),
            None,
        )
        if ops_sec and ops_sec.knowledge_item_count == 0:
            structured_blockers.append(
                ReadinessStructuredBlockerResponse(
                    id="blocker-missing-operational",
                    group="missing_operational_info",
                    severity="medium",
                    description="No human-verified operational procedures or runbooks are compiled into this package version.",
                    originating_subsystem="Knowledge Reconstruction",
                    related_section_tab="operations",
                    recommended_action="Verify setup, deployment, and troubleshooting procedures in Verification Center.",
                    target_url=f"/handovers/{case_id}?tab=operations",
                )
            )
        if total_kis == 0:
            structured_blockers.append(
                ReadinessStructuredBlockerResponse(
                    id="blocker-missing-knowledge",
                    group="missing_knowledge",
                    severity="critical",
                    description="No project knowledge items have been extracted yet.",
                    originating_subsystem="Evidence Workspace",
                    related_section_tab="overview",
                    recommended_action="Upload specifications or connect GitHub/Jira/Slack sources and run reconstruction.",
                    target_url=f"/projects/{project_id}/evidence",
                )
            )

        # Approval Eligibility (authoritative backend gating derived from live DB truth)
        overall_score = overall_row.score if overall_row else 0
        overall_level = overall_row.level if overall_row else ReadinessLevel.NOT_READY.value

        score_gate_passed = overall_score >= 70
        verification_gate_passed = (total_kis == 0) or (ver_cov_pct >= 50 and len(verified_kis) > 0)
        conflict_gate_passed = blocking_cf == 0
        checklist_gate_passed = mandatory_outstanding == 0

        # Non-verification, non-conflict category blockers from latest persisted assessment
        other_category_blockers = [
            b
            for a in non_overall_rows
            if a.category
            not in (
                HandoverReadinessCategory.VERIFICATION_COMPLETENESS.value,
                HandoverReadinessCategory.CONFLICT_RESOLUTION.value,
            )
            for b in (a.blockers_json or [])
        ]

        blocking_reqs: list[str] = []
        live_unverified = total_kis - len(verified_kis)
        if not verification_gate_passed:
            blocking_reqs.append(
                f"{live_unverified} knowledge items have not been verified by a human reviewer ({ver_cov_pct}% verified)."
            )
        if not conflict_gate_passed:
            blocking_reqs.append(
                f"Found {blocking_cf} unresolved cross-source contradictions."
            )
            if crit_high_cf > 0:
                blocking_reqs.append(
                    f"{crit_high_cf} unresolved critical/high-priority conflicts block approval."
                )
        for ob in other_category_blockers:
            if ob not in blocking_reqs:
                blocking_reqs.append(ob)
        if not score_gate_passed:
            blocking_reqs.append(
                f"Overall readiness score ({overall_score}/100) is below the minimum approval threshold (70/100)."
            )
        if not checklist_gate_passed:
            blocking_reqs.append(
                f"{mandatory_outstanding} mandatory transition checklist item(s) remain incomplete."
            )
        if not case.successor_id:
            category_warnings.append("No incoming successor has been assigned to this handover case yet.")

        # Required signoffs status (strictly excluding superseded signoffs)
        active_version_signoffs = [
            s for s in version_signoffs if not getattr(s, "is_superseded", False)
        ]
        dep_signed = next(
            (
                s
                for s in active_version_signoffs
                if s.signoff_type == SignoffType.DEPARTING_SIGNOFF.value
                and s.decision == SignoffDecision.APPROVED.value
            ),
            None,
        )
        rev_signed = next(
            (
                s
                for s in active_version_signoffs
                if s.signoff_type == SignoffType.REVIEWER_APPROVAL.value
                and s.decision == SignoffDecision.APPROVED.value
            ),
            None,
        )
        suc_signed = next(
            (
                s
                for s in active_version_signoffs
                if s.signoff_type == SignoffType.SUCCESSOR_ACKNOWLEDGEMENT.value
            ),
            None,
        )
        required_signoffs = [
            {
                "phase": "Phase 1: Departing Member Sign-Off",
                "signoff_type": SignoffType.DEPARTING_SIGNOFF.value,
                "status": "completed" if dep_signed else "pending",
                "signed_at": dep_signed.signed_at.isoformat() if dep_signed else None,
            },
            {
                "phase": "Phase 2: Reviewer Approval",
                "signoff_type": SignoffType.REVIEWER_APPROVAL.value,
                "status": "completed" if rev_signed else "blocked" if blocking_reqs else "pending",
                "signed_at": rev_signed.signed_at.isoformat() if rev_signed else None,
            },
            {
                "phase": "Phase 3: Successor Acknowledgement",
                "signoff_type": SignoffType.SUCCESSOR_ACKNOWLEDGEMENT.value,
                "status": "completed" if suc_signed else "pending",
                "signed_at": suc_signed.signed_at.isoformat() if suc_signed else None,
            },
        ]

        is_ready = (
            score_gate_passed
            and verification_gate_passed
            and conflict_gate_passed
            and checklist_gate_passed
            and len(other_category_blockers) == 0
        )

        # Assessment History items
        history_items: list[ReadinessAssessmentHistoryItem] = []
        for h_row in overall_history_rows:
            assessor = user_map.get(h_row.assessed_by_user_id) if h_row.assessed_by_user_id else None
            history_items.append(
                ReadinessAssessmentHistoryItem(
                    id=h_row.id,
                    assessed_at=h_row.assessed_at,
                    overall_score=h_row.score,
                    overall_level=h_row.level,
                    blocker_count=len(h_row.blockers_json or []),
                    warning_count=len(h_row.warnings_json or []),
                    assessed_by_name=(assessor.full_name or assessor.email) if assessor else None,
                    notes=(h_row.details_json or {}).get("notes"),
                )
            )

        return HandoverReadinessSummaryResponse(
            version_id=version.id,
            case_id=case.id,
            project_id=project_id,
            version_number=version.version_number,
            content_hash=version.content_hash,
            assessed_at=overall_row.assessed_at if overall_row else None,
            overall_score=overall_score,
            overall_level=overall_level,
            categories=cat_responses,
            is_ready_for_signoff=is_ready,
            blocker_count=len(category_blockers),
            warning_count=len(category_warnings),
            structured_blockers=structured_blockers,
            recommendations=dedup_recommendations,
            verification_summary=ReadinessVerificationSummary(
                total_knowledge_items=total_kis,
                eligible_human_verified=len(verified_kis),
                pending_verification=pending_kis_count,
                rejected_items=len(rejected_kis),
                verification_coverage_pct=ver_cov_pct,
                case_counts=case_counts,
                outstanding_blockers=[
                    b
                    for a in non_overall_rows
                    if a.category == HandoverReadinessCategory.VERIFICATION_COMPLETENESS.value
                    for b in (a.blockers_json or [])
                ],
                recent_reviews=[
                    ReadinessReviewEventItem(
                        id=ev.id,
                        verification_case_id=ev.case_id,
                        action=_val(ev.action),
                        new_status=ev.new_status,
                        reviewer_name=(
                            (user_map[ev.reviewer_user_id].full_name or user_map[ev.reviewer_user_id].email)
                            if ev.reviewer_user_id in user_map
                            else None
                        ),
                        review_notes=redact_secrets(ev.review_notes or ev.decision_reason)
                        if (ev.review_notes or ev.decision_reason)
                        else None,
                        created_at=ev.created_at,
                    )
                    for ev in recent_events
                ],
            ),
            conflict_summary=ReadinessConflictSummary(
                total_conflicts=len(conflicts),
                open_conflicts=open_cf,
                under_investigation=under_inv_cf,
                awaiting_context=awaiting_ctx_cf,
                resolved_conflicts=resolved_cf,
                critical_and_high_count=crit_high_cf,
                blocking_approval_count=blocking_cf,
                items=conflict_items,
            ),
            evidence_quality=ReadinessEvidenceQualitySummary(
                total_knowledge_items=total_kis,
                items_with_evidence=linked_ki_count,
                items_missing_evidence=max(0, total_kis - linked_ki_count),
                evidence_coverage_pct=ev_cov_pct,
                corroborated_items=len(corroborated_kis),
                uncertain_items=len(uncertain_kis),
                stale_items=len(stale_kis),
                superseded_items=len(superseded_kis),
                total_evidence_sources=len(project_evidence_ids),
                accessible_evidence_count=max(0, len(project_evidence_ids) - len(inaccessible_ev_ids)),
                restricted_evidence_count=len(inaccessible_ev_ids),
            ),
            checklist_summary=ReadinessChecklistSummary(
                total_groups=len(chk_groups),
                total_items=chk_total,
                completed_items=chk_done,
                completion_pct=chk_pct,
                mandatory_total=mandatory_total,
                mandatory_completed=mandatory_done,
                mandatory_outstanding=mandatory_outstanding,
                groups=chk_groups,
            ),
            approval_eligibility=ReadinessApprovalEligibility(
                current_case_status=case.status,
                next_lifecycle_state=NEXT_LIFECYCLE_MAP.get(case.status),
                is_eligible_for_approval=is_ready,
                score_gate_passed=score_gate_passed,
                verification_gate_passed=verification_gate_passed,
                conflict_gate_passed=conflict_gate_passed,
                checklist_gate_passed=checklist_gate_passed,
                blocking_requirements=blocking_reqs,
                warnings=category_warnings,
                required_signoffs=required_signoffs,
            ),
            assessment_history=history_items,
        )
