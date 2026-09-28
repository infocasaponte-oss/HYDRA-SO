from hydra.code_verification import build_verification_report, extract_targeted_test
from hydra.sandbox import SandboxResult


def test_extract_targeted_test_from_pytest_output(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "test_app.py").write_text("def test_x(): pass")
    assert extract_targeted_test("FAILED test_app.py:1 - boom", root) == "test_app.py"


def test_verification_requires_all_layers():
    failed = SandboxResult(False, "failed", 1)
    passed = SandboxResult(True, "passed", 0)
    report = build_verification_report(
        baseline=failed,
        targeted_target="test_app.py",
        targeted=passed,
        full_suite=passed,
        syntax=passed,
    )
    assert report.improvement_demonstrated is True
    assert report.verified is True

    rejected = build_verification_report(
        baseline=failed,
        targeted_target="test_app.py",
        targeted=passed,
        full_suite=passed,
        syntax=SandboxResult(False, "syntax", 1),
    )
    assert rejected.verified is False
