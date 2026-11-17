"""Integration tests for Deep Research workflows and interactive clarification."""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import MagicMock

from app.models.enums import AssistantResponseMode
from app.services.ai.deep_research import DeepResearchWorkflow
from app.services.ai.registry import InvestigationRuntimeRegistry
from app.services.ai.state import InvestigationState, InvestigationStatus


def test_deep_research_clarification_gate() -> None:
    """Verify that ambiguous broad queries pause the investigation in WAITING_FOR_USER state."""
    async def _run():
        registry = InvestigationRuntimeRegistry()
        inv_id = uuid.uuid4()
        state = InvestigationState(
            investigation_id=inv_id,
            conversation_id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            organisation_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            user_role="manager",
            query="Should we investigate all repositories across the organization?",
            response_mode=AssistantResponseMode.DEEP_RESEARCH,
        )
        registry.register(state)

        mock_ctx = MagicMock()
        mock_ctx.has_permission.return_value = True

        updated_state = await DeepResearchWorkflow.execute_research_cycle(state, mock_ctx, registry)
        assert updated_state.status == InvestigationStatus.WAITING_FOR_USER

        # Verify clarification event was emitted
        events = registry.get_event_history(inv_id)
        assert any(e.event_type == "clarification_required" for e in events)

    asyncio.run(_run())
