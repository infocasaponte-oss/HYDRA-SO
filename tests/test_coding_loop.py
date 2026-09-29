import subprocess
from uuid import uuid4

import pytest

from hydra.artifacts import ArtifactStore
from hydra.coding_loop import CodingLoop
from hydra.events import JsonlEventStore
from hydra.patching import PatchTool
from hydra.sandbox import SandboxResult
from hydra.tools import Workspace


class StubSandbox:
    def __init__(self, results):
        self._results = iter(results)

    async def pytest(self, target="."):
        return next(self._results)


@pytest.mark.asyncio
async def test_rejected_patch_restores_workspace(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "a.txt").write_text("old\n")
    subprocess.run(["git", "add", "a.txt"], cwd=tmp_path, check=True)

    diff = "--- a/a.txt\n+++ b/a.txt\n@@ -1 +1 @@\n-old\n+new\n"
    loop = CodingLoop(
        sandbox=StubSandbox(
            [
                SandboxResult(False, "baseline failed", 1),
                SandboxResult(False, "still failing", 1),
            ]
        ),
        patcher=PatchTool(Workspace(tmp_path)),
        artifacts=ArtifactStore(tmp_path / "artifacts"),
        events=JsonlEventStore(tmp_path / "events.jsonl"),
    )

    result = await loop.verify_patch(
        task_id=uuid4(),
        trace_id="trace",
        diff=diff,
    )

    assert not result.accepted
    assert (tmp_path / "a.txt").read_text() == "old\n"


@pytest.mark.asyncio
async def test_accepted_patch_remains_applied(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "a.txt").write_text("old\n")
    subprocess.run(["git", "add", "a.txt"], cwd=tmp_path, check=True)

    diff = "--- a/a.txt\n+++ b/a.txt\n@@ -1 +1 @@\n-old\n+new\n"
    loop = CodingLoop(
        sandbox=StubSandbox(
            [
                SandboxResult(False, "baseline failed", 1),
                SandboxResult(True, "1 passed", 0),
            ]
        ),
        patcher=PatchTool(Workspace(tmp_path)),
        artifacts=ArtifactStore(tmp_path / "artifacts"),
        events=JsonlEventStore(tmp_path / "events.jsonl"),
    )

    result = await loop.verify_patch(
        task_id=uuid4(),
        trace_id="trace",
        diff=diff,
    )

    assert result.accepted
    assert (tmp_path / "a.txt").read_text() == "new\n"
