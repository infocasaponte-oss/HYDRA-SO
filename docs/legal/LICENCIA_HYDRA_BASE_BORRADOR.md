<!-- Copyright (c) 2026 Luis Manuel Cousido Hermida. All rights reserved. -->
# Licencia de los pesos HYDRA Base — BORRADOR

> **Borrador técnico, no asesoramiento jurídico.** Debe revisarlo un abogado especializado en
> propiedad intelectual antes de usarlo. Complementa el `LICENSE` del repositorio, que ya
> declara «Todos los derechos reservados» sobre el software y los modelos.

## 1. Objeto

«HYDRA Base» designa los parámetros (pesos), el tokenizador, la configuración, los checkpoints
intermedios, los manifiestos de entrenamiento y cualquier versión cuantizada, convertida o
ajustada de los modelos base entrenados desde cero por Luis Manuel Cousido Hermida (el
«Titular»), en lo sucesivo, el «Modelo».

## 2. Titularidad

El Modelo es propiedad exclusiva del Titular. Se protege como software, base de datos y secreto
empresarial (Ley 1/2019 de Secretos Empresariales) y mediante este contrato de licencia. Que
los pesos se hayan obtenido por entrenamiento no transfiere ningún derecho a los titulares de
los datos públicos o permisivos utilizados; sus avisos de atribución se conservan en el aviso
de datos de terceros que acompaña a cada versión.

## 3. No se concede licencia por defecto

Salvo un acuerdo escrito y firmado por el Titular, no se concede ningún derecho sobre el Modelo.
Cuando exista acuerdo, solo cubrirá el uso expresamente descrito, de forma no exclusiva, no
transferible y revocable.

## 4. Prohibiciones (salvo autorización escrita)

1. Copiar, distribuir, publicar, sublicenciar, vender o poner a disposición de terceros los pesos,
   el tokenizador o los checkpoints, por cualquier medio (incluidos repositorios de modelos y
   redes P2P).
2. Extraer, reconstruir o aproximar los pesos (ingeniería inversa, extracción por consultas o
   *model stealing*), en la medida en que la ley lo permita prohibir.
3. Usar las salidas del Modelo para entrenar, destilar o mejorar otro modelo que compita con él.
4. Eliminar, alterar u ocultar avisos de titularidad, huellas (*fingerprints*), marcas de agua o
   firmas criptográficas del Modelo o de sus artefactos.
5. Presentar el Modelo o sus derivados con un nombre distinto de «HYDRA» o atribuirlo a terceros.
6. Usar el Modelo para fines ilícitos o contrarios a la normativa aplicable (incluido el
   Reglamento (UE) 2024/1689 de Inteligencia Artificial).

## 5. Salidas

Salvo pacto distinto, el usuario autorizado puede usar las salidas que genere en su actividad,
sujeto a la prohibición 4.3 y sin garantía de exactitud. El Titular no reclama la titularidad de
los datos que el usuario aporte.

## 6. Acceso y confidencialidad

El acceso autorizado se presta preferentemente como servicio (API de HYDRA) y no mediante entrega
de pesos. Si se entregan pesos por acuerdo, el receptor debe mantenerlos cifrados, con acceso
restringido y registro de uso, y devolverlos o destruirlos al terminar.

## 7. Terminación, responsabilidad y ley aplicable

Cualquier uso no autorizado termina automáticamente los permisos concedidos. El Modelo se ofrece
«tal cual», sin garantías. Se rige por la ley española, con sometimiento a los juzgados y
tribunales de España, en los mismos términos que el `LICENSE` del repositorio.

## 8. Condición técnica de validez

Esta licencia solo es coherente si **ningún dato o profesor del entrenamiento impone condiciones
a los pesos**. La fábrica lo hace cumplir con `hydra/training/base_data_policy.py`: rechaza
*share-alike*, *copyleft*, no comercial, «sin obras derivadas» y licencias desconocidas; admite
dominio público, CC0, CC BY, MIT, BSD, ISC, Apache-2.0, reutilización del sector público y datos
generados por HYDRA; y solo admite profesores Apache-2.0 o MIT para la destilación. Los
candidatos ajustados sobre Qwen **no** son HYDRA Base: conservan la licencia de su base.
