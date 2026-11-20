"""SQLAlchemy 2.x repository for Verification Center Phase 1 Rebuild."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.enums import (
    ConflictResolutionState,
    ContextRequestStatus,
    IssueResolutionState,
    VerificationCaseStatus,
)
from app.models.verification import (
    VerificationCase,
    VerificationConflict,
    VerificationContextRequest,
    VerificationEvidenceRef,
    VerificationFindingRevision,
    VerificationIssue,
    VerificationReviewEvent,
)


class VerificationRepository:
    """Canonical data-access layer for Verification Center persistence."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_case(
        self,
        case_id: uuid.UUID,
        *,
        project_id: uuid.UUID,
        load_details: bool = True,
    ) -> VerificationCase | None:
        stmt = select(VerificationCase).where(
            VerificationCase.id == case_id,
            VerificationCase.project_id == project_id,
        )
        if load_details:
            stmt = stmt.options(
                selectinload(VerificationCase.issues),
                selectinload(VerificationCase.conflicts),
                selectinload(VerificationCase.evidence_refs),
                selectinload(VerificationCase.revisions),
                selectinload(VerificationCase.review_events),
                selectinload(VerificationCase.context_requests),
                selectinload(VerificationCase.assigned_reviewer),
            )
        return self.session.execute(stmt).scalar_one_or_none()

    def get_case_by_target(
        self,
        *,
        project_id: uuid.UUID,
        target_type: str,
        target_id: uuid.UUID,
    ) -> VerificationCase | None:
        stmt = (
            select(VerificationCase)
            .where(
                VerificationCase.project_id == project_id,
                VerificationCase.target_type == target_type,
                VerificationCase.target_id == target_id,
            )
            .options(
                selectinload(VerificationCase.evidence_refs),
                selectinload(VerificationCase.issues),
                selectinload(VerificationCase.conflicts),
                selectinload(VerificationCase.revisions),
            )
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def list_project_cases(
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
        sort_by: str = "updated_at",
        sort_dir: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[VerificationCase], int]:
        stmt = (
            select(VerificationCase)
            .where(
                VerificationCase.project_id == project_id,
                VerificationCase.case_status != VerificationCaseStatus.ARCHIVED.value,
            )
            .options(
                selectinload(VerificationCase.issues),
                selectinload(VerificationCase.evidence_refs),
                selectinload(VerificationCase.assigned_reviewer),
            )
        )
        count_stmt = select(func.count(func.distinct(VerificationCase.id))).where(
            VerificationCase.project_id == project_id,
            VerificationCase.case_status != VerificationCaseStatus.ARCHIVED.value,
        )

        filters: list[Any] = []
        if status:
            filters.append(VerificationCase.case_status == status)
        if domain:
            filters.append(VerificationCase.domain == domain)
        if person:
            filters.append(VerificationCase.person_name.ilike(f"%{person.strip()}%"))
        if source:
            filters.append(VerificationCase.source_provider == source)
        if reviewer_id:
            filters.append(VerificationCase.assigned_reviewer_id == reviewer_id)
        if search:
            q = f"%{search.strip()}%"
            filters.append(
                or_(
                    VerificationCase.title.ilike(q),
                    VerificationCase.current_claim.ilike(q),
                    VerificationCase.original_ai_claim.ilike(q),
                    VerificationCase.domain.ilike(q),
                )
            )
        if category:
            issue_case_ids = select(VerificationIssue.case_id).where(
                VerificationIssue.project_id == project_id,
                VerificationIssue.verification_category == category,
                VerificationIssue.resolution_state == IssueResolutionState.OPEN.value,
            )
            filters.append(VerificationCase.id.in_(issue_case_ids))

        if filters:
            stmt = stmt.where(*filters)
            count_stmt = count_stmt.where(*filters)

        sort_column = {
            "updated_at": VerificationCase.updated_at,
            "created_at": VerificationCase.created_at,
            "priority": VerificationCase.priority,
            "status": VerificationCase.case_status,
            "domain": VerificationCase.domain,
        }.get(sort_by, VerificationCase.updated_at)

        order_expr = sort_column.asc() if sort_dir.lower() == "asc" else sort_column.desc()
        stmt = stmt.order_by(order_expr, VerificationCase.id.asc()).limit(limit).offset(offset)

        items = list(self.session.execute(stmt).scalars().all())
        total = int(self.session.execute(count_stmt).scalar_one())
        return items, total

    def list_project_cases_for_acl(
        self,
        project_id: uuid.UUID,
        *,
        status: str | None = None,
        domain: str | None = None,
        source: str | None = None,
        reviewer_id: uuid.UUID | None = None,
        sort_by: str = "updated_at",
        sort_dir: str = "desc",
    ) -> list[VerificationCase]:
        """Fetch non-archived project cases matching structural filters for viewer ACL filtering.

        Text search, person, and category filters are applied post-ACL in the service
        layer so restricted claims, authors, and categories cannot leak via SQL queries.
        """
        stmt = (
            select(VerificationCase)
            .where(
                VerificationCase.project_id == project_id,
                VerificationCase.case_status != VerificationCaseStatus.ARCHIVED.value,
            )
            .options(
                selectinload(VerificationCase.issues),
                selectinload(VerificationCase.evidence_refs),
                selectinload(VerificationCase.conflicts),
                selectinload(VerificationCase.context_requests),
                selectinload(VerificationCase.assigned_reviewer),
            )
        )
        if status:
            stmt = stmt.where(VerificationCase.case_status == status)
        if domain:
            stmt = stmt.where(VerificationCase.domain == domain)
        if source:
            stmt = stmt.where(VerificationCase.source_provider == source)
        if reviewer_id:
            stmt = stmt.where(VerificationCase.assigned_reviewer_id == reviewer_id)

        sort_column = {
            "updated_at": VerificationCase.updated_at,
            "created_at": VerificationCase.created_at,
            "priority": VerificationCase.priority,
            "status": VerificationCase.case_status,
            "domain": VerificationCase.domain,
        }.get(sort_by, VerificationCase.updated_at)

        order_expr = sort_column.asc() if sort_dir.lower() == "asc" else sort_column.desc()
        stmt = stmt.order_by(order_expr, VerificationCase.id.asc())
        return list(self.session.execute(stmt).scalars().all())

    def list_project_cases_by_ids(
        self,
        project_id: uuid.UUID,
        case_ids: list[uuid.UUID],
    ) -> list[VerificationCase]:
        """Hydrate full VerificationCase ORM rows with relations ONLY for a small page of IDs."""
        if not case_ids:
            return []
        stmt = (
            select(VerificationCase)
            .where(
                VerificationCase.project_id == project_id,
                VerificationCase.id.in_(case_ids),
            )
            .options(
                selectinload(VerificationCase.issues),
                selectinload(VerificationCase.evidence_refs),
                selectinload(VerificationCase.conflicts),
                selectinload(VerificationCase.context_requests),
                selectinload(VerificationCase.assigned_reviewer),
            )
        )
        by_id = {c.id: c for c in self.session.execute(stmt).scalars().all()}
        return [by_id[cid] for cid in case_ids if cid in by_id]

    def list_project_cases_lightweight(
        self,
        project_id: uuid.UUID,
        *,
        status: str | None = None,
        domain: str | None = None,
        source: str | None = None,
        reviewer_id: uuid.UUID | None = None,
        sort_by: str = "updated_at",
        sort_dir: str = "desc",
        include_claim_text: bool = False,
    ) -> dict[str, Any]:
        """Fetch lightweight column projections for fast ACL evaluation, summary, and queue pagination."""
        cols: list[Any] = [
            VerificationCase.id,
            VerificationCase.case_status,
            VerificationCase.target_type,
            VerificationCase.target_id,
            VerificationCase.domain,
            VerificationCase.source_provider,
            VerificationCase.assigned_reviewer_id,
            VerificationCase.person_name,
        ]
        if include_claim_text:
            cols.extend(
                [
                    VerificationCase.title,
                    VerificationCase.current_claim,
                    VerificationCase.original_ai_claim,
                ]
            )

        base_filter = [
            VerificationCase.project_id == project_id,
            VerificationCase.case_status != VerificationCaseStatus.ARCHIVED.value,
        ]
        if status:
            base_filter.append(VerificationCase.case_status == status)
        if domain:
            base_filter.append(VerificationCase.domain == domain)
        if source:
            base_filter.append(VerificationCase.source_provider == source)
        if reviewer_id:
            base_filter.append(VerificationCase.assigned_reviewer_id == reviewer_id)

        sort_column = {
            "updated_at": VerificationCase.updated_at,
            "created_at": VerificationCase.created_at,
            "priority": VerificationCase.priority,
            "status": VerificationCase.case_status,
            "domain": VerificationCase.domain,
        }.get(sort_by, VerificationCase.updated_at)
        order_expr = sort_column.asc() if sort_dir.lower() == "asc" else sort_column.desc()

        case_rows = list(
            self.session.execute(
                select(*cols).where(*base_filter).order_by(order_expr, VerificationCase.id.asc())
            ).all()
        )
        if not case_rows:
            return {
                "cases": [],
                "refs_by_case": {},
                "open_issues_by_case": {},
                "conflicts_by_case": {},
                "pending_ctx_by_case": {},
            }

        case_id_subq = select(VerificationCase.id).where(*base_filter)

        refs_by_case: dict[uuid.UUID, list[uuid.UUID]] = {}
        for cid, eid in self.session.execute(
            select(VerificationEvidenceRef.case_id, VerificationEvidenceRef.evidence_item_id).where(
                VerificationEvidenceRef.case_id.in_(case_id_subq)
            )
        ).all():
            refs_by_case.setdefault(cid, []).append(eid)

        open_issues_by_case: dict[uuid.UUID, list[tuple[str | None, uuid.UUID | None]]] = {}
        for cid, cat, conf_ev_id in self.session.execute(
            select(
                VerificationIssue.case_id,
                VerificationIssue.verification_category,
                VerificationIssue.conflicting_evidence_id,
            ).where(
                VerificationIssue.case_id.in_(case_id_subq),
                VerificationIssue.resolution_state == IssueResolutionState.OPEN.value,
            )
        ).all():
            open_issues_by_case.setdefault(cid, []).append((cat, conf_ev_id))

        conflicts_by_case: dict[
            uuid.UUID, list[tuple[str, uuid.UUID | None, uuid.UUID | None]]
        ] = {}
        for cid, res_state, ev_a, ev_b in self.session.execute(
            select(
                VerificationConflict.case_id,
                VerificationConflict.resolution_state,
                VerificationConflict.claim_a_source_evidence_id,
                VerificationConflict.claim_b_source_evidence_id,
            ).where(VerificationConflict.case_id.in_(case_id_subq))
        ).all():
            conflicts_by_case.setdefault(cid, []).append((res_state, ev_a, ev_b))

        pending_ctx_by_case: dict[uuid.UUID, int] = {}
        for (cid,) in self.session.execute(
            select(VerificationContextRequest.case_id).where(
                VerificationContextRequest.case_id.in_(case_id_subq),
                VerificationContextRequest.status == ContextRequestStatus.PENDING.value,
            )
        ).all():
            pending_ctx_by_case[cid] = pending_ctx_by_case.get(cid, 0) + 1

        return {
            "cases": case_rows,
            "refs_by_case": refs_by_case,
            "open_issues_by_case": open_issues_by_case,
            "conflicts_by_case": conflicts_by_case,
            "pending_ctx_by_case": pending_ctx_by_case,
        }

    def get_summary_counts(self, project_id: uuid.UUID) -> dict[str, int]:
        rows = self.session.execute(
            select(VerificationCase.case_status, func.count(VerificationCase.id))
            .where(
                VerificationCase.project_id == project_id,
                VerificationCase.case_status != VerificationCaseStatus.ARCHIVED.value,
            )
            .group_by(VerificationCase.case_status)
        ).all()

        counts = {str(status): int(cnt) for status, cnt in rows}

        open_issues = int(
            self.session.execute(
                select(func.count(VerificationIssue.id)).where(
                    VerificationIssue.project_id == project_id,
                    VerificationIssue.resolution_state == IssueResolutionState.OPEN.value,
                )
            ).scalar_one()
        )
        open_conflicts = int(
            self.session.execute(
                select(func.count(VerificationConflict.id)).where(
                    VerificationConflict.project_id == project_id,
                    VerificationConflict.resolution_state
                    == ConflictResolutionState.UNRESOLVED.value,
                )
            ).scalar_one()
        )
        pending_ctx = int(
            self.session.execute(
                select(func.count(VerificationContextRequest.id)).where(
                    VerificationContextRequest.project_id == project_id,
                    VerificationContextRequest.status == ContextRequestStatus.PENDING.value,
                )
            ).scalar_one()
        )

        return {
            "total_cases": sum(counts.values()),
            "candidate_count": counts.get(VerificationCaseStatus.CANDIDATE.value, 0),
            "pending_review_count": counts.get(VerificationCaseStatus.PENDING_REVIEW.value, 0),
            "conflicted_count": counts.get(VerificationCaseStatus.CONFLICTED.value, 0),
            "unresolved_count": counts.get(VerificationCaseStatus.UNRESOLVED.value, 0),
            "verified_count": counts.get(VerificationCaseStatus.VERIFIED.value, 0),
            "rejected_count": counts.get(VerificationCaseStatus.REJECTED.value, 0),
            "open_issues_count": open_issues,
            "open_conflicts_count": open_conflicts,
            "pending_context_requests_count": pending_ctx,
        }

    def list_filter_facets(self, project_id: uuid.UUID) -> dict[str, list[str]]:
        base_filter = (
            VerificationCase.project_id == project_id,
            VerificationCase.case_status != VerificationCaseStatus.ARCHIVED.value,
        )
        domains = [
            d
            for (d,) in self.session.execute(
                select(VerificationCase.domain).where(*base_filter).distinct()
            ).all()
            if d
        ]
        sources = [
            s
            for (s,) in self.session.execute(
                select(VerificationCase.source_provider).where(*base_filter).distinct()
            ).all()
            if s
        ]
        people = [
            p
            for (p,) in self.session.execute(
                select(VerificationCase.person_name).where(*base_filter).distinct()
            ).all()
            if p
        ]
        return {
            "domains": sorted(domains),
            "sources": sorted(sources),
            "people": sorted(people),
        }

    def list_context_requests(
        self,
        project_id: uuid.UUID,
        *,
        case_id: uuid.UUID | None = None,
        status: str | None = None,
    ) -> list[VerificationContextRequest]:
        stmt = (
            select(VerificationContextRequest)
            .where(VerificationContextRequest.project_id == project_id)
            .options(
                selectinload(VerificationContextRequest.requested_by),
                selectinload(VerificationContextRequest.requested_from),
            )
            .order_by(VerificationContextRequest.created_at.desc())
        )
        if case_id:
            stmt = stmt.where(VerificationContextRequest.case_id == case_id)
        if status:
            stmt = stmt.where(VerificationContextRequest.status == status)
        return list(self.session.execute(stmt).scalars().all())

    def get_context_request(
        self, request_id: uuid.UUID, *, project_id: uuid.UUID
    ) -> VerificationContextRequest | None:
        stmt = (
            select(VerificationContextRequest)
            .where(
                VerificationContextRequest.id == request_id,
                VerificationContextRequest.project_id == project_id,
            )
            .options(
                selectinload(VerificationContextRequest.requested_by),
                selectinload(VerificationContextRequest.requested_from),
            )
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def add(self, entity: Any) -> Any:
        self.session.add(entity)
        return entity

    def flush(self) -> None:
        self.session.flush()


class VerificationCaseRepository(VerificationRepository):
    """Integration adapter for HandoverEligibilityService."""

    def get_by_target(
        self,
        *,
        project_id: uuid.UUID,
        target_type: Any,
        target_id: uuid.UUID,
    ) -> VerificationCase | None:
        tt = target_type.value if hasattr(target_type, "value") else str(target_type)
        return self.get_case_by_target(
            project_id=project_id, target_type=tt, target_id=target_id
        )


class VerificationIssueRepository:
    """Integration adapter for HandoverEligibilityService."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, issue: VerificationIssue) -> VerificationIssue:
        self.session.add(issue)
        self.session.flush()
        return issue

    def list_by_case(
        self, case_id: uuid.UUID, *, open_only: bool = False
    ) -> list[VerificationIssue]:
        stmt = select(VerificationIssue).where(VerificationIssue.case_id == case_id)
        if open_only:
            stmt = stmt.where(
                VerificationIssue.resolution_state == IssueResolutionState.OPEN.value
            )
        return list(self.session.execute(stmt).scalars().all())


class VerificationConflictRepository:
    """Integration adapter for HandoverEligibilityService."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, conflict: VerificationConflict) -> VerificationConflict:
        self.session.add(conflict)
        self.session.flush()
        return conflict

    def list_by_case(
        self, case_id: uuid.UUID, *, unresolved_only: bool = False
    ) -> list[VerificationConflict]:
        stmt = select(VerificationConflict).where(VerificationConflict.case_id == case_id)
        if unresolved_only:
            stmt = stmt.where(
                VerificationConflict.resolution_state
                == ConflictResolutionState.UNRESOLVED.value
            )
        return list(self.session.execute(stmt).scalars().all())
