# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
import json
import hashlib
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from hydra.api.main import create_app
from hydra.core.config import Settings
from hydra.hyd.corpus_contract import IntakeRecord, inspect_intake, snapshot
from hydra.hyd.integration import contract, RoutingAdapter, export_runtime
from hydra.hyd.lab import HydLab, JobRequest
from hydra.hyd.model import CandidateRanker
from hydra.router.decision_contract import CRITERIA


def record(label="chat", key="one", family="family"):
    return {"id": key, "original_text": f"Original question {key}", "text": f"Original question {key}",
            "expected": label, "family_id": family, "source_kind": "human_evaluator", "consent": True,
            "consent_version": "test-only", "consent_event_ref": "test-fixture-not-real-evidence",
            "privacy_reviewed": True, "suspect_template": False,
            "rights": {"license": "test-fixture", "verified": True, "evidence_ref": "fixture"},
            "reviews": [{"reviewer_id": name, "person_id": name, "label": label, "kind": "human", "reviewed_at": "2026-10-04"}
                        for name in ("fixture-a", "fixture-b")]}


def write_rows(path, rows):
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


def test_intake_requires_explicit_consent_origin_and_two_reviews():
    assert IntakeRecord.model_validate(record()).admissible()
    for update in ({"consent": False}, {"withdrawn": True}, {"source_kind": "unknown"},
                   {"source_kind": "ai_assisted"}, {"privacy_reviewed": False}, {"suspect_template": True}):
        assert not IntakeRecord.model_validate({**record(), **update}).admissible()
    row = record()
    row["reviews"][1]["reviewer_id"] = row["reviews"][0]["reviewer_id"]
    assert not IntakeRecord.model_validate(row).admissible()
    row = record()
    row["reviews"][1]["person_id"] = row["reviews"][0]["person_id"]
    assert not IntakeRecord.model_validate(row).admissible()
    row = record()
    row["reviews"][1]["label"] = "coding"
    assert not IntakeRecord.model_validate(row).admissible()
    with pytest.raises(ValueError):
        IntakeRecord.model_validate({**record(), "consent": "true"})


def test_correction_never_silently_changes_original():
    row = {**record(), "text": "Corrected question"}
    with pytest.raises(ValueError):
        IntakeRecord.model_validate(row)
    corrected = IntakeRecord.model_validate({**row, "correction": {"human_accepted": True,
        "reviewer_id": "fixture-a", "reason": "fixture spelling change"}})
    assert corrected.original_text != corrected.text


def test_ai_opinion_does_not_supply_human_review():
    row = {**record(), "reviews": [], "ai_second_opinions": [{"label": "chat", "provider": "fixture"}]}
    assert not IntakeRecord.model_validate(row).admissible()


def test_one_person_can_experiment_without_claiming_double_review(tmp_path):
    row = record()
    row["reviews"] = row["reviews"][:1]
    parsed = IntakeRecord.model_validate(row)
    assert parsed.admissible(require_double_review=False)
    assert not parsed.admissible(require_double_review=True)
    source = write_rows(tmp_path / "one-person.jsonl", [row])
    _, report = inspect_intake(source)
    assert report["admissible"] == 1 and report["double_reviewed"] == 0


def test_snapshot_keeps_family_together_and_hashes_match(tmp_path):
    rows = [record(label, f"{label}-{i}", f"family-{i}") for label in CRITERIA for i in range(50)]
    source = write_rows(tmp_path / "source.jsonl", rows)
    result = snapshot(source, tmp_path / "out")
    partitions = {}
    for split in ("train", "calibration", "test"):
        path = tmp_path / "out" / f"{split}.jsonl"
        assert result["sha256"][split] == hashlib.sha256(path.read_bytes()).hexdigest()
        for row in map(json.loads, path.read_text().splitlines()):
            assert row["training_allowed"] == (split == "train")
            assert row["family_id"] not in partitions or partitions[row["family_id"]] == split
            partitions[row["family_id"]] = split
    snapshot(source, tmp_path / "second")
    assert (tmp_path / "out" / "manifest.json").read_bytes() == (tmp_path / "second" / "manifest.json").read_bytes()


def test_current_lovable_export_is_not_silently_admitted(tmp_path):
    source = write_rows(tmp_path / "legacy.jsonl", [{"text": "Question", "expected": "chat",
        "meta": {"consent": True, "real": True, "author": "private@example.test"}}])
    _, result = inspect_intake(source)
    assert not result["complete"]
    assert "private@example" not in json.dumps(result)


