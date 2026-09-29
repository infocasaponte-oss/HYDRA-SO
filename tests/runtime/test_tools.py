# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
import pytest

from hydra.runtime.policy import PolicyDenied, ToolPermission
from hydra.runtime.sandbox import SandboxResult
from hydra.runtime.tool_runtime import ToolRuntime
from hydra.runtime.tools import Workspace


def test_workspace_rejects_escape(tmp_path):
    ws = Workspace(tmp_path)
    with pytest.raises(ValueError):
        ws.resolve("../outside")


@pytest.mark.asyncio
async def test_read_tool_is_allowed_by_default(tmp_path):
    (tmp_path / "hello.txt").write_text("hello HYDRA")
    runtime = ToolRuntime(Workspace(tmp_path))
    result = await runtime.run("workspace.read", {"path": "hello.txt"})
    assert result.ok
    assert result.output == "hello HYDRA"


@pytest.mark.asyncio
async def test_process_execution_denied_by_default(tmp_path):
    runtime = ToolRuntime(Workspace(tmp_path))
    with pytest.raises(PolicyDenied):
        await runtime.run("python.test", {"path": "."})


@pytest.mark.asyncio
async def test_process_execution_requires_explicit_permission_and_uses_sandbox(tmp_path):
    class FakeSandbox:
        def __init__(self):
            self.targets = []

        async def pytest(self, target):
            self.targets.append(target)
            return SandboxResult(True, "1 passed", 0)

    sandbox = FakeSandbox()
    runtime = ToolRuntime(Workspace(tmp_path), sandbox=sandbox)
    result = await runtime.run(
        "python.test",
        {"path": "."},
        ToolPermission(allow_execute=True),
    )
    assert result.ok
    assert result.output == "1 passed"
    assert sandbox.targets == ["."]
