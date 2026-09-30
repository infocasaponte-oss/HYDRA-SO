# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""Empirical exact-task reliability, not token confidence or production certification."""
import argparse
import asyncio
import json
import math
from pathlib import Path

import httpx
from hydra.training.evaluate_corpus import candidate_hash, model_identity
from hydra.training.verified_corpus import sha256


def wilson(successes, total):
    if total <= 0:
        raise ValueError("nonempty sample required")
    z = 1.959963984540054
    p = successes / total
    divisor = 1 + z*z/total
    center = (p + z*z/(2*total))/divisor
    delta = z*math.sqrt(p*(1-p)/total + z*z/(4*total*total))/divisor
    return [max(0, center-delta), min(1, center+delta)]


def same_json(actual, expected):
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(same_json(actual[k], expected[k]) for k in expected)
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(same_json(a, b) for a,b in zip(actual, expected))
    return actual == expected


def check(row, text):
    expected = row["verification"]["expected"]
    if row["verification"]["kind"] != "json":
        return text.strip() == expected
    try:
        return same_json(json.loads(text), json.loads(expected))
    except (ValueError, TypeError):
        return False


async def evaluate(model, corpus, output, manifest, split="calibration"):
    if split not in ("validation", "calibration"):
        raise ValueError("reliability uses development or separate calibration only")
    data = corpus / f"{split}.jsonl"
    dataset_manifest = json.loads((corpus / "manifest.json").read_text())
    if sha256(data) != dataset_manifest["files"][data.name]["sha256"]:
        raise ValueError("dataset changed")
    rows = [json.loads(line) for line in data.read_text(encoding="utf-8").splitlines()]
    artifact = candidate_hash(manifest)
    options = dict(temperature=0, seed=42, num_ctx=2048, num_predict=96, num_gpu=99)
    report = dict(model=model, artifact_sha256=artifact, dataset_sha256=sha256(data), split=split,
                  sampling=options, cases=[], approved=False, independent_test=False,
                  scope="synthetic exact-task empirical success, not probability that arbitrary responses are true")
    def save():
        output.parent.mkdir(parents=True, exist_ok=True)
        tmp = output.with_suffix(".tmp")
        tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(output)
    async with httpx.AsyncClient(base_url="http://127.0.0.1:11434", timeout=120) as client:
        identity = await model_identity(client, model, artifact)
        report["identity"] = identity
        for row in rows:
            case = dict(id=row["id"], family=row["family"], passed=False)
            try:
                r = await client.post("/api/chat", json=dict(model=model, stream=False,
                      messages=row["messages"][:-1], options=options, keep_alive="2m"))
                r.raise_for_status()
                case["output"] = r.json()["message"]["content"]
                case["passed"] = check(row, case["output"])
            except Exception as e:
                case["error"] = type(e).__name__
            report["cases"].append(case)
            save()
        if await model_identity(client, model, artifact) != identity:
            raise ValueError("model changed")
    cases = report["cases"]
    correct = sum(c["passed"] for c in cases)
    report.update(correct=correct, total=len(cases), accuracy=correct/len(cases), wilson95=wilson(correct,len(cases)), complete=True)
    report["families"] = {}
    for family in sorted({c["family"] for c in cases}):
        selected = [c for c in cases if c["family"] == family]
        n = sum(c["passed"] for c in selected)
        report["families"][family] = dict(correct=n, total=len(selected), accuracy=n/len(selected), wilson95=wilson(n,len(selected)))
    save()
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True)
    p.add_argument("--corpus", type=Path, default=Path("data/hydra-instruction-v4"))
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--split", choices=["validation", "calibration"], default="calibration")
    a = p.parse_args()
    result = asyncio.run(evaluate(a.model, a.corpus, a.output, a.manifest, a.split))
    print(json.dumps({k: v for k,v in result.items() if k not in ("cases", "identity")}, indent=2))
