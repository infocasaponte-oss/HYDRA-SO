# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""Bounded local decision experiment; it cannot modify the routing policy."""
from __future__ import annotations

import asyncio
import time

from hydra.core.contracts import DecisionObservation, ExecutionMode, HydraRequest, TaskType
from hydra.providers.decision import LocalSystemOneProvider, validate_answers
from hydra.training.calibrator import TemperatureCalibrator


class DecisionObserver:
    def __init__(self, provider: LocalSystemOneProvider, timeout_s: float = 0.5,
                 calibrator: TemperatureCalibrator | None = None):
        if not 0 < timeout_s <= 5:
            raise ValueError("observation timeout must be in (0, 5]")
        self.provider = provider
        self.timeout_s = timeout_s
        self.calibrator = calibrator

    async def observe(self, request: HydraRequest) -> DecisionObservation:
        base = {"model": self.provider.model}
        # Explicit latency budgets belong entirely to the actual execution.
        reason = ("private" if request.private else "fast" if request.mode == ExecutionMode.FAST
                  else "latency_budget" if request.max_latency_ms is not None else None)
        if reason:
            return DecisionObservation(status="skipped", reason=reason, **base)
        questions = {"task": {"type": "choice", "criteria": {
            task.value: f"The user requests a {task.value} task" for task in TaskType}}}
        start = time.perf_counter()
        try:
            payload = await asyncio.wait_for(
                self.provider.decide(request.last_user_text, questions), self.timeout_s)
            if payload.get("model") != self.provider.model:
                raise ValueError("model alias mismatch")
            answer = validate_answers(questions, payload)["answers"]["task"]
            if self.calibrator is not None:
                answer = self.calibrator.apply(answer)
            return DecisionObservation(
                status="observed", selected=answer["choice"],
                probabilities=answer["probabilities"], confidence=answer["confidence"],
                elapsed_ms=(time.perf_counter() - start) * 1000, **base)
        except Exception as exc:
            # Do not copy server errors or user content into telemetry.
            return DecisionObservation(
                status="timeout" if isinstance(exc, TimeoutError) else "error",
                reason=type(exc).__name__, elapsed_ms=(time.perf_counter() - start) * 1000, **base)

    async def close(self) -> None:
        await self.provider.close()
