"""Integration tests for Tool Registry and Consequential Operation Approvals."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from app.core.exceptions import ForbiddenError
from app.services.ai.state import ToolCallRequest
from app.services.ai.tools import ToolRegistry


def test_tool_registry_read_only_execution() -> None:
    """Verify that read-only tools execute autonomously when authorized."""
    mock_ctx = MagicMock()
    mock_ctx.has_permission.return_value = True
    mock_ctx.project.id = uuid.uuid4()

    req = ToolCallRequest(
        tool_id="search_knowledge",
        tool_name="Search Knowledge",
        arguments={"query": "architecture"},
        is_consequential=False,
    )

    res = ToolRegistry.execute_tool(request=req, project_ctx=mock_ctx)
    assert res.success is True
    assert res.data["query"] == "architecture"


def test_consequential_tool_requires_approval() -> None:
    """Verify that consequential operations are rejected without explicit approval."""
    mock_ctx = MagicMock()
    mock_ctx.has_permission.return_value = True

    # Without approval
    req_unapproved = ToolCallRequest(
        tool_id="approve_handover_task",
        tool_name="Approve Handover Task",
        arguments={"task_id": "task-123"},
        is_consequential=True,
        approved=None,
    )
    res_unapproved = ToolRegistry.execute_tool(request=req_unapproved, project_ctx=mock_ctx)
    assert res_unapproved.success is False
    assert "explicit human approval" in res_unapproved.error_message

    # With approval
    req_approved = ToolCallRequest(
        tool_id="approve_handover_task",
        tool_name="Approve Handover Task",
        arguments={"task_id": "task-123"},
        is_consequential=True,
        approved=True,
    )
    res_approved = ToolRegistry.execute_tool(request=req_approved, project_ctx=mock_ctx)
    assert res_approved.success is True
    assert res_approved.data["task_id"] == "task-123"


def test_tool_permission_denial() -> None:
    """Verify that callers lacking required permission raise ForbiddenError."""
    mock_ctx = MagicMock()
    # Caller does not have project.manage
    mock_ctx.has_permission.side_effect = lambda p: p != "project.manage"

    req = ToolCallRequest(
        tool_id="approve_handover_task",
        tool_name="Approve Handover Task",
        arguments={"task_id": "task-123"},
        is_consequential=True,
        approved=True,
    )
    with pytest.raises(ForbiddenError):
        ToolRegistry.execute_tool(request=req, project_ctx=mock_ctx)
