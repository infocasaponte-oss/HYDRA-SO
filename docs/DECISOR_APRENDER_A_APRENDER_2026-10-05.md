<!-- Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved. -->
# Decisor: aprender a aprender, y después las personas — 5 de octubre de 2026

Copyright (c) 2026 Luis Manuel Cousido Hermida. Todos los derechos reservados.

## Idea

El [corpus v4](INFORME_CORPUS_DECISION_V4_2026-10-05.md) mostró que el decisor acierta un 54 % con redacciones nuevas. Etiquetar a mano es caro, así que el sistema primero aprende **qué ejemplos le enseñan más rápido**. Después pide a una persona que etiquete justo esos ejemplos. Ninguna etiqueta la pone el modelo.

Módulo: `hydra/training/decision_active_learning.py`. Tres órdenes independientes; ninguna toca pesos en servicio, corpus publicados ni `models/`.

```powershell
# 1. Aprender a aprender: comparar estrategias de selección (solo CPU, unos 2 minutos)
python -m hydra.training.decision_active_learning simulate --out D:/ruta/simulacion-nueva.json

# 2. Ronda real: el modelo elige qué preguntar a las personas
python -m hydra.training.decision_active_learning queue --pool D:/ruta/peticiones-sin-etiqueta.jsonl `
    --strategy-from D:/ruta/simulacion-nueva.json -k 40 --out D:/ruta/revision-ronda-001

# 3. Tras la revisión humana: admitir solo lo que una persona etiquetó y firmó
python -m hydra.training.decision_active_learning admit --queue D:/ruta/revision-ronda-001 `
    --out D:/ruta/admitidos-ronda-001.jsonl
```

## 1. Simulación: elegir cómo aprender

Se parte de `decision-corpus-v4/train` (480 ejemplos) y de un conjunto de 300 textos únicos de `human-dev-v1/v2`, cuyas etiquetas permanecen ocultas hasta que se «adquiere» la fila. Así se simula la respuesta de una persona. En cada ronda se reentrena el decisor y se piden 10 etiquetas más, hasta 80.

Estrategias comparadas:
- `random`: al azar (3 semillas), como referencia.
- `margin`: lo que el modelo tiene más dudoso entre sus dos primeras opciones.
- `entropy`: lo que tiene más repartido entre todas.
- `safety_margin`: como `margin`, pero antepone los casos en que el modelo da al menos un 15 % a `high_risk_review` o `security` sin elegirlos. Fallar ahí es el error caro.

Además, en cada lote se evita preguntar dos veces por frases casi idénticas (SimHash).

La estrategia se elige **solo con la partición de calibración**. El test congelado se puntúa una vez al final, como informe, y nunca decide.

| Estrategia | Área bajo la curva (calibración) | Calibración tras 80 etiquetas | Test tras 80 etiquetas (solo informe) |
|---|---|---|---|
| random (media de 3) | 0,598 | 63,3 % | 54,6 % |
| margin | 0,588 | 66,3 % | 60,0 % |
| entropy | 0,622 | 66,3 % | 60,0 % |
| **safety_margin** (elegida) | **0,631** | **68,8 %** | **61,3 %** |

Punto de partida, sin etiquetas nuevas: 58,8 % en calibración. Evidencia: `docs/evidence/decision-active-learning-simulation-2026-10-05.json`.

**Lectura honesta.** Elegir bien las preguntas aprende más deprisa que preguntar al azar, y `safety_margin` queda primera. Pero la calibración tiene 80 filas: 3 puntos son 2 o 3 aciertos, así que el orden entre estrategias inteligentes no está demostrado. Hay que repetir la simulación tras cada ronda humana; la orden `queue` puede leer la estrategia ganadora directamente del último informe (`--strategy-from`).

## 2. Cola de revisión humana

`queue` toma un JSONL de peticiones sin etiqueta (`text` o `input.query`; si trae etiquetas, se ignoran) y escribe un directorio nuevo e inmutable:
- `queue.jsonl`, una fila por pregunta, con `text`, las 3 sugerencias del modelo con su probabilidad, `safety_flag`, y los campos vacíos `human_label`, `reviewer` y `notes`.
- `manifest.json`, con estrategia, hashes de entrada, etiquetas válidas, instrucciones y `training_allowed: false`.

Se descartan textos ya presentes en el entrenamiento y duplicados. **Las filas con datos personales detectados por el `PrivacyGate` de HYDRA no llegan a la cola**; solo queda el recuento.

## 3. Entran las personas

La persona revisora rellena `human_label` con una etiqueta válida, o `discard`, y `reviewer` con su nombre o iniciales. Las sugerencias del modelo son pistas, no respuestas.

`admit` crea un archivo de entrenamiento nuevo con `training_allowed: true`, solo con filas que tienen etiqueta válida y revisor. Las demás se cuentan y quedan fuera. Informa también de cuántas veces coincidió la persona con el modelo. Ese archivo se añade a las fuentes de `train_decision_v4.py` para entrenar un **candidato**, que se mide con el test v4 antes de cualquier promoción.

## Qué falta y qué necesito

1. **Peticiones reales sin etiqueta.** HYDRA no guarda el texto de las peticiones en telemetría, y es correcto que no lo haga. Para la primera ronda hace falta un archivo de peticiones reales o realistas, recogidas con permiso.
2. **Codificador semántico.** Este contenedor no puede descargar modelos de HuggingFace. El bucle no depende del modelo; en tu equipo puede usar el `LlamaCppEncoder` existente (`hydra/hyd/embedding.py`) para un decisor con *embeddings*. Es lo que más puede subir del 54–61 %.
3. Una interfaz de revisión más cómoda que editar JSONL, si se va a etiquetar mucho.

## Límites

La simulación usa un conjunto sintético ya etiquetado como sustituto de las personas. Las personas reales tardan más, pueden discrepar entre sí y verán tráfico real. Las cifras son de un clasificador léxico en CPU, no del decisor semántico pendiente.
