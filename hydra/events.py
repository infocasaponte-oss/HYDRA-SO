from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class EventEnvelope(BaseModel):
    schema_version: str = "1"
    event_id: UUID = Field(default_factory=uuid4)
    event_type: str
    aggregate_id: UUID
    sequence: int
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    producer: str
    trace_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    payload_hash: str


def canonical_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(raw).hexdigest()


class JsonlEventStore:
    """Development event store. PostgreSQL implementation replaces this in the next milestone."""

    def __init__(self, path: str | Path = "runtime/events.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._sequence = self._load_sequence()

    def _load_sequence(self) -> int:
        if not self.path.exists():
            return 0
        with self.path.open("r", encoding="utf-8") as handle:
            return sum(1 for line in handle if line.strip())

    def append(
        self,
        *,
        event_type: str,
        aggregate_id: UUID,
        producer: str,
        trace_id: str,
        payload: dict[str, Any] | None = None,
    ) -> EventEnvelope:
        body = payload or {}
        with self._lock:
            self._sequence += 1
            event = EventEnvelope(
                event_type=event_type,
                aggregate_id=aggregate_id,
                sequence=self._sequence,
                producer=producer,
                trace_id=trace_id,
                payload=body,
                payload_hash=canonical_hash(body),
            )
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(event.model_dump_json() + "\n")
            return event

    def for_aggregate(self, aggregate_id: UUID) -> list[EventEnvelope]:
        if not self.path.exists():
            return []
        events = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                event = EventEnvelope.model_validate_json(line)
                if event.aggregate_id == aggregate_id:
                    events.append(event)
        return events
