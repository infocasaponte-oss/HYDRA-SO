from __future__ import annotations

from dataclasses import dataclass, field

from hydra.circuit_breaker import CircuitBreaker


@dataclass
class RuntimeHealth:
    breakers: dict[str, CircuitBreaker] = field(default_factory=dict)

    def breaker_for(self, variant_id: str) -> CircuitBreaker:
        return self.breakers.setdefault(variant_id, CircuitBreaker())

    def available(self, variant_id: str) -> bool:
        return self.breaker_for(variant_id).allow()

    def success(self, variant_id: str) -> None:
        self.breaker_for(variant_id).record_success()

    def failure(self, variant_id: str) -> None:
        self.breaker_for(variant_id).record_failure()
