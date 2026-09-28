# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
from __future__ import annotations

import re

_HINTS = {
    "es": ({"que", "para", "como", "con", "gracias", "hola", "buenos"}, "áéíóúñ¿¡"),
    "en": ({"the", "and", "with", "for", "hello", "thanks", "what", "how"}, ""),
    "fr": ({"le", "la", "les", "avec", "pour", "bonjour", "merci"}, "àâçéèêëîïôùûüÿœ"),
    "de": ({"der", "die", "das", "und", "mit", "für", "hallo", "danke"}, "äöüß"),
    "pt": ({"com", "para", "olá", "obrigado", "como"}, "ãõáéíóúç"),
    "it": ({"il", "gli", "con", "per", "ciao", "grazie", "come"}, "àèéìíîòóù"),
}


def detect_language(text: str) -> str:
    clean = text.lower()
    tokens = set(re.findall(r"[a-zA-ZÀ-ÿ]+", clean))
    scores = {}
    for lang, (words, chars) in _HINTS.items():
        scores[lang] = sum(word in tokens for word in words) + sum(0.75 for ch in chars if ch in clean)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "unknown"
