from __future__ import annotations

import json
from pathlib import Path

from hydra.deployment import Deployment
from hydra.deployment_registry import DeploymentRegistry
from hydra.model_factory import ModelVariant


class DeploymentStore:
    def __init__(self, path: str | Path = "runtime/deployments.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, registry: DeploymentRegistry) -> None:
        body = [
            {
                "variant": item.variant.model_dump(mode="json"),
                "capabilities": sorted(item.capabilities),
                "state": item.state.value,
                "generation": item.generation,
                "metadata": item.metadata,
            }
            for item in registry.deployments.values()
        ]
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(body, sort_keys=True, indent=2),
            encoding="utf-8",
        )
        tmp.replace(self.path)

    def load(self) -> DeploymentRegistry:
        registry = DeploymentRegistry()
        if not self.path.exists():
            return registry
        body = json.loads(self.path.read_text(encoding="utf-8"))
        for raw in body:
            variant = ModelVariant.model_validate(raw["variant"])
            deployment = Deployment(
                variant=variant,
                capabilities=set(raw["capabilities"]),
                state=raw["state"],
                generation=raw["generation"],
                metadata=raw.get("metadata", {}),
            )
            registry.add(deployment)
        return registry
