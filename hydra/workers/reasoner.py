# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
from __future__ import annotations

from hydra.core.context import TaskContext
from hydra.core.contracts import ModelRequest
from hydra.core.events import EventType
from hydra.registry.models import ModelProfile
from hydra.workers.base import Worker, claim_id_for


class ReasonerWorker(Worker):
    role = "reasoner"
    system_prompt = (
        "You are HYDRA's reasoning worker. Solve the user's task precisely and completely. "
        "State assumptions explicitly, separate facts from hypotheses, and say what you are "
        "unsure about instead of guessing. Answer in the user's language."
    )

    async def execute(self, ctx: TaskContext, model: ModelProfile, index: int = 0,
                      extra_system: str = "", messages: list[dict] | None = None) -> dict:
        messages = self.build_messages(ctx, model, extra_system=extra_system, messages=messages)
        resp = await self.invoker.invoke(
            ctx, model, ModelRequest(messages=messages, temperature=0.2 + 0.15 * index, max_tokens=2048,
                              reasoning_level=self.reasoning_level(ctx)),
            role=self.role,
        )
        self.require_answer(ctx, resp.model_id, resp.content)
        candidate = {
            "claim_id": claim_id_for(resp.model_id, index),
            "model": resp.model_id,
            "worker": self.role,
            "answer": resp.content,
            "latency_ms": round(resp.latency_ms, 2),
        }
        await ctx.emit(EventType.ANSWER_PROPOSED, self.role, candidate)
        return candidate
