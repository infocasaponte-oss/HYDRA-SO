# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""Adapter Factory: one base model + many LoRA adapters instead of many full models.

    qwen-7b base ── router adapter ── critic adapter ── tool adapter
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel


class AdapterSpec(BaseModel):
    logical_model: str  # e.g. hydra-critic
    base_model: str  # e.g. qwen-7b (HF id / path / ollama name)
    adapter_name: str  # e.g. critic-v7
    adapter_path: str
    runtime: str = "vllm"  # vllm (--lora-modules) | ollama (ADAPTER)
    endpoint: str | None = None


class AdapterRegistry:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.adapters: dict[str, AdapterSpec] = {}
        if path.exists():
            self.adapters = {k: AdapterSpec.model_validate(v)
                             for k, v in json.loads(path.read_text(encoding="utf-8")).items()}

    def register(self, spec: AdapterSpec) -> AdapterSpec:
        self.adapters[spec.logical_model] = spec
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({k: v.model_dump() for k, v in self.adapters.items()}, indent=1),
                             encoding="utf-8")
        return spec

    def for_base(self, base: str) -> list[AdapterSpec]:
        return [a for a in self.adapters.values() if a.base_model == base]

    @staticmethod
    def vllm_flags(specs: list[AdapterSpec]) -> list[str]:
        """vLLM serves every adapter of a base from a single process."""
        if not specs:
            return []
        return ["--enable-lora", "--lora-modules", *[f"{s.adapter_name}={s.adapter_path}" for s in specs],
                "--max-loras", str(max(1, len(specs)))]
