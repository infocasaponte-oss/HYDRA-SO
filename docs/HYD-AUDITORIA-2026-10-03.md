<!-- Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved. -->
# Auditoría de Hyd e plan para sacar Kev de HYDRA

Data: 2026-10-03. Revisa o documento «Que debe aprender Hyd para substituír Kev e melloralo» contra o
código real (`hydra/hyd/`, sen commit en `D:\HYDRA`), as evidencias de `docs/evidence/hyd/` e medicións
novas sobre `data/human-paraphrase-v1.jsonl`.

## 0. Correccións (revisión do mesmo día)

- **`human-dev-v2` non son 1.000 exemplos humanos:** son 1.000 filas con **200 textos distintos**,
  xerados por 4 patróns × 5 temas por etiqueta (`hydra/training/human_dev_v2.py`). Detectouno Codex
  (`docs/HYD-AUDIT-ADDENDUM.md`). `boundary_family` coincide coa etiqueta, así que non serve para dividir.
- **Os temas do xerador reproducen os do test** («acertijo de interruptores», «romper el hielo»,
  «ordenar varias fracciones», «si el texto está girado», «protocolo OAuth 2.0»). Hai fuga a nivel de
  tema aínda que o solapamento léxico sexa baixo. Polo tanto, **retiro a recomendación de adestrar con
  `human-dev-v2` para mellorar a cifra do test de 100 frases**: calquera mellora alí estaría inflada.
  Sen un test novo e independente, ningunha mellora de calidade de Hyd é demostrable.
- Un porto pechado non demostra a ausencia de dependencia de Kev (o Studio e o bootstrap ofrecían o
  camiño). #111 xa cambia o Studio a Hyd.
- Implementado en #112 (sobre #111): motivos de observación separados (ocupado / tempo / backend / entrada)
  e calibración ligada só ao código que calcula probabilidades. As predicións quedan idénticas.

## 1. Conclusión

1. **Kev pódese sacar xa sen perder calidade.** Hoxe Kev só observa: a autoridade está apagada, o
   porto 8009 non escoita e ningunha decisión de HYDRA depende del. O enrutado real faino o router de
   regras. Sacar Kev é limpeza e independencia, non unha substitución que Hyd teña que gañar antes.
2. **Hyd aínda non decide mellor ca o que xa hai na casa.** No mesmo test (100 paráfrases humanas):

   | Sistema | Acerto | Nota |
   |---|---|---|
   | Router de regras + `policy_gate` (o que decide hoxe) | 35/100 | security 0/10, privacy 1/10, abstain 0/10 |
   | **Hyd** (ranker bilinear, CPU, 3 ms) | **52/100** | reasoning 1/10, security 2/10, privacy 3/10 |
   | `hydra-decision-v2` (clasificador lineal propio, sen Kev) | 70/100 | mellor ca Hyd e xa existe |
   | Kev compatible | 85/100 | — |
   | `hydra-decision-v4` «PROMOTED» | 96/100 | **non válido**, ver §3.2 |

3. O documento de Hyd está ben orientado (honesto coas cifras, separa clasificación de permisos,
   esixe test novo). O punto crítico é que **o test xa non é independente**: usouse para promover v4,
   e os temas de `human-dev-v2` repiten os do test (ver §0). Por iso o primeiro paso é un test novo.

## 2. Que está ben no documento e no código

- Hyd é código propio: non importa Kev nin usa os seus pesos. Tampouco usa as súas cabezas.
- A calibración está ligada por hash a modelo, implementación e criterios. Se non casan, o motor non arranca.
- A abstención é explícita (confianza ≥ 0,95, marxe ≥ 0,1), e unha decisión xeral sen dominio adestrado abstense.
- A autoridade só se activa con evidencia ligada a modelo, calibración e limiares.
- O router non rompe se o observador falla: devolve `status=error` e mantén a política. As pistas xa non
  apagan `requires_reasoning`/`requires_tools`: agora só os poden engadir.
- Seguridade, privacidade e permisos seguen fóra do aprendido. Iso é correcto.
- 33 tests de Hyd en verde.

## 3. Achados

### 3.1 Riscos operativos (arranxar antes de nada)

