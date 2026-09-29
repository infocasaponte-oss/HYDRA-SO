# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
from __future__ import annotations

from pydantic import BaseModel, Field


class VerificationResult(BaseModel):
    accepted: bool
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)
    reason: str


class Verifier:
    def verify_text(self, answer: str) -> VerificationResult:
        clean = answer.strip()
        if not clean:
            return VerificationResult(
                accepted=False,
                confidence=0.0,
                reason="empty_answer",
            )
        # This is structural verification only. Semantic verification arrives later.
        confidence = 0.60 if len(clean) >= 8 else 0.45
        return VerificationResult(
            accepted=True,
            confidence=confidence,
            evidence=["non_empty_output"],
            reason="structural_checks_passed",
        )
