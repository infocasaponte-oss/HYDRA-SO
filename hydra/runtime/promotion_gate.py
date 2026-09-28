from __future__ import annotations

from dataclasses import dataclass

from hydra.runtime.benchmarking import BenchmarkResult
from hydra.runtime.model_factory import ModelVariant
from hydra.runtime.promotion import promote


@dataclass(frozen=True)
class PromotionPolicy:
    min_quality: float = 0.80
    max_ttft_ms: float = 5000.0
    min_tokens_per_second: float = 5.0
    max_peak_vram_mb: float = 7680.0


def apply_promotion_gate(
    variant: ModelVariant,
    benchmark: BenchmarkResult,
    policy: PromotionPolicy | None = None,
) -> ModelVariant:
    policy = policy or PromotionPolicy()
    passed = (
        benchmark.passed
        and benchmark.quality_score >= policy.min_quality
        and benchmark.ttft_ms <= policy.max_ttft_ms
        and benchmark.tokens_per_second >= policy.min_tokens_per_second
        and benchmark.peak_vram_mb <= policy.max_peak_vram_mb
    )
    return promote(variant, benchmark_passed=passed)
