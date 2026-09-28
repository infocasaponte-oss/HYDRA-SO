from __future__ import annotations

import asyncio
from dataclasses import dataclass


@dataclass
class ManagedProcess:
    process: asyncio.subprocess.Process

    async def stop(self, grace_seconds: float = 5.0) -> None:
        if self.process.returncode is not None:
            return
        self.process.terminate()
        try:
            await asyncio.wait_for(self.process.wait(), timeout=grace_seconds)
        except TimeoutError:
            self.process.kill()
            await self.process.wait()


class ProcessSupervisor:
    async def start(self, argv: list[str]) -> ManagedProcess:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        return ManagedProcess(proc)
