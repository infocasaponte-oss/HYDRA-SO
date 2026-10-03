# Informe de preentrenamiento del corpus — 3 de octubre de 2026

Copyright (c) 2026 Luis Manuel Cousido Hermida. Todos los derechos reservados.

## Alcance

Auditoría previa al entrenamiento de los corpus de decisión versionados en `data/`. Son las tres fuentes que lee `hydra/training/train_decision_v4.py`, más las particiones reservadas:

| Fuente | Uso | Filas | Textos únicos |
| --- | --- | ---: | ---: |
| `data/decision-corpus-v3/train.jsonl` | Entrenamiento | 1.600 | 1.600 |
| `data/human-dev-v1.jsonl` | Entrenamiento | 100 | 100 |
| `data/human-dev-v2.jsonl` | Entrenamiento | 1.000 | **200** |
| `data/decision-corpus-v3/calibration.jsonl` | Reservado | 200 | 200 |
| `data/decision-corpus-v3/test.jsonl` | Reservado | 1.000 | 1.000 |

Los corpus de instrucciones v2–v9 (por ejemplo, v8 con 969/228/223/48 filas y un máximo de 173 tokens según `docs/evidence/instruction-v8-token-preflight.json`) no están en el repositorio. **No se auditan aquí**: solo existen en el equipo local de entrenamiento.

La auditoría es de solo lectura: no se modificó ni se borró ninguna fila. No se ejecutó ningún entrenamiento.

## Veredicto

- **Integridad: apta.** Hashes, recuentos, identificadores, etiquetas y permisos de entrenamiento son coherentes.
- **Balance: apto.** Las diez etiquetas tienen exactamente el mismo peso en todas las particiones.
- **Capacidad de medir generalización: no apta.** Calibración y test reutilizan las mismas 40 plantillas que el entrenamiento. Un acierto en `test.jsonl` mide reconocimiento de plantilla, no generalización a peticiones nuevas.
- **Redundancia: a corregir o declarar.** `human-dev-v2` tiene 800 repeticiones exactas: funciona como sobreponderación de 200 textos, no como 1.000 ejemplos.

## Integridad

Los tres archivos de `decision-corpus-v3` coinciden con el SHA256 y el número de ejemplos de `manifest.json` (`corpus_sha256` `b81b75fe…c1da6`). Los dos archivos de desarrollo humano no tienen manifiesto. Sus hashes actuales quedan fijados en la evidencia:

- `human-dev-v1.jsonl`: `51fb2288420f93d58a81cffcec5b00a0185caf03f7b34a4a40cbd546b1bff04d`.
- `human-dev-v2.jsonl`: `724013ee30c0f1aebb4f95b7474244989e7d674e9204984e9acc729278edcea5`.

Comprobaciones por fila, todas con **0 incidencias**:

- Hash almacenado frente a hash recalculado. En v3 se recalcula sobre el prompt normalizado, igual que el generador; en desarrollo humano, sobre el texto literal.
- Identificadores duplicados.
- Etiquetas fuera de las diez declaradas.
- Campo `split` distinto del archivo que lo contiene.
- Filas de entrenamiento con `training_allowed` distinto de `true`.
- Filas de `train` con derechos no verificados.

Las filas de desarrollo humano no llevan campo `rights`. Su procedencia se apoya en `source` y en `human-dev-v2.review.json` (`reviewed_by_user: true`, `test_excluded: true`).

## Distribución

| Partición | Por etiqueta | Palabras (mín./mediana/media/máx.) |
| --- | ---: | --- |
| train | 160 | 4 / 12 / 11,45 / 14 |
| calibration | 20 | 8 / 12 / 11,55 / 14 |
| test | 100 | 8 / 12 / 11,55 / 14 |
| human-dev-v1 | 10 | 4 / 7 / 7,64 / 15 |
| human-dev-v2 | 100 | 6 / 10 / 10,06 / 14 |

Etiquetas: `abstain`, `chat`, `coding`, `high_risk_review`, `privacy`, `reasoning`, `research`, `security`, `tool_use` y `vision`. Ninguna falta en ninguna partición.

