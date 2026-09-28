from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from hydra.outbox import TransactionalOutbox


@dataclass(frozen=True)
class OutboxMetrics:
    pending: int
    dead_letters: int
    oldest_pending_age_seconds: float | None


def collect_outbox_metrics(outbox: TransactionalOutbox) -> OutboxMetrics:
    pending = outbox.pending(limit=10_000)
    oldest_age = None
    if pending:
        oldest = min(datetime.fromisoformat(item.created_at) for item in pending)
        oldest_age = max((datetime.now(UTC) - oldest).total_seconds(), 0.0)
    return OutboxMetrics(
        pending=len(pending),
        dead_letters=len(outbox.dead_letters(limit=10_000)),
        oldest_pending_age_seconds=oldest_age,
    )
