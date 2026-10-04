# Ferramentas locais de Hyd e integración en HYDRA

Primeiro incremento do plan do 2026-10-04: contrato `hyd-routing/1`, adaptador de observación, intake humano estrito, snapshots por familias e traballos persistentes de laboratorio. Non activa autoridade, non cambia configuracións en produción e non modifica o adestramento en marcha.

## Dependencia separada

Instalar o wheel de `hyd-calibrator` da PR de Hyd no mesmo ambiente de HYDRA:

```powershell
python -m pip install C:\ruta\hyd_calibrator-0.1.0-py3-none-any.whl
python -m hydra.hyd.tools contract
```

O contrato e a validación de intake non precisan o calibrador. Calibración, informes e exportación si. A integración comproba igualdade exacta dos criterios e carga os artefactos coas regras de hash e implementación do paquete separado. Só se admite o ranker hash v1 neste incremento.

## Traballos CLI

Exemplo de petición real de calibración (substituír as rutas polos artefactos existentes, non crear preguntas para encher as particións):

```json
{"kind":"calibrate","model":"staging/hyd/model.json","dataset":"staging/corpus/calibration.jsonl","train_dataset":"staging/corpus/train.jsonl","target":0.95,"min_coverage":0.1}
```

```powershell
python -m hydra.hyd.tools --root . --state data/hyd-tools submit request.json
python -m hydra.hyd.tools --root . --state data/hyd-tools status JOB_ID
python -m hydra.hyd.tools --root . --state data/hyd-tools run JOB_ID
python -m hydra.hyd.tools --root . --state data/hyd-tools cancel JOB_ID
```

Tipos: `calibrate` (modelo ficheiro e train obrigatorio), `report` (dataset e directorio modelo), `validate` (intake JSONL), `snapshot` (intake JSONL), `export` (directorio do candidato calibrado). Os resultados e artefactos quedan baixo state/JOB_ID. Entrada limitada ao root, ficheiros ≤20 MiB, dez traballos pendentes e un traballo executándose. Os hashes fíxanse ao enviar e compróbanse antes e despois da execución. Os resultados con inputs cambiados quedan como fallo.

Enviar non executa. Cancelar só afecta traballos queued. `run` é unha chamada que agarda polo resultado, executada nun fío cando se usa HTTP. Este incremento non inclúe un worker distribuído, cancelación cooperativa dun traballo en marcha, nin recuperación automática dun proceso interrompido. Un traballo running tras unha caída precisa revisión do operador, sen asumilo completado. Usar unha instancia local de laboratorio e preservar a base SQLite; non está preparado para varias réplicas.

`export` crea unha calibración nativa ligada ao implementation_digest desta versión de HYDRA, conserva exactamente os bytes dos pesos e comproba que HydController carga sen autoridade. Require obxectivo cumprido, abstain_all=false, evidencia de selección coherente e comprobación de solapamento co train. Non sobrescribe un directorio existente nin promove nada. A adaptación dun candidato non acredita que estea listo para produción. O candidato actual da app non cumpre o obxectivo estrito: a exportación rexéitase, aínda que se pode analizar en sombra mediante RoutingAdapter.

## API de operador, opt-in

Configurar HYDRA_HYD_TOOLS_ENABLED=true e HYDRA_HYD_TOOLS_INPUT_ROOT nunha carpeta de inputs autorizados. Usa a autenticación existente do gateway e ademais X-Hydra-Admin-Token. Coa opción require_shared_state=true o laboratorio local rexéitase.

- GET `/hydra/v1/hyd-tools/contract`
- POST `/hydra/v1/hyd-tools/jobs` con JobRequest
- GET `/hydra/v1/hyd-tools/jobs/{id}`
- POST `/hydra/v1/hyd-tools/jobs/{id}/run`
- POST `/hydra/v1/hyd-tools/jobs/{id}/cancel`

Son operacións de administrador, non ferramentas que o modelo poida invocar automaticamente. Non hai endpoints de promoción. A API normal non cambia cando a opción está desactivada.

## Intake e snapshots

O esquema executable é IntakeRecord en hydra/hyd/corpus_contract.py. Require id, texto orixinal e actual, etiqueta, family_id, orixe explícita, evento/version do consentimento, revisión de privacidade, sospeita de plantilla, dereitos con referencia e revisións humanas. Exixe booleans estritos. As variantes corrixidas precisan aceptación humana e motivo; o orixinal consérvase. As opinións da IA quedan nun campo separado e non contan como votos humanos.

En modo development (por defecto), unha revisión humana abonda para experimentar; non se declara evidencia independente. O modo double_review require dúas persoas distintas. Só son admisibles rexistros non retirados, con consentimento e privacidade revisados, dereitos verificados declarados, revisións concordantes segundo o modo escollido e orixe user_traffic ou human_evaluator. Outros rexistros quedan en corentena. O intake non demostra que esas identidades ou declaracións sexan certas: o sistema de recollida deberá autenticarlas e manter as súas referencias. Varias contas do mesmo propietario contan como unha soa persoa; non como revisores independentes. A app actual do ZIP non achega esa evidencia e non se migra automaticamente como datos verificados.

Snapshots deterministas por family_id, variantes xuntas, train/calibration/test sen familias cruzadas. Exixen as dez clases e particións non baleiras. Exportan hashes, recontos e procedencia mínima sen correos, nomes de revisores, notas persoais, opinións IA nin texto orixinal de variantes ao ficheiro de adestramento. As referencias tamén deben ser pseudónimas; non introducir correos nelas. Os rexistros retirados quedan fóra dos snapshots novos; este incremento non desaprende pesos nin busca o impacto sobre modelos históricos.

## Verificación e límites pendentes

Probas: consentimento estrito, orixe, consenso, corrección, IA separada, familias, reproducibilidade, hashes, cancelación, persistencia, permisos e rexeitamento multi-nodo. As dúas probas de paridade/exportación son opcionais se non está instalado hyd-calibrator; para validalas, instalar ese paquete e executar `pytest tests/test_hyd_tools.py tests/test_hyd.py tests/test_contracts.py -q`.

Pendentes do plan: verificar RLS e migracións Supabase, modificar a UI de Lovable, corrector/provedor de segunda opinión, arbitraxe humana autenticada, separación dev e test externo independente, rexistro de releases/promoción, operación multi-nodo e medición de capacidade. Non se declaran esas partes completadas nin se certifica produción.
