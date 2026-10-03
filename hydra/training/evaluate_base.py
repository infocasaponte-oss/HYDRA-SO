# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""Evaluate a HYDRA Base checkpoint: perplexity per source on the held-out split, and text samples.

Reads only the corpus ``validation`` shards (never used for training). Documents are framed as in
pretraining (BOS + document + EOS) and scored in windows of the trained context length. Samples use
fixed prompts and a fixed seed so two checkpoints can be compared side by side.
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
import random
from collections import defaultdict
from pathlib import Path

PROMPTS = (
    "Artículo 1. Objeto.\nLa presente ley tiene por objeto",
    "Era una tarde de invierno en el puerto de Vigo y",
    "def suma_lista(numeros):\n    \"\"\"Devuelve la suma de los números de la lista.\"\"\"\n",
    "La fotosíntesis es el proceso por el cual",
    "Madrid, 14 de marzo de 1898. Ayer se celebró en el Ateneo",
)


def validation_by_source(corpus: Path, per_source: int, seed: int = 7) -> dict[str, list[str]]:
    """Uniform per-source sample of the validation split, streamed with a bounded reservoir."""
    rng = random.Random(seed)
    reservoirs, seen = defaultdict(list), defaultdict(int)
    for shard in sorted(corpus.glob("validation-*.jsonl.gz")):
        with gzip.open(shard, "rt", encoding="utf-8") as stream:
            for line in stream:
                record = json.loads(line)
                source = record["source"]
                seen[source] += 1
                if len(reservoirs[source]) < per_source:
                    reservoirs[source].append(record["text"])
                else:
                    j = rng.randrange(seen[source])
                    if j < per_source:
                        reservoirs[source][j] = record["text"]
    if not reservoirs:
        raise ValueError(f"{corpus}: no validation records; refusing to report an empty evaluation")
    return dict(sorted(reservoirs.items()))


def lineage(checkpoint: Path, tokenizer_dir: Path) -> dict:
    """The checkpoint's build manifest, after checking that the tokenizer is the one it was trained with."""
    from hydra.training.base_corpus import file_sha256
    path = next((p for p in (checkpoint / "build-manifest.json", checkpoint.parent / "build-manifest.json")
                 if p.is_file()), None)
    if path is None:
        raise ValueError(f"{checkpoint}: no HYDRA Base build-manifest.json to bind the tokenizer to")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("tokenizer_sha256") != file_sha256(tokenizer_dir / "tokenizer.model"):
        raise ValueError("tokenizer does not match the one this checkpoint was trained with")
    return manifest


def perplexity(model, tokenizer, texts: list[str], context: int, device) -> dict:
    import torch

    total_loss, total_tokens = 0.0, 0
    with torch.inference_mode():
        for text in texts:
            ids = [tokenizer.bos_token_id] + tokenizer.encode(text, add_special_tokens=False) + [tokenizer.eos_token_id]
            for start in range(0, len(ids) - 1, context):
                window = torch.tensor([ids[start:start + context + 1]], device=device)
                if window.shape[1] < 2:
                    continue
                logits = model(input_ids=window[:, :-1], use_cache=False).logits.float()
                loss = torch.nn.functional.cross_entropy(logits[0], window[0, 1:], reduction="sum")
                total_loss += float(loss)
                total_tokens += window.shape[1] - 1
    mean = total_loss / max(1, total_tokens)
    try:
        value = round(math.exp(mean), 2)
    except OverflowError:
        value = None  # not representable; reported explicitly rather than capped
    return {"documents": len(texts), "tokens": total_tokens, "loss": round(mean, 4), "perplexity": value,
            "perplexity_overflow": value is None}


def samples(model, tokenizer, device, max_new_tokens: int = 80, seed: int = 1234) -> list[dict]:
    import torch

    out = []
    for prompt in PROMPTS:
        torch.manual_seed(seed)
        ids = tokenizer(prompt, return_tensors="pt").input_ids.to(device)
        generated = model.generate(ids, max_new_tokens=max_new_tokens, do_sample=True, top_p=0.9, temperature=0.8,
                                   repetition_penalty=1.1, pad_token_id=tokenizer.pad_token_id)
        out.append({"prompt": prompt, "continuation": tokenizer.decode(generated[0, ids.shape[1]:],
                                                                       skip_special_tokens=True)})
    return out


def evaluate(checkpoint: Path, tokenizer_dir: Path, corpus: Path, per_source: int = 40, device: str = "cpu") -> dict:
    import torch
    from transformers import AutoTokenizer, LlamaForCausalLM

    manifest = lineage(checkpoint, tokenizer_dir)
    tokenizer = AutoTokenizer.from_pretrained(tokenizer_dir, local_files_only=True)
    model = LlamaForCausalLM.from_pretrained(checkpoint, local_files_only=True, use_safetensors=True)
    model = model.to(torch.device(device)).eval()
    # the sequence length it was trained with, not just the architectural position limit
    context = int(manifest.get("plan", {}).get("seq_len") or model.config.max_position_embeddings)
    per_source_scores = {source: perplexity(model, tokenizer, texts, context, model.device)
                         for source, texts in validation_by_source(corpus, per_source).items()}
    return {"format": "hydra-base-evaluation/1", "checkpoint": str(checkpoint), "corpus": str(corpus),
            "split": "validation", "context": context, "weights_sha256": manifest.get("weights_sha256"), "per_source": per_source_scores, "samples": samples(model, tokenizer, model.device)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--tokenizer", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--per-source", type=int, default=40)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)  # before the expensive part, not after
    report = evaluate(args.checkpoint, args.tokenizer, args.corpus, args.per_source, args.device)
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
