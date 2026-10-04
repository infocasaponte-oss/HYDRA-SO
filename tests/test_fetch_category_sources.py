# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
import importlib.util
import json
from pathlib import Path

import pytest

from hydra.training.base_data_policy import admit_record

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("fetch", ROOT / "scripts/fetch_category_sources.py")
fetch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetch)


@pytest.mark.parametrize("text,expected", [
    ("Creative Commons - Attribution - https://creativecommons.org/licenses/by/4.0/", "CC-BY-4.0"),
    ("Creative Commons - Attribution - https://creativecommons.org/licenses/by-sa/4.0/", "CC-BY-SA-4.0"),
    ("https://creativecommons.org/licenses/by-nc/3.0/", "CC-BY-NC-3.0"),
    ("Public Domain", "public-domain"),
    ("https://creativecommons.org/publicdomain/zero/1.0/", "CC0-1.0"),
    ("CCBY", "CC-BY"), ("CC-By", "CC-BY"), ("CC-By-SA", None),
    ("Creative Commons - Attribution - https://creativecommons.org/licenses/", "CC-BY"), (None, None)])
def test_licences_are_normalised_fail_closed(text, expected):
    assert fetch.normalize_license(text) == expected


def test_only_admitted_licences_and_topics_are_kept():
    source = {"kind": "licensed", "keywords": ["robot", "drone"], "min_keyword_hits": 2}
    by = "Creative Commons - Attribution - https://creativecommons.org/licenses/by/4.0/"
    ok = {"text": "A robot arm and a drone with a robot gripper.", "metadata": {"license": by}}
    assert fetch.keep_row(source, ok) == ("CC-BY-4.0", "ok")
    off = {"text": "A method for brewing coffee.", "metadata": {"license": by}}
    assert fetch.keep_row(source, off) == (None, "off_topic")
    sa = {"text": ok["text"], "metadata": {"license": by.replace("/by/", "/by-sa/")}}
    assert fetch.keep_row(source, sa) == (None, "license")
    old = {"text": ok["text"], "metadata": {"license": by.replace("4.0", "3.0")}}
    assert fetch.keep_row(source, old) == ("CC-BY-3.0", "ok")  # earlier CC BY versions admitted 2026-10-04


def test_stack_rows_need_language_permissive_and_not_vendor():
    source = {"kind": "stack", "languages": ["python"]}
    row = {"text": "x = 1", "metadata": {"language": "Python", "license_type": "permissive",
                                         "detected_licenses": ["MIT"]}}
    assert fetch.keep_row(source, row) == ("MIT", "ok")
    assert fetch.keep_row(source, {**row, "metadata": {**row["metadata"], "language": "Java"}})[1] == "language"
    assert fetch.keep_row(source, {**row, "metadata": {**row["metadata"], "is_vendor": True}})[1] == "license_or_vendor"
    gpl = {**row, "metadata": {**row["metadata"], "detected_licenses": ["GPL-3.0"]}}
    assert fetch.keep_row(source, gpl) == (None, "license")


def test_routing_by_url():
    source = {"route": {"matematicas": ["math.libretexts"], "default": "educacion"}}
    assert fetch.route(source, {"metadata": {"url": "https://math.libretexts.org/x"}}, "educacion") == "matematicas"
    assert fetch.route(source, {"metadata": {"url": "https://chem.libretexts.org/x"}}, "x") == "educacion"


def test_plan_sources_exist_and_targets_are_declared():
    plan = json.loads((ROOT / "config/base_categories.json").read_text(encoding="utf-8"))
    assert len(plan["categories"]) == 10
    for category in plan["categories"]:
        assert category["target_tokens"] > 0
        for source in category["sources"]:
            assert source in plan["sources"]
    for source in plan["sources"].values():
        if "license" in source:
            assert admit_record([source["license"]]).allowed


def test_every_cc_by_version_is_admitted_but_sa_nc_nd_are_not():
    for licence in ("CC-BY", "CC-BY-2.0", "CC-BY-2.5", "CC-BY-3.0", "CC-BY-4.0"):
        assert admit_record([licence]).allowed
    for licence in ("CC-BY-SA", "CC-BY-SA-3.0", "CC-BY-NC-3.0", "CC-BY-ND-4.0"):
        assert not admit_record([licence]).allowed


