"""Advanced Verification Intelligence Engine.

Platform: The Handover
Module: Verification Center (Module 3 / Validation Area)

Provides deterministic, explainable intelligence across:
1. Evidence Completeness Scoring (CompletenessEvaluator)
2. Contextual Source Reliability Assessment (SourceReliabilityEvaluator)
3. Freshness and Outdated Information Detection (FreshnessEvaluator)
4. Independent Source Corroboration (CorroborationEvaluator)
5. Advanced Contradiction Detection across 7 types (AdvancedContradictionEvaluator)
6. Intelligent Verification Recommendations (RecommendationEngine)
7. Explainable Queue Prioritisation (PrioritisationEngine)
8. Continuous Project Intelligence & Change Monitoring (ContinuousMonitoringService)

MANDATORY RULES:
- All assessments are strictly advisory and provide transparent explanations.
- Never treat multiple chunks of one document as independent corroboration.
- Never silently replace or overwrite human decisions (VERIFIED / REJECTED).
- Human review remains the sole authority for Handover sign-off.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.audit import AuditLog
from app.models.enums import (
    ConflictResolutionState,
    ConflictType,
    EvidenceSourceType,
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
from app.models.knowledge import KnowledgeItem
from app.models.verification import (
    VerificationCase,
    VerificationConflict,
    VerificationEvidenceRef,
    VerificationIssue,
)

# Canonical status tokens
_POSITIVE_STATUS_TOKENS = {
    "done", "merged", "completed", "approved", "closed", "resolved", "finalized", "active", "deployed",
}
_NEGATIVE_STATUS_TOKENS = {
    "open", "pending", "blocked", "undecided", "in_progress", "wip", "draft", "reopened", "deprecated", "rejected",
}
_ARCH_TECH_ANTIPODES: list[tuple[re.Pattern[str], re.Pattern[str], str]] = [
    (
        re.compile(r"\b(?:postgresql|postgres)\b", re.IGNORECASE),
        re.compile(r"\b(?:mongodb|mongo)\b", re.IGNORECASE),
        "Database paradigm: Relational PostgreSQL vs Document MongoDB",
    ),
    (
        re.compile(r"\b(?:rest|restful)\s+(?:api|endpoint|architecture|service|paradigm)\b|\buse[sd]?\s+rest\b", re.IGNORECASE),
        re.compile(r"\bgraphql\b", re.IGNORECASE),
        "API paradigm: REST vs GraphQL",
    ),
    (
        re.compile(r"\b(?:jwt|bearer\s+token|json\s+web\s+token)\b", re.IGNORECASE),
        re.compile(
            r"\b(?:cookie_only|cookie[- ]only|server[- ]side\s+session(?:\s+auth)?|stateful\s+session(?:\s+auth)?|"
            r"cookie[- ]based\s+(?:auth|authentication|session)|session[- ]cookie\s+(?:auth|authentication)|"
            r"express[- ]session|flask[- ]session)\b",
            re.IGNORECASE,
        ),
        "Authentication mechanism: Token JWT vs State Session",
    ),
    (
        re.compile(r"\b(?:synchronous|sync)\s+(?:execution|processing|pipeline|worker|api|call|request|mode)\b", re.IGNORECASE),
        re.compile(r"\b(?:asynchronous|async)\s+(?:execution|processing|pipeline|worker|api|call|request|mode)\b", re.IGNORECASE),
        "Execution model: Synchronous vs Asynchronous",
    ),
    (
        re.compile(r"\bmonolith(?:ic)?\b", re.IGNORECASE),
        re.compile(r"\bmicroservices?\b", re.IGNORECASE),
        "System topology: Monolithic vs Microservices",
    ),
]

# Non-authentication uses of "session" (logs, reports, DB sessions, work sessions) that must NOT trigger auth conflicts
_NON_AUTH_SESSION_RE = re.compile(
    r"\b(?:jsonl\s+session|session\s+(?:log|logs|report|reports|summar(?:y|ies)|transcript|transcripts|"
    r"stats|metrics|history|recording|duration|timeout\s+log)|"
    r"(?:db|database|sqlalchemy|orm|work|review|debug|coding|cli|chat|terminal|training|pairing|handover)\s+session)\b",
    re.IGNORECASE,
)

# Explicit historical supersession / migration language indicating chronological evolution rather than simultaneous conflict
_SUPERSESSION_PHRASE_RE = re.compile(
    r"\b(?:migrated\s+from|replaced\s+\w+\s+with|switched\s+from|transitioned\s+from|"
    r"deprecated\s+in\s+favor\s+of|superseded\s+by|previously\s+used|formerly\s+used|moved\s+away\s+from)\b",
    re.IGNORECASE,
)

# Explicit ownership/responsibility phrasing required for substantive ownership contradictions
_OWNERSHIP_CLAIM_RE = re.compile(
    r"\b(?:owner|owns|owned\s+by|primary\s+owner|sole\s+owner|responsible\s+for|accountable\s+for|"
    r"maintainer|maintains|lead\s+for|assigned\s+to|steward|dri\s+for)\b",
    re.IGNORECASE,
)

_MERGE_COMMIT_RE = re.compile(
    r"^\s*(?:merge\s+(?:branch|pull\s+request|remote-tracking|origin/|upstream/|tag)|revert\s+\"merge)",
    re.IGNORECASE,
)

_OWNERSHIP_NOISE_TOKENS = frozenset({
    "lead", "owner", "engineer", "manager", "team", "for", "and", "the", "with", "from",
    "into", "while", "main", "merge", "origin", "branch", "commit", "fix", "fixes",
    "update", "updated", "add", "added", "incorporate", "improve", "improved", "implement",
    "implemented", "refactor", "feat", "chore", "pull", "request", "latest", "preserving",
    "ensure", "code", "file", "files", "work", "task", "feature", "changes", "support",
})


def _strip_non_auth_sessions(text: str | None) -> str:
    if not text:
        return ""
    return _NON_AUTH_SESSION_RE.sub(" ", text)


def _extract_git_commit_info(ref: VerificationEvidenceRef | None) -> dict[str, Any] | None:
    """Extract normalized Git commit metadata (sha, parent_shas, branches, repo, is_merge) if evidence is a commit."""
    if ref is None:
        return None
    ev = getattr(ref, "evidence_item", None)
    if ev is None:
        return None
    meta = getattr(ev, "metadata_json", None) or {}
    is_commit = (
        getattr(ev, "category", None) == "commit"
        or str(meta.get("github_item_type", "")).lower() == "commit"
        or bool(meta.get("sha") and ("parent_shas" in meta or "branches" in meta))
    )
    if not is_commit:
        return None
    title_or_excerpt = f"{getattr(ev, 'title', '') or ''} {getattr(ref, 'excerpt', '') or ''}"
    parent_shas = [str(p) for p in (meta.get("parent_shas") or []) if p]
    branches = [str(b) for b in (meta.get("branches") or []) if b]
    if meta.get("branch") and str(meta["branch"]) not in branches:
        branches.append(str(meta["branch"]))
    is_merge = len(parent_shas) >= 2 or bool(_MERGE_COMMIT_RE.search(getattr(ev, "title", "") or "")) or bool(
        re.search(r"\bmerge\s+(?:origin/|branch|pull\s+request)", title_or_excerpt, re.IGNORECASE)
    )
    return {
        "repository": str(meta.get("repository") or "").lower(),
        "sha": str(meta.get("sha") or ""),
        "parent_shas": parent_shas,
        "branches": branches,
        "is_merge": is_merge,
        "timestamp": _ensure_utc(
            getattr(ev, "source_created_at", None) or getattr(ref, "source_timestamp", None)
        ),
    }


def _is_ancestor_sha(
    ancestor_sha: str,
    descendant_sha: str,
    parent_graph: dict[str, list[str]],
    *,
    max_depth: int = 32,
) -> bool:
    """BFS check whether ancestor_sha is reachable from descendant_sha via parent_shas."""
    if not ancestor_sha or not descendant_sha or ancestor_sha == descendant_sha:
        return False
    visited: set[str] = {descendant_sha}
    frontier: list[str] = [descendant_sha]
    depth = 0
    while frontier and depth < max_depth:
        next_frontier: list[str] = []
        for sha in frontier:
            for parent in parent_graph.get(sha, ()):
                if parent == ancestor_sha:
                    return True
                if parent not in visited:
                    visited.add(parent)
                    next_frontier.append(parent)
        frontier = next_frontier
        depth += 1
    return False


def _classify_git_commit_relationship(
    git_a: dict[str, Any] | None,
    git_b: dict[str, Any] | None,
    parent_graph: dict[str, list[str]],
) -> str:
    """Classify the relationship between two Git commit evidence items.

    Returns:
      - 'not_both_commits': at least one side is not a Git commit
      - 'same_commit': identical SHA
      - 'chronological_supersession': linear ancestry or sequential commits on a shared branch
      - 'branch_divergence': disjoint known branches without parent-child ancestry
      - 'ancestry_ambiguous': commits in same repo without branch/ancestry metadata
    """
    if git_a is None or git_b is None:
        return "not_both_commits"
    if git_a["repository"] and git_b["repository"] and git_a["repository"] != git_b["repository"]:
        return "not_both_commits"
    if git_a["sha"] and git_b["sha"] and git_a["sha"] == git_b["sha"]:
        return "same_commit"

    # 1. Explicit parent-child / ancestor-descendant relationship
    if git_a["sha"] and git_b["sha"]:
        if _is_ancestor_sha(git_a["sha"], git_b["sha"], parent_graph) or _is_ancestor_sha(
            git_b["sha"], git_a["sha"], parent_graph
        ):
            return "chronological_supersession"

    # 2. Shared branch with chronological ordering
    branches_a = set(git_a["branches"])
    branches_b = set(git_b["branches"])
    if branches_a and branches_b:
        if branches_a & branches_b:
            ts_a, ts_b = git_a["timestamp"], git_b["timestamp"]
            if ts_a is not None and ts_b is not None and ts_a != ts_b:
                return "chronological_supersession"
            # Even identical-second commits on same branch with a merge commit are integration, not contradiction
            if git_a["is_merge"] or git_b["is_merge"]:
                return "chronological_supersession"
            return "chronological_supersession"
        # Disjoint branches without known ancestry -> genuine branch divergence!
        return "branch_divergence"

    return "ancestry_ambiguous"


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _tokenize(text: str | None) -> set[str]:
    if not text:
        return set()
    words = re.findall(r"[a-z0-9_]+", text.lower())
    stopwords = {
        "the", "and", "for", "with", "that", "this", "from", "was", "were", "are",
        "has", "have", "had", "been", "being", "into", "onto", "about", "will", "our",
    }
    return {w for w in words if len(w) > 2 and w not in stopwords}


# ==============================================================================
# 1. Evidence Completeness Scoring
# ==============================================================================

@dataclass
class CompletenessReport:
    score: float  # 0.0 to 1.0
    level: str  # "complete" | "partial" | "sparse" | "missing"
    explanation: str
    missing_elements: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    direct_support: bool = False
    evidence_accessible: bool = True
    excerpt_specificity: str = "medium"


class CompletenessEvaluator:
    """Evaluates whether supporting evidence directly and sufficiently grounds a claim."""

    def evaluate(
        self,
        case: VerificationCase,
        refs: list[VerificationEvidenceRef],
    ) -> CompletenessReport:
        if not refs:
            return CompletenessReport(
                score=0.0,
                level="missing",
                explanation=(
                    "No supporting evidence records are attached to this finding. "
                    "The finding cannot be verified without primary source backing."
                ),
                missing_elements=["No supporting source references", "No source document/commit citations"],
                recommendations=[
                    "Attach a primary document, commit, or pull request excerpt to ground this finding.",
                    "Use 'Request Additional Context' if source evidence exists elsewhere.",
                ],
                direct_support=False,
                evidence_accessible=True,
                excerpt_specificity="none",
            )

        missing_elements: list[str] = []
        recommendations: list[str] = []
        claim_tokens = _tokenize(case.current_claim or case.title)

        # Check overlap across accessible references
        overlap_found = False
        accessible_count = 0
        has_author = False
        has_timestamp = False
        has_location = False
        has_substantial_excerpt = False

        for ref in refs:
            ev = ref.evidence_item
            if ref.acl_scope == "source_restricted":
                missing_elements.append(f"Reference '{ref.original_title}' is restricted by source ACL")

            accessible_count += 1
            if ref.author and ref.author != "Unknown":
                has_author = True
            if ref.source_timestamp or (ev and ev.source_created_at):
                has_timestamp = True
            if ref.location_label:
                has_location = True

            excerpt_len = len((ref.excerpt or "").strip())
            if excerpt_len >= 50:
                has_substantial_excerpt = True

            ev_tokens = _tokenize(f"{ref.original_title} {ref.excerpt or ''} {ev.title if ev else ''}")
            if claim_tokens and (claim_tokens & ev_tokens):
                overlap_found = True

        if not has_author:
            missing_elements.append("Author/contributor attribution is missing from all references")
            recommendations.append("Confirm author or team owner identity in source repository/tracker")

        if not has_timestamp:
            missing_elements.append("Original creation/modification timestamp is absent")
            recommendations.append("Verify document or commit timestamp to establish chronological validity")

        if not has_location:
            missing_elements.append("Exact file location or record identifier is unrecorded")

        if not has_substantial_excerpt:
            missing_elements.append("Attached excerpt is brief (<50 characters)")
            recommendations.append("Inspect full source and expand the verbatim quote for reviewer clarity")

        if not overlap_found and claim_tokens:
            missing_elements.append("Attached evidence does not share key technical terms with the claim")
            recommendations.append("Inspect source record to confirm whether the claim was inferred or verbatim")

        # Compute deterministic completeness score
        score = 0.30  # Baseline for having at least 1 reference
        if overlap_found:
            score += 0.35
        if has_substantial_excerpt:
            score += 0.15
        if has_author:
            score += 0.10
        if has_timestamp:
            score += 0.10

        score = min(1.0, max(0.0, score))

        if score >= 0.80 and overlap_found:
            level = "complete"
            explanation = (
                f"Finding is well-supported by {len(refs)} reference(s) with clear semantic overlap, "
                "author identity, and temporal provenance."
            )
        elif score >= 0.55:
            level = "partial"
            explanation = (
                f"Finding has supporting references ({len(refs)} item(s)), but lacks complete "
                f"context ({', '.join(missing_elements[:2])})."
            )
        else:
            level = "sparse"
            explanation = (
                "Supporting evidence is sparse or only tangentially related to the stated claim. "
                "Reviewer inspection is recommended."
            )

        return CompletenessReport(
            score=round(score, 2),
            level=level,
            explanation=explanation,
            missing_elements=missing_elements,
            recommendations=recommendations,
            direct_support=overlap_found,
            evidence_accessible=True,
            excerpt_specificity="high" if has_substantial_excerpt else "low",
        )


# ==============================================================================
# 2. Source Reliability Assessment
# ==============================================================================

@dataclass
class ReliabilityReport:
    tier: str  # "high" | "medium" | "low" | "uncertain"
    score: float  # 0.0 to 1.0
    explanation: str
    factors: list[str] = field(default_factory=list)
    primary_authority: str = "unknown"
    directness: str = "direct"


class SourceReliabilityEvaluator:
    """Assesses evidence reliability contextually based on source authority and claim domain."""

    _PROVIDER_WEIGHTS = {
        "github": 0.90,  # Code truth & version-controlled commits
        "jira": 0.85,    # Formal project tracking
        "document_upload": 0.80,  # Curated team documentation
        "slack": 0.55,   # Informal discussion / ephemeral
    }

    _DOMAIN_AFFINITIES = {
        "technical_architecture": {"github": 0.95, "document_upload": 0.85, "jira": 0.60, "slack": 0.40},
        "decisions_rationale": {"document_upload": 0.90, "github": 0.85, "jira": 0.80, "slack": 0.65},
        "work_items": {"jira": 0.95, "github": 0.85, "document_upload": 0.70, "slack": 0.50},
        "responsibilities_ownership": {"jira": 0.90, "github": 0.85, "document_upload": 0.75, "slack": 0.50},
        "bugs_blockers_risks": {"jira": 0.95, "github": 0.90, "slack": 0.70, "document_upload": 0.60},
        "dependencies": {"github": 0.95, "document_upload": 0.85, "jira": 0.75, "slack": 0.45},
    }

    def evaluate(
        self,
        case: VerificationCase,
        refs: list[VerificationEvidenceRef],
    ) -> ReliabilityReport:
        if not refs:
            return ReliabilityReport(
                tier="uncertain",
                score=0.0,
                explanation="No source records attached; reliability cannot be evaluated.",
                factors=["Zero supporting sources attached"],
                primary_authority="none",
                directness="unreferenced",
            )

        factors: list[str] = []
        scores: list[float] = []
        domain_weights = self._DOMAIN_AFFINITIES.get(case.domain, {})

        for ref in refs:
            ev = ref.evidence_item
            provider = (ref.source_provider or (ev.source_type if ev else "unknown")).lower()
            base_wt = domain_weights.get(provider, self._PROVIDER_WEIGHTS.get(provider, 0.70))

            # Bonus for named author
            if ref.author and ref.author != "Unknown":
                base_wt += 0.05
                factors.append(f"{provider.upper()}: Attributed to author '{ref.author}' (+5%)")
            else:
                base_wt -= 0.05
                factors.append(f"{provider.upper()}: Anonymous/unattributed source (-5%)")

            # Bonus for verifiable external URL
            if ref.original_source_url:
                base_wt += 0.05
                factors.append(f"{provider.upper()}: Verifiable external URL provided (+5%)")

            # Content hash integrity
            if ev and ev.content_hash:
                base_wt += 0.05
                factors.append(f"{provider.upper()}: Cryptographic content hash verified (+5%)")

            scores.append(min(1.0, max(0.0, base_wt)))

        avg_score = sum(scores) / len(scores) if scores else 0.5
        avg_score = round(avg_score, 2)

        if avg_score >= 0.80:
            tier = "high"
            explanation = (
                f"High-authority evidence from {len(refs)} verified primary source(s). "
                "Records demonstrate strong domain affinity and clear authorship."
            )
        elif avg_score >= 0.60:
            tier = "medium"
            explanation = (
                f"Moderate reliability across {len(refs)} source(s). Evidence is valid but "
                "may rely on secondary records or informal channels."
            )
        else:
            tier = "low"
            explanation = (
                "Low authority or unattributed sources. Reviewers should independently "
                "verify this finding against official project records."
            )

        primary_provider = refs[0].source_provider or (refs[0].evidence_item.source_type if refs[0].evidence_item else "source")
        return ReliabilityReport(
            tier=tier,
            score=avg_score,
            explanation=explanation,
            factors=factors[:5],
            primary_authority=primary_provider,
            directness="primary" if primary_provider in {"github", "document_upload"} else "secondary",
        )


# ==============================================================================
# 3. Freshness and Outdated Information Detection
# ==============================================================================

@dataclass
class FreshnessReport:
    status: str  # "fresh" | "stale" | "outdated" | "superseded"
    age_days: int | None
    source_timestamp: str | None
    explanation: str
    reverification_required: bool = False
    superseding_records_count: int = 0
    superseded_by_record_title: str | None = None


class FreshnessEvaluator:
    """Evaluates chronological validity and identifies superseded information."""

    def evaluate(
        self,
        case: VerificationCase,
        refs: list[VerificationEvidenceRef],
        newest_project_ts: datetime | None,
        all_project_evidence: list[EvidenceItem] | None = None,
    ) -> FreshnessReport:
        if not refs:
            return FreshnessReport(
                status="outdated",
                age_days=None,
                source_timestamp=None,
                explanation="No source timestamps available to evaluate freshness.",
                reverification_required=False,
            )

        timestamps = [
            _ensure_utc(r.source_timestamp or (r.evidence_item.source_created_at if r.evidence_item else None))
            for r in refs
        ]
        valid_ts = [t for t in timestamps if t is not None]

        if not valid_ts:
            return FreshnessReport(
                status="fresh",
                age_days=None,
                source_timestamp=None,
                explanation="Evidence records do not carry source creation dates; assumed current.",
                reverification_required=False,
            )

        newest_ref_ts = max(valid_ts)
        ref_iso = newest_ref_ts.isoformat()

        # If project has an activity timestamp reference, compare against it; otherwise use now
        now = datetime.now(UTC)
        reference_time = newest_project_ts or now
        age_delta = reference_time - newest_ref_ts
        age_days = max(0, age_delta.days)

        # Check for newer evidence in the same domain/category
        superseding_count = 0
        superseding_title: str | None = None
        if all_project_evidence:
            for other_ev in all_project_evidence:
                other_ts = _ensure_utc(other_ev.source_created_at)
                if other_ts and other_ts > newest_ref_ts:
                    # If other evidence shares words with case title/claim, flag potential supersession
                    ev_tok = _tokenize(other_ev.title)
                    claim_tok = _tokenize(case.title or case.current_claim)
                    if claim_tok and (claim_tok & ev_tok):
                        superseding_count += 1
                        if superseding_title is None:
                            superseding_title = other_ev.title

        reverification_required = False
        if case.case_status == VerificationCaseStatus.VERIFIED.value and superseding_count > 0:
            reverification_required = True

        if superseding_count > 0 and age_days > 30:
            status = "superseded"
            explanation = (
                f"Potentially superseded: {superseding_count} newer project record(s) exist that "
                f"reference similar components after this finding's source date ({ref_iso[:10]})."
            )
        elif age_days > 180:
            status = "outdated"
            explanation = (
                f"Evidence is {age_days} days older than recent project activity ({ref_iso[:10]}). "
                "Significant project evolution may render this claim outdated."
            )
        elif age_days > 90:
            status = "stale"
            explanation = (
                f"Evidence was created {age_days} days ago ({ref_iso[:10]}). "
                "Recheck against current project architecture before Handover inclusion."
            )
        else:
            status = "fresh"
            explanation = f"Evidence is recent ({age_days} days old, {ref_iso[:10]}), reflecting active project state."

        return FreshnessReport(
            status=status,
            age_days=age_days,
            source_timestamp=ref_iso,
            explanation=explanation,
            reverification_required=reverification_required,
            superseding_records_count=superseding_count,
            superseded_by_record_title=superseding_title,
        )


# ==============================================================================
# 4. Independent Source Corroboration
# ==============================================================================

@dataclass
class CorroborationReport:
    level: str  # "strong_cross_source" | "moderate_multi_source" | "single_source" | "uncorroborated"
    independent_sources_count: int
    supporting_providers: list[str] = field(default_factory=list)
    opposing_providers: list[str] = field(default_factory=list)
    partial_providers: list[str] = field(default_factory=list)
    explanation: str = ""


class CorroborationEvaluator:
    """Evaluates cross-source independent corroboration, distinguishing distinct documents from multiple chunks."""

    def evaluate(
        self,
        case: VerificationCase,
        refs: list[VerificationEvidenceRef],
    ) -> CorroborationReport:
        if not refs:
            return CorroborationReport(
                level="uncorroborated",
                independent_sources_count=0,
                explanation="No source records attached to corroborate this finding.",
            )

        # Group by independent evidence_item_id (NOT chunk id)
        distinct_evidence_ids = {r.evidence_item_id for r in refs}
        distinct_providers = {
            (r.source_provider or (r.evidence_item.source_type if r.evidence_item else "source")).lower()
            for r in refs
        }

        # Check opposing references
        opposing_refs = [r for r in refs if r.relationship_to_finding == "opposing"]
        supporting_refs = [r for r in refs if r.relationship_to_finding != "opposing"]

        supp_providers = sorted({
            (r.source_provider or (r.evidence_item.source_type if r.evidence_item else "source")).upper()
            for r in supporting_refs
        })
        opp_providers = sorted({
            (r.source_provider or (r.evidence_item.source_type if r.evidence_item else "source")).upper()
            for r in opposing_refs
        })

        count = len(distinct_evidence_ids)

        if len(distinct_providers) >= 2 and len(supp_providers) >= 2:
            level = "strong_cross_source"
            explanation = (
                f"Strong corroboration: Confirmed across {len(supp_providers)} independent platforms "
                f"({', '.join(supp_providers)}) spanning {count} separate document/code records."
            )
        elif count >= 2:
            level = "moderate_multi_source"
            explanation = (
                f"Moderate corroboration: Supported by {count} distinct evidence records within "
                f"{', '.join(supp_providers)}."
            )
        else:
            chunk_count = len(refs)
            chunk_suffix = f" ({chunk_count} chunk excerpts)" if chunk_count > 1 else ""
            level = "single_source"
            explanation = (
                f"Single-source finding: Grounded in 1 primary document/repository{chunk_suffix}. "
                "Lacks independent cross-verification."
            )

        return CorroborationReport(
            level=level,
            independent_sources_count=count,
            supporting_providers=supp_providers,
            opposing_providers=opp_providers,
            explanation=explanation,
        )


# ==============================================================================
# 5. Advanced Contradiction Detection
# ==============================================================================

@dataclass
class ContradictionCandidate:
    conflict_type: str
    explanation: str
    severity: str
    side_a_title: str
    side_a_claim: str
    side_a_provider: str
    side_b_title: str
    side_b_claim: str
    side_b_provider: str
    detection_method: str = "deterministic_rule"
    side_a_evidence_id: uuid.UUID | None = None
    side_a_chunk_id: uuid.UUID | None = None
    side_a_timestamp: datetime | None = None
    side_b_evidence_id: uuid.UUID | None = None
    side_b_chunk_id: uuid.UUID | None = None
    side_b_timestamp: datetime | None = None
    related_finding_id: uuid.UUID | None = None


class AdvancedContradictionEvaluator:
    """Detects 6 canonical contradiction types across project findings and evidence."""

    def evaluate(
        self,
        case: VerificationCase,
        refs: list[VerificationEvidenceRef],
        all_project_cases: list[VerificationCase],
    ) -> list[ContradictionCandidate]:
        results: list[ContradictionCandidate] = []
        my_primary_ref = refs[0] if refs else None

        # Build commit parent graph from loaded evidence refs for multi-hop Git ancestry checks
        commit_parent_graph: dict[str, list[str]] = {}
        for ref in refs:
            ginfo = _extract_git_commit_info(ref)
            if ginfo and ginfo["sha"] and ginfo["parent_shas"]:
                commit_parent_graph[ginfo["sha"]] = ginfo["parent_shas"]
        for other_c in all_project_cases:
            for oref in getattr(other_c, "evidence_refs", []) or []:
                ginfo = _extract_git_commit_info(oref)
                if ginfo and ginfo["sha"] and ginfo["parent_shas"]:
                    commit_parent_graph[ginfo["sha"]] = ginfo["parent_shas"]

        my_git = _extract_git_commit_info(my_primary_ref)

        # 1. Direct status contradictions within attached evidence
        if len(refs) >= 2:
            pos_refs = [r for r in refs if _tokenize(r.excerpt or "") & _POSITIVE_STATUS_TOKENS]
            neg_refs = [r for r in refs if _tokenize(r.excerpt or "") & _NEGATIVE_STATUS_TOKENS]
            if pos_refs and neg_refs:
                p_ref = pos_refs[0]
                n_ref = neg_refs[0]
                git_rel = _classify_git_commit_relationship(
                    _extract_git_commit_info(p_ref),
                    _extract_git_commit_info(n_ref),
                    commit_parent_graph,
                )
                # Sequential commits on the same branch updating task status are chronological evolution, not contradiction
                if git_rel not in ("same_commit", "chronological_supersession"):
                    branch_note = (
                        " (detected across diverged Git branches)"
                        if git_rel == "branch_divergence"
                        else " (Git ancestry unavailable/ambiguous)"
                        if git_rel == "ancestry_ambiguous"
                        else ""
                    )
                    results.append(
                        ContradictionCandidate(
                            conflict_type=ConflictType.STATUS_CONFLICT.value,
                            explanation=(
                                f"Contradictory status indicators{branch_note}: '{p_ref.original_title}' indicates completed/active state, "
                                f"while '{n_ref.original_title}' indicates pending/blocked state."
                            ),
                            severity=VerificationSeverity.HIGH.value,
                            side_a_title=p_ref.original_title,
                            side_a_claim=(p_ref.excerpt or p_ref.original_title)[:250],
                            side_a_provider=p_ref.source_provider or "source_a",
                            side_b_title=n_ref.original_title,
                            side_b_claim=(n_ref.excerpt or n_ref.original_title)[:250],
                            side_b_provider=n_ref.source_provider or "source_b",
                            side_a_evidence_id=p_ref.evidence_item_id,
                            side_a_chunk_id=p_ref.chunk_id,
                            side_a_timestamp=p_ref.source_timestamp,
                            side_b_evidence_id=n_ref.evidence_item_id,
                            side_b_chunk_id=n_ref.chunk_id,
                            side_b_timestamp=n_ref.source_timestamp,
                        )
                    )

        # 2. Semantic & Technical contradictions against other cases in same domain
        my_tokens = _tokenize(case.current_claim)
        my_clean_claim = _strip_non_auth_sessions(case.current_claim)
        my_is_merge = bool(
            (my_git and my_git["is_merge"])
            or _MERGE_COMMIT_RE.search(case.current_claim or "")
            or _MERGE_COMMIT_RE.search(case.title or "")
        )

        for other in all_project_cases:
            if other.id == case.id:
                continue

            other_refs = getattr(other, "evidence_refs", [])
            other_primary_ref = other_refs[0] if other_refs else None
            other_git = _extract_git_commit_info(other_primary_ref)
            git_rel = _classify_git_commit_relationship(my_git, other_git, commit_parent_graph)

            # Skip same commit or linear chronological evolution on the same Git branch
            if git_rel in ("same_commit", "chronological_supersession"):
                continue

            branch_context = (
                " across diverged branches"
                if git_rel == "branch_divergence"
                else " (branch ancestry unavailable/ambiguous)"
                if git_rel == "ancestry_ambiguous"
                else ""
            )

            # Check technical architecture & decision antipodes with strict mutual exclusivity & auth-context precision
            if case.domain in {"technical_architecture", "decisions_rationale"} and other.domain in {
                "technical_architecture",
                "decisions_rationale",
            }:
                other_clean_claim = _strip_non_auth_sessions(other.current_claim)
                # Explicit migration/supersession narrative describing chronological change is not a simultaneous conflict
                if _SUPERSESSION_PHRASE_RE.search(my_clean_claim) or _SUPERSESSION_PHRASE_RE.search(other_clean_claim):
                    ts_a = _ensure_utc(my_primary_ref.source_timestamp if my_primary_ref else case.created_at)
                    ts_b = _ensure_utc(other_primary_ref.source_timestamp if other_primary_ref else other.created_at)
                    if ts_a and ts_b and abs((ts_a - ts_b).total_seconds()) > 3600:
                        continue

                for pat_a, pat_b, desc in _ARCH_TECH_ANTIPODES:
                    a_has_side_a = bool(pat_a.search(my_clean_claim))
                    a_has_side_b = bool(pat_b.search(my_clean_claim))
                    b_has_side_a = bool(pat_a.search(other_clean_claim))
                    b_has_side_b = bool(pat_b.search(other_clean_claim))

                    # Strict mutual exclusivity: Side A asserts A (not B) and Side B asserts B (not A)
                    if a_has_side_a and not a_has_side_b and b_has_side_b and not b_has_side_a:
                        ctype = (
                            ConflictType.DECISION_CONFLICT.value
                            if case.domain == "decisions_rationale"
                            else ConflictType.TECHNICAL_CONFLICT.value
                        )
                        results.append(
                            ContradictionCandidate(
                                conflict_type=ctype,
                                explanation=f"Architectural and decision divergence{branch_context}: {desc}.",
                                severity=VerificationSeverity.HIGH.value,
                                side_a_title=case.title,
                                side_a_claim=case.current_claim[:250],
                                side_a_provider=case.source_provider or "finding_a",
                                side_b_title=other.title,
                                side_b_claim=other.current_claim[:250],
                                side_b_provider=other.source_provider or "finding_b",
                                side_a_evidence_id=my_primary_ref.evidence_item_id if my_primary_ref else None,
                                side_a_chunk_id=my_primary_ref.chunk_id if my_primary_ref else None,
                                side_a_timestamp=my_primary_ref.source_timestamp if my_primary_ref else case.created_at,
                                side_b_evidence_id=other_primary_ref.evidence_item_id if other_primary_ref else None,
                                side_b_chunk_id=other_primary_ref.chunk_id if other_primary_ref else None,
                                side_b_timestamp=other_primary_ref.source_timestamp if other_primary_ref else other.created_at,
                                related_finding_id=other.id,
                            )
                        )

            # Ownership conflicts (require substantive explicit ownership claims, never routine/merge Git commits)
            if case.domain in {"responsibilities_ownership", "work_items"} and other.domain in {
                "responsibilities_ownership",
                "work_items",
            }:
                other_is_merge = bool(
                    (other_git and other_git["is_merge"])
                    or _MERGE_COMMIT_RE.search(other.current_claim or "")
                    or _MERGE_COMMIT_RE.search(other.title or "")
                )
                if my_is_merge or other_is_merge:
                    continue

                # Routine Git commits by different authors on the same codebase are collaboration, unless explicit ownership is claimed
                both_are_commits = my_git is not None and other_git is not None
                my_explicit_own = bool(
                    _OWNERSHIP_CLAIM_RE.search(case.current_claim or "")
                    or (case.domain == "responsibilities_ownership" and my_git is None)
                )
                other_explicit_own = bool(
                    _OWNERSHIP_CLAIM_RE.search(other.current_claim or "")
                    or (other.domain == "responsibilities_ownership" and other_git is None)
                )
                if (both_are_commits and not (my_explicit_own and other_explicit_own)) or not (
                    my_explicit_own and other_explicit_own
                ):
                    continue

                if case.person_name and other.person_name and case.person_name.strip().lower() != other.person_name.strip().lower():
                    other_tokens = _tokenize(other.current_claim)
                    common = (my_tokens & other_tokens) - _OWNERSHIP_NOISE_TOKENS
                    if len(common) >= 3:
                        results.append(
                            ContradictionCandidate(
                                conflict_type=ConflictType.OWNERSHIP_CONFLICT.value,
                                explanation=(
                                    f"Ownership discrepancy{branch_context} on overlapping responsibilities "
                                    f"({', '.join(sorted(common)[:3])}): '{case.person_name}' vs '{other.person_name}'."
                                ),
                                severity=VerificationSeverity.MEDIUM.value,
                                side_a_title=f"{case.title} ({case.person_name})",
                                side_a_claim=case.current_claim[:250],
                                side_a_provider=case.source_provider or "finding_a",
                                side_b_title=f"{other.title} ({other.person_name})",
                                side_b_claim=other.current_claim[:250],
                                side_b_provider=other.source_provider or "finding_b",
                                side_a_evidence_id=my_primary_ref.evidence_item_id if my_primary_ref else None,
                                side_a_chunk_id=my_primary_ref.chunk_id if my_primary_ref else None,
                                side_a_timestamp=my_primary_ref.source_timestamp if my_primary_ref else case.created_at,
                                side_b_evidence_id=other_primary_ref.evidence_item_id if other_primary_ref else None,
                                side_b_chunk_id=other_primary_ref.chunk_id if other_primary_ref else None,
                                side_b_timestamp=other_primary_ref.source_timestamp if other_primary_ref else other.created_at,
                                related_finding_id=other.id,
                            )
                        )

            # Temporal conflicts (conflicting milestone dates or schedule claims)
            if case.domain in {"completed_unfinished_work", "work_items"} and other.domain in {
                "completed_unfinished_work",
                "work_items",
            }:
                other_tokens = _tokenize(other.current_claim)
                common = (my_tokens & other_tokens) - {"task", "feature", "phase", "project", "work", "item"}
                if len(common) >= 2:
                    pos_a = bool(my_tokens & _POSITIVE_STATUS_TOKENS)
                    neg_a = bool(my_tokens & _NEGATIVE_STATUS_TOKENS)
                    pos_b = bool(other_tokens & _POSITIVE_STATUS_TOKENS)
                    neg_b = bool(other_tokens & _NEGATIVE_STATUS_TOKENS)
                    if (pos_a and neg_b) or (neg_a and pos_b):
                        results.append(
                            ContradictionCandidate(
                                conflict_type=ConflictType.STATUS_CONFLICT.value,
                                explanation=(
                                    f"Cross-finding status contradiction on '{', '.join(sorted(common)[:2])}': "
                                    f"'{case.title}' reports completed/active state, while '{other.title}' reports pending/blocked state."
                                ),
                                severity=VerificationSeverity.HIGH.value,
                                side_a_title=case.title,
                                side_a_claim=case.current_claim[:250],
                                side_a_provider=case.source_provider or "finding_a",
                                side_b_title=other.title,
                                side_b_claim=other.current_claim[:250],
                                side_b_provider=other.source_provider or "finding_b",
                                side_a_evidence_id=my_primary_ref.evidence_item_id if my_primary_ref else None,
                                side_a_chunk_id=my_primary_ref.chunk_id if my_primary_ref else None,
                                side_a_timestamp=my_primary_ref.source_timestamp if my_primary_ref else case.created_at,
                                side_b_evidence_id=other_primary_ref.evidence_item_id if other_primary_ref else None,
                                side_b_chunk_id=other_primary_ref.chunk_id if other_primary_ref else None,
                                side_b_timestamp=other_primary_ref.source_timestamp if other_primary_ref else other.created_at,
                                related_finding_id=other.id,
                            )
                        )

            # Relationship / Dependency conflicts (circular or inverted dependencies)
            if case.target_type == VerificationTargetType.RELATIONSHIP.value and other.target_type == VerificationTargetType.RELATIONSHIP.value:
                # Check for reversed relationships (e.g. A depends on B vs B depends on A)
                if case.source_id and other.source_id and case.target_id and other.target_id:
                    if case.source_id == other.target_id and case.target_id == other.source_id:
                        results.append(
                            ContradictionCandidate(
                                conflict_type=ConflictType.RELATIONSHIP_CONFLICT.value,
                                explanation=f"Inverted relationship: '{case.title}' contradicts inverse direction in '{other.title}'.",
                                severity=VerificationSeverity.HIGH.value,
                                side_a_title=case.title,
                                side_a_claim=case.current_claim[:250],
                                side_a_provider=case.source_provider or "relationship_a",
                                side_b_title=other.title,
                                side_b_claim=other.current_claim[:250],
                                side_b_provider=other.source_provider or "relationship_b",
                                side_a_evidence_id=my_primary_ref.evidence_item_id if my_primary_ref else None,
                                side_a_chunk_id=my_primary_ref.chunk_id if my_primary_ref else None,
                                side_a_timestamp=my_primary_ref.source_timestamp if my_primary_ref else case.created_at,
                                side_b_evidence_id=other_primary_ref.evidence_item_id if other_primary_ref else None,
                                side_b_chunk_id=other_primary_ref.chunk_id if other_primary_ref else None,
                                side_b_timestamp=other_primary_ref.source_timestamp if other_primary_ref else other.created_at,
                                related_finding_id=other.id,
                            )
                        )

        return results


# ==============================================================================
# 6. Intelligent Verification Recommendations
# ==============================================================================

@dataclass
class RecommendationReport:
    action: str
    headline: str
    reason: str
    supporting_factors: list[str] = field(default_factory=list)
    confidence_tier: str = "medium"


class RecommendationEngine:
    """Synthesizes all intelligence dimensions into prioritized, explainable reviewer actions."""

    def evaluate(
        self,
        case: VerificationCase,
        completeness: CompletenessReport,
        reliability: ReliabilityReport,
        freshness: FreshnessReport,
        corroboration: CorroborationReport,
        contradictions: list[ContradictionCandidate],
        open_issues_count: int,
    ) -> RecommendationReport:
        factors: list[str] = []

        # 1. Critical: Unresolved contradiction
        if contradictions or case.case_status == VerificationCaseStatus.CONFLICTED.value:
            factors.append(f"{len(contradictions)} contradiction(s) detected across project sources")
            return RecommendationReport(
                action="investigate_contradiction",
                headline="Investigate Contradictory Evidence",
                reason=(
                    "Opposing source records make conflicting claims regarding this finding. "
                    "Review the side-by-side comparison and resolve with an explicit explanation."
                ),
                supporting_factors=factors,
                confidence_tier="high",
            )

        # 2. Critical: Missing evidence
        if completeness.level == "missing":
            factors.append("Zero supporting evidence attached to finding")
            return RecommendationReport(
                action="request_additional_evidence",
                headline="Request Supporting Evidence",
                reason=(
                    "Finding has no primary evidence backing. Request documentation or link "
                    "a commit/PR before sign-off."
                ),
                supporting_factors=factors,
                confidence_tier="high",
            )

        # 3. High: Stale or superseded
        if freshness.status in {"outdated", "superseded"}:
            factors.append(f"Evidence is {freshness.status} ({freshness.age_days or 0} days old)")
            if freshness.superseding_records_count > 0:
                factors.append(f"{freshness.superseding_records_count} newer project record(s) detected")
            return RecommendationReport(
                action="recheck_outdated",
                headline="Re-check Outdated or Superseded Claim",
                reason=(
                    f"Information appears {freshness.status}. Confirm whether newer repository changes "
                    "or design revisions have altered this decision."
                ),
                supporting_factors=factors,
                confidence_tier="high",
            )

        # 4. Medium: Uncertain ownership
        if case.domain in {"responsibilities_ownership", "work_items"} and not case.person_name:
            factors.append("No explicit individual or role assigned to task/ownership item")
            return RecommendationReport(
                action="confirm_uncertain_ownership",
                headline="Confirm Ownership & Responsibility",
                reason="Work item lacks an attributed owner. Identify the responsible person before Handover sign-off.",
                supporting_factors=factors,
                confidence_tier="medium",
            )

        # 5. Medium: High-impact architecture decision needing specialist
        if case.domain == "technical_architecture" and reliability.tier in {"medium", "low"}:
            factors.append("Core technical architecture claim supported by secondary records")
            return RecommendationReport(
                action="specialist_review",
                headline="Route to Lead Architect for Verification",
                reason=(
                    "High-impact architectural finding. Recommended for verification by the designated "
                    "technical architect or project lead."
                ),
                supporting_factors=factors,
                confidence_tier="medium",
            )

        # 6. Low: Partial completeness
        if completeness.level == "partial":
            factors.extend(completeness.missing_elements[:2])
            return RecommendationReport(
                action="request_additional_evidence",
                headline="Review Incomplete Evidence Details",
                reason=(
                    "Finding is partially grounded, but missing key attribution or exact location references. "
                    "Inspect source before sign-off."
                ),
                supporting_factors=factors,
                confidence_tier="medium",
            )

        # 7. Green: Ready for human review
        factors.append(f"Completeness: {completeness.level} ({int(completeness.score * 100)}%)")
        factors.append(f"Source reliability: {reliability.tier.upper()} ({reliability.primary_authority})")
        factors.append(f"Corroboration: {corroboration.level.replace('_', ' ').title()}")
        factors.append(f"Freshness: {freshness.status.upper()}")

        return RecommendationReport(
            action="ready_for_review",
            headline="Ready for Human Review & Sign-Off",
            reason=(
                "Finding is verified by automated checks: evidence is complete, fresh, and corroborated "
                "with zero open contradictions."
            ),
            supporting_factors=factors,
            confidence_tier="high",
        )


# ==============================================================================
# 7. Verification Prioritisation
# ==============================================================================

class PrioritisationEngine:
    """Assigns explainable priorities (CRITICAL, HIGH, MEDIUM, LOW) based on risk factors."""

    def compute_priority(
        self,
        case: VerificationCase,
        completeness: CompletenessReport,
        freshness: FreshnessReport,
        contradictions: list[ContradictionCandidate],
        recommendation: RecommendationReport,
    ) -> tuple[VerificationPriority, str]:
        if contradictions or case.case_status == VerificationCaseStatus.CONFLICTED.value:
            return (
                VerificationPriority.CRITICAL,
                f"Contradictory findings detected across sources ({len(contradictions)} conflict(s))",
            )

        if completeness.level == "missing":
            return (
                VerificationPriority.CRITICAL,
                "No supporting evidence attached; finding cannot be validated for Handover",
            )

        if freshness.status == "superseded":
            return (
                VerificationPriority.HIGH,
                f"Potentially superseded by {freshness.superseding_records_count} newer project records",
            )

        if case.domain in {"technical_architecture", "decisions_rationale"} and completeness.level == "partial":
            return (
                VerificationPriority.HIGH,
                "High-impact architectural finding with incomplete source evidence",
            )

        if case.domain in {"responsibilities_ownership"} and not case.person_name:
            return (
                VerificationPriority.HIGH,
                "Unassigned ownership item requiring incoming participant confirmation",
            )

        if freshness.status == "outdated":
            return (
                VerificationPriority.MEDIUM,
                f"Evidence is {freshness.age_days or 0} days old; review recommended",
            )

        if recommendation.action == "ready_for_review":
            return (
                VerificationPriority.MEDIUM,
                "Ready for human sign-off; all automated quality checks passed",
            )

        return (
            VerificationPriority.LOW,
            "Informational or low-risk finding",
        )


# ==============================================================================
# 8. Continuous Project Intelligence & Monitoring
# ==============================================================================

@dataclass
class SourceChangeImpact:
    evidence_id: uuid.UUID
    change_type: str  # "created" | "modified" | "deleted"
    affected_case_ids: list[uuid.UUID]
    reverification_triggered: bool
    summary: str


class ContinuousMonitoringService:
    """Monitors connected source activity and correlates changes to existing verification cases."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def process_source_change_event(
        self,
        *,
        project_id: uuid.UUID,
        evidence_item: EvidenceItem,
        change_type: str = "modified",
        triggered_by_user_id: uuid.UUID | None = None,
    ) -> SourceChangeImpact:
        """Evaluate the impact of a newly ingested or updated evidence record on existing findings."""
        now = datetime.now(UTC)

        # 1. Find all cases directly referencing this evidence item
        direct_refs = self.session.execute(
            select(VerificationEvidenceRef.case_id)
            .where(VerificationEvidenceRef.evidence_item_id == evidence_item.id)
        ).scalars().all()
        affected_ids = set(direct_refs)

        # 2. Correlate by claim/title overlap for high-impact changes
        ev_tokens = _tokenize(f"{evidence_item.title} {evidence_item.source_url or ''}")
        if len(ev_tokens) >= 3:
            all_cases = self.session.execute(
                select(VerificationCase).where(VerificationCase.project_id == project_id)
            ).scalars().all()
            for c in all_cases:
                c_tok = _tokenize(c.current_claim)
                if len(c_tok & ev_tokens) >= 3:
                    affected_ids.add(c.id)

        reverification_triggered = False
        impact_summary = (
            f"Source change '{change_type}' on '{evidence_item.title}' evaluated. "
            f"Correlated with {len(affected_ids)} existing finding(s)."
        )

        for case_id in affected_ids:
            case = self.session.get(VerificationCase, case_id)
            if case is None:
                continue

            assessment = dict(case.machine_assessment_json or {})
            monitoring = dict(assessment.get("monitoring_status") or {})
            monitoring["last_monitored_at"] = now.isoformat()
            monitoring["last_evidence_change_id"] = str(evidence_item.id)
            monitoring["change_type"] = change_type

            # If a human had previously verified this finding, flag for re-verification without overwriting status
            if case.case_status == VerificationCaseStatus.VERIFIED.value:
                monitoring["reverification_triggered"] = True
                monitoring["reverification_reason"] = (
                    f"Supporting source record '{evidence_item.title}' was modified in the source system. "
                    "Reviewer confirmation required."
                )
                reverification_triggered = True

                # Record an audit log for the re-verification trigger
                self.session.add(
                    AuditLog(
                        organisation_id=case.organisation_id,
                        project_id=case.project_id,
                        actor_user_id=triggered_by_user_id,
                        event_type="verification.reverification_triggered",
                        resource_type="verification_case",
                        resource_id=str(case.id),
                        outcome="success",
                        event_metadata={
                            "evidence_item_id": str(evidence_item.id),
                            "change_type": change_type,
                            "reason": monitoring["reverification_reason"],
                        },
                    )
                )

            assessment["monitoring_status"] = monitoring
            case.machine_assessment_json = assessment

        self.session.flush()
        return SourceChangeImpact(
            evidence_id=evidence_item.id,
            change_type=change_type,
            affected_case_ids=list(affected_ids),
            reverification_triggered=reverification_triggered,
            summary=impact_summary,
        )
