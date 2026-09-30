# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
import asyncio

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


def test_unhealthy_provider_is_excluded_before_scoring():
    registry = ModelRegistry(default_models())
    registry.set_provider_health("ollama", False)
    request = req("python bug")
    route = asyncio.run(CognitiveRouter().route(request))
    assert all(m.provider != "ollama" for m in registry.select(request, route))


def test_unknown_provider_health_remains_optimistic():
    registry = ModelRegistry(default_models())
    assert registry.provider_healthy("new-provider")
    assert len(registry.available()) == len(default_models())


def test_failed_health_probe_expires_so_the_provider_is_retried(monkeypatch):
    # workers run without RuntimeMonitor: a provider down at startup must not stay excluded forever
    registry = ModelRegistry(default_models())
    now = [1000.0]
    monkeypatch.setattr("hydra.registry.registry.time.monotonic", lambda: now[0])
    registry.set_provider_health("ollama", False)
    assert not registry.provider_healthy("ollama")
    now[0] += ModelRegistry.PROVIDER_HEALTH_TTL_S + 1
    assert registry.provider_healthy("ollama")


def test_models_not_installed_in_the_runtime_are_excluded(monkeypatch):
    # a configured model the runtime does not have must not be routed to (it could only time out)
    from hydra.providers.ollama import ollama_model_key
    from hydra.registry.registry import refresh_installed_models

    registry = ModelRegistry([model("coder", provider="ollama", runtime_model="qwen2.5-coder:7b"),
                              model("hydra", provider="ollama", runtime_model="hydra-q5"),
                              model("vision", provider="ollama", runtime_model="llava:34b"),
                              model("other", provider="mock")])

    class FakeOllama:
        async def installed_models(self):
            return {ollama_model_key("qwen2.5-coder:7b"), ollama_model_key("hydra-q5:latest")}

    now = [1000.0]
    monkeypatch.setattr("hydra.registry.registry.time.monotonic", lambda: now[0])
    missing = asyncio.run(refresh_installed_models(registry, {"ollama": FakeOllama(), "mock": object()}))
    assert missing == {"ollama": ["vision"]}
    assert {m.id for m in registry.available()} == {"coder", "hydra", "other"}  # untagged == :latest
    now[0] += ModelRegistry.PROVIDER_HEALTH_TTL_S + 1  # stale mark: retried, e.g. after `ollama pull`
    assert "vision" in {m.id for m in registry.available()}


def test_ollama_provider_lists_installed_models():
    import httpx

    from hydra.providers.ollama import OllamaProvider

    tags = {"models": [{"name": "qwen3:8b", "model": "qwen3:8b"}, {"name": "hydra-q5-v2:latest"}]}
    provider = OllamaProvider("http://ollama")
    provider.client = httpx.AsyncClient(base_url="http://ollama", transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=tags)))
    assert asyncio.run(provider.installed_models()) == {"qwen3:8b", "hydra-q5-v2:latest"}
    provider.client = httpx.AsyncClient(base_url="http://ollama", transport=httpx.MockTransport(
        lambda request: httpx.Response(500)))
    assert asyncio.run(provider.installed_models()) is None  # unknown, never "nothing installed"


def test_ollama_think_runtime_option_is_a_top_level_field():
    # qwen3-vl thinks by default; `think: false` must reach Ollama as a request field, not a sampling option
    import json

    import httpx

    from hydra.core.contracts import ModelRequest
    from hydra.providers.ollama import OllamaProvider

    sent = {}

    def handler(request):
        sent.update(json.loads(request.content))
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "ok"}, "done": True})

    provider = OllamaProvider("http://ollama")
    provider.client = httpx.AsyncClient(base_url="http://ollama", transport=httpx.MockTransport(handler))
    request = ModelRequest(messages=[{"role": "user", "content": "hola"}],
                           metadata={"runtime_options": {"think": False, "num_ctx": 8192}})
    asyncio.run(provider.generate("qwen3-vl:8b", request))
    assert sent["think"] is False
    assert "think" not in sent["options"] and sent["options"]["num_ctx"] == 8192
