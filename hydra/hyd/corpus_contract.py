# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
"""Strict intake contract for human-labelled routing evidence, not an authorship oracle."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from hydra.core.atomic import write_text_atomic
from hydra.hyd.integration import contract
from hydra.router.decision_contract import CRITERIA


class Rights(BaseModel):
    model_config = ConfigDict(extra="forbid")
    license: str = Field(min_length=1, max_length=200)
    verified: StrictBool
    evidence_ref: str = Field(min_length=1, max_length=500)


class HumanReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reviewer_id: str = Field(min_length=1, max_length=200)
    person_id: str = Field(min_length=1, max_length=200)
    label: str
    reviewed_at: str = Field(min_length=1, max_length=100)
    kind: Literal["human"]


class IntakeRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=200)
    original_text: str = Field(min_length=1, max_length=50000)
    text: str = Field(min_length=1, max_length=50000)
    expected: str
    family_id: str = Field(min_length=1, max_length=200)
    source_kind: Literal["user_traffic", "human_evaluator", "ai_assisted", "synthetic", "unknown"]
    consent: StrictBool
    consent_version: str = Field(min_length=1, max_length=100)
    consent_event_ref: str = Field(min_length=1, max_length=500)
    privacy_reviewed: StrictBool
    suspect_template: StrictBool
    rights: Rights
    reviews: list[HumanReview] = Field(max_length=10)
    correction: dict | None = None
    ai_second_opinions: list[dict] = Field(default_factory=list, max_length=20)
    withdrawn: StrictBool = False

    @model_validator(mode="after")
    def semantic(self):
        if not self.text.strip() or not self.original_text.strip() or self.expected not in CRITERIA:
            raise ValueError("nonempty original/text and known label required")
        if any(r.label not in CRITERIA or not r.reviewer_id.strip() for r in self.reviews):
            raise ValueError("invalid human review")
        if self.text != self.original_text and (not isinstance(self.correction, dict)
                or self.correction.get("human_accepted") is not True
                or not self.correction.get("reviewer_id") or not self.correction.get("reason")):
            raise ValueError("derived text needs explicit human acceptance and reason")
        return self

    def admissible(self, require_double_review: bool = True) -> bool:
        # Identity/evidence references are declared inputs, not cryptographic verification.
        reviewers = {r.reviewer_id for r in self.reviews if r.label == self.expected}
        people = {r.person_id for r in self.reviews if r.label == self.expected}
        enough_reviews = len(reviewers) >= 2 and len(people) >= 2 if require_double_review else len(reviewers) >= 1
        return (not self.withdrawn and self.consent and self.privacy_reviewed and not self.suspect_template
                and self.rights.verified and enough_reviews
                and all(r.label == self.expected for r in self.reviews)
                and self.source_kind in ("user_traffic", "human_evaluator"))


def inspect_intake(path: Path) -> tuple[list[IntakeRecord], dict]:
    raw = Path(path).read_bytes()
    records, errors, ids, texts = [], [], set(), set()
    for number, line in enumerate(raw.decode("utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = IntakeRecord.model_validate_json(line)
            key = " ".join(record.text.casefold().split())
            if record.id in ids or key in texts:
                raise ValueError("duplicate id or normalized text; review before snapshot")
            ids.add(record.id)
            texts.add(key)
            records.append(record)
        except ValueError:
            # Do not echo submitted questions or personal information in an error response.
            errors.append({"line": number, "error": "invalid intake contract or duplicate"})
    return records, {"format": "hyd-intake-validation/1", "source_sha256": hashlib.sha256(raw).hexdigest(),
                     "n": len(records), "admissible": sum(r.admissible(False) for r in records),
                     "double_reviewed": sum(r.admissible() for r in records),
                     "quarantined": sum(not r.admissible(False) for r in records), "errors": errors,
                     "complete": not errors, "contract": contract()}


def snapshot(path: Path, out: Path, review_mode: str = "development") -> dict:
    if review_mode not in ("development", "double_review"):
        raise ValueError("unknown review mode")
    records, validation = inspect_intake(path)
    if not validation["complete"] or not records:
        raise ValueError("invalid or empty intake; no snapshot created")
    if Path(out).exists():
        raise ValueError("snapshot destination already exists")
    selected = [r for r in records if r.admissible(review_mode == "double_review")]
    if {r.expected for r in selected} != set(CRITERIA):
        raise ValueError("admissible corpus must cover every class")
    # All variants of a family stay together. Sort for stable byte-for-byte exports.
    parts = {"train": [], "calibration": [], "test": []}
    for record in sorted(selected, key=lambda r: r.id):
        bucket = int(hashlib.sha256(record.family_id.encode()).hexdigest()[:8], 16) % 100
        split = "train" if bucket < 70 else "calibration" if bucket < 85 else "test"
        parts[split].append({"id": record.id, "split": split, "family_id": record.family_id,
                            "input": {"query": record.text}, "output": {"task_type": record.expected},
                            "training_allowed": split == "train", "consent": True,
                            "rights": record.rights.model_dump(),
                            "meta": {"source_kind": record.source_kind,
                                     "original_sha256": hashlib.sha256(record.original_text.encode()).hexdigest(),
                                     "consent_event_ref": record.consent_event_ref,
                                     "consent_version": record.consent_version,
                                     "review_count": len(record.reviews), "correction": record.correction is not None}})
    if any(not part for part in parts.values()):
        raise ValueError("empty partition; collect more independent families before freezing")
    Path(out).mkdir(parents=True)
    hashes = {}
    for name, rows in parts.items():
        target = Path(out) / f"{name}.jsonl"
        write_text_atomic(target, "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows))
        hashes[name] = hashlib.sha256(target.read_bytes()).hexdigest()
    manifest = {"format": "hyd-human-snapshot/1", "contract": contract(), "source_sha256": validation["source_sha256"],
                "counts": {name: len(rows) for name, rows in parts.items()}, "sha256": hashes,
                "quarantined": len(records)-len(selected), "review_mode": review_mode, "independent_test": False,
                "limitation": "Family membership, origin, rights and reviewer identity are declared and require source-system verification."}
    write_text_atomic(Path(out) / "manifest.json", json.dumps(manifest, indent=2))
    return manifest
