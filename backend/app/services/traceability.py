"""Decision Traceability Service for Relationship Explorer.

Reconstructs and indexes 5-stage Decision-to-Implementation chains:
Decision ──▶ Work Item ──▶ Pull Request ──▶ Commit ──▶ Component

Classifies completeness:
- COMPLETE: All stages connected with verifiable evidence
- PARTIALLY_TRACED: Some stages connected, with explicit missing link annotations
- UNTRACED: Decision has no linked work items or code delivery artefacts
- CONFLICTING: Conflicting architectural choices or rejected links
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import (
    EntityType,
    TraceabilityCompletenessStatus,
)
from app.models.relationship import (
    DecisionTraceabilityChain,
    KnowledgeEntity,
    KnowledgeRelationship,
)
from app.repositories.relationship import TraceabilityRepository

logger = logging.getLogger("app.services.traceability")


@dataclass(frozen=True, slots=True)
class TraceabilityChainAnalysis:
    """Evaluated 5-stage traceability chain for a decision entity."""

    decision_entity_id: uuid.UUID
    completeness_status: str
    work_item_ids: list[str]
    pull_request_ids: list[str]
    commit_ids: list[str]
    component_ids: list[str]
    relationship_ids: list[str]
    missing_links: list[str]
    uncertainty_reasons: list[str]
    aggregate_confidence: float


class DecisionTraceabilityService:
    """Walks the knowledge graph from decisions down to code commits and components."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._trace_repo = TraceabilityRepository(session)

    def _compute_chain_analysis(
        self,
        decision_entity: KnowledgeEntity,
        rels_by_entity: dict[uuid.UUID, list[KnowledgeRelationship]],
        entities_by_id: dict[uuid.UUID, KnowledgeEntity],
    ) -> TraceabilityChainAnalysis:
        """Traverse 5 traceability stages strictly from preloaded adjacency maps."""
        decision_id = decision_entity.id
        work_item_ids: set[str] = set()
        pr_ids: set[str] = set()
        commit_ids: set[str] = set()
        component_ids: set[str] = set()
        relationship_ids: set[str] = set()
        confidences: list[float] = [float(decision_entity.confidence_score)]

        for rel in rels_by_entity.get(decision_id, []):
            relationship_ids.add(str(rel.id))
            confidences.append(float(rel.confidence_score))
            other_id = rel.target_entity_id if rel.source_entity_id == decision_id else rel.source_entity_id
            other_entity = entities_by_id.get(other_id)
            if not other_entity or other_entity.is_deleted:
                continue
            if other_entity.entity_type == EntityType.WORK_ITEM.value:
                work_item_ids.add(str(other_entity.id))
            elif other_entity.entity_type == EntityType.PULL_REQUEST.value:
                pr_ids.add(str(other_entity.id))
            elif other_entity.entity_type == EntityType.COMPONENT.value:
                component_ids.add(str(other_entity.id))

        for wi_id_str in list(work_item_ids):
            wi_uuid = uuid.UUID(wi_id_str)
            for rel in rels_by_entity.get(wi_uuid, []):
                other_id = rel.target_entity_id if rel.source_entity_id == wi_uuid else rel.source_entity_id
                other_entity = entities_by_id.get(other_id)
                if not other_entity or other_entity.is_deleted:
                    continue
                if other_entity.entity_type == EntityType.PULL_REQUEST.value:
                    pr_ids.add(str(other_entity.id))
                    relationship_ids.add(str(rel.id))
                    confidences.append(float(rel.confidence_score))
                elif other_entity.entity_type == EntityType.COMMIT.value:
                    commit_ids.add(str(other_entity.id))
                    relationship_ids.add(str(rel.id))
                    confidences.append(float(rel.confidence_score))
                elif other_entity.entity_type == EntityType.COMPONENT.value:
                    component_ids.add(str(other_entity.id))

        for pr_id_str in list(pr_ids):
            pr_uuid = uuid.UUID(pr_id_str)
            for rel in rels_by_entity.get(pr_uuid, []):
                other_id = rel.target_entity_id if rel.source_entity_id == pr_uuid else rel.source_entity_id
                other_entity = entities_by_id.get(other_id)
                if not other_entity or other_entity.is_deleted:
                    continue
                if other_entity.entity_type == EntityType.COMMIT.value:
                    commit_ids.add(str(other_entity.id))
                    relationship_ids.add(str(rel.id))
                    confidences.append(float(rel.confidence_score))
                elif other_entity.entity_type == EntityType.COMPONENT.value:
                    component_ids.add(str(other_entity.id))
                    relationship_ids.add(str(rel.id))
                    confidences.append(float(rel.confidence_score))

        missing_links: list[str] = []
        uncertainty: list[str] = []
        if not work_item_ids:
            missing_links.append("Missing tracked Work Item / Jira issue")
            uncertainty.append("No Jira issue or task explicitly links to this decision.")
        if not pr_ids:
            missing_links.append("Missing Pull Request")
            uncertainty.append("No GitHub PR has been identified implementing this decision.")
        if not commit_ids:
            missing_links.append("Missing Commit")
            uncertainty.append("No specific commit hash is directly linked.")
        if not component_ids:
            missing_links.append("Missing Component attribution")
            uncertainty.append("Target component or repository is not formally tagged.")

        if not work_item_ids and not pr_ids and not commit_ids:
            status = TraceabilityCompletenessStatus.UNTRACED.value
        elif len(missing_links) == 0:
            status = TraceabilityCompletenessStatus.COMPLETE.value
        else:
            status = TraceabilityCompletenessStatus.PARTIALLY_TRACED.value

        agg_conf = sum(confidences) / len(confidences) if confidences else 1.0
        return TraceabilityChainAnalysis(
            decision_entity_id=decision_id,
            completeness_status=status,
            work_item_ids=sorted(list(work_item_ids)),
            pull_request_ids=sorted(list(pr_ids)),
            commit_ids=sorted(list(commit_ids)),
            component_ids=sorted(list(component_ids)),
            relationship_ids=sorted(list(relationship_ids)),
            missing_links=missing_links,
            uncertainty_reasons=uncertainty,
            aggregate_confidence=round(agg_conf, 3),
        )

    def _preload_project_graph(
        self, project_id: uuid.UUID
    ) -> tuple[dict[uuid.UUID, KnowledgeEntity], dict[uuid.UUID, list[KnowledgeRelationship]]]:
        from app.repositories.relationship import EntityRepository, RelationshipRepository

        _, entities_by_id = EntityRepository(self._session)._project_entities(project_id)
        rels_by_fp = RelationshipRepository(self._session)._project_relationships(project_id)
        rels_by_entity: dict[uuid.UUID, list[KnowledgeRelationship]] = {}
        for rel in rels_by_fp.values():
            rels_by_entity.setdefault(rel.source_entity_id, []).append(rel)
            rels_by_entity.setdefault(rel.target_entity_id, []).append(rel)
        return entities_by_id, rels_by_entity

    def analyze_decision_traceability(
        self,
        decision_entity: KnowledgeEntity,
    ) -> TraceabilityChainAnalysis:
        """Trace a decision down through the 5 stages and evaluate completeness."""
        entities_by_id, rels_by_entity = self._preload_project_graph(decision_entity.project_id)
        return self._compute_chain_analysis(decision_entity, rels_by_entity, entities_by_id)

    def index_project_traceability(
        self,
        *,
        organisation_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> list[DecisionTraceabilityChain]:
        """Compute and persist traceability chains for all decisions in a project."""
        entities_by_id, rels_by_entity = self._preload_project_graph(project_id)
        decisions = [
            e for e in entities_by_id.values() if e.entity_type == EntityType.DECISION.value
        ]
        existing_chains = {
            c.decision_entity_id: c
            for c in self._session.execute(
                select(DecisionTraceabilityChain).where(
                    DecisionTraceabilityChain.project_id == project_id
                )
            )
            .scalars()
            .all()
        }

        chains: list[DecisionTraceabilityChain] = []
        for dec in decisions:
            analysis = self._compute_chain_analysis(dec, rels_by_entity, entities_by_id)
            chain = existing_chains.get(analysis.decision_entity_id)
            if chain is not None:
                chain.completeness_status = analysis.completeness_status
                chain.work_item_ids_json = analysis.work_item_ids
                chain.pull_request_ids_json = analysis.pull_request_ids
                chain.commit_ids_json = analysis.commit_ids
                chain.component_ids_json = analysis.component_ids
                chain.relationship_ids_json = analysis.relationship_ids
                chain.missing_links_json = analysis.missing_links
                chain.uncertainty_reasons_json = analysis.uncertainty_reasons
                chain.aggregate_confidence = analysis.aggregate_confidence
            else:
                chain = self._trace_repo.create_or_update_chain(
                    organisation_id=organisation_id,
                    project_id=project_id,
                    decision_entity_id=analysis.decision_entity_id,
                    completeness_status=analysis.completeness_status,
                    work_item_ids_json=analysis.work_item_ids,
                    pull_request_ids_json=analysis.pull_request_ids,
                    commit_ids_json=analysis.commit_ids,
                    component_ids_json=analysis.component_ids,
                    relationship_ids_json=analysis.relationship_ids,
                    missing_links_json=analysis.missing_links,
                    uncertainty_reasons_json=analysis.uncertainty_reasons,
                    aggregate_confidence=analysis.aggregate_confidence,
                )
                existing_chains[analysis.decision_entity_id] = chain
            chains.append(chain)

        self._session.flush()
        return chains
