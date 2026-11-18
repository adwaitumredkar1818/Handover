"""Independent backend grounding, schema, citation & dedup validator (`NO EVIDENCE -> NO CLAIM`)."""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ValidationError, create_model

from app.models.enums import (
    ConfidenceLevel,
    EpistemicStatus,
    KnowledgeCategory,
    KnowledgeReviewStatus,
    SupportClassification,
)
from app.schemas.knowledge import (
    CandidateEvidenceRef,
    ConfidenceMetadata,
    DecisionCandidate,
    DependencyCandidate,
    OperationalHistoricalCandidate,
    ProjectOverviewCandidate,
    ResponsibilityCandidate,
    RiskBlockerCandidate,
    TechnicalKnowledgeCandidate,
    WorkItemCandidate,
)
from app.services.extraction_prompts import ChunkPromptInput
from app.services.knowledge_domains import map_category_to_domain

_WHITESPACE_RE = re.compile(r"\s+")
_FINGERPRINT_SLUG_RE = re.compile(r"[^a-z0-9]+")
_EXPLICIT_SEVERITY_RE = re.compile(
    r"\b(critical|blocker|blocking|sev[- ]?[0-4]|p[0-3]"
    r"|high(?:er|est)?\s+(?:severity|priority|risk)"
    r"|medium\s+(?:severity|priority|risk)|low\s+(?:severity|priority|risk)"
    r"|urgent|major|minor)\b",
    flags=re.IGNORECASE,
)

_CANDIDATE_MODEL_BY_CATEGORY: dict[KnowledgeCategory, type[Any]] = {
    KnowledgeCategory.PROJECT_OVERVIEW_CONTEXT: ProjectOverviewCandidate,
    KnowledgeCategory.DECISIONS_RATIONALE: DecisionCandidate,
    KnowledgeCategory.WORK_ITEMS: WorkItemCandidate,
    KnowledgeCategory.RESPONSIBILITIES_OWNERSHIP: ResponsibilityCandidate,
    KnowledgeCategory.TECHNICAL_ARCHITECTURE: TechnicalKnowledgeCandidate,
    KnowledgeCategory.BUGS_BLOCKERS_RISKS: RiskBlockerCandidate,
    KnowledgeCategory.DEPENDENCIES: DependencyCandidate,
    KnowledgeCategory.OPERATIONAL_HISTORICAL: OperationalHistoricalCandidate,
    # Domain aliases
    KnowledgeCategory.WORK_PROGRESS: WorkItemCandidate,
    KnowledgeCategory.ARCHITECTURE_TECHNICAL: TechnicalKnowledgeCandidate,
    KnowledgeCategory.DEPENDENCIES_RELATIONSHIPS: DependencyCandidate,
    KnowledgeCategory.RISKS_BLOCKERS_QUESTIONS: RiskBlockerCandidate,
}


def get_category_response_json_schema(category: KnowledgeCategory) -> dict[str, Any]:
    """Return a Pydantic-generated JSON schema envelope for structured LLM extraction."""
    candidate_cls = _CANDIDATE_MODEL_BY_CATEGORY.get(category)
    if candidate_cls is None:
        return {"type": "object", "properties": {"items": {"type": "array"}}}
    envelope_model = create_model(
        f"{candidate_cls.__name__}BatchEnvelope",
        items=(list[candidate_cls], ...),  # type: ignore[valid-type]
        __base__=BaseModel,
    )
    return envelope_model.model_json_schema()


def get_multi_domain_response_json_schema() -> dict[str, Any]:
    """Return unified compact JSON schema envelope for multi-domain structured extraction."""
    return {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "category": {
                            "type": "string",
                            "enum": [
                                "project_overview_context",
                                "decisions_rationale",
                                "technical_architecture",
                                "work_items",
                                "responsibilities_ownership",
                                "dependencies",
                                "bugs_blockers_risks",
                                "operational_historical",
                            ],
                        },
                        "title": {"type": "string"},
                        "structured_summary": {"type": "string"},
                        "evidence_refs": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "chunk_id": {"type": "string"},
                                    "supporting_excerpt": {"type": "string"},
                                    "support_type": {
                                        "type": "string",
                                        "enum": ["direct", "interpretation", "uncertain"],
                                    },
                                },
                                "required": ["chunk_id", "supporting_excerpt", "support_type"],
                            },
                        },
                        "is_interpretation": {"type": "boolean"},
                        "is_uncertain": {"type": "boolean"},
                        "confidence_level": {
                            "type": "string",
                            "enum": ["high", "medium", "low"],
                        },
                        "graph_classifications": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": [
                                    "TECHNOLOGY_STACK",
                                    "SYSTEM_ARCHITECTURE",
                                    "FEATURES_WORKFLOWS",
                                ],
                            },
                        },
                        "technology_details": {
                            "type": ["object", "null"],
                            "properties": {
                                "technology_name": {"type": "string"},
                                "technology_category": {"type": ["string", "null"]},
                                "role_in_project": {"type": ["string", "null"]},
                                "version": {"type": ["string", "null"]},
                                "usage_status": {
                                    "type": "string",
                                    "enum": [
                                        "DECLARED_DEPENDENCY",
                                        "DIRECTLY_EVIDENCED_USE",
                                        "DOCUMENTED_PLANNED",
                                        "DEPRECATED_OR_REMOVED",
                                        "MENTIONED_ONLY",
                                        "UNKNOWN",
                                    ],
                                },
                                "associated_component": {"type": ["string", "null"]},
                            },
                        },
                        "architecture_details": {
                            "type": ["object", "null"],
                            "properties": {
                                "component_name": {"type": "string"},
                                "component_type": {"type": ["string", "null"]},
                                "component_responsibility": {"type": ["string", "null"]},
                                "implementation_status": {"type": ["string", "null"]},
                                "associated_technologies": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "relationship_type": {"type": ["string", "null"]},
                                "source_component": {"type": ["string", "null"]},
                                "target_component": {"type": ["string", "null"]},
                            },
                        },
                        "feature_details": {
                            "type": ["object", "null"],
                            "properties": {
                                "feature_name": {"type": "string"},
                                "user_goal": {"type": ["string", "null"]},
                                "user_actor": {"type": ["string", "null"]},
                                "user_visible_behavior": {"type": ["string", "null"]},
                                "implementation_status": {"type": ["string", "null"]},
                                "workflow_steps": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "related_components": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                        },
                    },
                    "required": [
                        "category",
                        "title",
                        "structured_summary",
                        "evidence_refs",
                        "confidence_level",
                    ],
                },
            },
        },
        "required": ["items"],
    }



