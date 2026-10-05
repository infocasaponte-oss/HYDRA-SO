<!-- Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved. -->
# Fontes de castelán moderno para HYDRA Base

Data: 2026-10-04. Obxectivo da categoría `lingua_moderna`: 1.000 M tokens de castelán.
Conseguido: ~430 M (EUR-Lex: propostas e acordos internacionais).
Política: `hydra/training/base_data_policy.py`, que admite CC BY en todas as versións desde 2026-10-04.

## Estado de cada fonte

| # | Fonte | Rexistro | Tamaño aproximado | Licenza | Estado | Acceso |
|---|---|---|---|---|---|---|
| 1 | **EUR-Lex en castelán** (`joelniklaus/eurlex_resources`) | xurídico e administrativo formal | ~1.800 M tokens | reutilización UE (Decisión 2011/833) | ✅ **descargado** (propostas e acordos en lingua moderna; o resto en lexislación, con cupo por tipo) | HF, directo |
| 2 | **YouTube-Commons**, só vídeos orixinalmente en castelán (`PleIAs/YouTube-Commons`) | falado, divulgación, conversa | ~2.000 M tokens (~2.150 vídeos por ficheiro de 385 MB) | CC BY 3.0 | ✅ **engadido ao descargador** (tope 600 M tokens; ~60 GB de descarga) | HF, directo |
| 3 | Corpus xurídico paralelo catalán-castelán (`BSC-LT/Legal_Catalan_Spanish_Parallel_Corpus`) | lexislación autonómica | ~2 GB | CC BY 4.0 | 🟡 admisible; falta comprobar o formato | HF |
| 4 | Boletín Oficial da República Arxentina (`marianbasti/boletin-oficial-argentina`) | normas e actos oficiais | por medir | dataset Apache-2.0; textos oficiais | 🟡 verificar a base legal da reutilización dos textos oficiais arxentinos | HF |
| 5 | DGT-TM e EMEA da UE (OPUS) | administración UE, medicamentos | centos de M de palabras | reutilización UE | 🟡 admisible; a ficha de HF di «unknown», hai que citar a fonte orixinal | OPUS / HF |
| 6 | Europarl en castelán | debates parlamentarios | ~55 M palabras | reutilización do Parlamento Europeo | 🟡 verificar o aviso legal actual do PE | OPUS / HF |
| 7 | Diarios oficiais autonómicos | normativa e actos autonómicos | grande | CC BY 4.0 (Aragón, Euskadi) ou Lei 37/2007 | ✅ **BOA (Aragón) engadido** (1996–2025, texto completo en JSON aberto, ~12 M tokens/ano; sección I → lexislación, resto → lingua moderna). 🟡 BOPV (Euskadi, API REST CC BY 4.0) e os demais pendentes de descargador | portais abertos |
| 8 | Diarios de sesións do Congreso e do Senado | debate parlamentario moderno | grande | condicións propias das Cortes | 🟡 verificar as condicións de reutilización | webs oficiais |
| 9 | Notas de prensa da Moncloa e dos ministerios | comunicación institucional | medio | Lei 37/2007, segundo o aviso legal de cada sitio | 🟡 verificar sitio a sitio | rastrexo |
| 10 | OpenStax en castelán | educativo | 8 libros admitidos | CC BY 4.0 (comprobada libro a libro) | ✅ **engadido**: Física universitaria 1–3 e as dúas Químicas → ciencia; Estatística, Estatística empresarial e Precálculo → matemáticas. Cálculo 1–3 rexeitado (CC BY-NC-SA) | API do arquivo de OpenStax |
| 11 | Artigos de SciELO con CC BY | científico | grande | CC BY por artigo | 🟡 admisible; precisa OAI-PMH e filtrar a licenza de cada artigo | API |
| 12 | Tatoeba (castelán) | frases curtas | pequeno | CC BY 2.0 | 🟡 admisible, pouco volume | descarga |
| 13 | Frases de Common Voice (castelán) | frases curtas | pequeno | CC0 | 🟡 admisible, pouco volume | descarga |

## Rexeitadas

| Fonte | Motivo |
|---|---|
| Wikipedia, Wikilibros, Wikisource | CC BY-SA: obrigaría a licenciar os pesos igual |
| mC4-es, CulturaX, OSCAR, FineWeb-2 | rastrexo web: a licenza cobre a compilación, non os textos |
| Redalyc | maioritariamente CC BY-NC-SA |
| esCorpius | CC BY-NC-ND |
| CENDOJ (xurisprudencia española) | condicións do CGPJ restritivas para reutilización masiva e comercial |
| Restos de Common Corpus (Eurovoc, VoxPopuli) | admisibles pero espallados (~0,15 M tokens por ficheiro de 470 MB): non é eficiente descargalos |

## Proposta

1. **Xa:** YouTube-Commons en castelán. Achega castelán falado moderno, o rexistro que máis falta.
2. **Seguinte, se o apruebas:** fontes 3 (BSC-LT) e 5 (DGT-TM), xa admisibles e de descarga directa.
3. **Despois:** descargadores propios para diarios oficiais autonómicos (7) e OpenStax (10), e verificación
   legal das fontes 4, 6, 8 e 9 antes de usalas.
