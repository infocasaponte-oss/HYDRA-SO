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
    with gzip.open(tmp_path / "matematicas" / "lt" / "part-lt-0000.jsonl.gz", "rt", encoding="utf-8") as stream:
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


def test_failed_unit_is_retried_from_scratch_without_duplicates(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "ROOT", tmp_path)
    monkeypatch.setattr(fetch.time, "sleep", lambda s: None)
    by = "Creative Commons - Attribution - https://creativecommons.org/licenses/by/4.0/"
    rows = [{"id": str(i), "text": "texto " * 20, "metadata": {"license": by}} for i in range(4)]
    calls = {"n": 0}

    def flaky(url, token):
        calls["n"] += 1
        for i, row in enumerate(rows):
            if calls["n"] == 1 and i == 2:
                raise OSError("connection reset")
            yield row
    monkeypatch.setattr(fetch, "stream_jsonl_gz", flaky)
    plan = {"sources": {"s": {"repo": "r/s", "pattern": "s-{:04d}.json.gz", "files": [0, 0], "kind": "licensed"}}}
    (tmp_path / "_manifests").mkdir()
    (tmp_path / "_manifests" / "s.json").write_text(json.dumps(
        {"revision": "abc", "files_done": [], "chars": {}, "docs": {}, "rejected": {}, "licenses": {}}), encoding="utf-8")
    fetch.run_source(plan, "ciencia", "s", None, {"ciencia": 10 ** 6})
    status = json.loads((tmp_path / "_manifests" / "s.json").read_text(encoding="utf-8"))
    assert calls["n"] == 2 and status["docs"] == {"ciencia": 4}  # not 6: the failed prefix was discarded


def test_unit_failing_every_attempt_is_recorded_and_the_next_unit_still_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "ROOT", tmp_path)
    monkeypatch.setattr(fetch.time, "sleep", lambda s: None)
    by = "Creative Commons - Attribution - https://creativecommons.org/licenses/by/4.0/"

    def stream(url, token):
        if "s-0000" in url:
            raise OSError("truncated compressed stream")
        yield {"id": "1", "text": "texto " * 20, "metadata": {"license": by}}
    monkeypatch.setattr(fetch, "stream_jsonl_gz", stream)
    plan = {"sources": {"s": {"repo": "r/s", "pattern": "s-{:04d}.json.gz", "files": [0, 1], "kind": "licensed"}}}
    (tmp_path / "_manifests").mkdir()
    (tmp_path / "_manifests" / "s.json").write_text(json.dumps(
        {"revision": "abc", "files_done": [], "chars": {}, "docs": {}, "rejected": {}, "licenses": {}}), encoding="utf-8")
    fetch.run_source(plan, "ciencia", "s", None, {"ciencia": 10 ** 6}, attempts=2)
    status = json.loads((tmp_path / "_manifests" / "s.json").read_text(encoding="utf-8"))
    assert status["files_done"] == ["s-0001.json.gz"] and list(status["files_failed"]) == ["s-0000.json.gz"]
    assert status["docs"] == {"ciencia": 1}
    assert not list(tmp_path.rglob("*.tmp"))
    fetch.run_source(plan, "ciencia", "s", None, {"ciencia": 10 ** 6}, attempts=2)  # skipped on the next run
    assert json.loads((tmp_path / "_manifests" / "s.json").read_text(encoding="utf-8"))["docs"] == {"ciencia": 1}


def test_truncated_gzip_stream_is_an_error(monkeypatch):
    import gzip as gz
    import io
    body = gz.compress(b'{"text": "a"}\n{"text": "b"}\n')[:-8]  # trailer missing

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False
    monkeypatch.setattr(fetch.urllib.request, "urlopen", lambda request, timeout: Response(body))
    with pytest.raises(OSError, match="truncated"):
        list(fetch.stream_jsonl_gz("https://example.org/x.json.gz", None))


