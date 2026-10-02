# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
from __future__ import annotations

from dataclasses import dataclass

from hydra.runtime.model_registry import ModelRegistry
from hydra.scheduler.native import ExecutionPlan, StepKind
from hydra.providers.local_llm import LocalLLM
from hydra.runtime.verifier import VerificationResult, Verifier


class UnsafePlan(RuntimeError):
    pass


@dataclass
class ExecutionOutput:
    answer: str
    model_id: str
    verification: VerificationResult | None


class Executor:
    def __init__(
        self,
        llm: LocalLLM,
        registry: ModelRegistry,
        verifier: Verifier,
    ):
        self.llm = llm
        self.registry = registry
        self.verifier = verifier

    async def execute(self, plan: ExecutionPlan, max_tokens: int) -> ExecutionOutput:
        if any(step.side_effects or step.kind == StepKind.TOOL for step in plan.steps):
            raise UnsafePlan("Tool/side-effect execution requires HYDRA Sandbox")

        answer = ""
        model_id = ""
        verification = None

        for step in plan.steps:
            if step.kind == StepKind.MODEL:
                model = self.registry.resolve(step.capability, local_only=True)
                model_id = model.model_id
                answer = await self.llm.chat(
                    [{"role": "user", "content": step.instruction}],
                    max_tokens=max_tokens,
                )
            elif step.kind == StepKind.VERIFY:
                verification = self.verifier.verify_text(answer)

        return ExecutionOutput(answer, model_id, verification)
