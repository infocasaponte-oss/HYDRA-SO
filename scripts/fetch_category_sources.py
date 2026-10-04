# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""Download admitted open sources into data/sources/categories/<category>/<source>/, by category gap.

Plan: config/base_categories.json (ten categories with target valid tokens). Categories with the
largest relative gap go first; a category stops once its downloaded characters cover ~1.4x the gap
(filters later discard part). Every row passes the licence policy (base_data_policy) on its own
per-document licence; rows under share-alike, non-commercial, no-derivatives or unversioned licences
are dropped. Raw shards are streamed and never stored; each input shard becomes one output part,
written atomically, so an interrupted run resumes at the next shard. Nothing downloaded is executed.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import time
import urllib.request
import zlib
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


def stream_jsonl_gz(url: str, token: str | None, attempts: int = 5):
    for attempt in range(1, attempts + 1):
        try:
            headers = {"User-Agent": "HYDRA-corpus/1.0"}
            if token:
                headers["Authorization"] = f"Bearer {token}"
            decoder, pending = zlib.decompressobj(16 + zlib.MAX_WBITS), b""
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=180) as response:
                while chunk := response.read(1 << 20):
                    pending += decoder.decompress(chunk)
                    *lines, pending = pending.split(b"\n")
                    for line in lines:
                        if line.strip():
                            yield json.loads(line)
            if pending.strip():
                yield json.loads(pending)
            return
        except Exception as exc:  # broken connections on multi-hundred-MB shards
            if attempt == attempts:
                raise
            print(f"retry {attempt} {url.rsplit('/', 1)[-1]}: {type(exc).__name__}", flush=True)
            time.sleep(min(300, 20 * 2 ** attempt))


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
               for m in ROOT.glob("*/*/manifest.json"))


def run_source(plan: dict, category: str, source_id: str, token: str | None, need_chars: dict[str, int]):
    from huggingface_hub import HfApi

    source = plan["sources"][source_id]
    if source["kind"] == "parquet":
        print(f"skip {source_id}: parquet sources run with fetch_cosmopedia (not implemented yet)", flush=True)
        return
    folder = ROOT / category / source_id
    status_path = folder / "manifest.json"
    status = load_status(status_path)
    if "revision" not in status:
        status.update({"repo": source["repo"], "revision": HfApi(token=token).dataset_info(source["repo"]).sha,
                       "policy": "hydra/training/base_data_policy.py", "source_id": source_id})
    first, last = source["files"]
    for index in range(first, last + 1):
        name = source["pattern"].format(index)
        if name in status["files_done"]:
            continue
        if all(need_chars.get(c, 0) <= 0 for c in {category, *source.get("route", {})} - {"default"}):
            break
        url = HF.format(repo=source["repo"], revision=status["revision"], name=name)
        parts: dict[str, list[str]] = {}
        for row in stream_jsonl_gz(url, token):
            licence, reason = keep_row(source, row)
            if licence is None:
                status["rejected"][reason] = status["rejected"].get(reason, 0) + 1
                continue
            target = route(source, row, category)
            meta = row.get("metadata") or {}
            record = {"text": row["text"], "id": row.get("id"), "license": licence, "source": source["repo"],
                      "source_revision": status["revision"], "url": meta.get("url"), "title": meta.get("title"),
                      "category": target, "language": meta.get("language")}
            parts.setdefault(target, []).append(json.dumps(record, ensure_ascii=False))
            status["chars"][target] = status["chars"].get(target, 0) + len(row["text"])
            status["docs"][target] = status["docs"].get(target, 0) + 1
            status["licenses"][licence] = status["licenses"].get(licence, 0) + 1
        for target, lines in parts.items():
            out = ROOT / target / source_id / f"part-{index:05d}.jsonl.gz"
            out.parent.mkdir(parents=True, exist_ok=True)
            tmp = out.with_suffix(".tmp")
            with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=6) as stream:
                stream.write("\n".join(lines) + "\n")
            os.replace(tmp, out)
            need_chars[target] = need_chars.get(target, 0) - sum(len(json.loads(x)["text"]) for x in lines)
        status["files_done"].append(name)
        save_json(status_path, status)
        print(f"{category}/{source_id} {name}: kept {sum(len(v) for v in parts.values())} docs; "
              f"remaining chars {({k: v for k, v in need_chars.items() if v > 0})}", flush=True)


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