def test_stack_records_keep_attribution_fields(tmp_path, monkeypatch):
    import gzip as gz
    monkeypatch.setattr(fetch, "ROOT", tmp_path)
    row = {"id": "1", "text": "x = 1", "metadata": {"language": "Python", "license_type": "permissive",
                                                    "detected_licenses": ["MIT"], "repo_name": "o/r",
                                                    "path": "/a.py", "revision_id": "abc"}}
    monkeypatch.setattr(fetch, "stream_jsonl_gz", lambda url, token: iter([row]))
    plan = {"sources": {"code": {"repo": "r/c", "pattern": "c-{:04d}.json.gz", "files": [0, 0], "kind": "stack",
                                 "languages": ["python"]}}}
    (tmp_path / "_manifests").mkdir()
    (tmp_path / "_manifests" / "code.json").write_text(json.dumps(
        {"revision": "abc", "files_done": [], "chars": {}, "docs": {}, "rejected": {}, "licenses": {}}), encoding="utf-8")
    fetch.run_source(plan, "codigo", "code", None, {"codigo": 10 ** 6})
    with gz.open(tmp_path / "codigo" / "code" / "part-c-0000.jsonl.gz", "rt", encoding="utf-8") as stream:
        record = json.loads(stream.readline())
    assert (record["repo_name"], record["path"], record["revision_id"]) == ("o/r", "/a.py", "abc")


def test_per_file_caps_balance_document_types(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "ROOT", tmp_path)
    streamed = []

    def stream(url, token):
        for i in range(10):
            streamed.append(url[-24:])
            yield {"celex": f"{url[-20:]}{i}", "text": "a" * 100, "language": "es"}
    monkeypatch.setattr(fetch, "stream_jsonl_xz", stream)
    plan = {"sources": {"eu": {"repo": "r/eu", "kind": "xz_jsonl", "license": "eu-reuse-2011-833",
                               "files": {"es/regulation.jsonl.xz": {"target": "lexislacion", "max_chars": 300},
                                         "es/directive.jsonl.xz": {"target": "lexislacion", "max_chars": 300}}}}}
    (tmp_path / "_manifests").mkdir()
    (tmp_path / "_manifests" / "eu.json").write_text(json.dumps(
        {"revision": "abc", "files_done": [], "chars": {}, "docs": {}, "rejected": {}, "licenses": {}}), encoding="utf-8")
    fetch.run_source(plan, "lexislacion", "eu", None, {"lexislacion": 10 ** 6})
    status = json.loads((tmp_path / "_manifests" / "eu.json").read_text(encoding="utf-8"))
    assert status["docs"] == {"lexislacion": 6}  # 3 per document type, not 20 regulations
    assert len(streamed) == 8  # each file stops streaming once its share is full
    assert sorted(p.name for p in (tmp_path / "lexislacion" / "eu").iterdir()) == [
        "part-es_directive.jsonl.gz", "part-es_regulation.jsonl.gz"]


def test_parquet_filter_keeps_only_original_spanish(tmp_path):
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    pq.write_table(pa.table({"video_id": ["a", "b", "c"], "text": ["hola qué tal", "machine translated", ""],
                             "title": ["t"] * 3, "original_language": ["es", "en", "es"],
                             "transcription_language": ["es", "es", "es"], "video_link": ["l"] * 3}),
                   tmp_path / "y.parquet")
    source = {"filters": {"original_language": ["es"], "transcription_language": ["es"]}, "text_column": "text",
              "id_column": "video_id", "keep_columns": ["video_link"], "license": "CC-BY-3.0", "language": "es",
              "target": "lingua_moderna"}
    out = list(fetch.parquet_filter_rows(tmp_path / "y.parquet", source))
    kept = [(r["id"], t, r["license"]) for r, t, _ in out if r]
    assert kept == [("a", "lingua_moderna", "CC-BY-3.0")]
    assert sorted(reason for r, _, reason in out if r is None) == ["empty", "filtered"]


def test_tsv_column_is_read_and_grouped(monkeypatch):
    import io
    body = "\ufeffca\tes\r\nhola ca\thola es\r\nadeu\tadiós\r\nmal\r\n"  # BOM and CRLF, as real files

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False
    monkeypatch.setattr(fetch.urllib.request, "urlopen", lambda request, timeout: Response(body.encode()))
    values = list(fetch.stream_tsv_column("https://example.org/x.tsv", None, "es"))
    assert values == ["hola es", "adiós"]  # malformed row skipped
    assert list(fetch.grouped(["a", "b", "", "c"], 2)) == ["a\nb", "c"]

