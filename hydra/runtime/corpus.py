# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from hydra.runtime.privacy import PrivacyScanResult, PrivacyScanStatus


class CorpusStatus(StrEnum):
    QUARANTINED = "quarantined"
    CURATED = "curated"
    BLOCKED = "blocked"
    TOMBSTONED = "tombstoned"


class QualityTier(StrEnum):
    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"
    PLATINUM = "platinum"


class RightsDeclaration(BaseModel):
    rights_confirmed: bool = False
    privacy_reviewed: bool = False
    training_allowed: bool = False
    source_license: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)


class CorpusRecord(BaseModel):
    record_id: UUID = Field(default_factory=uuid4)
    task_id: UUID
    belief_id: UUID
    artifact_hashes: list[str]
    status: CorpusStatus = CorpusStatus.QUARANTINED
    quality_tier: QualityTier = QualityTier.BRONZE
    rights: RightsDeclaration = Field(default_factory=RightsDeclaration)
    privacy_scan: PrivacyScanResult = Field(default_factory=PrivacyScanResult)
    content_hash: str = ""


class CorpusGate:
    def evaluate(self, record: CorpusRecord) -> CorpusRecord:
        rights_evidence = bool(
            record.rights.source_license or record.rights.evidence_refs
        )
        allowed = (
            record.rights.rights_confirmed
            and record.rights.privacy_reviewed
            and record.rights.training_allowed
            and rights_evidence
            and record.privacy_scan.status == PrivacyScanStatus.CLEAR
        )
        if record.privacy_scan.status == PrivacyScanStatus.FLAGGED:
            record.status = CorpusStatus.BLOCKED
        else:
            record.status = (
                CorpusStatus.CURATED
                if allowed
                else CorpusStatus.QUARANTINED
            )
        body = {
            "task_id": str(record.task_id),
            "belief_id": str(record.belief_id),
            "artifact_hashes": sorted(record.artifact_hashes),
            "status": record.status.value,
            "quality_tier": record.quality_tier.value,
            "rights": record.rights.model_dump(),
            "privacy_scan": record.privacy_scan.model_dump(mode="json"),
        }
        record.content_hash = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return record


class CorpusIndex:
    """In-memory exact-dedup index suitable for ingestion gates."""

    def __init__(self) -> None:
        self._hashes: set[str] = set()

    def accept(self, record: CorpusRecord) -> bool:
        if not record.content_hash:
            raise ValueError("Corpus record must be hashed before deduplication")
        if record.content_hash in self._hashes:
            return False
        self._hashes.add(record.content_hash)
        return True


class CorpusStore:
    def __init__(self, path: str | Path = "runtime/corpus.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: CorpusRecord) -> CorpusRecord:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(record.model_dump_json() + "\n")
        return record

    def contains_hash(self, content_hash: str) -> bool:
        if not self.path.exists():
            return False
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                existing = CorpusRecord.model_validate_json(line)
                if existing.content_hash == content_hash:
                    return True
        return False

    def append_once(self, record: CorpusRecord) -> bool:
        if not record.content_hash:
            raise ValueError("Corpus record must have content_hash")
        if self.contains_hash(record.content_hash):
            return False
        self.append(record)
        return True
