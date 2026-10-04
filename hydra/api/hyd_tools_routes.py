# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""Opt-in single-node operator API. Shares the gateway's admin authentication."""
import asyncio

from fastapi import HTTPException

from hydra.hyd.integration import contract
from hydra.hyd.lab import HydLab, JobRequest


def register(app, settings, admin_secured):
    if settings.require_shared_state:
        raise ValueError("Hyd tools currently require a single-node local lab; disable for shared-state deployments")
    lab = HydLab(settings.hyd_tools_input_root, settings.data_dir / "hyd-tools")
    app.state.hyd_tools = lab

    def operation(fn, *args):
        try:
            return fn(*args)
        except KeyError as error:
            raise HTTPException(404, "job not found") from error
        except (ValueError, OSError) as error:
            raise HTTPException(409, "invalid job request, input path or state") from error

    @app.get("/hydra/v1/hyd-tools/contract", dependencies=admin_secured)
    async def routing_contract():
        return contract()

    @app.post("/hydra/v1/hyd-tools/jobs", dependencies=admin_secured, status_code=201)
    async def submit(body: JobRequest):
        return await asyncio.to_thread(operation, lab.submit, body)

    @app.get("/hydra/v1/hyd-tools/jobs/{job_id}", dependencies=admin_secured)
    async def status(job_id: str):
        return operation(lab.get, job_id)

    @app.post("/hydra/v1/hyd-tools/jobs/{job_id}/run", dependencies=admin_secured)
    async def run(job_id: str):
        return await asyncio.to_thread(operation, lab.run, job_id)

    @app.post("/hydra/v1/hyd-tools/jobs/{job_id}/cancel", dependencies=admin_secured)
    async def cancel(job_id: str):
        return operation(lab.cancel, job_id)
