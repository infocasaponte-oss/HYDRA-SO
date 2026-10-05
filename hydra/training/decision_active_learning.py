# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""Learning to learn for the routing decider: measure which way of choosing examples teaches
the model fastest, then ask humans to label exactly those examples.

Three steps, each a separate command; none edits live weights, a published corpus or a model:

``simulate``  Compares acquisition strategies on a labelled pool whose labels stay hidden until a
              row is "acquired" (a stand-in for a human answer). Strategies are ranked on the
              calibration split only; the frozen test is scored once per strategy, at the end, as
              a report, and never drives a choice.
``queue``     Real round. Scores an unlabelled pool with the current model and writes the rows the
              winning strategy would ask about to a new, immutable review queue. The model's
              suggestion is shown to the reviewer but never becomes a label.
``admit``     Turns a human-completed queue into an admitted training file. Rows without an
              explicit human label and reviewer stay out.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from pathlib import Path

from hydra.corpus.artifact_privacy import _finding_types
from hydra.corpus.dedup import hamming, normalize_text, simhash
from hydra.training.evidence_io import write_json
from hydra.training.specialists import TextClassifier

STRATEGIES = ("random", "margin", "entropy", "safety_margin")
SAFETY_LABELS = ("high_risk_review", "security")
SAFETY_MASS = 0.15  # probability on a safety label that always earns a human look
NEAR_BITS = 3
EPOCHS = 18


def read_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def text_label(row: dict) -> tuple[str, str | None]:
    if "text" in row:
        return row["text"], row.get("expected") or row.get("human_label")
    return row["input"]["query"], (row.get("output") or {}).get("task_type")


def admitted(paths: list[Path]) -> list[tuple[str, str]]:
    """Training rows, deduplicated like train_decision_v4 so repetition never weighs."""
    seen: dict[str, tuple[str, str]] = {}
    for path in paths:
        for row in read_rows(path):
            if row.get("training_allowed") is not True:
                continue
            text, label = text_label(row)
            key = normalize_text(text)
            if key in seen and seen[key][1] != label:
                raise ValueError("conflicting labels for the same training text")
            seen.setdefault(key, (text, label))
    return list(seen.values())


def fit(examples: list[tuple[str, str]], labels: list[str], seed: int = 42) -> TextClassifier:
    clf = TextClassifier(labels)
    clf.fit([t for t, _ in examples], [y for _, y in examples], epochs=EPOCHS, seed=seed)
    return clf


def accuracy(clf: TextClassifier, rows: list[tuple[str, str]]) -> float:
    return sum(clf.predict(t)[0] == y for t, y in rows) / len(rows)


def priority(probabilities: dict[str, float], strategy: str) -> float:
    """Higher means ask a human sooner. Uses only the model's own probabilities, never a label."""
    ranked = sorted(probabilities.values(), reverse=True)
    margin = ranked[0] - ranked[1]
    if strategy == "margin":
        return -margin
    if strategy == "entropy":
        return -sum(p * math.log(p) for p in probabilities.values() if p > 0)
    if strategy == "safety_margin":
        # A plausible safety label outranks plain uncertainty: missing it is the costly error.
        safety = sum(probabilities.get(label, 0.0) for label in SAFETY_LABELS)
        top_is_safety = max(probabilities, key=probabilities.get) in SAFETY_LABELS
        return (1.0 if safety >= SAFETY_MASS and not top_is_safety else 0.0) - margin
    raise ValueError(f"unknown strategy: {strategy}")


def select(clf: TextClassifier, pool: list[str], k: int, strategy: str, rng: random.Random) -> list[int]:
    """Pick k pool indices; near-identical texts (SimHash) are not asked twice in one batch."""
    if strategy == "random":
        order = list(range(len(pool)))
        rng.shuffle(order)
    else:
        scores = [priority(clf.predict_proba(text), strategy) for text in pool]
        order = sorted(range(len(pool)), key=lambda i: (-scores[i], i))
    chosen: list[int] = []
    hashes: list[int] = []
    for index in order:
        h = simhash(pool[index])
        if any(hamming(h, other) <= NEAR_BITS for other in hashes):
            continue
        chosen.append(index)
        hashes.append(h)
        if len(chosen) == k:
            break
    return chosen


