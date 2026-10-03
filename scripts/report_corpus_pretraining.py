# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""Pre-training audit of the decision corpora in data/: integrity, balance, duplicates and leakage.

Read-only: rows are never modified or deleted. The output is evidence for a human decision,
not an approval to train."""
import argparse
import hashlib
import json
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from hydra.corpus.dedup import hamming, normalize_text, simhash
from hydra.training.evidence_io import write_json

CORPUS = Path("data/decision-corpus-v3")
HUMAN = [Path("data/human-dev-v1.jsonl"), Path("data/human-dev-v2.jsonl")]
NEAR_BITS = 3


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path, split: str) -> list[dict]:
    rows = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        r = json.loads(line)
        text = r["input"]["query"] if "input" in r else r["text"]
        label = r["output"]["task_type"] if "output" in r else r["expected"]
        # decision_corpus_v3 hashes the lower-cased, whitespace-normalized prompt; human-dev hashes raw text.
        stored, hashed = (r["prompt_sha256"], " ".join(text.lower().split())) if "prompt_sha256" in r \
            else (r.get("sha256"), text)
        rows.append(dict(id=r["id"], split=split, declared_split=r.get("split"), source=str(path), line=n, text=text, label=label,
                         family=r.get("family") or r.get("boundary_family"),
                         training_allowed=r.get("training_allowed"), rights=r.get("rights"),
                         stored_sha256=stored, sha256=hashlib.sha256(hashed.encode()).hexdigest()))
    return rows


def lengths(rows: list[dict]) -> dict:
    words = [len(r["text"].split()) for r in rows]
    return dict(min=min(words), median=statistics.median(words), mean=round(statistics.mean(words), 2),
                max=max(words))


def audit(corpus: Path, human: list[Path]) -> dict:
    manifest = json.loads((corpus / "manifest.json").read_text(encoding="utf-8"))
    integrity = {}
    splits: dict[str, list[dict]] = {}
    for name, meta in manifest["files"].items():
        path = corpus / name
        actual = file_sha256(path)
        split = name.removesuffix(".jsonl")
        splits[split] = load(path, split)
        integrity[str(path)] = dict(manifest_sha256=meta["sha256"], actual_sha256=actual,
                                    sha256_match=actual == meta["sha256"], manifest_examples=meta["examples"],
                                    actual_examples=len(splits[split]))
    for path in human:
        splits[path.stem] = load(path, path.stem)
        integrity[str(path)] = dict(actual_sha256=file_sha256(path), actual_examples=len(splits[path.stem]),
                                    manifest_sha256=None, sha256_match=None)

    rows = [r for s in splits.values() for r in s]
    labels = manifest["labels"]
    # train_decision_v4 trains on these three sources; calibration and test must stay disjoint from them.
    training = ["train", *[p.stem for p in human]]
    held_out = [s for s in splits if s not in training]

    hash_mismatch = [r["id"] for r in rows if r["stored_sha256"] and r["stored_sha256"] != r["sha256"]]
    ids = Counter(r["id"] for r in rows)
    unknown_labels = sorted({r["label"] for r in rows} - set(labels))
    split_field_mismatch = [r["id"] for r in rows if r["declared_split"] not in (None, r["split"])]
    not_allowed = [r["id"] for s in training for r in splits[s] if r["training_allowed"] is not True]
    unverified_rights = [r["id"] for r in splits["train"] if not (r["rights"] or {}).get("verified")]

    by_norm: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_norm[normalize_text(r["text"])].append(r)
    exact_within = {s: sum(len(g) - 1 for g in _groups(splits[s]) if len(g) > 1) for s in splits}
    exact_cross = []
    label_conflicts = []
    for text, group in by_norm.items():
        if len({r["split"] for r in group}) > 1 and any(r["split"] in held_out for r in group) \
                and any(r["split"] in training for r in group):
            exact_cross.append(dict(text=text, rows=[(r["split"], r["id"], r["label"]) for r in group]))
        if len({r["label"] for r in group}) > 1:
            label_conflicts.append(dict(text=text, rows=[(r["split"], r["id"], r["label"]) for r in group]))

    hashes = {r["id"]: simhash(r["text"]) for r in rows}
    train_rows = [r for s in training for r in splits[s]]
    near = {}
    for s in held_out:
        flagged = []
        for r in splits[s]:
            best = min(train_rows, key=lambda t: hamming(hashes[r["id"]], hashes[t["id"]]))
            d = hamming(hashes[r["id"]], hashes[best["id"]])
            if d <= NEAR_BITS:
                flagged.append(dict(id=r["id"], text=r["text"], nearest=best["id"], nearest_text=best["text"],
                                    hamming=d, same_label=r["label"] == best["label"]))
        near[s] = dict(rows=len(splits[s]), flagged=len(flagged), examples=flagged[:10])

    # Template reuse: identical text once the paraphrase prefix/suffix is stripped.
    stems = {s: Counter(_stem(r["text"]) for r in splits[s]) for s in ("train", "calibration", "test")}
    template_overlap = {s: sum(1 for r in splits[s] if _stem(r["text"]) in stems["train"])
                        for s in ("calibration", "test")}

    families = {s: sorted({r["family"] for r in splits[s] if r["family"]}) for s in splits}
    return dict(
        format="hydra-corpus-pretraining-audit/1",
        corpus_manifest=dict(format=manifest["format"], corpus_sha256=manifest["corpus_sha256"],
                             source=manifest["source"], limitations=manifest["limitations"],
                             training_allowed_splits=manifest["training_allowed_splits"]),
        training_sources=training, held_out_splits=held_out,
        integrity=integrity,
        counts={s: len(v) for s, v in splits.items()},
        unique_texts={s: len({normalize_text(r["text"]) for r in v}) for s, v in splits.items()},
        labels={s: dict(sorted(Counter(r["label"] for r in v).items())) for s, v in splits.items()},
        labels_missing={s: [lab for lab in labels if lab not in {r["label"] for r in v}] for s, v in splits.items()},
        word_lengths={s: lengths(v) for s, v in splits.items()},
        families=families,
        checks=dict(row_hash_mismatches=hash_mismatch, duplicate_ids=[i for i, c in ids.items() if c > 1],
                    unknown_labels=unknown_labels, training_not_allowed=not_allowed,
                    train_rights_unverified=len(unverified_rights), split_field_mismatch=split_field_mismatch),
        duplicates=dict(exact_within_split=exact_within, exact_training_vs_held_out=len(exact_cross),
                        exact_training_vs_held_out_examples=exact_cross[:10],
                        label_conflicts=len(label_conflicts), label_conflict_examples=label_conflicts[:10]),
        near_duplicates=dict(method=f"64-bit SimHash over word trigrams, Hamming <= {NEAR_BITS}", **near),
        template_stem_overlap_with_train=template_overlap,
        unique_template_stems={s: len(c) for s, c in stems.items()},
        limitation="Lexical/hash checks only; semantic contamination and label correctness need human review.",
    )


def _groups(rows: list[dict]) -> list[list[dict]]:
    g: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        g[normalize_text(r["text"])].append(r)
    return list(g.values())


PREFIXES = ("por favor, ", "necesito que ", "en español, ", "ayúdame a ")
SUFFIX = re.compile(r"\s*caso de referencia \d+\.?$")


def _stem(text: str) -> str:
    """Base template once the v3 paraphrase prefix and the "Caso de referencia N." suffix are removed."""
    t = SUFFIX.sub("", normalize_text(text))
    for p in PREFIXES:
        if t.startswith(p):
            t = t[len(p):]
    return t.rstrip(" .")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, default=CORPUS)
    parser.add_argument("--human", type=Path, nargs="*", default=HUMAN)
    parser.add_argument("--out", type=Path, default=Path("docs/evidence/corpus-pretraining-audit-2026-10-03.json"))
    args = parser.parse_args()
    write_json(args.out, audit(args.corpus, args.human))
    print(args.out)
