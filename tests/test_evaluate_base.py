# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
import gzip
import json

import pytest


def test_evaluate_reports_per_source_perplexity_and_samples(tmp_path):
    torch = pytest.importorskip("torch")
    transformers = pytest.importorskip("transformers")
    spm = pytest.importorskip("sentencepiece")
    from hydra.training import evaluate_base as ev
    text = [f"frase {i} sobre el puerto, la costa y la ciudad" for i in range(300)]
    (tmp_path / "c.txt").write_text("\n".join(text), encoding="utf-8")
    tok = tmp_path / "tok"
    tok.mkdir()
    spm.SentencePieceTrainer.train(input=str(tmp_path / "c.txt"), model_prefix=str(tok / "tokenizer"),
                                   vocab_size=50, unk_id=0, bos_id=1, eos_id=2, pad_id=3)
    transformers.LlamaTokenizer(vocab_file=str(tok / "tokenizer.model"), legacy=False,
                                pad_token="<pad>").save_pretrained(str(tok))
    torch.manual_seed(0)
    model_dir = tmp_path / "base"
    transformers.LlamaForCausalLM(transformers.LlamaConfig(
        vocab_size=50, hidden_size=16, intermediate_size=32, num_hidden_layers=1, num_attention_heads=2,
        num_key_value_heads=1, max_position_embeddings=32, bos_token_id=1, eos_token_id=2,
        pad_token_id=3)).save_pretrained(model_dir)
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    with gzip.open(corpus / "validation-00000.jsonl.gz", "wt", encoding="utf-8") as stream:
        for i, line in enumerate(text[:6]):
            stream.write(json.dumps({"text": line * 5, "source": "A" if i % 2 else "B"}) + "\n")
    with gzip.open(corpus / "train-00000.jsonl.gz", "wt", encoding="utf-8") as stream:
        stream.write(json.dumps({"text": "nunca se lee", "source": "C"}) + "\n")
    from hydra.training.base_corpus import file_sha256
    with pytest.raises(ValueError, match="build-manifest"):
        ev.evaluate(model_dir, tok, corpus, per_source=2)
    manifest = {"kind": "hydra-base", "tokenizer_sha256": "0" * 64, "plan": {"seq_len": 16}}
    (model_dir / "build-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="tokenizer"):
        ev.evaluate(model_dir, tok, corpus, per_source=2)
    manifest["tokenizer_sha256"] = file_sha256(tok / "tokenizer.model")
    (model_dir / "build-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="no validation"):
        ev.evaluate(model_dir, tok, tmp_path / "missing", per_source=2)
    report = ev.evaluate(model_dir, tok, corpus, per_source=2)
    assert report["context"] == 16
    assert set(report["per_source"]) == {"A", "B"}  # validation only
    assert all(s["tokens"] > 0 and s["perplexity"] > 1 for s in report["per_source"].values())
    assert len(report["samples"]) == len(ev.PROMPTS)
