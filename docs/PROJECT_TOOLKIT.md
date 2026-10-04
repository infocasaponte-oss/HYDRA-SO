<!-- Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved. -->
# Ferramentas do proxecto

Entrada integrada: `hydra-project-tools` tras instalar esta versión de HYDRA, ou `python -m hydra.project_tools` desde o checkout. Sen argumentos mostra un inventario local. Non instala paquetes, contacta servizos externos nin inicia adestramentos. Seleccionar unha ferramenta sen argumentos mostra a súa axuda.

```powershell
python -m hydra.project_tools doctor
python -m hydra.project_tools corpus-audit -- --corpus D:/ruta/corpus --out D:/ruta/auditoria-nova.json
python -m hydra.project_tools prepare-4b -- --verify-meta --out D:/ruta/preparacion-nova.json
python -m hydra.project_tools hyd-calibrator -- --help
python -m hydra.project_tools hyd-lab -- --help
python -m hydra.project_tools base-tokenizer
python -m hydra.project_tools base-trainer
```

O catálogo reúne recepción/auditoría do corpus, preparación 4B, tokenizer, laboratorio persistente, adestramento independente de Hyd, calibración, informes e exportación shadow. O adestrador base actual só ten perfís 30M/125M. O backend para adestrar 4B segue pendente; non se presenta como instalado ou probado.

Dependencias opcionais: as de adestramento están no extra `training`, as de Parquet en `parquet` e as de verificación en `dev` de pyproject.toml. Instalar nunha contorna separada do adestramento activo, por exemplo `python -m pip install -e ".[training,parquet,dev]"`. Non actualizar a contorna dun proceso en marcha. O calibrador é un paquete separado da PR #1 de infocasaponte-oss/Hyd: instalar o wheel revisado nesa mesma contorna de ferramentas. `doctor` distingue metadatos de distribución de descubrimento de módulos; non certifica versións compatibles por atopar un paquete.

A área humana mellorada está no ZIP local hydra-calibrator-mellorado-2026-10-04.zip, con código, probas e migración aditiva. Non se incorpora silenciosamente ao servidor HYDRA nin se conecta a Supabase. Aplicación real de SQL, políticas existentes e OAuth necesitan a conta/configuración e probas reais. O proveedor de segunda opinión é configurable, sen autoridade de etiqueta.

As funcións de avaliación, Model Factory, benchmarking, canary e rollback xa forman parte da CLI `hydra model`/`hydra eval`/`hydra lab`; consultar `hydra --help`. A súa existencia non implica validación do novo candidato: cada release precisa evidencia e configuración propias.

Guías detalladas: docs/HYD_TOOLS.md e docs/CORPUS_4B_PREFLIGHT.md. As ferramentas preparan resultados revisables; non aproban corpus, modelos ou produción automaticamente.
