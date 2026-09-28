# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""Evaluate a real Ollama model on the frozen coding holdout using Docker."""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
from pathlib import Path

import httpx

from hydra.tools.sandbox import DockerSandbox
from hydra.training.verified_corpus import sha256


async def evaluate(model: str, corpus: Path, output: Path, limit: int = 0) -> dict:
    dataset = corpus/"test.jsonl"
    manifest = json.loads((corpus/"manifest.json").read_text(encoding="utf-8"))
    if sha256(dataset) != manifest["files"][dataset.name]["sha256"]:
        raise ValueError("holdout hash mismatch")
    rows = [json.loads(line) for line in dataset.read_text(encoding="utf-8").splitlines()]
    if limit:
        rows = rows[:limit]
    if not rows:
        raise ValueError("empty holdout")
    sandbox = DockerSandbox()
    result = {"model":model,"dataset_sha256":sha256(dataset),"subset":bool(limit),
              "approved":False,"cases":[]}
    output.parent.mkdir(parents=True,exist_ok=True)
    def save():
        output.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding="utf-8")
    async with httpx.AsyncClient(base_url="http://127.0.0.1:11434",timeout=180) as client:
        show = await client.post("/api/show",json={"model":model})
        show.raise_for_status()
        result["model_info"] = show.json().get("details",{})
        for row in rows:
            start = time.perf_counter()
            case = {"id":row["id"],"family":row["family"],"passed":False}
            try:
                response = await client.post("/api/chat",json={"model":model,"stream":False,
                    "messages":row["messages"][:-1],
                    "options":{"temperature":0,"seed":42,"num_predict":256,"num_ctx":2048}})
                response.raise_for_status()
                payload = response.json()
                answer = payload["message"]["content"]
                match = re.search(r"```(?:python|py)?\s*\n(.*?)```",answer,re.S)
                code = match.group(1) if match else answer
                tests = "\n".join(f"assert solve({c['input']!r}) == {c['expected']!r}"
                                  for c in row["verification"]["cases"])
                execution = await sandbox.execute_python(code+"\n"+tests,timeout=15)
                case.update(passed=execution.exit_code == 0,output=answer,
                            stderr=execution.stderr[-1000:],tokens=payload.get("eval_count"))
            except Exception as exc:
                case["error"] = f"{type(exc).__name__}: {exc}"
            case["latency_ms"] = round((time.perf_counter()-start)*1000,1)
            result["cases"].append(case)
            result["score"] = sum(c["passed"] for c in result["cases"])/len(result["cases"])
            save()
    result["status"] = "EVALUATED_SUBSET" if limit else "EVALUATED"
    save()
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--model",required=True)
    p.add_argument("--corpus",type=Path,default=Path("data/hydra-corpus-v1"))
    p.add_argument("--output",type=Path,default=Path("data/evaluations/holdout.json"))
    p.add_argument("--limit",type=int,default=0)
    args = p.parse_args()
    print(json.dumps(asyncio.run(evaluate(args.model,args.corpus,args.output,args.limit)),indent=2))
