# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
from __future__ import annotations

import re

from hydra.core.context import TaskContext
from hydra.core.contracts import ModelRequest
from hydra.core.events import EventType
from hydra.registry.models import ModelProfile
from hydra.workers.base import Worker, claim_id_for


def requested_json_schema(messages: list[dict], typed_state_json: bool = False) -> dict | None:
    """Honor explicit JSON-only instructions without parsing arbitrary prose as a format request."""
    user = next((m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), "")
    if not isinstance(user, str):
        return None
    if re.search(r"\bno\s+(?:quiero|devuelvas|uses|respondas)\s+(?:solo\s+)?json\b", user, re.I):
        return None
    state_record = re.search(r"\b(?:claves|registro|json)\s*:\s*id\s*[:=]\s*\d+\s*;\s*activo\s*:\s*(?:sí|si|no)"
                             r"\s*\.?\s*(?:No uses Markdown\.?)?\s*$",user,re.I)
    if typed_state_json and state_record and re.search(r"\bobjeto\s+json\b",user,re.I):
        return {"type":"object","properties":{"id":{"type":"integer"},"activo":{"type":"boolean"}},
                "required":["id","activo"],"additionalProperties":False}
    explicit = (r"\b(?:solo|solamente|únicamente|only)\s+(?:un\s+)?json\b|\bjson\s+only\b|"
                r"\b(?:devuelve|devuélveme|genera|crea|entrega|return)\s+(?:(?:un|a|solo|solamente|only)\s+)?(?:objeto\s+)?json\b|"
                r"^\s*json\s+con\b")
    if not re.search(explicit, user, re.I):
        return None
    # Permit any valid JSON value; do not invent an object schema or remove model text afterwards.
    return {"anyOf": [{"type": t} for t in ("object", "array", "string", "number", "boolean", "null")]}


class ReasonerWorker(Worker):
    role = "reasoner"
    system_prompt = (
        "You are HYDRA's reasoning worker. Solve the user's task precisely and completely. "
        "State assumptions explicitly, separate facts from hypotheses, and say what you are "
        "unsure about instead of guessing. Answer in the user's language. "
        "Honor the requested output format: when only code or JSON is requested, omit "
        "commentary and headings. For code, preserve the exact function signature, include "
        "required imports, and handle the edge cases stated in the request. Do not claim "
        "tests passed unless an execution result confirms it."
    )

    async def execute(self, ctx: TaskContext, model: ModelProfile, index: int = 0,
                      extra_system: str = "", messages: list[dict] | None = None) -> dict:
        messages = self.build_messages(ctx, model, extra_system=extra_system, messages=messages)
        schema = requested_json_schema(messages, model.quirks.typed_state_json) if model.quirks.native_json_schema else None
        resp = await self.invoker.invoke(
            ctx, model, ModelRequest(messages=messages, temperature=0.2 + 0.15 * index, max_tokens=2048,
                              response_schema=schema,
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
