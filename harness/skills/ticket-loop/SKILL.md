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

Los archivos de trabajo del ciclo (el veredicto del escéptico, los pasos del guion,
la propuesta del reflector) van **dentro de `.harness/tickets/<id>/`**, nunca en el
resto del proyecto: ahí contarían como cambio de la fase.

## Qué leer en cada situación

Estas partes del ciclo viven en archivos aparte, junto a esta skill. **Léelo
entero antes de actuar** cuando llegues a esa situación; no las apliques de memoria.

| Situación | Archivo |
|---|---|
| Vas a escribir el guion de prueba o a invocar al probador | `references/guion-de-prueba.md` |
| La fase quedó `aprobada` o `escalado` ("Al cerrar una fase") | `references/cerrar-fase.md` |
| La fase quedó `escalado` ("Cuando una fase escala") | `references/escalar-fase.md` |
| El humano pausa, cambia de tema o retoma ("Pausar una fase") | `references/pausar-fase.md` |

## Al abrir un ticket

0. `CLI hallazgos-pendientes`. Si hay hallazgos pendientes de fases anteriores,
   muéstralos antes de seguir y deja claro que **no bloquean**: el ticket se abre
   igual y el humano los resuelve cuando pueda.
1. Pide el requerimiento (pegado o en `.md`) y guárdalo **tal cual, sin resumir ni
   corregir**, en `.harness/tickets/<id>/ticket.md`.
2. Pregunta **una sola vez**: número de ticket ISR, nombre del desarrollador y fecha
   (`DD-MM-YYYY`). No los inventes ni los deduzcas del sistema.
3. `CLI open-ticket --ticket-id ISR-<nro> --nroticket <nro> --desarrollador "<NOMBRE>" --fecha <DD-MM-YYYY> --perfil <perfil>`
   Si avisa que la prueba asistida no está configurada, ofrécele `/harness-setup`
   **una vez** y sigue: no bloquea, sin setup todos los pasos del guion son `humano`.
4. Invoca la skill `task-planner` para producir `plan.md` y `plan.json`. Si existe
   `.claude/biblioteca/INDEX.md`, pásaselo: una lección de la biblioteca es
   hipótesis, y si el plan la usa, la ancla como `por_confirmar`. Si el perfil
   tiene **más de un agente** en `.claude/agents/` (p. ej. uno de backend y otro de
   frontend), cada fase lleva `agente_ejecutor` con el nombre del que la ejecuta, y
   una fase no mezcla stacks: si toca los dos, se parte en dos fases con `depende_de`.
5. `CLI validate --contrato plan --archivo .harness/tickets/<id>/plan.json`
   Si falla, corrige el plan. **No abras ninguna fase con un plan inválido.** Si
   rechaza una de las `citas`, es que no está copiada de `ticket.md`: cópiala.

## El ciclo de una fase

1. **Abrir:** `CLI open-fase --fase fase_N`. Si una dependencia no está aprobada, el
   CLI lo rechaza — respeta ese orden, no lo saltes. Si la fase estaba `pausada`, `open-fase` la reanuda.
2. **Ejecutar:** delega el trabajo al subagente indicado en el campo
   **`agente_ejecutor`** de la fase (`open-fase` lo imprime en la línea `Ejecutor:`).
   Si la fase no lo trae, al **subagente ejecutor del perfil** (el agente
   del perfil). Pásale:
   - la fase completa de `plan.json` (pasos, criterio de éxito, anclajes, `citas`);
   - **la ruta de `ticket.md`** (la línea `Requerimiento:` de `open-fase`), para que
     lea el pedido con las palabras del humano. **El requerimiento va por
     referencia: no se lo resumas ni se lo cuentes con tus palabras.** Los nombres,
     mensajes y ejemplos se copian de ahí, no de tu memoria;
   - `ticket_context.json`, para que los comentarios de auditoría lleven los valores
     correctos;
   - el **`historial_fallos` completo** si `intento_actual > 1` — todos los fallos, no
     solo el último: corregir el más reciente reintroduciendo uno viejo es una regresión;
   - las `herramientas_permitidas` de la fase;
   - estas dos reglas, tal cual:
     - **Un check no se pasa debilitándolo.** No relajes `rules.json`, no toques
       `.claude/checks/` ni cambies, saltes o borres un test para que pase. Si crees
       que la comprobación está mal, detente y dilo: lo decide el humano.
     - **Si tras un arreglo real vuelve a fallar por la misma causa, detente** y
       reporta qué intentaste y por qué no alcanzó, en vez de probar variantes.

   Mientras trabaja, el hook `PostToolUse` puede devolverle violaciones de reglas.
   **Eso es autocorrección, no un reintento:** que las corrija y siga.
