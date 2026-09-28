from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ProvenanceRecord(BaseModel):
    record_id: UUID = Field(default_factory=uuid4)
    task_id: UUID
    trace_id: str
    action: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    inputs: dict = Field(default_factory=dict)
    outputs: dict = Field(default_factory=dict)
    record_hash: str = ""


class ProvenanceLedger:
    def __init__(self, path: str | Path = "runtime/provenance.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: ProvenanceRecord) -> ProvenanceRecord:
        body = record.model_dump(mode="json", exclude={"record_hash"})
        raw = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        record.record_hash = hashlib.sha256(raw).hexdigest()
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(record.model_dump_json() + "\n")
        return record
