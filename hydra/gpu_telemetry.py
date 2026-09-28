from __future__ import annotations

import asyncio
from dataclasses import dataclass


@dataclass(frozen=True)
class GpuSample:
    name: str
    memory_used_mb: int
    memory_total_mb: int
    utilization_gpu: int


async def sample_nvidia_smi() -> list[GpuSample]:
    proc = await asyncio.create_subprocess_exec(
        "nvidia-smi",
        "--query-gpu=name,memory.used,memory.total,utilization.gpu",
        "--format=csv,noheader,nounits",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    if proc.returncode != 0:
        return []
    samples = []
    for line in stdout.decode().splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 4:
            continue
        samples.append(
            GpuSample(
                name=parts[0],
                memory_used_mb=int(parts[1]),
                memory_total_mb=int(parts[2]),
                utilization_gpu=int(parts[3]),
            )
        )
    return samples


class PeakVramMonitor:
    def __init__(self, interval_seconds: float = 0.1):
        self.interval_seconds = interval_seconds
        self.peak_mb = 0
        self.samples = 0
        self._running = False

    async def run(self) -> None:
        self._running = True
        while self._running:
            readings = await sample_nvidia_smi()
            for reading in readings:
                self.peak_mb = max(self.peak_mb, reading.memory_used_mb)
                self.samples += 1
            await asyncio.sleep(self.interval_seconds)

    def stop(self) -> None:
        self._running = False
