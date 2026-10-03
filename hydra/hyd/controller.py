# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""In-process Hyd observer; authority binds model, features and calibration bytes."""
from __future__ import annotations

import hashlib
import asyncio
import json
import time
from pathlib import Path

from hydra.core.contracts import DecisionObservation, HydraRequest, TaskType
from hydra.hyd.engine import HydEngine
from hydra.hyd.model import CandidateRanker
from hydra.router.decision_authority import DecisionAuthority
from hydra.router.decision_contract import CRITERIA
from hydra.router.observer import policy_gate


class HydBusyError(RuntimeError):
    pass


def implementation_digest() -> str:
    """Hash of the code that computes probabilities, confidence and abstention. The controller
    (scheduling, telemetry) is excluded: changing it cannot alter a calibrated answer, so it must
    not silently invalidate calibration or authority evidence."""
    digest = hashlib.sha256()
    for name in ("model.py", "engine.py", "neural.py", "embedding.py"):
        digest.update(name.encode())
        digest.update(Path(__file__).with_name(name).read_bytes().replace(b"\r\n", b"\n"))
    return digest.hexdigest()


class HydController:
    model = "hyd-latest"

    FALLBACK_COOLDOWN_S = 60.0
    """After a backend failure the primary is skipped for this long, so a stopped encoder costs one
    failed connection per minute rather than one per request."""

    def __init__(self, model_path: Path, calibration_path: Path, evidence_path: Path | None = None,
                 fallback: HydController | None = None):
        metadata = json.loads(model_path.read_text(encoding="utf-8"))
        if metadata.get("format") == "hyd-contextual-ranker/1":
            from hydra.hyd.neural import ContextRanker
            ranker = ContextRanker.load(model_path)
        elif metadata.get("format") == "hyd-embedding-head/1":
            from hydra.hyd.embedding import EmbeddingRanker
            ranker = EmbeddingRanker.load(model_path)
        else:
            ranker = CandidateRanker.load(model_path)
        raw = calibration_path.read_bytes()
        calibration = json.loads(raw)
        if (calibration.get("format") != "hyd-calibration/1"
                or calibration.get("model_sha256") != ranker.revision
                or calibration.get("implementation_sha256") != implementation_digest()
                or calibration.get("temperature") != ranker.temperature
                or calibration.get("criteria") != CRITERIA
                or not calibration.get("dataset_sha256")):
            raise ValueError("Hyd calibration does not match the model and implementation")
        self.engine = HydEngine(ranker, calibration["min_confidence"], calibration["min_margin"])
        self.authority = DecisionAuthority(False, self.model)
        self.calibration_revision = hashlib.sha256(raw).hexdigest()
        self._active = None
        self._jobs = set()
        # GPU backbones and single-slot encoder servers take one decision at a time.
        self._capacity = 1 if hasattr(ranker, "backbone") or getattr(ranker, "exclusive", False) else 4
        self._closed = False
        self.fallback = fallback  # observations only; never inherits or grants authority
        self._primary_down_until = 0.0
        if evidence_path:
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            bound = (evidence.get("format") == "hyd-authority/1"
                     and evidence.get("model_revision") == ranker.revision
                     and evidence.get("implementation_sha256") == implementation_digest()
                     and evidence.get("calibration_sha256") == self.calibration_revision
                     and evidence.get("threshold") == self.engine.min_confidence
                     and evidence.get("margin") == self.engine.min_margin)
            if not bound:
                raise ValueError("Hyd authority evidence belongs to another runtime")
            self.authority = DecisionAuthority.from_evidence(evidence, self.model)

    FALLBACK_MODEL = "hyd-latest-cpu-fallback"
    """Distinct model name: authority evidence bound to the primary never applies to the fallback."""

    async def observe(self, request: HydraRequest) -> DecisionObservation:
        start = time.perf_counter()  # whole operation, including any failed primary attempt
        gate = policy_gate(request.last_user_text)
        if gate:
            return DecisionObservation(status="observed", model="hydra-policy-v2", reason=gate[1],
                                       selected=gate[0], probabilities={gate[0]: 1}, confidence=1)
        if request.max_latency_ms is not None:
            return DecisionObservation(status="skipped", model=self.model, reason="latency_budget")
        elapsed = lambda: (time.perf_counter() - start) * 1000  # noqa: E731
        try:
            result = await self.decide(request.last_user_text, {"task": {"type": "choice", "criteria": CRITERIA}})
            answer = result["answers"]["task"]
            prefix = "hyd.fallback_cpu." if result.get("fallback") else "hyd."
            return DecisionObservation(status="observed", model=result["model"],
                selected="abstain" if answer["abstained"] else answer["choice"],
                probabilities=answer["probabilities"], confidence=answer["selection_probability"],
                reason=prefix + answer["reason"], elapsed_ms=elapsed())
        except HydBusyError:
            # Capacity, not input: telemetry must not count load shedding as malformed requests.
            return DecisionObservation(status="skipped", model=self.model, reason="hyd.busy", elapsed_ms=elapsed())
        except TimeoutError:
            return DecisionObservation(status="timeout", model=self.model, reason="hyd.deadline", elapsed_ms=elapsed())
        except RuntimeError:
            return DecisionObservation(status="error", model=self.model, reason="hyd.backend_failure",
                                       elapsed_ms=elapsed())
        except (ValueError, TypeError, OverflowError):
            return DecisionObservation(status="error", model=self.model, reason="hyd.invalid_input",
                                       elapsed_ms=elapsed())

    def task_hint(self, observation: DecisionObservation) -> TaskType | None:
        return self.authority.task_hint(observation)

    async def decide(self, state, questions, timeout_s: float = 5):
        """Primary decision; with a fallback configured, a stopped or busy primary (also a recovery
        probe still in flight) answers from the fallback instead of failing. Used by observations
        and by the public decision endpoints alike."""
        fallback = getattr(self, "fallback", None)
        if fallback is None or self._closed:
            return await self._decide(state, questions, timeout_s)
        if time.monotonic() < self._primary_down_until:
            return await self._from_fallback(fallback, state, questions, timeout_s)
        started = time.monotonic()
        try:
            return await self._decide(state, questions, timeout_s)
        except HydBusyError:
            return await self._from_fallback(fallback, state, questions, timeout_s)
        except (RuntimeError, TimeoutError):
            self._primary_down_until = time.monotonic() + self.FALLBACK_COOLDOWN_S
            remaining = max(0.5, timeout_s - (time.monotonic() - started))
            return await self._from_fallback(fallback, state, questions, remaining)

    async def _from_fallback(self, fallback, state, questions, timeout_s):
        result = await fallback.decide(state, questions, timeout_s=min(60, timeout_s))
        return {**result, "model": self.FALLBACK_MODEL, "fallback": "cpu"}

    async def _decide(self, state, questions, timeout_s: float = 5):
        # Bounded CPU concurrency; one slot for mutable contextual/GPU inference.
        # A timed-out worker retains its slot until completion.
        if not 0 < timeout_s <= 60:
            raise ValueError("invalid Hyd deadline")
        if self._closed:
            raise HydBusyError("Hyd decision controller is closed")
        self._jobs = {task for task in self._jobs if not task.done()}
        if len(self._jobs) >= self._capacity:
            raise HydBusyError("Hyd decision capacity is busy")
        self._active = asyncio.create_task(asyncio.to_thread(self.engine.decide, state, questions, time.monotonic() + timeout_s))
        self._jobs.add(self._active)
        self._active.add_done_callback(lambda task: task.exception() if not task.cancelled() else None)
        return await asyncio.wait_for(asyncio.shield(self._active), timeout=timeout_s)

    def backend(self) -> str:
        ranker = self.engine.ranker
        if hasattr(ranker, "backbone"):
            return "hyd-native-contextual"
        if hasattr(ranker, "encoder"):
            return "hyd-native-encoder"
        return "hyd-native-cpu"

    async def close(self):
        self._closed = True
        for task in self._jobs:
            try:
                await asyncio.shield(task)
            except (ValueError, TypeError, OverflowError, RuntimeError, TimeoutError):
                pass
        self._jobs.clear()
        fallback = getattr(self, "fallback", None)  # tolerate controllers built without __init__
        if fallback is not None:
            await fallback.close()
