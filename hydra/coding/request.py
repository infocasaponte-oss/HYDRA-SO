# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""Coding requests and the repository they target (confined)."""
from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field


class CodingRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=20_000)
    repository: str = Field(min_length=1, max_length=500)
    max_tokens: int = Field(default=2048, ge=128, le=8192)


def resolve_repository(root: str | Path, repository: str) -> Path:
    """The repository directory ``repository`` names inside ``root`` (``root`` itself included). Symlinks
    are resolved first, so a link pointing outside ``root`` is rejected like ``../``."""
    base = os.path.realpath(root)
    candidate = os.path.realpath(os.path.join(base, repository))
    if candidate != base and not candidate.startswith(base + os.sep):
        raise ValueError("Repository path escape rejected")
    if not os.path.isdir(candidate):
        raise ValueError("Repository does not exist")
    return Path(candidate)
