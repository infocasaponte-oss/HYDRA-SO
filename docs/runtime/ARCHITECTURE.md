# HYDRA Architecture

Copyright (c) 2026 Luis Manuel Cousido Hermida. Todos los derechos reservados.

HYDRA separates four planes.

## Cognitive Plane

Gateway -> Kernel -> Router -> Planner -> Scheduler -> Models/Tools/Memory -> Verifier -> Belief State.

## Corpus Plane

Execution traces -> rights/privacy gate -> curation -> immutable dataset releases.

## Model Plane

Dataset -> training/distillation -> evaluation -> Model Factory -> GGUF/FP8/MLX variants -> registry.

## IP & License Plane

Provenance -> invention/evidence ledger -> SBOM/MBOM/DBOM -> release gate.

## Invariants

1. Models request capabilities; the kernel resolves providers.
2. LLMs never execute host tools directly.
3. Working memory, durable memory and training corpus are separate.
4. Raw experience is never automatically training-eligible.
5. Every promoted model/dataset retains lineage.
6. Production self-modification is forbidden: Observe -> Propose -> Train -> Prove -> Deploy.
