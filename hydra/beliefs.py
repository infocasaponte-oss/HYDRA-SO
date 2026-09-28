from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class BeliefStatus(StrEnum):
    HYPOTHESIS = "hypothesis"
    SUPPORTED = "supported"
    VERIFIED = "verified"
    CONTESTED = "contested"
    REJECTED = "rejected"
    OBSOLETE = "obsolete"


class EvidenceRef(BaseModel):
    artifact_id: UUID
    sha256: str
    kind: str


class Belief(BaseModel):
    belief_id: UUID = Field(default_factory=uuid4)
    task_id: UUID
    claim: str
    status: BeliefStatus
    evidence: list[EvidenceRef] = Field(default_factory=list)
    verifier: str


class BeliefStore:
    def __init__(self, path: str | Path = "runtime/beliefs.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, belief: Belief) -> Belief:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(belief.model_dump_json() + "\n")
        return belief
