# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""Runtime settings, read from environment variables (prefix HYDRA_)."""

from __future__ import annotations

from pathlib import Path
import sys

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_SOURCE_ROOT = Path(__file__).resolve().parents[2]
# Source checkout -> repository root; installed package -> current directory.
_INSTALLED_ROOT = Path(sys.prefix) / "share" / "hydra"
ROOT = (_SOURCE_ROOT if (_SOURCE_ROOT / "config").is_dir() else
        _INSTALLED_ROOT if (_INSTALLED_ROOT / "config").is_dir() else Path.cwd())


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HYDRA_", env_file=".env", extra="ignore")

    models_config: Path = ROOT / "config" / "models.yaml"
    policy_config: Path = ROOT / "config" / "policy.yaml"
    evals_dir: Path = ROOT / "config" / "evals"
    data_dir: Path = Path.cwd() / "data"
    """Local state: failure memory, lab experiments, model factory store."""

    # Infrastructure. Empty value -> in-memory implementation.
    postgres_url: str = ""
    redis_url: str = ""

    # Runtimes
    vllm_base_url: str = "http://localhost:8000/v1"
    ollama_base_url: str = "http://localhost:11434"
    llamacpp_base_url: str = "http://localhost:8081/v1"
    cloud_base_url: str = "https://api.openai.com/v1"
    cloud_api_key: str = ""
    internal_api_key: str = "internal"

    # Use deterministic offline models (no runtime needed). Great for dev/tests.
    offline: bool = False

    # Sandbox: "docker" (isolated container) or "subprocess" (dev only).
    sandbox_backend: str = "docker"
    sandbox_image: str = "python:3.12-slim"
    workspace_dir: Path = Path.cwd() / "workspace"
    # Mount source for the sandbox as seen by the Docker daemon (e.g. a named volume
    # when HYDRA itself runs in a container). Empty -> workspace_dir.
    sandbox_workspace_source: str = ""

    # Optional System-One routing classifier (a model id from the registry).
    router_model: str = ""
    # Embeddings: "hashing" (local, no model) | "vllm" | "ollama" (e.g. nomic-embed-text).
    embedding_provider: str = "hashing"
    embedding_model: str = ""
    # Domains research workers may fetch from (comma separated). Empty -> built-in list.
    network_domains: str = ""

    # Gateway protection. Empty -> no auth (development).
    api_key: str = Field(default="", validation_alias=AliasChoices("api_key", "HYDRA_API_KEY", "HYDRA_API_TOKEN"))
    """Gateway token (HYDRA_API_KEY, or HYDRA_API_TOKEN as used by the runtime line)."""
    api_rate_limit_per_minute: int = 60
    """Per-client limit for authenticated API routes. Set <= 0 to disable."""

    # Poll runtime metrics (vLLM/llama.cpp /metrics, Ollama /api/ps, nvidia-smi) for load-aware routing.
    runtime_monitor: bool = True
    monitor_interval_s: float = 5.0
    # NATS JetStream bus (takes precedence over Redis when set), e.g. nats://localhost:4222
    nats_url: str = ""
    # Model Factory toolchain: llama.cpp checkout/build dir (convert_hf_to_gguf.py, llama-quantize...).
    llamacpp_dir: str = ""

    # Stretch wall-clock budgets (local GPUs with cold model loads: 2-4).
    budget_time_scale: float = 1.0

    # ---- HYDRA 1.0 planes ----------------------------------------------------------
    policy_rules_config: Path = ROOT / "config" / "policy_rules.yaml"
    """Policy DSL rules (deny/review/allow)."""
    licenses_config: Path = ROOT / "config" / "licenses.yaml"
    """License profiles and registered component licenses."""
    capture: bool = True
    """Capture pipeline: world model, artifacts (CAS), corpus, ledger, flight recorder."""
    capture_outbox_poll_s: float = 2.0
    """How often deferred capture writes (ledger/corpus) are retried from the outbox."""
    corpus_auto_training_max_sensitivity: int = 0
    """Own executions at or below this sensitivity are trainable by default (0 = PUBLIC)."""
    deterministic_first: bool = False
    """Answer with deterministic solvers (calculator, sympy, JSON/SQL validators) when certain."""
    ledger_anchor_every: int = 1000
    node_id: str = ""
    """Cluster node id (default: hostname)."""
    cluster_rerank: bool = True
    """Re-rank models by cluster placement (residency, KV locality, queue, SLA) when nodes report."""
    heartbeat_interval_s: float = 15.0
    otel_endpoint: str = ""
    """OTLP/HTTP traces endpoint (e.g. http://localhost:4318). Empty -> in-process spans only."""
    llama_server: str = ""
    """Path to llama-server for the AutoBuilder (default: search PATH / HYDRA_LLAMACPP_DIR)."""

    # Request budgets shared with the runtime line (HYDRA_MAX_INPUT_CHARS, HYDRA_MAX_TRANSLATION_CHUNKS).
    max_input_chars: int = 50_000
    max_translation_chunks: int = 64

    runtime_api: bool = True
    """Serve the HYDRA-SO runtime line (/ready, /v1/chat, /hydra/v1/admin/*, coding) from the gateway."""

    hedge_after_ms: float = 3500
    breaker_failures: int = 5
    breaker_cooldown_s: float = 60
