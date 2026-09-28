from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path

from hydra.gguf import GGUFError, inspect_gguf


@dataclass(frozen=True)
class ModelArtifact:
    name: str
    path: str
    size_bytes: int
    sha256: str
    gguf_valid: bool = False
    gguf_version: int | None = None
    tensor_count: int | None = None
    architecture: str | None = None
    model_name: str | None = None
    context_length: int | None = None
    embedding_length: int | None = None
    block_count: int | None = None
    file_type: int | None = None
    quantization_version: int | None = None
    metadata_error: str | None = None
    runtime_eligible: bool = False

    def as_dict(self) -> dict:
        return asdict(self)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def scan_models(models_root: str | Path) -> list[ModelArtifact]:
    root = Path(models_root).resolve()
    if not root.exists():
        return []
    artifacts = []
    for path in sorted(root.rglob("*.gguf")):
        resolved = path.resolve()
        if root not in resolved.parents:
            continue

        metadata = None
        metadata_error = None
        try:
            metadata = inspect_gguf(resolved)
        except (GGUFError, OSError) as exc:
            metadata_error = str(exc)

        artifacts.append(
            ModelArtifact(
                name=resolved.name,
                path=str(resolved.relative_to(root)),
                size_bytes=resolved.stat().st_size,
                sha256=_sha256(resolved),
                gguf_valid=metadata is not None,
                gguf_version=metadata.version if metadata else None,
                tensor_count=metadata.tensor_count if metadata else None,
                architecture=metadata.architecture if metadata else None,
                model_name=metadata.model_name if metadata else None,
                context_length=metadata.context_length if metadata else None,
                embedding_length=metadata.embedding_length if metadata else None,
                block_count=metadata.block_count if metadata else None,
                file_type=metadata.file_type if metadata else None,
                quantization_version=(
                    metadata.quantization_version if metadata else None
                ),
                metadata_error=metadata_error,
                runtime_eligible=bool(
                    metadata
                    and metadata.tensor_count > 0
                    and metadata.architecture
                    and metadata.context_length
                    and metadata.context_length > 0
                    and metadata.embedding_length
                    and metadata.embedding_length > 0
                    and metadata.block_count
                    and metadata.block_count > 0
                ),
            )
        )
    return artifacts
