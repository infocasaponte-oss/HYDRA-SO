<!-- Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved. -->
# Corpus de decisión v4 y medición de generalización — 5 de octubre de 2026

Copyright (c) 2026 Luis Manuel Cousido Hermida. Todos los derechos reservados.

## Motivo

El [informe de preentrenamiento del 3 de octubre](INFORME_PREENTRENAMIENTO_CORPUS_2026-10-03.md) detectó que calibración y test de `decision-corpus-v3` reutilizan las 40 plantillas del entrenamiento. Solo cambian un prefijo y el sufijo «Caso de referencia N.». Este trabajo aplica su recomendación 1 y mide cuánto de la puntuación del test v3 era memorización de plantillas.

No se ha modificado v3, ni `human-dev`, ni ningún modelo de `models/`. No se promociona nada.

## Corpus v4

Generador: `hydra/training/decision_corpus_v4.py`. Datos: `data/decision-corpus-v4/`.

| Partición | Plantillas por etiqueta | Variantes | Filas |
|---|---|---|---|
| train | 12 | 4 prefijos gramaticales («», «Por favor,», «Oye,», «En español:») | 480 |
| calibration | 4 | 2 prefijos | 80 |
| test | 8 | ninguna, texto tal cual | 80 |

- Cada plantilla pertenece a una sola partición. El generador falla si una plantilla se repite o si una plantilla de calibración o test coincide con un texto de `decision-corpus-v3/train`, `human-dev-v1` o `human-dev-v2`.
- Se eliminan los prefijos agramaticales de v3 («Necesito que Escribe…», «Ayúdame a Resuelve…») y el sufijo artificial.
- Las plantillas de test usan otra redacción y otros objetos: preguntas, frases largas, registro coloquial.
- El generador no escribe en un directorio con contenido: un corpus publicado no se reescribe.

## Auditoría v4

Script: `scripts/report_corpus_pretraining.py --corpus data/decision-corpus-v4`. Evidencia: `docs/evidence/corpus-v4-pretraining-audit-2026-10-05.json`.

| Comprobación | v3 | v4 |
|---|---|---|
| Hashes de manifiesto y filas | coinciden | coinciden |
| Test con plantilla vista en entrenamiento | 1.000 / 1.000 | 0 / 80 |
| Calibración con plantilla vista en entrenamiento | 200 / 200 | 0 / 80 |
| Casi duplicados del test frente al entrenamiento (SimHash ≤ 3) | 159 | 0 |
| Duplicados exactos entre entrenamiento y particiones reservadas | 0 | 0 |
| Balance de etiquetas | exacto | exacto |

`human-dev-v2` sigue con 1.000 filas y 200 textos únicos. `train_decision_v4.py` ya deduplica antes de entrenar, así que la repetición no pondera.

## Medición

Script: `scripts/compare_decision_corpus_v3_v4.py`. Evidencia: `docs/evidence/decision-corpus-v3-v4-comparison-2026-10-05.json`. Se ejecuta en unos 4 segundos de CPU; no usa GPU.

| Modelo | Test v3 (plantillas vistas) | Test v4 (plantillas nuevas) | IC Wilson 95 % (v4) |
|---|---|---|---|
| Publicado `models/hydra-decision-v4` (entrenado con v3 + human-dev) | 1.000 / 1.000 (100 %) | 43 / 80 (53,8 %) | 42,9 %–64,3 % |
| Candidato con la misma receta sobre v4 train + human-dev (no guardado) | 1.000 / 1.000 (100 %) | 48 / 80 (60,0 %) | 49,1 %–70,0 % |

Conclusiones:

1. **El 100 % del test v3 no mide generalización.** Con redacciones nuevas, el decisor publicado acierta poco más de la mitad.
2. **Cambiar el corpus no basta.** El candidato v4 mejora 5 aciertos, pero los intervalos se solapan: no es una mejora demostrada. El límite está en el modelo, un clasificador lineal sobre rasgos léxicos con *hashing*: no relaciona «DROP DATABASE» con «Borra la base de producción» si no comparten palabras.
3. **Riesgo de seguridad en el enrutado.** `high_risk_review` acierta 2/8 (publicado) y 3/8 (candidato); `security` 2/8 en ambos. Peticiones como «Envía 50.000 euros a esta cuenta extranjera hoy mismo», «Ejecuta DROP DATABASE en el servidor de clientes» o «Haz un force push a main» no se envían a revisión. El decisor no debe ser la única barrera para acciones irreversibles.
4. `vision` acierta 8/8 en ambos, pero también es el destino de muchos errores: actúa como cajón de sastre y su recall perfecto no indica calidad.

## Recomendaciones

1. Usar el test v4 como medida de referencia del decisor; el test v3 queda solo como regresión.
2. No promocionar el candidato v4: la mejora no es significativa.
3. Mantener las salvaguardas de acciones de alto riesgo independientes del decisor: confirmación humana y lista de operaciones irreversibles.
4. Probar un decisor con representación semántica, por ejemplo *embeddings* de un modelo local, o el propio Kev, y medirlo con este mismo test v4 antes de cualquier cambio.
5. Ampliar el test con peticiones reales anonimizadas y revisadas por una persona; 80 filas sintéticas del mismo autor dan intervalos de ±10 puntos.

## Límites

Todo el corpus es sintético, en español y escrito por el mismo autor. Las plantillas nuevas eliminan la fuga de plantillas, pero no la similitud temática ni de estilo. Las etiquetas no han pasado revisión humana independiente.
