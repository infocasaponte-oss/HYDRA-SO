<!-- Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved. -->
# Hyd fronte a HYDRA v8 no corpus da app

Data: 2026-10-04. Diagnóstico de clasificación nas dez rutas; non é unha proba da calidade das respostas xeradas nin certificación de produción.

| Métrica | Hyd da app | HYDRA instruction v8, zero-shot |
|---|---:|---:|
| Acertos / preguntas | 223/313 | 129/313 |
| Acierto global | 71.25% | 41.21% |
| Macro-F1 | 0.6923 | 0.3144 |
| Saídas inválidas | 0 | 0 |
| Latencia p50 en CPU, ms | 4.04 | 511.76 |
| Latencia p95 en CPU, ms | 6.19 | 672.90 |

Diferenza de acerto Hyd−v8: 30.03 puntos porcentuais.

| Clase | Preguntas | Acertos Hyd | Acertos v8 | F1 Hyd | F1 v8 |
|---|---:|---:|---:|---:|---:|
| chat | 28 | 18 | 3 | 0.679 | 0.146 |
| coding | 31 | 22 | 15 | 0.721 | 0.536 |
| reasoning | 34 | 26 | 9 | 0.776 | 0.217 |
| research | 33 | 25 | 29 | 0.694 | 0.644 |
| vision | 44 | 41 | 38 | 0.901 | 0.510 |
| tool_use | 23 | 12 | 5 | 0.511 | 0.250 |
| abstain | 31 | 15 | 0 | 0.536 | 0.000 |
| security | 38 | 26 | 27 | 0.754 | 0.659 |
| privacy | 30 | 25 | 3 | 0.746 | 0.182 |
| high_risk_review | 21 | 13 | 0 | 0.605 | 0.000 |

Comparación pareada: Hyd acerta e v8 falla en 118 preguntas; v8 acerta e Hyd falla en 24. McNemar exacto bilateral p=4.15443e-16. Intervalos e contraste describen este conxunto; non acreditan independencia semántica nin de avaliadores.

Hyd acepta 96/313 coa calibración orixinal (confianza ≥0,95 e marxe ≥0,1); acerta 93/96. Esa precisión selectiva non se compara co acerto global de v8.

## Protocolo e límites

- Mesmos 313 textos e etiquetas do test; ningunha pregunta empregada como exemplo no prompt de v8. Sen adestramento nin axuste de v8 neste corpus.
- v8 xerou unha etiqueta con temperatura 0, seed 42 e gramática das dez clases. A gramática evita formatos alleos pero non garante que a etiqueta sexa correcta. O resultado depende deste protocolo; non representa todos os prompts posibles.
- Non se inferiron probabilidades para v8 nin se inventaron métricas de calibración.
- v8 executouse no GGUF verificado en CPU con catro fíos para conservar o adestramento activo na GPU. Latencia de Hyd: chamada local do ranker. Latencia de v8: HTTP local, procesado de prompt e xeración; non é unha comparación de rendemento na GPU.
- Non hai coincidencias exactas normalizadas coas preguntas das particións locais de instruction-v8. Isto non exclúe relación semántica, exposición no preadestramento nin outras fontes.
- Hyd si foi adestrado coa partición train da mesma app. Comparación entre un clasificador especializado e un modelo xeral zero-shot; non comparar capacidade xeral a partir deste resultado.
- Non se executaron os comandos perigosos mencionados nas preguntas: só se clasificou texto.

## Conclusión práctica

Conservar o ranker especializado como candidato de enrutamento e avaliar v8 separadamente nas tarefas de resposta. Esta proba non promove Hyd: aínda require cobertura suficiente, clases de risco revisadas e evidencia independente. Se se quere probar unha cabeza baseada nos embeddings de v8, executar un experimento distinto con train/calibration/test separados e o mesmo protocolo de comparación.

## Evidencia

Dataset SHA-256: `3b629a34232164fcb51bb2c2ba0a851d6c55e71b48df261b4e5765a6e18dfe84`.
Hyd modelo SHA-256: `ebf5e67e46612d211c7369119ef2cb3f7c52381612632e8822b94670b82aa565`.
v8 GGUF SHA-256: `0ef14148ababf98c52623f164d776ed76f17a583175ea91301e024a157231761`.
Predicións, protocolo, tempos e hashes: `.codex-artifacts/v8-vs-hyd-app-test-2026-10-04.json`.
Comprobación de solapamento exacto: `.codex-artifacts/v8-app-exact-contamination.json`.
