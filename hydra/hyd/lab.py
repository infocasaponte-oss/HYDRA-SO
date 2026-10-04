# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""Local, persistent operator jobs. No release promotion or inference configuration writes."""
from __future__ import annotations

import json
import hashlib
import sqlite3
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from hydra.hyd.corpus_contract import inspect_intake, snapshot
from hydra.hyd.integration import calibrator, export_runtime


class JobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["calibrate", "report", "validate", "snapshot", "export"]
    review_mode: Literal["development", "double_review"] = "development"
    dataset: str | None = Field(default=None, max_length=1000)
    model: str | None = Field(default=None, max_length=1000)
    train_dataset: str | None = Field(default=None, max_length=1000)
    target: float = Field(default=.95, gt=0, lt=1, allow_inf_nan=False)
    min_coverage: float = Field(default=.1, ge=0, le=1, allow_inf_nan=False)


class HydLab:
    def __init__(self, root: Path, state: Path):
        self.root, self.state = Path(root).resolve(), Path(state).resolve()
        self.state.mkdir(parents=True, exist_ok=True)
        self.db = self.state / "jobs.sqlite"
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, state TEXT NOT NULL, request TEXT NOT NULL, result TEXT, inputs TEXT NOT NULL)")

    def connect(self):
        return sqlite3.connect(self.db, timeout=10)

    def path(self, value: str | None, directory=False):
        if not value:
            raise ValueError("missing input path")
        path = (self.root / value).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("input must stay within input root")
        if directory:
            if not path.is_dir():
                raise ValueError("model directory not found")
            for name in ("model.json", "calibration.json"):
                child = (path / name).resolve()
                if not child.is_relative_to(self.root) or not child.is_file() or child.stat().st_size > 20*1024*1024:
                    raise ValueError("invalid model artifact")
        elif not path.is_file() or path.stat().st_size > 20*1024*1024:
            raise ValueError("input missing or exceeds 20 MiB")
        return path

    def validate_request(self, request):
        if request.kind != "export":
            self.path(request.dataset)
        if request.kind in ("calibrate", "report", "export"):
            self.path(request.model, directory=request.kind != "calibrate")
        if request.kind == "calibrate":
            self.path(request.train_dataset)  # overlap check is mandatory in HYDRA jobs

    def submit(self, request: JobRequest):
        self.validate_request(request)
        inputs = self.input_hashes(request)
        job_id = str(uuid4())
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT COUNT(*) FROM jobs WHERE state IN ('queued','running')").fetchone()[0] >= 10:
                raise ValueError("local job queue is full")
            db.execute("INSERT INTO jobs VALUES (?, 'queued', ?, NULL, ?)", (job_id, request.model_dump_json(), json.dumps(inputs)))
        return self.get(job_id)

    def get(self, job_id):
        UUID(job_id)
        with self.connect() as db:
            row = db.execute("SELECT state, request, result, inputs FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise KeyError("job not found")
        return {"id": job_id, "state": row[0], "request": json.loads(row[1]),
                "result": json.loads(row[2]) if row[2] else None, "inputs": json.loads(row[3]), "activated": False}

    def input_hashes(self, request):
        values = {}
        for field in ("dataset", "model", "train_dataset"):
            value = getattr(request, field)
            if value:
                directory = field == "model" and request.kind in ("report", "export")
                path = self.path(value, directory)
                paths = [path / "model.json", path / "calibration.json"] if directory else [path]
                values[field] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        return values

    def cancel(self, job_id):
        self.get(job_id)
        with self.connect() as db:
            if db.execute("UPDATE jobs SET state='cancelled' WHERE id=? AND state='queued'", (job_id,)).rowcount != 1:
                raise ValueError("only queued jobs can be cancelled")
        return self.get(job_id)

    def run(self, job_id):
        job = self.get(job_id)
        request = JobRequest.model_validate(job["request"])
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT COUNT(*) FROM jobs WHERE state='running'").fetchone()[0]:
                raise ValueError("another local job is running")
            if db.execute("UPDATE jobs SET state='running' WHERE id=? AND state='queued'", (job_id,)).rowcount != 1:
                raise ValueError("job is not queued")
        try:
            self.validate_request(request)
            if self.input_hashes(request) != job["inputs"]:
                raise ValueError("job inputs changed after submission")
            output = self.state / job_id
            if request.kind == "validate":
                _, result = inspect_intake(self.path(request.dataset))
            elif request.kind == "snapshot":
                result = snapshot(self.path(request.dataset), output, request.review_mode)
            elif request.kind == "export":
                result = export_runtime(self.path(request.model, directory=True), output)
            else:
                module, _ = calibrator()
                if request.kind == "calibrate":
                    result = module.calibrate(self.path(request.model), self.path(request.dataset), output,
                                              request.target, request.min_coverage, self.path(request.train_dataset))
                else:
                    from hyd_calibrator.corpus import report
                    result = report(self.path(request.dataset), self.path(request.model, directory=True))
            if self.input_hashes(request) != job["inputs"]:
                raise ValueError("job inputs changed during execution")
            state = "completed"
        except Exception as error:
            # Public error category only; full input texts and provider keys never enter job responses.
            state, result = "failed", {"error_type": type(error).__name__, "error": "Job failed; inspect input contract, hashes and tool installation."}
        with self.connect() as db:
            db.execute("UPDATE jobs SET state=?, result=? WHERE id=?", (state, json.dumps(result, allow_nan=False), job_id))
        return self.get(job_id)