def test_html_text_keeps_paragraphs_math_symbols_and_exponents():
    markup = ('<p>Carga de 1,6 <span><math><semantics><mrow><mo>&#215;</mo></mrow><annotation-xml encoding="MathML-Content">'
              '<mo>times</mo></annotation-xml></semantics></math></span> 10<sup>-19</sup> C.</p><p>H<sub>2</sub>O</p>'
              '<script>x()</script>')
    assert fetch.html_text(markup) == "Carga de 1,6 × 10^-19 C.\nH_2O"


def test_boa_rows_route_by_section_and_skip_days_without_bulletin(monkeypatch):
    body = json.dumps([
        {"DOCN": "1", "Seccion": "I. Disposiciones Generales", "Titulo": "LEY 1/2024", "Texto": "Artículo uno.  " + "a" * 400,
         "FechaPublicacion": "20240102", "Emisor": "CORTES"},
        {"DOCN": "2", "Seccion": "III. Otras Disposiciones", "Titulo": "RESOLUCIÓN", "Texto": "Se resuelve &quot;x&quot; " + "b" * 400},
        {"DOCN": "3", "Seccion": "V. Anuncios", "Titulo": "ANUNCIO", "Texto": "corto"}], ensure_ascii=False)
    calls = []

    def http_text(url, encoding="utf-8", timeout=120):
        calls.append(url)
        return body if url.endswith("20240102") else "<!DOCTYPE html><html></html>"
    monkeypatch.setattr(fetch, "http_text", http_text)
    source = {"url": "https://boa.example/x?PUBL-C={date}", "license": "CC-BY-4.0", "target": "lingua_moderna",
              "section_targets": {"I": "lexislacion"}, "attribution": "Fuente: BOA"}
    rows = list(fetch.boa_rows(2024, source, pause=0))
    assert len(calls) == 366  # one request per day of a leap year
    kept = [(r["id"], t) for r, t, reason in rows if reason == "ok"]
    assert kept == [("BOA-1", "lexislacion"), ("BOA-2", "lingua_moderna")]
    assert [reason for _, _, reason in rows].count("short") == 1
    first = rows[0][0]
    assert first["text"].startswith("LEY 1/2024\n\nArtículo uno.\n") and first["attribution"] == "Fuente: BOA"
    assert '"x"' in rows[1][0]["text"]


def test_openstax_rows_read_the_book_licence_and_skip_non_admitted_books(monkeypatch):
    release = {"archiveUrl": "/apps/archive/1", "books": {"ok": {"defaultVersion": "v1"}, "nc": {"defaultVersion": "v2"}}}
    tree = {"contents": [{"id": "ch@", "title": "Cap 1", "contents": [
        {"id": "p1@", "title": "<span>Intro</span>", "slug": "1-intro"}, {"id": "p2@", "title": "Corta", "slug": "c"}]}]}
    pages = {"p1": "<p>" + "texto de física " * 40 + "</p>", "p2": "<p>breve</p>"}

    def http_text(url, encoding="utf-8", timeout=120):
        if url.endswith("ok@v1.json"):
            return json.dumps({"title": "Física", "slug": "fisica", "tree": tree,
                               "license": {"url": "http://creativecommons.org/licenses/by/4.0/"}})
        if url.endswith("nc@v2.json"):
            return json.dumps({"title": "Cálculo", "tree": tree,
                               "license": {"url": "http://creativecommons.org/licenses/by-nc-sa/4.0/"}})
        return json.dumps({"content": pages[url.rsplit(":", 1)[1][:-5]]})
    monkeypatch.setattr(fetch, "http_text", http_text)
    ok = list(fetch.openstax_rows("ok", "ciencia", release, {}))
    assert [(r["license"], t, r["url"]) for r, t, reason in ok if reason == "ok"] == [
        ("CC-BY-4.0", "ciencia", "https://openstax.org/books/fisica/pages/1-intro")]
    assert ok[0][0]["title"] == "Física — Intro" and [x[2] for x in ok] == ["ok", "short"]
    assert list(fetch.openstax_rows("nc", "matematicas", release, {})) == [(None, None, "license")]

