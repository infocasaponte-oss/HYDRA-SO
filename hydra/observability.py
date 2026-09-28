from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Iterator
from uuid import UUID, uuid4


@dataclass
class CognitiveSpan:
    span_id: UUID = field(default_factory=uuid4)
    trace_id: str = ""
    task_id: UUID | None = None
    name: str = ""
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    duration_ms: float | None = None
    status: str = "in_progress"
    error_type: str | None = None
    attributes: dict = field(default_factory=dict)


class TraceStore:
    def __init__(self, path: str | Path = "runtime/traces.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, span: CognitiveSpan) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(span), sort_keys=True, default=str) + "\n")


class CognitiveTracer:
    def __init__(self, store: TraceStore | None = None):
        self.store = store or TraceStore()

    @contextmanager
    def span(
        self,
        name: str,
        *,
        trace_id: str,
        task_id: UUID | None = None,
        attributes: dict | None = None,
    ) -> Iterator[CognitiveSpan]:
        span = CognitiveSpan(
            trace_id=trace_id,
            task_id=task_id,
            name=name,
            attributes=attributes or {},
        )
        started = perf_counter()
        try:
            yield span
        except Exception as exc:
            span.status = "error"
            span.error_type = type(exc).__name__
            raise
        else:
            span.status = "ok"
        finally:
            span.duration_ms = (perf_counter() - started) * 1000
            self.store.append(span)
