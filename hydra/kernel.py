from __future__ import annotations

from uuid import uuid4

from hydra.contracts import HydraResult, HydraTask, Route, TaskStatus
from hydra.events import JsonlEventStore
from hydra.executor import Executor
from hydra.model_registry import ModelRegistry
from hydra.planner import Planner
from hydra.provider import LocalLLM
from hydra.router import CapabilityRouter
from hydra.state import validate_transition
from hydra.verifier import Verifier


class HydraKernel:
    def __init__(
        self,
        router: CapabilityRouter | None = None,
        events: JsonlEventStore | None = None,
        planner: Planner | None = None,
    ):
        self.router = router or CapabilityRouter()
        self.events = events or JsonlEventStore()
        self.planner = planner or Planner()

    def _transition(self, task: HydraTask, target: TaskStatus, trace_id: str) -> None:
        validate_transition(task.status, target)
        previous = task.status
        task.status = target
        self.events.append(
            event_type="hydra.task.transitioned",
            aggregate_id=task.id,
            producer="hydra.kernel",
            trace_id=trace_id,
            payload={"from": previous.value, "to": target.value},
        )

    def prepare(self, task: HydraTask) -> tuple[str, Route]:
        trace_id = uuid4().hex
        self.events.append(
            event_type="hydra.task.created",
            aggregate_id=task.id,
            producer="hydra.kernel",
            trace_id=trace_id,
            payload={"goal": task.goal, "budget": task.budget.model_dump()},
        )
        self._transition(task, TaskStatus.ROUTING, trace_id)
        route = self.router.route(task)
        self.events.append(
            event_type="hydra.route.completed",
            aggregate_id=task.id,
            producer="hydra.router",
            trace_id=trace_id,
            payload=route.model_dump(),
        )
        return trace_id, route

    async def run(self, task: HydraTask, llm: LocalLLM) -> HydraResult:
        trace_id, route = self.prepare(task)

        self._transition(task, TaskStatus.PLANNING, trace_id)
        plan = self.planner.build(task, route)
        self.events.append(
            event_type="hydra.plan.created",
            aggregate_id=task.id,
            producer="hydra.planner",
            trace_id=trace_id,
            payload=plan.model_dump(mode="json"),
        )

        self._transition(task, TaskStatus.EXECUTING, trace_id)
        executor = Executor(llm, ModelRegistry(), Verifier())
        output = await executor.execute(plan, task.budget.max_output_tokens)

        self.events.append(
            event_type="hydra.model.completed",
            aggregate_id=task.id,
            producer="hydra.executor",
            trace_id=trace_id,
            payload={"model_id": output.model_id},
        )

        confidence = 0.55
        if route.needs_verification:
            self._transition(task, TaskStatus.VERIFYING, trace_id)
            verification = output.verification or Verifier().verify_text(output.answer)
            self.events.append(
                event_type="hydra.verification.completed",
                aggregate_id=task.id,
                producer="hydra.verifier",
                trace_id=trace_id,
                payload=verification.model_dump(),
            )
            confidence = verification.confidence
            self._transition(task, TaskStatus.SYNTHESIZING, trace_id)
        else:
            self._transition(task, TaskStatus.SYNTHESIZING, trace_id)

        self._transition(task, TaskStatus.COMPLETED, trace_id)
        result = HydraResult(
            task_id=task.id,
            status=task.status,
            answer=output.answer,
            confidence=confidence,
            trace_id=trace_id,
            metadata={"model_id": output.model_id, "capability": route.capability},
        )
        self.events.append(
            event_type="hydra.task.completed",
            aggregate_id=task.id,
            producer="hydra.kernel",
            trace_id=trace_id,
            payload={"confidence": confidence, "model_id": output.model_id},
        )
        return result
