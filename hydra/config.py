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
    readiness_max_pending: int = int(os.getenv("HYDRA_READINESS_MAX_PENDING", "1000"))
    readiness_max_pending_age_seconds: float = float(
        os.getenv("HYDRA_READINESS_MAX_PENDING_AGE_SECONDS", "300")
    )
    max_input_chars: int = int(os.getenv("HYDRA_MAX_INPUT_CHARS", "50000"))
    max_output_tokens: int = int(os.getenv("HYDRA_MAX_OUTPUT_TOKENS", "4096"))
    max_translation_chunks: int = int(os.getenv("HYDRA_MAX_TRANSLATION_CHUNKS", "64"))


settings = Settings()
