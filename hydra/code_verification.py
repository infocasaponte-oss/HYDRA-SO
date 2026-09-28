from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from hydra.sandbox import SandboxResult


@dataclass(frozen=True)
class VerificationReport:
    baseline_failed: bool
    targeted_target: str | None
    targeted_passed: bool
    full_suite_passed: bool
    syntax_passed: bool
    improvement_demonstrated: bool
    verified: bool


def extract_targeted_test(pytest_output: str, workspace: str | Path) -> str | None:
    root = Path(workspace).resolve()
    for token in pytest_output.split():
        cleaned = token.strip("()[]{}<>,;'\"")
        marker = cleaned.find(".py")
        if marker < 0:
            continue
        raw = cleaned[: marker + 3]
        candidate = (root / raw).resolve()
        if candidate == root or root not in candidate.parents:
            continue
        if candidate.is_file():
            return str(candidate.relative_to(root))
    return None


def build_verification_report(
    *,
    baseline: SandboxResult,
    targeted_target: str | None,
    targeted: SandboxResult,
    full_suite: SandboxResult,
    syntax: SandboxResult,
) -> VerificationReport:
    improvement = (not baseline.ok) and full_suite.ok
    verified = improvement and targeted.ok and full_suite.ok and syntax.ok
    return VerificationReport(
        baseline_failed=not baseline.ok,
        targeted_target=targeted_target,
        targeted_passed=targeted.ok,
        full_suite_passed=full_suite.ok,
        syntax_passed=syntax.ok,
        improvement_demonstrated=improvement,
        verified=verified,
    )
