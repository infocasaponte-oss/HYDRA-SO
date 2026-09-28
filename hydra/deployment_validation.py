from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from hydra.model_factory import ModelVariant
from hydra.model_scout import ModelArtifact, inspect_model_artifact


@dataclass(frozen=True)
class DeploymentArtifactValidator:
    models_root: Path

    def __init__(self, models_root: str | Path):
        object.__setattr__(self, "models_root", Path(models_root).resolve())

    def validate(self, variant: ModelVariant) -> ModelArtifact:
        artifact = inspect_model_artifact(
            self.models_root,
            variant.artifact_path,
        )
        if artifact.sha256 != variant.artifact_sha256:
            raise ValueError("Model artifact SHA-256 does not match variant declaration")
        if not artifact.gguf_valid:
            raise ValueError("Model artifact is not a valid GGUF")
        if not artifact.runtime_eligible:
            raise ValueError(
                "Model artifact lacks required runtime GGUF metadata"
            )
        return artifact
