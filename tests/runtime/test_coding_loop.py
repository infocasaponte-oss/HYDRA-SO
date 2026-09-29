# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
from types import SimpleNamespace
from uuid import uuid4

import pytest

from hydra.runtime.coding_loop import CodingLoop
from hydra.runtime.patching import PatchResult
from hydra.runtime.sandbox import SandboxResult


class FakeSandbox:
    def __init__(self):
        self.calls = 0

    async def pytest(self, target="."):
        self.calls += 1
        if self.calls == 1:
            return SandboxResult(True, "baseline ok", 0)
        return SandboxResult(False, "verification failed", 1)


class FakePatcher:
    def __init__(self):
        self.reversed = []

    def apply(self, diff):
        return PatchResult(True, "")

    def reverse(self, diff):
        self.reversed.append(diff)
        return PatchResult(True, "")


class FakeArtifacts:
    def put_text(self, **kwargs):
        return SimpleNamespace(artifact_id=uuid4())


class FakeEvents:
    def __init__(self):
        self.items = []

    def append(self, **kwargs):
        self.items.append(kwargs)


@pytest.mark.asyncio
async def test_rejected_patch_is_rolled_back():
    patcher = FakePatcher()
    loop = CodingLoop(FakeSandbox(), patcher, FakeArtifacts(), FakeEvents())
    diff = "--- a/a.txt\n+++ b/a.txt\n@@ -1 +1 @@\n-old\n+new\n"

    result = await loop.verify_patch(
        task_id=uuid4(),
        trace_id="trace",
        diff=diff,
    )

    assert not result.accepted
    assert patcher.reversed == [diff]
