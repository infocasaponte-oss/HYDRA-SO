# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""Project tool launcher and dependency inventory; no automatic training or deployment."""
import argparse
import importlib.util
from importlib.metadata import PackageNotFoundError, version
import json
import shutil
import subprocess
import sys

TOOLS = {
    "corpus-audit": ("hydra.training.corpus_preflight", "Audit JSONL/gzip shards, hashes and split leakage"),
    "prepare-4b": ("hydra.training.prepare_4b", "Prepare and optionally meta-check the 3.98B architecture"),
    "hyd-lab": ("hydra.hyd.tools", "Local queued validation, snapshots, calibration and shadow export"),
    "hyd-calibrator": ("hyd_calibrator", "Standalone admitted-data training, calibration and reports"),
    "base-trainer": ("hydra.training.base_pretrain", "Existing 30M/125M training; not a validated 4B backend"),
    "base-tokenizer": ("hydra.training.base_tokenizer", "Train tokenizer on admitted training documents"),
}
DEPENDENCIES = {
    "hyd-calibrator": "standalone Hyd experiments",
    "numpy": "ranker and base token files",
    "torch": "training and optional architecture meta-check",
    "transformers": "model architecture and training",
    "sentencepiece": "base tokenizer and actual token counts",
    "safetensors": "training weights",
    "pyarrow": "optional Parquet ingestion",
    "pytest": "verification",
    "ruff": "source checks",
}


def inventory():
    packages = {}
    for name, purpose in DEPENDENCIES.items():
        try:
            installed = version(name)
        except PackageNotFoundError:
            installed = None
        packages[name] = {"version": installed, "purpose": purpose}
    tools = {}
    for name, (module, description) in TOOLS.items():
        try:
            available = importlib.util.find_spec(module) is not None
        except (ImportError, ModuleNotFoundError):
            available = False
        tools[name] = {"module": module, "import_discoverable": available, "description": description}
    return {"format": "hydra-project-toolkit/1", "python": sys.version.split()[0],
            "tools": tools, "dependencies": packages,
            "executables": {name: shutil.which(name) is not None for name in ("git", "bun", "node", "nvidia-smi")},
            "availability_basis": "distribution metadata and module discovery; not execution or backend compatibility",
            "remote_services": "OAuth, Supabase and opinion providers not probed",
            "four_b_training_backend": "pending validation", "automatic_install": False,
            "automatic_launch": False, "authority_enabled": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tool", choices=("doctor", *TOOLS), nargs="?", default="doctor")
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.tool == "doctor":
        if args.arguments:
            parser.error("doctor takes no additional arguments")
        print(json.dumps(inventory(), indent=2, allow_nan=False))
        return 0
    module = TOOLS[args.tool][0]
    arguments = args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
    # A bare tool selection shows its help. Only explicit arguments execute work.
    return subprocess.run([sys.executable, "-m", module, *(arguments or ["--help"])], check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
