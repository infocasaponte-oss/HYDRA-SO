# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""Factory store: artifacts, variants, lineage, jobs + the Logical Model Resolver.

    await models.resolve("hydra-reasoner", {"quality": 0.95, "max_memory_gb": 12, "local": True})
    -> hydra-reasoner-14b-q5_k_m.gguf here, hydra-reasoner-14b-fp8 on another server.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from hydra.model_factory.hardware import HardwareProfile, preferred_formats
from hydra.model_factory.manifest import FactoryJob, ModelArtifact, ModelFormat, ModelLineage, ModelVariant


class ResolveConstraints(BaseModel):
    quality: float | None = None
    max_memory_gb: float | None = None
    local: bool | None = None
    formats: list[ModelFormat] | None = None
    min_tokens_per_second: float | None = None
    hardware: HardwareProfile | None = None
    include_unapproved: bool = False


class FactoryStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.artifacts: dict[str, ModelArtifact] = self._load("artifacts.json", ModelArtifact)
        self.variants: dict[str, ModelVariant] = self._load("variants.json", ModelVariant)
        self.lineage: dict[str, ModelLineage] = self._load("lineage.json", ModelLineage)
        self.jobs: dict[str, FactoryJob] = self._load("jobs.json", FactoryJob)

    def _load(self, name: str, model: type[BaseModel]) -> dict[str, Any]:
        p = self.root / name
        if not p.exists():
            return {}
        return {k: model.model_validate(v) for k, v in json.loads(p.read_text(encoding="utf-8")).items()}

    def _save(self, name: str, data: dict[str, BaseModel]) -> None:
        with self._lock:
            tmp = self.root / f".{name}.tmp"
            tmp.write_text(json.dumps({k: v.model_dump(mode="json") for k, v in data.items()}, indent=1),
                           encoding="utf-8")
            tmp.replace(self.root / name)

    def dir_for(self, logical: str) -> Path:
        d = self.root / "builds" / logical.replace("/", "_").replace(":", "_")
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ------------------------------------------------------------------ artifacts
    def add_artifact(self, a: ModelArtifact, lineage: ModelLineage) -> ModelArtifact:
        self.artifacts[a.id] = a
        self.lineage[a.id] = lineage
        self._save("artifacts.json", self.artifacts)
        self._save("lineage.json", self.lineage)
        return a

    def source_of(self, logical: str) -> ModelArtifact | None:
        cands = [a for a in self.artifacts.values() if a.logical_model == logical and a.parent_id is None]
        return max(cands, key=lambda a: a.created_at) if cands else None

    def artifacts_of(self, logical: str) -> list[ModelArtifact]:
        return sorted((a for a in self.artifacts.values() if a.logical_model == logical), key=lambda a: a.created_at)

    def ancestry(self, artifact_id: str) -> list[ModelLineage]:
        chain, seen = [], set()
        todo = [artifact_id]
        while todo:
            aid = todo.pop()
            if aid in seen or aid not in self.lineage:
                continue
            seen.add(aid)
            node = self.lineage[aid]
            chain.append(node)
            todo += node.parent_ids
        return chain

    # ------------------------------------------------------------------ variants
    def upsert_variant(self, v: ModelVariant) -> ModelVariant:
        self.variants[v.id] = v
        self._save("variants.json", self.variants)
        return v

    def variants_of(self, logical: str) -> list[ModelVariant]:
        return [v for v in self.variants.values() if v.logical_model == logical]

    def logical_models(self) -> list[str]:
        return sorted({a.logical_model for a in self.artifacts.values()})

    # ------------------------------------------------------------------ jobs
    def save_job(self, job: FactoryJob) -> FactoryJob:
        self.jobs[job.id] = job
        self._save("jobs.json", self.jobs)
        return job

    def reload_jobs(self) -> None:
        self.jobs = self._load("jobs.json", FactoryJob)

    # ------------------------------------------------------------------ resolver
    def resolve(self, logical: str, constraints: ResolveConstraints | dict | None = None) -> ModelVariant | None:
        c = constraints if isinstance(constraints, ResolveConstraints) else ResolveConstraints.model_validate(
            constraints or {})
        pool = [v for v in self.variants_of(logical)
                if (v.approved or c.include_unapproved) and v.status != "retired"]
        max_mem = c.max_memory_gb
        if c.hardware is not None:
            max_mem = min(max_mem or 1e9, c.hardware.memory_budget_gb)
        if max_mem is not None:
            pool = [v for v in pool if v.memory_gb <= max_mem]
        if c.quality is not None:
            pool = [v for v in pool if v.quality_score >= c.quality]
        if c.min_tokens_per_second is not None:
            pool = [v for v in pool if v.tokens_per_second >= c.min_tokens_per_second]
        if c.local:
            pool = [v for v in pool if v.runtime in ("ollama", "llamacpp", "mlx", "onnx", "vllm")]
        order = c.formats or (preferred_formats(c.hardware) if c.hardware else None)
        if order:
            pool = [v for v in pool if v.format in order or v.format == ModelFormat.OLLAMA]

        def key(v: ModelVariant):
            fmt_rank = order.index(v.format) if order and v.format in order else len(order or [])
            return (-round(v.quality_score, 2), fmt_rank, -v.tokens_per_second, v.memory_gb)

        return min(pool, key=key) if pool else None
