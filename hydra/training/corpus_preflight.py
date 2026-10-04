# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""Read-only, streaming corpus checks before planning a larger training run."""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile

from hydra.core.atomic import write_text_atomic

SPLITS = {"train", "dev", "validation", "calibration", "test"}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def audit(corpus: Path, tokenizer: Path | None = None) -> dict:
    root = Path(corpus).resolve()
    manifest_path = root / "manifest.json"
    manifest_hash = digest(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), dict):
        raise ValueError("manifest requires a files mapping")
    encoder = None
    tokenizer_hash = None
    if tokenizer is not None:
        import sentencepiece as spm
        tokenizer_hash = digest(tokenizer)
        encoder = spm.SentencePieceProcessor(model_file=str(tokenizer))
    files, errors, splits = {}, Counter(), Counter()
    declared_licenses, sources = Counter(), Counter()
    duplicate_rows = cross_split_rows = family_overlap_rows = 0
    family_rows = license_rows = characters = tokens = records = family_overlap_groups = 0
    with tempfile.TemporaryDirectory(prefix="hydra-corpus-audit-") as scratch:
        db = sqlite3.connect(str(Path(scratch) / "index.sqlite3"))
        try:
            db.execute("CREATE TABLE texts (hash TEXT PRIMARY KEY, split TEXT)")
            db.execute("CREATE TABLE families (hash TEXT, split TEXT, PRIMARY KEY(hash, split))")
            for name, entry in sorted(manifest["files"].items()):
                if not isinstance(name, str) or not name.endswith((".jsonl", ".jsonl.gz")):
                    continue
                if name.startswith("THIRD_PARTY_ATTRIBUTIONS"):
                    continue
                path = (root / name).resolve()
                if not path.is_relative_to(root) or not path.is_file():
                    raise ValueError("manifest shard must be a file inside corpus")
                if not isinstance(entry, dict) or not isinstance(entry.get("sha256"), str):
                    raise ValueError("every shard requires a declared sha256")
                before = digest(path)
                if before != entry["sha256"]:
                    errors["shard_hash_mismatch"] += 1
                file_split = entry.get("split", name.split("/")[-1].split(".")[0].split("-")[0])
                count = valid = 0
                opener = gzip.open if name.endswith(".gz") else open
                with opener(path, "rt", encoding="utf-8") as stream:
                    for line in stream:
                        if not line.strip():
                            continue
                        count += 1
                        try:
                            row = json.loads(line)
                            if not isinstance(row, dict):
                                raise ValueError
                            split = row.get("split", file_split)
                            if split not in SPLITS:
                                errors["unknown_split"] += 1
                                continue
                            if file_split in SPLITS and split != file_split:
                                errors["row_shard_split_mismatch"] += 1
                                continue
                            text = row.get("text")
                            if text is None and isinstance(row.get("input"), dict):
                                text = row["input"].get("query")
                            if not isinstance(text, str) or not text.strip():
                                errors["unsupported_or_empty_text"] += 1
                                continue
                            if row.get("training_allowed") is True and split != "train":
                                errors["holdout_marked_for_training"] += 1
                            text_hash = hashlib.sha256(" ".join(text.casefold().split()).encode()).hexdigest()
                            existing = db.execute("SELECT split FROM texts WHERE hash=?", (text_hash,)).fetchone()
                            if existing:
                                duplicate_rows += 1
                                if existing[0] != split:
                                    cross_split_rows += 1
                            else:
                                db.execute("INSERT INTO texts VALUES (?,?)", (text_hash, split))
                            family = row.get("family_id")
                            if family is not None:
                                if not isinstance(family, str) or not family.strip():
                                    errors["invalid_family_id"] += 1
                                else:
                                    family_rows += 1
                                    family_hash = hashlib.sha256(family.encode()).hexdigest()
                                    existing = db.execute("SELECT split FROM families WHERE hash=?", (family_hash,)).fetchone()
                                    if existing and existing[0] != split:
                                        family_overlap_rows += 1
                                    db.execute("INSERT OR IGNORE INTO families VALUES (?,?)", (family_hash, split))
                            rights = row.get("rights")
                            license_name = row.get("license")
                            if license_name is None and isinstance(rights, dict):
                                license_name = rights.get("license")
                            if isinstance(license_name, str) and license_name.strip():
                                license_rows += 1
                                declared_licenses[hashlib.sha256(license_name.encode()).hexdigest()] += 1
                            source = row.get("source")
                            if isinstance(source, str) and source.strip():
                                sources[hashlib.sha256(source.encode()).hexdigest()] += 1
                            characters += len(text)
                            if encoder is not None:
                                tokens += len(encoder.encode(text))
                            splits[split] += 1
                            valid += 1
                        except (ValueError, TypeError):
                            errors["invalid_record"] += 1
                records += valid
                declared_count = entry.get("documents", entry.get("examples"))
                if declared_count is not None and (type(declared_count) is not int or declared_count != count):
                    errors["declared_count_mismatch"] += 1
                if digest(path) != before:
                    errors["shard_changed_during_audit"] += 1
                files[name] = {"sha256": before, "rows": count, "valid_rows": valid}
                db.commit()
            family_overlap_groups = db.execute("SELECT COUNT(*) FROM (SELECT hash FROM families GROUP BY hash HAVING COUNT(*) > 1)").fetchone()[0]
        finally:
            db.close()
    if digest(manifest_path) != manifest_hash:
        errors["manifest_changed_during_audit"] += 1
    if tokenizer is not None and digest(tokenizer) != tokenizer_hash:
        errors["tokenizer_changed_during_audit"] += 1
    if not splits["train"] or not any(splits[s] for s in SPLITS - {"train"}):
        errors["train_and_holdout_required"] += 1
    clean = not errors and not duplicate_rows and not family_overlap_rows
    return {"format": "hydra-corpus-preflight/1", "manifest_sha256": manifest_hash,
            "files": files, "records": records, "splits": dict(splits), "characters": characters,
            "tokens": tokens if encoder is not None else None, "tokenizer_sha256": tokenizer_hash,
            "token_count_basis": "encoded document content; excludes BOS/EOS and packing" if encoder else "not measured",
            "duplicate_rows": duplicate_rows, "cross_split_duplicate_rows": cross_split_rows,
            "family_overlap_rows": family_overlap_rows, "family_overlap_groups": family_overlap_groups,
            "rows_with_family_id": family_rows,
            "rows_with_declared_license": license_rows, "declared_license_hashes": dict(declared_licenses),
            "source_hashes": dict(sources), "errors": dict(errors), "integrity_checks_passed": clean,
            "ready_for_4b_training": False, "activated": False,
            "pending": ["semantic leakage review", "privacy and provenance review", "independent evaluation",
                        "4B architecture, tokenizer, trainer and hardware validation"],
            "limitation": "Structural checks do not certify licensing, factual quality or dataset sufficiency."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--tokenizer", type=Path)
    args = parser.parse_args()
    if args.out.exists():
        parser.exit(2, "error: choose a new report path\n")
    try:
        result = audit(args.corpus, args.tokenizer)
        write_text_atomic(args.out, json.dumps(result, indent=2, allow_nan=False))
    except (ValueError, OSError, sqlite3.Error) as error:
        parser.exit(2, f"error: corpus audit failed ({type(error).__name__})\n")
    print(json.dumps({k: result[k] for k in ("records", "splits", "integrity_checks_passed", "ready_for_4b_training")}, indent=2))
    if not result["integrity_checks_passed"]:
        parser.exit(1)


if __name__ == "__main__":
    main()
