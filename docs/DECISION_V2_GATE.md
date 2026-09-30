# HYDRA Decision v2: compuerta de cobertura

La cabeza Kev validada solo cubre parte de las etiquetas del corpus v3. HYDRA
ahora incorpora una compuerta determinista previa al observador:

- `review`: producción, pagos irreversibles, acciones médicas y cambios de permisos.
- `security`: phishing, credenciales, exfiltración y comandos peligrosos.
- `privacy`: datos personales, anonimización y borrado de datos.
- `abstain`: entradas vacías, referencias sin contexto y peticiones ambiguas.

La compuerta devuelve una observación tipada de `hydra-policy-v2`, con probabilidad
1, y no llama a Kev. Estas etiquetas son resultados de política HYDRA, no una
predicción del checkpoint. `review` exige revisión posterior y `abstain` pide
contexto; ninguno concede permisos.

Las solicitudes restantes siguen pasando por Kev con opciones canónicas. Si Kev
falla, las reglas deterministas del router siguen siendo la decisión efectiva.
Para sustituir la compuerta por una cabeza Kev v2 se necesitan datos verificados,
test independiente y los umbrales de [PLAN_MEJORA_KEV.md](PLAN_MEJORA_KEV.md).

Validación: 19 pruebas del gate, observador y canonicalización; Ruff correcto.