@dataclass(frozen=True, slots=True)
class VerifiedEvidenceLinkDraft:
    """Validated provenance link verified against a concrete supplied EvidenceChunk."""

    evidence_id: uuid.UUID
    evidence_chunk_id: uuid.UUID
    support_type: str
    source_location: dict[str, Any]
    supporting_excerpt: str
    excerpt_match_mode: str
    source_metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ValidatedKnowledgeItemDraft:
    """Fully verified knowledge item ready for transactional persistence in PostgreSQL."""

    category: KnowledgeCategory
    epistemic_status: str
    review_status: str
    support_classification: str
    title: str
    structured_summary: str
    structured_payload: dict[str, Any]
    normalised_status: str | None
    person_or_owner_label: str | None
    source_attribution: dict[str, Any]
    fingerprint: str
    confidence_metadata: dict[str, Any]
    uncertainty_reason: str | None
    source_observed_at: datetime | None
    is_synthetic: bool
    evidence_links: tuple[VerifiedEvidenceLinkDraft, ...]
    primary_domain: str | None = None
    secondary_domains: tuple[str, ...] = ()


@dataclass(slots=True)
class BatchValidationReport:
    """Aggregated outcome and rejection audit breakdown for one LLM batch response."""

    accepted_items: list[ValidatedKnowledgeItemDraft] = field(default_factory=list)
    candidates_received: int = 0
    rejected_schema_count: int = 0
    rejected_ungrounded_count: int = 0
    rejection_reasons: list[str] = field(default_factory=list)
    rejected_items: list[dict[str, Any]] = field(default_factory=list)


def _normalize_text_for_matching(value: str) -> str:
    """Normalize typography and whitespace cleanly without altering word boundaries."""
    normalized = (
        value.replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
    )
    return _WHITESPACE_RE.sub(" ", normalized).strip().lower()


def verify_excerpt_in_chunk(
    *,
    excerpt: str,
    chunk_text: str,
) -> tuple[bool, str | None, str]:
    """Verify verbatim or whitespace-normalised quote presence inside `chunk_text`."""
    cleaned_excerpt = excerpt.strip()
    if len(cleaned_excerpt) < 8:
        return False, None, "excerpt_too_short"

    if cleaned_excerpt in chunk_text:
        return True, "exact", cleaned_excerpt

    norm_excerpt = _normalize_text_for_matching(cleaned_excerpt)
    norm_chunk = _normalize_text_for_matching(chunk_text)
    if len(norm_excerpt) >= 8 and norm_excerpt in norm_chunk:
        return True, "normalized_whitespace", cleaned_excerpt

    return False, None, "excerpt_not_found_in_chunk"


def _slugify_key(value: str) -> str:
    lowered = _normalize_text_for_matching(value)
    slug = _FINGERPRINT_SLUG_RE.sub("-", lowered).strip("-")
    return slug[:160]


def _extract_normalised_status(category: KnowledgeCategory, payload: dict[str, Any]) -> str | None:
    field_map = {
        KnowledgeCategory.PROJECT_OVERVIEW_CONTEXT: "status",
        KnowledgeCategory.DECISIONS_RATIONALE: "decision_status",
        KnowledgeCategory.WORK_ITEMS: "work_status",
        KnowledgeCategory.WORK_PROGRESS: "work_status",
        KnowledgeCategory.RESPONSIBILITIES_OWNERSHIP: "ownership_status",
        KnowledgeCategory.TECHNICAL_ARCHITECTURE: "technical_status",
        KnowledgeCategory.ARCHITECTURE_TECHNICAL: "technical_status",
        KnowledgeCategory.BUGS_BLOCKERS_RISKS: "risk_status",
        KnowledgeCategory.RISKS_BLOCKERS_QUESTIONS: "risk_status",
        KnowledgeCategory.DEPENDENCIES: "dependency_status",
        KnowledgeCategory.DEPENDENCIES_RELATIONSHIPS: "dependency_status",
        KnowledgeCategory.OPERATIONAL_HISTORICAL: "status",
    }
    field_name = field_map.get(category, "status")
    raw = payload.get(field_name)
    return str(raw).strip() if raw is not None else None


