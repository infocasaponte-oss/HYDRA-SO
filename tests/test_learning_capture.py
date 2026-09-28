from uuid import uuid4

from hydra.artifacts import ArtifactStore
from hydra.beliefs import BeliefStatus, BeliefStore
from hydra.corpus import CorpusStatus, CorpusStore, RightsDeclaration
from hydra.learning_capture import LearningCapture


def test_verified_experience_is_quarantined_by_default(tmp_path):
    task_id = uuid4()
    artifacts = ArtifactStore(tmp_path / "artifacts")
    artifact = artifacts.put_text(task_id=task_id, kind="tests-after", text="1 passed")
    capture = LearningCapture(
        beliefs=BeliefStore(tmp_path / "beliefs.jsonl"),
        corpus=CorpusStore(tmp_path / "corpus.jsonl"),
    )
    belief, record = capture.capture_verified_patch(task_id=task_id, artifacts=[artifact])
    assert belief.status == BeliefStatus.VERIFIED
    assert record.status == CorpusStatus.QUARANTINED


def test_training_requires_all_rights_gates(tmp_path):
    task_id = uuid4()
    artifact = ArtifactStore(tmp_path / "artifacts").put_text(
        task_id=task_id, kind="patch", text="diff"
    )
    capture = LearningCapture(
        beliefs=BeliefStore(tmp_path / "beliefs.jsonl"),
        corpus=CorpusStore(tmp_path / "corpus.jsonl"),
    )
    _, record = capture.capture_verified_patch(
        task_id=task_id,
        artifacts=[artifact],
        rights=RightsDeclaration(
            rights_confirmed=True,
            privacy_reviewed=True,
            training_allowed=True,
            source_license="internal-approved",
        ),
    )
    assert record.status == CorpusStatus.CURATED
    assert len(record.content_hash) == 64