| # | Risco | Onde | Arranxo |
|---|---|---|---|
| R1 | **Todo Hyd está sen commit** nun checkout 5 commits por detrás de `origin`, mesturado con edicións doutro traballo (`base_corpus.py`, `base_pretrain.py`, `base_tokenizer.py`) | `D:\HYDRA` | Pasalo a unha rama desde `origin/integration/hydra-1.0`, só os ficheiros de Hyd, e abrir PR |
| R2 | `hyd_enabled=True` por defecto e `config/hyd/model.json` sen versionar: nun checkout limpo o arranque falla | `hydra/core/config.py`, `bootstrap.py` | Versionar `config/hyd/` (1,3 MB) ou desactivar Hyd con aviso se faltan os ficheiros |
| R3 | O Studio candidato segue apuntando a Kev (`decision_shadow_endpoint=…:8009`, calibrador `kev-hydra-v2-r1`) | `scripts/run_studio_candidate.py:29-31` | Cambialo a Hyd |
| R4 | `HydController` admite unha soa decisión á vez tamén para o ranker de CPU de 3 ms. Con peticións concorrentes, as demais dan `error` e ensucian a telemetría | `hydra/hyd/controller.py` | Ranker CPU sen semáforo (ou con N slots); o slot único, só para o backend GPU |

### 3.2 Avaliación

- **O 96 % de v4 é sobreaxuste ao test.** A súa capa de regras (`hybrid_classifier.py`, borrada o
  01-10 como código morto) ten patróns copiados das frases do test: «suplanta», «interruptores»,
  «fracciones», «girad», «romper el hielo». O `PROMOTED` de `models/hydra-decision-v4/promotion.json`
  hai que retiralo ou marcalo como inválido.
- **`human-paraphrase-v1` está gastado.** Xa decidiu dúas promocións e o axuste de Hyd. Úsase como
  regresión, nunca máis como test de promoción. Fai falta un test novo, escrito despois de conxelar o
  modelo e por familias.
- O solapamento léxico entre o test e `human-dev-v2` é baixo (mediana Jaccard 0,18; 3/100 ≥ 0,5): o
  conxunto dev pódese usar para adestrar.
- **Sobreconfianza:** os casos que Hyd dá con confianza ~0,96 só acertan o 86 %, porque a temperatura
  0,5 se axustou a frases sintéticas. Isto confirma o documento.

### 3.3 Seguridade

- **O `policy_gate` determinista apenas detecta casos reais:** security 0/10, privacy 1/10, high_risk 0/10.
  Este é o maior oco, e non depende de Kev nin de Hyd. Hoxe a protección real vén dos mecanismos de
  permisos do kernel (correcto), pero a etiqueta de risco que activa a verificación case nunca salta.

## 4. Plan para sacar Kev

Non hai perda funcional en ningunha fase, porque Kev non ten autoridade.

**Fase A, desconectar (1 PR):**
1. R1–R3: Hyd á súa rama e o Studio a Hyd.
2. Quitar o camiño de observador HTTP: `DecisionProvider` «Kev-compatible» (`hydra/providers/decision.py`), a rama
   `decision_shadow_*` de `bootstrap.py` e os axustes `decision_shadow_*`/`decision_calibrator_path` de `config.py`.
   Hyd queda como único observador.
3. Tests: retirar `test_kev_*` e adaptar `test_decision_provider.py`/`test_decision_observer.py`.

**Fase B, limpar o repositorio (1 PR):** 46 ficheiros con «kev» no nome.
- **Código:** `scripts/*kev*` (10), `patches/kev/`, `kev_tests/` e en `hydra/training/` os módulos
  `*kev*`, `prepare_kev_hydra_v2.py` e os avaliadores que só serven a Kev.
- **Docs:** `docs/*KEV*` (14) pasan a `docs/history/kev/`, sen borrar a evidencia histórica.
  `docs/evidence/kev-*` quedan como evidencia arquivada.

**Fase C, artefactos locais (precisa a túa confirmación, á papeleira de reciclaxe):**
- `models/kev-hydra-v2-r1`, `kev-training-parity-*` (3 × 63 MB) e os calibradores `kev-*.json`.
- `D:\kev-main` (820 MB, código Apache-2.0 de terceiros). Tes unha terminal aberta nese cartafol.

## 5. Melloras para Hyd, por orde de retorno

### Rápidas (días, sen GPU)
1. **Test novo e independente primeiro** (antes era o punto 7): 300–500 frases humanas en gl/es/en,
   escritas por ti ou por persoas reais **sen ver os xeradores nin o test vello**, conxeladas en
   `data/private/` antes de adestrar nada. Sen isto, as melloras seguintes non se poden medir.
