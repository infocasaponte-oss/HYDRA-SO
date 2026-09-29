# Seguridad de HYDRA

Copyright (c) 2026 Luis Manuel Cousido Hermida. Todos los derechos reservados.

## Modelo de amenazas (resumen)
| Amenaza | Control |
|---|---|
| Inyección de instrucciones en documentos/web | Frontera de contenido no confiable (`hydra.governance.boundary`): etiquetado de fuente, detección, neutralización, `<untrusted_data>` |
| Exfiltración de secretos | Secrets Broker (`secret://`), redacción de salidas, Policy Kernel (sensibilidad → solo local), corpus bloquea credenciales |
| Acciones destructivas | Capacidades mínimas por worker, motor de riesgo (D,E,P,F,I), confirmación explícita, simulación previa, sandbox Docker sin red |
| Modelos maliciosos | Supply-chain scanner (opcodes pickle, `auto_map`/código remoto, lista blanca de arquitecturas), firma Ed25519 obligatoria para producción |
| Manipulación de evidencias | Ledger hash-encadenado y firmado, anclas Merkle, CAS con verificación, triggers append-only en PostgreSQL |
| Fuga entre inquilinos | `TenantRegistry` (modelos, herramientas, presupuesto, residencia), filtros por `tenant_id` en corpus |
| Divulgación prematura de invenciones | Disclosure firewall en la Release Gate |

## Pruebas continuas
`hydra redteam` (inyección, secretos, peticiones prohibidas, herramientas peligrosas, JSON malformado,
evidencias en conflicto, contexto gigante, fallo de modelo, OOM de GPU, artefacto corrupto, ledger
manipulado, registro de corpus malicioso). Cada fallo se convierte en caso de regresión y en corpus de fallos.