def test_html_text_linearises_structural_mathml_and_separates_table_cells():
    frac = ('<p>Raíz: <math xmlns="http://www.w3.org/1998/Math/MathML"><semantics><mrow><mi>x</mi><mo>=</mo><mfrac>'
            '<mrow><mo>-</mo><mi>b</mi></mrow><mrow><mn>2</mn><mi>a</mi></mrow></mfrac></mrow>'
            '<annotation-xml encoding="MathML-Content"><ci>ignored</ci></annotation-xml></semantics></math></p>')
    assert fetch.html_text(frac) == "Raíz: x=(-b)/(2a)"
    root = '<math><msqrt><msup><mi>x</mi><mn>2</mn></msup><mo>+</mo><mn>1</mn></msqrt></math>'
    assert fetch.html_text(root) == "√(x^2+1)"
    table = "<table><tr><th>Masa</th><th>Valor</th></tr><tr><td>12</td><td>34</td></tr></table>"
    assert fetch.html_text(table) == "Masa Valor\n12 34"


def test_boa_invalid_day_fails_the_year_so_it_is_retried(monkeypatch):
    monkeypatch.setattr(fetch, "http_text", lambda url, encoding="utf-8", timeout=120: '[{"DOCN": "1", "Texto": "cort')
    source = {"url": "https://boa.example/x?PUBL-C={date}", "license": "CC-BY-4.0", "target": "lingua_moderna",
              "section_targets": {}, "attribution": "BOA"}
    with pytest.raises(OSError, match="invalid BOA JSON"):
        list(fetch.boa_rows(2024, source, pause=0))


def test_source_wide_outage_aborts_without_blacklisting_units(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "ROOT", tmp_path)
    monkeypatch.setattr(fetch.time, "sleep", lambda s: None)

    def down(url, token):
        raise OSError("401 token expired")
        yield
    monkeypatch.setattr(fetch, "stream_jsonl_gz", down)
    plan = {"sources": {"s": {"repo": "r/s", "pattern": "s-{:04d}.json.gz", "files": [0, 5], "kind": "licensed"}}}
    (tmp_path / "_manifests").mkdir()
    (tmp_path / "_manifests" / "s.json").write_text(json.dumps(
        {"revision": "abc", "files_done": [], "chars": {}, "docs": {}, "rejected": {}, "licenses": {}}), encoding="utf-8")
    with pytest.raises(OSError, match="consecutive units failed"):
        fetch.run_source(plan, "ciencia", "s", None, {"ciencia": 10 ** 6}, attempts=1)
    status = json.loads((tmp_path / "_manifests" / "s.json").read_text(encoding="utf-8"))
    assert not status.get("files_failed") and status["files_done"] == []


def test_openstax_release_is_pinned_in_the_manifest_and_reused_on_resume(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "ROOT", tmp_path)
    releases = iter([{"archiveUrl": "/apps/archive/20260604.1", "books": {"b1": {"defaultVersion": "v1"},
                                                                          "other": {"defaultVersion": "x"}}}])
    seen = []

    def http_text(url, encoding="utf-8", timeout=120):
        if url.endswith("release.json"):
            return json.dumps(next(releases))  # a second call would raise StopIteration
        raise AssertionError(url)
    monkeypatch.setattr(fetch, "http_text", http_text)
    monkeypatch.setattr(fetch, "openstax_rows", lambda book, target, release, source: (
        seen.append(release["books"][book]["defaultVersion"]) or iter([])))
    plan = {"sources": {"os": {"repo": "openstax.org", "kind": "openstax", "books": {"b1": "ciencia"}}}}
    fetch.run_source(plan, "ciencia", "os", None, {"ciencia": 10 ** 6})
    status = json.loads((tmp_path / "_manifests" / "os.json").read_text(encoding="utf-8"))
    assert status["revision"] == "openstax-archive-20260604.1"
    assert status["web_release"] == {"archiveUrl": "/apps/archive/20260604.1", "books": {"b1": {"defaultVersion": "v1"}}}
    status["files_done"] = []  # simulate a resume: the pinned release is used, no new release.json fetch
    (tmp_path / "_manifests" / "os.json").write_text(json.dumps(status), encoding="utf-8")
    fetch.run_source(plan, "ciencia", "os", None, {"ciencia": 10 ** 6})
    assert seen == ["v1", "v1"]


def test_boa_is_scheduled_from_both_categories_it_feeds():
    plan = json.loads((ROOT / "config/base_categories.json").read_text(encoding="utf-8"))
    cats = {c["id"]: c["sources"] for c in plan["categories"]}
    assert "boa_aragon" in cats["lingua_moderna"] and "boa_aragon" in cats["lexislacion"]
