# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""Fresh versioned release assessment. Never overwrites reference evidence or promotes."""
import argparse
import asyncio
import json
from pathlib import Path

from hydra.training.generation_reliability import evaluate as quality
from hydra.training.evaluate_instruction_v2 import evaluate as instructions
from hydra.training.evaluate_corpus import evaluate as coding
from hydra.training.evidence_io import write_json
from scripts.evaluate_external_holdout import evaluate as external


async def run(output:Path, version=5):
    if version not in (5,6):
        raise ValueError("unsupported candidate")
    output.mkdir(parents=True,exist_ok=False)
    status=dict(complete=False,approved=False,stage="development")
    def stage(name):
        status["stage"]=name
        write_json(output/"status.json",status)
    model=f"hydra-instruction-v{version}:latest"
    manifest=Path(f"models/hydra-instruction-v{version}/build-manifest.json")
    corpus=Path(f"data/hydra-instruction-v{version}")
    results={}
    stage("development")
    results[f"v{version}_development"]=await quality(model,corpus,output/f"instruction-v{version}-v{version}-development.json",manifest,"validation")
    stage("calibration")
    results[f"v{version}_calibration"]=await quality(model,corpus,output/f"instruction-v{version}-generation-calibration.json",manifest,"calibration")
    stage("raw_instructions")
    results[f"v{version}_frozen_instruction"]=await instructions(model,output/f"instruction-v{version}-original-contract.json",manifest,corpus)
    stage("configured_instructions")
    results[f"v{version}_typed_state"]=await instructions(model,output/f"instruction-v{version}-typed-state-contract.json",manifest,corpus,True)
    stage("coding")
    results[f"v{version}_coding"]=await coding(model,Path("data/hydra-corpus-v1"),output/f"instruction-v{version}-coding-regression.json",build_manifest=manifest)
    stage("external_holdout")
    await external(output/f"external-evaluation-v{version}.json",version)
    compact={k:{field:v[field] for field in ("accuracy","score","correct","total","wilson95","complete","protocol") if field in v}
             for k,v in results.items()}
    compact.update(approved=False,independent_test=False,serving_model_changed=False)
    write_json(output/f"instruction-v{version}-summary.json",compact)
    status.update(complete=True,stage="evaluations_complete_requires_tests_soak_and_human_review")
    write_json(output/"status.json",status)
    print(json.dumps(compact,indent=2))


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--version",type=int,choices=[5,6],default=5)
    args=parser.parse_args()
    asyncio.run(run(args.output,args.version))
