# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""Mount the HYDRA-SO runtime line (``hydra.runtime.api``) into the unified gateway.

Platform routes win on (path, method) collisions:

* ``GET /health``            platform health (``hydra: ok`` kept for runtime clients)
* ``GET /v1/models``         platform model list; the runtime GGUF scan moves to
                             ``GET /hydra/v1/models/artifacts``
* ``POST /v1/translate``     platform engine (accepts the runtime schema)
* ``PUT /v1/glossaries/{}``  platform glossary store

Everything else (``/ready``, ``/v1/chat``, ``/hydra/v1/tasks/route|execute``,
``/hydra/v1/admin/*``, ``/hydra/v1/coding/verify-fix``) is served by the runtime line with
its own token policy (``HYDRA_API_TOKEN`` / ``HYDRA_ADMIN_TOKEN``) and its transactional
outbox worker, which runs inside the gateway lifespan.

The runtime line keeps process-wide state under ``./runtime`` (HYDRA-SO layout), so it is
mounted once per process even when several apps are created (tests).
"""

from __future__ import annotations

import re
from contextlib import asynccontextmanager, nullcontext
from dataclasses import replace
from types import ModuleType

from fastapi import FastAPI
from fastapi.routing import APIRoute

RELOCATED = {("/v1/models", "GET"): "/hydra/v1/models/artifacts"}
_PARAM = re.compile(r"\{[^}]+\}")


def _shape(path: str) -> str:
    """``/v1/glossaries/{name}`` and ``/v1/glossaries/{glossary_id}`` are the same route."""
    return _PARAM.sub("{}", path)


def runtime_module() -> ModuleType:
    from hydra.runtime import api

    return api


def register_runtime_routes(app: FastAPI) -> list[str]:
    """Append runtime routes that do not collide with platform routes. Returns what was mounted."""
    runtime = runtime_module()
    taken = {(_shape(route.path), method) for route in app.routes if isinstance(route, APIRoute)
             for method in route.methods}
    mounted = []
    for route in runtime.app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in sorted(route.methods):
            path = RELOCATED.get((route.path, method), route.path)
            if (_shape(path), method) in taken:
                continue
            app.add_api_route(path, route.endpoint, methods=[method], name=f"runtime.{route.name}",
                              response_model=route.response_model, status_code=route.status_code,
                              tags=["runtime"], summary=route.summary, description=route.description)
            taken.add((_shape(path), method))
            mounted.append(f"{method} {path}")
    return mounted


@asynccontextmanager
async def runtime_lifespan(enabled: bool, api_key: str = ""):
    """Outbox recovery + worker of the runtime line, bound to the gateway lifespan.

    A gateway token given in code (not only through HYDRA_API_KEY/HYDRA_API_TOKEN) also
    protects the runtime routes while this app is running."""
    if not enabled:
        yield
        return
    runtime = runtime_module()
    previous = runtime.security_config
    if api_key:
        runtime.security_config = replace(previous, api_token=api_key)
    worker = getattr(runtime.app.state, "outbox_worker_task", None)
    running = worker is not None and not worker.done()  # already started by another app in this process
    try:
        async with nullcontext() if running else runtime.lifespan(runtime.app):
            yield
    finally:
        runtime.security_config = previous
