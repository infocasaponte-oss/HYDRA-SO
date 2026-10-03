# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""Hyd ranker on a frozen contextual encoder: encoder embeddings -> HYDRA-trained linear head.

The encoder is interchangeable and recorded in the model file: today the HYDRA v8 GGUF served by
llama-server with ``--embeddings`` (Qwen2.5-1.5B base, Apache-2.0), later HYDRA Base. Only the head
(standardisation, weights, bias, temperature) is trained by HYDRA. The head knows a fixed label set;
any other option set gets a uniform distribution, which the engine reports as unsupported/abstained.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from pathlib import Path

import numpy as np

from hydra.core.atomic import write_text_atomic
from hydra.hyd.model import render

FORMAT = "hyd-embedding-head/1"


class LlamaCppEncoder:
    """OpenAI-compatible ``/v1/embeddings`` of a local llama-server started with ``--embeddings``."""

    def __init__(self, endpoint: str, model: str, dims: int, timeout_s: float = 30):
        if not endpoint.startswith(("http://127.0.0.1", "http://localhost")):
            raise ValueError("Hyd encoder must be a local endpoint")
        self.endpoint, self.model, self.dims, self.timeout_s = endpoint.rstrip("/"), model, dims, timeout_s

    def embed(self, texts: list[str], deadline: float | None = None) -> np.ndarray:
        import httpx

        timeout = self.timeout_s if deadline is None else max(0.05, min(self.timeout_s, deadline - time.monotonic()))
        vectors = []
        with httpx.Client(timeout=timeout) as client:
            for start in range(0, len(texts), 32):
                if deadline is not None and time.monotonic() >= deadline:
                    raise TimeoutError("Hyd encoder deadline exceeded")
                response = client.post(self.endpoint + "/v1/embeddings",
                                       json={"model": self.model, "input": texts[start:start + 32]})
                if response.status_code != 200:
                    raise RuntimeError(f"Hyd encoder returned HTTP {response.status_code}")
                data = sorted(response.json()["data"], key=lambda item: item["index"])
                vectors += [item["embedding"] for item in data]
        array = np.asarray(vectors, dtype=np.float64)
        if array.shape != (len(texts), self.dims) or not np.isfinite(array).all():
            raise RuntimeError("Hyd encoder returned embeddings of the wrong shape or non-finite values")
        return array


def encoder_from(spec: dict):
    if spec.get("kind") == "llamacpp-embeddings":
        return LlamaCppEncoder(spec["endpoint"], spec["model"], int(spec["dims"]))
    raise ValueError(f"unsupported Hyd encoder kind: {spec.get('kind')}")


def softmax(logits: np.ndarray, temperature: float) -> np.ndarray:
    z = logits / temperature
    z = z - z.max(axis=-1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=-1, keepdims=True)


def fit_head(x: np.ndarray, y: np.ndarray, classes: int, l2: float, epochs: int = 300, rate: float = 0.5):
    """Full-batch multinomial logistic regression on standardised features (deterministic)."""
    w = np.zeros((x.shape[1], classes))
    b = np.zeros(classes)
    onehot = np.eye(classes)[y]
    for _ in range(epochs):
        p = softmax(x @ w + b, 1.0)
        gradient = (p - onehot) / len(x)
        w -= rate * (x.T @ gradient + l2 * w)
        b -= rate * gradient.sum(axis=0)
    return w, b


class EmbeddingRanker:
    def __init__(self, encoder, labels: list[str], mean, scale, weights, bias, temperature: float = 1.0):
        self.encoder, self.labels = encoder, list(labels)
        self.mean, self.scale = np.asarray(mean, dtype=np.float64), np.asarray(scale, dtype=np.float64)
        self.weights, self.bias = np.asarray(weights, dtype=np.float64), np.asarray(bias, dtype=np.float64)
        self.temperature = temperature
        self.training: dict = {}
        self.revision = "untrained"
        self.exclusive = True  # one encoder call at a time: llama-server runs a single slot
        self.last_input_tokens = 0

    def text_of(self, state, instructions) -> str:
        return render(state) if instructions is None else render(state) + "\nInstructions: " + render(instructions)

    def probabilities_batch(self, texts: list[str], deadline=None) -> list[dict[str, float]]:
        return self.probabilities_from_embeddings(self.encoder.embed(texts, deadline))

    def probabilities_from_embeddings(self, embeddings: np.ndarray) -> list[dict[str, float]]:
        x = (embeddings - self.mean) / self.scale
        return [dict(zip(self.labels, map(float, row))) for row in softmax(x @ self.weights + self.bias,
                                                                          self.temperature)]

    def probabilities(self, state, instructions, options: dict, deadline=None) -> dict[str, float]:
        if deadline is not None and time.monotonic() >= deadline:
            raise TimeoutError("Hyd deadline exceeded")
        if set(options) != set(self.labels):
            return {key: 1 / len(options) for key in options}  # untrained option set: no opinion
        self.last_input_tokens = 0
        probabilities = self.probabilities_batch([self.text_of(state, instructions)], deadline)[0]
        return {key: probabilities[key] for key in options}

    def save(self, path: Path, encoder_spec: dict):
        payload = {"format": FORMAT, "encoder": encoder_spec, "labels": self.labels, "temperature": self.temperature,
                   "mean": self.mean.tolist(), "scale": self.scale.tolist(), "weights": self.weights.tolist(),
                   "bias": self.bias.tolist(), "training": self.training}
        write_text_atomic(path, json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")))
        self.revision = hashlib.sha256(path.read_bytes()).hexdigest()

    @classmethod
    def load(cls, path: Path, encoder=None):
        raw = path.read_bytes()
        if len(raw) > 64 * 1024 * 1024:
            raise ValueError("Hyd embedding head exceeds size limit")
        data = json.loads(raw)
        if data.get("format") != FORMAT:
            raise ValueError("unsupported Hyd embedding head format")
        labels = data["labels"]
        dims = int(data["encoder"]["dims"])
        weights, bias = np.asarray(data["weights"], dtype=np.float64), np.asarray(data["bias"], dtype=np.float64)
        mean, scale = np.asarray(data["mean"], dtype=np.float64), np.asarray(data["scale"], dtype=np.float64)
        temperature = data["temperature"]
        if (weights.shape != (dims, len(labels)) or bias.shape != (len(labels),) or mean.shape != (dims,)
                or scale.shape != (dims,) or not (scale > 0).all()
                or not all(np.isfinite(a).all() for a in (weights, bias, mean, scale))
                or type(temperature) not in (int, float) or not math.isfinite(temperature) or temperature <= 0
                or len(set(labels)) != len(labels) or not 2 <= len(labels) <= 255):
            raise ValueError("invalid Hyd embedding head parameters")
        model = cls(encoder or encoder_from(data["encoder"]), labels, mean, scale, weights, bias, float(temperature))
        model.training = data.get("training", {})
        model.revision = hashlib.sha256(raw).hexdigest()
        return model