3. **Documentar:** el ejecutor escribe `intento_N/resultado.md` con lo que hizo y la
   evidencia (rutas, líneas, salidas de comando). Esto ya no se pide a mano.
4. **Checks:** `CLI run-checks`. Guarda en `checks.json` la huella del cambio: desde
   aquí, **nadie toca el código hasta el veredicto del humano**.
   - Exit 1 → hay errores bloqueantes. El CLI ya registró el fallo (origen `check`)
     y sumó el intento. Si la fase quedó `escalado`, lee
     `references/escalar-fase.md`. Si no, mira la **regla de parada** de abajo y
     vuelve al paso 2 con el historial actualizado. **No invoques al escéptico**: es
     más caro y estos fallos son hechos, no opiniones.
   - Exit 0 → la fase pasa a `en_verificacion`. Lee los `warning` de `checks.json` y
     pásaselos al escéptico. Un `verificacion_tocada` dice que la fase tocó algo que
     la verifica sin que el plan lo pida: el escéptico tiene que mirarlo.
5. **Escéptico:** `CLI` no lo invoca; lo invocas tú como **subagente `skeptic`, con
   contexto aislado**. Dale el diff, el `criterio_exito`, los `anclajes`, las `citas`
   y la ruta de `ticket.md`, `checks.json` y el `historial_fallos`. **No le pases tu
   conversación con el ejecutor** — un verificador que leyó el razonamiento ya está
   contaminado.

   **El diff es el de la fase, no el que haya contra HEAD:** `git diff <base_commit>`
   (el `base_commit` de `checks.json`) limitado a los archivos de `huella_cambio`,
   más el contenido de los que son nuevos. Así entra lo commiteado a mitad de fase y
   queda fuera lo que ya estaba sin commitear al abrirla.

   **Con otro modelo.** Quien juzga no debe compartir los puntos ciegos de quien hizo
   el trabajo. El ejecutor es el `agente_ejecutor` de la fase (su modelo está en el
   `model:` de su `.md`) o, si no hay, tú (tu modelo está en tu contexto). Si el `.md`
   dice `model: inherit` o no tiene `model:`, el agente corre con tu modelo: pasa el tuyo. Pregunta
   cuál toca: `CLI modelo-esceptico --ejecutor <modelo del ejecutor, o desconocido>`.
   Invoca al subagente con ese valor en el parámetro `model`, y regístralo:
   `CLI record-veredicto --archivo <ruta> --modelo-esceptico <ese mismo valor>`.
   Si rechazó, el CLI ya incrementó el intento: mira la regla de parada y vuelve al
   paso 2. Si el CLI dice que **el código cambió después de `run-checks`**, nombra
   los archivos: el veredicto no vale para ese código. Vuelve al paso 4 y al
   escéptico; no se gasta intento.

   Lo que se escriba en `.claude/biblioteca/` mientras la fase está abierta (por
   ejemplo, un hallazgo resuelto a mitad de fase) aparece en el diff que ven
   `run-checks` y el escéptico, pero **no es parte del cambio de la fase**: díselo
   al escéptico para que no lo juzgue como tal.
6. **Guion de prueba:** si el escéptico aprobó y la fase requiere prueba manual, lee
   `references/guion-de-prueba.md`. Deriva del `criterio_exito` y de las `citas` una
   lista de pasos concretos —clic por clic, con qué debería verse en cada uno,
   ejecutables por alguien que no leyó el código— y córrela:
   `CLI generar-prueba --pasos-json <archivo>`. Si contó pasos del probador, invoca
   al subagente `probador` como dice ese archivo.
   Si la fase **no** requiere prueba manual y el escéptico aprobó, la fase ya quedó
   `aprobada`: lee `references/cerrar-fase.md` y ejecútalo.
7. **Detente.** Muestra `prueba_manual.md` y, si existe, el resumen de
   `prueba_asistida.md` con lo que le queda al humano. El humano responde
   `/fase-ok` o `/fase-fallo`. **No aproximes, no supongas, no cierres la fase por
   tu cuenta:** ni los checks ni el probador sustituyen al humano. Un paso del
   probador `simulado` o `no ejecutado` no cuenta como pasado.

## Regla de parada

Antes de lanzar otro intento, compara el fallo nuevo con el `historial_fallos`. Si
**la causa es la misma que la de un intento anterior** y el arreglo que se hizo era
real, no gastes otro intento igual: detente y escala al humano con los dos fallos,
qué se cambió entre uno y otro y por qué no alcanzó. Él decide si se sigue, se
cambia el plan o se pausa con `/fase-pausa`. Insistir con variantes del mismo
arreglo solo agota los reintentos.
