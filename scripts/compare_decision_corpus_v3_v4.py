# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""Measure how much of the v3 decision test score was template memorisation.

Evaluates the published routing classifier (models/hydra-decision-v4, trained on v3 templates)
and a candidate trained in memory with the same recipe on v4 train + human-dev, on both the v3
test (shared templates) and the v4 test (unseen templates). Writes evidence only: no model file
is written, replaced or promoted."""
import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

from hydra.training.evidence_io import write_json
from hydra.training.specialists import TextClassifier
from hydra.training.train_decision_v4 import load as load_admitted
from hydra.training.train_decision_v4 import train

HUMAN = [Path("data/human-dev-v1.jsonl"), Path("data/human-dev-v2.jsonl")]


def held_out(path: Path) -> list[tuple[str, str]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [(r["input"]["query"], r["output"]["task_type"]) for r in rows]


def wilson(correct: int, total: int, z: float = 1.96) -> list[float]:
    p = correct / total
    centre = (p + z * z / (2 * total)) / (1 + z * z / total)
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / (1 + z * z / total)
    return [round(centre - half, 4), round(centre + half, 4)]


def score(clf: TextClassifier, rows: list[tuple[str, str]]) -> dict:
    wrong = []
    per_label: dict[str, Counter] = {}
    for text, label in rows:
        predicted, confidence = clf.predict(text)
        per_label.setdefault(label, Counter())["total"] += 1
        if predicted == label:
            per_label[label]["correct"] += 1
        else:
            wrong.append({"text": text, "expected": label, "predicted": predicted, "confidence": round(confidence, 4)})
    correct = len(rows) - len(wrong)
    return {"examples": len(rows), "correct": correct, "accuracy": round(correct / len(rows), 4),
            "wilson_95": wilson(correct, len(rows)),
            "per_label_accuracy": {k: round(v["correct"] / v["total"], 4) for k, v in sorted(per_label.items())},
            "errors": wrong}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--published", type=Path, default=Path("models/hydra-decision-v4/classifier.json"))
    parser.add_argument("--v3", type=Path, default=Path("data/decision-corpus-v3"))
    parser.add_argument("--v4", type=Path, default=Path("data/decision-corpus-v4"))
    parser.add_argument("--scratch", type=Path, required=True, help="where the candidate is written temporarily")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    tests = {"v3_test_shared_templates": held_out(args.v3 / "test.jsonl"),
             "v4_test_unseen_templates": held_out(args.v4 / "test.jsonl")}
    published = TextClassifier.load(args.published)
    candidate_path = args.scratch / "candidate-v4-corpus.json"
    report = train([args.v4 / "train.jsonl", *HUMAN], candidate_path)
    candidate = TextClassifier.load(candidate_path)
    candidate_sha = hashlib.sha256(candidate_path.read_bytes()).hexdigest()
    candidate_path.unlink()
    # The candidate never saw a v3 row, so its v3 test score is a fair cross-corpus check too.
    assert not {t for t, _ in tests["v4_test_unseen_templates"]} & set(load_admitted(args.v4 / "train.jsonl")[0])
    write_json(args.out, {
        "format": "hydra-decision-corpus-comparison/1",
        "published_model": {"path": str(args.published),
                            "sha256": hashlib.sha256(args.published.read_bytes()).hexdigest(),
                            "trained_on": "decision-corpus-v3/train + human-dev-v1 + human-dev-v2",
                            **{name: score(published, rows) for name, rows in tests.items()}},
        "candidate_v4_corpus": {"sha256_discarded_file": candidate_sha, "training_report": report,
                                **{name: score(candidate, rows) for name, rows in tests.items()}},
        "promotion": "none; evidence only, no model written to models/",
        "limitation": ("Synthetic Spanish prompts written by the same author; unseen templates measure "
                       "generalisation better than v3 but are not real user traffic."),
    })
    print(args.out)


if __name__ == "__main__":
    main()
