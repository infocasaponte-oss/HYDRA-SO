<!-- Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved. -->
# Plan de ferramentas e integración Hyd → HYDRA

Data: 2026-10-04. Estado: proposta de traballo, non certificación de produción.

## Obxectivo e punto de partida

Construír un ciclo verificable: preguntas con procedencia → revisión humana → corpus versionado → adestramento → calibración → avaliación independente → integración en sombra → promoción controlada → operación e mellora. Hyd poderá evolucionar separado, conservando un contrato para volver a HYDRA. O calibrador será unha ferramenta do plano de aprendizaxe, non unha modificación automática do motor en produción.

Evidencia dispoñible: revisión de Hyd e PR borrador #1, dous ZIP e capturas da área de avaliadores. No candidato incluído reproducíronse 223/313 acertos, 93/96 entre os aceptados e 30,67 % de cobertura. Isto non certifica produción. O axuste de temperatura mellora lixeiramente a NLL de calibración, pero non cumpre o obxectivo Wilson proposto. Non temos o código nin o esquema da app Lovable nesta revisión: os cambios desa app descríbense como traballo pendente.

As capturas amosan entrada individual e por lotes, consentimento, clase asignada e segunda opinión de IA. Hai variantes de preguntas próximas; a captura non permite acreditar a súa orixe. HYDRA xa dispón de revisión humana de holdouts ligada a hashes en `hydra/api/evaluation_routes.py`; esa revisión e a recollida de corpus son funcións diferentes, aínda que poden compartir identidade, auditoría e UI.

## 1. Contrato para poder integrar calquera evolución de Hyd

«Calquera evolución» significa calquera implementación que cumpra un contrato versionado; non asumir que pesos ou formatos novos sexan automaticamente compatibles.

Crear un paquete pequeno de contratos, compartido por Hyd, calibrador, app e HYDRA. Primeira versión: identificadores e descricións exactas das dez clases actuais, esquema das entradas/saídas, significado da abstención, versión das características, esquema do corpus e dos manifestos. Cambiar unha clase ou o significado dunha decisión require nova versión e avaliación de migración.

Interface proposta do adaptador: recibe estado, instrucións, criterios e prazo; devolve probabilidades finitas normalizadas, clase proposta, confianza, marxe, abstención e motivo, revisión do modelo e revisión da calibración. A abstención técnica e a clase semántica `abstain` deben representarse separadamente. Timeout, fallo ou dominio non soportado conservan a ruta segura de HYDRA. O policy gate segue antes do ranker.

Un paquete de candidato inclúe pesos, tokenizador se procede, manifestos, contrato, hashes de datos/modelo/calibración/implementación, versión do código, ambiente reproducible, informes, límites e instrucións de carga. O adaptador verifica estes vínculos antes de cargar. O manifest incorpora tamén `abstain_all`: se non se alcanza o obxectivo, ningún redondeo ou probabilidade saturada pode activar decisións.

O formato actual `hyd-standalone-calibration/1` non se copiará directamente sobre a configuración do runtime. Desenvolver un adaptador/exportador explícito, probar paridade numérica con Hyd e ligar a calibración á implementación destino. Se cambia o cálculo das probabilidades, repetir calibración e avaliación. Se a validación falla, o candidato non recibe autoridade.

## 2. Área humana: preservar preguntas, corrixir con trazabilidade

Separar tres orixes: tráfico real de usuarios con permiso, preguntas escritas por avaliadores humanos e contido asistido ou xerado por IA. Unha pregunta humana creada para avaliar non se presentará como tráfico real. As marcas son declaracións acompañadas de procedencia, non probas automáticas.

Gardar texto orixinal inmutable, idioma, contexto necesario, orixe declarada, evento de consentimento versionado, alcance de uso, procedencia dos dereitos, identidade interna pseudonimizada do colaborador, momento de recollida e historial de revisión. Non exportar correo nin identificadores persoais ao corpus de adestramento. Aplicar revisión de privacidade antes de enviar texto a un provedor externo; os datos sensibles quedan en corentena ou nunha versión redactada trazable.

O corrector terá dúas funcións visibles:

- **Revisión da pregunta:** detectar erros de escritura, contexto ausente, ambigüidade e posibles datos sensibles. Propoñer un diff; nunca sobrescribir o orixinal. Un humano acepta, rexeita ou modifica a proposta. Se a corrección cambia a intención, rexistrar unha pregunta derivada e volver etiquetala.
- **Revisión da etiqueta:** mostrar a definición das clases e permitir decisión humana por pregunta. O modo lote facilita a entrada, pero a clase común é provisional ata revisar as filas. As discrepancias non se resolven por maioría de saídas de IA.

