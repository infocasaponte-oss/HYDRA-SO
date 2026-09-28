import pytest

from hydra.contracts import HydraTask, TaskStatus
from hydra.deployment import Deployment, DeploymentState
from hydra.deployment_registry import DeploymentRegistry
from hydra.events import JsonlEventStore
from hydra.kernel import HydraKernel
from hydra.model_factory import BuildState, ModelLineage, ModelVariant
from hydra.runtime_bridge import RuntimeBridge
from hydra.runtime_events import RuntimeEventEmitter
from hydra.runtime_executor import RuntimeExecutor
from hydra.runtime_health import RuntimeHealth
from hydra.traffic_router import TrafficRouter


class UnusedLLM:
    async def chat(self, messages, *, temperature=0.2, max_tokens=1024):
        raise AssertionError("logical LLM should not be called")


@pytest.mark.asyncio
async def test_kernel_uses_active_physical_runtime(tmp_path):
    variant = ModelVariant(
        lineage=ModelLineage(base_model="base", base_model_sha256="a" * 64),
        quantization="Q4_K_M",
        artifact_path="model.gguf",
        artifact_sha256="b" * 64,
        state=BuildState.PROMOTED,
    )
    deployment = Deployment(
        variant=variant,
        capabilities={"chat.multilingual"},
        state=DeploymentState.ACTIVE,
        generation=1,
    )
    registry = DeploymentRegistry()
    registry.add(deployment)
    health = RuntimeHealth()

    async def call(variant_id: str, prompt: str, max_tokens: int) -> str:
        assert variant_id == str(variant.variant_id)
        assert prompt == "Hola runtime"
        assert max_tokens > 0
        return "physical-answer"

    events = JsonlEventStore(tmp_path / "events.jsonl")
    runtime = RuntimeBridge(
        RuntimeExecutor(TrafficRouter(registry, health), health, call),
        health,
        RuntimeEventEmitter(events),
    )
    kernel = HydraKernel(events=events, runtime_bridge=runtime)
    task = HydraTask(goal="Hola runtime")

    result = await kernel.run(task, UnusedLLM())

    assert result.status == TaskStatus.COMPLETED
    assert result.answer == "physical-answer"
    assert result.metadata["model_id"] == str(variant.variant_id)
    names = [event.event_type for event in events.for_aggregate(task.id)]
    assert "hydra.model.selected" in names
    assert "hydra.task.completed" in names
