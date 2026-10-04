<!-- Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved. -->
# Informe de preadestramento — 4 de outubro de 2026

Observación: 2026-10-04T13:20:30.432257+02:00. Fontes: manifestos locais, train.log e resume.json/pt. Non se lanzou nin modificou o adestramento.

**Estado:** non se detecta un proceso de preadestramento activo nesta observación. O motivo non está rexistrado; non se afirma fallo nin pausa voluntaria. Non existe build-manifest.json final nesta execución.

## Modelo e progreso

Modelo HYDRA Base v2, perfil 125M: 124,635,456 parámetros calculados para vocabulario 32000. É o modelo base actual; non o candidato de 4B nin o ranker Hyd.

- Plan: 13039 pasos, secuencia 1024, microbatch 8 e acumulación 8; 65,536 tokens por paso.
- Último checkpoint: paso 10250 (78.61% do plan). SHA-256 comprobado, coincidencia=True.
- Última actualización no log: paso 10420, loss=3.2247. O índice do log comeza en cero e non é un checkpoint.
- Tokens consumidos ata o checkpoint: 671,744,000. Son tokens procesados, non documentos únicos nin garantía de percorrer todo o corpus.
- Ao retomar, os avances posteriores ao checkpoint deben repetirse. Non se retomou automaticamente.

## Corpus e tokenizer

Segundo os manifestos: 252,833 documentos e 3,350,705,256 caracteres. Tokens de train: 854,577,886; validation: 9,430,961, con BOS/documento/EOS. Tokenizer SentencePiece BPE de 32000 entradas. Nesta revisión non se releu todo o corpus nin se recomprobaron os hashes de todos os shards/tokenfiles.

| Fonte declarada | Documentos conservados |
|---|---:|
| BOE legislación consolidada | 8,497 |
| Stack v2 edu (Python, permissive) | 15,285 |
| Stack v2 edu (Markdown, permissive) | 60,239 |
| PleIAs Spanish-PD-Books | 127,243 |
| PleIAs Spanish-PD-Newspapers | 40,414 |
| Acquisition batches (technical-clear) | 1,155 |

## Aprendizaxe observada

Primeira avaliación gardada: paso 250, train_loss=5.735, val_loss=5.6591, perplexidade=286.89.

Última avaliación gardada: paso 10250, train_loss=3.3497, val_loss=3.6281, perplexidade=37.64.

A baixada de perda indica progreso no obxectivo de predición do seguinte token sobre estes datos. Non acredita exactitude factual, seguimento de instrucións nin preparación para produción. A última loss de minibatch (3.2247) non é a val_loss. A independencia da avaliación non queda acreditada por este informe.

## Seguinte paso

Conservar o checkpoint, confirmar cando retomar e validar identidade/hashes de tokens e tokenizer mediante o adestrador antes de continuar. O plan aínda ten 2789 pasos desde o checkpoint. Ao completar, verificar o manifesto final, facer avaliación independente e comprobar recuperación/inferencia. Non se substitúe este adestramento polo perfil de 4B preparado: o seu backend e a memoria seguen por validar.
