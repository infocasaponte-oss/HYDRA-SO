import pytest

from hydra.policy import PolicyDenied, ToolPermission
from hydra.sandbox import SandboxResult
from hydra.tool_runtime import ToolRuntime
from hydra.tools import Workspace


class StubSandbox:
    def __init__(self, root):
        self.root = root
        self.targets = []

    async def pytest(self, target="."):
        self.targets.append(target)
        return SandboxResult(True, "1 passed", 0)


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
    sandbox = StubSandbox(tmp_path)
    runtime = ToolRuntime(
        Workspace(tmp_path),
        sandbox_factory=lambda root: sandbox,
    )
    result = await runtime.run(
        "python.test",
        {"path": "."},
        ToolPermission(allow_execute=True),
    )
    assert result.ok
    assert "passed" in result.output
    assert sandbox.root == tmp_path.resolve()
    assert sandbox.targets == ["."]


@pytest.mark.asyncio
async def test_process_execution_rejects_target_escape_before_sandbox(tmp_path):
    sandbox = StubSandbox(tmp_path)
    runtime = ToolRuntime(
        Workspace(tmp_path),
        sandbox_factory=lambda root: sandbox,
    )
    with pytest.raises(ValueError, match="escape"):
        await runtime.run(
            "python.test",
            {"path": "../outside"},
            ToolPermission(allow_execute=True),
        )
    assert sandbox.targets == []