2. **Recalibrar** con datos que non sexan plantillas (temperatura por clase se hai mostra) e informar
   de ECE, Brier e NLL, e da curva cobertura/risco.
3. **Ensemble con `hydra-decision-v2`** (propio, <1 ms), decidido só con datos de desenvolvemento
   e medido no test novo. Ollo: v2 tamén se adestrou con plantillas da mesma familia.
4. **Autoridade asimétrica:** Hyd só pode **subir** o risco (verificación/revisión), nunca baixalo nin
   conceder nada. Detrás dun axuste desactivado por defecto ata ter o test novo.
5. **Reforzar o `policy_gate`** cun léxico por categorías, escrito por alguén que non vise o test.

### Medias (semanas)
6. **Corpus xeral de decisións (P0 do documento):** opcións dinámicas e nomes opacos, negación e regras compostas
   con oráculo, abstención útil, Noul e Score. Xerado por HYDRA, con holdout por estrutura da regra.
7. **Xeradores con temas propios:** os xeradores de dev deben levar temas novos, non tirados do test.
8. **Runner emparellado** con bootstrap por familia, latencia e memoria totais (punto 6 do documento).

### Longas (dependen de decisións túas)
9. **Encoder contextual:** `hydra/hyd/neural.py` xa existe e carga HYDRA Base. Dúas vías:
   - **(a) HYDRA Base 125M:** propio de punta a punta, pero aínda non está adestrado (agarda a túa orde)
     e a 125M a comprensión será limitada.
   - **(b) Capas de HYDRA v8 (base Qwen, Apache-2.0)** como encoder, con cabeza propia. Sería moito máis
     capaz xa. Os pesos non son de orixe propia; habería que rexistrar licenza e hash.

   Recomendo medir (b) como teito e (a) como obxectivo, coa mesma cabeza e o mesmo corpus.
10. **Promoción xestionada con rollback** (punto 7 do documento). A autoridade completa só cando supere
    os criterios no test novo.

## 6. Criterio para dar autoridade a Hyd

No test novo e emparellado, fronte ao router actual e fronte a `hydra-decision-v2`:
- Cobertura ≥ 0,80 e acerto nos aceptados con Wilson inferior ≥ 0,90.
- ECE ≤ 0,05 e ningunha familia peor ca o router actual.
- Latencia p95 dentro do orzamento do router.

Ata entón, só autoridade asimétrica (subir o risco).

## 7. Decisións que che corresponden

1. Confirmar a Fase A e a Fase B (PRs).
2. Fase C: mandar `models/kev-*` e `D:\kev-main` á papeleira?
3. Encoder: medir a vía (b) v8/Qwen como teito, ou só HYDRA Base?
4. Retirar o `PROMOTED` de `hydra-decision-v4`?

## 8. Primeira medida no test novo (`data/private/hyd-test-v3`, 2026-10-03)

450 frases entregadas polo usuario (3 bloques × 10 etiquetas × 15; 150 grupos paralelos), conxeladas
antes de medir (sha256 `81be6d5f…2e27`). Ningunha ten Jaccard ≥ 0,5 con `decision-corpus-v3`,
`human-dev-v2` nin co test vello. Nada se axustou con elas. IC 95 % por bootstrap de grupos.

| Sistema | Acerto | IC 95 % | Observación |
|---|---|---|---|
| HYDRA v8 sen adestrar, saída restrinxida ás 10 etiquetas | 34,9 % | — | vision 43/45, security 33/45; abstain e high_risk 0/45 |
| Router de regras + `policy_gate` | 24,7 % | 19–31 % | todo o descoñecido vai a `chat` |
| Hyd (ranker CPU) | 19,8 % | 15–24 % | **acepta 19 con confianza ≥ 0,95 e falla 13** |
| `hydra-decision-v2` | 16,4 % | 13–20 % | — |

(azar: 10 %). As cifras anteriores de 52/70/96 % eran froito do parecido entre plantillas de
adestramento e test. Hyd non debe ter ningunha autoridade, nin sequera asimétrica: a súa abstención non
protexe (68 % de erro nos casos que acepta). Mellorar Hyd require un modelo contextual axustado con
datos diversos e etiquetados, separados deste test, que queda só para medir.
