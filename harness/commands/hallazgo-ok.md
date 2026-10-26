---
description: Aprueba un hallazgo del reflector para que entre a la biblioteca
argument-hint: <id> [fase_N]
---

El usuario aprueba un hallazgo propuesto por el reflector. Sus argumentos: `$ARGUMENTS`

Extrae el id del hallazgo (por ejemplo `h1`) y, si lo dio, la fase (`fase_N`), y córrelo:

```bash
python "$HOME/.claude/hooks/cli.py" resolver-hallazgo --decision ok --id <id> [--fase <fase>]
```

Si falta el id, pídeselo antes de correr nada. Pasa `--fase` solo si el usuario
la dio; sin ella el CLI usa la fase activa de `current.json`.

Reporta la salida del comando tal cual, sin agregar interpretación. Si falla,
muestra el error tal cual. No edites `hallazgos.json` ni la biblioteca a mano: el
CLI es el único que escribe estado. Después de aprobar, sugiere versionar
`.claude/biblioteca/` con el proyecto.
