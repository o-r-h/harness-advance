# Pausa de fase y registro automático de hooks — diseño

Paso 3 del orden acordado con Omar el 02-11-2026 (ver `docs/tecnico.md`, "Pendientes
conocidos"). Dos piezas independientes que comparten rama: **M1** pausar una fase y
**M2** que `deploy.ps1` registre los hooks.

Las decisiones marcadas *decisión de Claude* no las tomó Omar: revísalas al leer.

## Por qué

**La fase secuestra la conversación.** Cuando una fase está abierta (`en_ejecucion`,
`en_correccion`, `en_verificacion`), el hook `Stop` bloquea el fin de cada turno y
empuja a Claude de vuelta a la fase. Si Omar le pregunta otra cosa, o quiere cerrar el
día, Claude responde y enseguida retoma el trabajo de la fase por su cuenta en vez de
esperarlo. En palabras de Omar: "si se empieza la fase prácticamente hay que
terminarla". No es un encierro, porque `stop_hook_active` deja cerrar al segundo
intento, pero sí una pelea en cada turno. Además, si el bug está en el propio hook o
en el estado, no hay un interruptor explícito.

**Registrar los hooks es un paso manual que se olvida.** `deploy.ps1` copia el
harness, respalda `settings.json` e imprime un bloque JSON para pegarlo a mano. Un
colega que lo instale sin ese paso tiene un harness sin hooks: nada bloquea y nada
avisa, y no se nota. Además cada deploy pisa `settings.json.bak`, así que el segundo
deploy reemplaza el respaldo bueno por uno ya modificado.

## Objetivos

1. Omar puede pausar una fase abierta y retomarla después sin perder el intento ni
   gastar uno.
2. Una variable de entorno apaga el hook `Stop` por completo, para emergencias.
3. `deploy.ps1` deja los dos hooks del harness registrados en `~/.claude/settings.json`
   sin tocar nada más del archivo, y una segunda corrida no cambia nada.

## No objetivos

- Tickets o fases en paralelo: sigue habiendo un solo `current.json` (backlog, paso 6).
- Pausar un ticket entero o pausar automáticamente por tiempo.
- Registrar hooks en el `settings.json` del proyecto: el harness vive en `~/.claude`
  y sus hooks se registran ahí. En un proyecto sin `rules.json` los hooks ya salen en
  silencio.
- Desinstalar o quitar hooks: el registro nunca borra entradas.
- Testear `deploy.ps1` mismo (PowerShell); se testea el script de Python que llama.

## Anti-objetivos (sería un fracaso aunque funcione)

- Que Claude pause la fase por su cuenta para escapar del gate. Pausar es decisión del
  humano y queda registrada.
- Que la pausa consuma un intento, cuente como fallo o borre `historial_fallos`.
- Que el registro de hooks toque los hooks de otras herramientas (codebase-memory),
  `env`, `model`, plugins, el orden de las claves o los acentos de `settings.json`.
- Que un `settings.json` roto termine sobrescrito o vaciado.

## M1 — Pausar y reanudar una fase

### Estado `pausada`

- `ESTADOS_FASE` (en `lib/contracts.py`) suma `pausada`.
- `fase_state.json` suma un campo opcional `pausas`: una lista de
  `{"desde": <estado>, "fecha": "dd-mm-aaaa", "motivo": <texto>}`, una por cada pausa,
  en orden. Nunca se borra; reanudar no la modifica.
- Contrato: si `estado == "pausada"`, `pausas` es una lista no vacía y el `desde` de la
  última pausa está entre `en_ejecucion`, `en_correccion` y `en_verificacion`. Cada
  elemento de `pausas` lleva `desde`, `fecha` y `motivo` de tipo texto, y `fecha` con
  el formato `dd-mm-aaaa`.
- Pausar no toca `intento_actual` ni `historial_fallos`.
- El contrato se aplica donde ya se aplica el de `fase_state`: `state._guardar` valida
  en cada escritura, y el reporte valida al leer. El hook `Stop` no valida; si no puede
  leer el estado, no bloquea, como hoy.
- En `lib/state.py`, `registrar_fallo` y `aprobar_fase` lanzan `TransicionInvalida` con
  la fase en `pausada`. Es la red de seguridad debajo de los rechazos del CLI.

### Pausar: `cli.py pausar-fase [--motivo "<texto>"]`

- Actúa sobre la fase activa de `current.json`.
- Solo se pausa desde `en_ejecucion`, `en_correccion` o `en_verificacion`. Desde
  cualquier otro estado da un error que nombra el estado. En `esperando_humano` el
  mensaje aclara que esa fase ya no bloquea el turno.
- `--motivo` es opcional; sin él se guarda `"sin motivo"` (*decisión de Claude*: pausar
  para cerrar el día no debería exigir explicación).
- Imprime la fase, el intento y cómo reanudarla (`/fase fase_N`).

### Reanudar: `open-fase` sobre una fase `pausada`

- `cli.py open-fase --fase fase_N` sobre una fase `pausada` la devuelve al estado
  `desde` de su última pausa e imprime que se reanudó en ese estado y en ese intento.
- Así `/fase fase_N`, que ya pasa por `open-fase`, sirve para retomar sin un comando
  nuevo (*decisión de Claude*: un solo camino para "seguir con la fase").
- `open-fase` sobre una fase que no está `pausada` sigue como hoy: idempotente, devuelve
  el estado existente sin cambiarlo.
- Si se intenta abrir otra fase del mismo ticket que depende de la pausada, el error de
  dependencia que ya existe lo cubre: la pausada no está `aprobada`.

### No se deja una fase corriendo sin dueño

Hoy `open-fase` de otra fase, u `open-ticket` de otro ticket, reapunta `current.json`
aunque la fase activa siga corriendo. Esa fase queda huérfana: sigue `en_ejecucion`,
pero `Stop` y `pausar-fase` ya no la ven. Con la pausa hay una salida explícita, así que
(*decisión de Claude*):

- `open-fase` de una fase distinta y `open-ticket` se rechazan si la fase activa de
  `current.json` está en `en_ejecucion`, `en_correccion` o `en_verificacion`. El error
  dice cuál y pide pausarla primero con `/fase-pausa`.
- Con la fase activa en `pausada`, `esperando_humano`, `aprobada` o `escalado`, se
  permite. Una fase pausada queda pausada y se retoma después con `/fase fase_N`.

### Lo que se rechaza mientras la fase está pausada

`run-checks` ya se rechaza fuera de su ciclo. Se suman `record-veredicto` y
`generar-prueba`: con la fase en `pausada` dan un error que dice que primero hay que
reanudarla con `/fase fase_N`. `record-manual` ya exige `esperando_humano`.

### Comando `/fase-pausa ["<motivo>"]`

- Nuevo `harness/commands/fase-pausa.md`. Corre `pausar-fase` con el motivo si lo hay,
  muestra la salida tal cual y termina el turno.
- `argument-hint: "<motivo>"` (opcional).

### Hook `Stop` (`gate_phase.py`)

- `pausada` no bloquea: queda fuera de `BLOQUEANTES`, igual que `esperando_humano`.
- **Interruptor de emergencia:** si la variable de entorno `HARNESS_STOP` vale `off`
  (sin distinguir mayúsculas), el hook sale con 0 sin leer nada. Solo vale para
  sesiones abiertas con la variable puesta (`$env:HARNESS_STOP="off"; claude`); no
  cambia una sesión que ya está corriendo.
- El mensaje de bloqueo suma una línea: si el humano pidió detenerse o cambió de tema,
  hay que ofrecerle `/fase-pausa` y terminar el turno sin retomar la fase.

### Skill `ticket-loop`

- Nueva sección corta "Pausar una fase":
  - Solo el humano pausa, con `/fase-pausa`. Claude nunca corre `pausar-fase` por
    iniciativa propia.
  - Si el humano pregunta otra cosa a mitad de fase, o pide parar, Claude responde, le
    recuerda `/fase-pausa` y termina el turno sin retomar el trabajo de la fase.
  - Para retomar, `/fase fase_N`.
- La línea de "Al abrir un ticket" o del ciclo que hable de retomar menciona que
  `open-fase` también reanuda una fase pausada.

### Reporte (`report.py`)

- `fases.pausas_por_fase`: `{"TICKET/fase_N": <cantidad de pausas>}`, solo las fases
  con al menos una pausa. Se muestra en la sección Fases del texto.
- `intentos_por_fase` ya muestra el estado; una fase pausada aparece como `pausada`.

## M2 — `deploy.ps1` registra los hooks

### `registrar_hooks.py` (raíz del repo)

Script de Python que corre solo al desplegar; no se copia a `~/.claude`. Va en Python
porque el `ConvertTo-Json` de PowerShell 5.1 corta lo anidado y escapa los acentos, y
Python ya es requisito de los hooks.

Uso: `python registrar_hooks.py --settings <ruta settings.json> --hooks-dir <ruta ~/.claude/hooks>`.

Hooks que registra, con la misma forma que hoy imprime `deploy.ps1`:

| Evento | matcher | comando |
|---|---|---|
| `PostToolUse` | `Edit\|Write\|MultiEdit` | `python "<hooks-dir>\check_rules.py"` |
| `Stop` | `""` | `python "<hooks-dir>\gate_phase.py"` |

Comportamiento:

- **Identificación:** una entrada es del harness si el `command` de alguno de sus hooks
  nombra `check_rules.py` (en `PostToolUse`) o `gate_phase.py` (en `Stop`), sea cual
  sea la ruta.
- **Si existe:** se corrige el `command` de nuestro hook a la ruta de la tabla. El
  `matcher` de la entrada se corrige solo si todos sus hooks son nuestros. Si la entrada
  mezcla hooks ajenos, el `matcher` no se toca y se avisa. Si ya estaba todo así, no se
  cambia nada. Un comando personalizado (barras `/`, `$HOME`) se reescribe con la ruta
  de la tabla y se informa como "ruta actualizada".
- **Si no existe:** se agrega al final de la lista del evento. Si faltan la lista o el
  objeto `hooks`, se crean.
- **Si hay más de una entrada del harness en el mismo evento:** se corrigen todas y se
  avisa del duplicado; no se borra ninguna (*decisión de Claude*: el registro nunca
  borra).
- **Lo demás no se toca:** las otras entradas del evento, los otros eventos y las otras
  claves conservan su contenido y su orden.
- **Escritura:** solo si los datos cambiaron (se comparan los datos, no el texto).
  - Antes de escribir, respaldo con fecha y hora: `settings.json.bak-dd-mm-aaaa-HHMMSS`.
    Los respaldos no se podan (*decisión de Claude*): solo se crean cuando algo
    cambió, que es raro.
  - Se escribe en UTF-8 sin BOM, sin escapar los acentos, con indentación de 2 y saltos
    de línea `\n`, como el archivo actual.
  - La escritura es atómica: archivo temporal y luego reemplazo.
- **Si `settings.json` no existe:** se crea solo con los hooks, sin respaldo.
- **Si `settings.json` no es JSON válido, o no es un objeto:** no se escribe nada, se
  imprime el error con la línea y la columna, y se sale con 1.
- **Salida:** una línea por hook, con "registrado", "ruta actualizada" o "ya estaba",
  más la ruta del respaldo si lo hubo. Exit 0 si todo salió bien.

### `deploy.ps1`

- Deja de hacer el respaldo fijo `settings.json.bak` y de imprimir el bloque para pegar.
- Llama a `python "<repo>\registrar_hooks.py" --settings <...> --hooks-dir <...>`. Si
  sale distinto de 0, el deploy falla con ese mensaje (el harness y el perfil ya
  copiados quedan copiados).
- Nuevo switch `-SinHooks`: no toca `settings.json` e imprime el bloque para pegar
  como hoy, para quien maneje su `settings.json` por su cuenta (*decisión de Claude*,
  pensando en el equipo).

## Documentación

- `README.md` (uso):
  - La instalación queda en un paso: `deploy.ps1` registra los hooks.
  - `-SinHooks` y su bloque manual.
  - `/fase-pausa` y cómo retomar con `/fase fase_N`.
  - `HARNESS_STOP=off` como interruptor de emergencia.
- `docs/tecnico.md`:
  - Fila de `pausar-fase` y nota de que `open-fase` reanuda.
  - Estado `pausada` en "Estados de una fase".
  - `pausas` en el contrato.
  - `registrar_hooks.py` en la estructura del repo.
  - El paso 3 sale de "Pendientes conocidos".
- `test_documentacion` ya exige que el README nombre cada comando y `tecnico.md` cada
  subcomando: `/fase-pausa` y `pausar-fase` entran ahí.

## Pruebas

- `unittest`, como todo el repo. Cada cambio entra con su test escrito primero.
- **M1:**
  - Pausar desde cada estado permitido y rechazo desde los demás.
  - `open-fase` de otra fase y `open-ticket` se rechazan con la fase activa corriendo y
    se permiten con ella pausada.
  - `registrar_fallo` y `aprobar_fase` lanzan en `pausada`.
  - El intento y el historial no cambian al pausar.
  - `open-fase` reanuda al estado previo.
  - `record-veredicto` y `generar-prueba` se rechazan en `pausada`.
  - `Stop` no bloquea en `pausada` ni con `HARNESS_STOP=off`, y sigue bloqueando sin la
    variable.
  - El contrato acepta y rechaza `pausas` y `pausada`.
  - El reporte cuenta las pausas.
- **M2**, con un `settings.json` como el real (hooks de codebase-memory en
  `PostToolUse`, `PreToolUse`, `SessionStart` y `SubagentStart`, más `env`, `model` y
  `enabledPlugins`, con acentos):
  - Registro desde cero.
  - Segunda corrida sin cambios, sin escribir y sin respaldo.
  - Ruta vieja que se actualiza.
  - Nada ajeno cambia.
  - Archivo inexistente.
  - JSON roto intacto con exit 1.
  - Duplicados.
  - Una entrada que mezcla nuestro hook con uno ajeno.
  - Los tests importan `registrar_hooks.py` con un `sys.path.insert` a la raíz, como
    hoy hacen con `harness/hooks`.
  - El respaldo existe solo cuando se escribió.
- **Punta a punta:** `test_punta_a_punta` suma una pausa a mitad de un intento: `Stop`
  deja de bloquear, `/fase` reanuda y el ciclo sigue con el mismo intento.

## Lo que queda al constructor

- Nombres internos, mensajes exactos y cómo se reparte el código entre `cli.py`,
  `lib/state.py` y `report.py`, siguiendo el estilo existente: API en inglés, locales y
  dominio en español, fechas `dd-mm-aaaa`.
- Cómo `deploy.ps1` arma las rutas y propaga el error de Python.
