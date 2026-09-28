from __future__ import annotations

from uuid import UUID

from hydra.artifacts import ArtifactRecord
from hydra.beliefs import Belief, BeliefStatus, BeliefStore, EvidenceRef
from hydra.corpus import CorpusGate, CorpusRecord, CorpusStore, RightsDeclaration


class LearningCapture:
    def __init__(
        self,
        beliefs: BeliefStore | None = None,
        corpus: CorpusStore | None = None,
        gate: CorpusGate | None = None,
    ):
        self.beliefs = beliefs or BeliefStore()
        self.corpus = corpus or CorpusStore()
        self.gate = gate or CorpusGate()

    def capture_verified_patch(
        self,
        *,
        task_id: UUID,
        artifacts: list[ArtifactRecord],
        rights: RightsDeclaration | None = None,
    ) -> tuple[Belief, CorpusRecord]:
        evidence = [
            EvidenceRef(artifact_id=a.artifact_id, sha256=a.sha256, kind=a.kind)
            for a in artifacts
        ]
        belief = self.beliefs.append(
            Belief(
                task_id=task_id,
                claim="Candidate patch passed the configured verification tests.",
                status=BeliefStatus.VERIFIED,
                evidence=evidence,
                verifier="hydra.oci.pytest",
            )
        )
        record = CorpusRecord(
            task_id=task_id,
            belief_id=belief.belief_id,
            artifact_hashes=[a.sha256 for a in artifacts],
            rights=rights or RightsDeclaration(),
        )
        return belief, self.corpus.append(self.gate.evaluate(record))
