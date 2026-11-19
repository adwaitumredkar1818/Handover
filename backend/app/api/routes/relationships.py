"""FastAPI HTTP endpoints for Relationship Explorer module.

Provides:
- Graph projection for React Flow frontend (`/graph`)
- Entity listing and node detail side-panel (`/entities`, `/entities/{id}`)
- Relationship queries, evidence links, and human review queue
  (`/{id}`, `/{id}/evidence`, `/{id}/submit-for-review`)
- Decision-to-implementation traceability chains (`/traceability`, `/traceability/{decision_id}`)
- Directed dependency hierarchy with cycle detection (`/dependencies`)
- Chronological timeline event stream (`/timeline`)
- Asynchronous and on-demand graph reconstruction runs (`/reconstruct`, `/runs`)
- Multi-signal identity candidate review and reversible merge (`/identities/candidates`)

Enforces strict fail-closed source ACL checks on all endpoints.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import (
    get_db_session,
    require_project_permission,
)
from app.core.cache.local_cache import local_response_cache
from app.models.enums import (
    BackgroundJobType,
    TraceabilityCompletenessStatus,
)
from app.models.relationship import KnowledgeEntity
from app.repositories.job import BackgroundJobRepository
from app.repositories.relationship import (
    EntityRepository,
    RelationshipRepository,
    RelationshipRunRepository,
    TimelineRepository,
    TraceabilityRepository,
)
from app.schemas.relationship import (
    ContributorGraphResponse,
    ContributorIdentityReviewRequest,
    ContributorIdentityReviewResponse,
    ContributorIdentitySummaryResponse,
    DecisionTraceabilityResponse,
    DependencyGraphResponse,
    EntityListResponse,
    GraphProjectionResponse,
    IdentityCandidateResponse,
    IdentityReviewRequest,
    IdentitySelectableMemberResponse,
    KnowledgeEntityResponse,
    KnowledgeRelationshipResponse,
    NodeDetailResponse,
    ReconstructionTriggerRequest,
    RelationshipEvidenceLinkResponse,
    RelationshipListResponse,
    RelationshipReconstructionRunResponse,
    RelationshipReviewRequest,
    TimelineEventGraphResponse,
    TimelineGraphStreamResponse,
    TraceabilityListResponse,
    WorkClusterRebuildResponse,
    WorkClusterResponse,
)
from app.services.contribution_attribution import ContributionAttributionService
from app.services.dependency_intelligence import DependencyIntelligenceService
from app.services.graph_projection import GraphProjectionService
from app.services.rbac import ProjectContext
from app.services.traceability import DecisionTraceabilityService
from app.services.work_grouping import WorkGroupingService

router = APIRouter(tags=["Relationship Explorer"])


def _invalidate_project_graph_caches(project_id: uuid.UUID) -> None:
    """Clear short-lived L1 caches for KI graphs, relationship explorer, and contributor graph."""
    local_response_cache.invalidate_prefix(f"ki_graph:{project_id}:")
    local_response_cache.invalidate_prefix(f"rel_graph:{project_id}:")
    local_response_cache.invalidate_prefix(f"contrib_graph:{project_id}:")
    local_response_cache.invalidate_prefix(f"rel_contributors:{project_id}:")
    local_response_cache.invalidate_prefix(f"rel_selectable_members:{project_id}:")
    local_response_cache.invalidate_prefix(f"project_members:{project_id}:")
    local_response_cache.invalidate_prefix(f"work_clusters:{project_id}:")
    local_response_cache.invalidate_prefix(f"rel_traceability:{project_id}:")
    local_response_cache.invalidate_prefix(f"rel_deps:{project_id}:")
    local_response_cache.invalidate_prefix(f"rel_timeline:{project_id}:")


# ==============================================================================
# Graph Projection & Node Detail
# ==============================================================================


@router.get(
    "/projects/{project_id}/relationships/graph",
    response_model=GraphProjectionResponse,
    status_code=status.HTTP_200_OK,
    summary="Project knowledge graph into React Flow format",
)
def get_graph_projection(
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("project.read"))],
    db_session: Annotated[Session, Depends(get_db_session)],
    center_node_id: Annotated[uuid.UUID | None, Query()] = None,
    depth: Annotated[int, Query(ge=1, le=5)] = 2,
    entity_type: Annotated[str | None, Query()] = None,
    verification_status: Annotated[str | None, Query()] = None,
    limit_nodes: Annotated[int, Query(ge=1, le=1000)] = 250,
    limit_edges: Annotated[int, Query(ge=1, le=2000)] = 500,
) -> GraphProjectionResponse:
    """Return a React Flow projection filtered strictly by caller source permissions."""
    service = GraphProjectionService(db_session)
    has_manage = project_ctx.has_permission("project.manage")
    return service.project_graph(
        project_id=project_ctx.project.id,
        viewer_user_id=project_ctx.principal.user_id,
        has_project_manage=has_manage,
        center_node_id=center_node_id,
        depth=depth,
        entity_type_filter=entity_type,
        verification_status_filter=verification_status,
        limit_nodes=limit_nodes,
        limit_edges=limit_edges,
    )


# ==============================================================================
# Entities
# ==============================================================================


@router.get(
    "/projects/{project_id}/relationships/entities",
    response_model=EntityListResponse,
    status_code=status.HTTP_200_OK,
    summary="List accessible entities in the project",
)
def list_entities(
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("project.read"))],
    db_session: Annotated[Session, Depends(get_db_session)],
    entity_type: Annotated[str | None, Query()] = None,
    resolution_status: Annotated[str | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> EntityListResponse:
    """Return paginated entities visible to caller."""
    repo = EntityRepository(db_session)
    has_manage = project_ctx.has_permission("project.manage")
    items, total = repo.list_accessible_entities(
        project_id=project_ctx.project.id,
        viewer_user_id=project_ctx.principal.user_id,
        has_project_manage=has_manage,
        entity_type=entity_type,
        resolution_status=resolution_status,
        query=q,
        limit=limit,
        offset=offset,
    )
    return EntityListResponse(
        items=[KnowledgeEntityResponse.model_validate(e) for e in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/projects/{project_id}/relationships/entities/{entity_id}",
    response_model=NodeDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get node side-panel details with adjacent edges",
)
def get_node_details(
    entity_id: uuid.UUID,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("project.read"))],
    db_session: Annotated[Session, Depends(get_db_session)],
) -> NodeDetailResponse:
    """Return comprehensive metadata and adjacent relationships for selected entity."""
    service = GraphProjectionService(db_session)
    has_manage = project_ctx.has_permission("project.manage")
    try:
        return service.get_node_details(
            project_id=project_ctx.project.id,
            entity_id=entity_id,
            viewer_user_id=project_ctx.principal.user_id,
            has_project_manage=has_manage,
        )
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "SOURCE_ACCESS_DENIED: Entity primary evidence is restricted to external accounts."
            ),
        ) from None


# ==============================================================================
# Relationships & Review Queue
# ==============================================================================


@router.get(
    "/projects/{project_id}/relationships",
    response_model=RelationshipListResponse,
    status_code=status.HTTP_200_OK,
    summary="List accessible knowledge graph relationships",
)
def list_relationships(
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("project.read"))],
    db_session: Annotated[Session, Depends(get_db_session)],
    relationship_type: Annotated[str | None, Query()] = None,
    relationship_basis: Annotated[str | None, Query()] = None,
    verification_status: Annotated[str | None, Query()] = None,
    entity_id: Annotated[uuid.UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RelationshipListResponse:
    """Return paginated relationships where caller has access to supporting evidence."""
    repo = RelationshipRepository(db_session)
    has_manage = project_ctx.has_permission("project.manage")
    items, total = repo.list_accessible_relationships(
        project_id=project_ctx.project.id,
        viewer_user_id=project_ctx.principal.user_id,
        has_project_manage=has_manage,
        relationship_type=relationship_type,
        relationship_basis=relationship_basis,
        verification_status=verification_status,
        entity_id=entity_id,
        limit=limit,
        offset=offset,
    )
    return RelationshipListResponse(
        items=[KnowledgeRelationshipResponse.model_validate(r) for r in items],
        total=total,
        limit=limit,
        offset=offset,
    )


# ==============================================================================
# Decision Traceability
# ==============================================================================


@router.get(
    "/projects/{project_id}/relationships/traceability",
    response_model=TraceabilityListResponse,
    status_code=status.HTTP_200_OK,
    summary="List decision traceability chains",
)
def list_traceability_chains(
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("project.read"))],
    db_session: Annotated[Session, Depends(get_db_session)],
    completeness_status: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TraceabilityListResponse:
    """Return 5-stage decision-to-implementation traceability chains."""
    has_manage = project_ctx.has_permission("project.manage")
    bind_id = id(db_session.get_bind())
    cache_key = (
        f"rel_traceability:{project_ctx.project.id}:{bind_id}:"
        f"{project_ctx.principal.user_id}:{int(has_manage)}:{completeness_status or ''}:{limit}:{offset}"
    )
    cached = local_response_cache.get(cache_key)
    if isinstance(cached, dict):
        try:
            return TraceabilityListResponse.model_validate(cached)
        except Exception:
            local_response_cache.delete(cache_key)

    repo = TraceabilityRepository(db_session)
    items, total = repo.list_accessible_chains(
        project_id=project_ctx.project.id,
        viewer_user_id=project_ctx.principal.user_id,
        has_project_manage=has_manage,
        completeness_status=completeness_status,
        limit=limit,
        offset=offset,
    )

    # Counts
    complete_c = sum(
        1 for c in items if c.completeness_status == TraceabilityCompletenessStatus.COMPLETE.value
    )
    part_c = sum(
        1
        for c in items
        if c.completeness_status == TraceabilityCompletenessStatus.PARTIALLY_TRACED.value
    )
    untraced_c = sum(
        1 for c in items if c.completeness_status == TraceabilityCompletenessStatus.UNTRACED.value
    )
    conf_c = sum(
        1
        for c in items
        if c.completeness_status == TraceabilityCompletenessStatus.CONFLICTING.value
    )

    dec_ids = list({c.decision_entity_id for c in items if c.decision_entity_id})
    dec_map = (
        {
            e.id: e
            for e in db_session.execute(
                select(KnowledgeEntity).where(KnowledgeEntity.id.in_(dec_ids))
            )
            .scalars()
            .all()
        }
        if dec_ids
        else {}
    )
    res_items = []
    for c in items:
        dec = dec_map.get(c.decision_entity_id)
        resp = DecisionTraceabilityResponse.model_validate(c)
        resp.decision_name = dec.canonical_name if dec else None
        res_items.append(resp)

    resp_obj = TraceabilityListResponse(
        items=res_items,
        total=total,
        complete_count=complete_c,
        partially_traced_count=part_c,
        untraced_count=untraced_c,
        conflicting_count=conf_c,
    )
    local_response_cache.set(cache_key, resp_obj.model_dump(mode="json"), ttl_seconds=120)
    return resp_obj


@router.get(
    "/projects/{project_id}/relationships/traceability/{decision_entity_id}",
    response_model=DecisionTraceabilityResponse,
    status_code=status.HTTP_200_OK,
    summary="Get single decision traceability chain",
)
def get_decision_traceability(
    decision_entity_id: uuid.UUID,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("project.read"))],
    db_session: Annotated[Session, Depends(get_db_session)],
) -> DecisionTraceabilityResponse:
    """Return single decision traceability chain."""
    repo = TraceabilityRepository(db_session)
    entity_repo = EntityRepository(db_session)
    has_manage = project_ctx.has_permission("project.manage")

    ent, denied = entity_repo.get_accessible_entity(
        decision_entity_id,
        project_id=project_ctx.project.id,
        viewer_user_id=project_ctx.principal.user_id,
        has_project_manage=has_manage,
    )
    if ent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Decision entity not found."
        )
    if denied:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="SOURCE_ACCESS_DENIED: Decision is restricted.",
        )

    chain = repo.get_chain_by_decision(
        project_id=project_ctx.project.id,
        decision_entity_id=decision_entity_id,
    )
    if chain is None:
        # Dynamically compute on demand
        service = DecisionTraceabilityService(db_session)
        analysis = service.analyze_decision_traceability(ent)
        chain = repo.create_or_update_chain(
            organisation_id=project_ctx.organisation.id,
            project_id=project_ctx.project.id,
            decision_entity_id=ent.id,
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

    resp = DecisionTraceabilityResponse.model_validate(chain)
    resp.decision_name = ent.canonical_name
    return resp


# ==============================================================================
# Dependency Intelligence & Cycle Detection
# ==============================================================================


@router.get(
    "/projects/{project_id}/relationships/dependencies",
    response_model=DependencyGraphResponse,
    status_code=status.HTTP_200_OK,
    summary="Analyze dependency graph with cycle detection",
)
def get_dependencies_graph(
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("project.read"))],
    db_session: Annotated[Session, Depends(get_db_session)],
    root_entity_id: Annotated[uuid.UUID | None, Query()] = None,
    max_depth: Annotated[int, Query(ge=1, le=20)] = 10,
) -> DependencyGraphResponse:
    """Traverse directed dependency hierarchy, detect cycles, and identify root blockers."""
    has_manage = project_ctx.has_permission("project.manage")
    bind_id = id(db_session.get_bind())
    cache_key = (
        f"rel_deps:{project_ctx.project.id}:{bind_id}:"
        f"{project_ctx.principal.user_id}:{int(has_manage)}:{root_entity_id or ''}:{max_depth}"
    )
    cached = local_response_cache.get(cache_key)
    if isinstance(cached, dict):
        try:
            return DependencyGraphResponse.model_validate(cached)
        except Exception:
            local_response_cache.delete(cache_key)

    service = DependencyIntelligenceService(db_session)
    result = service.analyze_dependencies(
        project_id=project_ctx.project.id,
        viewer_user_id=project_ctx.principal.user_id,
        has_project_manage=has_manage,
        root_entity_id=root_entity_id,
        max_depth=max_depth,
    )
    local_response_cache.set(cache_key, result.model_dump(mode="json"), ttl_seconds=120)
    return result


# ==============================================================================
# Knowledge Timeline
# ==============================================================================


@router.get(
    "/projects/{project_id}/relationships/timeline",
    response_model=TimelineGraphStreamResponse,
    status_code=status.HTTP_200_OK,
    summary="Get chronological stream of graph timeline events",
)
def get_timeline_stream(
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("project.read"))],
    db_session: Annotated[Session, Depends(get_db_session)],
    entity_id: Annotated[uuid.UUID | None, Query()] = None,
    event_type: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TimelineGraphStreamResponse:
    """Return chronological event stream with verifiable timestamp precision."""
    has_manage = project_ctx.has_permission("project.manage")
    bind_id = id(db_session.get_bind())
    cache_key = (
        f"rel_timeline:{project_ctx.project.id}:{bind_id}:"
        f"{project_ctx.principal.user_id}:{int(has_manage)}:{entity_id or ''}:{event_type or ''}:{limit}:{offset}"
    )
    cached = local_response_cache.get(cache_key)
    if isinstance(cached, dict):
        try:
            return TimelineGraphStreamResponse.model_validate(cached)
        except Exception:
            local_response_cache.delete(cache_key)

    repo = TimelineRepository(db_session)
    events, total = repo.list_accessible_events(
        project_id=project_ctx.project.id,
        viewer_user_id=project_ctx.principal.user_id,
        has_project_manage=has_manage,
        entity_id=entity_id,
        event_type=event_type,
        limit=limit,
        offset=offset,
    )
    ent_ids = list({evt.entity_id for evt in events if evt.entity_id})
    ent_map = (
        {
            e.id: e
            for e in db_session.execute(
                select(KnowledgeEntity).where(KnowledgeEntity.id.in_(ent_ids))
            )
            .scalars()
            .all()
        }
        if ent_ids
        else {}
    )
    items = []
    for evt in events:
        e_resp = TimelineEventGraphResponse.model_validate(evt)
        ent = ent_map.get(evt.entity_id) if evt.entity_id else None
        if ent:
            e_resp.entity_name = ent.canonical_name
            e_resp.entity_type = ent.entity_type
        items.append(e_resp)

    resp_obj = TimelineGraphStreamResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )
    local_response_cache.set(cache_key, resp_obj.model_dump(mode="json"), ttl_seconds=120)
    return resp_obj


# ==============================================================================
# Reconstruction Runs
# ==============================================================================


@router.post(
    "/projects/{project_id}/relationships/reconstruct",
    response_model=RelationshipReconstructionRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue asynchronous relationship discovery and graph rebuild",
)
def trigger_reconstruction(
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("project.manage"))],
    db_session: Annotated[Session, Depends(get_db_session)],
    payload: Annotated[ReconstructionTriggerRequest | None, Body()] = None,
) -> RelationshipReconstructionRunResponse:
    """Queue asynchronous relationship reconstruction on the background worker."""
    req = payload or ReconstructionTriggerRequest()
    run_repo = RelationshipRunRepository(db_session)
    job_repo = BackgroundJobRepository(db_session)

    active_run = run_repo.get_active_run(project_id=project_ctx.project.id)
    if active_run is not None:
        return RelationshipReconstructionRunResponse.model_validate(active_run)

    run = run_repo.create_run(
        organisation_id=project_ctx.organisation.id,
        project_id=project_ctx.project.id,
        is_synthetic=False,
    )
    active_job = job_repo.has_active_job_for_project(
        project_id=project_ctx.project.id,
        job_types=(BackgroundJobType.RELATIONSHIP_RECONSTRUCTION.value,),
    )
    if active_job is None:
        job_repo.create_job(
            organisation_id=project_ctx.organisation.id,
            project_id=project_ctx.project.id,
            evidence_id=None,
            triggered_by_user_id=project_ctx.principal.user_id,
            job_type=BackgroundJobType.RELATIONSHIP_RECONSTRUCTION.value,
            max_attempts=3,
            priority=40,
            payload_json={
                "run_id": str(run.id),
                "include_llm_suggestions": bool(req.include_llm_suggestions),
            },
        )
    _invalidate_project_graph_caches(project_ctx.project.id)
    db_session.commit()
    return RelationshipReconstructionRunResponse.model_validate(run, from_attributes=True)


@router.get(
    "/projects/{project_id}/relationships/runs",
    response_model=list[RelationshipReconstructionRunResponse],
    status_code=status.HTTP_200_OK,
    summary="List relationship reconstruction runs",
)
def list_reconstruction_runs(
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("project.read"))],
    db_session: Annotated[Session, Depends(get_db_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[RelationshipReconstructionRunResponse]:
    """Return historical reconstruction runs and discovery metrics."""
    repo = RelationshipRunRepository(db_session)
    runs, _ = repo.list_runs(project_id=project_ctx.project.id, limit=limit, offset=offset)
    return [RelationshipReconstructionRunResponse.model_validate(r) for r in runs]


@router.get(
    "/projects/{project_id}/relationships/runs/{run_id}",
    response_model=RelationshipReconstructionRunResponse,
    status_code=status.HTTP_200_OK,
    summary="Get single reconstruction run telemetry",
)
def get_reconstruction_run(
    run_id: uuid.UUID,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("project.read"))],
    db_session: Annotated[Session, Depends(get_db_session)],
) -> RelationshipReconstructionRunResponse:
    """Return detailed progress telemetry for a run."""
    repo = RelationshipRunRepository(db_session)
    run = repo.get_run(run_id, project_id=project_ctx.project.id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Run {run_id} not found."
        )
    return RelationshipReconstructionRunResponse.model_validate(run)


# ==============================================================================
# Identity Candidate Review & Reversible Merge
# ==============================================================================


@router.get(
    "/projects/{project_id}/relationships/identities/candidates",
    response_model=list[IdentityCandidateResponse],
    status_code=status.HTTP_200_OK,
    summary="List candidate identity matches for review",
)
def list_identity_candidates(
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("project.read"))],
    db_session: Annotated[Session, Depends(get_db_session)],
    decision_status: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[IdentityCandidateResponse]:
    """Return identity resolution candidate pairs."""
    repo = EntityRepository(db_session)
    candidates, _ = repo.list_identity_candidates(
        project_id=project_ctx.project.id,
        decision_status=decision_status,
        limit=limit,
        offset=offset,
    )
    ent_ids = list(
        {
            eid
            for c in candidates
            for eid in (c.left_entity_id, c.right_entity_id)
            if eid is not None
        }
    )
    ent_map = (
        {
            e.id: e
            for e in db_session.execute(
                select(KnowledgeEntity)
                .options(selectinload(KnowledgeEntity.aliases))
                .where(
                    KnowledgeEntity.id.in_(ent_ids),
                    KnowledgeEntity.is_deleted.is_(False),
                )
            )
            .scalars()
            .all()
        }
        if ent_ids
        else {}
    )
    result = []
    for c in candidates:
        c_resp = IdentityCandidateResponse.model_validate(c)
        l_ent = ent_map.get(c.left_entity_id)
        r_ent = ent_map.get(c.right_entity_id)
        if l_ent:
            c_resp.left_entity = KnowledgeEntityResponse.model_validate(l_ent)
        if r_ent:
            c_resp.right_entity = KnowledgeEntityResponse.model_validate(r_ent)
        result.append(c_resp)
    return result


@router.post(
    "/projects/{project_id}/relationships/identities/candidates/{candidate_id}/review",
    response_model=IdentityCandidateResponse,
    status_code=status.HTTP_200_OK,
    summary="Review and merge/reject an identity candidate",
)
def review_identity_candidate(
    candidate_id: uuid.UUID,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("project.manage"))],
    db_session: Annotated[Session, Depends(get_db_session)],
    payload: Annotated[IdentityReviewRequest, Body()],
) -> IdentityCandidateResponse:
    """Accept (reversible merge) or reject identity candidate."""
    repo = EntityRepository(db_session)
    try:
        updated = repo.review_identity_candidate(
            candidate_id,
            user_id=project_ctx.principal.user_id,
            action=payload.action,
            rationale=payload.rationale,
        )
        _invalidate_project_graph_caches(project_ctx.project.id)
        db_session.commit()
        return IdentityCandidateResponse.model_validate(updated)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None


@router.post(
    "/projects/{project_id}/relationships/identities/candidates/{candidate_id}/revert",
    response_model=IdentityCandidateResponse,
    status_code=status.HTTP_200_OK,
    summary="Revert an accepted identity merge",
)
def revert_identity_candidate(
    candidate_id: uuid.UUID,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("project.manage"))],
    db_session: Annotated[Session, Depends(get_db_session)],
    payload: Annotated[dict[str, str] | None, Body()] = None,
) -> IdentityCandidateResponse:
    """Revert an accepted merge, restoring right entity to canonical status."""
    repo = EntityRepository(db_session)
    rationale = (payload or {}).get("rationale")
    try:
        updated = repo.revert_identity_candidate(
            candidate_id,
            user_id=project_ctx.principal.user_id,
            rationale=rationale,
        )
        _invalidate_project_graph_caches(project_ctx.project.id)
        db_session.commit()
        return IdentityCandidateResponse.model_validate(updated)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None


# ==============================================================================
# People-Centric Contributor Graph, Identity Review & Work Clusters
# ==============================================================================


@router.get(
    "/projects/{project_id}/relationships/contributors/graph",
    response_model=ContributorGraphResponse,
    status_code=status.HTTP_200_OK,
    summary="Project people-centric contributor and work cluster graph",
)
def get_contributors_graph(
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("project.read"))],
    db_session: Annotated[Session, Depends(get_db_session)],
    contributor_type: Annotated[str | None, Query()] = None,
    work_cluster: Annotated[str | None, Query()] = None,
    repository: Annotated[str | None, Query()] = None,
    verification_state: Annotated[str | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
    include_external: Annotated[bool, Query()] = True,
    include_bots: Annotated[bool, Query()] = True,
    expand_contributor_key: Annotated[str | None, Query()] = None,
    expand_cluster_name: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 120,
) -> ContributorGraphResponse:
    """Return ACL-filtered contributor & work cluster graph projection."""
    service = WorkGroupingService(db_session)
    payload = service.get_contributors_graph(
        project_id=project_ctx.project.id,
        viewer_user_id=project_ctx.principal.user_id,
        has_project_manage=project_ctx.has_permission("project.manage"),
        contributor_type=contributor_type,
        work_cluster=work_cluster,
        repository=repository,
        verification_state=verification_state,
        search=search,
        include_external=include_external,
        include_bots=include_bots,
        expand_contributor_key=expand_contributor_key,
        expand_cluster_name=expand_cluster_name,
        limit=limit,
    )
    return ContributorGraphResponse.model_validate(payload)


@router.get(
    "/projects/{project_id}/relationships/contributors",
    response_model=list[ContributorIdentitySummaryResponse],
    status_code=status.HTTP_200_OK,
    summary="List contributor identities for review and attribution inspection",
)
def list_contributors(
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("project.read"))],
    db_session: Annotated[Session, Depends(get_db_session)],
    contributor_type: Annotated[str | None, Query()] = None,
    review_status: Annotated[str | None, Query()] = None,
) -> list[ContributorIdentitySummaryResponse]:
    """List contributor identities strictly filtered by accessible evidence."""
    has_manage = project_ctx.has_permission("project.manage")
    bind_id = id(db_session.get_bind())
    cache_key = (
        f"rel_contributors:{project_ctx.project.id}:{bind_id}:{project_ctx.principal.user_id}:"
        f"{int(has_manage)}:{contributor_type or ''}:{review_status or ''}"
    )
    cached = local_response_cache.get(cache_key)
    if isinstance(cached, list):
        try:
            return [ContributorIdentitySummaryResponse.model_validate(r) for r in cached]
        except Exception:
            local_response_cache.delete(cache_key)

    accessible_ids: set[uuid.UUID] | None = None
    if not has_manage:
        wg_service = WorkGroupingService(db_session)
        accessible_ids = wg_service._accessible_evidence_ids(
            project_id=project_ctx.project.id,
            viewer_user_id=project_ctx.principal.user_id,
            has_project_manage=has_manage,
        )
    attr_service = ContributionAttributionService(db_session)
    rows = attr_service.list_contributor_identities(
        project_id=project_ctx.project.id,
        accessible_evidence_ids=accessible_ids,
        has_project_manage=has_manage,
        contributor_type_filter=contributor_type,
        review_status_filter=review_status,
    )
    result = [ContributorIdentitySummaryResponse.model_validate(r) for r in rows]
    local_response_cache.set(
        cache_key, [r.model_dump(mode="json") for r in result], ttl_seconds=300
    )
    return result


@router.get(
    "/projects/{project_id}/relationships/contributors/{contributor_key}",
    response_model=ContributorIdentitySummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve detailed contributor profile and evidence references",
)
def get_contributor_detail(
    contributor_key: str,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("project.read"))],
    db_session: Annotated[Session, Depends(get_db_session)],
) -> ContributorIdentitySummaryResponse:
    """Return aggregated contributor identity detail filtered by caller source ACLs."""
    wg_service = WorkGroupingService(db_session)
    has_manage = project_ctx.has_permission("project.manage")
    accessible_ids = wg_service._accessible_evidence_ids(
        project_id=project_ctx.project.id,
        viewer_user_id=project_ctx.principal.user_id,
        has_project_manage=has_manage,
    )
    attr_service = ContributionAttributionService(db_session)
    rows = attr_service.list_contributor_identities(
        project_id=project_ctx.project.id,
        accessible_evidence_ids=accessible_ids,
        has_project_manage=has_manage,
    )
    match = next((r for r in rows if r["contributor_key"] == contributor_key), None)
    if match is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Contributor '{contributor_key}' not found or inaccessible.",
        )
    return ContributorIdentitySummaryResponse.model_validate(match)


@router.get(
    "/projects/{project_id}/relationships/identities/selectable-members",
    response_model=list[IdentitySelectableMemberResponse],
    status_code=status.HTTP_200_OK,
    summary="List canonical project members, org members, invitations, and roster entries for Identity Review",
)
def list_identity_selectable_members(
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("project.read"))],
    db_session: Annotated[Session, Depends(get_db_session)],
) -> list[IdentitySelectableMemberResponse]:
    """Return canonical selectable members for Identity Review dropdown without auto-accepting invitations."""
    has_manage = project_ctx.has_permission("project.manage")
    bind_id = id(db_session.get_bind())
    cache_key = f"rel_selectable_members:{project_ctx.project.id}:{bind_id}:{int(has_manage)}"
    cached = local_response_cache.get(cache_key)
    if isinstance(cached, list):
        try:
            return [IdentitySelectableMemberResponse.model_validate(r) for r in cached]
        except Exception:
            local_response_cache.delete(cache_key)

    attr_service = ContributionAttributionService(db_session)
    items = attr_service.list_selectable_members(
        project_id=project_ctx.project.id,
        has_project_manage=has_manage,
    )
    validated = [IdentitySelectableMemberResponse.model_validate(i) for i in items]
    local_response_cache.set(
        cache_key,
        [v.model_dump(mode="json") for v in validated],
        ttl_seconds=10,
    )
    return validated


@router.post(
    "/projects/{project_id}/relationships/contributors/{contributor_key}/review",
    response_model=ContributorIdentityReviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Confirm, mark external/bot, reject, or revert contributor identity mapping",
)
def review_contributor_identity(
    contributor_key: str,
    payload: Annotated[ContributorIdentityReviewRequest, Body()],
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("project.manage"))],
    db_session: Annotated[Session, Depends(get_db_session)],
) -> ContributorIdentityReviewResponse:
    """Human review action for unmatched or candidate contributor identities."""
    attr_service = ContributionAttributionService(db_session)
    result = attr_service.review_contributor_identity(
        organisation_id=project_ctx.project.organisation_id,
        project_id=project_ctx.project.id,
        contributor_key=contributor_key,
        action=payload.action,
        reviewer_user_id=project_ctx.principal.user_id,
        project_membership_id=payload.project_membership_id,
        user_id=payload.user_id,
        invitation_id=payload.invitation_id,
        roster_member_id=payload.roster_member_id,
        notes=payload.notes,
    )
    _invalidate_project_graph_caches(project_ctx.project.id)
    db_session.commit()
    return ContributorIdentityReviewResponse.model_validate(result)


@router.get(
    "/projects/{project_id}/relationships/work-clusters",
    response_model=list[WorkClusterResponse],
    status_code=status.HTTP_200_OK,
    summary="List evidence-based technical work clusters",
)
def list_work_clusters(
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("project.read"))],
    db_session: Annotated[Session, Depends(get_db_session)],
) -> list[WorkClusterResponse]:
    """List ACL-filtered technical work area clusters."""
    has_manage = project_ctx.has_permission("project.manage")
    bind_id = id(db_session.get_bind())
    cache_key = (
        f"work_clusters:{project_ctx.project.id}:{bind_id}:{project_ctx.principal.user_id}:{int(has_manage)}"
    )
    cached = local_response_cache.get(cache_key)
    if isinstance(cached, list):
        try:
            return [WorkClusterResponse.model_validate(c) for c in cached]
        except Exception:
            local_response_cache.delete(cache_key)

    service = WorkGroupingService(db_session)
    clusters = service.list_work_clusters(
        project_id=project_ctx.project.id,
        viewer_user_id=project_ctx.principal.user_id,
        has_project_manage=has_manage,
    )
    result = [WorkClusterResponse.model_validate(c) for c in clusters]
    local_response_cache.set(
        cache_key, [c.model_dump(mode="json") for c in result], ttl_seconds=60
    )
    return result


@router.get(
    "/projects/{project_id}/relationships/work-clusters/{cluster_id}",
    response_model=WorkClusterResponse,
    status_code=status.HTTP_200_OK,
    summary="Get detailed breakdown for one technical work cluster",
)
def get_work_cluster_detail(
    cluster_id: str,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("project.read"))],
    db_session: Annotated[Session, Depends(get_db_session)],
) -> WorkClusterResponse:
    """Return contributor and contribution breakdown for a specific work cluster."""
    service = WorkGroupingService(db_session)
    clusters = service.list_work_clusters(
        project_id=project_ctx.project.id,
        viewer_user_id=project_ctx.principal.user_id,
        has_project_manage=project_ctx.has_permission("project.manage"),
    )
    match = next(
        (c for c in clusters if c["cluster_id"] == cluster_id or c["name"].lower() == cluster_id.lower()),
        None,
    )
    if match is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Work cluster '{cluster_id}' not found or inaccessible.",
        )
    return WorkClusterResponse.model_validate(match)


@router.post(
    "/projects/{project_id}/relationships/work-clusters/rebuild",
    response_model=WorkClusterRebuildResponse,
    status_code=status.HTTP_200_OK,
    summary="Rebuild evidence-based work clusters from persisted attributions and evidence",
)
def rebuild_work_clusters(
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("project.read"))],
    db_session: Annotated[Session, Depends(get_db_session)],
) -> WorkClusterRebuildResponse:
    """Persist deterministic WorkCluster entities and relationships in PostgreSQL."""
    service = WorkGroupingService(db_session)
    result = service.rebuild_work_clusters(
        organisation_id=project_ctx.project.organisation_id,
        project_id=project_ctx.project.id,
        triggered_by_user_id=project_ctx.principal.user_id,
    )
    _invalidate_project_graph_caches(project_ctx.project.id)
    db_session.commit()
    return WorkClusterRebuildResponse.model_validate(result)


# ==============================================================================
# Parameterized Relationship Lookup & Review (MUST BE LAST ROUTE IN MODULE)
# ==============================================================================


@router.get(
    "/projects/{project_id}/relationships/{relationship_id}",
    response_model=KnowledgeRelationshipResponse,
    status_code=status.HTTP_200_OK,
    summary="Get single relationship details and provenance",
)
def get_relationship_detail(
    relationship_id: uuid.UUID,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("project.read"))],
    db_session: Annotated[Session, Depends(get_db_session)],
) -> KnowledgeRelationshipResponse:
    """Return single relationship detail; fails closed if evidence is restricted."""
    repo = RelationshipRepository(db_session)
    has_manage = project_ctx.has_permission("project.manage")
    rel, links, denied = repo.get_accessible_relationship(
        relationship_id,
        project_id=project_ctx.project.id,
        viewer_user_id=project_ctx.principal.user_id,
        has_project_manage=has_manage,
    )
    if rel is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Relationship {relationship_id} not found in project.",
        )
    if denied:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="SOURCE_ACCESS_DENIED: All supporting evidence links are restricted.",
        )

    return KnowledgeRelationshipResponse.model_validate(rel)


@router.get(
    "/projects/{project_id}/relationships/{relationship_id}/evidence",
    response_model=list[RelationshipEvidenceLinkResponse],
    status_code=status.HTTP_200_OK,
    summary="Get supporting evidence links for a relationship",
)
def get_relationship_evidence(
    relationship_id: uuid.UUID,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("project.read"))],
    db_session: Annotated[Session, Depends(get_db_session)],
) -> list[RelationshipEvidenceLinkResponse]:
    """Return supporting evidence links accessible to caller."""
    repo = RelationshipRepository(db_session)
    has_manage = project_ctx.has_permission("project.manage")
    rel, links, denied = repo.get_accessible_relationship(
        relationship_id,
        project_id=project_ctx.project.id,
        viewer_user_id=project_ctx.principal.user_id,
        has_project_manage=has_manage,
    )
    if rel is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Relationship {relationship_id} not found.",
        )
    if denied:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="SOURCE_ACCESS_DENIED: Supporting evidence is restricted.",
        )

    return [RelationshipEvidenceLinkResponse.model_validate(link) for link in links]


@router.post(
    "/projects/{project_id}/relationships/{relationship_id}/submit-for-review",
    response_model=KnowledgeRelationshipResponse,
    status_code=status.HTTP_200_OK,
    summary="Submit review decision for a relationship",
)
def submit_relationship_review(
    relationship_id: uuid.UUID,
    project_ctx: Annotated[ProjectContext, Depends(require_project_permission("project.manage"))],
    db_session: Annotated[Session, Depends(get_db_session)],
    payload: Annotated[RelationshipReviewRequest, Body()],
) -> KnowledgeRelationshipResponse:
    """Verify, reject, dispute, or request evidence for candidate relationship."""
    repo = RelationshipRepository(db_session)
    try:
        updated = repo.review_relationship(
            relationship_id,
            user_id=project_ctx.principal.user_id,
            action=payload.action,
            note=payload.note,
        )
        _invalidate_project_graph_caches(project_ctx.project.id)
        db_session.commit()
        return KnowledgeRelationshipResponse.model_validate(updated)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
