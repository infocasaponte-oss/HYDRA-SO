# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""Numeric verification for arithmetic questions (Verifier v2: 'maths -> symbolic/numeric check')."""

from __future__ import annotations

import ast
import operator
import re

_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv, ast.USub: operator.neg, ast.UAdd: operator.pos,
}

ARITH = re.compile(r"(-?\d+(?:\.\d+)?(?:\s*[-+*/×x÷^%]\s*-?\d+(?:\.\d+)?)+)")
NUM = re.compile(r"-?\d+(?:[.,]\d+)?")


def safe_arith(expr: str) -> float | int | None:
    expr = expr.replace("×", "*").replace("x", "*").replace("÷", "/").replace("^", "**")

    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            if isinstance(node.op, ast.Pow) and abs(ev(node.right)) > 100:
                raise ValueError("exponent too large")
            return _OPS[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](ev(node.operand))
        raise ValueError("unsupported")

    try:
        return ev(ast.parse(expr.strip(), mode="eval"))
    except Exception:
        return None


def expected_value(question: str) -> tuple[str, float] | None:
    """The arithmetic expression in a question and its exact value, if any."""
    m = ARITH.search(question)
    if not m:
        return None
    value = safe_arith(m.group(1))
    return (m.group(1).strip(), float(value)) if value is not None else None


def answer_matches(answer: str, value: float, rel: float = 1e-6) -> bool:
    for n in NUM.findall(answer.replace(" ", "").replace(" ", "")):
        try:
            x = float(n.replace(",", "."))
        except ValueError:
            continue
        if abs(x - value) <= max(rel * abs(value), 1e-9):
            return True
    return False