def test_run_source_streams_to_parts_and_counts_only_completed_shards(tmp_path, monkeypatch):
    import gzip
    monkeypatch.setattr(fetch, "ROOT", tmp_path)
    by = "Creative Commons - Attribution - https://creativecommons.org/licenses/by/4.0/"
    rows = [{"id": str(i), "text": "texto " * 50, "metadata": {"license": by, "url": f"https://math.libretexts.org/{i}"
                                                                if i % 2 else f"https://chem.libretexts.org/{i}"}}
            for i in range(6)] + [{"id": "sa", "text": "x", "metadata": {"license": by.replace("/by/", "/by-sa/")}}]
    monkeypatch.setattr(fetch, "stream_jsonl_gz", lambda url, token: iter(rows))
    plan = {"sources": {"lt": {"repo": "r/lt", "pattern": "lt-{:04d}.json.gz", "files": [0, 1], "kind": "licensed",
                               "route": {"matematicas": ["math.libretexts"], "default": "educacion"}}}}
    (tmp_path / "_manifests").mkdir(parents=True)
    (tmp_path / "_manifests" / "lt.json").write_text(json.dumps(
        {"revision": "abc", "files_done": [], "chars": {}, "docs": {}, "rejected": {}, "licenses": {}}), encoding="utf-8")
    need = {"educacion": 10 ** 9, "matematicas": 10 ** 9}
    fetch.run_source(plan, "educacion", "lt", None, need)
    status = json.loads((tmp_path / "_manifests" / "lt.json").read_text(encoding="utf-8"))
    assert status["files_done"] == ["lt-0000.json.gz", "lt-0001.json.gz"]
    assert status["docs"] == {"educacion": 6, "matematicas": 6} and status["rejected"] == {"license": 2}
    with gzip.open(tmp_path / "matematicas" / "lt" / "part-00000.jsonl.gz", "rt", encoding="utf-8") as stream:
        assert len(stream.read().splitlines()) == 3
    assert not list(tmp_path.rglob("*.tmp"))


def test_common_corpus_rows_filter_collection_language_and_licence(tmp_path):
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    rows = {"identifier": ["a", "b", "c", "d", "e"],
            "collection": ["OpenAlex", "OpenAlex", "Wikipedia", "dotgov", "VoxPopuli"],
            "license": ["CC-By", "CC-By-SA", "CC-By-SA", "Public Domain", "CC0"],
            "language": ["English", "English", "English", "English", "Spanish"],
            "title": ["t"] * 5, "text": ["uno", "dos", "tres", "cuatro", "cinco"]}
    pq.write_table(pa.table(rows), tmp_path / "f.parquet")
    source = {"collections": {"English|OpenAlex": "ciencia", "English|dotgov": "lingua_moderna",
                              "Spanish|VoxPopuli": "lingua_moderna"}}
    out = list(fetch.common_corpus_rows(tmp_path / "f.parquet", source))
    kept = [(r["id"], t, r["license"]) for r, t, _ in out if r]
    assert kept == [("a", "ciencia", "CC-BY"), ("d", "lingua_moderna", "public-domain"),
                    ("e", "lingua_moderna", "CC0-1.0")]
    assert sorted(reason for r, _, reason in out if r is None) == ["collection", "license"]


def test_one_source_feeding_two_categories_is_downloaded_once(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "ROOT", tmp_path)
    monkeypatch.setattr(fetch, "stream_jsonl_xz", lambda url, token: iter(
        [{"celex": url[-12:], "text": "artículo " * 30, "language": "es"}, {"celex": "x", "text": ""}]))
    plan = {"sources": {"eu": {"repo": "r/eu", "kind": "xz_jsonl", "license": "eu-reuse-2011-833",
                               "files": {"es/regulation.jsonl.xz": "lexislacion", "es/proposal.jsonl.xz": "lingua_moderna"},
                               "targets": ["lexislacion", "lingua_moderna"]}}}
    (tmp_path / "_manifests").mkdir()
    (tmp_path / "_manifests" / "eu.json").write_text(json.dumps(
        {"revision": "abc", "files_done": [], "chars": {}, "docs": {}, "rejected": {}, "licenses": {}}), encoding="utf-8")
    need = {"lexislacion": 10 ** 6, "lingua_moderna": 10 ** 6}
    fetch.run_source(plan, "lingua_moderna", "eu", None, need)
    fetch.run_source(plan, "lexislacion", "eu", None, need)  # nothing left to download
    status = json.loads((tmp_path / "_manifests" / "eu.json").read_text(encoding="utf-8"))
    assert status["docs"] == {"lexislacion": 1, "lingua_moderna": 1} and status["rejected"] == {"empty": 2}
    assert len(status["files_done"]) == 2
