from uuid import uuid4

import pytest

from hydra.artifacts import ArtifactStore
from hydra.code_agent import CodeAgent
from hydra.events import JsonlEventStore
from hydra.sandbox import SandboxResult
from hydra.workspaces import WorkspaceManager


class FakeLLM:
    def __init__(self):
        self.calls = 0

    async def chat(self, messages, *, temperature=0.0, max_tokens=1024):
        self.calls += 1
        return "should not be called"


class UnavailableSandbox:
    image = "hydra-sandbox:py311-v1"

    def __init__(self, workspace):
        self.workspace = workspace

    async def preflight(self):
        return SandboxResult(False, "missing image", 125)

    async def pytest(self, target="."):
        raise AssertionError("pytest must not run after failed preflight")


@pytest.mark.asyncio
async def test_code_agent_aborts_before_llm_when_sandbox_unavailable(tmp_path):
    source = tmp_path / "repo"
    source.mkdir()
    (source / "test_sample.py").write_text("def test_ok(): assert True")

    llm = FakeLLM()
    events = JsonlEventStore(tmp_path / "events.jsonl")
    agent = CodeAgent(
        llm,
        WorkspaceManager(tmp_path / "workspaces"),
        ArtifactStore(tmp_path / "artifacts"),
        events,
        sandbox_factory=UnavailableSandbox,
    )

    result = await agent.run(
        task_id=uuid4(),
        trace_id="trace",
        goal="fix it",
        source=source,
        max_tokens=128,
    )

    assert result.accepted is False
    assert llm.calls == 0
    assert "Sandbox unavailable" in result.answer
    assert "hydra.code.sandbox_unavailable" in (tmp_path / "events.jsonl").read_text()
