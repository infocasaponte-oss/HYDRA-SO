# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
import pytest

from hydra.core.contracts import ExecutionMode, HydraRequest, Message, TaskType
from hydra.registry.circuit_breaker import CircuitBreaker
from hydra.registry.registry import ModelRegistry, update_quality
from hydra.router.router import CognitiveRouter
from hydra.router.scoring import filter_models

from .conftest import default_models, model


def req(text: str, **kw) -> HydraRequest:
    return HydraRequest(messages=[Message(role="user", content=text)], **kw)


@pytest.mark.parametrize("text,task", [
    ("Encuentra el bug en esta función Python", TaskType.CODING),
    ("Demuestra que la raíz de 2 es irracional y razona cada paso", TaskType.REASONING),
    ("Hola, ¿qué tal?", TaskType.CHAT),
    ("Describe esta imagen captura.png", TaskType.VISION),
])
async def test_router_classifies(text, task):
    assert (await CognitiveRouter().route(req(text))).task_type == task


async def test_router_policy_by_mode():
    router = CognitiveRouter()
    fast = await router.route(req("analiza esto", mode=ExecutionMode.FAST))
    assert fast.desired_parallelism == 1 and not fast.requires_verification
    deep = await router.route(req("analiza esto", mode=ExecutionMode.DEEP))
    assert deep.desired_parallelism >= 3 and deep.requires_verification


async def test_router_high_risk_forces_verification():
    d = await CognitiveRouter().route(req("borra la tabla de producción con drop table y el password"))
    assert d.risk > 0.5 and d.requires_verification


async def test_private_mode_never_selects_cloud():
    registry = ModelRegistry(default_models())
    r = req("hola", mode=ExecutionMode.PRIVATE)
    route = await CognitiveRouter().route(r)
    assert all(m.local for m in registry.select(r, route))
    assert "cloud" not in [m.id for m in registry.select(r, route)]


async def test_vision_filter():
    models = default_models() + [model("vlm", vision=0.9)]
    r = req("describe la imagen foto.jpg")
    route = await CognitiveRouter().route(r)
    assert [m.id for m in filter_models(models, r, route)] == ["vlm"]


def test_ema_learning_and_escalation_target():
    assert update_quality(0.86, 0.98) == pytest.approx(0.866)
    registry = ModelRegistry(default_models())
    for _ in range(60):
        registry.record("small", TaskType.CODING, 1.0, 100)
    assert registry.get("small").quality(TaskType.CODING) > 0.9


async def test_escalation_and_smaller():
    registry = ModelRegistry(default_models())
    r = req("python bug")
    route = await CognitiveRouter().route(r)
    assert registry.escalation_target(registry.get("small"), r, route).id == "medium"
    assert registry.smaller_than(registry.get("large"), r, route).id == "medium"


def test_circuit_breaker_opens_and_half_opens():
    b = CircuitBreaker(max_failures=2, cooldown_s=0)
    b.register_failure("m")
    assert b.available("m")
    b.register_failure("m")
    assert b.models["m"].open
    assert b.available("m")  # cooldown 0 -> half-open trial
    b.register_failure("m")
    assert b.models["m"].open
    b2 = CircuitBreaker(max_failures=5, cooldown_s=999)
    b2.register_failure("x", fatal=True)
    assert not b2.available("x")


def test_qwen_coder_is_registered_as_internal_ollama_backend():
    from hydra.registry.registry import ModelRegistry
    from hydra.core.config import ROOT

    registry = ModelRegistry.from_yaml(ROOT / "config" / "models.yaml")
    qwen = registry.get("qwen2.5-coder-7b")
    assert qwen.provider == "ollama"
    assert qwen.physical_name == "qwen2.5-coder:7b"
    assert qwen.local
    assert qwen.capabilities.coding >= 0.8
