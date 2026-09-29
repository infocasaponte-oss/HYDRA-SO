# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
from __future__ import annotations

import pytest

from hydra.core.bootstrap import build_runtime
from hydra.core.config import Settings
from hydra.providers.mock import MockProvider
from hydra.registry.circuit_breaker import CircuitBreaker
from hydra.registry.models import Capabilities, ModelProfile
from hydra.registry.registry import ModelRegistry
from hydra.tools.sandbox import SubprocessSandbox


def model(id: str, tier: int = 2, local: bool = True, coding: float = 0.7, reasoning: float = 0.7,
          chat: float = 0.8, tools: float = 0.8, vision: float = 0.0, latency: float = 500,
          provider: str = "mock", **kw) -> ModelProfile:
    return ModelProfile(
        id=id, provider=provider, local=local, tier=tier, context_window=32768,
        capabilities=Capabilities(chat=chat, coding=coding, reasoning=reasoning, tools=tools,
                                  vision=vision, research=0.6),
        estimated_latency_ms=latency, **kw,
    )


def default_models() -> list[ModelProfile]:
    return [
        model("small", tier=1, coding=0.62, reasoning=0.62, chat=0.75, latency=200),
        model("medium", tier=3, coding=0.85, reasoning=0.85, chat=0.85, latency=800),
        model("large", tier=4, coding=0.93, reasoning=0.95, chat=0.9, latency=1500),
        model("cloud", tier=5, local=False, coding=0.95, reasoning=0.96, chat=0.95, latency=2000,
              input_cost=2.5, output_cost=10, provider="mock-cloud"),
    ]


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(offline=True, sandbox_backend="subprocess", workspace_dir=tmp_path / "ws",
                    data_dir=tmp_path / "data", postgres_url="", redis_url="", nats_url="")


@pytest.fixture
def mock() -> MockProvider:
    return MockProvider()


@pytest.fixture
async def runtime(settings, mock):
    rt = await build_runtime(
        settings,
        providers={"mock": mock, "mock-cloud": mock},
        registry=ModelRegistry(default_models(), CircuitBreaker(max_failures=2, cooldown_s=60)),
        sandbox=SubprocessSandbox(),
    )
    yield rt
    await rt.close()