Conservar tamén os erros naturais de escritura: son parte da distribución que Hyd debe comprender. O corpus poderá ter variantes corrixidas para experimentos, pero todas as variantes da mesma pregunta permanecerán na mesma partición. Unha corrección de IA aceptada segue tendo procedencia asistida; non pasa a «humana pura».

Etiquetado humano en dúas pasadas independentes, sen mostrar a etiqueta doutro revisor nin a IA na primeira pasada. Discrepancias a arbitraxe humana, con motivo e opción «non resolto». Medir acordo global e por clase, incluíndo confusións e soporte. As preguntas non resoltas non entran silenciosamente como verdade de referencia.

## 3. Segunda opinión de IA intercambiable e sen autoridade de etiqueta

Manter a opinión actual como axuda informativa, identificada como «suxestión de IA, sen validar». Rexistrar provedor, modelo/revisión dispoñible, prompt versionado, resposta, momento, latencia, erros e hash da entrada concreta. Se o provedor non ofrece unha revisión estable, declarar esa limitación.

Interface de provedor proposta: recibe unha pregunta xa autorizada/redactada e o contrato de clases; devolve clase suxerida, explicación e límites. O resultado almacénase separado das etiquetas humanas. Non alimenta directamente train, calibration nin test como etiqueta correcta. Mostrar a opinión tras pechar a primeira revisión humana para reducir ancoraxe; calquera cambio posterior queda rexistrado.

O corrector e a segunda opinión poden usar regras locais, un modelo propio ou un provedor externo. A UI non dependerá de Lovable como formato de datos nin como autoridade. Erros do provedor non impiden gardar nin revisar unha pregunta humana.

## 4. Corpus fiable e test realmente separado

Estados propostos: recibido → corentena/revisión → etiquetado → arbitrado → admisible → incluído en snapshot; retirada e exclusión teñen eventos propios. O backend, non só a UI, aplica as regras. Exportación paginada, reconto total e hashes verificables, sen truncar aos rexistros visibles.

Deduplicar textos exactos e detectar familias/variantes semánticas como avisos revisables. Identificador estable de familia; dividir por familia antes de adestrar. Conservar tamén agrupación de procedencia/evaluador cando corresponda. O hash estable por texto actual evita solapamento exacto, pero non separa paráfrases.

Crear particións distintas: train, dev para elección de arquitectura/hiperparámetros, calibration só para temperatura/limiares, e test externo con acceso restrinxido e protocolo de uso. Engadir avaliación temporal e por dominio. Un test usado repetidamente para decidir melloras convértese en diagnóstico; para a seguinte promoción preparar outro holdout.

O snapshot leva esquema, hashes, reconto por clase/orixe/idioma, familias, exclusións e versión das revisións humanas. Se falta procedencia, marcala como descoñecida; non completala con datos inventados. A retirada dun rexistro produce un tombstone e unha análise dos snapshots/modelos afectados; non se afirma que borrar o JSONL elimine a súa influencia dos pesos xa adestrados.

## 5. Calibrador como ferramenta de HYDRA

Primeiro usar o CLI independente. Despois integralo como traballo versionado do plano de aprendizaxe: validar corpus, comprobar separación, ler candidato, axustar temperatura, seleccionar limiares con obxectivo explícito e xerar paquete de evidencia. Engadir comparación reproducible coa base usando exactamente os mesmos casos.

A API futura devolve job_id, estado, artefactos e erros; a UI amosa condicións incumpridas, numeradores, intervalos e exclusións. Separar permiso para lanzar traballos de permiso para promover. Cotas, cancelación, límites de recursos, rexistro e resultados persistentes. O calibrador non reescribe configuracións activas nin inicia adestramento externo por conta propia.

Informar acerto global, precisión/recall/F1 por clase, matriz de confusión, NLL, Brier, ECE, cobertura, precisión aceptada e Wilson; distinguir abstención técnica da clase `abstain`. Engadir métricas por orixe, idioma, dominio e clases de risco, e custo/latencia de extremo a extremo. Os obxectivos deben quedar fixados antes de consultar o test.

## 6. Produción do motor e do modelo: dúas portas separadas

Un motor pode estar listo para operar con provedores substituíbles mentres un modelo propio segue sen evidencia suficiente. Non declarar ambos listos por ter unha API ou un GGUF.

| Porta | Evidencia necesaria | Se falla |
|---|---|---|
| Hyd como ranker | Paridade do adaptador, contrato e hashes, cobertura/acerto por clase, abstención e fallos controlados | Continúa en sombra coa ruta base |
| Motor HYDRA | Autenticación, policy gate, illamento entre clientes, límites, auditoría, persistencia, recuperación e rollback probados | Non abrir produción |
| Modelo propio | Pesos e procedencia verificables, tarefas de xeración reais, comparación coa base, seguridade, ferramentas, latencia e memoria no hardware destino | Mantelo como candidato de laboratorio |
| Operación | Alertas útiles, responsables, copias restauradas, rexistro de versións e protocolo de incidentes | Non ampliar exposición |

