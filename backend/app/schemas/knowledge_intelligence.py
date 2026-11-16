"""Pydantic schemas for Module 3: Knowledge Intelligence APIs."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.schemas.common import BaseSchema
from app.schemas.knowledge import (
    KnowledgeExtractionRunResponse,
)


class DomainCoverageMetric(BaseSchema):
    """Granular coverage, confidence, and verification breakdown for one canonical domain."""

    domain_id: str
    code: int
    display_name: str
    description: str
    item_count: int = 0
    verified_count: int = 0
    pending_review_count: int = 0
    rejected_count: int = 0
    stale_count: int = 0
    high_confidence_count: int = 0
    medium_confidence_count: int = 0
    low_confidence_count: int = 0
    uncertain_count: int = 0
    completeness_score: float = 0.0
    sources_breakdown: dict[str, int] = Field(default_factory=dict)
    last_extracted_at: datetime | None = None


class KnowledgeIntelligenceDomainsResponse(BaseSchema):
    """All eight canonical project knowledge domains with live coverage telemetry."""

    domains: list[DomainCoverageMetric]
    total_domains: int = 8
    active_domains_count: int = 0


class KnowledgeIntelligenceSummaryResponse(BaseSchema):
    """Executive project knowledge intelligence summary for dashboard and audits."""

    project_id: uuid.UUID
    total_findings: int
    verified_findings: int
    pending_verification: int
    rejected_findings: int
    stale_findings: int
    overall_confidence_score: float
    overall_readiness_pct: float
    domain_coverage: list[DomainCoverageMetric]
    active_runs_count: int
    latest_run: KnowledgeExtractionRunResponse | None = None


class KnowledgeIntelligenceExtractRequest(BaseSchema):
    """Trigger or schedule knowledge extraction across specified domains."""

    evidence_ids: list[uuid.UUID] | None = Field(default=None, max_length=100)
    domains: list[str] | None = Field(default=None, max_length=16)
    force_rerun: bool = False
    include_synthetic: bool = False


class KnowledgeGraphNode(BaseSchema):
    """Projected node for Technology Stack, System Architecture, or Features & Workflows."""

    id: uuid.UUID
    entity_type: str
    label: str
    description: str | None = None
    category: str | None = None
    status: str = "documented"
    verification_status: str = "pending"
    evidence_count: int = 0
    evidence_ids: list[uuid.UUID] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    last_observed_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeGraphEdge(BaseSchema):
    """Directed evidence-backed relationship edge for Knowledge Intelligence graphs."""

    id: uuid.UUID
    source: uuid.UUID
    target: uuid.UUID
    relationship_type: str
    label: str
    evidence_basis: str
    verification_status: str = "pending"
    confidence_score: float = 1.0
    evidence_ids: list[uuid.UUID] = Field(default_factory=list)


class KnowledgeGraphSummary(BaseSchema):
    """Counts and category breakdown for a Knowledge Intelligence graph projection."""

    node_count: int = 0
    edge_count: int = 0
    categories: dict[str, int] = Field(default_factory=dict)


class KnowledgeGraphProjectionResponse(BaseSchema):
    """Complete bounded graph projection returned by Knowledge Intelligence graph endpoints."""

    graph_type: Literal["technology-stack", "system-architecture", "features-workflows"]
    project_id: uuid.UUID
    nodes: list[KnowledgeGraphNode] = Field(default_factory=list)
    edges: list[KnowledgeGraphEdge] = Field(default_factory=list)
    summary: KnowledgeGraphSummary
    next_cursor: str | None = None


class KnowledgeGraphEvidenceRef(BaseSchema):
    """Authorised source reference attached to a Knowledge Intelligence graph node."""

    evidence_id: uuid.UUID
    title: str
    source_type: str
    source_url: str | None = None
    supporting_excerpt: str | None = None


class KnowledgeGraphNodeDetailResponse(BaseSchema):
    """Detailed node inspection payload with authorised provenance and adjacent edges."""

    graph_type: str
    project_id: uuid.UUID
    node: KnowledgeGraphNode
    adjacent_edges: list[KnowledgeGraphEdge] = Field(default_factory=list)
    related_nodes: list[KnowledgeGraphNode] = Field(default_factory=list)
    evidence_refs: list[KnowledgeGraphEvidenceRef] = Field(default_factory=list)
