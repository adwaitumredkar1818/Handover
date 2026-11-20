"""Project Knowledge Quality and Completeness Scoring Engine.

Implements explainable, transparent 9-dimension project knowledge quality analysis:
1. Evidence Coverage (Ratio of project areas supported by raw evidence)
2. Verification Coverage (Ratio of findings reviewed/verified by humans)
3. Decision Traceability (Ratio of decisions with complete 5-stage causal chains)
4. Ownership Coverage (Ratio of components with active maintainers vs unowned)
5. Dependency Clarity (Ratio of dependencies without cycles or unresolved blockers)
6. Documentation Coverage (Ratio of architecture & operational specs documented)
7. Operational Readiness (Ratio of verified runbooks and deploy procedures)
8. Risk Coverage (Ratio of identified risks with mitigation strategies)
9. Knowledge Freshness (Recency decay and staleness evaluation)
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import (
    EpistemicStatus,
    KnowledgeCategory,
    KnowledgeReviewStatus,
    RelationshipVerificationStatus,
    TraceabilityCompletenessStatus,
    VerificationCaseStatus,
)
from app.models.handover import HandoverCase, HandoverResponsibilityTransfer
from app.models.knowledge import KnowledgeEvidenceLink, KnowledgeItem
from app.models.relationship import (
    DecisionTraceabilityChain,
    KnowledgeEntity,
    KnowledgeRelationship,
)
from app.models.verification import (
    VerificationCase,
    VerificationConflict,
    VerificationIssue,
)

logger = logging.getLogger(__name__)


class KnowledgeQualityEngine:
    """Evaluates project-level knowledge quality across 9 explainable dimensions."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def assess_project_quality(
        self,
        *,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        sync_findings: bool = False,
    ) -> dict[str, Any]:
        """Perform comprehensive, real-time 9-dimension knowledge quality assessment."""
        # Synchronize findings if explicitly requested (e.g., on "Refresh Assessment")
        if sync_findings:
            try:
                from app.services.verification_engine import VerificationEngine

                v_engine = VerificationEngine(self.session)
                v_engine.sync_project_findings(project_id)
                self.session.commit()
            except Exception as exc:
                logger.warning(
                    "Failed to synchronize project findings during quality assessment for project %s: %s",
                    project_id,
                    exc,
                )
                self.session.rollback()

        # Query active (non-deleted) knowledge items
        items = (
            self.session.query(KnowledgeItem)
            .filter(
                KnowledgeItem.project_id == project_id,
                KnowledgeItem.is_deleted.is_(False),
            )
            .all()
        )
        total_items = len(items)

        # Query verification cases (findings displayed in the Verification Center)
        cases = (
            self.session.query(VerificationCase)
            .filter(VerificationCase.project_id == project_id)
            .all()
        )
        total_cases = len(cases)

        entities = (
            self.session.query(KnowledgeEntity)
            .filter(KnowledgeEntity.project_id == project_id)
            .all()
        )
        relationships = (
            self.session.query(KnowledgeRelationship)
            .filter(KnowledgeRelationship.project_id == project_id)
            .all()
        )

        issues = (
            self.session.query(VerificationIssue)
            .filter(VerificationIssue.project_id == project_id)
            .all()
        )
        conflicts = (
            self.session.query(VerificationConflict)
            .filter(VerificationConflict.project_id == project_id)
            .all()
        )

        chains = (
            self.session.query(DecisionTraceabilityChain)
            .filter(DecisionTraceabilityChain.project_id == project_id)
            .all()
        )

        transfers = (
            self.session.query(HandoverResponsibilityTransfer)
            .join(HandoverCase, HandoverResponsibilityTransfer.case_id == HandoverCase.id)
            .filter(HandoverCase.project_id == project_id)
            .all()
        )

        evaluated_findings_count = max(total_items, total_cases)

        # ZERO-DATA GUARD: If there are no extracted items or verification cases,
        # report 0.0% overall and 0.0% across all dimensions with an honest gap message.
        if evaluated_findings_count == 0:
            zero_scores = {
                "evidence_coverage": 0.0,
                "verification_coverage": 0.0,
                "decision_traceability": 0.0,
                "ownership_coverage": 0.0,
                "dependency_clarity": 0.0,
                "documentation_coverage": 0.0,
                "operational_readiness": 0.0,
                "risk_coverage": 0.0,
                "knowledge_freshness": 0.0,
            }
            empty_gaps = [
                {
                    "type": "no_extracted_knowledge",
                    "severity": "high",
                    "title": "No Project Knowledge Extracted",
                    "description": (
                        "No extracted project knowledge items or verification findings were found. "
                        "Knowledge quality, provenance grounding, and handover readiness cannot be evaluated without evidence."
                    ),
                    "recommendation": "Connect external sources (GitHub, Jira, Slack) or upload project documents in Evidence Center, then run extraction.",
                }
            ]
            return {
                "project_id": str(project_id),
                "overall_quality_score": 0.0,
                "dimension_scores": zero_scores,
                "total_items": 0,
                "verified_items": 0,
                "stale_items": 0,
                "identified_gaps": empty_gaps,
                "recommendation_count": len(empty_gaps),
            }

        # ── 1. Evidence Coverage (15% weight) ──────────────────────────────────
        # Check active items with cited evidence links or structured source attribution
        linked_item_ids: set[uuid.UUID] = set()
        if total_items > 0:
            stmt_links = (
                select(KnowledgeEvidenceLink.knowledge_item_id)
                .join(KnowledgeItem, KnowledgeEvidenceLink.knowledge_item_id == KnowledgeItem.id)
                .where(KnowledgeItem.project_id == project_id, KnowledgeItem.is_deleted.is_(False))
            )
            linked_item_ids = set(self.session.execute(stmt_links).scalars().all())

        grounded_items_count = sum(
            1
            for i in items
            if i.id in linked_item_ids
            or (bool(i.source_attribution_json) and i.source_attribution_json.get("source_provider"))
        )
        evidence_coverage = (grounded_items_count / total_items) if total_items > 0 else 0.0

        # ── 2. Verification Coverage (15% weight) ──────────────────────────────
        # Proportion of findings reviewed and verified by human auditors
        if total_cases > 0:
            verified_cases = sum(
                1 for c in cases if c.case_status == VerificationCaseStatus.VERIFIED.value
            )
            verification_coverage = verified_cases / total_cases
            verified_items = verified_cases
        elif total_items > 0:
            verified_items = sum(
                1
                for i in items
                if i.review_status == KnowledgeReviewStatus.APPROVED.value
                or i.epistemic_status == EpistemicStatus.HUMAN_VERIFIED.value
            )
            verification_coverage = verified_items / total_items
        else:
            verified_items = 0
            verification_coverage = 0.0

        # ── 3. Decision Traceability (12% weight) ──────────────────────────────
        # 5-stage causal chains linking problem -> decision -> work items -> PRs/commits -> components
        decision_items = [
            i
            for i in items
            if i.category in (KnowledgeCategory.DECISIONS_RATIONALE.value, "decisions_rationale")
            or "decision" in (i.title or "").lower()
        ]
        decision_entities = [e for e in entities if e.entity_type == "decision"]
        total_decisions = max(len(decision_items), len(decision_entities), len(chains))

        complete_chains = sum(
            1
            for c in chains
            if c.completeness_status
            in (
                "complete",
                "verified",
                TraceabilityCompletenessStatus.COMPLETE.value,
            )
            or (
                bool(c.work_item_ids_json)
                and (bool(c.pull_request_ids_json) or bool(c.commit_ids_json))
            )
        )
        traceability_coverage = (complete_chains / total_decisions) if total_decisions > 0 else 0.0

        # ── 4. Ownership Coverage (12% weight) ─────────────────────────────────
        # Technical components mapped to active owners or maintainers
        comp_types = ("component", "technical_component", "repository", "module", "service")
        component_entities = [e for e in entities if e.entity_type in comp_types]
        ownership_items = [
            i
            for i in items
            if i.category in (KnowledgeCategory.RESPONSIBILITIES_OWNERSHIP.value, "responsibilities_ownership")
            or bool(i.person_or_owner_label and i.person_or_owner_label.strip())
        ]
        total_ownership_targets = max(len(component_entities), len(ownership_items))

        owned_components = 0
        for comp in component_entities:
            has_owner = any(
                (r.target_entity_id == comp.id or r.source_entity_id == comp.id)
                and r.relationship_type in ("owned_by", "maintained_by", "assigned_to", "managed_by", "authored_by")
                for r in relationships
            )
            if has_owner:
                owned_components += 1

        owned_items_count = sum(
            1 for i in ownership_items if bool(i.person_or_owner_label and i.person_or_owner_label.strip())
        )
        assigned_transfers = sum(1 for t in transfers if bool(t.proposed_successor_id))

        effective_owned = max(owned_components, owned_items_count, assigned_transfers)
        ownership_coverage = (
            (effective_owned / total_ownership_targets) if total_ownership_targets > 0 else 0.0
        )

        # ── 5. Dependency Clarity (10% weight) ─────────────────────────────────
        # Free of dependency cycles, untracked blockers, and open contradictions
        dep_relationships = [
            r
            for r in relationships
            if r.relationship_type
            in ("depends_on", "blocks", "blocked_by", "imports", "calls", "requires")
        ]
        dep_items = [
            i
            for i in items
            if i.category
            in (
                KnowledgeCategory.DEPENDENCIES.value,
                KnowledgeCategory.DEPENDENCIES_RELATIONSHIPS.value,
                "dependencies",
                "dependencies_relationships",
            )
        ]
        total_deps = len(dep_relationships) + len(dep_items)

        if total_deps == 0:
            dependency_clarity = 0.0
        else:
            conflicting_deps = sum(
                1
                for iss in issues
                if any(
                    k in (iss.issue_type or "").lower()
                    for k in ("cycle", "blocker", "circular", "unresolved")
                )
            )
            open_conflicts = sum(
                1 for c in conflicts if str(c.resolution_state or "").lower() in ("unresolved", "open")
            )
            penalized_count = conflicting_deps + open_conflicts
            clear_deps = max(0, total_deps - penalized_count)
            dependency_clarity = clear_deps / total_deps

        # ── 6. Documentation Coverage (10% weight) ─────────────────────────────
        # Grounded documentation across 5 core canonical domains
        has_arch = any(
            i.category
            in (
                KnowledgeCategory.TECHNICAL_ARCHITECTURE.value,
                KnowledgeCategory.ARCHITECTURE_TECHNICAL.value,
                "technical_architecture",
                "architecture_technical",
            )
            or "architecture" in (i.title or "").lower()
            for i in items
        )
        has_decisions = any(
            i.category in (KnowledgeCategory.DECISIONS_RATIONALE.value, "decisions_rationale")
            or "decision" in (i.title or "").lower()
            for i in items
        )
        has_ops = any(
            i.category in (KnowledgeCategory.OPERATIONAL_HISTORICAL.value, "operational_historical")
            or any(kw in (i.title or "").lower() for kw in ("runbook", "deploy", "setup", "procedure"))
            for i in items
        )
        has_work = any(
            i.category in (KnowledgeCategory.WORK_PROGRESS.value, "work_items", "work_progress")
            or "progress" in (i.title or "").lower()
            for i in items
        )
        has_context = any(
            i.category
            in (KnowledgeCategory.PROJECT_OVERVIEW_CONTEXT.value, "project_overview_context")
            or "overview" in (i.title or "").lower()
            for i in items
        )
        covered_domains = sum(1 for c in (has_arch, has_decisions, has_ops, has_work, has_context) if c)
        documentation_coverage = covered_domains / 5.0

        # ── 7. Operational Readiness (10% weight) ──────────────────────────────
        # Verified runbooks, deployment guides, and operational procedures
        ops_items = [
            i
            for i in items
            if i.category in (KnowledgeCategory.OPERATIONAL_HISTORICAL.value, "operational_historical")
            or any(
                kw in (i.title or "").lower()
                for kw in ("runbook", "deploy", "setup", "procedure", "environment", "incident", "release")
            )
        ]
        if not ops_items:
            operational_readiness = 0.0
        else:
            verified_ops = sum(
                1
                for i in ops_items
                if i.review_status == KnowledgeReviewStatus.APPROVED.value
                or i.epistemic_status == EpistemicStatus.HUMAN_VERIFIED.value
            )
            grounded_ops = sum(
                1
                for i in ops_items
                if i.id in linked_item_ids
                or (bool(i.source_attribution_json) and i.source_attribution_json.get("source_provider"))
            )
            readiness_ratio = (verified_ops * 0.6 + grounded_ops * 0.4) / len(ops_items)
            operational_readiness = min(1.0, max(0.0, readiness_ratio))

        # ── 8. Risk Coverage (8% weight) ───────────────────────────────────────
        # Identified risks and blockers with documented mitigation or resolution
        risk_items = [
            i
            for i in items
            if i.category
            in (
                KnowledgeCategory.BUGS_BLOCKERS_RISKS.value,
                KnowledgeCategory.RISKS_BLOCKERS_QUESTIONS.value,
                "bugs_blockers_risks",
                "risks_blockers_questions",
            )
            or any(kw in (i.title or "").lower() for kw in ("risk", "blocker", "vulnerability", "hazard"))
        ]
        if not risk_items:
            risk_coverage = 0.0
        else:
            mitigated_risks = 0
            for r in risk_items:
                summary_text = (r.structured_summary or "").lower()
                payload = r.structured_payload if isinstance(r.structured_payload, dict) else {}
                payload_status = str(payload.get("status") or "").lower()
                payload_mitigation = str(payload.get("mitigation") or "").lower()
                is_mitigated = (
                    "mitigat" in summary_text
                    or "resolved" in summary_text
                    or "workaround" in summary_text
                    or "mitigat" in payload_mitigation
                    or payload_status in ("resolved", "mitigated", "closed")
                    or r.review_status == KnowledgeReviewStatus.APPROVED.value
                )
                if is_mitigated:
                    mitigated_risks += 1
            risk_coverage = mitigated_risks / len(risk_items)

        # ── 9. Knowledge Freshness (8% weight) ─────────────────────────────────
        # Active knowledge without stale or outdated artifacts
        stale_count = sum(1 for i in items if i.is_stale)
        freshness_score = max(0.0, 1.0 - (stale_count / total_items)) if total_items > 0 else 0.0

        dimension_scores = {
            "evidence_coverage": round(evidence_coverage * 100, 1),
            "verification_coverage": round(verification_coverage * 100, 1),
            "decision_traceability": round(traceability_coverage * 100, 1),
            "ownership_coverage": round(ownership_coverage * 100, 1),
            "dependency_clarity": round(dependency_clarity * 100, 1),
            "documentation_coverage": round(documentation_coverage * 100, 1),
            "operational_readiness": round(operational_readiness * 100, 1),
            "risk_coverage": round(risk_coverage * 100, 1),
            "knowledge_freshness": round(freshness_score * 100, 1),
        }

        weights = {
            "evidence_coverage": 0.15,
            "verification_coverage": 0.15,
            "decision_traceability": 0.12,
            "ownership_coverage": 0.12,
            "dependency_clarity": 0.10,
            "documentation_coverage": 0.10,
            "operational_readiness": 0.10,
            "risk_coverage": 0.08,
            "knowledge_freshness": 0.08,
        }
        overall_score = sum(dimension_scores[k] * weights[k] for k in weights)

        # Detect Actionable Knowledge Gaps grounded in real metrics
        gaps: list[dict[str, str]] = []
        if verification_coverage < 0.5:
            pct = dimension_scores["verification_coverage"]
            gaps.append({
                "type": "unverified_knowledge",
                "severity": "high",
                "title": "Low Human Verification Coverage",
                "description": f"Only {pct}% of extracted items/findings have been verified by an auditor.",
                "recommendation": "Review pending candidate findings in Verification Center.",
            })

        if ownership_coverage < 0.7:
            gaps.append({
                "type": "unowned_components",
                "severity": "high",
                "title": "Unowned Technical Components Detected",
                "description": f"Ownership coverage is {dimension_scores['ownership_coverage']}%. Several technical components have no designated owner.",
                "recommendation": "Map outgoing developers to incoming successors in Handover.",
            })

        if operational_readiness < 0.5:
            gaps.append({
                "type": "missing_runbook",
                "severity": "medium",
                "title": "Incomplete Operational Runbooks",
                "description": "Deployment, setup, or incident runbook documentation is missing or unverified.",
                "recommendation": "Upload deployment instructions to Evidence Workspace and verify them.",
            })

        if traceability_coverage < 0.6:
            gaps.append({
                "type": "untraced_decisions",
                "severity": "medium",
                "title": "Low Decision Traceability",
                "description": f"Only {dimension_scores['decision_traceability']}% of project decisions have complete causal chains linking work items and commits.",
                "recommendation": "Link pull requests and commits to key architectural decisions in Relationship Explorer.",
            })

        if stale_count > 0:
            gaps.append({
                "type": "stale_knowledge",
                "severity": "low",
                "title": "Stale Evidence Present",
                "description": f"{stale_count} item(s) are flagged as potentially outdated.",
                "recommendation": "Sync latest GitHub commits or Jira tickets to refresh.",
            })

        if conflicts:
            open_confs = sum(
                1 for c in conflicts if str(c.resolution_state or "").lower() in ("unresolved", "open")
            )
            if open_confs > 0:
                gaps.append({
                    "type": "open_conflicts",
                    "severity": "high",
                    "title": "Unresolved Contradictions Detected",
                    "description": f"{open_confs} conflicting claims across sources remain unresolved.",
                    "recommendation": "Resolve source contradictions in Conflict Management.",
                })

        return {
            "project_id": str(project_id),
            "overall_quality_score": round(overall_score, 1),
            "dimension_scores": dimension_scores,
            "total_items": evaluated_findings_count,
            "verified_items": verified_items,
            "stale_items": stale_count,
            "identified_gaps": gaps,
            "recommendation_count": len(gaps),
        }
