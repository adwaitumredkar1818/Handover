"""Knowledge Intelligence Graph Projection Service (Technology Stack, System Architecture, Features & Workflows).

Builds bounded, deterministic, strictly source-ACL-filtered projections directly from
persisted PostgreSQL canonical entities, relationships, knowledge items, and evidence links.
Never triggers LLM inference during graph browsing.
"""

from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from collections.abc import Iterable
from typing import Literal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.cache.local_cache import local_response_cache
from app.models.enums import EntityType, EpistemicStatus, RelationshipBasis
from app.models.evidence import EvidenceItem
from app.models.knowledge import KnowledgeEvidenceLink, KnowledgeItem
from app.models.relationship import (
    EntityAlias,
    KnowledgeEntity,
    KnowledgeRelationship,
    RelationshipEvidenceLink,
)
from app.repositories.relationship import _build_accessible_evidence_clause
from app.schemas.knowledge_intelligence import (
    KnowledgeGraphEdge,
    KnowledgeGraphEvidenceRef,
    KnowledgeGraphNode,
    KnowledgeGraphNodeDetailResponse,
    KnowledgeGraphProjectionResponse,
    KnowledgeGraphSummary,
)
from app.services.rbac import ProjectContext
from app.services.relationship_taxonomy import get_display_label

GraphKind = Literal["technology-stack", "system-architecture", "features-workflows"]

_GRAPH_ALLOWED_ENTITY_TYPES: dict[str, set[str]] = {
    "technology-stack": {
        EntityType.PROJECT.value,
        EntityType.TECHNOLOGY.value,
        EntityType.FRAMEWORK.value,
        EntityType.LIBRARY.value,
        EntityType.DATABASE.value,
        EntityType.TECHNICAL_COMPONENT.value,
        EntityType.ARCHITECTURE_COMPONENT.value,
        EntityType.DOCUMENT.value,
    },
    "system-architecture": {
        EntityType.PROJECT.value,
        EntityType.ARCHITECTURE_COMPONENT.value,
        EntityType.TECHNICAL_COMPONENT.value,
        EntityType.COMPONENT.value,
        EntityType.SERVICE.value,
        EntityType.API.value,
        EntityType.DATABASE.value,
        EntityType.TECHNOLOGY.value,
    },
    "features-workflows": {
        EntityType.FEATURE.value,
        EntityType.REQUIREMENT.value,
        EntityType.OPERATIONAL_PROCEDURE.value,
        EntityType.TECHNICAL_COMPONENT.value,
        EntityType.ARCHITECTURE_COMPONENT.value,
        EntityType.PULL_REQUEST.value,
        EntityType.COMMIT.value,
        EntityType.WORK_ITEM.value,
    },
}


def _chunked(items: Iterable[uuid.UUID], size: int = 500) -> list[list[uuid.UUID]]:
    seq = list(items)
    return [seq[i : i + size] for i in range(0, len(seq), size)]


