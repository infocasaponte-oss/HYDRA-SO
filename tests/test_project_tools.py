# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
import subprocess

from hydra import project_tools


def test_doctor_is_read_only_and_declares_backend_limits(monkeypatch):
    monkeypatch.setattr(project_tools.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("execution")))
    result = project_tools.inventory()
    assert not result["automatic_launch"] and not result["automatic_install"]
    assert result["four_b_training_backend"] == "pending validation"
    assert "prepare-4b" in result["tools"]


def test_bare_selection_shows_help_and_literal_arguments_are_preserved(monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 7)

    monkeypatch.setattr(project_tools.subprocess, "run", run)
    assert project_tools.main(["prepare-4b"]) == 7
    assert calls[0][0][-1] == "--help"
    assert project_tools.main(["corpus-audit", "--", "--corpus", "path with spaces;literal"]) == 7
    assert calls[1][0][-1] == "path with spaces;literal"
    assert "shell" not in calls[1][1]
