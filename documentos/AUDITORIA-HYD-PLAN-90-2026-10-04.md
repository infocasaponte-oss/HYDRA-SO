# Auditoría de Hyd e plan de implementación para intentar superar o 90 %

Data: 2026-10-04. Estado: auditoría e plan; non se readestrou nin promoveu ningún modelo.

## Conclusión

Hyd ten unha base de runtime e probas sólida, pero non demostrou o 90 % global independente. Reproducín hyd-app-v2: 224/313 = 71,5655 %. A matriz de E2 suma 267/313 = 85,3035 %, co hash correcto do test; non reproducín a inferencia E2 neste contorno. Precisión superior ao 90 % só nas preguntas aceptadas é unha métrica distinta, e non proba un 90 % sobre todas as preguntas.

A mellor orde é corrixir admisión e etiquetas, selar particións por grupos, reproducir especialistas e comparar candidatos antes de combinar modelos. Nin máis parámetros nin unha mestura de expertos garanten ese resultado.

## Alcance, versión e evidencias

- ZIP: `D:/Hyd-main.zip`; SHA256 `8149ce860a4ce2bacdcf9e1c5220040441cda2af87e5d6abe1c980d790ff8a53`; 1.339 entradas. Extracción illada con validación de rutas.
- GitHub main: `9767b997ed201eac8f6a589ce1090aae772a5f2a`. Os seus 1.238 ficheiros versionados coinciden co ZIP tras normalizar CRLF/LF: ningún ausente nin diferente.
- O ZIP representa main, non a PR #1 do calibrador. Contén unha copia ampla de HYDRA, non só o laboratorio Hyd.
- Revisión detallada de `hydra/hyd`, contrato/autoridade do router, corpus da app, adestramento, informes, modelos/calibracións, dependencias e configuración; execución de toda a batería Python e lint de todo o repo.
- Non equivale a unha inspección manual de cada liña nin a pentesting. Non se probaron servizos externos, OAuth, SDK TypeScript, PostgreSQL/Redis reais nin Lovable nesta auditoría do ZIP.
- Faltan neste main: E3, artefactos/informes externos HYD-020/021, frontend e SQL de Lovable, `hyd_calibrator` da PR #1 e workflows CI. Hai só `.github/dependabot.yml`. Non se certifica código que só está visible no panel de Lovable.

Evidencias en `D:/HYDRA/.codex-artifacts/audit-hyd-main-20261004/`: `pytest.txt`, `hyd-tests.txt`, `ruff-full.txt`, `baseline-reproduced.json`, `admission-probes.json`, `runtime-load.json`. Inventario, cálculo de métricas e scan están en `Hyd-main/inventory.json`, `Hyd-main/metric-audit.json` e `Hyd-main/static-scan.json` dentro dese directorio. Non conteñen preguntas completas nin correos dos avaliadores.

## Verificación realizada

| Comprobación | Resultado | Límite |
|---|---|---|
| pytest completo | 1.053 pasan, 88 omitidas, 1 warning; 157,26 s | As omitidas non quedan validadas; non é instalación limpa |
| Seis ficheiros específicos Hyd/router | 54 pasan, 1 warning; 16,10 s | Non cobren directamente E2/app_corpus |
| Ruff en todo o repo | 31 incidencias | Concentradas en app_corpus/e2_semantic; non se modificaron fontes |
| Informe app-v2 reproducido | 224/313; macro-F1 0,695; ECE 0,087 | Test interno xa usado |
| Informe E2 | Matriz 267/313, hash de test coincide | Encoder non executado aquí |
| Carga HydController | config/hyd, app-v1 e app-v2 cargan; autoridade false | Non valida E2 nin pesos contextuais externos |
| Corpus/particións | 2.077 filas; train 1.449/calibration 315/test 313; cero solapamento exacto normalizado | Non certifica separación semántica nin por persoa |
| Sondas en ficheiros temporais | Fallos de admisión reproducidos | Sen alterar corpus/modelos |
| Scan limitado de segredos | Catro patróns en tests/redteam/evals | Fixtures de proba; tres patróns non son auditoría de todos os segredos |

