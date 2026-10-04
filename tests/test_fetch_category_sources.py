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
    ("CCBY", None), (None, None)])
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
    assert fetch.keep_row(source, old) == (None, "license")  # CC BY 3.0 is not on the policy list


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