def _extract_person_label(category: KnowledgeCategory, payload: dict[str, Any]) -> str | None:
    if category == KnowledgeCategory.RESPONSIBILITIES_OWNERSHIP:
        val = payload.get("person_identity")
        return str(val).strip() if val else None
    if category in {KnowledgeCategory.WORK_ITEMS, KnowledgeCategory.WORK_PROGRESS}:
        val = payload.get("assignee") or payload.get("creator")
        return str(val).strip() if val else None
    if category == KnowledgeCategory.DECISIONS_RATIONALE:
        val = payload.get("decision_maker")
        return str(val).strip() if val else None
    if category in {KnowledgeCategory.BUGS_BLOCKERS_RISKS, KnowledgeCategory.RISKS_BLOCKERS_QUESTIONS}:
        val = payload.get("responsible_person")
        return str(val).strip() if val else None
    return None


def compute_conservative_fingerprint(
    *,
    category: KnowledgeCategory,
    title: str,
    payload: dict[str, Any],
    normalised_status: str | None,
    person_or_owner_label: str | None,
) -> str:
    """Compute conservative deduplication hash preserving statuses and unmerged identities."""
    status_key = _slugify_key(normalised_status or "unknown")
    if category == KnowledgeCategory.RESPONSIBILITIES_OWNERSHIP:
        # Preserve distinct person_identity representations cleanly without merging near-matches.
        raw_identity = str(payload.get("person_identity") or "").strip().lower()
        comp_slug = _slugify_key(str(payload.get("component_or_workstream") or ""))
        role_slug = _slugify_key(str(payload.get("ownership_role") or ""))
        material = f"{category.value}|{raw_identity}|{comp_slug}|{role_slug}|{status_key}"
    elif category in {KnowledgeCategory.DEPENDENCIES, KnowledgeCategory.DEPENDENCIES_RELATIONSHIPS}:
        src_slug = _slugify_key(str(payload.get("source_item") or ""))
        dst_slug = _slugify_key(str(payload.get("target_item") or ""))
        dep_type = _slugify_key(str(payload.get("dependency_type") or ""))
        direction = _slugify_key(str(payload.get("direction") or ""))
        material = f"{category.value}|{src_slug}|{dst_slug}|{dep_type}|{direction}|{status_key}"
    elif category == KnowledgeCategory.PROJECT_OVERVIEW_CONTEXT:
        overview_cat = _slugify_key(str(payload.get("overview_category") or ""))
        title_slug = _slugify_key(title)
        material = f"{category.value}|{overview_cat}|{title_slug}|{status_key}"
    elif category == KnowledgeCategory.OPERATIONAL_HISTORICAL:
        know_type = _slugify_key(str(payload.get("knowledge_type") or ""))
        proc_name = _slugify_key(str(payload.get("procedure_name") or title))
        env = _slugify_key(str(payload.get("target_environment") or "any"))
        material = f"{category.value}|{know_type}|{proc_name}|{env}|{status_key}"
    else:
        title_slug = _slugify_key(title)
        identity_suffix = (person_or_owner_label or "").strip().lower()
        material = f"{category.value}|{title_slug}|{status_key}|{identity_suffix}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _parse_optional_source_timestamp(chunks: list[ChunkPromptInput]) -> datetime | None:
    for ch in chunks:
        if ch.source_created_at_iso:
            try:
                return datetime.fromisoformat(ch.source_created_at_iso)
            except ValueError:
                continue
    return None


