# Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved.
from hydra.runtime.runtime_evidence import RuntimeEvidenceStore


def test_runtime_evidence_hashes_outputs(tmp_path):
    store = RuntimeEvidenceStore(tmp_path / "evidence.jsonl")
    record = store.append(
        trace_id="trace",
        capability="reasoning.general",
        primary_variant_id="active",
        primary_output="same",
        shadow_variant_id="shadow",
        shadow_output="same",
    )
    assert record.exact_agreement is True
    assert len(record.primary_output_sha256) == 64
    assert record.primary_output_sha256 == record.shadow_output_sha256
