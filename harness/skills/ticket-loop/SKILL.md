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

0. `CLI hallazgos-pendientes`. Si hay hallazgos pendientes de fases anteriores,
   muéstralos antes de seguir y deja claro que **no bloquean**: el ticket se abre
   igual y el humano los resuelve cuando pueda.
1. Pide el requerimiento (pegado o en `.md`) y guárdalo en `.harness/tickets/<id>/ticket.md`.
2. Pregunta **una sola vez**: número de ticket ISR, nombre del desarrollador y fecha
   (`DD-MM-YYYY`). No los inventes ni los deduzcas del sistema.
3. `CLI open-ticket --ticket-id ISR-<nro> --nroticket <nro> --desarrollador "<NOMBRE>" --fecha <DD-MM-YYYY> --perfil <perfil>`
4. Invoca la skill `task-planner` para producir `plan.md` y `plan.json`. Si existe
   `.claude/biblioteca/INDEX.md`, pásaselo: una lección de la biblioteca es
   hipótesis, y si el plan la usa, la ancla como `por_confirmar`. Si el perfil
   tiene **más de un agente** en `.claude/agents/` (p. ej. uno de backend y otro de
   frontend), cada fase lleva `agente_ejecutor` con el nombre del que la ejecuta, y
   una fase no mezcla stacks: si toca los dos, se parte en dos fases con `depende_de`.
5. `CLI validate --contrato plan --archivo .harness/tickets/<id>/plan.json`
   Si falla, corrige el plan. **No abras ninguna fase con un plan inválido.**

## El ciclo de una fase

1. **Abrir:** `CLI open-fase --fase fase_N`. Si una dependencia no está aprobada, el
   CLI lo rechaza — respeta ese orden, no lo saltes. Si la fase estaba `pausada`, `open-fase` la reanuda.
2. **Ejecutar:** delega el trabajo al subagente indicado en el campo
   **`agente_ejecutor`** de la fase (`open-fase` lo imprime en la línea `Ejecutor:`).
   Si la fase no lo trae, al **subagente ejecutor del perfil** (para ReviewSystemGFS,
   `agent-rsgfs`). Pásale:
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
   - Exit 1 → hay errores bloqueantes. El CLI ya registró el fallo (origen `check`)
     y sumó el intento: vuelve al paso 2 con el historial actualizado, o, si la fase
     quedó `escalado`, ve a "Cuando una fase escala". **No invoques al escéptico**: es
     más caro y estos fallos son hechos, no opiniones.
   - Exit 0 → la fase pasa a `en_verificacion`. Lee los `warning` de `checks.json` y pásaselos al escéptico.
5. **Escéptico:** `CLI` no lo invoca; lo invocas tú como **subagente `skeptic`, con
   contexto aislado**. Dale el diff, el `criterio_exito`, los `anclajes`,
   `checks.json` y el `historial_fallos`. **No le pases tu conversación con el
   ejecutor** — un verificador que leyó el razonamiento ya está contaminado.
   Guarda su JSON y córrelo: `CLI record-veredicto --archivo <ruta>`.
   Si rechazó, el CLI ya incrementó el intento: vuelve al paso 2.

   Lo que se escriba en `.claude/biblioteca/` mientras la fase está abierta (por
   ejemplo, un hallazgo resuelto a mitad de fase) aparece en el diff que ven
   `run-checks` y el escéptico, pero **no es parte del cambio de la fase**: díselo
   al escéptico para que no lo juzgue como tal.
6. **Guion de prueba:** si el escéptico aprobó y la fase requiere prueba manual,
   deriva del `criterio_exito` una lista de pasos concretos —clic por clic, con qué
   debería verse en cada uno— y córrela:
   `CLI generar-prueba --pasos-json <archivo>`.
   Los pasos deben ser ejecutables por alguien que no leyó el código.
   Si la fase **no** requiere prueba manual y el escéptico aprobó, la fase ya quedó
   `aprobada`: ejecuta "Al cerrar una fase".
7. **Detente.** Muestra el contenido de `prueba_manual.md` y espera. El humano
   responde `/fase-ok` o `/fase-fallo`. **No aproximes, no supongas, no cierres la
   fase por tu cuenta:** aunque el perfil tenga build y pruebas automáticas (que
   corren como checks estructurales), la prueba en el navegador es la única
   verificación funcional de punta a punta.

## Pausar una fase

- Solo el humano pausa, con `/fase-pausa`. Nunca corras `pausar-fase` por iniciativa
  propia.
- Si a mitad de fase el humano pregunta otra cosa o pide parar, respóndele,
  recuérdale `/fase-pausa` y termina el turno sin retomar la fase.
- Se retoma con `/fase fase_N`: `open-fase` reanuda en el mismo intento.
- Mientras la fase activa corre, `open-fase` de otra fase y `open-ticket` se
  rechazan.

## Cuando una fase escala

Al agotarse los reintentos, la fase queda en `escalado`. No arranques otro intento
ni pases a la fase siguiente. Reporta al humano, en este orden:

1. Qué se intentó en cada intento y qué falló, tomado del `historial_fallos`.
2. Qué patrón se repite entre los fallos.
3. Si el patrón es un fallo del escéptico que ya apareció más de una vez,
   propón la corrección según la escalera *dónde va cada corrección*: la pieza más
   barata que lo habría atrapado. Ese es el ciclo de mejora del harness: convertir
   juicio caro en verificación barata.

Haya o no patrón, después del reporte ejecuta siempre "Al cerrar una fase": la
fase escalada es la que más enseña. Esto vale también cuando la fase escaló por un
`/fase-fallo`.

## Al cerrar una fase

Aplica a toda fase que quede `aprobada` (tras `/fase-ok` o directamente tras
`record-veredicto`) o `escalado`. Corre de inmediato, antes de cualquier
`CLI open-fase` de la fase siguiente: sin más argumentos, `record-hallazgos`
registra sobre la fase activa. Si la fase siguiente ya se abrió, registra la
propuesta igual, indicando la fase cerrada:
`CLI record-hallazgos --archivo <ruta> --ticket <id> --fase <fase>`.

1. Invoca al **subagente `reflector`, con contexto aislado**. Dale: la fase de
   `plan.json`; el `historial_fallos` completo; el `checks.json` y el
   `veredicto.json` de **cada** `intento_N`; el resultado de la prueba manual; y
   `.claude/biblioteca/INDEX.md` si existe. **No le pases tu conversación con el
   ejecutor**: igual que el escéptico, un reflector que leyó el razonamiento ya
   está contaminado.
2. Guarda su JSON en `.harness/tickets/<id>/<fase>/propuesta_hallazgos.json` y
   córrelo: `CLI record-hallazgos --archivo <ruta>`. Una propuesta vacía
   (`"hallazgos": []`) también se registra. Si el CLI rechaza la propuesta,
   devuélvele el error al reflector **una vez** para que la corrija y vuelve a
   registrarla; si falla de nuevo, avisa al humano con el error tal cual y termina
   el turno: no escribas `hallazgos.json` a mano.
3. Muestra el contenido de `hallazgos.md` y explica al humano sus opciones, con la
   referencia completa que trae cada hallazgo (`TICKET/fase_N/hN`):
   `/hallazgo-ok <ref>`, `/hallazgo-editar <ref> "<lección>"`,
   `/hallazgo-no <ref> "<motivo>"` y `/hallazgo "<lección>"` para proponer una
   propia. Los hallazgos pendientes no bloquean la fase ni el ticket. Tras aprobar,
   sugiere versionar `.claude/biblioteca/` con el proyecto.
4. **El turno termina ahí.** No resuelvas hallazgos por tu cuenta.
