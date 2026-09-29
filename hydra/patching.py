from __future__ import annotations

import os
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

from hydra.tools import Workspace


@dataclass(frozen=True)
class PatchResult:
    ok: bool
    output: str


@dataclass(frozen=True)
class PatchFileSnapshot:
    path: str
    content: bytes | None
    mode: int | None


@dataclass(frozen=True)
class PatchSnapshot:
    files: tuple[PatchFileSnapshot, ...]


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

    @staticmethod
    def _relative_path(raw: str) -> str | None:
        raw = raw.strip()
        if raw == "/dev/null":
            return None
        if raw.startswith(("a/", "b/")):
            raw = raw[2:]
        return str(Path(raw))

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

    @classmethod
    def _touched_paths(cls, diff: str) -> list[str]:
        cls._validate_headers(diff)
        paths: list[str] = []
        seen: set[str] = set()
        for line in diff.splitlines():
            if not line.startswith(("--- ", "+++ ")):
                continue
            raw = line[4:].split("\t", 1)[0]
            relative = cls._relative_path(raw)
            if relative is not None and relative not in seen:
                paths.append(relative)
                seen.add(relative)
        return paths

    def snapshot(self, diff: str) -> PatchSnapshot:
        files: list[PatchFileSnapshot] = []
        for relative in self._touched_paths(diff):
            path = self.workspace.resolve(relative)
            if path.is_symlink():
                raise ValueError("Patch target may not be a symlink")
            if path.exists():
                if not path.is_file():
                    raise ValueError("Patch target must be a regular file")
                files.append(
                    PatchFileSnapshot(
                        path=relative,
                        content=path.read_bytes(),
                        mode=stat.S_IMODE(path.stat().st_mode),
                    )
                )
            else:
                files.append(PatchFileSnapshot(path=relative, content=None, mode=None))
        return PatchSnapshot(tuple(files))

    def restore(self, snapshot: PatchSnapshot) -> None:
        for item in snapshot.files:
            path = self.workspace.resolve(item.path)
            if item.content is None:
                if path.is_symlink() or path.is_file():
                    path.unlink()
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.is_symlink():
                path.unlink()
            path.write_bytes(item.content)
            if item.mode is not None:
                path.chmod(item.mode)

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
        output = proc.stdout[-20_000:]
        if proc.returncode != 0:
            return PatchResult(False, output)
        if self._contains_symlink():
            return PatchResult(False, output + "\nPatch created a forbidden symlink")
        return PatchResult(True, output)
