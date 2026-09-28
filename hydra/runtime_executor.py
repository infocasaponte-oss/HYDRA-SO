from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable

from hydra.runtime_health import RuntimeHealth
from hydra.traffic_router import TrafficDecision, TrafficRouter


InferenceCall = Callable[[str], Awaitable[str]]


@dataclass(frozen=True)
class RuntimeExecution:
    answer: str
    primary_variant_id: str
    shadow_variant_id: str | None = None
    shadow_answer: str | None = None
    canary_variant_id: str | None = None


class RuntimeExecutor:
    def __init__(
        self,
        router: TrafficRouter,
        health: RuntimeHealth,
        inference_call: InferenceCall,
    ):
        self.router = router
        self.health = health
        self.inference_call = inference_call

    async def execute(
        self,
        *,
        capability: str,
        trace_id: str,
    ) -> RuntimeExecution:
        decision = self.router.route(capability, trace_id)
        primary = decision.canary or decision.primary
        primary_id = str(primary.variant_id)
        shadow_task = self._start_shadow(decision)
        try:
            answer = await self.inference_call(primary_id)
        except Exception:
            self.health.failure(primary_id)
            if primary is decision.canary:
                answer, primary_id = await self._fallback(decision)
            else:
                raise
        else:
            self.health.success(primary_id)

        shadow_id = None
        shadow_answer = None
        if shadow_task is not None:
            shadow_id = str(decision.shadow.variant_id) if decision.shadow else None
            try:
                shadow_answer = await shadow_task
                if shadow_id:
                    self.health.success(shadow_id)
            except Exception:
                if shadow_id:
                    self.health.failure(shadow_id)

        return RuntimeExecution(
            answer=answer,
            primary_variant_id=primary_id,
            shadow_variant_id=shadow_id,
            shadow_answer=shadow_answer,
            canary_variant_id=(
                str(decision.canary.variant_id) if decision.canary else None
            ),
        )

    def _start_shadow(
        self, decision: TrafficDecision
    ) -> asyncio.Task[str] | None:
        if decision.shadow is None:
            return None
        return asyncio.create_task(
            self.inference_call(str(decision.shadow.variant_id))
        )

    async def _fallback(self, decision: TrafficDecision) -> tuple[str, str]:
        fallback_id = str(decision.primary.variant_id)
        answer = await self.inference_call(fallback_id)
        self.health.success(fallback_id)
        return answer, fallback_id
