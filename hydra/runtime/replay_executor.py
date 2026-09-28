from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from hydra.runtime.events import JsonlEventStore
from hydra.runtime.provenance import ProvenanceLedger
from hydra.runtime.replay import ReplayManifest
from hydra.runtime.replay_integrity import verify_replay_sources


@dataclass(frozen=True)
class AuditReplayResult:
    valid: bool
    checked_artifacts: int
    event_records: int
    provenance_records: int
    error: str | None = None


def verify_manifest_hash(manifest: ReplayManifest) -> bool:
    body = manifest.model_dump(mode="json", exclude={"manifest_hash"})
    digest = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return digest == manifest.manifest_hash


class AuditReplayExecutor:
    def __init__(
        self,
        *,
        events: JsonlEventStore,
        provenance: ProvenanceLedger,
        artifact_root: str | Path = "runtime/artifacts",
    ):
        self.events = events
        self.provenance = provenance
        self.artifact_root = Path(artifact_root)

    def audit(self, manifest: ReplayManifest) -> AuditReplayResult:
        if not verify_manifest_hash(manifest):
            return AuditReplayResult(
                valid=False,
                checked_artifacts=0,
                event_records=0,
                provenance_records=0,
                error="replay manifest hash mismatch",
            )

        sources = verify_replay_sources(self.events, self.provenance)
        if not sources.valid:
            return AuditReplayResult(
                valid=False,
                checked_artifacts=0,
                event_records=sources.event_records,
                provenance_records=sources.provenance_records,
                error=sources.error,
            )

        checked = 0
        for digest in manifest.artifact_hashes:
            if len(digest) != 64:
                return AuditReplayResult(
                    valid=False,
                    checked_artifacts=checked,
                    event_records=sources.event_records,
                    provenance_records=sources.provenance_records,
                    error="invalid artifact digest",
                )
            blob = self.artifact_root / "sha256" / digest[:2] / digest
            if not blob.is_file():
                return AuditReplayResult(
                    valid=False,
                    checked_artifacts=checked,
                    event_records=sources.event_records,
                    provenance_records=sources.provenance_records,
                    error=f"artifact missing: {digest}",
                )
            actual = hashlib.sha256(blob.read_bytes()).hexdigest()
            if actual != digest:
                return AuditReplayResult(
                    valid=False,
                    checked_artifacts=checked,
                    event_records=sources.event_records,
                    provenance_records=sources.provenance_records,
                    error=f"artifact hash mismatch: {digest}",
                )
            checked += 1

        return AuditReplayResult(
            valid=True,
            checked_artifacts=checked,
            event_records=sources.event_records,
            provenance_records=sources.provenance_records,
        )
