---
name: ticket-loop
description: >-
  Conduce el ciclo de una fase del harness: ejecutar, verificar con scripts,
  verificar con el escéptico, generar el guion de prueba manual y detenerse en
  el gate humano. Usar cuando se trabaje un ticket bajo el harness — al abrir
  un ticket, al arrancar una fase, o al retomar tras un fallo.
---

# Ciclo de fase

`CLI` = `python "$HOME/.claude/hooks/cli.py"`. **Todo cambio de estado pasa por el
CLI.** No edites `fase_state.json`, `checks.json` ni `veredicto.json` a mano: si te
sientes tentado a hacerlo, es que falta un subcomando.

## Al abrir un ticket

1. Pide el requerimiento (pegado o en `.md`) y guárdalo en `.harness/tickets/<id>/ticket.md`.
2. Pregunta **una sola vez**: número de ticket ISR, nombre del desarrollador y fecha
   (`DD-MM-YYYY`). No los inventes ni los deduzcas del sistema.
3. `CLI open-ticket --ticket-id ISR-<nro> --nroticket <nro> --desarrollador "<NOMBRE>" --fecha <DD-MM-YYYY> --perfil <perfil>`
4. Invoca la skill `task-planner` para producir `plan.md` y `plan.json`.
5. `CLI validate --contrato plan --archivo .harness/tickets/<id>/plan.json`
   Si falla, corrige el plan. **No abras ninguna fase con un plan inválido.**

## El ciclo de una fase

1. **Abrir:** `CLI open-fase --fase fase_N`. Si una dependencia no está aprobada, el
   CLI lo rechaza — respeta ese orden, no lo saltes.
2. **Ejecutar:** delega el trabajo al **subagente ejecutor del perfil** (para
   ReviewSystemGFS, `agent-rsgfs`). Pásale:
   - la fase completa de `plan.json` (pasos, criterio de éxito, anclajes);
   - `ticket_context.json`, para que los comentarios de auditoría lleven los valores
     correctos;
   - el **`historial_fallos` completo** si `intento_actual > 1` — todos los fallos, no
     solo el último: corregir el más reciente reintroduciendo uno viejo es una regresión;
   - las `herramientas_permitidas` de la fase.

   Mientras trabaja, el hook `PostToolUse` puede devolverle violaciones de reglas.
   **Eso es autocorrección, no un reintento:** que las corrija y siga.
3. **Documentar:** el ejecutor escribe `intento_N/resultado.md` con lo que hizo y la
   evidencia (rutas, líneas, salidas de comando). Esto ya no se pide a mano.
4. **Checks:** `CLI run-checks`.
   - Exit 1 → hay errores bloqueantes. Registra el fallo y vuelve al paso 2 con el
     historial actualizado. **No invoques al escéptico**: es más caro y estos fallos
     son hechos, no opiniones.
   - Exit 0 → sigue. Lee los `warning` de `checks.json` y pásaselos al escéptico.
5. **Escéptico:** `CLI` no lo invoca; lo invocas tú como **subagente `skeptic`, con
   contexto aislado**. Dale el diff, el `criterio_exito`, los `anclajes`,
   `checks.json` y el `historial_fallos`. **No le pases tu conversación con el
   ejecutor** — un verificador que leyó el razonamiento ya está contaminado.
   Guarda su JSON y córrelo: `CLI record-veredicto --archivo <ruta>`.
   Si rechazó, el CLI ya incrementó el intento: vuelve al paso 2.
6. **Guion de prueba:** si el escéptico aprobó y la fase requiere prueba manual,
   deriva del `criterio_exito` una lista de pasos concretos —clic por clic, con qué
   debería verse en cada uno— y córrela:
   `CLI generar-prueba --pasos-json <archivo>`.
   Los pasos deben ser ejecutables por alguien que no leyó el código.
7. **Detente.** Muestra el contenido de `prueba_manual.md` y espera. El humano
   responde `/fase-ok` o `/fase-fallo`. **No aproximes, no supongas, no cierres la
   fase por tu cuenta:** no hay build ni tests en este proyecto, así que su
   navegador es la única prueba funcional que existe.

## Cuando una fase escala

Al agotarse los reintentos, la fase queda en `escalado`. No arranques otro intento
ni pases a la fase siguiente. Reporta al humano, en este orden:

1. Qué se intentó en cada intento y qué falló, tomado del `historial_fallos`.
2. Qué patrón se repite entre los fallos.
3. Si el patrón es un fallo del escéptico que ya apareció más de una vez,
   **propón el check determinista que lo habría atrapado.** Ese es el ciclo de
   mejora del harness: convertir juicio caro en verificación barata.
