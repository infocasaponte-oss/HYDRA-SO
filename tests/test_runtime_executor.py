import pytest

from hydra.deployment import Deployment, DeploymentState
from hydra.deployment_registry import DeploymentRegistry
from hydra.model_factory import BuildState, ModelLineage, ModelVariant
from hydra.runtime_executor import RuntimeExecutor
from hydra.runtime_health import RuntimeHealth
from hydra.traffic_router import TrafficRouter


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
async def test_shadow_is_not_authoritative():
    registry = DeploymentRegistry()
    active = deployment(DeploymentState.ACTIVE, 1)
    shadow = deployment(DeploymentState.SHADOW, 2)
    registry.add(active)
    registry.add(shadow)
    answers = {
        str(active.variant_id): "active-answer",
        str(shadow.variant_id): "shadow-answer",
    }

    async def call(variant_id: str) -> str:
        return answers[variant_id]

    health = RuntimeHealth()
    executor = RuntimeExecutor(
        TrafficRouter(registry, health),
        health,
        call,
    )
    result = await executor.execute(
        capability="reasoning.general",
        trace_id="trace",
    )
    assert result.answer == "active-answer"
    assert result.shadow_answer == "shadow-answer"
