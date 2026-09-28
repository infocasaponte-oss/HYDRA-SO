# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""Failure Memory: operational errors, kept apart from knowledge memory.

    model X fails with structured output      model Y breaks with context > 80k
    tool Z usually times out                  runtime R runs out of memory

The scheduler consults it to avoid known failure patterns before they happen.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from hydra.core.events import EventType, HydraEvent

CONDITION_KEYS = ("ctx_bucket", "structured", "tools", "images")


class FailurePattern(BaseModel):
    subject_type: str  # model | tool
    subject_id: str
    kind: str
    condition: dict = Field(default_factory=dict)
    failures: int = 0
    last_seen: datetime | None = None


def _cond(payload: dict) -> tuple:
    return tuple((k, payload.get(k)) for k in CONDITION_KEYS if k in payload)


class FailureMemory:
    def __init__(self, path: Path | None = None, min_observations: int = 3, avoid_above: float = 0.5) -> None:
        self.path = path
        self.min_observations = min_observations
        self.avoid_above = avoid_above
        # (subject_type, subject_id, condition) -> [runs, failures]
        self.stats: dict[tuple, list[int]] = defaultdict(lambda: [0, 0])
        self.patterns: dict[tuple, FailurePattern] = {}
        self._load()

    # ------------------------------------------------------------------ learning
    async def observe(self, event: HydraEvent) -> None:
        p = event.payload
        if event.type in (EventType.MODEL_COMPLETED, EventType.MODEL_FAILED):
            key = ("model", p.get("model", "?"), _cond(p))
            self.stats[key][0] += 1
            if event.type == EventType.MODEL_FAILED:
                self._record(key, p.get("kind", "unknown"))
        elif event.type in (EventType.TOOL_COMPLETED, EventType.TOOL_FAILED):
            key = ("tool", p.get("tool", "?"), ())
            self.stats[key][0] += 1
            if event.type == EventType.TOOL_FAILED and p.get("kind") in ("timeout", "tool_error"):
                self._record(key, p["kind"])

    def _record(self, key: tuple, kind: str) -> None:
        self.stats[key][1] += 1
        pkey = (*key, kind)
        pat = self.patterns.get(pkey) or FailurePattern(
            subject_type=key[0], subject_id=key[1], kind=kind, condition=dict(key[2]))
        pat.failures += 1
        pat.last_seen = datetime.now(UTC)
        self.patterns[pkey] = pat
        self._save()

    # ------------------------------------------------------------------ querying
    def failure_rate(self, subject_type: str, subject_id: str, condition: dict | None = None) -> tuple[float, int]:
        """Failure rate under a condition (all conditions if None) and number of observations."""
        runs = fails = 0
        want = tuple((k, condition[k]) for k in CONDITION_KEYS if condition and k in condition)
        for (st, sid, cond), (r, f) in self.stats.items():
            if st != subject_type or sid != subject_id:
                continue
            if want and not set(want) <= set(cond):
                continue
            runs += r
            fails += f
        return (fails / runs if runs else 0.0), runs

    def should_avoid(self, model_id: str, condition: dict) -> bool:
        rate, n = self.failure_rate("model", model_id, condition)
        return n >= self.min_observations and rate > self.avoid_above

    def report(self) -> list[dict]:
        out = []
        for pat in sorted(self.patterns.values(), key=lambda p: -p.failures):
            key = (pat.subject_type, pat.subject_id, tuple(pat.condition.items()))
            runs = self.stats.get(key, [0, 0])[0]
            out.append({**pat.model_dump(mode="json"), "runs": runs,
                        "failure_rate": round(pat.failures / runs, 3) if runs else None})
        return out

    # ------------------------------------------------------------------ persistence
    def _save(self) -> None:
        if self.path is None:
            return
        data = {"stats": [[list(k[:2]), [list(c) for c in k[2]], v] for k, v in self.stats.items()],
                "patterns": [p.model_dump(mode="json") for p in self.patterns.values()]}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data), encoding="utf-8")

    def _load(self) -> None:
        if self.path is None or not self.path.exists():
            return
        data = json.loads(self.path.read_text(encoding="utf-8"))
        for (st, sid), cond, v in data.get("stats", []):
            self.stats[(st, sid, tuple(tuple(c) for c in cond))] = v
        for p in data.get("patterns", []):
            pat = FailurePattern.model_validate(p)
            self.patterns[(pat.subject_type, pat.subject_id, tuple(pat.condition.items()), pat.kind)] = pat
