<!-- Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved. -->
# HYDRA Base v2 (125M): informe do preadestramento

Estado: **en curso**, informe parcial do 2026-10-04 ás 13:12, no paso 10.410 de 13.039 (80 %).
Remate estimado: 2026-10-04 arredor das 18:50. As cifras finais e a avaliación engadiranse ao rematar.

## 1. Resumo

- Primeira base 100 % propia de HYDRA, con licenza limpa e reproducible: corpus, tokenizador e
  pesos levan os seus hashes no manifesto.
- O adestramento está san: a perplexidade de validación baixou de forma continua de 287 a 37,6, sen
  saltos nin sobreaxuste, e sobreviviu a un reinicio do equipo grazas aos puntos de retoma.
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

| Paso | 250 | 500 | 1.000 | 2.000 | 3.000 | 4.000 | 5.000 | 6.000 | 7.000 | 8.000 | 9.000 | 10.000 | 10.250 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Perplexidade | 287 | 153 | 81,6 | 58,4 | 50,4 | 46,3 | 43,6 | 41,8 | 40,1 | 39,3 | 38,5 | 37,7 | 37,6 |

- Perda de adestramento ~3,3–3,6 e de validación 3,63: separación pequena, sen sobreaxuste.
- A partir do paso ~10.430 o ritmo de aprendizaxe baixa ata o 10 % do máximo. Nesta fase adoita
  baixar outra vez a perplexidade; a estimación é rematar arredor de 33–36 (por confirmar).

## 6. Incidencias

| Cando | Que | Efecto |
|---|---|---|
| 2026-10-04 00:24 | Reinicio do equipo (probablemente Windows Update) | Retomado desde o paso 4.500; perdéronse ~170 pasos (~22 min) |
| Continuo | GPU ao 100 % e 79–81 °C, freo por potencia, sen freo térmico | Normal; recomendable pausar actualizacións ata rematar |

## 7. Que esperar (avaliación pendente)

1. **Perplexidade por fonte** (`hydra.training.evaluate_base`) fronte á base de 30M da etapa 0
   (BOE 8,3; Python 4,6; Markdown 23,7; libros 383; prensa 209). Espérase unha gran mellora en libros
   e prensa, e algo de perda relativa en BOE e código, porque agora pesan menos no corpus.
2. **Mostras de texto** cos cinco prompts fixos: castelán coherente pero con ton antigo ou legal, e
   pouco coñecemento do mundo actual. Non é un modelo de conversa.
3. **Como encoder de Hyd** (mesmas probas que v8, que acerta un 83 % en desenvolvemento): esperamos
   bastante máis que o 47,5 % da base de 30M, pero probablemente menos que v8.

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
