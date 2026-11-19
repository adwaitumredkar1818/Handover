import uuid
import asyncio
from app.core.config import get_settings
from app.db.session import create_db_engine, create_session_factory
from app.services.ai.registry import InvestigationRuntimeRegistry
from app.services.ai.state import InvestigationState, InvestigationStatus

settings = get_settings()
engine = create_db_engine(settings)
session_factory = create_session_factory(engine)

conv_id = uuid.UUID('6223c9df-3c15-4093-a53e-0bc00adf43fb')
org_id = uuid.UUID('ee03ecd4-eece-4918-8b6c-21cfd4735a91')
proj_id = uuid.UUID('5b30f757-4e93-41c1-b0f3-02f5950af30b')
user_id = uuid.UUID('df938f1c-d4ba-43e1-a76e-1874ca7d021a')
inv_id = uuid.uuid4()

reg = InvestigationRuntimeRegistry()
reg._session_factory = session_factory
state = InvestigationState(
    investigation_id=inv_id,
    conversation_id=conv_id,
    project_id=proj_id,
    organisation_id=org_id,
    user_id=user_id,
    user_role='admin',
    query='Test recovery query',
    status=InvestigationStatus.RUNNING,
    current_node='plan_and_decompose',
)

async def test_recovery():
    print(f"Registering investigation {inv_id}...")
    reg.register(state)
    await reg.emit_event(inv_id, 'plan_created', {'plan': 'step 1, step 2'})
    
    # update state to multi_source_retrieval
    state.current_node = 'multi_source_retrieval'
    state.tokens_consumed = 150
    reg.update_state(state)
    await reg.emit_event(inv_id, 'retrieval_started', {'query': 'db schema'})

    # Wipe in-memory and Redis
    reg._states.clear()
    reg._event_history.clear()
    reg._sequence_counters.clear()
    r = reg._get_redis()
    if r:
        r.delete(f'investigation:{inv_id}:state')
        r.delete(f'investigation:{inv_id}:events')
        print('Redis and In-Memory completely wiped!')

    # Now recover from PostgreSQL!
    recovered_state = reg.get_state(inv_id)
    assert recovered_state is not None, 'State failed to recover from PG'
    assert recovered_state.current_node == 'multi_source_retrieval', f'Expected multi_source_retrieval, got {recovered_state.current_node}'
    assert recovered_state.tokens_consumed == 150, f'Expected 150, got {recovered_state.tokens_consumed}'
    print(f'State recovered successfully from PG! Node: {recovered_state.current_node}')

    recovered_events = reg.get_event_history(inv_id)
    assert len(recovered_events) == 2, f'Expected 2 events, got {len(recovered_events)}'
    print(f'Events recovered successfully from PG! Count: {len(recovered_events)}')
    for ev in recovered_events:
        print(f'  Event #{ev.sequence_number}: {ev.event_type} -> {ev.payload}')

    print("ALL DURABILITY CHECKS PASSED: PostgreSQL is authoritative and independent of Redis!")

if __name__ == '__main__':
    asyncio.run(test_recovery())
