from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from hydra.hash_chain import canonical_hash, lock_for


class ProvenanceRecord(BaseModel):
    record_id: UUID = Field(default_factory=uuid4)
    task_id: UUID
    trace_id: str
    action: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    inputs: dict = Field(default_factory=dict)
    outputs: dict = Field(default_factory=dict)
    previous_hash: str | None = None
    record_hash: str = ""


class ProvenanceIntegrity(BaseModel):
    valid: bool
    records: int
    legacy_records: int = 0
    error: str | None = None


def _record_body(record: ProvenanceRecord) -> dict:
    return record.model_dump(mode="json", exclude={"record_hash"})


class ProvenanceLedger:
    def __init__(self, path: str | Path = "runtime/provenance.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = lock_for(self.path)
        self._last_hash = self._load_last_hash()

    def _load_last_hash(self) -> str | None:
        if not self.path.exists():
            return None
        last_hash = None
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                record = ProvenanceRecord.model_validate_json(line)
                last_hash = record.record_hash or last_hash
        return last_hash

    def append(self, record: ProvenanceRecord) -> ProvenanceRecord:
        with self._lock:
            record.previous_hash = self._last_hash
            record.record_hash = canonical_hash(_record_body(record))
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(record.model_dump_json() + "\n")
                handle.flush()
            self._last_hash = record.record_hash
            return record

    def verify_integrity(self) -> ProvenanceIntegrity:
        if not self.path.exists():
            return ProvenanceIntegrity(valid=True, records=0)
        previous_hash = None
        records = 0
        legacy = 0
        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    record = ProvenanceRecord.model_validate_json(line)
                except Exception as exc:  # noqa: BLE001
                    return ProvenanceIntegrity(
                        valid=False,
                        records=records,
                        legacy_records=legacy,
                        error=f"line {line_number}: invalid record: {exc}",
                    )
                records += 1
                if not record.record_hash:
                    legacy += 1
                    previous_hash = None
                    continue
                if record.previous_hash != previous_hash:
                    return ProvenanceIntegrity(
                        valid=False,
                        records=records,
                        legacy_records=legacy,
                        error=f"line {line_number}: previous hash mismatch",
                    )
                if canonical_hash(_record_body(record)) != record.record_hash:
                    return ProvenanceIntegrity(
                        valid=False,
                        records=records,
                        legacy_records=legacy,
                        error=f"line {line_number}: record hash mismatch",
                    )
                previous_hash = record.record_hash
        return ProvenanceIntegrity(
            valid=True,
            records=records,
            legacy_records=legacy,
        )
