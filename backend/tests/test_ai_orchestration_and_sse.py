"""Integration tests for Project Intelligence Engine SSE Streaming and Investigation Lifecycle."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.models.enums import AssistantResponseMode
from app.services.ai.events import SSEEventFrame
from app.services.ai.registry import InvestigationRuntimeRegistry
from app.services.ai.state import InvestigationPlanStep, InvestigationState, InvestigationStatus, PlanStepStatus


def test_sse_event_frame_formatting() -> None:
    """Verify W3C compliance of serialized SSE event frames."""
    frame = SSEEventFrame(
        investigation_id="inv-123",
        sequence_number=1,
        event_type="test_event",
        payload={"message": "hello world"},
    )
    raw_sse = frame.to_sse_format()
    assert "event: test_event\n" in raw_sse
    assert "id: 1\n" in raw_sse
    assert "data: {" in raw_sse
    assert '"message": "hello world"' in raw_sse
    assert raw_sse.endswith("\n\n")


def test_investigation_runtime_registry_lifecycle() -> None:
    """Verify in-flight state registration, monotonic event sequencing, and subscriber fanout."""
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
            query="What is the platform auth model?",
        )

        registry.register(state)
        assert registry.get_state(inv_id) is not None
        assert registry.get_state(inv_id).query == "What is the platform auth model?"

        # Subscribe queue
        sub_queue = await registry.subscribe(inv_id)

        # Emit two events
        f1 = await registry.emit_event(inv_id, "node_started", {"node": "init"})
        f2 = await registry.emit_event(inv_id, "token_delta", {"delta": "test"})

        assert f1.sequence_number == 1
        assert f2.sequence_number == 2

        # Subscriber receives both
        rec1 = await asyncio.wait_for(sub_queue.get(), timeout=1.0)
        rec2 = await asyncio.wait_for(sub_queue.get(), timeout=1.0)

        assert rec1.event_type == "node_started"
        assert rec2.event_type == "token_delta"

        # Verify Last-Event-ID replay
        history = registry.get_event_history(inv_id, since_sequence=1)
        assert len(history) == 1
        assert history[0].sequence_number == 2

        await registry.unsubscribe(inv_id, sub_queue)

    asyncio.run(_run())
