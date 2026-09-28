from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from hydra.artifacts import ArtifactRecord, ArtifactStore
from hydra.code_context import CodeContextSelector
from hydra.events import JsonlEventStore
from hydra.patching import PatchTool
from hydra.provider import LocalLLM
from hydra.sandbox import OciSandbox
from hydra.tools import Workspace
from hydra.workspaces import TaskWorkspace, WorkspaceManager


@dataclass
class CodeAgentResult:
    accepted: bool
    answer: str
    artifacts: list[ArtifactRecord]
    workspace: TaskWorkspace


def extract_unified_diff(text: str) -> str:
    fence = chr(96) * 3
    candidate = text.strip()
    if candidate.startswith(fence):
        first_newline = candidate.find(chr(10))
        closing = candidate.rfind(fence)
        if first_newline < 0 or closing <= first_newline:
            raise ValueError("Malformed fenced diff")
        candidate = candidate[first_newline + 1 : closing].strip()
    if "--- " not in candidate or "+++ " not in candidate or "@@" not in candidate:
        raise ValueError("Model did not return a valid unified diff")
    return candidate + chr(10)


SandboxFactory = Callable[[Path], OciSandbox]


class CodeAgent:
    def __init__(
        self,
        llm: LocalLLM,
        workspace_manager: WorkspaceManager,
        artifacts: ArtifactStore,
        events: JsonlEventStore,
        sandbox_factory: SandboxFactory | None = None,
        context_selector: CodeContextSelector | None = None,
    ):
        self.llm = llm
        self.workspace_manager = workspace_manager
        self.artifacts = artifacts
        self.events = events
        self.sandbox_factory = sandbox_factory or OciSandbox
        self.context_selector = context_selector or CodeContextSelector()

    async def run(
        self,
        *,
        task_id: UUID,
        trace_id: str,
        goal: str,
        source: str | Path,
        max_tokens: int,
    ) -> CodeAgentResult:
        workspace = self.workspace_manager.create(task_id, source)
        sandbox = self.sandbox_factory(workspace.root)
        records: list[ArtifactRecord] = []

        preflight = await sandbox.preflight()
        if not preflight.ok:
            self.events.append(
                event_type="hydra.code.sandbox_unavailable",
                aggregate_id=task_id,
                producer="hydra.code_agent",
                trace_id=trace_id,
                payload={
                    "exit_code": preflight.exit_code,
                    "image": getattr(sandbox, "image", None),
                },
            )
            return CodeAgentResult(
                False,
                "Sandbox unavailable; coding task was not executed.",
                records,
                workspace,
            )

        before = await sandbox.pytest(".")
        records.append(self.artifacts.put_text(
            task_id=task_id, kind="tests-before", text=before.output,
            metadata={"exit_code": before.exit_code},
        ))

        context_files = self.context_selector.select(
            workspace.root,
            before.output[-20_000:],
        )
        source_context = self.context_selector.render(context_files)
        prompt = (
            "You are HYDRA CodeAgent. Diagnose the task using the bounded source context "
            "and pytest output below. Return only one unified diff in a diff fenced block. "
            "Do not include shell commands. Do not modify tests unless explicitly requested. "
            "Never reference files outside the provided workspace.\n\n"
            f"TASK:\n{goal}\n\n"
            f"SOURCE CONTEXT:\n{source_context}\n\n"
            f"PYTEST:\n{before.output[-20_000:]}"
        )
        proposal = await self.llm.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=max_tokens,
        )
        records.append(self.artifacts.put_text(
            task_id=task_id,
            kind="model-patch-proposal",
            text=proposal,
            metadata={"context_paths": [item.path for item in context_files]},
        ))
        diff = extract_unified_diff(proposal)

        patcher = PatchTool(Workspace(workspace.root))
        applied = patcher.apply(diff)
        if not applied.ok:
            self.events.append(
                event_type="hydra.code.patch_rejected",
                aggregate_id=task_id,
                producer="hydra.code_agent",
                trace_id=trace_id,
                payload={"reason": "git_apply_failed"},
            )
            return CodeAgentResult(False, "Patch could not be applied.", records, workspace)

        after = await sandbox.pytest(".")
        records.append(self.artifacts.put_text(
            task_id=task_id, kind="tests-after", text=after.output,
            metadata={"exit_code": after.exit_code},
        ))
        records.append(self.artifacts.put_text(
            task_id=task_id, kind="applied-patch", text=diff
        ))

        if not after.ok:
            workspace = self.workspace_manager.create(task_id, source)
            self.events.append(
                event_type="hydra.code.patch_rejected",
                aggregate_id=task_id,
                producer="hydra.code_agent",
                trace_id=trace_id,
                payload={"reason": "tests_failed_after_patch"},
            )
            return CodeAgentResult(
                False, "Patch rejected: verification tests failed.", records, workspace
            )

        records.append(self.artifacts.put_text(
            task_id=task_id, kind="verified-patch", text=diff
        ))
        self.events.append(
            event_type="hydra.code.patch_verified",
            aggregate_id=task_id,
            producer="hydra.code_agent",
            trace_id=trace_id,
            payload={"artifact_ids": [str(r.artifact_id) for r in records]},
        )
        return CodeAgentResult(
            True, "Patch verified in isolated task workspace.", records, workspace
        )
