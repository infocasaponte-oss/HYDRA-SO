# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
import json

import numpy as np
import pytest

from hydra.training import base_corpus as bc
from hydra.training import base_pretrain as bp


def test_wsd_schedule_warms_up_holds_and_decays():
    plan = bp.TrainPlan(learning_rate=1.0, warmup_fraction=0.1, decay_fraction=0.2, min_lr_ratio=0.1)
    lrs = [bp.wsd_lr(step, 100, plan) for step in range(100)]
    assert lrs[0] < lrs[9] == 1.0 and lrs[50] == 1.0 and lrs[79] == 1.0
    assert lrs[99] == pytest.approx(0.1, abs=0.01) and all(a >= b for a, b in zip(lrs[80:], lrs[81:]))


def test_no_weight_decay_on_embeddings_and_norms():
    from transformers import LlamaConfig, LlamaForCausalLM

    model = LlamaForCausalLM(LlamaConfig(vocab_size=64, hidden_size=16, intermediate_size=32, num_hidden_layers=1,
                                         num_attention_heads=2, num_key_value_heads=1, tie_word_embeddings=True))
    decay, no_decay = bp.param_groups(model, 0.1)
    assert all(p.ndim >= 2 for p in decay["params"]) and no_decay["weight_decay"] == 0.0
    names = {id(p): n for n, p in model.named_parameters()}
    assert any("embed" in names[id(p)] for p in no_decay["params"])


def test_tokenize_and_train_a_tiny_model_end_to_end(tmp_path):
    spm = pytest.importorskip("sentencepiece")
    sentences = [f"El artículo {i} regula la materia número {i * 7} de la ley de prueba." for i in range(400)]
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    import gzip
    for split, rows in (("train", sentences[:380]), ("validation", sentences[380:])):
        with gzip.open(corpus / f"{split}-00000.jsonl.gz", "wt", encoding="utf-8") as stream:
            for text in rows:
                stream.write(json.dumps({"text": text * 3}) + "\n")
    (corpus / "manifest.json").write_text("{}", encoding="utf-8")
    tok = tmp_path / "tok"
    tok.mkdir()
    (tmp_path / "sample.txt").write_text("\n".join(sentences), encoding="utf-8")
    spm.SentencePieceTrainer.train(input=str(tmp_path / "sample.txt"), model_prefix=str(tok / "tokenizer"),
                                   model_type="bpe", vocab_size=400, byte_fallback=True, unk_id=0, bos_id=1,
                                   eos_id=2, pad_id=3)
    for name in ("tokenizer_config.json", "special_tokens_map.json"):
        (tok / name).write_text("{}", encoding="utf-8")
    data = tmp_path / "data"
    counts = bp.tokenize(corpus, tok, data)
    assert counts["train"]["tokens"] > 0 and counts["validation"]["tokens"] > 0
    assert np.fromfile(data / "train.bin", dtype=np.uint16).max() < 400
    (data / "tokens-manifest.json").write_text(json.dumps(counts), encoding="utf-8")
    shape = bp.ModelShape(hidden_size=32, num_hidden_layers=2, num_attention_heads=2, num_key_value_heads=1,
                          intermediate_size=64, max_position_embeddings=64)
    plan = bp.TrainPlan(seq_len=32, micro_batch=4, accumulation=1, eval_every=3, eval_batches=2)
    report = bp.train(data, tok, tmp_path / "model", shape, plan, max_steps=6, device="cpu")
    assert report["steps"] == 6 and len(report["history"]) == 2
    assert report["history"][-1]["val_loss"] < report["history"][0]["val_loss"] + 1.0
    assert (tmp_path / "model" / "final" / "model.safetensors").exists()
    assert (tmp_path / "model" / "final" / "tokenizer.model").exists()
    with pytest.raises(FileExistsError):
        bp.train(data, tok, tmp_path / "model", shape, plan, max_steps=1, device="cpu")
    assert list(bc.iter_texts(corpus, "validation"))
