from __future__ import annotations

from dataclasses import dataclass

from hydra.runtime.outbox_worker import OutboxWorker
from hydra.runtime.startup_recovery import RecoveryResult, recover_pending


@dataclass(frozen=True)
class BootstrapResult:
    recovery: RecoveryResult


def bootstrap_runtime(worker: OutboxWorker) -> BootstrapResult:
    return BootstrapResult(recovery=recover_pending(worker))
