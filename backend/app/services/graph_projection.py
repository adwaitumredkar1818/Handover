"""Graph Projection Service for Relationship Explorer.

Produces frontend-ready React Flow node and edge structures with:
- Bounded depth BFS/DFS traversal
- Source-ACL fail-closed edge and node pruning
- Node side-panel detail aggregation
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Session

from app.core.cache.local_cache import local_response_cache
from app.models.enums import EntityType, EvidenceProcessingStatus
from app.models.evidence import EvidenceItem
from app.models.relationship import (
    KnowledgeEntity,
    KnowledgeRelationship,
    KnowledgeTimelineEvent,
    RelationshipEvidenceLink,
)
from app.repositories.relationship import (
    EntityRepository,
    RelationshipRepository,
    _build_accessible_evidence_clause,
)
from app.schemas.relationship import (
    GraphEdgeProjection,
    GraphNodeProjection,
    GraphProjectionResponse,
    KnowledgeEntityResponse,
    KnowledgeRelationshipResponse,
    NodeDetailResponse,
)
from app.services.relationship_taxonomy import get_display_label

logger = logging.getLogger("app.services.graph_projection")


class GraphProjectionService:
    """Projects relational PostgreSQL knowledge graph records into frontend React Flow format."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._entity_repo = EntityRepository(session)
        self._rel_repo = RelationshipRepository(session)

    def project_graph(
        self,
        *,
        project_id: uuid.UUID,
        viewer_user_id: uuid.UUID,
        has_project_manage: bool,
        center_node_id: uuid.UUID | None = None,
        depth: int = 2,
        entity_type_filter: str | None = None,
        verification_status_filter: str | None = None,
        limit_nodes: int = 250,
        limit_edges: int = 500,
    ) -> GraphProjectionResponse:
        """Generate a React Flow-compatible projection of the accessible project knowledge graph."""
        bind_id = id(self._session.get_bind())
        cache_key = (
            f"rel_graph:{project_id}:{bind_id}:{viewer_user_id}:{int(has_project_manage)}:"
            f"{center_node_id or ''}:{depth}:{entity_type_filter or ''}:"
            f"{verification_status_filter or ''}:{limit_nodes}:{limit_edges}"
        )
        cached = local_response_cache.get(cache_key)
        if cached is not None:
            try:
                return GraphProjectionResponse.model_validate(cached)
            except Exception:
                local_response_cache.delete(cache_key)

        acl_clause = _build_accessible_evidence_clause(
            self._session,
            project_id=project_id,
            viewer_user_id=viewer_user_id,
            has_project_manage=has_project_manage,
        )

        # Single grouped query yields caller-accessible relationships + accessible evidence counts
        # without duplicating KnowledgeEntity rows or downloading RelationshipEvidenceLink excerpts.
        rel_filters: list[Any] = [
            KnowledgeRelationship.project_id == project_id,
            acl_clause,
            EvidenceItem.deleted_at.is_(None),
            EvidenceItem.processing_status != EvidenceProcessingStatus.DELETED.value,
        ]
        if verification_status_filter:
            rel_filters.append(
                KnowledgeRelationship.verification_status == verification_status_filter
            )
        rel_rows = list(
            self._session.execute(
                select(
                    KnowledgeRelationship.id,
                    KnowledgeRelationship.source_entity_id,
                    KnowledgeRelationship.target_entity_id,
                    KnowledgeRelationship.relationship_type,
                    KnowledgeRelationship.relationship_basis,
                    KnowledgeRelationship.verification_status,
                    KnowledgeRelationship.confidence_score,
                    KnowledgeRelationship.is_bidirectional_display,
                    func.count(RelationshipEvidenceLink.id).label("evidence_count"),
                )
                .join(
                    RelationshipEvidenceLink,
                    RelationshipEvidenceLink.relationship_id == KnowledgeRelationship.id,
                )
                .join(
                    EvidenceItem,
                    EvidenceItem.id == RelationshipEvidenceLink.evidence_id,
                )
                .where(*rel_filters)
                .group_by(
                    KnowledgeRelationship.id,
                    KnowledgeRelationship.source_entity_id,
                    KnowledgeRelationship.target_entity_id,
                    KnowledgeRelationship.relationship_type,
                    KnowledgeRelationship.relationship_basis,
                    KnowledgeRelationship.verification_status,
                    KnowledgeRelationship.confidence_score,
                    KnowledgeRelationship.is_bidirectional_display,
                    KnowledgeRelationship.created_at,
                )
                .order_by(KnowledgeRelationship.created_at.desc())
                .limit(limit_edges)
            ).all()
        )

        ep_ids: set[uuid.UUID] = set()
        for r in rel_rows:
            ep_ids.add(r.source_entity_id)
            ep_ids.add(r.target_entity_id)

        ep_by_id: dict[uuid.UUID, KnowledgeEntity] = {}
        if ep_ids:
            ep_id_list = list(ep_ids)
            for idx in range(0, len(ep_id_list), 500):
                chunk = ep_id_list[idx : idx + 500]
                stmt = select(KnowledgeEntity).where(
                    KnowledgeEntity.id.in_(chunk),
                    KnowledgeEntity.project_id == project_id,
                    KnowledgeEntity.is_deleted.is_(False),
                )
                if entity_type_filter:
                    stmt = stmt.where(KnowledgeEntity.entity_type == entity_type_filter)
                for ent in self._session.execute(stmt).scalars().all():
                    ep_by_id[ent.id] = ent

        # Preserve endpoint encounter order from relationships so limit_nodes never drops edges
        entity_map: dict[uuid.UUID, KnowledgeEntity] = {}
        rel_endpoints: list[KnowledgeEntity] = []
        seen_ep_ids: set[uuid.UUID] = set()
        for r in rel_rows:
            for eid in (r.source_entity_id, r.target_entity_id):
                endpoint = ep_by_id.get(eid)
                if endpoint is None or endpoint.id in seen_ep_ids:
                    continue
                seen_ep_ids.add(endpoint.id)
                rel_endpoints.append(endpoint)

        allowed_ep_ev_ids: set[uuid.UUID] = set()
        cand_ep_ev_ids = list({e.primary_evidence_id for e in rel_endpoints if e.primary_evidence_id})
        if cand_ep_ev_ids:
            for idx in range(0, len(cand_ep_ev_ids), 500):
                ev_chunk = cand_ep_ev_ids[idx : idx + 500]
                allowed_ep_ev_ids.update(
                    self._session.execute(
                        select(EvidenceItem.id).where(
                            EvidenceItem.id.in_(ev_chunk),
                            acl_clause,
                            EvidenceItem.deleted_at.is_(None),
                            EvidenceItem.processing_status != EvidenceProcessingStatus.DELETED.value,
                        )
                    )
                    .scalars()
                    .all()
                )

        for endpoint in rel_endpoints:
            if len(entity_map) >= limit_nodes:
                break
            if (
                endpoint.primary_evidence_id is not None
                and endpoint.primary_evidence_id not in allowed_ep_ev_ids
            ):
                continue
            entity_map[endpoint.id] = endpoint

        # Fill remaining node capacity up to limit_nodes without selectinload(aliases) overhead
        if len(entity_map) < limit_nodes:
            extra_filters: list[Any] = [
                KnowledgeEntity.project_id == project_id,
                KnowledgeEntity.is_deleted.is_(False),
            ]
            if seen_ep_ids:
                extra_filters.append(KnowledgeEntity.id.notin_(list(seen_ep_ids)))
            if entity_type_filter:
                extra_filters.append(KnowledgeEntity.entity_type == entity_type_filter)
            accessible_ev_exists = exists(
                select(EvidenceItem.id).where(
                    EvidenceItem.id == KnowledgeEntity.primary_evidence_id,
                    acl_clause,
                    EvidenceItem.deleted_at.is_(None),
                    EvidenceItem.processing_status != EvidenceProcessingStatus.DELETED.value,
                )
            )
            extra_filters.append(
                or_(
                    KnowledgeEntity.primary_evidence_id.is_(None),
                    accessible_ev_exists,
                )
            )
            extra_entities = list(
                self._session.execute(
                    select(KnowledgeEntity)
                    .where(and_(*extra_filters))
                    .order_by(KnowledgeEntity.canonical_name.asc())
                    .limit(limit_nodes - len(entity_map))
                )
                .scalars()
                .all()
            )
            for ent in extra_entities:
                if ent.id not in entity_map:
                    entity_map[ent.id] = ent
                    if len(entity_map) >= limit_nodes:
                        break

        # If center_node_id is specified, compute BFS neighborhood up to `depth`
        if center_node_id is not None and center_node_id in entity_map:
            adj: dict[uuid.UUID, set[uuid.UUID]] = {e_id: set() for e_id in entity_map}
            for r in rel_rows:
                if r.source_entity_id in adj and r.target_entity_id in adj:
                    adj[r.source_entity_id].add(r.target_entity_id)
                    adj[r.target_entity_id].add(r.source_entity_id)

            visited: set[uuid.UUID] = {center_node_id}
            queue: list[tuple[uuid.UUID, int]] = [(center_node_id, 0)]
            while queue:
                curr, d = queue.pop(0)
                if d >= depth:
                    continue
                for neighbor in adj.get(curr, set()):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append((neighbor, d + 1))

            # Restrict entities and relationships to visited set
            entity_map = {e_id: ent for e_id, ent in entity_map.items() if e_id in visited}
            rel_rows = [
                r
                for r in rel_rows
                if r.source_entity_id in visited and r.target_entity_id in visited
            ]

        # Build GraphNodeProjections
        nodes: list[GraphNodeProjection] = []
        for ent in entity_map.values():
            nodes.append(
                GraphNodeProjection(
                    id=str(ent.id),
                    entity_id=ent.id,
                    label=ent.canonical_name,
                    description=ent.description,
                    entity_type=ent.entity_type,
                    status=ent.resolution_status,
                    source_provider=ent.source_provider,
                    verification_status=ent.resolution_status,
                    confidence=float(ent.confidence_score),
                    metadata=ent.metadata_json or {},
                )
            )

        # Build GraphEdgeProjections
        edges: list[GraphEdgeProjection] = []
        for r in rel_rows:
            # Ensure both endpoints exist in projected nodes
            if r.source_entity_id not in entity_map or r.target_entity_id not in entity_map:
                continue

            ev_count = int(r.evidence_count or 0)
            edges.append(
                GraphEdgeProjection(
                    id=str(r.id),
                    relationship_id=r.id,
                    source=str(r.source_entity_id),
                    target=str(r.target_entity_id),
                    relationship_type=r.relationship_type,
                    label=get_display_label(r.relationship_type),
                    relationship_basis=r.relationship_basis,
                    verification_status=r.verification_status,
                    confidence=float(r.confidence_score),
                    evidence_count=ev_count,
                    source_provider=None,
                    supporting_evidence_available=ev_count > 0,
                    is_bidirectional=r.is_bidirectional_display,
                )
            )

        resp = GraphProjectionResponse(
            nodes=nodes,
            edges=edges,
            total_nodes=len(nodes),
            total_edges=len(edges),
            is_truncated=len(nodes) >= limit_nodes or len(edges) >= limit_edges,
            center_node_id=str(center_node_id) if center_node_id else None,
            depth=depth,
        )
        local_response_cache.set(cache_key, resp.model_dump(mode="json"), ttl_seconds=60)
        return resp

    def get_node_details(
        self,
        *,
        project_id: uuid.UUID,
        entity_id: uuid.UUID,
        viewer_user_id: uuid.UUID,
        has_project_manage: bool,
    ) -> NodeDetailResponse:
        """Fetch complete detailed metadata, adjacent relationships, and related entities for a node."""
        entity, denied = self._entity_repo.get_accessible_entity(
            entity_id,
            project_id=project_id,
            viewer_user_id=viewer_user_id,
            has_project_manage=has_project_manage,
        )
        if entity is None or denied:
            raise PermissionError("Access denied or entity not found.")

        # Adjacent relationships
        rels, _ = self._rel_repo.list_accessible_relationships(
            project_id=project_id,
            viewer_user_id=viewer_user_id,
            has_project_manage=has_project_manage,
            entity_id=entity_id,
            limit=100,
        )

        incoming: list[KnowledgeRelationshipResponse] = []
        outgoing: list[KnowledgeRelationshipResponse] = []
        decisions: list[str] = []
        work_items: list[str] = []
        components: list[str] = []
        evidence_count = 0

        for r in rels:
            evidence_count += len(r.evidence_links)
            r_schema = KnowledgeRelationshipResponse.model_validate(r)
            if r.target_entity_id == entity_id:
                incoming.append(r_schema)
                other = r.source_entity
            else:
                outgoing.append(r_schema)
                other = r.target_entity

            if other:
                if other.entity_type == EntityType.DECISION.value:
                    decisions.append(other.canonical_name)
                elif other.entity_type == EntityType.WORK_ITEM.value:
                    work_items.append(other.canonical_name)
                elif other.entity_type == EntityType.COMPONENT.value:
                    components.append(other.canonical_name)

        # Timeline event count
        timeline_count = (
            self._session.execute(
                select(KnowledgeTimelineEvent.id).where(
                    KnowledgeTimelineEvent.project_id == project_id,
                    KnowledgeTimelineEvent.entity_id == entity_id,
                )
            )
            .scalars()
            .all()
        )

        return NodeDetailResponse(
            entity=KnowledgeEntityResponse.model_validate(entity),
            incoming_edges=incoming,
            outgoing_edges=outgoing,
            supporting_evidence_count=evidence_count,
            related_decisions=sorted(list(set(decisions))),
            related_work_items=sorted(list(set(work_items))),
            related_components=sorted(list(set(components))),
            timeline_events_count=len(timeline_count),
        )
