# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""Versioned laboratory bridge; produces loadable candidates, never activates them."""
from __future__ import annotations

import hashlib
import json
import math
import time
from pathlib import Path

from hydra.core.atomic import write_text_atomic
from hydra.hyd.controller import HydController, implementation_digest
from hydra.hyd.engine import HydEngine
from hydra.hyd.model import CandidateRanker
from hydra.router.decision_contract import CRITERIA

CONTRACT_VERSION = "hyd-routing/1"


def contract() -> dict:
    criteria_hash = hashlib.sha256(json.dumps(CRITERIA, sort_keys=True, ensure_ascii=False,
                                             separators=(",", ":")).encode()).hexdigest()
    return {"format": CONTRACT_VERSION, "criteria": CRITERIA, "criteria_sha256": criteria_hash,
            "supported_model": "hyd-candidate-ranker/1", "supported_features": "hyd-hash-words-characters/1",
            "technical_abstention_distinct_from_label": True, "authority_enabled": False}


def calibrator():
    try:
        from hyd_calibrator import calibrate, evaluation, contract as external
    except ImportError as error:
        raise RuntimeError("Install the standalone hyd-calibrator wheel first; see docs/HYD_TOOLS.md") from error
    if external.CRITERIA != CRITERIA:
        raise ValueError("calibrator routing contract differs from HYDRA")
    return calibrate, evaluation


class RoutingAdapter:
    """Observation-only adapter preserving semantic choice and technical abstention."""

    def __init__(self, model_dir: Path):
        _, evaluation = calibrator()
        self.model_dir = Path(model_dir)
        self.ranker = CandidateRanker.load(self.model_dir / "model.json")
        self.calibration = evaluation.load_calibration(self.model_dir / "calibration.json", self.ranker)
        self.engine = HydEngine(self.ranker, self.calibration["min_confidence"], self.calibration["min_margin"])
        self.authority_enabled = False

    def decide(self, state: str, deadline: float | None = None) -> dict:
        if not isinstance(state, str) or not state.strip():
            raise ValueError("routing requires nonempty text")
        answer = self.engine.decide(state, {"task": {"type": "choice", "criteria": CRITERIA}}, deadline)["answers"]["task"]
        abstain_all = self.calibration.get("abstain_all", False)
        if type(abstain_all) is not bool:
            raise ValueError("invalid abstain_all")
        if abstain_all:
            answer = {**answer, "abstained": True, "reason": "calibration_target_unmet"}
        if deadline is not None and time.monotonic() >= deadline:
            raise TimeoutError("routing deadline exceeded")
        probabilities = answer["probabilities"]
        if (set(probabilities) != set(CRITERIA) or any(not math.isfinite(p) or not 0 <= p <= 1 for p in probabilities.values())
                or not math.isclose(math.fsum(probabilities.values()), 1, abs_tol=1e-9)):
            raise ValueError("invalid routing probabilities")
        return {"contract": CONTRACT_VERSION, "choice": answer["choice"],
                "probabilities": probabilities, "selection_probability": answer["selection_probability"],
                "margin": answer["margin"], "abstained": answer["abstained"], "reason": answer["reason"],
                "model_revision": self.ranker.revision,
                "calibration_revision": hashlib.sha256((self.model_dir / "calibration.json").read_bytes()).hexdigest(),
                "authority_enabled": False}


def export_runtime(model_dir: Path, out: Path) -> dict:
    """Bind a qualified standalone candidate to this runtime; preserve original artifacts."""
    adapter = RoutingAdapter(model_dir)
    cal = adapter.calibration
    if cal.get("format") != "hyd-standalone-calibration/1" or cal.get("target_met") is not True or cal.get("abstain_all") is not False:
        raise ValueError("only a qualified standalone calibration can be exported")
    if cal.get("train_overlap_checked") is not True:
        raise ValueError("verified training source and overlap check required")
    selected = cal.get("selected")
    if (not isinstance(selected, dict) or selected.get("min_confidence") != cal["min_confidence"]
            or selected.get("min_margin") != cal["min_margin"]
            or selected.get("accuracy_wilson_lower_95", 0) < cal["target_wilson_lower_95"]
            or selected.get("coverage", 0) < cal["minimum_coverage"]):
        raise ValueError("calibration target evidence is inconsistent")
    out = Path(out)
    if out.resolve() == Path(model_dir).resolve() or out.exists():
        raise ValueError("export requires a new output directory")
    native = {"format": "hyd-calibration/1", "model_sha256": adapter.ranker.revision,
              "implementation_sha256": implementation_digest(), "temperature": adapter.ranker.temperature,
              "dataset_sha256": cal["dataset_sha256"], "criteria": CRITERIA,
              "min_confidence": cal["min_confidence"], "min_margin": cal["min_margin"],
              "status": "SHADOW_ONLY", "independent_test": False,
              "source_calibration_sha256": adapter.decide("Export compatibility probe")["calibration_revision"],
              "contract": contract(), "metrics": selected,
              "limitation": "Qualified on calibration only. External evaluation and release review required."}
    out.mkdir(parents=True)
    # Bytes are kept identical: serialization would change the model revision.
    (out / "model.json").write_bytes((Path(model_dir) / "model.json").read_bytes())
    write_text_atomic(out / "calibration.json", json.dumps(native, indent=2, allow_nan=False))
    controller = HydController(out / "model.json", out / "calibration.json")
    if controller.authority.enabled:
        raise ValueError("export unexpectedly granted authority")
    return {"output": str(out), "contract": contract(), "model_sha256": adapter.ranker.revision,
            "authority_enabled": False, "activated": False}
