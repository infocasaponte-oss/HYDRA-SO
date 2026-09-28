from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass

from fastapi import HTTPException, Request, status


_LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


@dataclass(frozen=True)
class SecurityConfig:
    api_token: str | None
    admin_token: str | None


def _provided_token(request: Request) -> str | None:
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return request.headers.get("x-hydra-token")


def _local_request(request: Request) -> bool:
    client = request.client
    return client is not None and client.host in _LOCAL_HOSTS


def _matches(provided: str | None, expected: str | None) -> bool:
    if not provided or not expected:
        return False
    return hmac.compare_digest(provided.encode(), expected.encode())


def require_api_access(request: Request, config: SecurityConfig) -> str:
    provided = _provided_token(request)
    if config.api_token:
        if not _matches(provided, config.api_token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid HYDRA API token",
            )
        return hashlib.sha256(provided.encode()).hexdigest()

    if not _local_request(request):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="HYDRA API token is not configured; remote access is disabled",
        )
    return f"local:{request.client.host}"


def require_admin_access(request: Request, config: SecurityConfig) -> str:
    provided = _provided_token(request)
    if not config.admin_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="HYDRA admin token is not configured",
        )
    if not _matches(provided, config.admin_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid HYDRA admin token",
        )
    return hashlib.sha256(provided.encode()).hexdigest()
