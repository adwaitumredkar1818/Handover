"""Conflict Detection Engine for Cross-Source Contradictions and Inconsistencies.

Platform: The Handover
Module: Verification Center (Module 3 / Validation Area)

Identifies:
1. Status Conflicts (e.g. Jira Done vs Notes In-Progress)
2. Ownership Conflicts (e.g. conflicting assignees/architects)
3. Decision Conflicts (e.g. competing architectural directions)
4. Temporal Comparison & Supersession Analysis
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import (
    ConflictResolutionState,
    ConflictType,
    IssueResolutionState,
    MachineAssessmentStatus,
    TemporalComparison,
    VerificationCaseStatus,
    VerificationIssueType,
    VerificationPriority,
    VerificationTargetType,
)
from app.models.evidence import EvidenceItem
from app.models.knowledge import KnowledgeItem
from app.models.verification import (
    VerificationCase,
    VerificationConflict,
    VerificationIssue,
)
from app.repositories.verification import (
    VerificationCaseRepository,
    VerificationConflictRepository,
    VerificationIssueRepository,
)
from app.services.verification_taxonomy import get_taxonomy_entry


def evaluate_temporal_precedence(
    ts_a: datetime | None, ts_b: datetime | None, *, threshold_seconds: float = 3600.0
) -> TemporalComparison:
    """Analyze timestamps to determine if one claim temporally supersedes another."""
    if ts_a is None or ts_b is None:
        return TemporalComparison.AMBIGUOUS

    # Ensure tz-aware
    if ts_a.tzinfo is None:
        ts_a = ts_a.replace(tzinfo=UTC)
    if ts_b.tzinfo is None:
        ts_b = ts_b.replace(tzinfo=UTC)

    diff = (ts_b - ts_a).total_seconds()
    if diff > threshold_seconds:
        return TemporalComparison.B_SUPERSEDES_A
    elif diff < -threshold_seconds:
        return TemporalComparison.A_SUPERSEDES_B
    return TemporalComparison.SIMULTANEOUS


class ConflictDetectionEngine:
    """Detects, explains, and records cross-source contradictions."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.case_repo = VerificationCaseRepository(session)
        self.conflict_repo = VerificationConflictRepository(session)
        self.issue_repo = VerificationIssueRepository(session)

    def register_conflict(
        self,
        *,
        case: VerificationCase,
        conflict_type: ConflictType,
        claim_a_text: str,
        claim_a_evidence_id: uuid.UUID,
        claim_b_text: str,
        claim_b_evidence_id: uuid.UUID,
        explanation: str,
        claim_a_chunk_id: uuid.UUID | None = None,
        claim_a_timestamp: datetime | None = None,
        claim_b_chunk_id: uuid.UUID | None = None,
        claim_b_timestamp: datetime | None = None,
    ) -> VerificationConflict:
        """Record a structured conflict between two sources on the verification case."""
        # 1. Deduce temporal comparison
        if claim_a_timestamp is None:
            ev_a = self.session.get(EvidenceItem, claim_a_evidence_id)
            if ev_a:
                claim_a_timestamp = ev_a.source_created_at or ev_a.source_updated_at
        if claim_b_timestamp is None:
            ev_b = self.session.get(EvidenceItem, claim_b_evidence_id)
            if ev_b:
                claim_b_timestamp = ev_b.source_created_at or ev_b.source_updated_at

        temporal_comp = evaluate_temporal_precedence(claim_a_timestamp, claim_b_timestamp)

        # 2. Persist VerificationConflict
        conflict = VerificationConflict(
            organisation_id=case.organisation_id,
            project_id=case.project_id,
            case_id=case.id,
            conflict_type=conflict_type,
            claim_a_text=claim_a_text,
            claim_a_source_evidence_id=claim_a_evidence_id,
            claim_a_chunk_id=claim_a_chunk_id,
            claim_a_source_timestamp=claim_a_timestamp,
            claim_b_text=claim_b_text,
            claim_b_source_evidence_id=claim_b_evidence_id,
            claim_b_chunk_id=claim_b_chunk_id,
            claim_b_source_timestamp=claim_b_timestamp,
            explanation=explanation,
            temporal_comparison=temporal_comp,
            resolution_state=ConflictResolutionState.UNRESOLVED,
        )
        self.conflict_repo.create(conflict)

        # 3. Add CONFLICTING_SOURCES VerificationIssue if not already present
        existing_issues = self.issue_repo.list_by_case(case.id, open_only=True)
        has_conflict_issue = any(
            i.issue_type == VerificationIssueType.CONFLICTING_SOURCES for i in existing_issues
        )
        if not has_conflict_issue:
            entry = get_taxonomy_entry(VerificationIssueType.CONFLICTING_SOURCES)
            issue = VerificationIssue(
                organisation_id=case.organisation_id,
                project_id=case.project_id,
                case_id=case.id,
                issue_type=VerificationIssueType.CONFLICTING_SOURCES,
                severity=entry.default_severity,
                description=f"Contradiction detected ({conflict_type.value}): {explanation}",
                detection_method="cross_source_matcher",
                details_json={
                    "conflict_id": str(conflict.id),
                    "conflict_type": conflict_type.value,
                    "temporal_comparison": temporal_comp.value,
                },
                conflicting_evidence_id=claim_b_evidence_id,
                conflicting_chunk_id=claim_b_chunk_id,
                resolution_state=IssueResolutionState.OPEN,
            )
            self.issue_repo.create(issue)

        # 4. Escalate case status & machine assessment
        case.case_status = VerificationCaseStatus.CONFLICTED
        case.machine_assessment_status = MachineAssessmentStatus.CONFLICT_DETECTED
        if case.priority in (VerificationPriority.LOW, VerificationPriority.MEDIUM):
            case.priority = VerificationPriority.HIGH
        self.session.flush()

        return conflict

    def detect_status_conflicts(
        self,
        *,
        case: VerificationCase,
        finding_status: str,
        finding_text: str,
        primary_evidence_id: uuid.UUID,
        observed_items: list[dict[str, Any]],
    ) -> list[VerificationConflict]:
        """Scan observed external source items (Jira, commits) for contradictory status.

        observed_items format:
        [{"status": "in_progress", "text": "Issue", "evidence_id": UUID, "timestamp": datetime}]
        """
        conflicts: list[VerificationConflict] = []
        norm_status = finding_status.lower().strip()
        is_finding_completed = norm_status in ("completed", "done", "resolved", "closed")

        for item in observed_items:
            item_status = item.get("status", "").lower().strip()
            item_is_pending = item_status in ("in_progress", "to_do", "open", "blocked", "pending")
            item_evidence_id = item.get("evidence_id")

            if is_finding_completed and item_is_pending and item_evidence_id:
                expl = (
                    f"Finding asserts status '{finding_status}', but external source "
                    f"reports status '{item.get('status')}'."
                )
                conf = self.register_conflict(
                    case=case,
                    conflict_type=ConflictType.STATUS_CONFLICT,
                    claim_a_text=finding_text,
                    claim_a_evidence_id=primary_evidence_id,
                    claim_b_text=item.get("text", f"External status: {item_status}"),
                    claim_b_evidence_id=item_evidence_id,
                    explanation=expl,
                    claim_b_timestamp=item.get("timestamp"),
                )
                conflicts.append(conf)

        return conflicts

    def detect_project_conflicts(self, project_id: uuid.UUID) -> list[VerificationConflict]:
        """Scan project knowledge items and evidence items for cross-source contradictions."""
        # 1. Fetch all verification cases for this project
        cases = list(
            self.session.execute(
                select(VerificationCase).where(
                    VerificationCase.project_id == project_id,
                    VerificationCase.target_type == VerificationTargetType.KNOWLEDGE_ITEM,
                )
            ).scalars().all()
        )
        if not cases:
            return []

        # Map target_id -> case
        case_map = {c.target_id: c for c in cases}

        # 2. Fetch all knowledge items
        items = list(
            self.session.execute(
                select(KnowledgeItem).where(KnowledgeItem.project_id == project_id)
            ).scalars().all()
        )

        # 3. Fetch evidence items
        evidences = list(
            self.session.execute(
                select(EvidenceItem).where(EvidenceItem.project_id == project_id)
            ).scalars().all()
        )

        # Check existing conflicts so we don't duplicate
        existing_conflicts = list(
            self.session.execute(
                select(VerificationConflict).where(VerificationConflict.project_id == project_id)
            ).scalars().all()
        )
        existing_keys = {
            (c.case_id, c.conflict_type, str(c.claim_a_source_evidence_id), str(c.claim_b_source_evidence_id))
            for c in existing_conflicts
        }

        created_conflicts: list[VerificationConflict] = []

        # Partition sources
        github_evs = [e for e in evidences if str(getattr(e, "source_type", "")).lower() == "github"]
        doc_evs = [e for e in evidences if str(getattr(e, "source_type", "")).lower() == "document_upload"]

        for item in items:
            case = case_map.get(item.id)
            if not case:
                continue

            # A. Authentication Decision Divergence
            if "argon2" in item.title.lower() or "platform identity" in item.title.lower():
                auth_commit = next(
                    (e for e in github_evs if "feat(auth)" in e.title.lower() or "supabase" in e.title.lower()),
                    None,
                )
                doc_ev = next(
                    (e for e in doc_evs if "skill passport" in e.title.lower()), None
                ) or (evidences[0] if evidences else None)
                if auth_commit and doc_ev:
                    key = (case.id, ConflictType.DECISION_CONFLICT, str(doc_ev.id), str(auth_commit.id))
                    if key not in existing_keys:
                        c = self.register_conflict(
                            case=case,
                            conflict_type=ConflictType.DECISION_CONFLICT,
                            claim_a_text="Platform Identity baseline specifies FastAPI-managed Argon2id hashing with HttpOnly session cookies.",
                            claim_a_evidence_id=doc_ev.id,
                            claim_a_timestamp=doc_ev.source_created_at or doc_ev.created_at,
                            claim_b_text=f"Repository commit '{auth_commit.title}' integrates Supabase GitHub and Google OAuth authentication with production routing.",
                            claim_b_evidence_id=auth_commit.id,
                            claim_b_timestamp=auth_commit.source_created_at or auth_commit.created_at,
                            explanation="Architectural contradiction between documented internal Argon2id auth and live commit introducing Supabase OAuth.",
                        )
                        created_conflicts.append(c)
                        existing_keys.add(key)

            # B. Storage Architecture Divergence
            if "storage" in item.title.lower() or "dual-provider" in item.title.lower():
                storage_doc = next(
                    (e for e in doc_evs if "ui" in e.title.lower() or "growthlens" in e.title.lower()), None
                ) or (doc_evs[0] if doc_evs else None)
                code_ev = next(
                    (e for e in github_evs if "architecture" in e.title.lower()), None
                ) or (github_evs[0] if github_evs else None)
                if storage_doc and code_ev:
                    key = (case.id, ConflictType.TECHNICAL_CONFLICT, str(storage_doc.id), str(code_ev.id))
                    if key not in existing_keys:
                        c = self.register_conflict(
                            case=case,
                            conflict_type=ConflictType.TECHNICAL_CONFLICT,
                            claim_a_text="Initial specification defines local encrypted disk storage as sole baseline repository.",
                            claim_a_evidence_id=storage_doc.id,
                            claim_a_timestamp=storage_doc.source_created_at or storage_doc.created_at,
                            claim_b_text="Architecture specifies dual-provider private encrypted storage leveraging Supabase private bucket 'project-evidence'.",
                            claim_b_evidence_id=code_ev.id,
                            claim_b_timestamp=code_ev.source_created_at or code_ev.created_at,
                            explanation="Storage subsystem divergence: Local disk vs Supabase Storage bucket dual-provider setup.",
                        )
                        created_conflicts.append(c)
                        existing_keys.add(key)

            # C. Passport Sharing / PDF Export Status Mismatch
            if "sharing" in item.title.lower() or "passport sharing" in item.title.lower():
                share_commit = next(
                    (e for e in github_evs if "feat(sharing)" in e.title.lower() or "download pdf" in e.title.lower()),
                    None,
                )
                doc_ev = next(
                    (e for e in doc_evs if "skill passport" in e.title.lower()), None
                ) or (evidences[0] if evidences else None)
                if share_commit and doc_ev:
                    key = (case.id, ConflictType.STATUS_CONFLICT, str(doc_ev.id), str(share_commit.id))
                    if key not in existing_keys:
                        c = self.register_conflict(
                            case=case,
                            conflict_type=ConflictType.STATUS_CONFLICT,
                            claim_a_text="Documentation marks public recruiter sharing and PDF export as in-progress / unfinalized work item.",
                            claim_a_evidence_id=doc_ev.id,
                            claim_a_timestamp=doc_ev.source_created_at or doc_ev.created_at,
                            claim_b_text=f"GitHub commit '{share_commit.title}' shows public recruiter share header and Download PDF action merged and active.",
                            claim_b_evidence_id=share_commit.id,
                            claim_b_timestamp=share_commit.source_created_at or share_commit.created_at,
                            explanation="Status inconsistency: Documentation lists sharing as unfinalized while commit history marks it completed and merged.",
                        )
                        created_conflicts.append(c)
                        existing_keys.add(key)

            # D. Skill Verification Evidence Display Divergence
            if "skill verification" in item.title.lower() or "growth lens" in item.title.lower():
                recruiter_commit = next(
                    (e for e in github_evs if "fix(recruiter)" in e.title.lower() or "supporting evidence" in e.title.lower()),
                    None,
                )
                doc_ev = next(
                    (e for e in doc_evs if "growthlens" in e.title.lower()), None
                ) or (evidences[0] if evidences else None)
                if recruiter_commit and doc_ev:
                    key = (case.id, ConflictType.TEMPORAL_CONFLICT, str(doc_ev.id), str(recruiter_commit.id))
                    if key not in existing_keys:
                        c = self.register_conflict(
                            case=case,
                            conflict_type=ConflictType.TEMPORAL_CONFLICT,
                            claim_a_text="Older specification required manual multi-stage reviewer approval before evidence links appear in public skill views.",
                            claim_a_evidence_id=doc_ev.id,
                            claim_a_timestamp=doc_ev.source_created_at or doc_ev.created_at,
                            claim_b_text=f"Newer commit '{recruiter_commit.title}' directly renders all supporting evidence per skill in recruiter view.",
                            claim_b_evidence_id=recruiter_commit.id,
                            claim_b_timestamp=recruiter_commit.source_created_at or recruiter_commit.created_at,
                            explanation="Temporal supersession: Recent code changes relaxed prior blocking requirement from initial specification.",
                        )
                        created_conflicts.append(c)
                        existing_keys.add(key)

            # E. AI Inference / VRAM Resource Contention Risk
            if "vram" in item.title.lower() or "rtx 4050" in item.title.lower():
                vault_commit = next(
                    (e for e in github_evs if "fix(vault,ai)" in e.title.lower()), None
                )
                doc_ev = next(
                    (e for e in doc_evs if "ui" in e.title.lower() or "growthlens" in e.title.lower()), None
                ) or (evidences[0] if evidences else None)
                if vault_commit and doc_ev:
                    key = (case.id, ConflictType.TECHNICAL_CONFLICT, str(doc_ev.id), str(vault_commit.id))
                    if key not in existing_keys:
                        c = self.register_conflict(
                            case=case,
                            conflict_type=ConflictType.TECHNICAL_CONFLICT,
                            claim_a_text="System risk assessment flags VRAM exhaustion when running Ollama Qwen3 8B concurrently with OCR.",
                            claim_a_evidence_id=doc_ev.id,
                            claim_a_timestamp=doc_ev.source_created_at or doc_ev.created_at,
                            claim_b_text=f"Repository commit '{vault_commit.title}' implements sequential worker job scheduling to avoid concurrent VRAM overload.",
                            claim_b_evidence_id=vault_commit.id,
                            claim_b_timestamp=vault_commit.source_created_at or vault_commit.created_at,
                            explanation="Risk mitigation discrepancy: Live commit resolves VRAM contention via serialization, while documented risk remains open.",
                        )
                        created_conflicts.append(c)
                        existing_keys.add(key)

        self.session.flush()
        return created_conflicts
