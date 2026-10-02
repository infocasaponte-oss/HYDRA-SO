# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""The cognitive kernel's model-call counter is the shared native inference budget."""
from types import SimpleNamespace

import pytest

from hydra.core.budget import BudgetExceeded, BudgetTracker, budget_for
from hydra.core.contracts import ExecutionMode, HydraRequest, Message
from hydra.core.inference_budget import ModelCallBudgetExceeded, reserve_model_call, use_inference_budget
from hydra.core.kernel import HydraKernel


def tracker(mode=ExecutionMode.BALANCED) -> BudgetTracker:
    return BudgetTracker(budget_for(HydraRequest(messages=[Message(role="user", content="hola")], mode=mode)))


def test_reservation_cannot_overrun_with_concurrent_callers():
    budget = tracker(ExecutionMode.FAST)  # one model call
    budget.reserve_model_call()
    with pytest.raises(BudgetExceeded):
        budget.reserve_model_call()  # the hedged twin finds no free unit
    assert budget.model_calls == 1 and not budget.can_call_model()


def test_reserved_charge_does_not_count_twice_and_legacy_charge_still_counts():
    budget = tracker()
    budget.reserve_model_call()
    budget.charge_model(100, 0.01, reserved=True)
    assert budget.model_calls == 1 and budget.tokens == 100
    budget.charge_model(50, 0.0)  # callers that never reserved keep the old behaviour
    assert budget.model_calls == 2 and budget.snapshot()["model_calls"] == 2


def test_native_calls_inside_a_cognitive_task_use_the_same_counter():
    budget = tracker(ExecutionMode.FAST)
    with use_inference_budget(budget.calls):
        assert reserve_model_call() is True  # e.g. RuntimeExecutor primary
        with pytest.raises(ModelCallBudgetExceeded):
            reserve_model_call()
    assert budget.model_calls == 1
    with pytest.raises(BudgetExceeded):
        budget.reserve_model_call()


@pytest.mark.asyncio
async def test_kernel_run_exposes_its_budget_to_native_executors():
    kernel = object.__new__(HydraKernel)
    kernel.config = SimpleNamespace(time_scale=1.0)
    seen = {}

    async def fake_run(request, task_id, *, shadow, learn, budget):
        reserve_model_call()  # a native executor reached from the task
        seen["calls"] = budget.model_calls
        return "done"

    kernel._run = fake_run
    request = HydraRequest(messages=[Message(role="user", content="hola")], mode=ExecutionMode.FAST)
    assert await kernel.run(request) == "done"
    assert seen["calls"] == 1
    assert reserve_model_call() is True  # outside the task the legacy (unbounded) path is restored


@pytest.mark.asyncio
async def test_failed_attempt_through_the_invoker_consumes_its_unit():
    from hydra.core.context import TaskContext
    from hydra.core.contracts import ModelRequest
    from hydra.scheduler.invoker import ModelInvoker

    class Failing:
        async def generate(self, model_id, request):
            raise RuntimeError("provider down")

    budget = tracker()
    ctx = TaskContext(request=HydraRequest(messages=[Message(role="user", content="hola")]),
                      bus=SimpleNamespace(), budget=budget)

    async def emit(*args, **kwargs):
        return None

    ctx.emit = emit
    model = SimpleNamespace(id="m", provider="p", physical_name="m", runtime_options={})
    invoker = ModelInvoker({"p": Failing()}, SimpleNamespace(), compiler=SimpleNamespace(compile=lambda m, r: r))
    with pytest.raises(RuntimeError):
        await invoker._call_once(ctx, model, ModelRequest(messages=[{"role": "user", "content": "x"}]), "worker")
    assert budget.model_calls == 1
