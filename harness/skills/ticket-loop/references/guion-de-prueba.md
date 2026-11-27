## El guion de prueba y la prueba asistida

### Quién corre cada paso

Cada paso del JSON de `generar-prueba` lleva `paso`, `esperado` y `quien`:

- `agente`, si se puede correr con el navegador automatizado de la sesión y
  consultas de solo lectura. Lleva siempre `esperado`: sin eso el probador no tiene
  contra qué comparar y el CLI lo rechaza. Recargar (F5) sí es `agente`: para la
  página es lo mismo.
- `humano`, con su `motivo`, si exige login, pagar o cobrar, algo que hace el
  navegador y no la página (reabrir una pestaña cerrada, cerrar el navegador y
  volver), comparar contra el mockup, o datos que el agente no puede preparar.

Si la sesión no tiene navegador automatizado, o `.claude/prueba_asistida.json` dice
`"navegador": null`, solo son `agente` los pasos que no lo necesitan: consultas de
solo lectura y llamadas a la API.

### Prueba asistida

Si `generar-prueba` contó pasos del probador, invoca al **subagente `probador`, con
contexto aislado**. Dale la carpeta del intento, el `criterio_exito`, la URL, los
datos y el contenido de `.claude/prueba_asistida.json` (qué navegador, qué base y
qué herramientas tiene prohibidas). **No le pases tu conversación con el ejecutor ni
el veredicto del escéptico.** Deja `prueba_asistida.md` y `evidencia/` en el intento.

- Si reporta `bloqueado: falta login`, pídele al humano que inicie sesión en la
  ventana del navegador automatizado y vuelve a invocarlo. No teclees
  credenciales tú tampoco.
- Si algún paso `falla`, no corrijas ni reintentes: el humano decide si es
  `/fase-fallo`.