class KnowledgeGraphProjectionService:
    """Projects canonical PostgreSQL knowledge entities/relationships into 3 KI graph modes."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def _get_accessible_evidence_ids(
        self,
        *,
        project_id: uuid.UUID,
        viewer_user_id: uuid.UUID,
        has_project_manage: bool,
        source_type: str | None = None,
    ) -> set[uuid.UUID]:
        clause = _build_accessible_evidence_clause(
            self._session,
            project_id=project_id,
            viewer_user_id=viewer_user_id,
            has_project_manage=has_project_manage,
        )
        stmt = select(EvidenceItem.id).where(
            EvidenceItem.project_id == project_id,
            EvidenceItem.deleted_at.is_(None),
            clause,
        )
        if source_type:
            stmt = stmt.where(EvidenceItem.source_type == source_type)
        return set(self._session.execute(stmt).scalars().all())

    def _get_accessible_evidence_map(
        self,
        *,
        project_id: uuid.UUID,
        viewer_user_id: uuid.UUID,
        has_project_manage: bool,
        source_type: str | None = None,
        evidence_ids: Iterable[uuid.UUID] | None = None,
    ) -> dict[uuid.UUID, EvidenceItem]:
        id_list = list(evidence_ids) if evidence_ids is not None else None
        if id_list is not None and not id_list:
            return {}
        clause = _build_accessible_evidence_clause(
            self._session,
            project_id=project_id,
            viewer_user_id=viewer_user_id,
            has_project_manage=has_project_manage,
        )
        base_stmt = select(EvidenceItem).where(
            EvidenceItem.project_id == project_id,
            EvidenceItem.deleted_at.is_(None),
            clause,
        )
        if source_type:
            base_stmt = base_stmt.where(EvidenceItem.source_type == source_type)
        if id_list is None:
            items = list(self._session.execute(base_stmt).scalars().all())
        else:
            items = []
            for chunk in _chunked(id_list):
                items.extend(self._session.execute(base_stmt.where(EvidenceItem.id.in_(chunk))).scalars().all())
        return {ev.id: ev for ev in items}

    def _to_graph_node(
        self,
        ent: KnowledgeEntity,
        *,
        graph_type: str,
        accessible_ev_ids: list[uuid.UUID],
        knowledge_item: KnowledgeItem | None = None,
        ki_status: tuple[str, str] | None = None,
        aliases: list[str] | None = None,
    ) -> KnowledgeGraphNode:
        meta = dict(ent.metadata_json or {})
        review_status = (
            knowledge_item.review_status
            if knowledge_item is not None
            else (ki_status[0] if ki_status is not None else None)
        )
        epistemic_status = (
            knowledge_item.epistemic_status
            if knowledge_item is not None
            else (ki_status[1] if ki_status is not None else None)
        )
        ver_status = (
            review_status
            if review_status is not None
            else str(meta.get("verification_status") or ent.resolution_status or "pending")
        )
        if graph_type == "technology-stack":
            cat = str(meta.get("technology_category") or ent.entity_type)
            status = str(meta.get("usage_basis") or "documented")
        elif graph_type == "system-architecture":
            cat = str(meta.get("layer") or ent.entity_type)
            status = str(meta.get("implementation_basis") or "documented_only")
        else:
            cat = str(meta.get("work_category") or ent.entity_type)
            status = str(meta.get("feature_status") or meta.get("normalised_status") or "PLANNED")

        if epistemic_status == EpistemicStatus.HUMAN_VERIFIED.value:
            ver_status = "approved"
            if graph_type == "system-architecture":
                status = "verified_implementation"
            elif graph_type == "features-workflows" and ent.entity_type == EntityType.FEATURE.value:
                status = "HUMAN_VERIFIED"

        node_aliases = (
            aliases
            if aliases is not None
            else [a.alias_value for a in (ent.aliases or [])]
        )

        return KnowledgeGraphNode(
            id=ent.id,
            entity_type=ent.entity_type,
            label=ent.canonical_name,
            description=ent.description,
            category=cat,
            status=status,
            verification_status=ver_status,
            evidence_count=len(accessible_ev_ids),
            evidence_ids=accessible_ev_ids,
            aliases=node_aliases,
            last_observed_at=ent.last_observed_at or ent.updated_at,
            metadata=meta,
        )

    def get_graph(
        self,
        *,
        project_ctx: ProjectContext,
        graph_type: GraphKind,
        search: str | None = None,
        status: str | None = None,
        source_type: str | None = None,
        verification_state: str | None = None,
        limit: int = 150,
        cursor: str | None = None,
        include_suggested: bool = True,
    ) -> KnowledgeGraphProjectionResponse:
        project_id = project_ctx.project.id
        viewer_id = project_ctx.principal.user_id
        has_manage = project_ctx.has_permission("project.manage")
        bind = self._session.get_bind()
        cache_key = (
            f"ki_graph:{project_id}:{id(bind)}:{viewer_id}:{int(has_manage)}:"
            f"{graph_type}:{search or ''}:{status or ''}:{source_type or ''}:"
            f"{verification_state or ''}:{limit}:{cursor or ''}:{int(include_suggested)}"
        )
        cached = local_response_cache.get(cache_key)
        if cached is not None:
            try:
                return KnowledgeGraphProjectionResponse.model_validate(cached)
            except Exception:
                local_response_cache.delete(cache_key)

        accessible_ev_set = self._get_accessible_evidence_ids(
            project_id=project_id,
            viewer_user_id=viewer_id,
            has_project_manage=has_manage,
            source_type=source_type,
        )
        if not accessible_ev_set:
            return KnowledgeGraphProjectionResponse(
                graph_type=graph_type,
                project_id=project_id,
                nodes=[],
                edges=[],
                summary=KnowledgeGraphSummary(node_count=0, edge_count=0, categories={}),
                next_cursor=None,
            )

        allowed_types = _GRAPH_ALLOWED_ENTITY_TYPES[graph_type]
        entities = list(
            self._session.execute(
                select(KnowledgeEntity).where(
                    KnowledgeEntity.project_id == project_id,
                    KnowledgeEntity.is_deleted.is_(False),
                    KnowledgeEntity.is_stale.is_(False),
                    KnowledgeEntity.entity_type.in_(allowed_types),
                )
            )
            .scalars()
            .all()
        )
        if not entities:
            return KnowledgeGraphProjectionResponse(
                graph_type=graph_type,
                project_id=project_id,
                nodes=[],
                edges=[],
                summary=KnowledgeGraphSummary(node_count=0, edge_count=0, categories={}),
                next_cursor=None,
            )

        ent_ids = {e.id for e in entities}

        # Load aliases only for the scoped graph entities
        aliases_by_ent: dict[uuid.UUID, list[str]] = defaultdict(list)
        for chunk in _chunked(ent_ids):
            alias_rows = self._session.execute(
                select(EntityAlias.entity_id, EntityAlias.alias_value).where(
                    EntityAlias.project_id == project_id,
                    EntityAlias.entity_id.in_(chunk),
                )
            ).all()
            for a_ent_id, a_val in alias_rows:
                aliases_by_ent[a_ent_id].append(a_val)

        # Load lightweight KnowledgeItem status and evidence links for scoped entities only
        ki_id_set = {e.primary_knowledge_item_id for e in entities if e.primary_knowledge_item_id}
        ki_status_map: dict[uuid.UUID, tuple[str, str]] = {}
        ki_ev_map: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
        if ki_id_set:
            for chunk in _chunked(ki_id_set):
                ki_rows = self._session.execute(
                    select(
                        KnowledgeItem.id,
                        KnowledgeItem.review_status,
                        KnowledgeItem.epistemic_status,
                    ).where(
                        KnowledgeItem.project_id == project_id,
                        KnowledgeItem.is_deleted.is_(False),
                        KnowledgeItem.id.in_(chunk),
                    )
                ).all()
                for ki_id, r_status, e_status in ki_rows:
                    ki_status_map[ki_id] = (r_status, e_status)

            if ki_status_map:
                for chunk in _chunked(ki_status_map.keys()):
                    ki_link_rows = self._session.execute(
                        select(
                            KnowledgeEvidenceLink.knowledge_item_id,
                            KnowledgeEvidenceLink.evidence_id,
                        ).where(
                            KnowledgeEvidenceLink.project_id == project_id,
                            KnowledgeEvidenceLink.knowledge_item_id.in_(chunk),
                        )
                    ).all()
                    for ki_id, ev_id in ki_link_rows:
                        ki_ev_map[ki_id].append(ev_id)

        # Load lightweight intra-graph relationship tuples where BOTH endpoints match allowed_types
        ent_id_subq = select(KnowledgeEntity.id).where(
            KnowledgeEntity.project_id == project_id,
            KnowledgeEntity.is_deleted.is_(False),
            KnowledgeEntity.is_stale.is_(False),
            KnowledgeEntity.entity_type.in_(allowed_types),
        )
        rel_rows = self._session.execute(
            select(
                KnowledgeRelationship.id,
                KnowledgeRelationship.source_entity_id,
                KnowledgeRelationship.target_entity_id,
                KnowledgeRelationship.relationship_type,
                KnowledgeRelationship.relationship_basis,
                KnowledgeRelationship.verification_status,
                KnowledgeRelationship.confidence_score,
            ).where(
                KnowledgeRelationship.project_id == project_id,
                KnowledgeRelationship.is_stale.is_(False),
                KnowledgeRelationship.source_entity_id.in_(ent_id_subq),
                KnowledgeRelationship.target_entity_id.in_(ent_id_subq),
            )
        ).all()

        rel_ev_map: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
        if rel_rows:
            rel_id_set = [r[0] for r in rel_rows]
            for chunk in _chunked(rel_id_set):
                rel_link_rows = self._session.execute(
                    select(
                        RelationshipEvidenceLink.relationship_id,
                        RelationshipEvidenceLink.evidence_id,
                    ).where(
                        RelationshipEvidenceLink.project_id == project_id,
                        RelationshipEvidenceLink.relationship_id.in_(chunk),
                    )
                ).all()
                for rel_id, ev_id in rel_link_rows:
                    rel_ev_map[rel_id].append(ev_id)

        node_ev_ids: dict[uuid.UUID, set[uuid.UUID]] = {}
        for ent in entities:
            ev_set: set[uuid.UUID] = set()
            if ent.primary_evidence_id and ent.primary_evidence_id in accessible_ev_set:
                ev_set.add(ent.primary_evidence_id)
            if ent.primary_knowledge_item_id and ent.primary_knowledge_item_id in ki_status_map:
                for ev_id in ki_ev_map.get(ent.primary_knowledge_item_id, ()):
                    if ev_id in accessible_ev_set:
                        ev_set.add(ev_id)
            node_ev_ids[ent.id] = ev_set

        # Augment node accessible evidence from accessible relationship evidence links
        valid_edges: list[KnowledgeGraphEdge] = []
        for rel_id, src_id, dst_id, rel_type, rel_basis, rel_ver_status, rel_conf in rel_rows:
            if not include_suggested and rel_basis == RelationshipBasis.INFERRED.value:
                continue
            rel_ev_ids = [
                ev_id for ev_id in rel_ev_map.get(rel_id, ()) if ev_id in accessible_ev_set
            ]
            if not rel_ev_ids:
                continue
            node_ev_ids.setdefault(src_id, set()).update(rel_ev_ids)
            node_ev_ids.setdefault(dst_id, set()).update(rel_ev_ids)
            valid_edges.append(
                KnowledgeGraphEdge(
                    id=rel_id,
                    source=src_id,
                    target=dst_id,
                    relationship_type=rel_type,
                    label=get_display_label(rel_type),
                    evidence_basis=rel_basis,
                    verification_status=rel_ver_status,
                    confidence_score=float(rel_conf),
                    evidence_ids=sorted(set(rel_ev_ids), key=str),
                )
            )

        # Build nodes strictly backed by accessible evidence (keep Project root only if graph has other nodes)
        search_low = search.strip().lower() if search else None
        status_low = status.strip().lower() if status else None
        ver_low = verification_state.strip().lower() if verification_state else None

        tech_node_types = {
            EntityType.TECHNOLOGY.value,
            EntityType.FRAMEWORK.value,
            EntityType.LIBRARY.value,
            EntityType.DATABASE.value,
        }
        arch_component_types = {
            EntityType.TECHNICAL_COMPONENT.value,
            EntityType.ARCHITECTURE_COMPONENT.value,
            EntityType.COMPONENT.value,
            EntityType.SERVICE.value,
            EntityType.API.value,
        }
        tech_id_set = {e.id for e in entities if e.entity_type in tech_node_types}
        comp_id_set = {e.id for e in entities if e.entity_type in arch_component_types}
        feature_core_types = {
            EntityType.FEATURE.value,
            EntityType.REQUIREMENT.value,
            EntityType.OPERATIONAL_PROCEDURE.value,
            EntityType.WORK_ITEM.value,
        }
        feature_aux_types = {
            EntityType.COMMIT.value,
            EntityType.PULL_REQUEST.value,
            EntityType.TECHNICAL_COMPONENT.value,
            EntityType.ARCHITECTURE_COMPONENT.value,
        }
        feature_core_id_set = {e.id for e in entities if e.entity_type in feature_core_types}
        feature_linked_aux_ids: set[uuid.UUID] = set()
        tech_linked_comp_ids: set[uuid.UUID] = set()
        configured_doc_ids: set[uuid.UUID] = set()
        arch_linked_tech_ids: set[uuid.UUID] = set()
        for e_edge in valid_edges:
            if e_edge.relationship_type == "CONFIGURED_IN":
                configured_doc_ids.add(e_edge.target)
            if e_edge.source in tech_id_set and e_edge.target in comp_id_set:
                tech_linked_comp_ids.add(e_edge.target)
                arch_linked_tech_ids.add(e_edge.source)
            elif e_edge.target in tech_id_set and e_edge.source in comp_id_set:
                tech_linked_comp_ids.add(e_edge.source)
                arch_linked_tech_ids.add(e_edge.target)
            if e_edge.source in feature_core_id_set:
                feature_linked_aux_ids.add(e_edge.target)
            if e_edge.target in feature_core_id_set:
                feature_linked_aux_ids.add(e_edge.source)

        candidate_nodes: list[KnowledgeGraphNode] = []
        project_root_node: KnowledgeGraphNode | None = None
        for ent in entities:
            ev_ids = sorted(node_ev_ids.get(ent.id, set()), key=str)
            ki_st = (
                ki_status_map.get(ent.primary_knowledge_item_id)
                if ent.primary_knowledge_item_id
                else None
            )
            ent_aliases = aliases_by_ent.get(ent.id, [])
            if ent.entity_type == EntityType.PROJECT.value:
                project_root_node = self._to_graph_node(
                    ent,
                    graph_type=graph_type,
                    accessible_ev_ids=ev_ids,
                    ki_status=ki_st,
                    aliases=ent_aliases,
                )
                continue
            if not ev_ids:
                # Fail-closed: strip nodes with zero accessible evidence support
                continue
            # For technology-stack, strip unconnected generic components and non-CONFIGURED_IN documents
            if graph_type == "technology-stack":
                if ent.entity_type == EntityType.DOCUMENT.value and ent.id not in configured_doc_ids:
                    continue
                if ent.entity_type in arch_component_types and ent.id not in tech_linked_comp_ids:
                    continue
            # For system-architecture, keep technology nodes only when tied to a component/database layer
            if graph_type == "system-architecture" and ent.entity_type == EntityType.TECHNOLOGY.value:
                tech_cat = str((ent.metadata_json or {}).get("technology_category") or "").lower()
                if ent.id not in arch_linked_tech_ids and tech_cat != "database":
                    continue
            # For features-workflows, strip unlinked raw commits/PRs/components
            if (
                graph_type == "features-workflows"
                and ent.entity_type in feature_aux_types
                and ent.id not in feature_linked_aux_ids
            ):
                continue
            node = self._to_graph_node(
                ent,
                graph_type=graph_type,
                accessible_ev_ids=ev_ids,
                ki_status=ki_st,
                aliases=ent_aliases,
            )
            if search_low and (
                search_low not in node.label.lower()
                and search_low not in (node.description or "").lower()
                and not any(search_low in a.lower() for a in node.aliases)
            ):
                continue
            if status_low and node.status.lower() != status_low:
                continue
            if ver_low and node.verification_status.lower() != ver_low:
                continue
            candidate_nodes.append(node)

        # Include Project root only when there are non-project nodes in Technology Stack / Architecture
        if project_root_node is not None and candidate_nodes and graph_type in {"technology-stack", "system-architecture"}:
            candidate_nodes.insert(0, project_root_node)

        offset = int(cursor) if cursor and cursor.isdigit() else 0
        sliced_nodes = candidate_nodes[offset : offset + limit]
        next_cursor = str(offset + limit) if offset + limit < len(candidate_nodes) else None

        visible_ids = {n.id for n in sliced_nodes}
        filtered_edges = [
            e for e in valid_edges if e.source in visible_ids and e.target in visible_ids
        ]

        cat_counts = Counter(n.category or n.entity_type for n in sliced_nodes)
        resp = KnowledgeGraphProjectionResponse(
            graph_type=graph_type,
            project_id=project_id,
            nodes=sliced_nodes,
            edges=filtered_edges,
            summary=KnowledgeGraphSummary(
                node_count=len(sliced_nodes),
                edge_count=len(filtered_edges),
                categories=dict(cat_counts),
            ),
            next_cursor=next_cursor,
        )
        local_response_cache.set(cache_key, resp.model_dump(mode="json"), ttl_seconds=60)
        return resp

    def _collect_entity_metadata_maps(
        self,
        *,
        project_id: uuid.UUID,
        entities: list[KnowledgeEntity],
    ) -> tuple[
        dict[uuid.UUID, list[str]],
        dict[uuid.UUID, tuple[str, str]],
        dict[uuid.UUID, list[uuid.UUID]],
    ]:
        ent_ids = [e.id for e in entities]
        aliases_by_ent: dict[uuid.UUID, list[str]] = defaultdict(list)
        if ent_ids:
            for chunk in _chunked(ent_ids):
                rows = self._session.execute(
                    select(EntityAlias.entity_id, EntityAlias.alias_value).where(
                        EntityAlias.project_id == project_id,
                        EntityAlias.entity_id.in_(chunk),
                    )
                ).all()
                for eid, aval in rows:
                    aliases_by_ent[eid].append(aval)

        ki_ids = list({e.primary_knowledge_item_id for e in entities if e.primary_knowledge_item_id})
        ki_status_map: dict[uuid.UUID, tuple[str, str]] = {}
        ki_ev_map: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
        if ki_ids:
            for chunk in _chunked(ki_ids):
                k_rows = self._session.execute(
                    select(
                        KnowledgeItem.id,
                        KnowledgeItem.review_status,
                        KnowledgeItem.epistemic_status,
                    ).where(
                        KnowledgeItem.id.in_(chunk),
                        KnowledgeItem.is_deleted.is_(False),
                    )
                ).all()
                for kid, r_status, e_status in k_rows:
                    ki_status_map[kid] = (r_status, e_status)
                l_rows = self._session.execute(
                    select(
                        KnowledgeEvidenceLink.knowledge_item_id,
                        KnowledgeEvidenceLink.evidence_id,
                    ).where(KnowledgeEvidenceLink.knowledge_item_id.in_(chunk))
                ).all()
                for kid, ev_id in l_rows:
                    ki_ev_map[kid].append(ev_id)
        return aliases_by_ent, ki_status_map, ki_ev_map

    def get_node_detail(
        self,
        *,
        project_ctx: ProjectContext,
        graph_type: GraphKind,
        node_id: uuid.UUID,
    ) -> KnowledgeGraphNodeDetailResponse:
        from app.core.exceptions import NotFoundError

        project_id = project_ctx.project.id
        viewer_id = project_ctx.principal.user_id
        has_manage = project_ctx.has_permission("project.manage")
        allowed_types = _GRAPH_ALLOWED_ENTITY_TYPES[graph_type]

        target_ent = self._session.execute(
            select(KnowledgeEntity).where(
                KnowledgeEntity.id == node_id,
                KnowledgeEntity.project_id == project_id,
                KnowledgeEntity.is_deleted.is_(False),
                KnowledgeEntity.is_stale.is_(False),
                KnowledgeEntity.entity_type.in_(allowed_types),
            )
        ).scalar_one_or_none()
        if target_ent is None:
            raise NotFoundError("Graph node not found or inaccessible.", code="GRAPH_NODE_NOT_FOUND")

        accessible_ev_set = self._get_accessible_evidence_ids(
            project_id=project_id,
            viewer_user_id=viewer_id,
            has_project_manage=has_manage,
        )
        if not accessible_ev_set:
            raise NotFoundError("Graph node not found or inaccessible.", code="GRAPH_NODE_NOT_FOUND")

        # Load only incident relationships touching node_id
        inc_rel_rows = self._session.execute(
            select(
                KnowledgeRelationship.id,
                KnowledgeRelationship.source_entity_id,
                KnowledgeRelationship.target_entity_id,
                KnowledgeRelationship.relationship_type,
                KnowledgeRelationship.relationship_basis,
                KnowledgeRelationship.verification_status,
                KnowledgeRelationship.confidence_score,
            ).where(
                KnowledgeRelationship.project_id == project_id,
                KnowledgeRelationship.is_stale.is_(False),
                or_(
                    KnowledgeRelationship.source_entity_id == node_id,
                    KnowledgeRelationship.target_entity_id == node_id,
                ),
            )
        ).all()

        rel_ev_map: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
        if inc_rel_rows:
            inc_rel_ids = [r[0] for r in inc_rel_rows]
            for chunk in _chunked(inc_rel_ids):
                rows = self._session.execute(
                    select(
                        RelationshipEvidenceLink.relationship_id,
                        RelationshipEvidenceLink.evidence_id,
                    ).where(RelationshipEvidenceLink.relationship_id.in_(chunk))
                ).all()
                for rid, eid in rows:
                    rel_ev_map[rid].append(eid)

        valid_incident_edges: list[KnowledgeGraphEdge] = []
        neighbor_ids: set[uuid.UUID] = set()
        node_ev_ids: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
        for rel_id, src_id, dst_id, rel_type, rel_basis, rel_ver_status, rel_conf in inc_rel_rows:
            rel_ev_ids = [
                ev_id for ev_id in rel_ev_map.get(rel_id, ()) if ev_id in accessible_ev_set
            ]
            if not rel_ev_ids:
                continue
            node_ev_ids[src_id].update(rel_ev_ids)
            node_ev_ids[dst_id].update(rel_ev_ids)
            other_id = dst_id if src_id == node_id else src_id
            if other_id != node_id:
                neighbor_ids.add(other_id)
            valid_incident_edges.append(
                KnowledgeGraphEdge(
                    id=rel_id,
                    source=src_id,
                    target=dst_id,
                    relationship_type=rel_type,
                    label=get_display_label(rel_type),
                    evidence_basis=rel_basis,
                    verification_status=rel_ver_status,
                    confidence_score=float(rel_conf),
                    evidence_ids=sorted(set(rel_ev_ids), key=str),
                )
            )

        if (
            graph_type == "technology-stack"
            and target_ent.entity_type == EntityType.DOCUMENT.value
            and not any(
                e.target == target_ent.id and e.relationship_type == "CONFIGURED_IN"
                for e in valid_incident_edges
            )
        ):
            raise NotFoundError("Graph node not found or inaccessible.", code="GRAPH_NODE_NOT_FOUND")

        adj_entities: list[KnowledgeEntity] = []
        if neighbor_ids:
            for chunk in _chunked(neighbor_ids):
                adj_entities.extend(
                    self._session.execute(
                        select(KnowledgeEntity).where(
                            KnowledgeEntity.id.in_(chunk),
                            KnowledgeEntity.project_id == project_id,
                            KnowledgeEntity.is_deleted.is_(False),
                            KnowledgeEntity.is_stale.is_(False),
                            KnowledgeEntity.entity_type.in_(allowed_types),
                        )
                    )
                    .scalars()
                    .all()
                )

        scoped_entities = [target_ent, *adj_entities]
        aliases_by_ent, ki_status_map, ki_ev_map = self._collect_entity_metadata_maps(
            project_id=project_id,
            entities=scoped_entities,
        )

        for ent in scoped_entities:
            ev_set = node_ev_ids[ent.id]
            if ent.primary_evidence_id and ent.primary_evidence_id in accessible_ev_set:
                ev_set.add(ent.primary_evidence_id)
            if ent.primary_knowledge_item_id and ent.primary_knowledge_item_id in ki_status_map:
                for ev_id in ki_ev_map.get(ent.primary_knowledge_item_id, ()):
                    if ev_id in accessible_ev_set:
                        ev_set.add(ev_id)

        target_ev_ids = sorted(node_ev_ids.get(target_ent.id, set()), key=str)
        if target_ent.entity_type != EntityType.PROJECT.value and not target_ev_ids:
            raise NotFoundError("Graph node not found or inaccessible.", code="GRAPH_NODE_NOT_FOUND")

        target_ki_st = (
            ki_status_map.get(target_ent.primary_knowledge_item_id)
            if target_ent.primary_knowledge_item_id
            else None
        )
        target_node = self._to_graph_node(
            target_ent,
            graph_type=graph_type,
            accessible_ev_ids=target_ev_ids,
            ki_status=target_ki_st,
            aliases=aliases_by_ent.get(target_ent.id, []),
        )

        # Build related nodes backed by accessible evidence within allowed types
        related_node_map: dict[uuid.UUID, KnowledgeGraphNode] = {}
        doc_adj_ids = {
            e.id
            for e in adj_entities
            if graph_type == "technology-stack" and e.entity_type == EntityType.DOCUMENT.value
        }
        configured_doc_ids: set[uuid.UUID] = set()
        if doc_adj_ids:
            configured_doc_rows = self._session.execute(
                select(KnowledgeRelationship.target_entity_id)
                .where(
                    KnowledgeRelationship.project_id == project_id,
                    KnowledgeRelationship.is_stale.is_(False),
                    KnowledgeRelationship.relationship_type == "CONFIGURED_IN",
                    KnowledgeRelationship.target_entity_id.in_(list(doc_adj_ids)),
                )
            ).scalars().all()
            configured_doc_ids = set(configured_doc_rows)

        for ent in adj_entities:
            ev_ids = sorted(node_ev_ids.get(ent.id, set()), key=str)
            if ent.entity_type != EntityType.PROJECT.value and not ev_ids:
                continue
            if (
                graph_type == "technology-stack"
                and ent.entity_type == EntityType.DOCUMENT.value
                and ent.id not in configured_doc_ids
            ):
                continue
            ki_st = (
                ki_status_map.get(ent.primary_knowledge_item_id)
                if ent.primary_knowledge_item_id
                else None
            )
            related_node_map[ent.id] = self._to_graph_node(
                ent,
                graph_type=graph_type,
                accessible_ev_ids=ev_ids,
                ki_status=ki_st,
                aliases=aliases_by_ent.get(ent.id, []),
            )

        visible_adj_ids = set(related_node_map.keys()) | {target_ent.id}
        adj_edges = [
            e
            for e in valid_incident_edges
            if e.source in visible_adj_ids and e.target in visible_adj_ids
        ]
        related_nodes = [
            related_node_map[rid]
            for rid in {
                e.target if e.source == node_id else e.source for e in adj_edges
            }
            if rid in related_node_map
        ]

        # Fetch ONLY the EvidenceItems referenced by target_node
        accessible_ev_map = self._get_accessible_evidence_map(
            project_id=project_id,
            viewer_user_id=viewer_id,
            has_project_manage=has_manage,
            evidence_ids=target_node.evidence_ids,
        )
        ev_refs: list[KnowledgeGraphEvidenceRef] = []
        for eid in target_node.evidence_ids:
            ev = accessible_ev_map.get(eid)
            if ev is not None:
                ev_refs.append(
                    KnowledgeGraphEvidenceRef(
                        evidence_id=ev.id,
                        title=ev.title,
                        source_type=ev.source_type,
                        source_url=ev.source_url,
                        supporting_excerpt=target_node.description[:220] if target_node.description else None,
                    )
                )

        return KnowledgeGraphNodeDetailResponse(
            graph_type=graph_type,
            project_id=project_id,
            node=target_node,
            adjacent_edges=adj_edges,
            related_nodes=related_nodes,
            evidence_refs=ev_refs,
        )
