# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""HYDRA EDGE sync: signed deltas between an edge node and the central deployment.

    edge -> signed delta (world changes, approved corpus records, model manifests, ledger digest) -> central

Never syncs memories or sensitive corpus indiscriminately: only CURATED/GOLD records whose
classification is PUBLIC/INTERNAL and that allow it. Conflicts are resolved by lineage and
versioning (content hash + training status precedence), never "last write wins"."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from hydra.core.hashing import canonical_json, now_iso, sha256_hex
from hydra.ledger.signing import verify_envelope

STATUS_RANK = {"RAW": 0, "QUARANTINED": 1, "REVIEW": 2, "CURATED": 3, "GOLD": 4, "BLOCKED": 5, "TOMBSTONED": 6}


class SyncCursor(BaseModel):
    world_version: int = 0
    corpus_offset: int = 0
    ledger_sequence: int = 0


class SyncBundle(BaseModel):
    origin: str
    created_at: str = Field(default_factory=now_iso)
    cursor_from: SyncCursor
    cursor_to: SyncCursor
    world_deltas: list[dict[str, Any]] = Field(default_factory=list)
    corpus_records: list[dict[str, Any]] = Field(default_factory=list)
    model_manifests: list[dict[str, Any]] = Field(default_factory=list)
    ledger_digest: dict[str, Any] = Field(default_factory=dict)
    signature: dict[str, Any] | None = None

    def digest(self) -> str:
        return sha256_hex(canonical_json(self.model_dump(exclude={"signature"})))


def export_delta(runtime, since: SyncCursor, origin: str) -> SyncBundle:
    world_deltas = []
    log = runtime.world.root / "deltas.jsonl" if runtime.world.root else None
    if log and log.exists():
        lines = [x for x in log.read_text(encoding="utf-8").splitlines() if x.strip()]
        world_deltas = [json.loads(x) for x in lines[since.world_version:]]
    corpus = []
    lines = [x for x in runtime.corpus.log_path.read_text(encoding="utf-8").splitlines() if x.strip()] \
        if runtime.corpus.log_path.exists() else []
    for line in lines[since.corpus_offset:]:
        r = json.loads(line)
        if r.get("training_status") in ("CURATED", "GOLD") and r.get("classification") in ("PUBLIC", "INTERNAL"):
            corpus.append(r)
    manifests = []
    if runtime.factory is not None:
        manifests = [v.model_dump(mode="json") for v in runtime.factory.store.variants.values()]
    events = list(runtime.ledger.events())
    head = events[-1] if events else None
    b = SyncBundle(origin=origin, cursor_from=since,
                   cursor_to=SyncCursor(world_version=runtime.world.version, corpus_offset=len(lines),
                                        ledger_sequence=len(runtime.ledger)),
                   world_deltas=world_deltas, corpus_records=corpus, model_manifests=manifests,
                   ledger_digest={"sequence": head.sequence if head else 0, "head": head.event_hash if head else None})
    b.signature = runtime.signer.envelope(b.digest())
    return b


class ImportReport(BaseModel):
    ok: bool
    reason: str = ""
    world_deltas_applied: int = 0
    corpus_added: int = 0
    corpus_conflicts: list[str] = Field(default_factory=list)
    manifests: int = 0


def import_delta(runtime, bundle: SyncBundle, trusted_keys: set[str]) -> ImportReport:
    if bundle.signature is None or bundle.signature.get("digest") != bundle.digest() \
            or not verify_envelope(bundle.signature, trusted_keys):
        return ImportReport(ok=False, reason="invalid or untrusted signature")
    from hydra.corpus.records import CorpusRecord
    from hydra.world.model import KnowledgeDelta

    rep = ImportReport(ok=True)
    seen_path = runtime.settings.data_dir / "edge" / "applied_deltas.json"
    seen: set[str] = set(json.loads(seen_path.read_text())) if seen_path.exists() else set()
    for d in bundle.world_deltas:
        h = sha256_hex(canonical_json(d))
        if h in seen:
            continue
        runtime.world.apply(KnowledgeDelta.model_validate(d))
        seen.add(h)
        rep.world_deltas_applied += 1
    seen_path.parent.mkdir(parents=True, exist_ok=True)
    seen_path.write_text(json.dumps(sorted(seen)))
    for r in bundle.corpus_records:
        rec = CorpusRecord.model_validate(r)
        rec.residency = rec.residency or bundle.origin
        existing = runtime.corpus.get(rec.id)
        if existing is not None:
            same = existing.hashes.get("exact") == rec.hashes.get("exact")
            if not same:
                rep.corpus_conflicts.append(rec.id)
                rec.id = f"{rec.id}@{bundle.origin}"  # keep both, linked by lineage
                rec.provenance["conflicts_with"] = existing.id
            elif STATUS_RANK.get(existing.training_status.value, 0) >= STATUS_RANK.get(rec.training_status.value, 0):
                continue
        rec.provenance["synced_from"] = bundle.origin
        runtime.corpus.ingest(rec, curate=True)
        rep.corpus_added += 1
    rep.manifests = len(bundle.model_manifests)
    runtime.ledger.append("CONFIG_CHANGED", {"edge_sync_from": bundle.origin, "digest": bundle.digest(),
                                             "world_deltas": rep.world_deltas_applied, "corpus": rep.corpus_added,
                                             "conflicts": rep.corpus_conflicts, "remote_ledger": bundle.ledger_digest},
                          object_type="edge_sync", object_id=bundle.origin)
    return rep


def save_bundle(b: SyncBundle, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(b.model_dump_json(), encoding="utf-8")
    return path
