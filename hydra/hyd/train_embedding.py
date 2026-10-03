# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""Train a Hyd embedding head: frozen encoder embeddings -> linear head chosen and calibrated on dev.

Never reads a test set. Reports dev metrics and the controlled probes of ``hydra.hyd.probes``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from hydra.core.atomic import write_text_atomic
from hydra.hyd import probes
from hydra.hyd.controller import implementation_digest
from hydra.hyd.embedding import EmbeddingRanker, encoder_from, fit_head
from hydra.router.decision_contract import CRITERIA
from hydra.training.calibrator import fit_temperature
from hydra.training.decision_metrics import metrics, wilson_lower

L2_GRID = (1e-3, 1e-2, 1e-1, 1.0)


def selective_metrics(rows: list[dict], min_confidence: float, min_margin: float) -> dict:
    """Calibration diagnostics where "accepted" uses the engine's own rule: confidence and margin."""
    report = metrics(rows, 0)
    accepted = []
    for row in rows:
        ranked = sorted(row["probabilities"].values(), reverse=True)
        if ranked[0] >= min_confidence and (len(ranked) < 2 or ranked[0] - ranked[1] >= min_margin):
            accepted.append(row)
    correct = sum(row["selected"] == row["expected"] for row in accepted)
    report.update({"accepted": len(accepted), "coverage": len(accepted) / len(rows) if rows else 0,
                   "accuracy": correct / len(accepted) if accepted else None,
                   "accuracy_wilson_lower_95": wilson_lower(correct, len(accepted)),
                   "acceptance_rule": {"min_confidence": min_confidence, "min_margin": min_margin}})
    return report


def accuracy(model: EmbeddingRanker, rows: list[dict], embeddings: np.ndarray | None = None) -> float:
    distributions = (model.probabilities_batch([r["text"] for r in rows]) if embeddings is None
                     else model.probabilities_from_embeddings(embeddings))
    return sum(max(d, key=d.get) == r["expected"] for d, r in zip(distributions, rows)) / len(rows)


def train(corpus: Path, encoder_spec: dict, out: Path, min_confidence: float = .95, min_margin: float = .1) -> dict:
    raw = (corpus / "corpus.jsonl").read_bytes()
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    labels = list(CRITERIA)
    train_rows = [r for r in rows if r["split"] == "train"]
    dev_rows = [r for r in rows if r["split"] == "dev"]
    if {r["expected"] for r in train_rows} != set(labels) or {r["expected"] for r in dev_rows} != set(labels):
        raise ValueError("corpus must have train and dev rows covering every routing label")
    if {r["template"] for r in train_rows} & {r["template"] for r in dev_rows}:
        raise ValueError("train and dev share templates; dev would not measure unseen phrasings")
    encoder = encoder_from(encoder_spec)
    x_train = encoder.embed([r["text"] for r in train_rows])
    x_dev = encoder.embed([r["text"] for r in dev_rows])
    mean, scale = x_train.mean(axis=0), x_train.std(axis=0) + 1e-6
    y_train = np.array([labels.index(r["expected"]) for r in train_rows])
    best = None
    for l2 in L2_GRID:  # chosen on dev only
        w, b = fit_head((x_train - mean) / scale, y_train, len(labels), l2)
        model = EmbeddingRanker(encoder, labels, mean, scale, w, b)
        dev_accuracy = accuracy(model, dev_rows, x_dev)  # dev is embedded once
        if best is None or dev_accuracy > best[0]:
            best = (dev_accuracy, l2, model)
    _, l2, model = best
    dev_distributions = model.probabilities_from_embeddings(x_dev)
    model.temperature = fit_temperature([{"expected": r["expected"], "probabilities": d}
                                         for r, d in zip(dev_rows, dev_distributions)])
    model.training = {"criteria": CRITERIA, "corpus_sha256": hashlib.sha256(raw).hexdigest(),
                      "examples": len(train_rows), "l2": l2, "rights": "proprietary-hydra-authored head",
                      "encoder_license": encoder_spec.get("license"), "domain": "routing_only",
                      "general_decision_quality": "unvalidated"}
    out.mkdir(parents=True, exist_ok=True)
    model.save(out / "model.json", encoder_spec)
    measured = []
    for row, distribution in zip(dev_rows, model.probabilities_from_embeddings(x_dev)):
        measured.append({"expected": row["expected"], "selected": max(distribution, key=distribution.get),
                         "probabilities": distribution})
    probe_scores = {name: round(accuracy(model, items), 3)
                    for name, items in probes.build(dev_rows, labels).items()}
    report = {"format": "hyd-calibration/1", "model_sha256": model.revision,
              "implementation_sha256": implementation_digest(), "temperature": model.temperature,
              "dataset_sha256": hashlib.sha256(raw).hexdigest(), "criteria": CRITERIA,
              "min_confidence": min_confidence, "min_margin": min_margin, "status": "SHADOW_ONLY",
              "independent_test": False, "encoder": encoder_spec, "l2": l2,
              "metrics": selective_metrics(measured, min_confidence, min_margin), "probes_dev": probe_scores,
              "limitation": "Synthetic training and dev data; authority requires an independent human test."}
    if not math.isfinite(report["temperature"]):
        raise ValueError("non-finite calibration temperature")
    write_text_atomic(out / "calibration.json", json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, default=Path("data/hyd-route-corpus-v5"))
    parser.add_argument("--out", type=Path, default=Path("config/hyd-embedding-v5"))
    parser.add_argument("--endpoint", default="http://127.0.0.1:18094")
    parser.add_argument("--encoder-model", default="hydra-instruction-v8")
    parser.add_argument("--encoder-gguf-sha256", default="0ef14148ababf98c52623f164d776ed76f17a583175ea91301e024a157231761")
    parser.add_argument("--dims", type=int, default=1536)
    parser.add_argument("--hydra-base", type=Path, help="HYDRA Base checkpoint directory (own-weights encoder)")
    parser.add_argument("--hydra-base-tokenizer", type=Path)
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()
    if args.hydra_base:
        from hydra.training.base_corpus import file_sha256
        config = json.loads((args.hydra_base / "config.json").read_text(encoding="utf-8"))
        spec = {"kind": "hydra-base-mean", "model_dir": str(args.hydra_base.resolve()),
                "tokenizer_dir": str(args.hydra_base_tokenizer.resolve()), "dims": config["hidden_size"],
                "weights_sha256": file_sha256(args.hydra_base / "model.safetensors"),
                "tokenizer_sha256": file_sha256(args.hydra_base_tokenizer / "tokenizer.model"),
                "device": args.device, "pooling": "mean", "base": "HYDRA Base (own weights)",
                "license": "HYDRA Base proprietary"}
    else:
        spec = {"kind": "llamacpp-embeddings", "endpoint": args.endpoint, "model": args.encoder_model,
                "dims": args.dims, "pooling": "mean", "gguf_sha256": args.encoder_gguf_sha256,
                "base": "Qwen2.5-1.5B (Apache-2.0) fine-tuned as HYDRA v8", "license": "Apache-2.0"}
    print(json.dumps(train(args.corpus, spec, args.out), ensure_ascii=False, indent=2))
