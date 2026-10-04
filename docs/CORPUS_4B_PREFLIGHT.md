<!-- Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved. -->
# Recepción do corpus para o candidato de 4B

Preparación local, sen dependencias de Lovable. Non lanza adestramentos nin modifica modelos activos. O corpus futuro aínda non se recibiu: non se declara completo, validado nin suficiente.

## Auditoría executable

```powershell
python -m hydra.training.corpus_preflight --corpus D:/ruta/corpus --out D:/ruta/auditoria-nova.json
```

O directorio require manifest.json cun mapa files. Cada entrada leva sha256 e, opcionalmente, documents ou examples e split. Os shards admitidos son JSONL ou JSONL.gz con text, ou input.query. A partición debe constar en split ou nun nome train, dev, validation, calibration ou test (admite sufixos de shard). Conversacións messages e Parquet necesitan un adaptador explícito: non se concatenan nin se converten automaticamente.

A ferramenta le por liñas, calcula hashes por bloques e usa un índice SQLite temporal en disco para duplicados e familias. A RAM non necesita conter todo o corpus; a capacidade do disco temporal debe soportar o índice. Compara hashes e recontos declarados e detecta cambios de ficheiros durante a auditoría. Non exporta textos nin os nomes dos colaboradores. Os nomes de ficheiros quedan no informe; non deben conter datos persoais.

O hash de duplicación normaliza maiúsculas e espazos. Non acredita separación semántica. family_id declarado detecta variantes repartidas entre particións; a ausencia de familias queda cuantificada. Non se inventan familias nin se deducen licenzas ausentes.

Saída CLI: 0 se pasan as comprobacións de integridade, 1 se hai problemas e 2 se a entrada non se pode auditar. Un informe que pasa segue con ready_for_4b_training=false: é unha comprobación estrutural, non unha autorización de adestramento.

Se está dispoñible o tokenizer real SentencePiece, --tokenizer D:/ruta/tokenizer.model conta os tokens do contido. Non inclúe BOS/EOS, chat templates nin packing; non equivale aos tokens finais consumidos polo adestrador. Sen tokenizer queda tokens=null. Non se estima a suficiencia dun corpus a partir de caracteres.

## Orde de traballo cando chegue

1. Rexistrar o inventario e hashes do orixinal, conservar unha copia inmutable e determinar se é pretraining, instrucións ou routing. Un corpus de preguntas etiquetadas para Hyd non proporciona por si mesmo exemplos completos de resposta para un modelo xerativo.
2. Comprobar procedencia, permisos declarados, orixe humana/asistida/sintética e revisión de privacidade. Preservar texto orixinal e decisións de exclusión. Non completar datos históricos por inferencia.
3. Separar familias e procedencias antes de fixar train/dev/calibration/test. Reservar unha avaliación nova: o test de 313 preguntas xa é diagnóstico de desenvolvemento.
4. Executar a auditoría e resolver fugas, duplicados e erros. Validar tamén o mapa de familias/variantes e fontes compartidas; non abonda o hash exacto.
5. Fixar tokenizer, esquema de entrada/saída e contido real dos exemplos. Contar tokens coa mesma serialización que consumirá o adestrador; comprobar límites e truncamento.
6. Escoller explicitamente adestramento desde cero ou adaptación dun checkpoint. Para adaptación, fixar identidade/hash/revisión do modelo e tokenizador. Para desde cero, validar unha arquitectura concreta e o reconto efectivo de parámetros. Non reutilizar o comando base actual como se soportase 4B.
7. Medir memoria e rendemento nunha proba pequena cando a GPU estea dispoñible, sen interromper o adestramento activo. Preparar checkpoints, reanudación e unha proba de recuperación. Non presupor que o hardware actual soporta 4B.
8. Só entón fixar o plan de adestramento e os criterios de avaliación, regresión, abstención e integración shadow. A promoción require evidencia independente e revisión.

O adestrador base inspeccionado só define SHAPES/PLANS para 30m e 125m. Esta mellora prepara a recepción do corpus; non engade nin certifica un trainer de 4B. O candidato de routing 1024/256 xa medido é outro modelo e conserva autoridade desactivada.

## Evidencia desta implementación

Seis probas da ferramenta máis nove de integridade do dataset pasan localmente. A execución real sobre unha copia byte a byte do corpus actual da app auditou 2077 filas: train=1449, calibration=315, test=313. Hashes e recontos coinciden, sen duplicados exactos. Non hai family_id nesas filas: a separación semántica segue pendente. Sen tokenizer non se contou ningún token. O informe está en docs/evidence/hyd/corpus-preflight-app-20261004.json. Esta proba non audita o corpus de 4B que aínda non chegou.

## Arquitectura candidata de aproximadamente 4B

```powershell
python -m hydra.training.prepare_4b --verify-meta --vocab-size 32000 --out D:/ruta/preparacion-4b-nova.json
```

Configuración proposta: Llama con embeddings compartidos, 41 capas, hidden_size=2560, intermediate_size=10240, 20 cabezas de atención e 5 KV, contexto máximo 4096. Co vocabulario proposto de 32000 ten exactamente **3.978.247.680 parámetros**. O reconto foi comprobado cun LlamaForCausalLM real sobre dispositivo meta: non se reservaron os pesos en RAM nin en GPU. Isto valida construción e reconto, non unha pasada forward/backward ou a calidade do modelo. Evidencia: docs/evidence/hyd/4b-architecture-preparation-20261004.json.

O vocabulario é unha proposta, non o tokenizer definitivo. A preparación permite cambiar --vocab-size e recalcula o reconto; os IDs especiais deben lerse do tokenizer real. O perfil non se engade aos comandos de lanzamento do adestrador base, porque ese backend aínda non se validou para 4B. A taxa de aprendizaxe, scheduler e batch efectivo permanecen sen fixar.

Equipo observado nesta sesión: RTX 3060 Ti con 8192 MiB de VRAM e 34314792960 bytes de RAM instalada. Non se iniciou unha carga de GPU. O propietario indica que xa executou un 7B cuantizado neste equipo; esa experiencia está rexistrada como declaración do propietario, sen afirmar unha medición nova de latencia, contexto ou memoria. O adestramento actual mantense e a proba grande queda pendente da súa dispoñibilidade.

Para esta configuración, os límites aritméticos son 7,41 GiB só de pesos bf16 e 59,28 GiB para pesos fp32, gradientes fp32 e dous estados Adam fp32. Non inclúen activacións, logits nin buffers. O adestrador actual utiliza ese último esquema de estados; non cabe integramente na RAM observada. Executar inferencia cuantizada non mide ese custo de adestramento.

Cando estea dispoñible o corpus, decidir explicitamente se se quere adestramento desde cero ou adaptar un checkpoint existente. A configuración propia de 4B corresponde á primeira vía; non crea un checkpoint pretrained. Para adaptación dun 4B/7B cuantizado hai que identificar o checkpoint/tokenizer e preparar un backend de adaptación validado para ese formato; non se deduce compatibilidade a partir do tamaño. A proba inicial proposta é de 2 pasos, contexto 512, microbatch 1 e checkpointing, pero só se executará despois de validar o backend e a memoria. A produción segue desactivada.
