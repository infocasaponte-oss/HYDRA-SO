import pytest

from hydra.deployment import Deployment, DeploymentState
from hydra.deployment_controller import DeploymentController
from hydra.deployment_evidence import CanaryEvidence, ShadowEvidence
from hydra.deployment_registry import DeploymentRegistry
from hydra.model_factory import BuildState, ModelLineage, ModelVariant


def deployment() -> Deployment:
    model = ModelVariant(
        lineage=ModelLineage(base_model="base", base_model_sha256="a" * 64),
        quantization="Q4_K_M",
        artifact_path="model.gguf",
        artifact_sha256="b" * 64,
        state=BuildState.PROMOTED,
    )
    return Deployment(model, {"reasoning.general"}, generation=1)


def test_shadow_needs_evidence():
    registry = DeploymentRegistry()
    item = deployment()
    registry.add(item)
    controller = DeploymentController(registry)
    controller.begin_shadow(item)
    with pytest.raises(ValueError):
        controller.approve_canary(item, ShadowEvidence(2, 1.0, 0.0))


def test_canary_evidence_activates():
    registry = DeploymentRegistry()
    item = deployment()
    registry.add(item)
    controller = DeploymentController(registry)
    controller.begin_shadow(item)
    controller.approve_canary(item, ShadowEvidence(20, 0.96, 0.0))
    controller.activate(item, CanaryEvidence(20, 0.0, 500.0))
    assert item.state == DeploymentState.ACTIVE
