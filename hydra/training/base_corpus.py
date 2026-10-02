# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""Clean pretraining corpus for HYDRA Base (proprietary weights).

Every document passes, in order: licence policy (``base_data_policy``, per record), privacy gate
(credentials and personal contact data are dropped), quality filters (length, mostly-printable,
not dominated by repeated lines) and exact deduplication of the normalised text. Output is a set
of gzipped JSONL shards plus a manifest with per-source counts, rejections, sha256 of every input
and shard, the hold-out split and the third-party attribution notice for a release.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import re
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from hydra.corpus.gates import PrivacyGate
from hydra.training.base_data_policy import admit_record, attribution_notice

MIN_CHARS = 200
SHARD_DOCS = 20_000
HOLDOUT_PERCENT = 1  # documents whose hash bucket is < 1 go to validation (perplexity)


@dataclass(frozen=True)
class SourceSpec:
    name: str
    path: Path
    kind: str  # "boe" | "stack_python" | "stack_markdown"
    url: str


def default_sources(root: Path = Path("data/sources")) -> list[SourceSpec]:
    return [
        SourceSpec("BOE legislación consolidada", root / "boe/boe_legislacion_consolidada.jsonl", "boe",
                   "https://www.boe.es/datosabiertos/"),
        SourceSpec("Stack v2 edu (Python, permissive)", root / "code/stackv2_edu_python_sample.jsonl", "stack_python",
                   "https://huggingface.co/datasets/common-pile/stackv2_edu_filtered"),
        SourceSpec("Stack v2 edu (Markdown, permissive)", root / "code/stackv2_edu_markdown_sample.jsonl",
                   "stack_markdown", "https://huggingface.co/datasets/common-pile/stackv2_edu_filtered"),
    ]


def record_licenses(kind: str, row: dict) -> list[str]:
    if kind == "boe":
        return ["es-public-sector-reuse"]  # BOE datos abiertos: reutilización con cita de la fuente
    if kind == "stack_python":
        return list(row.get("detected_licenses") or [])
    if kind == "stack_markdown":  # fetcher rows carry detected_licenses; older rows a "license" string
        if row.get("detected_licenses"):
            return list(row["detected_licenses"])
        return [lic.strip() for lic in str(row.get("license") or "").split(",") if lic.strip()]
    raise ValueError(f"unknown source kind {kind}")


def record_attribution(kind: str, row: dict, licenses: str) -> dict | None:
    """Per-file attribution kept for permissive code/docs (MIT/Apache/BSD notices name the work)."""
    if kind == "boe":
        return None
    return {"repository": row.get("repo_name"), "path": row.get("path"), "url": row.get("url"),
            "revision": row.get("revision_id"), "license": licenses}


def document_id(kind: str, row: dict) -> str:
    if kind == "boe":
        return row["document_id"]
    return str(row.get("id") or row.get("url") or row.get("path") or "")


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{4,}", "\n\n\n", text).strip()


def quality_problem(text: str) -> str | None:
    if len(text) < MIN_CHARS:
        return "too_short"
    sample = text[:20_000]
    if sum(ch.isprintable() or ch in "\n\t" for ch in sample) / len(sample) < 0.98:
        return "non_printable"
    lines = [line.strip() for line in sample.splitlines() if line.strip()]
    if len(lines) >= 20 and len(set(lines)) / len(lines) < 0.5:
        return "repetitive"
    return None


def holdout(doc_hash: str) -> bool:
    return int(doc_hash[:8], 16) % 100 < HOLDOUT_PERCENT


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def snapshot(path: Path) -> tuple[bytes, str]:
    """The exact complete-line bytes that will be parsed, and their sha256 (a source may be growing)."""
    data = path.read_bytes()
    data = data[:data.rfind(b"\n") + 1]
    return data, hashlib.sha256(data).hexdigest()


def read_rows(path: Path) -> Iterator[dict]:
    """Complete JSON lines only (a source may still be growing)."""
    data, _ = snapshot(path)
    for raw in data.splitlines():
        if raw.strip():
            yield json.loads(raw)


def scan_privacy(gate: PrivacyGate, text: str, chunk: int = 50_000, overlap: int = 512) -> tuple[bool, bool]:
    """Scan the whole document in overlapping chunks (secrets can sit anywhere in a long file)."""
    credential = pii = False
    for start in range(0, max(1, len(text)), chunk):
        _, found_credential, found_pii = gate.scan_text(text[max(0, start - overlap):start + chunk])
        credential, pii = credential or found_credential, pii or found_pii
        if credential:
            break
    return credential, pii


def gzip_text(path: Path):
    """Text gzip writer with a fixed header timestamp, so identical records give identical bytes."""
    return io.TextIOWrapper(gzip.GzipFile(filename="", mode="wb", fileobj=path.open("wb"), mtime=0),
                            encoding="utf-8", newline="\n")


