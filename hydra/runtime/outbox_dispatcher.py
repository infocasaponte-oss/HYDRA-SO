# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
from __future__ import annotations

from dataclasses import dataclass

from hydra.runtime.corpus import CorpusRecord, CorpusStore
from hydra.runtime.events import JsonlEventStore
from hydra.runtime.outbox import OutboxMessage, TransactionalOutbox
from hydra.runtime.provenance import ProvenanceLedger, ProvenanceRecord


@dataclass(frozen=True)
class DispatchResult:
    published: int
    failed: int


class OutboxDispatcher:
    def __init__(
        self,
        outbox: TransactionalOutbox,
        events: JsonlEventStore,
        provenance: ProvenanceLedger,
        corpus: CorpusStore | None = None,
    ):
        self.outbox = outbox
        self.events = events
        self.provenance = provenance
        self.corpus = corpus

    def dispatch_once(self, limit: int = 100) -> DispatchResult:
        published = 0
        failed = 0
        for message in self.outbox.pending(limit):
            try:
                self._dispatch(message)
            except Exception:  # noqa: BLE001
                failed += 1
                continue
            self.outbox.mark_published(message.id)
            published += 1
        return DispatchResult(published=published, failed=failed)

    def _dispatch(self, message: OutboxMessage) -> None:
        if message.topic == "event":
            payload = message.payload
            self.events.append(
                event_type=payload["event_type"],
                aggregate_id=message.aggregate_id,
                producer=payload.get("producer", "hydra.runtime.outbox"),
                trace_id=message.trace_id,
                payload=payload.get("payload", {}),
                source_message_id=message.id,
            )
            return
        if message.topic == "provenance":
            payload = message.payload
            self.provenance.append(
                ProvenanceRecord(
                    task_id=message.aggregate_id,
                    trace_id=message.trace_id,
                    action=payload["action"],
                    inputs=payload.get("inputs", {}),
                    outputs=payload.get("outputs", {}),
                    source_message_id=message.id,
                )
            )
            return
        if message.topic == "corpus":
            if self.corpus is None:
                raise RuntimeError("Corpus store is not configured")
            record = CorpusRecord.model_validate(message.payload)
            self.corpus.append_once(record)
            return
        raise ValueError(f"Unknown outbox topic: {message.topic}")
