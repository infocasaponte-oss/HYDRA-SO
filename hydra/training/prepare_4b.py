# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""Prepare a ~4B architecture and arithmetic budgets without allocating weights."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

from hydra.core.atomic import write_text_atomic
from hydra.training.base_pretrain import ModelShape

SHAPE = ModelShape(hidden_size=2560, num_hidden_layers=41, num_attention_heads=20,
                   num_key_value_heads=5, intermediate_size=10240, max_position_embeddings=4096)


def parameter_count(shape: ModelShape, vocab_size: int) -> int:
    if type(vocab_size) is not int or not 4 <= vocab_size <= 65535:
        raise ValueError("vocabulary must fit the current uint16 pipeline")
    h, layers, heads, kv, intermediate = (shape.hidden_size, shape.num_hidden_layers,
                                         shape.num_attention_heads, shape.num_key_value_heads, shape.intermediate_size)
    if min(h, layers, heads, kv, intermediate, shape.max_position_embeddings) <= 0 or h % heads or heads % kv:
        raise ValueError("invalid GQA architecture")
    # Bias-free Q/O, K/V, SwiGLU gate/up/down, two RMSNorms per layer;
    # one final RMSNorm, tied input/output embeddings.
    kv_width = h // heads * kv
    per_layer = 2 * h * h + 2 * h * kv_width + 3 * h * intermediate + 2 * h
    return vocab_size * h + layers * per_layer + h


def prepare(vocab_size=32000, verify_meta=False) -> dict:
    count = parameter_count(SHAPE, vocab_size)
    config = {"model_type": "llama", "architectures": ["LlamaForCausalLM"],
              "vocab_size": vocab_size, "tie_word_embeddings": True, "rms_norm_eps": 1e-5,
              "rope_theta": 10000.0, "attention_bias": False, "mlp_bias": False,
              "use_cache": False, **asdict(SHAPE)}
    verified = None
    versions = None
    if verify_meta:
        import torch
        import transformers
        from transformers import LlamaConfig, LlamaForCausalLM
        with torch.device("meta"):
            model = LlamaForCausalLM(LlamaConfig(**config))
        verified = sum(p.numel() for p in model.parameters())
        if verified != count or any(p.device.type != "meta" for p in model.parameters()):
            raise ValueError("architecture count or meta allocation differs from preparation")
        versions = {"torch": torch.__version__, "transformers": transformers.__version__}
    gib = 1024 ** 3
    return {"format": "hydra-4b-preparation/1", "status": "PREPARATION_ONLY", "parameters": count,
            "vocab_size_basis": "proposed; must match the real tokenizer", "config": config,
            "meta_parameter_count": verified, "verification_versions": versions,
            "arithmetic_memory_bounds_gib": {"bf16_weights_only": count * 2 / gib,
                "fp32_weights_only": count * 4 / gib,
                "current_trainer_fp32_weights_gradients_adam_states": count * 16 / gib},
            "memory_basis": "Arithmetic only; excludes activations, logits, buffers, allocator and checkpoints. Not measured peak memory.",
            "candidate_smoke_plan": {"sequence_length": 512, "micro_batch": 1, "accumulation": 1,
                                     "steps": 2, "gradient_checkpointing": True, "validated": False},
            "hyperparameters": "learning rate, schedule and batch plan remain unset until trainer and corpus validation",
            "tokenizer_special_ids": "unset; read from the actual tokenizer before constructing a training model",
            "training_backend": "not selected or validated for 4B", "launch_enabled": False,
            "authority_enabled": False, "approved": False,
            "required_evidence": ["corpus audit and source review", "real tokenizer hash, vocabulary and special IDs",
                "chosen from-scratch or checkpoint-adaptation path", "trainer memory and throughput smoke run",
                "checkpoint resume test", "independent evaluation and shadow integration"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vocab-size", type=int, default=32000)
    parser.add_argument("--verify-meta", action="store_true")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.out.exists():
        parser.exit(2, "error: choose a new preparation file\n")
    try:
        result = prepare(args.vocab_size, args.verify_meta)
        write_text_atomic(args.out, json.dumps(result, indent=2, allow_nan=False))
    except (ValueError, OSError, ImportError) as error:
        parser.exit(2, f"error: preparation failed ({type(error).__name__})\n")
    print(json.dumps({k: result[k] for k in ("parameters", "meta_parameter_count", "launch_enabled")}, indent=2))


if __name__ == "__main__":
    main()
