from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class ModelArtifact:
    name: str
    path: str
    size_bytes: int
    sha256: str

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
        artifacts.append(
            ModelArtifact(
                name=resolved.name,
                path=str(resolved.relative_to(root)),
                size_bytes=resolved.stat().st_size,
                sha256=_sha256(resolved),
            )
        )
    return artifacts
