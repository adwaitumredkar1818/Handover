"""SQLAlchemy 2.x repository for the Conflict Management Workspace."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.enums import ConflictPriority, ConflictResolutionState
from app.models.evidence import EvidenceItem
from app.models.verification import VerificationCase, VerificationConflict


class ConflictRepository:
    """Data-access layer for cross-source contradiction and conflict records."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_conflict_by_id(
        self,
        conflict_id: uuid.UUID,
        *,
        project_id: uuid.UUID,
    ) -> VerificationConflict | None:
        """Fetch a single VerificationConflict by ID with scoped project security."""
        stmt = (
            select(VerificationConflict)
            .where(
                VerificationConflict.id == conflict_id,
                VerificationConflict.project_id == project_id,
            )
            .options(
                selectinload(VerificationConflict.case).selectinload(VerificationCase.evidence_refs),
                selectinload(VerificationConflict.claim_a_evidence).selectinload(
                    EvidenceItem.source_access_policy
                ),
                selectinload(VerificationConflict.claim_b_evidence).selectinload(
                    EvidenceItem.source_access_policy
                ),
                selectinload(VerificationConflict.assigned_reviewer),
                selectinload(VerificationConflict.resolved_by_user),
                selectinload(VerificationConflict.related_finding).selectinload(
                    VerificationCase.evidence_refs
                ),
            )
        )
        return self.session.execute(stmt).scalars().first()

    def list_project_conflicts_for_acl(
        self,
        project_id: uuid.UUID,
        *,
        conflict_type: str | None = None,
        resolution_state: str | None = None,
        priority: str | None = None,
        assigned_to: uuid.UUID | None = None,
    ) -> list[VerificationConflict]:
        """Fetch project conflicts matching non-text filters for per-viewer ACL filtering.

        Text search is intentionally NOT applied in SQL here so restricted claims
        and titles cannot be probed via search oracle before ACL evaluation.
        """
        stmt = select(VerificationConflict).where(
            VerificationConflict.project_id == project_id
        )

        if conflict_type:
            stmt = stmt.where(VerificationConflict.conflict_type == conflict_type)

        if resolution_state:
            if resolution_state == "open":
                stmt = stmt.where(
                    VerificationConflict.resolution_state.in_([
                        ConflictResolutionState.OPEN.value,
                        ConflictResolutionState.UNRESOLVED.value,
                    ])
                )
            elif resolution_state == "resolved":
                stmt = stmt.where(
                    VerificationConflict.resolution_state.in_([
                        ConflictResolutionState.RESOLVED.value,
                        ConflictResolutionState.RECONCILED.value,
                        ConflictResolutionState.SUPERSEDED.value,
                        ConflictResolutionState.DISMISSED.value,
                    ])
                )
            else:
                stmt = stmt.where(VerificationConflict.resolution_state == resolution_state)

        if priority:
            stmt = stmt.where(VerificationConflict.priority == priority)

        if assigned_to:
            stmt = stmt.where(VerificationConflict.assigned_reviewer_id == assigned_to)

        stmt = stmt.options(
            selectinload(VerificationConflict.case).selectinload(VerificationCase.evidence_refs),
            selectinload(VerificationConflict.assigned_reviewer),
            selectinload(VerificationConflict.resolved_by_user),
            selectinload(VerificationConflict.related_finding).selectinload(
                VerificationCase.evidence_refs
            ),
        ).order_by(
            VerificationConflict.priority.desc(),
            VerificationConflict.created_at.desc(),
            VerificationConflict.id.asc(),
        )
        return list(self.session.execute(stmt).scalars().all())

    def list_conflicts(
        self,
        project_id: uuid.UUID,
        *,
        conflict_type: str | None = None,
        resolution_state: str | None = None,
        priority: str | None = None,
        assigned_to: uuid.UUID | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[VerificationConflict], int]:
        """List conflicts with comprehensive filtering and total count."""
        stmt = select(VerificationConflict).where(
            VerificationConflict.project_id == project_id
        )

        if conflict_type:
            stmt = stmt.where(VerificationConflict.conflict_type == conflict_type)

        if resolution_state:
            # Map friendly filters (e.g. "open" matches open & unresolved)
            if resolution_state == "open":
                stmt = stmt.where(
                    VerificationConflict.resolution_state.in_([
                        ConflictResolutionState.OPEN.value,
                        ConflictResolutionState.UNRESOLVED.value,
                    ])
                )
            elif resolution_state == "resolved":
                stmt = stmt.where(
                    VerificationConflict.resolution_state.in_([
                        ConflictResolutionState.RESOLVED.value,
                        ConflictResolutionState.RECONCILED.value,
                        ConflictResolutionState.SUPERSEDED.value,
                        ConflictResolutionState.DISMISSED.value,
                    ])
                )
            else:
                stmt = stmt.where(VerificationConflict.resolution_state == resolution_state)

        if priority:
            stmt = stmt.where(VerificationConflict.priority == priority)

        if assigned_to:
            stmt = stmt.where(VerificationConflict.assigned_reviewer_id == assigned_to)

        if search:
            pattern = f"%{search.strip().lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(VerificationConflict.explanation).like(pattern),
                    func.lower(VerificationConflict.claim_a_text).like(pattern),
                    func.lower(VerificationConflict.claim_b_text).like(pattern),
                    func.lower(VerificationConflict.side_a_source_title).like(pattern),
                    func.lower(VerificationConflict.side_b_source_title).like(pattern),
                )
            )

        # Count total matching rows
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = self.session.execute(count_stmt).scalar() or 0

        # Fetch page with eager loading
        stmt = (
            stmt.options(
                selectinload(VerificationConflict.case),
                selectinload(VerificationConflict.assigned_reviewer),
                selectinload(VerificationConflict.resolved_by_user),
            )
            .order_by(
                VerificationConflict.priority.desc(),
                VerificationConflict.created_at.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
        items = list(self.session.execute(stmt).scalars().all())
        return items, total

    def get_dashboard_metrics(self, project_id: uuid.UUID) -> dict[str, Any]:
        """Aggregate all dashboard metrics from live PostgreSQL database records."""
        # 1. Status counts
        status_stmt = (
            select(VerificationConflict.resolution_state, func.count(VerificationConflict.id))
            .where(VerificationConflict.project_id == project_id)
            .group_by(VerificationConflict.resolution_state)
        )
        status_rows = self.session.execute(status_stmt).all()
        status_counts = {r[0]: r[1] for r in status_rows}

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

        # 2. Priority counts
        prio_stmt = (
            select(VerificationConflict.priority, func.count(VerificationConflict.id))
            .where(VerificationConflict.project_id == project_id)
            .group_by(VerificationConflict.priority)
        )
        prio_rows = self.session.execute(prio_stmt).all()
        prio_counts = {r[0]: r[1] for r in prio_rows}

        critical_count = prio_counts.get("critical", 0)
        high_count = prio_counts.get("high", 0)
        medium_count = prio_counts.get("medium", 0)
        low_count = prio_counts.get("low", 0)

        # 3. Category counts across 6 canonical categories
        cat_stmt = (
            select(VerificationConflict.conflict_type, func.count(VerificationConflict.id))
            .where(VerificationConflict.project_id == project_id)
            .group_by(VerificationConflict.conflict_type)
        )
        cat_rows = self.session.execute(cat_stmt).all()
        category_counts = {r[0]: r[1] for r in cat_rows}

        total = sum(status_counts.values())
        attention_required = open_count + investigating_count + awaiting_count

        return {
            "project_id": project_id,
            "total_conflicts": total,
            "open_conflicts": open_count,
            "under_investigation": investigating_count,
            "awaiting_context": awaiting_count,
            "resolved": resolved_count,
            "reopened": reopened_count,
            "critical_priority": critical_count,
            "high_priority": high_count,
            "medium_priority": medium_count,
            "low_priority": low_count,
            "category_counts": category_counts,
            "attention_required_count": attention_required,
        }
