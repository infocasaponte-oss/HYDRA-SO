# Arquitectura de HYDRA 1.0

Copyright (c) 2026 Luis Manuel Cousido Hermida. Todos los derechos reservados.

## Planos

| Plano | Paquetes |
|---|---|
| Cognitivo | `hydra.core` (kernel, contratos, máquina de estados, capture), `hydra.router`, `hydra.scheduler`, `hydra.workers`, `hydra.verification`, `hydra.meta`, `hydra.memory`, `hydra.world`, `hydra.planning`, `hydra.market` |
| Ejecución | `hydra.tools` (incl. workspace y tests estructurados), `hydra.cluster` (nodos, scheduler, fabric, capacidad), `hydra.providers`, `hydra.edge` |
| Aprendizaje | `hydra.corpus`, `hydra.training`, `hydra.model_factory`, `hydra.discovery`, `hydra.federated`, `hydra.lab`, `hydra.evals`, `hydra.replay` |
| IP y gobernanza | `hydra.ledger` (chain, signing, ip, licenses, bom, release), `hydra.governance` (security, boundary, secrets, policy_dsl, config_registry, redteam, invariants, recovery), `hydra.policy` |
| Interfaces | `hydra.api` (gateway, rutas OS y plataforma, Studio), `hydra.protocols` (MCP), `hydra.sdk`, `hydra.cli`, `sdk/typescript` |
| Observabilidad | `hydra.observability` (OTLP GenAI, flamegraph, costes, Prometheus), `hydra.telemetry` |

## Contratos estables

`hydra.core.task`: `HydraTask`, `HydraResult`, `EventEnvelope` (con `schema_version` y `payload_hash`),
`ContextFragment`, `SecurityContext`. Los servicios se comunican con estos contratos, eventos y APIs;
nunca con modelos internos de otro paquete.

## Almacenamiento

Local por defecto (`HYDRA_DATA_DIR`): `ledger/` (JSONL encadenado + anclas), `artifacts/` (CAS por sha256),
`world/` (log de deltas = versiones), `corpus/` (log versionado, linaje, tombstones, snapshots, releases),
`ip/`, `flight/`, `fabric/queue.db` (SQLite WAL), `planning/`, `training/`, `configs/`, `keys/`.
Multi-nodo: tablas equivalentes en `sql/schema.sql`, blobs en almacenamiento de objetos, bus NATS/Redis.

## Cadenas de suministro

Código, datos, modelos e IP siguen la misma disciplina: artefacto → evaluación → firma → linaje → gate
→ promoción. El grafo maestro PERSONA → CÓDIGO → EXPERIMENTO → DATOS → DATASET → MODELO → RESULTADO →
INVENCIÓN → PRODUCTO se reconstruye desde el ledger, el linaje del corpus y el del Model Factory.
