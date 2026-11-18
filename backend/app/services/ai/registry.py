"""Durable registry tracking active investigation sessions, persistent checkpoints, and SSE events."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.core.config import get_settings
from app.core.cache.redis_client import RedisConnectionManager
from app.db.session import create_db_engine, create_session_factory
from app.models.assistant import AssistantMessage
from app.models.enums import AssistantAnswerStatus, AssistantSenderType
from app.services.ai.events import SSEEventFrame
from app.services.ai.state import InvestigationState, InvestigationStatus

logger = logging.getLogger("app.services.ai.registry")


class InvestigationRuntimeRegistry:
    """Authoritative durable registry tracking in-flight and persisted investigations.

    PostgreSQL is the authoritative durable store for investigation lifecycle,
    intermediate checkpoints, and event history. Redis is used for:
    1. Active live event pubsub dispatch.
    2. Ephemeral high-throughput caching.
    3. Distributed locking and coordination.
    """

    _instance: InvestigationRuntimeRegistry | None = None

    def __init__(self) -> None:
        self._states: dict[uuid.UUID, InvestigationState] = {}
        self._event_history: dict[uuid.UUID, list[SSEEventFrame]] = defaultdict(list)
        self._subscribers: dict[uuid.UUID, list[asyncio.Queue[SSEEventFrame]]] = defaultdict(list)
        self._sequence_counters: dict[uuid.UUID, int] = defaultdict(int)
        self._lock = asyncio.Lock()
        
        # Redis client for runtime acceleration & distributed coordination
        self._redis_mgr: RedisConnectionManager | None = None
        try:
            settings = get_settings()
            self._redis_mgr = RedisConnectionManager(settings)
            self._redis_mgr.initialize()
        except Exception as exc:
            logger.warning("Could not initialize Redis client for durable registry: %s", exc)

        # Synchronous session factory for PostgreSQL durable checkpoints
        self._session_factory = None
        try:
            settings = get_settings()
            engine = create_db_engine(settings)
            self._session_factory = create_session_factory(engine)
        except Exception as exc:
            logger.warning("Could not initialize DB session factory for durable registry: %s", exc)

    @classmethod
    def get_instance(cls) -> InvestigationRuntimeRegistry:
        if cls._instance is None:
            cls._instance = InvestigationRuntimeRegistry()
        return cls._instance

    def _get_redis(self):
        if self._redis_mgr:
            try:
                return self._redis_mgr.get_client()
            except Exception:
                return None
        return None

    def _persist_pg_checkpoint(self, state: InvestigationState, latest_event: SSEEventFrame | None = None) -> None:
        """Durable transactional checkpoint update in PostgreSQL."""
        if not self._session_factory:
            return
        session = self._session_factory()
        try:
            from sqlalchemy import text

            inv_str = str(state.investigation_id)
            # Find existing checkpoint message for this investigation
            msg = session.scalars(
                select(AssistantMessage)
                .where(
                    AssistantMessage.conversation_id == state.conversation_id,
                    text("structured_payload_json->>'investigation_id' = :inv_id"),
                )
                .params(inv_id=inv_str)
            ).first()

            events_payload = [
                {
                    "event_id": e.event_id,
                    "investigation_id": e.investigation_id,
                    "sequence_number": e.sequence_number,
                    "event_type": e.event_type,
                    "timestamp": e.timestamp.isoformat(),
                    "payload": e.payload,
                }
                for e in self._event_history.get(state.investigation_id, [])
            ]

            checkpoint_payload = json.loads(
                json.dumps(
                    {
                        "investigation_id": inv_str,
                        "status": state.status.value,
                        "current_node": state.current_node,
                        "iteration_count": state.iteration_count,
                        "plan_steps": [s.model_dump() for s in state.plan_steps],
                        "agent_findings": [f.model_dump() for f in state.agent_findings],
                        "claims": [c.model_dump() for c in state.claims],
                        "tokens_consumed": state.tokens_consumed,
                        "query": state.query,
                        "response_mode": state.response_mode.value,
                        "raw_answer": state.raw_answer,
                        "error_message": state.error_message,
                        "citations_manifest": [c.model_dump() for c in state.citations_manifest],
                        "event_history": events_payload,
                        "updated_at": state.updated_at.isoformat(),
                    },
                    default=str,
                )
            )

            if not msg:
                # Insert initial checkpoint record
                msg = AssistantMessage(
                    conversation_id=state.conversation_id,
                    organisation_id=state.organisation_id,
                    project_id=state.project_id,
                    sender_type=AssistantSenderType.SYSTEM.value,
                    content=f"Investigation Checkpoint: {state.current_node}",
                    answer_status=AssistantAnswerStatus.ANSWERED.value,
                    structured_payload_json=checkpoint_payload,
                )
                session.add(msg)
            else:
                # Update existing checkpoint transactionally
                msg.content = f"Investigation Checkpoint: {state.current_node}"
                msg.structured_payload_json = checkpoint_payload

            session.commit()
        except Exception as exc:
            session.rollback()
            logger.warning("Failed to persist durable checkpoint to PostgreSQL: %s", exc)
        finally:
            session.close()

    def register(self, state: InvestigationState) -> None:
        self._states[state.investigation_id] = state
        self._sequence_counters[state.investigation_id] = 0
        
        # Persist durable checkpoint in PostgreSQL
        self._persist_pg_checkpoint(state)

        # Ephemeral caching in Redis
        r = self._get_redis()
        if r:
            try:
                key = f"investigation:{state.investigation_id}:state"
                r.set(key, state.model_dump_json(), ex=86400)
            except Exception as exc:
                logger.warning("Failed to persist initial state to Redis: %s", exc)

    def get_state(self, investigation_id: uuid.UUID) -> InvestigationState | None:
        # Check in-memory first
        if investigation_id in self._states:
            return self._states[investigation_id]

        # Check durable Redis store
        r = self._get_redis()
        if r:
            try:
                key = f"investigation:{investigation_id}:state"
                data = r.get(key)
                if data:
                    raw_str = data.decode("utf-8") if isinstance(data, bytes) else str(data)
                    state = InvestigationState.model_validate_json(raw_str)
                    self._states[investigation_id] = state
                    return state
            except Exception as exc:
                logger.warning("Failed to restore investigation state from Redis: %s", exc)

        # Authoritative Fallback: Reconstruct state from PostgreSQL
        if self._session_factory:
            session = self._session_factory()
            try:
                from sqlalchemy import text
                inv_str = str(investigation_id)
                msg = session.scalars(
                    select(AssistantMessage)
                    .where(
                        text("structured_payload_json->>'investigation_id' = :inv_id")
                    )
                    .params(inv_id=inv_str)
                ).first()
                if msg and msg.structured_payload_json:
                    p = msg.structured_payload_json
                    # Reconstruct InvestigationState
                    state = InvestigationState(
                        investigation_id=uuid.UUID(p["investigation_id"]),
                        conversation_id=msg.conversation_id,
                        project_id=msg.project_id,
                        organisation_id=msg.organisation_id,
                        user_id=msg.conversation.created_by_user_id if msg.conversation else uuid.uuid4(),
                        user_role="admin",
                        query=p.get("query", ""),
                        status=InvestigationStatus(p.get("status", "running")),
                        current_node=p.get("current_node", "init"),
                        iteration_count=p.get("iteration_count", 0),
                        plan_steps=p.get("plan_steps", []),
                        agent_findings=p.get("agent_findings", []),
                        claims=p.get("claims", []),
                        tokens_consumed=p.get("tokens_consumed", 0),
                        raw_answer=p.get("raw_answer", ""),
                        error_message=p.get("error_message"),
                    )
                    self._states[investigation_id] = state

                    # Also reconstruct event history if available
                    if "event_history" in p and p["event_history"]:
                        frames = []
                        for ed in p["event_history"]:
                            frames.append(
                                SSEEventFrame(
                                    event_id=ed["event_id"],
                                    investigation_id=ed["investigation_id"],
                                    sequence_number=ed["sequence_number"],
                                    event_type=ed["event_type"],
                                    timestamp=datetime.fromisoformat(ed["timestamp"]),
                                    payload=ed.get("payload", {}),
                                )
                            )
                        self._event_history[investigation_id] = frames
                        self._sequence_counters[investigation_id] = max(
                            (f.sequence_number for f in frames), default=0
                        )

                    return state
            except Exception as exc:
                logger.warning("Failed to recover investigation state from PostgreSQL: %s", exc)
            finally:
                session.close()

        return None

    def update_state(self, state: InvestigationState) -> None:
        state.updated_at = datetime.now(timezone.utc)
        self._states[state.investigation_id] = state

        # Durable PostgreSQL checkpoint
        self._persist_pg_checkpoint(state)

        # Update ephemeral Redis checkpoint
        r = self._get_redis()
        if r:
            try:
                key = f"investigation:{state.investigation_id}:state"
                r.set(key, state.model_dump_json(), ex=86400)
            except Exception as exc:
                logger.warning("Failed to update state in Redis: %s", exc)

    async def emit_event(
        self,
        investigation_id: uuid.UUID,
        event_type: str,
        payload: dict[str, Any],
    ) -> SSEEventFrame:
        """Record an event frame in order and dispatch to all active SSE subscribers."""
        async with self._lock:
            # Sync sequence counter if restoring after restart
            if self._sequence_counters[investigation_id] == 0:
                history = self.get_event_history(investigation_id, since_sequence=0)
                if history:
                    self._sequence_counters[investigation_id] = max(e.sequence_number for e in history)

            self._sequence_counters[investigation_id] += 1
            seq = self._sequence_counters[investigation_id]

            frame = SSEEventFrame(
                investigation_id=str(investigation_id),
                sequence_number=seq,
                event_type=event_type,
                payload=payload,
            )
            self._event_history[investigation_id].append(frame)

            # Persist event frame to Redis list for durable replay
            r = self._get_redis()
            if r:
                try:
                    events_key = f"investigation:{investigation_id}:events"
                    frame_json = json.dumps(
                        {
                            "event_id": frame.event_id,
                            "investigation_id": frame.investigation_id,
                            "sequence_number": frame.sequence_number,
                            "event_type": frame.event_type,
                            "timestamp": frame.timestamp.isoformat(),
                            "payload": frame.payload,
                        },
                        default=str,
                    )
                    r.rpush(events_key, frame_json)
                    r.expire(events_key, 86400)
                except Exception as exc:
                    logger.warning("Failed to persist event to Redis: %s", exc)

            # Dispatch to live listener queues
            for queue in self._subscribers.get(investigation_id, []):
                await queue.put(frame)

            # Persist event history update to durable PostgreSQL checkpoint
            if investigation_id in self._states:
                self._persist_pg_checkpoint(self._states[investigation_id])

            return frame

    def get_event_history(
        self,
        investigation_id: uuid.UUID,
        since_sequence: int = 0,
    ) -> list[SSEEventFrame]:
        """Retrieve historical events for Last-Event-ID replay upon client reconnection.

        Ensures full durability across process restarts by querying Redis buffer if
        in-memory history is empty.
        """
        events = self._event_history.get(investigation_id, [])

        # If in-memory is empty (e.g. after restart), load from Redis first
        if not events:
            r = self._get_redis()
            if r:
                try:
                    events_key = f"investigation:{investigation_id}:events"
                    items = r.lrange(events_key, 0, -1)
                    loaded = []
                    for it in items:
                        raw_str = it.decode("utf-8") if isinstance(it, bytes) else str(it)
                        d = json.loads(raw_str)
                        loaded.append(
                            SSEEventFrame(
                                event_id=d["event_id"],
                                investigation_id=d["investigation_id"],
                                sequence_number=int(d["sequence_number"]),
                                event_type=d["event_type"],
                                timestamp=datetime.fromisoformat(d["timestamp"]),
                                payload=d.get("payload", {}),
                            )
                        )
                    if loaded:
                        self._event_history[investigation_id] = loaded
                        events = loaded
                except Exception as exc:
                    logger.warning("Failed to read events from Redis: %s", exc)

        # Authoritative fallback: load from PostgreSQL durable checkpoint if still empty
        if not events and self._session_factory:
            session = self._session_factory()
            try:
                from sqlalchemy import text
                inv_str = str(investigation_id)
                msg = session.scalars(
                    select(AssistantMessage)
                    .where(
                        text("structured_payload_json->>'investigation_id' = :inv_id")
                    )
                    .params(inv_id=inv_str)
                ).first()
                if msg and msg.structured_payload_json and "event_history" in msg.structured_payload_json:
                    hist_data = msg.structured_payload_json["event_history"]
                    loaded = []
                    for d in hist_data:
                        loaded.append(
                            SSEEventFrame(
                                event_id=d["event_id"],
                                investigation_id=d["investigation_id"],
                                sequence_number=int(d["sequence_number"]),
                                event_type=d["event_type"],
                                timestamp=datetime.fromisoformat(d["timestamp"]),
                                payload=d.get("payload", {}),
                            )
                        )
                    if loaded:
                        self._event_history[investigation_id] = loaded
                        events = loaded
            except Exception as exc:
                logger.warning("Failed to recover event history from PostgreSQL: %s", exc)
            finally:
                session.close()

        if since_sequence <= 0:
            return list(events)
        return [e for e in events if e.sequence_number > since_sequence]

    async def subscribe(
        self,
        investigation_id: uuid.UUID,
    ) -> asyncio.Queue[SSEEventFrame]:
        """Subscribe an SSE streaming consumer to live event broadcasts."""
        queue: asyncio.Queue[SSEEventFrame] = asyncio.Queue()
        async with self._lock:
            self._subscribers[investigation_id].append(queue)
        return queue

    async def unsubscribe(
        self,
        investigation_id: uuid.UUID,
        queue: asyncio.Queue[SSEEventFrame],
    ) -> None:
        """Unsubscribe an SSE stream connection when closed."""
        async with self._lock:
            if investigation_id in self._subscribers:
                try:
                    self._subscribers[investigation_id].remove(queue)
                except ValueError:
                    pass
