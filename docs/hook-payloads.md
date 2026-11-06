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

Notas:

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
