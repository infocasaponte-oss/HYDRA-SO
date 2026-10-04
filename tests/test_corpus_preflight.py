# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
import gzip
import json

import pytest

from hydra.training.corpus_preflight import audit, digest


def corpus(root, train, test):
    files = {}
    for split, rows in (("train", train), ("test", test)):
        path = root / f"{split}-00000.jsonl.gz"
        with gzip.open(path, "wt", encoding="utf-8") as stream:
            for row in rows:
                stream.write(json.dumps(row) + "\n")
        files[path.name] = {"sha256": digest(path), "documents": len(rows)}
    (root / "manifest.json").write_text(json.dumps({"files": files}), encoding="utf-8")


def test_hash_pinned_streaming_gzip_audit_without_invented_tokens(tmp_path):
    corpus(tmp_path, [{"text": "Training text", "license": "user grant", "family_id": "a"}],
           [{"text": "Held out text", "family_id": "b"}])
    report = audit(tmp_path)
    assert report["integrity_checks_passed"]
    assert report["splits"] == {"test": 1, "train": 1}
    assert report["tokens"] is None
    assert report["rows_with_declared_license"] == 1
    assert not report["ready_for_4b_training"] and not report["activated"]
    assert "Training text" not in json.dumps(report)


def test_cross_split_duplicates_and_family_variants_are_reported(tmp_path):
    corpus(tmp_path, [{"text": "Same question", "family_id": "family"}],
           [{"text": " SAME   QUESTION ", "family_id": "family"},
            {"text": "Paraphrase of question", "family_id": "family"}])
    report = audit(tmp_path)
    assert report["cross_split_duplicate_rows"] == 1
    assert report["family_overlap_rows"] == 1
    assert report["family_overlap_groups"] == 1
    assert not report["integrity_checks_passed"]


def test_hash_count_and_holdout_training_flags_fail(tmp_path):
    corpus(tmp_path, [{"text": "Training"}], [{"text": "Test", "training_allowed": True}])
    path = tmp_path / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["files"]["train-00000.jsonl.gz"].update(sha256="0" * 64, documents=3)
    path.write_text(json.dumps(manifest))
    report = audit(tmp_path)
    assert report["errors"] == {"holdout_marked_for_training": 1, "shard_hash_mismatch": 1, "declared_count_mismatch": 1}
    assert not report["integrity_checks_passed"]


def test_path_escape_is_rejected(tmp_path):
    (tmp_path / "manifest.json").write_text(json.dumps({"files": {"../escape.jsonl": {"sha256": "0" * 64}}}))
    with pytest.raises(ValueError, match="inside corpus"):
        audit(tmp_path)


def test_invalid_records_do_not_echo_input(tmp_path):
    corpus(tmp_path, [None, {"text": "secret", "split": "invalid"}, {"text": ""}],
           [{"input": {"query": "Valid question"}, "split": "train"}])
    report = audit(tmp_path)
    assert report["errors"]["invalid_record"] == 1
    assert report["errors"]["row_shard_split_mismatch"] == 1
    assert "secret" not in json.dumps(report)


def test_changes_during_audit_are_detected(tmp_path, monkeypatch):
    corpus(tmp_path, [{"text": "Train"}], [{"text": "Test"}])
    from hydra.training import corpus_preflight
    original = corpus_preflight.digest
    counts = {}

    def changed(path):
        counts[path] = counts.get(path, 0) + 1
        value = original(path)
        return "1" * 64 if path.name.startswith("train-") and counts[path] == 2 else value

    monkeypatch.setattr(corpus_preflight, "digest", changed)
    report = audit(tmp_path)
    assert report["errors"]["shard_changed_during_audit"] == 1
    assert not report["integrity_checks_passed"]
