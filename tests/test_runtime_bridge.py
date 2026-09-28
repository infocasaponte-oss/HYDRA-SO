from uuid import uuid4

import pytest

from hydra.deployment import Deployment, DeploymentState
from hydra.deployment_registry import DeploymentRegistry
from hydra.events import JsonlEventStore
from hydra.model_factory import BuildState, ModelLineage, ModelVariant
from hydra.runtime_bridge import RuntimeBridge
from hydra.runtime_events import RuntimeEventEmitter
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
async def test_bridge_emits_selection_and_shadow(tmp_path):
    registry = DeploymentRegistry()
    active = deployment(DeploymentState.ACTIVE, 1)
    shadow = deployment(DeploymentState.SHADOW, 2)
    registry.add(active)
    registry.add(shadow)

    async def call(variant_id: str) -> str:
        return "same"

    health = RuntimeHealth()
    executor = RuntimeExecutor(TrafficRouter(registry, health), health, call)
    events = JsonlEventStore(tmp_path / "events.jsonl")
    bridge = RuntimeBridge(executor, health, RuntimeEventEmitter(events))
    await bridge.execute(
        task_id=uuid4(),
        trace_id="trace",
        capability="reasoning.general",
    )
    text = (tmp_path / "events.jsonl").read_text()
    assert "hydra.model.selected" in text
    assert "hydra.shadow.compared" in text