Proposta inicial para discutir antes do test: precisión aceptada do ranker con límite Wilson ≥95 % e cobertura ≥60 %, sen degradación relevante nas clases de risco. Non son resultados alcanzados nin unha garantía de seguridade. A mostra necesaria dependerá da precisión, cobertura e resultados por clase; fixala mediante un deseño de avaliación, non só cun número global arbitrario.

Ruta de promoción: laboratorio → integración en sombra → proba externa → aprobación de release → canary con exposición limitada → ampliación por etapas. Cada release liga modelo, calibración, contrato e configuración. Rollback conserva unha versión anterior cargable e probada. A activación de autoridade é un paso explícito, non consecuencia de rematar unha calibración.

## 7. Escalar despois de medir

Medir primeiro tráfico, concorrencia, memoria, throughput, p50/p95/p99 de extremo a extremo, colas, timeouts, custo e taxa de fallback no hardware real. As latencias do ranker en CPU non son latencias do servizo completo. Despois decidir batching, workers ou máis hardware segundo o colo de botella observado.

Separar recollida/revisión humana, traballos de aprendizaxe e inferencia. Traballos longos con idempotencia e checkpoints; corpus e rexistro de modelos compartidos e versionados. Antes de varias réplicas, probar estado compartido, illamento, recuperación e rollback. Calquera GPU/modelo/provedor novo require medición real, non cifras supostas.

## 8. Orde de execución e entregables

| Paso | Entregable concreto | Criterio para pechalo |
|---|---|---|
| A. Consolidar o calibrador | Revisar PR #1 e rexistrar versión | Probas e reprodución pasan; límites aceptados |
| B. Fixar contrato v1 | Esquemas, exemplos exclusivamente de proba e adaptador de Hyd | Validación e paridade contra HYDRA; erros sen autoridade |
| C. Auditar a app | Código/esquema actuais, permisos, exportación e historial | Inventario comprobado; sen cambios de datos por inferencia |
| D. Mellorar a área humana | Orixinal/derivado, corrector, revisión por fila, segunda opinión separada | Ningunha IA se converte en etiqueta humana; exportación completa |
| E. Rexistro e snapshots | Procedencia, familias, arbitraxe e retirada | Recontos/hashes coherentes, separación comprobada |
| F. Integrar ferramentas | Job de calibración e UI de evidencia en HYDRA | Traballos reproducibles e sen activar releases |
| G. Probar candidatos | Informes comparables e test externo pechado | Obxectivos predeclarados cumpridos ou fallo visible |
| H. Preparar produción | Dúas portas, runbook, canary e rollback | Evidencia operativa e de modelo aprobada |
| I. Escalar | Informe de carga e plan de capacidade | Capacidade medida e estabilidade demostrada |

Non se asignan datas nin avances ficticios. Cada paso terá un responsable humano e unha PR acoutada; dependencias e traballo independente poderán solaparse cando haxa capacidade real.

## Primeiro incremento executable

Tras revisar a PR actual, implementar contrato v1 e unha proba de paridade de Hyd dentro de HYDRA sen activar autoridade. Para cambiar a app, obter acceso ao seu repositorio/esquema e confirmar se «corrector» inclúe escritura, etiqueta ou ambas; o plan propón ambas como funcións separadas. Mentres tanto pódense preparar contratos, criterios de admisión, esquema de procedencia e protocolo de avaliación.

Todo avance debe apuntar á súa evidencia: commit, snapshot, execución e revisión humana. Se non se mediu, figura como pendente; se non se pode verificar, figura como descoñecido.


## Avance comprobado: preparación da recepción de corpus (2026-10-04)

Implementada a auditoría local hydra.training.corpus_preflight na rama codex/hyd-integration-tools (PR #119). Le shards JSONL/JSONL.gz, valida hashes/recontos e fugas exactas/familias con índice SQLite temporal. Non precisa Lovable nin activa adestramentos. Proba real: 2077 filas do corpus actual, hashes/recontos correctos e sen duplicados exactos; sen IDs de familia, revisión semántica pendente. Corpus futuro de 4B: aínda non recibido nin auditado. O adestrador base só ten configuracións 30m/125m; unha configuración 4B e a súa viabilidade no hardware seguen pendentes.

Guía executable: docs/CORPUS_4B_PREFLIGHT.md da PR #119. Non se programou ningún traballo para mañá nin se interrompeu o adestramento activo.
