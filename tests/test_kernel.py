from hydra.contracts import HydraTask, TaskStatus, TaskType
from hydra.events import JsonlEventStore
from hydra.kernel import HydraKernel


def test_kernel_prepares_and_records_route(tmp_path):
    events = JsonlEventStore(tmp_path / "events.jsonl")
    kernel = HydraKernel(events=events)
    task = HydraTask(goal="Traduce hola al inglés")
    trace_id, route = kernel.prepare(task)
    assert trace_id
    assert task.status == TaskStatus.ROUTING
    assert route.task_type == TaskType.TRANSLATION
    recorded = events.for_aggregate(task.id)
    assert [e.event_type for e in recorded] == [
        "hydra.task.created",
        "hydra.task.transitioned",
        "hydra.route.completed",
    ]