Contorno existente: NumPy 2.5.2, pytest 9.1.1, Ruff 0.16.8, torch 2.5.1+cu121, Transformers 4.46.3 e hub 0.26.5. Non ten sentence-transformers nin scikit-learn. Non se alterou a venv nin se descargaron encoders, e non se lanzou traballo GPU. Estas versións non certifican o ficheiro requirements-training actual.

## Achados e solucións

### P0 — O builder inventa metadatos de dereitos

`hydra/hyd/app_corpus.py:78` escribe `rights.verified=true` e `license=proprietary-hydra-authored` en toda fila admitida, sen ler unha declaración da fonte. As 2.077 filas non teñen rights, source_kind, consent_version nin family_id no meta. Ao transformar tamén perde autor e parte da procedencia.

Non se cuestiona que o propietario declarase seus os datos: o fallo é que o código pode certificar automaticamente calquera fila admitida. Eliminar esa asignación; separar declaración humana, validación estrutural e permisos de uso. Conservar metadatos e orixinais. Migrar datos históricos con declaración explícita do propietario e rexistro de versión; pendentes nunca se marcan verificados automaticamente.

Probas: ausente/false/null/cadea en permisos debe rexeitarse ou quedar pendente; round-trip preserva texto e procedencia; ningún rexistro se perde.

### P0 — Consentimento non comprobado en train e flags non estritos

`hydra/hyd/train.py:rows` comproba rights/split/training_allowed, pero non consent. Unha sonda `consent=false` con dereitos e split declarados foi admitida. `app_corpus.validate` tamén admite suspect_template ausente porque comproba truthiness en vez de false explícito.

Crear admisión compartida para todos os loaders, con booleanos literais e schema versionado; consentimento de almacenamento, adestramento e transmisión externa deben poder distinguirse. Probas con flags ausentes, false, strings, meta malformado, etiquetas descoñecidas e export legado. E2 debe usar a mesma admisión.

### P0 — Definicións de abstain incompatibles

`hydra/router/decision_contract.py:10` define abstain como falta de entrada/contexto. Lovable tamén o usa para peticións perigosas. `HydController.observe` ademais converte baixa confianza en selected=abstain. Etiqueta semántica, decisión de rexeitar e incerteza non deben medirse como se fosen a mesma cousa.

Versionar as dez rutas e engadir eixos auxiliares: risk_kind, context_status, abstain_reason, annotation_status. As etiquetas pendentes nunca contan como negativas. Unha petición lexítima de seguridade non é perigosa por conter certas palabras; unha acción tool_use pode requirir revisión adicional de risco.

Guía única, revisión humana dos casos ambiguos, desacordos/adjudicación rexistrados. Correccións nun evento/táboa separado conservando pregunta e etiqueta orixinais. Confirmar identidade por persoa, non por conta; as dúas contas do propietario son unha persoa. Engadir metadatos reais sobre imaxe/contexto dispoñibles: este encoder textual clasifica intención, non demostra comprensión visual.

### P1 — Split exacto non é separación por familia/persoa

Non hai textos normalizados repetidos entre train/cal/test. O hash non separa paráfrases, moldes, conversacións ou autores. O test interno xa se consultou para varios candidatos: queda como regresión diagnóstica, non unha nova proba cega.

Engadir person_id pseudónimo confirmado, family_id, idioma, orixe, data e conversation_id cando exista; selar manifestos/hash/reconto e separar train/dev/calibration/test por grupos. Con poucas persoas non presentar CV como independente: usar familias para dev e novas persoas para test. Marcar moldes con motivos, sen borrar historia.

### P1 — E2 incompleto para reprodución e integración

`e2_semantic.py:59` carga encoder externo por nome sen revisión/hashes. As súas dependencias non están declaradas no extra do proxecto. `load` non valida consentimento, permisos, particións, duplicados ou manifestos. C escóllese en calibration; a mesma calibration axusta T e limiar. Isto introduce optimismo de selección; non demostra que test se usase no gradiente. O comentario «test touched once» non impide volver executalo.

