# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""Verifier v2: deterministic checks -> tool validation -> evidence validation -> model critic."""

from __future__ import annotations

import ast
import json
import re
from typing import Any

from pydantic import BaseModel, Field

from hydra.blackboard.state import BlackboardState
from hydra.core.contracts import HydraRequest, RoutingDecision, TaskType
from hydra.verification.math_check import answer_matches, expected_value

REFUSAL = re.compile(
    r"^\s*(i can'?t|i cannot|no puedo|lo siento|sorry,? (but )?i|i'?m sorry|i apologi[sz]e)|"
    r"\b(no tengo (información|informacion|datos|acceso)|i (don'?t|do not) have (information|access|data)|"
    r"(could|can) you (please )?provide more (context|details)|¿podrías proporcionar(me)? más (contexto|detalles)|"
    r"as an ai(,)? i (can'?t|cannot|don'?t))", re.I)
PY_BLOCK = re.compile(r"```(?:python|py)\s*\n(.*?)```", re.S)
JSON_BLOCK = re.compile(r"```json\s*\n(.*?)```", re.S)


class Check(BaseModel):
    layer: str
    name: str
    passed: bool
    score: float
    detail: str = ""


class VerificationResult(BaseModel):
    passed: bool
    score: float
    verified: bool
    checks: list[Check] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    tool_validation: float | None = None
    evidence: float | None = None
    critic: float | None = None
    independent: bool = False
    """True when a layer beyond format checks (tool, evidence, critic) took part."""

    @property
    def confidence_signal(self) -> float:
        """Format checks alone prove little: cap their contribution to confidence."""
        return self.score if self.independent else min(self.score, 0.65)


class Verifier:
    def __init__(self, pass_threshold: float = 0.6) -> None:
        self.pass_threshold = pass_threshold

    def deterministic(self, answer: str, request: HydraRequest, route: RoutingDecision) -> list[Check]:
        checks = [Check(layer="deterministic", name="non_empty", passed=bool(answer.strip()),
                        score=1.0 if answer.strip() else 0.0)]
        refused = bool(REFUSAL.search(answer[:600]))
        checks.append(Check(layer="deterministic", name="answers_the_question", passed=not refused,
                            score=0.0 if refused else 1.0,
                            detail="the model declined or did not answer" if refused else ""))
        if route.task_type == TaskType.CODING:
            for i, block in enumerate(PY_BLOCK.findall(answer)):
                try:
                    ast.parse(block)
                    checks.append(Check(layer="deterministic", name=f"python_syntax_{i}", passed=True, score=1.0))
                except SyntaxError as exc:
                    checks.append(Check(layer="deterministic", name=f"python_syntax_{i}", passed=False,
                                        score=0.0, detail=f"line {exc.lineno}: {exc.msg}"))
        wants_json = "json" in request.last_user_text.lower() and "```json" in answer
        if wants_json:
            for i, block in enumerate(JSON_BLOCK.findall(answer)):
                try:
                    json.loads(block)
                    checks.append(Check(layer="deterministic", name=f"json_{i}", passed=True, score=1.0))
                except json.JSONDecodeError as exc:
                    checks.append(Check(layer="deterministic", name=f"json_{i}", passed=False, score=0.0,
                                        detail=str(exc)))
        return checks

    @staticmethod
    def numeric(answer: str, request: HydraRequest) -> Check | None:
        """Arithmetic in the question -> recompute it exactly and compare."""
        exp = expected_value(request.last_user_text)
        if exp is None:
            return None
        expr, value = exp
        ok = answer_matches(answer, value)
        shown = int(value) if value.is_integer() else value
        return Check(layer="math", name="numeric_check", passed=ok, score=1.0 if ok else 0.0,
                     detail="" if ok else f"{expr} = {shown}, not found in the answer")

    @staticmethod
    def tool_validation(state: BlackboardState, model_id: str | None = None) -> Check | None:
        def mine(r: dict) -> bool:
            return model_id is None or str(r.get("requested_by", "")).endswith(f":{model_id}")

        results = [r for r in state.tool_results if mine(r)]
        failures = [f for f in state.failures if f.get("type", "").startswith("tool") and mine(f)]
        if not results and not failures:
            return None
        ok = sum(1 for r in results if r.get("success", True))
        failed_tools = len(failures)
        total = ok + failed_tools
        if total == 0:
            return None
        score = ok / total
        return Check(layer="tool", name="tool_success_rate", passed=score >= 0.5, score=score,
                     detail=f"{ok}/{total} tool calls succeeded")

    @staticmethod
    def evidence(state: BlackboardState, claim_id: str | None = None) -> Check | None:
        evs = [e for e in state.evidence.values() if claim_id is None or e.claim_id == claim_id]
        if not evs:
            return None
        sup = sum(e.strength for e in evs if e.supports)
        con = sum(e.strength for e in evs if not e.supports)
        score = sup / (sup + con) if (sup + con) else 0.5
        return Check(layer="evidence", name="evidence_balance", passed=score >= 0.5, score=score,
                     detail=f"support={sup:.2f} against={con:.2f}")

    @staticmethod
    def critic(state: BlackboardState, claim_id: str | None = None) -> tuple[Check | None, list[str]]:
        critiques = [c for c in state.critiques if claim_id is None or c.get("target") == claim_id]
        if not critiques:
            return None, []
        latest = critiques[-1]
        score = float(latest.get("score", 0.5))
        verdict = latest.get("verdict", "pass")
        issues = [str(i) for i in latest.get("issues", [])]
        return Check(layer="critic", name="model_critic", passed=verdict != "fail" and score >= 0.5,
                     score=score, detail="; ".join(issues)[:500]), issues

    def verify(self, request: HydraRequest, route: RoutingDecision, state: BlackboardState,
               answer: str, claim_id: str | None = None, model_id: str | None = None) -> VerificationResult:
        checks = self.deterministic(answer, request, route)
        tool = self.tool_validation(state, model_id)
        ev = self.evidence(state, claim_id)
        crit, issues = self.critic(state, claim_id)
        math = self.numeric(answer, request)
        checks += [c for c in (math, tool, ev, crit) if c is not None]

        hard_fail = any(not c.passed for c in checks if c.layer in ("deterministic", "math"))
        layer_scores: dict[str, list[float]] = {}
        for c in checks:
            layer_scores.setdefault(c.layer, []).append(c.score)
        weights = {"deterministic": 0.3, "math": 0.4, "tool": 0.3, "evidence": 0.2, "critic": 0.2}
        num = sum(weights[layer] * (sum(v) / len(v)) for layer, v in layer_scores.items())
        den = sum(weights[layer] for layer in layer_scores)
        score = round(num / den, 4) if den else 0.0

        uncertainties = list(issues)
        uncertainties += [f"{c.name}: {c.detail}" for c in checks if not c.passed and c.detail and c.layer != "critic"]

        passed = not hard_fail and score >= self.pass_threshold
        # "verified" means an independent layer beyond format checks confirmed it.
        # Tool execution proves retrieval/execution succeeded, not that the answer is correct.
        independent = [c for c in checks if c.layer in ("math", "evidence", "critic")]
        verified = passed and bool(independent) and all(c.passed for c in independent)
        return VerificationResult(
            passed=passed, score=score, verified=verified, checks=checks, uncertainties=uncertainties,
            tool_validation=tool.score if tool else None, evidence=ev.score if ev else None,
            critic=crit.score if crit else None, independent=bool(independent),
        )


def summarize(result: VerificationResult) -> dict[str, Any]:
    return result.model_dump()
