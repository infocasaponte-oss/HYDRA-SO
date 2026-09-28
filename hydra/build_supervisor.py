from __future__ import annotations

import asyncio
from dataclasses import dataclass
from hydra.llama_factory import BuildCommand
from hydra.model_factory import file_sha256


@dataclass(frozen=True)
class BuildResult:
    ok: bool
    exit_code: int
    output: str
    artifact_path: str | None = None
    artifact_sha256: str | None = None


class BuildSupervisor:
    async def execute(self, command: BuildCommand, timeout_seconds: int = 3600) -> BuildResult:
        command.output.parent.mkdir(parents=True, exist_ok=True)
        proc = await asyncio.create_subprocess_exec(
            *command.argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            return BuildResult(False, 124, "build timed out")

        output = stdout.decode("utf-8", errors="replace")[-100_000:]
        if proc.returncode != 0:
            return BuildResult(False, proc.returncode, output)
        if not command.output.is_file() or command.output.stat().st_size == 0:
            return BuildResult(False, proc.returncode, output + "\nmissing build artifact")
        return BuildResult(
            True,
            proc.returncode,
            output,
            str(command.output),
            file_sha256(command.output),
        )
