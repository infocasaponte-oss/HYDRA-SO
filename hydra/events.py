from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from hydra.hash_chain import canonical_hash, lock_for


class EventEnvelope(BaseModel):
    schema_version: str = "2"
    event_id: UUID = Field(default_factory=uuid4)
    event_type: str
    aggregate_id: UUID
    sequence: int
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    producer: str
    trace_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    payload_hash: str
    previous_hash: str | None = None
    event_hash: str = ""


class IntegrityReport(BaseModel):
    valid: bool
    records: int
    legacy_records: int = 0
    error: str | None = None


def _event_body(event: EventEnvelope) -> dict[str, Any]:
    return event.model_dump(
        mode="json",
        exclude={"event_hash"},
    )


class JsonlEventStore:
    """Append-only development event store with a verifiable hash chain."""

    def __init__(self, path: str | Path = "runtime/events.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = lock_for(self.path)
        self._sequence, self._last_hash = self._load_tail()

    def _load_tail(self) -> tuple[int, str | None]:
        if not self.path.exists():
            return 0, None
        sequence = 0
        last_hash = None
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                event = EventEnvelope.model_validate_json(line)
                sequence = max(sequence, event.sequence)
                last_hash = event.event_hash or last_hash
        return sequence, last_hash

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
                previous_hash=self._last_hash,
            )
            event.event_hash = canonical_hash(_event_body(event))
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(event.model_dump_json() + "\n")
                handle.flush()
            self._last_hash = event.event_hash
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

    def verify_integrity(self) -> IntegrityReport:
        if not self.path.exists():
            return IntegrityReport(valid=True, records=0)
        previous_hash = None
        previous_sequence = 0
        records = 0
        legacy = 0
        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    event = EventEnvelope.model_validate_json(line)
                except Exception as exc:  # noqa: BLE001
                    return IntegrityReport(
                        valid=False,
                        records=records,
                        legacy_records=legacy,
                        error=f"line {line_number}: invalid event: {exc}",
                    )
                records += 1
                if canonical_hash(event.payload) != event.payload_hash:
                    return IntegrityReport(
                        valid=False,
                        records=records,
                        legacy_records=legacy,
                        error=f"line {line_number}: payload hash mismatch",
                    )
                if event.sequence <= previous_sequence:
                    return IntegrityReport(
                        valid=False,
                        records=records,
                        legacy_records=legacy,
                        error=f"line {line_number}: non-monotonic sequence",
                    )
                if not event.event_hash:
                    legacy += 1
                    previous_sequence = event.sequence
                    previous_hash = None
                    continue
                if event.previous_hash != previous_hash:
                    return IntegrityReport(
                        valid=False,
                        records=records,
                        legacy_records=legacy,
                        error=f"line {line_number}: previous hash mismatch",
                    )
                if canonical_hash(_event_body(event)) != event.event_hash:
                    return IntegrityReport(
                        valid=False,
                        records=records,
                        legacy_records=legacy,
                        error=f"line {line_number}: event hash mismatch",
                    )
                previous_sequence = event.sequence
                previous_hash = event.event_hash
        return IntegrityReport(valid=True, records=records, legacy_records=legacy)