def test_jobs_persist_detect_tampering_and_can_cancel(tmp_path):
    source = write_rows(tmp_path / "source.jsonl", [record()])
    lab = HydLab(tmp_path, tmp_path / "state")
    job = lab.submit(JobRequest(kind="validate", dataset="source.jsonl"))
    source.write_text("invalid JSON")
    assert lab.run(job["id"])["state"] == "failed"
    assert HydLab(tmp_path, tmp_path / "state").get(job["id"])["state"] == "failed"
    write_rows(source, [record()])
    job = lab.submit(JobRequest(kind="validate", dataset="source.jsonl"))
    assert lab.cancel(job["id"])["state"] == "cancelled"
    with pytest.raises(ValueError):
        lab.run(job["id"])
    with pytest.raises(ValueError):
        lab.submit(JobRequest(kind="validate", dataset="../outside.jsonl"))


def test_no_auto_execution_and_successful_validation(tmp_path):
    write_rows(tmp_path / "source.jsonl", [record()])
    lab = HydLab(tmp_path, tmp_path / "state")
    job = lab.submit(JobRequest(kind="validate", dataset="source.jsonl"))
    assert job["state"] == "queued"
    result = lab.run(job["id"])
    assert result["state"] == "completed" and result["result"]["admissible"] == 1
    assert result["activated"] is False


def test_opt_in_admin_routes_and_single_node_guard(tmp_path):
    settings = Settings(offline=True, runtime_api=False, api_key="api-test", admin_token="admin-test",
                        hyd_tools_enabled=True, hyd_tools_input_root=tmp_path, data_dir=tmp_path)
    client = TestClient(create_app(settings))
    path = "/hydra/v1/hyd-tools/contract"
    assert client.get(path).status_code == 401
    assert client.get(path, headers={"X-API-Key": "api-test"}).status_code == 403
    headers = {"X-API-Key": "api-test", "X-Hydra-Admin-Token": "admin-test"}
    assert client.get(path, headers=headers).json() == contract()
    assert client.get("/hydra/v1/hyd-tools/jobs/not-a-uuid", headers=headers).status_code == 409
    settings.require_shared_state = True
    with pytest.raises(ValueError, match="single-node"):
        create_app(settings)


def standalone_fixture(tmp_path, qualified=False):
    pytest.importorskip("hyd_calibrator")
    from hyd_calibrator.evaluation import implementation_sha256
    model = CandidateRanker()
    model.training = {"criteria": CRITERIA}
    model.weights = np.random.default_rng(7).normal(size=model.weights.shape)
    source = tmp_path / "standalone"
    source.mkdir()
    model.save(source / "model.json")
    cal = {"format": "hyd-standalone-calibration/1", "model_sha256": model.revision,
           "temperature": 1, "criteria": CRITERIA, "min_confidence": .5, "min_margin": .1,
           "dataset_sha256": "0"*64, "calibrator_implementation_sha256": implementation_sha256(),
           "target_met": qualified, "abstain_all": not qualified, "train_overlap_checked": True,
           "target_wilson_lower_95": .95, "minimum_coverage": .1,
           "selected": {"min_confidence": .5, "min_margin": .1, "accuracy_wilson_lower_95": .96, "coverage": .5}}
    (source / "calibration.json").write_text(json.dumps(cal))
    return source


def test_real_standalone_numerical_parity_and_deadline(tmp_path):
    source = standalone_fixture(tmp_path)
    from hyd_calibrator.model import CandidateRanker as ExternalRanker
    external = ExternalRanker.load(source / "model.json")
    adapter = RoutingAdapter(source)
    for text in ("hola", "Escribe Python", "elimina os datos", "¿Falta contexto?"):
        answer = adapter.decide(text)
        assert answer["probabilities"] == external.probabilities(text, None, CRITERIA)
        assert answer["abstained"] and not answer["authority_enabled"]
    with pytest.raises(TimeoutError):
        adapter.decide("hola", deadline=time.monotonic()-1)
    with pytest.raises(ValueError, match="qualified"):
        export_runtime(source, tmp_path / "native")


def test_export_loads_original_controller_without_authority(tmp_path):
    source = standalone_fixture(tmp_path, qualified=True)
    result = export_runtime(source, tmp_path / "native")
    from hydra.hyd.controller import HydController
    controller = HydController(tmp_path / "native/model.json", tmp_path / "native/calibration.json")
    adapter = RoutingAdapter(source)
    answer = controller.engine.decide("hola", {"task": {"type": "choice", "criteria": CRITERIA}})["answers"]["task"]
    assert answer["probabilities"] == adapter.decide("hola")["probabilities"]
    assert not controller.authority.enabled and not result["activated"]
