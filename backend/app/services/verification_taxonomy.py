"""Verification taxonomy definitions, severity defaults, and validation rule catalog.

Platform: The Handover
Module: Verification Center (Module 3 / Validation Area)
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.enums import EvidenceSourceType, VerificationIssueType, VerificationSeverity


@dataclass(frozen=True, slots=True)
class IssueTaxonomyEntry:
    """Canonical metadata for a verification issue category."""

    issue_type: VerificationIssueType
    category: str
    default_severity: VerificationSeverity
    description_template: str
    recommended_action: str
    blocks_handover: bool


TAXONOMY_CATALOG: dict[VerificationIssueType, IssueTaxonomyEntry] = {
    VerificationIssueType.MISSING_EVIDENCE: IssueTaxonomyEntry(
        issue_type=VerificationIssueType.MISSING_EVIDENCE,
        category="Provenance",
        default_severity=VerificationSeverity.CRITICAL,
        description_template="Finding has no supporting evidence links or cited ID does not exist.",
        recommended_action="Attach verified primary source document, commit, or issue.",
        blocks_handover=True,
    ),
    VerificationIssueType.INVALID_SOURCE_REFERENCE: IssueTaxonomyEntry(
        issue_type=VerificationIssueType.INVALID_SOURCE_REFERENCE,
        category="Provenance",
        default_severity=VerificationSeverity.HIGH,
        description_template="Cited chunk does not belong to cited item or is outside workspace.",
        recommended_action="Re-link excerpt to valid chunk within project workspace.",
        blocks_handover=True,
    ),
    VerificationIssueType.UNSUPPORTED_CLAIM: IssueTaxonomyEntry(
        issue_type=VerificationIssueType.UNSUPPORTED_CLAIM,
        category="Grounding",
        default_severity=VerificationSeverity.HIGH,
        description_template="Supporting excerpt text cannot be matched in cited source chunk.",
        recommended_action="Review primary text and update excerpt or remove statement.",
        blocks_handover=True,
    ),
    VerificationIssueType.CONFLICTING_SOURCES: IssueTaxonomyEntry(
        issue_type=VerificationIssueType.CONFLICTING_SOURCES,
        category="Consistency",
        default_severity=VerificationSeverity.HIGH,
        description_template="Contradictory facts detected between two or more project sources.",
        recommended_action="Inspect claims in conflict view and select canonical source.",
        blocks_handover=True,
    ),
    VerificationIssueType.INCONSISTENT_STATUS: IssueTaxonomyEntry(
        issue_type=VerificationIssueType.INCONSISTENT_STATUS,
        category="Consistency",
        default_severity=VerificationSeverity.MEDIUM,
        description_template="Finding status contradicts observed Jira issue or Git commit state.",
        recommended_action="Synchronize finding status with verified tracking system or document.",
        blocks_handover=False,
    ),
    VerificationIssueType.OUTDATED_INFORMATION: IssueTaxonomyEntry(
        issue_type=VerificationIssueType.OUTDATED_INFORMATION,
        category="Freshness",
        default_severity=VerificationSeverity.MEDIUM,
        description_template="Supporting evidence was superseded by subsequent activity.",
        recommended_action="Verify against latest document revision or mark superseded.",
        blocks_handover=False,
    ),
    VerificationIssueType.STALE_KNOWLEDGE: IssueTaxonomyEntry(
        issue_type=VerificationIssueType.STALE_KNOWLEDGE,
        category="Freshness",
        default_severity=VerificationSeverity.HIGH,
        description_template="Source was revoked or deleted, rendering evidence unverified.",
        recommended_action="Re-authenticate source or link alternative active evidence.",
        blocks_handover=True,
    ),
    VerificationIssueType.DUPLICATE_RECORD: IssueTaxonomyEntry(
        issue_type=VerificationIssueType.DUPLICATE_RECORD,
        category="Uniqueness",
        default_severity=VerificationSeverity.MEDIUM,
        description_template="Another finding shares identical semantic content or fingerprint.",
        recommended_action="Merge duplicate findings into canonical record or dismiss secondary.",
        blocks_handover=False,
    ),
    VerificationIssueType.UNCERTAIN_RELATIONSHIP: IssueTaxonomyEntry(
        issue_type=VerificationIssueType.UNCERTAIN_RELATIONSHIP,
        category="Relational",
        default_severity=VerificationSeverity.LOW,
        description_template="Relationship basis is inferred without direct identifier reference.",
        recommended_action="Human reviewer should confirm or reject graph edge connection.",
        blocks_handover=False,
    ),
    VerificationIssueType.INVALID_ENTITY_MAPPING: IssueTaxonomyEntry(
        issue_type=VerificationIssueType.INVALID_ENTITY_MAPPING,
        category="Relational",
        default_severity=VerificationSeverity.HIGH,
        description_template="Target entity does not match required entity type for relationship.",
        recommended_action="Re-map relationship to valid entity node.",
        blocks_handover=True,
    ),
    VerificationIssueType.INCORRECT_ATTRIBUTION: IssueTaxonomyEntry(
        issue_type=VerificationIssueType.INCORRECT_ATTRIBUTION,
        category="Attribution",
        default_severity=VerificationSeverity.MEDIUM,
        description_template="Attributed owner does not match commit author or assignee.",
        recommended_action="Correct attributed team member in finding payload.",
        blocks_handover=False,
    ),
    VerificationIssueType.MISSING_SOURCE_CONTEXT: IssueTaxonomyEntry(
        issue_type=VerificationIssueType.MISSING_SOURCE_CONTEXT,
        category="Completeness",
        default_severity=VerificationSeverity.LOW,
        description_template="Finding omits expected context (e.g. decision rationale).",
        recommended_action="Request clarification from departing team member.",
        blocks_handover=False,
    ),
    VerificationIssueType.INSUFFICIENT_INFORMATION: IssueTaxonomyEntry(
        issue_type=VerificationIssueType.INSUFFICIENT_INFORMATION,
        category="Completeness",
        default_severity=VerificationSeverity.MEDIUM,
        description_template="Available evidence is insufficient for confident handover sign-off.",
        recommended_action="Request additional context from project lead or departing team member.",
        blocks_handover=False,
    ),
    VerificationIssueType.INCOMPLETE_TRACEABILITY: IssueTaxonomyEntry(
        issue_type=VerificationIssueType.INCOMPLETE_TRACEABILITY,
        category="Traceability",
        default_severity=VerificationSeverity.LOW,
        description_template="Decision-to-implementation chain has untraced links across items.",
        recommended_action="Connect intermediate work item or pull request to complete trace.",
        blocks_handover=False,
    ),
}

SOURCE_AUTHORITY_WEIGHTS: dict[str, float] = {
    EvidenceSourceType.GITHUB.value: 0.95,
    EvidenceSourceType.DOCUMENT_UPLOAD.value: 0.90,
    EvidenceSourceType.JIRA.value: 0.80,
    EvidenceSourceType.SLACK.value: 0.65,
    EvidenceSourceType.MANUAL_NOTE.value: 0.50,
}

SEVERITY_PENALTIES: dict[str, float] = {
    VerificationSeverity.CRITICAL.value: 0.30,
    VerificationSeverity.HIGH.value: 0.15,
    VerificationSeverity.MEDIUM.value: 0.08,
    VerificationSeverity.LOW.value: 0.03,
    VerificationSeverity.INFO.value: 0.01,
}


def get_taxonomy_entry(issue_type: VerificationIssueType | str) -> IssueTaxonomyEntry:
    """Retrieve taxonomy entry for an issue type, falling back to safe default if unknown."""
    if isinstance(issue_type, str):
        try:
            issue_type = VerificationIssueType(issue_type.lower())
        except ValueError:
            pass

    if issue_type in TAXONOMY_CATALOG:
        return TAXONOMY_CATALOG[issue_type]
    return IssueTaxonomyEntry(
        issue_type=issue_type,  # type: ignore[arg-type]
        category="General",
        default_severity=VerificationSeverity.MEDIUM,
        description_template=f"Verification issue detected: {getattr(issue_type, 'value', issue_type)}.",
        recommended_action="Inspect evidence and verify with project lead.",
        blocks_handover=False,
    )


def get_severity_penalty(severity: VerificationSeverity | str) -> float:
    """Get confidence score deduction penalty for an issue severity level."""
    val = getattr(severity, "value", str(severity)).lower()
    return SEVERITY_PENALTIES.get(val, 0.05)


def get_source_authority_weight(source_type: str | EvidenceSourceType | None) -> float:
    """Get the authority weighting factor for a primary source type."""
    if source_type is None:
        return 0.50
    val = getattr(source_type, "value", str(source_type)).lower()
    return SOURCE_AUTHORITY_WEIGHTS.get(val, 0.50)


def is_handover_blocking_issue(issue_type: VerificationIssueType | str) -> bool:
    """Check if an issue type is configured to block downstream handover package compilation."""
    return get_taxonomy_entry(issue_type).blocks_handover


def get_taxonomy_by_category(category: str) -> list[IssueTaxonomyEntry]:
    """Retrieve all catalog entries belonging to a given taxonomy category."""
    norm_cat = category.strip().lower()
    return [
        entry for entry in TAXONOMY_CATALOG.values()
        if entry.category.strip().lower() == norm_cat
    ]
