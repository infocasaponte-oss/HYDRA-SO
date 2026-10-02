# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""Download a deterministic slice of PleIAs Spanish public-domain books and newspapers.

Both collections declare public domain in all regions (authors dead > 70 years, EU Copyright
Directive art. 14), so they pass ``base_data_policy`` as "public-domain". Files land in
``data/sources/pleias/<collection>/`` with a manifest of sha256 per file; the selection is a
fixed, sorted prefix so a re-run resumes and reproduces the same slice.
"""
import argparse
import hashlib
import json
from pathlib import Path

from huggingface_hub import HfApi, hf_hub_download

COLLECTIONS = {"spanish-pd-books": "PleIAs/Spanish-PD-Books", "spanish-pd-newspapers": "PleIAs/Spanish-PD-Newspapers"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def fetch(collection: str, count: int, root: Path) -> dict:
    repo = COLLECTIONS[collection]
    files = sorted(f for f in HfApi().list_repo_files(repo, repo_type="dataset") if f.endswith(".parquet"))[:count]
    target = root / collection
    target.mkdir(parents=True, exist_ok=True)
    manifest_path = target / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {
        "repo": repo, "license": "public-domain", "files": {}}
    for name in files:
        if name in manifest["files"] and (target / name).exists():
            continue
        local = Path(hf_hub_download(repo, name, repo_type="dataset", local_dir=target))
        manifest["files"][name] = {"bytes": local.stat().st_size, "sha256": sha256(local)}
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(f"{collection}: {name} ({local.stat().st_size / 1e6:.0f} MB)", flush=True)
    return {"collection": collection, "files": len(manifest["files"]),
            "gb": round(sum(f["bytes"] for f in manifest["files"].values()) / 1e9, 2)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--books", type=int, default=12)
    parser.add_argument("--newspapers", type=int, default=300)
    parser.add_argument("--root", type=Path, default=Path("data/sources/pleias"))
    args = parser.parse_args()
    print(json.dumps([fetch("spanish-pd-books", args.books, args.root),
                      fetch("spanish-pd-newspapers", args.newspapers, args.root)]))