def canonical_sha256(path: Path) -> str:
    """Digest of a JSON/text artifact with LF endings, matching the repository's normalised copy."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


class ShardWriter:
    def __init__(self, folder: Path, split: str) -> None:
        self.folder, self.split, self.index, self.count = folder, split, 0, 0
        self.stream = None
        self.files: dict[str, dict] = {}

    def write(self, record: dict) -> None:
        if self.stream is None or self.count >= SHARD_DOCS:
            self.close()
            name = f"{self.split}-{self.index:05d}.jsonl.gz"
            self.stream = gzip_text(self.folder / name)
            self.files[name] = {"documents": 0}
            self.index += 1
            self.count = 0
        self.stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        self.files[f"{self.split}-{self.index - 1:05d}.jsonl.gz"]["documents"] += 1
        self.count += 1

    def close(self) -> None:
        if self.stream is not None:
            self.stream.close()
            self.stream = None


def build(output: Path, sources: list[SourceSpec]) -> dict:
    if output.exists():
        raise FileExistsError("use a new versioned corpus directory")
    output.mkdir(parents=True)
    gate = PrivacyGate(pseudonymize_persons=False)  # official texts name public officials by design
    seen: set[str] = set()
    writers = {"train": ShardWriter(output, "train"), "validation": ShardWriter(output, "validation")}
    report: dict = {"version": "hydra-base-corpus-v0", "sources": [], "totals": {"documents": 0, "characters": 0}}
    notice_sources = []
    attributions = gzip_text(output / "THIRD_PARTY_ATTRIBUTIONS.jsonl.gz")
    attribution_count = 0
    for spec in sources:
        data, input_sha = snapshot(spec.path)  # hash exactly the bytes that are parsed
        stats = {"name": spec.name, "path": str(spec.path), "kind": spec.kind, "input_sha256": input_sha,
                 "read": 0, "kept": 0, "characters": 0, "rejected": {}}
        licenses_kept: set[str] = set()
        for raw in data.splitlines():
            if not raw.strip():
                continue
            row = json.loads(raw)
            stats["read"] += 1
            decision = admit_record(record_licenses(spec.kind, row))
            reason = None if decision.allowed else "license"
            text = normalize(row.get("text") or "") if reason is None else ""
            if reason is None:
                reason = quality_problem(text)
            if reason is None:
                credential, pii = scan_privacy(gate, text)
                reason = "credential" if credential else "personal_data" if pii else None
            doc_hash = hashlib.sha256(text.encode("utf-8")).hexdigest() if reason is None else ""
            if reason is None and doc_hash in seen:
                reason = "duplicate"
            if reason is not None:
                stats["rejected"][reason] = stats["rejected"].get(reason, 0) + 1
                continue
            seen.add(doc_hash)
            licenses_kept.update(decision.license.split(", "))
            writers["validation" if holdout(doc_hash) else "train"].write({
                "text": text, "source": spec.name, "document_id": document_id(spec.kind, row),
                "license": decision.license, "sha256": doc_hash})
            attribution = record_attribution(spec.kind, row, decision.license)
            if attribution is not None:
                attributions.write(json.dumps({"source": spec.name, "document_id": document_id(spec.kind, row),
                                               **attribution}, ensure_ascii=False) + "\n")
                attribution_count += 1
            stats["kept"] += 1
            stats["characters"] += len(text)
        report["sources"].append(stats)
        report["totals"]["documents"] += stats["kept"]
        report["totals"]["characters"] += stats["characters"]
        notice_sources += [{"name": spec.name, "license": lic, "url": spec.url} for lic in sorted(licenses_kept)]
    files = {}
    for writer in writers.values():
        writer.close()
        for name, entry in writer.files.items():
            files[name] = {**entry, "sha256": file_sha256(output / name)}
    attributions.close()
    report["files"] = files
    report["holdout_percent"] = HOLDOUT_PERCENT
    notice = attribution_notice(notice_sources) + (
        f"\nPer-file attribution (repository, path, revision, licence) for {attribution_count} retained "
        "code and documentation files: THIRD_PARTY_ATTRIBUTIONS.jsonl.gz\n")
    (output / "THIRD_PARTY_DATA_NOTICE.txt").write_text(notice, encoding="utf-8", newline="\n")
    report["notice_sha256"] = hashlib.sha256(notice.encode("utf-8")).hexdigest()
    report["attributions"] = {"file": "THIRD_PARTY_ATTRIBUTIONS.jsonl.gz", "records": attribution_count,
                              "sha256": file_sha256(output / "THIRD_PARTY_ATTRIBUTIONS.jsonl.gz")}
    report["generator_sha256"] = hashlib.sha256(Path(__file__).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    (output / "manifest.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
                                          newline="\n")
    return report


def iter_texts(corpus: Path, split: str = "train") -> Iterator[str]:
    for shard in sorted(corpus.glob(f"{split}-*.jsonl.gz")):
        with gzip.open(shard, "rt", encoding="utf-8") as stream:
            for line in stream:
                yield json.loads(line)["text"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("data/hydra-base-corpus-v0"))
    parser.add_argument("--sources-root", type=Path, default=Path("data/sources"))
    args = parser.parse_args()
    summary = build(args.output, default_sources(args.sources_root))
    print(json.dumps({k: summary[k] for k in ("totals", "sources")}, indent=2, ensure_ascii=False))
