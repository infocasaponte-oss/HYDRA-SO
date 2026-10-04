<!-- Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved. -->
# HYDRA Base v2 (125M): informe do preadestramento

Estado: **rematado** o 2026-10-04 ás 19:11 (13.039 pasos). Perplexidade final de validación: **30,09**.
Pesos en `models/hydra-base-v2-125m/final` (non se publican). Avaliación en `runtime/base-v2-eval/`.

## 1. Resumo

- Primeira base 100 % propia de HYDRA, con licenza limpa e reproducible: corpus, tokenizador e
  pesos levan os seus hashes no manifesto.
- O adestramento estivo san: a perplexidade de validación baixou de forma continua de 287 a 30,1, sen
  saltos nin sobreaxuste. Sobreviviu a un reinicio do equipo e a unha caída por falta de RAM (seccións 6)
  grazas aos puntos de retoma.
- O resultado será modesto. 125M parámetros con 0,85 mil millóns de tokens é unhas tres veces menos
  datos do recomendable para este tamaño, e os datos están desequilibrados cara a textos antigos e
  legais. Valida o proceso completo; non é un modelo competitivo. Isto debeu explicarse antes de
  lanzalo.

## 2. Corpus v2 (`data/hydra-base-corpus-v2`)

Selado o 2026-10-03 ás 03:06. Código do constructor: `63b127a` (filtros profesionais, PR #109/#113).

| Fonte | Conservado | Caracteres | Principais rexeitamentos |
|---|---|---|---|
| Libros PleIAs (dominio público) | 127.243 trozos | 1.939 M | ruído OCR 55.108, OCR ilexible 10.132 |
| BOE consolidado | 8.497 docs | 610 M | casi-duplicados 631, avaliación 504, datos persoais 260 |
| Prensa PleIAs (dominio público) | 40.414 trozos | 570 M | ruído OCR 34.378 |
| Stack v2 Markdown (permisivas) | 60.239 | 165 M | moi curtos 6.849, repetición 6.557, datos persoais 6.525 |
| Stack v2 Python (permisivas) | 15.285 | 63 M | non compila 1.410, datos persoais 1.302, credenciais 659 |
| Lotes de adquisición revisados | 1.155 | 5 M | idioma 475, licenza 442 |
| **Total** | **252.833** | **3.351 M** | |

- **Descontaminación:** 403 documentos BOE das avaliacións e 5.281 tramos de 13 palabras excluídos.
- **Auditoría de integridade:** aprobada, 0 fallos (hashes, licenzas, duplicados entre particións,
  obras repartidas entre adestramento e validación).
- **Avisos revisados:** 3 «correos» falsos positivos, 112 documentos con restos de OCR, 1 de código.
  Revisión asinada en `runtime/corpus-v2-review/review.json`, ligada ao hash do informe.
- **Defectos coñecidos, non bloqueantes:** guións no medio da liña en libros antigos («res- petos»)
  e unha páxina de spam en Markdown.

## 3. Tokenizador v2 (`models/hydra-base-tokenizer-v2`)

- SentencePiece BPE, 32.000 pezas, *byte fallback*, díxitos separados e marcadores de chat reservados.
- Adestrado cunha mostra de 192 M caracteres do corpus v2.
- Eficiencia fronte ao tokenizador de Qwen (v7): castelán legal 1,84 tokens/palabra (Qwen 1,69);
  código 2,86 (Qwen 2,07). Bo en castelán, peor en código, como cabe esperar polo corpus.

## 4. Modelo e plan

| Parámetro | Valor |
|---|---|
| Arquitectura | Llama, 30 capas × 576, atención GQA 9/3, MLP 1.536, embeddings atados |
| Parámetros | 124,6 M |
| Tokens de adestramento | 854.577.886 (validación 9.430.961) |
| Contexto | 1.024 tokens, documento enmarcado con BOS + EOS |
| Optimización | AdamW, LR 2e-3, quecemento 2 %, estable, baixada final 20 % (WSD) |
| Lote | 65.536 tokens por paso (micro-lote 8 × acumulación 8), checkpointing de gradientes |
| Pasos | 13.039 (unha pasada) |
| Hardware | RTX 3060 Ti 8 GB, ~6 GB en uso, ~7,6 s por paso (~8.600 tokens/s) |
| Puntos de retoma | cada 250 pasos (`resume.pt`, 1,5 GB) |

## 5. Curva de validación

| Paso | 250 | 500 | 1.000 | 2.000 | 4.000 | 6.000 | 8.000 | 10.000 | 11.000 | 12.000 | 12.750 | **13.039** |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Perplexidade | 287 | 153 | 81,6 | 58,4 | 46,3 | 41,8 | 39,3 | 37,7 | 35,7 | ~32,5 | 30,7 | **30,1** |

- Perda de adestramento ~3,3–3,6 e de validación 3,63: separación pequena, sen sobreaxuste.
- O tramo final, coa baixada do ritmo de aprendizaxe desde o paso ~10.430, levou a perplexidade de 37,6
  a 30,1: mellor que a estimación previa (33–36).

## 6. Incidencias

| Cando | Que | Efecto |
|---|---|---|
| 2026-10-04 00:24 | Reinicio do equipo (probablemente Windows Update) | Retomado desde o paso 4.500; perdéronse ~170 pasos (~22 min) |
| 2026-10-04 13:14 | Caída por falta de memoria: o descargador de fontes esgotou a RAM do equipo | Relanzado ás 13:22 (fóra desta sesión) desde o paso 10.250; o descargador xa escribe en disco fila a fila |
| Continuo | GPU ao 100 % e 79–81 °C, freo por potencia, sen freo térmico | Normal |

## 7. Resultados

### 7.1 Perplexidade por fonte (validación, 40 documentos por fonte)

| Fonte | Base 30M (etapa 0) | **Base 125M (etapa 1)** |
|---|---|---|
| BOE | 8,3 | **7,2** |
| Python | 4,6 | 5,9 |
| Markdown | 23,7 | **13,9** |
| Libros PleIAs | 383 | **40,8** |
| Prensa PleIAs | 209 | **59,8** |
| Lotes técnicos | 78,8 | **19,3** |

Gran mellora en libros, prensa e documentación. Python empeora un pouco porque agora pesa menos no corpus.

### 7.2 Mostras (prompts fixos, `runtime/base-v2-eval/evaluation.json`)

- **Lei:** continúa con naturalidade («establecer las medidas que faciliten la integración de la perspectiva de
  género…»), en ton lexislativo correcto.
- **Narrativa:** castelán fluído e coherente, pero con ton do século XIX.
- **Prensa histórica:** reproduce o estilo das revistas de sanidade militar.
- **Ciencia:** «la fotosíntesis es el proceso por el cual los hombres han tomado conciencia…» — sen
  coñecemento do mundo actual.
- **Código:** sintaxe Python verosímil pero sen sentido.

### 7.3 Como encoder de Hyd (mesma receita que v8: cabeza lineal, corpus v4)

| Encoder | Desenvolvemento | Test humano (Juan, Belén e Lois) |
|---|---|---|
| Hyd actual (n-gramas) | 46,3 % | 19,8 % |
| HYDRA Base 30M | 47,5 % | — |
| **HYDRA Base 125M (propio)** | **65,6 %** | **50,2 %** (IC 44–56 %) |
| HYDRA v8 (base Qwen) | 82,9 % | 71,8 % |

- O Hyd 100 % propio pasa do 20 % ao 50 % no test humano, pero queda por debaixo de v8.
- Con confianza ≥ 0,9 acerta 89 de 112 (79 %): aínda non é fiable para dar autoridade.
- Probas controladas de desenvolvemento: sinónimos 59 %, erros de tecleo 60 %, frase distractora 34 %,
  negación 24 %.

### 7.4 Valoración

Primeira base propia válida e reproducible. Mellora moito a de 30M, pero como modelo é modesta polo tamaño
(125M), polos datos (0,85 mil millóns de tokens, ~3× menos do recomendable) e polo desequilibrio cara a
textos antigos e legais. O corpus da seguinte etapa (sección 8) corrixe sobre todo isto último.

## 8. Seguinte etapa (en preparación)

- **Dez categorías con obxectivo de tokens** (`config/base_categories.json`, ~6.000 M en total) e
  descargador automático por oco (`scripts/fetch_category_sources.py`, PR #120). En marcha: ciencia,
  industria (patentes de robótica, drones, impresión 3D, automatización), educación, matemáticas,
  código, documentación e lexislación.
- **Bilingüe castelán + inglés:** case todo o descargable con licenza limpa está en inglés.
- **Castelán moderno:** rastrexo por mostraxe de Common Corpus en curso (só metadatos).
- **Decisión pendente:** en Common Corpus moitas filas indican «CC-By» **sen versión** (por exemplo
  OpenAlex). A política actual só admite CC BY 4.0 e rexéitaas. Todas as versións de CC BY permiten uso
  comercial e obras derivadas con atribución; admitilas ampliaría moito a ciencia e o castelán moderno,
  pero é un cambio de política que require a túa aprobación.
- **Escala:** a seguinte base debería ser de 350M–1B parámetros con 6–20 mil millóns de tokens, en nube.
