# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""Compare GGUF candidate with deployed baseline; never promotes either model."""
import asyncio
import json
from pathlib import Path

import httpx
from hydra.training.generation_reliability import evaluate as reliability
from hydra.training.evaluate_instruction_v2 import evaluate as instruction
from hydra.training.evaluate_corpus import evaluate as coding


async def main():
    corpus = Path("data/hydra-instruction-v4")
    results = {}
    for version in (3,4):
        name = f"hydra-instruction-v{version}:latest"
        manifest = Path(f"models/hydra-instruction-v{version}/build-manifest.json")
        results[f"v{version}_development"] = await reliability(name,corpus,
            Path(f"docs/evidence/instruction-v{version}-v4-development.json"), manifest, "validation")
        if version == 3:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post("http://127.0.0.1:11434/api/generate",json=dict(model=name,keep_alive=0))
                r.raise_for_status()
    manifest = Path("models/hydra-instruction-v4/build-manifest.json")
    results["v4_calibration"] = await reliability("hydra-instruction-v4:latest",corpus,
        Path("docs/evidence/instruction-v4-generation-calibration.json"),manifest,"calibration")
    results["v4_frozen_instruction"] = await instruction("hydra-instruction-v4:latest",
        Path("docs/evidence/instruction-v4-original-contract.json"),manifest,corpus)
    results["v4_coding"] = await coding("hydra-instruction-v4:latest",Path("data/hydra-corpus-v1"),
        Path("docs/evidence/instruction-v4-coding-regression.json"),build_manifest=manifest)
    compact = {k:{field:v[field] for field in ("accuracy","score","correct","total","wilson95","complete") if field in v}
               for k,v in results.items()}
    compact.update(approved=False, independent_test=False, serving_model_changed=False)
    Path("docs/evidence/instruction-v4-summary.json").write_text(json.dumps(compact,indent=2),encoding="utf-8")
    print(json.dumps(compact,indent=2))


if __name__ == "__main__":
    asyncio.run(main())
