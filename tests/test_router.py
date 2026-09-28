from hydra.contracts import HydraTask, TaskType
from hydra.router import CapabilityRouter


def test_routes_translation():
    route = CapabilityRouter().route(HydraTask(goal="Traduce este documento al inglés"))
    assert route.task_type == TaskType.TRANSLATION
    assert route.capability == "language.translate"


def test_routes_coding_with_verification():
    route = CapabilityRouter().route(HydraTask(goal="Debug this Python test failure"))
    assert route.task_type == TaskType.CODING
    assert route.needs_tools is True
    assert route.needs_verification is True
