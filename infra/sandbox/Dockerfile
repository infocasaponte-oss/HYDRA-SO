# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m pip install --no-cache-dir \
    "pytest>=8,<9" \
    "pytest-asyncio>=0.24,<1" \
    "ruff>=0.16,<1" \
    "mypy>=1.18,<2"

WORKDIR /workspace
USER 65532:65532
