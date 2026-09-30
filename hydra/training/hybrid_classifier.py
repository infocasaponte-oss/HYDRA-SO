"""Safety-first hybrid decision classifier for HYDRA."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from hydra.training.specialists import TextClassifier


@dataclass(frozen=True)
class HybridDecision:
    label: str
    confidence: float
    source: str


_ABSTAIN = (r"\b(resuelve esto|decide esto|hazlo|aprueba esto)\b", r"sin contexto", r"no aparece")
_HIGH_RISK = (r"pago urgente", r"ejecut(ar|a) .*m[eé]dic", r"cerr(a|ar) .*cuenta", r"cambia(r)? .*firewall", r"concede .*acceso")
_PRIVACY = (r"historial", r"direcci[oó]n de correo", r"grabaci[oó]n", r"datos personales", r"tercero")
_SECURITY = (r"contrase[nñ]a", r"fraude", r"carga maliciosa", r"enviar archivos fuera", r"malware", r"vulnerabilidad")
_CODING = (r"consulta sql", r"expresi[oó]n regular", r"parametriz")
_REASONING = (r"problema matem[aá]tico", r"demuestra", r"razona")
_RESEARCH = (r"investiga", r"fuentes", r"documentaci[oó]n")
_TOOL = (r"ejecuta", r"comando", r"archivos del proyecto")
_VISION = (r"imagen", r"fotograf[ií]a", r"documento visual")
_CHAT = (r"saluda", r"felicit", r"conversaci[oó]n")


def _hit(patterns: tuple[str, ...], text: str) -> bool:
    return any(re.search(p, text, re.I) for p in patterns)


class HybridClassifier:
    def __init__(self, statistical: TextClassifier) -> None:
        self.statistical = statistical

    def predict(self, text: str) -> HybridDecision:
        text = text.strip()
        if not text or _hit(_ABSTAIN, text):
            return HybridDecision("abstain", 0.99, "policy")
        if _hit(_HIGH_RISK, text):
            return HybridDecision("high_risk_review", 0.98, "policy")
        if _hit(_PRIVACY, text) and not _hit(_SECURITY, text):
            return HybridDecision("privacy", 0.94, "policy")
        if _hit(_SECURITY, text):
            return HybridDecision("security", 0.96, "policy")
        for label, patterns in (("coding", _CODING), ("reasoning", _REASONING), ("research", _RESEARCH),
                                ("tool_use", _TOOL), ("vision", _VISION), ("chat", _CHAT)):
            if _hit(patterns, text):
                return HybridDecision(label, 0.93, "policy")
        label, confidence = self.statistical.predict(text)
        return HybridDecision(label, confidence, "statistical")


def evaluate(classifier: HybridClassifier, rows: list[dict[str, Any]]) -> dict[str, Any]:
    correct = sum(classifier.predict(r["text"]).label == r["expected"] for r in rows)
    return {"rows": len(rows), "correct": correct, "accuracy": round(correct / len(rows), 4),
            "promotion_eligible": correct / len(rows) >= 0.90}