def _build_confidence_and_uncertainty(
    *,
    category: KnowledgeCategory,
    candidate: Any,
    payload: dict[str, Any],
    verified_links: list[VerifiedEvidenceLinkDraft],
    normalised_status: str | None,
) -> tuple[dict[str, Any], str | None, str, str]:
    """Compute honest epistemic status, support classification & missing-field flags."""
    missing_fields: list[str] = []
    if category == KnowledgeCategory.DECISIONS_RATIONALE:
        if not payload.get("decision_maker"):
            missing_fields.append("decision_maker")
        if not payload.get("decision_date"):
            missing_fields.append("decision_date")
        if not payload.get("rationale"):
            missing_fields.append("rationale")
    elif category == KnowledgeCategory.WORK_ITEMS:
        if not payload.get("assignee"):
            missing_fields.append("assignee")
        if not (
            payload.get("created_date")
            or payload.get("updated_date")
            or payload.get("completed_date")
        ):
            missing_fields.append("work_dates")
    elif category == KnowledgeCategory.RESPONSIBILITIES_OWNERSHIP:
        if not payload.get("start_or_observed_date"):
            missing_fields.append("start_or_observed_date")
    elif category in {KnowledgeCategory.BUGS_BLOCKERS_RISKS, KnowledgeCategory.RISKS_BLOCKERS_QUESTIONS}:
        if payload.get("severity") == "unspecified":
            missing_fields.append("severity")
        if not payload.get("reported_date"):
            missing_fields.append("reported_date")
    elif category == KnowledgeCategory.PROJECT_OVERVIEW_CONTEXT:
        if not payload.get("overview_category"):
            missing_fields.append("overview_category")
    elif category == KnowledgeCategory.OPERATIONAL_HISTORICAL:
        if not payload.get("knowledge_type"):
            missing_fields.append("knowledge_type")
        if payload.get("knowledge_type") in {"deployment_runbook", "incident_response"} and not payload.get("execution_steps"):
            missing_fields.append("execution_steps")

    has_date = bool(
        payload.get("decision_date")
        or payload.get("completed_date")
        or payload.get("updated_date")
        or payload.get("created_date")
        or payload.get("start_or_observed_date")
        or payload.get("reported_date")
        or payload.get("event_timestamp")
    )
    temporal_certainty = "exact_date" if has_date else "missing"

    has_attribution = bool(
        payload.get("decision_maker")
        or payload.get("assignee")
        or payload.get("creator")
        or payload.get("person_identity")
        or payload.get("responsible_person")
    )
    attribution_certainty = "explicit" if has_attribution else "missing"
    if (
        category == KnowledgeCategory.RESPONSIBILITIES_OWNERSHIP
        and payload.get("ownership_basis") in {"inferred_contribution", "unconfirmed"}
    ):
        attribution_certainty = "inferred"

    is_interpretation = bool(candidate.is_interpretation) or any(
        link.support_type == "interpretation" for link in verified_links
    )
    if (
        category == KnowledgeCategory.RESPONSIBILITIES_OWNERSHIP
        and payload.get("ownership_basis") == "inferred_contribution"
    ):
        is_interpretation = True

    is_uncertain = (
        bool(candidate.is_uncertain)
        or normalised_status in {"unclear", "unknown", "unconfirmed"}
        or any(link.support_type == "uncertain" for link in verified_links)
    )

    if is_uncertain:
        support_classification = SupportClassification.UNCERTAIN.value
    elif is_interpretation:
        support_classification = SupportClassification.INTERPRETATION.value
    elif len({link.evidence_id for link in verified_links}) > 1:
        support_classification = SupportClassification.CORROBORATED.value
    else:
        support_classification = SupportClassification.DIRECT.value

    # LLM may NEVER produce `human_verified`.
    epistemic_status = (
        EpistemicStatus.AI_INTERPRETED.value
        if is_interpretation
        else EpistemicStatus.EXTRACTED.value
    )

    uncertainty_reason = candidate.uncertainty_reason
    if (is_uncertain or is_interpretation) and not uncertainty_reason:
        if normalised_status in {"unclear", "unknown", "unconfirmed"}:
            uncertainty_reason = f"Status could not be confirmed beyond '{normalised_status}'."
        elif is_interpretation:
            uncertainty_reason = "Derived via AI interpretation of supporting source evidence."
        else:
            uncertainty_reason = "Source evidence contains ambiguity or missing details."

    completeness = (
        "complete"
        if not missing_fields
        else ("partial" if len(missing_fields) <= 2 else "incomplete")
    )
    evidence_quality = (
        "weak_or_indirect"
        if support_classification in {SupportClassification.UNCERTAIN.value}
        else ("partial" if is_interpretation else "explicit")
    )

    # Calculate accurate numeric confidence score based on Ollama's extraction certainty
    base_score = 0.88
    cand_level = str(getattr(candidate, "confidence_level", "medium")).lower()
    if cand_level == "high":
        base_score = 0.92
    elif cand_level == "medium":
        base_score = 0.78
    elif cand_level == "low":
        base_score = 0.58

    if evidence_quality == "explicit":
        base_score += 0.05
    elif evidence_quality == "weak_or_indirect":
        base_score -= 0.12

    if completeness == "complete":
        base_score += 0.03
    elif completeness == "incomplete":
        base_score -= 0.08

    if attribution_certainty == "explicit":
        base_score += 0.02
    elif attribution_certainty == "missing":
        base_score -= 0.04

    if temporal_certainty == "exact_date":
        base_score += 0.02
    elif temporal_certainty == "missing":
        base_score -= 0.03

    if is_uncertain:
        base_score -= 0.15

    if missing_fields:
        base_score -= min(len(missing_fields) * 0.02, 0.10)

    calculated_confidence_score = round(max(0.35, min(0.99, base_score)), 2)

    confidence_meta = ConfidenceMetadata(
        extraction_confidence=ConfidenceLevel(candidate.confidence_level),
        confidence_score=calculated_confidence_score,
        evidence_support_quality=evidence_quality,
        information_completeness=completeness,
        attribution_certainty=attribution_certainty,
        temporal_certainty=temporal_certainty,
        missing_fields=missing_fields,
        conflict_or_ambiguity_flag=bool(is_uncertain),
    ).model_dump(mode="json")
    confidence_meta["confidence_score"] = calculated_confidence_score

    return confidence_meta, uncertainty_reason, epistemic_status, support_classification


_VALID_GRAPH_CLASSIFICATIONS = {
    "TECHNOLOGY_STACK",
    "SYSTEM_ARCHITECTURE",
    "FEATURES_WORKFLOWS",
}
_VALID_TECH_USAGE_STATUSES = {
    "DECLARED_DEPENDENCY",
    "DIRECTLY_EVIDENCED_USE",
    "DOCUMENTED_PLANNED",
    "DEPRECATED_OR_REMOVED",
    "MENTIONED_ONLY",
    "UNKNOWN",
}
_NON_FEATURE_INTERNAL_TERMS = (
    "database migration",
    "db migration",
    "alembic migration",
    "postgresql integration",
    "fastapi routing",
    "internal queue",
    "ci/cd",
    "unit test",
    "integration test",
    "refactoring",
    "auth middleware",
    "authentication middleware",
    "infrastructure configuration",
    "docker compose",
)


