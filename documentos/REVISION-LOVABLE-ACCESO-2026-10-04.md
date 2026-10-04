# Revisión directa de Lovable — 2026-10-04

Observación 2026-10-04T16:43:21.329088+02:00. Proxecto Hyd Calibration Boost, aa8d2d14-948e-4449-adcc-67f047985344. Sesión accesible no navegador; non se pediron nin exportaron credenciais.

## Comprobado na interface

Panel: 2936 rexistros, 2598 textos distintos, 521 apartados por heurística de molde, 2077 admitidos polo filtro actual, 0 conflitos. Non se certifica tráfico real nin autoría mediante eses filtros. O informe mostrado segue sendo hyd-app-v1, 313 preguntas, accuracy 71,2%, macro-F1 0,692, ECE 0,057, cobertura 30,7% e precisión selectiva 96,9%. Ese informe non foi substituído.

A táboa visible hyd_records conserva o esquema antigo: id, user_id, question, expected_label, hyd_prediction, prediction_correct, ai_label, ai_intent, ai_confidence, ai_model, consent, consent_text, notes, created_at. Non apareceron consent_version, source_kind, rights_verified nin unha táboa de variantes nesta vista. Isto confirma que a migración preparada non está visible como aplicada.

RLS está activada e a interface amosa catro políticas para authenticated. SELECT: USING auth.uid()=user_id. INSERT: WITH CHECK auth.uid()=user_id AND consent=true. UPDATE: USING auth.uid()=user_id. DELETE: política de propietario listada, expresión aínda non expandida nesta revisión. Non se executaron probas de acceso entre contas nin se modificaron políticas.

No editor, src/lib/hyd-records.functions.ts segue validando question con z.string().trim() e gravando consent:true sen consentimento explícito na petición. O comentario de texto verbatim non coincide co comportamento. O parche local resolve ambos puntos; aínda non se afirma que estea integrado na aplicación remota.

## Acción realizada

Enviouse unha petición á cola activa de Lovable para revisar e adaptar integrations/evaluator-app/offline-improvements.patch da PR #1 de Hyd. Require primeiro exportación privada completa, con reconto e SHA256, conservación dos rexistros, migración aditiva revisada, ámbito autorizado e probas. Mantén aparte corpus filtrado e arquivo portable. Non pide publicar, activar modelos, borrar historia nin completar automaticamente a procedencia descoñecida.

Lovable segue executando a petición previa do propietario sobre E2. A petición nova aparece como unha mensaxe na cola activa, non como traballo completado. Non se confirmou ningún adestramento E2, resultado novo, copia descargada nin migración aplicada. A afirmación de teito do ranker non está demostrada; o candidato local 1024/256 obtivo 241/313 fronte a 223/313, nun test diagnóstico xa usado.

Evidencia da cola: .codex-artifacts/lovable-integration-queued-20261004.jpg. Non inclúe contrasinais, claves ou filas de corpus. O código revisado e a exportación real deben comprobarse cando remate a execución remota.

## Actualización tras a execución remota (16:54)

Lovable terminou a adaptación parcial e informou de 8 tests e build correctos. Preparou arquivos privados visibles en Files: hyd_records-full-2026-10-04.json (2 MB), CSV, SHA256SUMS.txt e hyd-evaluator-app-src.zip (263 kB, 122 ficheiros segundo Lovable). Non se recibiu unha descarga verificable mediante o navegador tras dous intentos; reconto e hashes do backup seguen declarados por Lovable, non comprobados localmente. Non publicar estes arquivos con IDs de contas.

A migración foi rexeitada pola configuración Database migrations=Never allow; non se cambiou ese permiso. Procedencia persistida, correccións humanas e provedor substituíble seguen pendentes. OAuth real e exportación autenticada non probados. Os cambios de app aínda non están confirmados como subidos a GitHub.

Lovable concedera automaticamente acceso administrativo ás dúas contas. Solicitouse retirar esa ampliación inmediatamente; informou da retirada e do rexeitamento server-side do ámbito global. Mantéñense os totais agregados globais que xa existían. A retirada aínda require comprobación do código descargado.

Na vista previa comprobouse que o panel di filtro técnico con procedencia pendente e comparativa diagnóstica. E2 identifícase como encoder externo MiniLM conxelado máis cabeza loxística; SHADOW_ONLY. O GitHub origin/main 694860d contén o informe E2, a cabeza e as particións. Verificouse coincidencia SHA256 do test co informe e a matriz: 267 acertos / 313 = 85,3035%. Os pares texto/etiqueta son os mesmos do test local anterior. Non se reproduciu a inferencia completa. Non é un modelo HYDRA 4B desde cero nin evidencia independente para produción. Faltan revisión fixada do encoder, reprodución, adapter de inferencia e selección/calibración máis estrita (C, temperatura e limiar usan a mesma calibración).

Evidencia: .codex-artifacts/lovable-mejoras-verificadas-20261004.jpg. Proxecto mantido aberto para continuar a comprobación.
