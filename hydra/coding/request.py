# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""Coding requests and the repository they target (confined)."""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class CodingRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=20_000)
    repository: str = Field(min_length=1, max_length=500)
    max_tokens: int = Field(default=2048, ge=128, le=8192)


def resolve_repository(root: str | Path, repository: str) -> Path:
    base = Path(root).resolve()
    candidate = (base / repository).resolve()
    if candidate != base and base not in candidate.parents:
        raise ValueError("Repository path escape rejected")
    if not candidate.is_dir():
        raise ValueError("Repository does not exist")
    return candidate
