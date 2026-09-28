from __future__ import annotations

from uuid import uuid4

from hydra.contracts import HydraTask, Route, TaskStatus
from hydra.events import JsonlEventStore
from hydra.router import CapabilityRouter
from hydra.state import validate_transition


class HydraKernel:
    def __init__(
        self,
        router: CapabilityRouter | None = None,
        events: JsonlEventStore | None = None,
    ):
        self.router = router or CapabilityRouter()
        self.events = events or JsonlEventStore()

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
