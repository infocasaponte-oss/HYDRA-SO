# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
import hashlib
import json

import numpy as np
import pytest

from hydra.hyd import probes
from hydra.hyd import route_corpus_v5 as v5
from hydra.hyd.embedding import EmbeddingRanker, fit_head
from hydra.router.decision_contract import CRITERIA

LABELS = list(CRITERIA)


class FakeEncoder:
    """Deterministic bag-of-hashed-words embedding: enough to exercise the head and the engine."""
    dims = 64

    def __init__(self):
        self.calls = 0

    def embed(self, texts, deadline=None):
        self.calls += 1
        out = np.zeros((len(texts), self.dims))
        for i, text in enumerate(texts):
            for word in text.lower().split():
                out[i, int(hashlib.sha256(word.encode()).hexdigest(), 16) % self.dims] += 1
        return out


def trained_head(encoder):
    texts = [f"{label} petición número {i}" for label in LABELS for i in range(6)]
    y = np.array([LABELS.index(t.split()[0]) for t in texts])
    x = encoder.embed(texts)
    mean, scale = x.mean(0), x.std(0) + 1e-6
    w, b = fit_head((x - mean) / scale, y, len(LABELS), 0.01)
    model = EmbeddingRanker(encoder, LABELS, mean, scale, w, b)
    model.training = {"criteria": CRITERIA}
    return model


