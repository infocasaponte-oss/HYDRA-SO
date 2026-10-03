# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""Hyd routing corpus v5: v4 plus the capabilities the v4 audit found missing in every model.

Added on top of the v4 templates (same decontamination guard, template-level dev split):
- references to context that does not exist in the conversation (abstain);
- numbers in requests that are not calculations (money, years, ports, sizes, ages);
- a conversational preamble before the real request (label of the request);
- contrast and negation, "olvida lo de X, ahora Y" (label of Y).
The wordings of preambles and contrasts deliberately differ from ``hydra.hyd.probes``, so the
probes keep measuring generalisation instead of memorised strings.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import Counter
from pathlib import Path

from hydra.hyd import route_corpus_v4 as v4
from hydra.hyd.route_corpus_v4 import num, pick


def abstain_context(rng):
    return [
        ("abs5-said", lambda: f"{pick(rng, 'lo que', 'eso que', 'aquello que')} me {pick(rng, 'comentaste', 'contaste', 'propusiste')} {pick(rng, 'el martes', 'hace un rato', 'la semana pasada')}, {pick(rng, 'lo hacemos así', 'sigue en pie', 'cómo quedaba')}"),
        ("abs5-agreed", lambda: f"{pick(rng, 'como quedamos', 'según lo hablado', 'tal como acordamos')}, {pick(rng, 'prepáramelo', 'mándamelo', 'déjalo listo')} {pick(rng, 'para mañana', 'ya', 'antes del viernes')}"),
        ("abs5-recommended", lambda: f"{pick(rng, 'el libro', 'la serie', 'el taller', 'la crema')} que me {pick(rng, 'recomendaste', 'nombraste', 'apuntaste')} {pick(rng, 'cuánto cuesta', 'dónde lo encuentro', 'cómo se llamaba')}"),
        ("abs5-their", lambda: f"y {pick(rng, 'su respuesta', 'lo de ellos', 'el suyo')} {pick(rng, 'qué te parece', 'es normal', 'cómo lo ves')}"),
        ("abs5-number", lambda: f"{pick(rng, 'súmale', 'réstale', 'aplícale')} {pick(rng, 'lo del otro día', 'la cifra de antes', 'el porcentaje que dijimos')} y {pick(rng, 'dime el total', 'cierra la cuenta', 'pásame el resultado')}"),
    ]


def numbers_not_math(rng):
    return [
        ("num5-year", lambda: f"qué pasó en {pick(rng, 'galicia', 'españa', 'europa')} en {num(rng, 1850, 2020)} según {pick(rng, 'los historiadores', 'las hemerotecas', 'fuentes fiables')}"),
        ("num5-port", lambda: f"abre la configuración del proxy y pon el puerto {num(rng, 1025, 65000)} en lugar del actual"),
        ("num5-size", lambda: f"borra de la carpeta temporal los ficheros de más de {num(rng, 10, 900)} megas que tengan más de {num(rng, 2, 30)} días"),
        ("num5-age", lambda: f"un menor de {num(rng, 12, 17)} años puede {pick(rng, 'abrir una cuenta de redes', 'dar su consentimiento para fotos', 'apuntarse solo a la newsletter')} sin sus padres según la ley de datos"),
        ("num5-money", lambda: f"paga ahora la factura de {num(rng, 3, 99)}.{num(rng, 100, 999)} euros del proveedor nuevo sin esperar a contabilidad"),
        ("num5-version", lambda: f"en {pick(rng, 'python', 'node', 'java')} {num(rng, 8, 21)} cómo {pick(rng, 'leo un fichero comprimido', 'hago una petición asíncrona', 'formateo una fecha')}"),
    ]


EXTRA = {"abstain": abstain_context, "_numbers": numbers_not_math}
NUMBER_LABELS = {"num5-year": "research", "num5-port": "tool_use", "num5-size": "tool_use", "num5-age": "privacy",
                 "num5-money": "high_risk_review", "num5-version": "coding"}
PREAMBLES = ["bueno, cambiando de tema, ", "perdona el rollo de antes, ", "estoy en el bus y me acordé: ",
             "mi jefe me pregunta y no sé qué decirle, ", "antes de que se me olvide, ", "una cosa rápida entre medias, ",
             "llevo toda la mañana con mil cosas, ", "sin prisa ninguna, "]
CONTRASTS = ["olvida lo de {x}, ahora {y}", "no quiero que {x}; lo que me hace falta es que {y}",
             "en vez de {x}, {y}", "lo de {x} otro día; hoy {y}", "deja eso de {x} y mejor {y}"]


