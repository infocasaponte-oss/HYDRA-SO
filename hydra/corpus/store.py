# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""Corpus store: append-only versioned log, lineage graph, tombstones and snapshots.

    corpus/
    ├── log.jsonl          every record version (latest wins; nothing is rewritten)
    ├── lineage.jsonl      parent -> child edges (record -> dataset -> training run -> model -> artifact)
    ├── tombstones.jsonl   excluded records + impact analysis
    ├── snapshots.jsonl    Corpus Time Machine (log offset + content hash)
    ├── curated/           partitioned export  year=/month=/domain=  (Parquet if pyarrow, else JSONL)
    └── releases/          frozen dataset releases (never "latest")
"""

from __future__ import annotations

import json
import threading
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel, Field

from hydra.core.hashing import hash_obj, now_iso
from hydra.corpus.dedup import ContaminationGuard, Deduplicator
from hydra.corpus.gates import CorpusCurator, GateDecision
from hydra.corpus.records import CorpusRecord, LineageEdge, Tombstone, TrainingStatus


class CorpusSnapshot(BaseModel):
    id: str
    created_at: str = Field(default_factory=now_iso)
    log_offset: int
    records: int
    content_hash: str
    parent: str | None = None


class CorpusStore:
    def __init__(self, root: Path, curator: CorpusCurator | None = None, ledger=None) -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        (root / "releases").mkdir(exist_ok=True)
        self.log_path = root / "log.jsonl"
        self.lineage_path = root / "lineage.jsonl"
        self.tomb_path = root / "tombstones.jsonl"
        self.snap_path = root / "snapshots.jsonl"
        self.ledger = ledger
        self._lock = threading.RLock()
        self.records: dict[str, CorpusRecord] = {}
        self.offset = 0
        self.edges: list[LineageEdge] = []
        self.tombstones: dict[str, Tombstone] = {}
        self.dedup = curator.dedup if curator and curator.dedup else Deduplicator()
        self.curator = curator or CorpusCurator(dedup=self.dedup)
        if self.curator.dedup is None:
            self.curator.dedup = self.dedup
        for line in self._lines(self.log_path):
            rec = CorpusRecord.model_validate_json(line)
            self.records[rec.id] = rec
            self.offset += 1
        for rec in self.records.values():
            if rec.training_status in (TrainingStatus.CURATED, TrainingStatus.GOLD):
                self.dedup.add(rec)
        self.edges = [LineageEdge.model_validate_json(x) for x in self._lines(self.lineage_path)]
        for x in self._lines(self.tomb_path):
            t = Tombstone.model_validate_json(x)
            self.tombstones[t.record_id] = t

    @staticmethod
    def _lines(path: Path) -> Iterable[str]:
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    yield line

    def _append(self, path: Path, model: BaseModel) -> None:
        with open(path, "a", encoding="utf-8") as f:
            f.write(model.model_dump_json() + "\n")

    def set_contamination(self, guard: ContaminationGuard) -> None:
        self.curator.contamination = guard

    # ------------------------------------------------------------------ write
    def _write(self, rec: CorpusRecord) -> CorpusRecord:
        with self._lock:
            self._append(self.log_path, rec)
            self.records[rec.id] = rec
            self.offset += 1
        return rec

    def ingest(self, rec: CorpusRecord, curate: bool = True) -> tuple[CorpusRecord, GateDecision | None]:
        """incoming -> QUARANTINE -> gates -> CURATED/GOLD/BLOCKED/DUPLICATE."""
        decision = None
        if rec.id in self.tombstones:
            rec.training_status = TrainingStatus.TOMBSTONED
            return rec, None
        rec.training_status = TrainingStatus.QUARANTINED
        if curate:
            decision = self.curator.curate(rec)
            rec.training_status = decision.status
            rec.metadata["gate_reasons"] = decision.reasons
            if decision.status in (TrainingStatus.CURATED, TrainingStatus.GOLD):
                self.dedup.add(rec)
        self._write(rec)
        if self.ledger is not None and rec.training_status in (TrainingStatus.CURATED, TrainingStatus.GOLD):
            self.ledger.append("CORPUS_RECORD_CREATED", {
                "record_id": rec.id, "type": rec.record_type.value, "status": rec.training_status.value,
                "source": rec.source_type, "task": rec.source_task_id, "rights": rec.rights.model_dump(),
                "privacy": rec.privacy.action, "hash": rec.hashes.get("exact"),
                "parents": rec.provenance.get("parent_records", [])},
                object_type="corpus_record", object_id=rec.id)
        for parent in rec.provenance.get("parent_records", []):
            self.add_lineage(parent, rec.id, rec.provenance.get("transformation", "derived"))
        return rec, decision

    def review(self, record_id: str, approve: bool, reviewer: str, training_allowed: bool | None = None
               ) -> CorpusRecord:
        rec = self.records[record_id].model_copy(deep=True)
        if training_allowed is not None:
            rec.rights.training_allowed = training_allowed
        rec.metadata.setdefault("reviews", []).append({"by": reviewer, "approve": approve, "at": now_iso()})
        rec.metadata["human_reviewed"] = approve
        if approve:
            rec.training_status = TrainingStatus.GOLD if rec.quality > 0.92 else TrainingStatus.CURATED
            self.dedup.add(rec)
        else:
            rec.training_status = TrainingStatus.BLOCKED
        return self._write(rec)

    def add_lineage(self, parent: str, child: str, transformation: str) -> LineageEdge:
        e = LineageEdge(parent_id=parent, child_id=child, transformation=transformation)
        with self._lock:
            self._append(self.lineage_path, e)
            self.edges.append(e)
        return e

    # ------------------------------------------------------------------ lineage / impact
    def descendants(self, node: str) -> list[LineageEdge]:
        out, frontier, seen = [], [node], {node}
        while frontier:
            cur = frontier.pop()
            for e in self.edges:
                if e.parent_id == cur and e.child_id not in seen:
                    seen.add(e.child_id)
                    out.append(e)
                    frontier.append(e.child_id)
        return out

    def ancestors(self, node: str) -> list[LineageEdge]:
        out, frontier, seen = [], [node], {node}
        while frontier:
            cur = frontier.pop()
            for e in self.edges:
                if e.child_id == cur and e.parent_id not in seen:
                    seen.add(e.parent_id)
                    out.append(e)
                    frontier.append(e.parent_id)
        return out

    def tombstone(self, record_id: str, reason: str) -> Tombstone:
        """Exclude a record everywhere and report which datasets/models may have learned from it."""
        down = self.descendants(record_id)
        kinds: dict[str, list[str]] = {"dataset": [], "model": [], "artifact": []}
        for e in down:
            for k in kinds:
                if e.child_id.startswith(f"{k}:") or e.transformation.startswith(k):
                    kinds[k].append(e.child_id)
        t = Tombstone(record_id=record_id, reason=reason, affected_datasets=sorted(set(kinds["dataset"])),
                      affected_models=sorted(set(kinds["model"])), affected_artifacts=sorted(set(kinds["artifact"])))
        with self._lock:
            self._append(self.tomb_path, t)
            self.tombstones[record_id] = t
            if record_id in self.records:
                rec = self.records[record_id].model_copy(deep=True)
                rec.training_status = TrainingStatus.TOMBSTONED
                self._write(rec)
        if self.ledger is not None:
            self.ledger.append("CORPUS_RECORD_TOMBSTONED", t.model_dump(), object_type="corpus_record",
                               object_id=record_id)
        return t

    # ------------------------------------------------------------------ read
    def get(self, record_id: str) -> CorpusRecord | None:
        return self.records.get(record_id)

    def search(self, *, record_type: str | list[str] | None = None, domain: str | None = None,
               language: str | None = None, capability: str | None = None, min_quality: float = 0.0,
               min_verification: float = 0.0, statuses: set[str] | None = None, text: str | None = None,
               tenant_id: str | None = None, synthetic: bool | None = None, flag: str | None = None,
               task_id: str | None = None, limit: int | None = None) -> list[CorpusRecord]:
        types = {record_type} if isinstance(record_type, str) else set(record_type or [])
        out = []
        for r in self.records.values():
            if types and r.record_type.value not in types:
                continue
            if domain and domain not in r.domain:
                continue
            if language and r.language != language:
                continue
            if capability and not any(c == capability or c.startswith(capability + ".") for c in r.capabilities):
                continue
            if r.quality < min_quality or r.verification < min_verification:
                continue
            if statuses and r.training_status.value not in statuses:
                continue
            if tenant_id is not None and r.tenant_id != tenant_id:
                continue
            if synthetic is not None and r.synthetic != synthetic:
                continue
            if flag and flag not in r.flags:
                continue
            if task_id and r.source_task_id != task_id:
                continue
            if text and text.lower() not in r.text().lower():
                continue
            out.append(r)
            if limit and len(out) >= limit:
                break
        return out

    def trainable(self) -> list[CorpusRecord]:
        return [r for r in self.records.values() if r.trainable and r.id not in self.tombstones]

    # ------------------------------------------------------------------ snapshots
    def snapshot(self) -> CorpusSnapshot:
        with self._lock:
            state = sorted((r.id, r.training_status.value) for r in self.records.values())
            snaps = list(self._lines(self.snap_path))
            parent = CorpusSnapshot.model_validate_json(snaps[-1]).id if snaps else None
            s = CorpusSnapshot(id=f"hc-{datetime.now().strftime('%Y.%m.%d')}-{len(snaps) + 1}", log_offset=self.offset,
                               records=len(self.records), content_hash=hash_obj(state), parent=parent)
            self._append(self.snap_path, s)
        return s

    def snapshots(self) -> list[CorpusSnapshot]:
        return [CorpusSnapshot.model_validate_json(x) for x in self._lines(self.snap_path)]

    def at_snapshot(self, snapshot_id: str) -> dict[str, CorpusRecord]:
        snap = next(s for s in self.snapshots() if s.id == snapshot_id)
        state: dict[str, CorpusRecord] = {}
        for i, line in enumerate(self._lines(self.log_path)):
            if i >= snap.log_offset:
                break
            rec = CorpusRecord.model_validate_json(line)
            state[rec.id] = rec
        return state

    # ------------------------------------------------------------------ export
    def export_partitioned(self, statuses: set[str] | None = None) -> dict[str, Any]:
        """curated/year=YYYY/month=MM/domain=D/part.{parquet|jsonl}"""
        statuses = statuses or {"CURATED", "GOLD"}
        groups: dict[tuple, list[dict]] = {}
        for r in self.records.values():
            if r.training_status.value not in statuses or r.id in self.tombstones:
                continue
            y, m = r.created_at[:4], r.created_at[5:7]
            d = (r.domain or ["general"])[0]
            groups.setdefault((y, m, d), []).append(r.model_dump(mode="json"))
        written = []
        for (y, m, d), rows in groups.items():
            folder = self.root / "curated" / f"year={y}" / f"month={m}" / f"domain={d}"
            folder.mkdir(parents=True, exist_ok=True)
            written.append(str(write_table(folder / "part", rows)))
        return {"partitions": len(groups), "files": written}

    def stats(self) -> dict[str, Any]:
        recs = list(self.records.values())
        status = Counter(r.training_status.value for r in recs)
        tiers = Counter(r.tier.value for r in recs)
        langs = Counter(r.language or "unknown" for r in recs)
        domains = Counter(d for r in recs for d in (r.domain or ["general"]))
        types = Counter(r.record_type.value for r in recs)
        total = len(recs) or 1
        return {
            "records": len(recs), "status": dict(status), "tiers": dict(tiers),
            "record_types": dict(types),
            "languages": {k: round(v / total, 3) for k, v in langs.most_common()},
            "domains": {k: round(v / total, 3) for k, v in domains.most_common()},
            "synthetic_fraction": round(sum(r.synthetic for r in recs) / total, 3),
            "duplicates_removed": status.get("DUPLICATE", 0),
            "privacy_rejected": sum(1 for r in recs if r.privacy.action == "REJECT"),
            "pseudonymized": sum(1 for r in recs if r.privacy.action == "PSEUDONYMIZE"),
            "tombstones": len(self.tombstones), "lineage_edges": len(self.edges),
            "trainable": len(self.trainable()),
            "hard": sum("hard" in r.flags for r in recs), "frontier": sum("frontier" in r.flags for r in recs),
        }


def write_table(stem: Path, rows: list[dict]) -> Path:
    """Parquet when pyarrow is installed (columnar source of truth), otherwise JSONL."""
    try:
        import pyarrow as pa  # type: ignore
        import pyarrow.parquet as pq  # type: ignore

        table = pa.Table.from_pylist([{k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v
                                       for k, v in r.items()} for r in rows])
        path = stem.with_suffix(".parquet")
        pq.write_table(table, path)
        return path
    except ImportError:
        path = stem.with_suffix(".jsonl")
        with open(path, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
        return path
