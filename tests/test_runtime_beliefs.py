# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
from uuid import uuid4

from fastapi.testclient import TestClient

from hydra.api.main import create_app
from hydra.runtime import api as runtime_api
from hydra.runtime.beliefs import Belief, BeliefStatus, EvidenceRef
from hydra.world.model import BeliefStatus as WorldStatus
from hydra.world.runtime_beliefs import WorldBeliefStore


def _verified_patch() -> Belief:
    return Belief(task_id=uuid4(), claim="Candidate patch passed the configured HYDRA verification policy.",
                  status=BeliefStatus.VERIFIED, verifier="hydra.code.verification.v2",
                  evidence=[EvidenceRef(artifact_id=uuid4(), sha256="ab" * 32, kind="patch")])


async def test_runtime_belief_is_recorded_in_world_model_and_jsonl(runtime, tmp_path):
    store = WorldBeliefStore(runtime.world, tmp_path / "beliefs.jsonl")
    version = runtime.world.version
    belief = store.append(_verified_patch())
    assert runtime.world.version > version
    recorded = [b for b in runtime.world.beliefs.values() if b.predicate == "verification"
                and b.subject_id and str(belief.task_id) in b.subject_id]
    assert recorded and recorded[0].status == WorldStatus.VERIFIED
    evidence = [runtime.world.evidence[e] for e in recorded[0].supporting_evidence]
    assert evidence[0].evidence_type.value == "UNIT_TEST" and evidence[0].source_id == "ab" * 32
    assert str(belief.belief_id) in (tmp_path / "beliefs.jsonl").read_text(encoding="utf-8")


def test_gateway_routes_runtime_beliefs_to_its_world_model(settings):
    original = runtime_api.learning.beliefs
    app = create_app(settings)
    with TestClient(app):
        store = runtime_api.learning.beliefs
        assert isinstance(store, WorldBeliefStore) and store.world is app.state.runtime.world
    assert runtime_api.learning.beliefs is original
