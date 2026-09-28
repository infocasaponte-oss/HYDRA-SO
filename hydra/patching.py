from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from hydra.tools import Workspace


@dataclass(frozen=True)
class PatchResult:
    ok: bool
    output: str


class PatchTool:
    """Apply unified diffs only inside a HYDRA workspace."""

    def __init__(self, workspace: Workspace):
        self.workspace = workspace

    @staticmethod
    def _validate_headers(diff: str) -> None:
        for line in diff.splitlines():
            if line.startswith(("--- ", "+++ ")):
                raw = line[4:].split("\t", 1)[0].strip()
                if raw == "/dev/null":
                    continue
                if raw.startswith(("a/", "b/")):
                    raw = raw[2:]
                path = Path(raw)
                if path.is_absolute() or ".." in path.parts:
                    raise ValueError("Patch path escape rejected")

    def apply(self, diff: str) -> PatchResult:
        self._validate_headers(diff)
        proc = subprocess.run(
            ["git", "apply", "--whitespace=nowarn", "-"],
            input=diff,
            text=True,
            cwd=self.workspace.root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=30,
            check=False,
        )
        return PatchResult(proc.returncode == 0, proc.stdout[-20_000:])
