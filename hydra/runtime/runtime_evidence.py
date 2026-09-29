# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class RuntimeEvidence:
    trace_id: str
    capability: str
    primary_variant_id: str
    shadow_variant_id: str | None
    primary_output_sha256: str
    shadow_output_sha256: str | None
    exact_agreement: bool | None
    created_at: str


class RuntimeEvidenceStore:
    def __init__(self, path: str | Path = "runtime/runtime-evidence.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(
        self,
        *,
        trace_id: str,
        capability: str,
        primary_variant_id: str,
        primary_output: str,
        shadow_variant_id: str | None = None,
        shadow_output: str | None = None,
    ) -> RuntimeEvidence:
        primary_hash = hashlib.sha256(primary_output.encode()).hexdigest()
        shadow_hash = (
            hashlib.sha256(shadow_output.encode()).hexdigest()
            if shadow_output is not None
            else None
        )
        record = RuntimeEvidence(
            trace_id=trace_id,
            capability=capability,
            primary_variant_id=primary_variant_id,
            shadow_variant_id=shadow_variant_id,
            primary_output_sha256=primary_hash,
            shadow_output_sha256=shadow_hash,
            exact_agreement=(
                primary_output == shadow_output
                if shadow_output is not None
                else None
            ),
            created_at=datetime.now(UTC).isoformat(),
        )
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(record), sort_keys=True) + "\n")
        return record
