from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class HardwareProfile:
    gpu_name: str
    vram_mb: int
    profile: str
    quant: str
    context: int
    parallel: int
    kv_k: str = "q8_0"
    kv_v: str = "q8_0"

    def as_dict(self) -> dict:
        return asdict(self)


def resolve_profile(gpu_name: str, vram_mb: int) -> HardwareProfile:
    name = gpu_name.lower()
    gb = vram_mb / 1024

    if "3060 ti" in name and gb >= 7.5:
        return HardwareProfile(gpu_name, vram_mb, "rtx3060ti", "Q4_K_M", 8192, 1)

    if gb >= 20:
        return HardwareProfile(gpu_name, vram_mb, "nvidia_24gb_class", "Q5_K_M", 32768, 2)

    if gb >= 11:
        return HardwareProfile(gpu_name, vram_mb, "nvidia_12gb_class", "Q5_K_M", 16384, 1)

    return HardwareProfile(gpu_name, vram_mb, "nvidia_low_vram", "Q4_K_M", 4096, 1)
