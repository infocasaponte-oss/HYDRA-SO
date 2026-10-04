# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""Index Common Corpus by language and licence without downloading its text.

Common Corpus (PleIAs) is several TB of parquet. For every file this reads only the parquet footer
and the metadata columns (language, licence, open_type, collection, token_count) through HTTP range
requests, and appends per-file aggregates to an index. The index tells which files hold modern
Spanish or English under an admitted licence, so only those are downloaded later. Resumable.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter
from pathlib import Path

COLUMNS = ["language", "license", "open_type", "collection", "token_count"]


def hf_token() -> str | None:
    token = os.environ.get("HF_TOKEN")
    if not token and Path(".env").is_file():
        for line in Path(".env").read_text(encoding="utf-8").splitlines():
            if line.startswith(("HF_TOKEN=", "HUGGINGFACE_HUB_TOKEN=")):
                token = line.split("=", 1)[1].strip().strip('"')
    return token


def scan(out: Path, languages: set[str], limit: int | None = None, stride: int = 1):
    import pyarrow.parquet as pq
    from huggingface_hub import HfApi, HfFileSystem

    token = hf_token()
    revision = HfApi(token=token).dataset_info("PleIAs/common_corpus").sha
    fs = HfFileSystem(token=token)
    # files are shuffled mixes of collections, so a strided sample estimates the whole corpus
    files = sorted(f for f in fs.glob(f"datasets/PleIAs/common_corpus@{revision}/**/*.parquet"))[::stride]
    out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out.is_file():
        done = {json.loads(line)["file"] for line in out.read_text(encoding="utf-8").splitlines() if line.strip()}
    print(f"revision {revision}: {len(files)} files, {len(done)} already indexed", flush=True)
    with out.open("a", encoding="utf-8", newline="\n") as stream:
        for count, path in enumerate(files):
            name = path.split("@", 1)[1].split("/", 1)[1]
            if name in done:
                continue
            if limit is not None and count >= limit:
                break
            for attempt in range(1, 6):
                try:
                    with fs.open(path, "rb", block_size=1 << 20) as handle:
                        table = pq.ParquetFile(handle).read(columns=COLUMNS)
                    break
                except Exception as exc:
                    if attempt == 5:
                        raise
                    print(f"retry {attempt} {name}: {type(exc).__name__}", flush=True)
                    time.sleep(30 * attempt)
            groups: Counter = Counter()
            tokens: Counter = Counter()
            for row in table.to_pylist():
                key = (row["language"], row["license"], row["open_type"], row["collection"])
                groups[key] += 1
                try:
                    tokens[key] += int(row["token_count"] or 0)
                except (TypeError, ValueError):
                    pass
            stream.write(json.dumps({"file": name, "revision": revision, "rows": table.num_rows,
                                     "groups": [{"language": k[0], "license": k[1], "open_type": k[2],
                                                 "collection": k[3], "rows": n, "tokens": tokens[k]}
                                                for k, n in groups.items() if k[0] in languages]},
                                    ensure_ascii=False) + "\n")
            stream.flush()
            if count % 50 == 0:
                print(f"{count}/{len(files)} {name}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("data/sources/categories/_index/common_corpus_meta.jsonl"))
    parser.add_argument("--languages", nargs="*", default=["Spanish", "English"])
    parser.add_argument("--limit", type=int)
    parser.add_argument("--stride", type=int, default=1, help="index every n-th file (estimate first)")
    args = parser.parse_args()
    scan(args.out, set(args.languages), args.limit, args.stride)
