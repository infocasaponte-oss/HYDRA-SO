from hydra.circuit_breaker import CircuitState
from hydra.runtime_health import RuntimeHealth
from hydra.runtime_health_store import RuntimeHealthStore


def test_runtime_health_persists_open_circuit(tmp_path):
    path = tmp_path / "hydra.db"
    store = RuntimeHealthStore(path)
    health = RuntimeHealth(store=store)

    for _ in range(3):
        health.failure("variant-1")

    assert health.breaker_for("variant-1").state == CircuitState.OPEN

    restored = RuntimeHealth(store=RuntimeHealthStore(path))
    breaker = restored.breaker_for("variant-1")
    assert breaker.state == CircuitState.OPEN
    assert breaker.failures == 3


def test_runtime_health_persists_success_reset(tmp_path):
    path = tmp_path / "hydra.db"
    health = RuntimeHealth(store=RuntimeHealthStore(path))
    health.failure("variant-1")
    health.success("variant-1")

    restored = RuntimeHealth(store=RuntimeHealthStore(path))
    breaker = restored.breaker_for("variant-1")
    assert breaker.state == CircuitState.CLOSED
    assert breaker.failures == 0
