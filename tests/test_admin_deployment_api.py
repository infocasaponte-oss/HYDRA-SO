import hashlib
import struct

from fastapi.testclient import TestClient

from hydra import api
from hydra.deployment_controller import DeploymentController
from hydra.deployment_evidence_store import DeploymentEvidenceStore
from hydra.deployment_store import DeploymentStore
from hydra.deployment_validation import DeploymentArtifactValidator
from hydra.model_factory import BuildState, ModelLineage, ModelVariant
from hydra.rate_limit import RateLimit, SlidingWindowRateLimiter
from hydra.security import SecurityConfig


def _string(value: str) -> bytes:
    raw = value.encode("utf-8")
    return struct.pack("<Q", len(raw)) + raw


def _variant(models_root, quantization: str) -> ModelVariant:
    entries = [
        _string("general.architecture")
        + struct.pack("<I", 8)
        + _string("llama"),
        _string("llama.context_length")
        + struct.pack("<I", 4)
        + struct.pack("<I", 8192),
        _string("llama.embedding_length")
        + struct.pack("<I", 4)
        + struct.pack("<I", 4096),
        _string("llama.block_count")
        + struct.pack("<I", 4)
        + struct.pack("<I", 32),
    ]
    payload = (
        b"GGUF"
        + struct.pack("<I", 3)
        + struct.pack("<Q", 1)
        + struct.pack("<Q", len(entries))
        + b"".join(entries)
    )
    filename = f"{quantization}.gguf"
    (models_root / filename).write_bytes(payload)
    return ModelVariant(
        lineage=ModelLineage(
            base_model="base",
            base_model_sha256="a" * 64,
        ),
        quantization=quantization,
        artifact_path=filename,
        artifact_sha256=hashlib.sha256(payload).hexdigest(),
        state=BuildState.PROMOTED,
    )


def test_admin_deployment_lifecycle_and_rollback(tmp_path):
    original_security = api.security_config
    original_store = api.deployment_store
    original_registry = api.deployment_registry
    original_evidence_store = api.deployment_evidence_store
    original_controller = api.deployment_controller
    original_validator = api.deployment_artifact_validator
    original_limiter = api.rate_limiter
    original_limit = api.admin_rate_limit

    path = tmp_path / "deployments.json"
    temp_store = DeploymentStore(path)
    temp_registry = temp_store.load()
    temp_evidence = DeploymentEvidenceStore(tmp_path / "hydra.db")
    models_root = tmp_path / "models"
    models_root.mkdir()

    api.security_config = SecurityConfig(api_token=None, admin_token="admin-secret")
    api.deployment_store = temp_store
    api.deployment_registry = temp_registry
    api.deployment_evidence_store = temp_evidence
    api.deployment_controller = DeploymentController(
        temp_registry,
        evidence_store=temp_evidence,
    )
    api.deployment_artifact_validator = DeploymentArtifactValidator(models_root)
    api.rate_limiter = SlidingWindowRateLimiter()
    api.admin_rate_limit = RateLimit(requests=100, window_seconds=60)

    headers = {"Authorization": "Bearer admin-secret"}

    try:
        with TestClient(api.app) as client:
            first = _variant(models_root, "Q4_K_M")
            second = _variant(models_root, "Q5_K_M")

            for generation, variant in [(1, first), (2, second)]:
                registered = client.post(
                    "/hydra/v1/admin/deployments/register",
                    headers=headers,
                    json={
                        "variant": variant.model_dump(mode="json"),
                        "capabilities": ["reasoning.general"],
                        "generation": generation,
                    },
                )
                assert registered.status_code == 200

                shadow = client.post(
                    f"/hydra/v1/admin/deployments/{variant.variant_id}/shadow",
                    headers=headers,
                )
                assert shadow.status_code == 200
                assert shadow.json()["state"] == "shadow"

                canary = client.post(
                    f"/hydra/v1/admin/deployments/{variant.variant_id}/canary",
                    headers=headers,
                    json={
                        "samples": 20,
                        "agreement_rate": 0.96,
                        "error_rate": 0.0,
                    },
                )
                assert canary.status_code == 200
                assert canary.json()["state"] == "canary"

                active = client.post(
                    f"/hydra/v1/admin/deployments/{variant.variant_id}/activate",
                    headers=headers,
                    json={
                        "requests": 20,
                        "error_rate": 0.0,
                        "p95_latency_ms": 500.0,
                    },
                )
                assert active.status_code == 200
                assert active.json()["state"] == "active"

            listed = client.get(
                "/hydra/v1/admin/deployments",
                headers=headers,
            )
            assert listed.status_code == 200
            states = {
                item["variant_id"]: item["state"]
                for item in listed.json()["deployments"]
            }
            assert states[str(first.variant_id)] == "deprecated"
            assert states[str(second.variant_id)] == "active"

            rollback = client.post(
                "/hydra/v1/admin/deployments/rollback/reasoning.general",
                headers=headers,
            )
            assert rollback.status_code == 200
            assert rollback.json()["variant_id"] == str(first.variant_id)

        restored = DeploymentStore(path).load()
        active = restored.active_for("reasoning.general")
        assert active.variant_id == first.variant_id
        assert temp_evidence.latest_shadow(str(second.variant_id)) is not None
        assert temp_evidence.latest_canary(str(second.variant_id)) is not None
    finally:
        api.security_config = original_security
        api.deployment_store = original_store
        api.deployment_registry = original_registry
        api.deployment_evidence_store = original_evidence_store
        api.deployment_controller = original_controller
        api.deployment_artifact_validator = original_validator
        api.rate_limiter = original_limiter
        api.admin_rate_limit = original_limit
