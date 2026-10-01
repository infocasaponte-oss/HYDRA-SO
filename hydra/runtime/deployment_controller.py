# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""SHADOW -> CANARY -> ACTIVE promotions gated by evidence.

The evidence is measured by the server from live traffic (``RuntimeEvidenceStore``), counted only
from the records written after the deployment entered the phase being judged (log offset). Callers may still pass explicit
evidence in-process (offline evaluation, tests), but the admin API never accepts it from a client."""

from __future__ import annotations

from datetime import UTC, datetime

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
from hydra.runtime.runtime_evidence import RuntimeEvidenceStore

SHADOW_STARTED_AT = "shadow_started_at"
CANARY_STARTED_AT = "canary_started_at"
SHADOW_EVIDENCE_OFFSET = "shadow_evidence_offset"
CANARY_EVIDENCE_OFFSET = "canary_evidence_offset"


class EvidenceRejected(ValueError):
    """The measured evidence does not satisfy the deployment policy."""

    def __init__(self, message: str, evidence: ShadowEvidence | CanaryEvidence):
        super().__init__(message)
        self.evidence = evidence


def _now() -> str:
    return datetime.now(UTC).isoformat()


class DeploymentController:
    def __init__(
        self,
        registry: DeploymentRegistry,
        policy: DeploymentPolicy | None = None,
        evidence_store: DeploymentEvidenceStore | None = None,
        runtime_evidence: RuntimeEvidenceStore | None = None,
    ):
        self.registry = registry
        self.policy = policy or DeploymentPolicy()
        self.evidence_store = evidence_store
        self.runtime_evidence = runtime_evidence

    def begin_shadow(self, deployment: Deployment) -> None:
        deployment.transition(DeploymentState.SHADOW)
        self._mark_phase(deployment, SHADOW_STARTED_AT, SHADOW_EVIDENCE_OFFSET)

    def measure_shadow(self, deployment: Deployment) -> ShadowEvidence:
        return self._store().shadow_evidence(
            str(deployment.variant_id), int(deployment.metadata.get(SHADOW_EVIDENCE_OFFSET, 0))
        )

    def measure_canary(self, deployment: Deployment) -> CanaryEvidence:
        return self._store().canary_evidence(
            str(deployment.variant_id), int(deployment.metadata.get(CANARY_EVIDENCE_OFFSET, 0))
        )

    def _mark_phase(self, deployment: Deployment, started_key: str, offset_key: str) -> None:
        deployment.metadata[started_key] = _now()
        if self.runtime_evidence is not None:
            deployment.metadata[offset_key] = self.runtime_evidence.position()

    def approve_canary(
        self, deployment: Deployment, evidence: ShadowEvidence | None = None
    ) -> ShadowEvidence:
        if deployment.state != DeploymentState.SHADOW:
            raise ValueError("Deployment is not in SHADOW")
        evidence = evidence if evidence is not None else self.measure_shadow(deployment)
        if not shadow_passes(evidence, self.policy):
            raise EvidenceRejected("Shadow evidence did not pass deployment policy", evidence)
        deployment.metadata["shadow_samples"] = evidence.samples
        if self.evidence_store is not None:
            self.evidence_store.append_shadow(str(deployment.variant_id), evidence)
        deployment.transition(DeploymentState.CANARY)
        self._mark_phase(deployment, CANARY_STARTED_AT, CANARY_EVIDENCE_OFFSET)
        return evidence

    def activate(
        self, deployment: Deployment, evidence: CanaryEvidence | None = None
    ) -> Deployment:
        if deployment.state != DeploymentState.CANARY:
            raise ValueError("Deployment is not in CANARY")
        evidence = evidence if evidence is not None else self.measure_canary(deployment)
        if not canary_passes(evidence, self.policy):
            raise EvidenceRejected("Canary evidence did not pass deployment policy", evidence)
        deployment.metadata["canary_requests"] = evidence.requests
        if self.evidence_store is not None:
            self.evidence_store.append_canary(str(deployment.variant_id), evidence)
        return self.registry.activate(str(deployment.variant_id))

    def _store(self) -> RuntimeEvidenceStore:
        if self.runtime_evidence is None:
            raise ValueError("No runtime evidence store: promotion evidence cannot be measured")
        return self.runtime_evidence
