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
import datetime
import gzip
import html
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
WEB_KINDS = ("boa_aragon", "openstax")  # official portals, not Hugging Face datasets


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


def http_text(url: str, encoding: str = "utf-8", timeout: int = 120) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "HYDRA-corpus/1.0 (open-data reuse; cites source)"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode(encoding, "replace")


_BLOCK = re.compile(r"</?(?:p|div|li|h[1-6]|section|table|tr|figcaption|caption|ul|ol|dd|dt|br|pre)\b[^>]*>", re.I)


def html_text(markup: str) -> str:
    """Readable text of an HTML fragment: block tags become line breaks, MathML keeps its presentation
    symbols (annotations dropped), superscripts and subscripts become ^ and _."""
    s = re.sub(r"(?is)<(script|style|annotation-xml|annotation)\b.*?</\1>", " ", markup)
    s = re.sub(r"(?i)<sup\b[^>]*>", "^", s)
    s = re.sub(r"(?i)<sub\b[^>]*>", "_", s)
    s = _BLOCK.sub("\n", s)
    s = html.unescape(re.sub(r"<[^>]+>", "", s))
    lines = (" ".join(line.split()) for line in s.split("\n"))
    return "\n".join(line for line in lines if line)


def boa_rows(year: int, source: dict, pause: float = 0.3):
    """(record, target, reason) for every disposition of the Boletín Oficial de Aragón published in one
    year, from its open-data JSON (full text included). Section I (general provisions) goes to the
    legal category; the other sections (appointments, resolutions, notices) to modern administrative Spanish."""
    day = datetime.date(year, 1, 1)
    while day.year == year:
        url = source["url"].format(date=day.strftime("%Y%m%d"))
        body = http_text(url, encoding="iso-8859-1").strip()
        time.sleep(pause)
        day += datetime.timedelta(days=1)
        if not body.startswith("["):
            continue  # no bulletin that day
        try:
            items = json.loads(body, strict=False)
        except ValueError:
            yield None, None, "bad_day_json"
            continue
        for item in items:
            text = html.unescape(item.get("Texto") or "").strip()
            if len(text) < source.get("min_chars", 300):
                yield None, None, "short"
                continue
            text = re.sub(r" {2,}", "\n", text)
            title = html.unescape(item.get("Titulo") or "").strip()
            section = (item.get("Seccion") or "").split(".")[0].strip()
            target = source["section_targets"].get(section, source["target"])
            yield ({"text": f"{title}\n\n{text}" if title else text, "id": f"BOA-{item.get('DOCN')}",
                    "license": source["license"], "title": title, "language": "es",
                    "date": item.get("FechaPublicacion"), "section": item.get("Seccion"), "issuer": item.get("Emisor"),
                    "url": f"https://www.boa.aragon.es/cgi-bin/EBOA/BRSCGI?CMD=VEROBJ&MLKOB={item.get('DOCN')}",
                    "attribution": source["attribution"]}, target, "ok")


def _openstax_pages(tree: dict):
    for node in tree.get("contents", []):
        if "contents" in node:
            yield from _openstax_pages(node)
        else:
            yield node


def openstax_rows(book_id: str, target: str, release: dict, source: dict):
    """(record, target, reason) for every page of one OpenStax book; the licence is read from the book
    itself and the whole book is skipped unless the policy admits it."""
    archive = "https://openstax.org" + release["archiveUrl"]
    version = release["books"][book_id]["defaultVersion"]
    base = f"{archive}/contents/{book_id}@{version}"
    book = json.loads(http_text(base + ".json"))
    licence = normalize_license((book.get("license") or {}).get("url"))
    if licence is None or not admit_record([licence]).allowed:
        yield None, None, "license"
        return
    title = html_text(book["title"])
    for page in _openstax_pages(book["tree"]):
        page_id = page["id"].split("@")[0]
        content = json.loads(http_text(f"{base}:{page_id}.json")).get("content") or ""
        text = html_text(content)
        if len(text) < source.get("min_chars", 400):
            yield None, None, "short"
            continue
        yield ({"text": text, "id": f"openstax:{book_id}@{version}:{page_id}", "license": licence,
                "title": f"{title} — {html_text(page.get('title', ''))}", "language": "es",
                "url": f"https://openstax.org/books/{book.get('slug', book_id)}/pages/{page.get('slug', page_id)}",
                "attribution": f"{title}, OpenStax (Rice University), {licence}"}, target, "ok")


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


