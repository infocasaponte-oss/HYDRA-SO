# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""Durable retry for capture writes, on the HYDRA-SO transactional outbox.

The CapturePipeline writes inline and never fails a user request. When a ledger or corpus
write fails, the write is deferred to this outbox instead of being lost: the runtime
``OutboxWorker`` retries it with exponential backoff and moves it to the dead-letter queue
after ``max_attempts`` (at-least-once delivery; corpus ingestion deduplicates)."""

from __future__ import annotations

import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from hydra.runtime.outbox import OutboxMessage, TransactionalOutbox
from hydra.runtime.outbox_worker import OutboxWorker, RetryPolicy, WorkerResult

log = logging.getLogger("hydra.capture")

LEDGER = "capture.ledger"
CORPUS = "capture.corpus"


class CaptureDispatcher:
    """Replays deferred capture writes (duck-typed ``OutboxDispatcher`` for ``OutboxWorker``)."""

    def __init__(self, ledger=None, corpus=None) -> None:
        self.ledger = ledger
        self.corpus = corpus

    def _dispatch(self, message: OutboxMessage) -> None:
        payload = message.payload
        if message.topic == LEDGER:
            if self.ledger is None:
                raise RuntimeError("ledger is not configured")
            self.ledger.append(payload["event_type"], payload["payload"], **payload.get("options", {}))
            return
        if message.topic == CORPUS:
            if self.corpus is None:
                raise RuntimeError("corpus is not configured")
            from hydra.corpus.records import CorpusRecord

            self.corpus.ingest(CorpusRecord.model_validate(payload["record"]))
            return
        raise ValueError(f"Unknown capture outbox topic: {message.topic}")


def _aggregate(task_id: str) -> UUID:
    try:
        return UUID(task_id)
    except ValueError:
        return uuid5(NAMESPACE_URL, f"hydra:task:{task_id}")


class CaptureOutbox:
    def __init__(self, path: Path, *, ledger=None, corpus=None, policy: RetryPolicy | None = None) -> None:
        self.outbox = TransactionalOutbox(path)
        self.worker = OutboxWorker(self.outbox, CaptureDispatcher(ledger, corpus), policy)

    def defer(self, topic: str, task_id: str, payload: dict[str, Any], trace_id: str = "") -> None:
        with self.outbox.transaction() as connection:
            self.outbox.enqueue(connection, topic=topic, aggregate_id=_aggregate(task_id),
                                trace_id=trace_id or task_id, payload=payload)
        log.warning("capture write deferred to outbox", extra={"topic": topic, "task": task_id})

    def drain(self, limit: int = 100) -> WorkerResult:
        return self.worker.run_once(limit)

    def stats(self) -> dict[str, Any]:
        return {"pending": len(self.outbox.pending(1000)), "dead_letters": len(self.outbox.dead_letters(1000))}

    def dead_letters(self, limit: int = 100) -> list[dict[str, Any]]:
        return [{**asdict(m), "id": str(m.id), "aggregate_id": str(m.aggregate_id)}
                for m in self.outbox.dead_letters(limit)]