def _validate_and_normalize_graph_payload(
    *,
    payload: dict[str, Any],
    title: str,
    cited_chunks: list[ChunkPromptInput],
    verified_links: list[VerifiedEvidenceLinkDraft],
) -> tuple[bool, str | None]:
    """Validate and normalize graph_classifications and *_details against cited evidence.

    Returns (ok, rejection_reason). Mutates `payload` in place to strip ungrounded fields.
    """
    combined_text = "\n".join(
        [ch.chunk_text for ch in cited_chunks]
        + [lk.supporting_excerpt for lk in verified_links]
    ).lower()

    raw_graphs = payload.get("graph_classifications")
    if isinstance(raw_graphs, list):
        graphs = [
            str(g).strip().upper()
            for g in raw_graphs
            if str(g).strip().upper() in _VALID_GRAPH_CLASSIFICATIONS
        ]
    else:
        graphs = []

    had_only_tech = graphs == ["TECHNOLOGY_STACK"]

    # 1. Validate technology_details
    td = payload.get("technology_details")
    if isinstance(td, dict):
        tech_name = str(td.get("technology_name") or "").strip()
        if not tech_name or tech_name.lower() not in combined_text:
            # Check short token match (e.g. "PostgreSQL 16" -> "postgresql")
            first_tok = tech_name.split()[0].lower() if tech_name else ""
            if not first_tok or len(first_tok) < 2 or first_tok not in combined_text:
                payload.pop("technology_details", None)
                graphs = [g for g in graphs if g != "TECHNOLOGY_STACK"]
                if had_only_tech:
                    return False, "ungrounded_technology_name"
                td = None

        if isinstance(td, dict):
            raw_ver = str(td.get("version") or "").strip()
            clean_ver: str | None = None
            if raw_ver:
                ver_core = raw_ver.lstrip("^~>=<vV ").strip().lower()
                if ver_core and ver_core in combined_text:
                    clean_ver = raw_ver
            usage_status = str(td.get("usage_status") or "UNKNOWN").strip().upper()
            if usage_status not in _VALID_TECH_USAGE_STATUSES:
                usage_status = "UNKNOWN"
            assoc_comp = str(td.get("associated_component") or "").strip() or None
            if assoc_comp and assoc_comp.lower() not in combined_text:
                assoc_comp = None
            normalized_td = {
                "technology_name": tech_name,
                "technology_category": (str(td.get("technology_category") or "").strip().lower() or None),
                "role_in_project": (str(td.get("role_in_project") or "").strip() or None),
                "version": clean_ver,
                "usage_status": usage_status,
                "associated_component": assoc_comp,
            }
            payload["technology_details"] = normalized_td
            if "TECHNOLOGY_STACK" not in graphs:
                graphs.append("TECHNOLOGY_STACK")
            payload.setdefault("technical_category", "technology_choice")
            existing_ids = list(payload.get("exact_identifiers") or [])
            if tech_name not in existing_ids:
                existing_ids.append(tech_name)
            payload["exact_identifiers"] = existing_ids

    # 2. Validate architecture_details
    ad = payload.get("architecture_details")
    if isinstance(ad, dict):
        comp_name = str(ad.get("component_name") or "").strip()
        src_comp = str(ad.get("source_component") or "").strip() or None
        dst_comp = str(ad.get("target_component") or "").strip() or None
        rel_type = str(ad.get("relationship_type") or "").strip().lower() or None
        if src_comp and src_comp.lower() not in combined_text:
            src_comp = None
            rel_type = None
        if dst_comp and dst_comp.lower() not in combined_text:
            dst_comp = None
            rel_type = None
        assoc_techs = [
            str(t).strip()
            for t in (ad.get("associated_technologies") or [])
            if isinstance(t, str) and t.strip() and t.strip().lower() in combined_text
        ]
        if comp_name:
            payload["architecture_details"] = {
                "component_name": comp_name,
                "component_type": (str(ad.get("component_type") or "").strip().lower() or None),
                "component_responsibility": (str(ad.get("component_responsibility") or "").strip() or None),
                "implementation_status": (str(ad.get("implementation_status") or "unknown").strip().lower()),
                "associated_technologies": assoc_techs,
                "relationship_type": rel_type,
                "source_component": src_comp,
                "target_component": dst_comp,
            }
            existing_comps = list(payload.get("components") or [])
            if comp_name not in existing_comps:
                existing_comps.append(comp_name)
            payload["components"] = existing_comps
            if "SYSTEM_ARCHITECTURE" not in graphs:
                graphs.append("SYSTEM_ARCHITECTURE")
        else:
            payload.pop("architecture_details", None)

    # 3. Validate feature_details & exclude non-feature internal dev/infra tasks
    fd = payload.get("feature_details")
    feat_name = (
        str(fd.get("feature_name") or "").strip()
        if isinstance(fd, dict)
        else ""
    ) or title
    low_feat = feat_name.lower()
    is_internal_non_feature = any(term in low_feat for term in _NON_FEATURE_INTERNAL_TERMS)
    if is_internal_non_feature:
        graphs = [g for g in graphs if g != "FEATURES_WORKFLOWS"]
        payload.pop("feature_details", None)
    elif isinstance(fd, dict) and feat_name:
        rel_comps = [
            str(c).strip()
            for c in (fd.get("related_components") or [])
            if isinstance(c, str) and c.strip() and c.strip().lower() in combined_text
        ]
        payload["feature_details"] = {
            "feature_name": feat_name,
            "user_goal": (str(fd.get("user_goal") or "").strip() or None),
            "user_actor": (str(fd.get("user_actor") or "").strip() or None),
            "user_visible_behavior": (str(fd.get("user_visible_behavior") or "").strip() or None),
            "implementation_status": (str(fd.get("implementation_status") or "unknown").strip().lower()),
            "workflow_steps": [
                str(s).strip()
                for s in (fd.get("workflow_steps") or [])
                if isinstance(s, str) and s.strip()
            ],
            "related_components": rel_comps,
        }
        if "FEATURES_WORKFLOWS" not in graphs:
            graphs.append("FEATURES_WORKFLOWS")

    if graphs:
        payload["graph_classifications"] = list(dict.fromkeys(graphs))
    else:
        payload.pop("graph_classifications", None)

    return True, None