Separar C/dev, T+limiares/calibration e test final selado; CV agrupada cando haxa suficientes grupos. Fixar revisión do encoder/tokenizer e SHA dos pesos, dependencias e ambiente; caché de embeddings vinculada a datos/modelo. Declarar MiniLM como dependencia externa preadestrada, sen atribuílo a HYDRA desde cero.

`head.npz` só leva coef/intercept/labels/T. Faltan encoder fixado, hashes train/dev/cal, contrato de features/criterios, limiar operativo e implementación. HydController só carga os dous rankers nativos, non E2. Crear artefacto versionado completo e adapter explícito SHADOW_ONLY, con paridade offline/API e validación de finitude, dimensións, clases e hashes.

### P1 — O limiar E2 pode parecer validado sen estalo

`e2_semantic.py:75` acepta >=95 % empírico mesmo con unha soa pregunta aceptada; se non hai limiar válido usa 0,95 sen target_met=false nin abstain_all. Non impón cobertura mínima nin límite Wilson.

Usar mínimo de cobertura, soporte, marxe e límite estatístico, con fail-closed se non se cumpre. Informar accepted/correct e intervalos, non só números redondeados. A calibración non aumenta por si mesma o acerto argmax.

### P1 — Sobrescritura de runs e calibración mal vinculada

`train.py:87` usa config/hyd por defecto e acepta saída existente. app_corpus.build e E2 tamén reutilizan directorios. Isto pode sobrescribir pesos ou snapshots. app_corpus.report non comproba o vínculo modelo/calibración como HydController.

Run_id inmutable, saída nova obrigatoria, escritura atómica e promoción separada con rollback. Vincular datos, criterios e implementación; rexeitar calibración doutro modelo. Proba: unha repetición non cambia ningún byte do run anterior.

### P1 — Código de Lovable e repo diverxen

Faltan E3 e as avaliacións externas neste ZIP/main. As cifras vistas antes no panel non están reproducidas por esta auditoría. Recuperar fonte, SQL, artefactos, scripts e resultados privados completos, con reconto de toda fila/exclusión. Non empezar un mesturador sobre especialistas sen poder reproducilos.

Probar RLS e exports con conta propietaria e allea: SELECT/INSERT/UPDATE/DELETE. Non crear administradores para facilitar acceso. Migracións aditivas revisadas, copia completa e anotacións exportables.

### P2 — CI, instalación e código

31 incidencias Ruff; CI ausente no ZIP. Dependabot non substitúe CI. requirements-training comenta hub>=1.5,<2.0 pero fixa 1.33.0: comentario/pin discordantes; non se afirma incompatibilidade efectiva sen resolver metadatos. Falta extra semantic. Paquete raíz hydra-engine; calibrador da PR #1 aínda non incluído.

CI Linux/Windows, Ruff, wheel e smoke desde instalación limpa fóra do checkout. Locks por perfil CPU semantic/GPU native; resolver e probar nunha venv illada, sen actualizar o contorno de adestramento activo. Pesos grandes con SHA, localización privada e procedemento de recuperación. Os modelos de hash cargan; iso non certifica os pesos contextuais ausentes.

## Que significa superar o 90 %

| Modelo | Acerto global | Macro-F1 | ECE | Evidencia |
|---|---:|---:|---:|---|
| app-v2 | 224/313 = 71,5655 % | 0,695 | 0,087 | Reproducido |
| E2 | 267/313 = 85,3035 % | 0,847 | 0,030 | Matriz/hash verificados; inferencia pendente |
| E2 confianza >=0,85 | 94,8 % entre aceptadas | — | — | Informe, cobertura 61,7 %; cifras redondeadas |

Wilson 95 % de 267/313: 80,95–88,80 %. O intervalo binomial non resolve correlación por familia/persoa nin sesgo do test. En 313 filas, >90 % require 282 acertos; límite inferior Wilson >=90 % require 293. Nun test de 1.000 filas require 919 acertos para ese límite. Son cálculos, non unha indicación de optimizar estas preguntas xa vistas.

