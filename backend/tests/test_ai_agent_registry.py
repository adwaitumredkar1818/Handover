"""Integration tests for Permanent Agent Registry and Dynamic Worker Factory."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from app.core.exceptions import ForbiddenError
from app.services.ai.agent_factory import DynamicAgentFactory
from app.services.ai.agent_registry import AgentRegistry


def test_agent_registry_contains_approved_library() -> None:
    """Verify that all 10 canonical specialized agents are registered with immutable specifications."""
    agents = AgentRegistry.list_all()
    assert len(agents) >= 10

    expected_agents = [
        "knowledge_agent",
        "engineering_agent",
        "project_agent",
        "decision_agent",
        "security_agent",
        "database_agent",
        "api_agent",
        "infrastructure_agent",
        "analysis_agent",
        "planning_agent",
    ]
    registered_ids = [a.agent_id for a in agents]
    for exp_id in expected_agents:
        assert exp_id in registered_ids
        agent_def = AgentRegistry.get(exp_id)
        assert agent_def is not None
        assert agent_def.name != ""
        assert agent_def.system_instructions != ""


def test_dynamic_agent_factory_permission_boundary() -> None:
    """Verify that factory refuses to instantiate agents requiring ungranted permissions."""
    # Mock project context without assistant.admin permission
    mock_ctx = MagicMock()
    mock_ctx.has_permission.side_effect = lambda p: p == "assistant.chat"

    # Knowledge agent requires assistant.chat -> should succeed
    worker = DynamicAgentFactory.create_worker(agent_id="knowledge_agent", project_ctx=mock_ctx)
    assert worker.definition.agent_id == "knowledge_agent"

    # Security agent requires assistant.admin -> should fail closed with ForbiddenError
    with pytest.raises(ForbiddenError):
        DynamicAgentFactory.create_worker(agent_id="security_agent", project_ctx=mock_ctx)
