from __future__ import annotations

from dataclasses import dataclass, field

from hydra.deployment import Deployment, DeploymentState


@dataclass
class DeploymentRegistry:
    deployments: dict[str, Deployment] = field(default_factory=dict)

    def add(self, deployment: Deployment) -> None:
        key = str(deployment.variant_id)
        if key in self.deployments:
            raise ValueError("Deployment already registered")
        self.deployments[key] = deployment

    def active_for(self, capability: str) -> Deployment:
        matches = [
            item
            for item in self.deployments.values()
            if item.state == DeploymentState.ACTIVE and capability in item.capabilities
        ]
        if not matches:
            raise LookupError(f"No ACTIVE deployment for {capability}")
        return max(matches, key=lambda item: item.generation)

    def activate(self, variant_id: str) -> Deployment:
        incoming = self.deployments[variant_id]
        if incoming.state != DeploymentState.CANARY:
            raise ValueError("Only CANARY deployment can become ACTIVE")
        for current in self.deployments.values():
            if current.state != DeploymentState.ACTIVE:
                continue
            if current.capabilities & incoming.capabilities:
                current.transition(DeploymentState.DEPRECATED)
        incoming.transition(DeploymentState.ACTIVE)
        return incoming

    def rollback(self, capability: str) -> Deployment:
        current = self.active_for(capability)
        previous = [
            item
            for item in self.deployments.values()
            if item.state == DeploymentState.DEPRECATED
            and capability in item.capabilities
            and item.generation < current.generation
        ]
        if not previous:
            raise LookupError("No rollback deployment available")
        target = max(previous, key=lambda item: item.generation)
        current.transition(DeploymentState.DEPRECATED)
        target.transition(DeploymentState.ACTIVE)
        return target