Todo el corpus está en español y es corto: ningún prompt supera 15 palabras. No hay ejemplos multilingües, largos ni con contexto adjunto real.

## Duplicados y fuga entre particiones

| Comprobación | Resultado |
| --- | ---: |
| Duplicados exactos dentro de train / calibration / test / human-dev-v1 | 0 |
| Duplicados exactos dentro de human-dev-v2 | **800** |
| Textos idénticos entre entrenamiento y reservado | 0 |
| Mismo texto con etiquetas distintas | 0 |
| Casi duplicados de calibración frente a entrenamiento (SimHash, Hamming ≤ 3) | **32/200** |
| Casi duplicados de test frente a entrenamiento (SimHash, Hamming ≤ 3) | **159/1000** |
| Calibración con plantilla base presente en train | **200/200** |
| Test con plantilla base presente en train | **1000/1000** |

### Causa

`hydra/training/decision_corpus_v3.py` genera las tres particiones con las mismas cuatro plantillas por etiqueta. Solo varían uno de cinco prefijos («Por favor, », «Necesito que »…) y el sufijo «Caso de referencia N.». Ejemplo marcado:

- Test: «Por favor, Propón un nombre para una mascota. Caso de referencia 186.»
- Train: «Por favor, Propón un nombre para una mascota. Caso de referencia 46.»

No hay fuga literal, pero sí fuga de plantilla total. Los prefijos generan además frases agramaticales («Ayúdame a Resuelve 3x + 7 = 22.»).

En `hydra/training/human_dev_v2.py`, cada etiqueta combina 4 patrones con 5 temas: 20 textos distintos repetidos cinco veces. Con las tres fuentes de `train_decision_v4`, el entrenamiento suma 2.700 filas pero solo 1.900 textos únicos.

## Implicaciones para el entrenamiento

1. Las métricas de calibración y test del corpus v3 son cotas optimistas. No deben presentarse como precisión sobre peticiones de usuarios. El protocolo con valor de generalización sigue siendo el test humano congelado y la evaluación externa.
2. La repetición de `human-dev-v2` multiplica por cinco el peso de sus 200 textos. Si es intencionado, debe declararse en la receta como ponderación. Si no, hay que deduplicar antes de entrenar.
3. La uniformidad de longitud e idioma limita lo que puede aprenderse. Un decisor entrenado solo con esto no tiene evidencia de funcionar con peticiones largas, mixtas o en otros idiomas.

## Recomendaciones antes del próximo entrenamiento

- **Separar plantillas entre particiones**, como ya hace `corpus-pilot` («disjoint problem families»): plantillas de calibración y test que no aparezcan en entrenamiento.
- **Deduplicar `human-dev-v2`** o pasar su peso explícitamente a la receta.
- **Añadir un manifiesto con hashes** a `human-dev-v1` y `human-dev-v2`, y el campo `rights`, para que la procedencia sea verificable como en v3.
- **Corregir los prefijos agramaticales** del generador v3. Hay que regenerar con una nueva versión de corpus, no reescribir los archivos de v3: sus hashes están referenciados por modelos y evidencias anteriores.
- **Repetir esta auditoría** sobre los corpus de instrucciones en el equipo local con el mismo criterio de plantillas y casi duplicados. Hoy solo existe un filtro léxico frente al test (`instruction-v8-source-contamination.json`).

## Limitaciones

Las comprobaciones son de hash, léxicas y de plantilla. No detectan contaminación semántica, por ejemplo una paráfrasis completa del test, ni verifican que cada etiqueta sea correcta. Ambas cosas requieren revisión humana. El umbral de SimHash (≤ 3 bits) es conservador: el 100% de solapamiento de plantilla es la medida más fiel de la fuga.

## Cómo reproducirlo

```bash
PYTHONPATH=. python scripts/report_corpus_pretraining.py
```

## Evidencias

- Auditoría completa: `docs/evidence/corpus-pretraining-audit-2026-10-03.json`.
- Script: `scripts/report_corpus_pretraining.py`.
- Manifiesto del corpus: `data/decision-corpus-v3/manifest.json`.
