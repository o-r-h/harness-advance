## Al cerrar una fase

Aplica a toda fase que quede `aprobada` (tras `/fase-ok` o directamente tras
`record-veredicto`) o `escalado`. Corre de inmediato, antes de cualquier
`CLI open-fase` de la fase siguiente: sin más argumentos, `record-hallazgos`
registra sobre la fase activa. Si la fase siguiente ya se abrió, registra la
propuesta igual, indicando la fase cerrada:
`CLI record-hallazgos --archivo <ruta> --ticket <id> --fase <fase>`.

1. Invoca al **subagente `reflector`, con contexto aislado**. Dale: la fase de
   `plan.json`; el `historial_fallos` completo; el `checks.json` y el
   `veredicto.json` de **cada** `intento_N`; el resultado de la prueba manual y, si
   existe, el `prueba_asistida.md` de cada intento; y
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
