import pytest

from hydra.deployment import Deployment, DeploymentState
from hydra.deployment_registry import DeploymentRegistry
from hydra.deployment_resolver import DeploymentResolver
from hydra.model_factory import BuildState, ModelLineage, ModelVariant


def promoted(quant: str) -> ModelVariant:
    return ModelVariant(
        lineage=ModelLineage(base_model="base", base_model_sha256="a" * 64),
        quantization=quant,
        artifact_path=f"{quant}.gguf",
        artifact_sha256="b" * 64,
        state=BuildState.PROMOTED,
    )


def deploy(quant: str, generation: int) -> Deployment:
    item = Deployment(
        variant=promoted(quant),
        capabilities={"reasoning.general"},
        generation=generation,
    )
    item.transition(DeploymentState.SHADOW)
    item.transition(DeploymentState.CANARY)
    return item


def test_candidate_cannot_skip_to_active():
    item = Deployment(variant=promoted("Q4_K_M"), capabilities={"reasoning.general"})
    with pytest.raises(ValueError):
        item.transition(DeploymentState.ACTIVE)


def test_activate_preserves_previous_for_rollback():
    registry = DeploymentRegistry()
    old = deploy("Q4_K_M", 1)
    registry.add(old)
    registry.activate(str(old.variant_id))
    new = deploy("Q5_K_M", 2)
    registry.add(new)
    registry.activate(str(new.variant_id))
    assert old.state == DeploymentState.DEPRECATED
    assert DeploymentResolver(registry).resolve("reasoning.general") is new
    restored = registry.rollback("reasoning.general")
    assert restored is old
    assert old.state == DeploymentState.ACTIVE
