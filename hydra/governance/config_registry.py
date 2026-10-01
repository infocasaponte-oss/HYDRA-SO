# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""Configuration Registry and Feature Flags.

Nothing important lives only in environment variables: router weights, policy sets,
model profiles, eval thresholds, corpus filters and scheduler parameters are versioned
config sets (``config-set/production/172``) linked to every trace, so HYDRA can always
reproduce why it took a decision. Feature flags ship changes gradually:
``new_scheduler=false``, ``belief_v3=10%``, ``new_critic=shadow``."""

from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from hydra.core.atomic import write_text_atomic
from hydra.core.hashing import hash_obj, now_iso
from hydra.core.paths import safe_id


class ConfigSet(BaseModel):
    environment: str
    version: int
    created_at: str = Field(default_factory=now_iso)
    author: str = "hydra"
    message: str = ""
    values: dict[str, Any]
    content_hash: str = ""
    parent: int | None = None

    @property
    def ref(self) -> str:
        return f"config-set/{self.environment}/{self.version}"


class ConfigRegistry:
    def __init__(self, root: Path, ledger=None) -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.ledger = ledger
        self._lock = threading.Lock()

    def _path(self, env: str) -> Path:
        # The environment name becomes a file name: never let it carry separators or '..'.
        return self.root / f"{safe_id(env, 'config environment')}.jsonl"

    def history(self, env: str) -> list[ConfigSet]:
        p = self._path(env)
        if not p.exists():
            return []
        return [ConfigSet.model_validate_json(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]

    def current(self, env: str) -> ConfigSet | None:
        h = self.history(env)
        return h[-1] if h else None

    def get(self, env: str, version: int) -> ConfigSet:
        return next(c for c in self.history(env) if c.version == version)

    def commit(self, env: str, values: dict[str, Any], author: str = "hydra", message: str = "") -> ConfigSet:
        with self._lock:
            cur = self.current(env)
            merged = {**(cur.values if cur else {}), **values}
            c = ConfigSet(environment=env, version=(cur.version + 1) if cur else 1, author=author, message=message,
                          values=merged, content_hash=hash_obj(merged), parent=cur.version if cur else None)
            with open(self._path(env), "a", encoding="utf-8") as f:
                f.write(c.model_dump_json() + "\n")
        if self.ledger is not None:
            self.ledger.append("CONFIG_CHANGED", {"ref": c.ref, "hash": c.content_hash, "author": author,
                                                  "message": message, "keys": sorted(values)},
                               object_type="config", object_id=c.ref)
        return c

    def diff(self, env: str, a: int, b: int) -> dict[str, Any]:
        va, vb = self.get(env, a).values, self.get(env, b).values
        return {k: {"from": va.get(k), "to": vb.get(k)} for k in sorted(set(va) | set(vb)) if va.get(k) != vb.get(k)}

    def rollback(self, env: str, version: int, author: str) -> ConfigSet:
        target = self.get(env, version)
        with self._lock:
            cur = self.current(env)
            c = ConfigSet(environment=env, version=cur.version + 1, author=author,
                          message=f"rollback to {version}", values=target.values, content_hash=target.content_hash,
                          parent=cur.version)
            with open(self._path(env), "a", encoding="utf-8") as f:
                f.write(c.model_dump_json() + "\n")
        return c


class FeatureFlag(BaseModel):
    name: str
    mode: str = "off"
    """off | on | percent | shadow"""
    percent: float = 0.0
    description: str = ""
    updated_at: str = Field(default_factory=now_iso)


class FeatureFlags:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.flags: dict[str, FeatureFlag] = {}
        if path.exists():
            for k, v in json.loads(path.read_text(encoding="utf-8")).items():
                self.flags[k] = FeatureFlag(**v)

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        write_text_atomic(self.path, json.dumps({k: v.model_dump() for k, v in self.flags.items()}, indent=2))

    def set(self, name: str, value: str | bool | float, description: str = "") -> FeatureFlag:
        if isinstance(value, bool):
            f = FeatureFlag(name=name, mode="on" if value else "off")
        elif isinstance(value, (int, float)):
            f = FeatureFlag(name=name, mode="percent", percent=float(value))
        elif str(value).endswith("%"):
            f = FeatureFlag(name=name, mode="percent", percent=float(str(value)[:-1]))
        elif str(value).lower() in ("on", "true", "1"):
            f = FeatureFlag(name=name, mode="on")
        elif str(value).lower() == "shadow":
            f = FeatureFlag(name=name, mode="shadow")
        else:
            f = FeatureFlag(name=name, mode="off")
        f.description = description
        self.flags[name] = f
        self._save()
        return f

    def enabled(self, name: str, key: str = "") -> bool:
        f = self.flags.get(name)
        if f is None or f.mode in ("off", "shadow"):
            return False
        if f.mode == "on":
            return True
        bucket = int(hashlib.sha256(f"{name}:{key}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF * 100
        return bucket < f.percent

    def shadow(self, name: str) -> bool:
        f = self.flags.get(name)
        return f is not None and f.mode == "shadow"

    def snapshot(self) -> dict[str, str]:
        return {k: (f"{v.percent:g}%" if v.mode == "percent" else v.mode) for k, v in self.flags.items()}
