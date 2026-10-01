# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""Isolated Studio for the trained 1.5B GGUF and calibrated Kev shadow."""
import argparse
from pathlib import Path
import uvicorn
from hydra.api.main import create_app
from hydra.core.config import Settings


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=18084)
    parser.add_argument("--version", choices=["3", "4", "5", "6", "7", "8"], default="3")
    parser.add_argument("--backend", choices=["ollama", "llamacpp"], default="ollama")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    suffix = "-llamacpp" if args.backend == "llamacpp" else ""
    settings = Settings(models_config=root / f"config/models.hydra-instruction-v{args.version}{suffix}.yaml", offline=False,
                        evaluation_candidate_version=int(args.version) if int(args.version)>=6 else 5,
                        data_dir=root / f"runtime/studio-candidate-v{args.version}{suffix}/state", capture=False, public_web_enabled=True,
                        deterministic_first=True,
                        budget_time_scale=6, decision_shadow_endpoint="http://127.0.0.1:8009",
                        decision_shadow_timeout_s=5, decision_full_contract=True,
                        decision_calibrator_path=root / "models/kev-hydra-v2-r1/router-calibrator-precision-v1.json",
                        decision_local_model_path=None, decision_authority_evidence_path=None)
    uvicorn.run(create_app(settings), host="127.0.0.1", port=args.port)
