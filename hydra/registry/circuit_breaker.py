# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""Temporarily disable models that keep failing (OOM, timeouts, crashes)."""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class BreakerState:
    failures: int = 0
    open: bool = False
    opened_at: float = 0.0


class CircuitBreaker:
    def __init__(self, max_failures: int = 5, cooldown_s: float = 60, slow_ms: float = 20_000) -> None:
        self.max_failures = max_failures
        self.cooldown_s = cooldown_s
        self.slow_ms = slow_ms
        self.models: dict[str, BreakerState] = {}

    def _state(self, model_id: str) -> BreakerState:
        return self.models.setdefault(model_id, BreakerState())

    def register_failure(self, model_id: str, fatal: bool = False) -> None:
        state = self._state(model_id)
        state.failures += 1
        if fatal or state.failures >= self.max_failures:
            state.open = True
            state.opened_at = time.monotonic()

    def register_success(self, model_id: str, latency_ms: float) -> None:
        if latency_ms > self.slow_ms:
            self.register_failure(model_id)
            return
        state = self._state(model_id)
        state.failures = 0
        state.open = False

    def available(self, model_id: str) -> bool:
        state = self._state(model_id)
        if not state.open:
            return True
        if time.monotonic() - state.opened_at >= self.cooldown_s:
            # half-open: allow one trial, a new failure reopens immediately
            state.open = False
            state.failures = self.max_failures - 1
            return True
        return False