def test_head_learns_saves_loads_and_refuses_unknown_option_sets(tmp_path):
    encoder = FakeEncoder()
    model = trained_head(encoder)
    p = model.probabilities("coding por favor", None, CRITERIA)
    assert max(p, key=p.get) == "coding" and abs(sum(p.values()) - 1) < 1e-9
    other = model.probabilities("lo que sea", None, {"a": "x", "b": "y"})
    assert other == {"a": 0.5, "b": 0.5}  # no opinion outside the trained label set
    spec = {"kind": "llamacpp-embeddings", "endpoint": "http://127.0.0.1:1", "model": "m", "dims": 64}
    model.save(tmp_path / "model.json", spec)
    loaded = EmbeddingRanker.load(tmp_path / "model.json", encoder=encoder)
    assert loaded.revision == model.revision and loaded.exclusive
    assert loaded.probabilities("coding por favor", None, CRITERIA) == pytest.approx(p)
    data = json.loads((tmp_path / "model.json").read_text(encoding="utf-8"))
    data["scale"][0] = 0
    (tmp_path / "bad.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        EmbeddingRanker.load(tmp_path / "bad.json", encoder=encoder)


def test_encoder_must_be_local():
    from hydra.hyd.embedding import LlamaCppEncoder
    with pytest.raises(ValueError):
        LlamaCppEncoder("https://example.org", "m", 8)


def test_controller_serves_embedding_head_with_one_slot(tmp_path, monkeypatch):
    from hydra.hyd import embedding
    from hydra.hyd.controller import HydController, implementation_digest
    encoder = FakeEncoder()
    model = trained_head(encoder)
    spec = {"kind": "llamacpp-embeddings", "endpoint": "http://127.0.0.1:1", "model": "m", "dims": 64}
    model.save(tmp_path / "model.json", spec)
    calibration = {"format": "hyd-calibration/1", "model_sha256": model.revision,
                   "implementation_sha256": implementation_digest(), "temperature": model.temperature,
                   "criteria": CRITERIA, "dataset_sha256": "x", "min_confidence": .5, "min_margin": .05}
    (tmp_path / "calibration.json").write_text(json.dumps(calibration), encoding="utf-8")
    monkeypatch.setattr(embedding, "encoder_from", lambda _spec: encoder)
    hyd = HydController(tmp_path / "model.json", tmp_path / "calibration.json")
    assert hyd._capacity == 1 and not hyd.authority.enabled
    answer = hyd.engine.decide("coding por favor", {"task": {"type": "choice", "criteria": CRITERIA}})["answers"]["task"]
    assert answer["choice"] == "coding" and answer["reason"] in ("accepted", "low_confidence")


def test_probes_keep_labels_and_negation_takes_the_wanted_request():
    rows = [{"text": f"petición de {label} número {i}", "expected": label} for label in LABELS for i in range(3)]
    built = probes.build(rows, LABELS, per_probe=20)
    assert set(built) == {"synonyms", "typos", "preamble", "shuffled_order", "negation"}
    for item in built["negation"]:
        assert item["text"].endswith(next(r["text"] for r in rows if r["text"] in item["text"].split("esto: ")[1]))
        assert item["expected"] in item["text"].split("esto: ")[1]


def test_corpus_v5_adds_capabilities_and_stays_decontaminated(tmp_path):
    test = tmp_path / "test.jsonl"
    test.write_text(json.dumps({"text": "a qué hora me dijiste que pasaba el último tren"}) + "\n", encoding="utf-8")
    manifest = v5.build(test, tmp_path / "out", seed=3, per_template=4)
    assert set(manifest["labels"]) == set(CRITERIA)
    assert {"preamble", "contrast"} <= set(manifest["augmentations"])
    rows = [json.loads(line) for line in (tmp_path / "out/corpus.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(r["template"].startswith("abs5") and r["expected"] == "abstain" for r in rows)
    assert any(r["template"] == "num5-money" and r["expected"] == "high_risk_review" for r in rows)
    train = {r["template"] for r in rows if r["split"] == "train"}
    dev = {r["template"] for r in rows if r["split"] == "dev"}
    assert not train & dev


def test_encoder_down_is_a_backend_failure():
    from hydra.hyd.embedding import LlamaCppEncoder
    encoder = LlamaCppEncoder("http://127.0.0.1:9", "m", 8, timeout_s=2)  # discard port: nothing listens
    with pytest.raises(RuntimeError, match="unavailable"):
        encoder.embed(["hola"])


@pytest.mark.parametrize("endpoint", ["http://localhost.attacker.example:80", "http://127.0.0.1@attacker.example:80",
                                      "https://127.0.0.1:18094", "http://127.0.0.1", "http://10.0.0.5:18094",
                                      "http://127.0.0.1:18094/v1?x=1"])
def test_encoder_endpoint_must_be_exactly_loopback(endpoint):
    from hydra.hyd.embedding import LlamaCppEncoder
    with pytest.raises(ValueError):
        LlamaCppEncoder(endpoint, "m", 8)
    assert LlamaCppEncoder("http://127.0.0.1:18094", "m", 8).endpoint == "http://127.0.0.1:18094"


def test_selective_metrics_apply_the_margin_rule():
    from hydra.hyd.train_embedding import selective_metrics
    rows = [{"expected": "a", "selected": "a", "probabilities": {"a": .5, "b": .45, "c": .05}},
            {"expected": "a", "selected": "a", "probabilities": {"a": .9, "b": .05, "c": .05}}]
    report = selective_metrics(rows, .3, .2)
    assert report["accepted"] == 1 and report["coverage"] == .5

async def test_stopped_encoder_falls_back_to_cpu_ranker_with_cooldown():
    from pathlib import Path

    from hydra.core.contracts import HydraRequest, Message
    from hydra.hyd.controller import HydController
    root = Path(__file__).resolve().parents[1]
    cpu = HydController(root / "config/hyd/model.json", root / "config/hyd/calibration.json")
    gpu = HydController(root / "config/hyd-embedding/model.json", root / "config/hyd-embedding/calibration.json",
                        fallback=cpu)
    gpu.engine.ranker.encoder.endpoint = "http://127.0.0.1:9"  # nothing listens here
    calls = []
    original = gpu._observe

    async def counting(request):
        calls.append(1)
        return await original(request)
    gpu._observe = counting
    request = HydraRequest(messages=[Message(role="user", content="Escribe una función que sume dos números")])
    first = await gpu.observe(request)
    assert first.status == "observed" and first.reason.startswith("hyd.fallback_cpu.")
    second = await gpu.observe(request)
    assert second.reason.startswith("hyd.fallback_cpu.") and len(calls) == 1  # primary skipped during cooldown
    assert not gpu.authority.enabled and not cpu.authority.enabled
    await gpu.close()
