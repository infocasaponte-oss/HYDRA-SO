# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass

from hydra.runtime.policy import PolicyEngine, ToolPermission
from hydra.runtime.tools import ToolRegistry, Workspace

_WINDOWS_SYSTEM_ENV = ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP")


@dataclass(frozen=True)
class ToolResult:
    tool: str
    ok: bool
    output: str
    exit_code: int | None = None


class ToolRuntime:
    def __init__(
        self,
        workspace: Workspace,
        registry: ToolRegistry | None = None,
        policy: PolicyEngine | None = None,
    ):
        self.workspace = workspace
        self.registry = registry or ToolRegistry()
        self.policy = policy or PolicyEngine()

    async def run(
        self,
        name: str,
        arguments: dict,
        permission: ToolPermission | None = None,
    ) -> ToolResult:
        permission = permission or ToolPermission()
        spec = self.registry.get(name)
        self.policy.authorize(spec, permission)

        if name == "workspace.list":
            path = self.workspace.resolve(arguments.get("path", "."))
            items = sorted(p.name + ("/" if p.is_dir() else "") for p in path.iterdir())
            return ToolResult(name, True, "\n".join(items))

        if name == "workspace.read":
            path = self.workspace.resolve(arguments["path"])
            if not path.is_file():
                raise ValueError("Not a file")
            limit = min(int(arguments.get("max_chars", 20_000)), 100_000)
            return ToolResult(name, True, path.read_text(encoding="utf-8")[:limit])

        if name == "workspace.search":
            query = str(arguments["query"])
            root = self.workspace.resolve(arguments.get("path", "."))
            hits = []
            for path in root.rglob("*"):
                if not path.is_file() or path.stat().st_size > 1_000_000:
                    continue
                try:
                    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                        if query in line:
                            hits.append(f"{path.relative_to(self.workspace.root)}:{line_no}:{line}")
                            if len(hits) >= 100:
                                return ToolResult(name, True, "\n".join(hits))
                except (UnicodeDecodeError, OSError):
                    continue
            return ToolResult(name, True, "\n".join(hits))

        if name == "python.test":
            # Constrained subprocess: fixed executable/arguments, no shell, no network feature.
            target = self.workspace.resolve(arguments.get("path", "."))
            env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(self.workspace.root)}
            # Windows cannot start Python (Winsock/CRT init) without these system variables.
            env.update({k: os.environ[k] for k in _WINDOWS_SYSTEM_ENV if k in os.environ})
            proc = await asyncio.create_subprocess_exec(
                "python", "-m", "pytest", "-q", str(target),
                cwd=str(self.workspace.root),
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            try:
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=spec.timeout_seconds)
            except TimeoutError:
                proc.kill()
                await proc.wait()
                return ToolResult(name, False, "pytest timed out", exit_code=124)
            text = stdout.decode("utf-8", errors="replace")[-50_000:]
            return ToolResult(name, proc.returncode == 0, text, exit_code=proc.returncode)

        raise KeyError(name)
