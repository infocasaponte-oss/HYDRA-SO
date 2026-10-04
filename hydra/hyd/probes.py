# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""Controlled capability probes for Hyd routing, built only from development data.

Each probe rewrites development requests whose label is known and keeps (or deterministically
derives) the expected label, so a model can be measured on what it should handle without touching
the frozen human test: unseen synonyms, heavy typos, a distracting preamble, shuffled word order
(a sensitivity check, not a target), and negation/contrast ("no te pido X; lo que necesito es Y").
"""
from __future__ import annotations

import random
from collections import defaultdict

SYNONYMS = {"busca": "localiza", "búscame": "encuéntrame", "foto": "instantánea", "imagen": "estampa",
            "captura": "pantallazo", "código": "programa", "borra": "suprime", "elimina": "quita",
            "contraseña": "clave", "archivo": "fichero", "carpeta": "directorio", "escribe": "redacta",
            "escríbeme": "redáctame", "precio": "coste", "datos": "información", "error": "fallo",
            "función": "rutina", "servidor": "máquina", "cuenta": "perfil", "mensaje": "recado",
            "explícame": "aclárame", "dime": "cuéntame", "haz": "realiza", "crea": "genera", "abre": "accede a",
            "ejecuta": "corre", "web": "página", "correo": "email", "móvil": "teléfono", "empresa": "compañía"}
PREAMBLES = ["ayer estuve toda la tarde peleándome con el ordenador, en fin, ",
             "mi hermana dice que soy un desastre con las fotos jaja, bueno a lo que iba: ",
             "te cuento que esta semana voy fatal de trabajo y de todo, ",
             "aunque no tenga nada que ver con lo de la contraseña del otro día, "]


def synonyms(text: str, rng: random.Random) -> str:
    return " ".join(SYNONYMS.get(word.lower(), word) for word in text.split())


def typos(text: str, rng: random.Random) -> str:
    words = text.split()
    for _ in range(3):
        i = rng.randrange(len(words))
        if len(words[i]) > 3:
            j = rng.randrange(1, len(words[i]) - 1)
            words[i] = words[i][:j] + words[i][j + 1:]
    return " ".join(words)


def preamble(text: str, rng: random.Random) -> str:
    return rng.choice(PREAMBLES) + text


def shuffled(text: str, rng: random.Random) -> str:
    words = text.split()
    rng.shuffle(words)
    return " ".join(words)


REWRITES = {"synonyms": synonyms, "typos": typos, "preamble": preamble, "shuffled_order": shuffled}


def build(rows: list[dict], labels: list[str], per_probe: int = 150, seed: int = 11) -> dict[str, list[dict]]:
    """Probe sets from labelled development rows: {probe: [{"text", "expected"}]}."""
    rng = random.Random(seed)
    sample = rng.sample(rows, min(per_probe, len(rows)))
    probes = {name: [{"text": fn(row["text"], rng), "expected": row["expected"]} for row in sample]
              for name, fn in REWRITES.items()}
    by_label = defaultdict(list)
    for row in rows:
        by_label[row["expected"]].append(row["text"])
    present = [label for label in labels if by_label[label]]
    negation = []
    for _ in range(per_probe):
        refused, wanted = rng.sample(present, 2)
        x, y = rng.choice(by_label[refused]), rng.choice(by_label[wanted])
        negation.append({"text": f"no te pido que {x.lower()}, eso ya está; lo que necesito es esto: {y}",
                         "expected": wanted})
    probes["negation"] = negation
    return probes