E2 erra 46: 13 abstain e 7 chat explican 20/46. Confusións frecuentes: abstain/privacy/security, coding/tool_use, vision/research, privacy/security. Recoller novas familias destas fronteiras para dev; non reciclar silenciosamente test en train.

Protocolo de obxectivos proposto antes de experimentar:

- Accuracy global >90 % e límite inferior Wilson >=90 % nun test novo selado; macro-F1 >=0,90 para evitar ocultar clases débiles.
- Supports, P/R/F1 e intervalos por clase/idioma/persoa/orixe; bootstrap por grupos ademais de Wilson.
- Precisión selectiva e cobertura separadas. Conservar os requisitos actuais do gate de autoridade: cobertura >=80 %, ECE <=0,10, evidencia independente e vínculos. Non usar abstención para inflar accuracy global.
- Perigosidade: proposta de deseño recall >=95 % e FPR <=5 % con positivos e negativos humanos e intervalos; aínda non demostrado nin suficiente por si só para executar accións.
- CPU/dispositivo: medir p50/p95/p99, memoria, throughput, arranque frío/quente e concorrencia; fixar orzamento antes de seleccionar modelo, sen inventar latencias.

## Plan de implementación ordenado

| Entrega | Implementación | Probas de aceptación | Depende de |
|---|---|---|---|
| A01 | Schema de admisión común, procedencia, permisos e orixinal/variantes; eliminar auto-verified | false/ausente rexeitado; round-trip exacto; cero perda de rexistros | Primeiro |
| A02 | Taxonomía versionada e eixos risco/contexto; motivos de abstención | Casos ambiguos adjudicados; pendentes nunca negativos; dous emails non dous humanos | A01 |
| A03 | Snapshots/hash e train/dev/cal/test por familias/persoas | Cero overlap exacto/grupal; detectar adulteración; exclusións auditables | A01–02 |
| A04 | Exportar Lovable e reproducir E2/E3; locks e encoder fixado | Reproducir predicións/recontos nun ambiente CPU limpo | A03 |
| A05 | E1 TF-IDF word/char + regresión/SVM calibrada; baseline hash 512/1024 | CV agrupada; etiquetas non usadas como features; ablations por idioma/familia | A03 |
| A06 | Fine-tuning dun encoder pequeno; comparar cabeza lineal e clasificador por pares | Tres sementes en dev, early stop, curvas datos/erro e custo medido | A04–05 |
| A07 | E3 risco separado de ruta, subtipos e negativos lexítimos | P/R/F1/FPR con denominadores por tipo, anotacións humanas | A02–04 |
| A08 | Ensemble simple antes de mesturador complexo | Predicións out-of-fold; ablations E1/E2/E3; OOD e desacordos fail-closed | A05–07 |
| A09 | Calibración separada e adapter runtime/API | Paridade offline/API, hashes, invariancias, timeout, fail-closed | A06–08 |
| A10 | Test final cego, release evidence, shadow e rollback | Gates estatísticos/risco/latencia/acceso; promoción explícita | A09 |

Cada entrega: PR pequena, evidence.json e probas. Son paquetes de traballo, non promesas de prazo. Non empezar por un 4B desde cero: routing é clasificación e un encoder pequeno é unha hipótese máis barata. 4B/VL necesita outra liña de datos, orzamento e validación multimodal; non garante mellorar este problema.

### Datos que faltan e recollida

Recuperar o código Lovable actual, migracións, artifacts E3, scripts e predicións por fila das avaliacións externas; export privado completo actualizado e manifestos. O ZIP non inclúe os novos rexistros do panel. Confirmar a identidade declarada dos novos autores sen inferila polo email. As marcas de estilo/moldes son heurísticas: non demostran autoría IA.

