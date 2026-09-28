# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, Field

from hydra.runtime.artifacts import ArtifactRecord, ArtifactStore


class PrivacyScanStatus(StrEnum):
    NOT_SCANNED = "not_scanned"
    CLEAR = "clear"
    FLAGGED = "flagged"
    INCOMPLETE = "incomplete"


class PrivacyScanResult(BaseModel):
    status: PrivacyScanStatus = PrivacyScanStatus.NOT_SCANNED
    scanner_version: str = "hydra-privacy-v1"
    finding_types: list[str] = Field(default_factory=list)
    artifacts_scanned: int = 0
    bytes_scanned: int = 0


_EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)
_SECRET_RE = re.compile(
    r"(?i)\b(api[_-]?key|password|passwd|secret|access[_-]?token|auth[_-]?token)"
    r"\s*[:=]\s*['\"]?[^\s'\"]{6,}"
)
_PRIVATE_KEY_RE = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")


class PrivacyScanner:
    def __init__(
        self,
        *,
        max_artifact_bytes: int = 1 * 1024 * 1024,
        max_total_bytes: int = 4 * 1024 * 1024,
    ):
        self.max_artifact_bytes = max_artifact_bytes
        self.max_total_bytes = max_total_bytes

    def scan(
        self,
        artifacts: list[ArtifactRecord],
        store: ArtifactStore,
    ) -> PrivacyScanResult:
        findings: set[str] = set()
        scanned = 0
        total = 0
        incomplete = False

        text_artifacts = [
            artifact
            for artifact in artifacts
            if artifact.media_type.startswith("text/")
            or "json" in artifact.media_type
        ]
        if not text_artifacts:
            return PrivacyScanResult(status=PrivacyScanStatus.INCOMPLETE)

        for artifact in text_artifacts:
            try:
                data = store.get_bytes(
                    artifact.sha256,
                    max_bytes=self.max_artifact_bytes,
                )
            except (FileNotFoundError, ValueError):
                incomplete = True
                continue

            if total + len(data) > self.max_total_bytes:
                incomplete = True
                break

            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                incomplete = True
                continue

            scanned += 1
            total += len(data)
            if _EMAIL_RE.search(text):
                findings.add("email")
            if _SECRET_RE.search(text):
                findings.add("credential_or_secret")
            if _PRIVATE_KEY_RE.search(text):
                findings.add("private_key")

        if findings:
            status = PrivacyScanStatus.FLAGGED
        elif incomplete or scanned != len(text_artifacts):
            status = PrivacyScanStatus.INCOMPLETE
        else:
            status = PrivacyScanStatus.CLEAR

        return PrivacyScanResult(
            status=status,
            finding_types=sorted(findings),
            artifacts_scanned=scanned,
            bytes_scanned=total,
        )
