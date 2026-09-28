# HYDRA-SO

**HYDRA** es un sistema operativo cognitivo híbrido orientado a orquestar modelos locales/cloud, herramientas, memoria, verificación, corpus de entrenamiento y trazabilidad de modelos/datos/IP.

> Estado: **pre-alpha / research & engineering prototype**.

## Primer objetivo de hardware

La implementación inicial está diseñada para una **NVIDIA GeForce RTX 3060 Ti (8 GB)** usando `llama.cpp` + CUDA y modelos GGUF cuantizados.

## Capacidades iniciales

- inferencia local OpenAI-compatible;
- routing por capacidades;
- traducción multilingüe;
- perfiles automáticos de hardware;
- selección/benchmark de runtime;
- Model Scout para GGUF;
- ejecución verificable y event sourcing (roadmap);
- Corpus Engine y provenance/IP ledger (roadmap);
- Model Factory / Cognitive JIT (roadmap).

## Arquitectura

```text
Input/API
   |
Gateway
   |
Cognitive Kernel
   +-- Router / Planner / Scheduler
   +-- Models / Tools / Memory
   +-- Verifier / Belief State
   |
Capture
   +-- Corpus
   +-- Telemetry
   +-- Provenance / IP
   |
Model Factory / Training Lab
```

## Seguridad

No expongas `llama-server` directamente a Internet. El prototipo debe permanecer ligado a localhost hasta incorporar autenticación, rate limiting, sandboxing y Policy Engine.

## Desarrollo

Requiere Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

## Estado del proyecto

La primera rama de desarrollo construirá **HYDRA Runtime v0.3.1 (Audit Hardening)** y posteriormente el Cognitive Kernel.

Consulta `docs/ROADMAP.md` y `docs/ARCHITECTURE.md`.
