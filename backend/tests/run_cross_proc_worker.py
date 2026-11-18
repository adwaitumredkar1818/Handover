import sys
import uuid
from app.core.config import get_settings
from app.db.session import create_db_engine, create_session_factory
from app.services.ai.tools import ToolRegistry, ToolDefinition
from app.services.ai.state import ToolCallRequest

target_ver = sys.argv[1]

settings = get_settings()
engine = create_db_engine(settings)
session_factory = create_session_factory(engine)
ToolRegistry.set_session_factory(session_factory)

def mock_handler(project_ctx, target_version: str):
    return {"migration": "applied", "version": target_version}

tool_def = ToolDefinition(
    tool_id="apply_cross_proc_migration",
    name="Apply Migration",
    description="Cross proc migration tool",
    is_consequential=True,
    required_permission="assistant.chat",
    argument_schema={"target_version": {"type": "string"}}
)
ToolRegistry.register_tool(tool_def, mock_handler)

class MockUser:
    id = uuid.UUID("df938f1c-d4ba-43e1-a76e-1874ca7d021a")
    email = "alice@example.com"
class MockProject:
    id = uuid.UUID("0f73217a-dbbd-4ef6-92a9-16bace7aaba0")
    organisation_id = uuid.UUID("ee03ecd4-eece-4918-8b6c-21cfd4735a91")
class MockPrincipal:
    user = MockUser()
class MockOrg:
    id = uuid.UUID("ee03ecd4-eece-4918-8b6c-21cfd4735a91")
class MockProjectContext:
    principal = MockPrincipal()
    project = MockProject()
    organisation = MockOrg()
    def has_permission(self, p): return True

req = ToolCallRequest(
    call_id=str(uuid.uuid4()),
    tool_id="apply_cross_proc_migration",
    tool_name="Apply Migration",
    arguments={"target_version": target_ver},
    approved=True
)

res = ToolRegistry.execute_tool(request=req, project_ctx=MockProjectContext())
print(f"PROC_EXECUTION_RESULT: success={res.success} error={res.error_message}")
