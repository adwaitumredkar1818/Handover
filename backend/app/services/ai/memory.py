"""Hybrid Working Memory Service for Project Intelligence Engine.

Maintains distinction between:
1. Authoritative Project Knowledge (PostgreSQL canonical tables & ChromaDB document chunks).
2. Derived Assistant Working Memory (AI-synthesized insights, evolving hypotheses, decisions).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import AssistantResponseMode
from app.models.knowledge import KnowledgeItem
from app.schemas.assistant import AssistantCitationResponse
from app.services.rbac import ProjectContext

logger = logging.getLogger("app.services.ai.memory")


class ProjectDerivedMemoryItem(BaseModel):
    """An AI-synthesized observation or insight with strict evidence provenance."""

    memory_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: uuid.UUID
    topic: str
    insight_text: str
    confidence: float = 1.0
    is_hypothesis: bool = False
    supporting_citations: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = 1


class ProjectWorkingMemoryService:
    """Manages ephemeral and persistent working memory for ongoing project investigations."""

    def __init__(self, session: Session) -> None:
        self.session = session
        # Ephemeral project memory store keyed by project_id
        self._memory_cache: dict[uuid.UUID, list[ProjectDerivedMemoryItem]] = {}

    def get_working_memory(
        self,
        project_id: uuid.UUID,
        topic: str | None = None,
    ) -> list[ProjectDerivedMemoryItem]:
        """Fetch active derived working memory items for a project."""
        items = self._memory_cache.get(project_id, [])
        if topic:
            return [m for m in items if topic.lower() in m.topic.lower()]
        return items

    def record_derived_insight(
        self,
        *,
        project_id: uuid.UUID,
        topic: str,
        insight_text: str,
        supporting_citations: list[str],
        confidence: float = 1.0,
        is_hypothesis: bool = False,
    ) -> ProjectDerivedMemoryItem:
        """Record an evidence-backed insight into working memory without overwriting canonical truth."""
        item = ProjectDerivedMemoryItem(
            project_id=project_id,
            topic=topic,
            insight_text=insight_text,
            supporting_citations=supporting_citations,
            confidence=confidence,
            is_hypothesis=is_hypothesis,
        )
        if project_id not in self._memory_cache:
            self._memory_cache[project_id] = []
        self._memory_cache[project_id].append(item)
        logger.info(
            "Recorded derived working memory item for project %s (topic: %s)",
            project_id,
            topic,
        )
        return item
