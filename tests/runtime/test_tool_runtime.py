# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
import pytest

from hydra.runtime.policy import ToolPermission
from hydra.runtime.sandbox import SandboxResult
from hydra.runtime.tool_runtime import ToolRuntime
from hydra.runtime.tools import Workspace


@pytest.mark.asyncio
async def test_python_test_delegates_to_oci_sandbox(monkeypatch, tmp_path):
    calls = {}

    async def fake_pytest(self, target="."):
        calls["workspace"] = self.workspace
        calls["target"] = target
        return SandboxResult(True, "sandboxed", 0)

    monkeypatch.setattr("hydra.runtime.tool_runtime.OciSandbox.pytest", fake_pytest)
    runtime = ToolRuntime(Workspace(tmp_path))

    result = await runtime.run(
        "python.test",
        {"path": "."},
        ToolPermission(allow_execute=True),
    )

    assert result.ok
    assert result.output == "sandboxed"
    assert calls["workspace"] == tmp_path.resolve()
    assert calls["target"] == "."


@pytest.mark.asyncio
async def test_python_test_rejects_workspace_escape(tmp_path):
    runtime = ToolRuntime(Workspace(tmp_path))

    with pytest.raises(ValueError, match="Workspace path escape"):
        await runtime.run(
            "python.test",
            {"path": "../outside"},
            ToolPermission(allow_execute=True),
        )
