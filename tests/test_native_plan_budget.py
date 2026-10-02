# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from hydra.registry.native import ModelRegistry
from hydra.scheduler.native import ExecutionPlan, PlanStep, StepKind
from hydra.scheduler.native_executor import Executor, ModelCallBudgetExceeded
from hydra.verification.verifier import Verifier


def plan():
    return ExecutionPlan(task_id=uuid4(), steps=[
        PlanStep(kind=StepKind.MODEL, capability="chat.multilingual", instruction="hello"),
        PlanStep(kind=StepKind.MODEL, capability="chat.multilingual", instruction="again"),
    ])


@pytest.mark.asyncio
async def test_over_budget_plan_is_rejected_before_inference():
    llm = AsyncMock()
    executor = Executor(llm, ModelRegistry(), Verifier())
    with pytest.raises(ModelCallBudgetExceeded):
        await executor.execute(plan(), 64, max_model_calls=1)
    llm.chat.assert_not_called()


@pytest.mark.asyncio
async def test_exact_budget_executes_all_model_steps():
    llm = AsyncMock()
    llm.chat.side_effect = ["first", "second"]
    result = await Executor(llm, ModelRegistry(), Verifier()).execute(
        plan(), 64, max_model_calls=2,
    )
    assert result.answer == "second"
    assert llm.chat.await_count == 2
