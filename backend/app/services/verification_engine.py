"""Automated Verification Engine for Verification Center (Phase 1 Rebuild).

Implements deterministic, traceable checks across all six PDF review categories:
1. extracted_finding_verification
2. conflicting_evidence
3. missing_evidence
4. outdated_information
5. uncertain_relationships
6. duplicate_findings

Automated checks NEVER approve or reject findings and NEVER overwrite human decisions.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.enums import (
    ConflictResolutionState,
    IssueResolutionState,
    MachineAssessmentStatus,
    TemporalComparison,
    VerificationCaseStatus,
    VerificationCategory,
    VerificationIssueType,
    VerificationPriority,
    VerificationSeverity,
    VerificationTargetType,
)
from app.models.evidence import EvidenceChunk, EvidenceItem
from app.models.knowledge import KnowledgeEvidenceLink, KnowledgeItem
from app.models.relationship import (
    KnowledgeEntity,
    KnowledgeRelationship,
    RelationshipEvidenceLink,
)
from app.models.verification import (
    VerificationCase,
    VerificationConflict,
    VerificationEvidenceRef,
    VerificationFindingRevision,
    VerificationIssue,
)
from app.repositories.verification import VerificationRepository
from app.services.verification_intelligence import (
    AdvancedContradictionEvaluator,
    CompletenessEvaluator,
    ContinuousMonitoringService,
    CorroborationEvaluator,
    FreshnessEvaluator,
    PrioritisationEngine,
    RecommendationEngine,
    SourceChangeImpact,
    SourceReliabilityEvaluator,
)

_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "was", "were", "are",
    "has", "have", "had", "been", "being", "into", "onto", "about", "will",
}
_POSITIVE_STATUS_TOKENS = {"done", "merged", "completed", "approved", "closed", "resolved", "finalized"}
_NEGATIVE_STATUS_TOKENS = {"open", "pending", "blocked", "undecided", "in_progress", "wip", "draft", "reopened"}


def _candidate_to_dict(c: ContradictionCandidate) -> dict[str, Any]:
    d = asdict(c)
    for k, v in list(d.items()):
        if isinstance(v, uuid.UUID):
            d[k] = str(v)
        elif isinstance(v, datetime):
            d[k] = v.isoformat()
    return d


def _tokenize(text: str | None) -> set[str]:
    if not text:
        return set()
    words = re.findall(r"[a-z0-9_]+", text.lower())
    return {w for w in words if len(w) > 2 and w not in _STOPWORDS}


def _jaccard_similarity(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


class VerificationEngine:
    """Syncs Knowledge Intelligence outputs and runs traceable automated checks."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = VerificationRepository(session)
        self.completeness_eval = CompletenessEvaluator()
        self.reliability_eval = SourceReliabilityEvaluator()
        self.freshness_eval = FreshnessEvaluator()
        self.corroboration_eval = CorroborationEvaluator()
        self.contradiction_eval = AdvancedContradictionEvaluator()
        self.recommendation_engine = RecommendationEngine()
        self.prioritisation_engine = PrioritisationEngine()
        self.monitoring_service = ContinuousMonitoringService(self.session)

    def sync_project_findings(self, project_id: uuid.UUID) -> dict[str, int]:
        """Materialize VerificationCases for KnowledgeItems and KnowledgeRelationships."""
        created = 0
        updated = 0

        # 1. Sync KnowledgeItems
        ki_stmt = (
            select(KnowledgeItem)
            .where(KnowledgeItem.project_id == project_id, KnowledgeItem.is_deleted.is_(False))
            .options(
                selectinload(KnowledgeItem.evidence_links).selectinload(
                    KnowledgeEvidenceLink.evidence_item
                ),
                selectinload(KnowledgeItem.evidence_links).selectinload(
                    KnowledgeEvidenceLink.evidence_chunk
                ),
            )
        )
        items = list(self.session.execute(ki_stmt).scalars().all())
        for ki in items:
            existing = self.repo.get_case_by_target(
                project_id=project_id,
                target_type=VerificationTargetType.KNOWLEDGE_ITEM.value,
                target_id=ki.id,
            )
            conf_meta = ki.confidence_metadata_json or {}
            model_conf = conf_meta.get("confidence") or conf_meta.get("score")
            uncertainty = ki.uncertainty_reason or conf_meta.get("uncertainty_note") or conf_meta.get("uncertainty")
            person_name = ki.person_or_owner_label or conf_meta.get("owner")

            if existing is None:
                primary_provider = None
                if ki.evidence_links and ki.evidence_links[0].evidence_item is not None:
                    primary_provider = ki.evidence_links[0].evidence_item.source_type

                case = VerificationCase(
                    organisation_id=ki.organisation_id,
                    project_id=ki.project_id,
                    target_type=VerificationTargetType.KNOWLEDGE_ITEM.value,
                    target_id=ki.id,
                    domain=ki.category,
                    title=ki.title,
                    original_ai_claim=ki.structured_summary,
                    current_claim=ki.structured_summary,
                    person_name=person_name,
                    source_provider=primary_provider,
                    model_confidence=float(model_conf) if model_conf is not None else None,
                    uncertainty_note=str(uncertainty) if uncertainty else None,
                    case_status=VerificationCaseStatus.CANDIDATE.value,
                    priority=VerificationPriority.MEDIUM.value,
                )
                self.session.add(case)
                self.session.flush()

                self.session.add(
                    VerificationFindingRevision(
                        organisation_id=ki.organisation_id,
                        project_id=ki.project_id,
                        case_id=case.id,
                        revision_number=1,
                        claim_text=ki.structured_summary,
                        domain=ki.category,
                        is_ai_original=True,
                        edit_reason="Initial AI knowledge extraction",
                    )
                )
                self._sync_knowledge_evidence_refs(case, ki.evidence_links)
                created += 1
            else:
                if self._sync_knowledge_evidence_refs(existing, ki.evidence_links) > 0:
                    updated += 1

        # 2. Sync KnowledgeRelationships
        rel_stmt = (
            select(KnowledgeRelationship)
            .where(KnowledgeRelationship.project_id == project_id)
            .options(selectinload(KnowledgeRelationship.evidence_links))
        )
        rels = list(self.session.execute(rel_stmt).scalars().all())
        entity_names: dict[uuid.UUID, str] = {}
        if rels:
            ent_rows = self.session.execute(
                select(KnowledgeEntity.id, KnowledgeEntity.canonical_name).where(
                    KnowledgeEntity.project_id == project_id
                )
            ).all()
            entity_names = {eid: name for eid, name in ent_rows}

        for rel in rels:
            existing = self.repo.get_case_by_target(
                project_id=project_id,
                target_type=VerificationTargetType.RELATIONSHIP.value,
                target_id=rel.id,
            )
            src_name = entity_names.get(rel.source_entity_id, "Source Entity")
            tgt_name = entity_names.get(rel.target_entity_id, "Target Entity")
            claim = f"{src_name} —[{rel.relationship_type}]→ {tgt_name}"
            rel_desc = getattr(rel, "description", None) or getattr(rel, "evidence_summary", None)
            if rel_desc:
                claim = f"{claim}: {rel_desc}"

            if existing is None:
                primary_provider = None
                if rel.evidence_links:
                    ev0 = self.session.get(EvidenceItem, rel.evidence_links[0].evidence_id)
                    if ev0 is not None:
                        primary_provider = ev0.source_type

                case = VerificationCase(
                    organisation_id=rel.organisation_id,
                    project_id=rel.project_id,
                    target_type=VerificationTargetType.RELATIONSHIP.value,
                    target_id=rel.id,
                    domain="relationship",
                    title=f"Relationship: {src_name} → {tgt_name}",
                    original_ai_claim=claim,
                    current_claim=claim,
                    source_provider=primary_provider,
                    model_confidence=float(rel.confidence_score)
                    if getattr(rel, "confidence_score", None) is not None
                    else None,
                    case_status=VerificationCaseStatus.CANDIDATE.value,
                    priority=VerificationPriority.MEDIUM.value,
                )
                self.session.add(case)
                self.session.flush()

                self.session.add(
                    VerificationFindingRevision(
                        organisation_id=rel.organisation_id,
                        project_id=rel.project_id,
                        case_id=case.id,
                        revision_number=1,
                        claim_text=claim,
                        domain="relationship",
                        is_ai_original=True,
                        edit_reason="Initial AI relationship extraction",
                    )
                )
                self._sync_relationship_evidence_refs(case, rel.evidence_links)
                created += 1
            else:
                if self._sync_relationship_evidence_refs(existing, rel.evidence_links) > 0:
                    updated += 1

        self.session.flush()
        return {"cases_created": created, "cases_updated": updated}

    def _sync_knowledge_evidence_refs(
        self, case: VerificationCase, links: list[KnowledgeEvidenceLink]
    ) -> int:
        existing_pairs = {(r.evidence_item_id, r.evidence_chunk_id) for r in case.evidence_refs}
        added = 0
        for link in links:
            key = (link.evidence_id, link.evidence_chunk_id)
            if key in existing_pairs:
                continue
            ev_item: EvidenceItem | None = link.evidence_item
            ev_chunk: EvidenceChunk | None = link.evidence_chunk
            excerpt = getattr(link, "supporting_excerpt", None) or (
                ev_chunk.chunk_text[:500] if ev_chunk is not None else None
            )
            loc = None
            if ev_chunk is not None and getattr(ev_chunk, "page_number", None) is not None:
                loc = f"Page {ev_chunk.page_number}"
            elif ev_item is not None and getattr(ev_item, "source_external_id", None):
                loc = ev_item.source_external_id

            self.session.add(
                VerificationEvidenceRef(
                    organisation_id=case.organisation_id,
                    project_id=case.project_id,
                    case_id=case.id,
                    evidence_item_id=link.evidence_id,
                    evidence_chunk_id=link.evidence_chunk_id,
                    relationship_to_finding="supports",
                    excerpt=excerpt,
                    location_label=loc,
                    source_timestamp=ev_item.source_created_at if ev_item else None,
                )
            )
            existing_pairs.add(key)
            added += 1
        return added

    def _sync_relationship_evidence_refs(
        self, case: VerificationCase, links: list[RelationshipEvidenceLink]
    ) -> int:
        existing_pairs = {(r.evidence_item_id, r.evidence_chunk_id) for r in case.evidence_refs}
        added = 0
        for link in links:
            key = (link.evidence_id, link.evidence_chunk_id)
            if key in existing_pairs:
                continue
            ev_item = self.session.get(EvidenceItem, link.evidence_id)
            ev_chunk = (
                self.session.get(EvidenceChunk, link.evidence_chunk_id)
                if link.evidence_chunk_id
                else None
            )
            excerpt = getattr(link, "evidence_excerpt", None) or (
                ev_chunk.chunk_text[:500] if ev_chunk is not None else None
            )
            self.session.add(
                VerificationEvidenceRef(
                    organisation_id=case.organisation_id,
                    project_id=case.project_id,
                    case_id=case.id,
                    evidence_item_id=link.evidence_id,
                    evidence_chunk_id=link.evidence_chunk_id,
                    relationship_to_finding="supports",
                    excerpt=excerpt,
                    location_label=ev_item.source_external_id if ev_item else None,
                    source_timestamp=ev_item.source_created_at if ev_item else None,
                )
            )
            existing_pairs.add(key)
            added += 1
        return added

    def assess_project(
        self,
        project_id: uuid.UUID,
        *,
        case_id: uuid.UUID | None = None,
    ) -> dict[str, int]:
        """Run deterministic checks and advanced intelligence across all 6 categories."""
        all_cases, _ = self.repo.list_project_cases(project_id, limit=500, offset=0)
        targets = [c for c in all_cases if case_id is None or c.id == case_id]

        # Load all project evidence items for freshness and authority context
        all_project_evidence = list(
            self.session.execute(
                select(EvidenceItem).where(EvidenceItem.project_id == project_id)
            )
            .scalars()
            .all()
        )

        # Precompute newest project evidence timestamp for freshness checks
        newest_ev_ts = self.session.execute(
            select(EvidenceItem.source_created_at)
            .where(
                EvidenceItem.project_id == project_id,
                EvidenceItem.source_created_at.is_not(None),
            )
            .order_by(EvidenceItem.source_created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        newest_ev_ts = _ensure_utc(newest_ev_ts)

        # Precompute token sets for duplicate detection
        claim_tokens: dict[uuid.UUID, set[str]] = {
            c.id: _tokenize(c.current_claim or c.title) for c in all_cases
        }

        issues_detected = 0
        now = datetime.now(UTC)

        for case in targets:
            # Clear prior unresolved automated issues on re-assessment so issues stay current
            for old_issue in list(case.issues):
                if (
                    old_issue.resolution_state == IssueResolutionState.OPEN.value
                    and old_issue.detection_method == "deterministic_rule"
                ):
                    self.session.delete(old_issue)
            self.session.flush()

            refs = list(
                self.session.execute(
                    select(VerificationEvidenceRef)
                    .where(VerificationEvidenceRef.case_id == case.id)
                    .options(selectinload(VerificationEvidenceRef.evidence_item))
                )
                .scalars()
                .all()
            )
            new_issues: list[VerificationIssue] = []

            # ---------------------------------------------------------------
            # Advanced Verification Intelligence Suite
            # ---------------------------------------------------------------
            comp_report = self.completeness_eval.evaluate(case, refs)
            rel_report = self.reliability_eval.evaluate(case, refs)
            fresh_report = self.freshness_eval.evaluate(
                case, refs, newest_ev_ts, all_project_evidence
            )
            corrob_report = self.corroboration_eval.evaluate(case, refs)
            contra_candidates = self.contradiction_eval.evaluate(case, refs, all_cases)
            rec_report = self.recommendation_engine.evaluate(
                case,
                comp_report,
                rel_report,
                fresh_report,
                corrob_report,
                contra_candidates,
                len(case.issues),
            )
            prio, prio_reason = self.prioritisation_engine.compute_priority(
                case, comp_report, fresh_report, contra_candidates, rec_report
            )

            # Update structured finding properties
            case.evidence_completeness = comp_report.level
            case.priority = prio.value

            # 1 & 3: Completeness, Provenance, Missing Evidence
            if comp_report.level in {"missing", "sparse"}:
                new_issues.append(
                    self._build_issue(
                        case,
                        category=VerificationCategory.MISSING_EVIDENCE.value,
                        issue_type=VerificationIssueType.MISSING_EVIDENCE.value,
                        severity=VerificationSeverity.HIGH.value
                        if comp_report.level == "missing"
                        else VerificationSeverity.MEDIUM.value,
                        description=comp_report.explanation,
                        details={
                            "missing_elements": comp_report.missing_elements,
                            "recommendations": comp_report.recommendations,
                            "score": comp_report.score,
                        },
                    )
                )
            elif not comp_report.direct_support and refs:
                new_issues.append(
                    self._build_issue(
                        case,
                        category=VerificationCategory.EXTRACTED_FINDING_VERIFICATION.value,
                        issue_type=VerificationIssueType.UNSUPPORTED_CLAIM.value,
                        severity=VerificationSeverity.MEDIUM.value,
                        description=comp_report.explanation,
                        details={"score": comp_report.score},
                    )
                )

            # Check for invalid / cross-project evidence references
            for ref in refs:
                ev = ref.evidence_item
                if ev is None or ev.project_id != project_id:
                    new_issues.append(
                        self._build_issue(
                            case,
                            category=VerificationCategory.EXTRACTED_FINDING_VERIFICATION.value,
                            issue_type=VerificationIssueType.INVALID_SOURCE_REFERENCE.value,
                            severity=VerificationSeverity.CRITICAL.value,
                            description="Referenced evidence item is missing or belongs to another project.",
                            details={"evidence_item_id": str(ref.evidence_item_id)},
                        )
                    )

            # 2: Conflicting Evidence (open VerificationConflict or detected contradictions)
            active_conflict_states = [
                ConflictResolutionState.UNRESOLVED.value,
                ConflictResolutionState.OPEN.value,
                ConflictResolutionState.UNDER_INVESTIGATION.value,
                ConflictResolutionState.AWAITING_CONTEXT.value,
                ConflictResolutionState.REOPENED.value,
            ]
            open_conflicts = list(
                self.session.execute(
                    select(VerificationConflict).where(
                        VerificationConflict.case_id == case.id,
                        VerificationConflict.resolution_state.in_(active_conflict_states),
                    )
                )
                .scalars()
                .all()
            )

            # Materialize newly detected contradiction candidates into canonical VerificationConflict records
            for cand in contra_candidates:
                existing_match = self.session.execute(
                    select(VerificationConflict).where(
                        VerificationConflict.case_id == case.id,
                        VerificationConflict.conflict_type == cand.conflict_type,
                        VerificationConflict.claim_b_text == cand.side_b_claim,
                    )
                ).scalars().first()
                if not existing_match:
                    temp_comp = TemporalComparison.AMBIGUOUS.value
                    if cand.side_a_timestamp and cand.side_b_timestamp:
                        if cand.side_b_timestamp > cand.side_a_timestamp:
                            temp_comp = TemporalComparison.B_SUPERSEDES_A.value
                        elif cand.side_a_timestamp > cand.side_b_timestamp:
                            temp_comp = TemporalComparison.A_SUPERSEDES_B.value

                    new_conflict = VerificationConflict(
                        organisation_id=case.organisation_id,
                        project_id=case.project_id,
                        case_id=case.id,
                        conflict_type=cand.conflict_type,
                        claim_a_text=cand.side_a_claim,
                        claim_a_source_evidence_id=cand.side_a_evidence_id or (refs[0].evidence_item_id if refs else None),
                        claim_a_chunk_id=cand.side_a_chunk_id or (refs[0].chunk_id if refs else None),
                        claim_a_source_timestamp=cand.side_a_timestamp or (refs[0].source_timestamp if refs else None),
                        claim_b_text=cand.side_b_claim,
                        claim_b_source_evidence_id=cand.side_b_evidence_id,
                        claim_b_chunk_id=cand.side_b_chunk_id,
                        claim_b_source_timestamp=cand.side_b_timestamp,
                        side_a_source_title=cand.side_a_title,
                        side_a_provider=cand.side_a_provider,
                        side_b_source_title=cand.side_b_title,
                        side_b_provider=cand.side_b_provider,
                        related_finding_id=cand.related_finding_id,
                        explanation=cand.explanation,
                        priority="critical" if cand.severity == "critical" else ("high" if cand.severity == "high" else "medium"),
                        temporal_comparison=temp_comp,
                        resolution_state=ConflictResolutionState.UNRESOLVED.value,
                    )
                    self.session.add(new_conflict)
                    open_conflicts.append(new_conflict)

            has_conflict = bool(open_conflicts) or bool(contra_candidates)
            if open_conflicts:
                new_issues.append(
                    self._build_issue(
                        case,
                        category=VerificationCategory.CONFLICTING_EVIDENCE.value,
                        issue_type=VerificationIssueType.CONFLICTING_SOURCES.value,
                        severity=VerificationSeverity.HIGH.value,
                        description=open_conflicts[0].explanation if open_conflicts else "Cross-source contradiction detected.",
                        details={
                            "conflict_count": len(open_conflicts),
                            "conflict_ids": [str(c.id) for c in open_conflicts],
                            "contradictions": [_candidate_to_dict(c) for c in contra_candidates],
                        },
                    )
                )

            # 4: Outdated Information & Freshness
            if fresh_report.status in {"stale", "outdated"}:
                new_issues.append(
                    self._build_issue(
                        case,
                        category=VerificationCategory.OUTDATED_INFORMATION.value,
                        issue_type=VerificationIssueType.OUTDATED_INFORMATION.value,
                        severity=VerificationSeverity.HIGH.value
                        if fresh_report.status == "outdated"
                        else VerificationSeverity.MEDIUM.value,
                        description=fresh_report.explanation,
                        details={
                            "age_days": fresh_report.age_days,
                            "superseded_by": fresh_report.superseded_by_record_title,
                            "reverification_required": fresh_report.reverification_required,
                        },
                    )
                )

            # 5: Uncertain Relationships
            if case.target_type == VerificationTargetType.RELATIONSHIP.value:
                if (case.model_confidence is not None and case.model_confidence < 0.70) or not refs:
                    new_issues.append(
                        self._build_issue(
                            case,
                            category=VerificationCategory.UNCERTAIN_RELATIONSHIPS.value,
                            issue_type=VerificationIssueType.UNCERTAIN_RELATIONSHIP.value,
                            severity=VerificationSeverity.MEDIUM.value,
                            description=(
                                "AI-suggested relationship has low confidence or lacks an explicit "
                                "cross-source reference."
                            ),
                            details={"model_confidence": case.model_confidence},
                        )
                    )

            # 6: Duplicate Findings
            my_tok = claim_tokens.get(case.id, set())
            if len(my_tok) >= 3:
                dup_ids = [
                    str(o.id)
                    for o in all_cases
                    if o.id != case.id
                    and _jaccard_similarity(my_tok, claim_tokens.get(o.id, set())) >= 0.72
                ]
                if dup_ids:
                    new_issues.append(
                        self._build_issue(
                            case,
                            category=VerificationCategory.DUPLICATE_FINDINGS.value,
                            issue_type=VerificationIssueType.DUPLICATE_RECORD.value,
                            severity=VerificationSeverity.LOW.value,
                            description=(
                                f"Potential duplicate of {len(dup_ids)} other extracted finding(s) "
                                "with overlapping claims."
                            ),
                            details={"duplicate_case_ids": dup_ids},
                        )
                    )

            for issue in new_issues:
                self.session.add(issue)
                issues_detected += 1

            # Preserve any existing monitoring status when updating machine assessment
            prior_assessment = dict(case.machine_assessment_json or {})
            prior_monitoring = prior_assessment.get("monitoring_status")

            contra_dict = {
                "has_contradiction": bool(contra_candidates),
                "contradiction_count": len(contra_candidates),
                "summary": (
                    f"{len(contra_candidates)} contradiction(s) detected across project sources"
                    if contra_candidates
                    else "Zero detected contradictions across project evidence"
                ),
                "contradictions": [_candidate_to_dict(c) for c in contra_candidates],
            }

            assessment_payload = {
                "completeness_assessment": asdict(comp_report),
                "reliability_assessment": asdict(rel_report),
                "freshness_assessment": asdict(fresh_report),
                "corroboration_assessment": asdict(corrob_report),
                "contradiction_analysis": contra_dict,
                "recommendation": asdict(rec_report),
                "priority_reason": prio_reason,
                "assessed_at": now.isoformat(),
            }
            if prior_monitoring:
                assessment_payload["monitoring_status"] = prior_monitoring

            case.machine_assessment_json = assessment_payload

            # Update machine assessment status & non-human-decided case status
            case.last_assessed_at = now
            if has_conflict:
                case.machine_assessment_status = MachineAssessmentStatus.CONFLICT_DETECTED.value
            elif not refs:
                case.machine_assessment_status = MachineAssessmentStatus.INSUFFICIENT_EVIDENCE.value
            elif new_issues:
                case.machine_assessment_status = MachineAssessmentStatus.ISSUES_DETECTED.value
            else:
                case.machine_assessment_status = MachineAssessmentStatus.PASSED.value

            # Never overwrite human VERIFIED / REJECTED decisions
            if case.case_status not in {
                VerificationCaseStatus.VERIFIED.value,
                VerificationCaseStatus.REJECTED.value,
            }:
                if has_conflict:
                    case.case_status = VerificationCaseStatus.CONFLICTED.value
                elif not refs and case.case_status == VerificationCaseStatus.CANDIDATE.value:
                    case.case_status = VerificationCaseStatus.UNRESOLVED.value

        self.session.flush()
        return {"cases_assessed": len(targets), "issues_detected": issues_detected}

    def monitor_source_change(
        self,
        *,
        project_id: uuid.UUID,
        evidence_item: EvidenceItem,
        change_type: str = "modified",
        triggered_by_user_id: uuid.UUID | None = None,
    ) -> SourceChangeImpact:
        """Trigger continuous monitoring evaluation for a modified evidence item."""
        return self.monitoring_service.process_source_change_event(
            project_id=project_id,
            evidence_item=evidence_item,
            change_type=change_type,
            triggered_by_user_id=triggered_by_user_id,
        )

        self.session.flush()
        return {"cases_assessed": len(targets), "issues_detected": issues_detected}

    def _build_issue(
        self,
        case: VerificationCase,
        *,
        category: str,
        issue_type: str,
        severity: str,
        description: str,
        details: dict[str, Any],
    ) -> VerificationIssue:
        return VerificationIssue(
            organisation_id=case.organisation_id,
            project_id=case.project_id,
            case_id=case.id,
            verification_category=category,
            issue_type=issue_type,
            severity=severity,
            description=description,
            detection_method="deterministic_rule",
            details_json=details,
            resolution_state=IssueResolutionState.OPEN.value,
        )
