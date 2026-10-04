# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""Download admitted open sources into data/sources/categories/<category>/<source>/, by category gap.

Plan: config/base_categories.json (ten categories with target valid tokens). Categories with the
largest relative gap go first; a category stops once its downloaded characters cover ~1.4x the gap
(filters later discard part). Every row passes the licence policy (base_data_policy) on its own
per-document licence; rows under share-alike, non-commercial or no-derivatives licences are dropped.
Three source families: Common Pile json.gz shards and EUR-Lex json.xz files are streamed and never
stored; Common Corpus parquet files are downloaded one at a time, filtered by language, collection and
licence, and deleted. Each input unit becomes one output part per category, written atomically, so an
interrupted run resumes at the next unit. Per-source caps keep one language or source from filling a
category. Nothing downloaded is executed.
"""
from __future__ import annotations

import argparse
import gzip
import json
import lzma
import os
import re
import time
import urllib.request
import zlib
from collections import Counter
from pathlib import Path

from hydra.training.base_data_policy import admit_record

ROOT = Path("data/sources/categories")
HF = "https://huggingface.co/datasets/{repo}/resolve/{revision}/{name}"
SAFETY = 1.4


def hf_token() -> str | None:
    token = os.environ.get("HF_TOKEN")
    env = Path(".env")
    if not token and env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith(("HF_TOKEN=", "HUGGINGFACE_HUB_TOKEN=")):
                token = line.split("=", 1)[1].strip().strip('"')
    return token


def normalize_license(text: str | None) -> str | None:
    """Policy id for a Common Pile licence string; None when it cannot be pinned down (fail-closed)."""
    if not text:
        return None
    t = text.lower()
    if "public domain" in t or "publicdomain/mark" in t:
        return "public-domain"
    if "publicdomain/zero" in t or "cc0" in t:
        return "CC0-1.0"
    m = re.search(r"licenses/([a-z-]+)/(\d\.\d)", t)
    if m:
        kind, version = m.groups()
        return f"CC-{kind.upper()}-{version}" if kind != "by" else f"CC-BY-{version}"
    # unversioned CC BY ("CC-By", "CCBY", ".../licenses/" with no path): admitted by the owner 2026-10-04;
    # any SA/NC/ND marker keeps it out
    compact = re.sub(r"[^a-z]", "", t)
    if compact in ("ccby", "creativecommonsattribution") or re.fullmatch(
            r"creative commons - attribution - https?://creativecommons\.org/licenses/?", t.strip()):
        return "CC-BY"
    for name in ("MIT", "Apache-2.0", "BSD-3-Clause", "BSD-2-Clause", "ISC", "Unlicense", "0BSD"):
        if name.lower() in t:
            return name
    return None


def _stream_lines(url: str, token: str | None, decoder):
    """JSON rows of one compressed file; fails unless the compressed stream reached its own end, so a
    body cut short between the last row and the trailer can never be taken for a complete file."""
    headers = {"User-Agent": "HYDRA-corpus/1.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    pending = b""
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=180) as response:
        while chunk := response.read(1 << 20):
            pending += decoder.decompress(chunk)
            *lines, pending = pending.split(b"\n")
            for line in lines:
                if line.strip():
                    yield json.loads(line)
    if not decoder.eof:
        raise OSError(f"truncated compressed stream: {url.rsplit('/', 1)[-1]}")
    if pending.strip():
        yield json.loads(pending)


def stream_jsonl_gz(url: str, token: str | None):
    yield from _stream_lines(url, token, zlib.decompressobj(16 + zlib.MAX_WBITS))


def stream_jsonl_xz(url: str, token: str | None):
    yield from _stream_lines(url, token, lzma.LZMADecompressor())


COMMON_CORPUS_LICENSES = {"public domain": "public-domain", "publc domain": "public-domain", "cc-by": "CC-BY",
                          "cc0": "CC0-1.0", "cc-by 4.0": "CC-BY-4.0", "mit": "MIT", "apache 2.0": "Apache-2.0"}


def common_corpus_rows(path: Path, source: dict):
    """(record, target category or None, reason) for each row of one Common Corpus parquet file."""
    import pyarrow.parquet as pq

    collections = source["collections"]  # "language|collection" -> category
    columns = ["identifier", "collection", "license", "language", "title", "text"]
    for batch in pq.ParquetFile(path).iter_batches(batch_size=2000, columns=columns):
        for row in batch.to_pylist():
            target = collections.get(f"{row['language']}|{row['collection']}")
            if target is None:
                yield None, None, "collection"
                continue
            licence = COMMON_CORPUS_LICENSES.get((row["license"] or "").strip().lower())
            if licence is None or not admit_record([licence]).allowed:
                yield None, None, "license"
                continue
            yield ({"text": row["text"] or "", "id": row["identifier"], "license": licence, "title": row["title"],
                    "url": None, "language": row["language"], "collection": row["collection"]}, target, "ok")


def parquet_filter_rows(path: Path, source: dict):
    """(record, target, reason) for each row of a parquet file filtered on column values (fixed licence)."""
    import pyarrow.parquet as pq

    filters = source["filters"]  # column -> allowed values
    columns = sorted({source["text_column"], source["id_column"], *filters, *source.get("keep_columns", [])})
    for batch in pq.ParquetFile(path).iter_batches(batch_size=2000, columns=columns):
        for row in batch.to_pylist():
            if any(row.get(column) not in allowed for column, allowed in filters.items()):
                yield None, None, "filtered"
                continue
            text = row.get(source["text_column"]) or ""
            if not text.strip():
                yield None, None, "empty"
                continue
            record = {"text": text, "id": row.get(source["id_column"]), "license": source["license"], "url": None,
                      "title": row.get("title"), "language": source.get("language")}
            record.update({k: row.get(k) for k in source.get("keep_columns", [])})
            yield record, source.get("target"), "ok"


def keep_row(source: dict, row: dict) -> tuple[str | None, str]:
    """(licence id or None, reason) for one input row."""
    meta = row.get("metadata") or {}
    if source["kind"] == "stack":
        language = (meta.get("language") or "").lower()
        if language not in source["languages"]:
            return None, "language"
        if meta.get("license_type") != "permissive" or meta.get("is_vendor") or meta.get("is_generated"):
            return None, "license_or_vendor"
        licenses = list(meta.get("detected_licenses") or [])
        decision = admit_record(licenses) if licenses else None
        return (decision.license, "ok") if decision and decision.allowed else (None, "license")
    licence = normalize_license(meta.get("license") or meta.get("oa_license"))
    if licence is None or not admit_record([licence]).allowed:
        return None, "license"
    if "keywords" in source:
        head = row.get("text", "")[:6000].lower()
        if sum(head.count(k) for k in source["keywords"]) < source.get("min_keyword_hits", 1):
            return None, "off_topic"
    return licence, "ok"


def route(source: dict, row: dict, default: str) -> str:
    rules = source.get("route")
    if not rules:
        return default
    url = str((row.get("metadata") or {}).get("url") or "")
    for category, needles in rules.items():
        if category != "default" and any(n in url for n in needles):
            return category
    return rules.get("default", default)


def load_status(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"files_done": [], "chars": {}, "docs": {},
                                                                               "rejected": {}, "licenses": {}}


def save_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def downloaded_chars(category: str) -> int:
    """Characters already downloaded for a category, including rows routed from another folder."""
    return sum(json.loads(m.read_text(encoding="utf-8")).get("chars", {}).get(category, 0)
               for m in ROOT.glob("_manifests/*.json"))


def units(source: dict, status: dict, token: str | None):
    """(unit name, factory of an iterator of (record or None, target or None, reason)) per input unit."""
    if source["kind"] in ("licensed", "stack"):
        first, last = source["files"]
        for index in range(first, last + 1):
            name = source["pattern"].format(index)

            def rows(name=name):
                url = HF.format(repo=source["repo"], revision=status["revision"], name=name)
                for row in stream_jsonl_gz(url, token):
                    licence, reason = keep_row(source, row)
                    if licence is None:
                        yield None, None, reason
                        continue
                    meta = row.get("metadata") or {}
                    record = {"text": row["text"], "id": row.get("id"), "license": licence, "url": meta.get("url"),
                              "title": meta.get("title"), "language": meta.get("language")}
                    if source["kind"] == "stack":  # per-file attribution, as base_corpus.record_attribution expects
                        record.update({key: meta.get(key) for key in ("repo_name", "path", "revision_id",
                                                                      "detected_licenses")})
                    yield record, route(source, row, None), "ok"
            yield name, rows
    elif source["kind"] == "xz_jsonl":
        for name, spec in source["files"].items():
            target = spec if isinstance(spec, str) else spec["target"]

            def rows(name=name, target=target):
                url = HF.format(repo=source["repo"], revision=status["revision"], name=name)
                for row in stream_jsonl_xz(url, token):
                    if not (row.get("text") or "").strip():
                        yield None, None, "empty"
                        continue
                    yield ({"text": row["text"], "id": row.get("celex"), "license": source["license"],
                            "title": row.get("title"), "date": row.get("date"), "language": row.get("language"),
                            "url": f"https://eur-lex.europa.eu/legal-content/ES/TXT/?uri=CELEX:{row.get('celex')}"},
                           target, "ok")
            yield name, rows
    elif source["kind"] in ("common_corpus", "parquet_filter"):
        from huggingface_hub import HfApi, hf_hub_download

        siblings = HfApi(token=token).dataset_info(source["repo"], revision=status["revision"]).siblings
        files = sorted(x.rfilename for x in siblings if x.rfilename.endswith(".parquet"))[::source.get("stride", 1)]
        files = files[:source.get("max_units", len(files))]  # each file is ~470 MB; past its caps it adds little
        for name in files:
            def rows(name=name):
                local = Path(hf_hub_download(source["repo"], name, repo_type="dataset", revision=status["revision"],
                                             local_dir=ROOT / "_tmp", token=token))
                try:
                    reader = common_corpus_rows if source["kind"] == "common_corpus" else parquet_filter_rows
                    yield from reader(local, source)
                finally:
                    local.unlink(missing_ok=True)
            yield name, rows
    else:
        raise ValueError(f"unknown source kind {source['kind']}")


def run_source(plan: dict, category: str, source_id: str, token: str | None, need_chars: dict[str, int],
               attempts: int = 5):
    source = plan["sources"][source_id]
    status_path = ROOT / "_manifests" / f"{source_id}.json"  # one per source: it may feed several categories
    status = load_status(status_path)
    if "revision" not in status:
        from huggingface_hub import HfApi
        status.update({"repo": source["repo"], "revision": HfApi(token=token).dataset_info(source["repo"]).sha,
                       "policy": "hydra/training/base_data_policy.py", "source_id": source_id})
    caps = source.get("caps", {})  # category -> max characters this source may contribute
    targets = {category, *(c for c in source.get("route", {}) if c != "default"), *source.get("targets", [])}

    def open_for(target, pending=0):
        return (need_chars.get(target, 0) - pending > 0
                and status["chars"].get(target, 0) + pending < caps.get(target, float("inf")))

    for name, rows in units(source, status, token):
        if name in status["files_done"]:
            continue
        spec = source.get("files", {}).get(name) if isinstance(source.get("files"), dict) else None
        unit_cap = spec.get("max_chars") if isinstance(spec, dict) else None  # keeps one file type from filling a category
        if not any(open_for(t) for t in targets):
            break
        # The whole unit is one transaction: rows stream to temporary parts and the manifest changes only after
        # the unit completes. A failed attempt discards its parts and counters and the unit starts over, so a
        # retried download can never leave a duplicated prefix.
        part = re.sub(r"[^A-Za-z0-9._-]+", "_", name.rsplit(".json", 1)[0])  # stable name per unit, no collisions
        for attempt in range(1, attempts + 1):
            writers, temps = {}, {}
            chars, docs, rejected, licences = Counter(), Counter(), Counter(), Counter()
            try:
                for record, target, reason in rows():
                    if record is None:
                        rejected[reason] += 1
                        continue
                    target = target or category
                    if unit_cap is not None and chars[target] >= unit_cap:
                        rejected["unit_cap"] += 1
                        break  # stop streaming this file: its share is full
                    if not open_for(target, chars[target]):
                        rejected["category_full"] += 1
                        continue
                    record.update({"source": source["repo"], "source_revision": status["revision"], "category": target})
                    if target not in writers:
                        out = ROOT / target / source_id / f"part-{part}.jsonl.gz"
                        out.parent.mkdir(parents=True, exist_ok=True)
                        temps[target] = (out.with_suffix(".tmp"), out)
                        writers[target] = gzip.open(temps[target][0], "wt", encoding="utf-8", compresslevel=6)
                    writers[target].write(json.dumps(record, ensure_ascii=False) + "\n")
                    chars[target] += len(record["text"])
                    docs[target] += 1
                    licences[record["license"]] += 1
                for writer in writers.values():
                    writer.close()
                break
            except Exception as exc:  # network cuts, truncated streams
                for writer in writers.values():
                    writer.close()
                for tmp, _ in temps.values():
                    tmp.unlink(missing_ok=True)
                if attempt == attempts:
                    raise
                print(f"retry unit {attempt}/{attempts - 1} {name}: {type(exc).__name__}", flush=True)
                time.sleep(min(300, 20 * 2 ** attempt))
        for tmp, out in temps.values():
            os.replace(tmp, out)
        for counter, key in ((chars, "chars"), (docs, "docs"), (rejected, "rejected"), (licences, "licenses")):
            for k, v in counter.items():
                status[key][k] = status[key].get(k, 0) + v
        for target, n in chars.items():
            need_chars[target] = need_chars.get(target, 0) - n
        status["files_done"].append(name)
        save_json(status_path, status)
        print(f"{category}/{source_id} {name}: kept {sum(docs.values())} docs ({sum(chars.values()) / 1e6:.0f} M chars) "
              f"{dict(chars)}; remaining {({k: v for k, v in need_chars.items() if v > 0})}", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, default=Path("config/base_categories.json"))
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    token = hf_token()
    cpt = plan["chars_per_token"]
    need = {}
    for c in plan["categories"]:
        gap = max(0, c["target_tokens"] - c["current_tokens"])
        need[c["id"]] = int(gap * cpt * SAFETY) - downloaded_chars(c["id"])
    order = sorted(plan["categories"], key=lambda c: -(max(0, c["target_tokens"] - c["current_tokens"]) / c["target_tokens"]))
    save_json(ROOT / "plan-status.json", {"need_chars": need, "order": [c["id"] for c in order]})
    for category in order:
        for source_id in category["sources"]:
            if need.get(category["id"], 0) > 0:
                run_source(plan, category["id"], source_id, token, need)
        save_json(ROOT / "plan-status.json", {"need_chars": need, "order": [c["id"] for c in order]})
    print("done", json.dumps({k: v for k, v in need.items()}), flush=True)


if __name__ == "__main__":
    main()
