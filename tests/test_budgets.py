import pytest

from hydra.budgets import BudgetExceeded, RequestBudget


def test_rejects_oversized_input():
    budget = RequestBudget(max_input_chars=4)
    with pytest.raises(BudgetExceeded):
        budget.validate_input("12345")


def test_caps_output_tokens():
    budget = RequestBudget(max_output_tokens=100)
    assert budget.output_tokens(500) == 100