def simulate(train: list[Path], pool_paths: list[Path], calibration: Path, test: Path, *,
             rounds: int = 8, batch: int = 10, seeds: int = 3) -> dict:
    if not (1 <= rounds <= 50 and 1 <= batch <= 500 and 1 <= seeds <= 10):
        raise ValueError("invalid simulation budget")
    base = admitted(train)
    base_keys = {normalize_text(t) for t, _ in base}
    # The pool is labelled, but a label is only read after its row has been acquired.
    pool = [row for row in admitted(pool_paths) if normalize_text(row[0]) not in base_keys]
    cal = [text_label(r) for r in read_rows(calibration)]
    held = [text_label(r) for r in read_rows(test)]
    if {normalize_text(t) for t, _ in held} & ({normalize_text(t) for t, _ in pool} | base_keys):
        raise ValueError("test rows overlap the training base or pool")
    labels = sorted({y for _, y in base} | {y for _, y in pool})
    curves: dict[str, list[list[float]]] = {}
    final_test: dict[str, list[float]] = {}
    acquired_safety: dict[str, list[int]] = {}
    for strategy in STRATEGIES:
        runs = seeds if strategy == "random" else 1  # deterministic strategies need one run
        for seed in range(runs):
            rng = random.Random(seed)
            remaining = list(pool)
            known = list(base)
            clf = fit(known, labels)
            curve = [accuracy(clf, cal)]
            safety = 0
            for _ in range(rounds):
                picked = set(select(clf, [t for t, _ in remaining], batch, strategy, rng))
                answers = [remaining[i] for i in sorted(picked)]  # the simulated human answers here
                safety += sum(label in SAFETY_LABELS for _, label in answers)
                known += answers
                remaining = [row for i, row in enumerate(remaining) if i not in picked]
                clf = fit(known, labels)
                curve.append(accuracy(clf, cal))
            curves.setdefault(strategy, []).append(curve)
            final_test.setdefault(strategy, []).append(accuracy(clf, held))
            acquired_safety.setdefault(strategy, []).append(safety)
    summary = {}
    for strategy, runs in curves.items():
        mean_curve = [sum(c[i] for c in runs) / len(runs) for i in range(rounds + 1)]
        summary[strategy] = {
            "runs": len(runs),
            "calibration_curve": [round(v, 4) for v in mean_curve],
            # Area under the learning curve: rewards learning early, not only the last round.
            "calibration_auc": round(sum(mean_curve[1:]) / rounds, 4),
            "safety_examples_acquired": round(sum(acquired_safety[strategy]) / len(runs), 2),
            "test_after_budget_report_only": round(sum(final_test[strategy]) / len(runs), 4)}
    # Ties go to the strategy that asked humans about more safety cases.
    winner = max(summary, key=lambda s: (summary[s]["calibration_auc"], summary[s]["safety_examples_acquired"]))
    return {"format": "hydra-decision-active-learning-simulation/1",
            "base_examples": len(base), "pool_examples": len(pool), "rounds": rounds, "batch": batch,
            "labels_budget": rounds * batch, "random_seeds": seeds,
            "selection_split": "calibration", "test_role": "reported once after the budget; never used to choose",
            "strategies": summary, "chosen_strategy": winner,
            "sources_sha256": {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in [*train, *pool_paths, calibration, test]},
            "limitation": ("The simulated human is a pre-labelled synthetic pool; real reviewers are slower, "
                           "can disagree and see real traffic. Re-run the simulation after each human round.")}


def make_queue(train: list[Path], pool_path: Path, out: Path, *, strategy: str, k: int = 40) -> dict:
    if strategy not in STRATEGIES:
        raise ValueError(f"unknown strategy: {strategy}")
    if out.exists():
        raise FileExistsError("each review round is a new, immutable directory")
    base = admitted(train)
    known = {normalize_text(t) for t, _ in base}
    labels = sorted({y for _, y in base})
    candidates, quarantined, seen = [], 0, set()
    for row in read_rows(pool_path):
        text = text_label(row)[0]
        key = normalize_text(text)
        if not text.strip() or key in known or key in seen:
            continue
        seen.add(key)
        if _finding_types(text):
            quarantined += 1  # personal data never reaches a reviewer queue; only the count is kept
            continue
        candidates.append(text)
    clf = fit(base, labels)
    picked = select(clf, candidates, k, strategy, random.Random(0))
    rows = []
    for rank, index in enumerate(picked):
        text = candidates[index]
        probabilities = clf.predict_proba(text)
        top = sorted(probabilities, key=probabilities.get, reverse=True)[:3]
        rows.append({"id": f"review-{hashlib.sha256(text.encode()).hexdigest()[:12]}", "rank": rank, "text": text,
                     "model_suggestions": {label: probabilities[label] for label in top},
                     "safety_flag": sum(probabilities.get(s, 0.0) for s in SAFETY_LABELS) >= SAFETY_MASS,
                     "human_label": None, "reviewer": None, "notes": ""})
    out.mkdir(parents=True)
    (out / "queue.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                                     encoding="utf-8")
    manifest = {"format": "hydra-decision-review-queue/1", "strategy": strategy, "requested": k,
                "queued": len(rows), "pool_candidates": len(candidates), "privacy_quarantined": quarantined,
                "labels": labels, "pool_sha256": hashlib.sha256(pool_path.read_bytes()).hexdigest(),
                "train_sha256": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in train},
                "instructions": ("Fill human_label with one of labels (or 'discard') and reviewer with your "
                                 "name or initials. model_suggestions are hints, not answers."),
                "training_allowed": False}
    write_json(out / "manifest.json", manifest)
    return manifest


