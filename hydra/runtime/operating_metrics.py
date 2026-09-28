from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from hydra.runtime.deployment_registry import DeploymentRegistry
from hydra.runtime.outbox import TransactionalOutbox
from hydra.runtime.outbox_metrics import collect_outbox_metrics


@dataclass(frozen=True)
class OperatingMetrics:
    outbox_pending: int
    outbox_dead_letters: int
    oldest_pending_age_seconds: float | None
    spans_total: int
    spans_error: int
    avg_span_duration_ms: float | None
    spans_by_name: dict[str, int]
    deployments_by_state: dict[str, int]


def collect_operating_metrics(
    *,
    outbox: TransactionalOutbox,
    trace_path: str | Path = "runtime/traces.jsonl",
    deployments: DeploymentRegistry | None = None,
    max_trace_records: int = 10_000,
) -> OperatingMetrics:
    outbox_metrics = collect_outbox_metrics(outbox)
    path = Path(trace_path)
    records: list[dict] = []
    if path.exists():
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
        for line in lines[-max_trace_records:]:
            records.append(json.loads(line))

    durations = [
        float(record["duration_ms"])
        for record in records
        if record.get("duration_ms") is not None
    ]
    names = Counter(str(record.get("name", "unknown")) for record in records)
    deployment_states: Counter[str] = Counter()
    if deployments is not None:
        deployment_states.update(
            item.state.value for item in deployments.deployments.values()
        )

    return OperatingMetrics(
        outbox_pending=outbox_metrics.pending,
        outbox_dead_letters=outbox_metrics.dead_letters,
        oldest_pending_age_seconds=outbox_metrics.oldest_pending_age_seconds,
        spans_total=len(records),
        spans_error=sum(record.get("status") == "error" for record in records),
        avg_span_duration_ms=(
            sum(durations) / len(durations) if durations else None
        ),
        spans_by_name=dict(sorted(names.items())),
        deployments_by_state=dict(sorted(deployment_states.items())),
    )
