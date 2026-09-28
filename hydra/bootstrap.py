from __future__ import annotations

from dataclasses import dataclass

from hydra.startup_recovery import RecoveryResult, recover_pending
from hydra.outbox_worker import OutboxWorker


@dataclass(frozen=True)
class BootstrapResult:
    recovery: RecoveryResult


def bootstrap_runtime(worker: OutboxWorker) -> BootstrapResult:
    return BootstrapResult(recovery=recover_pending(worker))
