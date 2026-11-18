import asyncio
import uuid
from app.core.config import get_settings
from app.db.session import create_db_engine, create_session_factory
from app.models.assistant import AssistantConversation
from app.models.user import User
from app.repositories.user import UserRepository
from app.repositories.rbac import RbacRepository
from app.repositories.organisation import OrganisationRepository
from app.repositories.project import ProjectRepository
from app.services.rbac import RbacService, ProjectContext
from app.services.ai.orchestrator import ProjectIntelligenceOrchestrator
from app.services.ai.state import InvestigationState, InvestigationStatus, AssistantResponseMode
from app.services.ai.registry import InvestigationRuntimeRegistry
from sqlalchemy import select

async def run_multi_agent_investigation():
    settings = get_settings()
    engine = create_db_engine(settings)
    session_factory = create_session_factory(engine)
    session = session_factory()

    try:
        project_id = uuid.UUID("5b30f757-4e93-41c1-b0f3-02f5950af30b")
        user_id = uuid.UUID("df938f1c-d4ba-43e1-a76e-1874ca7d021a")
        
        # Build authenticated ProjectContext via RbacService
        rbac_repo = RbacRepository(session)
        user_repo = UserRepository(session)
        org_repo = OrganisationRepository(session)
        proj_repo = ProjectRepository(session)
        rbac_service = RbacService(
            db_session=session,
            rbac_repository=rbac_repo,
            user_repository=user_repo,
            organisation_repository=org_repo,
            project_repository=proj_repo,
        )

        user = user_repo.get_by_id(user_id)
        assert user is not None, "User not found"
        principal = rbac_service.resolve_principal(user=user, session_family_id=uuid.uuid4())
        project_ctx = rbac_service.resolve_project_context(
            project_id=project_id,
            principal=principal,
            require_explicit_membership=False,
        )
        print(f"ProjectContext initialized: User={project_ctx.principal.user.email}, Role={project_ctx.project_role.name if project_ctx.project_role else 'None'}")

        # Fetch or create conversation
        conv = session.scalars(
            select(AssistantConversation).where(
                AssistantConversation.project_id == project_id
            )
        ).first()
        if not conv:
            conv = AssistantConversation(
                project_id=project_id,
                organisation_id=project_ctx.project.organisation_id,
                created_by_user_id=user_id,
                title="Multi-Agent Investigation Test",
            )
            session.add(conv)
            session.commit()

        conversation_id = conv.id
        print(f"Conversation ID: {conversation_id}")

        query = "What architectural decisions and choices were made regarding the database schema and PostgreSQL?"
        print(f"Query: '{query}'")

        orchestrator = ProjectIntelligenceOrchestrator(
            session=session,
            settings=settings,
        )
        
        # Subscribe to SSE events to monitor live stream
        inv_id = uuid.uuid4()
        queue = await orchestrator.registry.subscribe(inv_id)

        async def monitor_events():
            captured = []
            while True:
                ev = await queue.get()
                captured.append(ev)
                print(f"  [STREAM #{ev.sequence_number}] {ev.event_type}: {str(ev.payload)[:100]}")
                if ev.event_type in ("investigation_completed", "investigation_failed"):
                    break
            return captured

        monitor_task = asyncio.create_task(monitor_events())

        state = InvestigationState(
            investigation_id=inv_id,
            conversation_id=conversation_id,
            project_id=project_id,
            organisation_id=project_ctx.project.organisation_id,
            user_id=user_id,
            user_role=project_ctx.project_role.name if project_ctx.project_role else "member",
            query=query,
            response_mode=AssistantResponseMode.STANDARD,
        )

        # Run investigation
        final_state = await orchestrator.run_investigation(
            state=state,
            project_ctx=project_ctx,
        )

        events = await monitor_task

        print("\n================ INVESTIGATION RESULT ================")
        print(f"Status: {final_state.status.value}")
        print(f"Current Node: {final_state.current_node}")
        print(f"Agent Findings Count: {len(final_state.agent_findings)}")
        for f in final_state.agent_findings:
            print(f"  - Agent: {f.agent_id} ({f.agent_name})")
            print(f"    Claim: {f.claim_text}")
            print(f"    Confidence: {f.confidence}")
            print(f"    Citations: {f.supporting_citations}")

        print(f"\nFinal Answer Preview:\n{final_state.raw_answer[:400]}...")
        print(f"\nValidated Citations: {len(final_state.validated_citations)}")
        for c in final_state.validated_citations:
            print(f"  - [{c.citation_label}] {c.source_title} ({c.source_provider})")

        # Verify multi-agent assertions
        agent_ids = [f.agent_id for f in final_state.agent_findings]
        assert "decision_agent" in agent_ids, f"Expected decision_agent in {agent_ids}"
        assert "database_agent" in agent_ids, f"Expected database_agent in {agent_ids}"
        assert len(final_state.agent_findings) >= 2, f"Expected at least 2 findings, got {len(final_state.agent_findings)}"
        assert final_state.status == InvestigationStatus.COMPLETED, f"Expected COMPLETED, got {final_state.status}"
        print("\nSUCCESS: Multi-agent collaboration with decision_agent and database_agent verified end-to-end!")

    finally:
        session.close()

if __name__ == "__main__":
    asyncio.run(run_multi_agent_investigation())
