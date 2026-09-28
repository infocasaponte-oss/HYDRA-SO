import pytest

from hydra.contracts import TaskStatus
from hydra.state import InvalidTransition, validate_transition


def test_valid_transition():
    validate_transition(TaskStatus.CREATED, TaskStatus.ROUTING)


def test_terminal_transition_rejected():
    with pytest.raises(InvalidTransition):
        validate_transition(TaskStatus.COMPLETED, TaskStatus.ROUTING)
