# Payloads reales de los hooks de Claude Code

> Capturados el 28-07-2026 con `harness/hooks/probe_hook.py` en esta máquina
> (Claude Code sobre Windows 11, Python 3.12). **Los hooks del harness deben usar
> estos nombres de campo, no los asumidos en el plan.**
>
> Cómo re-capturar si algo cambia en una versión futura: registrar `probe_hook.py`
> en `~/.claude/settings.json` para `PostToolUse` y `Stop`, editar cualquier archivo,
> terminar un turno, y leer `probe-out/`.

## `PostToolUse`

```json
{
  "session_id": "80ff9241-df53-46db-9660-bff846460605",
  "transcript_path": "C:\\Users\\<usuario>\\.claude\\projects\\<proyecto>\\<session>.jsonl",
  "cwd": "C:\\ruta\\al\\IA harness",
  "prompt_id": "2c14db29-7597-4918-b9fd-f9e8d89db210",
  "permission_mode": "acceptEdits",
  "effort": { "level": "medium" },
  "hook_event_name": "PostToolUse",
  "tool_name": "Write",
  "tool_input": {
    "file_path": "C:\\...\\disparo-sonda.txt",
    "content": "..."
  },
  "tool_response": {
    "type": "create",
    "filePath": "C:\\...\\disparo-sonda.txt",
    "content": "...",
    "structuredPatch": [],
    "originalFile": null,
    "userModified": false
  },
  "tool_use_id": "toolu_018Gda1c6TzKCx3wJ6QAevcm",
  "duration_ms": 41
}
```

Campos que usa `check_rules.py`:

| Campo | Uso |
|---|---|
| `tool_input.file_path` | Ruta absoluta del archivo tocado. **Confirmado.** |
| `cwd` | Directorio de la sesión. Ver desvío 1 abajo. |
| `hook_event_name`, `tool_name` | Solo informativos; el `matcher` de `settings.json` ya filtra por herramienta |

Notas:

- El payload es el **mismo objeto** para `Write`, `Edit` y `MultiEdit`; `tool_input`
  cambia de forma (`content` vs. `old_string`/`new_string`), pero `file_path` está en
  los tres. El harness solo lee `file_path` y el archivo en disco, así que esa
  diferencia no lo afecta.
- `tool_response.structuredPatch` traería el parche, pero el harness **no** lo usa:
  obtiene el cambio con `git diff`, que refleja el estado real del archivo
  independientemente de cuántas ediciones lo hayan tocado en el turno.
- Los hooks se aplican **sin reiniciar la sesión**: al guardar `settings.json` el
  siguiente evento ya los ejecuta. Esto vale para desarrollo del harness.

## `Stop`

```json
{
  "session_id": "80ff9241-df53-46db-9660-bff846460605",
  "transcript_path": "C:\\Users\\<usuario>\\.claude\\projects\\...\\<session>.jsonl",
  "cwd": "C:\\ruta\\al\\IA harness",
  "prompt_id": "2c14db29-7597-4918-b9fd-f9e8d89db210",
  "permission_mode": "acceptEdits",
  "effort": { "level": "medium" },
  "hook_event_name": "Stop",
  "stop_hook_active": false,
  "last_assistant_message": "…texto completo del último mensaje del asistente…",
  "background_tasks": [],
  "session_crons": []
}
```

Campos que usa `gate_phase.py`:

| Campo | Uso |
|---|---|
| `stop_hook_active` | Indicador de reentrada. **Confirmado**, y con ese nombre exacto. Si es `true`, salir con 0 de inmediato o se produce un bucle |
| `cwd` | Único punto de partida disponible para resolver el proyecto: este payload **no** trae ninguna ruta de archivo |
| `background_tasks` | Si trae un subagente con `status: "running"`, el hook no bloquea. Ver abajo |
| `session_id` | Se compara con la sesión que conduce la fase (`sesion` en `.harness/current.json`). Si son distintas, el hook no bloquea. Ver abajo |

**Qué sesión conduce la fase.** Claude Code le pone a cada comando de shell la
variable `CLAUDE_CODE_SESSION_ID` (comprobado el 27-11-2026: su valor es el mismo
`session_id` que trae el payload de `Stop` de esa sesión). `open-fase` y `run-checks`
la anotan en `current.json`, así que conduce la fase la última sesión que corrió uno
de los dos. El hook solo le exige cerrar el ciclo a esa sesión: una segunda sesión
abierta en el mismo proyecto para consultar algo no tiene ciclo que cerrar, y si
corriera `run-checks` le pisaría la fase a la otra. Si falta cualquiera de los dos
datos (un CLI corrido fuera de Claude Code, un `current.json` anterior), bloquea como
siempre. La variable no está documentada: si una versión futura la quita, el hook
vuelve solo a ese comportamiento.

`background_tasks` con algo corriendo (capturado el 27-11-2026, una entrada por tarea):

```json
[
  { "id": "a1c6734a796fdfbd9", "type": "subagent", "status": "running",
    "description": "Espera de 90 segundos", "agent_type": "general-purpose" },
  { "id": "b322jltpk", "type": "shell", "status": "running",
    "description": "Wait 60 seconds", "command": "python -c \"import time; time.sleep(60)\"" }
]
```

Notas:

- Con un subagente en vuelo el turno termina igual y `Stop` se dispara, aunque el
  agente no tenga nada que hacer salvo esperar. Bloquear ahí solo gasta un turno:
  la sesión se reactiva sola cuando el subagente termina. Por eso `gate_phase.py`
  sale con 0 si alguna tarea es `type: "subagent"` y `status: "running"`.
- Una tarea `type: "shell"` **no** cuenta: una API levantada para la prueba puede
  quedar viva toda la sesión y apagaría el gate. No se capturó ningún otro valor de
  `status`; cualquier cosa distinta de `"running"` bloquea como siempre.

- `last_assistant_message` viene completo. **No usarlo:** juzgar el texto del modelo
  es exactamente el tipo de verificación blanda que el harness reemplaza por estado
  en disco.
- El evento se dispara al terminar el turno del agente principal. Un subagente no
  puede observar el `Stop` de su controlador — por eso la captura de este payload se
  hizo en la sesión principal y no se delegó.

## Desvíos respecto al plan

### 1. El orden de resolución del proyecto estaba invertido (afecta a la Task 9)

El plan proponía `payload.get("cwd") or Path(file_path).parent`. La captura muestra
que **`cwd` es el directorio de la sesión, no el del archivo editado**: en la prueba
se editó un archivo bajo el scratchpad de temporales y `cwd` seguía siendo
la carpeta del repo del harness.

Con el orden del plan, un archivo de otro proyecto —o de fuera de todo proyecto— se
juzgaría con las reglas del proyecto donde arrancó la sesión: falsos positivos, o
peor, aplicar las reglas del stack equivocado.

**Orden correcto:** resolver primero desde el directorio del archivo, y caer a `cwd`
solo si el archivo no está bajo ningún perfil.

```python
raiz = harness.find_project_root(Path(ruta_archivo).parent)
if raiz is None and payload.get("cwd"):
    raiz = harness.find_project_root(payload["cwd"])
```

### 2. `gate_phase.py` no tiene alternativa a `cwd` (afecta a la Task 13)

El payload de `Stop` no incluye ninguna ruta de archivo, así que `cwd` es la única
vía para ubicar el proyecto. No es un problema: el hook `Stop` pregunta por el estado
de la fase activa de la sesión, y la sesión es precisamente lo que `cwd` identifica.
Queda documentado para que nadie intente "arreglarlo" con el desvío 1.
