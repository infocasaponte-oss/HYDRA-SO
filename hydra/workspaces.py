from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID


@dataclass(frozen=True)
class TaskWorkspace:
    task_id: UUID
    root: Path
    source: Path


class WorkspaceManager:
    """
    Creates expendable per-task copies. The original checkout is never mounted
    into the execution sandbox.
    """

    def __init__(self, root: str | Path = "runtime/workspaces"):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def create(self, task_id: UUID, source: str | Path) -> TaskWorkspace:
        source_path = Path(source).resolve()
        if not source_path.is_dir():
            raise ValueError("Workspace source must be a directory")

        task_root = (self.root / str(task_id)).resolve()
        if self.root not in task_root.parents:
            raise ValueError("Invalid task workspace")

        if task_root.exists():
            shutil.rmtree(task_root)

        def ignore(_directory: str, names: list[str]) -> set[str]:
            blocked = {".venv", "__pycache__", ".pytest_cache", "runtime"}
            return {name for name in names if name in blocked}

        shutil.copytree(source_path, task_root, ignore=ignore, symlinks=False)
        return TaskWorkspace(task_id=task_id, root=task_root, source=source_path)

    def destroy(self, workspace: TaskWorkspace) -> None:
        root = workspace.root.resolve()
        if root.exists() and self.root in root.parents:
            shutil.rmtree(root)
