"""Typed Server-Sent Event (SSE) frames and serializer for Project Intelligence."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class SSEEventFrame(BaseModel):
    """A typed event frame serialized and delivered over the SSE stream."""

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    investigation_id: str
    sequence_number: int
    event_type: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict[str, Any] = Field(default_factory=dict)

    def to_sse_format(self) -> str:
        """Format the event frame according to the W3C Server-Sent Events standard."""
        data_json = json.dumps(
            {
                "event_id": self.event_id,
                "investigation_id": self.investigation_id,
                "sequence_number": self.sequence_number,
                "event_type": self.event_type,
                "timestamp": self.timestamp.isoformat(),
                "payload": self.payload,
            },
            ensure_ascii=False,
            default=str,
        )
        return f"event: {self.event_type}\nid: {self.sequence_number}\ndata: {data_json}\n\n"
