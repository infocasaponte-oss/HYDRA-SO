# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
import json
import random

from hydra.hyd import route_corpus_v4 as rc
from hydra.router.decision_contract import CRITERIA

TEST = ["mi madre tiene el doble de edad que yo tenía cuando ella tenía mi edad actual",
        "a qué hora me dijiste que pasaba el último tren para volver a casa el fin de semana",
        "analiza esta radiografía que me dio el dentista se ve si me va a salir la muela del juicio"]


def test_guard_rejects_resemblance_and_keeps_new_requests():
    guard = rc.TestGuard(TEST)
    assert guard.reason("mi madre tiene el doble de edad que yo tenia, cuantos años tiene") is not None
    assert guard.reason("oye nos vemos luego, a qué hora me dijiste que salimos mañana para ir al monte con los primos") == "shared_4gram"
    assert guard.reason("mi dentista quiere otra radiografía antes de empezar la ortodoncia en septiembre") == "distinctive_words"
    assert guard.reason("comprime la carpeta de facturas en un zip") is None


def test_style_keeps_enye_and_fixes_contraction():
    rng = random.Random(1)
    assert rc.strip_accents("niño pequeño en España, cómo está") == "niño pequeño en España, como esta"
    styled = {rc.style("el precio de el gasoil en españa", rng) for _ in range(200)}
    assert all(" de el " not in s and "espana" not in s for s in styled)


def test_build_is_reproducible_balanced_and_template_split(tmp_path):
    test = tmp_path / "test.jsonl"
    test.write_text("".join(json.dumps({"text": t}, ensure_ascii=False) + "\n" for t in TEST), encoding="utf-8")
    first = rc.build(test, tmp_path / "a", seed=5, per_label=60)
    second = rc.build(test, tmp_path / "b", seed=5, per_label=60)
    assert first["corpus_sha256"] == second["corpus_sha256"]
    assert set(first["labels"]) == set(CRITERIA)
    rows = [json.loads(l) for l in (tmp_path / "a" / "corpus.jsonl").read_text(encoding="utf-8").splitlines()]
    train = {r["template"] for r in rows if r["split"] == "train"}
    dev = {r["template"] for r in rows if r["split"] == "dev"}
    assert train and dev and not train & dev  # dev measures unseen phrasings
    guard = rc.TestGuard(TEST)
    assert all(guard.reason(r["text"]) is None for r in rows)
    assert len({" ".join(rc.words(r["text"])) for r in rows}) == len(rows)
