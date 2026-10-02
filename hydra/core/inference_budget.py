# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass


class ModelCallBudgetExceeded(RuntimeError):
    pass


@dataclass
class InferenceBudget:
    limit: int
    used: int = 0

    def reserve(self) -> bool:
        if self.used >= self.limit:
            return False
        self.used += 1
        return True


_current: ContextVar[InferenceBudget | None] = ContextVar("hydra_inference_budget", default=None)


@contextmanager
def inference_budget(limit: int):
    budget = InferenceBudget(limit)
    token = _current.set(budget)
    try:
        yield budget
    finally:
        _current.reset(token)


def reserve_model_call(*, optional: bool = False) -> bool:
    budget = _current.get()
    if budget is None or budget.reserve():
        return True
    if optional:
        return False
    raise ModelCallBudgetExceeded("Model-call budget exhausted")
