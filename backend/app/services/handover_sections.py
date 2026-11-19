"""Read-Only Canonical Handover Section Retrieval & Provenance Hydration Service.

Platform: The Handover
Module: Handover Workspace (Module 4 / Knowledge Transfer Area)

Provides read-only hydration of persisted HandoverPackageSection records and
HandoverContentLink provenance chains for a specific handover case and immutable
package version while enforcing:
1. Strict project & case scoping (prevents cross-project/cross-case leakage)
2. Fail-closed read-time source ACL checks via check_evidence_accessibility()
3. Four-tier epistemic separation (never upgrades unverified or conflicted items)
4. Defensive secret redaction on displayed content (Domain 8 & all domains)
5. Zero mutation of persisted versions, sections, or hashes
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import NotFoundError
from app.models.enums import (
    ChecklistItemStatus,
    ConflictResolutionState,
    EpistemicStatus,
    HandoverLinkType,
    HandoverPackageSectionType,
    KnowledgeReviewStatus,
    ProjectMembershipStatus,
    VerificationTargetType,
)
from app.models.evidence import EvidenceItem
from app.models.handover import (
    HandoverCase,
    HandoverChecklist,
    HandoverContentLink,
    HandoverPackageSection,
    HandoverPackageVersion,
    HandoverResponsibilityTransfer,
)
from app.models.integration import SourceAccessPolicy
from app.models.knowledge import KnowledgeEvidenceLink, KnowledgeItem
from app.models.project import Project, ProjectMembership
from app.models.relationship import (
    KnowledgeEntity,
    KnowledgeRelationship,
    RelationshipEvidenceLink,
)
from app.models.user import User
from app.models.verification import (
    VerificationCase,
    VerificationConflict,
    VerificationReviewEvent,
)
from app.repositories.handover import HandoverPackageVersionRepository
from app.schemas.handover import (
    HandoverContentLinkResponse,
    HandoverDomainEpistemicBreakdown,
    HandoverEvidenceProvenanceResponse,
    HandoverMandatorySectionResponse,
    HandoverPackageVersionResponse,
    HandoverSectionConflictItemResponse,
    HandoverSectionDetailResponse,
    HandoverSectionKnowledgeItemResponse,
    HandoverSectionRelationshipResponse,
    HandoverVerificationSummaryResponse,
    HandoverVersionSectionsResponse,
)
from app.services.handover_assembly import DOMAIN_CATEGORY_MAP, SECTION_ORDER
from app.services.handover_eligibility import check_evidence_accessibility

_SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"-----BEGIN [A-Z0-9 ]+ PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9 ]+ PRIVATE KEY-----"), "[REDACTED_PRIVATE_KEY]"),
    (re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{20,}\b"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"), "[REDACTED_GITHUB_PAT]"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), "[REDACTED_SLACK_TOKEN]"),
    (re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"), "[REDACTED_API_KEY]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED_AWS_KEY]"),
    (re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9\-._~+/]+=*"), r"\1 [REDACTED_TOKEN]"),
    (
        re.compile(r"(?i)\b(password|passwd|api_key|apikey|secret_key|client_secret|access_token|refresh_token|private_key)\s*[:=]\s*['\"]?[^\s'\",;]{6,}['\"]?"),
        r"\1=[REDACTED]",
    ),
]


def redact_secrets(text: str | None) -> str:
    """Defensively redact credential or token patterns from displayed text."""
    if not text:
        return ""
    cleaned = text
    for pattern, replacement in _SECRET_PATTERNS:
        cleaned = pattern.sub(replacement, cleaned)
    return cleaned


def _redact_payload(value: Any) -> Any:
    """Recursively redact secrets from structured JSON payloads for safe display."""
    if isinstance(value, str):
        return redact_secrets(value)
    if isinstance(value, list):
        return [_redact_payload(v) for v in value]
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for k, v in value.items():
            key_lower = str(k).lower()
            if any(tok in key_lower for tok in ("password", "secret", "token", "api_key", "private_key", "credential")):
                redacted[k] = "[REDACTED]"
            else:
                redacted[k] = _redact_payload(v)
        return redacted
    return value


def _extract_confidence(ki: KnowledgeItem) -> float | None:
    meta = ki.confidence_metadata_json or {}
    for key in ("confidence_score", "confidence", "score"):
        val = meta.get(key)
        if isinstance(val, (int, float)):
            return float(val) if val <= 1.0 else round(float(val) / 100.0, 3)
    return None


def _map_category_to_section(category: str) -> str:
    for sec_type, categories in DOMAIN_CATEGORY_MAP.items():
        if category in categories:
            return sec_type
    return HandoverPackageSectionType.PROJECT_OVERVIEW_CONTEXT.value


HANDOVER_ROLE_CONFIG: dict[str, dict[str, Any]] = {
    "developer": {
        "label": "Developer Handover",
        "focus_summary": (
            "Prioritises technical architecture, implementation decisions, pending engineering tasks, "
            "component dependencies, bugs/blockers, and practical next steps."
        ),
        "priority_order": [2, 5, 4, 6, 7, 9, 3, 8, 1, 10],
        "top_sections": {2, 5, 4, 6, 7, 9},
    },
    "project_manager": {
        "label": "Project Manager Handover",
        "focus_summary": (
            "Prioritises project status, completed and pending deliverables, active risks, dependencies, "
            "team responsibilities, and milestone decisions."
        ),
        "priority_order": [1, 3, 4, 7, 6, 8, 5, 9, 2, 10],
        "top_sections": {1, 3, 4, 7, 6, 8},
    },
    "technical_lead": {
        "label": "Technical Lead Handover",
        "focus_summary": (
            "Prioritises architectural decisions and trade-offs, system dependencies, component ownership, "
            "technical debt/risks, and strategic continuation steps."
        ),
        "priority_order": [5, 2, 6, 8, 7, 4, 9, 3, 1, 10],
        "top_sections": {5, 2, 6, 8, 7},
    },
}

_COMPLETED_STATUS_TOKENS: frozenset[str] = frozenset(
    {"completed", "done", "merged", "closed", "resolved", "delivered", "shipped", "finished"}
)
_PENDING_STATUS_TOKENS: frozenset[str] = frozenset(
    {"pending", "open", "in_progress", "in-progress", "todo", "blocked", "wip", "draft", "planned"}
)


def normalize_handover_type(handover_type: str | None) -> str:
    """Normalize role presentation key to one of developer | project_manager | technical_lead."""
    val = (handover_type or "developer").strip().lower()
    return val if val in HANDOVER_ROLE_CONFIG else "developer"


def _is_completed_work_item(item: HandoverSectionKnowledgeItemResponse) -> bool:
    """Classify an approved work_progress finding as completed vs pending strictly from evidence fields."""
    norm = (item.normalised_status or "").strip().lower()
    if norm in _COMPLETED_STATUS_TOKENS:
        return True
    if norm in _PENDING_STATUS_TOKENS:
        return False

    payload_status = str((item.structured_payload or {}).get("status") or "").strip().lower()
    if payload_status in _COMPLETED_STATUS_TOKENS:
        return True
    if payload_status in _PENDING_STATUS_TOKENS:
        return False

    combined = f"{item.title} {item.content}".lower()
    has_pending_marker = any(
        tok in combined for tok in ("pending", "todo", "to-do", "unfinished", "in progress", "blocked", "remaining", "next task", "open issue")
    )
    has_completed_marker = any(
        tok in combined for tok in ("completed", "delivered", "merged", "shipped", "finalized", "implemented and verified", "finished")
    )
    return has_completed_marker and not has_pending_marker


def _format_item_bullets(
    items: list[HandoverSectionKnowledgeItemResponse],
    *,
    note_pr_runtime: bool = False,
    note_decision_rationale: bool = False,
) -> str:
    """Deterministically format verified findings with full source attribution."""
    lines: list[str] = []
    for ki in items:
        lines.append(f"### {ki.title}")
        if ki.content:
            lines.append(ki.content)
        if ki.owner_label:
            lines.append(f"- **Owner / Actor**: {ki.owner_label}")
        if ki.normalised_status:
            lines.append(f"- **Recorded State**: {ki.normalised_status}")
        if note_pr_runtime and any(tok in f"{ki.title} {ki.content}".lower() for tok in ("pull request", "pr ", "merged")):
            lines.append(
                "- *Verification Scope Note*: Confirmed merged/delivered in repository evidence; verify runtime production deployment separately."
            )
        if note_decision_rationale and not any(
            tok in (ki.content or "").lower() for tok in ("because", "rationale", "reason", "trade-off", "alternative", "chosen")
        ) and not (ki.structured_payload or {}).get("rationale"):
            lines.append(
                "- *Rationale Note*: Documented decision is verified; underlying rationale or rejected alternatives were not explicitly recorded in linked evidence."
            )
        sources = ", ".join(
            p.source_name if not p.acl_restricted else "Restricted Source (Source ACL Protected)"
            for p in ki.provenance
        )
        if sources:
            lines.append(f"- **Sources**: {sources}")
        lines.append("")
    return "\n".join(lines).strip()


def build_mandatory_ten_sections(
    *,
    hydrated_sections: list[HandoverSectionDetailResponse],
    handover_type: str,
    unresolved_conflicts: list[HandoverSectionConflictItemResponse],
    resolved_conflicts: list[HandoverSectionConflictItemResponse],
    team_members_ctx: list[dict[str, Any]],
    transfers_ctx: list[dict[str, Any]],
    checklists: list[HandoverChecklist],
    domain_context_overview: dict[str, Any],
    omit_restricted_items: bool = False,
) -> list[HandoverMandatorySectionResponse]:
    """Assemble the canonical 10 mandatory handover sections deterministically from approved content."""
    role_key = normalize_handover_type(handover_type)
    role_cfg = HANDOVER_ROLE_CONFIG[role_key]
    priority_order: list[int] = role_cfg["priority_order"]
    top_sections: set[int] = role_cfg["top_sections"]
    rank_by_section_num = {sec_num: idx + 1 for idx, sec_num in enumerate(priority_order)}

    sec_map = {sec.section_type: sec for sec in hydrated_sections}

    def _permitted_kis(section_type: str) -> list[HandoverSectionKnowledgeItemResponse]:
        sec = sec_map.get(section_type)
        if not sec:
            return []
        if not omit_restricted_items:
            return list(sec.knowledge_items)
        return [
            ki for ki in sec.knowledge_items if not any(p.acl_restricted for p in ki.provenance)
        ]

    def _permitted_rels(section_type: str) -> list[HandoverSectionRelationshipResponse]:
        sec = sec_map.get(section_type)
        if not sec:
            return []
        if not omit_restricted_items:
            return list(sec.relationships)
        return [
            rel for rel in sec.relationships if not any(p.acl_restricted for p in rel.provenance)
        ]

    def _pending_count(section_types: list[str]) -> int:
        return sum(
            sec_map[st].epistemic_breakdown.pending_verification
            for st in section_types
            if st in sec_map
        )

    def _collect_provenance(
        items: list[HandoverSectionKnowledgeItemResponse],
        rels: list[HandoverSectionRelationshipResponse],
    ) -> list[HandoverEvidenceProvenanceResponse]:
        by_id: dict[uuid.UUID, HandoverEvidenceProvenanceResponse] = {}
        for ki in items:
            for p in ki.provenance:
                if omit_restricted_items and p.acl_restricted:
                    continue
                by_id.setdefault(p.evidence_id, p)
        for rel in rels:
            for p in rel.provenance:
                if omit_restricted_items and p.acl_restricted:
                    continue
                by_id.setdefault(p.evidence_id, p)
        return list(by_id.values())

    # 1. Project Overview
    overview_kis = _permitted_kis(HandoverPackageSectionType.PROJECT_OVERVIEW_CONTEXT.value)
    overview_pending = _pending_count([HandoverPackageSectionType.PROJECT_OVERVIEW_CONTEXT.value])
    overview_lines: list[str] = []
    if domain_context_overview.get("project_name"):
        overview_lines.append(
            f"**Project**: {redact_secrets(str(domain_context_overview.get('project_name')))}"
        )
    if domain_context_overview.get("project_description"):
        overview_lines.append(redact_secrets(str(domain_context_overview.get("project_description"))))
    if overview_kis:
        overview_lines.append("")
        overview_lines.append(_format_item_bullets(overview_kis))
    overview_ready = "ready" if overview_kis else "insufficient_information"
    overview_gap = (
        None
        if overview_kis
        else "Insufficient approved project overview findings. Verify project overview claims in Verification Center instead of relying on unreviewed summaries."
    )

    # 2. Architecture and Technical Context
    arch_kis = _permitted_kis(HandoverPackageSectionType.TECHNICAL_ARCHITECTURE.value)
    ops_kis = _permitted_kis(HandoverPackageSectionType.OPERATIONAL_HISTORICAL.value)
    arch_combined = arch_kis + ops_kis
    arch_pending = _pending_count([
        HandoverPackageSectionType.TECHNICAL_ARCHITECTURE.value,
        HandoverPackageSectionType.OPERATIONAL_HISTORICAL.value,
    ])
    arch_parts: list[str] = []
    if arch_kis:
        arch_parts.append(_format_item_bullets(arch_kis))
    if ops_kis:
        arch_parts.append("## Operational Procedures & Runbooks\n\n" + _format_item_bullets(ops_kis))
    arch_ready = "ready" if arch_combined else "insufficient_information"
    arch_gap = (
        None
        if arch_combined
        else "No human-verified system architecture, API, deployment, or operational procedure findings exist in this version."
    )

    # 3 & 4. Completed Work vs Pending Work
    work_kis = _permitted_kis(HandoverPackageSectionType.WORK_PROGRESS.value)
    work_pending_count = _pending_count([HandoverPackageSectionType.WORK_PROGRESS.value])
    completed_kis = [ki for ki in work_kis if _is_completed_work_item(ki)]
    pending_kis = [ki for ki in work_kis if not _is_completed_work_item(ki)]

    all_checklist_items = [item for chk in checklists for item in (chk.items or [])]
    completed_checklist = [
        it for it in all_checklist_items if it.status == ChecklistItemStatus.COMPLETED.value
    ]
    open_checklist = [
        it
        for it in all_checklist_items
        if it.status not in (ChecklistItemStatus.COMPLETED.value, ChecklistItemStatus.SKIPPED.value)
    ]

    comp_lines: list[str] = []
    if completed_kis:
        comp_lines.append(_format_item_bullets(completed_kis, note_pr_runtime=True))
    if completed_checklist:
        comp_lines.append("### Completed Handover Checklist Items")
        for it in completed_checklist:
            comp_lines.append(f"- [x] {redact_secrets(it.item_text)}")
    comp_ready = "ready" if (completed_kis or completed_checklist) else "insufficient_information"
    comp_gap = (
        None
        if (completed_kis or completed_checklist)
        else "No human-verified completed deliverables or merged milestones are recorded in this version."
    )

    pend_lines: list[str] = []
    if pending_kis:
        pend_lines.append(_format_item_bullets(pending_kis))
    if open_checklist:
        pend_lines.append("### Open Transition Checklist Tasks")
        for it in open_checklist:
            blocking_tag = " *(BLOCKING)*" if it.blocking else ""
            pend_lines.append(f"- [ ] {redact_secrets(it.item_text)}{blocking_tag}")
    pend_ready = "ready" if (pending_kis or open_checklist) else "insufficient_information"
    pend_gap = (
        None
        if (pending_kis or open_checklist)
        else "No human-verified pending work items or open checklist tasks are recorded."
    )

    # 5. Important Decisions and Rationale
    dec_kis = _permitted_kis(HandoverPackageSectionType.DECISIONS_RATIONALE.value)
    dec_pending = _pending_count([HandoverPackageSectionType.DECISIONS_RATIONALE.value])
    dec_md = _format_item_bullets(dec_kis, note_decision_rationale=True) if dec_kis else ""
    dec_ready = "ready" if dec_kis else "insufficient_information"
    dec_gap = (
        None
        if dec_kis
        else "No human-verified technical or project decisions with rationale have been approved yet."
    )

    # 6. Dependencies
    dep_kis = _permitted_kis(HandoverPackageSectionType.DEPENDENCIES_RELATIONSHIPS.value)
    dep_rels = _permitted_rels(HandoverPackageSectionType.DEPENDENCIES_RELATIONSHIPS.value)
    dep_pending = _pending_count([HandoverPackageSectionType.DEPENDENCIES_RELATIONSHIPS.value])
    dep_lines: list[str] = []
    if dep_rels:
        dep_lines.append("### Evidence-Supported Component & Task Relationships")
        for rel in dep_rels:
            dep_lines.append(
                f"- **{redact_secrets(rel.source_entity_name)}** (`{rel.relationship_type}`) -> **{redact_secrets(rel.target_entity_name)}**"
            )
        dep_lines.append("")
    if dep_kis:
        dep_lines.append(_format_item_bullets(dep_kis))
    dep_ready = "ready" if (dep_kis or dep_rels) else "insufficient_information"
    dep_gap = (
        None
        if (dep_kis or dep_rels)
        else "No evidence-supported component, service, or task dependencies have been verified yet."
    )

    # 7. Risks and Blockers
    risk_kis = _permitted_kis(HandoverPackageSectionType.BUGS_BLOCKERS_RISKS.value)
    risk_pending = _pending_count([HandoverPackageSectionType.BUGS_BLOCKERS_RISKS.value])
    risk_lines: list[str] = []
    if risk_kis:
        active_risks = [ki for ki in risk_kis if (ki.normalised_status or "").lower() not in _COMPLETED_STATUS_TOKENS]
        historical_risks = [ki for ki in risk_kis if (ki.normalised_status or "").lower() in _COMPLETED_STATUS_TOKENS]
        if active_risks:
            risk_lines.append("### Active Risks & Technical Blockers")
            risk_lines.append(_format_item_bullets(active_risks))
        if historical_risks:
            risk_lines.append("### Resolved Historical Issues")
            risk_lines.append(_format_item_bullets(historical_risks))
    if unresolved_conflicts:
        risk_lines.append(
            f"### Unresolved Cross-Source Conflicts ({len(unresolved_conflicts)} — Excluded from Verified Facts)"
        )
        for cf in unresolved_conflicts:
            risk_lines.append(f"- **{cf.conflict_type}**: {cf.explanation}")
    if resolved_conflicts:
        risk_lines.append(f"### Resolved Conflicts ({len(resolved_conflicts)})")
        for cf in resolved_conflicts:
            risk_lines.append(
                f"- **{cf.conflict_type}**: {cf.authoritative_claim_text or cf.explanation}"
            )

    if unresolved_conflicts:
        risk_ready = "blocked_by_conflict"
        risk_gap = (
            f"{len(unresolved_conflicts)} unresolved cross-source contradiction(s) require reviewer investigation in Conflict Management."
        )
    elif risk_kis or resolved_conflicts:
        risk_ready = "ready"
        risk_gap = None
    else:
        risk_ready = "insufficient_information"
        risk_gap = "No human-verified bugs, blockers, or risks are recorded in this version."

    # 8. Responsibilities
    resp_kis = _permitted_kis(HandoverPackageSectionType.RESPONSIBILITIES_OWNERSHIP.value)
    resp_pending = _pending_count([HandoverPackageSectionType.RESPONSIBILITIES_OWNERSHIP.value])
    unassigned_transfers = [t for t in transfers_ctx if not t.get("proposed_successor_id")]
    unassigned_checklist = [it for it in open_checklist if not it.assigned_to_user_id]

    resp_lines: list[str] = []
    if resp_kis:
        resp_lines.append("### Verified Ownership & Responsibility Findings")
        resp_lines.append(_format_item_bullets(resp_kis))
    if transfers_ctx:
        resp_lines.append("### Explicit Handover Responsibility Transfers")
        for tr in transfers_ctx:
            owner_name = tr.get("current_owner_name") or "Outgoing Member"
            succ_name = tr.get("proposed_successor_name") or "Unassigned (Requires Clarification)"
            resp_lines.append(
                f"- **{redact_secrets(tr.get('responsibility_description', ''))}** — {owner_name} -> {succ_name} (`{tr.get('transfer_status')}`)"
            )
    elif team_members_ctx:
        resp_lines.append("### Project Roster Reference (Membership != Technical Ownership)")
        for tm in team_members_ctx:
            role_note = f" ({tm.get('responsibility_description')})" if tm.get("responsibility_description") else ""
            resp_lines.append(
                f"- {tm.get('full_name') or tm.get('email') or 'Member'} — Role: `{tm.get('role_name')}`{role_note}"
            )
    if unassigned_transfers or unassigned_checklist:
        resp_lines.append("### Unassigned Duties Requiring Clarification")
        for tr in unassigned_transfers:
            resp_lines.append(f"- Transfer lacking proposed successor: {redact_secrets(tr.get('responsibility_description', ''))}")
        for it in unassigned_checklist:
            resp_lines.append(f"- Unassigned checklist task: {redact_secrets(it.item_text)}")

    resp_has_content = bool(resp_kis or transfers_ctx)
    resp_ready = (
        "needs_attention"
        if resp_has_content and unassigned_transfers
        else "ready"
        if resp_has_content
        else "insufficient_information"
    )
    resp_gap = (
        None
        if resp_ready == "ready"
        else "Some responsibilities lack an assigned successor."
        if resp_ready == "needs_attention"
        else "No verified ownership records or responsibility transfers are defined yet. Project membership alone does not establish component ownership."
    )

    # 9. Recommended Next Steps (strictly derived from verified pending work, blockers, dependencies, and runbooks)
    steps: list[dict[str, Any]] = []
    for cf in unresolved_conflicts:
        steps.append(
            {
                "priority": "urgent",
                "source_section": "Risks and Blockers",
                "title": f"Resolve verification conflict ({cf.conflict_type})",
                "detail": cf.explanation,
                "action_target": "conflicts",
            }
        )
    for ki in pending_kis:
        steps.append(
            {
                "priority": "high",
                "source_section": "Pending Work",
                "title": ki.title,
                "detail": ki.content,
                "owner": ki.owner_label,
                "action_target": "tasks",
            }
        )
    for rel in dep_rels:
        steps.append(
            {
                "priority": "medium",
                "source_section": "Dependencies",
                "title": f"Verify dependency: {redact_secrets(rel.source_entity_name)} -> {redact_secrets(rel.target_entity_name)}",
                "detail": f"Relationship type: {rel.relationship_type}",
                "action_target": "dependencies",
            }
        )
    for it in open_checklist:
        steps.append(
            {
                "priority": "high" if it.blocking else "medium",
                "source_section": "Transition Checklist",
                "title": redact_secrets(it.item_text),
                "detail": redact_secrets(it.description or ""),
                "action_target": "checklists",
            }
        )
    for ki in ops_kis[:3]:
        steps.append(
            {
                "priority": "normal",
                "source_section": "Operational Context",
                "title": f"Review operational runbook: {ki.title}",
                "detail": ki.content,
                "action_target": "operations",
            }
        )

    steps_lines: list[str] = []
    if steps:
        for idx, st in enumerate(steps, start=1):
            owner_suffix = f" (Owner: {st['owner']})" if st.get("owner") else ""
            steps_lines.append(
                f"{idx}. **[{st['priority'].upper()}] {st['title']}**{owner_suffix} — *From {st['source_section']}*"
            )
            if st.get("detail"):
                steps_lines.append(f"   {st['detail']}")
    steps_ready = "ready" if steps else "insufficient_information"
    steps_gap = (
        None
        if steps
        else "Insufficient approved pending work, dependencies, or open checklist tasks to derive continuation steps. Steps are never invented without evidence."
    )

    # 10. Evidence References (deduplicated across all permitted items and relationships)
    all_section_items = (
        overview_kis + arch_combined + completed_kis + pending_kis + dec_kis + dep_kis + risk_kis + resp_kis
    )
    all_evidence_refs = _collect_provenance(all_section_items, dep_rels)
    ref_lines: list[str] = []
    for ref in all_evidence_refs:
        if ref.acl_restricted:
            ref_lines.append(
                f"- `[{str(ref.evidence_id)[:8]}]` **Restricted Source (Source ACL Protected)** — Access restricted by external source ACL."
            )
        else:
            author_part = f" · Author: {ref.author}" if ref.author else ""
            url_part = f" · URL: {ref.source_url}" if ref.source_url else ""
            ref_lines.append(
                f"- `[{str(ref.evidence_id)[:8]}]` **{ref.source_name}** (`{ref.source_type}`){author_part}{url_part}"
            )
    ref_ready = "ready" if all_evidence_refs else "insufficient_information"
    ref_gap = (
        None
        if all_evidence_refs
        else "No supporting original evidence references are linked to approved findings in this version."
    )

    def _emphasis(num: int, default_note: str) -> str:
        if num in top_sections:
            return f"Primary focus for {role_cfg['label']}. {default_note}"
        return f"Contextual reference for {role_cfg['label']}. {default_note}"

    specs: list[dict[str, Any]] = [
        {
            "section_number": 1,
            "section_key": "project_overview",
            "section_title": "Project Overview",
            "source_domains": ["project_overview_context"],
            "emphasis": "Purpose, scope, project background, and verified current state.",
            "readiness_status": overview_ready,
            "insufficient_info_message": overview_gap,
            "content_markdown": "\n".join(overview_lines).strip(),
            "knowledge_items": overview_kis,
            "relationships": [],
            "unresolved_conflicts": [],
            "evidence_references": _collect_provenance(overview_kis, []),
            "pending_verification_count": overview_pending,
        },
        {
            "section_number": 2,
            "section_key": "architecture_technical_context",
            "section_title": "Architecture and Technical Context",
            "source_domains": ["technical_architecture", "operational_historical"],
            "emphasis": "System architecture, services, stack, APIs, constraints, and operational runbooks.",
            "readiness_status": arch_ready,
            "insufficient_info_message": arch_gap,
            "content_markdown": "\n\n".join(arch_parts).strip(),
            "knowledge_items": arch_combined,
            "relationships": [],
            "unresolved_conflicts": [],
            "evidence_references": _collect_provenance(arch_combined, []),
            "pending_verification_count": arch_pending,
        },
        {
            "section_number": 3,
            "section_key": "completed_work",
            "section_title": "Completed Work",
            "source_domains": ["work_progress"],
            "emphasis": "Delivered features, merged work, and completed handover milestones.",
            "readiness_status": comp_ready,
            "insufficient_info_message": comp_gap,
            "content_markdown": "\n\n".join(comp_lines).strip(),
            "knowledge_items": completed_kis,
            "relationships": [],
            "unresolved_conflicts": [],
            "evidence_references": _collect_provenance(completed_kis, []),
            "pending_verification_count": 0,
        },
        {
            "section_number": 4,
            "section_key": "pending_work",
            "section_title": "Pending Work",
            "source_domains": ["work_progress"],
            "emphasis": "In-progress tasks, open backlog, blocked deliverables, and remaining handover actions.",
            "readiness_status": pend_ready,
            "insufficient_info_message": pend_gap,
            "content_markdown": "\n\n".join(pend_lines).strip(),
            "knowledge_items": pending_kis,
            "relationships": [],
            "unresolved_conflicts": [],
            "evidence_references": _collect_provenance(pending_kis, []),
            "pending_verification_count": work_pending_count,
        },
        {
            "section_number": 5,
            "section_key": "important_decisions_rationale",
            "section_title": "Important Decisions and Rationale",
            "source_domains": ["decisions_rationale"],
            "emphasis": "Key engineering/product choices, why they were made, and trade-offs.",
            "readiness_status": dec_ready,
            "insufficient_info_message": dec_gap,
            "content_markdown": dec_md,
            "knowledge_items": dec_kis,
            "relationships": [],
            "unresolved_conflicts": [],
            "evidence_references": _collect_provenance(dec_kis, []),
            "pending_verification_count": dec_pending,
        },
        {
            "section_number": 6,
            "section_key": "dependencies",
            "section_title": "Dependencies",
            "source_domains": ["dependencies_relationships"],
            "emphasis": "Evidence-backed component, service, integration, and task dependencies.",
            "readiness_status": dep_ready,
            "insufficient_info_message": dep_gap,
            "content_markdown": "\n\n".join(dep_lines).strip(),
            "knowledge_items": dep_kis,
            "relationships": dep_rels,
            "unresolved_conflicts": [],
            "evidence_references": _collect_provenance(dep_kis, dep_rels),
            "pending_verification_count": dep_pending,
        },
        {
            "section_number": 7,
            "section_key": "risks_and_blockers",
            "section_title": "Risks and Blockers",
            "source_domains": ["bugs_blockers_risks"],
            "emphasis": "Confirmed open risks, active technical blockers, and separated unresolved conflicts.",
            "readiness_status": risk_ready,
            "insufficient_info_message": risk_gap,
            "content_markdown": "\n\n".join(risk_lines).strip(),
            "knowledge_items": risk_kis,
            "relationships": [],
            "unresolved_conflicts": unresolved_conflicts,
            "evidence_references": _collect_provenance(risk_kis, []),
            "pending_verification_count": risk_pending,
        },
        {
            "section_number": 8,
            "section_key": "responsibilities",
            "section_title": "Responsibilities",
            "source_domains": ["responsibilities_ownership"],
            "emphasis": "Verified ownership mappings, formal transfers, and duties needing clarification.",
            "readiness_status": resp_ready,
            "insufficient_info_message": resp_gap,
            "content_markdown": "\n\n".join(resp_lines).strip(),
            "knowledge_items": resp_kis,
            "relationships": [],
            "unresolved_conflicts": [],
            "evidence_references": _collect_provenance(resp_kis, []),
            "responsibilities_summary": transfers_ctx,
            "pending_verification_count": resp_pending,
        },
        {
            "section_number": 9,
            "section_key": "recommended_next_steps",
            "section_title": "Recommended Next Steps",
            "source_domains": ["work_progress", "dependencies_relationships", "bugs_blockers_risks", "operational_historical"],
            "emphasis": "Evidence-backed continuation order derived strictly from verified open work and blockers.",
            "readiness_status": steps_ready,
            "insufficient_info_message": steps_gap,
            "content_markdown": "\n".join(steps_lines).strip(),
            "knowledge_items": [],
            "relationships": [],
            "unresolved_conflicts": [],
            "evidence_references": _collect_provenance(pending_kis + ops_kis, dep_rels),
            "recommended_steps": steps,
            "pending_verification_count": 0,
        },
        {
            "section_number": 10,
            "section_key": "evidence_references",
            "section_title": "Evidence References",
            "source_domains": list(SECTION_ORDER),
            "emphasis": "Complete ACL-verified provenance index linking claims back to original sources.",
            "readiness_status": ref_ready,
            "insufficient_info_message": ref_gap,
            "content_markdown": "\n".join(ref_lines).strip(),
            "knowledge_items": [],
            "relationships": [],
            "unresolved_conflicts": [],
            "evidence_references": all_evidence_refs,
            "pending_verification_count": 0,
        },
    ]

    return [
        HandoverMandatorySectionResponse(
            section_number=s["section_number"],
            section_key=s["section_key"],
            section_title=s["section_title"],
            source_domains=s["source_domains"],
            role_priority_rank=rank_by_section_num[s["section_number"]],
            is_role_priority=s["section_number"] in top_sections,
            role_emphasis_note=_emphasis(s["section_number"], s["emphasis"]),
            readiness_status=s["readiness_status"],
            insufficient_info_message=s["insufficient_info_message"],
            content_markdown=s["content_markdown"],
            knowledge_items=s["knowledge_items"],
            relationships=s["relationships"],
            unresolved_conflicts=s["unresolved_conflicts"],
            evidence_references=s["evidence_references"],
            recommended_steps=s.get("recommended_steps", []),
            responsibilities_summary=s.get("responsibilities_summary", []),
            pending_verification_count=s["pending_verification_count"],
        )
        for s in specs
    ]


class HandoverSectionReadService:
    """Pure read-only service hydrating canonical handover sections with provenance and ACL checks."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.version_repo = HandoverPackageVersionRepository(session)

    def get_version_sections(
        self,
        case_id: uuid.UUID,
        version_id: uuid.UUID,
        *,
        project_id: uuid.UUID,
        viewer_user_id: uuid.UUID,
        has_project_manage: bool = False,
        role_override: str | None = None,
    ) -> HandoverVersionSectionsResponse:
        """Retrieve all persisted canonical sections for a specific case and package version."""
        version = self.version_repo.get_by_id(version_id, load_sections=True)
        if not version or version.project_id != project_id or version.case_id != case_id:
            raise NotFoundError("Handover package version not found for this case and project.")

        sections_sorted = sorted(version.sections, key=lambda s: (s.section_order, s.section_type))
        present_types = {s.section_type for s in sections_sorted}
        missing_types = [sec_t for sec_t in SECTION_ORDER if sec_t not in present_types]

        # Gather all linked IDs across sections
        linked_ki_ids: set[uuid.UUID] = set()
        linked_rel_ids: set[uuid.UUID] = set()
        for sec in sections_sorted:
            for link in sec.content_links:
                if link.link_type == HandoverLinkType.KNOWLEDGE_ITEM.value and link.knowledge_item_id:
                    linked_ki_ids.add(link.knowledge_item_id)
                elif link.link_type == HandoverLinkType.RELATIONSHIP.value and link.relationship_id:
                    linked_rel_ids.add(link.relationship_id)

        # Load linked KnowledgeItems with their evidence links
        ki_map: dict[uuid.UUID, KnowledgeItem] = {}
        if linked_ki_ids:
            ki_stmt = (
                select(KnowledgeItem)
                .where(
                    KnowledgeItem.id.in_(linked_ki_ids),
                    KnowledgeItem.project_id == project_id,
                )
                .options(selectinload(KnowledgeItem.evidence_links))
            )
            for ki in self.session.execute(ki_stmt).scalars().all():
                ki_map[ki.id] = ki

        # Load linked KnowledgeRelationships with entities & evidence links
        rel_map: dict[uuid.UUID, KnowledgeRelationship] = {}
        if linked_rel_ids:
            rel_stmt = (
                select(KnowledgeRelationship)
                .where(
                    KnowledgeRelationship.id.in_(linked_rel_ids),
                    KnowledgeRelationship.project_id == project_id,
                )
                .options(
                    selectinload(KnowledgeRelationship.source_entity),
                    selectinload(KnowledgeRelationship.target_entity),
                    selectinload(KnowledgeRelationship.evidence_links),
                )
            )
            for rel in self.session.execute(rel_stmt).scalars().all():
                rel_map[rel.id] = rel

        # Gather all referenced EvidenceItem IDs for a single batched ACL check + lookup
        all_evidence_ids: set[uuid.UUID] = set()
        for ki in ki_map.values():
            for el in ki.evidence_links:
                all_evidence_ids.add(el.evidence_id)
        for rel in rel_map.values():
            for rel_el in rel.evidence_links:
                all_evidence_ids.add(rel_el.evidence_id)

        cached_policies = list(
            self.session.execute(
                select(SourceAccessPolicy).where(SourceAccessPolicy.project_id == project_id)
            )
            .scalars()
            .all()
        )
        _, inaccessible_evidence_list = check_evidence_accessibility(
            self.session,
            list(all_evidence_ids),
            project_id=project_id,
            viewer_user_id=viewer_user_id,
            has_project_manage=has_project_manage,
            cached_policies=cached_policies,
        )
        inaccessible_evidence_ids = set(inaccessible_evidence_list)

        evidence_map: dict[uuid.UUID, EvidenceItem] = {}
        if all_evidence_ids:
            ev_stmt = select(EvidenceItem).where(
                EvidenceItem.id.in_(all_evidence_ids),
                EvidenceItem.project_id == project_id,
                EvidenceItem.deleted_at.is_(None),
            )
            for ev in self.session.execute(ev_stmt).scalars().all():
                evidence_map[ev.id] = ev

        # Load VerificationCases & latest VerificationReviewEvent for linked KnowledgeItems
        vc_map: dict[uuid.UUID, VerificationCase] = {}
        reviewer_user_ids: set[uuid.UUID] = set()
        if linked_ki_ids:
            vc_stmt = (
                select(VerificationCase)
                .where(
                    VerificationCase.project_id == project_id,
                    VerificationCase.target_type == VerificationTargetType.KNOWLEDGE_ITEM.value,
                    VerificationCase.target_id.in_(linked_ki_ids),
                )
                .options(selectinload(VerificationCase.review_events))
            )
            for vc in self.session.execute(vc_stmt).scalars().all():
                vc_map[vc.target_id] = vc
                if vc.review_events:
                    reviewer_user_ids.add(vc.review_events[0].reviewer_user_id)
                if vc.assigned_reviewer_id:
                    reviewer_user_ids.add(vc.assigned_reviewer_id)

        # Load Users needed for verification attribution & ownership context
        user_map: dict[uuid.UUID, User] = {}
        if reviewer_user_ids:
            u_stmt = select(User).where(User.id.in_(reviewer_user_ids))
            for u in self.session.execute(u_stmt).scalars().all():
                user_map[u.id] = u

        # Load project-wide epistemic counts (read-only transparency, never upgrades unverified items)
        all_project_kis = list(
            self.session.execute(
                select(
                    KnowledgeItem.id,
                    KnowledgeItem.category,
                    KnowledgeItem.epistemic_status,
                    KnowledgeItem.review_status,
                    KnowledgeItem.is_stale,
                    KnowledgeItem.superseded_by_id,
                ).where(
                    KnowledgeItem.project_id == project_id,
                    KnowledgeItem.is_deleted.is_(False),
                )
            ).all()
        )
        domain_epistemic: dict[str, dict[str, int]] = {
            sec_t: {
                "human_verified_included": 0,
                "pending_verification": 0,
                "rejected": 0,
                "unresolved_conflicts": 0,
                "resolved_conflicts": 0,
                "outdated": 0,
            }
            for sec_t in SECTION_ORDER
        }
        for row in all_project_kis:
            sec_t = _map_category_to_section(row.category)
            bucket = domain_epistemic.setdefault(
                sec_t,
                {
                    "human_verified_included": 0,
                    "pending_verification": 0,
                    "rejected": 0,
                    "unresolved_conflicts": 0,
                    "resolved_conflicts": 0,
                    "outdated": 0,
                },
            )
            if row.id in linked_ki_ids:
                bucket["human_verified_included"] += 1
            elif row.is_stale or row.superseded_by_id is not None:
                bucket["outdated"] += 1
            elif row.review_status == KnowledgeReviewStatus.REJECTED.value:
                bucket["rejected"] += 1
            elif (
                row.epistemic_status != EpistemicStatus.HUMAN_VERIFIED.value
                or row.review_status != KnowledgeReviewStatus.APPROVED.value
            ):
                bucket["pending_verification"] += 1

        # Load project VerificationConflicts (separated strictly from verified items)
        conflict_stmt = (
            select(VerificationConflict)
            .where(VerificationConflict.project_id == project_id)
            .order_by(VerificationConflict.updated_at.desc())
        )
        project_conflicts = list(self.session.execute(conflict_stmt).scalars().all())
        unresolved_conflict_items: list[HandoverSectionConflictItemResponse] = []
        resolved_conflict_items: list[HandoverSectionConflictItemResponse] = []
        for cf in project_conflicts:
            res_state = str(cf.resolution_state.value if hasattr(cf.resolution_state, "value") else cf.resolution_state)
            cf_type = str(cf.conflict_type.value if hasattr(cf.conflict_type, "value") else cf.conflict_type)
            item = HandoverSectionConflictItemResponse(
                id=cf.id,
                verification_case_id=cf.case_id,
                conflict_type=cf_type,
                priority=str(cf.priority or "medium"),
                resolution_state=res_state,
                explanation=redact_secrets(cf.explanation),
                claim_a_text=redact_secrets(cf.claim_a_text),
                claim_b_text=redact_secrets(cf.claim_b_text),
                side_a_source_title=cf.side_a_source_title,
                side_b_source_title=cf.side_b_source_title,
                authoritative_claim_text=redact_secrets(cf.authoritative_claim_text) if cf.authoritative_claim_text else None,
                resolution_notes=redact_secrets(cf.resolution_notes) if cf.resolution_notes else None,
                resolved_at=cf.resolved_at,
                updated_at=cf.updated_at,
            )
            if res_state in (
                ConflictResolutionState.RESOLVED.value,
                ConflictResolutionState.DISMISSED.value,
            ):
                resolved_conflict_items.append(item)
            else:
                unresolved_conflict_items.append(item)

        bugs_key = HandoverPackageSectionType.BUGS_BLOCKERS_RISKS.value
        domain_epistemic[bugs_key]["unresolved_conflicts"] = len(unresolved_conflict_items)
        domain_epistemic[bugs_key]["resolved_conflicts"] = len(resolved_conflict_items)

        # Load real Project, HandoverCase, active ProjectMemberships, and ResponsibilityTransfers
        project = self.session.get(Project, project_id)
        case = version.case or self.session.get(HandoverCase, case_id)

        memberships_stmt = (
            select(ProjectMembership)
            .where(
                ProjectMembership.project_id == project_id,
                ProjectMembership.status == ProjectMembershipStatus.ACTIVE.value,
            )
            .options(
                selectinload(ProjectMembership.user),
                selectinload(ProjectMembership.role),
            )
        )
        active_memberships = list(self.session.execute(memberships_stmt).scalars().all())
        team_members_ctx = [
            {
                "user_id": str(m.user_id),
                "full_name": m.user.full_name if m.user else None,
                "email": m.user.email if m.user else None,
                "role_name": m.role.name if m.role else "member",
                "responsibility_description": m.responsibility_description,
                "is_departing_member": bool(case and case.departing_member_id == m.user_id),
                "is_successor": bool(case and case.successor_id == m.user_id),
            }
            for m in active_memberships
        ]

        transfers_stmt = (
            select(HandoverResponsibilityTransfer)
            .where(
                HandoverResponsibilityTransfer.case_id == case_id,
                HandoverResponsibilityTransfer.project_id == project_id,
            )
            .options(
                selectinload(HandoverResponsibilityTransfer.current_owner),
                selectinload(HandoverResponsibilityTransfer.proposed_successor),
            )
            .order_by(HandoverResponsibilityTransfer.created_at.asc())
        )
        resp_transfers = list(self.session.execute(transfers_stmt).scalars().all())
        transfers_ctx = [
            {
                "id": str(t.id),
                "responsibility_description": t.responsibility_description,
                "knowledge_domain": t.knowledge_domain,
                "transfer_status": t.transfer_status,
                "transfer_notes": t.transfer_notes,
                "current_owner_id": str(t.current_owner_id),
                "current_owner_name": t.current_owner.full_name if t.current_owner else None,
                "proposed_successor_id": str(t.proposed_successor_id) if t.proposed_successor_id else None,
                "proposed_successor_name": t.proposed_successor.full_name if t.proposed_successor else None,
            }
            for t in resp_transfers
        ]

        checklists_stmt = (
            select(HandoverChecklist)
            .where(
                HandoverChecklist.case_id == case_id,
                HandoverChecklist.project_id == project_id,
            )
            .options(selectinload(HandoverChecklist.items))
            .order_by(HandoverChecklist.created_at.asc())
        )
        case_checklists = list(self.session.execute(checklists_stmt).scalars().all())

        overview_ctx: dict[str, Any] = {
            "project_name": project.name if project else None,
            "project_description": project.description if project else None,
            "project_status": project.status if project else None,
            "start_date": (
                project.start_date.isoformat()
                if project and project.start_date
                else None
            ),
            "target_completion_date": (
                project.target_completion_date.isoformat()
                if project and project.target_completion_date
                else None
            ),
            "case_title": case.title if case else None,
            "case_description": case.description if case else None,
            "case_status": case.status if case else None,
            "case_metadata": (case.metadata_json or {}) if case else {},
        }

        # Build hydrated sections
        hydrated_sections: list[HandoverSectionDetailResponse] = []
        for sec in sections_sorted:
            sec_kis: list[HandoverSectionKnowledgeItemResponse] = []
            sec_rels: list[HandoverSectionRelationshipResponse] = []
            content_links_out = [
                HandoverContentLinkResponse.model_validate(link) for link in sec.content_links
            ]

            for link in sec.content_links:
                if link.link_type == HandoverLinkType.KNOWLEDGE_ITEM.value and link.knowledge_item_id:
                    ki = ki_map.get(link.knowledge_item_id)
                    if not ki:
                        continue
                    provenance_list = self._build_ki_provenance(
                        ki.evidence_links, evidence_map, inaccessible_evidence_ids
                    )
                    vc = vc_map.get(ki.id)
                    verif_summary = self._build_verification_summary(vc, user_map)
                    sec_kis.append(
                        HandoverSectionKnowledgeItemResponse(
                            id=ki.id,
                            content_link_id=link.id,
                            title=redact_secrets(ki.title),
                            content=redact_secrets(ki.structured_summary),
                            category=ki.category,
                            epistemic_status=ki.epistemic_status,
                            review_status=ki.review_status,
                            support_classification=ki.support_classification,
                            normalised_status=ki.normalised_status,
                            owner_label=ki.person_or_owner_label,
                            structured_payload=_redact_payload(ki.structured_payload or {}),
                            confidence_score=_extract_confidence(ki),
                            is_stale=bool(ki.is_stale),
                            created_at=ki.created_at,
                            updated_at=ki.updated_at,
                            source_observed_at=ki.source_observed_at,
                            eligibility=link.eligibility_status_json or {},
                            verification=verif_summary,
                            provenance=provenance_list,
                            provenance_available=len(provenance_list) > 0,
                        )
                    )
                elif link.link_type == HandoverLinkType.RELATIONSHIP.value and link.relationship_id:
                    rel = rel_map.get(link.relationship_id)
                    if not rel:
                        continue
                    rel_prov = self._build_rel_provenance(
                        rel.evidence_links, evidence_map, inaccessible_evidence_ids
                    )
                    sec_rels.append(
                        HandoverSectionRelationshipResponse(
                            id=rel.id,
                            content_link_id=link.id,
                            relationship_type=rel.relationship_type,
                            source_entity_id=rel.source_entity_id,
                            source_entity_name=(
                                rel.source_entity.canonical_name
                                if rel.source_entity
                                else str(rel.source_entity_id)
                            ),
                            source_entity_type=(
                                rel.source_entity.entity_type if rel.source_entity else "entity"
                            ),
                            target_entity_id=rel.target_entity_id,
                            target_entity_name=(
                                rel.target_entity.canonical_name
                                if rel.target_entity
                                else str(rel.target_entity_id)
                            ),
                            target_entity_type=(
                                rel.target_entity.entity_type if rel.target_entity else "entity"
                            ),
                            verification_status=rel.verification_status,
                            confidence_score=float(rel.confidence_score or 1.0),
                            is_stale=bool(rel.is_stale),
                            reviewed_at=rel.reviewed_at,
                            eligibility=link.eligibility_status_json or {},
                            provenance=rel_prov,
                            provenance_available=len(rel_prov) > 0,
                        )
                    )

            domain_context: dict[str, Any] = {}
            if sec.section_type == HandoverPackageSectionType.PROJECT_OVERVIEW_CONTEXT.value:
                domain_context = overview_ctx
            elif sec.section_type == HandoverPackageSectionType.RESPONSIBILITIES_OWNERSHIP.value:
                domain_context = {
                    "team_members": team_members_ctx,
                    "responsibility_transfers": transfers_ctx,
                }

            sec_unresolved = (
                unresolved_conflict_items
                if sec.section_type == HandoverPackageSectionType.BUGS_BLOCKERS_RISKS.value
                else []
            )
            sec_resolved = (
                resolved_conflict_items
                if sec.section_type == HandoverPackageSectionType.BUGS_BLOCKERS_RISKS.value
                else []
            )
            ep_counts = domain_epistemic.get(
                sec.section_type,
                {
                    "human_verified_included": len(sec_kis),
                    "pending_verification": 0,
                    "rejected": 0,
                    "unresolved_conflicts": 0,
                    "resolved_conflicts": 0,
                    "outdated": 0,
                },
            )

            hydrated_sections.append(
                HandoverSectionDetailResponse(
                    id=sec.id,
                    version_id=sec.version_id,
                    section_type=sec.section_type,
                    section_title=sec.section_title,
                    section_content=redact_secrets(sec.section_content),
                    content_summary=sec.content_summary,
                    section_order=sec.section_order,
                    knowledge_item_count=sec.knowledge_item_count,
                    relationship_count=sec.relationship_count,
                    metadata_json=sec.metadata_json or {},
                    created_at=sec.created_at,
                    updated_at=sec.created_at,
                    content_links=content_links_out,
                    knowledge_items=sec_kis,
                    relationships=sec_rels,
                    unresolved_conflicts=sec_unresolved,
                    resolved_conflicts=sec_resolved,
                    epistemic_breakdown=HandoverDomainEpistemicBreakdown(**ep_counts),
                    domain_context=domain_context,
                )
            )

        # Aggregate project-level epistemic summary across all 8 domains
        summary = HandoverDomainEpistemicBreakdown(
            human_verified_included=sum(d["human_verified_included"] for d in domain_epistemic.values()),
            pending_verification=sum(d["pending_verification"] for d in domain_epistemic.values()),
            rejected=sum(d["rejected"] for d in domain_epistemic.values()),
            unresolved_conflicts=len(unresolved_conflict_items),
            resolved_conflicts=len(resolved_conflict_items),
            outdated=sum(d["outdated"] for d in domain_epistemic.values()),
        )

        version_res = HandoverPackageVersionResponse(
            id=version.id,
            package_id=version.package_id,
            version_number=version.version_number,
            assembly_status=version.assembly_status,
            assembly_notes=version.notes,
            notes=version.notes,
            content_hash=version.content_hash,
            assembly_snapshot_json=version.assembly_snapshot_json,
            assembled_by_user_id=version.assembled_by_user_id,
            assembled_at=version.assembled_at,
            is_current=version.is_current,
            created_at=version.created_at,
        )

        raw_type = role_override or ((case.metadata_json or {}).get("handover_type") if case else None)
        handover_type = normalize_handover_type(raw_type)
        role_cfg = HANDOVER_ROLE_CONFIG[handover_type]
        mandatory_sections = build_mandatory_ten_sections(
            hydrated_sections=hydrated_sections,
            handover_type=handover_type,
            unresolved_conflicts=unresolved_conflict_items,
            resolved_conflicts=resolved_conflict_items,
            team_members_ctx=team_members_ctx,
            transfers_ctx=transfers_ctx,
            checklists=case_checklists,
            domain_context_overview=overview_ctx,
            omit_restricted_items=False,
        )

        return HandoverVersionSectionsResponse(
            case_id=case_id,
            project_id=project_id,
            version=version_res,
            sections=hydrated_sections,
            missing_section_types=missing_types,
            epistemic_summary=summary,
            handover_type=handover_type,
            handover_type_label=role_cfg["label"],
            role_focus_summary=role_cfg["focus_summary"],
            mandatory_sections=mandatory_sections,
        )

    def _build_ki_provenance(
        self,
        links: list[KnowledgeEvidenceLink],
        evidence_map: dict[uuid.UUID, EvidenceItem],
        inaccessible_ids: set[uuid.UUID],
    ) -> list[HandoverEvidenceProvenanceResponse]:
        out: list[HandoverEvidenceProvenanceResponse] = []
        for el in links:
            if el.evidence_id in inaccessible_ids:
                out.append(
                    HandoverEvidenceProvenanceResponse(
                        evidence_id=el.evidence_id,
                        source_type="restricted",
                        source_provider=None,
                        source_name="Restricted Source (Source ACL Protected)",
                        source_reference=None,
                        source_url=None,
                        author=None,
                        source_timestamp=None,
                        extracted_at=None,
                        support_type=el.support_type,
                        supporting_excerpt=None,
                        acl_restricted=True,
                    )
                )
                continue
            ev = evidence_map.get(el.evidence_id)
            if not ev:
                continue
            out.append(
                HandoverEvidenceProvenanceResponse(
                    evidence_id=ev.id,
                    source_type=ev.source_type,
                    source_provider=ev.source_provider,
                    source_name=ev.title or ev.original_filename or ev.source_external_id,
                    source_reference=ev.source_external_id,
                    source_url=ev.source_url,
                    author=ev.source_author_identity,
                    source_timestamp=ev.source_created_at or ev.source_updated_at,
                    extracted_at=ev.extracted_at,
                    support_type=el.support_type,
                    supporting_excerpt=redact_secrets(el.supporting_excerpt),
                    acl_restricted=False,
                )
            )
        return out

    def _build_rel_provenance(
        self,
        links: list[RelationshipEvidenceLink],
        evidence_map: dict[uuid.UUID, EvidenceItem],
        inaccessible_ids: set[uuid.UUID],
    ) -> list[HandoverEvidenceProvenanceResponse]:
        out: list[HandoverEvidenceProvenanceResponse] = []
        for el in links:
            if el.evidence_id in inaccessible_ids:
                out.append(
                    HandoverEvidenceProvenanceResponse(
                        evidence_id=el.evidence_id,
                        source_type="restricted",
                        source_provider=None,
                        source_name="Restricted Source (Source ACL Protected)",
                        source_reference=None,
                        source_url=None,
                        author=None,
                        source_timestamp=None,
                        extracted_at=None,
                        support_type=el.evidence_role,
                        supporting_excerpt=None,
                        acl_restricted=True,
                    )
                )
                continue
            ev = evidence_map.get(el.evidence_id)
            if not ev:
                continue
            out.append(
                HandoverEvidenceProvenanceResponse(
                    evidence_id=ev.id,
                    source_type=ev.source_type,
                    source_provider=ev.source_provider,
                    source_name=ev.title or ev.original_filename or ev.source_external_id,
                    source_reference=ev.source_external_id,
                    source_url=ev.source_url,
                    author=ev.source_author_identity,
                    source_timestamp=ev.source_created_at or ev.source_updated_at,
                    extracted_at=ev.extracted_at,
                    support_type=el.evidence_role,
                    supporting_excerpt=redact_secrets(el.supporting_excerpt) if el.supporting_excerpt else None,
                    acl_restricted=False,
                )
            )
        return out

    def _build_verification_summary(
        self,
        vc: VerificationCase | None,
        user_map: dict[uuid.UUID, User],
    ) -> HandoverVerificationSummaryResponse:
        if not vc:
            return HandoverVerificationSummaryResponse()
        latest_event: VerificationReviewEvent | None = vc.review_events[0] if vc.review_events else None
        reviewer_id = latest_event.reviewer_user_id if latest_event else vc.assigned_reviewer_id
        reviewer = user_map.get(reviewer_id) if reviewer_id else None
        case_status = str(vc.case_status.value if hasattr(vc.case_status, "value") else vc.case_status)
        decision = None
        if latest_event:
            decision = str(
                latest_event.action.value
                if hasattr(latest_event.action, "value")
                else latest_event.action
            )
        return HandoverVerificationSummaryResponse(
            verification_case_id=vc.id,
            case_status=case_status,
            reviewer_decision=decision,
            reviewed_by_user_id=reviewer_id,
            reviewed_by_name=(reviewer.full_name or reviewer.email) if reviewer else None,
            reviewed_at=(latest_event.created_at if latest_event else vc.last_reviewed_at),
            review_notes=(
                redact_secrets(latest_event.review_notes or latest_event.decision_reason)
                if latest_event and (latest_event.review_notes or latest_event.decision_reason)
                else None
            ),
        )
