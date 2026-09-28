# HYDRA Deployment Lifecycle

Model quality promotion and production deployment are separate decisions.

PROMOTED -> CANDIDATE -> SHADOW -> CANARY -> ACTIVE -> DEPRECATED -> RETIRED

A candidate cannot skip directly to ACTIVE.

Shadow compares the candidate against the currently active path without making it authoritative. Advancement requires a minimum sample count, agreement threshold and error-rate ceiling.

Canary makes the candidate eligible for a limited production path. Activation requires a minimum request count plus error-rate and p95-latency gates.

When a new generation becomes ACTIVE, the overlapping previous generation becomes DEPRECATED rather than being deleted. HYDRA can therefore roll back to the latest compatible prior generation.

The current alpha controller encodes the lifecycle and evidence contracts. Traffic splitting and persistence of deployment evidence are subsequent runtime layers.
