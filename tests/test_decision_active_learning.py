# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
import json

import pytest

from hydra.training import decision_active_learning as al


def _write(path, rows):
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    return path


def _train(tmp_path):
    rows = [{"text": t, "expected": y, "training_allowed": True} for t, y in [
        ("Escribe una función en Python", "coding"), ("Corrige este error de JavaScript", "coding"),
        ("Hola, ¿qué tal?", "chat"), ("Cuéntame un chiste", "chat"),
        ("Borra la base de producción", "high_risk_review"), ("Autoriza un pago irreversible", "high_risk_review")]]
    return _write(tmp_path / "train.jsonl", rows)


def test_priority_never_reads_labels_and_lifts_hidden_safety_mass():
    calm = {"chat": 0.5, "coding": 0.45, "high_risk_review": 0.05}
    risky = {"chat": 0.5, "coding": 0.3, "high_risk_review": 0.2}
    assert al.priority(risky, "safety_margin") > al.priority(calm, "safety_margin")
    assert al.priority(calm, "margin") > al.priority({"chat": 0.9, "coding": 0.1}, "margin")
    with pytest.raises(ValueError):
        al.priority(calm, "oracle")


def test_simulation_chooses_on_calibration_and_rejects_test_leak(tmp_path):
    train = _train(tmp_path)
    pool = _write(tmp_path / "pool.jsonl", [{"text": t, "expected": y, "training_allowed": True} for t, y in [
        ("Implementa una cola en Go", "coding"), ("Buenos días, amigo", "chat"),
        ("Elimina el repositorio principal", "high_risk_review"), ("Saluda con cariño", "chat")]])
    cal = _write(tmp_path / "cal.jsonl", [{"input": {"query": "Programa un bucle en Rust"},
                                           "output": {"task_type": "coding"}}])
    test = _write(tmp_path / "test.jsonl", [{"input": {"query": "Apaga los servidores ya"},
                                             "output": {"task_type": "high_risk_review"}}])
    result = al.simulate([train], [pool], cal, test, rounds=1, batch=2, seeds=1)
    assert result["chosen_strategy"] in al.STRATEGIES and result["selection_split"] == "calibration"
    leak = _write(tmp_path / "leak.jsonl", [{"input": {"query": "Buenos días, amigo"}, "output": {"task_type": "chat"}}])
    with pytest.raises(ValueError, match="overlap"):
        al.simulate([train], [pool], cal, leak, rounds=1, batch=2, seeds=1)


def test_queue_quarantines_personal_data_and_only_humans_create_labels(tmp_path):
    train = _train(tmp_path)
    pool = _write(tmp_path / "pool.jsonl", [{"text": "Hola, ¿qué tal?"},  # already in training
                                            {"text": "Mi correo es ana@example.com, ¿lo guardas?"},
                                            {"text": "Despliega sin revisión en producción"},
                                            {"text": "Escribe un test unitario"}])
    queue = tmp_path / "round-001"
    manifest = al.make_queue([train], pool, queue, strategy="safety_margin", k=5)
    assert manifest["privacy_quarantined"] == 1 and manifest["queued"] == 2
    rows = al.read_rows(queue / "queue.jsonl")
    assert all(r["human_label"] is None for r in rows) and "ana@example.com" not in (queue / "queue.jsonl").read_text()
    with pytest.raises(ValueError, match="no human-labelled"):
        al.admit(queue, tmp_path / "admitted.jsonl")
    rows[0].update(human_label="high_risk_review", reviewer="LM")
    rows[1].update(human_label="coding")  # no reviewer: stays out
    _write(queue / "queue.jsonl", rows)
    report = al.admit(queue, tmp_path / "admitted.jsonl")
    assert report["admitted"] == 1 and report["skipped"]["no_reviewer"] == 1
    assert al.admitted([tmp_path / "admitted.jsonl"])[0][1] == "high_risk_review"
    with pytest.raises(FileExistsError):
        al.make_queue([train], pool, queue, strategy="margin")
