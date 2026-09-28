import pytest

from hydra.benchmarking import BenchmarkResult
from hydra.model_factory import BuildState, ModelLineage, ModelVariant
from hydra.promotion import PromotionDenied
from hydra.promotion_gate import apply_promotion_gate


def model() -> ModelVariant:
    return ModelVariant(
        lineage=ModelLineage(base_model="base", base_model_sha256="a" * 64),
        quantization="Q4_K_M",
        artifact_path="model.gguf",
        artifact_sha256="b" * 64,
        state=BuildState.BENCHMARKED,
    )


def benchmark(quality: float) -> BenchmarkResult:
    return BenchmarkResult(
        variant_id="v",
        profile="balanced",
        prompt_tokens=32,
        generated_tokens=64,
        ttft_ms=300,
        tokens_per_second=30,
        peak_vram_mb=7000,
        quality_score=quality,
        passed=True,
    )


def test_low_quality_cannot_be_promoted():
    with pytest.raises(PromotionDenied):
        apply_promotion_gate(model(), benchmark(0.5))


def test_quality_passing_variant_is_promoted():
    assert apply_promotion_gate(model(), benchmark(0.9)).state == BuildState.PROMOTED
