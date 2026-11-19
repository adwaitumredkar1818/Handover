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


def test_postgresql_tool_idempotency_survives_redis_loss() -> None:
    """Verify that PostgreSQL idempotency gate prevents duplicate execution even after Redis wipe."""
    from app.core.config import get_settings
    from app.db.session import create_db_engine, create_session_factory
    import uuid

    settings = get_settings()
    engine = create_db_engine(settings)
    sf = create_session_factory(engine)
    ToolRegistry.set_session_factory(sf)

    user_id = uuid.UUID("df938f1c-d4ba-43e1-a76e-1874ca7d021a")
    org_id = uuid.UUID("ee03ecd4-eece-4918-8b6c-21cfd4735a91")
    proj_id = uuid.UUID("5b30f757-4e93-41c1-b0f3-02f5950af30b")

    mock_ctx = MagicMock()
    mock_ctx.has_permission.return_value = True
    mock_ctx.principal.user.id = user_id
    mock_ctx.principal.user.email = "test@example.com"
    mock_ctx.project.id = proj_id
    mock_ctx.project.organisation_id = org_id

    unique_task_id = f"task-durable-{uuid.uuid4().hex[:8]}"
    req = ToolCallRequest(
        tool_id="approve_handover_task",
        tool_name="Approve Handover Task",
        arguments={"task_id": unique_task_id},
        is_consequential=True,
        approved=True,
    )

    # 1. First execution must succeed
    res1 = ToolRegistry.execute_tool(request=req, project_ctx=mock_ctx)
    assert res1.success is True, f"First execution failed: {res1.error_message}"
    assert res1.data["task_id"] == unique_task_id

    # 2. Simulate Redis crash / loss and memory reset
    ToolRegistry._executed_approvals.clear()
    r = ToolRegistry._get_redis()
    if r:
        fp = ToolRegistry._compute_approval_fingerprint(
            tool_id="approve_handover_task",
            user_id=str(user_id),
            project_id=str(proj_id),
            arguments={"task_id": unique_task_id},
        )
        r.delete(f"tool:idempotency:{fp}")

    # 3. Second execution attempt MUST be rejected by PostgreSQL authoritative idempotency gate
    res2 = ToolRegistry.execute_tool(request=req, project_ctx=mock_ctx)
    assert res2.success is False
    assert "Idempotency gate" in res2.error_message or "currently SUCCEEDED" in res2.error_message

