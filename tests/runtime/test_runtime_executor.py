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
