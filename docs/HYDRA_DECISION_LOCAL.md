# HYDRA-Decision: integración local en preparación

Copyright (c) 2026 Luis Manuel Cousido Hermida. Todos los derechos reservados.

## Cambios implementados

`hydra.providers.decision` define una interfaz independiente de la generación de texto y un cliente local compatible con `/v1/systemone`. Valida Choice, Noul y Score: identificadores, probabilidades finitas, suma de distribuciones, opción seleccionada y coherencia de la puntuación. Rechaza endpoints remotos, proxies de entorno y redirecciones. Un error o timeout no se convierte en una decisión aprobada. El cliente todavía no está conectado al router del motor: no cambia sus permisos ni su selección actual.

El alias devuelto se contrasta con el solicitado; no constituye una prueba criptográfica de identidad del checkpoint. La revisión del código y del modelo se fija en el lanzador de prueba. Antes de integrar producción falta contrastar la información de `/v1/models`, los hashes de los archivos cargados y la política de admisión del proveedor.

Corregidos tres problemas de preparación de datos:

- El exportador de especialistas/enrutamiento exige `verified is True` aunque se reduzca la confianza mínima.
- El crítico omite respuestas no verificadas; ya no las etiqueta automáticamente como fallos. Por ahora solo exporta positivos verificados. Los negativos requieren incorporar resultados explícitos de verificadores a las trazas.
- El clasificador no sustituye la validación ausente por la precisión de entrenamiento: informa `validation_status=not_evaluated` y no publica `valid_accuracy`.

Esto no completa la fase de admisión: todavía falta imponer permisos de entrenamiento, procedencia por ejemplo, verificador independiente y separación de datasets en todos los exportadores.

## Entorno Kev

- Código aislado: `runtime/kev`, commit `0c142becde423a0c68ec857f7831dac0315588a1`.
- Python aislado: `runtime/kev-env`; no reutiliza `.venv` del generador.
- Checkpoint de ensayo: `jaredpalmer/kev-0.8b@9a45d25eb2ab761841196625383fa1dff0e56c1e`.
- Caché de pesos: `runtime/kev-cache`.
- Arranque: `scripts/start_kev_local.ps1`, limitado a `127.0.0.1:8009`.

```powershell
.\runtime\kev-env\Scripts\python.exe -m pip install --index-url https://pypi.org/simple './runtime/kev[serve]'
.\runtime\kev-env\Scripts\python.exe -m pip check
.\scripts\start_kev_local.ps1
```

La instalación inicial no es un lock transitivo: guardar `pip freeze` tras la instalación para reproducir ese entorno. El primer arranque descarga la base y el adaptador; arrancar el proceso no demuestra que el servidor esté listo. La prueba usa FP32 y el dispositivo disponible en ese entorno. No atribuirle rendimiento CUDA si el paquete instalado funciona en CPU.

El checkpoint 0.8B es solo un ensayo de clasificación documental no crítica: su ficha desaconseja el enrutamiento de herramientas. Para aceptar un backend son necesarias pruebas reales de español, calibración, abstención, memoria y estabilidad. Las pruebas unitarias actuales utilizan transporte HTTP simulado, no certifican inferencia Kev.