Recoller diversidade de persoas/situacións/idiomas e fronteiras: escribir código/executalo, buscar evidencia/operar ferramentas, imaxe dispoñible/ausente, seguridade lexítima/abuso, privacidade/chat, revisión/acción irreversible. Separar tráfico real, preguntas escritas manualmente para avaliación e sintéticas; non inventar orixe.

Deseño proposto: test final de 1.000 preguntas, 100 por clase, de persoas/familias novas, máis unha mostra separada coa distribución real de uso. Non se afirma que esas filas existan. Polo menos cinco persoas novas como punto de partida de diversidade non garante representatividade. Dobre revisión dunha mostra e adjudicación de desacordos.

As avaliacións externas xa consultadas quedan como regresión. Se se utilizan para desenvolver/adestrar, documentar esa transferencia e reservar outro test cego. Non eliminar as preguntas difíciles para subir a métrica.

### Experimentos para buscar a mellora

1. Reproducir baseline/E2 e medir ruído de etiquetas en desenvolvemento.
2. TF-IDF word/char e C por grupos; comparar coa representación hash.
3. Fine-tuning moderado MiniLM con train/dev, tres sementes e parada temperá; pesos de clase só elixidos en dev.
4. Outro encoder ou clasificador por pares só se segue un déficit semántico, co mesmo protocolo/custo. Non buscar indefinidamente o modelo que mellor encaixa co test.
5. Ensemble E1+E2 e +E3 con out-of-fold; conservar o máis simple que mellore e cumpra límites.
6. Calibrar o gañador, selar pesos/protocolo e executar o novo test final. Se falla, rexistrar o fallo e abrir nova iteración; non retocar e presentar o mesmo test como independente.

## Matriz detallada de probas

| Área | Casos obrigatorios |
|---|---|
| Datos | JSON/unicode; espazos preservados; conflitos/duplicados; consentimento false/ausente; permisos pendentes; límites; hashes/familias/persoas; dez clases; reconto de exports/exclusións |
| Anotación | Orixinais inmutables; versión/autor/motivo; historial exportable; pendentes; identidade confirmada; evitar negativos inferidos por falta de marca |
| Modelo | Semente/reprodución; NaN/Inf/dimensións; encoder/tokenizer/clases errados; truncamento; lote/unitario; artefactos adulterados; revisión ausente |
| Métricas | Matriz suma n; P/R/F1 e soportes; ECE/NLL; cero/un aceptado; fail-closed; abstain semántico separado da incerteza; micro/macro; intervalos por grupo |
| Comparación | Pareada McNemar e bootstrap macro-F1 por grupo; ablations; filtro independente da predición; dev e test separados |
| Runtime/API | Autoridade false; hashes modelo/calibración/implementación; paridade; auth/429/504; límites; invariancia de orde; slot tras timeout; cold/hot; rollback |
| Lovable/BD | Migración aditiva revisada; backup completo; RLS propietario/alleo; anotación só propia; erro visible; gardar/recargar/exportar; provedor IA autorizado e sen autoridade |
| Entrega | CI Linux/Windows; Ruff; wheel e smoke fóra do checkout; lock semantic/native; manifestos de pesos; promoción manual |

Se só se marcan abstain non se pode inferir FPR en todo o tráfico: reunir negativos humanos ou declarar a métrica restrinxida. Se datos/taxonomía/reprodución fallan, non readestrar. Se dev non mellora, revisar etiquetas/recollida antes de aumentar tamaño. Se o global supera 90 % pero falla risco/cobertura, non promover.

## Fontes primarias do protocolo

- [Scikit-learn: validación cruzada por grupos](https://scikit-learn.org/stable/modules/cross_validation.html).
- [Scikit-learn: calibración de probabilidades](https://scikit-learn.org/stable/modules/calibration.html).
- [Sentence Transformers: adestramento e avaliación](https://www.sbert.net/docs/sentence_transformer/training_overview.html).

Estas fontes apoian a metodoloxía; non prometen unha accuracy de Hyd. A auditoría non cambia datos, dependencias, modelos activos nin permisos de Lovable.