def stream_tsv_column(url: str, token: str | None, column: str):
    """Values of one column of a plain TSV file over HTTP (header row names the columns)."""
    headers = {"User-Agent": "HYDRA-corpus/1.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=180) as response:
        names = [n.strip().lstrip("\ufeff") for n in response.readline().decode("utf-8").split("\t")]
        index = names.index(column)
        for raw in response:
            fields = raw.decode("utf-8", "replace").rstrip("\r\n").split("\t")
            if len(fields) == len(names):
                yield fields[index]


def grouped(values, size: int):
    """Join consecutive short segments (paragraphs, sentences) into documents of ``size`` segments."""
    block = []
    for value in values:
        if value.strip():
            block.append(value.strip())
        if len(block) == size:
            yield "\n".join(block)
            block = []
    if block:
        yield "\n".join(block)


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
    elif source["kind"] in ("tsv_column", "parquet_column"):
        for name in source["files"]:
            def rows(name=name):
                url = HF.format(repo=source["repo"], revision=status["revision"], name=name)
                if source["kind"] == "tsv_column":
                    values = stream_tsv_column(url, token, source["column"])
                else:  # nested parquet column, e.g. OPUS translation.es
                    import pyarrow.parquet as pq
                    from huggingface_hub import hf_hub_download
                    local = Path(hf_hub_download(source["repo"], name, repo_type="dataset", revision=status["revision"],
                                                 local_dir=ROOT / "_tmp", token=token))
                    outer, inner = source["column"].split(".")
                    values = (row[outer][inner] for batch in pq.ParquetFile(local).iter_batches(columns=[outer])
                              for row in batch.to_pylist())
                try:
                    for number, text in enumerate(grouped(values, source.get("group", 1))):
                        yield ({"text": text, "id": f"{name}:{number}", "license": source["license"], "url": None,
                                "title": None, "language": source.get("language")}, source.get("target"), "ok")
                finally:
                    if source["kind"] == "parquet_column":
                        local.unlink(missing_ok=True)
            yield name, rows
    elif source["kind"] == "boa_aragon":
        first, last = source["years"]
        for year in range(last, first - 1, -1):  # newest first: the most modern language arrives earliest
            yield str(year), (lambda year=year: boa_rows(year, source))
    elif source["kind"] == "openstax":
        release = json.loads(http_text("https://openstax.org/rex/release.json"))
        for book_id, target in source["books"].items():
            yield book_id, (lambda book_id=book_id, target=target: openstax_rows(book_id, target, release, source))
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
    if "revision" not in status and source["kind"] in WEB_KINDS:  # not on the Hub: date the snapshot instead
        status.update({"repo": source["repo"], "revision": "web-" + datetime.date.today().isoformat(),
                       "policy": "hydra/training/base_data_policy.py", "source_id": source_id})
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
        if name in status["files_done"] or name in status.get("files_failed", {}):
            continue  # a unit that failed every attempt is skipped; delete its entry in the manifest to retry it
        spec = source.get("files", {}).get(name) if isinstance(source.get("files"), dict) else None
        unit_cap = spec.get("max_chars") if isinstance(spec, dict) else None  # keeps one file type from filling a category
        if not any(open_for(t) for t in targets):
            break
        # The whole unit is one transaction: rows stream to temporary parts and the manifest changes only after
        # the unit completes. A failed attempt discards its parts and counters and the unit starts over, so a
        # retried download can never leave a duplicated prefix.
        part = re.sub(r"[^A-Za-z0-9._-]+", "_", name.rsplit(".json", 1)[0])  # stable name per unit, no collisions
        failed = None
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
                    failed = f"{type(exc).__name__}: {exc}"[:300]
                    break
                print(f"retry unit {attempt}/{attempts - 1} {name}: {type(exc).__name__}", flush=True)
                time.sleep(min(300, 20 * 2 ** attempt))
        if failed:  # one unreachable file must not stop the rest of the source
            status.setdefault("files_failed", {})[name] = failed
            save_json(status_path, status)
            print(f"UNIT FAILED {source_id} {name}: {failed}", flush=True)
            continue
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
                try:
                    run_source(plan, category["id"], source_id, token, need)
                except Exception as exc:  # one broken source must not stop the other categories
                    print(f"SOURCE FAILED {category['id']}/{source_id}: {type(exc).__name__}: {exc}", flush=True)
        save_json(ROOT / "plan-status.json", {"need_chars": need, "order": [c["id"] for c in order]})
    print("done", json.dumps({k: v for k, v in need.items()}), flush=True)


if __name__ == "__main__":
    main()
