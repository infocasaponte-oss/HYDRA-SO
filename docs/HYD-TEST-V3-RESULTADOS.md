<!-- Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved. -->
# Hyd: primeiro test humano independente e candidatos (2026-10-03)

## Test

`data/private/hyd-test-v3` (privado, fóra de git): 450 frases en castelán escritas por Juan, Belén e
Lois, 45 por etiqueta, en 150 grupos paralelos. Conxelado antes de medir (sha256 `81be6d5f…2e27`).
Ningunha frase ten Jaccard ≥ 0,5 con `decision-corpus-v3`, `human-dev-v2` nin co test vello.
Regra: só mide; nunca se adestra, calibra nin elixe receitas con el.

## Corpus de adestramento v4

`hydra/hyd/route_corpus_v4.py`, sintético, reproducible (semente + hash do test):
- 103 patróns, 10 etiquetas e 3.126 frases. Ningún patrón achega máis de 40 frases.
- Estilo humano: sen acentos (conservando a ñ), q/k, sen puntuación, erros de tecleo, saúdos e peches.
- **Descontaminación:** descarta calquera frase con Jaccard ≥ 0,3 contra unha do test, cun tramo
  común de 4 palabras ou con dúas palabras distintivas do test. Descartáronse 32.000 candidatas.
- O desenvolvemento usa patróns que non aparecen en adestramento (mide frases realmente novas).

## Resultados

Candidato e hiperparámetros elixidos só con desenvolvemento. O test mediuse **unha vez** por candidato.
IC 95 % por bootstrap de grupos.

| Sistema | Test humano | IC 95 % | Desenvolvemento |
|---|---|---|---|
| **v8 (embeddings, conxelado) + cabeza lineal propia** | **71,8 %** | 66–77 % | 82,9 % |
| Hyd ranker re-adestrado co corpus v4 | 34,7 % | 30–40 % | 46,3 % |
| v8 sen adestrar, saída restrinxida | 34,9 % | — | — |
| Router de regras (actual) | 24,7 % | 19–31 % | — |
| Hyd actual (`config/hyd`) | 19,8 % | 15–24 % | — |
| `hydra-decision-v2` | 16,4 % | 13–20 % | — |

**v8 + cabeza:**
- Con confianza ≥ 0,9 acepta 212 de 450 (cobertura 47 %) e acerta 195: 92 %, Wilson inferior 0,875.
- Por etiqueta: tool_use 42/45, security 39/45, high_risk 37/45, coding e research 36/45, abstain só 8/45.
  As frases de abstain do test refiren contexto anterior inexistente; o xerador cubriu sobre todo adxuntos ausentes.

**Conclusión:**
- O salto vén da representación, non dos datos: os mesmos datos dan 35 % co ranker de n-gramas e 72 % con v8.
- O camiño é un encoder contextual con cabeza propia. HYDRA Base valerá cando teña capacidade comparable;
  mentres tanto, v8 (base Qwen2.5-1.5B, Apache-2.0) queda rexistrado como encoder de referencia.

## Límites

- Non cumpre o criterio de autoridade: cobertura < 0,80 e Wilson < 0,90. **Sen autoridade.**
- Este test xa se usou unha vez para esta versión. Seguir iterando contra el inflaría as cifras: a
  próxima versión necesita outro test humano novo.
- `abstain` e `chat` son os puntos débiles; os datos novos deben cubrir referencias a contexto previo.

## Motor con encoder intercambiable (2026-10-03)

- `hydra/hyd/embedding.py`: formato `hyd-embedding-head/1`. Encoder rexistrado no modelo (tipo, endpoint
  local, dimensións, hash do GGUF e licenza) e cabeza lineal de HYDRA. Hoxe usa v8 por `llama-server
  --embeddings`; mañá HYDRA Base, sen cambiar o motor. Fóra das etiquetas adestradas non opina (abstense).
- `config/hyd-embedding/`: cabeza adestrada co corpus v4 (mesma receita medida no test: 71,8 %). Por defecto
  segue o ranker de CPU; o novo actívase con `HYDRA_HYD_MODEL_PATH`/`HYDRA_HYD_CALIBRATION_PATH` e
  `scripts/start_hyd_encoder.ps1`. **Sen autoridade.**
- `hydra/hyd/probes.py`: probas controladas desde desenvolvemento (sinónimos, tecleo, frase distractora,
  orde, negación).

## Corpus v5: resultado

`route_corpus_v5.py` engade contexto inexistente, números non aritméticos, frases distractoras e contrastes,
e herda o reparto de v4 (ningunha cabeza adestra con patróns de desenvolvemento da outra). Medido só en
desenvolvemento (1.123 frases que ningunha das dúas viu):

| Conxunto | Cabeza v4 | Cabeza v5 |
|---|---|---|
| Desenvolvemento total | **78,4 %** | 74,5 % |
| Frase distractora (proba) | 57 % | **65 %** |
| Contrastes | 29 % | **41 %** |
| Contexto inexistente | 94 % | 97 % |
| Números non aritméticos | 96 % | 94 % |
| Negación (proba) | 21 % | 20 % |

v5 non mellora o total e non resolve a negación: unha cabeza lineal sobre embeddings medios conxelados
non compón «non X, senón Y». Iso require axustar o encoder (non só a cabeza) ou outro tipo de agregación.
Por iso o motor inclúe a cabeza v4. O xerador v5 queda para os seguintes experimentos.
