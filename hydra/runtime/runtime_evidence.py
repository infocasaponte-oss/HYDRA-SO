# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""Per-request evidence of live traffic, and the promotion evidence measured from it.

Every routed request appends one JSONL record: which variants served it (primary, shadow copy,
canary), whether each call failed, how long it took and whether shadow and primary agreed. The
deployment controller derives ``ShadowEvidence`` / ``CanaryEvidence`` from these records instead
of trusting numbers sent by an operator."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from hydra.runtime.deployment_evidence import CanaryEvidence, ShadowEvidence
from hydra.runtime.paths import runtime_path


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
    primary_latency_ms: float | None = None
    shadow_error: bool | None = None
    shadow_latency_ms: float | None = None
    canary_variant_id: str | None = None
    canary_error: bool | None = None
    canary_latency_ms: float | None = None


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def p95(values: list[float]) -> float:
    """Nearest-rank 95th percentile (0.0 for no values: the request count gate fails first)."""
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


class RuntimeEvidenceStore:
    def __init__(self, path: str | Path = runtime_path("runtime-evidence.jsonl")):
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
        primary_latency_ms: float | None = None,
        shadow_error: bool | None = None,
        shadow_latency_ms: float | None = None,
        canary_variant_id: str | None = None,
        canary_error: bool | None = None,
        canary_latency_ms: float | None = None,
    ) -> RuntimeEvidence:
        if shadow_variant_id is not None and shadow_error is None:
            shadow_error = shadow_output is None
        record = RuntimeEvidence(
            trace_id=trace_id,
            capability=capability,
            primary_variant_id=primary_variant_id,
            shadow_variant_id=shadow_variant_id,
            primary_output_sha256=_sha256(primary_output),
            shadow_output_sha256=_sha256(shadow_output) if shadow_output is not None else None,
            exact_agreement=primary_output == shadow_output if shadow_output is not None else None,
            created_at=datetime.now(UTC).isoformat(),
            primary_latency_ms=primary_latency_ms,
            shadow_error=shadow_error,
            shadow_latency_ms=shadow_latency_ms,
            canary_variant_id=canary_variant_id,
            canary_error=canary_error,
            canary_latency_ms=canary_latency_ms,
        )
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(record), sort_keys=True) + "\n")
        return record

    def position(self) -> int:
        """Current end of the evidence log. A phase records it when it starts and only counts the
        records written after it: exact, unlike timestamps that can tie at the transition."""
        return self.path.stat().st_size if self.path.is_file() else 0

    def records(self, start: int = 0) -> Iterator[dict]:
        if not self.path.is_file():
            return
        with self.path.open("rb") as handle:
            handle.seek(start)
            for raw in handle:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except ValueError:
                    continue  # a torn last line from a crash is not evidence

    def shadow_evidence(self, variant_id: str, start: int = 0) -> ShadowEvidence:
        """Measured shadow behaviour of ``variant_id``: every mirrored request is a sample, a failed
        shadow call is an error, agreement is over the shadow calls that answered."""
        samples = errors = agreed = 0
        for record in self.records(start):
            if record.get("shadow_variant_id") != variant_id:
                continue
            samples += 1
            failed = record.get("shadow_error")
            if failed is None:  # records written before errors were tracked
                failed = record.get("shadow_output_sha256") is None
            if failed:
                errors += 1
            elif record.get("exact_agreement"):
                agreed += 1
        answered = samples - errors
        return ShadowEvidence(
            samples=samples,
            agreement_rate=agreed / answered if answered else 0.0,
            error_rate=errors / samples if samples else 0.0,
        )

    def canary_evidence(self, variant_id: str, start: int = 0) -> CanaryEvidence:
        """Measured canary behaviour of ``variant_id``: requests routed to it, the share that failed
        (and fell back to the active variant) and the p95 latency of those it answered."""
        requests = errors = 0
        latencies: list[float] = []
        for record in self.records(start):
            if record.get("canary_variant_id") != variant_id:
                continue
            requests += 1
            if record.get("canary_error"):
                errors += 1
            elif record.get("canary_latency_ms") is not None:
                latencies.append(float(record["canary_latency_ms"]))
        return CanaryEvidence(
            requests=requests,
            error_rate=errors / requests if requests else 0.0,
            p95_latency_ms=p95(latencies),
        )
