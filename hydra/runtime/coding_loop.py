from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from hydra.runtime.artifacts import ArtifactRecord, ArtifactStore
from hydra.runtime.events import JsonlEventStore
from hydra.runtime.patching import PatchTool
from hydra.runtime.sandbox import OciSandbox


@dataclass
class CodingLoopResult:
    accepted: bool
    before_ok: bool
    after_ok: bool
    artifacts: list[ArtifactRecord]


class CodingLoop:
    """
    Deterministic verification shell around a proposed patch.

    Patch generation remains separate from patch execution. A patch is accepted
    only when the post-patch test run succeeds.
    """

    def __init__(
        self,
        sandbox: OciSandbox,
        patcher: PatchTool,
        artifacts: ArtifactStore,
        events: JsonlEventStore,
    ):
        self.sandbox = sandbox
        self.patcher = patcher
        self.artifacts = artifacts
        self.events = events

    async def verify_patch(
        self,
        *,
        task_id: UUID,
        trace_id: str,
        diff: str,
        test_target: str = ".",
    ) -> CodingLoopResult:
        records: list[ArtifactRecord] = []

        before = await self.sandbox.pytest(test_target)
        records.append(
            self.artifacts.put_text(
                task_id=task_id,
                kind="tests-before",
                text=before.output,
                metadata={"exit_code": before.exit_code},
            )
        )

        patch = self.patcher.apply(diff)
        records.append(
            self.artifacts.put_text(
                task_id=task_id,
                kind="proposed-patch",
                text=diff,
                metadata={"applied": patch.ok},
            )
        )
        if not patch.ok:
            self.events.append(
                event_type="hydra.patch.rejected",
                aggregate_id=task_id,
                producer="hydra.runtime.coding_loop",
                trace_id=trace_id,
                payload={"reason": "apply_failed"},
            )
            return CodingLoopResult(False, before.ok, False, records)

        after = await self.sandbox.pytest(test_target)
        records.append(
            self.artifacts.put_text(
                task_id=task_id,
                kind="tests-after",
                text=after.output,
                metadata={"exit_code": after.exit_code},
            )
        )
        accepted = after.ok
        self.events.append(
            event_type="hydra.patch.verified",
            aggregate_id=task_id,
            producer="hydra.runtime.coding_loop",
            trace_id=trace_id,
            payload={
                "before_ok": before.ok,
                "after_ok": after.ok,
                "accepted": accepted,
                "artifact_ids": [str(r.artifact_id) for r in records],
            },
        )
        return CodingLoopResult(accepted, before.ok, after.ok, records)