class KnowledgeCandidateValidator:
    """Validates raw LLM JSON items against category schemas and canonical chunk texts."""

    def validate_batch_response(
        self,
        *,
        category: KnowledgeCategory,
        parsed_json: dict[str, Any],
        supplied_chunks: list[ChunkPromptInput],
        is_synthetic: bool,
    ) -> BatchValidationReport:
        report = BatchValidationReport()
        raw_items = parsed_json.get("items")
        if not isinstance(raw_items, list):
            report.rejection_reasons.append("missing_items_array")
            return report

        supplied_by_id = {str(ch.chunk_id): ch for ch in supplied_chunks}
        model_cls = _CANDIDATE_MODEL_BY_CATEGORY[category]
        report.candidates_received = len(raw_items)

        for raw_entry in raw_items:
            if not isinstance(raw_entry, dict):
                report.rejected_schema_count += 1
                report.rejection_reasons.append("candidate_not_object")
                continue

            try:
                candidate = model_cls.model_validate(raw_entry)
            except ValidationError as exc:
                report.rejected_schema_count += 1
                first_err = exc.errors()[0].get("loc", ("schema",))
                loc_tag = ".".join(map(str, first_err))
                report.rejection_reasons.append(f"schema_validation_failed:{loc_tag}")
                continue

            verified_links: list[VerifiedEvidenceLinkDraft] = []
            cited_chunks: list[ChunkPromptInput] = []
            seen_link_keys: set[tuple[uuid.UUID, str]] = set()
            ref_rejection: str | None = None

            ref_list: list[CandidateEvidenceRef] = candidate.evidence_refs
            for ref in ref_list:
                chunk_input = supplied_by_id.get(ref.chunk_id)
                if chunk_input is None:
                    ref_rejection = "cited_chunk_not_in_supplied_context"
                    continue
                ok, match_mode, match_err = verify_excerpt_in_chunk(
                    excerpt=ref.supporting_excerpt,
                    chunk_text=chunk_input.chunk_text,
                )
                if not ok or match_mode is None:
                    ref_rejection = match_err
                    continue

                dedup_key = (chunk_input.chunk_id, ref.supporting_excerpt)
                if dedup_key in seen_link_keys:
                    continue
                seen_link_keys.add(dedup_key)

                cited_chunks.append(chunk_input)
                verified_links.append(
                    VerifiedEvidenceLinkDraft(
                        evidence_id=chunk_input.evidence_id,
                        evidence_chunk_id=chunk_input.chunk_id,
                        support_type=ref.support_type,
                        source_location={
                            "chunk_index": chunk_input.chunk_index,
                            "chunk_type": chunk_input.chunk_type,
                            "page_number": chunk_input.page_number,
                            "section_title": chunk_input.section_title,
                            "char_start": chunk_input.char_start,
                            "char_end": chunk_input.char_end,
                        },
                        supporting_excerpt=ref.supporting_excerpt,
                        excerpt_match_mode=match_mode,
                        source_metadata={
                            "source_type": chunk_input.source_type,
                            "source_provider": chunk_input.source_provider,
                            "source_external_id": chunk_input.source_external_id,
                            "source_url": chunk_input.source_url,
                            "title": chunk_input.title,
                            "source_author_identity": chunk_input.source_author_identity,
                            "source_created_at": chunk_input.source_created_at_iso,
                            "source_updated_at": chunk_input.source_updated_at_iso,
                            "extracted_at": chunk_input.extracted_at_iso,
                            "evidence_content_hash": chunk_input.evidence_content_hash,
                            "chunk_content_hash": chunk_input.chunk_content_hash,
                        },
                    )
                )

            if not verified_links:
                report.rejected_ungrounded_count += 1
                rej_reason = ref_rejection or "no_verified_evidence_links"
                report.rejection_reasons.append(rej_reason)
                report.rejected_items.append({
                    "category": category.value if hasattr(category, "value") else str(category),
                    "title": getattr(candidate, "title", "untitled"),
                    "reason": rej_reason,
                })
                continue

            payload = candidate.model_dump(
                mode="json",
                exclude={
                    "title",
                    "description",
                    "is_interpretation",
                    "is_uncertain",
                    "uncertainty_reason",
                    "confidence_level",
                    "evidence_refs",
                },
            )
            payload["description"] = candidate.description

            # Guard against hallucinated severity in bugs_blockers_risks.
            if (
                category == KnowledgeCategory.BUGS_BLOCKERS_RISKS
                and payload.get("severity") not in (None, "unspecified")
            ):
                combined_excerpts = " ".join(link.supporting_excerpt for link in verified_links)
                combined_chunks = " ".join(ch.chunk_text for ch in cited_chunks)
                if not (
                    _EXPLICIT_SEVERITY_RE.search(combined_excerpts)
                    or _EXPLICIT_SEVERITY_RE.search(combined_chunks)
                ):
                    payload["severity"] = "unspecified"

            normalised_status = _extract_normalised_status(category, payload)
            person_label = _extract_person_label(category, payload)
            confidence_meta, uncertainty_reason, epistemic_status, support_classification = (
                _build_confidence_and_uncertainty(
                    category=category,
                    candidate=candidate,
                    payload=payload,
                    verified_links=verified_links,
                    normalised_status=normalised_status,
                )
            )
            fingerprint = compute_conservative_fingerprint(
                category=category,
                title=candidate.title,
                payload=payload,
                normalised_status=normalised_status,
                person_or_owner_label=person_label,
            )

            primary = cited_chunks[0]
            source_attribution = {
                "source_type": primary.source_type,
                "source_provider": primary.source_provider,
                "source_external_id": primary.source_external_id,
                "source_url": primary.source_url,
                "source_author_identity": primary.source_author_identity,
                "title": primary.title,
                "source_created_at": primary.source_created_at_iso,
                "evidence_count": len({link.evidence_id for link in verified_links}),
            }

            primary_dom = map_category_to_domain(category.value).value
            report.accepted_items.append(
                ValidatedKnowledgeItemDraft(
                    category=category,
                    epistemic_status=epistemic_status,
                    review_status=KnowledgeReviewStatus.PENDING_REVIEW.value,
                    support_classification=support_classification,
                    title=candidate.title,
                    structured_summary=candidate.description,
                    structured_payload=payload,
                    normalised_status=normalised_status,
                    person_or_owner_label=person_label,
                    source_attribution=source_attribution,
                    fingerprint=fingerprint,
                    confidence_metadata=confidence_meta,
                    uncertainty_reason=uncertainty_reason,
                    source_observed_at=_parse_optional_source_timestamp(cited_chunks),
                    is_synthetic=is_synthetic,
                    evidence_links=tuple(verified_links),
                    primary_domain=primary_dom,
                    secondary_domains=(),
                )
            )

        return report

    def validate_multi_domain_response(
        self,
        *,
        parsed_json: dict[str, Any],
        supplied_chunks: list[ChunkPromptInput],
        is_synthetic: bool,
    ) -> BatchValidationReport:
        """Validate multi-domain extraction output covering all 8 canonical categories in 1 pass."""
        report = BatchValidationReport()
        raw_items = parsed_json.get("items")
        if not isinstance(raw_items, list):
            report.rejection_reasons.append("missing_items_array")
            return report

        supplied_by_id = {str(ch.chunk_id): ch for ch in supplied_chunks}
        report.candidates_received = len(raw_items)

        category_aliases: dict[str, KnowledgeCategory] = {
            "project_overview_context": KnowledgeCategory.PROJECT_OVERVIEW_CONTEXT,
            "decisions_rationale": KnowledgeCategory.DECISIONS_RATIONALE,
            "technical_architecture": KnowledgeCategory.TECHNICAL_ARCHITECTURE,
            "work_items": KnowledgeCategory.WORK_ITEMS,
            "responsibilities_ownership": KnowledgeCategory.RESPONSIBILITIES_OWNERSHIP,
            "dependencies": KnowledgeCategory.DEPENDENCIES,
            "bugs_blockers_risks": KnowledgeCategory.BUGS_BLOCKERS_RISKS,
            "operational_historical": KnowledgeCategory.OPERATIONAL_HISTORICAL,
            "work_progress": KnowledgeCategory.WORK_ITEMS,
            "architecture_technical": KnowledgeCategory.TECHNICAL_ARCHITECTURE,
            "dependencies_relationships": KnowledgeCategory.DEPENDENCIES,
            "risks_blockers_questions": KnowledgeCategory.BUGS_BLOCKERS_RISKS,
        }

        for raw_entry in raw_items:
            if not isinstance(raw_entry, dict):
                report.rejected_schema_count += 1
                report.rejection_reasons.append("candidate_not_object")
                report.rejected_items.append({"category": "unknown", "title": "<non-dict>", "reason": "candidate_not_object"})
                continue

            raw_cat = str(raw_entry.get("category", "")).lower().strip()
            category = category_aliases.get(raw_cat)
            if category is None:
                report.rejected_schema_count += 1
                report.rejection_reasons.append(f"unknown_category:{raw_cat[:30]}")
                report.rejected_items.append({"category": raw_cat, "title": str(raw_entry.get("title", "")), "reason": f"unknown_category:{raw_cat[:30]}"})
                continue

            title = str(raw_entry.get("title", "")).strip()
            if not title:
                report.rejected_schema_count += 1
                report.rejection_reasons.append("missing_title")
                report.rejected_items.append({"category": raw_cat, "title": "<missing_title>", "reason": "missing_title"})
                continue

            summary = str(raw_entry.get("structured_summary") or raw_entry.get("description") or title).strip()

            raw_refs = raw_entry.get("evidence_refs")
            if not isinstance(raw_refs, list) or not raw_refs:
                report.rejected_ungrounded_count += 1
                report.rejection_reasons.append("missing_evidence_refs")
                report.rejected_items.append({"category": raw_cat, "title": title, "reason": "missing_evidence_refs"})
                continue

            verified_links: list[VerifiedEvidenceLinkDraft] = []
            cited_chunks: list[ChunkPromptInput] = []
            seen_link_keys: set[tuple[uuid.UUID, str]] = set()
            ref_rejection: str | None = None

            for ref in raw_refs:
                if not isinstance(ref, dict):
                    continue
                chunk_id_str = str(ref.get("chunk_id", "")).strip()
                chunk_input = supplied_by_id.get(chunk_id_str)
                if chunk_input is None:
                    ref_rejection = "cited_chunk_not_in_supplied_context"
                    continue

                excerpt = str(ref.get("supporting_excerpt", "")).strip()
                ok, match_mode, match_err = verify_excerpt_in_chunk(
                    excerpt=excerpt,
                    chunk_text=chunk_input.chunk_text,
                )
                if not ok or match_mode is None:
                    ref_rejection = match_err
                    continue

                dedup_key = (chunk_input.chunk_id, excerpt)
                if dedup_key in seen_link_keys:
                    continue
                seen_link_keys.add(dedup_key)

                support_type = str(ref.get("support_type", "direct")).lower()
                if support_type not in {"direct", "interpretation", "uncertain"}:
                    support_type = "direct"

                cited_chunks.append(chunk_input)
                verified_links.append(
                    VerifiedEvidenceLinkDraft(
                        evidence_id=chunk_input.evidence_id,
                        evidence_chunk_id=chunk_input.chunk_id,
                        support_type=support_type,
                        source_location={
                            "chunk_index": chunk_input.chunk_index,
                            "chunk_type": chunk_input.chunk_type,
                            "page_number": chunk_input.page_number,
                            "section_title": chunk_input.section_title,
                            "char_start": chunk_input.char_start,
                            "char_end": chunk_input.char_end,
                        },
                        supporting_excerpt=excerpt,
                        excerpt_match_mode=match_mode,
                        source_metadata={
                            "source_type": chunk_input.source_type,
                            "source_provider": chunk_input.source_provider,
                            "source_external_id": chunk_input.source_external_id,
                            "source_url": chunk_input.source_url,
                            "title": chunk_input.title,
                            "source_author_identity": chunk_input.source_author_identity,
                            "source_created_at": chunk_input.source_created_at_iso,
                            "source_updated_at": chunk_input.source_updated_at_iso,
                            "extracted_at": chunk_input.extracted_at_iso,
                            "evidence_content_hash": chunk_input.evidence_content_hash,
                            "chunk_content_hash": chunk_input.chunk_content_hash,
                        },
                    )
                )

            if not verified_links:
                report.rejected_ungrounded_count += 1
                rej_reason = ref_rejection or "no_verified_evidence_links"
                report.rejection_reasons.append(rej_reason)
                report.rejected_items.append({
                    "category": category.value if hasattr(category, "value") else str(category),
                    "title": title,
                    "reason": rej_reason,
                })
                continue

            payload = dict(raw_entry.get("structured_payload") or {})
            for k, v in raw_entry.items():
                if k not in {
                    "category",
                    "title",
                    "description",
                    "structured_summary",
                    "evidence_refs",
                    "is_interpretation",
                    "is_uncertain",
                    "uncertainty_reason",
                    "confidence_level",
                    "structured_payload",
                } and k not in payload:
                    payload[k] = v
            if "description" not in payload:
                payload["description"] = summary

            graph_ok, graph_rej = _validate_and_normalize_graph_payload(
                payload=payload,
                title=title,
                cited_chunks=cited_chunks,
                verified_links=verified_links,
            )
            if not graph_ok:
                report.rejected_ungrounded_count += 1
                rej_reason = graph_rej or "ungrounded_graph_details"
                report.rejection_reasons.append(rej_reason)
                report.rejected_items.append({
                    "category": category.value if hasattr(category, "value") else str(category),
                    "title": title,
                    "reason": rej_reason,
                })
                continue

            normalised_status = _extract_normalised_status(category, payload)
            person_label = _extract_person_label(category, payload)

            is_interpretation = bool(raw_entry.get("is_interpretation")) or any(
                link.support_type == "interpretation" for link in verified_links
            )
            is_uncertain = bool(raw_entry.get("is_uncertain")) or any(
                link.support_type == "uncertain" for link in verified_links
            )
            uncertainty_reason = str(raw_entry.get("uncertainty_reason") or "") if is_uncertain else None

            support_classification = "interpretation" if is_interpretation else "direct"
            epistemic_status = (
                EpistemicStatus.INTERPRETED.value if is_interpretation else EpistemicStatus.EXTRACTED.value
            )

            conf_level_str = str(raw_entry.get("confidence_level", "medium")).lower()
            if conf_level_str not in {"high", "medium", "low"}:
                conf_level_str = "medium"

            base_score = 0.90 if conf_level_str == "high" else (0.75 if conf_level_str == "medium" else 0.55)
            if is_interpretation:
                base_score -= 0.10
            if is_uncertain:
                base_score -= 0.15

            confidence_meta = {
                "extraction_confidence": conf_level_str,
                "confidence_score": round(max(0.35, min(0.99, base_score)), 2),
                "is_interpretation": is_interpretation,
                "conflict_or_ambiguity_flag": is_uncertain,
            }

            fingerprint = compute_conservative_fingerprint(
                category=category,
                title=title,
                payload=payload,
                normalised_status=normalised_status,
                person_or_owner_label=person_label,
            )

            primary = cited_chunks[0]
            source_attribution = {
                "source_type": primary.source_type,
                "source_provider": primary.source_provider,
                "source_external_id": primary.source_external_id,
                "source_url": primary.source_url,
                "source_author_identity": primary.source_author_identity,
                "title": primary.title,
                "source_created_at": primary.source_created_at_iso,
                "evidence_count": len({link.evidence_id for link in verified_links}),
            }

            primary_dom = map_category_to_domain(category.value).value
            report.accepted_items.append(
                ValidatedKnowledgeItemDraft(
                    category=category,
                    epistemic_status=epistemic_status,
                    review_status=KnowledgeReviewStatus.PENDING_REVIEW.value,
                    support_classification=support_classification,
                    title=title,
                    structured_summary=summary,
                    structured_payload=payload,
                    normalised_status=normalised_status,
                    person_or_owner_label=person_label,
                    source_attribution=source_attribution,
                    fingerprint=fingerprint,
                    confidence_metadata=confidence_meta,
                    uncertainty_reason=uncertainty_reason,
                    source_observed_at=_parse_optional_source_timestamp(cited_chunks),
                    is_synthetic=is_synthetic,
                    evidence_links=tuple(verified_links),
                    primary_domain=primary_dom,
                    secondary_domains=(),
                )
            )

        return report

