# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""Disaster Recovery: a coherent snapshot is more than a database dump.

    backup  = data dir (ledger + anchors, corpus log, world deltas, artifact manifests + objects,
              model factory registry, lab, config sets, keys' PUBLIC parts) + PostgreSQL dump (optional)
    restore = restore files -> verify ledger chain -> verify object hashes -> rebuild registries
              -> health check -> resume traffic

Private keys are excluded unless explicitly requested. With ``include_private_keys`` and a
``KeyStore``, keys held outside the data directory (OS keyring, HYDRA_KEYS_DIR) are exported at their
legacy paths; after a restore, the next start migrates them back into the configured backend."""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import subprocess
import tarfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from hydra.core.hashing import now_iso, sha256_file

EXCLUDE_ALWAYS = {".tmp"}
PRIVATE_KEY_NAMES = {"hydra-ed25519.pem", ".vault.key", ".broker.key", "token.key"}


class BackupManifest(BaseModel):
    created_at: str = Field(default_factory=now_iso)
    source: str
    files: dict[str, str] = Field(default_factory=dict)
    postgres_dump: str | None = None
    ledger_head: str | None = None
    ledger_events: int = 0
    include_private_keys: bool = False


# Key name -> legacy path inside the data directory (hydra.core.keystore).
KEY_LEGACY_PATHS = {"ledger-ed25519": "keys/hydra-ed25519.pem", "secrets-broker": "secrets/.broker.key"}


def backup(data_dir: Path, out: Path, *, include_private_keys: bool = False, postgres_url: str | None = None,
           keystore=None) -> BackupManifest:
    out.parent.mkdir(parents=True, exist_ok=True)
    manifest = BackupManifest(source=str(data_dir), include_private_keys=include_private_keys)
    files = [p for p in data_dir.rglob("*") if p.is_file() and p.suffix not in EXCLUDE_ALWAYS
             and (include_private_keys or p.name not in PRIVATE_KEY_NAMES)]
    ledger = data_dir / "ledger" / "events.jsonl"
    if ledger.exists():
        lines = [x for x in ledger.read_text(encoding="utf-8").splitlines() if x.strip()]
        manifest.ledger_events = len(lines)
        manifest.ledger_head = json.loads(lines[-1]).get("event_hash") if lines else None
    dump_path = None
    if postgres_url:
        dump_path = out.with_suffix(".pgdump.sql")
        r = subprocess.run(["pg_dump", "--no-owner", postgres_url], capture_output=True, text=True, timeout=600)
        if r.returncode == 0:
            dump_path.write_text(r.stdout, encoding="utf-8")
            manifest.postgres_dump = dump_path.name
    for p in files:
        manifest.files[p.relative_to(data_dir).as_posix()] = sha256_file(p)
    exported: dict[str, bytes] = {}
    if include_private_keys and keystore is not None:
        for name, rel in KEY_LEGACY_PATHS.items():
            if rel in manifest.files:
                continue  # still a legacy file: already in the archive
            value = keystore.get(name, data_dir / rel)
            if value is not None:
                exported[rel] = value
                manifest.files[rel] = hashlib.sha256(value).hexdigest()
    with tarfile.open(out, "w:gz") as tar:
        for p in files:
            tar.add(p, arcname=f"data/{p.relative_to(data_dir).as_posix()}")
        for rel, value in exported.items():
            info = tarfile.TarInfo(f"data/{rel}")
            info.size, info.mode = len(value), 0o600
            tar.addfile(info, io.BytesIO(value))
        if dump_path is not None and dump_path.exists():
            tar.add(dump_path, arcname=dump_path.name)
        mp = out.with_suffix(".manifest.json")
        mp.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
        tar.add(mp, arcname="backup-manifest.json")
    return manifest


class RestoreReport(BaseModel):
    restored_files: int
    hash_mismatches: list[str] = Field(default_factory=list)
    ledger: dict[str, Any] = Field(default_factory=dict)
    artifacts: dict[str, Any] = Field(default_factory=dict)
    world_version: int | None = None
    corpus_records: int | None = None
    ok: bool = False


def restore(archive: Path, data_dir: Path, *, overwrite: bool = False) -> RestoreReport:
    if data_dir.exists() and any(data_dir.iterdir()) and not overwrite:
        raise FileExistsError(f"{data_dir} is not empty (use overwrite=True)")
    tmp = data_dir.parent / f".restore-{archive.stem}"
    if tmp.exists():
        shutil.rmtree(tmp)
    with tarfile.open(archive, "r:gz") as tar:
        tar.extractall(tmp, filter="data")
    manifest = BackupManifest.model_validate_json((tmp / "backup-manifest.json").read_text(encoding="utf-8"))
    src = tmp / "data"
    if overwrite and data_dir.exists():
        shutil.rmtree(data_dir)
    shutil.copytree(src, data_dir, dirs_exist_ok=True)
    shutil.rmtree(tmp, ignore_errors=True)
    mismatches = [rel for rel, h in manifest.files.items()
                  if not (data_dir / rel).exists() or sha256_file(data_dir / rel) != h]
    report = RestoreReport(restored_files=len(manifest.files), hash_mismatches=mismatches)
    # verify ledger chain
    if (data_dir / "ledger" / "events.jsonl").exists():
        from hydra.ledger.chain import Ledger

        pubs = {}
        for pub in (data_dir / "keys").glob("*.pub.pem") if (data_dir / "keys").exists() else []:
            from hydra.core.hashing import sha256_hex

            pem = pub.read_text(encoding="utf-8")
            pubs[f"hydra-{sha256_hex(pem)[:16]}"] = pem
        rep = Ledger(data_dir / "ledger", anchor_every=0).verify(pubs)
        report.ledger = rep.model_dump()
        head_ok = True
        if manifest.ledger_head:
            lines = [x for x in (data_dir / "ledger" / "events.jsonl").read_text(encoding="utf-8").splitlines() if x]
            head_ok = json.loads(lines[-1]).get("event_hash") == manifest.ledger_head
        report.ledger["head_matches_backup"] = head_ok
    if (data_dir / "artifacts").exists():
        from hydra.artifacts.store import ArtifactStore

        report.artifacts = ArtifactStore(data_dir / "artifacts").verify()
    if (data_dir / "world").exists():
        from hydra.world.model import WorldModel

        report.world_version = WorldModel(data_dir / "world").version
    if (data_dir / "corpus").exists():
        from hydra.corpus.store import CorpusStore

        report.corpus_records = len(CorpusStore(data_dir / "corpus").records)
    report.ok = (not mismatches and report.ledger.get("ok", True) and report.ledger.get("head_matches_backup", True)
                 and report.artifacts.get("ok", True))
    return report
