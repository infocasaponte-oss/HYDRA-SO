# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from hydra.runtime.tools import Workspace


@dataclass(frozen=True)
class PatchResult:
    ok: bool
    output: str


class PatchTool:
    """Apply a constrained unified diff only inside a HYDRA workspace."""

    _REJECTED_PREFIXES = (
        "rename from ",
        "rename to ",
        "copy from ",
        "copy to ",
        "GIT binary patch",
        "Binary files ",
    )

    def __init__(self, workspace: Workspace):
        self.workspace = workspace

    @staticmethod
    def _validate_path(raw: str) -> None:
        raw = raw.strip()
        if not raw or raw.startswith('"') or "\x00" in raw:
            raise ValueError("Unsupported patch path")
        if raw == "/dev/null":
            return
        if raw.startswith(("a/", "b/")):
            raw = raw[2:]
        path = Path(raw)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("Patch path escape rejected")
        if ".git" in path.parts:
            raise ValueError("Patch may not modify Git metadata")

    @classmethod
    def _validate_headers(cls, diff: str) -> None:
        saw_old = False
        saw_new = False

        for line in diff.splitlines():
            if line.startswith(cls._REJECTED_PREFIXES):
                raise ValueError("Unsupported patch metadata")
            if line in {"new file mode 120000", "old mode 120000"}:
                raise ValueError("Symlink patches are not allowed")
            if line.startswith("diff --git "):
                parts = line.split()
                if len(parts) != 4:
                    raise ValueError("Unsupported diff path encoding")
                cls._validate_path(parts[2])
                cls._validate_path(parts[3])
            elif line.startswith("--- "):
                raw = line[4:].split("\t", 1)[0]
                cls._validate_path(raw)
                saw_old = True
            elif line.startswith("+++ "):
                raw = line[4:].split("\t", 1)[0]
                cls._validate_path(raw)
                saw_new = True

        if not saw_old or not saw_new:
            raise ValueError("Patch requires --- and +++ headers")

    def _contains_symlink(self) -> bool:
        for directory, dirnames, filenames in os.walk(
            self.workspace.root,
            followlinks=False,
        ):
            directory_path = Path(directory)
            for name in [*dirnames, *filenames]:
                if (directory_path / name).is_symlink():
                    return True
        return False

    def _git_apply(self, diff: str, *, reverse: bool = False) -> PatchResult:
        self._validate_headers(diff)
        command = ["git", "apply", "--whitespace=nowarn"]
        if reverse:
            command.append("--reverse")
        command.append("-")
        proc = subprocess.run(
            command,
            input=diff,
            text=True,
            cwd=self.workspace.root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=30,
            check=False,
        )
        output = proc.stdout[-20_000:]
        if proc.returncode != 0:
            return PatchResult(False, output)
        if self._contains_symlink():
            return PatchResult(False, output + "\nPatch created a forbidden symlink")
        return PatchResult(True, output)

    def apply(self, diff: str) -> PatchResult:
        return self._git_apply(diff)

    def revert(self, diff: str) -> PatchResult:
        """Reverse exactly a previously applied diff without touching unrelated workspace changes."""
        return self._git_apply(diff, reverse=True)
