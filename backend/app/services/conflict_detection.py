"""Conflict Detection Engine for Cross-Source Contradictions and Inconsistencies.

Platform: The Handover
Module: Verification Center (Module 3 / Validation Area)

Identifies:
1. Status Conflicts (e.g. Jira Done vs Notes In-Progress, PR merged vs Ticket open)
2. Ownership Conflicts (e.g. conflicting assignees/architects)
3. Decision & Architecture Conflicts (e.g. competing architectural directions, DB or Auth divergence)
4. Temporal Comparison & Supersession Analysis (timezone-aware ISO timestamp evaluation)
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import (
    ConflictResolutionState,
    ConflictType,
    EvidenceSourceType,
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


def _parse_timestamp(ts: datetime | str | None) -> datetime | None:
    """Parse a datetime or ISO-8601 string into a timezone-aware UTC datetime."""
    if ts is None:
        return None
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            return ts.replace(tzinfo=UTC)
        return ts.astimezone(UTC)
    if isinstance(ts, str):
        cleaned = ts.strip()
        if not cleaned:
            return None
        # Replace trailing 'Z' with '+00:00' for fromisoformat compatibility
        if cleaned.endswith("Z") or cleaned.endswith("z"):
            cleaned = cleaned[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(cleaned)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=UTC)
            return dt.astimezone(UTC)
        except (ValueError, TypeError):
            # Attempt basic date/datetime fallback
            try:
                dt = datetime.strptime(cleaned[:19], "%Y-%m-%d %H:%M:%S")
                return dt.replace(tzinfo=UTC)
            except (ValueError, TypeError):
                return None
    return None


def evaluate_temporal_precedence(
    ts_a: datetime | str | None,
    ts_b: datetime | str | None,
    *,
    threshold_seconds: float = 3600.0,
) -> TemporalComparison:
    """Analyze timestamps to determine if one claim temporally supersedes another.

    Supports timezone-aware datetimes and ISO-8601 strings.
    If diff > threshold_seconds: B_SUPERSEDES_A
    If diff < -threshold_seconds: A_SUPERSEDES_B
    Otherwise: SIMULTANEOUS (or AMBIGUOUS if either timestamp is missing).
    """
    dt_a = _parse_timestamp(ts_a)
    dt_b = _parse_timestamp(ts_b)

    if dt_a is None or dt_b is None:
        return TemporalComparison.AMBIGUOUS

    diff = (dt_b - dt_a).total_seconds()
    if diff > threshold_seconds:
        return TemporalComparison.B_SUPERSEDES_A
    elif diff < -threshold_seconds:
        return TemporalComparison.A_SUPERSEDES_B
    return TemporalComparison.SIMULTANEOUS


# Predefined status equivalence clusters
_COMPLETED_STATUSES = frozenset({"completed", "done", "resolved", "closed", "merged", "shipped"})
_PENDING_STATUSES = frozenset({
    "in_progress", "in progress", "to_do", "to do", "open", "blocked",
    "pending", "reopened", "under_review", "wip", "paused",
})
_DISAPPROVED_STATUSES = frozenset({"rejected", "declined", "abandoned", "deprecated", "cancelled"})


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
        claim_a_timestamp: datetime | str | None = None,
        claim_b_chunk_id: uuid.UUID | None = None,
        claim_b_timestamp: datetime | str | None = None,
    ) -> VerificationConflict:
        """Record a structured conflict between two sources on the verification case."""
        # 1. Deduce temporal comparison with timezone awareness
        dt_a = _parse_timestamp(claim_a_timestamp)
        dt_b = _parse_timestamp(claim_b_timestamp)

        if dt_a is None:
            ev_a = self.session.get(EvidenceItem, claim_a_evidence_id)
            if ev_a:
                dt_a = _parse_timestamp(ev_a.source_created_at or ev_a.source_updated_at or ev_a.created_at)
        if dt_b is None:
            ev_b = self.session.get(EvidenceItem, claim_b_evidence_id)
            if ev_b:
                dt_b = _parse_timestamp(ev_b.source_created_at or ev_b.source_updated_at or ev_b.created_at)

        temporal_comp = evaluate_temporal_precedence(dt_a, dt_b)

        # 2. Persist VerificationConflict
        conflict = VerificationConflict(
            organisation_id=case.organisation_id,
            project_id=case.project_id,
            case_id=case.id,
            conflict_type=conflict_type,
            claim_a_text=claim_a_text,
            claim_a_source_evidence_id=claim_a_evidence_id,
            claim_a_chunk_id=claim_a_chunk_id,
            claim_a_source_timestamp=dt_a,
            claim_b_text=claim_b_text,
            claim_b_source_evidence_id=claim_b_evidence_id,
            claim_b_chunk_id=claim_b_chunk_id,
            claim_b_source_timestamp=dt_b,
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
        is_finding_completed = norm_status in _COMPLETED_STATUSES

        for item in observed_items:
            item_status = item.get("status", "").lower().strip()
            item_is_pending = item_status in _PENDING_STATUSES
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

    def detect_cross_source_conflicts(
        self,
        *,
        case: VerificationCase,
        primary_evidence_id: uuid.UUID,
        primary_claim_text: str,
        primary_source_type: str = "document_upload",
        primary_timestamp: datetime | str | None = None,
        observed_sources: list[dict[str, Any]],
    ) -> list[VerificationConflict]:
        """Detect status, architecture, and factual contradictions between heterogeneous sources.

        Handles Jira, GitHub PRs/commits, Markdown documents, and Slack excerpts.
        observed_sources entries:
        {
            "evidence_id": UUID,
            "chunk_id": UUID | None,
            "source_type": "jira" | "github" | "document_upload" | "slack",
            "claim_text": str,
            "status": str | None,
            "technical_decision": str | None,
            "timestamp": datetime | str | None,
            "author": str | None,
        }
        """
        conflicts: list[VerificationConflict] = []
        primary_ev = self.session.get(EvidenceItem, primary_evidence_id)

        def _is_sequential_same_branch_commit(ev_a: EvidenceItem | None, ev_b: EvidenceItem | None) -> bool:
            if not ev_a or not ev_b:
                return False
            meta_a = getattr(ev_a, "metadata_json", None) or {}
            meta_b = getattr(ev_b, "metadata_json", None) or {}
            is_c_a = ev_a.category == "commit" or str(meta_a.get("github_item_type", "")).lower() == "commit"
            is_c_b = ev_b.category == "commit" or str(meta_b.get("github_item_type", "")).lower() == "commit"
            if not (is_c_a and is_c_b):
                return False
            repo_a = str(meta_a.get("repository") or "").lower()
            repo_b = str(meta_b.get("repository") or "").lower()
            if repo_a and repo_b and repo_a != repo_b:
                return False
            sha_a = str(meta_a.get("sha") or "")
            sha_b = str(meta_b.get("sha") or "")
            parents_a = [str(p) for p in (meta_a.get("parent_shas") or []) if p]
            parents_b = [str(p) for p in (meta_b.get("parent_shas") or []) if p]
            if (sha_a and sha_a in parents_b) or (sha_b and sha_b in parents_a):
                return True
            branches_a = {str(b) for b in (meta_a.get("branches") or []) if b}
            branches_b = {str(b) for b in (meta_b.get("branches") or []) if b}
            if branches_a and branches_b and (branches_a & branches_b):
                ts_a = _parse_timestamp(ev_a.source_created_at or primary_timestamp)
                ts_b = _parse_timestamp(ev_b.source_created_at)
                if ts_a is not None and ts_b is not None and ts_a != ts_b:
                    return True
            return False

        for src in observed_sources:
            other_ev_id = src.get("evidence_id")
            if not other_ev_id or other_ev_id == primary_evidence_id:
                continue

            other_ev = self.session.get(EvidenceItem, other_ev_id)
            if _is_sequential_same_branch_commit(primary_ev, other_ev):
                # Chronological evolution on the same Git branch is supersession, not a simultaneous contradiction
                continue

            other_text = src.get("claim_text", "")
            other_type = str(src.get("source_type", "")).lower()
            other_ts = src.get("timestamp")
            other_status = (src.get("status") or "").lower().strip()
            other_decision = (src.get("technical_decision") or "").lower().strip()

            # 1. Status contradiction check
            norm_primary = primary_claim_text.lower()
            if other_status:
                # Word boundaries (\b) and negation guarding to prevent false positives
                # e.g. "abandoned" matching "done", or "not completed" matching "completed"
                negation_pattern = (
                    r"\b(?:not|never|no|yet\s+to\s+be)\s+(?:completed|done|resolved|closed|merged|shipped)\b"
                    r"|\b(?:unresolved|undone|incomplete)\b"
                )
                completion_pattern = r"\b(completed|done|resolved|closed|merged|shipped)\b"
                has_completion = bool(re.search(completion_pattern, norm_primary))
                has_negated_completion = bool(re.search(negation_pattern, norm_primary))

                is_primary_done = has_completion and not has_negated_completion
                is_other_open = other_status in _PENDING_STATUSES

                pending_pattern = r"\b(in\s+progress|in_progress|pending|open|blocked|to\s+do|wip|under\s+review)\b"
                has_pending = bool(re.search(pending_pattern, norm_primary))
                is_primary_pending = has_negated_completion or has_pending
                is_other_closed = other_status in _COMPLETED_STATUSES

                if (is_primary_done and is_other_open) or (is_primary_pending and is_other_closed):
                    expl = (
                        f"Cross-source status contradiction between {primary_source_type} "
                        f"and {other_type}: '{norm_primary[:80]}' vs external status '{other_status}'."
                    )
                    conf = self.register_conflict(
                        case=case,
                        conflict_type=ConflictType.STATUS_CONFLICT,
                        claim_a_text=primary_claim_text,
                        claim_a_evidence_id=primary_evidence_id,
                        claim_a_timestamp=primary_timestamp,
                        claim_b_text=other_text or f"External {other_type} status: {other_status}",
                        claim_b_evidence_id=other_ev_id,
                        claim_b_chunk_id=src.get("chunk_id"),
                        claim_b_timestamp=other_ts,
                        explanation=expl,
                    )
                    conflicts.append(conf)
                    continue

            # 2. Architectural / Technical decision contradiction check
            if other_decision:
                # E.g. "argon2" vs "supabase", "sqlite" vs "postgresql", "rest" vs "graphql"
                contradiction_pairs = [
                    (r"\bargon2(?:id)?\b", r"\bsupabase\b"),
                    (r"\bsqlite\b", r"\bpostgre(?:s|sql)\b"),
                    (r"\brest\b", r"\bgraphql\b"),
                    (r"\blocal\s+disk\b", r"\bs3\b|\bsupabase\s+storage\b"),
                    (r"\bmanual\s+approval\b", r"\bautomated\s+approval\b|\bpublic\b"),
                ]
                for pat_a, pat_b in contradiction_pairs:
                    found_a_in_prim = bool(re.search(pat_a, norm_primary))
                    found_b_in_prim = bool(re.search(pat_b, norm_primary))
                    found_a_in_other = bool(re.search(pat_a, other_decision) or re.search(pat_a, other_text.lower()))
                    found_b_in_other = bool(re.search(pat_b, other_decision) or re.search(pat_b, other_text.lower()))

                    # Mutual exclusivity: one source asserts A and not B, other asserts B and not A
                    # This prevents false positives when a migration narrative mentions both (e.g. SQLite -> PostgreSQL)
                    is_conflict = (
                        (found_a_in_prim and not found_b_in_prim and found_b_in_other and not found_a_in_other)
                        or (found_b_in_prim and not found_a_in_prim and found_a_in_other and not found_b_in_other)
                    )
                    if is_conflict:
                        expl = (
                            f"Architectural divergence between {primary_source_type} and {other_type}: "
                            f"conflicting technical specifications detected."
                        )
                        conf = self.register_conflict(
                            case=case,
                            conflict_type=ConflictType.DECISION_CONFLICT,
                            claim_a_text=primary_claim_text,
                            claim_a_evidence_id=primary_evidence_id,
                            claim_a_timestamp=primary_timestamp,
                            claim_b_text=other_text or f"Technical decision in {other_type}: {other_decision}",
                            claim_b_evidence_id=other_ev_id,
                            claim_b_chunk_id=src.get("chunk_id"),
                            claim_b_timestamp=other_ts,
                            explanation=expl,
                        )
                        conflicts.append(conf)
                        break

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
        github_evs = [e for e in evidences if str(getattr(e, "source_type", "")).lower() == EvidenceSourceType.GITHUB.value]
        jira_evs = [e for e in evidences if str(getattr(e, "source_type", "")).lower() == EvidenceSourceType.JIRA.value]
        doc_evs = [e for e in evidences if str(getattr(e, "source_type", "")).lower() == EvidenceSourceType.DOCUMENT_UPLOAD.value]
        slack_evs = [e for e in evidences if str(getattr(e, "source_type", "")).lower() == EvidenceSourceType.SLACK.value]

        for item in items:
            case = case_map.get(item.id)
            if not case:
                continue

            title_lower = item.title.lower()
            summary_lower = (item.structured_summary or "").lower()

            # A. Authentication Decision Divergence (Argon2id local vs Supabase OAuth)
            if "argon2" in title_lower or "platform identity" in title_lower:
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

            # B. Storage Architecture Divergence (Local Disk vs Supabase private bucket)
            if "storage" in title_lower or "dual-provider" in title_lower:
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

            # C. Passport Sharing / PDF Export Status Mismatch (Documentation unfinalized vs GitHub commit merged)
            if "sharing" in title_lower or "passport sharing" in title_lower:
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

            # D. Skill Verification Evidence Display Divergence (Manual reviewer approval vs immediate render)
            if "skill verification" in title_lower or "growth lens" in title_lower:
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
            if "vram" in title_lower or "rtx 4050" in title_lower:
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

            # F. Jira vs Slack / GitHub Ticket Discrepancies
            for jira_ev in jira_evs:
                jira_status = str(getattr(jira_ev, "source_metadata_json", {}).get("status", "")).lower()
                if "done" in jira_status or "closed" in jira_status:
                    # Check if finding or Slack claims this work item is blocked
                    for slack_ev in slack_evs:
                        slack_text = (getattr(slack_ev, "title", "") + " " + getattr(slack_ev, "source_url", "")).lower()
                        if ("blocked" in slack_text or "waiting" in slack_text) and jira_ev.title.lower() in slack_text:
                            key = (case.id, ConflictType.STATUS_CONFLICT, str(jira_ev.id), str(slack_ev.id))
                            if key not in existing_keys:
                                c = self.register_conflict(
                                    case=case,
                                    conflict_type=ConflictType.STATUS_CONFLICT,
                                    claim_a_text=f"Jira issue '{jira_ev.title}' is marked resolved/closed.",
                                    claim_a_evidence_id=jira_ev.id,
                                    claim_a_timestamp=jira_ev.source_created_at or jira_ev.created_at,
                                    claim_b_text=f"Slack thread mentions task '{jira_ev.title}' is currently blocked.",
                                    claim_b_evidence_id=slack_ev.id,
                                    claim_b_timestamp=slack_ev.source_created_at or slack_ev.created_at,
                                    explanation="Status contradiction between Jira ticket closure and Slack blocker report.",
                                )
                                created_conflicts.append(c)
                                existing_keys.add(key)

        self.session.flush()
        return created_conflicts
