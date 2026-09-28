from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ArtifactRecord(BaseModel):
    artifact_id: UUID = Field(default_factory=uuid4)
    task_id: UUID
    kind: str
    media_type: str
    sha256: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict = Field(default_factory=dict)


class ArtifactStore:
    def __init__(self, root: str | Path = "runtime/artifacts"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def put_bytes(
        self,
        *,
        task_id: UUID,
        kind: str,
        data: bytes,
        media_type: str = "application/octet-stream",
        metadata: dict | None = None,
    ) -> ArtifactRecord:
        digest = hashlib.sha256(data).hexdigest()
        blob = self.root / "sha256" / digest[:2] / digest
        blob.parent.mkdir(parents=True, exist_ok=True)
        if not blob.exists():
            blob.write_bytes(data)
        record = ArtifactRecord(
            task_id=task_id,
            kind=kind,
            media_type=media_type,
            sha256=digest,
            metadata=metadata or {},
        )
        manifest = self.root / "manifests"
        manifest.mkdir(parents=True, exist_ok=True)
        (manifest / f"{record.artifact_id}.json").write_text(
            record.model_dump_json(indent=2), encoding="utf-8"
        )
        return record

    def get_bytes(self, sha256: str, *, max_bytes: int | None = None) -> bytes:
        if len(sha256) != 64:
            raise ValueError("Artifact SHA-256 must contain 64 hex characters")
        try:
            int(sha256, 16)
        except ValueError as exc:
            raise ValueError("Artifact SHA-256 must be hexadecimal") from exc

        blob = self.root / "sha256" / sha256[:2] / sha256
        if not blob.is_file():
            raise FileNotFoundError(f"Artifact blob not found: {sha256}")
        if max_bytes is not None and blob.stat().st_size > max_bytes:
            raise ValueError("Artifact exceeds read limit")
        return blob.read_bytes()

    def get_text(self, sha256: str, *, max_bytes: int | None = None) -> str:
        data = self.get_bytes(sha256, max_bytes=max_bytes)
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("Artifact is not valid UTF-8 text") from exc

    def put_text(self, *, task_id: UUID, kind: str, text: str, metadata: dict | None = None):
        return self.put_bytes(
            task_id=task_id,
            kind=kind,
            data=text.encode("utf-8"),
            media_type="text/plain; charset=utf-8",
            metadata=metadata,
        )
