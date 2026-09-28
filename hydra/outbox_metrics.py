from __future__ import annotations

from dataclasses import dataclass

from hydra.outbox import TransactionalOutbox


@dataclass(frozen=True)
class OutboxMetrics:
    pending: int
    dead_letters: int


def collect_outbox_metrics(outbox: TransactionalOutbox) -> OutboxMetrics:
    return OutboxMetrics(
        pending=len(outbox.pending(limit=10_000)),
        dead_letters=len(outbox.dead_letters(limit=10_000)),
    )
