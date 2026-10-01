# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values  # python-dotenv ships with pydantic-settings

# Same sources and precedence as the platform Settings (hydra.core.config): process environment
# first, then ./.env. Without this, a HYDRA_ADMIN_TOKEN kept in .env protected the platform but
# left the runtime admin routes answering 503.
_DOTENV = {k: v for k, v in dotenv_values(".env").items() if v is not None} if Path(".env").is_file() else {}


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value is not None else _DOTENV.get(name, default)


@dataclass(frozen=True)
class Settings:
    api_host: str = _env("HYDRA_API_HOST", "127.0.0.1")
    api_port: int = int(_env("HYDRA_API_PORT", "8080"))
    llm_url: str = _env("HYDRA_LLM_URL", "http://127.0.0.1:8081/v1")
    models_dir: str = _env("HYDRA_MODELS_DIR", "models")
    repositories_root: str = _env("HYDRA_REPOSITORIES_ROOT", "repositories")
    runtime_dir: str = _env("HYDRA_RUNTIME_DIR", "runtime")
    runtime_db: str = _env("HYDRA_RUNTIME_DB", str(Path(runtime_dir) / "hydra.db"))
    deployments_file: str = _env(
        "HYDRA_DEPLOYMENTS_FILE", str(Path(runtime_dir) / "deployments.json")
    )
    readiness_max_pending: int = int(_env("HYDRA_READINESS_MAX_PENDING", "1000"))
    readiness_max_pending_age_seconds: float = float(
        _env("HYDRA_READINESS_MAX_PENDING_AGE_SECONDS", "300")
    )
    # One gateway token for both lines: HYDRA_API_TOKEN (HYDRA-SO) or HYDRA_API_KEY (platform).
    api_token: str | None = _env("HYDRA_API_TOKEN") or _env("HYDRA_API_KEY") or None
    admin_token: str | None = _env("HYDRA_ADMIN_TOKEN") or None
    api_rate_limit_per_minute: int = int(
        _env("HYDRA_API_RATE_LIMIT_PER_MINUTE", "60")
    )
    admin_rate_limit_per_minute: int = int(
        _env("HYDRA_ADMIN_RATE_LIMIT_PER_MINUTE", "6")
    )
    sandbox_image: str = _env(
        "HYDRA_SANDBOX_IMAGE", "hydra-sandbox:py312-v3"
    )
    sandbox_runtime: str = _env("HYDRA_SANDBOX_RUNTIME", "docker")
    code_verification_mode: str = _env(
        "HYDRA_CODE_VERIFICATION_MODE", "advisory"
    )
    workspace_max_files: int = int(_env("HYDRA_WORKSPACE_MAX_FILES", "20000"))
    workspace_max_bytes: int = int(
        _env("HYDRA_WORKSPACE_MAX_BYTES", str(256 * 1024 * 1024))
    )
    max_input_chars: int = int(_env("HYDRA_MAX_INPUT_CHARS", "50000"))
    max_output_tokens: int = int(_env("HYDRA_MAX_OUTPUT_TOKENS", "4096"))
    max_translation_chunks: int = int(_env("HYDRA_MAX_TRANSLATION_CHUNKS", "64"))


settings = Settings()