def _generate(rng, guard, templates, label_of, per_template, seen, rejected):
    rows = []
    for tid, fn in templates:
        made, attempts = 0, 0
        while made < per_template and attempts < per_template * 60:
            attempts += 1
            text = v4.style(fn(), rng)
            key = " ".join(v4.words(text))
            if key in seen:
                rejected["duplicate"] += 1
                continue
            why = guard.reason(text)
            if why:
                rejected[why] += 1
                continue
            seen.add(key)
            rows.append({"text": text, "expected": label_of(tid), "template": tid})
            made += 1
    return rows


def stable_dev(template: str, fraction: float) -> bool:
    """Same answer in every corpus version, so no later head trains on an earlier dev template."""
    return int(hashlib.sha256(template.encode()).hexdigest()[:8], 16) % 1000 < fraction * 1000


def build(test_path: Path, out: Path, seed: int = 20261004, per_template: int = 30, dev_fraction: float = .25,
          inherit_split: Path | None = None) -> dict:
    """``inherit_split``: an earlier corpus whose template splits are kept (its dev stays dev)."""
    test_raw = test_path.read_bytes()
    guard = v4.TestGuard([json.loads(line)["text"] for line in test_raw.decode("utf-8").splitlines() if line.strip()])
    rng = random.Random(seed)
    seen, rejected, rows = set(), Counter(), []
    for label, factory in v4.LABELS.items():
        rows += _generate(rng, guard, factory(rng), lambda _t, lab=label: lab, per_template, seen, rejected)
    rows += _generate(rng, guard, abstain_context(rng), lambda _t: "abstain", per_template, seen, rejected)
    rows += _generate(rng, guard, numbers_not_math(rng), NUMBER_LABELS.get, per_template, seen, rejected)
    templates = sorted({r["template"] for r in rows})
    inherited = {}
    if inherit_split is not None:
        for line in inherit_split.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                inherited[row["template"]] = row["split"]
    dev_templates = {t for t in templates
                     if inherited.get(t) == "dev" or (t not in inherited and stable_dev(t, dev_fraction))}
    for row in rows:
        row["split"] = "dev" if row["template"] in dev_templates else "train"
        row["augmentation"] = "none"
    augmented = []
    for split in ("train", "dev"):
        pool = [r for r in rows if r["split"] == split]
        for row in rng.sample(pool, len(pool) // 4):  # a preamble before the real request
            text = v4.style(rng.choice(PREAMBLES) + row["text"].lower(), rng)
            if guard.reason(text) is None:
                augmented.append({**row, "text": text, "augmentation": "preamble"})
        for _ in range(len(pool) // 4):  # contrast: the request that counts is the second one
            a, b = rng.sample(pool, 2)
            if a["expected"] == b["expected"]:
                continue
            text = v4.style(rng.choice(CONTRASTS).format(x=a["text"].lower().rstrip("?"), y=b["text"].lower()), rng)
            if guard.reason(text) is None:
                augmented.append({"text": text, "expected": b["expected"], "template": b["template"],
                                  "split": split, "augmentation": "contrast"})
    rows += augmented
    rng.shuffle(rows)
    out.mkdir(parents=True, exist_ok=True)
    data = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    (out / "corpus.jsonl").write_text(data, encoding="utf-8", newline="\n")
    manifest = {"format": "hyd-route-corpus-v5/1", "seed": seed, "rows": len(rows),
                "labels": dict(Counter(r["expected"] for r in rows)), "splits": dict(Counter(r["split"] for r in rows)),
                "augmentations": dict(Counter(r["augmentation"] for r in rows)), "templates": len(templates),
                "dev_templates": sorted(dev_templates), "inherited_split_from": str(inherit_split) if inherit_split else None,
                "rejected": dict(rejected),
                "decontaminated_against_sha256": hashlib.sha256(test_raw).hexdigest(),
                "corpus_sha256": hashlib.sha256(data.encode()).hexdigest(),
                "generator_sha256": hashlib.sha256(b"".join(Path(m.__file__).read_bytes().replace(b"\r\n", b"\n")
                                                            for m in (v4, __import__(__name__)))).hexdigest(),
                "rights": "proprietary-hydra-authored", "synthetic": True}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
                                       newline="\n")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", type=Path, default=Path("data/private/hyd-test-v3/test.jsonl"))
    parser.add_argument("--out", type=Path, default=Path("data/hyd-route-corpus-v5"))
    parser.add_argument("--seed", type=int, default=20261004)
    parser.add_argument("--inherit-split", type=Path, default=Path("data/hyd-route-corpus-v4/corpus.jsonl"))
    args = parser.parse_args()
    print(json.dumps(build(args.test, args.out, args.seed, inherit_split=args.inherit_split), indent=2,
                     ensure_ascii=False))
