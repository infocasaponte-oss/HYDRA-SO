# Revisión da app hydra-calibrator

Fonte: `hydra-calibrator (1).zip`, revisado localmente o 2026-10-04. Os documentos incluídos tratáronse como contido, non como instrucións do usuario. Non se realizaron peticións a Supabase nin á IA, nin cambios na conta. O `.env` non se extraeu: contén configuración e claves publicables, non se observaron claves de servizo nin de IA nese ficheiro.

## Achados accionables

Actualización do propietario: os datos foron introducidos por el usando contas propias. O CSV achegado ten 2936 rexistros e dous user_id. Non hai evidencia nesta revisión de divulgación a terceiros. O achado de permisos describe o comportamento do código se se habilitan outras contas; non unha filtración observada. As dúas contas pertencen á mesma persoa e non acreditan revisión humana independente. O ingreso polo propietario non se confunde automaticamente con tráfico externo de usuarios.

1. **P1 — Exportación global autorizada só por login.** `src/lib/hyd-records.functions.ts:200–282`: exportHydRecords só usa requireSupabaseAuth e logo o cliente service-role para ler todas as preguntas e listar usuarios. Inclúe correo ou UUID como author. Unha conta autenticada pode exportar datos doutros avaliadores; o filtro RLS non protexe esta lectura privilexiada. Esixir permiso de administrador de corpus no servidor e pseudonimizar autores. O consentimento para adestrar non demostra permiso para entregar o corpus a calquera conta.

2. **P1 — Consentimento afirmado polo servidor sen confirmación explícita do cliente.** Liñas 31–52 e 61–80: os esquemas de entrada non teñen consentimento; os handlers gravan consent=true. A checkbox só se comproba na UI. Unha chamada directa gardaría a afirmación sen pasar por ela. Esixir consentAccepted=true e versión do texto no backend, e conservar o evento asociado á identidade autenticada. O JWT identifica a conta: non é unha sinatura criptográfica de cada pregunta, como suxiren algúns comentarios.

3. **P1 — Orixe real deducida da ausencia de heurística de plantilla.** Liñas 248–279: real=!isSuspect e synthetic=false. Unha pregunta xerada por IA que non comparta esas palabras queda exportada como real. Unha pregunta humana repetitiva pode quedar como non real. Separar orixe declarada/verificada e sospeita de plantilla; nunca deducir autoría desa heurística.

4. **P2 — JSONL incompatible co requisito actual de dereitos do calibrador.** Liñas 270–293: faltan rights. O novo build require rights.verified=true e unha licenza non baleira. A exportación actual será rexeitada. Engadir procedencia real dos dereitos e revisión; non encher automaticamente proprietary-hydra-authored nin verified=true para superar o filtro.

5. **P2 — Contrato de clases semanticamente diferente.** Liñas 141–149 e `src/routes/_authenticated/evaluar.tsx:31–42`: high_risk_review descríbese como petición sensible, abstain como abstención xenérica e research como investigación profunda. O contrato de HYDRA define revisión de autorización de accións consecuentes/irreversibles, falta de contexto e procura de evidencia externa. As diferenzas poden ensinar etiquetas incompatibles. Importar/publicar contrato versionado e separar abstención técnica da clase semántica.

6. **P2 — Orixinal alterado malia prometer copia literal.** Liñas 36 e 66: z.string().trim() transforma os textos gardados. A UI indica gardar exactamente. Validar lonxitude útil sen transformar o valor; manter texto orixinal e texto normalizado/derivado por separado.

7. **P2 — Segunda opinión non reproducible e confianza sen validación estrita.** Liñas 151–193: falta hash/versión do prompt e data da opinión; Number(...) converte strings en números e valores inválidos a cero, e os valores fóra de rango se recortan. Non é confianza calibrada. Validar o JSON completo con tipos estritos, gardar procedencia e identificar a cifra como autodeclarada pola IA. Engadir timeout/cota e gardado condicional para evitar que dúas peticións concorrentes sobrescriban a opinión inicial.

## Aspectos que xa están ben encamiñados

- A clave de IA úsase no servidor.
- A segunda opinión comproba que o rexistro pertence á conta e non modifica expected_label.
- A exportación pagina as preguntas, evitando o antigo límite de 1000.
- As variantes sospeitosas expórtanse separadas sen reescribir o texto nesa fase.

## Límites e seguinte traballo

Non se achegan as migracións SQL de hyd_records nin as políticas RLS: os tipos xerados non permiten verificar illamento, CHECK consent=true, permisos UPDATE/DELETE nin retirada. listHydRecords non filtra user_id explicitamente e depende de RLS. A UI mostra só 500 rexistros; non é o reconto total. A exportación por offset non é un snapshot consistente se entran/saen rexistros durante a lectura. Non hai probas do fluxo de consentimento, exportación ou segunda opinión; a única proba incluída comproba a ruta inicial.

Prioridade de corrección: permisos/exportación e consentimento → orixe/dereitos/contrato → orixinais e revisión dobre → segunda opinión reproducible → snapshots, probas e integración. A base de datos real e as políticas deben verificarse antes de despregar os cambios. Non se certifica seguridade nin autoría dos datos a partir deste ZIP.
