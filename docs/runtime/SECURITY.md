# Security Policy

Copyright (c) 2026 Luis Manuel Cousido Hermida. Todos los derechos reservados.

HYDRA is currently pre-alpha.

## Current constraints

- Bind development services to localhost.
- Do not expose llama.cpp/vLLM directly to the public Internet.
- Never commit credentials, model-provider tokens or private datasets.
- Do not execute generated code on the host; the planned Tool Runtime must use isolated sandboxes.
- Treat downloaded model weights and datasets as untrusted artifacts until verified.

## Reporting

Use the repository's private security reporting mechanism when enabled. Do not publish secrets or exploitable vulnerabilities in public issues.
