from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

_BLOCKED_NAMES = {".venv", "__pycache__", ".pytest_cache", "runtime"}


@dataclass(frozen=True)
class TaskWorkspace:
    task_id: UUID
    root: Path
    source: Path


@dataclass(frozen=True)
class WorkspaceStats:
    files: int
    bytes: int


class WorkspaceManager:
    """
    Creates expendable per-task copies. The original checkout is never mounted
    into the execution sandbox.
    """

    def __init__(
        self,
        root: str | Path = "runtime/workspaces",
        *,
        max_files: int = 20_000,
        max_bytes: int = 256 * 1024 * 1024,
    ):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_files = max_files
        self.max_bytes = max_bytes

    def _scan_source(self, source: Path) -> WorkspaceStats:
        files = 0
        total_bytes = 0

        if source.is_symlink():
            raise ValueError("Workspace source may not be a symlink")

        for directory, dirnames, filenames in os.walk(source, followlinks=False):
            directory_path = Path(directory)

            allowed_dirs: list[str] = []
            for name in dirnames:
                path = directory_path / name
                if path.is_symlink():
                    raise ValueError(f"Workspace source contains symlink: {path}")
                if name not in _BLOCKED_NAMES:
                    allowed_dirs.append(name)
            dirnames[:] = allowed_dirs

            for name in filenames:
                if name in _BLOCKED_NAMES:
                    continue
                path = directory_path / name
                if path.is_symlink():
                    raise ValueError(f"Workspace source contains symlink: {path}")
                if not path.is_file():
                    raise ValueError(f"Workspace source contains non-regular file: {path}")
                files += 1
                total_bytes += path.stat().st_size
                if files > self.max_files:
                    raise ValueError("Workspace source exceeds maximum file count")
                if total_bytes > self.max_bytes:
                    raise ValueError("Workspace source exceeds maximum byte size")

        return WorkspaceStats(files=files, bytes=total_bytes)

    def _validate_no_symlinks(self, root: Path) -> None:
        for directory, dirnames, filenames in os.walk(root, followlinks=False):
            directory_path = Path(directory)
            for name in [*dirnames, *filenames]:
                path = directory_path / name
                if path.is_symlink():
                    raise ValueError(f"Copied workspace contains symlink: {path}")

    def create(self, task_id: UUID, source: str | Path) -> TaskWorkspace:
        raw_source = Path(source)
        if raw_source.is_symlink():
            raise ValueError("Workspace source may not be a symlink")
        source_path = raw_source.resolve()
        if not source_path.is_dir():
            raise ValueError("Workspace source must be a directory")

        self._scan_source(source_path)

        task_root = (self.root / str(task_id)).resolve()
        if self.root not in task_root.parents:
            raise ValueError("Invalid task workspace")

        if task_root.exists():
            shutil.rmtree(task_root)

        def ignore(_directory: str, names: list[str]) -> set[str]:
            return {name for name in names if name in _BLOCKED_NAMES}

        try:
            shutil.copytree(
                source_path,
                task_root,
                ignore=ignore,
                symlinks=True,
            )
            self._validate_no_symlinks(task_root)
        except Exception:
            if task_root.exists():
                shutil.rmtree(task_root)
            raise

        return TaskWorkspace(task_id=task_id, root=task_root, source=source_path)

    def destroy(self, workspace: TaskWorkspace) -> None:
        root = workspace.root.resolve()
        if root.exists() and self.root in root.parents:
            shutil.rmtree(root)
