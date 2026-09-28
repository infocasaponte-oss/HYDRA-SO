# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    api_host: str = os.getenv("HYDRA_API_HOST", "127.0.0.1")
    api_port: int = int(os.getenv("HYDRA_API_PORT", "8080"))
    llm_url: str = os.getenv("HYDRA_LLM_URL", "http://127.0.0.1:8081/v1")
    models_dir: str = os.getenv("HYDRA_MODELS_DIR", "models")
    repositories_root: str = os.getenv("HYDRA_REPOSITORIES_ROOT", "repositories")
    runtime_db: str = os.getenv("HYDRA_RUNTIME_DB", "runtime/hydra.db")
    deployments_file: str = os.getenv(
        "HYDRA_DEPLOYMENTS_FILE", "runtime/deployments.json"
    )
    readiness_max_pending: int = int(os.getenv("HYDRA_READINESS_MAX_PENDING", "1000"))
    readiness_max_pending_age_seconds: float = float(
        os.getenv("HYDRA_READINESS_MAX_PENDING_AGE_SECONDS", "300")
    )
    # One gateway token for both lines: HYDRA_API_TOKEN (HYDRA-SO) or HYDRA_API_KEY (platform).
    api_token: str | None = os.getenv("HYDRA_API_TOKEN") or os.getenv("HYDRA_API_KEY") or None
    admin_token: str | None = os.getenv("HYDRA_ADMIN_TOKEN") or None
    api_rate_limit_per_minute: int = int(
        os.getenv("HYDRA_API_RATE_LIMIT_PER_MINUTE", "60")
    )
    admin_rate_limit_per_minute: int = int(
        os.getenv("HYDRA_ADMIN_RATE_LIMIT_PER_MINUTE", "6")
    )
    sandbox_image: str = os.getenv(
        "HYDRA_SANDBOX_IMAGE", "hydra-sandbox:py312-v3"
    )
    sandbox_runtime: str = os.getenv("HYDRA_SANDBOX_RUNTIME", "docker")
    code_verification_mode: str = os.getenv(
        "HYDRA_CODE_VERIFICATION_MODE", "advisory"
    )
    workspace_max_files: int = int(os.getenv("HYDRA_WORKSPACE_MAX_FILES", "20000"))
    workspace_max_bytes: int = int(
        os.getenv("HYDRA_WORKSPACE_MAX_BYTES", str(256 * 1024 * 1024))
    )
    max_input_chars: int = int(os.getenv("HYDRA_MAX_INPUT_CHARS", "50000"))
    max_output_tokens: int = int(os.getenv("HYDRA_MAX_OUTPUT_TOKENS", "4096"))
    max_translation_chunks: int = int(os.getenv("HYDRA_MAX_TRANSLATION_CHUNKS", "64"))


settings = Settings()