def admit(queue_dir: Path, out: Path) -> dict:
    if out.exists():
        raise FileExistsError("admitted files are never rewritten")
    manifest = json.loads((queue_dir / "manifest.json").read_text(encoding="utf-8"))
    labels = set(manifest["labels"])
    admitted_rows, skipped = [], {"unlabelled": 0, "discarded": 0, "no_reviewer": 0, "unknown_label": 0}
    for row in read_rows(queue_dir / "queue.jsonl"):
        label, reviewer = row.get("human_label"), row.get("reviewer")
        if not label:
            skipped["unlabelled"] += 1
        elif label == "discard":
            skipped["discarded"] += 1
        elif not (isinstance(reviewer, str) and reviewer.strip()):
            skipped["no_reviewer"] += 1
        elif label not in labels:
            skipped["unknown_label"] += 1
        else:
            admitted_rows.append({"id": row["id"], "text": row["text"], "expected": label,
                                  "source": f"human-reviewed active learning ({queue_dir.name})",
                                  "reviewer": reviewer.strip(), "training_allowed": True,
                                  "model_agreed": label == next(iter(row["model_suggestions"]), None),
                                  "sha256": hashlib.sha256(row["text"].encode("utf-8")).hexdigest()})
    if not admitted_rows:
        raise ValueError("no human-labelled rows to admit")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in admitted_rows), encoding="utf-8")
    return {"admitted": len(admitted_rows), "skipped": skipped,
            "model_agreement": round(sum(r["model_agreed"] for r in admitted_rows) / len(admitted_rows), 4),
            "out": str(out), "sha256": hashlib.sha256(out.read_bytes()).hexdigest()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    default_train = [Path("data/decision-corpus-v4/train.jsonl")]
    sim = sub.add_parser("simulate")
    sim.add_argument("--train", type=Path, nargs="+", default=default_train)
    sim.add_argument("--pool", type=Path, nargs="+",
                     default=[Path("data/human-dev-v1.jsonl"), Path("data/human-dev-v2.jsonl")])
    sim.add_argument("--calibration", type=Path, default=Path("data/decision-corpus-v4/calibration.jsonl"))
    sim.add_argument("--test", type=Path, default=Path("data/decision-corpus-v4/test.jsonl"))
    sim.add_argument("--rounds", type=int, default=8)
    sim.add_argument("--batch", type=int, default=10)
    sim.add_argument("--seeds", type=int, default=3)
    sim.add_argument("--out", type=Path, required=True)
    que = sub.add_parser("queue")
    que.add_argument("--train", type=Path, nargs="+", default=default_train)
    que.add_argument("--pool", type=Path, required=True, help="JSONL with text (or input.query); labels ignored")
    que.add_argument("--strategy", choices=STRATEGIES)
    que.add_argument("--strategy-from", type=Path, help="simulation evidence whose chosen_strategy to use")
    que.add_argument("-k", type=int, default=40)
    que.add_argument("--out", type=Path, required=True)
    adm = sub.add_parser("admit")
    adm.add_argument("--queue", type=Path, required=True)
    adm.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "simulate":
        if args.out.exists():
            parser.error("choose a new evidence path")
        result = simulate(args.train, args.pool, args.calibration, args.test,
                          rounds=args.rounds, batch=args.batch, seeds=args.seeds)
        write_json(args.out, result)
        print(json.dumps({"chosen_strategy": result["chosen_strategy"],
                          **{s: v["calibration_auc"] for s, v in result["strategies"].items()}}, indent=2))
    elif args.command == "queue":
        strategy = args.strategy or (json.loads(args.strategy_from.read_text(encoding="utf-8"))["chosen_strategy"]
                                     if args.strategy_from else None)
        if strategy is None:
            parser.error("pass --strategy or --strategy-from")
        print(json.dumps(make_queue(args.train, args.pool, args.out, strategy=strategy, k=args.k), indent=2,
                         ensure_ascii=False))
    else:
        print(json.dumps(admit(args.queue, args.out), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
