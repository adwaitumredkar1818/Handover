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
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.enums import (
    ConflictResolutionState,
    IssueResolutionState,
    MachineAssessmentStatus,
    RelationshipBasis,
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
from app.repositories.verification import (
    VerificationCaseRepository,
    VerificationIssueRepository,
    VerificationRepository,
)
from app.services.verification_taxonomy import (
    get_severity_penalty,
    get_source_authority_weight,
    get_taxonomy_entry,
)
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
    "use", "using", "uses",
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


def verify_excerpt_grounding(
    excerpt: str, chunk: Any
) -> tuple[bool, float, str, dict[str, Any]]:
    """Determine whether an excerpt is grounded verbatim or via fuzzy token overlap in a chunk."""
    chunk_text = chunk if isinstance(chunk, str) else (getattr(chunk, "chunk_text", None) or "")
    excerpt_norm = re.sub(r'[\s“”"\'`]+', " ", excerpt).strip().lower()
    chunk_norm = re.sub(r'[\s“”"\'`]+', " ", chunk_text).strip().lower()

    if excerpt_norm and excerpt_norm in chunk_norm:
        return True, 1.0, "verbatim", {"normalized_match": True, "containment_ratio": 1.0}

    toks_e = _tokenize(excerpt)
    toks_c = _tokenize(chunk_text)
    if not toks_e:
        return False, 0.0, "unsupported", {"containment_ratio": 0.0}

    overlap = toks_e & toks_c
    containment = len(overlap) / len(toks_e)
    if containment >= 0.85:
        return True, round(containment, 4), "fuzzy_token_overlap", {
            "containment_ratio": round(containment, 4),
            "matched_tokens": sorted(list(overlap)),
        }
    return False, round(containment, 4), "unsupported", {
        "containment_ratio": round(containment, 4),
        "missing_tokens": sorted(list(toks_e - toks_c)),
    }


def verify_claim_support(
    title: str, summary: str, chunks: list[Any]
) -> tuple[bool, float, list[str]]:
    """Verify whether core substantive claim tokens are grounded in cited chunk texts."""
    claim_tokens = _tokenize(f"{title} {summary}")
    if not claim_tokens:
        return True, 1.0, []

    chunk_tokens: set[str] = set()
    for ch in chunks:
        ch_text = ch if isinstance(ch, str) else (getattr(ch, "chunk_text", None) or "")
        chunk_tokens |= _tokenize(ch_text)

    grounded: set[str] = set()
    missing: list[str] = []

    for t in sorted(list(claim_tokens)):
        matched = False
        if t in chunk_tokens:
            matched = True
        else:
            t_stem = t.rstrip("s")
            for c in chunk_tokens:
                c_stem = c.rstrip("s")
                if t_stem == c_stem or (len(t) >= 4 and len(c) >= 4 and (t.startswith(c) or c.startswith(t))):
                    matched = True
                    break
        if matched:
            grounded.add(t)
        else:
            missing.append(t)

    ratio = len(grounded) / len(claim_tokens)
    supported = ratio >= 0.70
    return supported, round(ratio, 4), missing


def calculate_composite_confidence(
    *,
    target_type: VerificationTargetType | str,
    evidence_links: list[Any],
    issues: list[dict[str, Any]],
    conflicts_count: int = 0,
    is_stale: bool = False,
    is_inferred: bool = False,
) -> tuple[float, dict[str, Any]]:
    """Calibrate composite confidence score with authority, freshness, coverage, and penalties."""
    authority_scores = []
    coverage_lengths = []
    for link in evidence_links:
        ev = getattr(link, "evidence_item", None)
        st = getattr(ev, "source_type", None)
        authority_scores.append(get_source_authority_weight(st))
        chunk = getattr(link, "evidence_chunk", None)
        text = getattr(chunk, "chunk_text", "") or ""
        coverage_lengths.append(len(text))

    if authority_scores:
        authority_score = max(authority_scores)
    else:
        authority_score = 0.50

    freshness_score = 0.40 if is_stale else 1.00

    if not evidence_links:
        coverage_score = 0.0
    else:
        avg_len = sum(coverage_lengths) / len(coverage_lengths) if coverage_lengths else 0
        base_cov = min(1.0, 0.50 + 0.10 * len(evidence_links) + (0.20 if avg_len > 100 else 0.0))
        coverage_score = base_cov

    if is_inferred:
        coverage_score = coverage_score * 0.80

    conflict_penalty = 0.25 if conflicts_count > 0 else 0.0

    issue_penalty = 0.0
    for iss in issues:
        sev = iss.get("severity")
        issue_penalty += get_severity_penalty(sev)

    if not evidence_links:
        base_confidence = 0.20 * freshness_score
    else:
        base_confidence = 0.45 * authority_score + 0.35 * coverage_score + 0.20 * freshness_score

    final_score = max(0.0, min(1.0, round(base_confidence - conflict_penalty - issue_penalty, 4)))

    breakdown = {
        "authority_score": round(authority_score, 4),
        "freshness_score": round(freshness_score, 4),
        "coverage_score": round(coverage_score, 4),
        "conflict_penalty": round(conflict_penalty, 4),
        "issue_penalty": round(issue_penalty, 4),
    }
    return final_score, breakdown


@dataclass
class AssessmentResult:
    """In-memory assessment outcome from deterministic rules."""

    target_type: VerificationTargetType
    target_id: uuid.UUID
    project_id: uuid.UUID
    organisation_id: uuid.UUID
    machine_status: MachineAssessmentStatus
    priority: VerificationPriority
    issues: list[dict[str, Any]] = field(default_factory=list)
    assessment_metadata: dict[str, Any] = field(default_factory=dict)


class VerificationIntelligenceEngine:
    """Deterministic intelligence engine assessing findings, relationships, and claim grounding."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.case_repo = VerificationCaseRepository(session)
        self.issue_repo = VerificationIssueRepository(session)

    def assess_knowledge_item(self, item: KnowledgeItem) -> AssessmentResult:
        issues: list[dict[str, Any]] = []

        links_stmt = (
            select(KnowledgeEvidenceLink)
            .where(KnowledgeEvidenceLink.knowledge_item_id == item.id)
            .options(
                selectinload(KnowledgeEvidenceLink.evidence_item),
                selectinload(KnowledgeEvidenceLink.evidence_chunk),
            )
        )
        links = list(self.session.execute(links_stmt).scalars().all())

        chunks_text: list[str] = []
        is_stale = getattr(item, "is_stale", False) or False

        if not links:
            entry = get_taxonomy_entry(VerificationIssueType.MISSING_EVIDENCE)
            issues.append({
                "issue_type": VerificationIssueType.MISSING_EVIDENCE,
                "severity": entry.default_severity,
                "category": entry.category,
                "description": "Finding has no supporting evidence links.",
                "details_json": {"reason": "zero_links_found"},
                "conflicting_evidence_id": None,
                "conflicting_chunk_id": None,
            })
        else:
            for link in links:
                ev = link.evidence_item
                chunk = link.evidence_chunk

                if not ev or ev.project_id != item.project_id:
                    entry = get_taxonomy_entry(VerificationIssueType.INVALID_SOURCE_REFERENCE)
                    issues.append({
                        "issue_type": VerificationIssueType.INVALID_SOURCE_REFERENCE,
                        "severity": entry.default_severity,
                        "category": entry.category,
                        "description": "Cited evidence item is invalid or not in workspace.",
                        "details_json": {"cited_evidence_id": str(link.evidence_id)},
                        "conflicting_evidence_id": link.evidence_id,
                        "conflicting_chunk_id": link.evidence_chunk_id,
                    })
                    continue

                if chunk and getattr(chunk, "chunk_text", None):
                    chunks_text.append(chunk.chunk_text)

                if link.supporting_excerpt:
                    is_gr, score, mode, details = verify_excerpt_grounding(link.supporting_excerpt, chunk)
                    if not is_gr:
                        entry = get_taxonomy_entry(VerificationIssueType.UNSUPPORTED_CLAIM)
                        issues.append({
                            "issue_type": VerificationIssueType.UNSUPPORTED_CLAIM,
                            "severity": entry.default_severity,
                            "category": entry.category,
                            "description": "Supporting excerpt could not be matched in source chunk.",
                            "details_json": {
                                "excerpt_preview": link.supporting_excerpt[:200],
                                "match_mode": mode,
                                "support_ratio": score,
                                "chunk_id": str(getattr(chunk, "id", None)),
                            },
                            "conflicting_evidence_id": ev.id,
                            "conflicting_chunk_id": getattr(chunk, "id", None),
                        })

                if getattr(ev, "processing_status", None) == "failed" or getattr(ev, "is_stale", False):
                    is_stale = True
                    entry = get_taxonomy_entry(VerificationIssueType.STALE_KNOWLEDGE)
                    issues.append({
                        "issue_type": VerificationIssueType.STALE_KNOWLEDGE,
                        "severity": entry.default_severity,
                        "category": entry.category,
                        "description": "Cited evidence item is marked stale or failed processing.",
                        "details_json": {"evidence_id": str(ev.id)},
                        "conflicting_evidence_id": ev.id,
                        "conflicting_chunk_id": None,
                    })

        if chunks_text and not any(i["issue_type"] == VerificationIssueType.UNSUPPORTED_CLAIM for i in issues):
            item_summary = getattr(item, "structured_summary", "") or getattr(item, "summary", "") or ""
            supported, ratio, missing = verify_claim_support(item.title, item_summary, chunks_text)
            if not supported:
                entry = get_taxonomy_entry(VerificationIssueType.UNSUPPORTED_CLAIM)
                issues.append({
                    "issue_type": VerificationIssueType.UNSUPPORTED_CLAIM,
                    "severity": entry.default_severity,
                    "category": entry.category,
                    "description": "Finding title and summary claim terms are not grounded in cited chunks.",
                    "details_json": {
                        "support_ratio": ratio,
                        "missing_tokens": missing,
                        "match_mode": "unsupported",
                    },
                    "conflicting_evidence_id": None,
                    "conflicting_chunk_id": None,
                })

        if getattr(item, "is_stale", False):
            if not any(i["issue_type"] == VerificationIssueType.STALE_KNOWLEDGE for i in issues):
                entry = get_taxonomy_entry(VerificationIssueType.STALE_KNOWLEDGE)
                issues.append({
                    "issue_type": VerificationIssueType.STALE_KNOWLEDGE,
                    "severity": entry.default_severity,
                    "category": entry.category,
                    "description": "Knowledge item is flagged as stale or superseded.",
                    "details_json": {"superseded_by_id": str(item.superseded_by_id) if item.superseded_by_id else None},
                    "conflicting_evidence_id": None,
                    "conflicting_chunk_id": None,
                })

        item_toks = _tokenize(item.title)
        other_items = (
            self.session.execute(
                select(KnowledgeItem).where(
                    KnowledgeItem.project_id == item.project_id,
                    KnowledgeItem.id != item.id,
                )
            )
            .scalars()
            .all()
        )
        dup_ids = []
        for o in other_items:
            if item.fingerprint and o.fingerprint and item.fingerprint == o.fingerprint:
                dup_ids.append(str(o.id))
                continue
            o_toks = _tokenize(o.title)
            if not item_toks or not o_toks:
                continue
            sim = _jaccard_similarity(item_toks, o_toks)
            overlap_ratio = len(item_toks & o_toks) / max(len(item_toks), len(o_toks))
            if sim >= 0.72 or overlap_ratio > 0.85:
                dup_ids.append(str(o.id))

        if dup_ids:
            entry = get_taxonomy_entry(VerificationIssueType.DUPLICATE_RECORD)
            issues.append({
                "issue_type": VerificationIssueType.DUPLICATE_RECORD,
                "severity": entry.default_severity,
                "category": entry.category,
                "description": f"Potential duplicate of {len(dup_ids)} other finding(s).",
                "details_json": {"duplicate_item_ids": dup_ids},
                "conflicting_evidence_id": None,
                "conflicting_chunk_id": None,
            })

        priority, machine_status = self._compute_priority_and_status(issues)

        conf_score, conf_breakdown = calculate_composite_confidence(
            target_type=VerificationTargetType.KNOWLEDGE_ITEM,
            evidence_links=links,
            issues=issues,
            conflicts_count=0,
            is_stale=is_stale,
        )

        return AssessmentResult(
            target_type=VerificationTargetType.KNOWLEDGE_ITEM,
            target_id=item.id,
            project_id=item.project_id,
            organisation_id=item.organisation_id,
            machine_status=machine_status,
            priority=priority,
            issues=issues,
            assessment_metadata={
                "assessed_at": datetime.now(UTC).isoformat(),
                "confidence_score": conf_score,
                "confidence_breakdown": conf_breakdown,
                "links_checked": len(links),
                "issues_count": len(issues),
            },
        )

    def assess_relationship(self, rel: KnowledgeRelationship) -> AssessmentResult:
        issues: list[dict[str, Any]] = []

        links_stmt = (
            select(RelationshipEvidenceLink)
            .where(RelationshipEvidenceLink.relationship_id == rel.id)
            .options(
                selectinload(RelationshipEvidenceLink.evidence_item),
                selectinload(RelationshipEvidenceLink.evidence_chunk),
            )
        )
        links = list(self.session.execute(links_stmt).scalars().all())

        if not links:
            entry = get_taxonomy_entry(VerificationIssueType.MISSING_EVIDENCE)
            issues.append({
                "issue_type": VerificationIssueType.MISSING_EVIDENCE,
                "severity": entry.default_severity,
                "category": entry.category,
                "description": "Relationship edge has no cited supporting evidence links.",
                "details_json": {"relationship_type": rel.relationship_type},
                "conflicting_evidence_id": None,
                "conflicting_chunk_id": None,
            })
        else:
            for link in links:
                if link.supporting_excerpt:
                    chunk = link.evidence_chunk
                    is_gr, score, mode, details = verify_excerpt_grounding(link.supporting_excerpt, chunk)
                    if not is_gr:
                        entry = get_taxonomy_entry(VerificationIssueType.UNSUPPORTED_CLAIM)
                        issues.append({
                            "issue_type": VerificationIssueType.UNSUPPORTED_CLAIM,
                            "severity": entry.default_severity,
                            "category": entry.category,
                            "description": "Relationship excerpt does not appear in cited chunk text.",
                            "details_json": {"excerpt": link.supporting_excerpt[:200], "match_mode": mode},
                            "conflicting_evidence_id": link.evidence_id,
                            "conflicting_chunk_id": link.evidence_chunk_id,
                        })

        is_inferred = rel.relationship_basis == RelationshipBasis.INFERRED
        if is_inferred:
            entry = get_taxonomy_entry(VerificationIssueType.UNCERTAIN_RELATIONSHIP)
            issues.append({
                "issue_type": VerificationIssueType.UNCERTAIN_RELATIONSHIP,
                "severity": entry.default_severity,
                "category": entry.category,
                "description": "Relationship was inferred without explicit key reference.",
                "details_json": {
                    "confidence_score": float(rel.confidence_score) if rel.confidence_score is not None else 0.85,
                    "inference_reason": getattr(rel, "inference_reason", None) or "contextual_match",
                },
                "conflicting_evidence_id": None,
                "conflicting_chunk_id": None,
            })

        source_ent = self.session.get(KnowledgeEntity, rel.source_entity_id)
        target_ent = self.session.get(KnowledgeEntity, rel.target_entity_id)
        if not source_ent or not target_ent:
            entry = get_taxonomy_entry(VerificationIssueType.INVALID_ENTITY_MAPPING)
            issues.append({
                "issue_type": VerificationIssueType.INVALID_ENTITY_MAPPING,
                "severity": entry.default_severity,
                "category": entry.category,
                "description": "One or both linked entity nodes do not exist.",
                "details_json": {"source_exists": bool(source_ent), "target_exists": bool(target_ent)},
                "conflicting_evidence_id": None,
                "conflicting_chunk_id": None,
            })

        dup_rel_stmt = select(KnowledgeRelationship).where(
            KnowledgeRelationship.project_id == rel.project_id,
            KnowledgeRelationship.id != rel.id,
            KnowledgeRelationship.source_entity_id == rel.source_entity_id,
            KnowledgeRelationship.target_entity_id == rel.target_entity_id,
            KnowledgeRelationship.relationship_type == rel.relationship_type,
        )
        dup_rels = list(self.session.execute(dup_rel_stmt).scalars().all())
        if dup_rels:
            entry = get_taxonomy_entry(VerificationIssueType.DUPLICATE_RECORD)
            issues.append({
                "issue_type": VerificationIssueType.DUPLICATE_RECORD,
                "severity": entry.default_severity,
                "category": entry.category,
                "description": "Duplicate relationship connecting identical entities.",
                "details_json": {"duplicate_rel_ids": [str(d.id) for d in dup_rels]},
                "conflicting_evidence_id": None,
                "conflicting_chunk_id": None,
            })

        priority, machine_status = self._compute_priority_and_status(issues)

        conf_score, conf_breakdown = calculate_composite_confidence(
            target_type=VerificationTargetType.RELATIONSHIP,
            evidence_links=links,
            issues=issues,
            conflicts_count=0,
            is_stale=False,
            is_inferred=is_inferred,
        )

        return AssessmentResult(
            target_type=VerificationTargetType.RELATIONSHIP,
            target_id=rel.id,
            project_id=rel.project_id,
            organisation_id=rel.organisation_id,
            machine_status=machine_status,
            priority=priority,
            issues=issues,
            assessment_metadata={
                "assessed_at": datetime.now(UTC).isoformat(),
                "confidence_score": conf_score,
                "confidence_breakdown": conf_breakdown,
                "relationship_type": rel.relationship_type,
                "basis": rel.relationship_basis,
                "issues_count": len(issues),
            },
        )

    def persist_assessment(self, result: AssessmentResult) -> VerificationCase:
        tt = result.target_type.value if hasattr(result.target_type, "value") else str(result.target_type)
        case = self.case_repo.get_case_by_target(
            project_id=result.project_id,
            target_type=tt,
            target_id=result.target_id,
        )

        now = datetime.now(UTC)
        if case is None:
            initial_case_status = VerificationCaseStatus.PENDING_REVIEW.value
            if result.machine_status == MachineAssessmentStatus.PASSED:
                initial_case_status = VerificationCaseStatus.CANDIDATE.value
            elif any(i["severity"] == VerificationSeverity.CRITICAL for i in result.issues):
                initial_case_status = VerificationCaseStatus.UNRESOLVED.value

            case = VerificationCase(
                organisation_id=result.organisation_id,
                project_id=result.project_id,
                target_type=tt,
                target_id=result.target_id,
                case_status=initial_case_status,
                machine_assessment_status=result.machine_status.value if hasattr(result.machine_status, "value") else str(result.machine_status),
                priority=result.priority.value if hasattr(result.priority, "value") else str(result.priority),
                machine_assessment_json=result.assessment_metadata,
                last_assessed_at=now,
                version=1,
            )
            self.session.add(case)
            self.session.flush()
        else:
            case.machine_assessment_status = result.machine_status.value if hasattr(result.machine_status, "value") else str(result.machine_status)
            case.priority = result.priority.value if hasattr(result.priority, "value") else str(result.priority)
            case.machine_assessment_json = result.assessment_metadata
            case.last_assessed_at = now
            self.session.flush()

        if tt == VerificationTargetType.KNOWLEDGE_ITEM.value:
            kitem = self.session.get(KnowledgeItem, result.target_id)
            if kitem:
                c_meta = dict(kitem.confidence_metadata_json or {})
                c_meta["confidence_score"] = result.assessment_metadata.get("confidence_score", 0.85)
                c_meta["confidence_breakdown"] = result.assessment_metadata.get("confidence_breakdown", {})
                kitem.confidence_metadata_json = c_meta

        existing_issues = self.issue_repo.list_by_case(case.id, open_only=True)
        existing_types = {i.issue_type: i for i in existing_issues}
        new_types = {i["issue_type"] for i in result.issues}

        for itype, ex_issue in existing_types.items():
            if itype not in new_types:
                ex_issue.resolution_state = IssueResolutionState.RESOLVED.value
                ex_issue.resolution_reason = "Auto-resolved by re-assessment: issue condition no longer met."
                ex_issue.resolved_at = now

        for issue_dict in result.issues:
            itype_val = issue_dict["issue_type"].value if hasattr(issue_dict["issue_type"], "value") else str(issue_dict["issue_type"])
            if itype_val not in existing_types:
                sev_val = issue_dict["severity"].value if hasattr(issue_dict["severity"], "value") else str(issue_dict["severity"])
                new_issue = VerificationIssue(
                    organisation_id=result.organisation_id,
                    project_id=result.project_id,
                    case_id=case.id,
                    verification_category=issue_dict.get("category", "General"),
                    issue_type=itype_val,
                    severity=sev_val,
                    description=issue_dict["description"],
                    detection_method="deterministic_rule",
                    details_json=issue_dict.get("details_json", {}),
                    conflicting_evidence_id=issue_dict.get("conflicting_evidence_id"),
                    conflicting_chunk_id=issue_dict.get("conflicting_chunk_id"),
                    resolution_state=IssueResolutionState.OPEN.value,
                )
                self.session.add(new_issue)

        self.session.flush()
        return case

    def _compute_priority_and_status(
        self, issues: list[dict[str, Any]]
    ) -> tuple[VerificationPriority, MachineAssessmentStatus]:
        if not issues:
            return VerificationPriority.LOW, MachineAssessmentStatus.PASSED

        severities = {i["severity"] for i in issues}
        types = {i["issue_type"] for i in issues}

        if (
            VerificationIssueType.CONFLICTING_SOURCES in types
            or any(getattr(t, "value", str(t)) == VerificationIssueType.CONFLICTING_SOURCES.value for t in types)
        ):
            return VerificationPriority.HIGH, MachineAssessmentStatus.CONFLICT_DETECTED

        if (
            VerificationIssueType.MISSING_EVIDENCE in types
            or any(getattr(t, "value", str(t)) == VerificationIssueType.MISSING_EVIDENCE.value for t in types)
        ):
            return VerificationPriority.CRITICAL, MachineAssessmentStatus.INSUFFICIENT_EVIDENCE

        if VerificationSeverity.CRITICAL in severities or "critical" in severities:
            return VerificationPriority.CRITICAL, MachineAssessmentStatus.ISSUES_DETECTED

        if VerificationSeverity.HIGH in severities or "high" in severities:
            return VerificationPriority.HIGH, MachineAssessmentStatus.ISSUES_DETECTED

        if VerificationSeverity.MEDIUM in severities or "medium" in severities:
            return VerificationPriority.MEDIUM, MachineAssessmentStatus.ISSUES_DETECTED

        return VerificationPriority.LOW, MachineAssessmentStatus.UNCERTAIN


DeterministicVerificationEngine = VerificationIntelligenceEngine



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
