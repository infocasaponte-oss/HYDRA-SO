# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
import pytest

from hydra.training.base_pretrain import ModelShape, SHAPES
from hydra.training.prepare_4b import parameter_count, prepare


def test_budget_has_no_automatic_launch_or_fabricated_runtime_metrics():
    result = prepare()
    assert 3.9e9 < result["parameters"] < 4.1e9
    assert result["meta_parameter_count"] is None
    assert not result["launch_enabled"] and not result["approved"]
    assert result["arithmetic_memory_bounds_gib"]["current_trainer_fp32_weights_gradients_adam_states"] > 59
    assert "4b" not in SHAPES  # unvalidated backend is not silently enabled


@pytest.mark.parametrize("vocab", [0, True, 65536, 32000.0])
def test_reject_vocab_incompatible_with_token_pipeline(vocab):
    with pytest.raises(ValueError):
        parameter_count(ModelShape(), vocab)


def test_invalid_grouped_attention_is_rejected():
    with pytest.raises(ValueError):
        parameter_count(ModelShape(num_attention_heads=7), 32000)


def test_parameter_formula_matches_actual_tiny_transformers_model():
    torch = pytest.importorskip("torch")
    pytest.importorskip("transformers")
    from dataclasses import asdict
    from transformers import LlamaConfig, LlamaForCausalLM
    shape = ModelShape(hidden_size=32, num_hidden_layers=2, num_attention_heads=4,
                       num_key_value_heads=2, intermediate_size=96)
    with torch.device("meta"):
        model = LlamaForCausalLM(LlamaConfig(vocab_size=300, tie_word_embeddings=True,
                                           attention_bias=False, mlp_bias=False, **asdict(shape)))
    assert sum(p.numel() for p in model.parameters()) == parameter_count(shape, 300)
