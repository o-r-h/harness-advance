---
description: Aprueba un hallazgo del reflector con la lección corregida por el humano
argument-hint: <id> "<lección corregida>" [fase_N]
---

El usuario aprueba un hallazgo, pero con la lección corregida. Sus argumentos: `$ARGUMENTS`

Extrae el id del hallazgo, la lección corregida y, si lo dio, la fase (`fase_N`), y córrelo:

```bash
python "$HOME/.claude/hooks/cli.py" resolver-hallazgo --decision editar --id <id> --texto "<texto>" [--fase <fase>]
```

Si falta el id o el texto, pídeselos antes de correr nada. Pasa `--fase` solo si
el usuario la dio; sin ella el CLI usa la fase activa de `current.json`.

Reporta la salida del comando tal cual, sin agregar interpretación. Si falla,
muestra el error tal cual. No edites `hallazgos.json` ni la biblioteca a mano: el
CLI es el único que escribe estado. Después de aprobar, sugiere versionar
`.claude/biblioteca/` con el proyecto.
