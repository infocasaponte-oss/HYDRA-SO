from hydra.deployment import Deployment, DeploymentState
from hydra.deployment_registry import DeploymentRegistry
from hydra.deployment_store import DeploymentStore
from hydra.model_factory import BuildState, ModelLineage, ModelVariant


def test_round_trip_registry(tmp_path):
    variant = ModelVariant(
        lineage=ModelLineage(base_model="base", base_model_sha256="a" * 64),
        quantization="Q4_K_M",
        artifact_path="model.gguf",
        artifact_sha256="b" * 64,
        state=BuildState.PROMOTED,
    )
    deployment = Deployment(
        variant=variant,
        capabilities={"reasoning.general"},
        state=DeploymentState.ACTIVE,
        generation=3,
    )
    registry = DeploymentRegistry()
    registry.add(deployment)
    store = DeploymentStore(tmp_path / "deployments.json")
    store.save(registry)
    loaded = store.load()
    restored = loaded.active_for("reasoning.general")
    assert restored.generation == 3
    assert restored.variant.variant_id == variant.variant_id
