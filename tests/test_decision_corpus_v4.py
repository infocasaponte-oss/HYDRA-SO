# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
import json

import pytest

from hydra.training import decision_corpus_v4 as v4


def _rows(root, split):
    return [json.loads(line) for line in (root / f"{split}.jsonl").read_text(encoding="utf-8").splitlines()]


def test_splits_use_disjoint_templates_and_only_train_is_admitted(tmp_path):
    manifest = v4.build(tmp_path / "corpus", reserved_sources=[])
    assert manifest["counts"] == {"train": 480, "calibration": 80, "test": 80}
    rows = {split: _rows(tmp_path / "corpus", split) for split in manifest["counts"]}
    templates = {split: {r["template_id"] for r in values} for split, values in rows.items()}
    assert not templates["train"] & templates["calibration"] and not templates["train"] & templates["test"]
    texts = {split: {v4.normalize(r["input"]["query"]) for r in values} for split, values in rows.items()}
    assert not texts["train"] & (texts["calibration"] | texts["test"])
    assert all(r["training_allowed"] is (split == "train") for split, values in rows.items() for r in values)
    assert not any(r["input"]["query"].startswith(("Necesito que ", "Ayúdame a ")) for r in rows["train"])


def test_held_out_template_matching_reserved_text_is_rejected(tmp_path):
    reserved = tmp_path / "human.jsonl"
    reserved.write_text(json.dumps({"text": v4.TEMPLATES["chat"]["test"][0], "expected": "chat"}) + "\n",
                        encoding="utf-8")
    with pytest.raises(ValueError, match="held-out template"):
        v4.build(tmp_path / "corpus", reserved_sources=[reserved])
    assert not (tmp_path / "corpus").exists()


def test_existing_corpus_is_never_rewritten(tmp_path):
    v4.build(tmp_path, reserved_sources=[])
    with pytest.raises(ValueError, match="never rewritten"):
        v4.build(tmp_path, reserved_sources=[])
