# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
import pytest

from hydra.runtime.deployment import Deployment, DeploymentState
from hydra.runtime.deployment_registry import DeploymentRegistry
from hydra.runtime.model_factory import BuildState, ModelLineage, ModelVariant
from hydra.runtime.runtime_evidence import RuntimeEvidenceStore
from hydra.runtime.runtime_executor import RuntimeExecutor
from hydra.runtime.runtime_health import RuntimeHealth
from hydra.runtime.traffic_router import TrafficRouter


def deployment(state: DeploymentState, generation: int) -> Deployment:
    variant = ModelVariant(
        lineage=ModelLineage(base_model="base", base_model_sha256="a" * 64),
        quantization="Q4_K_M",
        artifact_path=f"{generation}.gguf",
        artifact_sha256="b" * 64,
        state=BuildState.PROMOTED,
    )
    return Deployment(
        variant=variant,
        capabilities={"reasoning.general"},
        state=state,
        generation=generation,
    )


@pytest.mark.asyncio
async def test_shadow_is_not_authoritative(tmp_path):
    registry = DeploymentRegistry()
    active = deployment(DeploymentState.ACTIVE, 1)
    shadow = deployment(DeploymentState.SHADOW, 2)
    registry.add(active)
    registry.add(shadow)
    answers = {
        str(active.variant_id): "active-answer",
        str(shadow.variant_id): "shadow-answer",
    }

    async def call(variant_id: str, prompt: str, max_tokens: int) -> str:
        assert prompt == "hello"
        assert max_tokens == 64
        return answers[variant_id]

    health = RuntimeHealth()
    evidence = RuntimeEvidenceStore(tmp_path / "evidence.jsonl")
    executor = RuntimeExecutor(
        TrafficRouter(registry, health),
        health,
        call,
        evidence,
    )
    result = await executor.execute(
        capability="reasoning.general",
        trace_id="trace",
        prompt="hello",
        max_tokens=64,
    )
    assert result.answer == "active-answer"
    assert result.shadow_answer == "shadow-answer"
    saved = (tmp_path / "evidence.jsonl").read_text()
    assert "active-answer" not in saved
    assert "shadow-answer" not in saved


@pytest.mark.asyncio
async def test_canary_failures_and_latency_are_recorded_as_evidence(tmp_path):
    registry = DeploymentRegistry()
    active = deployment(DeploymentState.ACTIVE, 1)
    canary = deployment(DeploymentState.CANARY, 2)
    shadow = deployment(DeploymentState.SHADOW, 3)
    for item in (active, canary, shadow):
        registry.add(item)
    canary_id, shadow_id = str(canary.variant_id), str(shadow.variant_id)

    async def call(variant_id: str, prompt: str, max_tokens: int) -> str:
        if variant_id in (canary_id, shadow_id):
            raise RuntimeError("variant down")
        return "active-answer"

    health = RuntimeHealth()
    evidence = RuntimeEvidenceStore(tmp_path / "evidence.jsonl")
    executor = RuntimeExecutor(TrafficRouter(registry, health, canary_percent=100), health, call, evidence)
    result = await executor.execute(capability="reasoning.general", trace_id="t", prompt="p", max_tokens=8)
    assert result.answer == "active-answer" and result.canary_variant_id == canary_id

    measured_canary = evidence.canary_evidence(canary_id)
    assert measured_canary.requests == 1 and measured_canary.error_rate == 1.0
    measured_shadow = evidence.shadow_evidence(shadow_id)
    assert measured_shadow.samples == 1 and measured_shadow.error_rate == 1.0
    record = next(evidence.records())
    assert record["canary_error"] is True and record["primary_latency_ms"] >= 0
