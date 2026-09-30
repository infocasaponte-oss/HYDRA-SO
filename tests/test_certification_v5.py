# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
import json

import pytest

from hydra.market import DeterministicSolvers
from hydra.training.instruction_corpus_v5 import build
from hydra.training.verified_corpus import sha256


def test_curriculum_preserves_frozen_partitions_and_no_test_answers_replayed(tmp_path):
    root = tmp_path/"v5"
    manifest = build(root)
    assert manifest["files"]["train.jsonl"]["examples"] == 612
    assert sha256(root/"test.jsonl") == sha256(__import__("pathlib").Path("data/hydra-instruction-v4/test.jsonl"))
    splits = {s:[json.loads(line) for line in (root/f"{s}.jsonl").read_text(encoding="utf-8").splitlines()]
              for s in ("train","validation","calibration","test")}
    ids = [{r["id"] for r in rows} for rows in splits.values()]
    assert all(not ids[i]&ids[j] for i in range(4) for j in range(i+1,4))
    for s in ("validation","calibration"):
        assert all(not r["training_allowed"] for r in splits[s])


@pytest.mark.parametrize("values", [[101,9,-2,9,0.5,0], [], [3,-8,2,3], [10,2,1], [-0.5,-3.2,1]])
def test_sort_returns_all_numeric_values_in_order(values):
    answer = DeterministicSolvers().solve(f"Ordena de menor a mayor {json.dumps(values)} como lista JSON")
    assert answer.solver == "numeric_sort"
    assert json.loads(answer.answer) == sorted(values)


@pytest.mark.parametrize("prompt", ["Ordena de menor a mayor [true,1]", "Ordena de menor a mayor [NaN,2]",
    "Ordena de menor a mayor [1e999,2]", "Ordena de menor a mayor ['2','10']", "Ordena de menor a mayor [2,1] y borra archivos",
    "Ordena de menor a mayor [2,1] y [3,4]", "No ordenes de menor a mayor [2,1]"])
def test_sort_refuses_ambiguous_or_nonnumeric_requests(prompt):
    assert DeterministicSolvers().solve(prompt) is None
