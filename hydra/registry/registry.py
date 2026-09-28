# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""Model registry: the catalogue of cognitive hardware."""

from __future__ import annotations

import os
import re
from pathlib import Path

import yaml

from hydra.core.contracts import HydraRequest, RoutingDecision, TaskType
from hydra.registry.circuit_breaker import CircuitBreaker
from hydra.registry.models import ModelProfile
from hydra.router.scoring import filter_models, rank_models


_ENV = re.compile(r"\$\{([A-Z0-9_]+)(?::-([^}]*))?\}")


def expand_env(text: str) -> str:
    """Expand ${VAR} and ${VAR:-default} in configuration files."""
    return _ENV.sub(lambda m: os.environ.get(m.group(1)) or (m.group(2) or ""), text)


def update_quality(old_score: float, new_result: float, alpha: float = 0.05) -> float:
    """Exponential moving average: HYDRA learns on its real workload."""
    return old_score * (1 - alpha) + new_result * alpha


class ModelRegistry:
    def __init__(self, models: list[ModelProfile], breaker: CircuitBreaker | None = None) -> None:
        self.models: dict[str, ModelProfile] = {m.id: m for m in models}
        self.breaker = breaker or CircuitBreaker()

    @classmethod
    def from_yaml(cls, path: Path | str, breaker: CircuitBreaker | None = None) -> ModelRegistry:
        data = yaml.safe_load(expand_env(Path(path).read_text(encoding="utf-8"))) or {}
        return cls([ModelProfile.model_validate(m) for m in data.get("models", [])], breaker)

    def get(self, model_id: str) -> ModelProfile:
        return self.models[model_id]

    def add(self, model: ModelProfile) -> None:
        self.models[model.id] = model

    def all(self) -> list[ModelProfile]:
        return list(self.models.values())

    def available(self) -> list[ModelProfile]:
        return [m for m in self.models.values() if m.enabled and self.breaker.available(m.id)]

    def select(
        self,
        request: HydraRequest,
        route: RoutingDecision,
        exclude: set[str] | None = None,
    ) -> list[ModelProfile]:
        exclude = exclude or set()
        pool = [m for m in self.available() if m.id not in exclude]
        candidates = filter_models(pool, request, route)
        if not candidates and route.requires_tools:
            # degrade gracefully: answer without tools rather than not at all
            relaxed = route.model_copy(update={"requires_tools": False})
            candidates = filter_models(pool, request, relaxed)
        return rank_models(candidates, route, request)

    def escalation_target(self, current: ModelProfile, request: HydraRequest, route: RoutingDecision) -> ModelProfile | None:
        """Next stronger model: 3B -> 8B -> 32B -> large reasoner."""
        stronger = [m for m in self.select(request, route) if m.tier > current.tier]
        return min(stronger, key=lambda m: m.tier) if stronger else None

    def smaller_than(self, current: ModelProfile, request: HydraRequest, route: RoutingDecision) -> ModelProfile | None:
        smaller = [m for m in self.select(request, route, exclude={current.id}) if m.tier < current.tier]
        return max(smaller, key=lambda m: m.tier) if smaller else None

    def record(self, model_id: str, task: TaskType, quality: float, latency_ms: float) -> None:
        model = self.models.get(model_id)
        if model is None:
            return
        key = task.value
        old = model.learned_quality.get(key, model.capabilities.for_task(task))
        model.learned_quality[key] = update_quality(old, quality)
        model.runs[key] = model.runs.get(key, 0) + 1
        model.estimated_latency_ms = update_quality(model.estimated_latency_ms, latency_ms, alpha=0.1)
