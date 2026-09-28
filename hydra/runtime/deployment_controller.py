from __future__ import annotations

from hydra.runtime.deployment import Deployment, DeploymentState
from hydra.runtime.deployment_evidence import (
    CanaryEvidence,
    DeploymentPolicy,
    ShadowEvidence,
    canary_passes,
    shadow_passes,
)
from hydra.runtime.deployment_evidence_store import DeploymentEvidenceStore
from hydra.runtime.deployment_registry import DeploymentRegistry


class DeploymentController:
    def __init__(
        self,
        registry: DeploymentRegistry,
        policy: DeploymentPolicy | None = None,
        evidence_store: DeploymentEvidenceStore | None = None,
    ):
        self.registry = registry
        self.policy = policy or DeploymentPolicy()
        self.evidence_store = evidence_store

    def begin_shadow(self, deployment: Deployment) -> None:
        deployment.transition(DeploymentState.SHADOW)

    def approve_canary(
        self, deployment: Deployment, evidence: ShadowEvidence
    ) -> None:
        if deployment.state != DeploymentState.SHADOW:
            raise ValueError("Deployment is not in SHADOW")
        if not shadow_passes(evidence, self.policy):
            raise ValueError("Shadow evidence did not pass deployment policy")
        deployment.metadata["shadow_samples"] = evidence.samples
        if self.evidence_store is not None:
            self.evidence_store.append_shadow(str(deployment.variant_id), evidence)
        deployment.transition(DeploymentState.CANARY)

    def activate(
        self, deployment: Deployment, evidence: CanaryEvidence
    ) -> Deployment:
        if deployment.state != DeploymentState.CANARY:
            raise ValueError("Deployment is not in CANARY")
        if not canary_passes(evidence, self.policy):
            raise ValueError("Canary evidence did not pass deployment policy")
        deployment.metadata["canary_requests"] = evidence.requests
        if self.evidence_store is not None:
            self.evidence_store.append_canary(str(deployment.variant_id), evidence)
        return self.registry.activate(str(deployment.variant_id))
